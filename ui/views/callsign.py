import re

import discord

import texts
from core.exceptions import ServiceError
from services.authorization import AuthorizationService
from services.callsign import CallsignService
from ui.modals.callsign import CallsignModal
from utils.helpers import build_mentions, random_loading_message, safe_edit_message, safe_respond


class CallsignApplyView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(texts.callsign_title))
        container.add_item(discord.ui.TextDisplay(texts.callsign_submission))
        container.add_item(discord.ui.TextDisplay(texts.callsign_requirements))
        container.add_item(discord.ui.Separator(visible=True))

        btn = discord.ui.Button(
            label="Подать заявление",
            emoji="📨",
            style=discord.ButtonStyle.primary,
            custom_id="callsign_apply_btn",
        )
        btn.callback = self.on_apply

        row = discord.ui.ActionRow()
        row.add_item(btn)
        container.add_item(row)
        self.add_item(container)

    async def on_apply(self, interaction: discord.Interaction):
        try:
            user_db = await AuthorizationService.require_active_soldier(interaction)
            await CallsignService.validate_can_apply(user_db)
            await interaction.response.send_modal(CallsignModal(user_db))
        except ServiceError as error:
            await safe_respond(interaction, error.message)


class CallsignManagementButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"callsign:(?P<action>approve|reject):(?P<id>\d+)",
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
                custom_id=f"callsign:{action}:{request_id}",
            )
        )
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls(match.group("action"), int(match.group("id")))

    async def callback(self, interaction: discord.Interaction):
        try:
            officer = await AuthorizationService.require_active_soldier(interaction)
            await safe_respond(interaction, random_loading_message(), ephemeral=True)

            result = await CallsignService.process_callsign(
                interaction=interaction,
                request_id=self.request_id,
                action=self.action,
                officer=officer,
            )
            await safe_edit_message(
                message=interaction.message,
                content=build_mentions([result.request.user_id, interaction.user.id]),
                embed=result.embed,
                view=result.view,
            )
            await safe_respond(interaction, result.message)
        except ServiceError as error:
            await safe_respond(interaction, error.message)


class CallsignManagementView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.add_item(CallsignManagementButton("approve", request_id))
        self.add_item(CallsignManagementButton("reject", request_id))