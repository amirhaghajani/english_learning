import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.config import ROOT, settings
from app.tutor.feedback import SENTINEL_RE

logger = logging.getLogger(__name__)

_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U0001f000-\U0001f2ff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u2b00-\u2bff]"
)
_MD_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|`{1,3})")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_DASHES = {
    "\u2014": ", ",
    "\u2013": ", ",
    "\u2212": ", ",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2015": ", ",
    "\u2e3a": ", ",
    "\u2e3b": ", ",
    "\uff0d": ", ",
}
_SPACED_DASH_RE = re.compile(r"[ \t]+[-–—―][ \t]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([,.!?;:])")
_WS_RE = re.compile(r"\s+")

DEFAULT_LEXICON: dict[str, str] = {
    "etc.": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
    "vs.": "versus",
    "approx.": "approximately",
    "w/": "with",
    "b/c": "because",
}


@lru_cache
def _load_lexicon() -> dict[str, str]:
    lexicon = dict(DEFAULT_LEXICON)

    path = (
        Path(settings.pronunciation_file)
        if settings.pronunciation_file
        else ROOT / "content" / "pronunciation.json"
    )
    if not path.is_absolute():
        path = ROOT / path

    if path.exists():
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("could not read pronunciation file %s: %s", path, exc)
            return lexicon

        if isinstance(extra, dict):
            for key, value in extra.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue
                if key.strip() and value.strip():
                    lexicon[key.strip()] = value.strip()
        else:
            logger.warning("pronunciation file %s must contain a JSON object", path)

    return lexicon


def _apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    for word, replacement in lexicon.items():
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])")
        if pattern.search(text):
            text = pattern.sub(replacement, text)
    return text


def normalize_for_speech(text: str) -> str:
    """Clean tutor prose into something Piper will pronounce the way it was written."""
    if not text:
        return ""

    cleaned = text

    sentinel = SENTINEL_RE.search(cleaned)
    if sentinel:
        cleaned = cleaned[: sentinel.start()]

    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    cleaned = _MD_HEADING_RE.sub("", cleaned)
    cleaned = _MD_EMPHASIS_RE.sub("", cleaned)

    # A dash is never spoken as punctuation: turn every form into a short pause.
    cleaned = _SPACED_DASH_RE.sub(", ", cleaned)
    for src, dst in _DASHES.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = _SPACED_DASH_RE.sub(", ", cleaned)

    cleaned = _EMOJI_RE.sub("", cleaned)
    cleaned = _apply_lexicon(cleaned, _load_lexicon())
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()

    return cleaned