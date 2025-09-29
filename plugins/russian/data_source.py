import contextlib
from datetime import datetime, timedelta
from pathlib import Path
import random
import time

from apscheduler.jobstores.base import JobLookupError
from nonebot.adapters import Bot
from nonebot_plugin_alconna import At, UniMessage
from nonebot_plugin_apscheduler import scheduler

from zhenxun import ui
from zhenxun.configs.config import BotConfig, Config
from zhenxun.models.group_member_info import GroupInfoUser
from zhenxun.models.user_console import UserConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import GoldHandle
from zhenxun.utils.exception import InsufficientGold
from zhenxun.utils.image_utils import BuildImage, BuildMat, MatType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .config import (
    EXPIRE_TIME,
    PlayerDeathException,
    Russian,
    death_messages,
    live_messages,
)
from .equipment import get_weapon, get_weapons
from .models.russian_user import RussianUser

base_config = Config.get("russian")


class RussianManager:
    def __init__(self) -> None:
        self._data: dict[str, Russian] = {}

    def __check_is_timeout(self, group_id: str) -> bool:
        """检查决斗是否超时

        参数:
            group_id: 群组id

        返回:
            bool: 是否超时
        """
        if russian := self._data.get(group_id):
            if russian.time + EXPIRE_TIME < time.time():
                return True
        return False

    def __random_bullet(self, num: int) -> list[int]:
        """随机排列子弹

        参数:
            num: 子弹数量

        返回:
            list[int]: 子弹排列数组
        """
        bullet_list = [0, 0, 0, 0, 0, 0, 0]
        for i in random.sample([0, 1, 2, 3, 4, 5, 6], num):
            bullet_list[i] = 1
        return bullet_list

    def __remove_job(self, group_id: str):
        """移除定时任务

        参数:
            group_id: 群组id
        """
        with contextlib.suppress(JobLookupError):
            scheduler.remove_job(f"russian_job_{group_id}")

    def __build_job(
        self, bot: Bot, group_id: str, is_add: bool = False, platform: str | None = None
    ):
        """移除定时任务和构建新定时任务

        参数:
            bot: Bot
            group_id: 群组id
            is_add: 是否添加新定时任务.
            platform: 平台
        """
        self.__remove_job(group_id)
        if is_add and not PlatformUtils.is_qbot(bot):
            date = datetime.now() + timedelta(seconds=31)
            scheduler.add_job(
                self.__auto_end_game,
                "date",
                run_date=date.replace(microsecond=0),
                id=f"russian_job_{group_id}",
                args=[bot, group_id, platform],
            )

    async def __auto_end_game(self, bot: Bot, group_id: str, platform: str):
        """自动结束对决

        参数:
            bot: Bot
            group_id: 群组id
            platform: 平台
        """
        result = await self.settlement(group_id, None, platform)
        if result:
            await PlatformUtils.send_message(bot, None, group_id, result)

    async def add_russian(
        self,
        bot: Bot,
        group_id: str,
        rus: Russian,
    ) -> UniMessage:
        """添加决斗

        参数:
            bot: Bot
            group_id: 群组id
            rus: Russian

        返回:
            UniMessage: 返回消息
        """
        if russian := self._data.get(group_id):
            if russian.time + EXPIRE_TIME < time.time():
                if not russian.player2:
                    return MessageUtils.build_message(
                        f"现在是 {russian.player1[1]} 发起的对决,"
                        f" 请接受对决或等待决斗超时..."
                    )
                else:
                    return MessageUtils.build_message(
                        f"{russian.player1[1]} 和 {russian.player2[1]}的对决还未结束！"
                    )
            return MessageUtils.build_message(
                f"现在是 {russian.player1[1]} 发起的对决\n请等待比赛结束后再开始下一轮."
            )
        max_money = base_config.get("MAX_RUSSIAN_BET_GOLD")
        if rus.money > max_money:
            return MessageUtils.build_message(f"太多了！单次金额不能超过{max_money}！")
        user = await UserConsole.get_user(rus.player1[0])
        if user.gold < rus.money:
            return MessageUtils.build_message(
                "你没有足够的钱支撑起这场挑战，如果需要指定金额，"
                "可以输入 装弹 1(子弹数) 100(金额)"
            )
        rus.bullet_arr = self.__random_bullet(rus.bullet_num)

        # 设置玩家1的装备
        weapon_list = get_weapons()
        random_weapon = random.choice(list(weapon_list.keys()))

        self._data[group_id] = rus
        message_list: list[str | At] = []
        if rus.at_user:
            user = await GroupInfoUser.get_or_none(
                user_id=rus.at_user, group_id=group_id
            )
            message_list = [
                f"{rus.player1[1]} 向",
                At(flag="user", target=rus.at_user),
                f"发起了决斗！请 {user.user_name if user else rus.at_user}",
                f" 在{EXPIRE_TIME}秒内回复‘接受对决’ or ‘拒绝对决’，超时此次决斗作废！",
            ]
        else:
            message_list = [
                f"若{EXPIRE_TIME}秒内无人接受挑战则此次对决作废"
                "【首次游玩请at我发送 ’帮助俄罗斯轮盘‘ 来查看命令】"
            ]
        rus.weapon = random_weapon
        # rus.weapon = "gambler"
        weapon_config = get_weapon(random_weapon)

        result = (
            "咔 " * rus.bullet_num
            + f"装填完毕\n挑战金额：{rus.money}\n"
            + f"第一枪的概率为：{float(rus.bullet_num) / 7.0 * 100:.2f}%\n"
            + f"装备：{weapon_config.name}\n"
        )

        message_list.insert(0, result)
        self.__build_job(bot, group_id, True)
        return MessageUtils.build_message(message_list)  # type: ignore

    async def accept(
        self,
        bot: Bot,
        group_id: str,
        user_id: str,
        uname: str,
    ) -> UniMessage:
        """接受对决

        参数:
            bot: Bot
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称

        返回:
            Text | MessageFactory: 返回消息
        """
        if not (russian := self._data.get(group_id)):
            return MessageUtils.build_message(
                "目前没有进行的决斗，请发送 装弹 开启决斗吧！"
            )
        if russian.at_user and russian.at_user != user_id:
            return MessageUtils.build_message("又不是找你决斗，你接受什么啊！气！")
        if russian.player2:
            return MessageUtils.build_message(
                "当前决斗已被其他玩家接受！请等待下局对决！"
            )
        if russian.player1[0] == user_id:
            return MessageUtils.build_message("你发起的对决，你接受什么啊！气！")
        user = await UserConsole.get_user(user_id)
        if user.gold < russian.money:
            return MessageUtils.build_message("你没有足够的钱来接受这场挑战...")
        russian.player2 = (user_id, uname)
        russian.next_user = russian.player1[0]

        template_path = Path(__file__).parent / "render" / "start.html"

        player1_russian = await RussianUser.get_user(russian.player1[0], group_id)
        player2_russian = await RussianUser.get_user(russian.player2[0], group_id)

        if player1_russian.win_count + player1_russian.fail_count > 0:
            player1_win_rate = round(
                player1_russian.win_count
                / (player1_russian.win_count + player1_russian.fail_count)
                * 100,
                2,
            )
        else:
            player1_win_rate = 0
        if player2_russian.win_count + player2_russian.fail_count > 0:
            player2_win_rate = round(
                player2_russian.win_count
                / (player2_russian.win_count + player2_russian.fail_count)
                * 100,
                2,
            )
        else:
            player2_win_rate = 0
        weapon_config = get_weapon(russian.weapon)

        component = ui.template(
            template_path,
            data={
                "russian": russian,
                "player1_avatar": PlatformUtils.get_user_avatar_url(
                    russian.player1[0], "qq"
                ),
                "player2_avatar": PlatformUtils.get_user_avatar_url(
                    russian.player2[0], "qq"
                ),
                "player1_win_rate": player1_win_rate,
                "player1_wins": player1_russian.win_count,
                "player2_win_rate": player2_win_rate,
                "player2_wins": player2_russian.win_count,
                "weapon_name": weapon_config.name,
                "weapon_description": weapon_config.special_effect.name,
                "weapon_effect": weapon_config.special_effect.description,
            },
        )
        image_bytes = await ui.render(
            component, viewport={"width": 640, "height": 10}, wait=2
        )

        self.__build_job(bot, group_id, True)
        return MessageUtils.build_message(
            [
                "决斗已经开始！请",
                At(flag="user", target=russian.player1[0]),
                "先开枪！",
                image_bytes,
            ]
        )

    def refuse(self, group_id: str, user_id: str, uname: str) -> UniMessage:
        """拒绝决斗

        参数:
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称

        返回:
            Text | MessageFactory: 返回消息
        """
        if russian := self._data.get(group_id):
            if russian.at_user:
                if russian.at_user != user_id:
                    return MessageUtils.build_message(
                        "又不是找你决斗，你拒绝什么啊！气！"
                    )
                del self._data[group_id]
                self.__remove_job(group_id)
                return MessageUtils.build_message(
                    [
                        At(flag="user", target=russian.player1[0]),
                        f"{uname}拒绝了你的对决！",
                    ]
                )
            return MessageUtils.build_message("当前决斗并没有指定对手，无法拒绝哦！")
        return MessageUtils.build_message(
            "目前没有进行的决斗，请发送 装弹 开启决斗吧！"
        )

    async def shoot(
        self, bot: Bot, group_id: str, user_id: str, uname: str, platform: str
    ) -> tuple[UniMessage, UniMessage | None]:
        """开枪

        参数:
            bot: Bot
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称
            platform: 平台

        返回:
            Text | MessageFactory: 返回消息
        """
        if russian := self._data.get(group_id):
            if not russian.player2:
                return (
                    MessageUtils.build_message("当前还没有玩家接受对决，无法开枪..."),
                    None,
                )
            if user_id not in [russian.player1[0], russian.player2[0]]:
                """非玩家1和玩家2发送开枪"""
                rand_list = [
                    f"不要打扰 {russian.player1[1]} 和 {russian.player2[1]} 的决斗啊！",
                    f"给我好好做好一个观众！不然{BotConfig.self_nickname}就要生气了",
                    f"不要捣乱啊baka{uname}！",
                ]
                return (
                    MessageUtils.build_message(random.choice(rand_list)),
                    None,
                )
            if user_id != russian.next_user:
                """相同玩家连续开枪"""
                return (
                    MessageUtils.build_message(
                        f"左轮不是连发的！该 {russian.player2[1]} 开枪了!"
                    ),
                    None,
                )

            weapon_config = get_weapon(russian.weapon)

            is_dead = False
            result = ""
            try:
                if r := weapon_config.special_effect.effect_func(russian, user_id):
                    result = r + "\n"
            except PlayerDeathException as e:
                is_dead = True
                result = str(e.message)

            logger.debug(
                f"当前子弹排列: {russian.bullet_arr} | "
                f"当前子弹下标: {russian.bullet_index}",
                "russian",
            )

            if is_dead:
                result = random.choice(death_messages) + "\n" + result
                settle = await self.settlement(group_id, user_id, platform)
                return MessageUtils.build_message(result), settle
            else:
                p = (
                    (russian.bullet_index + russian.bullet_num + 1)
                    / len(russian.bullet_arr)
                    * 100
                )
                result += (
                    f"{random.choice(live_messages)}\n下一枪中弹的概率: {p:.2f}%, 轮到 "
                )
                next_user = (
                    russian.player2[0]
                    if russian.next_user == russian.player1[0]
                    else russian.player1[0]
                )
                russian.bullet_index += 1
                russian.next_user = next_user
                self.__build_job(bot, group_id, True)
                return (
                    MessageUtils.build_message(
                        [result, At(flag="user", target=next_user), " 了!"]
                    ),
                    None,
                )

        return (
            MessageUtils.build_message("目前没有进行的决斗，请发送 装弹 开启决斗吧！"),
            None,
        )

    async def settlement(
        self, group_id: str, user_id: str | None, platform: str | None = None
    ) -> UniMessage:
        """结算

        参数:
            group_id: 群组id
            user_id: 用户id
            platform: 平台

        返回:
            Text | MessageFactory: 返回消息
        """
        if not (russian := self._data.get(group_id)):
            return MessageUtils.build_message("比赛并没有开始...无法结算...")
        if not russian.player2:
            if self.__check_is_timeout(group_id):
                del self._data[group_id]
                return MessageUtils.build_message(
                    "规定时间内还未有人接受决斗，当前决斗过期..."
                )
            return MessageUtils.build_message("决斗还未开始,，无法结算哦...")
        if user_id and user_id not in [russian.player1[0], russian.player2[0]]:
            return MessageUtils.build_message("吃瓜群众不要捣乱！黄牌警告！")
        # if not self.__check_is_timeout(group_id):
        #     return MessageUtils.build_message(
        #         f"{russian.player1[1]} 和 {russian.player2[1]} 比赛并未超时，请继续比赛"
        #     )
        win_user = None
        lose_user = None
        if win_user:
            russian.next_user = (
                russian.player1[0]
                if win_user == russian.player2[0]
                else russian.player2[0]
            )
        if russian.next_user != russian.player1[0]:
            win_user = russian.player1
            lose_user = russian.player2
        else:
            win_user = russian.player2
            lose_user = russian.player1
        if win_user and lose_user:
            rand = 0
            if russian.money > 10:
                rand = random.randint(0, 5)
                fee = int(russian.money * float(rand) / 100)
                fee = 1 if fee < 1 and rand != 0 else fee
            else:
                fee = 0
            winner = await RussianUser.add_count(win_user[0], group_id, "win")
            loser = await RussianUser.add_count(lose_user[0], group_id, "lose")
            await RussianUser.money(win_user[0], group_id, "win", russian.money - fee)
            await RussianUser.money(lose_user[0], group_id, "lose", russian.money)
            await UserConsole.add_gold(
                win_user[0], russian.money - fee, "russian", platform
            )
            try:
                await UserConsole.reduce_gold(
                    lose_user[0],
                    russian.money,
                    GoldHandle.PLUGIN,
                    "russian",
                    platform,
                )
            except InsufficientGold:
                if u := await UserConsole.get_user(lose_user[0]):
                    u.gold = 0
                    await u.save(update_fields=["gold"])
            result = [
                "这场决斗是 ",
                At(flag="user", target=win_user[0]),
                " 胜利了!",
            ]

            weapon_config = get_weapon(russian.weapon)

            template_path = Path(__file__).parent / "render" / "end.html"

            component = ui.template(
                template_path,
                data={
                    "russian": russian,
                    "win_user": win_user,
                    "winner": winner,
                    "winner_avatar": PlatformUtils.get_user_avatar_url(
                        win_user[0], "qq"
                    ),
                    "lose_user": lose_user,
                    "loser": loser,
                    "loser_avatar": PlatformUtils.get_user_avatar_url(
                        lose_user[0], "qq"
                    ),
                    "weapon_config": weapon_config,
                    "fee": fee,
                    "rand": rand,
                    "bot_nickname": BotConfig.self_nickname,
                },
            )

            image_bytes = await ui.render(
                component, viewport={"width": 640, "height": 10}, wait=2
            )
            self.__remove_job(group_id)
            result.append(image_bytes)
            del self._data[group_id]
            return MessageUtils.build_message(result)
        return MessageUtils.build_message("赢家和输家获取错误...")

    async def __get_x_index(self, users: list[RussianUser], group_id: str):
        uid_list = [u.user_id for u in users]
        group_user_list = await GroupInfoUser.filter(
            user_id__in=uid_list, group_id=group_id
        ).all()
        group_user = {gu.user_id: gu.user_name for gu in group_user_list}
        data = []
        for uid in uid_list:
            if uid in group_user:
                data.append(group_user[uid])
            else:
                data.append(uid)
        return data

    async def rank(
        self, user_id: str, group_id: str, rank_type: str, num: int
    ) -> BuildImage | str:
        x_index = []
        data = []
        title = ""
        x_name = ""
        if rank_type == "a":
            users = (
                await RussianUser.filter(group_id=group_id, make_money__not=0)
                .order_by("make_money")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.make_money for u in users]
            title = "欧洲人排行"
            x_name = "金币"
        elif rank_type == "b":
            users = (
                await RussianUser.filter(group_id=group_id, lose_money__not=0)
                .order_by("lose_money")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.lose_money for u in users]
            title = "慈善家排行"
            x_name = "金币"
        elif rank_type == "lose":
            users = (
                await RussianUser.filter(group_id=group_id, fail_count__not=0)
                .order_by("fail_count")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.fail_count for u in users]
            title = "败场排行"
            x_name = "场次"
        elif rank_type == "max_lose":
            users = (
                await RussianUser.filter(group_id=group_id, max_losing_streak__not=0)
                .order_by("max_losing_streak")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.max_losing_streak for u in users]
            title = "最高连败排行"
            x_name = "场次"
        elif rank_type == "max_win":
            users = (
                await RussianUser.filter(group_id=group_id, max_winning_streak__not=0)
                .order_by("max_winning_streak")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.max_winning_streak for u in users]
            title = "最高连胜排行"
            x_name = "场次"
        elif rank_type == "win":
            users = (
                await RussianUser.filter(group_id=group_id, win_count__not=0)
                .order_by("win_count")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.win_count for u in users]
            title = "胜场排行"
            x_name = "场次"
        if not data:
            return "当前数据为空..."
        mat = BuildMat(MatType.BARH)
        mat.x_index = x_index
        mat.data = data  # type: ignore
        mat.title = title
        mat.x_name = x_name
        return await mat.build()


russian_manager = RussianManager()
