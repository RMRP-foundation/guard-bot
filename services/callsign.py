import logging
import re
from dataclasses import dataclass
from typing import Callable

import discord

from core.exceptions import ServiceError
from database import divisions
from database.counters import get_next_id
from database.models import CallsignRequest, User
from database.status import RequestStatus
from ui.embeds.callsign import callsign_embed
from utils.atomic import atomic_status_transition
from utils.helpers import build_request_mentions, safe_publish_request
from utils.permissions import is_high_command

logger = logging.getLogger(__name__)

_FIO_REGEX = re.compile(r"^[А-ЯЁа-яё]{2,} [А-ЯЁа-яё]{2,} [А-ЯЁа-яё]{2,}$")
_CALLSIGN_WORD_REGEX = re.compile(r"^[А-ЯЁа-яё]{2,}$")
_CALLSIGN_NUM_REGEX = re.compile(r"^\d{2}-[йя]$")

_STATUS_ACTION = {
    "approve": (RequestStatus.APPROVED, "Одобрил", "👍", "✅ Заявка на позывной одобрена."),
    "reject": (RequestStatus.REJECTED, "Отклонил", "👎", "❌ Заявка на позывной отклонена."),
}


@dataclass(frozen=True)
class CallsignActionResult:
    request: CallsignRequest
    embed: discord.Embed
    view: discord.ui.View
    message: str


class CallsignService:

    @staticmethod
    def validate_fio(raw: str, user_db: User | None = None) -> str:
        error_msg = "❌ Некорректное ФИО. Правильный формат: Смирнов Александр Сергеевич."
        cleaned = " ".join(raw.split())
        if not _FIO_REGEX.match(cleaned):
            raise ServiceError(error_msg)

        w1, w2, w3 = (word.capitalize() for word in cleaned.split())

        if user_db and user_db.first_name and user_db.last_name:
            norm = lambda s: s.lower().replace("ё", "е")
            if norm(w1) != norm(user_db.last_name) or norm(w2) != norm(user_db.first_name):
                raise ServiceError(error_msg)

        return f"{w1} {w2} {w3}"

    @staticmethod
    def validate_callsign(raw: str, user_db: User) -> str:
        parts = raw.split()
        if len(parts) != 2:
            raise ServiceError(
                "❌ Позывной должен состоять из двух частей. Пример: Кедр 49-й."
            )

        word, number_part = parts[0].capitalize(), parts[1].lower()

        if not _CALLSIGN_WORD_REGEX.match(word):
            raise ServiceError(
                "❌ Первая часть позывного должна быть одним словом на кириллице. Пример: Кедр 49-й."
            )

        if not _CALLSIGN_NUM_REGEX.match(number_part):
            raise ServiceError(
                "❌ Вторая часть должна быть в формате ХХ-й или ХХ-я. Пример: Кедр 49-й."
            )

        if user_db.static is not None:
            expected_digits = str(user_db.static).zfill(6)[-2:]
            if not number_part.startswith(expected_digits):
                raise ServiceError(
                    f"❌ Цифры позывного должны совпадать с двумя последними цифрами вашего статика ({expected_digits})."
                )

        return f"{word} {number_part}"

    @staticmethod
    async def validate_can_apply(user_db: User) -> None:
        existing = await CallsignRequest.find_one(
            CallsignRequest.user_id == user_db.discord_id,
            CallsignRequest.status == RequestStatus.PENDING,
        )
        if existing:
            raise ServiceError(f"❌ У вас уже есть активная заявка #{existing.id} на рассмотрении.")

    @staticmethod
    def validate_reviewer_permissions(officer: User, applicant: User | None) -> None:
        if is_high_command(officer):
            return

        if officer.division is not None and (applicant is None or officer.division == applicant.division):
            div = divisions.get_division(officer.division)
            if div and div.positions:
                if any(p.name == officer.position and p.privilege.value >= 2 for p in div.positions):
                    return

        raise ServiceError("❌ Рассматривать заявки может только руководство подразделения или высшее командование.")

    @staticmethod
    async def create_request(user_id: int, full_name: str, callsign: str) -> CallsignRequest:
        new_id = await get_next_id("callsign_requests")
        request = CallsignRequest(
            id=new_id,
            user_id=user_id,
            full_name=full_name,
            callsign=callsign,
            status=RequestStatus.PENDING,
        )
        await request.create()
        return request

    @staticmethod
    async def publish_request(
        interaction: discord.Interaction,
        request: CallsignRequest,
        user_db: User,
        view: discord.ui.View,
    ) -> None:
        await safe_publish_request(
            channel=interaction.channel,
            request=request,
            embed=callsign_embed(request, user_db),
            content=build_request_mentions(user_id=user_db.discord_id, user_division_id=user_db.division),
            view=view,
        )

        from services.bottom_messages import request_refresh
        await request_refresh(interaction.client, interaction.channel_id)

    @classmethod
    async def submit_callsign(
        cls,
        interaction: discord.Interaction,
        user_db: User,
        full_name: str,
        callsign: str,
        view_factory: Callable[[int], discord.ui.View],
    ) -> None:
        await cls.validate_can_apply(user_db)
        valid_fio = cls.validate_fio(full_name, user_db)
        valid_callsign = cls.validate_callsign(callsign, user_db)

        request = await cls.create_request(
            user_id=interaction.user.id,
            full_name=valid_fio,
            callsign=valid_callsign,
        )
        await cls.publish_request(
            interaction=interaction,
            request=request,
            user_db=user_db,
            view=view_factory(request.id),
        )

    @classmethod
    async def process_callsign(
        cls,
        interaction: discord.Interaction,
        request_id: int,
        action: str,
        officer: User,
    ) -> CallsignActionResult:
        req = await CallsignRequest.find_one(CallsignRequest.id == request_id)
        if not req or req.status != RequestStatus.PENDING:
            raise ServiceError(f"❌ Заявка #{request_id} не найдена или уже обработана.")

        target_user = await User.get_by_discord_id(req.user_id)
        cls.validate_reviewer_permissions(officer, target_user)

        target_status, label, emoji, msg = _STATUS_ACTION[action]
        updated_dict = await atomic_status_transition(
            CallsignRequest,
            request_id,
            RequestStatus.PENDING,
            target_status,
            extra_fields={"reviewer_id": interaction.user.id, "reviewed_at": discord.utils.utcnow()},
        )
        if not updated_dict:
            raise ServiceError(f"❌ Заявка #{request_id} уже обработана.")

        request = CallsignRequest(**updated_dict)

        from ui.views.indicators import indicator_view
        return CallsignActionResult(
            request=request,
            embed=callsign_embed(request, target_user),
            view=indicator_view(f"{label} {interaction.user.display_name}", emoji=emoji),
            message=msg,
        )