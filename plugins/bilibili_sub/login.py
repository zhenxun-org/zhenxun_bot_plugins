import time
from io import BytesIO

from bilireq.login import Login
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Args, on_alconna

from .auth import AuthManager
from .utils import calc_time_total
from ...utils.message import MessageUtils

blive_check = on_alconna(Alconna("bil_check"), aliases={"检测b站","检测b站登录", "b站登录检测"}, permission=SUPERUSER,
                         priority=5,
                         block=True)
blive_login = on_alconna(Alconna("bil_login"), aliases={"登录b站", "b站登录"}, permission=SUPERUSER,
                         priority=5,
                         block=True)
blive_logout = on_alconna(
    Alconna("bil_logout", Args["uid", int]), aliases={"退出b站", "退出b站登录", "b站登录退出"}, permission=SUPERUSER,
    priority=5,
    block=True, )


@blive_check.handle()
async def _():
    if not AuthManager.grpc_auths:
        await MessageUtils.build_message("没有缓存的登录信息").finish()
    msgs = []
    for auth in AuthManager.grpc_auths:
        token_time = calc_time_total(auth.tokens_expired - int(time.time()))
        cookie_time = calc_time_total(auth.cookies_expired - int(time.time()))
        msg = (
            f"账号uid: {auth.uid}\n"
            f"token有效期: {token_time}\n"
            f"cookie有效期: {cookie_time}"
        )
        msgs.append(msg)
    await MessageUtils.build_message("\n----------\n".join(msgs)).finish()


@blive_login.handle()
async def _(matcher: Matcher):
    login = Login()
    qr_url = await login.get_qrcode_url()
    logger.debug(f"qrcode login url: {qr_url}")
    img = await login.get_qrcode(qr_url)
    if not img:
        await MessageUtils.build_message("获取二维码失败").finish()
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_data = buffered.getvalue()
    await MessageUtils.build_message(img_data).send()
    try:
        auth = await login.qrcode_login(interval=5)
        assert auth, "登录失败，返回数据为空"
        logger.debug(auth.data)
        AuthManager.add_auth(auth)
    except Exception as e:
        await MessageUtils.build_message(f"登录失败: {e}").finish()
    await MessageUtils.build_message("登录成功，已将验证信息缓存至文件").finish()


@blive_logout.handle()
async def _(uid: int):
    if msg := AuthManager.remove_auth(uid):
        await MessageUtils.build_message(msg).finish()
    await MessageUtils.build_message(f"账号 {uid} 已退出登录").finish()
