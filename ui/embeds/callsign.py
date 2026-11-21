import discord

from database.models import CallsignRequest, User
from database.status import get_status_display
from utils.user_data import format_static


def callsign_embed(request: CallsignRequest, user: User | None) -> discord.Embed:
    status_display = get_status_display(request.status)

    embed = discord.Embed(
        title=f"{status_display.emoji} Реестр позывных #{request.id} — {status_display.text}",
        color=status_display.color,
        timestamp=request.created_at,
    )

    static_str = format_static(user.static) if user else "N/A"

    embed.add_field(name="ФИО", value=request.full_name, inline=True)
    embed.add_field(name="Статик", value=static_str, inline=True)
    embed.add_field(name="Позывной", value=request.callsign, inline=False)

    embed.set_footer(text="Отправлено")
    return embed