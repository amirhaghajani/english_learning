import json
from collections.abc import Iterator

import httpx

from app.config import settings
from app.llm.base import ChatMessage, LLMError, ReplyRequest

_OLLAMA_HINT = (
    "Ollama is unreachable at {base}. Start it with `ollama serve` and pull the model "
    "with `ollama pull {model}`."
)


class OllamaLLM:
    name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout

    def _endpoint(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def stream(self, req: ReplyRequest) -> Iterator[str]:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": req.system}]
            + [{"role": m.role, "content": m.content} for m in req.messages],
            "stream": True,
            "think": False,
            "options": {"temperature": req.temperature},
        }
        if req.max_tokens:
            payload["options"]["num_predict"] = req.max_tokens

        try:
            with (
                httpx.Client(timeout=self.timeout) as client,
                client.stream("POST", self._endpoint("/api/chat"), json=payload) as resp,
            ):
                if resp.status_code == 404:
                    raise LLMError(
                        "model_missing",
                        f"Ollama model '{self.model}' is not installed. "
                        f"Run `ollama pull {self.model}`.",
                        status_code=503,
                    )
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", "replace")[:500]
                    raise LLMError(
                        "llm_unreachable",
                        f"Ollama returned {resp.status_code}: {body}",
                        status_code=503,
                    )
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise LLMError(
                            "llm_error", str(chunk["error"]), status_code=502
                        )
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise LLMError(
                "llm_unreachable",
                _OLLAMA_HINT.format(base=self.base_url, model=self.model),
                status_code=503,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError("llm_unreachable", f"Ollama request failed: {exc}", 503) from exc

    def probe(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(self._endpoint("/api/tags"))
            if resp.status_code >= 400:
                return False, f"Ollama /api/tags returned {resp.status_code}"
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            have = ", ".join(models) or "none"
            if not any(m.startswith(self.model) or m == self.model for m in models):
                return False, f"model '{self.model}' not pulled; have: {have}"
            return True, f"{self.model} ready"
        except Exception as exc:  # noqa: BLE001
            return False, f"Ollama unreachable at {self.base_url}: {exc}"


def build_ollama_llm() -> OllamaLLM:
    return OllamaLLM()


def describe_messages(messages: list[ChatMessage]) -> str:
    return "\n".join(f"[{m.role}] {m.content}" for m in messages)
