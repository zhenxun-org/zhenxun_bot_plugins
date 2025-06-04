import datetime
import traceback

from nonebot_plugin_htmlrender import get_new_page

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .auth import AuthManager
from .wbi import encode_wbi, get_wbi_img

BASE_URL = "https://api.bilibili.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
" AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


async def get_meta(media_id: int, auth=None, req_type="both", **kwargs):
    """
    根据番剧 ID 获取番剧元数据信息，
    作为bilibili_api和bilireq的替代品。
    如果bilireq.bangumi更新了，可以转为调用bilireq.bangumi的get_meta方法，两者完全一致。

    参数:
        media_id: 番剧 ID
        auth: bilireq.Auth对象
        req_type: 请求类型，可选值: "both", "web", "app"
    """
    from bilireq.utils import get

    url = f"{BASE_URL}/pgc/review/user"
    params = {"media_id": media_id}
    raw_json = await get(
        url,
        cookies=AuthManager.get_cookies(),
        raw=True,
        params=params,
        auth=auth,
        reqtype=req_type,
        **kwargs,
    )
    return raw_json["result"]


async def get_videos(uid: int):
    """获取用户投该视频信息

    参数:
        uid: 用户 UID
    """
    space_videos_api = f"{BASE_URL}/x/space/wbi/arc/search"
    ps = 30
    pn = 1
    wbi_img = await get_wbi_img(AuthManager.get_cookies())
    params = {
        "mid": uid,
        "ps": ps,
        "tid": 0,
        "pn": pn,
        "order": "pubdate",
    }
    params = encode_wbi(params, wbi_img)
    res = await AsyncHttpx.get(
        space_videos_api,
        params=params,
        cookies=AuthManager.get_cookies(),
        headers=HEADERS,
    )
    res.raise_for_status()
    return res.json()


async def get_user_card(mid, photo: bool = False, auth=None, req_type="both", **kwargs):
    from bilireq.utils import get

    url = f"{BASE_URL}/x/web-interface/card"
    return (
        await get(
            url,
            cookies=AuthManager.get_cookies(),
            params={"mid": mid, "photo": photo},
            auth=auth,
            reqtype=req_type,
            **kwargs,
        )
    )["card"]


async def get_user_dynamics(uid: int, offset: int = 0, need_top: bool = False):
    from bilireq.utils import get

    """获取指定用户历史动态"""
    url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
    params = {
        "host_uid": uid,
        "offset_dynamic_id": offset,
        "need_top": int(bool(need_top)),
    }
    return await get(
        url, headers=HEADERS, cookies=AuthManager.get_cookies(), params=params
    )


async def get_room_info_by_id(live_id: int, *, auth=None, req_type="app", **kwargs):
    from bilireq.utils import get

    """根据房间号获取指定直播间信息"""
    url = "https://api.live.bilibili.com/room/v1/Room/get_info"
    params = {"id": live_id}
    return await get(
        url,
        cookies=AuthManager.get_cookies(),
        params=params,
        auth=auth,
        reqtype=req_type,
        **kwargs,
    )


async def get_dynamic_screenshot(dynamic_id: int) -> bytes | None:
    url = f"https://t.bilibili.com/{dynamic_id}"
    try:
        async with get_new_page(
            viewport={"width": 2000, "height": 1000},
            user_agent=USER_AGENT,
            device_scale_factor=3,
        ) as page:
            cookies = AuthManager.get_cookies()
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
            await page.goto(url, wait_until="networkidle")
            # 动态被删除或者进审核了
            if page.url == "https://www.bilibili.com/404":
                logger.warning(f"动态 {dynamic_id} 不存在")
                return
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


def calc_time_total(t: float):
    """
    Calculate the total time in a human-readable format.
    Args:
    t (float | int): The time in seconds.
    Returns:
    str: The total time in a human-readable format.
    Example:
    >>> calc_time_total(4.5)
    '4500 毫秒'
    >>> calc_time_total(3600)
    '1 小时'
    >>> calc_time_total(3660)
    '1 小时 1 分钟'
    """
    t = int(t * 1000)
    if t < 5000:
        return f"{t} 毫秒"
    timedelta = datetime.timedelta(seconds=t // 1000)
    day = timedelta.days
    hour, mint, sec = tuple(int(n) for n in str(timedelta).split(",")[-1].split(":"))
    total = ""
    if day:
        total += f"{day} 天 "
    if hour:
        total += f"{hour} 小时 "
    if mint:
        total += f"{mint} 分钟 "
    if sec and not day and not hour:
        total += f"{sec} 秒 "
    return total
