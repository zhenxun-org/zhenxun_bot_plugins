import asyncio
import contextlib

from bilibili_api import exceptions as BiliExceptions
from bilibili_api import login_v2
from bilibili_api.utils.picture import Picture
from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER

from zhenxun.services.log import logger

from ..config import get_credential, save_credential_to_file

login_matcher = on_command("bili登录", permission=SUPERUSER, priority=5, block=True)
credential_status_matcher = on_command(
    "bili状态", permission=SUPERUSER, priority=5, block=True
)

login_sessions: dict[str, login_v2.QrCodeLogin] = {}


@login_matcher.handle()
async def handle_login_start(bot: Bot, event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    if user_id in login_sessions and not login_sessions[user_id].has_done():
        await matcher.send("您当前有一个登录流程正在进行中，请先完成或等待超时。")
        return

    logger.info(f"用户 {user_id} 请求 B站扫码登录")
    await matcher.send("正在生成登录二维码，请稍候...")

    login_instance: login_v2.QrCodeLogin | None = None
    try:
        login_instance = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB)

        logger.debug("调用 login.generate_qrcode()")
        try:
            await login_instance.generate_qrcode()
            logger.debug("generate_qrcode 调用完成")
        except BiliExceptions.ApiException as api_err:
            logger.error(
                f"调用 generate_qrcode 时发生 BiliApiException: {api_err.code} - {api_err.message}"
            )
            await matcher.finish(
                f"连接 B站 API 失败，请稍后再试 (错误: {api_err.message})。"
            )
            return
        except Exception as gen_err:
            logger.error("调用 generate_qrcode 时发生未知错误", e=gen_err)
            await matcher.finish("生成二维码数据时发生未知错误，请检查网络或稍后再试。")
            return

        login_sessions[user_id] = login_instance

        qr_bytes: bytes | None = None
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

        try:
            if qr_bytes:
                await matcher.send(message)
                await matcher.send(MessageSegment.image(qr_bytes))
                logger.debug("登录提示和二维码图片已发送")
            else:
                error_msg = "错误：无法生成二维码图片。登录流程已启动，请关注后续提示或尝试扫描App通知。"
                await matcher.send(message + "\n" + error_msg)
                logger.debug("登录提示（仅文本）已发送")
        except Exception as send_err:
            logger.error("发送登录提示消息失败", e=send_err)
            await matcher.finish("发送二维码失败，请稍后重试。")
            return

        if login_instance.has_qrcode():
            logger.debug("准备启动 check_login_status 任务")
            asyncio.create_task(check_login_status(matcher, user_id))  # noqa: RUF006
            logger.debug("check_login_status 任务已启动")
            matcher.stop_propagation()
        else:
            logger.error("二维码核心数据未生成，无法启动检查任务")
            login_sessions.pop(user_id, None)
            await matcher.finish("获取二维码核心数据失败，请重试。")
            return

    except Exception as e:
        logger.error("启动登录流程时发生意外错误", e=e)
        login_sessions.pop(user_id, None)
        await matcher.finish("启动登录流程时发生错误，请检查日志。")


