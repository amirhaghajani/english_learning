import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from app.config import settings

os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "15")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

logger = logging.getLogger(__name__)

_NO_SPEECH_PROB = 0.6
_LOW_LOGPROB = -1.2
_MIN_CHARS = 2


@dataclass
class Transcription:
    text: str
    language: str = "en"
    no_speech: bool = False
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0
    duration_s: float = 0.0
    segments: list[dict] = field(default_factory=list)


class SpeechToText(Protocol):
    name: str
    model_id: str

    def transcribe(self, samples: np.ndarray) -> Transcription: ...

    def probe(self) -> tuple[bool, str]: ...


class WhisperSTT:
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self.model_size = model_size or settings.whisper_model
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self.model_id = self.model_size
        self.load_timeout = settings.whisper_load_timeout
        self._model = None
        self._load_error: str | None = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if self._load_error:
            raise RuntimeError(self._load_error)
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            self._load_error = (
                "faster-whisper is not installed. Run `uv sync` from backend/."
            )
            raise RuntimeError(self._load_error) from exc

        holder: dict = {}

        def _load() -> None:
            try:
                holder["model"] = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except BaseException as exc:  # noqa: BLE001
                holder["error"] = exc

        thread = threading.Thread(target=_load, name="whisper-load", daemon=True)
        thread.start()
        thread.join(self.load_timeout)

        if thread.is_alive():
            self._load_error = (
                f"Loading Whisper model '{self.model_size}' timed out after "
                f"{self.load_timeout:.0f}s. The first run downloads the model, so check that "
                "huggingface.co is reachable or point WHISPER_MODEL at a local model folder."
            )
            raise RuntimeError(self._load_error)

        if "error" in holder:
            self._load_error = (
                f"Could not load Whisper model '{self.model_size}': {holder['error']}. "
                "The first run downloads it, so check your network connection or set "
                "WHISPER_MODEL to a local model directory."
            )
            raise RuntimeError(self._load_error)

        self._model = holder["model"]
        return self._model

    def transcribe(self, samples: np.ndarray) -> Transcription:
        model = self._ensure_model()
        audio = np.asarray(samples, dtype=np.float32)
        if audio.size == 0:
            return Transcription(text="", no_speech=True)
        duration = audio.size / 16000.0
        segments, info = model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=False,
            condition_on_previous_text=False,
            word_timestamps=False,
        )
        collected: list[dict] = []
        text_parts: list[str] = []
        logprobs: list[float] = []
        no_speech_probs: list[float] = []
        for seg in segments:
            text_parts.append(seg.text)
            logprobs.append(float(getattr(seg, "avg_logprob", 0.0)))
            no_speech_probs.append(float(getattr(seg, "no_speech_prob", 0.0)))
            collected.append(
                {
                    "start": getattr(seg, "start", 0.0),
                    "end": getattr(seg, "end", 0.0),
                    "text": getattr(seg, "text", ""),
                }
            )

        text = " ".join(part.strip() for part in text_parts if part).strip()
        avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0.0
        max_no_speech = max(no_speech_probs) if no_speech_probs else 0.0

        no_speech = (
            len(text) < _MIN_CHARS
            or max_no_speech > _NO_SPEECH_PROB
            or (bool(text) and avg_logprob < _LOW_LOGPROB)
        )

        return Transcription(
            text=text,
            language=getattr(info, "language", "en") or "en",
            no_speech=no_speech,
            no_speech_prob=max_no_speech,
            avg_logprob=avg_logprob,
            duration_s=duration,
            segments=collected,
        )

    def probe(self) -> tuple[bool, str]:
        if self._load_error:
            return False, self._load_error
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed (uv sync from backend/)"
        local = Path(self.model_size)
        if local.exists() and not local.is_dir():
            return False, f"WHISPER_MODEL points at a file, expected a folder: {local}"
        if local.is_dir() and not (local / "model.bin").exists():
            return False, f"{local} is not a faster-whisper model folder (no model.bin)"
        return True, f"{self.model_size} on {self.device}/{self.compute_type} (loads on first turn)"


class FakeSTT:
    name = "fake"

    def __init__(self, transcript: str | None = None, model_id: str = "fake") -> None:
        source = transcript if transcript is not None else settings.fake_transcript
        self.transcript = source.strip()
        self.model_id = model_id

    def transcribe(self, samples: np.ndarray) -> Transcription:
        text = self.transcript.strip()
        return Transcription(
            text=text,
            no_speech=not text,
            avg_logprob=-0.1 if text else -3.0,
        )

    def probe(self) -> tuple[bool, str]:
        return True, "fake STT"


def build_stt() -> SpeechToText:
    backend = (settings.stt_backend or "whisper").strip().lower()
    if backend in {"fake", "none"}:
        return FakeSTT()
    return WhisperSTT()


_stt: SpeechToText | None = None


def get_stt() -> SpeechToText:
    global _stt
    if _stt is None:
        _stt = build_stt()
        logger.info("STT ready: %s (%s)", _stt.name, _stt.model_id)
    return _stt


def reset_stt() -> None:
    global _stt
    _stt = None