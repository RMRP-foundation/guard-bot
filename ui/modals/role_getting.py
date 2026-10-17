import discord.ui

from core.exceptions import ServiceError
from database.models import RoleData, RoleType
from services.role_getting import RoleService
from ui.modals.labels import (
    name_input,
    static_label,
)
from utils.helpers import safe_respond
from utils.user_data import clean_name, clean_static


class RoleRequestModal(discord.ui.Modal, title="Заявление на получение роли"):
    name = name_input()
    static_id = static_label()
    footer = discord.ui.TextDisplay(
        "Если вы что-то не понимаете, обратитесь к сотруднику за помощью."
    )

    def __init__(self, user_name: str | None = None, static_id: str | None = None):
        super().__init__()
        if user_name:
            self.name.default = user_name
        if static_id:
            self.static_id.component.default = static_id

    async def on_submit(self, interaction: discord.Interaction):
        from ui.views.role_getting import RoleManagementView

        try:
            await safe_respond(interaction, "⏳ Заявление отправляется...")

            await RoleService.submit_role(
                interaction=interaction,
                role_type=RoleType.ARMY,
                data=RoleData(
                    full_name=clean_name(self.name.value),
                    static_id=clean_static(self.static_id.component.value),
                ),
                view_factory=RoleManagementView,
            )
            await safe_respond(interaction, "### Заявление отправлено на рассмотрение.")
        except ServiceError as error:
            await safe_respond(interaction, error.message)
