import random
from datetime import datetime, timedelta

import nonebot
from bilireq.exceptions import ResponseCodeError
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.config import Config
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.platform import PlatformUtils

from .config import LOG_COMMAND, SEARCH_URL
from .filter import check_page_elements
from .model import BilibiliSub
from .utils import (
    get_dynamic_screenshot,
    get_meta,
    get_room_info_by_id,
    get_user_card,
    get_user_dynamics,
    get_videos,
)

base_config = Config.get("bilibili_sub")


async def handle_video_info_error(video_info: dict) -> str:
    """处理B站视频信息获取错误并发送通知给超级用户

    参数:
        video_info: 包含错误信息的字典
        platform_utils: 用于发送消息的工具类

    返回:
        str: 返回信息
    """
    str_msg = "b站订阅检测失败："
    if video_info["code"] == -352:
        str_msg += "风控校验失败，请登录后再尝试。发送'登录b站'"
    elif video_info["code"] == -799:
        str_msg += "请求过于频繁，请增加时长，更改配置文件下的'CHECK_TIME''"
    else:
        str_msg += f"{video_info['code']}，{video_info['message']}"

    bots = nonebot.get_bots()
    for bot in bots.values():
        if bot:
            await PlatformUtils.send_superuser(bot, str_msg)

    return str_msg


async def add_live_sub(session: Uninfo, live_id: int, sub_user: str) -> str:
    """添加直播订阅

    参数:
        live_id: 直播房间号
        sub_user: 订阅用户 id # 7384933:private or 7384933:2342344(group)

    返回:
        str: 订阅结果
    """
    try:
        try:
            """bilibili_api.live库的LiveRoom类中get_room_info改为bilireq.live库的get_room_info_by_id方法"""
            live_info = await get_room_info_by_id(live_id)
        except ResponseCodeError:
            return f"未找到房间号Id：{live_id} 的信息，请检查Id是否正确"
        uid = live_info["uid"]
        room_id = live_info["room_id"]
        short_id = live_info["short_id"]
        title = live_info["title"]
        live_status = live_info["live_status"]
        if await BilibiliSub.sub_handle(
            room_id,
            "live",
            sub_user,
            uid=uid,
            live_short_id=short_id,
            live_status=live_status,
        ):
            await _get_up_status(session, room_id)
            sub_data = await BilibiliSub.get_or_none(sub_id=room_id)
            if not sub_data:
                logger.debug(
                    f"未找到sub_id为{room_id}的数据", LOG_COMMAND, session=session
                )
                return "添加订阅失败..."
            return (
                "订阅成功！🎉\n"
                f"主播名称：{sub_data.uname}\n"
                f"直播标题：{title}\n"
                f"直播间ID：{room_id}\n"
                f"用户UID：{uid}"
            )
        else:
            return "数据添加失败，添加订阅失败..."
    except Exception as e:
        logger.error(
            f"订阅主播live_id：{live_id} 发生了错误", LOG_COMMAND, session=session, e=e
        )
    return "添加订阅失败..."


async def add_up_sub(session: Uninfo, uid: int, sub_user: str) -> str:
    """添加订阅 UP

    参数:
        uid: UP uid
        sub_user: 订阅用户

    返回:
        str: 订阅结果
    """
    try:
        try:
            """bilibili_api.user库中User类的get_user_info改为bilireq.user库的get_user_info方法"""
            user_info = await get_user_card(uid)
        except ResponseCodeError:
            return f"未找到UpId：{uid} 的信息，请检查Id是否正确"
        uname = user_info["name"]
        try:
            dynamic_info = await get_user_dynamics(uid)
        except ResponseCodeError as e:
            return (
                "风控校验失败，请联系管理员登录b站'"
                if e.code == -352
                else "添加订阅失败..."
            )
        dynamic_upload_time = 0
        if dynamic_info.get("cards"):
            dynamic_upload_time = dynamic_info["cards"][0]["desc"]["timestamp"]
        """bilibili_api.user库中User类的get_videos改为bilireq.user库的get_videos方法"""
        video_info = await get_videos(uid)
        if not video_info.get("data"):
            await handle_video_info_error(video_info)
            return "订阅失败，请联系管理员"
        else:
            video_info = video_info["data"]
        if video_info.get("code") != 0:
            return f"添加订阅失败，请联系管理员：{video_info.get('message', '')}"
        latest_video_created = 0
        if video_info["list"].get("vlist"):
            latest_video_created = video_info["list"]["vlist"][0]["created"]
        if await BilibiliSub.sub_handle(
            uid,
            "up",
            sub_user,
            uid=uid,
            uname=uname,
            dynamic_upload_time=dynamic_upload_time,
            latest_video_created=latest_video_created,
        ):
            return f"订阅成功！🎉\nUP主名称：{uname}\n用户UID：{uid}"
        else:
            return "添加订阅失败..."
    except Exception as e:
        logger.error(f"订阅Up uid：{uid} 发生了错误", LOG_COMMAND, session=session, e=e)
    return "添加订阅失败..."


