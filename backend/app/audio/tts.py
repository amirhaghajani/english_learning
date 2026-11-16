import io
import logging
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import numpy as np

from app.audio.wav import silence
from app.config import ROOT, settings

logger = logging.getLogger(__name__)

_DOWNLOAD_HINT = (
    "Piper voice '{model}' is missing. Download it with:\n"
    "    python -m piper.download_voices {model} --data-dir {dir}\n"
    "or set PIPER_MODEL to a voice you already have."
)


class SpeechSynth(Protocol):
    name: str
    model_id: str
    sample_rate: int

    def synthesize(self, text: str) -> Iterator[bytes]: ...

    def probe(self) -> tuple[bool, str]: ...


def _piper_command() -> list[str]:
    explicit = shutil.which("piper")
    if explicit:
        return [explicit]
    return [sys.executable, "-m", "piper"]


class PiperTTS:
    name = "piper"

    def __init__(
        self,
        model: str | None = None,
        models_dir: str | None = None,
        length_scale: float | None = None,
        chunk_ms: int = 120,
    ) -> None:
        self.model = model or settings.piper_model
        self.models_dir = Path(models_dir or settings.piper_models_dir)
        if not self.models_dir.is_absolute():
            self.models_dir = ROOT / self.models_dir
        self.model_path = self._resolve_model(self.model)
        self.length_scale = length_scale or settings.piper_speech_speed
        self.chunk_ms = chunk_ms
        self.sample_rate = settings.piper_sample_rate
        self.model_id = self.model

    def _resolve_model(self, model: str) -> Path:
        candidate = Path(model)
        if candidate.suffix == ".onnx" and candidate.exists():
            return candidate
        direct = self.models_dir / f"{model}.onnx"
        if direct.exists():
            return direct
        raise RuntimeError(
            _DOWNLOAD_HINT.format(model=model, dir=self.models_dir)
        )

    def _run(self, text: str) -> bytes:
        try:
            import piper  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "The 'piper-tts' package is not installed. "
                "Install it with `uv sync --extra tts`."
            ) from exc
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.wav"
            cmd = [
                *_piper_command(),
                "-m",
                str(self.model_path),
                "-f",
                str(out_path),
                "--length-scale",
                str(self.length_scale),
            ]
            proc = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=False,
            )
            if not out_path.exists():
                detail = (proc.stderr or proc.stdout or "").strip()[:600]
                raise RuntimeError(f"Piper failed for text {text!r}: {detail}")
            return out_path.read_bytes()

    def _pcm(self, wav_bytes: bytes) -> tuple[bytes, int]:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            if wav.getsampwidth() != 2:
                raise RuntimeError("Piper returned non 16-bit audio")
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        self.sample_rate = rate
        return frames, rate

    def synthesize(self, text: str) -> Iterator[bytes]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        try:
            wav_bytes = self._run(cleaned)
            pcm, rate = self._pcm(wav_bytes)
        except RuntimeError:
            raise
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Piper timed out on {text!r}") from exc

        if not pcm:
            return
        samples = np.frombuffer(pcm, dtype="<i2")
        chunk = max(1, int(rate * self.chunk_ms / 1000))
        for start in range(0, samples.size, chunk):
            yield samples[start : start + chunk].tobytes()

    def probe(self) -> tuple[bool, str]:
        if not self.model_path.exists():
            return False, _DOWNLOAD_HINT.format(model=self.model, dir=self.models_dir)
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts is not installed (uv sync --extra tts)"
        return True, f"{self.model} at {self.model_path.name}"


class FakeTTS:
    name = "fake"

    def __init__(self, model_id: str = "fake", sample_rate: int = 22050) -> None:
        self.model_id = model_id
        self.sample_rate = sample_rate

    def synthesize(self, text: str) -> Iterator[bytes]:
        if not text.strip():
            return
        yield silence(140, self.sample_rate)

    def probe(self) -> tuple[bool, str]:
        return True, "fake TTS"


def build_tts() -> SpeechSynth:
    backend = (settings.tts_backend or "piper").strip().lower()
    if backend in {"fake", "none"}:
        return FakeTTS()
    return PiperTTS()


_tts: SpeechSynth | None = None


def get_tts() -> SpeechSynth:
    global _tts
    if _tts is None:
        _tts = build_tts()
        logger.info("TTS ready: %s (%s)", _tts.name, _tts.model_id)
    return _tts


def reset_tts() -> None:
    global _tts
    _tts = None