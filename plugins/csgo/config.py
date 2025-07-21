from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

try:
    from pydantic import field_validator  # Pydantic v2

    VALIDATOR = field_validator
    VALIDATOR_MODE = {"mode": "before"}
except ImportError:
    from pydantic import validator  # Pydantic v1

    VALIDATOR = validator
    VALIDATOR_MODE = {"pre": True}

from zhenxun.configs.path_config import DATA_PATH

PERFECT_WORLD_MAP_RATE_URL = (
    "https://api.wmpvp.com/api/v2/csgo/pvpMapStats?steamId64={}&csgoSeasonId={}"
)
"""完美世界平台地图胜率"""


PERFECT_WORLD_BAN_STAT_URL = (
    "https://pvp.wanmei.com/user-info/forbid-stats?game_abbr_list=PVP,CSGO"
)
"""完美世界封禁统计"""

PERFECT_WORLD_USER_PLATFORM_DATA_URL = (
    "https://api.wmpvp.com/api/v2/csgo/pvpDetailDataStats"
)
"""完美世界平台用户数据"""


PERFECT_WORLD_USER_OFFICIAL_DATA_API_URL = (
    "https://api.wmpvp.com/api/csgo/home/official/detailStats"
)
"""完美世界官方用户数据"""

PERFECT_WORLD_VIDEO_URL = (
    "https://appactivity.wmpvp.com/steamcn/video/getPerfectlist?toSteamId={}"
)
"""完美世界视频"""

PERFECT_WORLD_MATCH_LIST_URL = "https://api.wmpvp.com/api/csgo/home/match/list"
"""完美世界用户比赛列表"""

PERFECT_WORLD_WWS = "wss://wss-csgo-pwa.wmpvp.com/"
"""完美世界WebSocket"""

PERFECT_WORLD_USER_MATCH_DATA_URL = (
    "https://api.wmpvp.com/api/v2/home/validUser?sign={}"
)

PERFECT_WORLD_MATCH_DETAIL_URL = "https://api.wmpvp.com/api/v1/csgo/match"
"""完美世界用户比赛详情"""

MATCH_DATA_URL = (
    "https://gwapi.pwesports.cn/eventcenter/app/csgo/event/getMatchlist?matchTime={}"
)
"""赛事数据"""

SAVE_PATH = DATA_PATH / "csgo"

SAVE_PATH.mkdir(parents=True, exist_ok=True)

DEFAULT_AVATAR_URL = "https://i0.hdslb.com/bfs/article/a6e3fa3c2a173df4a21651ee2ffe541b0a4beea0.png@1192w_1192h.avif"

LOG_COMMAND = "CSGO"

CURRENT_SEASON = "S20"

T = TypeVar("T")


class SteamUserInfo(BaseModel):
    name: str = Field(..., description="用户名")
    """用户名"""
    avatar: str = Field(..., description="头像URL")
    """头像URL"""
    steam_id: str = Field(..., description="Steam ID")
    """Steam ID"""
    friend_code: str = Field(..., description="好友代码")
    """好友代码"""


class BaseResponse(BaseModel, Generic[T]):
    status_code: int = Field(..., alias="statusCode", description="状态码")
    """状态码"""
    error_message: str = Field(..., alias="errorMessage", description="错误信息")
    """错误信息"""
    data: T
    """数据"""


class PerfectWorldMapRate(BaseModel):
    map_name_zh: str = Field(..., alias="mapNameZh", description="地图名称")
    """地图名称"""
    map_name_en: str = Field(..., alias="mapNameEn", description="地图英文名称")
    """地图英文名称"""
    map_url: str = Field(..., alias="mapUrl", description="地图图片链接")
    """地图图片链接"""
    match_cnt: int = Field(..., alias="matchCnt", description="比赛场次")
    """比赛场次"""
    win_cnt: int = Field(..., alias="winCnt", description="胜利场次")
    """胜利场次"""
    win_rate: float = Field(..., alias="winRate", description="胜率")
    """胜率"""
    t_win_rate: float = Field(..., alias="tWinRate", description="T阵营胜率")
    """T阵营胜率"""
    ct_win_rate: float = Field(..., alias="ctWinRate", description="CT阵营胜率")
    """CT阵营胜率"""