async def add_season_sub(session: Uninfo, media_id: int, sub_user: str) -> str:
    """添加订阅 UP

    参数:
        media_id: 番剧 media_id
        sub_user: 订阅用户

    返回:
        str: 订阅结果
    """
    try:
        try:
            """bilibili_api.bangumi库中get_meta改为bilireq.bangumi库的get_meta方法"""
            season_info = await get_meta(media_id)
        except ResponseCodeError:
            return f"未找到media_id：{media_id} 的信息，请检查Id是否正确"
        season_id = season_info["media"]["season_id"]
        season_current_episode = season_info["media"]["new_ep"]["index"]
        season_name = season_info["media"]["title"]
        if await BilibiliSub.sub_handle(
            media_id,
            "season",
            sub_user,
            season_name=season_name,
            season_id=season_id,
            season_current_episode=season_current_episode,
        ):
            return (
                "订阅成功！🎉\n"
                f"番剧名称：{season_name}\n"
                f"当前集数：{season_current_episode}"
            )
        else:
            return "添加订阅失败..."
    except Exception as e:
        logger.error(
            f"订阅番剧 media_id：{media_id} 发生了错误",
            LOG_COMMAND,
            session=session,
            e=e,
        )
    return "添加订阅失败..."


async def delete_sub(sub_id: str, sub_user: str) -> str:
    """删除订阅

    参数:
        sub_id: 订阅 id
        sub_user: 订阅用户 id # 7384933:private or 7384933:2342344(group)

    返回:
        str: 删除结果
    """
    if await BilibiliSub.delete_bilibili_sub(int(sub_id), sub_user):
        return f"已成功取消订阅：{sub_id}"
    else:
        return f"取消订阅：{sub_id} 失败，请检查是否订阅过该Id...."


@Retry.api()
async def get_media_id(keyword: str) -> dict | None:
    """获取番剧的 media_id

    参数:
        keyword: 番剧名称

    返回:
        dict: 番剧信息
    """
    from .auth import AuthManager

    params = {"keyword": keyword}
    _season_data = {}
    response = await AsyncHttpx.get(
        SEARCH_URL, params=params, cookies=AuthManager.get_cookies(), timeout=5
    )
    response.raise_for_status()
    data = response.json()
    if data.get("data"):
        for item in data["data"]["result"]:
            if item["result_type"] == "media_bangumi":
                idx = 0
                for x in item["data"]:
                    _season_data[idx] = {
                        "media_id": x["media_id"],
                        "title": x["title"]
                        .replace('<em class="keyword">', "")
                        .replace("</em>", ""),
                    }
                    idx += 1
                return _season_data
    return {}


async def get_sub_status(
    session: Uninfo | None, sub_id: int, sub_type: str
) -> list | None:
    """获取订阅状态

    参数:
        sub_id: 订阅 id
        sub_type: 订阅类型

    返回:
        list: 订阅状态
    """
    try:
        if sub_type == "live":
            return await _get_live_status(session, sub_id)
        elif sub_type == "up":
            return await _get_up_status(session, sub_id)
        elif sub_type == "season":
            return await _get_season_status(session, sub_id)
    except ResponseCodeError as e:
        logger.error(f"Id：{sub_id} 获取信息失败...", LOG_COMMAND, session=session, e=e)
        return None


async def _get_live_status(session: Uninfo | None, sub_id: int) -> list:
    """获取直播订阅状态

    参数:
        session: Uninfo
        sub_id: 直播间 id

    返回:
        list: 直播状态
    """
    """bilibili_api.live库的LiveRoom类中get_room_info改为bilireq.live库的get_room_info_by_id方法"""
    live_info = await get_room_info_by_id(sub_id)
    title = live_info["title"]
    room_id = live_info["room_id"]
    live_status = live_info["live_status"]
    cover = live_info["user_cover"]
    sub_data = await BilibiliSub.get_or_none(sub_id=sub_id)
    if not sub_data:
        return ["该直播间未订阅，数据不存在"]
    msg_list = []
    image = None
    if sub_data.live_status != live_status:
        await BilibiliSub.sub_handle(sub_id, live_status=live_status)
        try:
            image_bytes = await AsyncHttpx.get_content(cover)
            image = BuildImage(background=image_bytes)
        except Exception as e:
            logger.error(
                f"下载图片构造失败: {cover}", LOG_COMMAND, session=session, e=e
            )
    if sub_data.live_status in [0, 2] and live_status == 1 and image:
        msg_list = [
            image,
            "\n",
            f"{sub_data.uname} 开播啦！🎉\n",
            f"标题：{title}\n",
            f"直播间链接：https://live.bilibili.com/{room_id}",
        ]
    return msg_list


