import datetime

import discord
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, desc
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core import constants
from database.base import Doc, PydanticJSON
# Re-export: остальной код импортирует эти имена из database.models
from database.schemas import (  # noqa: F401
    Blacklist, DismissalType, ExtendedRoleData, LeaveType, Position, Privilege,
    ReinstatementData, RoleData, RoleType,
)

BigInt = BigInteger
TZ = DateTime(timezone=True)


def _enum(enum_cls) -> SAEnum:
    # В БД лежит .value ("IC", "ПСЖ"), как раньше в Mongo
    return SAEnum(enum_cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


def _pk() -> Mapped[int]:
    # id заявок выдаёт get_next_id() (nextval), поэтому в конструктор передаётся явно
    return mapped_column(Integer, primary_key=True, autoincrement=True)


def _now() -> Mapped[datetime.datetime]:
    return mapped_column(TZ, default_factory=discord.utils.utcnow)


class Division(Doc):
    __tablename__ = "divisions"

    division_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String)
    abbreviation: Mapped[str] = mapped_column(String)
    role_id: Mapped[int] = mapped_column(BigInt)
    transfer_channel: Mapped[int | None] = mapped_column(BigInt, default=None)
    description: Mapped[str | None] = mapped_column(String, default=None)
    emoji: Mapped[str | None] = mapped_column(String, default=None)
    positions: Mapped[list[Position] | None] = mapped_column(PydanticJSON(list[Position]), default=None)
    promotion_channel: Mapped[int | None] = mapped_column(BigInt, default=None)

    def get_position_by_name(self, name: str) -> Position | None:
        if not self.positions:
            return None
        for pos in self.positions:
            if pos.name.lower() == name.lower():
                return pos
        return None


class User(Doc):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_division_rank", "division", desc("rank")),)

    discord_id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=False)
    static: Mapped[int | None] = mapped_column(Integer, default=None)
    first_name: Mapped[str | None] = mapped_column(String, default=None)
    last_name: Mapped[str | None] = mapped_column(String, default=None)
    rank: Mapped[int | None] = mapped_column(Integer, default=None)
    position: Mapped[str | None] = mapped_column(String, default=None)
    division: Mapped[int | None] = mapped_column(Integer, default=None)
    leave_status: Mapped[str | None] = mapped_column(String, default=None)
    invited_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    blacklist: Mapped[Blacklist | None] = mapped_column(PydanticJSON(Blacklist), default=None)
    last_supply_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    has_military_id: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_inited: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def full_name(self) -> str | None:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name

    @property
    def short_name(self) -> str | None:
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}. {self.last_name}"
        return None

    @property
    def discord_nick(self) -> str:
        from database import divisions
        from utils.user_data import transliterate_abbreviation
        from core.config import DivisionId

        parts = []
        if self.leave_status:
            parts.append(self.leave_status)

        if self.division is not None:
            div = divisions.get_division(self.division)
            if div:
                if div.division_id == DivisionId.AVNG:
                    parts.append(div.abbreviation)
                else:
                    parts.append(transliterate_abbreviation(div.abbreviation))
        if self.rank is not None:
            parts.append(constants.RANKS_SHORT[self.rank])
        if self.full_name:
            if len(" | ".join(parts + [self.full_name])) > 32:
                parts.append(self.short_name or self.full_name)
            else:
                parts.append(self.full_name)
        return " | ".join(parts)[:32]

    @staticmethod
    async def get_active_soldier(discord_id: int) -> "User | None":
        """Возвращает пользователя, если он состоит на службе (rank задан), иначе None."""
        user = await User.get_by_discord_id(discord_id)
        if not user or user.rank is None:
            return None
        return user

    @classmethod
    async def get_by_discord_id(cls, discord_id: int) -> "User | None":
        """Находит пользователя в базе данных по его Discord ID."""
        return await cls.find_one(cls.discord_id == discord_id)


class ReinstatementRequest(Doc):
    __tablename__ = "reinstatement_requests"

    id: Mapped[int] = _pk()
    user: Mapped[int] = mapped_column(BigInt)
    data: Mapped[ReinstatementData] = mapped_column(PydanticJSON(ReinstatementData))
    status: Mapped[str] = mapped_column(String, default="PENDING")
    rank: Mapped[int | None] = mapped_column(Integer, default=None)
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    reject_reason: Mapped[str | None] = mapped_column(String, default=None)
    sent_at: Mapped[datetime.datetime] = _now()


