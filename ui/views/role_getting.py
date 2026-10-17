import re

import discord

from core.exceptions import ServiceError
from database.models import User
from services.authorization import AuthorizationService
from services.role_getting import RoleService
import texts
from ui.modals.role_getting import RoleRequestModal
from utils.helpers import safe_respond, safe_edit_message, build_mentions, random_loading_message
from utils.user_data import format_static


async def _get_applicant_defaults(user_id: int) -> tuple[str, str]:
    """Возвращает предзаполненное имя и статик пользователя, если они есть."""
    user = await User.get_by_discord_id(user_id)
    default_name = user.full_name if user and user.full_name else ""
    default_static = format_static(user.static) if user and user.static else ""
    return default_name, default_static


async def _handle_role_apply(interaction: discord.Interaction) -> None:
    """Проверяет ограничения и открывает соответствующую модалку."""
    try:
        await RoleService.validate_can_apply(interaction.user.id, interaction.channel, check_blacklist=True)
        name, static = await _get_applicant_defaults(interaction.user.id)
        await interaction.response.send_modal(RoleRequestModal(user_name=name, static_id=static))
    except ServiceError as error:
        await safe_respond(interaction, error.message)


class RoleApplyView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(texts.role_title))
    container.add_item(discord.ui.TextDisplay(texts.role_submission))
    container.add_item(discord.ui.TextDisplay(texts.role_requirements))
    container.add_item(discord.ui.Separator(visible=True))

    army_button = discord.ui.Button(
        label="ФСВНГ", emoji="🎖️", style=discord.ButtonStyle.primary, custom_id="role_apply_army"
    )
    army_button.callback = _handle_role_apply

    action_row = discord.ui.ActionRow()
    action_row.add_item(army_button)
    container.add_item(action_row)


class RoleManagementButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"role_(?P<action>approve|reject):(?P<id>\d+)",
):
    def __init__(self, action: str, request_id: int):
        labels = {"approve": "Одобрить", "reject": "Отклонить"}
        styles = {"approve": discord.ButtonStyle.success, "reject": discord.ButtonStyle.danger}
        emojis = {"approve": "👍", "reject": "👎"}

        super().__init__(
            discord.ui.Button(
                label=labels[action],
                emoji=emojis[action],
                style=styles[action],
                custom_id=f"role_{action}:{request_id}",
            )
        )
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(match.group("action"), int(match.group("id")))

    async def callback(self, interaction: discord.Interaction):
        try:
            officer = await AuthorizationService.require_active_soldier(interaction)
            await safe_respond(interaction, random_loading_message())

            if self.action == "approve":
                result = await RoleService.approve_role(interaction, self.request_id, officer)
            else:
                result = await RoleService.reject_role(interaction, self.request_id, officer)

            await safe_edit_message(
                message=interaction.message,
                content=build_mentions([result.request.user, interaction.user.id]),
                embed=result.embed,
                view=result.view,
            )
            await safe_respond(interaction, result.message)

        except ServiceError as error:
            await safe_respond(interaction, error.message)


class RoleManagementView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.add_item(RoleManagementButton("approve", request_id))
        self.add_item(RoleManagementButton("reject", request_id))