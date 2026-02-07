import base64
from pathlib import Path
import re
import time
from typing import Optional
from io import BytesIO
from .common import format_number, format_duration

import aiofiles

from bs4 import BeautifulSoup
import jinja2
from nonebot_plugin_alconna import UniMsg, UniMessage, Text, Image

from zhenxun import ui
from zhenxun.ui.models import MarkdownData
from zhenxun.utils.http_utils import AsyncHttpx

from bilibili_api import comment
from bilibili_api.comment import CommentResourceType, OrderType

from zhenxun.services.log import logger

from ..model import ArticleInfo, LiveInfo, VideoInfo, SeasonInfo, UserInfo
import asyncio
from nonebot.adapters.onebot.v11 import MessageSegment as V11MessageSegment
from zhenxun.utils.decorator.retry import Retry
from ..config import (
    SEND_VIDEO_MAX_RETRIES,
    SEND_VIDEO_RETRY_DELAY,  # type: ignore
    SEND_VIDEO_TIMEOUT,
    IMAGE_CACHE_DIR,
    base_config,
    bili_credential,
)
from ..utils.exceptions import DownloadError


TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
FONT_FILE = TEMPLATE_DIR / "vanfont.ttf"
FONT_BASE64_CONTENT = ""
try:
    if FONT_FILE.exists():
        with open(FONT_FILE, "rb") as f:
            font_bytes = f.read()
        FONT_BASE64_CONTENT = base64.b64encode(font_bytes).decode()
        logger.debug("成功加载并编码 vanfont.ttf")
    else:
        logger.error(f"图标字体文件未找到: {FONT_FILE}")
except Exception as e:
    logger.error(f"加载或编码 vanfont.ttf 时出错: {e}")
template_loader = jinja2.FileSystemLoader(str(TEMPLATE_DIR))
template_env = jinja2.Environment(loader=template_loader, enable_async=True)


