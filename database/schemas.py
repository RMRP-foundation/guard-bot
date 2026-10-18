"""Pydantic-схемы и enum'ы, которые лежат внутри таблиц (JSONB / строковые колонки)."""
import datetime
from enum import Enum

import discord
from pydantic import BaseModel


class Privilege(Enum):
    COMMANDER = 4
    DEPUTY_COMMANDER = 3
    OFFICER = 2
    DEFAULT = 1


class Position(BaseModel):
    name: str
    role_id: int
    privilege: Privilege = Privilege.DEFAULT


class Blacklist(BaseModel):
    initiator: int
    reason: str
    evidence: str
    ends_at: datetime.datetime | None = None

    def __bool__(self):
        if self.ends_at is None:
            return True
        return discord.utils.utcnow() < self.ends_at


class RoleType(str, Enum):
    ARMY = "army"  # ВС РФ


class RoleData(BaseModel):
    full_name: str
    static_id: int


class ExtendedRoleData(BaseModel):
    full_name: str
    static_id: int
    faction: str
    rank_position: str
    purpose: str | None = None  # Цель и удостоверение для гос. сотрудника
    certificate_link: str | None = None  # Только для доступа к поставке


class ReinstatementData(BaseModel):
    full_name: str
    all_documents: str
    certificate: str


class DismissalType(str, Enum):
    PJS = "ПСЖ"
    AUTO = "Потеря спец. связи"


class LeaveType(str, Enum):
    IC = "IC"
    OOC = "OOC"