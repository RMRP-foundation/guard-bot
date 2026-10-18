from __future__ import annotations

from typing import Any, Self, Sequence

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy.types import TypeDecorator

from database.connection import Session


class Base(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """MappedAsDataclass: дефолты применяются в конструкторе, как у Pydantic/Beanie."""


class PydanticJSON(TypeDecorator):
    """JSONB <-> pydantic-модель (или list[...]). Сохраняет доступ вида request.data.full_name."""

    impl = JSONB(none_as_null=True)  # None -> SQL NULL, а не JSON 'null'
    cache_ok = True

    def __init__(self, tp: Any):
        super().__init__()
        self._adapter = TypeAdapter(tp)
        self._tp = tp

    def process_bind_param(self, value, dialect):
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value, dialect):
        return None if value is None else self._adapter.validate_python(value)

    @property
    def python_type(self):
        return self._tp


class _Query:
    def __init__(self, model: type[Doc], criteria: Sequence[Any]):
        self.model = model
        self.stmt = select(model).where(*criteria)

    def sort(self, key: str) -> Self:
        col = getattr(self.model, key.lstrip("-"))
        self.stmt = self.stmt.order_by(col.desc() if key.startswith("-") else col)
        return self

    async def to_list(self) -> list:
        async with Session() as s:
            return list((await s.scalars(self.stmt)).all())

    async def first_or_none(self):
        async with Session() as s:
            return (await s.scalars(self.stmt.limit(1))).first()


class Doc(Base):
    """Минимальная Beanie-совместимость: find/find_one/find_all/save/create/delete/set."""

    __abstract__ = True

    @classmethod
    def find(cls, *criteria) -> _Query:
        return _Query(cls, criteria)

    @classmethod
    def find_all(cls) -> _Query:
        return _Query(cls, ())

    @classmethod
    async def find_one(cls, *criteria):
        return await cls.find(*criteria).first_or_none()

    async def create(self) -> Self:
        async with Session() as s:
            s.add(self)
            await s.commit()
        return self

    async def save(self) -> Self:
        async with Session() as s:
            await s.merge(self)
            await s.commit()
        return self

    async def set(self, values: dict) -> Self:
        for key, value in values.items():
            setattr(self, getattr(key, "key", key), value)
        return await self.save()

    async def delete(self) -> None:
        async with Session() as s:
            obj = await s.merge(self)
            await s.delete(obj)
            await s.commit()