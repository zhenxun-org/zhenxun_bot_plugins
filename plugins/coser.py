import asyncio
from pathlib import Path
import re
import time

from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.withdraw_manage import WithdrawManager

__plugin_meta__ = PluginMetadata(
    name="coser",
    description="三次元也不戳，嘿嘿嘿",
    usage="""
    ?N连cos/coser
    示例: cos
    示例: 5连cos （单次请求张数小于9）
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        commands=[Command(command="n（数字）连cos")],
        configs=[
            RegisterConfig(
                key="WITHDRAW_COS_MESSAGE",
                value=(0, 1),
                help="自动撤回，参1：延迟撤回色图时间(秒)，0 为关闭 | 参2：监控聊天类型，0(私聊) 1(群聊) 2(群聊+私聊)",
                default_value=(0, 1),
                type=tuple[int, int],
            ),
            RegisterConfig(
                key="MAX_ONCE_NUM2FORWARD",
                value=None,
                help="单次发送的图片数量达到指定值时转发为合并消息",
                default_value=None,
                type=int,
            ),
        ],
    ).to_dict(),
)

_matcher = on_alconna(Alconna("get-cos", Args["num", int, 1]), priority=5, block=True)

_matcher.shortcut(
    r"cos",
    command="get-cos",
    arguments=["1"],
    prefix=True,
)

_matcher.shortcut(
    r"(?P<num>\d)(张|个|条|连)cos",
    command="get-cos",
    arguments=["{num}"],
    prefix=True,
)


url = "https://v2.xxapi.cn/api/yscos"


async def _fetch_image(index: int) -> tuple[int, bytes | str | None]:
    """获取单张图片，返回 (索引, 图片数据或URL)"""
    try:
        response = await AsyncHttpx.get(url)
        content_type = response.headers.get("content-type", "")
        if "image" in content_type:
            return (index, response.content)
        else:
            text = response.text
            match = re.search(r'(https?://[^\s"\'\]}>]+)', text)
            if match:
                return (index, match.group(1))
    except Exception:
        pass
    return (index, None)


@_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    num: int,
):
    withdraw_time = Config.get_config("coser", "WITHDRAW_COS_MESSAGE")
    max_once_num2forward = Config.get_config("coser", "MAX_ONCE_NUM2FORWARD")

    # 并发获取所有图片数据或URL
    tasks = [_fetch_image(i) for i in range(num)]
    results = await asyncio.gather(*tasks)

    # 处理结果：分离直接获取的图片数据和需要下载的URL
    image_data_map: dict[int, bytes | Path] = {}
    url_to_download: list[tuple[int, str]] = []

    for index, data in results:
        if data is None:
            continue
        if isinstance(data, bytes):
            image_data_map[index] = data
        else:
            url_to_download.append((index, data))

    # 并发下载需要下载的图片
    if url_to_download:
        path_list = [
            TEMP_PATH / f"cos_cc{int(time.time())}_{idx}.jpeg"
            for idx, _ in url_to_download
        ]
        url_list = [u for _, u in url_to_download]
        download_results = await AsyncHttpx.gather_download_file(
            url_list, path_list, limit_async_number=5
        )
        for i, success in enumerate(download_results):
            if success:
                idx = url_to_download[i][0]
                image_data_map[idx] = path_list[i]

    # 按顺序发送图片
    if not image_data_map:
        await MessageUtils.build_message("获取图片失败，你cos给我看！").send()
        logger.error(
            "cos错误: 所有图片获取失败", arparma.header_result, session=session
        )
        return

    message_list = [image_data_map[index] for index in sorted(image_data_map.keys())]
    is_forward = max_once_num2forward and len(image_data_map) >= max_once_num2forward
    try:
        receipt = await MessageUtils.build_message(
            message_list,  # pyright: ignore[reportArgumentType]
            auto_forward_msg=session if is_forward else None,
        ).send()
        message_id = receipt.msg_ids[0]["message_id"]
        if message_id and WithdrawManager.check(session, withdraw_time):
            WithdrawManager.append(
                bot,
                message_id,
                withdraw_time[0],
            )
    except Exception as e:
        logger.error(
            "cos发送错误",
            arparma.header_result,
            session=session,
            e=e,
        )
        return