class HotMap(BaseModel):
    """玩家常玩地图的统计数据"""

    map: str = Field(..., alias="map", description="地图代码（如 de_dust2）")
    """地图代码（如 de_dust2）"""
    map_image: str = Field(..., alias="mapImage", description="地图背景图URL")
    """地图背景图URL"""
    map_logo: str = Field(..., alias="mapLogo", description="地图LOGO URL")
    """地图LOGO URL"""
    map_name: str = Field(
        ..., alias="mapName", description="地图中文名（如 炙热沙城Ⅱ）"
    )
    """地图中文名（如 炙热沙城Ⅱ）"""
    total_match: int = Field(..., alias="totalMatch", description="该地图总比赛场次")
    """该地图总比赛场次"""
    win_count: int = Field(..., alias="winCount", description="胜利场次")
    """胜利场次"""
    total_kill: int = Field(..., alias="totalKill", description="总击杀数")
    """总击杀数"""
    total_adr: float = Field(
        ..., alias="totalAdr", description="总伤害（可能是累计值）"
    )
    """总伤害（可能是累计值）"""
    rank: int | None = Field(None, alias="rank", description="排名（可能未启用）")
    """排名（可能未启用）"""
    rating_sum: float = Field(
        ..., alias="ratingSum", description="评分总和（用于计算平均）"
    )
    """评分总和（用于计算平均）"""
    rws_sum: float = Field(..., alias="rwsSum", description="RWS（回合胜利贡献值）总和")
    """RWS（回合胜利贡献值）总和"""
    death_num: int = Field(..., alias="deathNum", description="总死亡数")
    """总死亡数"""
    first_kill_num: int = Field(..., alias="firstKillNum", description="首杀次数")
    """首杀次数"""
    first_death_num: int = Field(..., alias="firstDeathNum", description="首死次数")
    """首死次数"""
    headshot_kill_num: int = Field(
        ..., alias="headshotKillNum", description="爆头击杀数"
    )
    """爆头击杀数"""
    match_mvp_num: int = Field(..., alias="matchMvpNum", description="MVP次数")
    """MVP次数"""
    three_kill_num: int = Field(..., alias="threeKillNum", description="三杀次数")
    """三杀次数"""
    four_kill_num: int = Field(..., alias="fourKillNum", description="四杀次数")
    """四杀次数"""
    five_kill_num: int = Field(..., alias="fiveKillNum", description="五杀次数")
    """五杀次数"""
    v3_num: int = Field(..., alias="v3Num", description="1v3残局胜利次数")
    """1v3残局胜利次数"""
    v4_num: int = Field(..., alias="v4Num", description="1v4残局胜利次数")
    """1v4残局胜利次数"""
    v5_num: int = Field(..., alias="v5Num", description="1v5残局胜利次数")
    """1v5残局胜利次数"""
    scuffle: bool = Field(..., alias="scuffle", description="是否为混战模式")
    """是否为混战模式"""


class HotWeapon(BaseModel):
    """武器简单统计数据"""

    weapon_image: str = Field(..., alias="weaponImage", description="武器图片URL")
    """武器图片URL"""
    weapon_name: str = Field(
        ..., alias="weaponName", description="武器英文名（如 AK47）"
    )
    """武器英文名（如 AK47）"""
    weapon_kill: int = Field(..., alias="weaponKill", description="该武器击杀数")
    """该武器击杀数"""
    weapon_head_shot: int = Field(
        ..., alias="weaponHeadShot", description="该武器爆头数"
    )
    """该武器爆头数"""
    total_match: int = Field(..., alias="totalMatch", description="使用该武器的总场次")
    """使用该武器的总场次"""


class PerfectWorldScore(BaseModel):
    """完美世界玩家评分"""

    match_id: str = Field(..., alias="matchId", description="比赛ID")
    """比赛ID"""
    score: int = Field(..., alias="score", description="分数")
    """分数"""
    time: int = Field(..., alias="time", description="比赛时间")
    """比赛时间"""
    stars: int = Field(..., alias="stars", description="星数")
    """星数"""
    slevel: int = Field(..., alias="slevel", description="段位")
    """段位"""


