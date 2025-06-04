from datetime import datetime, timedelta

from nonebot.adapters.onebot.v11 import ActionFailed, Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from tortoise.functions import Count, Sum

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import (
    AICallableParam,
    AICallableProperties,
    AICallableTag,
    PluginExtraData,
    PluginSetting,
)
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .models import LikeLog

_matcher = on_alconna(Alconna("re:(点赞|赞我)"), priority=5, block=True, rule=to_me())

_info_matcher = on_alconna(Alconna("点赞信息"), priority=5, block=True)


@_matcher.handle()
async def send_like(bot: Bot, session: Uninfo):

    now = datetime.now()
    filter_time: datetime = now - timedelta(
        hours=now.hour, minutes=now.minute, seconds=now.second
    )
    if await LikeLog.exists(user_id=session.user.id, create_time__gte=filter_time):
        await MessageUtils.build_message("请不要这么贪心，今天已经点过赞了哦！").finish(
            at_sender=True
        )
    like_count = 0
    try:
        for _ in range(5):
            await bot.send_like(user_id=int(session.user.id), times=10)
            like_count += 10
    except ActionFailed:
        pass
    except Exception as e:
        logger.error("点赞失败", "点赞", session=session, e=e)
        await MessageUtils.build_message("点赞失败了...").send(reply_to=True)
    await LikeLog.create(user_id=session.user.id, count=like_count)
    await MessageUtils.build_message(
        f"{BotConfig.self_nickname}给你点了 {like_count} 个赞哦，不客气！"
    ).send(reply_to=True)
    logger.info(f"成功点赞 {like_count} 次", "点赞", session=session)


@_info_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma):
    data = (
        await LikeLog.filter(user_id=session.user.id)
        .annotate(sum=Sum("count"), days=Count("id"))
        .values("sum", "days")
    )
    sum_count = data[0]["sum"]
    if not sum_count:
        await MessageUtils.build_message(
            f"{BotConfig.self_nickname}还没有给你点过赞哦..."
        ).finish(reply_to=True)
    days = data[0]["days"]
    await MessageUtils.build_message(
        f"总共累计点赞 {days} 天， 共给你点了 {sum_count} 个赞哦，"
        f"记得谢谢{BotConfig.self_nickname}！"
    ).send(reply_to=True)


__plugin_meta__ = PluginMetadata(
    name="点赞小助手",
    description=f"{BotConfig.self_nickname}觉得很赞！",
    usage="""
    需要好感度到达10及以上才行哦

    指令：
        点赞/赞我
        点赞信息
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        setting=PluginSetting(impression=10),
        smart_tools=[
            AICallableTag(
                name="send_like",
                description="如果你想为某人点赞，调用此方法",
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "user_id": AICallableProperties(
                            type="string", description="你想点赞的那个人QQ号"
                        ),
                        "times": AICallableProperties(
                            type="string",
                            description="你想点赞的次数，如果用户未指定，你默认填写1",
                        ),
                    },
                    required=["user_id", "times"],
                ),
                func=send_like,
            )
        ],
    ).to_dict(),
)
