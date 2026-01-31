from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncEngine
from core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=True,  
)

async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db():
    from models.db import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Database initialized!")
