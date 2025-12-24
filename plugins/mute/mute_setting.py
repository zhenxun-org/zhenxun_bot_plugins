from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, Option, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.rules import ensure_group
from zhenxun.utils.utils import get_entity_ids

from ._data_source import base_config, mute_manager

__plugin_meta__ = PluginMetadata(
    name="刷屏禁言",
    description="刷屏禁言相关操作",
    usage=f"""
    刷屏禁言相关操作，需要 {BotConfig.self_nickname} 有群管理员权限
    指令：
        刷屏设置: 查看当前设置
        -c [count]: 检测最大次数
        -t [time]: 规定时间内
        -d [duration]: 禁言时长
        示例:
            刷屏设置 -c 10: 设置最大次数为10
            刷屏设置 -t 100 -d 20: 设置规定时间和禁言时长
            刷屏设置 -d 10: 设置禁言时长为10
        * 即 X 秒内发送同样消息 N 次，禁言 M 分钟 *
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1-473ecd8",
        menu_type="其他",
        plugin_type=PluginType.ADMIN,
        admin_level=base_config.get("MUTE_LEVEL", 5),
        configs=[
            RegisterConfig(
                key="MUTE_LEVEL",
                value=5,
                help="更改禁言设置的管理权限",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_COUNT",
                value=10,
                help="刷屏禁言默认检测次数",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_TIME",
                value=7,
                help="刷屏检测默认规定时间",
                default_value=7,
                type=int,
            ),
            RegisterConfig(
                key="MUTE_DEFAULT_DURATION",
                value=10,
                help="刷屏检测默禁言时长（分钟）",
                default_value=10,
                type=int,
            ),
        ],
    ).to_dict(),
)


_setting_matcher = on_alconna(
    Alconna(
        "刷屏设置",
        Option("-t|--time", Args["time", int], help_text="检测时长"),
        Option("-c|--count", Args["count", int], help_text="检测次数"),
        Option("-d|--duration", Args["duration", int], help_text="禁言时长"),
    ),
    rule=ensure_group,
    block=True,
    priority=5,
)


@_setting_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    time: Match[int],
    count: Match[int],
    duration: Match[int],
):
    entity_ids = get_entity_ids(session)
    _time = time.result if time.available else None
    _count = count.result if count.available else None
    _duration = duration.result if duration.available else None
    group_data = mute_manager.get_group_data(entity_ids.group_id or "0")
    if _time is None and _count is None and _duration is None:
        await MessageUtils.build_message(
            f"最大次数：{group_data.count} 次\n"
            f"规定时间：{group_data.time} 秒\n"
            f"禁言时长：{group_data.duration:.2f} 分钟\n"
            f"【在规定时间内发送相同消息超过最大次数则禁言\n当禁言时长为0时关闭此功能】"
        ).finish(reply_to=True)
    if _time is not None:
        group_data.time = _time
    if _count is not None:
        group_data.count = _count
    if _duration is not None:
        group_data.duration = _duration
    await MessageUtils.build_message("设置成功!").send(reply_to=True)
    logger.info(
        f"设置禁言配置 time: {_time}, count: {_count}, duration: {_duration}",
        arparma.header_result,
        session=session,
    )
    mute_manager.save_data()
