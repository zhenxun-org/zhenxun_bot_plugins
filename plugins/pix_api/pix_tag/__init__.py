from httpx import HTTPStatusError
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Query, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.depends import CheckConfig
from zhenxun.utils.echart_utils import ChartUtils
from zhenxun.utils.echart_utils.models import Barh
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .._config import PixResult, base_config
from .config import TagItem

__plugin_meta__ = PluginMetadata(
    name="TAG缁熻",
    description="TAG缁熻",
    usage="""
    鎸囦护锛?
        pixtag ?[10] : 鏌ョ湅鎺掑悕鍓?0鐨則ag锛屾渶澶т笉鑳借秴杩?0
        绀轰緥:
            pixtag 20
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        menu_type="PIX鍥惧簱",
        superuser_help="""
        pix澶勭悊 ['a', 'f', 'i'] [id]
        """.strip(),
        version="0.1",
        commands=[Command(command="pixtag ?[10]")],
    ).to_dict(),
)


_add_matcher = on_alconna(
    Alconna("pixtag", Args["num?", int]),
    priority=5,
    block=True,
)


@_add_matcher.handle(parameterless=[CheckConfig("pix", "pix_api")])
async def _(session: Uninfo, arparma: Arparma, num: Query[int] = Query("num", 10)):
    if num.result <= 0:
        return await MessageUtils.build_message("查询数量必须大于 0...").finish()
    if num.result > 30:
        return await MessageUtils.build_message("查询最大不能超过 30...").finish()
    api = Config.get_config("pix", "pix_api")
    api = f"{api}/pix/tag_rank"
    json_data = {"num": num.result}
    logger.debug(f"灏濊瘯璋冪敤pix api: {api}, 鍙傛暟: {json_data}")
    headers = None
    if token := base_config.get("token"):
        headers = {"Authorization": token}
    try:
        res = await AsyncHttpx.get(
            api, params=json_data, headers=headers, timeout=base_config.get("timeout")
        )
        res.raise_for_status()
    except HTTPStatusError as e:
        logger.error(
            "pix鍥惧簱API鍑洪敊...", arparma.header_result, session=session, e=e
        )
        await MessageUtils.build_message(
            f"pix鍥惧簱API鍑洪敊鍟︼紒 code: {e.response.status_code}"
        ).finish()
    result = PixResult(**res.json())
    if not result.suc:
        await MessageUtils.build_message(result.info).finish()
    data_list = [TagItem(**v) for v in result.data]
    if not data_list:
        await MessageUtils.build_message("娌℃湁tag鏁版嵁...").finish()
    data_list.reverse()
    x_index = []
    data = []
    for v in data_list:
        x_index.append(v.tag)
        data.append(v.num)
    barh = Barh(data=data, category_data=x_index, title="PIX tag缁熻")
    await MessageUtils.build_message(await ChartUtils.barh(barh)).send()
    logger.info("鏌ョ湅PIX tag缁熻", arparma.header_result, session=session)
