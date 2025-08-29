from httpx import HTTPStatusError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from ._data_source import CsgoManager
from ._render import Renderer
from ._utils import SteamId, TargetId
from .commands import _official_data_matcher
from .exceptions import (
    CsgoDataQueryException,
    SteamIdNotBoundException,
)

__plugin_meta__ = PluginMetadata(
    name="官匹数据查询",
    description="查看官匹数据",
    usage="""
    指令：
        官匹数据 @/steamId
        示例：
        官匹数据
        官匹数据 @笨蛋
        官匹数据 1231231233
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1.1", menu_type="CSGO").to_dict(),
)


@_official_data_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    target_id: str | None = TargetId(),
    steam_id: str | None = SteamId(),
):
    await MessageUtils.build_message("正在获取数据，请稍等...").send()
    user_id = session.user.id
    is_query = bool(steam_id or steam_id)

    player_info = None
    try:
        if steam_id:
            player_info = await CsgoManager.get_user_official_data(
                session, target_id, steam_id, is_query
            )
        else:
            # 否则使用user_id查询
            queried_steam_id = await CsgoManager.get_steam_id_by_user_id(
                target_id or user_id
            )
            player_info = await CsgoManager.get_user_official_data(
                session, target_id, queried_steam_id, is_query
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
                    player_info.nick_name = user_info.user_name
        elif not steam_id:
            player_info.nick_name = session.user.name or "未知用户"
            if session.user.avatar:
                player_info.avatar = session.user.avatar

        image_bytes = await Renderer.render_official_user(
            player_info=player_info,
        )

        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except SteamIdNotBoundException:
        await MessageUtils.build_message("请先绑定Steam ID").finish(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error(
            "官匹用户数据调用出错...", arparma.header_result, session=session, e=e
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
