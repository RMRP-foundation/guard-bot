from sqlalchemy import update

from database.connection import Session


async def atomic_status_transition(
    model, request_id: int, from_status: str | list[str], to_status: str,
    extra_fields: dict | None = None, extra_filter: dict | None = None,
) -> dict | None:
    """UPDATE ... WHERE id AND status IN (...) RETURNING. Гонку выигрывает один апдейт."""
    from_list = from_status if isinstance(from_status, list) else [from_status]
    conditions = [model.id == request_id, model.status.in_(from_list)]
    conditions += [getattr(model, k) == v for k, v in (extra_filter or {}).items()]

    stmt = (
        update(model)
        .where(*conditions)
        .values(status=to_status, **(extra_fields or {}))
        .returning(model)
    )
    async with Session() as s:
        row = (await s.execute(stmt)).scalar_one_or_none()
        await s.commit()

    if row is None:
        return None
    return {attr.key: getattr(row, attr.key) for attr in model.__mapper__.column_attrs}