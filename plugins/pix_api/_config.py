import time
from typing import Generic, TypeVar

from pydantic import BaseModel

from zhenxun.configs.config import Config

base_config = Config.get("pix")


RT = TypeVar("RT")


class PixResult(Generic[RT], BaseModel):
    """
    总体返回
    """

    suc: bool
    code: int
    info: str
    warning: str | None
    data: RT


class PixModel(BaseModel):
    pid: str
    """pid"""
    uid: str
    """uid"""
    author: str
    """作者"""
    title: str
    """标题"""
    sanity_level: int
    """sanity_level"""
    x_restrict: int
    """x_restrict"""
    total_view: int
    """总浏览数"""
    total_bookmarks: int
    """总收藏数"""
    nsfw_tag: int
    """nsfw等级"""
    is_ai: bool
    """是否ai图"""
    url: str
    """图片url"""
    is_multiple: bool
    """是否多图"""
    img_p: str
    """多图第n张"""
    tags: str
    """tags"""


class InfoModel(BaseModel):
    msg_id: str
    """消息id"""
    time: int
    """时间戳"""
    info: PixModel
    """PixModel"""


class InfoManage:
    data: dict[str, InfoModel] = {}  # noqa: RUF012

    @classmethod
    def add(cls, msg_id: str, pix: PixModel):
        """添加图片信息

        参数:
            msg_id: 消息id
            pix: PixGallery
        """
        cls.data[msg_id] = InfoModel(msg_id=msg_id, time=int(time.time()), info=pix)

    @classmethod
    def get(cls, msg_id: str) -> PixModel | None:
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
            if now - cls.data[key].time > 60 * 5:
                cls.data.pop(key)
