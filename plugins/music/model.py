from pydantic import BaseModel


class MusicMetaData(BaseModel):
    type_: str  # 平台类型，如网易云是163
    id: str
    name: str  # 歌名
    alias: str  # 别名
    duration: int  # 时长
    album_name: str  # 专辑
    artist_names: str  # 歌手
    comment_count: int = 0  # 评论数
    share_count: int = 0  # 分享数
    url: str  # 链接
    picUrl: str  # 封面


class MusicHelper:
    @staticmethod
    async def meta_data(keywords: str) -> MusicMetaData | None:
        return None
