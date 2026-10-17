import discord

from core.exceptions import ServiceError
from database.models import User
from services.authorization import AuthorizationService
from services.military_id import MilitaryIdService
from ui.modals.labels import screenshot_label
from utils.helpers import safe_respond


class MilitaryIdModal(discord.ui.Modal, title="Предоставление военного билета"):
    evidence = screenshot_label("военного билета")

    def __init__(self, user_db: User):
        super().__init__()
        self.user_db = user_db

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            self.user_db = await AuthorizationService.require_active_soldier(interaction)
            await MilitaryIdService.validate_can_apply(self.user_db)
            return True
        except ServiceError as error:
            await safe_respond(interaction, error.message)
            return False

    async def on_submit(self, interaction: discord.Interaction):
        from ui.views.military_id import MilitaryIdManagementView

        link = self.evidence.component.value.strip()
        if not (link.startswith("http://") or link.startswith("https://")):
            await safe_respond(interaction, "❌ Введите корректную ссылку на фотохостинг со скриншотом.")
            return

        try:
            await safe_respond(interaction, "⏳ Отправляем данные военного билета...", ephemeral=True)
            await MilitaryIdService.submit_military_id(
                interaction=interaction,
                user_db=self.user_db,
                evidence=link,
                view_factory=MilitaryIdManagementView,
            )
            await safe_respond(interaction, "✅ Военный билет отправлен на проверку командованию.")
        except ServiceError as error:
            await safe_respond(interaction, error.message)