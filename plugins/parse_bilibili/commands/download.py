import asyncio
import re
import subprocess
import aiofiles
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import httpx
import requests
from typing import Optional, Dict, Any, Literal

from arclet.alconna import (
    Alconna,
    Args,
    Arparma,
    CommandMeta,
)
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import (
    GROUP_ADMIN,
    GROUP_OWNER,
    MessageSegment as V11MessageSegment,
)
from nonebot_plugin_alconna import AlconnaMatcher, on_alconna, AlconnaMatches, Reply
from nonebot_plugin_alconna.uniseg import UniMsg, Text, Hyper
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_session import EventSession, SessionLevel

from bilibili_api import video
from zhenxun.services.log import logger

from ..config import base_config, get_credential, PLUGIN_TEMP_DIR
from ..model import VideoInfo
from ..services.parser_service import ParserService
from ..utils.exceptions import MediaProcessError, DownloadError
from ..utils.url_parsers import ResourceType, UrlParserRegistry

from ..services import auto_download_manager

BILIBILI_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
    "referer": "https://www.bilibili.com",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


async def download_b_file(url: str, file_path: Path):
    max_retries = 3
    proxy_setting = base_config.get("PROXY")
    download_timeout = base_config.get("DOWNLOAD_TIMEOUT", 600)
    proxies = (
        {"http://": proxy_setting, "https://": proxy_setting} if proxy_setting else None
    )
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(
                headers=BILIBILI_HEADER,
                proxies=proxies,
                timeout=download_timeout,
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total_len = int(resp.headers.get("content-length", 0))
                    current_len = 0
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            await f.write(chunk)
                            current_len += len(chunk)
                    if total_len == 0 or current_len == total_len:
                        logger.debug(f"文件流下载完成: {file_path.name}")
                        return True
                    else:
                        logger.warning(
                            f"文件下载不完整: {file_path.name}, {current_len}/{total_len}"
                        )
                        return True
        except (
            httpx.HTTPStatusError,
            httpx.RequestError,
            asyncio.TimeoutError,
            Exception,
        ) as e:
            logger.error(
                f"下载文件流 {file_path.name} 失败 (尝试 {attempt + 1}/{max_retries})",
                e=e,
            )
            if attempt == max_retries - 1:
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
                raise
            await asyncio.sleep(2)
    return False


async def merge_file_to_mp4(
    v_path: Path,
    a_path: Path,
    output_path: Path,
    use_copy_codec: bool = False,
    log_output: bool = False,
):
    if use_copy_codec:
        logger.info(f"开始快速合并音视频 (copy codec) 到: {output_path.name}")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(v_path.resolve()),
            "-i",
            str(a_path.resolve()),
            "-c",
            "copy",
            "-loglevel",
            "error",
            str(output_path.resolve()),
        ]
    else:
        logger.info(
            f"开始合并音视频并编码为 H.264 (可能耗时较长) 到: {output_path.name}"
        )
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(v_path.resolve()),
            "-i",
            str(a_path.resolve()),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-loglevel",
            "error",
            str(output_path.resolve()),
        ]
    logger.debug(f"执行 FFmpeg 命令: {' '.join(command)}")
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE if log_output else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.info(f"音视频处理成功: {output_path.name}")
            return True
        else:
            error_message = stderr.decode("utf-8", errors="ignore").strip()
            logger.error(f"FFmpeg 处理失败 (返回码: {process.returncode})")
            if error_message:
                logger.error(f"FFmpeg 错误输出:\n{error_message}")
            else:
                logger.error("FFmpeg 未产生错误输出，请检查命令或文件。")
            if not use_copy_codec and (
                "Audio stream type 0x0 is not supported" in error_message
                or "codec copy and bitstream filter" in error_message
            ):
                logger.warning("重新编码视频时音频流复制失败，尝试同时编码音频...")
                for i in range(len(command)):
                    if (
                        command[i] == "-c:a"
                        and i + 1 < len(command)
                        and command[i + 1] == "copy"
                    ):
                        command[i + 1] = "aac"
                        command.extend(["-b:a", "128k"])
                        break
                logger.debug(f"重试 FFmpeg 命令 (编码音频): {' '.join(command)}")
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=subprocess.PIPE if log_output else subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    logger.info(f"音视频合并及 H.264/AAC 编码成功: {output_path.name}")
                    return True
                else:
                    error_message = stderr.decode("utf-8", errors="ignore").strip()
                    logger.error(
                        f"FFmpeg 重新编码音频后仍然失败 (返回码: {process.returncode})"
                    )
                if error_message:
                    logger.error(f"FFmpeg 错误输出:\n{error_message}")
                    return False
            return False
    except FileNotFoundError:
        logger.error("FFmpeg 未找到，请确保已安装 FFmpeg 并将其添加至系统 PATH。")
        return False
    except Exception as e:
        logger.error("执行 FFmpeg 时发生未知错误", e=e)
        return False
    finally:
        try:
            if v_path.exists():
                v_path.unlink()
            if a_path.exists():
                a_path.unlink()
            logger.debug(f"已清理临时文件: {v_path.name}, {a_path.name}")
        except OSError as e:
            logger.warning("清理临时文件失败", e=e)


