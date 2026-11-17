from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ReplyRequest:
    system: str
    messages: list[ChatMessage] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int | None = None
    repetition_penalty: float | None = None


@runtime_checkable
class TutorLLM(Protocol):
    name: str
    model: str

    def stream(self, req: ReplyRequest) -> Iterator[str]:
        """Yield raw text deltas as they arrive."""
        ...

    def probe(self) -> tuple[bool, str]:
        """Return (reachable, detail) without raising."""
        ...