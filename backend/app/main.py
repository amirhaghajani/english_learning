import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, settings
from app.db import SessionFactory, create_all, dispose_engine, ensure_sqlite_columns
from app.routers import admin, health, learners, scenarios, sessions, turns
from app.seed import seed_scenarios

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("emma")

DIST_DIR = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.is_sqlite:
        logger.info("using SQLite fallback at %s", settings.database_url)
        await create_all()
        await ensure_sqlite_columns()
    else:
        logger.info("using Postgres at %s", settings.database_url)

    async with SessionFactory() as session:
        await seed_scenarios(session)

    from app.audio.tts import get_tts

    try:
        tts = get_tts()
    except RuntimeError as exc:
        logger.error("TTS is not usable: %s", exc)
        raise
    ready, detail = tts.probe()
    if not ready:
        logger.error("TTS is not ready: %s", detail)
        raise RuntimeError(detail)
    logger.info("TTS ready: %s", detail)

    yield

    await dispose_engine()


app = FastAPI(title="Emma - English tutor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(learners.router)
app.include_router(scenarios.router)
app.include_router(sessions.router)
app.include_router(turns.router)
app.include_router(admin.router)


@app.get("/api", include_in_schema=False)
async def api_root() -> dict:
    return {"name": "emma", "version": app.version, "docs": "/docs"}


if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")