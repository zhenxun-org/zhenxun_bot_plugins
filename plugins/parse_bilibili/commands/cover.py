from typing import Optional

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import on_alconna, Alconna, AlconnaMatcher
from nonebot_plugin_alconna import UniMsg, Image

from zhenxun.services.log import logger

from ..services.network_service import ParserService, NetworkService
from ..utils.url_parser import extract_bilibili_url_from_event
from ..utils.exceptions import (
    BilibiliBaseException,
    UrlParseError,
    UnsupportedUrlError,
    ResourceNotFoundError,
)
from ..model import VideoInfo, SeasonInfo


async def get_reply_message(bot: Bot, event: Event) -> Optional[str]:
    """获取引用消息的内容"""
    try:
        if hasattr(event, "reply") and event.reply:
            reply_msg_id = event.reply.message_id
            logger.debug(f"检测到引用消息ID: {reply_msg_id}")

            if hasattr(bot, "get_msg"):
                try:
                    reply_msg = await bot.get_msg(message_id=reply_msg_id)
                    if reply_msg and "message" in reply_msg:
                        return str(reply_msg["message"])
                except Exception as e:
                    logger.debug(f"获取引用消息失败: {e}")

            if hasattr(event.reply, "message"):
                return str(event.reply.message)

        return None
    except Exception as e:
        logger.debug(f"获取引用消息时出错: {e}")
        return None


async def get_cover_url(content_info) -> Optional[str]:
    """从内容信息中获取封面URL"""
    if isinstance(content_info, VideoInfo):
        if hasattr(content_info, "pic") and content_info.pic:
            cover_url = content_info.pic
            if "@" in cover_url:
                cover_url = cover_url.split("@")[0]
            return cover_url
    elif isinstance(content_info, SeasonInfo):
        if hasattr(content_info, "cover") and content_info.cover:
            cover_url = content_info.cover
            if "@" in cover_url:
                cover_url = cover_url.split("@")[0]
            return cover_url

    return None


async def download_cover_image(cover_url: str) -> Optional[bytes]:
    """下载封面图片"""
    from ..utils.common import retry_async, RetryConfig

    async def _download_core():
        session = await NetworkService.get_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }

        async with session.get(cover_url, headers=headers) as response:
            if response.status == 200:
                image_data = await response.read()
                logger.debug(f"成功下载封面图片，大小: {len(image_data)} bytes")
                return image_data
            else:
                raise Exception(f"下载封面失败，状态码: {response.status}")

    config = RetryConfig.network_default()
    try:
        return await retry_async(_download_core, config=config)
    except Exception as e:
        logger.error(f"下载封面图片时出错: {e}")
        return None


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
    """处理bili封面命令"""
    logger.info("处理 bili封面 命令")

    bilibili_url = await extract_bilibili_url_from_event(bot, event)

    if not bilibili_url:
        await matcher.send("请引用包含B站链接的消息后使用此命令")
        return

    logger.info(f"从引用消息中提取到B站链接: {bilibili_url}")

    try:
        await matcher.send("正在获取封面，请稍候...")

        parsed_content = await ParserService.parse(bilibili_url)

        if not parsed_content:
            await matcher.send("无法解析该B站链接")
            return

        cover_url = await get_cover_url(parsed_content)

        if not cover_url:
            await matcher.send("该内容没有封面图片")
            return

        logger.info(f"获取到封面URL: {cover_url}")

        image_data = await download_cover_image(cover_url)

        if not image_data:
            await matcher.send("下载封面图片失败")
            return

        title = ""
        if isinstance(parsed_content, VideoInfo):
            title = f"视频《{parsed_content.title}》的封面"
        elif isinstance(parsed_content, SeasonInfo):
            title = f"番剧《{parsed_content.title}》的封面"
        else:
            title = "封面图片"

        cover_message = UniMsg(
            [Image(raw=image_data), f"\n{title}\n原始链接: {cover_url}"]
        )

        await cover_message.send()
        logger.info(f"成功发送封面: {title}")

    except (UrlParseError, UnsupportedUrlError) as e:
        logger.warning(f"URL解析失败: {bilibili_url}, 原因: {e}")
        await matcher.send(f"无法解析该B站链接: {str(e)}")

    except ResourceNotFoundError as e:
        logger.info(f"资源不存在: {bilibili_url}, 错误: {e}")
        await matcher.send("该B站内容不存在或已被删除")

    except BilibiliBaseException as e:
        logger.error(f"B站API错误: {e}")
        await matcher.send(f"获取B站内容失败: {str(e)}")

    except Exception as e:
        logger.error(f"处理bili封面命令时发生错误: {e}")
        await matcher.send("获取封面时发生错误，请稍后重试")
