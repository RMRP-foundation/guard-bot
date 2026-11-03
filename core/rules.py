from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.constants import Privilege, RoleType, RankIndex, DivisionId

if TYPE_CHECKING:
    from database.models import User


@dataclass(frozen=True, slots=True)
class DivisionRule:
    review_rank: int
    promote_rank: int = RankIndex.MAJOR
    review_positions: tuple[str, ...] = ()
    promote_positions: tuple[str, ...] = ()
    reviewer_division_id: int | None = None

    def can_review(self, user: User) -> bool:
        if (user.rank or 0) >= self.review_rank:
            return True
        if user.position and self.review_positions:
            return user.position.strip().lower() in {p.lower() for p in self.review_positions}
        return False

    def can_promote(self, user: User) -> bool:
        if (user.rank or 0) >= self.promote_rank:
            return True
        if user.position and self.promote_positions:
            return user.position.strip().lower() in {p.lower() for p in self.promote_positions}
        return False


PROMOTION_RULES: dict[int, DivisionRule] = {
    DivisionId.AVNG: DivisionRule(
        review_rank=RankIndex.MAJOR,
        promote_rank=RankIndex.MAJOR,
        review_positions=("Инструктор", "Главный инструктор"),
        reviewer_division_id=DivisionId.CPP,
    ),
    DivisionId.CPP: DivisionRule(
        review_rank=RankIndex.MAJOR,
        promote_rank=RankIndex.MAJOR,
        review_positions=("Главный инструктор",),
    ),
    DivisionId.USB: DivisionRule(
        review_rank=RankIndex.MAJOR,
        promote_rank=RankIndex.MAJOR,
    ),
    DivisionId.OMON: DivisionRule(
        review_rank=RankIndex.MAJOR,
        promote_rank=RankIndex.MAJOR,
    ),
    DivisionId.SOBR: DivisionRule(
        review_rank=RankIndex.MAJOR,
        promote_rank=RankIndex.MAJOR,
        review_positions=("Инструктор",),
    ),
}

DIVISION_EXTERNAL_GRANT_CEILING: dict[DivisionId, Privilege] = {
    DivisionId.GENERAL_STAFF: Privilege.COMMANDER,
}

ROLE_REQUIRED_RANKS = {
    RoleType.ARMY: "Младший лейтенант",
}

ROLE_REQUIRED_RANK_INDICES = {
    RoleType.ARMY: RankIndex.JUNIOR_LIEUTENANT,
}
