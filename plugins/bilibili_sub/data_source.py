import random
from asyncio.exceptions import TimeoutError
from datetime import datetime
from typing import Optional, Tuple

import nonebot
from bilireq.exceptions import ResponseCodeError

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.utils import ResourceDirManager
from zhenxun.utils._build_image import BuildImage

from .model import BilibiliSub
from .utils import get_meta, get_user_card, get_room_info_by_id, get_videos, get_user_dynamics, get_dynamic_screenshot
from ...utils.platform import PlatformUtils

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/all/v2"

DYNAMIC_PATH = IMAGE_PATH / "bilibili_sub" / "dynamic"
DYNAMIC_PATH.mkdir(exist_ok=True, parents=True)

ResourceDirManager.add_temp_dir(DYNAMIC_PATH)


async def add_live_sub(live_id: int, sub_user: str) -> str:
    """

    添加直播订阅
    :param live_id: 直播房间号
    :param sub_user: 订阅用户 id # 7384933:private or 7384933:2342344(group)
    :return:
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
            await _get_up_status(room_id)
            uname = (await BilibiliSub.get_or_none(sub_id=room_id)).uname
            return (
                "已成功订阅主播：\n"
                f"\ttitle：{title}\n"
                f"\tname： {uname}\n"
                f"\tlive_id：{room_id}\n"
                f"\tuid：{uid}"
            )
        else:
            return "添加订阅失败..."
    except Exception as e:
        logger.error(f"订阅主播live_id：{live_id} 发生了错误 {type(e)}：{e}")
    return "添加订阅失败..."


async def add_up_sub(uid: int, sub_user: str) -> str:
    """
    添加订阅 UP
    :param uid: UP uid
    :param sub_user: 订阅用户
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
            if e.code == -352:
                return f"风控校验失败，请联系管理员登录b站'"
            return "添加订阅失败..."
        dynamic_upload_time = 0
        if dynamic_info.get("cards"):
            dynamic_upload_time = dynamic_info["cards"][0]["desc"]["timestamp"]
        """bilibili_api.user库中User类的get_videos改为bilireq.user库的get_videos方法"""
        video_info = await get_videos(uid)
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
            return "已成功订阅UP：\n" f"\tname: {uname}\n" f"\tuid：{uid}"
        else:
            return "添加订阅失败..."
    except Exception as e:
        logger.error(f"订阅Up uid：{uid} 发生了错误 {type(e)}：{e}")
    return "添加订阅失败..."