async def send_video_final(bot: Bot, event: Event, video_path: Path):
    """仅发送最终视频，失败时只记录日志"""
    try:
        if video_path.exists():
            path_str = str(video_path.resolve())
            path_str = path_str.replace("\\", "/")
            file_uri = "file:///" + path_str
            video_segment = V11MessageSegment.video(file_uri)
            await bot.send(event=event, message=video_segment)
            logger.info(f"视频文件发送成功: {video_path}")
        else:
            logger.error(f"尝试发送时合并后的文件已不存在: {video_path}")
    except Exception as send_e:
        logger.error("发送视频文件失败", e=send_e)


def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', "_", filename)[:100]


def get_bangumi_info_sync(url_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """(同步) 获取番剧信息"""
    api_url = None
    if "ep_id" in url_info:
        api_url = (
            f"https://api.bilibili.com/pgc/view/web/season?ep_id={url_info['ep_id']}"
        )
    elif "season_id" in url_info:
        api_url = f"https://api.bilibili.com/pgc/view/web/season?season_id={url_info['season_id']}"
    else:
        logger.error("无效的番剧信息输入")
        return None

    logger.debug(f"请求番剧信息 (同步): {api_url}")
    try:
        cred = get_credential()
        response = requests.get(
            api_url,
            headers=HEADERS,
            cookies=cred.get_cookies() if cred else None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0 and "result" in data:
            logger.debug(f"获取到番剧信息: {data['result'].get('title', '未知')}")
            return data["result"]
        else:
            logger.error(
                f"获取番剧信息 API 错误: Code={data.get('code')} Msg={data.get('message')}"
            )
            return None
    except requests.RequestException as e:
        logger.error(f"请求番剧信息网络错误: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("解析番剧信息 JSON 失败")
        return None
    except Exception as e:
        logger.error(f"获取番剧信息时发生未知错误: {e}", e=e)
        return None


def get_play_url_sync(
    ep_id: int, cid: int, quality: int = 120, fnval: int = 16
) -> Optional[Dict[str, Any]]:
    """(同步) 获取番剧播放链接"""
    api_url = "https://api.bilibili.com/pgc/player/web/playurl"
    params = {
        "ep_id": ep_id,
        "cid": cid,
        "qn": quality,
        "fnval": fnval,
        "fnver": 0,
        "fourk": 1,
    }
    logger.debug(f"请求播放链接 (同步): {api_url} Params: {params}")
    try:
        cred = get_credential()
        response = requests.get(
            api_url,
            params=params,
            headers=HEADERS,
            cookies=cred.get_cookies() if cred else None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0 and "result" in data:
            logger.debug("获取播放链接成功")
            return data["result"]
        else:
            logger.warning(
                f"获取播放链接失败: Code={data.get('code')} Msg={data.get('message')}"
            )
            return None
    except requests.RequestException as e:
        logger.error(f"请求播放链接网络错误: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("解析播放链接 JSON 失败")
        return None
    except Exception as e:
        logger.error(f"获取播放链接时发生未知错误: {e}", e=e)
        return None


async def get_bangumi_play_url_with_fallback(
    ep_id: int, cid: int
) -> Optional[Dict[str, Any]]:
    """获取番剧播放链接 (异步封装同步请求)"""
    loop = asyncio.get_running_loop()

    play_info = await loop.run_in_executor(None, get_play_url_sync, ep_id, cid)

    if not play_info:
        logger.warning("获取播放链接失败")
        return None

    if "durl" not in play_info and "dash" not in play_info:
        logger.warning("获取的播放信息中缺少 durl 或 dash")
        return None

    logger.debug("获取播放链接成功")
    return play_info


async def _perform_bangumi_download(
    bot: Bot,
    event: Event,
    url_info_dict: Dict[str, Any],
    matcher: Optional[AlconnaMatcher] = None,
):
    """执行番剧下载的核心逻辑"""
    loop = asyncio.get_running_loop()
    logger.info(f"开始下载番剧: {url_info_dict}")

    bangumi_info = await loop.run_in_executor(
        None, get_bangumi_info_sync, url_info_dict
    )
    if not bangumi_info:
        logger.error("无法获取番剧信息")
        if matcher:
            await matcher.finish("无法获取番剧信息，请稍后重试。")
        return
    episodes = bangumi_info.get("episodes", [])
    if not episodes:
        logger.error("番剧没有剧集信息")
        if matcher:
            await matcher.finish("番剧没有剧集信息，请检查链接是否正确。")
        return

    target_episode = None
    target_ep_id = url_info_dict.get("ep_id")
    if target_ep_id:
        for ep in episodes:
            if ep.get("id") == target_ep_id:
                target_episode = ep
                break
    else:
        target_episode = episodes[0]

    if not target_episode:
        logger.error("未找到目标剧集")
        if matcher:
            await matcher.finish("未找到目标剧集，请检查链接是否正确。")
        return
    ep_id = target_episode.get("id")
    cid = target_episode.get("cid")
    title = sanitize_filename(target_episode.get("long_title", f"EP{ep_id}"))

    play_info = await get_bangumi_play_url_with_fallback(ep_id, cid)
    if not play_info:
        logger.error(f"获取播放链接失败 for ep {ep_id}")
        if matcher:
            await matcher.finish("获取番剧播放链接失败，请稍后重试。")
        return

    downloaded_file_path: Optional[Path] = None
    v_stream_path: Optional[Path] = None
    a_stream_path: Optional[Path] = None
    output_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_{title}.mp4"

    try:
        if "dash" in play_info:
            logger.debug("处理 DASH 流")
            dash_info = play_info["dash"]
            video_streams = dash_info.get("video", [])
            audio_streams = dash_info.get("audio", [])
            if not video_streams or not audio_streams:
                raise DownloadError("DASH 流缺少视频或音频")
            video_stream = sorted(
                video_streams, key=lambda x: x.get("id", 0), reverse=True
            )[0]
            audio_stream = sorted(
                audio_streams, key=lambda x: x.get("bandwidth", 0), reverse=True
            )[0]
            video_url = video_stream.get("baseUrl") or video_stream.get("base_url")
            audio_url = audio_stream.get("baseUrl") or audio_stream.get("base_url")
            if not video_url or not audio_url:
                raise DownloadError("无法获取 DASH 流 URL")

            v_stream_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_{title}_video.m4s"
            a_stream_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_{title}_audio.m4s"

            logger.info("开始下载番剧视频流...")
            dl_video_ok = await download_b_file(video_url, v_stream_path)
            logger.info("开始下载番剧音频流...")
            dl_audio_ok = await download_b_file(audio_url, a_stream_path)

            if not dl_video_ok or not dl_audio_ok:
                raise DownloadError("番剧音视频流下载失败")

            merge_ok = await merge_file_to_mp4(
                v_stream_path, a_stream_path, output_path, use_copy_codec=True
            )
            if not merge_ok:
                raise MediaProcessError("番剧合并失败")
            downloaded_file_path = output_path

        elif "durl" in play_info:
            logger.debug("处理 DURL 流 (FLV/MP4)")
            durl_info = play_info["durl"]
            if not durl_info:
                raise DownloadError("无法获取 DURL 信息")
            url = durl_info[0].get("url")
            if not url:
                raise DownloadError("无法获取 DURL URL")
            ext = ".flv" if ".flv" in url else ".mp4"
            output_path = PLUGIN_TEMP_DIR / f"bili_video_ep{ep_id}_{title}{ext}"
            logger.info(f"开始下载 DURL 流: {title}{ext}")
            dl_ok = await download_b_file(url, output_path)
            if not dl_ok:
                raise DownloadError("DURL 流下载失败")
            downloaded_file_path = output_path
        else:
            raise DownloadError("不支持的播放信息格式")

        if downloaded_file_path and downloaded_file_path.exists():
            logger.info(f"番剧下载/处理完成: {downloaded_file_path}")
            await send_video_final(bot, event, downloaded_file_path)
        else:
            logger.error("最终文件不存在")

    except Exception as e:
        logger.error(f"执行番剧下载失败 for ep {ep_id}", e=e)
        if v_stream_path and v_stream_path.exists():
            v_stream_path.unlink(missing_ok=True)
        if a_stream_path and a_stream_path.exists():
            a_stream_path.unlink(missing_ok=True)
        if matcher:
            await matcher.finish(f"番剧下载处理失败: {str(e)[:100]}")
        raise


async def _perform_video_download(
    bot: Bot,
    event: Event,
    video_info: VideoInfo,
    matcher: Optional[AlconnaMatcher] = None,
):
    """
    执行视频下载、合并和发送的核心逻辑。
    此函数不发送任何中间提示或错误消息给用户，只发送最终视频（如果成功）。
    """
    video_id = video_info.bvid or f"av{video_info.aid}"
    final_url = video_info.parsed_url
    page_num = 0

    parsed_final_url = urlparse(final_url)
    if parsed_final_url.query:
        query_params = parse_qs(parsed_final_url.query)
        p_value = query_params.get("p")
        if p_value and p_value[0].isdigit():
            page_num = int(p_value[0]) - 1
            if page_num < 0:
                page_num = 0

    logger.info(
        f"开始下载视频 (供 {event.get_event_name()}): {video_info.title} (ID: {video_id}, P{page_num + 1})"
    )

    downloaded_file_path: Path | None = None
    v_stream_path: Path | None = None
    a_stream_path: Path | None = None

    try:
        logger.debug("创建 bilibili_api.Video 对象")
        cred = get_credential()
        if video_id.startswith("BV"):
            v = video.Video(bvid=video_id, credential=cred)
        elif video_id.startswith("av"):
            v = video.Video(aid=int(video_id[2:]), credential=cred)
        else:
            raise ValueError(f"无效 video_id: {video_id}")

        logger.debug(f"获取下载链接 (P{page_num + 1})")
        download_url_data: Dict[str, Any] = await v.get_download_url(
            page_index=page_num
        )

        selected_video_stream: Optional[Dict[str, Any]] = None
        selected_audio_stream: Optional[Dict[str, Any]] = None
        video_url = None
        audio_url = None
        use_copy_codec = False

        if "dash" in download_url_data:
            dash_video_streams = download_url_data["dash"].get("video", [])
            dash_audio_streams = download_url_data["dash"].get("audio", [])
            h264_streams = [
                s
                for s in dash_video_streams
                if isinstance(s.get("codecs"), str)
                and s["codecs"].startswith("avc")
                and s.get("id", 0) <= 80
            ]
            if h264_streams:
                h264_streams.sort(key=lambda s: s.get("id", 0), reverse=True)
                selected_video_stream = h264_streams[0]
                use_copy_codec = True
                logger.info(f"找到 H.264 视频流 (qn={selected_video_stream.get('id')})")
            else:
                non_h264_streams = [
                    s for s in dash_video_streams if s.get("id", 0) <= 80
                ]
                if non_h264_streams:
                    non_h264_streams.sort(key=lambda s: s.get("id", 0), reverse=True)
                    selected_video_stream = non_h264_streams[0]
                    use_copy_codec = False
                    logger.warning(
                        f"未找到 H.264，选择最佳流 (qn={selected_video_stream.get('id')})，需重编码"
                    )
                else:
                    logger.error("未找到可用视频流")
            if dash_audio_streams:
                dash_audio_streams.sort(key=lambda s: s.get("id", 0), reverse=True)
                selected_audio_stream = dash_audio_streams[0]
            else:
                logger.error("未找到可用音频流")
            if selected_video_stream:
                video_url = selected_video_stream.get(
                    "baseUrl"
                ) or selected_video_stream.get("base_url")
            if selected_audio_stream:
                audio_url = selected_audio_stream.get(
                    "baseUrl"
                ) or selected_audio_stream.get("base_url")
        if not video_url or not audio_url:
            raise ValueError("未能选择有效的音视频流 URL")

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", video_info.title)[:100]
        base_filename = f"bili_video_{video_id}_P{page_num + 1}_{safe_title}"
        v_stream_path = PLUGIN_TEMP_DIR / f"{base_filename}-video.m4s"
        a_stream_path = PLUGIN_TEMP_DIR / f"{base_filename}-audio.m4s"
        output_mp4_path = PLUGIN_TEMP_DIR / f"{base_filename}.mp4"
        logger.info("开始下载音视频流...")
        results = await asyncio.gather(
            download_b_file(video_url, v_stream_path),
            download_b_file(audio_url, a_stream_path),
            return_exceptions=True,
        )
        if isinstance(results[0], Exception) or not results[0]:
            raise (
                results[0]
                if isinstance(results[0], Exception)
                else RuntimeError(f"下载视频流失败: {results[0]}")
            )
        if isinstance(results[1], Exception) or not results[1]:
            raise (
                results[1]
                if isinstance(results[1], Exception)
                else RuntimeError(f"下载音频流失败: {results[1]}")
            )
        logger.info("音视频流下载完成.")

        merge_success = await merge_file_to_mp4(
            v_stream_path, a_stream_path, output_mp4_path, use_copy_codec=use_copy_codec
        )
        if merge_success:
            downloaded_file_path = output_mp4_path
            logger.info(f"视频处理成功: {downloaded_file_path}")

            logger.debug(f"准备发送最终视频文件: {downloaded_file_path}")
            if downloaded_file_path.exists():
                try:
                    path_str = str(downloaded_file_path.resolve())
                    path_str = path_str.replace("\\", "/")
                    file_uri = "file:///" + path_str
                    video_segment = V11MessageSegment.video(file_uri)
                    logger.debug(
                        f"自动下载：准备发送的消息段类型: {type(video_segment)}, 内容: {video_segment}"
                    )
                    await bot.send(event=event, message=video_segment)
                except Exception as send_e:
                    logger.error("发送视频文件失败 (Bot API)", e=send_e)
            else:
                logger.error(f"尝试发送时文件已不存在: {downloaded_file_path}")

            delete_downloaded_video = False
            if downloaded_file_path.exists() and delete_downloaded_video:
                try:
                    downloaded_file_path.unlink(missing_ok=True)
                    logger.info(f"已删除视频文件: {downloaded_file_path}")
                except Exception as del_e:
                    logger.error("删除视频文件失败", e=del_e)

        else:
            raise MediaProcessError("FFmpeg 合并或编码失败")

    except Exception as e:
        logger.error(f"执行视频下载/处理失败 for {video_id}", e=e)
        if v_stream_path and v_stream_path.exists():
            v_stream_path.unlink(missing_ok=True)
        if a_stream_path and a_stream_path.exists():
            a_stream_path.unlink(missing_ok=True)
        if matcher:
            await matcher.finish(f"视频下载处理失败: {str(e)[:100]}")
        raise


bili_download_cmd = Alconna("bili下载", Args["link?", str])

bili_download_matcher = on_alconna(
    bili_download_cmd,
    block=True,
    priority=5,
    aliases={"b站下载"},
    skip_for_unmatch=False,
)


@bili_download_matcher.handle()
async def handle_bili_download(
    matcher: AlconnaMatcher, bot: Bot, event: Event, result: Arparma = AlconnaMatches()
):
    logger.info("处理 bili下载 命令")
    target_url_or_id = None
    url_info_dict: Optional[Dict[str, Any]] = None

    if result.matched and "link" in result.main_args:
        target_url_or_id = result.main_args["link"]
    else:
        reply: Reply | None = await reply_fetch(event, bot)
        if reply and reply.msg:
            patterns = {
                "b23_tv": UrlParserRegistry._parsers[0].PATTERN,
                "video": UrlParserRegistry._parsers[1].PATTERN,
                "live": UrlParserRegistry._parsers[2].PATTERN,
                "article": UrlParserRegistry._parsers[3].PATTERN,
                "opus": UrlParserRegistry._parsers[4].PATTERN,
                "pure_video_id": UrlParserRegistry._parsers[7].PATTERN,
            }
            url_match_order = ["b23_tv", "video", "live", "article", "opus"]
            for seg in reply.msg:
                if isinstance(seg, Hyper) and seg.raw:
                    try:
                        data = json.loads(seg.raw)
                        if data.get("app") == "com.tencent.qun.invite":
                            continue
                        meta_data = data.get("meta", {})
                        jump_url = (
                            meta_data.get("news", {}).get("jumpUrl")
                            or meta_data.get("detail_1", {}).get("qqdocurl")
                            or meta_data.get("detail_1", {}).get("preview")
                        )
                        if (
                            jump_url
                            and isinstance(jump_url, str)
                            and ("bilibili.com" in jump_url or "b23.tv" in jump_url)
                        ):
                            target_url_or_id = jump_url.split("?")[0]
                            if target_url_or_id.endswith("/"):
                                target_url_or_id = target_url_or_id[:-1]
                            logger.info(
                                f"从引用消息的 Hyper 段提取到链接: {target_url_or_id}"
                            )
                            break
                    except Exception as e:
                        logger.debug(f"解析引用 Hyper 失败: {e}")
            if not target_url_or_id:
                for seg in reply.msg:
                    if isinstance(seg, Text):
                        text_content = seg.text.strip()
                        if not text_content:
                            continue
                        logger.debug(f"检查引用消息的 Text 段: '{text_content}'")
                        for key in url_match_order:
                            match = patterns[key].search(text_content)
                            if match:
                                potential_url = match.group(0)
                                if (
                                    potential_url.startswith("http")
                                    or "b23.tv" in potential_url
                                    or key == "b23_tv"
                                ):
                                    target_url_or_id = potential_url
                                    logger.info(
                                        f"从引用消息的 Text 段提取到链接 ({key}): {target_url_or_id}"
                                    )
                                    break
                        if target_url_or_id:
                            break
                        if not target_url_or_id:
                            match = patterns["pure_video_id"].search(text_content)
                            if match:
                                target_url_or_id = match.group(0)
                                logger.info(
                                    f"从引用消息的 Text 段提取到纯视频ID: {target_url_or_id}"
                                )
                                break
            if not target_url_or_id:
                try:
                    plain_text = reply.msg.extract_plain_text().strip()
                    if plain_text:
                        logger.debug(f"尝试从引用消息的纯文本提取: '{plain_text}'")
                        for key in url_match_order:
                            match = patterns[key].search(plain_text)
                            if match:
                                potential_url = match.group(0)
                                if (
                                    potential_url.startswith("http")
                                    or "b23.tv" in potential_url
                                    or key == "b23_tv"
                                ):
                                    target_url_or_id = potential_url
                                    logger.info(
                                        f"从引用消息的纯文本找到URL ({key}): {target_url_or_id}"
                                    )
                                    break
                        if not target_url_or_id:
                            match = patterns["pure_video_id"].fullmatch(plain_text)
                            if match:
                                target_url_or_id = match.group(0)
                                logger.info(
                                    f"从引用消息纯文本找到独立视频ID: {target_url_or_id}"
                                )
                except Exception as e:
                    logger.warning(f"提取引用纯文本失败: {e}")
        else:
            logger.debug("未检测到回复")

    if not target_url_or_id:
        current_message: UniMsg = event.get_message()
        first_seg = current_message[0] if current_message else None
        if isinstance(first_seg, Hyper) and first_seg.raw:
            try:
                raw_str = first_seg.raw
                qqdocurl_match = re.search(r'"qqdocurl"\s*:\s*"([^"]+)"', raw_str)
                if qqdocurl_match:
                    qqdocurl = qqdocurl_match.group(1).replace("\\", "")
                    if "b23.tv" in qqdocurl or "bilibili.com" in qqdocurl:
                        target_url_or_id = qqdocurl
                        logger.info(f"从当前消息中提取到 B 站链接: {target_url_or_id}")
                if not target_url_or_id:
                    data = json.loads(first_seg.raw)
                    meta_data = data.get("meta", {})
                    jump_url = (
                        meta_data.get("news", {}).get("jumpUrl")
                        or meta_data.get("detail_1", {}).get("qqdocurl")
                        or meta_data.get("detail_1", {}).get("preview")
                    )
                    if (
                        jump_url
                        and isinstance(jump_url, str)
                        and ("bilibili.com" in jump_url or "b23.tv" in jump_url)
                    ):
                        target_url_or_id = jump_url.split("?")[0]
                        if target_url_or_id.endswith("/"):
                            target_url_or_id = target_url_or_id[:-1]
                        logger.debug(
                            f"从当前消息的小程序卡片提取链接: {target_url_or_id}"
                        )
            except Exception as e:
                logger.error(f"解析当前消息小程序卡片失败: {e}")

    if not target_url_or_id:
        logger.debug("未找到有效链接/ID")
        await matcher.finish(
            "未找到有效的B站链接或视频ID，请检查输入或回复包含B站链接的消息。"
        )
        return

    await matcher.send("正在解析B站链接并准备下载，请稍候...")

    resource_type: Optional[ResourceType] = None
    resource_id: Optional[str] = None
    try:
        parser = UrlParserRegistry.get_parser(target_url_or_id)
        if parser:
            resource_type, resource_id = parser.parse(target_url_or_id)
            logger.debug(f"通过 Registry 解析: Type={resource_type}, ID={resource_id}")
            if resource_type == ResourceType.BANGUMI:
                if resource_id.startswith("ss"):
                    url_info_dict = {"season_id": int(resource_id[2:])}
                elif resource_id.startswith("ep"):
                    url_info_dict = {"ep_id": int(resource_id[2:])}
            elif resource_type == ResourceType.VIDEO:
                if resource_id.startswith("av"):
                    url_info_dict = {"av_id": int(resource_id[2:])}
                elif resource_id.startswith("BV"):
                    url_info_dict = {"bv_id": resource_id}
    except Exception as e:
        logger.warning(f"使用 UrlParserRegistry 解析失败: {e}, 将尝试原始解析")

    if not url_info_dict and not resource_type:
        logger.error(f"无法识别的 URL 或 ID: {target_url_or_id}")
        await matcher.finish(f"无法识别的B站链接或ID: {target_url_or_id}")
        return

    if resource_type == ResourceType.BANGUMI and url_info_dict:
        await matcher.send("正在下载番剧，视频较大请耐心等待...")
        try:
            await _perform_bangumi_download(bot, event, url_info_dict, matcher)
        except Exception as e:
            logger.error(f"番剧下载失败: {e}", e=e)
            await matcher.finish(f"番剧下载失败: {str(e)[:100]}")
    elif resource_type == ResourceType.VIDEO and resource_id:
        video_info: Optional[VideoInfo] = None
        try:
            logger.debug(f"准备获取普通视频信息: {resource_id}")
            parsed_content = await ParserService.parse(target_url_or_id)
            if isinstance(parsed_content, VideoInfo):
                video_info = parsed_content
                await _perform_video_download(bot, event, video_info, matcher)
            else:
                logger.error(
                    f"解析普通视频链接未返回 VideoInfo: {type(parsed_content)}"
                )
                await matcher.finish("解析视频信息失败，请稍后重试。")
        except Exception as e:
            logger.error(f"执行普通视频下载失败 for {resource_id}", e=e)
            await matcher.finish(f"下载视频失败: {str(e)[:100]}")
    else:
        logger.warning(
            f"识别的资源类型 ({resource_type}) 不是支持的下载类型 (Video/Bangumi)"
        )
        await matcher.finish(f"不支持下载此类型的内容: {resource_type}")

    logger.info("handle_bili_download 函数执行完毕")


auto_download_cmd = Alconna(
    "bili自动下载",
    Args["action", Literal["on", "off"]],
    meta=CommandMeta(description="开启或关闭当前群聊的B站视频自动下载功能"),
)

auto_download_matcher = on_alconna(
    auto_download_cmd,
    aliases={"b站自动下载"},
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER,
    priority=10,
    block=True,
)


@auto_download_matcher.handle()
async def handle_auto_download_switch(
    matcher: AlconnaMatcher,
    session: EventSession,
    action: Literal["on", "off"],
):
    if session.level != SessionLevel.GROUP:
        await matcher.finish("此命令仅限群聊使用。")
        return

    group_id = str(session.id2)
    if action == "on":
        success = await auto_download_manager.enable_auto_download(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})开启B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})已开启自动下载，无需重复操作。")
    elif action == "off":
        success = await auto_download_manager.disable_auto_download(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})关闭B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})未开启自动下载，无需重复操作。")
