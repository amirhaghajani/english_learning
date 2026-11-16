from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionFactory
from app.models import CurriculumDoc, CurriculumKind
from app.rag.corpus import load_corpus, parse_document
from app.rag.index import CurriculumRetriever, allowed_levels

DOCS = [
    ("past-simple", "Past simple", "grammar", "B1", "I went to the store yesterday."),
    ("articles", "Articles", "grammar", "A2", "Use a or an for one of many things."),
    ("phrasal", "Phrasal verbs", "usage", "B1", "Put off means postpone."),
    ("nuance", "Nuance and register", "usage", "C1", "Hedging and subtle understatement."),
]


async def _seed() -> None:
    async with SessionFactory() as session:
        for slug, title, kind, level, body in DOCS:
            session.add(
                CurriculumDoc(
                    slug=slug,
                    title=title,
                    kind=CurriculumKind(kind),
                    level=level,
                    body=body,
                )
            )
        await session.commit()


def test_allowed_levels():
    assert allowed_levels("A1") == ["A1"]
    assert allowed_levels("B1") == ["A1", "A2", "B1"]
    assert allowed_levels("C1") == ["A1", "A2", "B1", "B2", "C1"]
    assert allowed_levels("nonsense") == ["A1", "A2", "B1"]


@pytest.mark.asyncio
async def test_keyword_search_finds_matching_doc():
    await _seed()
    async with SessionFactory() as session:
        retriever = CurriculumRetriever(session)
        docs = await retriever.search("put off postpone", top_k=3, max_level="C1")
        assert retriever.backend == "keyword"
        assert docs, "expected at least one keyword match"


@pytest.mark.asyncio
async def test_keyword_search_filters_by_level():
    await _seed()
    async with SessionFactory() as session:
        retriever = CurriculumRetriever(session)
        docs = await retriever.search("articles a an the", top_k=5, max_level="A1")
        for doc in docs:
            assert doc.level == "A1"


@pytest.mark.asyncio
async def test_recurring_errors_grouped_by_category():
    from app.models import Correction, CorrectionCategory, Learner, Session, Turn

    async with SessionFactory() as session:
        learner = Learner(name="Recur", goals="")
        session.add(learner)
        await session.flush()

        sess = Session(learner_id=learner.id, mode="free")
        session.add(sess)
        await session.flush()

        turn = Turn(session_id=sess.id, seq=1, transcript="I go yesterday")
        session.add(turn)
        await session.flush()

        for _ in range(2):
            session.add(
                Correction(
                    turn_id=turn.id,
                    said="I go",
                    replacement="I went",
                    category=CorrectionCategory.grammar,
                )
            )
        session.add(
            Correction(
                turn_id=turn.id,
                said="I has",
                replacement="I have",
                category=CorrectionCategory.grammar,
            )
        )
        await session.commit()

        retriever = CurriculumRetriever(session)
        rows = await retriever.recurring_errors(learner.id)
        assert rows[0]["said"] == "I go"
        assert rows[0]["count"] == 2


def test_load_corpus_reads_repo_content():
    docs = load_corpus()
    assert len(docs) >= 20
    slugs = {doc.slug for doc in docs}
    assert "present-perfect-vs-past-simple" in slugs
    assert "at-the-coffee-shop" in slugs
    assert all(doc.level in {"A1", "A2", "B1", "B2", "C1"} for doc in docs)


def test_parse_document_handles_missing_frontmatter(tmp_path: Path):
    path = tmp_path / "loose-note.md"
    path.write_text("Just a body without a header.\n", encoding="utf-8")
    doc = parse_document("Just a body without a header.\n", path)
    assert doc is not None
    assert doc.title == "Loose Note"
    assert doc.level == "A1"


def test_parse_document_rejects_empty_body(tmp_path: Path):
    path = tmp_path / "empty.md"
    assert parse_document("---\ntitle: Empty\n---\n\n", path) is None


@pytest.mark.asyncio
async def test_ingest_writes_curriculum_rows():
    async with SessionFactory() as session:
        retriever = CurriculumRetriever(session)
        outcome = await retriever.ingest()
        assert outcome.documents >= 20
        assert outcome.upserted == outcome.documents

        rows = list(
            (await session.execute(select(CurriculumDoc))).scalars().all()
        )
        assert len(rows) == outcome.upserted
        assert all(row.level in {"A1", "A2", "B1", "B2", "C1"} for row in rows)