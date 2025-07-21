import asyncio
import math
import time

from aiowebsocket.converses import AioWebSocket
from nonebot.adapters import Bot
from nonebot_plugin_uninfo import Uninfo
from tortoise.transactions import atomic
import ujson as json

from zhenxun.configs.config import Config
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.platform import PlatformUtils

from .config import (
    LOG_COMMAND,
    PERFECT_WORLD_MAP_RATE_URL,
    PERFECT_WORLD_MATCH_DETAIL_URL,
    PERFECT_WORLD_MATCH_LIST_URL,
    PERFECT_WORLD_USER_OFFICIAL_DATA_API_URL,
    PERFECT_WORLD_USER_PLATFORM_DATA_URL,
    PERFECT_WORLD_VIDEO_URL,
    PERFECT_WORLD_WWS,
    SAVE_PATH,
    BaseResponse,
    PerfectWorldMapRate,
    PerfectWorldMatchDetailData,
    PerfectWorldOfficialDetailDataStats,
    PerfectWorldPlatformDetailDataStats,
    PerfectWorldVideoListResult,
    UserMatch,
)
from .exceptions import CsgoDataQueryException, SteamIdNotBoundException
from .models.csgo_map_stats import CsgoMapStats
from .models.csgo_official_stats import CsgoOfficialStats
from .models.csgo_perfect_stats import CsgoPerfectStats
from .models.csgo_rating_history import CsgoRatingHistory
from .models.csgo_user import CsgoUser
from .models.csgo_weapon_efficiency import CsgoWeaponEfficiency
from .models.csgo_weapon_stats import CsgoWeaponStats

# 视频缓存目录
VIDEO_CACHE_DIR = SAVE_PATH / "videos"


base_config = Config.get("csgo")


