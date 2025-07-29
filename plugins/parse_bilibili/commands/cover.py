from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import on_alconna, Alconna, AlconnaMatcher
from zhenxun.services.log import logger

from ..services.cover_service import CoverService
from ..utils.url_parser import extract_bilibili_url_from_event
from ..utils.exceptions import BilibiliBaseException


bili_cover_cmd = Alconna("bili封面")

bili_cover_matcher = on_alconna(
    bili_cover_cmd,
    block=True,
    priority=5,
    aliases={"b站封面"},
    skip_for_unmatch=False,
)


@bili_cover_matcher.handle()
async def handle_bili_cover(matcher: AlconnaMatcher, bot: Bot, event: Event):
    logger.info("处理 bili封面 命令")

    bilibili_url = await extract_bilibili_url_from_event(bot, event)

    if not bilibili_url:
        await matcher.finish("请引用包含B站链接的消息后使用此命令。")

    await matcher.send("正在获取封面，请稍候...")

    try:
        cover_message = await CoverService.get_cover_message(bilibili_url)
        await cover_message.send()
        logger.info(f"成功发送封面 for {bilibili_url}")
    except BilibiliBaseException as e:
        logger.warning(f"获取封面失败 for {bilibili_url}: {e.message}")
        await matcher.send(f"获取封面失败: {e.message}")
    except Exception as e:
        logger.error(f"处理bili封面命令时发生错误: {e}", e=e)
        await matcher.send("获取封面时发生错误，请稍后重试。")