async def add_season_sub(media_id: int, sub_user: str) -> str:
    """
    添加订阅 UP
    :param media_id: 番剧 media_id
    :param sub_user: 订阅用户
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
                "已成功订阅番剧：\n"
                f"\ttitle: {season_name}\n"
                f"\tcurrent_episode: {season_current_episode}"
            )
        else:
            return "添加订阅失败..."
    except Exception as e:
        logger.error(f"订阅番剧 media_id：{media_id} 发生了错误 {type(e)}：{e}")
    return "添加订阅失败..."


async def delete_sub(sub_id: str, sub_user: str) -> str:
    """
    删除订阅
    :param sub_id: 订阅 id
    :param sub_user: 订阅用户 id # 7384933:private or 7384933:2342344(group)
    """
    if await BilibiliSub.delete_bilibili_sub(int(sub_id), sub_user):
        return f"已成功取消订阅：{sub_id}"
    else:
        return f"取消订阅：{sub_id} 失败，请检查是否订阅过该Id...."


async def get_media_id(keyword: str) -> dict:
    """
    获取番剧的 media_id
    :param keyword: 番剧名称
    """
    from .auth import AuthManager
    params = {"keyword": keyword}
    for _ in range(3):
        try:
            _season_data = {}
            response = await AsyncHttpx.get(SEARCH_URL, params=params, cookies=AuthManager.get_cookies(), timeout=5)
            if response.status_code == 200:
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
        except TimeoutError:
            pass
        return {}


async def get_sub_status(id_: int, sub_type: str) -> list | None:
    """
    获取订阅状态
    :param id_: 订阅 id
    :param sub_type: 订阅类型
    """
    try:
        if sub_type == "live":
            return await _get_live_status(id_)
        elif sub_type == "up":
            return await _get_up_status(id_)
        elif sub_type == "season":
            return await _get_season_status(id_)
    except ResponseCodeError as msg:
        logger.info(f"Id：{id_} 获取信息失败...{msg}")
        return None
        # return f"Id：{id_} 获取信息失败...请检查订阅Id是否存在或稍后再试..."
    # except Exception as e:
    #     logger.error(f"获取订阅状态发生预料之外的错误 id_：{id_} {type(e)}：{e}")
    #     return "发生了预料之外的错误..请稍后再试或联系管理员....."


async def _get_live_status(id_: int) -> list:
    """
    获取直播订阅状态
    :param id_: 直播间 id
    """
    """bilibili_api.live库的LiveRoom类中get_room_info改为bilireq.live库的get_room_info_by_id方法"""
    live_info = await get_room_info_by_id(id_)
    title = live_info["title"]
    room_id = live_info["room_id"]
    live_status = live_info["live_status"]
    cover = live_info["user_cover"]
    sub = await BilibiliSub.get_or_none(sub_id=id_)
    msg_list = []
    if sub.live_status != live_status:
        await BilibiliSub.sub_handle(id_, live_status=live_status)
    if sub.live_status in [0, 2] and live_status == 1:
        msg_list = [BuildImage(cover), "\n"
                                       f"{sub.uname} 开播啦！\n"
                                       f"标题：{title}\n"
                                       f"直链：https://live.bilibili.com/{room_id}"]
        # return (
        #     f""
        #     f"{BuildImage(cover)}\n"
        #     f"{sub.uname} 开播啦！\n"
        #     f"标题：{title}\n"
        #     f"直链：https://live.bilibili.com/{room_id}"
        # )
    return msg_list


async def _get_up_status(id_: int) -> list:
    """
    获取用户投稿状态
    :param id_: 订阅 id
    :return:
    """
    _user = await BilibiliSub.get_or_none(sub_id=id_)
    """bilibili_api.user库中User类的get_user_info改为bilireq.user库的get_user_info方法"""
    user_info = await get_user_card(_user.uid)
    uname = user_info["name"]
    """bilibili_api.user库中User类的get_videos改为bilireq.user库的get_videos方法"""
    video_info = await get_videos(_user.uid)
    if not video_info.get('data'):
        str_msg = "b站订阅检测失败："
        if video_info['code'] == -352:
            str_msg +="风控校验失败，请登录后再尝试。发送'登录b站'"
        elif video_info['code'] == -799:
            str_msg += "请求过于频繁，请增加时长，更改配置文件下的'CHECK_TIME''"
        else:
            str_msg += f"{video_info['code']}，{video_info['message']}"
        bots = nonebot.get_bots()
        for bot in bots.values():
            if bot:
                await PlatformUtils.send_superuser(bot, str_msg)
        return []
    else:
        video_info = video_info['data']
    latest_video_created = 0
    video = None
    dividing_line = "\n-------------\n"
    if _user.uname != uname:
        await BilibiliSub.sub_handle(id_, uname=uname)
    dynamic_img, dynamic_upload_time, link = await get_user_dynamic(_user.uid, _user)
    if video_info["list"].get("vlist"):
        video = video_info["list"]["vlist"][0]
        latest_video_created = video["created"]
    rst = ""
    msg_list = []
    if dynamic_img:
        await BilibiliSub.sub_handle(id_, dynamic_upload_time=dynamic_upload_time)
        # rst += f"{uname} 发布了动态！\n" f"{dynamic_img}\n{link}"
        msg_list = [f"{uname} 发布了动态！\n", dynamic_img, f"\n{link}"]
    if (
            latest_video_created
            and _user.latest_video_created
            and video
            and _user.latest_video_created < latest_video_created
    ):
        await BilibiliSub.sub_handle(id_, latest_video_created=latest_video_created)
        # rst += (
        #     f'{BuildImage(video["pic"])}\n'
        #     f"{uname} 投稿了新视频啦\n"
        #     f'标题：{video["title"]}\n'
        #     f'Bvid：{video["bvid"]}\n'
        #     f'直链：https://www.bilibili.com/video/{video["bvid"]}'
        # )
        if msg_list:
            msg_list.append(dividing_line)
        msg_list.append(BuildImage(video["pic"]))
        msg_list.append(f"\n"
                        f"{uname} 投稿了新视频啦\n"
                        f'标题：{video["title"]}\n'
                        f'Bvid：{video["bvid"]}\n'
                        f'直链：https://www.bilibili.com/video/{video["bvid"]}')
    return msg_list


async def _get_season_status(id_) -> list:
    """
    获取 番剧 更新状态
    :param id_: 番剧 id
    """
    """bilibili_api.bangumi库中get_meta改为bilireq.bangumi库的get_meta方法"""
    season_info = await get_meta(id_)
    title = season_info["media"]["title"]
    _idx = (await BilibiliSub.get_or_none(sub_id=id_)).season_current_episode
    new_ep = season_info["media"]["new_ep"]["index"]
    msg_list = []
    if new_ep != _idx:
        await BilibiliSub.sub_handle(
            id_, season_current_episode=new_ep, season_update_time=datetime.now()
        )
        msg_list = [BuildImage(season_info["media"]["cover"]), '\n'
                                                               f"[{title}]更新啦\n"
                                                               f"最新集数：{new_ep}"']']
        # return (
        #     f'{BuildImage(season_info["media"]["cover"])}\n'
        #     f"[{title}]更新啦\n"
        #     f"最新集数：{new_ep}"
        # )
    return msg_list


async def get_user_dynamic(
        uid: int, local_user: BilibiliSub
) -> Tuple[bytes | None, int, str]:
    """
    获取用户动态
    :param uid: 用户uid
    :param local_user: 数据库存储的用户数据
    :return: 最新动态截图与时间
    """
    dynamic_info = await get_user_dynamics(uid)
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
        if not self.live_data or not self.up_data or not self.season_data:
            (
                _live_data,
                _up_data,
                _season_data,
            ) = await BilibiliSub.get_all_sub_data()
            if not self.live_data:
                self.live_data = _live_data
            if not self.up_data:
                self.up_data = _up_data
            if not self.season_data:
                self.season_data = _season_data

    async def random_sub_data(self) -> Optional[BilibiliSub]:
        """
        随机获取一条数据
        :return:
        """
        sub = None
        if not self.live_data and not self.up_data and not self.season_data:
            return sub
        self.current_index += 1
        if self.current_index == 0:
            if self.live_data:
                sub = random.choice(self.live_data)
                self.live_data.remove(sub)
        elif self.current_index == 1:
            if self.up_data:
                sub = random.choice(self.up_data)
                self.up_data.remove(sub)
        elif self.current_index == 2:
            if self.season_data:
                sub = random.choice(self.season_data)
                self.season_data.remove(sub)
        else:
            self.current_index = -1
        if sub:
            return sub
        await self.reload_sub_data()
        return await self.random_sub_data()
