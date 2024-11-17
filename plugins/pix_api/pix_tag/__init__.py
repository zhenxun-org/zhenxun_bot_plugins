from httpx import HTTPStatusError
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Args, Alconna, Arparma, Query, on_alconna
from zhenxun.configs.config import Config
from zhenxun.services.log import logger
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.echart_utils import ChartUtils
from zhenxun.utils.echart_utils.models import Barh
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.utils import PluginExtraData
from .._config import PixResult, base_config
from .._enum import KwType
from .config import TagItem

__plugin_meta__ = PluginMetadata(
    name="TAG统计",
    description="TAG统计",
    usage="""
    指令：
        pixtag ?[10] : 查看排名前10的tag，最大不能超过30
        示例:
            pixtag 20
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        menu_type="PIX图库",
        superuser_help="""
        pix处理 ['a', 'f', 'i'] [id]
        """.strip(),
        version="0.1",
    ).dict(),
)


_add_matcher = on_alconna(
    Alconna("pixtag", Args["num?", int]),
    priority=5,
    block=True,
)


@_add_matcher.handle(parameterless=[CheckConfig("pix", "pix_api")])
async def _(session: Uninfo, arparma: Arparma, num: Query[int] = Query("num", 10)):
    if num.result > 30:
        return MessageUtils.build_message("查询最大不能超过30...").finish()
    api = Config.get_config("pix", "pix_api")
    api = f"{api}/pix/tag_rank"
    json_data = {"num": num.result}
    logger.debug(f"尝试调用pix api: {api}, 参数: {json_data}")
    headers = None
    if token := base_config.get("token"):
        headers = {"Authorization": token}
    try:
        res = await AsyncHttpx.get(api, params=json_data, headers=headers)
        res.raise_for_status()
    except HTTPStatusError as e:
        logger.error("pix图库API出错...", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message(
            f"pix图库API出错啦！ code: {e.response.status_code}"
        ).finish()
    result = PixResult(**res.json())
    if not result.suc:
        await MessageUtils.build_message(result.info).finish()
    data_list = [TagItem(**v) for v in result.data]
    if not data_list:
        await MessageUtils.build_message("没有tag数据...").finish()
    data_list.reverse()
    x_index = []
    data = []
    for v in data_list:
        x_index.append(v.tag)
        data.append(v.num)
    barh = Barh(data=data, category_data=x_index, title="PIX tag统计")
    await MessageUtils.build_message(await ChartUtils.barh(barh)).send()
    logger.info("查看PIX tag统计", arparma.header_result, session=session)
