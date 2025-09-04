from httpx import HTTPStatusError
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma, Match
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .._render import Renderer
from ..commands import _rank_matcher
from ..exceptions import CsgoDataQueryException
from .data_source import CsgoRankManager

__plugin_meta__ = PluginMetadata(
    name="群组完美排行",
    description="查看完美群组天梯排名",
    usage="""
    指令：
        完美天梯排行 ?[数量，默认10，最大50]
        完美rt排行 ?[数量，默认10，最大50]

        示例：
        完美天梯排行
        完美天梯排行 50
        完美rt排行
        完美rt排行 50
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1.1", menu_type="CSGO"
    ).to_dict(),
)


@_rank_matcher.handle()
async def _(
    bot: Bot, session: Uninfo, arparma: Arparma, type: Match[str], num: Match[int]
):
    group_id = session.group.id if session.group else None
    if not group_id:
        await MessageUtils.build_message("请在群内使用...").finish(reply_to=True)
    cnt = num.result if num.available else 10
    await MessageUtils.build_message("正在获取数据，请稍等...").send()
    try:
        member_list = await PlatformUtils.get_group_member_list(bot, group_id)
        user_id_list = [member.user_id for member in member_list]
        user_rank_data, user_index = await CsgoRankManager.get_group_user_rank(
            session.user.id, user_id_list, type.result, cnt
        )
        if not user_rank_data:
            await MessageUtils.build_message("没有找到任何数据...").send(reply_to=True)
            return

        image_bytes = await Renderer.render_rank_list(
            user_index, user_rank_data, type.result
        )
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error("群组排名调用出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error(
            f"群组 {group_id} 渲染排名失败",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)
