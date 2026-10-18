import logging
import os
from enum import Enum, IntEnum

from dotenv import load_dotenv

from core.constants import RANKS, RankIndex
from database.models import RoleType, Privilege
from utils.permissions import DivisionRule

load_dotenv()

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise Exception("TOKEN not found")

ENVIRONMENT = os.getenv("ENVIRONMENT")
if not ENVIRONMENT:
    raise Exception("ENVIRONMENT not set")

SENTRY_DSN = os.getenv("SENTRY_DSN")

IS_PRODUCTION = ENVIRONMENT.lower() == "production"
GUILD_ID = 1245655611484541009 if IS_PRODUCTION else 1469687237351309444

SERVICE_ACCOUNT_IDS: frozenset[int] = frozenset({
    531744307103662080,
    538662196297859082
})


class DivisionId(IntEnum):
    VBP = 0
    AVNG = 1
    CPP = 2
    USB = 3
    OMON = 4
    SOBR = 5
    GENERAL_STAFF = 6


if IS_PRODUCTION:

    class RoleId(Enum):
        ATTESTATION = 1402208331904450650
        MILITARY_ID = 1245663211647402107  # Военный билет
        MILITARY = 1245655611517964315  # Сотрудник ФСВНГ
        GENERAL_HQ = 1561021207485087764  # Руководство управления
        BRIGADE_HQ = 1245655611568427049  # Штаб управления
        IC_LEAVE = 1561017253779087400  # IC Отпуск
        OOC_LEAVE = 1561017289384665188  # OOC отпуск

else:

    class RoleId(Enum):
        ATTESTATION = 1484560969219707072
        CONTRACT = 1484560993286750259
        MILITARY = 1484561070495633450  # Военнослужащий ВС РФ
        GENERAL_HQ = 1484561198711308459  # Генеральный штаб
        BRIGADE_HQ = 1484561252553457735  # Штаб бригады
        IC_LEAVE = 1490255314459824259  # IC Отпуск
        OOC_LEAVE = 1490255334265327616  # OOC отпуск


RANK_ROLES = dict(zip(RANKS, [
    1245655611530809368,  # Рядовой
    1245655611530809369,  # Младший сержант
    1245655611530809370,  # Сержант
    1245655611530809371,  # Старший сержант
    1245655611530809372,  # Старшина
    1280627563890212894,  # Прапорщик
    1280626752087003177,  # Старший прапорщик
    1245655611530809373,  # Младший лейтенант
    1253776965760978954,  # Лейтенант
    1245655611543257098,  # Старший лейтенант
    1245655611543257099,  # Капитан
    1245655611543257100,  # Майор
    1249700690687950945,  # Подполковник
    1245655611543257101,  # Полковник
    1245655611543257103,  # Генерал-майор
    1245655611543257104,  # Генерал-лейтенант
    1245655611543257105,  # Генерал-полковник
    1375455567702917201,  # Генерал полиции
]))

if not IS_PRODUCTION:
    RANK_ROLES["Рядовой"] = 1554454960345710592
    RANK_ROLES["Младший сержант"] = 1554454940368506971
    RANK_ROLES["Старший сержант"] = 1554454898928656425

RANK_EMOJIS = [
    "<:ryadovoy:1560965085093171301>",  # Рядовой
    "<:ml_serzhant:1560965131016605757>",  # Младший сержант
    "<:serzhant:1560965187656482826>",  # Сержант
    "<:st_serzhant:1560965235974602792>",  # Старший сержант
    "<:starshina:1560965264525230283>",  # Старшина
    "<:praporshchik:1560965288172986460>",  # Прапорщик
    "<:st_praporshchik:1560965328324796466>",  # Старший прапорщик
    "<:ml_leytenant:1560965356800184411>",  # Младший лейтенант
    "<:leytenant:1560965405907099740>",  # Лейтенант
    "<:st_leytenant:1560965438278738040>",  # Старший лейтенант
    "<:kapitan:1560965463012286474>",  # Капитан
    "<:mayor:1560965501499351111>",  # Майор
    "<:podpolkovnik:1560965534324105277>",  # Подполковник
    "<:polkovnik:1560965563772178474>",  # Полковник
    "<:generalmayor:1560965611272671303>",  # Генерал-майор
    "<:generalleytenant:1560965654146981898>",  # Генерал-лейтенант
    "<:generalpolkovnik:1560965692516466759>",  # Генерал-полковник
    "<:generalpolicii:1560965723688534106>",  # Генерал полиции
]

