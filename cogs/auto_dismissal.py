import logging

import discord
from discord.ext import commands, tasks

from bot import Bot
from core.exceptions import ServiceError
from database.models import DismissalType, User
from services import presence
from services.dismissal import DismissalService

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 10
MAX_NEW_DISMISSALS_PER_CYCLE = 5  # чтобы накопившиеся «призраки» не залили канал рапортов разом


class AutoDismissal(commands.Cog):
    """Автоувольнение ушедших с сервера. Без members-интента вместо on_member_remove — опрос по REST."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.check_loop.start()

    async def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_loop(self):
        try:
            result = await presence.check(self.bot)
            submitted = 0
            for discord_id in sorted(result.absent):
                if submitted >= MAX_NEW_DISMISSALS_PER_CYCLE:
                    break
                if await self._dismiss(discord_id):
                    submitted += 1
        except Exception:
            logger.exception("Auto dismissal check failed")

    @check_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    async def _dismiss(self, discord_id: int) -> bool:
        user_db = await User.get_active_soldier(discord_id)
        if user_db is None:
            return False

        from ui.views.dismissal import DismissalManagementView

        full_name = user_db.full_name
        if not full_name:
            try:
                full_name = (await self.bot.getch_user(discord_id)).display_name
            except discord.HTTPException:
                full_name = str(discord_id)

        try:
            await DismissalService.submit_dismissal(
                bot=self.bot,
                user=user_db,
                full_name=full_name,
                dismissal_type=DismissalType.AUTO,
                view_factory=DismissalManagementView,
            )
        except ServiceError:
            return False  # уже есть активный рапорт
        return True


async def setup(bot: Bot):
    await bot.add_cog(AutoDismissal(bot))