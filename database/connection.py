import logging
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Читаем env напрямую: core.config импортирует database.models, а тот тянет этот модуль (цикл).
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL not found")

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
# expire_on_commit=False: объекты остаются читаемыми после закрытия сессии (аналог Beanie-документов)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

_IS_INITIALIZED = False


async def establish_db_connection():
    """Проверяет подключение. Схема создаётся Alembic'ом: `alembic upgrade head`."""
    global _IS_INITIALIZED
    if _IS_INITIALIZED:
        return

    async with engine.connect():
        pass

    _IS_INITIALIZED = True
    logging.info("Database connection established")