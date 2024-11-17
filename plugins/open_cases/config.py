from enum import Enum

from pydantic import BaseModel

from zhenxun.configs.path_config import IMAGE_PATH

BUFF_URL = "https://buff.163.com/api/market/goods"

BUFF_SELL_URL = "https://buff.163.com/goods"

BASE_PATH = IMAGE_PATH / "csgo_cases"

BLUE = 0.7981
BLUE_ST = 0.0699
PURPLE = 0.1626
PURPLE_ST = 0.0164
PINK = 0.0315
PINK_ST = 0.0048
RED = 0.0057
RED_ST = 0.00021
KNIFE = 0.0021
KNIFE_ST = 0.000041

# 崭新
FACTORY_NEW_S = 0
FACTORY_NEW_E = 0.0699999
# 略磨
MINIMAL_WEAR_S = 0.07
MINIMAL_WEAR_E = 0.14999
# 久经
FIELD_TESTED_S = 0.15
FIELD_TESTED_E = 0.37999
# 破损
WELL_WORN_S = 0.38
WELL_WORN_E = 0.44999
# 战痕
BATTLE_SCARED_S = 0.45
BATTLE_SCARED_E = 0.99999


class UpdateType(Enum):
    """
    更新类型
    """

    CASE = "case"
    WEAPON_TYPE = "weapon_type"


NAME2COLOR = {
    "消费级": "WHITE",
    "工业级": "LIGHTBLUE",
    "军规级": "BLUE",
    "受限": "PURPLE",
    "保密": "PINK",
    "隐秘": "RED",
    "非凡": "KNIFE",
}

COLOR2NAME = {
    "WHITE": "消费级",
    "LIGHTBLUE": "工业级",
    "BLUE": "军规级",
    "PURPLE": "受限",
    "PINK": "保密",
    "RED": "隐秘",
    "KNIFE": "非凡",
    "CASE": "武器箱",
}

COLOR2COLOR = {
    "WHITE": (255, 255, 255),
    "LIGHTBLUE": (0, 179, 255),
    "BLUE": (0, 85, 255),
    "PURPLE": (149, 0, 255),
    "PINK": (255, 0, 162),
    "RED": (255, 34, 0),
    "KNIFE": (255, 225, 0),
    "CASE": (255, 225, 0),
}

ABRASION_SORT = ["崭新出厂", "略有磨损", "久经沙场", "破损不堪", "战横累累"]

CASE_BACKGROUND = IMAGE_PATH / "csgo_cases" / "_background" / "shu"

# 刀
KNIFE2ID = {
    "鲍伊猎刀": "weapon_knife_survival_bowie",
    "蝴蝶刀": "weapon_knife_butterfly",
    "弯刀": "weapon_knife_falchion",
    "折叠刀": "weapon_knife_flip",
    "穿肠刀": "weapon_knife_gut",
    "猎杀者匕首": "weapon_knife_tactical",
    "M9刺刀": "weapon_knife_m9_bayonet",
    "刺刀": "weapon_bayonet",
    "爪子刀": "weapon_knife_karambit",
    "暗影双匕": "weapon_knife_push",
    "短剑": "weapon_knife_stiletto",
    "熊刀": "weapon_knife_ursus",
    "折刀": "weapon_knife_gypsy_jackknife",
    "锯齿爪刀": "weapon_knife_widowmaker",
    "海豹短刀": "weapon_knife_css",
    "系绳匕首": "weapon_knife_cord",
    "求生匕首": "weapon_knife_canis",
    "流浪者匕首": "weapon_knife_outdoor",
    "骷髅匕首": "weapon_knife_skeleton",
    "血猎手套": "weapon_bloodhound_gloves",
    "驾驶手套": "weapon_driver_gloves",
    "手部束带": "weapon_hand_wraps",
    "摩托手套": "weapon_moto_gloves",
    "专业手套": "weapon_specialist_gloves",
    "运动手套": "weapon_sport_gloves",
    "九头蛇手套": "weapon_hydra_gloves",
    "狂牙手套": "weapon_brokenfang_gloves",
}

WEAPON2ID = {}