async def _get_up_status(session: Uninfo | None, sub_id: int) -> list:
    # 获取当前时间戳
    current_time = datetime.now()

    sub_data = await BilibiliSub.get_or_none(sub_id=sub_id)
    if not sub_data:
        return ["该用户未订阅，数据不存在"]
    user_info = await get_user_card(sub_data.uid)
    uname = user_info["name"]

    # 获取用户视频信息
    video_info = await get_videos(sub_data.uid)
    if not video_info.get("data"):
        await handle_video_info_error(video_info)
        return []
    video_info = video_info["data"]

    # 初始化消息列表和时间阈值（30分钟）
    msg_list = []
    time_threshold = current_time - timedelta(minutes=30)
    dividing_line = "\n-------------\n"

    # 处理用户名更新
    if sub_data.uname != uname:
        await BilibiliSub.sub_handle(sub_id, uname=uname)

    # 处理动态信息
    dynamic_img = None
    try:
        dynamic_img, dynamic_upload_time, link = await get_user_dynamic(
            session, sub_data.uid, sub_data
        )
    except ResponseCodeError as e:
        logger.error(f"Id：{sub_id} 动态获取失败...", LOG_COMMAND, session=session, e=e)
        return [f"Id：{sub_id} 动态获取失败..."]

    # 动态时效性检查
    if dynamic_img and sub_data.dynamic_upload_time < dynamic_upload_time:
        dynamic_time = datetime.fromtimestamp(dynamic_upload_time)
        if dynamic_time > time_threshold:  # 30分钟内动态
            # 检查动态是否含广告
            if base_config.get("SLEEP_END_TIME"):
                if await check_page_elements(link):
                    await BilibiliSub.sub_handle(
                        sub_id, dynamic_upload_time=dynamic_upload_time
                    )
                    return msg_list  # 停止执行

            await BilibiliSub.sub_handle(
                sub_id, dynamic_upload_time=dynamic_upload_time
            )
            msg_list = [f"{uname} 发布了动态！📢\n", dynamic_img, f"\n查看详情：{link}"]
        else:  # 超过30分钟仍更新时间戳避免重复处理
            await BilibiliSub.sub_handle(
                sub_id, dynamic_upload_time=dynamic_upload_time
            )

    # 处理视频信息
    video = None
    if video_info["list"].get("vlist"):
        video = video_info["list"]["vlist"][0]
        latest_video_created = video.get("created", 0)
        sub_latest_video_created = sub_data.latest_video_created or 0

        # 视频时效性检查
        if (
            latest_video_created
            and sub_latest_video_created < latest_video_created
            and datetime.fromtimestamp(latest_video_created) > time_threshold
        ):
            # 检查视频链接是否被拦截
            video_url = f"https://www.bilibili.com/video/{video['bvid']}"

            # 带重试的封面获取
            image = None
            try:
                image_bytes = await AsyncHttpx.get_content(video["pic"])
                image = BuildImage(background=image_bytes)
            except Exception as e:
                logger.error(
                    f"下载图片构造失败: {video['pic']}",
                    LOG_COMMAND,
                    session=session,
                    e=e,
                )

            # 构建消息内容
            video_msg = [
                f"{uname} 投稿了新视频啦！🎉\n",
                f"标题：{video['title']}\n",
                f"Bvid：{video['bvid']}\n",
                f"链接：{video_url}",
            ]

            # 合并动态和视频消息
            if msg_list and image:
                msg_list += [dividing_line, image, *video_msg]
            elif image:  # 仅有视频更新
                msg_list = [image, *video_msg]
            elif msg_list:  # 有动态但无封面
                msg_list += [dividing_line, *video_msg]
            else:  # 仅有无封面视频
                msg_list = ["⚠️ 封面获取失败，但仍需通知：", *video_msg]

            # 强制更新视频时间戳
            await BilibiliSub.sub_handle(
                sub_id, latest_video_created=latest_video_created
            )

        elif latest_video_created > sub_latest_video_created:  # 超时视频仍更新时间戳
            await BilibiliSub.sub_handle(
                sub_id, latest_video_created=latest_video_created
            )

    return msg_list