class CallApi:
    @classmethod
    async def get_match_detail(
        cls, match_id: str
    ) -> BaseResponse[PerfectWorldMatchDetailData]:
        """获取玩家比赛详情"""

        app_version = base_config.get("appversion")
        if not app_version:
            raise CsgoDataQueryException("未设置appversion")

        token = base_config.get("token")
        if not token:
            raise CsgoDataQueryException("未设置token")

        response = await AsyncHttpx.post(
            PERFECT_WORLD_MATCH_DETAIL_URL,
            headers={
                "accessToken": token,
                "appversion": app_version,
                "platform": "h5_android",
            },
            json={"matchId": match_id, "platform": "admin", "dataSource": "3"},
        )
        response.raise_for_status()
        response_data = response.json()
        if response_data["statusCode"] != 0:
            logger.error(f"获取玩家完美战绩详情失败: {response_data['errorMessage']}")
            raise CsgoDataQueryException(
                f"获取玩家完美战绩详情失败: {response_data['errorMessage']}"
            )
        if not response_data["data"]:
            raise CsgoDataQueryException("未查询到数据，请检查比赛ID是否正确")
        return BaseResponse[PerfectWorldMatchDetailData](
            statusCode=response_data["statusCode"],
            errorMessage=response_data["errorMessage"],
            data=PerfectWorldMatchDetailData(**response_data["data"]),
        )

    @classmethod
    async def get_match_list(
        cls, steam_id: str, page_value: int
    ) -> BaseResponse[UserMatch]:
        """获取玩家比赛列表"""

        app_version = base_config.get("appversion")
        if not app_version:
            raise CsgoDataQueryException("未设置appversion")

        token = base_config.get("token")
        if not token:
            raise CsgoDataQueryException("未设置token")

        token_steam_id = base_config.get("token_steam_id")
        if not token_steam_id:
            raise CsgoDataQueryException("未设置token_steam_id")

        response = await AsyncHttpx.post(
            PERFECT_WORLD_MATCH_LIST_URL,
            headers={
                "User-Agent": "okhttp/4.11.0",
                "Content-Type": "application/json",
                "t": str(math.floor(time.time() / 1000)),
                "appversion": app_version,
                "token": token,
                "platform": "android",
                "gameType": "2",
                "gameTypeStr": "2",
            },
            json={
                "mySteamId": token_steam_id,
                "toSteamId": steam_id,
                "csgoSeasonId": "recent",
                "pvpType": -1,
                "page": page_value,
                "pageSize": 10,
                "dataSource": 3,
            },
        )
        response.raise_for_status()
        response_data = response.json()
        if response_data["statusCode"] != 0:
            logger.error(f"获取玩家完美战绩失败: {response_data['errorMessage']}")
            raise CsgoDataQueryException(
                f"获取玩家完美战绩失败: {response_data['errorMessage']}"
            )
        if not response_data["data"]:
            raise CsgoDataQueryException("未查询到数据，请检查Steam ID是否正确")

        return BaseResponse[UserMatch](
            statusCode=response_data["statusCode"],
            errorMessage=response_data["errorMessage"],
            data=UserMatch(**response_data["data"]),
        )

    @classmethod
    async def get_map_rate(
        cls, steam_id: str, season: str
    ) -> BaseResponse[list[PerfectWorldMapRate]]:
        """获取玩家地图胜率

        参数:
            steam_id: steam_id
            season: 赛季

        返回:
            PerfectWorldMapRate: PerfectWorldMapRate
        """
        response = await AsyncHttpx.get(
            PERFECT_WORLD_MAP_RATE_URL.format(steam_id, season)
        )
        response.raise_for_status()
        # 在pydantic1.x版本时无法序列化泛型
        # return BaseResponse[list[PerfectWorldMapRate]](**response.json())
        response_data = response.json()
        if response_data["statusCode"] != 0:
            logger.error(f"获取玩家平台数据失败: {response_data['errorMessage']}")
            raise CsgoDataQueryException(
                f"获取玩家平台数据失败: {response_data['errorMessage']}"
            )
        if not response_data["data"]:
            raise CsgoDataQueryException("未查询到数据，请检查Steam ID是否正确")
        return BaseResponse[list[PerfectWorldMapRate]](
            statusCode=response_data["statusCode"],
            errorMessage=response_data["errorMessage"],
            data=[PerfectWorldMapRate(**v) for v in response_data["data"]],
        )

    @classmethod
    async def get_platform_user_data(
        cls, steam_id: str, season: str
    ) -> BaseResponse[PerfectWorldPlatformDetailDataStats]:
        """完美数据

        参数:
            steam_id: steam_id
            season: 赛季，例如 S20

        返回: BaseResponse[PerfectWorldPlatformDetailDataStats]: 数据内容
        """
        headers = {
            "User-Agent": "okhttp/4.11.0",
            "Content-Type": "application/json",
            "t": str(math.floor(time.time() / 1000)),
        }
        response = await AsyncHttpx.post(
            PERFECT_WORLD_USER_PLATFORM_DATA_URL,
            headers=headers,
            json={"steamId64": steam_id, "csgoSeasonId": season},
        )
        response.raise_for_status()
        # 在pydantic1.x版本时无法序列化泛型
        # return BaseResponse[PerfectWorldPlatformDetailDataStats](**response.json())
        response_data = response.json()
        if response_data["statusCode"] != 0:
            logger.error(f"获取玩家平台数据失败: {response_data['errorMessage']}")
            raise CsgoDataQueryException(
                f"获取玩家平台数据失败: {response_data['errorMessage']}"
            )
        if not response_data["data"]:
            raise CsgoDataQueryException("未查询到数据，请检查Steam ID是否正确")
        return BaseResponse[PerfectWorldPlatformDetailDataStats](
            statusCode=response_data["statusCode"],
            errorMessage=response_data["errorMessage"],
            data=PerfectWorldPlatformDetailDataStats(**response_data["data"]),
        )

    @classmethod
    async def get_official_user_data(
        cls, steam_id: str
    ) -> BaseResponse[PerfectWorldOfficialDetailDataStats]:
        """官匹数据

        参数:
            steam_id: steam_id

        返回: BaseResponse[PerfectWorldOfficialDetailDataStats]: 数据内容
        """
        headers = {
            "User-Agent": "okhttp/4.11.0",
            "Content-Type": "application/json",
            "gameType": "1,2",
            "gameTypeStr": "1,2",
            "t": str(math.floor(time.time() / 1000)),
        }
        response = await AsyncHttpx.post(
            PERFECT_WORLD_USER_OFFICIAL_DATA_API_URL,
            headers=headers,
            json={"mySteamId": steam_id, "toSteamId": steam_id, "accessToken": ""},
        )
        response.raise_for_status()
        # 在pydantic1.x版本时无法序列化泛型
        # return BaseResponse[PerfectWorldOfficialDetailDataStats](**response.json())

        response_data = response.json()
        if response_data["statusCode"] != 0:
            logger.error(f"获取玩家平台数据失败: {response_data['errorMessage']}")
            raise CsgoDataQueryException(
                f"获取玩家平台数据失败: {response_data['errorMessage']}"
            )
        if not response_data["data"]:
            raise CsgoDataQueryException("未查询到数据，请检查Steam ID是否正确")
        return BaseResponse[PerfectWorldOfficialDetailDataStats](
            statusCode=response_data["statusCode"],
            errorMessage=response_data["errorMessage"],
            data=PerfectWorldOfficialDetailDataStats(**response_data["data"]),
        )

    @classmethod
    async def get_video_list(
        cls, steam_id: str
    ) -> BaseResponse[PerfectWorldVideoListResult]:
        """获取玩家视频列表

        参数:
            steam_id: steam_id

        返回:
            BaseResponse[PerfectWorldVideoListResult]: 视频列表
        """
        response = await AsyncHttpx.get(PERFECT_WORLD_VIDEO_URL.format(steam_id))
        response.raise_for_status()
        # return BaseResponse[PerfectWorldVideoListResult](**response.json())
        response_data = response.json()
        if response_data["code"] != 1:
            logger.error(f"获取玩家平台数据失败: {response_data['message']}")
            raise CsgoDataQueryException(
                f"获取玩家平台数据失败: {response_data['message']}"
            )
        if not response_data["result"]:
            raise CsgoDataQueryException("未查询到数据，请检查Steam ID是否正确")

        return BaseResponse[PerfectWorldVideoListResult](
            statusCode=response_data["code"],
            errorMessage=response_data["message"],
            data=PerfectWorldVideoListResult(**response_data["result"]),
        )


