import nonebot
from nonebot.drivers import Driver

from zhenxun.configs.config import BotConfig
from zhenxun.utils.decorator.shop import shop_register

from .data_source import Conversation

driver: Driver = nonebot.get_driver()


@shop_register(
    name="失忆卡",
    price=200,
    des="当你养成失败或真寻变得奇怪时，你需要这个道具。",
    icon="reload_ai_card.png",
)
async def _(user_id: str):
    Conversation.reset(user_id)
    return f"{BotConfig.self_nickname}忘记了你之前说过的话，仿佛一切可以重新开始...！"
