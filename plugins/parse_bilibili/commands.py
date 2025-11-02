import asyncio
from typing import Dict, Literal, Optional, cast

import httpx
from arclet.alconna import Alconna, Arparma, Args, CommandMeta
from bilibili_api import Picture, exceptions as BiliExceptions, login_v2
from bilibili_api.utils.network import get_session
from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GROUP_ADMIN, GROUP_OWNER, MessageSegment
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import AlconnaMatches, on_alconna, AlconnaMatcher
from nonebot_plugin_session import EventSession, SessionLevel

from zhenxun.services.log import logger

from .config import get_credential, save_credential_to_file
from .services.cover_service import CoverService
from .services.download_service import DownloadTask, download_manager
from .services.network_service import ParserService
from .services.utility_service import AutoDownloadManager
from .utils.exceptions import BilibiliBaseException
from .utils.url_parser import extract_bilibili_url_from_event


bili_cover_cmd = Alconna("bili封面")

bili_cover_matcher = on_alconna(
    bili_cover_cmd,
    block=True,
    priority=5,
    aliases={"b站封面"},
    skip_for_unmatch=False,
)


@bili_cover_matcher.handle()
async def handle_bili_cover(matcher: AlconnaMatcher, bot: Bot, event: Event):
    logger.info("处理 bili封面 命令")

    bilibili_url = await extract_bilibili_url_from_event(bot, event)

    if not bilibili_url:
        await matcher.finish("请引用包含B站链接的消息后使用此命令。")

    await matcher.send("正在获取封面，请稍候...")

    try:
        cover_message = await CoverService.get_cover_message(bilibili_url)
        await cover_message.send()
        logger.info(f"成功发送封面 for {bilibili_url}")
    except BilibiliBaseException as e:
        logger.warning(f"获取封面失败 for {bilibili_url}: {e.message}")
        await matcher.send(f"获取封面失败: {e.message}")
    except Exception as e:
        logger.error(f"处理bili封面命令时发生错误: {e}", e=e)
        await matcher.send("获取封面时发生错误，请稍后重试。")


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
    target_url = result.main_args.get("link") or await extract_bilibili_url_from_event(
        bot, event
    )

    if not target_url:
        await matcher.finish(
            "未找到有效的B站链接或ID，请检查输入或回复包含B站链接的消息。"
        )

    await matcher.send("正在解析链接...")

    try:
        parsed_content = await ParserService.parse(target_url)

        task = DownloadTask(
            bot=bot,
            event=event,
            info_model=parsed_content,
            is_manual=True,
        )
        await download_manager.add_task(task, matcher)

    except BilibiliBaseException as e:
        logger.error(f"下载任务创建失败 (已处理异常): {e}", e=e)
        await matcher.finish(f"任务创建失败: {e.message}")
    except Exception as e:
        logger.error(f"下载任务创建失败 (未处理异常): {e}", e=e)
        await matcher.finish("任务创建时发生意外错误，请检查日志。")


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

    group_id = str(session.id2)
    if action == "on":
        success = await AutoDownloadManager.enable(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})开启B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})已开启自动下载，无需重复操作。")
    elif action == "off":
        success = await AutoDownloadManager.disable(session)
        if success:
            await matcher.send(f"已为当前群聊({group_id})关闭B站视频自动下载功能。")
        else:
            await matcher.send(f"当前群聊({group_id})未开启自动下载，无需重复操作。")


login_matcher = on_command("bili登录", permission=SUPERUSER, priority=5, block=True)
credential_status_matcher = on_command(
    "bili状态", permission=SUPERUSER, priority=5, block=True
)

login_sessions: Dict[str, login_v2.QrCodeLogin] = {}


@login_matcher.handle()
async def handle_login_start(bot: Bot, event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    if user_id in login_sessions and not login_sessions[user_id].has_done():
        await matcher.send("您当前有一个登录流程正在进行中，请先完成或等待超时。")
        return

    logger.info(f"用户 {user_id} 请求 B站扫码登录")
    await matcher.send("正在生成登录二维码，请稍候...")

    login_instance: Optional[login_v2.QrCodeLogin] = None
    try:
        login_instance = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB)
        await login_instance.generate_qrcode()
        login_sessions[user_id] = login_instance

        qr_bytes: Optional[bytes] = None
        try:
            qr_pic: Picture = login_instance.get_qrcode_picture()
            qr_bytes = qr_pic.content
            if qr_bytes:
                logger.debug("二维码图片字节获取成功")
            else:
                logger.warning("get_qrcode_picture().content 为空")
        except Exception as img_err:
            logger.error("获取二维码图片字节失败", e=img_err)

        message = "请使用哔哩哔哩手机客户端扫描下方二维码登录："

        if qr_bytes:
            await matcher.send(message)
            await matcher.send(MessageSegment.image(qr_bytes))
            logger.debug("登录提示和二维码图片已发送")
        else:
            error_msg = "错误：无法生成二维码图片。登录流程已启动，请关注后续提示或尝试扫描App通知。"
            await matcher.send(message + "\n" + error_msg)
            logger.debug("登录提示（仅文本）已发送")

        asyncio.create_task(check_login_status(matcher, user_id))
        matcher.stop_propagation()

    except BiliExceptions.ApiException as e:
        logger.error(f"生成二维码时发生B站API错误: {e}", e=e)
        await matcher.finish(f"连接B站API失败，请稍后再试 (错误: {e})。")
    except Exception as e:
        logger.error("启动登录流程时发生意外错误", e=e)
        if user_id in login_sessions:
            del login_sessions[user_id]
        await matcher.finish("启动登录流程时发生错误，请检查日志。")


