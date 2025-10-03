import asyncio
from typing import Optional, Dict, cast

from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import MessageSegment
import aiohttp
from bilibili_api import login_v2, Picture
from bilibili_api import exceptions as BiliExceptions
from bilibili_api.utils.network import get_session

from zhenxun.services.log import logger
from ..config import save_credential_to_file, get_credential

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
    scan_message_sent = False  # 新增一个标志位，用于记录是否已发送"扫描成功"消息

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
                    # 仅在第一次检测到扫描状态时发送消息
                    logger.info(f"用户 {user_id} 已扫描，待确认")
                    await org_matcher.send("扫描成功，请在手机上确认登录。")
                    scan_message_sent = True  # 更新标志位，防止重复发送
                elif event == login_v2.QrCodeLoginEvents.DONE:
                    logger.info(f"用户 {user_id} 登录成功！")
                    credential = login.get_credential()

                    try:
                        session = get_session()
                        if hasattr(session, "cookie_jar"):
                            session = cast("aiohttp.ClientSession", session)
                            for cookie in session.cookie_jar:
                                if cookie.key == "buvid3":
                                    logger.info(f"成功获取到 buvid3: {cookie.value}")
                                    credential.buvid3 = cookie.value
                                    break
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
