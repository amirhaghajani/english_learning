import json
from collections.abc import Iterator

import httpx

from app.config import settings
from app.llm.base import LLMError, ReplyRequest

_OPENROUTER_HINT = (
    "OpenRouter request failed. Set OPENROUTER_API_KEY in .env and check the model id "
    "'{model}' at https://openrouter.ai/models."
)


class OpenRouterLLM:
    name = "openrouter"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.model = model or settings.openrouter_model
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.timeout = timeout

    def _headers(self) -> dict:
        if not self.api_key:
            raise LLMError(
                "llm_unconfigured",
                "OPENROUTER_API_KEY is empty. Add it to .env or switch LLM_PROVIDER=ollama.",
                status_code=503,
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "emma-english-tutor",
        }

    def stream(self, req: ReplyRequest) -> Iterator[str]:
        payload: dict = {
            "model": self.model,
            "stream": True,
            "temperature": req.temperature,
            "messages": [{"role": "system", "content": req.system}]
            + [{"role": m.role, "content": m.content} for m in req.messages],
        }
        if req.max_tokens:
            payload["max_tokens"] = req.max_tokens
        if req.repetition_penalty:
            payload["presence_penalty"] = round(max(0.0, req.repetition_penalty - 1.0), 3)

        headers = self._headers()
        try:
            with httpx.Client(timeout=self.timeout) as client, client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as resp:
                if resp.status_code in (401, 403):
                    raise LLMError(
                        "llm_unauthorized",
                        "OpenRouter rejected the API key. Check OPENROUTER_API_KEY.",
                        status_code=503,
                    )
                if resp.status_code == 404:
                    raise LLMError(
                        "model_missing",
                        f"OpenRouter has no model '{self.model}'.",
                        status_code=503,
                    )
                if resp.status_code == 429:
                    raise LLMError(
                        "llm_rate_limited",
                        "OpenRouter rate limit reached; wait a moment and retry.",
                        status_code=429,
                    )
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", "replace")[:500]
                    raise LLMError(
                        "llm_unreachable",
                        f"OpenRouter returned {resp.status_code}: {body}",
                        status_code=503,
                    )
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise LLMError(
                            "llm_error", str(chunk["error"]), status_code=502
                        )
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content") or ""
                        if piece:
                            yield piece
        except httpx.ConnectError as exc:
            raise LLMError(
                "llm_unreachable",
                _OPENROUTER_HINT.format(model=self.model),
                status_code=503,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                "llm_unreachable", f"OpenRouter request failed: {exc}", 503
            ) from exc

    def probe(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "OPENROUTER_API_KEY is not set"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.base_url}/models", headers=self._headers())
            if resp.status_code >= 400:
                return False, f"OpenRouter /models returned {resp.status_code}"
            models = {m.get("id") for m in resp.json().get("data", [])}
            if self.model not in models:
                return False, f"model '{self.model}' not listed by OpenRouter"
            return True, f"{self.model} reachable"
        except LLMError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, f"OpenRouter unreachable: {exc}"


def build_openrouter_llm() -> OpenRouterLLM:
    return OpenRouterLLM()