import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CONTENT_DIR
from app.models import Scenario
from app.rag.corpus import _slugify

logger = logging.getLogger(__name__)

_SCENARIO_FIELDS = (
    "setting",
    "learner_role",
    "emma_role",
    "opening_line",
    "target_language",
    "success_criteria",
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    meta: dict[str, str] = {}
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return meta


def load_scenarios(scenario_dir: Path | None = None) -> list[dict]:
    root = Path(scenario_dir) if scenario_dir else CONTENT_DIR / "scenarios"
    if not root.exists():
        return []

    out: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = _parse_frontmatter(text)
        if not meta:
            continue
        title = meta.get("title") or path.stem.replace("-", " ").title()
        slug = meta.get("slug") or _slugify(title)
        out.append(
            {
                "slug": slug,
                "title": title,
                "level": (meta.get("level") or "A1").upper(),
                "setting": meta.get("setting", ""),
                "learner_role": meta.get("learner_role", ""),
                "emma_role": meta.get("emma_role", ""),
                "opening_line": meta.get("opening_line", ""),
                "target_language": meta.get("target_language", ""),
                "success_criteria": meta.get("success_criteria", ""),
            }
        )
    return out


async def seed_scenarios(db: AsyncSession, scenario_dir: Path | None = None) -> int:
    rows = load_scenarios(scenario_dir)
    if not rows:
        logger.info("no scenario files found under content/scenarios")
        return 0

    seeded = 0
    for row in rows:
        existing = (
            await db.execute(select(Scenario).where(Scenario.slug == row["slug"]))
        ).scalar_one_or_none()
        if existing is None:
            db.add(Scenario(**row))
            seeded += 1
            continue
        for field in ("title", "level", *_SCENARIO_FIELDS):
            setattr(existing, field, row[field])
    await db.commit()
    logger.info("seeded %d new scenarios (%d total)", seeded, len(rows))
    return seeded


def seed_scenarios_standalone() -> int:
    import asyncio

    from app.db import SessionFactory

    async def _run() -> int:
        async with SessionFactory() as session:
            return await seed_scenarios(session)

    return asyncio.run(_run())