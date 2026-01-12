import traceback

from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot_plugin_alconna import Alconna, on_alconna

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from .data_source import DeltaService, COST_MAPPING

# 实例化服务
delta_service = DeltaService()
command_matcher = on_alconna(Alconna("re:(洲|粥)"), priority=1, block=True)


@command_matcher.handle()
async def handle_delta_command(bot: Bot, event: Event):
    try:
        # 1. 获取数据
        data = await delta_service.get_game_data()

        overview = data["overview"]
        cpv_data = data["cpv"]

        nodes = []

        def add_node(content: str):
            nodes.append(
                {
                    "type": "node",
                    "data": {"name": "真寻", "uin": event.self_id, "content": content},
                }
            )

        pw_msg = delta_service.process_passwords(overview.get("bdData", {}))
        add_node(pw_msg)

        profit_msg = delta_service.process_profits(overview.get("spData", {}))
        add_node(profit_msg)

        market_schemes = {
            s["targetValue"]: s for s in cpv_data if s.get("schemeType") == "market"
        }

        add_node("凑战备方案:")
        for level in range(5):
            target_cost = COST_MAPPING[level]
            scheme = market_schemes.get(target_cost)
            if scheme:
                items = "\n".join(
                    [i["objectName"] for i in scheme.get("schemeItems", [])]
                )
                msg = f"{target_cost}:\n{items}\n成本:{scheme['totalHafCost']}"
                add_node(msg)

        add_node("数据来源于: KK日报 & 官方\n若有侵权请联系删除")

        if isinstance(event, Event):
            if getattr(event, "group_id", None):
                await bot.send_group_forward_msg(
                    group_id=event.group_id, messages=nodes
                )
            else:
                await bot.send_private_forward_msg(
                    user_id=event.user_id, messages=nodes
                )

    except Exception:
        logger.error(f"三角洲插件出错: {traceback.format_exc()}")
        await MessageUtils.build_message("获取数据失败，请稍后再试...").send()
