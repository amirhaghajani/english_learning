import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.prompt import RetrievedDoc
from app.models import Correction, CorrectionCategory, CurriculumDoc, CurriculumKind, Session, Turn
from app.rag.corpus import CorpusDoc, load_corpus

logger = logging.getLogger(__name__)

TABLE_NAME = "emma_curriculum"
EMBED_DIM = 1024
LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5}
_STOPWORDS = {
    "the", "and", "for", "you", "your", "that", "this", "with", "have", "has", "was",
    "were", "are", "but", "not", "they", "them", "then", "than", "what", "when", "where",
    "which", "who", "how", "why", "can", "could", "would", "should", "about", "into",
    "from", "there", "here", "just", "like", "some", "any", "did", "does", "doing",
    "yesterday", "today", "tomorrow", "store", "went", "bought",
}
_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _terms(query: str, limit: int = 12) -> list[str]:
    tokens = _TOKEN_RE.findall((query or "").lower())
    out: list[str] = []
    for token in tokens:
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token not in out:
            out.append(token)
    return out[:limit]


def allowed_levels(max_level: str) -> list[str]:
    ceiling = LEVEL_ORDER.get((max_level or "A1").upper(), 3)
    return [lv for lv, rank in LEVEL_ORDER.items() if rank <= ceiling]


def _doc_from_row(row: CurriculumDoc, score: float) -> RetrievedDoc:
    return RetrievedDoc(
        title=row.title,
        body=row.body,
        kind=row.kind.value if isinstance(row.kind, CurriculumKind) else str(row.kind),
        level=row.level,
        score=score,
    )


@dataclass
class IngestOutcome:
    documents: int = 0
    upserted: int = 0
    skipped: int = 0
    embedded: int = 0
    backend: str = "none"
    warnings: list[str] = field(default_factory=list)


class CurriculumRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.backend = "keyword"
        self.warnings: list[str] = []
        self._vector = None

    def _db_url(self):
        return make_url(settings.database_url)

    def _vector_handles(self):
        if self._vector is not None:
            return self._vector
        if settings.is_sqlite:
            raise RuntimeError("pgvector retrieval requires Postgres; using keyword fallback")
        if not settings.rag_enabled:
            raise RuntimeError("RAG is disabled by configuration")

        from llama_index.core import VectorStoreIndex
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.vector_stores.postgres import PGVectorStore

        url = self._db_url()
        store = PGVectorStore.from_params(
            database=url.database,
            host=url.host or "127.0.0.1",
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            table_name=TABLE_NAME,
            embed_dim=EMBED_DIM,
        )
        embed = OllamaEmbedding(
            model_name=settings.embedding_model,
            base_url=settings.ollama_base_url,
            request_timeout=120.0,
        )
        index = VectorStoreIndex.from_vector_store(store, embed_model=embed)
        self._vector = (store, embed, index)
        return self._vector

    async def search(
        self, query: str, top_k: int | None = None, max_level: str = "C1"
    ) -> list[RetrievedDoc]:
        k = top_k or settings.rag_top_k
        levels = allowed_levels(max_level)

        try:
            docs = self._vector_search(query, k, levels)
            self.backend = "pgvector"
            return docs
        except Exception as exc:  # noqa: BLE001
            if not self.warnings:
                self.warnings.append(f"pgvector retrieval unavailable: {exc}")
            logger.warning("pgvector retrieval unavailable, falling back to keyword: %s", exc)

        self.backend = "keyword"
        return await self._keyword_search(query, k, levels)

    def _vector_search(self, query: str, k: int, levels: list[str]) -> list[RetrievedDoc]:
        _store, _embed, index = self._vector_handles()
        retriever = index.as_retriever(similarity_top_k=max(k * 4, k))
        nodes = retriever.retrieve(query)

        docs: list[RetrievedDoc] = []
        for node in nodes:
            meta = node.node.metadata or {}
            level = str(meta.get("level", "A1")).upper()
            if level not in levels:
                continue
            score = getattr(node, "score", None)
            docs.append(
                RetrievedDoc(
                    title=str(meta.get("title") or node.node.get_content()[:80]),
                    body=node.node.get_content(),
                    kind=str(meta.get("kind") or "grammar"),
                    level=level,
                    score=float(score) if score is not None else 0.0,
                )
            )
        docs.sort(key=lambda d: -d.score)
        return docs[:k]

    async def _keyword_search(
        self, query: str, k: int, levels: list[str]
    ) -> list[RetrievedDoc]:
        terms = _terms(query)
        stmt = select(CurriculumDoc).where(CurriculumDoc.level.in_(levels))
        rows = list((await self.db.execute(stmt)).scalars().all())
        if not rows:
            return []

        scored: list[tuple[float, CurriculumDoc]] = []
        for row in rows:
            haystack = f"{row.title} {row.body}".lower()
            if not terms:
                score = 0.0
            else:
                hits = sum(1 for term in terms if term in haystack)
                score = hits / len(terms)
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda pair: -pair[0])
        if not scored:
            return []
        return [_doc_from_row(row, round(score, 4)) for score, row in scored[:k]]

    async def recurring_errors(self, learner_id: int, limit: int = 5) -> list[dict]:
        stmt = (
            select(
                Correction.category,
                Correction.said,
                Correction.replacement,
                func.count(Correction.id).label("hits"),
            )
            .join(Turn, Turn.id == Correction.turn_id)
            .join(Session, Session.id == Turn.session_id)
            .where(Session.learner_id == learner_id)
            .group_by(Correction.category, Correction.said, Correction.replacement)
            .order_by(func.count(Correction.id).desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        out: list[dict] = []
        for category, said, replacement, hits in rows:
            value = category.value if isinstance(category, CorrectionCategory) else str(category)
            out.append(
                {
                    "category": value,
                    "said": said,
                    "replacement": replacement,
                    "count": int(hits),
                }
            )
        return out

    async def ingest(
        self, docs: list[CorpusDoc] | None = None, content_dir: Path | None = None
    ) -> IngestOutcome:
        corpus = docs if docs is not None else load_corpus(content_dir)
        outcome = IngestOutcome(documents=len(corpus), backend=self.backend)

        for doc in corpus:
            existing = (
                await self.db.execute(
                    select(CurriculumDoc).where(CurriculumDoc.slug == doc.slug)
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = CurriculumDoc(slug=doc.slug)
                self.db.add(existing)
            existing.title = doc.title
            existing.kind = CurriculumKind(doc.kind)
            existing.level = doc.level
            existing.body = doc.body
        await self.db.flush()

        outcome.upserted = len(corpus)

        try:
            embedded = await self._embed_into_vector(list(corpus))
            outcome.embedded = embedded
            outcome.backend = "pgvector"
            self.backend = "pgvector"
        except Exception as exc:  # noqa: BLE001
            outcome.backend = "keyword"
            self.backend = "keyword"
            outcome.warnings.append(f"vector ingest skipped: {exc}")
            logger.warning("vector ingest skipped: %s", exc)

        return outcome

    async def _embed_into_vector(self, corpus: list[CorpusDoc]) -> int:
        if settings.is_sqlite or not settings.rag_enabled:
            raise RuntimeError("vector ingest needs Postgres and RAG_ENABLED=true")

        store, embed, index = self._vector_handles()
        if not corpus:
            return 0

        from llama_index.core.schema import TextNode

        texts = [f"{doc.title}\n\n{doc.body}" for doc in corpus]
        vectors = embed.get_text_embedding_batch(texts)

        await self.db.execute(text(f'DELETE FROM "{TABLE_NAME}"'))

        nodes = []
        for doc, vector in zip(corpus, vectors, strict=True):
            nodes.append(
                TextNode(
                    text=f"{doc.title}\n\n{doc.body}",
                    embedding=vector,
                    metadata={
                        "slug": doc.slug,
                        "title": doc.title,
                        "kind": doc.kind,
                        "level": doc.level,
                    },
                )
            )
        index.insert_nodes(nodes)
        await self._store_curriculum_vectors(corpus, vectors)
        return len(nodes)

    async def _store_curriculum_vectors(
        self, corpus: list[CorpusDoc], vectors: list[list[float]]
    ) -> None:
        if settings.is_sqlite:
            return
        try:
            for doc, vector in zip(corpus, vectors, strict=True):
                literal = "[" + ",".join(f"{float(v):.6f}" for v in vector) + "]"
                await self.db.execute(
                    text(
                        "UPDATE curriculum_doc SET embedding = CAST(:vec AS vector) "
                        "WHERE slug = :slug"
                    ),
                    {"vec": literal, "slug": doc.slug},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not persist curriculum embeddings: %s", exc)

    def status(self) -> tuple[str, str]:
        if settings.is_sqlite:
            return "keyword", "sqlite detected; keyword retrieval over curriculum_doc"
        if not settings.rag_enabled:
            return "keyword", "RAG disabled by configuration"
        try:
            self._vector_handles()
            return "pgvector", f"{TABLE_NAME} via bge-m3 ({settings.embedding_model})"
        except Exception as exc:  # noqa: BLE001
            return "keyword", f"pgvector unavailable: {exc}"