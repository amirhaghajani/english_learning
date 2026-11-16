import re

_TERMINATORS = ".!?"
_CLOSERS = "\"'”’)]}"
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "eg",
    "ie",
    "approx",
    "dept",
    "u.s",
    "u.k",
    "a.m",
    "p.m",
}
_TOKEN_RE = re.compile(r"[A-Za-z.]+$")
_DOTTED_INITIAL_RE = re.compile(r"(?:\b[A-Za-z]\.)+$")
_WS_RE = re.compile(r"[ \t]+")


def _trailing_token(text: str) -> str:
    match = _TOKEN_RE.search(text)
    return match.group(0) if match else ""


def _is_abbreviation(prefix: str) -> bool:
    candidate = prefix + "."
    if _DOTTED_INITIAL_RE.search(candidate):
        return True
    return _trailing_token(candidate).rstrip(".").lower() in _ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences on `.?!` and newlines, tolerating abbreviations."""
    if not text:
        return []

    out: list[str] = []
    buf: list[str] = []
    i = 0
    length = len(text)

    def flush() -> None:
        sentence = _WS_RE.sub(" ", "".join(buf)).strip()
        if sentence:
            out.append(sentence)
        buf.clear()

    while i < length:
        ch = text[i]

        if ch == "\n":
            flush()
            i += 1
            continue

        if ch in _TERMINATORS:
            prefix = "".join(buf)
            j = i
            while j < length and text[j] in _TERMINATORS:
                j += 1
            while j < length and text[j] in _CLOSERS:
                j += 1
            buf.append(text[i:j])
            i = j

            if _is_abbreviation(prefix):
                continue
            if prefix[-1:].isdigit() and j < length and text[j].isdigit():
                continue
            flush()
            continue

        buf.append(ch)
        i += 1

    flush()
    return out


def strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if "```" not in cleaned:
        return cleaned
    kept = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
    return "\n".join(kept).strip()