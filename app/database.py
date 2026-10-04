from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Required if DB_HOST/DB_PORT point at a PgBouncer transaction-mode
    # pooler (e.g. Supabase's pooler on port 6543) - that mode doesn't
    # support asyncpg's prepared statements. Harmless no-op against a
    # direct Postgres connection, so safe to leave on either way.
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
