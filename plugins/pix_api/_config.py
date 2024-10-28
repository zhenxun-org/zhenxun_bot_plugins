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
