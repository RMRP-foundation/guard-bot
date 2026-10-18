import logging
from dataclasses import dataclass
from typing import Callable

import discord

from core import config
from core.config import RankIndex
from core.exceptions import ServiceError
from database.counters import get_next_id
from database.models import MilitaryIdRequest, User
from services.notifications import notify_military_id_approved, notify_military_id_rejected
from ui.embeds.military_id import military_id_embed
from utils.helpers import safe_publish_request, build_officer_mentions
from utils.atomic import atomic_status_transition
from utils.permissions import is_senior_officer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MilitaryIdActionResult:
    request: MilitaryIdRequest
    embed: discord.Embed
    view: discord.ui.View
    message: str


class MilitaryIdService:

    @staticmethod
    async def validate_can_apply(user_db: User) -> None:
        """Проверяет, нет ли уже активной заявки на рассмотрении."""
        existing = await MilitaryIdRequest.find_one(
            MilitaryIdRequest.user_id == user_db.discord_id,
            MilitaryIdRequest.status == "PENDING",
        )
        if existing:
            raise ServiceError(f"❌ У вас уже есть активная заявка #{existing.id} на рассмотрении.")

    @staticmethod
    def validate_reviewer_permissions(officer: User, applicant_id: int) -> None:
        """Проверяет права на проверку: только Майор+, нельзя проверять себя."""
        if officer.discord_id == applicant_id:
            raise ServiceError("❌ Вы не можете проверять собственный военный билет.")

        if not is_senior_officer(officer):
            raise ServiceError(f"❌ Проверять военный билет разрешено со звания {config.RANKS[RankIndex.MAJOR]}+.")

    @staticmethod
    async def create_request(user_id: int, full_name: str, evidence: str) -> MilitaryIdRequest:
        new_id = await get_next_id("military_id_requests")
        request = MilitaryIdRequest(
            id=new_id,
            user_id=user_id,
            full_name=full_name,
            evidence=evidence,
            status="PENDING",
        )
        await request.create()
        return request

    @staticmethod
    async def publish_request(
        interaction: discord.Interaction, request: MilitaryIdRequest, user_db: User, view: discord.ui.View,
    ) -> None:
        await safe_publish_request(
            channel=interaction.channel,
            request=request,
            embed=military_id_embed(request, user_db),
            content=build_officer_mentions(request.user_id, min_rank_index=RankIndex.MAJOR),
            view=view,
            error_message="❌ Не удалось отправить заявку в канал. Попробуйте ещё раз.",
        )

        from cogs.military_id import update_bottom_message
        await update_bottom_message(interaction.client)

    @classmethod
    async def submit_military_id(
        cls, interaction: discord.Interaction, user_db: User, evidence: str, view_factory: Callable[[int], discord.ui.View],
    ) -> None:
        await cls.validate_can_apply(user_db)
        full_name = user_db.full_name or interaction.user.display_name
        request = await cls.create_request(user_id=interaction.user.id, full_name=full_name, evidence=evidence)
        await cls.publish_request(interaction=interaction, request=request, user_db=user_db, view=view_factory(request.id))

    @classmethod
    async def approve_military_id(cls, interaction: discord.Interaction, request_id: int, officer: User) -> MilitaryIdActionResult:
        req = await MilitaryIdRequest.find_one(MilitaryIdRequest.id == request_id)
        if not req or req.status != "PENDING":
            raise ServiceError(f"❌ Заявка #{request_id} не найдена или уже обработана.")

        cls.validate_reviewer_permissions(officer, req.user_id)

        updated_dict = await atomic_status_transition(
            MilitaryIdRequest,
            request_id,
            "PENDING",
            "APPROVED",
            extra_fields={"reviewer_id": interaction.user.id, "reviewed_at": discord.utils.utcnow()},
        )
        if not updated_dict:
            raise ServiceError(f"❌ Заявка #{request_id} уже обработана.")

        request = MilitaryIdRequest(**updated_dict)
        target_user = await User.get_by_discord_id(request.user_id)

        if target_user:
            target_user.has_military_id = True
            await target_user.save()

        member = await interaction.client.getch_member(request.user_id)
        if member and hasattr(config.RoleId, "MILITARY_ID"):
            role = member.guild.get_role(config.RoleId.MILITARY_ID.value)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Подтверждён военный билет")
                except discord.HTTPException:
                    pass

        await notify_military_id_approved(interaction.client, request.user_id)

        from ui.views.indicators import indicator_view
        return MilitaryIdActionResult(
            request=request,
            embed=military_id_embed(request, target_user),
            view=indicator_view(f"Подтвердил {interaction.user.display_name}", emoji="👍"),
            message="✅ Военный билет успешно подтверждён.",
        )

    @classmethod
    async def reject_military_id(
        cls, interaction: discord.Interaction, request_id: int, officer: User, reason: str,
    ) -> MilitaryIdActionResult:
        req = await MilitaryIdRequest.find_one(MilitaryIdRequest.id == request_id)
        if not req or req.status != "PENDING":
            raise ServiceError(f"❌ Заявка #{request_id} не найдена или уже обработана.")

        cls.validate_reviewer_permissions(officer, req.user_id)

        updated_dict = await atomic_status_transition(
            MilitaryIdRequest,
            request_id,
            "PENDING",
            "REJECTED",
            extra_fields={
                "reviewer_id": interaction.user.id,
                "reviewed_at": discord.utils.utcnow(),
                "reject_reason": reason,
            },
        )
        if not updated_dict:
            raise ServiceError(f"❌ Заявка #{request_id} уже обработана.")

        request = MilitaryIdRequest(**updated_dict)
        target_user = await User.get_by_discord_id(request.user_id)
        await notify_military_id_rejected(interaction.client, request.user_id, reason)

        from ui.views.indicators import indicator_view
        return MilitaryIdActionResult(
            request=request,
            embed=military_id_embed(request, target_user),
            view=indicator_view(f"Отклонил {interaction.user.display_name}", emoji="👎"),
            message="❌ Военный билет отклонён.",
        )