import asyncio
from datetime import datetime
import re
from nonebot_plugin_alconna import UniMessage
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.models.sign_user import SignUser
from zhenxun.utils._image_template import ImageTemplate
from zhenxun.utils.utils import cn2py
from .models.open_cases_log import OpenCasesLog
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from nonebot_plugin_session import EventSession
from zhenxun.utils.message import MessageUtils
from .models.open_cases_user import OpenCasesUser
from .models.buff_skin import BuffSkin
from zhenxun.configs.config import Config
from .build_image import draw_card
from .utils import random_skin
from .buff import BuffUpdateManager, CaseManager
from tortoise.functions import Sum
from .config import CASE2ID, COLOR2CN
import random


base_config = Config.get("open_cases")


def add_count(user: OpenCasesUser, skin: BuffSkin, case_price: float):
    """数据添加

    参数:
        user: OpenCasesUser
        skin: BuffSkin
        case_price: 武器箱价格
    """
    if skin.color == "BLUE":
        if skin.is_stattrak:
            user.blue_st_count += 1
        else:
            user.blue_count += 1
    elif skin.color == "PURPLE":
        if skin.is_stattrak:
            user.purple_st_count += 1
        else:
            user.purple_count += 1
    elif skin.color == "PINK":
        if skin.is_stattrak:
            user.pink_st_count += 1
        else:
            user.pink_count += 1
    elif skin.color == "RED":
        if skin.is_stattrak:
            user.red_st_count += 1
        else:
            user.red_count += 1
    elif skin.color == "KNIFE":
        if skin.is_stattrak:
            user.knife_st_count += 1
        else:
            user.knife_count += 1
    user.make_money += skin.sell_min_price
    user.spend_money += int(17 + case_price)


