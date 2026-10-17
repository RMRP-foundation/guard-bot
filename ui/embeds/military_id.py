import discord

from database.models import MilitaryIdRequest, User
from database.status import get_status_display
from utils.user_data import format_static, format_rank


def military_id_embed(request: MilitaryIdRequest, user: User | None) -> discord.Embed:
    status_display = get_status_display(request.status)

    embed = discord.Embed(
        title=f"{status_display.emoji} Военный билет #{request.id} — {status_display.text}",
        color=status_display.color,
        timestamp=request.created_at,
    )

    static_str = format_static(user.static) if user else "Не указан"
    rank_str = format_rank(user.rank) if user else "Не указано"

    embed.add_field(name="Военнослужащий", value=request.full_name, inline=True)
    embed.add_field(name="Статик", value=static_str, inline=True)
    embed.add_field(name="Звание", value=rank_str, inline=False)
    embed.add_field(name="Военный билет", value=request.evidence, inline=False)

    if request.reject_reason:
        embed.add_field(name="Причина отказа", value=request.reject_reason, inline=False)

    if request.reviewer_id:
        reviewed = f" в {discord.utils.format_dt(request.reviewed_at)}" if request.reviewed_at else ""
        embed.add_field(name="Проверил", value=f"<@{request.reviewer_id}>{reviewed}", inline=False)

    embed.set_footer(text="Отправлено")
    return embed