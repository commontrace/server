from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)


@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Register pgvector types with asyncpg in text mode.

    Using text mode so SQLAlchemy's Vector bind_processor handles
    Python list → text conversion, asyncpg passes text through unchanged,
    and PostgreSQL parses the text as a vector. Binary mode (register_vector)
    conflicts with SQLAlchemy's bind_processor which already converts to text.
    """
    async def _register_text_codec(conn):
        await conn.set_type_codec(
            'vector', schema='public',
            encoder=str, decoder=str, format='text',
        )
    dbapi_connection.run_async(_register_text_codec)


async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    """FastAPI dependency: yields AsyncSession per request."""
    async with async_session_factory() as session:
        yield session
