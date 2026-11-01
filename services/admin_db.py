"""Слой данных админ-панели: универсальный CRUD по моделям и досье бойца."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String, func, inspect as sa_inspect, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

import database.models  # noqa: F401  (регистрирует мапперы)
from database.base import Base, Doc, PydanticJSON
from database.models import User
from database.connection import Session

_USER_FK = ("user_id", "user")  # так называется ссылка на бойца в моделях заявок
_TRUE = {"true", "1", "yes", "да"}
_FALSE = {"false", "0", "no", "нет"}


# ── модели ──────────────────────────────────────────────────────────────────

def get_models() -> dict[str, type[Doc]]:
    items = ((m.class_.__tablename__, m.class_) for m in Base.registry.mappers)
    return dict(sorted(items, key=lambda kv: kv[0]))


def columns(model: type[Doc]) -> list:
    return list(sa_inspect(model).columns)


def pk_name(model: type[Doc]) -> str:
    return sa_inspect(model).primary_key[0].key


def _column(model: type[Doc], name: str):
    for col in columns(model):
        if col.key == name:
            return col
    raise ValueError(f"Нет колонки `{name}`. Доступные: {', '.join(c.key for c in columns(model))}")


# ── парсинг / форматирование ────────────────────────────────────────────────

def parse_value(col, raw: str):
    t = col.type
    s = raw.strip()

    if s.lower() in ("null", "none") or s == "":
        if col.nullable:
            return None
        if isinstance(t, String) and s == "":
            return ""
        raise ValueError(f"`{col.key}` NOT NULL, null недопустим")

    if isinstance(t, PydanticJSON):
        return t._adapter.validate_python(json.loads(s))
    if isinstance(t, JSONB):
        return json.loads(s)
    if isinstance(t, SAEnum):  # до String: Enum — его подкласс
        cls = t.enum_class
        try:
            return cls(s)
        except ValueError:
            try:
                return cls[s]
            except KeyError:
                raise ValueError(f"Допустимо: {', '.join(str(m.value) for m in cls)}") from None
    if isinstance(t, Boolean):
        if s.lower() in _TRUE:
            return True
        if s.lower() in _FALSE:
            return False
        raise ValueError("Ожидалось true/false/1/0")
    if isinstance(t, Integer):  # BigInteger — подкласс
        return int(s)
    if isinstance(t, DateTime):
        if s.lstrip("-").isdigit():
            return dt.datetime.fromtimestamp(int(s), dt.UTC)
        value = dt.datetime.fromisoformat(s)
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    if isinstance(t, String):
        return raw
    raise ValueError(f"Тип {t} не поддерживается")


def format_value(col, value) -> str:
    if value is None:
        return "null"
    if isinstance(col.type, PydanticJSON):
        return json.dumps(col.type._adapter.dump_python(value, mode="json"), ensure_ascii=False)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def render_record(model: type[Doc], record, limit: int = 3000, value_limit: int = 150) -> str:
    """Components V2 даёт ~4000 символов текста на всё сообщение — держим бюджет."""
    lines = []
    for col in columns(model):
        text = format_value(col, getattr(record, col.key)).replace("\n", " ⏎ ").replace("`", "'")
        if len(text) > value_limit:
            text = text[:value_limit] + "…"
        lines.append(f"{'🔑 ' if col.primary_key else ''}`{col.key}` = {text}")
    result = "\n".join(lines)
    return result if len(result) <= limit else result[: limit - 1] + "…"


# ── CRUD ────────────────────────────────────────────────────────────────────

async def find_records(model: type[Doc], field: str, raw: str, limit: int = 10) -> list:
    col = _column(model, field)
    value = parse_value(col, raw)
    stmt = (
        select(model)
        .where(getattr(model, field) == value)
        .order_by(getattr(model, pk_name(model)))
        .limit(limit)
    )
    async with Session() as s:
        return list((await s.scalars(stmt)).all())


async def reload(model: type[Doc], record):
    pk = pk_name(model)
    return await model.find_one(getattr(model, pk) == getattr(record, pk))


async def update_fields(model: type[Doc], record, changes: dict[str, str]):
    """Применяет изменения к свежей копии из БД. Возвращает ([(поле, было, стало)], свежая запись)."""
    parsed = {}
    for name, raw in changes.items():
        col = _column(model, name)
        if col.primary_key:
            raise ValueError("Первичный ключ менять нельзя: удалите запись и создайте новую")
        parsed[name] = (col, parse_value(col, raw))

    target = await reload(model, record)
    if target is None:
        raise ValueError("Запись уже удалена")

    diff = []
    for name, (col, new) in parsed.items():
        diff.append((name, format_value(col, getattr(target, name)), format_value(col, new)))
        setattr(target, name, new)  # сработает и listener User.division -> transferred_at
    await target.save()
    return diff, await reload(model, target)


# ── досье бойца ─────────────────────────────────────────────────────────────

@dataclass
class DossierSection:
    table: str
    model: type[Doc]
    total: int
    rows: list


async def find_user(raw: str) -> User | None:
    """Discord ID (15+ цифр) или статик (короче; дефис допускается)."""
    digits = raw.strip().replace("-", "").replace(" ", "")
    if not digits.isdigit():
        raise ValueError("Нужен Discord ID или статик: число, статик можно с дефисом")
    field = "discord_id" if len(digits) >= 15 else "static"
    return await User.find_one(getattr(User, field) == int(digits))


async def dossier_sections(discord_id: int, per_model: int = 2) -> list[DossierSection]:
    """Заявки бойца по всем моделям со ссылкой на пользователя (находятся автоматически)."""
    sections: list[DossierSection] = []
    async with Session() as s:
        for name, model in get_models().items():
            if model is User:
                continue
            keys = {c.key for c in columns(model)}
            fk = next((k for k in _USER_FK if k in keys), None)
            if fk is None:
                continue
            cond = getattr(model, fk) == discord_id
            total = await s.scalar(select(func.count()).select_from(model).where(cond))
            if not total:
                continue
            pk = getattr(model, pk_name(model))
            rows = list((await s.scalars(select(model).where(cond).order_by(pk.desc()).limit(per_model))).all())
            sections.append(DossierSection(name, model, total, rows))
    return sections


def row_summary(model: type[Doc], row) -> str:
    text = f"#{getattr(row, pk_name(model))}"
    status = getattr(row, "status", None)
    return f"{text} {status}" if status else text


async def load_row(model: type[Doc], pk_value: int):
    return await model.find_one(getattr(model, pk_name(model)) == pk_value)