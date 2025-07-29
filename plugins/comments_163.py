from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

comments_163_url = "https://v3.alapi.cn/api/comment"

__plugin_meta__ = PluginMetadata(
    name="网易云热评",
    description="生了个人，我很抱歉",
    usage="""
    到点了，还是防不了下塔
    指令：
        网易云热评/到点了/12点了
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        commands=[Command(command="网易云热评/到点了")],
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
    Alconna("网易云热评"),
    priority=5,
    block=True,
)

_matcher.shortcut(
    "(到点了|12点了)",
    command="网易云热评",
    arguments=[],
    prefix=True,
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
            return f"发生了错误...code：{data['code']}", 999
    except TimeoutError:
        return "超时了....", 998


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    data, code = await get_data(comments_163_url)
    if code != 200 and isinstance(data, str):
        await MessageUtils.build_message(data).finish(reply_to=True)
    data = data["data"]  # type: ignore
    comment = data["comment_content"]  # type: ignore
    song_name = data["title"]  # type: ignore
    await MessageUtils.build_message(f"{comment}\n\t——《{song_name}》").send(
        reply_to=True
    )
    logger.info(
        f" 发送网易云热评: {comment} \n\t\t————{song_name}",
        arparma.header_result,
        session=session,
    )
