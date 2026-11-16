import re
from dataclasses import dataclass
from pathlib import Path

from app.config import CONTENT_DIR
from app.models import CurriculumKind

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LEVEL_RE = re.compile(r"^(A1|A2|B1|B2|C1)$", re.IGNORECASE)
_KINDS = {k.value for k in CurriculumKind}


@dataclass
class CorpusDoc:
    slug: str
    title: str
    kind: str
    level: str
    body: str
    path: Path


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_document(text: str, path: Path) -> CorpusDoc | None:
    meta: dict[str, str] = {}
    body = text

    match = _FRONTMATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
        body = text[match.end() :]

    title = meta.get("title") or path.stem.replace("-", " ").replace("_", " ").title()
    slug = meta.get("slug") or _slugify(title)
    kind = (meta.get("kind") or "grammar").strip().lower()
    if kind not in _KINDS:
        kind = "grammar"
    level = (meta.get("level") or "A1").strip().upper()
    if not _LEVEL_RE.match(level):
        level = "A1"

    body = body.strip()
    if not body:
        return None

    return CorpusDoc(
        slug=slug,
        title=title,
        kind=kind,
        level=level,
        body=body,
        path=path,
    )


def load_corpus(content_dir: Path | None = None) -> list[CorpusDoc]:
    root = Path(content_dir) if content_dir else CONTENT_DIR
    if not root.exists():
        return []

    docs: list[CorpusDoc] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.upper().startswith("README"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        parsed = parse_document(text, path)
        if parsed:
            docs.append(parsed)

    seen: set[str] = set()
    unique: list[CorpusDoc] = []
    for doc in docs:
        if doc.slug in seen:
            continue
        seen.add(doc.slug)
        unique.append(doc)
    return unique