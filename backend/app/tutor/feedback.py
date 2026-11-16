import json
import logging
import re
from dataclasses import dataclass, field

from app.models import CorrectionCategory, CorrectionSeverity
from app.tutor.sentences import strip_markdown_fences

logger = logging.getLogger(__name__)

SENTINEL_RE = re.compile(r"\[\[\s*CORRECTIONS\s*\]\]", re.IGNORECASE)

_CATEGORIES = {c.value for c in CorrectionCategory}
_SEVERITIES = {s.value for s in CorrectionSeverity}
_SEVERITY_RANK = {CorrectionSeverity.minor.value: 0, CorrectionSeverity.major.value: 1}
_TOKEN_RE = re.compile(r"[a-z0-9']+")


@dataclass
class ParsedCorrection:
    said: str
    replacement: str
    category: str = CorrectionCategory.grammar.value
    why: str = ""
    severity: str = CorrectionSeverity.minor.value
    order: int = field(default=0)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def extract_json_array(text: str) -> str | None:
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _coerce_category(value: object) -> str:
    if isinstance(value, str) and value.strip().lower() in _CATEGORIES:
        return value.strip().lower()
    return CorrectionCategory.grammar.value


def _coerce_severity(value: object) -> str:
    if isinstance(value, str) and value.strip().lower() in _SEVERITIES:
        return value.strip().lower()
    return CorrectionSeverity.minor.value


def is_grounded(said: str, transcript: str) -> bool:
    said_norm = _normalise(said).lower()
    if not said_norm:
        return False
    transcript_norm = _normalise(transcript).lower()
    if said_norm in transcript_norm:
        return True
    tokens = [t for t in _TOKEN_RE.findall(said_norm) if len(t) > 2]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in transcript_norm)
    return hits > 0


def parse_correction_items(raw_items: object, *, limit: int = 3) -> list[ParsedCorrection]:
    if not isinstance(raw_items, list):
        return []

    parsed: list[ParsedCorrection] = []
    seen: set[tuple[str, str]] = set()

    for order, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        said = _normalise(str(item.get("said") or ""))
        replacement = _normalise(str(item.get("replacement") or ""))
        if not said or not replacement:
            continue
        if said.lower() == replacement.lower():
            continue
        key = (said.lower(), replacement.lower())
        if key in seen:
            continue
        seen.add(key)
        parsed.append(
            ParsedCorrection(
                said=said,
                replacement=replacement,
                category=_coerce_category(item.get("category")),
                why=_normalise(str(item.get("why") or "")),
                severity=_coerce_severity(item.get("severity")),
                order=order,
            )
        )

    if limit and len(parsed) > limit:
        parsed = sorted(parsed, key=lambda c: -_SEVERITY_RANK[c.severity])[:limit]
        parsed = sorted(parsed, key=lambda c: c.order)
    return parsed


def parse_corrections(
    raw: str, *, limit: int = 3, ground_against: str | None = None
) -> list[ParsedCorrection]:
    if not raw:
        return []

    match = SENTINEL_RE.search(raw)
    if not match:
        return []

    tail = raw[match.end() :]
    payload = extract_json_array(tail)
    if payload is None:
        logger.warning("corrections sentinel found but no JSON array followed")
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.warning("dropping malformed corrections JSON: %s", exc)
        return []

    items = parse_correction_items(data, limit=limit)
    if ground_against is not None:
        items = [c for c in items if is_grounded(c.said, ground_against)]
    return items


def split_reply(
    raw: str, *, limit: int = 3, ground_against: str | None = None
) -> tuple[str, list[ParsedCorrection]]:
    text = strip_markdown_fences(raw or "")
    match = SENTINEL_RE.search(text)
    if not match:
        return text, []

    prose = text[: match.start()].strip()
    corrections = parse_corrections(
        text[match.start() :], limit=limit, ground_against=ground_against
    )
    return prose, corrections


def to_dict(item: ParsedCorrection) -> dict:
    return {
        "said": item.said,
        "replacement": item.replacement,
        "category": item.category,
        "why": item.why,
        "severity": item.severity,
    }