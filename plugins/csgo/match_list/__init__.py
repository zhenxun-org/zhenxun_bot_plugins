from httpx import HTTPStatusError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Match
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .._data_source import CsgoManager
from .._render import Renderer
from .._utils import SteamId, TargetId
from ..commands import _match_detail_matcher, _match_list_matcher
from ..exceptions import CsgoDataQueryException, SteamIdNotBoundException
from .data_source import MatchListManager

__plugin_meta__ = PluginMetadata(
    name="完美战绩查询",
    description="查看完美战绩",
    usage="""
    指令：
        完美战绩 @/steamId
        完美战绩 @/steamId -p 1（页码）
        
        完美战绩详情 比赛id
        
        示例：
            完美战绩 @笨蛋
            完美战绩 @笨蛋 -p 2
            完美战绩详情 1234
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1", menu_type="CSGO").to_dict(),
)


@_match_list_matcher.handle()
async def handle_match_list(
    session: Uninfo,
    page: Match[int],
    target_id: str | None = TargetId(),
    steam_id: str | None = SteamId(),
):
    """处理完美战绩查询命令"""
    await MessageUtils.build_message("正在获取战绩数据，请稍等...").send()
    try:
        avatar_url = None
        name = "未知用户"
        if not steam_id:
            if not target_id:
                avatar_url = PlatformUtils.get_user_avatar_url(
                    session.user.id, PlatformUtils.get_platform(session)
                )
                name = session.user.name or "未知用户"
                steam_id = await CsgoManager.get_steam_id_by_user_id(session.user.id)
            else:
                if session.group:
                    if user_info := await GroupInfoUser.get_or_none(
                        user_id=target_id, group_id=session.group.id
                    ):
                        avatar_url = PlatformUtils.get_user_avatar_url(
                            user_info.user_id, PlatformUtils.get_platform(session)
                        )
                        name = user_info.user_name
                steam_id = await CsgoManager.get_steam_id_by_user_id(target_id)
        if not steam_id:
            await MessageUtils.build_message("用户未绑定Steam ID").send(reply_to=True)
            return
        page_value = page.result if page.available else 1
        # 渲染比赛列表
        image_bytes = await MatchListManager.render_user_match_list(
            steam_id, page_value, avatar_url, name
        )
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except SteamIdNotBoundException:
        await MessageUtils.build_message(
            "该用户未绑定Steam ID，请先使用【绑定steamid】命令进行绑定"
        ).finish(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error("完美战绩查询请求失败", session=session, e=e)
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error("完美战绩查询失败", session=session, e=e)
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)


@_match_detail_matcher.handle()
async def handle_match_detail(
    session: Uninfo,
    match_id: str,
):
    await MessageUtils.build_message("正在获取战绩数据，请稍等...").send()
    try:
        match_detail = await MatchListManager.get_match_detail(match_id)
        image_bytes = await Renderer.render_match_detail(match_detail)
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error("完美战绩查询详情请求失败", session=session, e=e)
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error("完美战绩查询详情失败", session=session, e=e)
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)
