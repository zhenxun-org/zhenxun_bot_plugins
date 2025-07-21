import asyncio
from typing import Dict, Any, Optional, List

import aiohttp
from bilibili_api import exceptions as BiliExceptions
from bilibili_api import live, video, article, user

from zhenxun.services.log import logger
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.http_utils import AsyncHttpx

from ..config import get_credential
from ..model import (
    Owner,
    Stat,
    VideoInfo,
    LiveInfo,
    UserInfo,
    UserStat,
    SeasonInfo,
    SeasonStat,
    ArticleInfo,
)

from ..utils.exceptions import (
    BilibiliRequestError,
    BilibiliResponseError,
    ResourceNotFoundError,
    ResourceForbiddenError,
    UrlParseError,
    RateLimitError,
)


RETRYABLE_EXCEPTIONS = (
    BiliExceptions.NetworkException,
    aiohttp.ClientError,
    asyncio.TimeoutError,
    RateLimitError,
)


class BilibiliApiService:
    """B站API服务"""

    @staticmethod
    def _create_video_instance(vid: str) -> video.Video:
        """创建Video实例"""
        if vid.lower().startswith("av"):
            try:
                aid = int(vid[2:])
                return video.Video(aid=aid, credential=get_credential())
            except ValueError:
                raise UrlParseError(f"无效的av号: {vid}")
        elif vid.upper().startswith("BV"):
            return video.Video(bvid=vid, credential=get_credential())
        else:
            raise UrlParseError(f"无效的视频ID格式: {vid}")

    @staticmethod
    def _map_video_info_to_model(info: Dict[str, Any], parsed_url: str) -> VideoInfo:
        """将API返回的视频信息映射到VideoInfo模型"""
        owner = Owner(
            mid=info["owner"]["mid"],
            name=info["owner"]["name"],
            face=info["owner"]["face"],
        )

        stat = Stat(
            aid=info["stat"]["aid"],
            view=info["stat"]["view"],
            danmaku=info["stat"]["danmaku"],
            reply=info["stat"]["reply"],
            favorite=info["stat"]["favorite"],
            coin=info["stat"]["coin"],
            share=info["stat"]["share"],
            now_rank=info["stat"]["now_rank"],
            his_rank=info["stat"]["his_rank"],
            like=info["stat"]["like"],
            dislike=info["stat"]["dislike"],
        )

        video_model = VideoInfo(
            bvid=info["bvid"],
            aid=info["aid"],
            videos=info["videos"],
            tid=info["tid"],
            tname=info["tname"],
            copyright=info["copyright"],
            pic=info["pic"],
            title=info["title"],
            pubdate=info["pubdate"],
            ctime=info["ctime"],
            desc=info["desc"],
            state=info["state"],
            duration=info["duration"],
            rights=info["rights"],
            owner=owner,
            stat=stat,
            dynamic=info["dynamic"],
            cid=info["cid"],
            dimension=info["dimension"],
            parsed_url=parsed_url,
        )

        if "pages" in info:
            video_model.pages = info["pages"]
        if "short_link_v2" in info:
            video_model.short_link_v2 = info["short_link_v2"]
        if "first_frame" in info:
            video_model.first_frame = info["first_frame"]

        return video_model

    @staticmethod
    def _map_live_info_to_model(info: Dict[str, Any], parsed_url: str) -> LiveInfo:
        """将API返回的直播间信息映射到LiveInfo模型"""
        room_info = info["room_info"]
        anchor_info = info.get("anchor_info", {}).get("base_info", {})

        live_model = LiveInfo(
            room_id=room_info["room_id"],
            short_id=room_info["short_id"],
            uid=room_info["uid"],
            title=room_info["title"],
            cover=room_info["cover"],
            live_status=room_info["live_status"],
            live_start_time=room_info.get("live_start_time", 0),
            area_id=room_info["area_id"],
            area_name=room_info["area_name"],
            parent_area_id=room_info["parent_area_id"],
            parent_area_name=room_info["parent_area_name"],
            description=room_info.get("description", ""),
            parsed_url=parsed_url,
        )

        if anchor_info:
            live_model.uname = anchor_info.get("uname", "")
            live_model.face = anchor_info.get("face", "")

        live_model.room_url = f"https://live.bilibili.com/{room_info['room_id']}"
        live_model.space_url = f"https://space.bilibili.com/{room_info['uid']}"

        if "keyframe" in room_info:
            live_model.keyframe_url = room_info["keyframe"]

        return live_model

    @staticmethod
    async def get_video_info(vid: str, parsed_url: str) -> VideoInfo:
        """获取视频信息"""
        logger.debug(f"获取视频信息: {vid}, URL: {parsed_url}", "B站解析")

        try:
            v = BilibiliApiService._create_video_instance(vid)

            logger.debug(f"使用bilibili-api获取视频信息: {vid}", "B站解析")
            info = await v.get_info()

            if not info or "bvid" not in info:
                logger.warning(f"视频未找到: {vid}", "B站解析")
                raise ResourceNotFoundError(f"视频未找到: {vid}")

            logger.debug(f"创建VideoInfo模型: {vid}", "B站解析")
            video_model = BilibiliApiService._map_video_info_to_model(info, parsed_url)

            logger.debug(f"视频信息获取成功: {video_model.title}", "B站解析")
            return video_model

        # 新增的异常捕获块，用于处理无效的视频ID
        except BiliExceptions.ArgsException as e:
            logger.error(f"Bilibili-api参数错误 ({vid}): {e}", "B站解析")
            raise UrlParseError(
                f"视频ID格式错误: {vid}",
                cause=e,
                context={"vid": vid, "url": parsed_url},
            )
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"视频未找到: {vid}", context={"vid": vid, "url": parsed_url}
            )
        except BiliExceptions.ApiException as e:
            logger.error(
                f"B站API错误 ({vid}): 代码 {e.code}, 消息: {e.message}", "B站解析"
            )

            if e.code == -403:
                raise ResourceForbiddenError(
                    f"视频访问被禁止 ({vid}): {e.message}",
                    cause=e,
                    context={"vid": vid, "url": parsed_url, "code": e.code},
                )
            elif e.code == -404:
                raise ResourceNotFoundError(
                    f"视频未找到 ({vid}): {e.message}",
                    cause=e,
                    context={"vid": vid, "url": parsed_url, "code": e.code},
                )
            elif e.code == -412:
                raise RateLimitError(
                    f"请求频率过高 ({vid}): {e.message}",
                    retry_after=60,
                    context={"vid": vid, "url": parsed_url, "code": e.code},
                )
            else:
                raise BilibiliResponseError(
                    f"B站API错误 ({vid}): 代码 {e.code}, 消息: {e.message}",
                    cause=e,
                    context={"vid": vid, "url": parsed_url, "code": e.code},
                )

        except BiliExceptions.NetworkException as e:
            logger.error(f"获取视频信息网络错误 ({vid}): {e}", "B站解析")
            raise BilibiliRequestError(
                f"获取视频信息网络错误 ({vid}): {e}",
                cause=e,
                context={"vid": vid, "url": parsed_url},
            )

        except Exception as e:
            logger.error(f"获取视频信息失败 ({vid}): {e}", "B站解析")
            raise BilibiliResponseError(
                f"获取视频信息意外错误 ({vid}): {e}",
                cause=e,
                context={"vid": vid, "url": parsed_url},
            )

    @staticmethod
    async def get_live_info(room_id: int, parsed_url: str) -> LiveInfo:
        """获取直播间信息"""
        logger.debug(f"获取直播间信息: {room_id}", "B站解析")

        try:
            room = live.LiveRoom(room_display_id=room_id, credential=get_credential())

            logger.debug(f"使用bilibili-api获取直播间信息: {room_id}", "B站解析")
            info = await room.get_room_info()

            if not info or "room_info" not in info:
                logger.warning(f"直播间未找到或响应无效: {room_id}", "B站解析")
                raise ResourceNotFoundError(f"直播间信息未找到或响应无效: {room_id}")

            logger.debug(f"创建LiveInfo模型: {room_id}", "B站解析")
            live_model = BilibiliApiService._map_live_info_to_model(info, parsed_url)

            logger.debug(f"直播间信息获取成功: {live_model.title}", "B站解析")
            return live_model

        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"直播间未找到: {room_id}",
                context={"room_id": room_id, "url": parsed_url},
            )
        except BiliExceptions.ApiException as e:
            logger.error(
                f"B站API错误 (直播间 {room_id}): 代码 {e.code}, 消息: {e.message}",
                "B站解析",
            )

            if e.code == -403:
                raise ResourceForbiddenError(
                    f"直播间访问被禁止 ({room_id}): {e.message}",
                    cause=e,
                    context={"room_id": room_id, "url": parsed_url, "code": e.code},
                )
            elif e.code == -404:
                raise ResourceNotFoundError(
                    f"直播间未找到 ({room_id}): {e.message}",
                    cause=e,
                    context={"room_id": room_id, "url": parsed_url, "code": e.code},
                )
            elif e.code == -412:
                raise RateLimitError(
                    f"请求频率过高 ({room_id}): {e.message}",
                    retry_after=60,
                    context={"room_id": room_id, "url": parsed_url, "code": e.code},
                )
            else:
                raise BilibiliResponseError(
                    f"B站API错误 (直播间 {room_id}): 代码 {e.code}, 消息: {e.message}",
                    cause=e,
                    context={"room_id": room_id, "url": parsed_url, "code": e.code},
                )

        except BiliExceptions.NetworkException as e:
            logger.error(f"获取直播间信息网络错误 ({room_id}): {e}", "B站解析")
            raise BilibiliRequestError(
                f"获取直播间信息网络错误 ({room_id}): {e}",
                cause=e,
                context={"room_id": room_id, "url": parsed_url},
            )

        except Exception as e:
            logger.error(f"获取直播间信息失败 ({room_id}): {e}", "B站解析")
            raise BilibiliResponseError(
                f"获取直播间信息意外错误 ({room_id}): {e}",
                cause=e,
                context={"room_id": room_id, "url": parsed_url},
            )

    @staticmethod
    @Retry.api(exception=RETRYABLE_EXCEPTIONS)
    async def get_article_info(cv_id: str, parsed_url: str) -> ArticleInfo:
        """获取专栏文章信息"""
        logger.debug(f"获取专栏信息: {cv_id}", "B站解析")
        context = {"cv_id": cv_id, "url": parsed_url}

        try:
            article_id_int: int
            if cv_id.lower().startswith("cv"):
                try:
                    article_id_int = int(cv_id[2:])
                except ValueError:
                    raise UrlParseError(f"无效的专栏ID格式: {cv_id}", context=context)
            else:
                raise UrlParseError(f"专栏ID必须以 'cv' 开头: {cv_id}", context=context)

            art = article.Article(cvid=article_id_int, credential=get_credential())

            logger.debug(f"获取专栏基础信息: cv{article_id_int}", "B站解析")
            info_data = await art.get_info()
            if not info_data:
                raise ResourceNotFoundError(
                    f"获取专栏基础信息失败或为空: {cv_id}", context=context
                )

            title = info_data.get("title", "")
            author_name = info_data.get("author_name", "")

            logger.debug(f"获取专栏 Markdown 内容: cv{article_id_int}", "B站解析")
            await art.fetch_content()
            markdown_content = art.markdown()

            article_info = ArticleInfo(
                id=cv_id,
                type="article",
                url=parsed_url,
                title=title,
                author=author_name,
                markdown_content=markdown_content,
            )
            logger.debug(f"专栏信息获取成功: {title}", "B站解析")
            return article_info

        except BiliExceptions.ApiException as e:
            logger.error(
                f"B站API错误 (专栏 {cv_id}): 代码 {e.code}, 消息: {e.message}",
                "B站解析",
            )
            context["code"] = e.code
            if e.code == -404 or "获取信息失败" in str(e):
                raise ResourceNotFoundError(
                    f"专栏未找到: {cv_id}", cause=e, context=context
                )
            else:
                raise BilibiliResponseError(
                    f"B站API错误: {e.message}", cause=e, context=context
                )
        except BiliExceptions.NetworkException as e:
            logger.error(f"获取专栏信息网络错误 ({cv_id}): {e}", "B站解析")
            raise BilibiliRequestError(
                f"获取专栏信息网络错误: {e}", cause=e, context=context
            )
        except Exception as e:
            logger.error(f"获取专栏信息失败 ({cv_id}): {e}", "B站解析")
            raise BilibiliResponseError(
                f"获取专栏信息意外错误: {e}", cause=e, context=context
            )

    @staticmethod
    @Retry.api(exception=RETRYABLE_EXCEPTIONS)
    async def get_user_info(uid: int, parsed_url: str) -> UserInfo:
        """获取用户空间信息"""
        logger.debug(f"获取用户信息: {uid}", "B站解析")
        context = {"uid": uid, "url": parsed_url}

        try:
            user_instance = user.User(uid=uid, credential=get_credential())

            logger.debug(f"并发获取用户核心信息、关系信息、UP主统计: {uid}", "B站解析")
            results = await asyncio.gather(
                user_instance.get_user_info(),
                user_instance.get_relation_info(),
                user_instance.get_up_stat(),
                return_exceptions=True,
            )

            user_info_data: Optional[Dict[str, Any]] = None
            relation_info_data: Optional[Dict[str, Any]] = None
            up_stat_data: Optional[Dict[str, Any]] = None
            errors = []

            if isinstance(results[0], Exception):
                errors.append(f"get_user_info 失败: {results[0]}")
                logger.error("获取 user_info 失败", e=results[0])
            else:
                user_info_data = results[0]

            if isinstance(results[1], Exception):
                errors.append(f"get_relation_info 失败: {results[1]}")
                logger.error("获取 relation_info 失败", e=results[1])
            else:
                relation_info_data = results[1]

            if isinstance(results[2], Exception):
                errors.append(f"get_up_stat 失败: {results[2]}")
                logger.error("获取 up_stat 失败", e=results[2])
            else:
                up_stat_data = results[2]

            if not user_info_data:
                error_msg = ", ".join(errors)
                if any("-404" in str(e) for e in results if isinstance(e, Exception)):
                    raise ResourceNotFoundError(
                        f"用户未找到: {uid}",
                        cause=results[0] if errors else None,
                        context=context,
                    )
                raise BilibiliResponseError(
                    f"获取用户核心信息失败: {error_msg}",
                    cause=results[0] if errors else None,
                    context=context,
                )

            stat = UserStat(
                following=relation_info_data.get("following", 0)
                if relation_info_data
                else 0,
                follower=relation_info_data.get("follower", 0)
                if relation_info_data
                else 0,
                archive_view=up_stat_data.get("archive", {}).get("view", 0)
                if up_stat_data
                else 0,
                article_view=up_stat_data.get("article", {}).get("view", 0)
                if up_stat_data
                else 0,
                likes=up_stat_data.get("likes", 0) if up_stat_data else 0,
            )

            live_room_info = user_info_data.get("live_room", {})
            user_model = UserInfo(
                mid=user_info_data.get("mid", uid),
                name=user_info_data.get("name", ""),
                face=user_info_data.get("face", ""),
                sign=user_info_data.get("sign", ""),
                level=user_info_data.get("level", 0),
                sex=user_info_data.get("sex", "保密"),
                birthday=user_info_data.get("birthday", ""),
                top_photo=user_info_data.get("top_photo", ""),
                live_room_status=live_room_info.get("liveStatus", 0),
                live_room_url="https:" + live_room_info.get("url", "")
                if live_room_info.get("url")
                else "",
                live_room_title=live_room_info.get("title", ""),
                stat=stat,
                parsed_url=parsed_url,
            )

            logger.debug(f"用户信息获取成功: {user_model.name}", "B站解析")
            if errors:
                logger.warning(f"获取用户 {uid} 部分信息失败: {', '.join(errors)}")

            return user_model

        except ResourceNotFoundError:
            raise
        except ResourceForbiddenError:
            raise
        except BilibiliResponseError:
            raise
        except BilibiliRequestError:
            raise
        except Exception as e:
            logger.error(f"获取用户信息失败 ({uid}): {e}", "B站解析")
            raise BilibiliResponseError(
                f"获取用户信息意外错误 ({uid}): {e}",
                cause=e,
                context={"uid": uid, "url": parsed_url},
            )

    @staticmethod
    def _map_season_info_to_model(
        result: Dict[str, Any], parsed_url: str, target_ep_id: Optional[int] = None
    ) -> SeasonInfo:
        """将API返回的番剧信息映射到SeasonInfo模型"""
        stat_data = result.get("stat", {})
        stat = SeasonStat(
            views=stat_data.get("views", 0),
            danmakus=stat_data.get("danmakus", 0),
            reply=stat_data.get("reply", 0),
            favorites=stat_data.get("favorites", 0),
            coins=stat_data.get("coins", 0),
            share=stat_data.get("share", 0),
            likes=stat_data.get("likes", 0),
        )
        rating_data = result.get("rating", {})
        styles_data = result.get("styles", [])
        styles_str = ""
        if isinstance(styles_data, list):
            styles_str = ", ".join(str(style) for style in styles_data if style)
        elif styles_data:
            styles_str = str(styles_data)

        season_model = SeasonInfo(
            season_id=result.get("season_id", 0),
            media_id=result.get("media_id", 0),
            title=result.get("title", ""),
            cover=result.get("cover", ""),
            desc=result.get("evaluate", ""),
            type_name=result.get("type_name", ""),
            areas=", ".join(
                [
                    area.get("name", "")
                    for area in result.get("areas", [])
                    if isinstance(area, dict)
                ]
            ),
            styles=styles_str,
            publish=result.get("publish", {}),
            rating_score=rating_data.get("score", 0.0) if rating_data else 0.0,
            rating_count=rating_data.get("count", 0) if rating_data else 0,
            stat=stat,
            total_ep=len(result.get("episodes", [])),
            status=result.get("status", 0),
            parsed_url=parsed_url,
        )

        if target_ep_id:
            episodes: List[Dict[str, Any]] = result.get("episodes", [])
            for episode in episodes:
                if (
                    episode.get("ep_id") == target_ep_id
                    or episode.get("id") == target_ep_id
                ):
                    season_model.target_ep_id = target_ep_id
                    season_model.target_ep_title = episode.get("title", "")
                    season_model.target_ep_long_title = episode.get("long_title", "")
                    season_model.target_ep_cover = episode.get("cover", "")
                    logger.debug(f"找到目标分集信息: EP={target_ep_id}")
                    break
            if not season_model.target_ep_id:
                logger.warning(f"在番剧信息中未找到提供的 ep_id: {target_ep_id}")

        return season_model

    @staticmethod
    @Retry.api(exception=RETRYABLE_EXCEPTIONS)
    async def get_bangumi_info(
        parsed_url: str, season_id: Optional[int] = None, ep_id: Optional[int] = None
    ) -> SeasonInfo:
        """获取番剧/电影信息"""
        if not season_id and not ep_id:
            raise ValueError("必须提供 season_id 或 ep_id")

        log_id = f"ss{season_id}" if season_id else f"ep{ep_id}"
        logger.debug(f"获取番剧/影视信息: {log_id}", "B站解析")
        context = {"id": log_id, "url": parsed_url}

        try:
            api_param = ""
            if season_id:
                api_param = f"season_id={season_id}"
            elif ep_id:
                api_param = f"ep_id={ep_id}"

            season_url = f"https://api.bilibili.com/pgc/view/web/season?{api_param}"
            logger.debug(f"请求番剧API: {season_url}", "B站解析")

            # 使用 AsyncHttpx 替代 NetworkService.get_json
            from ..utils.headers import get_bilibili_headers

            cred = get_credential()
            headers = get_bilibili_headers()
            cookies = cred.get_cookies() if cred else None

            response = await AsyncHttpx.get(
                season_url, headers=headers, cookies=cookies
            )
            response.raise_for_status()  # 检查HTTP状态码
            season_resp = response.json()

            if not isinstance(season_resp, dict):
                logger.error(f"番剧API响应不是字典类型: {type(season_resp)}", "B站解析")
                raise BilibiliResponseError(
                    f"番剧API响应格式错误: {type(season_resp)}", context=context
                )

            if season_resp.get("code") != 0 or "result" not in season_resp:
                if season_resp.get("code") == -412:
                    logger.warning(f"请求过于频繁，等待后重试: {log_id}", "B站解析")
                    raise RateLimitError(
                        f"请求频率过高 ({log_id})",
                        retry_after=60,
                        context={**context, "code": season_resp.get("code")},
                    )
                elif season_resp.get("code") == -404:
                    logger.warning(f"番剧未找到: {log_id}", "B站解析")
                    raise ResourceNotFoundError(
                        f"番剧未找到: {log_id}",
                        context={**context, "code": season_resp.get("code")},
                    )
                else:
                    logger.warning(
                        f"番剧信息获取失败: {log_id}, 响应: {season_resp}", "B站解析"
                    )
                    raise BilibiliResponseError(
                        f"番剧信息获取失败: {log_id}, 响应码: {season_resp.get('code')}",
                        context={**context, "response": season_resp},
                    )

            result = season_resp["result"]

            season_model = BilibiliApiService._map_season_info_to_model(
                result, parsed_url, target_ep_id=ep_id
            )
            logger.debug(f"番剧/影视信息获取成功: {season_model.title}", "B站解析")
            return season_model

        except ResourceNotFoundError:
            raise
        except RateLimitError:
            raise
        except BilibiliResponseError:
            raise
        except BilibiliRequestError:
            raise
        except Exception as e:
            logger.error(f"获取番剧信息失败 ({season_id}): {e}", "B站解析")
            raise BilibiliResponseError(
                f"获取番剧信息意外错误 ({season_id}): {e}",
                cause=e,
                context={"season_id": season_id, "url": parsed_url},
            )
