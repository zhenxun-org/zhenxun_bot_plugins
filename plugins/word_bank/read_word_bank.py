from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Arparma,
    Match,
    Option,
    Query,
    on_alconna,
    store_true,
)
from nonebot_plugin_session import EventSession

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from ._config import ScopeType
from ._data_source import WordBankManage
from ._model import WordBank

__plugin_meta__ = PluginMetadata(
    name="查看词条",
    description="查看当前定义的词条",
    usage=r"""
    usage：
        查看词条:
            (在群组中使用时): 查看当前群组词条和全局词条
            (在私聊中使用时): 查看当前私聊词条和全局词条
        查看词条 谁是萝莉   : 查看词条 谁是萝莉 的全部回答
        查看词条 --id 2    : 查看词条序号为2的全部回答
        查看词条 谁是萝莉 --all: 查看全局词条 谁是萝莉 的全部回答
        查看词条 --id 2 --all: 查看全局词条序号为2的全部回答
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
    ).dict(),
)

_show_matcher = on_alconna(
    Alconna(
        "显示词条",
        Args["problem?", str],
        Option("-g|--group", Args["gid", str], help_text="群组id"),
        Option("--id", Args["index", int], help_text="词条id"),
        Option("--all", action=store_true, help_text="全局词条"),
    ),
    aliases={"查看词条"},
    priority=5,
    block=True,
)


@_show_matcher.handle()
async def _(
    session: EventSession,
    problem: Match[str],
    index: Match[int],
    gid: Match[str],
    arparma: Arparma,
    all: Query[bool] = AlconnaQuery("all.value", False),
):
    word_scope = ScopeType.GROUP if session.id3 or session.id2 else ScopeType.PRIVATE
    group_id = session.id3 or session.id2
    if all.result:
        word_scope = ScopeType.GLOBAL
    if gid.available:
        group_id = gid.result
    if problem.available:
        if index.available and (
            index.result < 0
            or index.result > len(await WordBank.get_problem_by_scope(word_scope))
        ):
            await MessageUtils.build_message("id必须在范围内...").finish(reply_to=True)
        result = await WordBankManage.show_word(
            problem.result,
            index.result if index.available else None,
            group_id,
            word_scope,
        )
    else:
        result = await WordBankManage.show_word(
            None, index.result if index.available else None, group_id, word_scope
        )
    await result.send()
    logger.info(
        f"查看词条回答: {problem.result if problem.available else index.result}",
        arparma.header_result,
        session=session,
    )