class PerfectWorldPlatformDetailDataStats(BaseModel):
    """完美世界玩家详细数据统计"""

    steam_id: str = Field(..., alias="steamId", description="Steam 玩家ID")
    """Steam 玩家ID"""
    season_id: str = Field(..., alias="seasonId", description="当前赛季ID（如 S18）")
    """当前赛季ID（如 S18）"""
    pvp_rank: int = Field(
        ..., alias="pvpRank", description="PVP排名（0可能表示未排名）"
    )
    """PVP排名（0可能表示未排名）"""
    avatar: str = Field(..., alias="avatar", description="玩家头像URL")
    """玩家头像URL"""
    name: str = Field(..., alias="name", description="玩家昵称")
    """玩家昵称"""
    cnt: int = Field(..., alias="cnt", description="总比赛场次")
    """总比赛场次"""
    kd: float = Field(..., alias="kd", description="击杀/死亡比")
    """击杀/死亡比"""
    win_rate: float = Field(..., alias="winRate", description="胜率（如 0.49 表示49%）")
    """胜率（如 0.49 表示49%）"""
    rating: float = Field(..., alias="rating", description="综合评分")
    """综合评分"""
    pw_rating: float = Field(..., alias="pwRating", description="完美世界自定义评分")
    """完美世界自定义评分"""
    hit_rate: float = Field(
        ..., alias="hitRate", description="命中率（如 1.0 表示100%）"
    )
    """命中率（如 1.0 表示100%）"""
    common_rating: float = Field(..., alias="commonRating", description="常规模式评分")
    """常规模式评分"""
    kills: int = Field(..., alias="kills", description="总击杀数")
    """总击杀数"""
    deaths: int = Field(..., alias="deaths", description="总死亡数")
    """总死亡数"""
    assists: int = Field(..., alias="assists", description="总助攻数")
    """总助攻数"""
    mvp_count: int = Field(..., alias="mvpCount", description="MVP次数")
    """MVP次数"""
    game_score: int = Field(
        ..., alias="gameScore", description="游戏内积分（可能未启用）"
    )
    """游戏内积分（可能未启用）"""
    rws: float = Field(..., alias="rws", description="RWS（回合胜利贡献值）")
    """RWS（回合胜利贡献值）"""
    adr: float = Field(..., alias="adr", description="ADR（场均伤害）")
    """ADR（场均伤害）"""
    head_shot_ratio: float = Field(..., alias="headShotRatio", description="爆头率")
    """爆头率"""
    entry_kill_ratio: float = Field(
        ..., alias="entryKillRatio", description="首杀成功率"
    )
    """首杀成功率"""
    k2: int = Field(..., alias="k2", description="双杀次数")
    """双杀次数"""
    k3: int = Field(..., alias="k3", description="三杀次数")
    """三杀次数"""
    k4: int = Field(..., alias="k4", description="四杀次数")
    """四杀次数"""
    k5: int = Field(..., alias="k5", description="五杀次数")
    """五杀次数"""
    multi_kill: int = Field(
        ..., alias="multiKill", description="多杀总次数（双杀及以上）"
    )
    """多杀总次数（双杀及以上）"""
    vs1: int = Field(..., alias="vs1", description="1v1残局胜利次数")
    """1v1残局胜利次数"""
    vs2: int = Field(..., alias="vs2", description="1v2残局胜利次数")
    """1v2残局胜利次数"""
    vs3: int = Field(..., alias="vs3", description="1v3残局胜利次数")
    """1v3残局胜利次数"""
    vs4: int = Field(..., alias="vs4", description="1v4残局胜利次数")
    """1v4残局胜利次数"""
    vs5: int = Field(..., alias="vs5", description="1v5残局胜利次数")
    """1v5残局胜利次数"""
    ending_win: int = Field(..., alias="endingWin", description="残局总胜利次数")
    """残局总胜利次数"""
    hot_maps: list[HotMap] = Field(..., alias="hotMaps", description="常玩地图数据列表")
    """常玩地图数据列表"""
    history_ratings: list[float] = Field(
        ..., alias="historyRatings", description="历史评分列表（按时间倒序）"
    )
    """历史评分列表（按时间倒序）"""
    history_pw_ratings: list[float] = Field(
        ..., alias="historyPwRatings", description="完美世界历史评分"
    )
    """完美世界历史评分"""
    history_scores: list[int] = Field(
        ..., alias="historyScores", description="历史分数（如天梯分）"
    )
    """历史分数（如天梯分）"""
    history_rws: list[float] = Field(..., alias="historyRws", description="历史RWS值")
    """历史RWS值"""
    history_dates: list[str] = Field(
        ..., alias="historyDates", description="历史数据对应时间戳"
    )
    """历史数据对应时间戳"""
    titles: list[str] = Field(..., alias="titles", description="玩家获得的称号列表")
    """玩家获得的称号列表"""
    shot: float = Field(..., alias="shot", description="射击评分（可能是自定义指标）")
    """射击评分（可能是自定义指标）"""
    victory: float = Field(..., alias="victory", description="胜利评分")
    """胜利评分"""
    breach: float = Field(..., alias="breach", description="突破评分")
    """突破评分"""
    snipe: float = Field(..., alias="snipe", description="狙击评分")
    """狙击评分"""
    prop: float = Field(..., alias="prop", description="道具使用评分")
    """道具使用评分"""
    vs1_win_rate: float = Field(..., alias="vs1WinRate", description="1v1残局胜率")
    """1v1残局胜率"""
    summary: str | None = Field(
        default_factory=str,
        alias="summary",
        description="系统生成的玩家评价标签（如 神枪不朽）",
    )
    """系统生成的玩家评价标签（如 神枪不朽）"""
    hot_weapons: list[HotWeapon] | None = Field(
        default_factory=list, alias="hotWeapons", description="常用武器简单数据"
    )
    """常用武器简单数据"""
    avg_we: float = Field(..., alias="avgWe", description="平均武器效率")
    """平均武器效率"""
    pvp_score: int = Field(..., alias="pvpScore", description="当前PVP分数")
    """当前PVP分数"""
    stars: int = Field(..., alias="stars", description="星级评价（可能未启用）")
    """星级评价（可能未启用）"""
    score_list: list[PerfectWorldScore] = Field(
        ..., alias="scoreList", description="单场比赛分数记录"
    )
    """单场比赛分数记录"""
    we_list: list[float] = Field(
        ..., alias="weList", description="武器效率列表（可能为最近10场）"
    )
    """武器效率列表（可能为最近10场）"""

    @VALIDATOR("hot_weapons", **VALIDATOR_MODE)  # type: ignore
    def check_hot_weapons(cls, v):
        return v if v is not None else []

    @VALIDATOR("summary", **VALIDATOR_MODE)  # type: ignore
    def check_summary(cls, v):
        return v if v is not None else ""


