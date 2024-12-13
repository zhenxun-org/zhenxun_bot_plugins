import time

from pydantic import BaseModel
from strenum import StrEnum

from zhenxun.builtin_plugins.pix_gallery.models.pix_gallery import PixGallery
from zhenxun.configs.config import Config

base_config = Config.get("pix")


class KwType(StrEnum):
    """关键词类型"""

    KEYWORD = "KEYWORD"
    """关键词"""
    UID = "UID"
    """用户uid"""
    PID = "PID"
    """图片pid"""


class KwHandleType(StrEnum):
    """关键词类型"""

    PASS = "PASS"
    """通过"""
    IGNORE = "IGNORE"
    """忽略"""
    FAIL = "FAIL"
    """未通过"""
    BLACK = "BLACK"
    """黑名单"""


class MyConfig(BaseModel):
    """项目配置"""

    superusers: list[str] = ["775757368"]
    """超级用户列表 """


Config = MyConfig()


class User(BaseModel):
    """用户模型"""

    id: int
    """uid"""
    name: str
    """用户名"""
    account: str
    """账号"""
    profile_image_urls: dict[str, str]
    """头像"""
    is_followed: bool | None = None
    """是否关注"""


class Tag(BaseModel):
    """标签模型"""

    name: str
    """标签名"""
    translated_name: str | None
    """翻译名称"""


class PidModel(BaseModel):
    """pid模型"""

    id: int
    """图片pid"""
    title: str
    """图片标题"""
    type: str
    """类型"""
    image_urls: dict[str, str]
    """图片链接"""
    user: User
    """用户模型"""
    tags: list[Tag]
    """标签列表"""
    create_date: str
    """创建时间"""
    page_count: int
    """页数"""
    width: int
    """宽度"""
    height: int
    """高度"""
    sanity_level: int
    """安全等级"""
    x_restrict: int
    """x等级"""
    meta_single_page: dict[str, str]
    """meta_single_page"""
    meta_pages: list[dict[str, dict[str, str]]] | None
    """meta_pages"""
    total_view: int
    """总浏览量"""
    total_bookmarks: int
    """总收藏量"""
    is_bookmarked: bool
    """是否收藏"""
    visible: bool
    """是否可见"""
    is_muted: bool
    """是否静音"""
    total_comments: int = 0
    """总评论数"""
    illust_ai_type: int
    """插画ai类型"""
    illust_book_style: int
    """插画书类型"""
    comment_access_control: int | None = None
    """评论访问控制"""

    @property
    def tags_text(self) -> str:
        tags = []
        if self.tags:
            for tag in self.tags:
                tags.append(tag.name)
                if tag.translated_name:
                    tags.append(tag.translated_name)
        return ",".join(tags)


class UidModel(BaseModel):
    """uid模型"""

    user: User
    """用户模型"""
    illusts: list[PidModel]
    """插画列表"""
    next_url: str | None
    """下一页链接"""


class KeywordModel(BaseModel):
    """关键词模型"""

    keyword: str
    """关键词"""
    illusts: list[PidModel]
    """插画列表"""
    next_url: str | None
    """下一页链接"""
    search_span_limit: int
    """搜索时间限制"""
    show_ai: bool
    """是否显示ai插画"""


class NoneModel(BaseModel):
    content: str
    """内容"""
    kw_type: KwType
    """关键词类型"""
    error: str
    """错误信息"""


class QueryCount(BaseModel):
    tags: list[str] | None = []


class QuerySeek(BaseModel):
    seek_type: KwType | None = None


class ImageCount(BaseModel):
    count: int
    """总数量"""
    normal: int
    """普通数量"""
    r18: int
    """r18数量"""
    ai: int
    """ai数量"""


class KeywordItem(BaseModel):
    id: int
    """id"""
    content: str
    """关键词"""
    kw_type: KwType
    """关键词类型"""
    handle_type: KwHandleType
    """操作类型"""
    seek_count: int
    """搜索次数"""


class InfoModel(BaseModel):
    msg_id: str
    """消息id"""
    time: int
    """时间戳"""
    info: PixGallery
    """PixModel"""

    class Config:
        arbitrary_types_allowed = True


class InfoManage:
    data: dict[str, InfoModel] = {}  # noqa: RUF012

    @classmethod
    def add(cls, msg_id: str, pix: PixGallery):
        """添加图片信息

        参数:
            msg_id: 消息id
            pix: PixGallery
        """
        cls.data[msg_id] = InfoModel(msg_id=msg_id, time=int(time.time()), info=pix)

    @classmethod
    def get(cls, msg_id: str) -> PixGallery | None:
        """获取图片信息

        参数:
            msg_id: 消息id

        返回:
            InfoModel | None: 图片信息
        """
        return info.info if (info := cls.data.get(msg_id)) else None

    @classmethod
    def remove(cls):
        """移除超时五分钟的图片数据"""
        now = time.time()
        key_list = list(cls.data.keys())
        for key in key_list:
            if now - cls.data[key].time > 60 * 60 * 3:
                cls.data.pop(key)
