from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

url = "https://v2.alapi.cn/api/soul"

__plugin_meta__ = PluginMetadata(
    name="鸡汤",
    description="喏，亲手为你煮的鸡汤",
    usage="""
    不喝点什么感觉有点不舒服
    指令：
        鸡汤
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        commands=[Command(command="鸡汤")],
        configs=[
            RegisterConfig(
                module="alapi",
                key="ALAPI_TOKEN",
                value=None,
                help="在https://admin.alapi.cn/user/login登录后获取token",
            )
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("鸡汤"),
    priority=5,
    block=True,
)


async def get_data(url: str, params: dict | None = None) -> tuple[dict | str, int]:
    """获取ALAPI数据

    参数:
        url: 请求链接
        params: 参数

    返回:
        tuple[dict | str, int]: 返回信息
    """
    if not params:
        params = {}
    params["token"] = Config.get_config("alapi", "ALAPI_TOKEN")
    try:
        data = (await AsyncHttpx.get(url, params=params, timeout=5)).json()
        if data["code"] == 200:
            if not data["data"]:
                return "没有搜索到...", 997
            return data, 200
        else:
            if data["code"] == 101:
                return "缺失ALAPI TOKEN，请在配置文件中填写！", 999
            return f'发生了错误...code：{data["code"]}', 999
    except TimeoutError:
        return "超时了....", 998


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    try:
        data, code = await get_data(url)
        if code != 200 and isinstance(data, str):
            await MessageUtils.build_message(data).finish(reply_to=True)
        await MessageUtils.build_message(data["data"]["content"]).send(reply_to=True)  # type: ignore
        logger.info(
            " 发送鸡汤:" + data["data"]["content"],  # type:ignore
            arparma.header_result,
            session=session,
        )
    except Exception as e:
        await MessageUtils.build_message("鸡汤煮坏掉了...").send()
        logger.error("鸡汤煮坏掉了", e=e)