class PerfectWorldOfficialDetailDataStats(BaseModel):
    """玩家核心数据"""

    steam_id: str = Field(..., alias="steamId")
    """Steam ID"""
    history_win_count: int = Field(..., alias="historyWinCount")
    """历史胜利场次"""
    cnt: int = Field(..., alias="cnt")
    """总比赛场次"""
    kd: float = Field(..., alias="kd")
    """K/D比率"""
    win_rate: float = Field(..., alias="winRate")
    """胜率"""
    rating: float = Field(..., alias="rating")
    """综合评分"""
    kills: int = Field(..., alias="kills")
    """总击杀数"""
    deaths: int = Field(..., alias="deaths")
    """总死亡数"""
    assists: int = Field(..., alias="assists")
    """总助攻数"""
    honor1_count: int = Field(..., alias="honor1Count")
    """荣誉1数量"""
    honor2_count: int = Field(..., alias="honor2Count")
    """荣誉2数量"""
    honor3_count: int = Field(..., alias="honor3Count")
    """荣誉3数量"""
    honor4_count: int = Field(..., alias="honor4Count")
    """荣誉4数量"""
    honor5_count: int = Field(..., alias="honor5Count")
    """荣誉5数量"""
    honor6_count: int = Field(..., alias="honor6Count")
    """荣誉6数量"""
    rws: float = Field(..., alias="rws")
    """RWS评分"""
    adr: float = Field(..., alias="adr")
    """场均伤害"""
    kast: int = Field(..., alias="kast")
    """KAST百分比"""
    ending_win: int = Field(..., alias="endingWin")
    """残局胜利次数"""
    k3: int = Field(..., alias="k3")
    """三杀次数"""
    k4: int = Field(..., alias="k4")
    """四杀次数"""
    k5: int = Field(..., alias="k5")
    """五杀次数"""
    vs3: int = Field(..., alias="vs3")
    """1v3胜利次数"""
    vs4: int = Field(..., alias="vs4")
    """1v4胜利次数"""
    vs5: int = Field(..., alias="vs5")
    """1v5胜利次数"""
    multi_kill: int = Field(..., alias="multiKill")
    """多杀总数"""
    head_shot_ratio: float = Field(..., alias="headShotRatio")
    """爆头率"""
    entry_kill_ratio: float = Field(..., alias="entryKillRatio")
    """首杀成功率"""
    awp_kill_ratio: float = Field(..., alias="awpKillRatio")
    """AWP击杀占比"""
    flash_success_ratio: float = Field(..., alias="flashSuccessRatio")
    """闪光弹成功率"""
    hot_maps: list[HotMap] = Field(..., alias="hotMaps")
    """常用地图数据"""
    hot_weapons: list[HotWeapon] | None = Field(..., alias="hotWeapons")
    """常用武器数据"""
    history_ratings: list[float] = Field(..., alias="historyRatings")
    """历史评分"""
    history_ranks: list[int] = Field(..., alias="historyRanks")
    """历史排名"""
    history_comprehensive_scores: list[int] = Field(
        ..., alias="historyComprehensiveScores"
    )
    """历史综合分数"""
    history_rws: list[float] = Field(..., alias="historyRws")
    """历史RWS"""
    history_dates: list[str] = Field(..., alias="historyDates")
    """历史记录日期"""
    refreshed: bool = Field(..., alias="refreshed")
    """是否已刷新"""
    entry_kill_avg: float = Field(..., alias="entryKillAvg")
    """平均首杀数"""
    match_list: list[str] | None = Field(default_factory=list, alias="matchList")
    """比赛列表"""
    nick_name: str = Field(..., alias="nickName")
    """昵称"""
    avatar: str = Field(..., alias="avatar")
    """头像URL"""
    friend_code: str = Field(..., alias="friendCode")
    """好友代码"""
    hours: int = Field(..., alias="hours")
    """游戏时长(小时)"""
    rank: int = Field(..., alias="rank")
    """当前排名"""
    auth_stats: int = Field(..., alias="authStats")
    """认证状态"""

    @VALIDATOR("hot_weapons", **VALIDATOR_MODE)  # type: ignore
    def check_hot_weapons(cls, v):
        return v if v is not None else []

    @VALIDATOR("match_list", **VALIDATOR_MODE)  # type: ignore
    def check_match_list(cls, v):
        return v if v is not None else []


class PerfectWorldVideoBase(BaseModel):
    """视频基础信息"""

    cover_url: str = Field(..., alias="coverURL")
    """封面图URL"""
    duration: str
    """视频时长(秒)"""
    status: str
    """视频状态"""
    video_id: str = Field(..., alias="videoId")
    """视频唯一ID"""


class PerfectWorldPlayInfo(BaseModel):
    """视频播放信息"""

    width: int
    """视频宽度"""
    height: int
    """视频高度"""
    size: int
    """文件大小(字节)"""
    play_url: str = Field(..., alias="playURL")
    """播放地址"""
    definition: str
    """清晰度标识"""
    duration: str
    """时长(秒)"""
    format: str
    """视频格式"""
    status: str
    """状态"""


class PerfectWorldVideoInfo(BaseModel):
    """视频详细信息"""

    video_base: PerfectWorldVideoBase = Field(..., alias="videoBase")
    """基础信息"""
    play_info_list: list[PerfectWorldPlayInfo] = Field(..., alias="playInfoList")
    """多清晰度播放列表"""


