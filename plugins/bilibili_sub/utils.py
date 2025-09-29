import datetime
import traceback
from pathlib import Path

from bilibili_api import user as bilibili_user_module
from bilibili_api import live as bilibili_live_module
from bilibili_api import Credential as BilibiliCredential

from nonebot_plugin_htmlrender import get_new_page

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.configs.path_config import IMAGE_PATH

from .config import AVATAR_CACHE_DIR, BANGUMI_COVER_CACHE_DIR, get_credential

BORDER_PATH = IMAGE_PATH / "border"
BORDER_PATH.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.bilibili.com"


async def get_pic(url: str) -> bytes:
    """获取图像"""
    return (await AsyncHttpx.get(url, timeout=10)).content


async def get_cached_avatar(uid: int, avatar_url: str) -> Path | None:
    """获取缓存的用户头像路径，如果不存在则下载"""
    if not avatar_url or not uid:
        return None
    cached_path = AVATAR_CACHE_DIR / f"{uid}.png"
    if cached_path.exists():
        logger.debug(f"头像缓存命中: UID {uid}")
        return cached_path

    logger.debug(f"头像缓存未命中，正在下载: UID {uid}")
    try:
        if await AsyncHttpx.download_file(avatar_url, cached_path):
            return cached_path
    except Exception as e:
        logger.error(f"下载头像失败 UID: {uid}, URL: {avatar_url}", e=e)
    return None


async def get_cached_bangumi_cover(season_or_ep_id: int, cover_url: str) -> Path | None:
    """获取缓存的番剧或剧集封面路径，如果不存在则下载"""
    if not cover_url or not season_or_ep_id:
        return None
    cached_path = BANGUMI_COVER_CACHE_DIR / f"{season_or_ep_id}.png"
    if cached_path.exists():
        logger.debug(f"番剧封面缓存命中: ID {season_or_ep_id}")
        return cached_path

    logger.debug(f"番剧封面缓存未命中，正在下载: ID {season_or_ep_id}")
    try:
        if await AsyncHttpx.download_file(cover_url, cached_path):
            return cached_path
    except Exception as e:
        logger.error(f"下载番剧封面失败 ID: {season_or_ep_id}, URL: {cover_url}", e=e)
    return None


async def get_videos(uid: int, auth: BilibiliCredential | None = None, **kwargs):
    """获取用户投搞视频信息"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=uid, credential=credential)
    return await user_instance.get_videos(**kwargs)


async def get_user_card(
    mid: int, photo: bool = False, auth: BilibiliCredential | None = None, **kwargs
):
    """获取用户卡片信息"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=mid, credential=credential)
    user_info = await user_instance.get_user_info()
    return user_info


async def get_user_dynamics(
    uid: int,
    offset: int = 0,
    need_top: bool = False,
    auth: BilibiliCredential | None = None,
    **kwargs,
):
    """获取指定用户历史动态"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=uid, credential=credential)
    return await user_instance.get_dynamics(offset=offset, need_top=need_top, **kwargs)


async def get_room_info_by_id(
    live_id: int, auth: BilibiliCredential | None = None, **kwargs
):
    """根据房间号获取指定直播间信息"""
    credential = auth or get_credential()
    liveroom_instance = bilibili_live_module.LiveRoom(
        room_display_id=live_id, credential=credential
    )
    return await liveroom_instance.get_room_info()


async def get_dynamic_screenshot(dynamic_id: int) -> bytes | None:
    url = f"https://t.bilibili.com/{dynamic_id}"
    try:
        async with get_new_page(
            viewport={"width": 2000, "height": 1000},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            device_scale_factor=3,
        ) as page:
            credential = get_credential()
            if credential:
                try:
                    cookies = credential.get_cookies()
                    if cookies:
                        await page.context.add_cookies(
                            [
                                {
                                    "domain": ".bilibili.com",
                                    "name": name,
                                    "path": "/",
                                    "value": value,
                                }
                                for name, value in cookies.items()
                            ]
                        )
                except Exception as e:
                    logger.warning(f"获取 cookies 失败: {e}")
            await page.goto(url, wait_until="networkidle")
            if page.url == "https://www.bilibili.com/404":
                logger.warning(f"动态 {dynamic_id} 不存在")
                return None
            await page.wait_for_load_state(state="domcontentloaded")
            card = await page.query_selector(".card")
            assert card
            clip = await card.bounding_box()
            assert clip
            bar = await page.query_selector(".bili-tabs__header")
            assert bar
            bar_bound = await bar.bounding_box()
            assert bar_bound
            clip["height"] = bar_bound["y"] - clip["y"]
            return await page.screenshot(clip=clip, full_page=True)
    except Exception:
        logger.warning(
            f"Error in get_dynamic_screenshot({url}): {traceback.format_exc()}"
        )
    return None


def calc_time_total(t: float):
    """计算人类可读格式的总时间"""
    if not isinstance(t, (int, float)):
        try:
            t = float(t)
        except (ValueError, TypeError):
            return "时间格式错误"

    t_int = int(t * 1000)
    if t_int < 5000:
        return f"{t_int} 毫秒"
    timedelta_obj = datetime.timedelta(seconds=t_int // 1000)
    day = timedelta_obj.days
    hour, mint, sec = tuple(
        int(n) for n in str(timedelta_obj).split(",")[-1].split(":")
    )
    total = ""
    if day:
        total += f"{day} 天 "
    if hour:
        total += f"{hour} 小时 "
    if mint:
        total += f"{mint} 分钟 "
    if sec and not day and not hour:
        total += f"{sec} 秒 "
    return total.strip()
