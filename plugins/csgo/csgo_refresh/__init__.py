from httpx import HTTPStatusError
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import AlconnaQuery, Arparma, Query
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from ..commands import _refresh_matcher
from ..exceptions import CsgoDataQueryException
from .data_source import CsgoRefreshManager

__plugin_meta__ = PluginMetadata(
    name="CSGO刷新数据",
    description="刷新官匹与完美数据",
    usage="""
    指令：
        csgo刷新数据
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1.1", menu_type="CSGO").to_dict(),
)


@_refresh_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    is_all: Query[bool] = AlconnaQuery("all", False),
):
    if is_all.result and session.user.id not in bot.config.superusers:
        await MessageUtils.build_message("权限不足...").finish(reply_to=True)
    await MessageUtils.build_message("正在获取数据，请稍等...").send()
    try:
        result = await CsgoRefreshManager.refresh_data(session, is_all.result)
        await MessageUtils.build_message(result).send(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except HTTPStatusError as e:
        logger.error("群组排名调用出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"获取数据请求失败！ code: {e.response.status_code}"
        ).finish()
    except Exception as e:
        logger.error(
            "CSGO刷新数据失败",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("其他未知错误，请稍后再试").send(reply_to=True)
