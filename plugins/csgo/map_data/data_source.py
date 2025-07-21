import asyncio

from nonebot_plugin_uninfo import Uninfo
from tortoise.transactions import atomic

from zhenxun.services.log import logger

from .._data_source import CallApi, CsgoManager
from ..config import LOG_COMMAND, HotMap, PerfectWorldMapRate
from ..exceptions import CsgoDataQueryException
from ..models.csgo_map_rate import CsgoMapRate
from ..models.csgo_user import CsgoUser


class CsgoMapDataManager:
    @classmethod
    async def get_user_platform_map_data(
        cls,
        session: Uninfo,
        target_id: str | None,
        steam_id: str | None,
        season: str,
        is_query: bool = False,
    ) -> list[HotMap] | str:
        """获取玩家平台地图数据

        参数:
            session: Uninfo
            target_id: 用户ID
            steam_id: Steam ID，如果为None则尝试从数据库查询
            season: 赛季，例如 S20
            is_query: 是否查询其他人

        返回:
            list[HotMap] | str: 玩家平台地图数据
        """
        result = await CsgoManager.get_user_platform_data(
            session, target_id, steam_id, season, is_query
        )
        return result if isinstance(result, str) else result.hot_maps

    @classmethod
    async def get_user_map_rate(
        cls,
        session: Uninfo,
        target_id: str | None,
        steam_id: str | None,
        season: str,
        is_query: bool = False,
    ) -> list[PerfectWorldMapRate] | str:
        """获取玩家地图胜率

        参数:
            session: Uninfo
            target_id: 用户ID
            steam_id: Steam ID，如果为None则尝试从数据库查询
            season: 赛季，例如 S20
            is_query: 是否查询其他人
        返回:
            list[PerfectWorldMapRate] | str: 玩家地图胜率
        """
        user_id = target_id or session.user.id
        if not user_id and not steam_id:
            logger.warning("用户ID和Steam ID不能同时为空", LOG_COMMAND, session=session)
            raise CsgoDataQueryException(
                "用户ID和Steam ID不能同时为空，请绑定或输入Steam ID"
            )
        if user_id and not steam_id:
            steam_id = await CsgoManager.get_steam_id_by_user_id(user_id)
        if not steam_id:
            raise CsgoDataQueryException("未找到Steam ID，请绑定或输入Steam ID")

        result = await CallApi.get_map_rate(steam_id, season)

        asyncio.create_task(  # noqa: RUF006
            cls._save_user_map_rate(user_id, steam_id, season, result.data, is_query)
        )
        return result.data

    @classmethod
    @atomic()
    async def _save_user_map_rate(
        cls,
        user_id: str | None,
        steam_id: str,
        season: str,
        map_datas: list[PerfectWorldMapRate],
        save_user_id: bool = True,
    ):
        """保存玩家地图胜率数据

        当user_id（这个是at用户时的user_id）为空时，使用session.user.id

        参数:
            session: Uninfo
            user_id: 用户ID
            steam_id: Steam ID
            season: 赛季
            map_datas: API返回的地图数据列表
            save_user_id: 是否保存user_id，当通过steam_id查询时应设为False
        """
        try:
            # 查找现有用户
            user = None
            if user_id and save_user_id:
                user = await CsgoUser.get_or_none(user_id=user_id)

            if not user:
                # 如果用户不存在，尝试通过steam_id查找
                user, _ = await CsgoUser.get_or_create(steam_id=steam_id)

            if save_user_id and user_id and user.user_id != user_id:
                user.user_id = user_id
                await user.save(update_fields=["user_id"])

            # 处理每个地图数据
            for map_data in map_datas:
                # 查找或创建地图胜率记录
                map_rate, _ = await CsgoMapRate.get_or_create(
                    user=user,
                    season_id=season,
                    map_name=map_data.map_name_en,
                    platform_type=1,  # 1表示完美世界平台
                    defaults={
                        "map_name_zh": map_data.map_name_zh,
                        "map_url": map_data.map_url,
                    },
                )

                # 更新地图胜率数据
                map_rate.match_count = map_data.match_cnt
                map_rate.win_count = map_data.win_cnt
                map_rate.win_rate = map_data.win_rate
                map_rate.t_win_rate = map_data.t_win_rate
                map_rate.ct_win_rate = map_data.ct_win_rate

                await map_rate.save()

            logger.info(
                f"保存玩家 {steam_id} 的地图胜率数据成功",
                LOG_COMMAND,
                session=user_id,
            )

        except Exception as e:
            logger.error(
                "保存玩家地图胜率数据时发生错误",
                LOG_COMMAND,
                session=user_id,
                e=e,
            )
