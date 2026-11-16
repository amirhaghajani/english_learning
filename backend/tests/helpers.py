import json
from collections.abc import Iterator

import numpy as np

from app.audio.wav import write_wav


def pcm_bytes(ms: int = 40, sample_rate: int = 22050) -> bytes:
    n = int(sample_rate * ms / 1000)
    return np.zeros(n, dtype="<i2").tobytes()


def make_wav(duration_ms: int = 500, sample_rate: int = 16000) -> bytes:
    n = int(sample_rate * duration_ms / 1000)
    return write_wav(np.zeros(n, dtype=np.float32), sample_rate)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        if event:
            events.append((event, json.loads(data) if data else {}))
    return events


def sse_order_ok(events: list[tuple[str, dict]]) -> bool:
    names = [name for name, _ in events]
    if not names or names[0] != "meta" or names[-1] != "done":
        return False
    if "corrections" not in names:
        return False
    return "error" not in names or names.index("error") > 0


def audio_chunks(events: list[tuple[str, dict]], index: int) -> list[str]:
    return [data["pcm_b64"] for name, data in events if name == "audio" and data["index"] == index]


def sentence_texts(events: list[tuple[str, dict]]) -> list[str]:
    return [data["text"] for name, data in events if name == "sentence"]


def as_iterator(chunks: list[str]) -> Iterator[str]:
    yield from chunks