class CsgoManager:
    """CSGO数据管理器，负责从API获取数据并存入数据库"""

    @classmethod
    async def get_steam_id_by_user_id(cls, user_id: str) -> str:
        """根据用户ID查询Steam ID

        参数:
            user_id: 用户ID

        返回:
            str: Steam ID

        异常:
            SteamIdNotBoundException: 如果用户未绑定Steam ID
        """
        # 查询用户记录
        user = await CsgoUser.get_or_none(user_id=user_id)
        if user and user.steam_id:
            return user.steam_id

        # 未找到Steam ID，抛出异常
        raise SteamIdNotBoundException()

    @classmethod
    async def get_user_platform_data(
        cls,
        session: Uninfo,
        target_id: str | None,
        steam_id: str | None,
        season: str,
        is_query: bool = False,
    ) -> PerfectWorldPlatformDetailDataStats | str:
        """获取玩家平台数据并在后台保存

        参数:
            session: Uninfo
            target_id: 用户ID
            steam_id: Steam ID，如果为None则尝试从数据库查询
            season: 赛季，例如 S20
            is_query: 是否查询其他人

        返回:
            数据内容，不等待保存完成
        """
        try:
            user_id = target_id or session.user.id
            if not user_id and not steam_id:
                logger.warning(
                    "用户ID和Steam ID不能同时为空", LOG_COMMAND, session=session
                )
                raise CsgoDataQueryException(
                    "用户ID和Steam ID不能同时为空，请绑定或输入Steam ID"
                )
            # 如果steam_id为空，尝试从数据库查询
            if user_id and not steam_id:
                steam_id = await cls.get_steam_id_by_user_id(user_id)
            if not steam_id:
                raise CsgoDataQueryException("未找到Steam ID，请绑定或输入Steam ID")

            response = await CallApi.get_platform_user_data(steam_id, season)

            # 综合评分，完美世界评分，分数趋势，rws，比赛分数需要反转
            if response.data.history_ratings:
                response.data.history_ratings.reverse()
            if response.data.history_rws:
                response.data.history_rws.reverse()
            if response.data.history_scores:
                response.data.history_scores.reverse()
            if response.data.history_pw_ratings:
                response.data.history_pw_ratings.reverse()
            if response.data.history_dates:
                response.data.history_dates.reverse()
            if response.data.score_list:
                response.data.score_list.reverse()
                response.data.pvp_score = response.data.score_list[-1].score

            asyncio.create_task(  # noqa: RUF006
                cls._save_user_platform_data(
                    user_id,
                    steam_id,
                    season,
                    response.data,
                    save_user_id=not is_query,
                )
            )

            # 立即返回数据
            return response.data
        except Exception as e:
            logger.error(
                "获取玩家平台数据时发生错误",
                LOG_COMMAND,
                session=session,
                e=e,
            )
            return "获取玩家平台数据失败..."

    @classmethod
    @atomic()
    async def _save_user_platform_data(
        cls,
        user_id: str,
        steam_id: str,
        season: str,
        data: PerfectWorldPlatformDetailDataStats,
        save_user_id: bool = True,
    ):
        """在后台保存玩家平台数据

        参数:
            user_id: 用户ID
            steam_id: Steam ID
            season: 赛季
            data: API返回的数据
            save_user_id: 是否保存user_id，当通过steam_id查询时应设为False
        """
        try:
            # 查找现有用户
            existing_user = None
            if user_id and save_user_id:
                existing_user = await CsgoUser.get_or_none(user_id=user_id)

            if not existing_user:
                # 如果用户不存在，尝试通过steam_id查找
                existing_user = await CsgoUser.get_or_none(steam_id=steam_id)

            if existing_user:
                # 用户存在，更新信息
                user = existing_user
                if not user.steam_id:
                    user.steam_id = steam_id
                user.perfect_name = data.name
                user.perfect_avatar_url = data.avatar
                await user.save(
                    update_fields=["steam_id", "perfect_name", "perfect_avatar_url"]
                )
            elif user_id and save_user_id:
                user = await CsgoUser.create(
                    user_id=user_id,
                    steam_id=steam_id,
                    name=data.name,
                    perfect_avatar_url=data.avatar,
                )
            else:
                # 只保存steam_id
                user = await CsgoUser.create(
                    steam_id=steam_id,
                    name=data.name,
                    perfect_avatar_url=data.avatar,
                )

            # 查找或创建完美平台统计数据
            stats, created = await CsgoPerfectStats.get_or_create(
                user=user, season_id=season
            )

            # 更新统计数据
            stats.season_id = data.season_id
            stats.pvp_rank = data.pvp_rank
            stats.total_matches = data.cnt
            stats.kd_ratio = data.kd
            stats.win_rate = data.win_rate
            stats.rating = data.rating
            stats.pw_rating = data.pw_rating
            stats.hit_rate = data.hit_rate
            stats.common_rating = data.common_rating
            stats.total_kills = data.kills
            stats.total_deaths = data.deaths
            stats.total_assists = data.assists
            stats.mvp_count = data.mvp_count
            stats.game_score = data.game_score
            stats.rws = data.rws
            stats.adr = data.adr
            stats.headshot_ratio = data.head_shot_ratio
            stats.entry_kill_ratio = data.entry_kill_ratio
            stats.double_kills = data.k2
            stats.triple_kills = data.k3
            stats.quad_kills = data.k4
            stats.penta_kills = data.k5
            stats.multi_kills = data.multi_kill
            stats.vs1_wins = data.vs1
            stats.vs2_wins = data.vs2
            stats.vs3_wins = data.vs3
            stats.vs4_wins = data.vs4
            stats.vs5_wins = data.vs5
            stats.ending_wins = data.ending_win
            stats.shot_rating = data.shot
            stats.victory_rating = data.victory
            stats.breach_rating = data.breach
            stats.snipe_rating = data.snipe
            stats.prop_rating = data.prop
            stats.vs1_win_rate = data.vs1_win_rate
            stats.summary = data.summary or ""
            stats.avg_weapon_efficiency = data.avg_we
            stats.pvp_score = data.pvp_score
            stats.stars = data.stars

            await stats.save()

            # 保存地图统计数据
            if data.hot_maps:
                for map_data in data.hot_maps:
                    map_stats, _ = await CsgoMapStats.get_or_create(
                        user=user,
                        map_name=map_data.map,
                        season_id=season,
                        defaults={
                            "map_image_url": map_data.map_image,
                            "map_logo_url": map_data.map_logo,
                            "map_name_zh": map_data.map_name,
                        },
                    )

                    map_stats.total_matches = map_data.total_match
                    map_stats.win_count = map_data.win_count
                    map_stats.total_kills = map_data.total_kill
                    map_stats.total_damage = int(map_data.total_adr)
                    map_stats.rating_sum = map_data.rating_sum
                    map_stats.rws_sum = map_data.rws_sum
                    map_stats.total_deaths = map_data.death_num
                    map_stats.first_kills = map_data.first_kill_num
                    map_stats.first_deaths = map_data.first_death_num
                    map_stats.headshot_kills = map_data.headshot_kill_num
                    map_stats.mvp_count = map_data.match_mvp_num
                    map_stats.triple_kills = map_data.three_kill_num
                    map_stats.quad_kills = map_data.four_kill_num
                    map_stats.penta_kills = map_data.five_kill_num
                    map_stats.vs3_wins = map_data.v3_num
                    map_stats.vs4_wins = map_data.v4_num
                    map_stats.vs5_wins = map_data.v5_num
                    map_stats.is_scuffle = map_data.scuffle

                    await map_stats.save()

            # 保存武器统计数据
            if data.hot_weapons:
                for weapon_data in data.hot_weapons:
                    weapon_stats, _ = await CsgoWeaponStats.get_or_create(
                        user=user,
                        weapon_code=weapon_data.weapon_name.lower(),
                        season_id=season,
                        platform_type=1,
                        defaults={
                            "weapon_name": weapon_data.weapon_name,
                            "weapon_image_url": weapon_data.weapon_image,
                        },
                    )

                    weapon_stats.total_kills = weapon_data.weapon_kill
                    weapon_stats.headshot_kills = weapon_data.weapon_head_shot
                    weapon_stats.total_matches = weapon_data.total_match
                    weapon_stats.headshot_rate = (
                        weapon_data.weapon_head_shot / weapon_data.weapon_kill
                        if weapon_data.weapon_kill > 0
                        else 0
                    )

                    await weapon_stats.save()

            # 保存评分历史
            if data.history_ratings and data.history_dates:
                # 只保存最新的评分记录
                if len(data.history_ratings) > 0 and len(data.history_dates) > 0:
                    await CsgoRatingHistory.create(
                        user=user,
                        rating_type="normal",
                        rating_value=data.history_ratings[0],
                        season_id=season,
                    )

                if len(data.history_pw_ratings) > 0 and len(data.history_dates) > 0:
                    await CsgoRatingHistory.create(
                        user=user,
                        rating_type="pw",
                        rating_value=data.history_pw_ratings[0],
                        season_id=season,
                    )

            # 保存武器效率记录
            if data.we_list:
                for idx, we_value in enumerate(data.we_list):
                    await CsgoWeaponEfficiency.create(
                        user=user,
                        efficiency_value=we_value,
                        record_index=idx,
                        season_id=season,
                    )

            logger.info(
                f"保存玩家 {steam_id} 的平台数据成功", LOG_COMMAND, session=user.user_id
            )

        except Exception as e:
            logger.error(
                f"保存玩家 {steam_id} 平台数据时发生错误",
                LOG_COMMAND,
                session=user_id,
                e=e,
            )

    @classmethod
    async def get_user_official_data(
        cls,
        session: Uninfo,
        target_id: str | None,
        steam_id: str | None,
        is_query: bool = False,
    ) -> PerfectWorldOfficialDetailDataStats | str:
        """获取玩家官方数据并在后台保存

        参数:
            session: Uninfo
            target_id: 用户ID
            steam_id: Steam ID，如果为None则尝试从数据库查询
            is_query: 是否查询他人

        返回:
            数据内容，不等待保存完成
        """
        try:
            user_id = target_id or session.user.id
            if not user_id and not steam_id:
                logger.warning(
                    "用户ID和Steam ID不能同时为空", LOG_COMMAND, session=session
                )
                raise CsgoDataQueryException(
                    "用户ID和Steam ID不能同时为空，请绑定或输入Steam ID"
                )

            # 如果steam_id为空，尝试从数据库查询
            if user_id and not steam_id:
                steam_id = await cls.get_steam_id_by_user_id(user_id)
            if not steam_id:
                raise CsgoDataQueryException("未找到Steam ID，请绑定或输入Steam ID")

            response = await CallApi.get_official_user_data(steam_id)

            max_length = min(
                [
                    len(response.data.history_dates or []),
                    30,
                ]
            )
            if not response.data.history_dates:
                response.data.history_ratings = []
                response.data.history_rws = []
                response.data.history_ranks = []
            else:

                def pad_and_slice(data_list: list, target_length: int) -> list:
                    """补0"""
                    if not data_list:
                        return [0] * target_length  #
                    current_length = len(data_list)
                    if current_length >= target_length:
                        return data_list[-target_length:]
                    else:
                        # 在前面补0
                        return data_list + [0] * (target_length - current_length)

                response.data.history_dates = pad_and_slice(
                    response.data.history_dates, max_length
                )
                response.data.history_ratings = pad_and_slice(
                    response.data.history_ratings, max_length
                )
                response.data.history_rws = pad_and_slice(
                    response.data.history_rws, max_length
                )
                response.data.history_comprehensive_scores = pad_and_slice(
                    response.data.history_comprehensive_scores or [], max_length
                )

                response.data.history_dates.reverse()
                response.data.history_ratings.reverse()
                response.data.history_rws.reverse()
                response.data.history_comprehensive_scores.reverse()

            asyncio.create_task(  # noqa: RUF006
                cls._save_user_official_data(
                    user_id, steam_id, response.data, save_user_id=not is_query
                )
            )

            return response.data
        except Exception as e:
            logger.error(
                "获取玩家官方数据时发生错误",
                LOG_COMMAND,
                session=session,
                e=e,
            )
            return "获取玩家官方数据失败..."

    @classmethod
    @atomic()
    async def _save_user_official_data(
        cls,
        user_id: str,
        steam_id: str,
        data: PerfectWorldOfficialDetailDataStats,
        save_user_id: bool = True,
    ):
        """保存玩家官方数据

        参数:
            user_id: 用户ID
            steam_id: Steam ID
            data: API返回的数据
            save_user_id: 是否保存user_id，当通过steam_id查询时应设为False
        """
        try:
            # 查找现有用户
            existing_user = None
            if user_id and save_user_id:
                existing_user = await CsgoUser.get_or_none(user_id=user_id)

            if not existing_user:
                # 如果用户不存在，尝试通过steam_id查找
                existing_user = await CsgoUser.get_or_none(steam_id=steam_id)

            if existing_user:
                # 用户存在，更新信息
                user = existing_user
                if not user.steam_id:
                    user.steam_id = steam_id
                user.official_name = data.nick_name
                user.official_avatar_url = data.avatar
                user.friend_code = data.friend_code
                await user.save()
            else:
                # 用户不存在，创建新用户
                # 如果有user_id且需要保存，则关联；否则只保存steam_id
                if user_id and save_user_id:
                    user = await CsgoUser.create(
                        user_id=user_id,
                        steam_id=steam_id,
                        name=data.nick_name,
                        official_avatar_url=data.avatar,
                        friend_code=data.friend_code,
                    )
                else:
                    # 只保存steam_id
                    user = await CsgoUser.create(
                        steam_id=steam_id,
                        name=data.nick_name,
                        official_avatar_url=data.avatar,
                        friend_code=data.friend_code,
                    )

            # 查找或创建官方匹配统计数据
            stats, created = await CsgoOfficialStats.get_or_create(
                user=user, season_id="default"
            )

            # 更新统计数据
            stats.history_win_count = data.history_win_count
            stats.total_matches = data.cnt
            stats.kd_ratio = data.kd
            stats.win_rate = data.win_rate
            stats.rating = data.rating
            stats.total_kills = data.kills
            stats.total_deaths = data.deaths
            stats.total_assists = data.assists
            stats.rws = data.rws
            stats.adr = data.adr
            stats.kast = data.kast
            stats.ending_wins = data.ending_win
            stats.triple_kills = data.k3
            stats.quad_kills = data.k4
            stats.penta_kills = data.k5
            stats.vs3_wins = data.vs3
            stats.vs4_wins = data.vs4
            stats.vs5_wins = data.vs5
            stats.multi_kills = data.multi_kill
            stats.headshot_ratio = data.head_shot_ratio
            stats.entry_kill_ratio = data.entry_kill_ratio
            stats.awp_kill_ratio = data.awp_kill_ratio
            stats.flash_success_ratio = data.flash_success_ratio
            stats.entry_kill_avg = data.entry_kill_avg
            stats.game_hours = data.hours
            stats.auth_stats = data.auth_stats

            await stats.save()

            # 保存地图统计数据
            if data.hot_maps:
                for map_data in data.hot_maps:
                    map_stats, _ = await CsgoMapStats.get_or_create(
                        user=user,
                        map_name=map_data.map,
                        platform_type=2,
                        defaults={
                            "map_name_zh": map_data.map_name,
                            "map_image_url": map_data.map_image,
                            "map_logo_url": map_data.map_logo,
                            "season_id": "default",
                        },
                    )

                    map_stats.total_matches = map_data.total_match
                    map_stats.win_count = map_data.win_count
                    map_stats.total_kills = map_data.total_kill
                    map_stats.total_damage = int(map_data.total_adr)
                    map_stats.rating_sum = map_data.rating_sum
                    map_stats.rws_sum = map_data.rws_sum
                    map_stats.total_deaths = map_data.death_num
                    map_stats.first_kills = map_data.first_kill_num
                    map_stats.first_deaths = map_data.first_death_num
                    map_stats.headshot_kills = map_data.headshot_kill_num
                    map_stats.mvp_count = map_data.match_mvp_num
                    map_stats.triple_kills = map_data.three_kill_num
                    map_stats.quad_kills = map_data.four_kill_num
                    map_stats.penta_kills = map_data.five_kill_num
                    map_stats.vs3_wins = map_data.v3_num
                    map_stats.vs4_wins = map_data.v4_num
                    map_stats.vs5_wins = map_data.v5_num
                    map_stats.is_scuffle = map_data.scuffle

                    await map_stats.save()

            # 保存武器统计数据
            if data.hot_weapons:
                for weapon_data in data.hot_weapons:
                    weapon_stats, _ = await CsgoWeaponStats.get_or_create(
                        user=user,
                        weapon_code=weapon_data.weapon_name.lower(),
                        platform_type=2,
                        defaults={
                            "weapon_name": weapon_data.weapon_name,
                            "weapon_image_url": weapon_data.weapon_image,
                        },
                    )

                    weapon_stats.total_kills = weapon_data.weapon_kill
                    weapon_stats.headshot_kills = weapon_data.weapon_head_shot
                    weapon_stats.total_matches = weapon_data.total_match
                    weapon_stats.headshot_rate = (
                        weapon_data.weapon_head_shot / weapon_data.weapon_kill
                        if weapon_data.weapon_kill > 0
                        else 0
                    )

                    await weapon_stats.save()

            # 保存评分历史
            if (
                data.history_ratings
                and data.history_dates
                and (len(data.history_ratings) > 0 and len(data.history_dates) > 0)
            ):
                await CsgoRatingHistory.create(
                    user=user,
                    rating_type="normal",
                    rating_value=data.history_ratings[0],
                    season_id="default",
                    platform_type=2,
                )

            logger.info(
                f"成功保存玩家 {steam_id} 的官方数据",
                LOG_COMMAND,
                session=user_id,
            )

        except Exception as e:
            logger.error("保存玩家官方数据时发生错误", e=e)

    @classmethod
    async def watch_play(
        cls, bot: Bot, user_id: str, steam_id: str | None, group_id: str | None
    ) -> str:
        if not steam_id:
            steam_id = await cls.get_steam_id_by_user_id(user_id)
        if not steam_id:
            raise SteamIdNotBoundException()
        user, _ = await CsgoUser.get_or_create(steam_id=steam_id)
        async with AioWebSocket(PERFECT_WORLD_WWS) as aws:
            converse = aws.manipulator
            if not converse:
                return "连接数据失败..."
            message = (
                f'{{"messageType":10001,"messageData":{{"steam_id": "{steam_id}"}}}}'
            )
            await converse.send(message)
            while True:
                mes = await converse.receive()
                if not mes:
                    continue
                try:
                    string_mes = mes.decode("utf-8")
                    data: dict = json.loads(string_mes)
                    message_type = data.get("messageType")
                    # message_data = data.get("messageData")
                    if user.watch_type != message_type:
                        user.watch_type = int(message_type or 0)
                        await user.save(update_fields=["watch_type"])
                    if message_type == 10003:
                        if user.start_watch:
                            # 监控行为，不退出ws
                            await PlatformUtils.send_message(
                                bot, user_id, group_id, "没有正在进行的对局..."
                            )
                        else:
                            return "没有正在进行的对局..."
                    # if message_type == 10002:

                except Exception:
                    logger.error(
                        f"Steam ID: {steam_id} 监控解析消息失败: {mes}",
                        LOG_COMMAND,
                    )
