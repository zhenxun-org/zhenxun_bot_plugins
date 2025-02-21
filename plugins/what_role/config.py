from pydantic import BaseModel


class Char(BaseModel):
    work: str
    """名称"""
    character: str
    """动漫名称"""


class Item(BaseModel):
    box: list[float]
    """box"""
    character: list[Char]
    """识别数据"""
    box_id: str
    """box_id"""


class Response(BaseModel):
    code: int
    """code"""
    ai: bool
    """ai"""
    trace_id: str
    """new_code"""
    data: list[Item]