async def check_login_status(org_matcher: Matcher, user_id: str):
    """后台轮询检查二维码登录状态"""
    login = login_sessions.get(user_id)
    if not login:
        logger.warning(f"尝试检查登录状态时，用户 {user_id} 的会话已不存在")
        return

    check_interval = 3
    timeout = 120
    start_time = asyncio.get_running_loop().time()
    scan_message_sent = False

    logger.info(f"开始为用户 {user_id} 检查登录状态...")
    await asyncio.sleep(check_interval)

    try:
        while asyncio.get_running_loop().time() - start_time < timeout:
            if not (login := login_sessions.get(user_id)) or login.has_done():
                break

            try:
                event = await login.check_state()
                logger.debug(f"用户 {user_id} 登录状态检查: {event.name}")

                if event == login_v2.QrCodeLoginEvents.TIMEOUT:
                    await org_matcher.send("登录二维码已超时失效。")
                    return
                elif event == login_v2.QrCodeLoginEvents.SCAN and not scan_message_sent:
                    logger.info(f"用户 {user_id} 已扫描，待确认")
                    await org_matcher.send("扫描成功，请在手机上确认登录。")
                    scan_message_sent = True
                elif event == login_v2.QrCodeLoginEvents.DONE:
                    logger.info(f"用户 {user_id} 登录成功！")
                    credential = login.get_credential()

                    try:
                        session = cast(httpx.AsyncClient, get_session())
                        if buvid3_cookie := session.cookies.get("buvid3"):
                            logger.info(f"成功获取到 buvid3: {buvid3_cookie}")
                            credential.buvid3 = buvid3_cookie
                    except Exception as e:
                        logger.error(f"尝试获取 buvid3 时出错: {e}")

                    await save_credential_to_file(credential)
                    await org_matcher.send("登录成功！凭证已保存。")
                    return

            except Exception as e:
                logger.error(f"检查用户 {user_id} 登录状态时出错", e=e)
                await org_matcher.send("检查登录状态时发生错误，请稍后重试。")
                return

            await asyncio.sleep(check_interval)

        if (
            asyncio.get_running_loop().time() - start_time >= timeout
            and login
            and not login.has_done()
        ):
            logger.warning(f"用户 {user_id} 登录超时")
            await org_matcher.send("登录二维码已超时失效。")

    finally:
        if user_id in login_sessions:
            del login_sessions[user_id]
            logger.debug(f"已清理用户 {user_id} 的登录会话")


@credential_status_matcher.handle()
async def handle_credential_status(bot: Bot, event: Event, matcher: Matcher):
    """处理凭证状态查询命令（优化版）"""
    credential = get_credential()

    if not credential:
        await matcher.finish("当前未登录B站账号，请使用 `bili登录` 命令登录。")

    is_valid: Optional[bool] = None
    need_refresh: Optional[bool] = None
    error_msg: Optional[str] = None

    try:
        results = await asyncio.gather(
            credential.check_valid(), credential.check_refresh(), return_exceptions=True
        )
        if isinstance(results[0], Exception):
            raise results[0]
        else:
            is_valid = results[0]  # type: ignore

        if isinstance(results[1], Exception):
            raise results[1]
        else:
            need_refresh = results[1]  # type: ignore
    except Exception as e:
        logger.error("检查凭证状态时出错", e=e)
        error_msg = str(e)

    status_lines = ["B站账号凭证状态摘要："]

    if error_msg:
        status_lines.append(f"❓ 检查失败: {error_msg}")
    else:
        status_lines.append(
            f"凭证有效性: {'✅ 有效' if is_valid else '❌ 无效或已过期'}"
        )
        status_lines.append(
            f"刷新状态: {'⚠️ 需要刷新' if need_refresh else '✅ 无需刷新'}"
        )

    if is_valid is False:
        status_lines.append("\n详细信息：")
        details = {
            "SESSDATA": credential.has_sessdata(),
            "bili_jct": credential.has_bili_jct(),
            "buvid3": credential.has_buvid3(),
            "DedeUserID": credential.has_dedeuserid(),
            "ac_time_value (用于自动刷新)": credential.has_ac_time_value(),
        }
        for name, has_value in details.items():
            status_lines.append(f"{name}: {'✅ 已设置' if has_value else '❌ 未设置'}")

    await matcher.finish("\n".join(status_lines))
