from asyncio.exceptions import TimeoutError

from httpx import NetworkError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Match,
    Option,
    Query,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.utils import BaseBlock, Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import is_valid_date

from .data_source import download_pixiv_imgs, get_pixiv_urls, search_pixiv_urls

__plugin_meta__ = PluginMetadata(
    name="P站排行/搜图",
    description="P站排行榜直接冲，P站搜图跟着冲",
    usage="""
    P站排行：
        可选参数:
        类型：
            1. 日排行
            2. 周排行
            3. 月排行
            4. 原创排行
            5. 新人排行
            6. R18日排行
            7. R18周排行
            8. R18受男性欢迎排行
            9. R18重口排行【慎重！】
        【使用时选择参数序号即可，R18仅可私聊】
        p站排行 ?[参数] ?[数量] ?[日期]
        示例：
            p站排行   [无参数默认为日榜]
            p站排行 1
            p站排行 1 5
            p站排行 1 5 2018-4-25
        【注意空格！！】【在线搜索会较慢】
    ---------------------------------
    P站搜图：
        搜图 [关键词] ?[数量] ?[页数=1] ?[r18](不屏蔽R-18)
        示例：
            搜图 樱岛麻衣
            搜图 樱岛麻衣 5
            搜图 樱岛麻衣 5 r18
            搜图 樱岛麻衣#1000users 5
        【多个关键词用#分割】
        【默认为 热度排序】
        【注意空格！！】【在线搜索会较慢】【数量可能不符？可能该页数量不够，也可能被R-18屏蔽】
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-89d294e",
        aliases={"P站排行", "搜图"},
        menu_type="来点好康的",
        commands=[
            Command(command="p站排行 ?[参数] ?[数量] ?[日期]"),
            Command(command="搜图 [关键词] ?[数量] ?[页数=1] ?[r18]"),
        ],
        limits=[BaseBlock(result="P站排行榜或搜图正在搜索，请不要重复触发命令...")],
        configs=[
            RegisterConfig(
                key="TIMEOUT",
                value=10,
                help="图片下载超时限制",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                key="MAX_PAGE_LIMIT",
                value=20,
                help="作品最大页数限制，超过的作品会被略过",
                default_value=20,
                type=int,
            ),
            RegisterConfig(
                key="ALLOW_GROUP_R18",
                value=False,
                help="图允许群聊中使用 r18 参数",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="hibiapi",
                key="HIBIAPI",
                value="https://api.obfs.dev",
                help="如果没有自建或其他hibiapi请不要修改",
                default_value="https://api.obfs.dev",
            ),
            RegisterConfig(
                module="pixiv",
                key="PIXIV_NGINX_URL",
                value="pixiv.re",
                help="Pixiv反向代理",
            ),
        ],
    ).to_dict(),
)


rank_dict = {
    "1": "day",
    "2": "week",
    "3": "month",
    "4": "week_original",
    "5": "week_rookie",
    "6": "day_r18",
    "7": "week_r18",
    "8": "day_male_r18",
    "9": "week_r18g",
}

_rank_matcher = on_alconna(
    Alconna("p站排行", Args["rank_type?", int]["num?", int]["datetime?", str]),
    aliases={"p站排行榜"},
    priority=5,
    block=True,
)

_keyword_matcher = on_alconna(
    Alconna(
        "搜图",
        Args["keyword", str]["num?", int, 10]["page?", int, 1],
        Option("-r", action=store_true, help_text="是否屏蔽r18"),
    ),
    priority=5,
    block=True,
)


@_rank_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    datetime: Match[str],
    rank_type: Query[int] = Query("rank_type", 1),
    num: Query[int] = Query("rank_type", 10),
):
    code = 0
    info_list = []
    _datetime = None
    if datetime.available:
        _datetime = datetime.result
        if not is_valid_date(_datetime):
            await MessageUtils.build_message("日期不合法，示例: 2018-4-25").finish(
                reply_to=True
            )
    if session.group and rank_type.result in [6, 7, 8, 9]:
        await MessageUtils.build_message("羞羞脸！私聊里自己看！").finish(
            at_sender=True
        )
    info_list, code = await get_pixiv_urls(
        rank_dict[str(rank_type.result)], num.result, date=_datetime
    )
    if code != 200 and info_list and isinstance(info_list[0], str):
        await MessageUtils.build_message(info_list[0]).finish()
    if not info_list:
        await MessageUtils.build_message("没有找到啊，等等再试试吧~V").send(
            at_sender=True
        )
    await MessageUtils.build_message("正在搜集图片，请稍后哦...").send()
    message_list = []
    for title, author, urls in info_list:
        try:
            images = await download_pixiv_imgs(urls, session.user.id)  # type: ignore
            message_list.append(
                [f"title: {title}\nauthor: {author}\n", *images]  # type: ignore
            )

        except (NetworkError, TimeoutError):
            message_list.append("这张图网络直接炸掉了！")
    platform = PlatformUtils.get_platform(session)
    if session.group and platform == "qq":
        await MessageUtils.alc_forward_msg(
            message_list, session.self_id, BotConfig.self_nickname
        ).send()
    else:
        for msg in message_list:
            await MessageUtils.build_message(msg).send()
    logger.info(
        f" 查看了P站排行榜 rank_type:{rank_type.result}",
        arparma.header_result,
        session=session,
    )


@_keyword_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    keyword: str,
    num: Query[int] = Query("num", 10),
    page: Query[int] = Query("page", 1),
):
    if (
        session.group
        and arparma.find("r")
        and not Config.get_config("pixiv_rank_search", "ALLOW_GROUP_R18")
    ):
        await MessageUtils.build_message("(脸红#) 你不会害羞的 八嘎！").finish(
            at_sender=True
        )
    r18 = 0 if arparma.find("r") else 1
    info_list = None
    keyword = keyword.replace("#", " ")
    info_list, code = await search_pixiv_urls(keyword, num.result, page.result, r18)
    if code != 200 and isinstance(info_list[0], str):
        await MessageUtils.build_message(info_list[0]).finish()
    if not info_list:
        await MessageUtils.build_message("没有找到啊，等等再试试吧~V").finish(
            at_sender=True
        )
    await MessageUtils.build_message("正在搜集图片，请稍后哦...").send()
    message_list = []
    for title, author, urls in info_list:
        try:
            images = await download_pixiv_imgs(urls, session.user.id)  # type: ignore
            message_list.append([f"title: {title}\nauthor: {author}\n", *images])

        except (NetworkError, TimeoutError):
            message_list.append(["这张图网络直接炸掉了！"])
    platform = PlatformUtils.get_platform(session)
    if session.group and platform == "qq":
        await MessageUtils.alc_forward_msg(
            message_list, session.self_id, BotConfig.self_nickname
        ).send()
    else:
        for msg in message_list:
            await MessageUtils.build_message(msg).send()
    logger.info(
        f" 查看了搜索 {keyword} R18：{r18}", arparma.header_result, session=session
    )
