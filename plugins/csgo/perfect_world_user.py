from httpx import HTTPStatusError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from ._data_source import CsgoManager
from ._render import Renderer
from ._utils import CheckSeason, SeasonId, SteamId, TargetId
from .commands import _user_data_matcher
from .config import DEFAULT_AVATAR_URL
from .exceptions import (
    CsgoDataQueryException,
    SteamIdNotBoundException,
)

__plugin_meta__ = PluginMetadata(
    name="完美数据查询",
    description="查看完美世界平台用户数据",
    usage="""
    指令：
        完美数据 @/steamId ?[赛季]
        示例：
        完美数据
        完美数据 S19（注：这个是赛季）
        完美数据 @笨蛋
        完美数据 @笨蛋 S20
        完美数据 1231231233
        完美数据 1231231233 S20
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1.1", menu_type="CSGO").to_dict(),
)


@_user_data_matcher.handle(parameterless=[CheckSeason()])
async def _(
    session: Uninfo,
    arparma: Arparma,
    target_id: str | None = TargetId(),
    steam_id: str | None = SteamId(),
    season_id: str = SeasonId(),
):
    await MessageUtils.build_message("正在获取数据，请稍等...").send()
    user_id = session.user.id
    is_query = bool(steam_id or steam_id)

    player_info = None
    avatar_url = session.user.avatar
    try:
        if steam_id:
            player_info = await CsgoManager.get_user_platform_data(
                session, target_id, steam_id, season_id, is_query
            )
        else:
            # 否则使用user_id查询
            queried_steam_id = await CsgoManager.get_steam_id_by_user_id(
                target_id or user_id
            )
            player_info = await CsgoManager.get_user_platform_data(
                session, target_id, queried_steam_id, season_id, is_query
            )

        if isinstance(player_info, str):
            await MessageUtils.build_message(player_info).send(reply_to=True)
            return

        if not player_info:
            await MessageUtils.build_message("查询失败，请稍后再试").send(reply_to=True)
            return

        if target_id:
            # 替换名称
            if session.group:
                user_info = await GroupInfoUser.get_or_none(
                    user_id=target_id, group_id=session.group.id
                )
                if user_info:
                    player_info.name = user_info.user_name
                avatar_url = (
                    PlatformUtils.get_user_avatar_url(
                        target_id, PlatformUtils.get_platform(session), session.self_id
                    )
                    if target_id
                    else DEFAULT_AVATAR_URL
                )
            else:
                avatar_url = player_info.avatar
        elif steam_id:
            avatar_url = player_info.avatar
        else:
            player_info.name = session.user.name or player_info.name

        image_bytes = await Renderer.render_perfect_world_user(
            player_info=player_info,
            avatar_url=avatar_url or DEFAULT_AVATAR_URL,
            season=season_id,
        )

        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except SteamIdNotBoundException:
        await MessageUtils.build_message("请先绑定Steam ID").finish(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error(
            "完美用户数据调用出错...", arparma.header_result, session=session, e=e
        )
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error(
            f"Steam ID: {steam_id} 渲染用户数据图片失败",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)
