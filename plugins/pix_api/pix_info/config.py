from pydantic import BaseModel


class ImageCount(BaseModel):
    count: int
    """总数量"""
    normal: int
    """普通数量"""
    setu: int
    """setu数量"""
    r18: int
    """r18数量"""
    ai: int
    """ai数量"""
