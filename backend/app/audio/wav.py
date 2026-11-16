import io
import wave
from dataclasses import dataclass

import numpy as np

TARGET_RATE = 16000


@dataclass
class WavData:
    samples: np.ndarray
    sample_rate: int
    duration_ms: int
    channels: int


def read_wav(data: bytes) -> WavData:
    if not data:
        raise ValueError("empty audio payload")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            raw = wav.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a readable WAV file: {exc}") from exc

    if width != 2:
        raise ValueError(f"expected 16-bit PCM WAV, got {width * 8}-bit")
    if rate <= 0 or frames <= 0:
        raise ValueError("WAV has no audio frames")

    pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        usable = (len(pcm) // channels) * channels
        pcm = pcm[:usable].reshape(-1, channels).mean(axis=1)

    return WavData(
        samples=pcm,
        sample_rate=rate,
        duration_ms=int(round(frames / rate * 1000)),
        channels=channels,
    )


def resample_to_16k(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    if sample_rate == TARGET_RATE or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    duration = samples.size / float(sample_rate)
    target_len = max(1, int(round(duration * TARGET_RATE)))
    source_idx = np.linspace(0.0, samples.size - 1, num=target_len)
    resampled = np.interp(source_idx, np.arange(samples.size), samples)
    return resampled.astype(np.float32)


def to_model_input(data: WavData) -> np.ndarray:
    return resample_to_16k(data.samples, data.sample_rate)


def write_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()


def write_wav_16k(samples: np.ndarray) -> bytes:
    return write_wav(samples, TARGET_RATE)


def silence(duration_ms: int, sample_rate: int = 22050) -> bytes:
    n = int(sample_rate * duration_ms / 1000)
    return write_wav(np.zeros(n, dtype=np.float32), sample_rate)