class RoleRequest(Doc):
    __tablename__ = "role_requests"

    id: Mapped[int] = _pk()
    user: Mapped[int] = mapped_column(BigInt)
    role_type: Mapped[RoleType] = mapped_column(_enum(RoleType), default=RoleType.ARMY)
    data: Mapped[RoleData | None] = mapped_column(PydanticJSON(RoleData), default=None)
    extended_data: Mapped[ExtendedRoleData | None] = mapped_column(PydanticJSON(ExtendedRoleData), default=None)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    sent_at: Mapped[datetime.datetime] = _now()
    message_id: Mapped[int | None] = mapped_column(BigInt, default=None)


class TimeoffRequest(Doc):
    __tablename__ = "timeoff_requests"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    data: Mapped[RoleData] = mapped_column(PydanticJSON(RoleData))
    status: Mapped[str] = mapped_column(String, default="PENDING")
    period: Mapped[str | None] = mapped_column(String, default=None)
    sent_at: Mapped[datetime.datetime] = _now()
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)


class SupplyRequest(Doc):
    __tablename__ = "supply_requests"
    __table_args__ = (Index("ix_supply_user_status_created", "user_id", "status", desc("created_at")),)

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    items: Mapped[dict[str, int]] = mapped_column(JSONB, default_factory=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    message_id: Mapped[int | None] = mapped_column(BigInt, default=None)


class DismissalRequest(Doc):
    __tablename__ = "dismissal_requests"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    type: Mapped[DismissalType] = mapped_column(_enum(DismissalType))
    full_name: Mapped[str] = mapped_column(String)
    static: Mapped[int] = mapped_column(Integer)
    rank_index: Mapped[int | None] = mapped_column(Integer, default=None)
    division_id: Mapped[int | None] = mapped_column(Integer, default=None)
    position: Mapped[str | None] = mapped_column(String, default=None)
    reject_reason: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)


class TransferRequest(Doc):
    __tablename__ = "transfer_requests"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    full_name: Mapped[str] = mapped_column(String)
    static: Mapped[int] = mapped_column(Integer)
    name_age: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String)
    online_prime: Mapped[str] = mapped_column(String)
    motivation: Mapped[str] = mapped_column(String)
    new_division_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    old_division_id: Mapped[int] = mapped_column(Integer, default=0)
    old_reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    new_reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    old_reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    new_reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    reject_reason: Mapped[str | None] = mapped_column(String, default=None)


class PatrolRequest(Doc):
    __tablename__ = "patrol_requests"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    full_name: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    date: Mapped[datetime.datetime] = _now()
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)


class MaterialsReport(Doc):
    __tablename__ = "materials_reports"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    full_name: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = _now()


class LeaveRequest(Doc):
    __tablename__ = "leave_requests"
    __table_args__ = (Index("ix_leave_status_ends", "status", "ends_at"),)

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    leave_type: Mapped[LeaveType] = mapped_column(_enum(LeaveType))
    reason: Mapped[str] = mapped_column(String)
    starts_at: Mapped[datetime.datetime] = mapped_column(TZ)
    ends_at: Mapped[datetime.datetime] = mapped_column(TZ)
    original_nick: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    annuller_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    annulled_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    approved_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)
    message_id: Mapped[int | None] = mapped_column(BigInt, default=None)


class PromotionRequest(Doc):
    __tablename__ = "promotion_reports"
    __table_args__ = (Index("ix_promotion_user_status", "user_id", "status"),)

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    division_id: Mapped[int] = mapped_column(Integer)
    current_rank: Mapped[int] = mapped_column(Integer)
    target_rank: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict[str, str]] = mapped_column(JSONB, default_factory=dict)
    score: Mapped[str | None] = mapped_column(String, default=None)
    reject_reason: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    promoted_by: Mapped[int | None] = mapped_column(BigInt, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    message_id: Mapped[int | None] = mapped_column(BigInt, default=None)


class MilitaryIdRequest(Doc):
    __tablename__ = "military_id_requests"

    id: Mapped[int] = _pk()
    user_id: Mapped[int] = mapped_column(BigInt)
    full_name: Mapped[str] = mapped_column(String)
    evidence: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    reviewer_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    reject_reason: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime.datetime] = _now()
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZ, default=None)


class BottomMessage(Doc):
    __tablename__ = "bottom_messages"

    channel_id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=False)
    message_id: Mapped[int] = mapped_column(BigInt)