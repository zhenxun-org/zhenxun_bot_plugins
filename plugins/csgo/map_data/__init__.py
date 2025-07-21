from httpx import HTTPStatusError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .._data_source import CsgoManager
from .._render import Renderer
from .._utils import CheckSeason, SeasonId, SteamId, TargetId
from ..commands import _map_rate_matcher
from ..config import DEFAULT_AVATAR_URL
from ..exceptions import CsgoDataQueryException, SteamIdNotBoundException
from ..models.csgo_user import CsgoUser
from .data_source import CsgoMapDataManager

__plugin_meta__ = PluginMetadata(
    name="完美地图数据",
    description="查看完美世界和官方匹配的地图胜率",
    usage="""
    指令：
        完美地图数据 @/steamId ?[赛季]
        示例：
        完美地图数据
        完美地图数据 S19（注：这个是赛季）
        完美地图数据 @笨蛋
        完美地图数据 @笨蛋 S20
        完美地图数据 1231231233
        完美地图数据 1231231233 S20
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1", menu_type="CSGO").to_dict(),
)


@_map_rate_matcher.handle(parameterless=[CheckSeason()])
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

    try:
        # 获取地图胜率数据
        map_rate_data = await CsgoMapDataManager.get_user_map_rate(
            session, target_id, steam_id, season_id, is_query
        )

        if isinstance(map_rate_data, str):
            await MessageUtils.build_message(map_rate_data).send(reply_to=True)
            return

        # 获取地图数据
        map_data = await CsgoMapDataManager.get_user_platform_map_data(
            session, target_id, steam_id, season_id, is_query
        )

        logger.info("获取的地图胜率数据", arparma.header_result, session=session)

        if isinstance(map_data, str):
            await MessageUtils.build_message(map_data).send(reply_to=True)
            return

        player_name = session.user.name
        avatar_url = session.user.avatar

        if target_id:
            if session.group:
                user_info = await GroupInfoUser.get_or_none(
                    user_id=target_id, group_id=session.group.id
                )
            else:
                user_info = await GroupInfoUser.get_or_none(user_id=target_id)
            player_name = user_info.user_name if user_info else ""
            avatar_url = (
                PlatformUtils.get_user_avatar_url(
                    target_id, PlatformUtils.get_platform(session), session.self_id
                )
                if target_id
                else DEFAULT_AVATAR_URL
            )
        elif steam_id:
            user = await CsgoUser.get_or_none(steam_id=steam_id)
            player_name = user.perfect_name if user else "未知玩家"
            avatar_url = user.perfect_avatar_url if user else DEFAULT_AVATAR_URL

        actual_steam_id = steam_id or (
            "未知"
            if isinstance(map_data, str)
            else await CsgoManager.get_steam_id_by_user_id(user_id)
        )

        image_bytes = await Renderer.render_map_data(
            map_data=map_data,
            map_rate_data=map_rate_data,
            player_name=player_name or "未知玩家",
            steam_id=actual_steam_id,
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
            "完美用户地图胜率调用出错...", arparma.header_result, session=session, e=e
        )
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error(
            f"Steam ID: {steam_id} 渲染地图胜率图片失败",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)
