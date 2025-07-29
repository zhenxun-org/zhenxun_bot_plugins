from nonebot_plugin_uninfo import Uninfo

from zhenxun.services.log import logger

from .._data_source import CsgoManager
from ..config import CURRENT_SEASON, LOG_COMMAND
from ..models.csgo_user import CsgoUser


class BindManager:
    @classmethod
    async def bind_steam_id(cls, session: Uninfo, user_id: str, steam_id: str) -> str:
        """绑定用户ID和Steam ID

        参数:
            session: Uninfo
            user_id: 用户ID
            steam_id: Steam ID

        返回:
            bool: 绑定是否成功
        """
        try:
            # 首先检查该steam_id是否已经被其他用户绑定
            existing_user = await CsgoUser.get_or_none(steam_id=steam_id)
            if existing_user:
                if not existing_user.user_id:
                    existing_user.user_id = user_id
                    await existing_user.save(update_fields=["user_id"])
                    logger.info(
                        f"为用户 {user_id} 绑定Steam ID {steam_id}",
                        LOG_COMMAND,
                        session=user_id,
                    )
                    return "绑定Steam ID成功！"
                elif existing_user.user_id != user_id:
                    logger.warning(
                        f"Steam ID {steam_id} 已被用户 {existing_user.user_id} 绑定",
                        LOG_COMMAND,
                        session=user_id,
                    )
                    return (
                        f"Steam ID {steam_id} 已被其他用户 {existing_user.user_id} 绑定"
                    )

            await CsgoUser.create(user_id=user_id, steam_id=steam_id)
            refresh_result = []
            try:
                await CsgoManager.get_user_official_data(
                    session, user_id, steam_id, False
                )
                refresh_result.append("官匹数据刷新成功")
            except Exception:
                logger.warning(
                    f"获取用户 {user_id} 官匹数据失败",
                    LOG_COMMAND,
                    session=user_id,
                )
                refresh_result.append("官匹数据刷新失败")
            try:
                await CsgoManager.get_user_platform_data(
                    session, user_id, steam_id, CURRENT_SEASON
                )
                refresh_result.append("完美平台数据刷新成功")
            except Exception:
                logger.warning(
                    f"获取用户 {user_id} 平台数据失败",
                    LOG_COMMAND,
                    session=user_id,
                )
                refresh_result.append("完美平台数据刷新失败")

            logger.info(
                f"为用户 {user_id} 绑定Steam ID {steam_id}",
                LOG_COMMAND,
                session=user_id,
            )
            return "绑定Steam ID成功！\n" + "\n".join(refresh_result)

        except Exception as e:
            logger.error(
                "绑定Steam ID时发生错误",
                LOG_COMMAND,
                session=user_id,
                e=e,
            )
            return "绑定Steam ID失败..."

    @classmethod
    async def unbind_steam_id(cls, user_id: str) -> str:
        """解绑用户ID和Steam ID

        参数:
            user_id: 用户ID

        返回:
            str: 解绑结果信息
        """
        try:
            # 检查是否存在映射关系
            user = await CsgoUser.get_or_none(user_id=user_id)
            if not user:
                return "您尚未绑定Steam ID"

            # 记录当前的Steam ID用于日志
            old_steam_id = user.steam_id

            # 不删除用户记录，只清空steam_id
            user.steam_id = ""
            await user.save()

            logger.info(
                f"成功解绑用户 {user_id} 的Steam ID {old_steam_id}",
                LOG_COMMAND,
                session=user_id,
            )
            return f"成功解绑Steam ID {old_steam_id}"

        except Exception as e:
            logger.error(
                "解绑Steam ID时发生错误",
                LOG_COMMAND,
                session=user_id,
                e=e,
            )
            return "解绑Steam ID失败..."