class ImageHelper:
    """图片处理辅助类"""

    @staticmethod
    async def download_image(url: str, save_path: Path) -> bool:
        """下载图片"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.bilibili.com",
            }
            return await AsyncHttpx.download_file(
                url=url, path=save_path, headers=headers, timeout=30
            )
        except Exception as e:
            logger.error(f"下载图片时出错 {url}: {e}")
            return False

    @staticmethod
    async def get_image_as_base64(path: Path) -> Optional[str]:
        """转换图片为Base64"""
        if not (path.exists() and path.stat().st_size > 0):
            return None

        try:
            async with aiofiles.open(path, "rb") as f:
                img_bytes = await f.read()
            img_base64 = base64.b64encode(img_bytes).decode()
            img_format = path.suffix.lstrip(".") or "jpeg"
            return f"data:image/{img_format};base64,{img_base64}"
        except Exception as e:
            logger.error(f"读取或编码图片失败: {path}", e=e)
            return None


class MessageBuilder:
    """消息构建器"""

    @staticmethod
    async def build_video_message(info: VideoInfo) -> UniMsg:
        """构建视频信息消息"""
        segments = []

        if base_config.get("SEND_VIDEO_PIC", True) and info.pic:
            file_name = f"bili_video_cover_{info.bvid or info.aid}.jpg"
            cover_path = IMAGE_CACHE_DIR / file_name
            if await ImageHelper.download_image(info.pic, cover_path):
                segments.append(Image(path=cover_path))

        pub_date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(info.pubdate))

        stat_parts = [
            f"播放: {info.stat.view}",
            f"弹幕: {info.stat.danmaku}",
            f"评论: {info.stat.reply}",
            f"点赞: {info.stat.like}",
            f"投币: {info.stat.coin}",
            f"收藏: {info.stat.favorite}",
        ]
        stat_str = "，".join(stat_parts)

        text_content = (
            f"{info.title}\n"
            f"UP: {info.owner.name}\n"
            f"发布于: {pub_date_str}\n"
            f"AV: {info.aid} | BV: {info.bvid}\n"
            f"数据: {stat_str}\n"
            f"链接: {info.parsed_url}"
        )
        segments.append(Text(text_content))

        return UniMessage(segments)

    @staticmethod
    def _clean_html_description(html_description: str) -> str:
        """清理HTML描述为纯文本"""
        soup = BeautifulSoup(html_description or "", "html.parser")
        return soup.get_text(separator=" ", strip=True)

    @staticmethod
    async def build_live_message(info: LiveInfo) -> UniMsg:
        """构建直播间信息消息"""
        segments = []
        status_text = {0: "未开播", 1: "直播中", 2: "轮播中"}

        if base_config.get("SEND_LIVE_PIC", True) and info.cover:
            file_name = f"bili_live_cover_{info.room_id}.jpg"
            cover_path = IMAGE_CACHE_DIR / file_name
            if await ImageHelper.download_image(info.cover, cover_path):
                segments.append(Image(path=cover_path))  # type: ignore

        start_time_str = ""
        if info.live_status == 1 and info.live_start_time:
            start_time_str = f"开播时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(info.live_start_time))}\n"

        plain_description = MessageBuilder._clean_html_description(
            info.description or ""
        )
        if len(plain_description) > 80:
            plain_description = plain_description[:80] + "..."

        text_content = (
            f"{info.title} ({status_text.get(info.live_status, '未知状态')})\n"
            f"主播: {info.uname or f'UID {info.uid}'}\n"
            f"分区: {info.parent_area_name} / {info.area_name}\n"
            f"{start_time_str}"
            f"简介: {plain_description}\n"
            f"直播间: {info.room_url or info.parsed_url}"
        )
        segments.append(Text(text_content))

        if (
            base_config.get("SEND_LIVE_PIC", True)
            and info.live_status == 1
            and info.keyframe_url
        ):
            segments.append(Text("\n直播画面:"))

            keyframe_name = f"bili_live_keyframe_{info.room_id}.jpg"
            keyframe_path = IMAGE_CACHE_DIR / keyframe_name
            if await ImageHelper.download_image(info.keyframe_url, keyframe_path):
                segments.append(Image(path=keyframe_path))

        return UniMessage(segments)

    @staticmethod
    async def build_article_message(
        info: ArticleInfo, render_enabled: bool = False
    ) -> Optional[UniMsg]:
        """构建文章/动态信息消息"""
        logger.debug(
            f"构建文章/动态消息: {info.type} {info.id}, 渲染模式: {render_enabled}"
        )

        if render_enabled:
            if info.screenshot_bytes:
                logger.debug("渲染模式：使用内存截图")
                return UniMessage(Image(raw=info.screenshot_bytes))
            elif info.screenshot_path:
                path = Path(info.screenshot_path)
                if path.exists():
                    logger.debug(f"渲染模式：使用本地截图: {path}")
                    return UniMessage(Image(path=path))
                else:
                    logger.error(f"渲染模式：截图路径不存在: {info.screenshot_path}")
            logger.warning("渲染模式：无可用截图，将回退发送文本信息")

        segments = []
        has_content = False

        if info.title:
            segments.append(Text(f"【专栏】{info.title}\n"))
            has_content = True
        if info.author:
            segments.append(Text(f"作者: {info.author}\n"))
            has_content = True

        if info.markdown_content:
            plain_content = re.sub(r"[#*`~_>]", "", info.markdown_content)
            plain_content = re.sub(r"!\[.*?\]\(.*?\)", "[图片]", plain_content)
            plain_content = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", plain_content)
            plain_content = re.sub(r"\n\s*\n", "\n", plain_content).strip()

            max_summary_len = 150
            summary = plain_content[:max_summary_len]
            if len(plain_content) > max_summary_len:
                summary += "..."
            segments.append(Text(f"摘要: {summary}\n"))
            has_content = True

        if info.url:
            segments.append(Text(f"链接: {info.url}"))
            has_content = True

        if has_content:
            return UniMessage(segments)
        else:
            logger.warning(f"文章/动态信息不足，无法构建消息: {info.type} {info.id}")
            return None

    @staticmethod
    async def build_season_message(info: SeasonInfo) -> UniMsg:
        """构建番剧/影视信息消息"""
        segments = []

        send_cover_enabled = True
        if send_cover_enabled and info.cover:
            file_name = f"bili_season_cover_{info.season_id or info.media_id}.jpg"
            cover_path = IMAGE_CACHE_DIR / file_name
            if await ImageHelper.download_image(info.cover, cover_path):
                segments.append(Image(path=cover_path))

        status_text = {
            2: "未开播",
            4: "会员抢先",
            13: "已完结",
        }.get(info.status, f"状态未知({info.status})")

        rating_str = (
            f"{info.rating_score}分 ({info.rating_count}人评分)"
            if info.rating_score > 0
            else "暂无评分"
        )

        pub_info = ""
        if info.publish:
            pub_date = info.publish.get("pub_time", "") or info.publish.get(
                "release_date", ""
            )
            weekday = (
                f" 周{info.publish.get('weekday', '')}"
                if info.publish.get("weekday")
                else ""
            )
            pub_info = f"发行时间: {pub_date}{weekday}\n"

        stat_parts = [
            f"播放: {format_number(info.stat.views)}",
            f"弹幕: {format_number(info.stat.danmakus)}",
            f"追番/系列: {format_number(info.stat.favorites)}",
            f"评论: {format_number(info.stat.reply)}",
            f"点赞: {format_number(info.stat.likes)}",
            f"投币: {format_number(info.stat.coins)}",
            f"分享: {format_number(info.stat.share)}",
        ]
        stat_str = "，".join(stat_parts)

        text_content = (
            f"{info.title} ({info.type_name})\n"
            f"状态: {status_text} (共{info.total_ep}话)\n"
            f"地区: {info.areas or '未知'} | 风格: {info.styles or '未知'}\n"
            f"评分: {rating_str}\n"
            f"{pub_info}"
            f"数据: {stat_str}\n"
            f"链接: {info.parsed_url}"
        )
        segments.append(Text(text_content))

        return UniMessage(segments)

    @staticmethod
    async def build_user_message(info: UserInfo) -> UniMsg:
        """构建用户信息消息"""
        segments = []

        if info.face:
            avatar_filename = f"bili_avatar_{info.mid}.jpg"
            avatar_path = IMAGE_CACHE_DIR / avatar_filename
            if await ImageHelper.download_image(info.face, avatar_path):
                segments.append(Image(path=avatar_path))

        live_status_text = " (直播中)" if info.live_room_status == 1 else ""
        birthday_str = f"生日: {info.birthday} | " if info.birthday else ""

        stat_parts = [
            f"关注: {format_number(info.stat.following)}",
            f"粉丝: {format_number(info.stat.follower)}",
            f"获赞: {format_number(info.stat.likes)}",
            f"播放: {format_number(info.stat.archive_view)}",
            f"阅读: {format_number(info.stat.article_view)}",
        ]
        stat_str = " | ".join(stat_parts)

        live_room_part = f"\n直播间: {info.live_room_url}" if info.live_room_url else ""
        text_content = (
            f"{info.name}{live_status_text} (Lv.{info.level})\n"
            f"{birthday_str}性别: {info.sex}\n"
            f"签名: {info.sign or '这个人很神秘，什么都没有写'}\n"
            f"统计: {stat_str}\n"
            f"空间: {info.parsed_url}{live_room_part}"
        )
        segments.append(Text(text_content))

        return UniMessage(segments)


async def render_video_info_to_image(info: VideoInfo) -> Optional[bytes]:
    """渲染视频信息为图片"""
    logger.debug("开始渲染 VideoInfo (style_blue with icons)")

    cover_image_src = None
    if base_config.get("SEND_VIDEO_PIC", True) and info.pic:
        file_name = f"bili_video_cover_{info.bvid or info.aid}.jpg"
        cover_path = IMAGE_CACHE_DIR / file_name

        if not (cover_path.exists() and cover_path.stat().st_size > 0):
            await ImageHelper.download_image(info.pic, cover_path)

        cover_image_src = await ImageHelper.get_image_as_base64(cover_path)

    up_avatar_src = None
    if info.owner.face:
        avatar_filename = f"bili_avatar_{info.owner.mid}.jpg"
        avatar_path = IMAGE_CACHE_DIR / avatar_filename

        if not (avatar_path.exists() and avatar_path.stat().st_size > 0):
            await ImageHelper.download_image(info.owner.face, avatar_path)

        up_avatar_src = await ImageHelper.get_image_as_base64(avatar_path)

    comments_list = []
    show_comments = True
    comment_count = 3

    if show_comments and comment_count > 0:
        logger.debug(f"尝试获取视频 {info.aid} 的热门评论 (最多 {comment_count} 条)")
        try:
            c = await comment.get_comments(
                oid=info.aid,
                type_=CommentResourceType.VIDEO,
                order=OrderType.LIKE,
                credential=bili_credential,
            )
            fetched_comments = c.get("replies", [])
            if fetched_comments:
                count = 0
                for _, cmt in enumerate(fetched_comments):
                    if count >= comment_count:
                        break
                    if (
                        cmt
                        and isinstance(cmt, dict)
                        and cmt.get("member")
                        and cmt.get("content")
                    ):
                        uname = cmt["member"].get("uname", "未知用户")
                        message = cmt["content"].get("message", "")
                        likes = cmt.get("like", 0)
                        message_text = re.sub(r"\[.*?\]", "", message).strip()
                        if message_text:
                            max_len = 50
                            display_comment = (
                                message_text[:max_len] + "..."
                                if len(message_text) > max_len
                                else message_text
                            )
                            comments_list.append(
                                {
                                    "uname": uname,
                                    "text": display_comment,
                                    "likes": likes,
                                }
                            )
                            count += 1
                logger.debug(f"成功获取到 {len(comments_list)} 条评论")
            else:
                logger.debug(f"视频 {info.aid} 没有评论或获取失败")
        except Exception as e:
            logger.error(f"获取视频评论失败: {info.aid}", e=e)

    display_summary = None
    if info.ai_summary:
        max_summary_len = 180
        if len(info.ai_summary) > max_summary_len:
            display_summary = info.ai_summary[:max_summary_len] + "..."
        else:
            display_summary = info.ai_summary

    template_data = {
        "cover_image_src": cover_image_src,
        "video_category": info.tname,
        "video_duration": format_duration(info.duration),
        "up_info": {
            "avatar_image": up_avatar_src,
            "name": info.owner.name,
            "name_color": "#fb7299",
        },
        "video_title": info.title,
        "view_count": format_number(info.stat.view),
        "dm_count": format_number(info.stat.danmaku),
        "reply_count": format_number(info.stat.reply),
        "upload_date": time.strftime("%Y-%m-%d", time.localtime(info.pubdate)),
        "id_number": f"{info.bvid}" if info.bvid else f"av{info.aid}",
        "video_summary": info.desc or "UP主没有填写简介",
        "like_count": format_number(info.stat.like),
        "coin_count": format_number(info.stat.coin),
        "fav_count": format_number(info.stat.favorite),
        "share_count": format_number(info.stat.share),
        "comments": comments_list,
        "online_count": info.online_count,
        "ai_summary": display_summary,
        "font_van_base64": FONT_BASE64_CONTENT,
    }

    template_path = TEMPLATE_DIR / "style_blue_video.html"
    component = ui.template(path=template_path, data=template_data)

    return await ui.render(component, viewport={"width": 780, "height": 10})


async def render_season_info_to_image(info: SeasonInfo) -> Optional[bytes]:
    """渲染番剧信息为图片"""
    logger.debug("开始渲染 SeasonInfo (style_blue)")

    cover_image_src = None
    cover_url_to_download = info.target_ep_cover or info.cover
    if cover_url_to_download:
        file_prefix = (
            f"bili_ep_cover_{info.target_ep_id}"
            if info.target_ep_id
            else f"bili_season_cover_{info.season_id or info.media_id}"
        )
        cover_path = IMAGE_CACHE_DIR / f"{file_prefix}.jpg"

        if not (cover_path.exists() and cover_path.stat().st_size > 0):
            await ImageHelper.download_image(cover_url_to_download, cover_path)
        cover_image_src = await ImageHelper.get_image_as_base64(cover_path)
    else:
        logger.warning(f"番剧/分集均无封面: {info.season_id or info.media_id}")

    status_text_map = {2: "未开播", 4: "会员抢先", 13: "已完结"}
    status_text = status_text_map.get(info.status, f"状态({info.status})")

    stat_to_display = info.stat
    fav_label = "追番"

    template_data = {
        "cover_image_src": cover_image_src,
        "title": info.target_ep_long_title or info.target_ep_title or info.title,
        "season_title": info.title if info.target_ep_id else None,
        "type_name": info.type_name,
        "status_text": status_text,
        "total_ep": info.total_ep,
        "areas": info.areas,
        "styles": info.styles,
        "rating_score": info.rating_score,
        "rating_count": info.rating_count,
        "desc": info.desc or "暂无简介",
        "view_count": format_number(stat_to_display.views),
        "dm_count": format_number(stat_to_display.danmakus),
        "fav_label": fav_label,
        "fav_count": format_number(stat_to_display.favorites),
        "reply_count": format_number(stat_to_display.reply),
        "like_count": format_number(stat_to_display.likes),
        "coin_count": format_number(stat_to_display.coins),
        "share_count": format_number(stat_to_display.share),
        "font_van_base64": FONT_BASE64_CONTENT,
    }

    template_path = TEMPLATE_DIR / "style_blue_season.html"
    component = ui.template(path=template_path, data=template_data)

    return await ui.render(component, viewport={"width": 420, "height": 10})


async def render_user_info_to_image(info: UserInfo) -> Optional[bytes]:
    """使用 zhenxun.ui 渲染更美观的用户信息为图片"""
    logger.debug(f"开始使用 zhenxun.ui 渲染更美观的用户信息: {info.name}")

    template_data = {
        "top_photo": info.top_photo
        or "https://i0.hdslb.com/bfs/space/cb1c36594b2de665b1b10a22a30b4923e3e41b31.png",
        "face": info.face,
        "name": info.name,
        "sign": info.sign or "这个人很神秘，什么都没有写...",
        "level": info.level,
        "sex": info.sex,
        "birthday": info.birthday,
        "following": format_number(info.stat.following),
        "follower": format_number(info.stat.follower),
        "likes": format_number(info.stat.likes),
        "archive_view": format_number(info.stat.archive_view),
        "article_view": format_number(info.stat.article_view),
        "live_status": info.live_room_status,
        "live_title": info.live_room_title,
        "font_van_base64": FONT_BASE64_CONTENT,
    }

    template_path = TEMPLATE_DIR / "user_card.html"
    component = ui.template(path=template_path, data=template_data)

    return await ui.render(component, viewport={"width": 500, "height": 10})


async def render_live_info_to_image(info: LiveInfo) -> Optional[bytes]:
    """使用 zhenxun.ui 渲染直播间信息为图片"""
    logger.debug(f"开始使用 zhenxun.ui 渲染直播间信息: {info.title}")

    plain_description = MessageBuilder._clean_html_description(info.description)

    start_time_str = ""
    if info.live_status == 1 and info.live_start_time > 0:
        start_time_str = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(info.live_start_time)
        )

    template_data = {
        "cover": info.cover,
        "face": info.face,
        "uname": info.uname,
        "title": info.title,
        "area_name": f"{info.parent_area_name} / {info.area_name}",
        "live_status": info.live_status,
        "start_time": start_time_str,
        "description": plain_description,
        "keyframe": info.keyframe_url,
        "font_van_base64": FONT_BASE64_CONTENT,
    }

    template_path = TEMPLATE_DIR / "live_card.html"
    component = ui.template(path=template_path, data=template_data)

    return await ui.render(component, viewport={"width": 500, "height": 10})


async def render_unimsg_to_image(message: UniMsg) -> Optional[bytes]:
    """将 UniMsg 渲染成图片"""
    logger.debug("开始渲染UniMsg消息")

    html_parts = []
    img_count = 0

    for seg in message:
        if isinstance(seg, Text):
            text = (
                seg.text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            html_parts.append(f"<p>{text}</p>")

        elif isinstance(seg, Image):
            img_src = None

            if seg.url:
                img_src = seg.url

            elif seg.path:
                try:
                    img_path = Path(seg.path)
                    if img_path.is_absolute():
                        path_str = str(img_path.resolve())
                        path_str = path_str.replace("\\", "/")
                        file_uri = "file:///" + path_str
                        img_src = file_uri
                    else:
                        logger.warning(f"图片路径不是绝对路径: {seg.path}")
                except Exception as e:
                    logger.error(f"转换图片路径到URI时出错: {seg.path}", e=e)

            elif seg.raw:
                try:
                    raw_data = (
                        seg.raw.getvalue() if isinstance(seg.raw, BytesIO) else seg.raw
                    )
                    img_base64 = base64.b64encode(raw_data).decode()
                    img_src = f"data:image/png;base64,{img_base64}"
                except Exception as e:
                    logger.error("转换原始图片数据到URI时出错", e=e)

            if img_src:
                html_parts.append(
                    f'<img src="{img_src}" alt="image_{img_count}" style="max-width: 90%; height: auto; display: block; margin-top: 5px; margin-bottom: 5px;" />'
                )
                img_count += 1
            else:
                html_parts.append("<p>[图片加载失败]</p>")

    if not html_parts:
        logger.warning("消息没有可渲染的内容")
        return None

    md_builder = MarkdownData(elements=[])
    for seg in message:
        if isinstance(seg, Text):
            md_builder.text(seg.text)
        elif isinstance(seg, Image):
            if seg.url:
                md_builder.image(seg.url)
            elif seg.path:
                md_builder.image(Path(seg.path))
            elif seg.raw:
                try:
                    raw_data = (
                        seg.raw.getvalue() if isinstance(seg.raw, BytesIO) else seg.raw
                    )
                    img_base64 = base64.b64encode(raw_data).decode()
                    md_builder.image(f"data:image/png;base64,{img_base64}")
                except Exception as e:
                    logger.error("转换原始图片数据失败", e=e)
                    md_builder.text("[图片加载失败]")

    return await ui.render(md_builder, viewport={"width": 650, "height": 10})


def _get_user_friendly_error_message(exception: Exception) -> str:
    """将技术错误转换为用户友好的错误信息"""
    error_str = str(exception)

    if "ActionFailed" in error_str:
        if "retcode=1200" in error_str or "rich media transfer failed" in error_str:
            return "视频发送失败，可能是文件过大或网络不稳定，请稍后重试"
        elif "retcode=100" in error_str:
            return "发送权限不足，请检查机器人权限设置"
        elif "retcode=1400" in error_str:
            return "消息发送频率过快，请稍后重试"
        else:
            return "视频发送失败，请稍后重试"

    if "timeout" in error_str.lower() or "TimeoutError" in error_str:
        return "发送超时，请稍后重试"
    elif "network" in error_str.lower() or "connection" in error_str.lower():
        return "网络连接问题，请检查网络后重试"
    elif "file too large" in error_str.lower() or "文件过大" in error_str:
        return "文件过大，无法发送"
    elif "permission" in error_str.lower() or "权限" in error_str:
        return "权限不足，请检查机器人权限设置"
    else:
        return "发送失败，请稍后重试"


@Retry.api(
    stop_max_attempt=SEND_VIDEO_MAX_RETRIES,
    wait_fixed_seconds=SEND_VIDEO_RETRY_DELAY,  # type: ignore
    exception=(asyncio.TimeoutError,),
    log_name="发送视频文件",
)
async def _send_video_core(bot, event, video_segment):
    """
    核心的视频发送动作，被重试装饰器包裹。
    """
    logger.debug(f"尝试发送视频，超时: {SEND_VIDEO_TIMEOUT}s")
    send_task = asyncio.create_task(bot.send(event=event, message=video_segment))
    await asyncio.wait_for(send_task, timeout=SEND_VIDEO_TIMEOUT)


async def send_video_with_retry(bot, event, video_path: Path) -> bool:
    """发送视频文件，并带有重试逻辑"""
    if not video_path.exists():
        error_msg = f"尝试发送时文件不存在: {video_path}"
        logger.error(error_msg)
        raise DownloadError(error_msg, context={"video_path": str(video_path)})

    path_str = str(video_path.resolve()).replace("\\", "/")
    file_uri = "file:///" + path_str
    video_segment = V11MessageSegment.video(file_uri)

    try:
        await _send_video_core(bot, event, video_segment)
        logger.info(f"视频文件发送成功: {video_path.name}")
        return True
    except Exception as e:
        user_friendly_msg = _get_user_friendly_error_message(e)
        logger.error(f"最终发送失败: {e}", e=e)
        raise DownloadError(
            user_friendly_msg,
            context={"video_path": str(video_path)},
            cause=e,
        ) from e
