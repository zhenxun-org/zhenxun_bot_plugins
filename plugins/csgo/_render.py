from pathlib import Path
from nonebot.compat import model_dump
from zhenxun import ui

from .config import (
    CURRENT_SEASON,
    HotMap,
    PerfectWorldMapRate,
    PerfectWorldMatchDetailData,
    PerfectWorldOfficialDetailDataStats,
    PerfectWorldPlatformDetailDataStats,
    UserMatchItem,
)


class Renderer:
    """渲染器"""

    @classmethod
    def _get_template_path(cls, template_name: str) -> Path:
        """获取模板文件路径"""
        return Path(__file__).parent / "csgo" / template_name

    @classmethod
    async def render_map_data(
        cls,
        map_data: list[HotMap],
        map_rate_data: list[PerfectWorldMapRate],
        player_name: str = "未知玩家",
        steam_id: str = "未知",
        avatar_url: str = "",
        season: str = CURRENT_SEASON,
    ) -> bytes:
        """渲染地图胜率HTML

        参数:
            map_data: 地图数据
            player_name: 玩家名称
            steam_id: Steam ID
            avatar_url: 头像URL
            season: 赛季

        返回:
            bytes: 图片数据
        """

        map_data_dict = [model_dump(v) for v in map_data]
        for map in map_data_dict:
            if map_rate := next(
                (rate for rate in map_rate_data if rate.map_name_en == map["map"]),
                None,
            ):
                map["map_rate"] = model_dump(map_rate)

        template_component = ui.template(
            path=cls._get_template_path("map_data.html"),
            data={
                "maps": map_data_dict,
                "player_name": player_name,
                "steam_id": steam_id,
                "avatar_url": avatar_url,
                "season": season,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_perfect_world_user(
        cls,
        player_info: PerfectWorldPlatformDetailDataStats,
        avatar_url: str = "",
        season: str = CURRENT_SEASON,
    ) -> bytes:
        """渲染地图胜率HTML

        参数:
            player_info: 玩家信息
            avatar_url: 头像URL
            season: 赛季

        返回:
            bytes: 图片数据
        """
        template_component = ui.template(
            path=cls._get_template_path("perfect_world_user.html"),
            data={
                "player_stats": model_dump(player_info),
                "avatar_url": avatar_url,
                "season": season,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_official_user(
        cls,
        player_info: PerfectWorldOfficialDetailDataStats,
    ) -> bytes:
        """渲染地图胜率HTML

        参数:
            player_info: 玩家信息

        返回:
            bytes: 图片数据
        """
        template_component = ui.template(
            path=cls._get_template_path("official_user.html"),
            data={
                "player_stats": model_dump(player_info),
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_match_list(
        cls,
        match_list: list[UserMatchItem],
        player_name: str = "未知玩家",
        steam_id: str = "未知",
        avatar_url: str = "",
        total_matches: int = 0,
        win_count: int = 0,
        win_rate: float = 0.0,
        kd_ratio: float = 0.0,
        avg_rating: float = 0.0,
        current_page: int = 1,
        page_count: int = 1,
    ) -> bytes:
        """渲染比赛列表HTML

        参数:
            match_list: 比赛列表数据
            player_name: 玩家名称
            steam_id: Steam ID
            avatar_url: 头像URL
            total_matches: 比赛总数
            win_count: 胜场数
            win_rate: 胜率
            kd_ratio: K/D比
            avg_rating: 平均评分
            current_page: 当前页码
            page_count: 总页数

        返回:
            bytes: 图片数据
        """
        match_list_dict = [model_dump(match) for match in match_list]

        template_component = ui.template(
            path=cls._get_template_path("match_list.html"),
            data={
                "match_list": match_list_dict,
                "player_name": player_name,
                "steam_id": steam_id,
                "avatar_url": avatar_url,
                "total_matches": total_matches,
                "win_count": win_count,
                "win_rate": win_rate,
                "kd_ratio": kd_ratio,
                "avg_rating": avg_rating,
                "current_page": current_page,
                "page_count": page_count,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_match_detail(
        cls,
        match_data: PerfectWorldMatchDetailData,
    ) -> bytes:
        """渲染比赛详情HTML

        参数:
            match_data: 比赛详情数据

        返回:
            bytes: 图片数据
        """
        base_data = model_dump(match_data.base)
        players_data = [model_dump(player) for player in match_data.players]

        template_component = ui.template(
            path=cls._get_template_path("match_detail.html"),
            data={
                "base": base_data,
                "players": players_data,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_video_list(
        cls,
        video_list: list,
        player_name: str = "未知玩家",
        steam_id: str = "未知",
        avatar_url: str = "",
        total_count: int = 0,
    ) -> bytes:
        """渲染视频列表HTML

        参数:
            video_list: 视频列表数据
            player_name: 玩家名称
            steam_id: Steam ID
            avatar_url: 头像URL
            total_count: 视频总数

        返回:
            bytes: 图片数据
        """
        template_component = ui.template(
            path=cls._get_template_path("video_list.html"),
            data={
                "videos": video_list,
                "player_name": player_name,
                "steam_id": steam_id,
                "avatar_url": avatar_url,
                "total_count": total_count,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )

    @classmethod
    async def render_rank_list(
        cls,
        user_index: int,
        player_list: list[dict],
        rank_type: str = "score",
    ) -> bytes:
        """渲染排行榜HTML

        参数:
            user_index: 用户排名
            player_list: 玩家列表数据
            rank_type: 排行榜类型，默认为"分数"

        返回:
            bytes: 图片数据
        """
        rank_type = "分数" if rank_type == "score" else "RT"
        template_component = ui.template(
            path=cls._get_template_path("rank_list.html"),
            data={
                "user_index": user_index,
                "player_list": player_list,
                "type": rank_type,
            },
        )
        return await ui.render(
            template_component,
            viewport={"width": 1000, "height": 600},
        )
