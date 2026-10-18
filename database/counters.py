from sqlalchemy import text

from database.connection import Session


async def get_next_id(collection_name: str) -> int:
    """Атомарно берёт следующий id из sequence таблицы (имя = имя бывшей коллекции)."""
    async with Session() as s:
        value = await s.scalar(
            text("SELECT nextval(pg_get_serial_sequence(:t, 'id'))"), {"t": collection_name}
        )
        await s.commit()
    return value