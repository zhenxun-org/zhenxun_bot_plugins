from pydantic import BaseModel


class TagItem(BaseModel):
    tag: str
    num: int
