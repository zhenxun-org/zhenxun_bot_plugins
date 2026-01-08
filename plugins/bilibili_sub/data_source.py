import asyncio
import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto

import httpx
import nonebot
from bilibili_api import bangumi, search
from bilibili_api import user as bilibili_user_module
from bilibili_api.exceptions import ResponseCodeException

from zhenxun import ui
from zhenxun.services.log import logger
from zhenxun.ui.builders import NotebookBuilder
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import ResourceDirManager

from .config import DYNAMIC_PATH, base_config, get_credential
from .filter import is_ad as is_dynamic_ad
from .model import BiliSub, BiliSubTarget
from .utils import (
    get_cached_bangumi_cover,
    get_dynamic_screenshot,
    get_room_info_by_id,
    get_user_card,
    get_user_dynamics,
    get_videos,
)

ResourceDirManager.add_temp_dir(DYNAMIC_PATH)


class NotificationType(Enum):
    """通知类型枚举"""

    DYNAMIC = auto()
    VIDEO = auto()
    LIVE = auto()


@dataclass
class Notification:
    """通知数据类"""

    content: list
    type: NotificationType


async def fetch_image_bytes(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        headers = {
            "Referer": "https://t.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        response = await client.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.content


async def handle_video_info_error(video_info: dict):
    """处理B站视频信息获取错误并发送通知给超级用户"""
    str_msg = "b站订阅检测失败："
    if video_info["code"] == -352:
        str_msg += "风控校验失败，请登录后再尝试。发送'登录b站'"
    elif video_info["code"] == -799:
        str_msg += "请求过于频繁，请增加时长，更改配置文件下的'CHECK_TIME''"
    else:
        str_msg += f"{video_info['code']}，{video_info['message']}"

    bots = nonebot.get_bots()
    for bot_instance in bots.values():
        if bot_instance:
            await PlatformUtils.send_superuser(bot_instance, str_msg)

    return str_msg


async def _add_subscription(
    uid: int,
    target_id: str,
    uname: str,
    push_config: dict,
    initial_timestamps: dict | None = None,
    **extra_fields,
) -> str:
    """通用的添加订阅和目标关系的内部函数"""
    sub, created = await BiliSub.get_or_create(uid=uid)

    if created:
        sub.push_dynamic = push_config.get("dynamic", False)
        sub.push_video = push_config.get("video", False)
        sub.push_live = push_config.get("live", False)
        if initial_timestamps:
            sub.last_dynamic_timestamp = initial_timestamps.get("dynamic", 0)
            sub.last_video_timestamp = initial_timestamps.get("video", 0)

    sub.uname = uname
    for field, value in extra_fields.items():
        if hasattr(sub, field):
            setattr(sub, field, value)
    await sub.save()

    _, created_target = await BiliSubTarget.get_or_create(
        subscription=sub, target_id=target_id
    )

    if not created_target:
        return f"ℹ️ 你已经订阅过「{uname}」(UID/SSID: {uid}) 了。"

    msg_parts = [
        "🎉 订阅成功！",
        f"{'番剧' if uid < 0 else 'UP主'}：{uname}",
        f"{'Season ID' if uid < 0 else 'UID'}：{abs(uid)}",
    ]
    if sub.room_id:
        msg_parts.append(f"直播间ID：{sub.room_id}")
    return "\n".join(msg_parts)


async def add_live_sub(room_id: int, target_id: str) -> str:
    """添加直播订阅"""
    try:
        try:
            live_info_raw = await get_room_info_by_id(room_id)
            if not live_info_raw or not live_info_raw.get("room_info"):
                return f"❌ 未找到房间号 {room_id} 的信息，请检查ID是否正确。"
            live_info = live_info_raw["room_info"]
        except ResponseCodeException:
            return f"❌ 未找到房间号 {room_id} 的信息，请检查ID是否正确。"
        uid = live_info["uid"]
        user_info = await get_user_card(uid)
        uname = user_info.get("name", "未知主播") if user_info else "未知主播"

        default_push_types = base_config.get("DEFAULT_LIVE_PUSH_TYPES", ["live"])
        push_config = {
            "dynamic": "dynamic" in default_push_types,
            "video": "video" in default_push_types,
            "live": "live" in default_push_types,
        }

        return await _add_subscription(
            uid, target_id, uname, push_config, room_id=live_info["room_id"]
        )
    except Exception as e:
        logger.error(f"订阅主播 room_id: {room_id} 时发生错误", e=e)
        return f"❌ 订阅失败，发生内部错误: {e}"


async def add_bangumi_sub(season_id: int, target_id: str) -> str:
    """添加番剧订阅"""
    try:
        credential = get_credential()
        b_obj = bangumi.Bangumi(ssid=season_id, credential=credential)
        meta_info = await b_obj.get_overview()
        title = meta_info.get("title", "未知番剧")

        push_config = {
            "dynamic": False,
            "video": True,
            "live": False,
        }
        initial_timestamps = {"video": 0}

        return await _add_subscription(
            -season_id, target_id, title, push_config, initial_timestamps
        )

    except Exception as e:
        logger.error(f"订阅番剧 season_id: {season_id} 时发生错误", e=e)
        return f"❌ 订阅失败，发生内部错误: {e}"


async def search_bangumi(keyword: str) -> list:
    try:
        result = await search.search_by_type(keyword, search.SearchObjectType.BANGUMI)
        return result.get("result", [])
    except Exception:
        return []


async def get_season_id_from_ep(ep_id: int) -> int | None:
    """通过剧集ep_id获取番剧season_id"""
    try:
        credential = get_credential()
        b_obj = bangumi.Bangumi(epid=ep_id, credential=credential)
        season_id = await b_obj.get_season_id()
        return season_id
    except Exception as e:
        logger.error(f"从 ep_id {ep_id} 获取 season_id 失败: {e}")
        return None


async def add_up_sub(uid: int, target_id: str) -> str:
    """添加订阅 UP"""
    try:
        try:
            user_info = await get_user_card(uid)
            if not user_info:
                return f"❌ 未找到ID {uid} 的信息，请检查ID是否正确。"
        except ResponseCodeException:
            return f"❌ API请求失败，请检查ID {uid} 是否正确。"

        authoritative_uid = user_info.get("mid")
        if not authoritative_uid:
            return "❌ 无法从B站API返回的数据中解析出核心UID，订阅失败。"
        uname = user_info.get("name", "未知UP主")

        room_id = None
        if user_info.get("live_room") and user_info["live_room"].get("roomid"):
            room_id = user_info["live_room"]["roomid"]
            logger.info(
                f"从用户信息中直接找到直播间ID: {room_id} (UID: {authoritative_uid})"
            )
        else:
            try:
                user_instance = bilibili_user_module.User(uid=authoritative_uid)
                live_info = await user_instance.get_live_info()
                if live_info and live_info.get("roomid"):
                    room_id = live_info.get("roomid")
                    logger.info(
                        f"通过单独请求找到直播间ID: {room_id} (UID: {authoritative_uid})"
                    )
            except ResponseCodeException:
                logger.debug(
                    f"后备方案：UID {authoritative_uid} 没有关联的直播间或查询失败。"
                )

        try:
            dynamic_info = await get_user_dynamics(authoritative_uid)
        except ResponseCodeException as e:
            if e.code == -352:
                return "❌ 风控校验失败，请联系管理员登录B站。"
            return f"获取动态失败: {e.code} {e.msg}"

        dynamic_upload_time = 0
        if dynamic_info and dynamic_info.get("cards"):
            dynamic_upload_time = dynamic_info["cards"][0]["desc"]["timestamp"]

        video_info_raw = await get_videos(authoritative_uid)

        if not isinstance(video_info_raw, dict):
            logger.error(
                f"get_videos 返回了非预期的类型: {type(video_info_raw)} for UID: {authoritative_uid}"
            )
            return "订阅失败，请联系管理员（视频信息获取类型错误）"
        if "code" in video_info_raw and video_info_raw["code"] != 0:
            await handle_video_info_error(video_info_raw)
            return f"获取视频列表失败: {video_info_raw.get('message', '未知API错误')}"
        if "data" in video_info_raw and isinstance(video_info_raw["data"], dict):
            video_info_data = video_info_raw["data"]
        else:
            video_info_data = video_info_raw

        latest_video_created = 0
        if video_info_data.get("list", {}).get("vlist"):
            latest_video_created = video_info_data["list"]["vlist"][0].get("created", 0)

        default_push_types = base_config.get(
            "DEFAULT_UP_PUSH_TYPES", ["dynamic", "video"]
        )
        push_config = {
            "dynamic": "dynamic" in default_push_types,
            "video": "video" in default_push_types,
            "live": "live" in default_push_types,
        }
        initial_timestamps = {
            "dynamic": dynamic_upload_time,
            "video": latest_video_created,
        }

        return await _add_subscription(
            authoritative_uid,
            target_id,
            uname,
            push_config,
            initial_timestamps,
            room_id=room_id,
        )

    except Exception as e:
        logger.error(f"订阅Up id：{uid} 发生了未预料的错误 {type(e)}：{e}")
        import traceback

        logger.error(traceback.format_exc())
        return "❌ 订阅失败（未知错误）。"


async def delete_sub(uid: int, target_id: str) -> str:
    """删除订阅"""
    try:
        sub = await BiliSub.get_or_none(uid=uid)
        if not sub:
            return f"❌ 未找到UID {uid} 的订阅。"

        target = await BiliSubTarget.get_or_none(subscription=sub, target_id=target_id)
        if not target:
            return f"❌ 你没有订阅过 {sub.uname} (UID: {uid})。"

        await target.delete()

        remaining_targets = await BiliSubTarget.filter(subscription=sub).count()
        if remaining_targets == 0:
            await sub.delete()
            logger.info(f"删除了孤立的订阅记录: UID={uid}")

        return f"✅ 成功取消订阅 {sub.uname} (UID: {uid})。"
    except Exception as e:
        logger.error(f"删除订阅时发生错误: UID={uid}, target_id={target_id}, 错误={e}")
        return f"❌ 删除订阅失败: {e}"


async def get_sub_status(sub: BiliSub, force_push: bool = False) -> list[Notification]:
    """获取订阅状态"""
    start_time = time.time()
    all_notifications: list[Notification] = []

    try:
        if sub.uid < 0:
            bangumi_notifications = await _get_bangumi_status(sub, force_push)
            if bangumi_notifications:
                all_notifications.extend(bangumi_notifications)
        else:
            if sub.push_dynamic or sub.push_video:
                up_notifications = await _get_up_status(sub, force_push)
                if up_notifications:
                    all_notifications.extend(up_notifications)

            if sub.push_live and sub.room_id:
                live_notifications = await _get_live_status(sub)
                if live_notifications:
                    all_notifications.extend(live_notifications)

    except ResponseCodeException as msg:
        error_code = getattr(msg, "code", "unknown")
        error_message = getattr(msg, "msg", str(msg))
        logger.error(
            f"订阅状态检查失败: UID={sub.uid}, 错误码={error_code}, 错误信息={error_message}"
        )
        return []
    except Exception as e:
        logger.error(
            f"订阅状态检查发生未预期异常: UID={sub.uid}, 异常类型={type(e).__name__}, 异常信息={e}"
        )
        import traceback

        logger.debug(f"异常详细信息:\n{traceback.format_exc()}")
        return []

    duration = time.time() - start_time
    if all_notifications:
        logger.info(
            f"订阅状态检查完成: UID={sub.uid}, 检测到 {len(all_notifications)} 个更新, 耗时={duration:.2f}秒"
        )
    else:
        logger.debug(
            f"订阅状态检查完成: UID={sub.uid}, 未检测到更新, 耗时={duration:.2f}秒"
        )

    return all_notifications


async def _get_live_status(sub: BiliSub) -> list[Notification]:
    """获取直播订阅状态"""
    start_time = time.time()
    if not sub.room_id:
        return []

    try:
        logger.debug(f"获取直播间信息: 房间ID={sub.room_id}")
        live_info_raw = await get_room_info_by_id(sub.room_id)
        if not live_info_raw or not live_info_raw.get("room_info"):
            logger.error(
                f"直播间信息获取失败或结构异常: 房间ID={sub.room_id}, 返回数据={live_info_raw}"
            )
            return []

        live_info = live_info_raw["room_info"]
        logger.debug(f"成功获取直播间信息: 房间ID={sub.room_id}, 数据结构完整")
    except Exception as e:
        logger.error(
            f"获取直播间信息异常: 房间ID={sub.room_id}, 异常类型={type(e).__name__}, 异常信息={e}"
        )
        import traceback

        logger.debug(f"异常详细信息:\n{traceback.format_exc()}")
        return []

    title = live_info["title"]
    room_id = live_info["room_id"]
    live_status = live_info["live_status"]
    cover = live_info.get("cover")
    logger.debug(
        f"直播间信息: 房间ID={sub.room_id}, 实际房间ID={room_id}, 标题={title}, 直播状态={live_status}"
    )

    old_live_status = sub.live_status
    logger.debug(
        f"订阅信息: 房间ID={sub.room_id}, 主播名={sub.uname}, 当前状态={old_live_status}, API状态={live_status}"
    )

    notifications = []
    if old_live_status != live_status:
        logger.info(
            f"直播状态变化: 房间ID={sub.room_id}, 主播={sub.uname}, 旧状态={old_live_status}, 新状态={live_status}"
        )
        sub.live_status = live_status
        await sub.save(update_fields=["live_status"])
        logger.debug(
            f"已更新数据库中的直播状态: 房间ID={sub.room_id}, 新状态={live_status}"
        )
    else:
        logger.debug(f"直播状态未变化: 房间ID={sub.room_id}, 状态={live_status}")

    if old_live_status in [0, 2] and live_status == 1 and cover:
        logger.info(f"检测到开播: 房间ID={sub.room_id}, 主播={sub.uname}, 标题={title}")

        notebook = NotebookBuilder()
        notebook.image(cover)
        notebook.head(f"{sub.uname} 开播啦！🎉", level=2)
        notebook.text(f"**标题：** {title}")
        notebook.text(
            f"**直播间：** [https://live.bilibili.com/{room_id}](https://live.bilibili.com/{room_id})"
        )

        img_bytes = await ui.render(notebook.build(), use_cache=False)
        notifications.append(
            Notification(
                content=[img_bytes, f"直播间链接: https://live.bilibili.com/{room_id}"],
                type=NotificationType.LIVE,
            )
        )

    duration = time.time() - start_time
    if notifications:
        logger.info(
            f"直播状态检查完成: 房间ID={sub.room_id}, 检测到开播, 耗时={duration:.2f}秒"
        )
    else:
        logger.debug(
            f"直播状态检查完成: 房间ID={sub.room_id}, 未检测到开播, 耗时={duration:.2f}秒"
        )

    return notifications


async def _get_bangumi_status(
    sub: BiliSub, force_push: bool = False
) -> list[Notification]:
    """获取番剧更新状态"""
    if not sub.uid < 0:
        return []

    logger.debug(
        f"番剧状态检查开始: SSID={abs(sub.uid)}, 名称={sub.uname}, force_push={force_push}"
    )

    season_id = abs(sub.uid)
    last_ep_id = sub.last_video_timestamp or 0
    notifications = []

    try:
        credential = get_credential()
        b_obj = bangumi.Bangumi(ssid=season_id, credential=credential)
        episodes_info = await b_obj.get_episode_list()

        if not episodes_info or not isinstance(episodes_info, dict):
            return []

        main_section = episodes_info.get("main_section")
        if not isinstance(main_section, dict) or not main_section.get("episodes"):
            return []

        all_eps = main_section["episodes"]
        new_eps = []
        latest_ep = None

        if not all_eps:
            return []

        if force_push:
            latest_ep = max(all_eps, key=lambda x: x.get("pub_time", 0))
        else:
            new_eps = [ep for ep in all_eps if ep.get("id", 0) > last_ep_id]
            if new_eps:
                latest_ep = max(new_eps, key=lambda x: x.get("id", 0))

        if not latest_ep:
            logger.debug(
                f"番剧状态检查: 未找到新剧集 for SSID={season_id}. last_ep_id={last_ep_id}"
            )
            return []

        from zhenxun.ui.builders import NotebookBuilder

        notebook = NotebookBuilder()
        cover_url = latest_ep.get("cover", "")
        cover_path = None
        if cover_url:
            cover_path = await get_cached_bangumi_cover(
                latest_ep.get("id", 0), cover_url
            )
        if cover_path:
            notebook.image(cover_path.absolute().as_uri())
        elif cover_url:
            notebook.image(cover_url)
        notebook.head(f"《{sub.uname}》更新啦！🎉", level=2)
        notebook.text(f"**标题：** {latest_ep.get('long_title', '未知标题')}")
        notebook.text(f"**Bvid：** {latest_ep.get('bvid', '未知')}")

        img_bytes = await ui.render(notebook.build(), use_cache=False)
        notifications.append(
            Notification(
                content=[
                    img_bytes,
                    f"https://www.bilibili.com/bangumi/play/ep{latest_ep.get('id', '')}",
                ],
                type=NotificationType.VIDEO,
            )
        )

        if not force_push:
            sub.last_video_timestamp = latest_ep.get("id", 0)
            await sub.save(update_fields=["last_video_timestamp"])
            logger.debug(
                f"番剧状态检查: 已更新 last_video_timestamp for SSID={season_id} to {sub.last_video_timestamp}"
            )

    except Exception as e:
        logger.error(f"检查番剧 {season_id} 更新失败: {e}", e=e)

    return notifications


async def fetch_image_with_retry(url, retries=3, delay=2):
    """带重试的图片获取函数"""
    for i in range(retries):
        try:
            return await fetch_image_bytes(url)
        except Exception as e:
            if i < retries - 1:
                await asyncio.sleep(delay)
            else:
                raise e
    return None


async def _get_up_status(sub: BiliSub, force_push: bool = False) -> list[Notification]:
    start_time = time.time()
    current_time = datetime.now()

    try:
        video_info_raw = await get_videos(sub.uid)

        uname = None
        if "data" in video_info_raw and video_info_raw["data"].get("list", {}).get(
            "vlist"
        ):
            uname = video_info_raw["data"]["list"]["vlist"][0].get("author")

        if not uname:
            logger.debug(f"视频信息中未找到用户名，回退到 get_user_card: UID={sub.uid}")
            user_info = await get_user_card(sub.uid)
            if not user_info:
                logger.warning(f"UP主信息获取失败: UID={sub.uid}")
                return []
            uname = user_info["name"]
        else:
            logger.debug(
                f"成功从视频信息中获取UP主用户名: UID={sub.uid}, 用户名={uname}"
            )

    except Exception as e:
        logger.error(
            f"获取视频列表异常: UID={sub.uid}, 异常类型={type(e).__name__}, 异常信息={e}"
        )
        import traceback

        logger.debug(f"异常详细信息:\n{traceback.format_exc()}")
        return []

    if not isinstance(video_info_raw, dict):
        logger.error(
            f"视频信息格式错误: UID={sub.uid}, 返回类型={type(video_info_raw)}"
        )
        await handle_video_info_error(
            {"code": -1, "message": "获取视频信息时返回了非字典类型"}
        )
        return []

    if "code" in video_info_raw and video_info_raw.get("code", 0) != 0:
        logger.error(
            f"视频API返回错误: UID={sub.uid}, 错误码={video_info_raw.get('code')}, 错误信息={video_info_raw.get('message', '未知错误')}"
        )
        await handle_video_info_error(video_info_raw)
        return []

    logger.debug(f"解析视频数据结构: UID={sub.uid}")
    if "list" in video_info_raw and "page" in video_info_raw:
        video_info_data = video_info_raw
        logger.debug(f"使用直接返回的视频数据结构: UID={sub.uid}")
    elif "data" in video_info_raw and isinstance(video_info_raw["data"], dict):
        video_info_data = video_info_raw["data"]
        logger.debug(f"使用data字段中的视频数据结构: UID={sub.uid}")
    else:
        logger.error(
            f"视频数据结构不符合预期: UID={sub.uid}, 数据结构={list(video_info_raw.keys())}"
        )
        await handle_video_info_error(video_info_raw.get("data", video_info_raw))
        return []

    notifications: list[Notification] = []
    notebook: NotebookBuilder | None = None
    notification_type: NotificationType | None = None
    is_new_video_pushed = False

    time_threshold = current_time - timedelta(minutes=30)
    logger.debug(f"设置时间阈值: UID={sub.uid}, 阈值={time_threshold}")

    if sub.uname != uname:
        logger.info(
            f"UP主用户名变更: UID={sub.uid}, 旧名称={sub.uname}, 新名称={uname}"
        )
        sub.uname = uname
        await sub.save(update_fields=["uname"])
        logger.debug(f"已更新UP主用户名: UID={sub.uid}, 新名称={uname}")

    dynamic_img = None
    dynamic_upload_time = 0
    dynamic_images = None

    if sub.push_dynamic:
        try:
            (
                dynamic_img,
                dynamic_upload_time,
                _,
                dynamic_images,
            ) = await get_user_dynamic(sub)
        except ResponseCodeException as msg:
            logger.error(
                f"动态获取失败: UID={sub.uid}, 错误码={getattr(msg, 'code', 'unknown')}, 错误信息={getattr(msg, 'msg', str(msg))}"
            )
    if dynamic_img and (
        sub.last_dynamic_timestamp is None
        or sub.last_dynamic_timestamp < dynamic_upload_time
    ):
        dynamic_time = datetime.fromtimestamp(dynamic_upload_time)
        dynamic_time_str = dynamic_time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"检测到新动态: UID={sub.uid}, 发布时间={dynamic_time_str}")

        is_new_and_recent = dynamic_time > time_threshold
        if force_push or is_new_and_recent:
            if is_new_and_recent:
                logger.debug(
                    f"动态在时间阈值内: UID={sub.uid}, 发布时间={dynamic_time_str}, 阈值={time_threshold}"
                )

            if base_config.get("ENABLE_AD_FILTER"):
                logger.info(
                    f"[广告过滤] 启用广告过滤检查: UID={sub.uid}, 用户名={sub.uname}"
                )

                dynamic_id = (await get_user_dynamics(sub.uid))["cards"][0]["desc"][
                    "dynamic_id"
                ]
                logger.debug(
                    f"[广告过滤] 提取动态ID: UID={sub.uid}, 动态ID={dynamic_id}"
                )

                filter_start_time = time.time()
                try:
                    is_ad_flag = await is_dynamic_ad(sub.uid, dynamic_id)
                    filter_duration = time.time() - filter_start_time

                    if is_ad_flag:
                        logger.warning(
                            f"[广告过滤] 动态被过滤拦截: UID={sub.uid}, 用户名={sub.uname}, 动态ID={dynamic_id}, 耗时={filter_duration:.2f}秒"
                        )
                        sub.last_dynamic_timestamp = dynamic_upload_time
                        await sub.save(update_fields=["last_dynamic_timestamp"])
                        return []
                    else:
                        logger.info(
                            f"[广告过滤] 动态通过过滤检查: UID={sub.uid}, 用户名={sub.uname}, 动态ID={dynamic_id}, 耗时={filter_duration:.2f}秒"
                        )
                except Exception as e:
                    filter_duration = time.time() - filter_start_time
                    logger.error(
                        f"[广告过滤] 过滤检查异常: UID={sub.uid}, 动态ID={dynamic_id}, 耗时={filter_duration:.2f}秒, 错误={e}"
                    )

            if not notebook:
                notebook = NotebookBuilder()
            notebook.head(f"{uname} 发布了动态！📢", level=2)
            base64_str = base64.b64encode(dynamic_img).decode()
            notebook.image(f"data:image/png;base64,{base64_str}")
            notification_type = NotificationType.DYNAMIC

            if not force_push:
                sub.last_dynamic_timestamp = dynamic_upload_time
                await sub.save(update_fields=["last_dynamic_timestamp"])
        elif not force_push:
            logger.debug(
                f"动态不在时间阈值内，仅更新记录: UID={sub.uid}, 发布时间={dynamic_time_str}, 阈值={time_threshold}"
            )
            sub.last_dynamic_timestamp = dynamic_upload_time
            await sub.save(update_fields=["last_dynamic_timestamp"])

    logger.debug(f"开始检查视频更新: UID={sub.uid}")
    video = None
    if sub.push_video and video_info_data.get("list", {}).get("vlist"):
        video = video_info_data["list"]["vlist"][0]
        latest_video_created = video.get("created", 0)
        video_title = video.get("title", "未知标题")
        video_bvid = video.get("bvid", "未知BV号")

        video_time_str = (
            datetime.fromtimestamp(latest_video_created).strftime("%Y-%m-%d %H:%M:%S")
            if latest_video_created
            else "未知时间"
        )
        logger.debug(
            f"获取到最新视频: UID={sub.uid}, 标题={video_title}, 发布时间={video_time_str}"
        )

        is_new_and_recent_video = (
            sub.last_video_timestamp is None
            or sub.last_video_timestamp < latest_video_created
        ) and datetime.fromtimestamp(latest_video_created) > time_threshold

        if force_push or is_new_and_recent_video:
            logger.info(f"检测到新视频 (或强制推送): UID={sub.uid}, 标题={video_title}")
            is_new_video_pushed = True

            notebook = NotebookBuilder()
            notification_type = NotificationType.VIDEO

            notebook.head(f"{uname} 投稿了新视频啦！🎉", level=2)
            notebook.image(video["pic"])
            notebook.text(f"**标题：** {video_title}")
            notebook.text(f"**Bvid：** {video_bvid}")

            if not force_push:
                logger.debug(
                    f"更新视频发布时间: UID={sub.uid}, 新时间={latest_video_created}"
                )
                sub.last_video_timestamp = latest_video_created
                await sub.save(update_fields=["last_video_timestamp"])
            logger.info(
                f"视频推送消息已准备: UID={sub.uid}, 用户名={uname}, 视频BV号={video_bvid}"
            )

        elif (
            not force_push
            and latest_video_created
            and (
                sub.last_video_timestamp is None
                or latest_video_created > sub.last_video_timestamp
            )
        ):
            logger.debug(
                f"检测到较早的新视频，仅更新记录: UID={sub.uid}, 视频发布时间={video_time_str}, 阈值={time_threshold}"
            )
            sub.last_video_timestamp = latest_video_created
            await sub.save(update_fields=["last_video_timestamp"])
        else:
            logger.debug(
                f"未检测到新视频: UID={sub.uid}, 最新视频时间={video_time_str}, 本地记录时间={'无记录' if sub.last_video_timestamp is None else datetime.fromtimestamp(sub.last_video_timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
            )
    else:
        logger.info(f"视频列表为空: UID={sub.uid}")

    if notebook:
        msg_list_content = []
        img_bytes = await ui.render(notebook.build(), frameless=True)
        msg_list_content.append(img_bytes)

        # 如果有动态原图，且功能开关已开启，则添加到消息列表中
        if (
            notification_type == NotificationType.DYNAMIC
            and dynamic_images
            and base_config.get("ENABLE_DYNAMIC_IMAGE", False)
        ):
            logger.info(f"动态中包含 {len(dynamic_images)} 张图片，将一并发送")
            for img_url in dynamic_images:
                try:
                    # 下载图片
                    img_data = await fetch_image_bytes(img_url)
                    msg_list_content.append(img_data)
                    logger.debug(f"成功添加动态原图: {img_url}")
                except Exception as e:
                    logger.warning(f"下载动态原图失败: {img_url}, 错误: {e}")

        if is_new_video_pushed and video:
            video_url_for_msg = (
                f"https://www.bilibili.com/video/{video.get('bvid', '')}"
            )
            msg_list_content.append(f"\n视频链接: {video_url_for_msg}")
        elif notification_type == NotificationType.DYNAMIC and dynamic_upload_time > 0:
            dynamic_id = (await get_user_dynamics(sub.uid))["cards"][0]["desc"][
                "dynamic_id"
            ]
            msg_list_content.append(f"\n查看详情: https://t.bilibili.com/{dynamic_id}")

        if notification_type:
            notifications.append(
                Notification(content=msg_list_content, type=notification_type)
            )

    duration = time.time() - start_time
    if notifications:
        logger.info(
            f"UP主状态检查完成: UID={sub.uid}, 检测到更新, 耗时={duration:.2f}秒"
        )
    else:
        logger.debug(
            f"UP主状态检查完成: UID={sub.uid}, 未检测到更新, 耗时={duration:.2f}秒"
        )

    return notifications


async def get_user_dynamic(
    sub: BiliSub,
) -> tuple[bytes | None, int, str, list[str] | None]:
    """获取用户动态"""
    start_time = time.time()
    uid = sub.uid

    try:
        dynamic_info = await get_user_dynamics(uid)
    except json.JSONDecodeError as e:
        logger.error(
            f"获取用户动态时返回了非JSON内容 (可能被风控): UID={uid}, 异常信息={e}"
        )
        return None, 0, "", None
    except ResponseCodeException as e:
        logger.error(f"获取用户动态API错误: UID={uid}, Code={e.code}, Message={e.msg}")
        return None, 0, "", None
    except Exception as e:
        logger.error(
            f"获取用户动态异常: UID={uid}, 异常类型={type(e).__name__}, 异常信息={e}"
        )
        import traceback

        logger.debug(f"异常详细信息:\n{traceback.format_exc()}")
        return None, 0, "", None

    if not dynamic_info:
        logger.warning(f"获取到的动态数据为空: UID={uid}")
        return None, 0, "", None

    if not dynamic_info.get("cards"):
        logger.warning(
            f"获取到的动态数据中没有cards字段: UID={uid}, 数据={dynamic_info.keys()}"
        )
        return None, 0, "", None

    if not dynamic_info["cards"]:
        logger.debug(f"用户没有动态: UID={uid}")
        return None, 0, "", None

    dynamic_upload_time = dynamic_info["cards"][0]["desc"]["timestamp"]
    dynamic_id = dynamic_info["cards"][0]["desc"]["dynamic_id"]
    dynamic_time_str = datetime.fromtimestamp(dynamic_upload_time).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    logger.debug(
        f"最新动态信息: UID={uid}, 动态ID={dynamic_id}, 发布时间={dynamic_time_str}"
    )

    # 提取动态中的图片URL
    dynamic_images = []
    try:
        card = dynamic_info["cards"][0]
        card_str = card.get("card", "{}")

        # 解析卡片内容
        # 检查card_str是否已经是dict
        if isinstance(card_str, dict):
            card_data = card_str
        else:
            card_data = json.loads(card_str)

        # 提取不同类型的图片（仅提取用户自己的动态图片，不包括被转发的动态）
        if "item" in card_data:
            item = card_data["item"]
            # 提取图片
            if "pictures" in item:
                # 图文动态
                for pic in item["pictures"]:
                    if "img_src" in pic:
                        dynamic_images.append(pic["img_src"])
            elif "pic" in item:
                # 单图片动态
                dynamic_images.append(item["pic"])

    except Exception as e:
        logger.warning(f"解析动态图片时出错: {e}")

    if (
        sub.last_dynamic_timestamp is None
        or sub.last_dynamic_timestamp < dynamic_upload_time
    ):
        logger.info(
            f"检测到新动态: UID={uid}, 用户名={sub.uname}, 动态ID={dynamic_id}, 发布时间={dynamic_time_str}"
        )

        logger.debug(f"开始获取动态截图: UID={uid}, 动态ID={dynamic_id}")
        try:
            image = await get_dynamic_screenshot(dynamic_id)
            if image:
                logger.debug(
                    f"成功获取动态截图: UID={uid}, 动态ID={dynamic_id}, 图片大小={len(image)}字节"
                )

                duration = time.time() - start_time
                logger.info(
                    f"获取用户动态完成: UID={uid}, 检测到新动态, 耗时={duration:.2f}秒"
                )

                return (
                    image,
                    dynamic_upload_time,
                    f"https://t.bilibili.com/{dynamic_id}",
                    dynamic_images if dynamic_images else None,
                )
            else:
                logger.warning(f"动态截图获取失败: UID={uid}, 动态ID={dynamic_id}")
        except Exception as e:
            logger.error(
                f"获取动态截图异常: UID={uid}, 动态ID={dynamic_id}, 异常类型={type(e).__name__}, 异常信息={e}"
            )
            import traceback

            logger.debug(f"异常详细信息:\n{traceback.format_exc()}")
    else:
        logger.debug(
            f"未检测到新动态: UID={uid}, 最新动态时间={dynamic_time_str}, 本地记录时间={'无记录' if sub.last_dynamic_timestamp is None else datetime.fromtimestamp(sub.last_dynamic_timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
        )

    duration = time.time() - start_time
    logger.debug(f"获取用户动态完成: UID={uid}, 未检测到新动态, 耗时={duration:.2f}秒")
    return None, 0, "", None
