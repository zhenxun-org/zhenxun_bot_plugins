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

    following: int = 0  # 关注数 (来自 relation_info)
    follower: int = 0  # 粉丝数 (来自 relation_info)
    archive_view: int = 0  # 视频播放数 (来自 up_stat)
    article_view: int = 0  # 文章阅读数 (来自 up_stat)
    likes: int = 0  # 获赞数 (来自 up_stat)


class UserInfo(BaseModel):
    """用户信息"""

    mid: int  # UID
    name: str  # 昵称
    face: str  # 头像 URL
    sign: str = ""  # 签名
    level: int = 0  # 等级
    sex: str = "保密"  # 性别
    birthday: str = ""  # 生日 (YYYY-MM-DD)
    top_photo: str = ""  # 空间头图 URL
    live_room_status: int = 0  # 直播间状态 (来自 get_user_info)
    live_room_url: str = ""  # 直播间 URL (来自 get_user_info)
    live_room_title: str = ""  # 直播间标题 (来自 get_user_info)
    stat: UserStat  # 统计信息
    parsed_url: str  # 解析时使用的URL


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
