import logging

import discord

from core.exceptions import ServiceError
from database.models import DismissalType, User, DismissalRequest
from services.authorization import AuthorizationService
from services.dismissal import DismissalService
from ui.modals.dismissal import DismissalModal
from ui.modals.reason import ReasonModal
from utils.helpers import safe_respond, build_mentions, safe_edit_message, safe_delete_message, random_loading_message, require_request
from utils.permissions import is_officer, has_disciplinary_restrictions, is_higher_rank

logger = logging.getLogger(__name__)


async def _open_dismissal_modal(interaction: discord.Interaction, d_type: DismissalType) -> None:
    """Проверяет отсутствие ограничений и открывает модалку подачи рапорта."""
    try:
        user_db = await AuthorizationService.require_active_soldier(interaction)
    except ServiceError as error:
        await safe_respond(interaction, error.message)
        return

    if has_disciplinary_restrictions(interaction.user):
        await safe_respond(
            interaction,
            "❌ Вы не можете подать рапорт на увольнение, "
            "пока у вас есть активные дисциплинарные взыскания.",
        )
        return

    full_name = user_db.full_name or ""
    await interaction.response.send_modal(DismissalModal(d_type, full_name))


class DismissalApplyView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay("# Рапорт на увольнение"))
    container.add_item(
        discord.ui.TextDisplay(
            "### Подача рапорта\n"
            "Нажмите соответствующую кнопку ниже.\n\n"
            "**Примечание:**\n"
            "- Если вы не отработали 5 дней во фракции, вы попадете в ЧС на 14 дней.\n"
            "- Заполняйте данные корректно, как в паспорте."
        )
    )
    container.add_item(discord.ui.Separator(visible=True))

    psj_button = discord.ui.Button(
        label="ПСЖ", style=discord.ButtonStyle.primary, custom_id="dismissal_pjs"
    )
    psj_button.callback = lambda inter: _open_dismissal_modal(inter, DismissalType.PJS)

    action_row = discord.ui.ActionRow()
    action_row.add_item(psj_button)
    container.add_item(action_row)


class DismissalManagementButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"dismissal:(?P<action>approve|reject):(?P<id>\d+)",
):
    def __init__(self, action: str, request_id: int):
        labels = {"approve": ("Одобрить", discord.ButtonStyle.success), "reject": ("Отклонить", discord.ButtonStyle.danger)}
        label, style = labels[action]
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=f"dismissal:{action}:{request_id}"))
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match.group("action"), int(match.group("id")))

    async def _handle_reject_modal(self, interaction: discord.Interaction, officer: User) -> None:
        req = await require_request(
            DismissalRequest, self.request_id,
            error_message=f"❌ Рапорт #{self.request_id} не найден или уже обработан.",
        )
        target_user_db = await User.get_by_discord_id(req.user_id)
        if not target_user_db or not is_higher_rank(officer, target_user_db):
            raise ServiceError("❌ Вы не можете обрабатывать рапорт равного или старшего звания.")

        async def on_submit(modal_inter: discord.Interaction, reason: str):
            await modal_inter.response.defer()
            try:
                result = await DismissalService.reject_dismissal(
                    interaction=modal_inter, request_id=self.request_id,
                    officer_user_db=officer, reason=reason,
                )
            except ServiceError as error:
                await modal_inter.followup.send(error.message, ephemeral=True)
                return

            await modal_inter.edit_original_response(
                content=build_mentions([result.request.user_id, modal_inter.user.id]),
                embed=result.embed, view=result.view,
            )
            await modal_inter.followup.send(result.message, ephemeral=True)

        await interaction.response.send_modal(
            ReasonModal("Отклонение рапорта на увольнение", on_submit, label="Причина отказа")
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            officer = await AuthorizationService.require_active_soldier(interaction)
            if not is_officer(officer):
                raise ServiceError("❌ Доступно со звания Капитан.")

            if self.action == "reject":
                await self._handle_reject_modal(interaction, officer)
                return

            await safe_respond(interaction, random_loading_message())

            result = await DismissalService.approve_dismissal(
                interaction=interaction, request_id=self.request_id, officer_user_db=officer,
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


class DismissalCancelButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"dismissal_cancel:(?P<id>\d+)",
):
    def __init__(self, request_id: int):
        super().__init__(discord.ui.Button(label="Отменить", style=discord.ButtonStyle.grey, custom_id=f"dismissal_cancel:{request_id}"))
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match.group("id")))

    async def callback(self, interaction: discord.Interaction):
        try:
            await DismissalService.cancel_dismissal(interaction=interaction, request_id=self.request_id)
            await safe_delete_message(interaction.message)
            await safe_respond(interaction, "✅ Ваш рапорт на увольнение был отменен.", ephemeral=True)
        except ServiceError as error:
            await safe_respond(interaction, error.message)


class DismissalManagementView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.add_item(DismissalManagementButton("approve", request_id))
        self.add_item(DismissalManagementButton("reject", request_id))
        self.add_item(DismissalCancelButton(request_id))