CHANNELS = (
    {
        "audit": 1245655614852431930,
        "reinstatement": 1561126408879870032,
        "role_getting": 1245655613594271752,
        "blacklist": 1268624099564060763,
        "storage_requests": 1245655615469256726,
        "storage_audit": 1245655615469256727,
        "dismissal": 1245667111930429460,
        "static_log": 1245655617226543150,
        "timeoff": 1245655615892754473,
        "patrol": 1561013787203739738,
        "materials": 1318570731457613844,
        "ic_leave": 1400905921990758431,
        "ooc_leave": 1347529377482670100,
        "military_id": 1561120220662210722,
    }
    if IS_PRODUCTION
    else {
        "audit": 1484560246348189717,
        "reinstatement": 1484560277981757621,
        "role_getting": 1484560302598127927,
        "blacklist": 1484560329949057084,
        "storage_requests": 1484560361645543517,
        "storage_audit": 1484560396496146594,
        "dismissal": 1484560450271182968,
        "static_log": 1484560489861091551,
        "timeoff": 1484560529937928293,
        "patrol": 1484560560421998755,
        "materials": 1484560587101831288,
        "ic_leave": 1490255233345912913,
        "ooc_leave": 1490255253918974114,
        "military_id": 1561053612598366398,
    }
)


ROLE_DISPLAY_NAMES = {
        RoleType.ARMY: "ФСВНГ",
}

ROLE_REQUIRED_RANKS = {
    RoleType.ARMY: "Младший лейтенант",
}

ROLE_REQUIRED_RANK_INDICES = {
    RoleType.ARMY: RankIndex.JUNIOR_LIEUTENANT,
}


IC_MIN_DAYS = 1
IC_MAX_DAYS = 5
OOC_MIN_DAYS = 7
OOC_MAX_DAYS = 30

ACADEMY_DAYS_LIMIT = 10

MATERIALS_MENTIONS = (1245655611627143173, 1245655611627143168)
BLACKLIST_MENTIONS = (1245655611627143173, 1245655611627143171, 1245655611627143168)
SUPPLIES_AUDIT_MENTIONS = (1245655611627143173, 1245655611627143171)
#                   Гражданин
EXCLUDED_ROLES = (1444484048629137579,)

PENALTY_THRESHOLD = 5
#                1 предупреждение     2 предупреждения     1 выговор             2 выговора
PENALTY_ROLES = (1245655611505508397, 1245655611505508396, 1245655611505508395, 1490463931087454218)

ROLE_RESUBMIT_COOLDOWN_HOURS = 24
PATROL_FAIL_COOLDOWN = 300

DIVISION_EXTERNAL_GRANT_CEILING: dict[DivisionId, Privilege] = {
    DivisionId.GENERAL_STAFF: Privilege.COMMANDER,
}

PROMOTION_SIMPLE_EVIDENCE_DIVISIONS = {DivisionId.AVNG}
PROMOTION_NOTIFY_ROLES: dict[int, tuple[int, ...]] = {
    DivisionId.AVNG: (1245655611568427045, 1245655611555971117, 1466027839202529352, 1245659712205361233),
    DivisionId.CPP: (1245655611568427045, 1245655611555971117, 1466027839202529352),
    DivisionId.USB: (1527952234422210681, 1527953170490462290),
    DivisionId.OMON: (1245655611568427048, 1245655611555971119, 1466029398997209130, 1245655611543257107),
    DivisionId.SOBR: (1410671556744450079, 1410674655978717314, 1466029855849185475, 1418672132333895740),
}

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

SUPPLY_INFO_LINK = "https://discord.com/channels/1245655611484541009/1348001487900381244/1561417774801231882"
