from datetime import datetime, timedelta, timezone
from pathlib import Path

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma, Video
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .._data_source import CsgoManager
from .._render import Renderer
from .._utils import SteamId, TargetId
from ..commands import _video_download_matcher, _video_matcher
from ..config import DEFAULT_AVATAR_URL, LOG_COMMAND
from ..exceptions import CsgoDataQueryException, SteamIdNotBoundException
from ..models.csgo_user import CsgoUser
from ..models.csgo_video import CsgoVideo
from .data_source import PerfectWorldVideoManager

# 定义上海时区（UTC+8）
SHANGHAI_TZ = timezone(timedelta(hours=8))


def format_datetime(dt: datetime) -> str:
    """
    将日期时间字符串转换为上海时区并格式化
    参数:
        dt: 日期
    返回:
        格式化后的日期时间字符串，如 "2025-03-09 22:20:35"
    """
    try:
        # 假设原始时间是UTC时间，转换为上海时区
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # 转换为上海时区
        dt_shanghai = dt.astimezone(SHANGHAI_TZ)

        # 格式化为易读的格式
        return dt_shanghai.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.error(f"日期时间格式化失败: {dt}", LOG_COMMAND, e=e)
        return str(dt)


__plugin_meta__ = PluginMetadata(
    name="完美时刻查询",
    description="查看和下载完美世界平台用户视频",
    usage="""
    指令：
        完美时刻 @/steamId
        完美时刻下载 视频ID前四位
        示例：
        完美时刻
        完美时刻 @笨蛋
        完美时刻 1231231233
        完美时刻下载 1234
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1.1", menu_type="CSGO"
    ).to_dict(),
)


@_video_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    target_id: str | None = TargetId(),
    steam_id: str | None = SteamId(),
):
    await MessageUtils.build_message("正在获取视频列表，请稍等...").send()
    user_id = session.user.id
    is_query = bool(steam_id or steam_id)

    try:
        # 确保player_name始终是字符串
        player_name = "未知玩家"
        if not is_query:
            player_name = session.user.name

        avatar_url = DEFAULT_AVATAR_URL
        if session.user.avatar:
            avatar_url = session.user.avatar

        # 如果是查询其他人
        if target_id and session.group:
            # 获取群内用户名
            user_info = await GroupInfoUser.get_or_none(
                user_id=target_id, group_id=session.group.id
            )
            if user_info:
                player_name = user_info.user_name

            if target_avatar := PlatformUtils.get_user_avatar_url(
                target_id, PlatformUtils.get_platform(session), session.self_id
            ):
                avatar_url = target_avatar

        if not target_id and steam_id:
            # 查询用户信息
            user = await CsgoUser.get_or_none(steam_id=steam_id)
            if user:
                player_name = user.perfect_name
                avatar_url = user.perfect_avatar_url

        if not steam_id:
            steam_id = await CsgoManager.get_steam_id_by_user_id(target_id or user_id)
        videos = await PerfectWorldVideoManager.get_user_videos(
            session, target_id, steam_id, is_query
        )
        if isinstance(videos, str):
            await MessageUtils.build_message(videos).send(reply_to=True)
            return

        if not videos or not videos.user_video_list:
            await MessageUtils.build_message("没有找到任何完美时刻").send(reply_to=True)
            return

        total_count = len(videos.user_video_list)

        processed_videos = []
        for video in videos.user_video_list:
            video_data = {
                "video_id": video.vid,
                "title": video.title or "无标题",
                "map_name": video.map_name or "未知地图",
                "kill_count": video.kill_count,
                "versus_count": video.versus_count,
                "match_round": video.match_round,
                "match_time": format_datetime(video.match_time),
                "cover_url": video.video_info.video_base.cover_url,
            }

            processed_videos.append(video_data)

        # 渲染视频列表图片
        image_bytes = await Renderer.render_video_list(
            video_list=processed_videos,
            player_name=player_name or "未知玩家",
            steam_id=steam_id,
            avatar_url=avatar_url or DEFAULT_AVATAR_URL,
            total_count=total_count,
        )

        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except SteamIdNotBoundException:
        await MessageUtils.build_message("请先绑定Steam ID").finish(reply_to=True)
    except CsgoDataQueryException as e:
        await MessageUtils.build_message(str(e)).finish(reply_to=True)
    except Exception as e:
        logger.error(
            "获取视频列表失败",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("获取视频列表失败，请稍后再试").send(
            reply_to=True
        )


@_video_download_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    video_id: str,
):
    await MessageUtils.build_message("正在下载视频，请稍等...").send(reply_to=True)
    user_id = session.user.id

    try:
        # 查询视频信息，根据视频ID前四位查找匹配的视频
        prefix = video_id[:4] if len(video_id) >= 4 else video_id

        # 从数据库查询匹配前缀的视频

        videos = await CsgoVideo.filter(video_id__startswith=prefix).limit(1).all()

        if not videos:
            await MessageUtils.build_message(f"未找到ID前缀为 {prefix} 的视频").send(
                reply_to=True
            )
            return

        video_info = videos[0]

        # 使用video_id字段下载视频
        video_path = await PerfectWorldVideoManager.download_video(
            user_id, video_info.video_id
        )

        if not video_path or not Path(video_path).exists():
            await MessageUtils.build_message("视频下载失败，请稍后再试").send(
                reply_to=True
            )
            return

        # 发送视频文件
        await MessageUtils.build_message(Video(path=video_path)).send()
    except Exception as e:
        logger.error(
            f"下载视频失败: {video_id}",
            arparma.header_result,
            session=session,
            e=e,
        )
        await MessageUtils.build_message("视频下载失败，请稍后再试").send(reply_to=True)
