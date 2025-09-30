from typing import Literal

from arclet.alconna import Alconna, Args, Arparma, CommandMeta
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import GROUP_ADMIN, GROUP_OWNER
from nonebot_plugin_alconna import AlconnaMatcher, on_alconna, AlconnaMatches
from nonebot_plugin_session import EventSession, SessionLevel
from zhenxun.services.log import logger

from ..services.network_service import ParserService
from ..services.utility_service import AutoDownloadManager
from ..services.download_service import DownloadTask, download_manager
from ..utils.exceptions import BilibiliBaseException
from ..utils.url_parser import extract_bilibili_url_from_event


bili_download_cmd = Alconna("bili下载", Args["link?", str])

bili_download_matcher = on_alconna(
    bili_download_cmd,
    block=True,
    priority=5,
    aliases={"b站下载"},
    skip_for_unmatch=False,
)


@bili_download_matcher.handle()
async def handle_bili_download(
    matcher: AlconnaMatcher, bot: Bot, event: Event, result: Arparma = AlconnaMatches()
):
    logger.info("处理 bili下载 命令")
    target_url = result.main_args.get("link") or await extract_bilibili_url_from_event(
        bot, event
    )

    if not target_url:
        await matcher.finish(
            "未找到有效的B站链接或ID，请检查输入或回复包含B站链接的消息。"
        )

    await matcher.send("正在解析链接...")

    try:
        parsed_content = await ParserService.parse(target_url)

        # 创建下载任务，不再包含 matcher
        task = DownloadTask(
            bot=bot,
            event=event,
            info_model=parsed_content,
            is_manual=True,
        )
        # 将 matcher 传递给 add_task 用于发送初始反馈
        await download_manager.add_task(task, matcher)

    except BilibiliBaseException as e:
        logger.error(f"下载任务创建失败 (已处理异常): {e}", e=e)
        await matcher.finish(f"任务创建失败: {e.message}")
    except Exception as e:
        logger.error(f"下载任务创建失败 (未处理异常): {e}", e=e)
        await matcher.finish("任务创建时发生意外错误，请检查日志。")


auto_download_cmd = Alconna(
    "bili自动下载",
    Args["action", Literal["on", "off"]],
    meta=CommandMeta(description="开启或关闭当前群聊的B站视频自动下载功能"),
)

auto_download_matcher = on_alconna(
    auto_download_cmd,
    aliases={"b站自动下载"},
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER,
    priority=10,
    block=True,
)


@auto_download_matcher.handle()
async def handle_auto_download_switch(
    matcher: AlconnaMatcher,
    session: EventSession,
    action: Literal["on", "off"],
):
    if session.level != SessionLevel.GROUP:
        await matcher.finish("此命令仅限群聊使用。")

    group_id = str(session.id2)
    if action == "on":
        success = await AutoDownloadManager.enable(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})开启B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})已开启自动下载，无需重复操作。")
    elif action == "off":
        success = await AutoDownloadManager.disable(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})关闭B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})未开启自动下载，无需重复操作。")