async def check_login_status(org_matcher: Matcher, user_id: str):
    """后台轮询检查二维码登录状态"""
    login = login_sessions.get(user_id)
    if not login:
        logger.warning(f"尝试检查登录状态时，用户 {user_id} 的会话已不存在")
        return

    check_interval = 2
    timeout = 60
    start_time = asyncio.get_running_loop().time()
    login_succeed = False

    logger.info(f"开始为用户 {user_id} 检查登录状态...")

    while True:
        login = login_sessions.get(user_id)
        if (
            not login
            or login.has_done()
            or asyncio.get_running_loop().time() - start_time > timeout
        ):
            if not login:
                logger.warning(f"用户 {user_id} 登录会话中途丢失")
            elif login.has_done() and not login_succeed:
                logger.info(f"用户 {user_id} 登录已完成 (可能在其他地方处理)")
            elif asyncio.get_running_loop().time() - start_time > timeout:
                logger.warning(f"用户 {user_id} 登录超时")
                with contextlib.suppress(Exception):
                    await org_matcher.send("登录二维码已超时失效。")
            break

        try:
            event = await login.check_state()
            logger.debug(f"用户 {user_id} 登录状态检查: {event.name}")

            if event == login_v2.QrCodeLoginEvents.TIMEOUT:
                break
            elif event == login_v2.QrCodeLoginEvents.SCAN:
                logger.info(f"用户 {user_id} 已扫描，待确认")
            elif event == login_v2.QrCodeLoginEvents.CONF:
                logger.info(f"用户 {user_id} 已确认，登录中")
            elif event == login_v2.QrCodeLoginEvents.DONE:
                logger.info(f"用户 {user_id} 登录成功！")
                credential = login.get_credential()

                try:
                    from bilibili_api import get_session

                    session = get_session()
                    cookie_jar = None
                    if hasattr(session, "cookie_jar"):
                        cookie_jar = getattr(session, "cookie_jar")

                    if cookie_jar:
                        for cookie in cookie_jar:
                            if cookie.key == "buvid3":
                                logger.info(f"成功获取到 buvid3: {cookie.value}")
                                credential.buvid3 = cookie.value
                                break

                    if not credential.buvid3:
                        logger.warning("未能从会话中获取 buvid3，尝试刷新 buvid")
                        try:
                            from bilibili_api import refresh_buvid

                            refresh_buvid()
                            if cookie_jar:
                                for cookie in cookie_jar:
                                    if cookie.key == "buvid3":
                                        logger.info(
                                            f"通过刷新获取到 buvid3: {cookie.value}"
                                        )
                                        credential.buvid3 = cookie.value
                                        break
                        except Exception as refresh_error:
                            logger.error(f"刷新 buvid 时出错: {refresh_error}")
                except Exception as e:
                    logger.error(f"尝试获取 buvid3 时出错: {e}")

                await save_credential_to_file(credential)
                login_succeed = True

                status_msg = "登录成功！Credential 已保存。" + (
                    "\nbuvid3 已成功获取并保存。"
                    if credential.buvid3
                    else "\n警告：未能获取 buvid3，部分功能可能受限。"
                )
                with contextlib.suppress(Exception):
                    await org_matcher.send(status_msg)
                break

        except Exception as e:
            logger.error(f"检查用户 {user_id} 登录状态时出错", e=e)
            with contextlib.suppress(Exception):
                await org_matcher.send("检查登录状态时发生错误，请稍后重试。")
            break

        await asyncio.sleep(check_interval)

    if user_id in login_sessions:
        del login_sessions[user_id]
        logger.debug(f"已清理用户 {user_id} 的登录会话")


@credential_status_matcher.handle()
async def handle_credential_status(bot: Bot, event: Event, matcher: Matcher):
    """处理凭证状态查询命令"""
    credential = get_credential()

    if not credential:
        await matcher.finish("当前未登录B站账号，请使用 bili登录 命令登录。")
        return

    status_lines = ["B站账号登录状态："]

    if credential.has_sessdata():
        status_lines.append("✅ SESSDATA: 已设置")
    else:
        status_lines.append("❌ SESSDATA: 未设置")

    if credential.has_bili_jct():
        status_lines.append("✅ bili_jct: 已设置")
    else:
        status_lines.append("❌ bili_jct: 未设置")

    if credential.has_buvid3():
        status_lines.append("✅ buvid3: 已设置")
    else:
        status_lines.append("❌ buvid3: 未设置")

    if credential.has_dedeuserid():
        status_lines.append("✅ DedeUserID: 已设置")
    else:
        status_lines.append("❌ DedeUserID: 未设置")

    if credential.has_ac_time_value():
        status_lines.append("✅ ac_time_value: 已设置 (支持自动刷新)")
    else:
        status_lines.append("❌ ac_time_value: 未设置 (不支持自动刷新)")

    try:
        is_valid = await credential.check_valid()
        if is_valid:
            status_lines.append("\n✅ 凭证有效，可以正常使用")
        else:
            status_lines.append("\n❌ 凭证无效，请重新登录")
    except Exception as e:
        logger.error("检查凭证有效性时出错", e=e)
        status_lines.append(f"\n❓ 凭证状态检查失败: {e!s}")

    try:
        need_refresh = await credential.check_refresh()
        if need_refresh:
            status_lines.append("⚠️ 凭证需要刷新，将在下次检查时自动刷新")
        else:
            status_lines.append("✅ 凭证不需要刷新")
    except Exception as e:
        logger.error("检查凭证刷新状态时出错", e=e)
        status_lines.append(f"❓ 凭证刷新状态检查失败: {e!s}")

    await matcher.finish("\n".join(status_lines))