async def _get_season_status(session: Uninfo | None, sub_id: int) -> list:
    """获取 番剧 更新状态

    参数:
        session: Uninfo
        sub_id: 番剧 id

    返回:
        list: 消息列表
    """
    """bilibili_api.bangumi库中get_meta改为bilireq.bangumi库的get_meta方法"""
    sub_data = await BilibiliSub.get_or_none(sub_id=sub_id)
    if not sub_data:
        return ["该用户未订阅，数据不存在"]
    season_info = await get_meta(sub_id)
    title = season_info["media"]["title"]
    index = sub_data.season_current_episode
    new_ep = season_info["media"]["new_ep"]["index"]
    msg_list = []
    if new_ep != index:
        image = None
        try:
            image_bytes = await AsyncHttpx.get_content(season_info["media"]["cover"])
            image = BuildImage(background=image_bytes)
        except Exception as e:
            logger.error(
                f"图片下载失败: {season_info['media']['cover']}",
                LOG_COMMAND,
                session=session,
                e=e,
            )
        if image:
            await BilibiliSub.sub_handle(
                sub_id, season_current_episode=new_ep, season_update_time=datetime.now()
            )
            msg_list = [
                image,
                "\n",
                f"[{title}] 更新啦！🎉\n",
                f"最新集数：{new_ep}",
            ]
    return msg_list


async def get_user_dynamic(
    session: Uninfo, uid: int, local_user: BilibiliSub
) -> tuple[bytes | None, int, str]:
    """获取用户动态

    参数:
        session: Uninfo
        uid: 用户uid
        local_user: 数据库存储的用户数据

    返回:
        tuple[bytes | None, int, str]: 最新动态截图与时间
    """
    try:
        dynamic_info = await get_user_dynamics(uid)
    except Exception:
        return None, 0, ""
    if dynamic_info:
        if dynamic_info.get("cards"):
            dynamic_upload_time = dynamic_info["cards"][0]["desc"]["timestamp"]
            dynamic_id = dynamic_info["cards"][0]["desc"]["dynamic_id"]
            if local_user.dynamic_upload_time < dynamic_upload_time:
                image = await get_dynamic_screenshot(dynamic_id)
                return (
                    image,
                    dynamic_upload_time,
                    f"https://t.bilibili.com/{dynamic_id}",
                )
    return None, 0, ""


class SubManager:
    def __init__(self):
        self.live_data = []
        self.up_data = []
        self.season_data = []
        self.current_index = -1

    async def reload_sub_data(self):
        """
        重载数据
        """
        # 如果 live_data、up_data 和 season_data 全部为空，重新加载所有数据
        if not (self.live_data and self.up_data and self.season_data):
            (
                self.live_data,
                self.up_data,
                self.season_data,
            ) = await BilibiliSub.get_all_sub_data()

    async def random_sub_data(self) -> BilibiliSub | None:
        """
        随机获取一条数据，保证所有 data 都轮询一次后再重载
        :return: Optional[BilibiliSub]
        """
        sub = None

        # 计算所有数据的总量，确保所有数据轮询完毕后再考虑重载
        total_data = sum(
            [len(self.live_data), len(self.up_data), len(self.season_data)]
        )

        # 如果所有列表都为空，重新加载一次数据以保证数据库非空
        if total_data == 0:
            await self.reload_sub_data()
            total_data = sum(
                [len(self.live_data), len(self.up_data), len(self.season_data)]
            )
            if total_data == 0:
                return sub

        attempts = 0

        # 开始轮询，直到所有数据都被遍历一次
        while attempts < total_data:
            self.current_index = (self.current_index + 1) % 3  # 轮询 0, 1, 2 之间

            # 根据 current_index 从相应的列表中随机取出数据
            if self.current_index == 0 and self.live_data:
                sub = random.choice(self.live_data)
                self.live_data.remove(sub)
                attempts += 1  # 成功从 live_data 获取数据
            elif self.current_index == 1 and self.up_data:
                sub = random.choice(self.up_data)
                self.up_data.remove(sub)
                attempts += 1  # 成功从 up_data 获取数据
            elif self.current_index == 2 and self.season_data:
                sub = random.choice(self.season_data)
                self.season_data.remove(sub)
                attempts += 1  # 成功从 season_data 获取数据

            # 如果成功找到数据，立即返回
            if sub:
                return sub
