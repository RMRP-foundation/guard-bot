import discord

from core.exceptions import ServiceError
from database.models import User
from services.authorization import AuthorizationService
from services.callsign import CallsignService
from utils.helpers import safe_respond


class CallsignModal(discord.ui.Modal, title="Подача в реестр позывных"):
    fio = discord.ui.Label(
        text="ФИО",
        description="Укажите фамилию, имя и отчество полностью.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            placeholder="Смирнов Александр Сергеевич",
            max_length=80,
            required=True,
        ),
    )
    callsign = discord.ui.Label(
        text="Позывной",
        description="Слово и две последние цифры номера паспорта.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            placeholder="Кедр 49-й",
            max_length=40,
            required=True,
        ),
    )

    def __init__(self, user_db: User):
        super().__init__()
        self.user_db = user_db

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            self.user_db = await AuthorizationService.require_active_soldier(interaction)
            await CallsignService.validate_can_apply(self.user_db)
            return True
        except ServiceError as error:
            await safe_respond(interaction, error.message)
            return False

    async def on_submit(self, interaction: discord.Interaction):
        from ui.views.callsign import CallsignManagementView

        try:
            await safe_respond(interaction, "⏳ Отправляем заявку...", ephemeral=True)
            await CallsignService.submit_callsign(
                interaction=interaction,
                user_db=self.user_db,
                full_name=self.fio.component.value,
                callsign=self.callsign.component.value,
                view_factory=CallsignManagementView,
            )
            await safe_respond(interaction, "✅ Заявка отправлена в реестр позывных.")
        except ServiceError as error:
            await safe_respond(interaction, error.message)