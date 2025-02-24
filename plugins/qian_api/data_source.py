from nonebot_plugin_alconna import (
    Image,
    UniMsg,
)
from nonebot_plugin_waiter import waiter

from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils


async def get_image_data() -> bytes:
    @waiter(waits=["message"], keep_session=True)
    async def check(message: UniMsg):
        return message[Image]

    resp = await check.wait("请发送需要操作的图片！", timeout=60)
    if resp is None:
        await MessageUtils.build_message("等待超时...").finish()
    if not resp:
        await MessageUtils.build_message(
            "未获取需要操作的图片，请重新发送命令！"
        ).finish()
    if not resp[0].url:
        await MessageUtils.build_message("获取图片失败，请重新发送命令！").finish()
    return await AsyncHttpx.get_content(resp[0].url)


def parser(data: dict) -> tuple[str | None, str | None]:
    if data.get("code") == 200 and data.get("data"):
        return data["data"], None
    if data.get("url"):
        return data["url"], None
    error_msg = data.get("msg", "未知API错误")
    error_code = data.get("code", "未知状态码")
    return None, f"API处理失败: {error_msg} (代码: {error_code})"
