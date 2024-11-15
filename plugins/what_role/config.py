from pydantic import BaseModel


class Char(BaseModel):
    name: str
    """名称"""
    cartoonname: str
    """动漫名称"""
    acc: float
    """准确率"""


class Item(BaseModel):
    box: list[float]
    """box"""
    char: list[Char]
    """识别数据"""
    box_id: str
    """box_id"""


class Response(BaseModel):
    code: int
    """code"""
    ai: bool
    """ai"""
    new_code: int
    """new_code"""
    data: list[Item]
