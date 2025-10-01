from pydantic import BaseModel
from typing import Optional, Dict, Any


class Owner(BaseModel):
    mid: int
    name: str
    face: str


class Stat(BaseModel):
    aid: int
    view: int
    danmaku: int
    reply: int
    favorite: int
    coin: int
    share: int
    now_rank: int
    his_rank: int
    like: int
    dislike: int
    vt: Optional[int] = None
    vv: Optional[int] = None


class VideoInfo(BaseModel):
    bvid: str
    aid: int
    videos: int
    tid: int
    tname: str
    copyright: int
    pic: str
    title: str
    pubdate: int
    ctime: int
    desc: str
    state: int
    duration: int
    mission_id: Optional[int] = None
    rights: dict
    owner: Owner
    stat: Stat
    dynamic: str
    cid: int
    dimension: dict
    short_link_v2: Optional[str] = None
    up_from_v2: Optional[int] = None
    first_frame: Optional[str] = None
    pub_location: Optional[str] = None
    pages: Optional[list] = None
    parsed_url: str
    ai_summary: Optional[str] = None
    online_count: Optional[str] = None


class LiveInfo(BaseModel):
    room_id: int
    short_id: int
    uid: int
    title: str
    cover: str
    live_status: int
    live_start_time: int
    area_id: int
    area_name: str
    parent_area_id: int
    parent_area_name: str
    description: str
    keyframe_url: Optional[str] = None
    parsed_url: str
    uname: Optional[str] = None
    face: Optional[str] = None
    room_url: Optional[str] = None
    space_url: Optional[str] = None


class ArticleInfo(BaseModel):
    id: str
    type: str
    url: str
    title: str | None = None
    author: str | None = None
    screenshot_path: str | None = None
    screenshot_bytes: bytes | None = None
    markdown_content: Optional[str] = None


class UserStat(BaseModel):
    """用户统计信息"""

    following: int = 0
    follower: int = 0
    archive_view: int = 0
    article_view: int = 0
    likes: int = 0


class UserInfo(BaseModel):
    """用户信息"""

    mid: int
    name: str
    face: str
    sign: str = ""
    level: int = 0
    sex: str = "保密"
    birthday: str = ""
    top_photo: str = ""
    live_room_status: int = 0
    live_room_url: str = ""
    live_room_title: str = ""
    stat: UserStat
    parsed_url: str


class SeasonStat(BaseModel):
    """番剧统计信息"""

    views: int = 0
    danmakus: int = 0
    reply: int = 0
    favorites: int = 0
    coins: int = 0
    share: int = 0
    likes: int = 0


class SeasonInfo(BaseModel):
    """番剧信息"""

    season_id: int
    media_id: int
    title: str
    cover: str
    desc: str = ""
    type_name: str = ""
    areas: str = ""
    styles: str = ""
    publish: Dict[str, Any] = {}
    rating_score: float = 0.0
    rating_count: int = 0
    stat: SeasonStat
    total_ep: int = 0
    status: int = 0
    parsed_url: str

    target_ep_id: Optional[int] = None
    target_ep_title: Optional[str] = None
    target_ep_long_title: Optional[str] = None
    target_ep_cover: Optional[str] = None
