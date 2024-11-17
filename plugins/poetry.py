from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="古诗",
    description="为什么突然文艺起来了！",
    usage="""
    平白无故念首诗
    示例：念诗/来首诗/念首诗
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        configs=[
            RegisterConfig(
                module="alapi",
                key="ALAPI_TOKEN",
                value=None,
                help="在https://admin.alapi.cn/user/login登录后获取token",
            )
        ],
    ).dict(),
)

_matcher = on_alconna(
    Alconna("念诗"),
    priority=5,
    block=True,
)

_matcher.shortcut(
    "(来首诗|念首诗)",
    command="念诗",
    arguments=[],
    prefix=True,
)


poetry_url = "https://v2.alapi.cn/api/shici"


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
    data, code = await get_data(poetry_url)
    if code != 200 and isinstance(data, str):
        await MessageUtils.build_message(data).finish(reply_to=True)
    data = data["data"]  # type: ignore
    content = data["content"]  # type: ignore
    title = data["origin"]  # type: ignore
    author = data["author"]  # type: ignore
    await MessageUtils.build_message(f"{content}\n\t——{author}《{title}》").send(
        reply_to=True
    )
    logger.info(
        f" 发送古诗: f'{content}\n\t--{author}《{title}》'",
        arparma.header_result,
        session=session,
    )
