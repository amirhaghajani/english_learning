import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

_SQLITE_EXTRA_COLUMNS = {
    "session": (("opening_line", "ALTER TABLE session ADD COLUMN opening_line TEXT"),),
}


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        kwargs: dict = {"echo": False}
        if ":memory:" in settings.database_url or "mode=memory" in settings.database_url:
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        return kwargs
    return {"echo": False, "pool_pre_ping": True}


engine = create_async_engine(settings.database_url, **_engine_kwargs())

if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_sqlite_columns() -> None:
    """Add columns introduced after an existing SQLite file was created."""
    if not settings.is_sqlite:
        return
    async with engine.begin() as conn:
        for table, columns in _SQLITE_EXTRA_COLUMNS.items():
            rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
            present = {row[1] for row in rows}
            for name, ddl in columns:
                if name not in present:
                    logger.info("sqlite: adding missing column %s.%s", table, name)
                    await conn.execute(text(ddl))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()