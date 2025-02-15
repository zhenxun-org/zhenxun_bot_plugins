import nonebot
from nonebot.drivers import Driver

from zhenxun.configs.config import BotConfig
from zhenxun.utils.decorator.shop import shop_register

from .data_source import Conversation

driver: Driver = nonebot.get_driver()


@shop_register(
    name="失忆卡",
    price=200,
    des=f"当你养成失败或{BotConfig.self_nickname}变得奇怪时，你需要这个道具。",
    icon="reload_ai_card.png",
)
async def _(user_id: str):
    await Conversation.reset(user_id, None)
    return f"{BotConfig.self_nickname}忘记了你之前说过的话，仿佛一切可以重新开始..."


@shop_register(
    name="群组失忆卡",
    price=300,
    des=f"当群聊内{BotConfig.self_nickname}变得奇怪时，你需要这个道具。",
    icon="reload_ai_card1.png",
)
async def _(user_id: str, group_id: str):
    await Conversation.reset(user_id, group_id)
    return f"前面忘了，后面忘了，{BotConfig.self_nickname}重新睁开了眼睛..."
