from pydantic import BaseModel

from zhenxun.configs.path_config import DATA_PATH

REPORT_PATH = DATA_PATH / "mahiro_report"
REPORT_PATH.mkdir(parents=True, exist_ok=True)


class Hitokoto(BaseModel):
    id: int
    """id"""
    uuid: str
    """uuid"""
    hitokoto: str
    """一言"""
    type: str
    """类型"""
    from_who: str | None
    """作者"""
    creator: str
    """创建者"""
    creator_uid: int
    """创建者id"""
    reviewer: int
    """审核者"""
    commit_from: str
    """提交来源"""
    created_at: str
    """创建日期"""
    length: int
    """长度"""


class SixDataTo(BaseModel):
    news: list[str]
    """新闻"""
    tip: str
    """tip"""
    updated: int
    """更新日期"""
    url: str
    """链接"""
    cover: str
    """图片"""


class SixData(BaseModel):
    status: int
    """状态码"""
    message: str
    """返回内容"""
    data: SixDataTo
    """数据"""


class WeekDay(BaseModel):
    en: str
    """英文"""
    cn: str
    """中文"""
    ja: str
    """日本称呼"""
    id: int
    """ID"""


class AnimeItem(BaseModel):
    name: str
    name_cn: str
    images: dict | None

    @property
    def image(self) -> str:
        return self.images["large"] if self.images else ""


class Anime(BaseModel):
    weekday: WeekDay
    items: list[AnimeItem]


favs_list = ["元旦", "劳动节", "国庆节", "春节", "清明", "端午", "中秋"]
favs_arr = [
    0,
    0,
    46,
    3,
    94,
    4,
    120,
    1,
    168,
    5,
    266,
    6,
    273,
    2,
    365,
    0,
    400,
    3,
    459,
    4,
    485,
    1,
    522,
    5,
    620,
    6,
    638,
    2,
    730,
    0,
    754,
    3,
    824,
    4,
    851,
    1,
    906,
    5,
    1004,
    2,
    1004,
    6,
    1096,
    0,
    1138,
    3,
    1189,
    4,
    1216,
    1,
    1260,
    5,
    1359,
    6,
    1369,
    2,
    1461,
    0,
    1492,
    3,
    1555,
    4,
    1581,
    1,
    1614,
    5,
    1713,
    6,
    1734,
    2,
    1826,
    0,
    1847,
    3,
    1920,
    4,
    1946,
    1,
    1998,
    5,
    2097,
    6,
    2099,
    2,
    2191,
    0,
    2231,
    3,
    2285,
    4,
    2312,
    1,
    2352,
    5,
    2451,
    6,
    2465,
    2,
    2557,
    0,
    2585,
    3,
    2650,
    4,
    2677,
    1,
    2707,
    5,
    2830,
    2,
    2835,
    6,
    2922,
    0,
    2969,
    3,
    3016,
    4,
    3042,
    1,
    3091,
    5,
    3189,
    6,
    3195,
    2,
    3287,
    0,
    3323,
    3,
    3381,
    4,
    3407,
    1,
    3446,
    5,
    3544,
    6,
    3560,
    2,
    3652,
    0,
    3677,
    3,
    3746,
    4,
    3773,
    1,
    3800,
    5,
    3926,
    2,
    3928,
    6,
    4018,
    0,
    4061,
    3,
    4111,
    4,
    4138,
    1,
    4184,
    5,
    4282,
    6,
    4291,
    2,
    4383,
    0,
    4416,
    3,
    4477,
    4,
    4503,
    1,
    4637,
    6,
    4656,
    2,
]
