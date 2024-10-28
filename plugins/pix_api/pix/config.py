from pydantic import BaseModel


class PixModel(BaseModel):
    pid: str
    uid: str
    author: str
    title: str
    sanity_level: int
    x_restrict: int
    total_view: int
    total_bookmarks: int
    nsfw_tag: int
    is_ai: bool
    url: str
