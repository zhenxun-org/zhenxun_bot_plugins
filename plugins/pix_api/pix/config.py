from pydantic import BaseModel


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