class PerfectWorldUserVideo(BaseModel):
    """用户视频数据"""

    id: int
    """视频记录ID"""
    weekend_league: bool = Field(..., alias="weekendLeague")
    """是否周末联赛"""
    album: bool
    """是否合集"""
    short_title: str | None = Field(None, alias="shortTitle")
    """短标题"""
    match_id: str = Field(..., alias="matchId")
    """比赛ID"""
    match_round: int = Field(..., alias="matchRound")
    """比赛回合数"""
    match_time: datetime = Field(..., alias="matchTime")
    """比赛时间戳"""
    map_name: str = Field(..., alias="mapName")
    """地图名称"""
    kill_count: int = Field(..., alias="killCount")
    """击杀数"""
    versus_count: int = Field(..., alias="versusCount")
    """对阵人数(如1v3)"""
    vid: str
    """视频标识"""
    video_status: int = Field(..., alias="videoStatus")
    """视频状态码"""
    video_reason: str | None = Field(None, alias="videoReason")
    """视频状态原因"""
    review_status: int = Field(..., alias="reviewStatus")
    """审核状态"""
    review_reason: str | None = Field(None, alias="reviewReason")
    """审核原因"""
    video_info: PerfectWorldVideoInfo = Field(..., alias="videoInfo")
    """视频详细信息"""
    map_url: str = Field(..., alias="mapUrl")
    """地图图片URL"""
    platform: int
    """平台标识"""
    post_id: int | None = Field(None, alias="postId")
    """社区帖子ID"""
    title: str | None
    """视频标题"""
    is_vote: bool | None = Field(None, alias="isVote")
    """是否可投票"""
    could_free_vote: bool | None = Field(None, alias="couldFreeVote")
    """是否可免费投票"""
    video_cut: bool = Field(..., alias="videoCut")
    """是否剪辑版"""
    view_steam_id: str | None = Field(None, alias="viewSteamId")
    """查看者SteamID"""
    could_grant_cut_video_vote: bool | None = Field(
        None, alias="couldGrantCutVideoVote"
    )
    """是否可授权剪辑"""
    type: int
    """视频类型"""


class PerfectWorldVideoListResult(BaseModel):
    """视频列表结果"""

    user_video_list: list[PerfectWorldUserVideo] = Field(..., alias="userVideoList")
    """用户视频列表"""


class WatchPlayDataPlayer(BaseModel):
    """监控数据玩家"""

    steam_id: str = Field(..., alias="steamId", description="steamID")
    """steamID"""
    side: str = Field(..., alias="side", description="阵营")
    """阵营"""
    kill: int = Field(..., alias="kill", description="击杀数")
    """击杀数"""
    headshot: int = Field(..., alias="headshot", description="爆头数")
    """爆头数"""
    adr: int = Field(..., alias="adr", description="ADR")
    """ADR"""
    death: int = Field(..., alias="death", description="死亡数")
    """死亡数"""
    assist: int = Field(..., alias="assist", description="助攻数")
    """助攻数"""
    score: int = Field(..., alias="score", description="得分")
    """得分"""


class WatchPlayDataMessageData(BaseModel):
    """监控数据消息数据"""

    player_list: list[WatchPlayDataPlayer] = Field(
        ..., alias="playerList", description="玩家列表"
    )
    """玩家列表"""


class WatchPlayData(BaseModel):
    start_time: datetime = Field(..., alias="startTime", description="开始时间")
    """开始时间"""
    duration: int = Field(..., alias="duration", description="持续时间")
    """持续时间"""
    map: str = Field(..., alias="map", description="地图")
    """地图"""
    ct_score: list[int] = Field(..., alias="ctScore", description="ct分数")
    """ct分数"""
    t_score: list[int] = Field(..., alias="terroristScore", description="t分数")
    """t分数"""
    message_data: WatchPlayDataMessageData = Field(
        ..., alias="messageData", description="消息数据"
    )
    """消息数据"""


