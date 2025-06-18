from typing import Any

from pydantic import BaseModel


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
    vt: int | None = None
    vv: int | None = None


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
    mission_id: int | None = None
    rights: dict
    owner: Owner
    stat: Stat
    dynamic: str
    cid: int
    dimension: dict
    short_link_v2: str | None = None
    up_from_v2: int | None = None
    first_frame: str | None = None
    pub_location: str | None = None
    pages: list | None = None
    parsed_url: str


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
    keyframe_url: str | None = None
    parsed_url: str
    uname: str | None = None
    face: str | None = None
    room_url: str | None = None
    space_url: str | None = None


class ArticleInfo(BaseModel):
    id: str
    type: str
    url: str
    title: str | None = None
    author: str | None = None
    screenshot_path: str | None = None
    screenshot_bytes: bytes | None = None
    markdown_content: str | None = None


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
    publish: dict[str, Any] = {}
    rating_score: float = 0.0
    rating_count: int = 0
    stat: SeasonStat
    total_ep: int = 0
    status: int = 0
    parsed_url: str

    target_ep_id: int | None = None
    target_ep_title: str | None = None
    target_ep_long_title: str | None = None
    target_ep_cover: str | None = None
