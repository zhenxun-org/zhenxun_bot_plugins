import asyncio
from pathlib import Path
import time

from nonebot_plugin_uninfo import Uninfo
from tortoise.transactions import atomic

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .._data_source import CallApi, CsgoManager
from ..config import LOG_COMMAND, SAVE_PATH, PerfectWorldVideoListResult
from ..exceptions import SteamIdNotBoundException
from ..models.csgo_user import CsgoUser
from ..models.csgo_video import CsgoVideo

VIDEO_CACHE_DIR = SAVE_PATH / "videos"


class PerfectWorldVideoManager:
    @classmethod
    async def get_user_videos(
        cls,
        session: Uninfo,
        target_id: str | None,
        steam_id: str | None,
        is_query: bool = False,
    ) -> PerfectWorldVideoListResult | str:
        """获取玩家视频列表

        参数:
            session: Uninfo
            target_id: 用户ID
            steam_id: Steam ID，如果为None则尝试从数据库查询
            is_query: 是否查询其他人

        返回:
            视频列表数据，不等待保存完成
        """
        try:
            user_id = target_id or session.user.id

            # 如果steam_id为空，尝试从数据库查询
            if not steam_id:
                steam_id = await CsgoManager.get_steam_id_by_user_id(user_id)

            response = await CallApi.get_video_list(steam_id)

            asyncio.create_task(  # noqa: RUF006
                cls._save_user_videos(
                    user_id, steam_id, response.data, save_user_id=not is_query
                )
            )

            return response.data
        except SteamIdNotBoundException as e:
            logger.error("获取玩家视频列表失败", LOG_COMMAND, session=session, e=e)
            return e.message
        except Exception as e:
            logger.error(
                "获取玩家视频列表时发生错误",
                LOG_COMMAND,
                session=session,
                e=e,
            )
            return "获取玩家视频列表失败..."

    @classmethod
    @atomic()
    async def _save_user_videos(
        cls,
        user_id: str,
        steam_id: str,
        data: PerfectWorldVideoListResult,
        save_user_id: bool = True,
    ):
        """保存玩家完美时刻

        参数:
            user_id: 用户ID
            steam_id: Steam ID
            data: API返回的完美时刻
            save_user_id: 是否保存user_id，当通过steam_id查询时应设为False
        """
        try:
            # 查找现有用户
            existing_user = None
            if user_id and save_user_id:
                existing_user = await CsgoUser.get_or_none(user_id=user_id)

            if not existing_user:
                # 如果用户不存在，尝试通过steam_id查找
                existing_user = await CsgoUser.get_or_none(steam_id=steam_id)

            if existing_user:
                # 用户存在，更新信息
                user = existing_user
                if not user.steam_id:
                    user.steam_id = steam_id
                    await user.save()
            elif user_id and save_user_id:
                user = await CsgoUser.create(
                    user_id=user_id,
                    steam_id=steam_id,
                )
            else:
                # 只保存steam_id
                user = await CsgoUser.create(
                    steam_id=steam_id,
                )

            # 保存完美时刻
            if not data.user_video_list:
                logger.info(
                    f"玩家 {steam_id} 没有完美时刻", LOG_COMMAND, session=user_id
                )
                return

            # 获取已存在的视频ID列表
            db_video_ids = await CsgoVideo.filter(user_id=user.id).values_list(
                "video_id", flat=True
            )

            # 筛选出需要新建的视频
            new_videos_data = [
                v for v in data.user_video_list if v.vid not in db_video_ids
            ]

            if not new_videos_data:
                logger.info(
                    f"玩家 {steam_id} 没有新的完美时刻需要保存",
                    LOG_COMMAND,
                    session=user_id,
                )
                return

            # 准备批量创建的数据
            videos_to_create = []
            for video_data in new_videos_data:
                # 获取视频信息
                video_info = video_data.video_info
                play_info = (
                    video_info.play_info_list[0] if video_info.play_info_list else None
                )

                if not play_info:
                    logger.warning(f"视频 {video_data.vid} 没有播放信息")
                    continue

                # 创建视频记录对象
                videos_to_create.append(
                    CsgoVideo(
                        video_id=video_data.vid,
                        user=user,
                        platform_type=1,  # 1表示完美世界平台
                        match_id=video_data.match_id,
                        title=video_data.title or "",
                        short_title=video_data.short_title or "",
                        match_round=video_data.match_round,
                        match_time=video_data.match_time,
                        map_name=video_data.map_name or "",
                        map_url=video_data.map_url or "",
                        kill_count=video_data.kill_count,
                        versus_count=video_data.versus_count,
                        video_status=video_data.video_status,
                        video_reason=video_data.video_reason or "",
                        review_status=video_data.review_status,
                        review_reason=video_data.review_reason or "",
                        platform=video_data.platform,
                        video_type=video_data.type,
                        is_weekend_league=video_data.weekend_league,
                        is_album=video_data.album,
                        is_video_cut=video_data.video_cut,
                        width=play_info.width,
                        height=play_info.height,
                        size=play_info.size,
                        duration=play_info.duration,
                        format=play_info.format,
                        definition=play_info.definition,
                        play_url=play_info.play_url,
                    )
                )

            # 批量创建视频记录
            if videos_to_create:
                await CsgoVideo.bulk_create(videos_to_create)
                logger.info(
                    f"成功批量保存玩家 {steam_id}"
                    f" 的完美时刻，共 {len(videos_to_create)} 条",
                    LOG_COMMAND,
                    session=user_id,
                )
            else:
                logger.info(
                    f"玩家 {steam_id} 没有有效的完美时刻需要保存",
                    LOG_COMMAND,
                    session=user_id,
                )

        except Exception as e:
            logger.error("保存玩家完美时刻时发生错误", LOG_COMMAND, e=e)

    @classmethod
    async def download_video(cls, user_id: str, video_id: str) -> Path | None:
        """下载视频并缓存到本地

        参数:
            user_id: 用户ID
            video_id: 视频ID

        返回:
            本地缓存路径，如果下载失败则返回None
        """
        try:
            # 查找视频记录
            video = await CsgoVideo.get_or_none(video_id=video_id)
            if not video:
                logger.warning(f"视频 {video_id} 不存在", LOG_COMMAND, session=user_id)
                return None

            cache_dir = VIDEO_CACHE_DIR / f"{user_id}"
            cache_dir.mkdir(parents=True, exist_ok=True)

            if video.is_cached and video.local_path:
                # 检查文件是否存在
                if Path(video.local_path).exists():
                    return Path(video.local_path)
                video.is_cached = False
                video.local_path = ""
                await video.save()

            # 生成本地文件路径
            file_extension = video.format.lower()
            local_filename = f"{video.video_id}_{int(time.time())}.{file_extension}"
            local_path = str(cache_dir / local_filename)

            # 下载视频
            logger.info(f"开始下载视频 {video_id}")
            await AsyncHttpx.download_file(video.play_url, local_path)

            # 更新视频记录
            video.is_cached = True
            video.local_path = local_path
            await video.save()

            logger.info(
                f"成功下载视频 {video_id} 到 {local_path}",
                LOG_COMMAND,
                session=user_id,
            )
            return Path(local_path)

        except Exception as e:
            logger.error(
                f"下载视频 {video_id} 时发生错误", LOG_COMMAND, session=user_id, e=e
            )
            return None

    @classmethod
    async def clear_video_cache(
        cls, user_id: str | None, video_id: str | None = None
    ) -> int:
        """清除视频缓存

        参数:
            user_id: 用户ID
            video_id: 视频ID，如果为None则清除所有缓存

        返回:
            int: 清除的文件数量
        """
        try:
            count = 0
            if video_id:
                # 清除指定视频的缓存
                video = await CsgoVideo.get_or_none(video_id=video_id)
                local_path = Path(video.local_path) if video else None
                if video and video.is_cached and local_path:
                    if local_path.exists():
                        local_path.unlink()
                        count = 1
                    video.is_cached = False
                    # 使用空字符串代替None
                    video.local_path = ""
                    await video.save()
            elif user_id:
                # 清除用户所有缓存
                perfect_videos = await CsgoVideo.filter(
                    user__user_id=user_id, is_cached=True
                ).all()
                official_videos = await CsgoVideo.filter(
                    user__user_id=user_id, is_cached=True
                ).all()

                # 合并两个列表
                videos = perfect_videos + official_videos

                for video in videos:
                    local_path = Path(video.local_path) if video else None
                    if local_path and local_path.exists():
                        local_path.unlink()
                        count += 1
                    video.is_cached = False
                    video.local_path = ""

                if videos:
                    await CsgoVideo.bulk_update(videos, ["is_cached", "local_path"])
            else:
                # 清除所有缓存
                videos = await CsgoVideo.filter(is_cached=True).all()
                for video in videos:
                    local_path = Path(video.local_path) if video else None
                    if local_path and local_path.exists():
                        local_path.unlink()
                        count += 1
                    video.is_cached = False
                    # 使用空字符串代替None
                    video.local_path = ""
                # 批量更新
                if videos:
                    await CsgoVideo.bulk_update(videos, ["is_cached", "local_path"])

            logger.info(
                f"成功清除 {count} 个视频缓存",
                LOG_COMMAND,
                session=user_id,
            )
            return count

        except Exception as e:
            logger.error("清除视频缓存时发生错误", e=e)
            return 0

    @classmethod
    async def get_video_by_id(cls, db_id: str) -> CsgoVideo | None:
        """通过数据库ID获取视频信息

        参数:
            db_id: 数据库ID

        返回:
            CsgoVideo | None: 视频信息，如果不存在则返回None
        """
        try:
            # 从数据库查询视频信息
            return await CsgoVideo.get_or_none(id=db_id)
        except Exception as e:
            logger.error(f"通过ID查询视频信息失败: {db_id}", LOG_COMMAND, e=e)
            return None
