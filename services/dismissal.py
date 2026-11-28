import logging
from dataclasses import dataclass
from typing import Callable

import discord

from core import config
from core.exceptions import ServiceError
from database.counters import get_next_id
from database.models import User, DismissalRequest, DismissalType
from database.status import RequestStatus
from services.audit import AuditAction, audit_logger
from services.member import MemberService
from services.notifications import notify_dismissed, notify_blacklisted
from ui.embeds.dismissal import dismissal_embed
from utils.dismissal_logic import check_and_apply_penalty, cleanup_user_leaves
from utils.helpers import build_request_mentions, safe_publish_request, require_no_active_request, require_request
from utils.atomic import atomic_transition
from utils.permissions import is_higher_rank
from utils.user_data import set_name_if_changed

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DismissalActionResult:
    """Результат approve/reject: данные для отрисовки, без единого discord-вызова внутри сервиса."""
    request: DismissalRequest
    embed: discord.Embed
    message: str
    view: discord.ui.View | None = None


class DismissalService:

    @staticmethod
    async def validate_no_active_request(user_id: int) -> None:
        await require_no_active_request(DismissalRequest, user_id)

    @staticmethod
    async def create_request(user: User, full_name: str, dismissal_type: DismissalType) -> DismissalRequest:
        """Создаёт и сохраняет заявку на увольнение со снимком текущих данных бойца."""
        new_id = await get_next_id("dismissal_requests")
        request = DismissalRequest(
            id=new_id,
            user_id=user.discord_id,
            type=dismissal_type,
            full_name=full_name,
            static=user.static,
            rank_index=user.rank,
            division_id=user.division,
            position=user.position,
        )
        await request.create()
        return request

    @staticmethod
    async def publish_request(bot: discord.Client, request: DismissalRequest, user_id: int,
                              division_id: int | None, view: discord.ui.View) -> None:
        """Публикует заявку в служебный канал увольнений и обновляет статус-бар подразделения."""
        embed = dismissal_embed(request)
        content_mentions = build_request_mentions(user_id=user_id, user_division_id=division_id)
        channel = bot.get_channel(config.CHANNELS["dismissal"])

        await safe_publish_request(channel=channel, request=request, embed=embed, content=content_mentions, view=view)

        from services.bottom_messages import request_refresh
        await request_refresh(bot, config.CHANNELS["dismissal"])

    @staticmethod
    async def submit_dismissal(bot: discord.Client, user: User, full_name: str,
                               dismissal_type: DismissalType, view_factory: Callable[[int], discord.ui.View]) -> None:
        """Оформляет и публикует рапорт на увольнение от имени бойца.

        Raises:
            ServiceError: Если у бойца уже есть активный рапорт, либо публикация не удалась.
        """
        await DismissalService.validate_no_active_request(user.discord_id)
        request = await DismissalService.create_request(user, full_name, dismissal_type)
        await DismissalService.publish_request(
            bot=bot,
            request=request,
            user_id=user.discord_id,
            division_id=user.division,
            view=view_factory(request.id),
        )

    @staticmethod
    async def _get_request_and_target(request_id: int) -> tuple[DismissalRequest, User]:
        req = await require_request(
            DismissalRequest, request_id,
            error_message=f"❌ Рапорт #{request_id} не найден или уже обработан.",
        )

        target_user_db = await User.get_by_discord_id(req.user_id)
        if not target_user_db:
            raise ServiceError("❌ Пользователь не найден в БД.")

        return req, target_user_db

    @classmethod
    async def _reject_already_dismissed(cls, request_id: int, reviewer_id: int) -> DismissalActionResult:
        request = await cls._apply_atomic_status_change(
            request_id, RequestStatus.REJECTED, reviewer_id,
            reject_reason="Сотрудник уже уволен.",
        )
        return DismissalActionResult(
            request=request,
            embed=dismissal_embed(request),
            message="❌ Сотрудник уже уволен. Рапорт отклонён.",
        )

    @staticmethod
    async def _apply_atomic_status_change(
        request_id: int, new_status: str, reviewer_id: int, reject_reason: str | None = None,
    ) -> DismissalRequest:
        """Атомарно переводит заявку из PENDING в новый статус."""
        extra_fields = {"reviewer_id": reviewer_id, "reviewed_at": discord.utils.utcnow()}
        if reject_reason is not None:
            extra_fields["reject_reason"] = reject_reason

        return await atomic_transition(
            DismissalRequest, request_id, RequestStatus.PENDING, new_status,
            extra_fields=extra_fields,
            error_message=f"❌ Рапорт #{request_id} не найден или уже обработан.",
        )

    @classmethod
    async def _execute_dismissal(
            cls,
            interaction: discord.Interaction,
            request: DismissalRequest,
            target_user_db: User,
            officer_user_db: User,
    ) -> bool:
        """Применяет увольнение: аудит, ЧС, обнуление профиля в БД, зачистка отпусков, синк ролей и ДМ.

        Возвращает True, если был наложен ЧС за неустойку.
        """
        # 1. Логируем увольнение в канал аудита
        audit_msg = await audit_logger.log_action(
            AuditAction.DISMISSED,
            interaction.user,
            request.user_id,
            additional_info={"Причина": f"[Рапорт на увольнение #{request.id}]({interaction.message.jump_url})"},
        )

        # 2. Проверяем неустойку
        penalty_applied = await check_and_apply_penalty(
            interaction, target_user_db, officer_user_db, audit_msg.jump_url
        )

        # 3. Обнуляем статус военнослужащего в БД
        set_name_if_changed(target_user_db, request.full_name)
        target_user_db.rank = None
        target_user_db.division = None
        target_user_db.position = None
        await target_user_db.save()

        # 4. Аннулируем/отклоняем активные отпуска
        await cleanup_user_leaves(interaction.client, request.user_id)

        # 5. Синхронизируем роли и никнейм на сервере Discord
        target_member = await interaction.client.getch_member(request.user_id)
        if target_member:
            await MemberService.sync_member_discord(
                member=target_member,
                user_db=target_user_db,
                reason=f"Увольнение по рапорту #{request.id}",
            )

        # 6. Уведомляем уволенного в ЛС
        await notify_dismissed(
            interaction.client,
            request.user_id,
            f"Увольнение по рапорту #{request.id}",
            by_report=True,
        )
        if penalty_applied:
            await notify_blacklisted(interaction.client, request.user_id, "Неустойка", "14 дней")

        return penalty_applied

    @classmethod
    async def approve_dismissal(cls, interaction: discord.Interaction, request_id: int,
                                officer_user_db: User) -> DismissalActionResult:
        _, target_user_db = await cls._get_request_and_target(request_id)
        if target_user_db.rank is None:
            return await cls._reject_already_dismissed(request_id, officer_user_db.discord_id)
        if not is_higher_rank(officer_user_db, target_user_db):
            raise ServiceError("❌ Вы не можете обрабатывать рапорт военнослужащего равного или старшего звания.")

        request = await cls._apply_atomic_status_change(request_id, RequestStatus.APPROVED, interaction.user.id)
        penalty_applied = await cls._execute_dismissal(interaction, request, target_user_db, officer_user_db)

        embed = dismissal_embed(request)
        if penalty_applied:
            embed.set_footer(text="Автоматически выдан ЧС за неустойку.")
        return DismissalActionResult(request=request, embed=embed, message="✅ Рапорт одобрен, сотрудник уволен.")

    @classmethod
    async def reject_dismissal(cls, interaction: discord.Interaction, request_id: int, officer_user_db: User,
                               reason: str) -> DismissalActionResult:
        _, target_user_db = await cls._get_request_and_target(request_id)
        if target_user_db.rank is None:
            return await cls._reject_already_dismissed(request_id, officer_user_db.discord_id)
        if not is_higher_rank(officer_user_db, target_user_db):
            raise ServiceError("❌ Вы не можете обрабатывать рапорт военнослужащего равного или старшего звания.")

        request = await cls._apply_atomic_status_change(request_id, RequestStatus.REJECTED, interaction.user.id,
                                                        reject_reason=reason)
        return DismissalActionResult(request=request, embed=dismissal_embed(request), message="✅ Рапорт отклонён.")

    @staticmethod
    async def cancel_dismissal(interaction: discord.Interaction, request_id: int) -> None:
        """Атомарно отменяет собственный рапорт автором. Удаление сообщения — на вызывающем.

        Raises:
            ServiceError: Если рапорт не найден или уже обработан.
        """
        await atomic_transition(
            DismissalRequest, request_id, RequestStatus.PENDING, RequestStatus.REJECTED,
            extra_fields={"reviewed_at": discord.utils.utcnow()},
            extra_filter={"user_id": interaction.user.id},
            error_message="❌ Рапорт не найден или уже обработан.",
        )