class UserMatchItem(BaseModel):
    """比赛详情项"""

    match_id: str = Field(..., alias="matchId", description="比赛ID")
    """比赛ID"""
    player_id: str = Field(..., alias="playerId", description="玩家ID")
    """玩家ID"""
    honor: Any = Field(None, alias="honor", description="荣誉值")
    """荣誉值"""
    k4: int = Field(..., alias="k4", description="四杀数量")
    """四杀数量"""
    k5: int = Field(..., alias="k5", description="五杀数量")
    """五杀数量"""
    match_score: float = Field(..., alias="matchScore", description="比赛得分")
    """比赛得分"""
    map_url: str = Field(..., alias="mapUrl", description="地图URL")
    """地图URL"""
    map_logo: str = Field(..., alias="mapLogo", description="地图Logo")
    """地图Logo"""
    map_name: str = Field(..., alias="mapName", description="地图名称")
    """地图名称"""
    steam_name: Any = Field(None, alias="steamName", description="Steam名称")
    """Steam名称"""
    steam_avatar: Any = Field(None, alias="steamAvatar", description="Steam头像")
    """Steam头像"""
    team: int = Field(..., alias="team", description="玩家所在队伍")
    """玩家所在队伍"""
    win_team: int = Field(..., alias="winTeam", description="获胜队伍")
    """获胜队伍"""
    score1: int = Field(..., alias="score1", description="队伍1得分")
    """队伍1得分"""
    score2: int = Field(..., alias="score2", description="队伍2得分")
    """队伍2得分"""
    rating: float = Field(..., alias="rating", description="比赛Rating")
    """比赛Rating"""
    pw_rating: float = Field(..., alias="pwRating", description="PW平台Rating")
    """PW平台Rating"""
    leave_time: str = Field(..., alias="leaveTime", description="离开时间")
    """离开时间"""
    start_time: str = Field(..., alias="startTime", description="开始时间")
    """开始时间"""
    end_time: str = Field(..., alias="endTime", description="结束时间")
    """结束时间"""
    time_stamp: int = Field(..., alias="timeStamp", description="时间戳")
    """时间戳"""
    page_time_stamp: int = Field(..., alias="pageTimeStamp", description="页面时间戳")
    """页面时间戳"""
    kill: int = Field(..., alias="kill", description="击杀数")
    """击杀数"""
    bot_kill: int = Field(..., alias="botKill", description="Bot击杀数")
    """Bot击杀数"""
    neg_kill: int = Field(..., alias="negKill", description="负击杀数")
    """负击杀数"""
    death: int = Field(..., alias="death", description="死亡数")
    """死亡数"""
    assist: int = Field(..., alias="assist", description="助攻数")
    """助攻数"""
    duration: int = Field(..., alias="duration", description="持续时间（分钟）")
    """持续时间（分钟）"""
    data_source: int = Field(..., alias="dataSource", description="数据来源")
    """数据来源"""
    cup_name: Any = Field(None, alias="cupName", description="杯赛名称")
    """杯赛名称"""
    round_remark: Any = Field(None, alias="roundRemark", description="回合备注")
    """回合备注"""
    mode: str = Field(..., alias="mode", description="游戏模式")
    """游戏模式"""
    pvp_score: int = Field(..., alias="pvpScore", description="PVP分数")
    """PVP分数"""
    pvp_score_change: int = Field(
        ..., alias="pvpScoreChange", description="PVP分数变化"
    )
    """PVP分数变化"""
    pvp_score_change_type: int = Field(
        ..., alias="pvpScoreChangeType", description="PVP分数变化类型"
    )
    """PVP分数变化类型"""
    pvp_mvp: bool = Field(..., alias="pvpMvp", description="是否PVP MVP")
    """是否PVP MVP"""
    pvp_normal_rank: Any = Field(None, alias="pvpNormalRank", description="PVP普通排名")
    """PVP普通排名"""
    pvp_stars: int = Field(..., alias="pvpStars", description="PVP星级")
    """PVP星级"""
    group: bool = Field(..., alias="group", description="是否组队")
    """是否组队"""
    rank: int = Field(..., alias="rank", description="排名")
    """排名"""
    old_rank: int = Field(..., alias="oldrank", description="旧排名")
    """旧排名"""
    game_mode: Any = Field(None, alias="gameMode", description="游戏模式（备用）")
    """游戏模式（备用）"""
    pvp_grading: int = Field(..., alias="pvpGrading", description="PVP评级")
    """PVP评级"""
    match_type: Any = Field(None, alias="matchType", description="比赛类型")
    """比赛类型"""
    delta_rank: Any = Field(None, alias="deltaRank", description="排名变化")
    """排名变化"""
    we: float = Field(..., alias="we", description="WE值")
    """WE值"""
    status: int = Field(..., alias="status", description="状态")
    """状态"""
    steam_nick: Any = Field(None, alias="steamNick", description="Steam昵称")
    """Steam昵称"""
    player_info_list: list[Any] = Field(
        ..., alias="playerInfoList", description="玩家信息列表"
    )
    """玩家信息列表"""
    green_match: bool = Field(..., alias="greenMatch", description="是否绿色比赛")
    """是否绿色比赛"""
    mvp: bool = Field(..., alias="mvp", description="是否MVP")
    """是否MVP"""


class UserMatch(BaseModel):
    """根模型"""

    data_public: bool = Field(..., alias="dataPublic", description="数据是否公开")
    """数据是否公开"""
    match_list: list[UserMatchItem] = Field(
        ..., alias="matchList", description="比赛列表"
    )
    """比赛列表"""


