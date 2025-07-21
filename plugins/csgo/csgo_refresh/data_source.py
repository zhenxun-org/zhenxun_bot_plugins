from nonebot_plugin_uninfo import Uninfo

from zhenxun.services.log import logger

from .._data_source import CsgoManager
from ..config import CURRENT_SEASON, LOG_COMMAND
from ..models.csgo_user import CsgoUser


class CsgoRefreshManager:
    @classmethod
    async def refresh_data(cls, session: Uninfo, is_all: bool) -> str:
        """刷新数据

        参数:
            session: Uninfo
            is_all: 是否刷新所有数据
        """
        result = []
        if is_all:
            cnt = 0
            results = await CsgoUser.annotate().values_list("user_id", "steam_id")
            for user_id, steam_id in results:
                if user_id and steam_id:
                    try:
                        await CsgoManager.get_user_official_data(
                            session, user_id, steam_id, True
                        )
                        await CsgoManager.get_user_platform_data(
                            session, user_id, steam_id, CURRENT_SEASON, True
                        )
                        cnt += 1
                    except Exception as e:
                        logger.error(
                            f"CSGO刷新用户 {user_id} 数据失败",
                            LOG_COMMAND,
                            session=session,
                            e=e,
                        )
            result.append(f"刷新 {cnt} 条数据成功，{len(results) - cnt} 条数据刷新失败")
        else:
            user = await CsgoUser.get_or_none(user_id=session.user.id)
            if user and user.steam_id:
                try:
                    await CsgoManager.get_user_official_data(
                        session, None, user.steam_id, False
                    )
                    result.append("官匹数据刷新成功")
                except Exception as e:
                    logger.error(
                        f"CSGO刷新用户 {user.user_id} 官匹数据失败",
                        LOG_COMMAND,
                        session=session,
                        e=e,
                    )
                    result.append("官匹数据刷新失败")
                try:
                    await CsgoManager.get_user_platform_data(
                        session, None, user.steam_id, CURRENT_SEASON, False
                    )
                    result.append("完美平台数据刷新成功")
                except Exception as e:
                    logger.error(
                        f"CSGO刷新用户 {user.user_id} 数据失败",
                        LOG_COMMAND,
                        session=session,
                        e=e,
                    )
                    result.append("完美平台数据刷新失败")
            else:
                result.append("您尚未绑定Steam ID")
        return "\n".join(result)
