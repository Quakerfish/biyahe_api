from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    # Serverless: every invocation may run in a fresh instance/event loop, so
    # holding pooled connections buys nothing. Supabase's pooler (port 6543)
    # does the real pooling. pool_pre_ping is removed on purpose: it sent an
    # extra "SELECT 1" round trip before every query.
    poolclass=NullPool,
    # Required for PgBouncer/Supavisor transaction mode (no prepared statements).
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session