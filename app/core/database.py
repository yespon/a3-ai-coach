from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,      # Auto-detect and recycle stale connections
    pool_size=5,             # Max persistent connections
    max_overflow=10,         # Extra connections above pool_size when under load
    pool_recycle=1800,       # Recycle connections every 30min to avoid server-side timeout
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped async session.

    Services are responsible for calling db.commit() when they make changes.
    This dependency only provides the session and ensures cleanup (rollback
    on unhandled exceptions, close always).
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
