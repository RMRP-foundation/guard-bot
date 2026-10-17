from .dismissal import (
    DismissalApplyView,
    DismissalCancelButton,
    DismissalManagementButton,
)
from .leave import ICLeaveApplyView, OOCLeaveApplyView, LeaveManagementButton
from .military_id import MilitaryIdApplyView, MilitaryIdManagementButton
from .promotion import (
    PromoteButton,
    PromotionApplyView,
    PromotionManagementButton,
)
from .materials import MaterialsReportView
from .reinstatement import (
    ReinstatementApplyView,
    ReinstatementManagementButton,
    ReinstatementRankSelect,
)
from .role_getting import RoleApplyView, RoleManagementButton
from .patrol import PatrolApplyView, PatrolManagementButton
from .supplies import SupplyCreateView, SupplyManageButton
from .supplies_audit import SupplyAuditView
from .timeoff import TimeoffApplyView, TimeoffCancelButton, TimeoffManagementButton
from .transfers import (
    ApproveNewDivisionButton,
    ApproveOldDivisionButton,
    RejectTransferButton,
    TransferApplyButton,
    CancelTransferButton,
)


def load_persistent_views(bot):
    bot.add_view(ReinstatementApplyView())
    bot.add_view(RoleApplyView())
    bot.add_view(SupplyCreateView())
    bot.add_view(SupplyAuditView())
    bot.add_view(DismissalApplyView())
    bot.add_view(TimeoffApplyView())
    bot.add_view(PatrolApplyView())
    bot.add_view(MaterialsReportView())
    bot.add_view(ICLeaveApplyView())
    bot.add_view(OOCLeaveApplyView())
    bot.add_view(PromotionApplyView())
    bot.add_view(MilitaryIdApplyView())

def load_buttons(bot):
    bot.add_dynamic_items(
        ReinstatementManagementButton,
        ReinstatementRankSelect,
        RoleManagementButton,
        SupplyManageButton,
        DismissalManagementButton,
        DismissalCancelButton,
        TransferApplyButton,
        ApproveNewDivisionButton,
        ApproveOldDivisionButton,
        RejectTransferButton,
        CancelTransferButton,
        TimeoffManagementButton,
        TimeoffCancelButton,
        PatrolManagementButton,
        LeaveManagementButton,
        PromotionManagementButton,
        PromoteButton,
        MilitaryIdManagementButton,
    )
    load_persistent_views(bot)
