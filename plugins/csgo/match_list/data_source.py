import asyncio
from datetime import datetime
from typing import cast

from .._data_source import CallApi
from .._render import Renderer
from ..config import DEFAULT_AVATAR_URL, PerfectWorldMatchDetailData, UserMatchItem
from ..exceptions import CsgoDataQueryException
from ..models.csgo_perfect_world_match import CsgoPerfectWorldMatch
from ..models.csgo_user import CsgoUser


class MatchListManager:
    @classmethod
    async def get_match_detail(cls, match_id: str) -> PerfectWorldMatchDetailData:
        match = await CsgoPerfectWorldMatch.get_or_none(match_id__endswith=match_id)
        if match:
            match_id = match.match_id
        else:
            raise CsgoDataQueryException(
                "未查询到对应后四位的比赛ID，请检查比赛ID是否正确"
            )

        response = await CallApi.get_match_detail(match_id)
        if not response.data:
            raise CsgoDataQueryException("未查询到数据，请检查比赛ID是否正确")
        return response.data

    @classmethod
    async def get_match_list(
        cls, steam_id: str, page_value: int
    ) -> list[UserMatchItem]:
        """获取玩家比赛列表"""

        response = await CallApi.get_match_list(steam_id, page_value)
        if not response.data:
            raise CsgoDataQueryException("完美战绩列表为空...")
        if not response.data.data_public:
            raise CsgoDataQueryException("用户隐藏了战绩...")

        # 异步保存比赛数据
        asyncio.create_task(cls.save_match_list(steam_id, response.data.match_list))  # noqa: RUF006

        return response.data.match_list

    @classmethod
    async def save_match_list(
        cls, steam_id: str, match_list: list[UserMatchItem]
    ) -> int:
        """将比赛数据保存到数据库

        参数:
            steam_id: steam_id
            match_list: 比赛列表数据

        返回:
            int: 成功保存的记录数
        """
        # 如果没有比赛数据，直接返回
        if not match_list:
            return 0

        # 获取所有match_id
        match_ids = [match.match_id for match in match_list]

        # 获取或创建用户
        user = await CsgoUser.get_or_none(steam_id=steam_id)
        if not user:
            user = await CsgoUser.create(steam_id=steam_id)

        # 查询数据库中已存在的match_id
        existing_match_ids = cast(
            list[str],
            await CsgoPerfectWorldMatch.filter(match_id__in=match_ids).values_list(
                "match_id", flat=True
            ),
        )

        # 筛选出需要保存的新比赛
        new_matches = [
            match for match in match_list if match.match_id not in existing_match_ids
        ]

        if not new_matches:
            return 0  # 没有新的比赛记录需要保存

        # 批量创建新记录
        match_records = []
        for match in new_matches:
            # 将字符串时间转换为datetime对象
            try:
                start_time = datetime.strptime(match.start_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # 如果格式不匹配，尝试其他可能的格式
                try:
                    start_time = datetime.strptime(
                        match.start_time, "%Y/%m/%d %H:%M:%S"
                    )
                except ValueError:
                    # 如果仍然失败，使用当前时间
                    start_time = datetime.now()

            # 创建新记录对象
            match_record = CsgoPerfectWorldMatch(
                user=user,
                match_id=match.match_id,
                mode=match.mode,
                map_name=match.map_name,
                map_logo=match.map_logo,
                score1=match.score1,
                score2=match.score2,
                team=match.team,
                win_team=match.win_team,
                kill=match.kill,
                death=match.death,
                assist=match.assist,
                rating=match.rating,
                we=match.we,
                mvp=match.mvp,
                k4=match.k4,
                k5=match.k5,
                start_time=start_time,
            )
            match_records.append(match_record)

        # 批量保存到数据库
        if match_records:
            await CsgoPerfectWorldMatch.bulk_create(match_records)

        return len(match_records)

    @classmethod
    async def render_user_match_list(
        cls, steam_id: str, page_value: int, avatar_url: str | None, name: str
    ) -> bytes:
        """获取玩家比赛列表并渲染为图片

        参数:
            steam_id: Steam ID
            page_value: 页码
            avatar_url: 头像URL
            name: 玩家名称

        返回:
            bytes: 渲染后的图片数据
        """
        if page_value < 1:
            raise CsgoDataQueryException("页码不能小于1")
        # 获取比赛列表
        match_list = await cls.get_match_list(steam_id, page_value)
        if not match_list:
            raise CsgoDataQueryException("未找到比赛记录...")

        # 获取用户信息
        user_info = await CsgoUser.filter(steam_id=steam_id).first()
        if not user_info:
            raise CsgoDataQueryException("未找到用户信息，请先绑定Steam ID...")

        # 计算统计数据
        total_matches = len(match_list)
        win_count = sum(match.team == match.win_team for match in match_list)
        win_rate = round(win_count / total_matches * 100, 2) if total_matches > 0 else 0

        total_kills = sum(match.kill for match in match_list)
        total_deaths = sum(match.death for match in match_list)
        kd_ratio = round(total_kills / total_deaths, 2) if total_deaths > 0 else 0

        # 计算平均评分
        total_rating = sum(match.rating for match in match_list)
        avg_rating = round(total_rating / total_matches, 2) if total_matches > 0 else 0

        # 获取头像URL和玩家名称
        avatar_url = avatar_url or user_info.perfect_avatar_url or DEFAULT_AVATAR_URL
        player_name = name or user_info.perfect_name or steam_id

        # 调用渲染器生成图片
        return await Renderer.render_match_list(
            match_list=match_list,
            player_name=player_name,
            steam_id=steam_id,
            avatar_url=avatar_url,
            total_matches=total_matches,
            win_count=win_count,
            win_rate=win_rate,
            kd_ratio=kd_ratio,
            avg_rating=avg_rating,
            current_page=page_value,
            page_count=10,  # 假设总页数为10，实际应该从API获取
        )
