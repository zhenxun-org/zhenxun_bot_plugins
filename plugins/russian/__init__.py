from pathlib import Path

from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Arparma, Match
from nonebot_plugin_alconna import At as alcAt
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import prompt

from zhenxun import ui
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.depends import UserName
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import get_entity_ids

from .command import (
    _accept_matcher,
    _rank_matcher,
    _record_matcher,
    _refuse_matcher,
    _russian_matcher,
    _settlement_matcher,
    _shoot_matcher,
)
from .config import EXPIRE_TIME
from .data_source import Russian, russian_manager
from .models.russian_user import RussianUser

__plugin_meta__ = PluginMetadata(
    name="俄罗斯轮盘",
    description="虽然是运气游戏，但这可是战场啊少年",
    usage=f"""
    又到了决斗时刻【新增随机左轮效果】
    指令：
        装弹 [子弹数] ?[金额] ?[at]:
                开启游戏，装填子弹，可选自定义金额和装备，或邀请决斗对象
        接受对决 ?[武器类型] : 接受当前存在的对决，可选择装备
        拒绝对决: 拒绝邀请的对决
        开枪: 开出未知的一枪
        结算: 强行结束当前比赛 (仅当一方未开枪超过{EXPIRE_TIME}秒时可使用)
        我的战绩: 对，你的战绩
        轮盘胜场排行
        轮盘败场排行
        轮盘欧洲人排行
        轮盘慈善家排行
        轮盘最高连胜排行
        轮盘最高连败排行: 各种排行榜
        * 注：同一时间群内只能有一场对决 *
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2-89d294e",
        menu_type="群内小游戏",
        commands=[
            Command(command="装弹 [子弹数] ?[金额] ?[at]"),
            Command(command="接受对决"),
            Command(command="拒绝对决"),
            Command(command="开枪"),
            Command(command="结算"),
            Command(command="我的战绩"),
            Command(command="装备列表"),
            Command(command="轮盘胜场排行"),
            Command(command="轮盘败场排行"),
            Command(command="轮盘欧洲人排行"),
            Command(command="轮盘慈善家排行"),
            Command(command="轮盘最高连胜排行"),
            Command(command="轮盘最高连败排行"),
        ],
        configs=[
            RegisterConfig(
                key="MAX_RUSSIAN_BET_GOLD",
                value=1000,
                help="俄罗斯轮盘最大赌注金额",
                default_value=1000,
                type=int,
            )
        ],
    ).to_dict(),
)


@_russian_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    num: Match[str],
    money: Match[int],
    at_user: Match[alcAt],
    uname: str = UserName(),
):
    entity = get_entity_ids(session)
    if not entity.group_id:
        await MessageUtils.build_message("群组id不能为空...").finish()
    real_money = money.result if money.available else 200
    if real_money <= 0:
        await MessageUtils.build_message("赌注金额必须大于0!").finish(reply_to=True)

    if num.available:
        num_resp = num.result
    else:
        num_resp = await prompt(
            "请输入子弹数量（最大6，或输入'取消'来取消装弹）", timeout=60
        )
        num_resp = str(num_resp)

    if num_resp in {"取消", "算了"}:
        await MessageUtils.build_message("已取消装弹...").finish()
    if not num_resp.isdigit():
        await MessageUtils.build_message("输入的子弹数必须是数字！").finish(
            reply_to=True
        )
    num_resp = int(num_resp)
    if not (1 <= num_resp <= 6):
        await MessageUtils.build_message("子弹数量必须在1-6之间!").finish(reply_to=True)

    _at_user = at_user.result.target if at_user.available else None
    rus = Russian(
        at_user=_at_user,
        player1=(entity.user_id, uname),
        money=real_money,
        bullet_num=num_resp,
    )
    result = await russian_manager.add_russian(bot, entity.group_id, rus)
    await result.send()
    logger.info(
        f"添加俄罗斯轮盘 装弹: {num_resp}, 金额: {real_money}",
        arparma.header_result,
        session=session,
    )


@_accept_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    uname: str = UserName(),
):
    entity = get_entity_ids(session)

    if not entity.group_id:
        await MessageUtils.build_message("群组id不能为空...").finish()

    result = await russian_manager.accept(bot, entity.group_id, entity.user_id, uname)
    await result.send()
    logger.info(
        "俄罗斯轮盘接受对决",
        arparma.header_result,
        session=session,
    )


@_refuse_matcher.handle()
async def _(session: Uninfo, arparma: Arparma, uname: str = UserName()):
    entity = get_entity_ids(session)
    if not entity.group_id:
        await MessageUtils.build_message("群组id不能为空...").finish()
    result = russian_manager.refuse(entity.group_id, entity.user_id, uname)
    await result.send()
    logger.info("俄罗斯轮盘拒绝对决", arparma.header_result, session=session)


@_settlement_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    entity = get_entity_ids(session)
    if not entity.group_id:
        await MessageUtils.build_message("群组id为空...").finish()
    result = await russian_manager.settlement(
        entity.group_id, entity.user_id, PlatformUtils.get_platform(session)
    )
    await result.send()
    logger.info("俄罗斯轮盘结算", arparma.header_result, session=session)


@_shoot_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, uname: str = UserName()):
    entity = get_entity_ids(session)
    if not entity.group_id:
        await MessageUtils.build_message("群组id为空...").finish()
    result, settle = await russian_manager.shoot(
        bot, entity.group_id, entity.user_id, uname, PlatformUtils.get_platform(session)
    )
    await result.send()
    if settle:
        await settle.send()
    logger.info("俄罗斯轮盘开枪", arparma.header_result, session=session)


@_record_matcher.handle()
async def _(session: Uninfo, arparma: Arparma, uname: str = UserName()):
    entity = get_entity_ids(session)
    if not entity.user_id:
        await MessageUtils.build_message("用户id为空...").finish()
    if not entity.group_id:
        await MessageUtils.build_message("群组id为空...").finish()

    user, _ = await RussianUser.get_or_create(
        user_id=entity.user_id, group_id=entity.group_id
    )

    # 计算统计数据
    total_games = user.win_count + user.fail_count
    win_rate = (user.win_count / total_games * 100) if total_games > 0 else 0
    net_profit = user.make_money - user.lose_money

    # 获取用户头像和名称
    user_avatar = PlatformUtils.get_user_avatar_url(entity.user_id, "qq")

    # 使用HTML模板渲染
    template_path = Path(__file__).parent / "render" / "record.html"

    component = ui.template(
        template_path,
        data={
            "user": user,
            "user_id": entity.user_id,
            "user_name": uname,
            "user_avatar": user_avatar,
            "total_games": total_games,
            "win_rate": win_rate,
            "net_profit": net_profit,
        },
    )

    image_bytes = await ui.render(
        component, viewport={"width": 640, "height": 10}, wait=2
    )

    await MessageUtils.build_message(image_bytes).send(reply_to=True)
    logger.info("俄罗斯轮盘查看战绩", arparma.header_result, session=session)


@_rank_matcher.handle()
async def _(session: Uninfo, arparma: Arparma, rank_type: str, num: int):
    entity = get_entity_ids(session)
    gid = entity.group_id
    if not entity.user_id:
        await MessageUtils.build_message("用户id为空...").finish()
    if not gid:
        await MessageUtils.build_message("群组id为空...").finish()
    if num > 51 or num < 10:
        num = 10
    result = await russian_manager.rank(entity.user_id, gid, rank_type, num)
    if isinstance(result, str):
        await MessageUtils.build_message(result).finish(reply_to=True)
    result.show()
    await MessageUtils.build_message(result).send(reply_to=True)
    logger.info(
        f"查看轮盘排行: {rank_type} 数量: {num}", arparma.header_result, session=session
    )
