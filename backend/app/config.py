from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models"
CONTENT_DIR = ROOT / "content"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/emma"

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_api_key: str = ""

    stt_backend: str = "whisper"
    whisper_model: str = "small.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_load_timeout: float = 120.0
    fake_transcript: str = ""

    tts_backend: str = "piper"
    piper_model: str = "en_US-lessac-medium"
    piper_models_dir: str = "models"
    piper_speech_speed: float = 1.0
    piper_sample_rate: int = 22050
    pronunciation_file: str = ""

    embedding_model: str = "bge-m3"
    rag_top_k: int = 3
    rag_min_score: float = 0.0
    rag_enabled: bool = True

    emma_name: str = "Emma"
    emma_voice_locale: str = "en-US"
    emma_variant: str = "American English"

    max_speak_chars: int = 220
    history_turns: int = 12
    max_corrections: int = 3

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def piper_model_path(self) -> Path:
        candidate = Path(self.piper_model)
        if candidate.suffix == ".onnx":
            return candidate
        models_dir = Path(self.piper_models_dir)
        if not models_dir.is_absolute():
            models_dir = ROOT / models_dir
        return models_dir / f"{self.piper_model}.onnx"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()