class OpenCaseManager:
    @classmethod
    async def get_group_data(cls, group_id: str):
        data = (
            await OpenCasesUser.filter(group_id=group_id)
            .annotate(
                at=Sum("total_count"),
                ato=Sum("today_open_total"),
                ab=Sum("blue_count"),
                abst=Sum("blue_st_count"),
                ap=Sum("purple_count"),
                apst=Sum("purple_st_count"),
                apk=Sum("pink_count"),
                apkst=Sum("pink_st_count"),
                ar=Sum("red_count"),
                arst=Sum("red_st_count"),
                ak=Sum("knife_count"),
                akst=Sum("knife_st_count"),
                am=Sum("make_money"),
                asp=Sum("spend_money"),
            )
            .values(
                "at",
                "ato",
                "ab",
                "abst",
                "ap",
                "apst",
                "apk",
                "apkst",
                "ar",
                "arst",
                "ak",
                "akst",
                "am",
                "asp",
            )
        )
        data = data[0]
        data_list = [
            ["开箱总数", data["at"]],
            ["今日开箱", data["ato"]],
            ["蓝色军规", data["ab"]],
            ["蓝色暗金", data["abst"]],
            ["紫色受限", data["ap"]],
            ["紫色暗金", data["apst"]],
            ["粉色保密", data["apk"]],
            ["粉色暗金", data["apkst"]],
            ["红色隐秘", data["ar"]],
            ["红色暗金", data["arst"]],
            ["金色罕见", data["ak"]],
            ["金色暗金", data["akst"]],
            ["花费金额", f'{data["am"]:.2f}'],
            ["获取金额", f'{data["asp"]:.2f}'],
        ]
        return await ImageTemplate.table_page(
            "群组开箱统计", None, ["名称", "数量"], data_list
        )

    @classmethod
    async def get_user_data(cls, uname: str, user_id: str, group_id: str) -> BuildImage:
        user, _ = await OpenCasesUser.get_or_create(user_id=user_id, group_id=group_id)
        data_list = [
            ["开箱总数", user.total_count],
            ["今日开箱", user.today_open_total],
            ["蓝色军规", user.blue_count],
            ["蓝色暗金", user.blue_st_count],
            ["紫色受限", user.purple_count],
            ["紫色暗金", user.purple_st_count],
            ["粉色保密", user.pink_count],
            ["粉色暗金", user.pink_st_count],
            ["红色隐秘", user.red_count],
            ["红色暗金", user.red_st_count],
            ["金色罕见", user.knife_count],
            ["金色暗金", user.knife_st_count],
            ["花费金额", f"{user.spend_money:.2f}"],
            ["获取金额", f"{user.make_money:.2f}"],
            ["最后开箱日期", user.open_cases_time_last.date()],
        ]
        return await ImageTemplate.table_page(
            f"{uname}开箱统计", None, ["名称", "数量"], data_list
        )

    @classmethod
    async def __open_check(
        cls, case_name: str | None, user_id: str, group_id: str
    ) -> tuple[OpenCasesUser | UniMessage, str, int]:
        """开箱前检查

        参数:
            case_name: 箱子名称
            user_id: 用户给id
            group_id: 群组id

        返回:
            tuple[OpenCasesUser | UniMessage, str, int]: 开箱用户或返回消息和箱子名称和最大开箱数
        """
        if not CaseManager.CURRENT_CASES:
            return MessageUtils.build_message("未收录任何武器箱"), "", 0
        if not case_name:
            case_name = random.choice(CaseManager.CURRENT_CASES)  # type: ignore
        if case_name and case_name not in CaseManager.CURRENT_CASES:
            return (
                "武器箱未收录, 当前可用武器箱:\n"
                + ", ".join(CaseManager.CURRENT_CASES),  # type: ignore
                "",
                0,
            )
        user, _ = await OpenCasesUser.get_or_create(
            user_id=user_id,
            group_id=group_id,
            defaults={"open_cases_time_last": datetime.now()},
        )
        max_count = await cls.get_user_max_count(user_id)
        # 一天次数上限
        if user.today_open_total >= max_count:
            return (
                MessageUtils.build_message(
                    "今天已达开箱上限了喔，明天再来吧\n(提升好感度可以增加每日开箱数 #疯狂暗示)"
                ),
                "",
                0,
            )
        return user, case_name or "", max_count

    @classmethod
    def __get_log(
        cls, skin: BuffSkin, rand: float, user_id: str, group_id: str, case_name: str
    ) -> OpenCasesLog:
        """构造日志

        参数:
            skin: BuffSkin
            rand: 随机磨损
            user_id: 用户id
            group_id: 群组id
            case_name: 箱子名称

        返回:
            OpenCasesLog: Log
        """
        return OpenCasesLog(
            user_id=user_id,
            group_id=group_id,
            case_name=case_name,
            name=skin.name,
            skin_name=skin.skin_name,
            is_stattrak=skin.is_stattrak,
            abrasion=skin.abrasion,
            color=skin.color,
            price=skin.sell_min_price,
            abrasion_value=rand,
            create_time=datetime.now(),
        )

    @classmethod
    async def __to_image(
        cls, img_w: int, img_h: int, img_list: list[BuildImage]
    ) -> BuildImage:
        """构造图片

        参数:
            img_w: 宽
            img_h: 高
            num: 图片

        返回:
            BuildImage: 图片
        """
        num = len(img_list)
        img_w += 10
        img_h += 10
        w = img_w * 5
        if num < 5:
            h = img_h - 10
            w = img_w * num
        elif not num % 5:
            h = img_h * (num // 5)
        else:
            h = img_h * (num // 5) + img_h
        mark_image = BuildImage(w - 10, h - 10, color=(255, 255, 255))
        mark_image = await mark_image.auto_paste(img_list, 5, padding=20)  # type: ignore
        return mark_image

    @classmethod
    async def __start_open_one(
        cls,
        case_name: str,
        user: OpenCasesUser,
        num: int,
        max_count: int,
        session: EventSession,
    ) -> UniMessage:
        """开一箱

        参数:
            case_name: 箱子名称
            user: 开箱用户
            num: 开箱数量
            max_count: 最大开箱数
            session: EventSession

        返回:
            UniMessage: 返回消息
        """
        skin_list = await random_skin(case_name, num)
        if not skin_list:
            return MessageUtils.build_message("未抽取到任何皮肤...")
        case_price = 10
        log_list = []
        skin_count = {}
        img_list = []
        total_price = 0
        img_w, img_h = 0, 0
        for skin, rand in skin_list:
            img = await draw_card(skin, str(rand)[:11])
            img_w, img_h = img.size
            total_price += skin.sell_min_price
            color_name = COLOR2CN[skin.color]
            if not skin_count.get(color_name):
                skin_count[color_name] = 0
            skin_count[color_name] += 1
            add_count(user, skin, case_price)
            log_list.append(
                cls.__get_log(skin, rand, user.user_id, user.group_id, case_name)
            )
            img_list.append(img)
            logger.info(
                f"开启{case_name}武器箱获得"
                f" {skin.name}{'（StatTrak™）' if skin.is_stattrak else ''}"
                f" | {skin.skin_name} ({skin.abrasion}) "
                f"磨损: [{rand:.11f}] 价格: {skin.sell_min_price}",
                "开箱",
                session=session,
            )
        await user.save()
        mark_image = await cls.__to_image(img_w, img_h, img_list)
        over_count = max_count - user.today_open_total
        result = "".join(
            f"[{color_name}:{value}] " for color_name, value in skin_count.items()
        )
        return MessageUtils.build_message(
            [
                f"开启{case_name}武器箱\n剩余开箱次数：{over_count}\n",
                mark_image,
                f"\n{result[:-1]}\n箱子单价：{case_price}\n"
                f"总获取金额：{total_price:.2f}\n总花费：{(17 + case_price) * num:.2f}",
            ]
        )

    @classmethod
    async def open_case(
        cls,
        user_id: str,
        group_id: str,
        case_name: str | None,
        num: int,
        session: EventSession,
    ) -> UniMessage:
        user, case_name, max_count = await cls.__open_check(
            case_name, user_id, group_id
        )
        if not isinstance(user, OpenCasesUser):
            return user
        logger.debug(f"尝试开启武器箱: {case_name}", "开箱", session=session)
        return await cls.__start_open_one(case_name, user, num, max_count, session)

    @classmethod
    async def get_user_max_count(cls, user_id: str) -> int:
        """获取用户最大开箱次数

        参数:
            user_id: 用户id

        返回:
            int: 用户最大开箱次数
        """
        user, _ = await SignUser.get_or_create(user_id=user_id)
        impression = int(user.impression)
        initial_open_case_count = base_config.get("INITIAL_OPEN_CASE_COUNT")
        each_impression_add_count = base_config.get("EACH_IMPRESSION_ADD_COUNT")
        return int(initial_open_case_count + impression / each_impression_add_count)  # type: ignore

    @classmethod
    async def get_my_knifes(cls, user_id: str, group_id: str) -> UniMessage:
        """获取我的金色

        参数:
            user_id: 用户id
            group_id: 群号

        返回:
            UniMessage: 回复消息或图片
        """
        data_list = await cls.get_old_knife(user_id, group_id)
        data_list += await OpenCasesLog.filter(
            user_id=user_id, group_id=group_id, color="KNIFE"
        ).all()
        if not data_list:
            return MessageUtils.build_message("您木有开出金色级别的皮肤喔...")
        length = len(data_list)
        if length < 5:
            h = 600
            w = length * 540
        elif length % 5 == 0:
            h = 600 * (length // 5)
            w = 540 * 5
        else:
            h = 600 * (length // 5) + 600
            w = 540 * 5
        A = BuildImage(w, h)
        image_list = []
        for skin in data_list:
            name = f"{skin.name}-{skin.skin_name}-{skin.abrasion}"
            img_path = (
                IMAGE_PATH / "csgo_cases" / cn2py(skin.case_name) / f"{cn2py(name)}.jpg"
            )
            knife_img = BuildImage(470, 600, font_size=20)
            await knife_img.paste(
                BuildImage(
                    470, 470, background=img_path if img_path.exists() else None
                ),
                (0, 0),
            )
            await knife_img.text(
                (5, 500), f"\t{skin.name}|{skin.skin_name}({skin.abrasion})"
            )
            await knife_img.text((5, 530), f"\t磨损：{skin.abrasion_value}")
            await knife_img.text((5, 560), f"\t价格：{skin.price}")
            image_list.append(knife_img)
        A = await A.auto_paste(image_list, 5)
        return MessageUtils.build_message(A)

    @classmethod
    async def get_old_knife(cls, user_id: str, group_id: str) -> list[OpenCasesLog]:
        """获取旧数据字段

        参数:
            user_id (str): 用户id
            group_id (str): 群号

        返回:
            list[OpenCasesLog]: 旧数据兼容
        """
        user, _ = await OpenCasesUser.get_or_create(user_id=user_id, group_id=group_id)
        data_list = []
        if knifes_name := user.knifes_name:
            knifes_list = knifes_name[:-1].split(",")
            for knife in knifes_list:
                try:
                    if r := re.search(
                        r"(.*)\|\|(.*) \| (.*)\((.*)\) 磨损：(.*)， 价格：(.*)", knife
                    ):
                        case_name_py = r[1]
                        name = r[2]
                        skin_name = r[3]
                        abrasion = r[4]
                        abrasion_value = r[5]
                        price = r[6]
                        name = name.replace("（StatTrak™）", "")
                        data_list.append(
                            OpenCasesLog(
                                user_id=user_id,
                                group_id=group_id,
                                name=name.strip(),
                                case_name=case_name_py.strip(),
                                skin_name=skin_name.strip(),
                                abrasion=abrasion.strip(),
                                abrasion_value=abrasion_value,
                                price=price,
                            )
                        )
                except Exception as e:
                    logger.error(
                        f"获取兼容旧数据错误: {knife}",
                        "我的金色",
                        session=user_id,
                        group_id=group_id,
                        e=e,
                    )
        return data_list


async def reset_count_daily(group_id: str | None = None):
    """
    重置每日开箱
    """
    try:
        if group_id:
            await OpenCasesUser.filter(group_id=group_id).update(today_open_total=0)
        else:
            await OpenCasesUser.all().update(today_open_total=0)
    except Exception as e:
        logger.error("开箱重置错误", e=e)


async def auto_update():
    """自动更新武器箱"""
    if case_list := base_config.get("DAILY_UPDATE"):
        logger.debug("尝试自动更新武器箱", "更新武器箱")
        if "ALL" in case_list:
            case_list = CASE2ID.keys()
        logger.debug(f"预计自动更新武器箱 {len(case_list)} 个", "更新武器箱")
        for case_name in case_list:
            logger.debug(f"开始自动更新武器箱: {case_name}", "更新武器箱")
            try:
                await BuffUpdateManager.update_skin(case_name)
                rand = random.randint(300, 500)
                logger.info(
                    f"成功自动更新武器箱: {case_name},"
                    f" 将在 {rand} 秒后再次更新下一武器箱",
                    "更新武器箱",
                )
                await asyncio.sleep(rand)
            except Exception as e:
                logger.error(f"自动更新武器箱: {case_name}", e=e)
