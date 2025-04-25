import asyncio
from typing import Optional, Dict, List, Union
from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import AlconnaMatcher, UniMsg, Image, Text

from bilibili_api import login_v2, exceptions as BiliExceptions
from bilibili_api.utils.picture import Picture

from zhenxun.services.log import logger
from ..config import save_credential_to_file

login_matcher = on_command(
    "bili登录", aliases={"b站登录"}, permission=SUPERUSER, priority=5, block=True
)

login_sessions: Dict[str, login_v2.QrCodeLogin] = {}


@login_matcher.handle()
async def handle_login_start(bot: Bot, event: Event, matcher: AlconnaMatcher):
    user_id = event.get_user_id()
    if user_id in login_sessions and not login_sessions[user_id].has_done():
        await matcher.send("您当前有一个登录流程正在进行中，请先完成或等待超时。")
        return

    logger.info(f"用户 {user_id} 请求 B站扫码登录")
    await matcher.send("正在生成登录二维码，请稍候...")

    login_instance: Optional[login_v2.QrCodeLogin] = None
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

        message_to_send_list: List[Union[Text, Image]] = []
        message_to_send_list.append(
            Text("请使用哔哩哔哩手机客户端扫描下方二维码登录：")
        )
        if qr_bytes:
            message_to_send_list.append(Image(raw=qr_bytes, name="bili_login_qr.png"))
        else:
            message_to_send_list.append(
                Text(
                    "\n错误：无法生成二维码图片。登录流程已启动，请关注后续提示或尝试扫描App通知。"
                )
            )
        message_to_send = UniMsg(message_to_send_list)

        try:
            await matcher.send(message_to_send)
            logger.debug("登录提示（图片或文本）已发送")
        except Exception as send_err:
            logger.error("发送登录提示消息失败", e=send_err)
            await matcher.finish("发送二维码失败，请稍后重试。")
            return

        if login_instance.has_qrcode():
            logger.debug("准备启动 check_login_status 任务")
            asyncio.create_task(check_login_status(matcher, user_id))
            logger.debug("check_login_status 任务已启动")
            await matcher.stop_propagation()
        else:
            logger.error("二维码核心数据未生成，无法启动检查任务")
            if user_id in login_sessions:
                del login_sessions[user_id]
            await matcher.finish("获取二维码核心数据失败，请重试。")
            return

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
                try:
                    await org_matcher.send("登录二维码已超时失效。", at_sender=True)
                except Exception:
                    pass
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
                await save_credential_to_file(credential)
                login_succeed = True
                try:
                    await org_matcher.send(
                        "登录成功！Credential 已保存。", at_sender=True
                    )
                except Exception:
                    pass
                break

        except Exception as e:
            logger.error(f"检查用户 {user_id} 登录状态时出错", e=e)
            try:
                await org_matcher.send(
                    "检查登录状态时发生错误，请稍后重试。", at_sender=True
                )
            except Exception:
                pass
            break

        await asyncio.sleep(check_interval)

    if user_id in login_sessions:
        del login_sessions[user_id]
        logger.debug(f"已清理用户 {user_id} 的登录会话")
