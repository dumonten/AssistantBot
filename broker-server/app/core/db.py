# core/db.py (existing, no changes needed for now)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from core.config import settings
from models.db import Base

# Асинхронный движок (для тестов можно добавить poolclass=NullPool)
engine = create_async_engine(
    settings.async_database_url,  # Используем async_database_url из settings
    echo=settings.LOG_LEVEL == "DEBUG",
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Зависимость для получения сессии (используется в эндпоинтах)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Инициализация БД (вызывается в main.py при старте)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # Только если не используете Alembic!