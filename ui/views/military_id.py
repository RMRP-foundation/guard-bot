import re
import discord

from core.exceptions import ServiceError
from database.models import MilitaryIdRequest, User
from services.authorization import AuthorizationService
from services.military_id import MilitaryIdService
from ui.modals.military_id import MilitaryIdModal
from utils.helpers import safe_respond, safe_edit_message, build_mentions, random_loading_message


class MilitaryIdApplyView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("# 🪖 Подтверждение военного билета"))
        container.add_item(
            discord.ui.TextDisplay(
                "### Подача\n"
                "Нажмите кнопку ниже и прикрепите прямую ссылку на скриншот военного билета."
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                "### Требования\n"
                "- Скриншот полный, без обрезки и правок\n"
                "- Ссылка прямая и открывается без авторизации\n"
                "- Все данные документа читаемы"
            )
        )
        container.add_item(discord.ui.Separator(visible=True))

        button = discord.ui.Button(
            label="Отправить военный билет",
            style=discord.ButtonStyle.primary,
            custom_id="military_id_apply_btn",
        )
        button.callback = self.on_apply

        row = discord.ui.ActionRow()
        row.add_item(button)
        container.add_item(row)

        self.add_item(container)

    async def on_apply(self, interaction: discord.Interaction):
        try:
            user_db = await AuthorizationService.require_active_soldier(interaction)
            await MilitaryIdService.validate_can_apply(user_db)
            await interaction.response.send_modal(MilitaryIdModal(user_db))
        except ServiceError as error:
            await safe_respond(interaction, error.message)


class MilitaryIdManagementButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"mil_id:(?P<action>approve|reject):(?P<id>\d+)",
):
    def __init__(self, action: str, request_id: int):
        labels = {"approve": "Подтвердить", "reject": "Отклонить"}
        styles = {"approve": discord.ButtonStyle.success, "reject": discord.ButtonStyle.danger}
        emojis = {"approve": "👍", "reject": "👎"}

        super().__init__(
            discord.ui.Button(
                label=labels[action],
                emoji=emojis[action],
                style=styles[action],
                custom_id=f"mil_id:{action}:{request_id}",
            )
        )
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(match.group("action"), int(match.group("id")))

    async def _handle_reject_modal(self, interaction: discord.Interaction, officer: User) -> None:
        req = await MilitaryIdRequest.find_one(MilitaryIdRequest.id == self.request_id)
        if not req or req.status != "PENDING":
            await safe_respond(interaction, f"❌ Заявка #{self.request_id} не найдена или уже обработана.")
            return

        try:
            MilitaryIdService.validate_reviewer_permissions(officer, req.user_id)
        except ServiceError as error:
            await safe_respond(interaction, error.message)
            return

        modal = discord.ui.Modal(title="Отклонение военного билета")
        reason_input = discord.ui.TextInput(
            label="Причина отклонения",
            style=discord.TextStyle.paragraph,
            placeholder="Укажите причину (не читаем, обрезан, не совпадает имя)",
            required=True,
            max_length=500,
        )
        modal.add_item(reason_input)

        async def on_submit(modal_inter: discord.Interaction):
            await modal_inter.response.defer()
            try:
                result = await MilitaryIdService.reject_military_id(
                    interaction=modal_inter,
                    request_id=self.request_id,
                    officer=officer,
                    reason=reason_input.value.strip(),
                )
            except ServiceError as error:
                await safe_respond(modal_inter, error.message)
                return

            await modal_inter.edit_original_response(
                content=build_mentions([result.request.user_id, modal_inter.user.id]),
                embed=result.embed,
                view=result.view,
            )

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def callback(self, interaction: discord.Interaction):
        try:
            officer = await AuthorizationService.require_active_soldier(interaction)

            if self.action == "reject":
                await self._handle_reject_modal(interaction, officer)
                return

            await safe_respond(interaction, random_loading_message(), ephemeral=True)
            result = await MilitaryIdService.approve_military_id(interaction, self.request_id, officer)

            await safe_edit_message(
                message=interaction.message,
                content=build_mentions([result.request.user_id, interaction.user.id]),
                embed=result.embed,
                view=result.view,
            )
            await safe_respond(interaction, result.message)

        except ServiceError as error:
            await safe_respond(interaction, error.message)


class MilitaryIdManagementView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.add_item(MilitaryIdManagementButton("approve", request_id))
        self.add_item(MilitaryIdManagementButton("reject", request_id))