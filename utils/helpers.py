import logging
import random
from typing import Iterable, TypeVar

import discord
from discord.utils import MISSING

from core import config, constants
from core.constants import LOADING_MESSAGES, DivisionId
from core.exceptions import ServiceError
from database import divisions
from database.status import RequestStatus

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def safe_respond(
    interaction: discord.Interaction,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | discord.ui.LayoutView | None = MISSING,
    ephemeral: bool = True,
) -> None:
    try:
        if interaction.response.is_done():
            try:
                await interaction.edit_original_response(content=content, view=view, embed=embed)
            except discord.HTTPException:
                await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, embed=embed, view=view, ephemeral=ephemeral)
    except (discord.NotFound, discord.HTTPException):
        pass


async def require_request(
    model: type[T],
    request_id: int,
    statuses: str | tuple[str, ...] = RequestStatus.PENDING,
    error_message: str | None = None,
) -> T:
    """Достаёт заявку в одном из допустимых статусов, иначе бросает ServiceError."""
    allowed = statuses if isinstance(statuses, tuple) else (statuses,)
    req = await model.find_one(model.id == request_id)
    if not req or req.status not in allowed:
        raise ServiceError(error_message or f"❌ Заявка #{request_id} не найдена или уже обработана.")
    return req


async def require_no_active_request(
    model,
    user_id: int,
    statuses: tuple[str, ...] = (RequestStatus.PENDING,),
    user_field: str = "user_id",
    error_message: str | None = None,
) -> None:
    """Проверяет отсутствие активной заявки у пользователя, иначе бросает ServiceError."""
    col = getattr(model, user_field)
    existing = await model.find_one(col == user_id, model.status.in_(statuses))
    if existing:
        raise ServiceError(
            error_message or f"❌ У вас уже есть активная заявка #{existing.id} на рассмотрении."
        )


def _normalize_ids(target: int | Iterable[int] | None) -> list[int]:
    """Приводит int, list, tuple или None к единому списку int."""
    if target is None:
        return []
    if isinstance(target, int):
        return [target]
    return [x for x in target if x]


def build_mentions(
        users: int | Iterable[int] = (),
        roles: int | Iterable[int] = (),
) -> str | None:
    """Универсальная сборка спойлер-упоминаний (-# ||<@123> <@&456>||).

    Принимает как одиночный ID (int), так и список/кортеж ID.
    Дедуплицирует упоминания с сохранением порядка.
    """
    seen: set[tuple[str, int]] = set()
    parts: list[str] = []

    for uid in _normalize_ids(users):
        key = ("user", uid)
        if key not in seen:
            seen.add(key)
            parts.append(f"<@{uid}>")

    for rid in _normalize_ids(roles):
        key = ("role", rid)
        if key not in seen:
            seen.add(key)
            parts.append(f"<@&{rid}>")

    if not parts:
        return None

    return f"-# ||{' '.join(parts)}||"

def build_request_mentions(
        user_id: int,
        user_division_id: int | None = None,
        min_privilege: int = 2,
        fallback_id: int = DivisionId.CPP,
) -> str:
    """Автор + руководящие должности его подразделения (или резервного, если позиций нет)."""
    div = divisions.get_division(user_division_id)
    if not div or not div.positions:
        div = divisions.get_division(fallback_id)

    positions = div.positions if (div and div.positions) else []
    role_ids = [pos.role_id for pos in positions if pos.privilege.value >= min_privilege and pos.role_id]

    return build_mentions(user_id, role_ids)

def build_officer_mentions(user_id: int, min_rank_index: int) -> str:
    """Спойлер с упоминанием автора и всего командного состава от указанного звания и выше."""
    officer_role_ids = [
        role_id for rank_name, role_id in config.RANK_ROLES.items()
        if constants.RANKS.index(rank_name) >= min_rank_index
    ]
    return build_mentions(user_id, officer_role_ids)

async def safe_edit_message(
    message: discord.Message | discord.PartialMessage | None,
    content: str | None = MISSING,
    embed: discord.Embed | None = MISSING,
    view: discord.ui.View | None = MISSING,
) -> bool:
    """Безопасно редактирует сообщение или PartialMessage без падений от 404/HTTP."""
    if not message:
        return False
    try:
        await message.edit(content=content, embed=embed, view=view)
        return True
    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
        return False


async def safe_delete_message(message: discord.Message | None) -> bool:
    """Безопасно удаляет сообщение Discord (игнорирует, если уже удалено)."""
    if not message:
        return False
    try:
        await message.delete()
        return True
    except (discord.NotFound, discord.HTTPException):
        return False

async def safe_publish_request(
    channel: discord.abc.Messageable | None,
    request,
    embed: discord.Embed,
    content: str | None = None,
    view: discord.ui.View | None = None,
    error_message: str = "❌ Не удалось отправить заявку в канал. Попробуйте ещё раз.",
) -> int:
    """Безопасно публикует заявку в канал с авто-откатом (удалением) при сбое Discord API."""
    if not channel:
        await request.delete()
        raise ServiceError("❌ Ошибка конфигурации: целевой канал не найден.")

    try:
        msg = await channel.send(content=content, embed=embed, view=view)
        return msg.id
    except Exception as error:
        logger.error(f"Failed to publish request #{request.id}: {error}", exc_info=True)
        await request.delete()
        raise ServiceError(error_message)

def random_loading_message() -> str:
    return random.choice(LOADING_MESSAGES)