class BaseMatchInfo(BaseModel):
    """基础比赛信息"""

    match_id: str = Field(..., alias="matchId", description="比赛ID")
    """比赛ID"""
    map: str = Field(..., alias="map", description="地图中文名")
    """地图中文名"""
    map_en: str = Field(..., alias="mapEn", description="地图英文名")
    """地图英文名"""
    map_url: str = Field(..., alias="mapUrl", description="地图背景图URL")
    """地图背景图URL"""
    match_type: Any = Field(None, alias="matchType", description="比赛类型")
    """比赛类型"""
    map_logo: str = Field(..., alias="mapLogo", description="地图Logo")
    """地图Logo"""
    start_time: str = Field(..., alias="startTime", description="开始时间")
    """开始时间"""
    end_time: str = Field(..., alias="endTime", description="结束时间")
    """结束时间"""
    duration: int = Field(..., alias="duration", description="持续时间（分钟）")
    """持续时间（分钟）"""
    win_team: int = Field(..., alias="winTeam", description="获胜队伍")
    """获胜队伍"""
    score1: int = Field(..., alias="score1", description="队伍1得分")
    """队伍1得分"""
    score2: int = Field(..., alias="score2", description="队伍2得分")
    """队伍2得分"""
    half_score1: int = Field(..., alias="halfScore1", description="上半场队伍1得分")
    """上半场队伍1得分"""
    half_score2: int = Field(..., alias="halfScore2", description="上半场队伍2得分")
    """上半场队伍2得分"""
    extra_score1: int = Field(..., alias="extraScore1", description="加时赛队伍1得分")
    """加时赛队伍1得分"""
    extra_score2: int = Field(..., alias="extraScore2", description="加时赛队伍2得分")
    """加时赛队伍2得分"""
    cup_name: Any = Field(None, alias="cupName", description="杯赛名称")
    """杯赛名称"""
    cup_logo: Any = Field(None, alias="cupLogo", description="杯赛Logo")
    """杯赛Logo"""
    round_remark: Any = Field(None, alias="roundRemark", description="回合备注")
    """回合备注"""
    team1_name: Any = Field(None, alias="team1Name", description="队伍1名称")
    """队伍1名称"""
    team1_logo: Any = Field(None, alias="team1Logo", description="队伍1 Logo")
    """队伍1 Logo"""
    team2_name: Any = Field(None, alias="team2Name", description="队伍2名称")
    """队伍2名称"""
    team2_logo: Any = Field(None, alias="team2Logo", description="队伍2 Logo")
    """队伍2 Logo"""
    team1_pvp_id: int = Field(..., alias="team1PvpId", description="队伍1 PVP ID")
    """队伍1 PVP ID"""
    team2_pvp_id: int = Field(..., alias="team2PvpId", description="队伍2 PVP ID")
    """队伍2 PVP ID"""
    pvp_ladder: bool = Field(..., alias="pvpLadder", description="是否PVP天梯赛")
    """是否PVP天梯赛"""
    half_camp1: int = Field(..., alias="halfCamp1", description="上半场队伍1阵营")
    """上半场队伍1阵营"""
    mode: str = Field(..., alias="mode", description="游戏模式")
    """游戏模式"""
    game_mode: Any = Field(None, alias="gameMode", description="游戏模式（备用）")
    """游戏模式（备用）"""
    team1_info: Any = Field(None, alias="team1Info", description="队伍1信息")
    """队伍1信息"""
    team2_info: Any = Field(None, alias="team2Info", description="队伍2信息")
    """队伍2信息"""
    kill_info: Any = Field(None, alias="killInfo", description="击杀信息")
    """击杀信息"""
    team1_round: Any = Field(None, alias="team1round", description="队伍1回合信息")
    """队伍1回合信息"""
    team2_round: Any = Field(None, alias="team2round", description="队伍2回合信息")
    """队伍2回合信息"""
    green_match: bool = Field(..., alias="greenMatch", description="是否绿色比赛")
    """是否绿色比赛"""


