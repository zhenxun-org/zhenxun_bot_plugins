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
