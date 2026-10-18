import logging
import os

import discord
import sentry_sdk
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from core.config import GUILD_ID, SENTRY_DSN
from database import divisions
from database.connection import establish_db_connection, Session
from database.models import User
from error_handling import _custom_view_on_error, on_tree_error, on_command_error
from ui.views import load_buttons
from services.audit import audit_logger
from utils.roles import get_rank_from_roles

logger = logging.getLogger(__name__)

sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0, send_default_pii=False)


discord.ui.View.on_error = _custom_view_on_error
discord.ui.LayoutView.on_error = _custom_view_on_error


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _sync_users(self):
        guild = self.get_guild(GUILD_ID)
        async with Session() as s:
            inited_ids = set(await s.scalars(select(User.discord_id).where(User.pre_inited.is_(True))))

            rows = []
            for member in guild.members:
                if member.id in inited_ids:
                    continue
                div, pos = divisions.get_user_data(member)
                rows.append({
                    "discord_id": member.id,
                    "division": div.division_id if div else None,
                    "position": pos.name if pos else None,
                    "rank": get_rank_from_roles(member.roles),
                    "pre_inited": True,
                })

            if rows:
                stmt = insert(User)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["discord_id"],
                    set_={k: stmt.excluded[k] for k in ("division", "position", "rank", "pre_inited")},
                )
                await s.execute(stmt, rows)
                await s.commit()
                logger.info(f"Synchronized {len(rows)} users from guild members")


    async def on_ready(self):
        print("done")
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("------")
        await self._sync_users()
        from cogs.leave import restore_leave_timers
        await restore_leave_timers(self)

    async def _load_cogs(self):
        for file in os.listdir("./cogs"):
            if file.endswith(".py"):
                await self.load_extension(f"cogs.{file[:-3]}")
                logger.info(f"Loaded cog {file[:-3]}")

    async def setup_hook(self):
        await establish_db_connection()
        await divisions.load()
        audit_logger.set_bot(self)

        load_buttons(self)
        await self._load_cogs()

        self.tree.on_error = on_tree_error

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info(f"Slash commands synced to guild {GUILD_ID}")

    async def getch_user(self, discord_id: int):
        if user := self.get_user(discord_id):
            return user
        return await self.fetch_user(discord_id)

    async def getch_member(self, discord_id: int):
        guild = self.get_guild(GUILD_ID)
        if member := guild.get_member(discord_id):
            return member

        try:
            return await guild.fetch_member(discord_id)
        except discord.NotFound:
            return None

    async def on_command_error(self, ctx, error):
        await on_command_error(ctx, error)
