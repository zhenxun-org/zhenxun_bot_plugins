from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Field, Image, on_alconna
from nonebot_plugin_session import EventSession
from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

cover_url = "https://v2.alapi.cn/api/bilibili/cover"

__plugin_meta__ = PluginMetadata(
    name="b封面",
    description="快捷的b站视频封面获取方式",
    usage="""
    b封面 [链接/av/bv/cv/直播id]
    示例:b封面 av86863038
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        menu_type="一些工具",
        commands=[Command(command="b封面 [链接/av/bv/cv/直播id]")],
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
    Alconna(
        "b封面",
        Args[
            "url",
            str,
            Field(
                missing_tips=lambda: "请在命令后跟随B站视频链接！",
            ),
        ],
    ),
    skip_for_unmatch=False,
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
            return (data, 200) if data["data"] else ("没有搜索到...", 997)
        if data["code"] == 101:
            return "缺失ALAPI TOKEN，请在配置文件中填写！", 999
        return f"发生了错误...code：{data['code']}", 999
    except TimeoutError:
        return "超时了....", 998


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma, url: str):
    params = {"c": url}
    data, code = await get_data(cover_url, params)
    if code != 200 and isinstance(data, str):
        await MessageUtils.build_message(data).finish(reply_to=True)
    data = data["data"]  # type: ignore
    title = data["title"]  # type: ignore
    img = data["cover"]  # type: ignore
    await MessageUtils.build_message([f"title：{title}\n", Image(url=img)]).send(
        reply_to=True
    )
    logger.info(
        f" 获取b站封面: {title} url：{img}", arparma.header_result, session=session
    )