# 武器箱
CASE2ID = {
    "变革": "set_community_32",
    "反冲": "set_community_31",
    "梦魇": "set_community_30",
    "激流": "set_community_29",
    "蛇噬": "set_community_28",
    "狂牙大行动": "set_community_27",
    "裂空": "set_community_26",
    "棱彩2号": "set_community_25",
    "CS20": "set_community_24",
    "裂网大行动": "set_community_23",
    "棱彩": "set_community_22",
    "头号特训": "set_community_21",
    "地平线": "set_community_20",
    "命悬一线": "set_community_19",
    "光谱2号": "set_community_18",
    "九头蛇大行动": "set_community_17",
    "光谱": "set_community_16",
    "手套": "set_community_15",
    "伽玛2号": "set_gamma_2",
    "伽玛": "set_community_13",
    "幻彩3号": "set_community_12",
    "野火大行动": "set_community_11",
    "左轮": "set_community_10",
    "暗影": "set_community_9",
    "弯曲猎手": "set_community_8",
    "幻彩2号": "set_community_7",
    "幻彩": "set_community_6",
    "先锋": "set_community_5",
    "电竞2014夏季": "set_esports_iii",
    "突围大行动": "set_community_4",
    "猎杀者": "set_community_3",
    "凤凰": "set_community_2",
    "电竞2013冬季": "set_esports_ii",
    "冬季攻势": "set_community_1",
    "军火交易3号": "set_weapons_iii",
    "英勇": "set_bravo_i",
    "电竞2013": "set_esports",
    "军火交易2号": "set_weapons_ii",
    "军火交易": "set_weapons_i",
}


RESULT_MESSAGE = {
    "BLUE": ["这样看着才舒服", "是自己人，大伙把刀收好", "非常舒适~"],
    "PURPLE": ["还行吧，勉强接受一下下", "居然不是蓝色，太假了", "运气-1-1-1-1-1..."],
    "PINK": ["开始不适....", "你妈妈买菜必涨价！涨三倍！", "你最近不适合出门，真的"],
    "RED": [
        "已经非常不适",
        "好兄弟你开的什么箱子啊，一般箱子不是只有蓝色的吗",
        "开始拿阳寿开箱子了？",
    ],
    "KNIFE": [
        "你的好运我收到了，你可以去喂鲨鱼了",
        "最近该吃啥就迟点啥吧，哎，好好的一个人怎么就....哎",
        "众所周知，欧皇寿命极短.",
    ],
}

COLOR2NAME = {
    "BLUE": "军规",
    "PURPLE": "受限",
    "PINK": "保密",
    "RED": "隐秘",
    "KNIFE": "罕见",
    "CASE": "武器箱",
}

COLOR2CN = {"BLUE": "蓝", "PURPLE": "紫", "PINK": "粉", "RED": "红", "KNIFE": "金"}


class Tag(BaseModel):
    """标签"""

    category: str
    """分类"""
    id: int
    """标签id"""
    internal_name: str
    """内部名称"""
    localized_name: str
    """本地化名称"""


class InnerInfo(BaseModel):
    """内部信息"""

    tags: dict[str, Tag]
    """标签"""


class GoodsInfo(BaseModel):
    """
    BUFF商品信息
    """

    icon_url: str
    """商品图片"""
    item_id: str | None
    """Item id"""
    original_icon_url: str
    """商品原始图片"""
    steam_price: float
    """steam价格"""
    steam_price_cny: float
    """steam价格人民币"""
    info: InnerInfo
    """信息"""

    @property
    def tags(self) -> dict[str, Tag]:
        return self.info.tags


class BuffItem(BaseModel):
    """buff商品"""

    appid: int
    """游戏id"""
    bookmarked: bool
    """是否收藏"""
    buy_max_price: float
    """最高购买价格"""
    buy_num: int
    """购买数量"""
    can_bargain: bool
    """是否可议价"""
    can_search_by_tournament: bool
    """是否可搜索锦标赛"""
    description: str | None
    """描述"""
    game: str
    """游戏名称"""
    goods_info: GoodsInfo
    """商品信息"""
    has_buff_price_history: bool
    """是否有价格历史"""
    id: int
    """皮肤id"""
    market_hash_name: str
    """皮肤英文hash名"""
    market_min_price: str
    """最低市场价格"""
    name: str
    """皮肤名称"""
    quick_price: float
    """快速购买价格"""
    sell_min_price: float
    """最低出售价格"""
    sell_num: int
    """出售数量"""
    sell_reference_price: float
    """出售参考价格"""
    short_name: str
    """皮肤短名称"""
    steam_market_url: str
    """steam市场链接"""
    transacted_num: int
    """交易数量"""


class BuffResponse(BaseModel):
    """
    Buff返回体
    """

    items: list[BuffItem]
    """数据列表"""
    page_num: int
    """当前页数"""
    page_size: int
    """当前页数内容数量"""
    total_count: int
    """总共数量"""
    total_page: int
    """总页数"""
