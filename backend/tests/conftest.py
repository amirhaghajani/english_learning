import os
import sys
from collections.abc import Iterator
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DB_PATH = BACKEND_ROOT / "tests" / "test_emma.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["TTS_BACKEND"] = "fake"
os.environ["STT_BACKEND"] = "fake"
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["RAG_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import deps  # noqa: E402
from app.audio.stt import FakeSTT  # noqa: E402
from app.audio.tts import FakeTTS  # noqa: E402
from app.db import SessionFactory, create_all  # noqa: E402
from app.llm.base import LLMError, ReplyRequest  # noqa: E402
from app.models import Base  # noqa: E402


class ScriptedLLM:
    name = "scripted"
    model = "scripted-model"

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.requests: list[ReplyRequest] = []
        self.error: LLMError | None = None

    def stream(self, req: ReplyRequest) -> Iterator[str]:
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        yield from self.chunks

    def probe(self) -> tuple[bool, str]:
        return True, "scripted"


@pytest.fixture
def scripted_llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def fake_tts() -> FakeTTS:
    return FakeTTS()


@pytest.fixture(autouse=True)
async def _clean_database():
    await create_all()
    yield
    async with SessionFactory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest.fixture
def client(scripted_llm, fake_stt, fake_tts) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[deps.get_llm_dep] = lambda: scripted_llm
    app.dependency_overrides[deps.get_stt_dep] = lambda: fake_stt
    app.dependency_overrides[deps.get_tts_dep] = lambda: fake_tts
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()