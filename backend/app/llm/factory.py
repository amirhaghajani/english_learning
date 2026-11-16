from functools import lru_cache

from app.config import settings
from app.llm.base import LLMError, TutorLLM
from app.llm.ollama import OllamaLLM
from app.llm.openrouter import OpenRouterLLM


@lru_cache
def get_llm() -> TutorLLM:
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider == "openrouter":
        return OpenRouterLLM()
    if provider == "ollama":
        return OllamaLLM()
    raise LLMError(
        "llm_unknown_provider",
        f"LLM_PROVIDER='{settings.llm_provider}' is not supported. Use 'ollama' or 'openrouter'.",
        status_code=500,
    )


def reset_llm_cache() -> None:
    get_llm.cache_clear()