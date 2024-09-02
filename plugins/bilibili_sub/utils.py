import datetime

import httpx  # type: ignore
import traceback
from zhenxun.utils.image_utils import BuildImage
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.utils.http_utils import AsyncHttpx
from bilireq.user import get_user_info  # type: ignore
from io import BytesIO
from .auth import AuthManager
from nonebot_plugin_htmlrender import get_new_page  # type: ignore
from .Wbi import get_wbi_img, encode_wbi
from ...services import logger

BORDER_PATH = IMAGE_PATH / "border"
BORDER_PATH.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.bilibili.com"


async def get_pic(url: str) -> bytes:
    """
    获取图像
    :param url: 图像链接
    :return: 图像二进制
    """
    return (await AsyncHttpx.get(url, timeout=10)).content


async def create_live_des_image(uid: int, title: str, cover: str, tags: str, des: str):
    """
    生成主播简介图片
    :param uid: 主播 uid
    :param title: 直播间标题
    :param cover: 直播封面
    :param tags: 直播标签
    :param des: 直播简介
    :return:
    """
    user_info = await get_user_info(uid, cookies=AuthManager.get_cookies())
    user_info["name"]
    user_info["sex"]
    face = user_info["face"]
    user_info["sign"]
    ava = BuildImage(100, 100, background=BytesIO(await get_pic(face)))
    ava.circle()
    cover = BuildImage(470, 265, background=BytesIO(await get_pic(cover)))


def _create_live_des_image(
    title: str,
    cover: BuildImage,
    tags: str,
    des: str,
    user_name: str,
    sex: str,
    sign: str,
    ava: BuildImage,
):
    """
    生成主播简介图片
    :param title: 直播间标题
    :param cover: 直播封面
    :param tags: 直播标签
    :param des: 直播简介
    :param user_name: 主播名称
    :param sex: 主播性别
    :param sign: 主播签名
    :param ava: 主播头像
    :return:
    """
    border = BORDER_PATH / "0.png"
    if border.exists():
        BuildImage(1772, 2657, background=border)
    bk = BuildImage(1772, 2657, font_size=30)
    bk.paste(cover, (0, 100), center_type="by_width")


async def get_meta(media_id: int, auth=None, reqtype="both", **kwargs):
    """
    根据番剧 ID 获取番剧元数据信息，
    作为bilibili_api和bilireq的替代品。
    如果bilireq.bangumi更新了，可以转为调用bilireq.bangumi的get_meta方法，两者完全一致。
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
        reqtype=reqtype,
        **kwargs,
    )
    return raw_json["result"]


async def get_videos(uid: int):
    """
    获取用户投该视频信息
    :param uid: 用户 UID
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    }
    async with httpx.AsyncClient(
        cookies=AuthManager.get_cookies(), headers=headers
    ) as client:
        space_videos_api = f"{BASE_URL}/x/space/wbi/arc/search"
        ps = 30
        pn = 1
        wbi_img = await get_wbi_img(client)
        params = {
            "mid": uid,
            "ps": ps,
            "tid": 0,
            "pn": pn,
            "order": "pubdate",
        }
        params = encode_wbi(params, wbi_img)
        json_data = (await client.get(space_videos_api, params=params)).json()
        return json_data


async def get_user_card(mid, photo: bool = False, auth=None, reqtype="both", **kwargs):
    from bilireq.utils import get

    url = f"{BASE_URL}/x/web-interface/card"
    return (
        await get(
            url,
            cookies=AuthManager.get_cookies(),
            params={"mid": mid, "photo": photo},
            auth=auth,
            reqtype=reqtype,
            **kwargs,
        )
    )["card"]


async def get_user_dynamics(uid: int, offset: int = 0, need_top: bool = False):
    from bilireq.utils import get

    """获取指定用户历史动态"""
    url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    }
    params = {
        "host_uid": uid,
        "offset_dynamic_id": offset,
        "need_top": int(bool(need_top)),
    }
    return await get(
        url, headers=headers, cookies=AuthManager.get_cookies(), params=params
    )


async def get_room_info_by_id(live_id: int, *, auth=None, reqtype="app", **kwargs):
    from bilireq.utils import get

    """根据房间号获取指定直播间信息"""
    url = "https://api.live.bilibili.com/room/v1/Room/get_info"
    params = {"id": live_id}
    return await get(
        url,
        cookies=AuthManager.get_cookies(),
        params=params,
        auth=auth,
        reqtype=reqtype,
        **kwargs,
    )


async def get_dynamic_screenshot(dynamic_id: int) -> bytes | None:
    url = f"https://t.bilibili.com/{dynamic_id}"
    try:
        async with get_new_page(
            viewport={"width": 2000, "height": 1000},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
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
