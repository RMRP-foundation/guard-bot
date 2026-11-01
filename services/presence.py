import asyncio
import logging
from dataclasses import dataclass

import discord
from sqlalchemy.dialects.postgresql import insert

from core.config import GUILD_ID, SERVICE_ACCOUNT_IDS
from database import divisions
from database.connection import Session
from database.models import User
from utils.roles import get_rank_from_roles

logger = logging.getLogger(__name__)

_PAUSE = 0.25  # между запросами, чтобы не упираться в rate limit

# Боевые с рангом, которых нет на сервере (по результатам последней проверки)
absent_ids: set[int] = set()


@dataclass(frozen=True)
class PresenceResult:
    checked: int
    absent: set[int]


async def init_user(member: discord.Member) -> tuple[User, bool]:
    """pre-init одного бойца по ролям Discord (вместо массового Bot._sync_users).

    Returns:
        (пользователь, создан/обновлён ли он сейчас). Уже инициализированных не трогает.
    """
    user = await User.get_by_discord_id(member.id)
    if user is not None and user.pre_inited:
        return user, False

    div, pos = divisions.get_user_data(member)
    values = {
        "division": div.division_id if div else None,
        "position": pos.name if pos else None,
        "rank": get_rank_from_roles(member.roles),
        "pre_inited": True,
    }
    stmt = insert(User).values(discord_id=member.id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=["discord_id"], set_=values)
    async with Session() as s:
        await s.execute(stmt)
        await s.commit()
    return await User.get_by_discord_id(member.id), True


async def check(bot: discord.Client) -> PresenceResult:
    """Проверяет по REST, что бойцы с рангом всё ещё на сервере. Обновляет absent_ids."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        raise RuntimeError("Гильдия не найдена в кэше бота")

    users = await User.find(User.rank.is_not(None)).to_list()
    ids = [u.discord_id for u in users if u.discord_id not in SERVICE_ACCOUNT_IDS]

    absent: set[int] = set()
    unknown: set[int] = set()
    for discord_id in ids:
        try:
            await guild.fetch_member(discord_id)
        except discord.NotFound:
            absent.add(discord_id)
        except discord.HTTPException:
            unknown.add(discord_id)  # сбой Discord — оставляем прежний статус
        await asyncio.sleep(_PAUSE)

    absent |= unknown & absent_ids
    absent_ids.clear()
    absent_ids.update(absent)
    return PresenceResult(checked=len(ids), absent=set(absent))