class PerfectWorldPlayerInfo(BaseModel):
    """玩家信息"""

    player_id: str = Field(..., alias="playerId", description="玩家ID")
    """玩家ID"""
    highlights_data: Any = Field(None, alias="highlightsData", description="高光数据")
    """高光数据"""
    nick_name: str = Field(..., alias="nickName", description="昵称")
    """昵称"""
    avatar: str = Field(..., alias="avatar", description="头像URL")
    """头像URL"""
    vac: bool = Field(..., alias="vac", description="是否VAC封禁")
    """是否VAC封禁"""
    team: int = Field(..., alias="team", description="队伍ID")
    """队伍ID"""
    kill: int = Field(..., alias="kill", description="击杀数")
    """击杀数"""
    bot_kill: int = Field(..., alias="botKill", description="Bot击杀数")
    """Bot击杀数"""
    neg_kill: int = Field(..., alias="negKill", description="负击杀数")
    """负击杀数"""
    hand_gun_kill: int = Field(..., alias="handGunKill", description="手枪击杀数")
    """手枪击杀数"""
    entry_kill: int = Field(..., alias="entryKill", description="首杀数")
    """首杀数"""
    awp_kill: int = Field(..., alias="awpKill", description="AWP击杀数")
    """AWP击杀数"""
    death: int = Field(..., alias="death", description="死亡数")
    """死亡数"""
    entry_death: int = Field(..., alias="entryDeath", description="首死数")
    """首死数"""
    assist: int = Field(..., alias="assist", description="助攻数")
    """助攻数"""
    head_shot: int = Field(..., alias="headShot", description="爆头数")
    """爆头数"""
    head_shot_ratio: float = Field(..., alias="headShotRatio", description="爆头率")
    """爆头率"""
    rating: float = Field(..., alias="rating", description="Rating")
    """Rating"""
    pw_rating: float = Field(..., alias="pwRating", description="PW Rating")
    """PW Rating"""
    damage: int = Field(..., alias="damage", description="伤害量")
    """伤害量"""
    item_throw: int = Field(..., alias="itemThrow", description="物品投掷数")
    """物品投掷数"""
    flash: int = Field(..., alias="flash", description="闪光弹投掷数")
    """闪光弹投掷数"""
    flash_teammate: int = Field(
        ..., alias="flashTeammate", description="闪光弹致盲队友数"
    )
    """闪光弹致盲队友数"""
    flash_success: int = Field(
        ..., alias="flashSuccess", description="闪光弹成功致盲数"
    )
    """闪光弹成功致盲数"""
    end_game: int = Field(..., alias="endGame", description="游戏结束次数")
    """游戏结束次数"""
    mvp_value: int = Field(..., alias="mvpValue", description="MVP值")
    """MVP值"""
    score: int = Field(..., alias="score", description="分数")
    """分数"""
    user_forbid_dto: Any = Field(None, alias="userForbidDTO", description="用户禁用DTO")
    """用户禁用DTO"""
    ban_type: int = Field(..., alias="banType", description="封禁类型")
    """封禁类型"""
    two_kill: int = Field(..., alias="twoKill", description="双杀数")
    """双杀数"""
    three_kill: int = Field(..., alias="threeKill", description="三杀数")
    """三杀数"""
    four_kill: int = Field(..., alias="fourKill", description="四杀数")
    """四杀数"""
    five_kill: int = Field(..., alias="fiveKill", description="五杀数")
    """五杀数"""
    multi_kills: int = Field(..., alias="multiKills", description="多杀次数")
    """多杀次数"""
    vs1: int = Field(..., alias="vs1", description="1vX 残局次数")
    """1vX 残局次数"""
    vs2: int = Field(..., alias="vs2", description="2vX 残局次数")
    """2vX 残局次数"""
    vs3: int = Field(..., alias="vs3", description="3vX 残局次数")
    """3vX 残局次数"""
    vs4: int = Field(..., alias="vs4", description="4vX 残局次数")
    """4vX 残局次数"""
    vs5: int = Field(..., alias="vs5", description="5vX 残局次数")
    """5vX 残局次数"""
    head_shot_count: int = Field(..., alias="headShotCount", description="爆头总数")
    """爆头总数"""
    dmg_armor: int = Field(..., alias="dmgArmor", description="护甲伤害")
    """护甲伤害"""
    dmg_health: int = Field(..., alias="dmgHealth", description="生命值伤害")
    """生命值伤害"""
    adpr: int = Field(..., alias="adpr", description="ADR")
    """ADR"""
    fire_count: int = Field(..., alias="fireCount", description="开火次数")
    """开火次数"""
    hit_count: int = Field(..., alias="hitCount", description="命中次数")
    """命中次数"""
    rws: float = Field(..., alias="rws", description="RWS值")
    """RWS值"""
    pvp_team: int = Field(..., alias="pvpTeam", description="PVP队伍ID")
    """PVP队伍ID"""
    kast: float = Field(..., alias="kast", description="KAST值")
    """KAST值"""
    rank: int = Field(..., alias="rank", description="排名")
    """排名"""
    old_rank: int = Field(..., alias="oldRank", description="旧排名")
    """旧排名"""
    start_time: Any = Field(None, alias="startTime", description="开始时间（备用）")
    """开始时间（备用）"""
    honor: str | None = Field(None, alias="honor", description="荣誉（字符串）")
    """荣誉（字符串）"""
    pvp_score: int = Field(..., alias="pvpScore", description="PVP分数")
    """PVP分数"""
    pvp_score_change: int = Field(
        ..., alias="pvpScoreChange", description="PVP分数变化"
    )
    """PVP分数变化"""
    we: float = Field(..., alias="we", description="WE值")
    """WE值"""
    weapons: Any = Field(None, alias="weapons", description="武器信息")
    """武器信息"""
    throws_cnt: int = Field(..., alias="throwsCnt", description="投掷物数量")
    """投掷物数量"""
    is_vip: bool = Field(..., alias="isVip", description="是否VIP")
    """是否VIP"""
    avatar_frame: Any = Field(None, alias="avatarFrame", description="头像框")
    """头像框"""
    team_id: int = Field(..., alias="teamId", description="队伍ID")
    """队伍ID"""
    pvp_normal_rank: Any = Field(None, alias="pvpNormalRank", description="PVP普通排名")
    """PVP普通排名"""
    snipe_num: int = Field(..., alias="snipeNum", description="狙击击杀数")
    """狙击击杀数"""
    first_death: int = Field(..., alias="firstDeath", description="首死数")
    """首死数"""
    bomb_planted: Any = Field(None, alias="bombPlanted", description="炸弹安放次数")
    """炸弹安放次数"""
    bomb_defused: Any = Field(None, alias="bombDefused", description="炸弹拆除次数")
    """炸弹拆除次数"""
    smoke_throws: Any = Field(None, alias="smokeThrows", description="烟雾弹投掷数")
    """烟雾弹投掷数"""
    grenade_damage: Any = Field(None, alias="grenadeDamage", description="手榴弹伤害")
    """手榴弹伤害"""
    inferno_damage: Any = Field(None, alias="infernoDamage", description="燃烧弹伤害")
    """燃烧弹伤害"""
    title: Any = Field(None, alias="title", description="头衔")
    """头衔"""
    interest_img: Any = Field(None, alias="interestImg", description="兴趣图片")
    """兴趣图片"""
    cs_match_player_interest_list: list[Any] = Field(
        ..., alias="csMatchPlayerInterestList", description="CS比赛玩家兴趣列表"
    )
    """CS比赛玩家兴趣列表"""
    first: list[Any] = Field(..., alias="first", description="第一名成就列表")
    """第一名成就列表"""
    second: list[Any] = Field(..., alias="second", description="第二名成就列表")
    """第二名成就列表"""
    third: list[Any] = Field(..., alias="third", description="第三名成就列表")
    """第三名成就列表"""
    match_id: Any = Field(None, alias="matchId", description="比赛ID（备用）")
    """比赛ID（备用）"""
    green_user: bool = Field(..., alias="greenUser", description="是否绿色用户")
    """是否绿色用户"""
    mvp: bool = Field(..., alias="mvp", description="是否MVP")
    """是否MVP"""


class PerfectWorldMatchDetailData(BaseModel):
    """根模型"""

    base: BaseMatchInfo = Field(..., alias="base", description="基础比赛信息")
    """基础比赛信息"""
    players: list[PerfectWorldPlayerInfo] = Field(
        ..., alias="players", description="玩家信息列表"
    )
    """玩家信息列表"""
