import random

from nonebot.params import Depends
from nonebot_plugin_uninfo import Uninfo

from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .config import (
    BLUE_ST,
    FACTORY_NEW_E,
    FIELD_TESTED_E,
    FIELD_TESTED_S,
    KNIFE,
    KNIFE_ST,
    MINIMAL_WEAR_E,
    MINIMAL_WEAR_S,
    PINK,
    PINK_ST,
    PURPLE,
    PURPLE_ST,
    RED,
    RED_ST,
    WELL_WORN_E,
    WELL_WORN_S,
)
from .models.buff_skin import BuffSkin


def GetGroupId():
    """获取群组id"""

    async def dependency(session: Uninfo):
        group_id = session.group.id if session.group else None
        if not group_id:
            await MessageUtils.build_message("群组id为空").finish()
        return group_id

    return Depends(dependency)


def get_wear(rand: float) -> str:
    """判断磨损度

    Args:
        rand: 随机rand

    Returns:
        str: 磨损名称
    """
    if rand <= FACTORY_NEW_E:
        return "崭新出厂"
    if MINIMAL_WEAR_S <= rand <= MINIMAL_WEAR_E:
        return "略有磨损"
    if FIELD_TESTED_S <= rand <= FIELD_TESTED_E:
        return "久经沙场"
    return "破损不堪" if WELL_WORN_S <= rand <= WELL_WORN_E else "战痕累累"


def random_color_and_st(rand: float) -> tuple[str, bool]:
    """获取皮肤品质及是否暗金

    参数:
        rand: 随机rand

    返回:
        tuple[str, bool]: 品质，是否暗金
    """
    if rand <= KNIFE:
        return ("KNIFE", True) if random.random() <= KNIFE_ST else ("KNIFE", False)
    elif KNIFE < rand <= RED:
        return ("RED", True) if random.random() <= RED_ST else ("RED", False)
    elif RED < rand <= PINK:
        return ("PINK", True) if random.random() <= PINK_ST else ("PINK", False)
    elif PINK < rand <= PURPLE:
        return ("PURPLE", True) if random.random() <= PURPLE_ST else ("PURPLE", False)
    else:
        return ("BLUE", True) if random.random() <= BLUE_ST else ("BLUE", False)


async def random_skin(case_name: str, num: int) -> list[tuple[BuffSkin, float]]:
    """抽取随机皮肤

    参数:
        case_name: 箱子名称
        num: 数量

    返回:
        list[tuple[BuffSkin, float]]: 随机皮肤列表
    """
    case_name = case_name.replace("武器箱", "").replace(" ", "")
    color_map = {}
    for _ in range(num):
        rand = random.random()
        # 尝试降低磨损
        if rand > MINIMAL_WEAR_E:
            for _ in range(2):
                if random.random() < 0.5:
                    logger.debug(f"[START]开箱随机磨损触发降低磨损条件: {rand}")
                    if random.random() < 0.2:
                        rand /= 3
                    else:
                        rand /= 2
                    logger.debug(f"[END]开箱随机磨损触发降低磨损条件: {rand}")
                    break
        abrasion = get_wear(rand)
        logger.debug(f"开箱随机磨损: {rand} | {abrasion}")
        color, is_stattrak = random_color_and_st(rand)
        if not color_map.get(color):
            color_map[color] = {}
        if is_stattrak:
            if not color_map[color].get(f"{abrasion}_st"):
                color_map[color][f"{abrasion}_st"] = []
            color_map[color][f"{abrasion}_st"].append(rand)
        else:
            if not color_map[color].get(abrasion):
                color_map[color][f"{abrasion}"] = []
            color_map[color][f"{abrasion}"].append(rand)
    skin_list = []
    for color in color_map:
        for abrasion in color_map[color]:
            rand_list = color_map[color][abrasion]
            is_stattrak = "_st" in abrasion
            abrasion = abrasion.replace("_st", "")
            skin_list_ = await BuffSkin.random_skin(
                len(rand_list), color, abrasion, is_stattrak, case_name
            )
            skin_list += list(zip(skin_list_, rand_list))
    return skin_list
