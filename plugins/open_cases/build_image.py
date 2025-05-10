from datetime import datetime, timedelta, timezone
import os
import random

from tortoise.functions import Count

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils._build_mat import BuildMat, MatType
from zhenxun.utils.image_utils import BuildImage
from zhenxun.utils.utils import cn2py

from .buff import CaseManager
from .config import CASE_BACKGROUND, COLOR2COLOR, COLOR2NAME
from .models.buff_skin import BuffSkin
from .models.buff_skin_log import BuffSkinLog

BASE_PATH = IMAGE_PATH / "csgo_cases"

ICON_PATH = IMAGE_PATH / "_icon"


async def draw_card(skin: BuffSkin, rand: str) -> BuildImage:
    """构造抽取图片

    参数:
        skin (BuffSkin): BuffSkin
        rand (str): 磨损

    返回:
        BuildImage: BuildImage
    """
    name = f"{skin.name}-{skin.skin_name}-{skin.abrasion}"
    file_path = BASE_PATH / cn2py(skin.case_name.split(",")[0]) / f"{cn2py(name)}.jpg"
    if not file_path.exists():
        logger.warning(f"皮肤图片: {name} 不存在", "开箱")
    skin_bk = BuildImage(
        460, 200, color=(25, 25, 25, 100), font_size=25, font="CJGaoDeGuo.otf"
    )
    if file_path.exists():
        skin_image = BuildImage(205, 153, background=file_path)
        await skin_bk.paste(skin_image, (10, 30))
    await skin_bk.line((220, 10, 220, 180))
    await skin_bk.text((10, 10), skin.name, (255, 255, 255))
    name_icon = BuildImage(20, 20, background=ICON_PATH / "name_white.png")
    await skin_bk.paste(name_icon, (240, 13))
    await skin_bk.text((265, 15), "名称:", (255, 255, 255), font_size=20)
    await skin_bk.text(
        (310, 15),
        f"{skin.skin_name + ('(St)' if skin.is_stattrak else '')}",
        (255, 255, 255),
    )
    tone_icon = BuildImage(20, 20, background=ICON_PATH / "tone_white.png")
    await skin_bk.paste(tone_icon, (240, 45))
    await skin_bk.text((265, 45), "品质:", (255, 255, 255), font_size=20)
    await skin_bk.text((310, 45), COLOR2NAME[skin.color][:2], COLOR2COLOR[skin.color])
    type_icon = BuildImage(20, 20, background=ICON_PATH / "type_white.png")
    await skin_bk.paste(type_icon, (240, 73))
    await skin_bk.text((265, 75), "类型:", (255, 255, 255), font_size=20)
    await skin_bk.text((310, 75), skin.weapon_type, (255, 255, 255))
    price_icon = BuildImage(20, 20, background=ICON_PATH / "price_white.png")
    await skin_bk.paste(price_icon, (240, 103))
    await skin_bk.text((265, 105), "价格:", (255, 255, 255), font_size=20)
    await skin_bk.text((310, 105), str(skin.sell_min_price), (0, 255, 98))
    abrasion_icon = BuildImage(20, 20, background=ICON_PATH / "abrasion_white.png")
    await skin_bk.paste(abrasion_icon, (240, 133))
    await skin_bk.text((265, 135), "磨损:", (255, 255, 255), font_size=20)
    await skin_bk.text((310, 135), skin.abrasion, (255, 255, 255))
    await skin_bk.text((228, 165), f"({rand})", (255, 255, 255))
    return skin_bk


async def generate_skin(skin: BuffSkin | str, update_count: int) -> BuildImage | None:
    """构造皮肤图片

    参数:
        skin (BuffSkin): BuffSkin

    返回:
        BuildImage | None: 图片
    """
    # if skin.color == "CASE":
    if isinstance(skin, str):
        case_bk = BuildImage(
            700, 200, color=(25, 25, 25, 100), font_size=25, font="CJGaoDeGuo.otf"
        )
        case_data = await BuffSkin.get_or_none(case_name=skin, color="CASE")
        if case_data:
            name = f"{case_data.name}-{case_data.skin_name}-{case_data.abrasion}"
            file_path = (
                BASE_PATH
                / cn2py(case_data.case_name.split(",")[0])
                / f"{cn2py(name)}.jpg"
            )
            if not file_path.exists():
                logger.warning(f"皮肤图片: {name} 不存在", "查看武器箱")
            else:
                skin_img = BuildImage(200, 200, background=file_path)
                await case_bk.paste(skin_img, (10, 10))
        await case_bk.line((250, 10, 250, 190))
        await case_bk.line((280, 160, 660, 160))
        name_icon = BuildImage(30, 30, background=ICON_PATH / "box_white.png")
        await case_bk.paste(name_icon, (260, 25))
        await case_bk.text((295, 30), "名称:", (255, 255, 255))
        await case_bk.text((345, 30), skin, (255, 0, 38), font_size=30)

        type_icon = BuildImage(30, 30, background=ICON_PATH / "type_white.png")
        await case_bk.paste(type_icon, (260, 70))
        await case_bk.text((295, 75), "类型:", (255, 255, 255))
        await case_bk.text((345, 75), "武器箱", (0, 157, 255), font_size=30)

        price_icon = BuildImage(30, 30, background=ICON_PATH / "price_white.png")
        await case_bk.paste(price_icon, (260, 114))
        await case_bk.text((295, 120), "单价:", (255, 255, 255))
        await case_bk.text(
            (340, 120),
            str(case_data.sell_reference_price) if case_data else "unknown",
            (0, 255, 98),
            font_size=30,
        )

        update_count_icon = BuildImage(
            40, 40, background=ICON_PATH / "reload_white.png"
        )
        await case_bk.paste(update_count_icon, (575, 10))
        await case_bk.text((625, 12), str(update_count), (255, 255, 255), font_size=45)

        num_icon = BuildImage(30, 30, background=ICON_PATH / "num_white.png")
        await case_bk.paste(num_icon, (455, 70))
        await case_bk.text((490, 75), "在售:", (255, 255, 255))
        await case_bk.text(
            (535, 75),
            str(case_data.sell_num) if case_data else "unknown",
            (144, 0, 255),
            font_size=30,
        )

        want_buy_icon = BuildImage(30, 30, background=ICON_PATH / "want_buy_white.png")
        await case_bk.paste(want_buy_icon, (455, 114))
        await case_bk.text((490, 120), "求购:", (255, 255, 255))
        await case_bk.text(
            (535, 120),
            str(case_data.buy_num) if case_data else "unknown",
            (144, 0, 255),
            font_size=30,
        )

        await case_bk.text(
            (275, 165),
            "更新日期: ",
            (255, 255, 255),
            font_size=22,
        )
        date = (
            str(
                case_data.update_time.replace(microsecond=0).astimezone(
                    timezone(timedelta(hours=8))
                )
            ).split("+")[0]
            if case_data
            else "unknown"
        )
        await case_bk.text(
            (350, 165),
            date,
            (255, 255, 255),
            font_size=30,
        )
        return case_bk
    else:
        name = f"{skin.name}-{skin.skin_name}-{skin.abrasion}"
        file_path = (
            BASE_PATH / cn2py(skin.case_name.split(",")[0]) / f"{cn2py(name)}.jpg"
        )
        if not file_path.exists():
            logger.warning(f"皮肤图片: {name} 不存在", "查看武器箱")
        skin_bk = BuildImage(
            235, 250, color=(25, 25, 25, 100), font_size=25, font="CJGaoDeGuo.otf"
        )
        if file_path.exists():
            skin_image = BuildImage(205, 153, background=file_path)
            await skin_bk.paste(skin_image, (10, 30))
        update_count_icon = BuildImage(
            35, 35, background=ICON_PATH / "reload_white.png"
        )
        await skin_bk.line((10, 180, 220, 180))
        await skin_bk.text((10, 10), skin.name, (255, 255, 255))
        await skin_bk.paste(update_count_icon, (140, 10))
        await skin_bk.text((175, 15), str(update_count), (255, 255, 255))
        await skin_bk.text((10, 185), f"{skin.skin_name}", (255, 255, 255), "width")
        await skin_bk.text((10, 218), "品质:", (255, 255, 255))
        await skin_bk.text((55, 218), COLOR2NAME[skin.color], COLOR2COLOR[skin.color])
        await skin_bk.text((100, 218), "类型:", (255, 255, 255))
        await skin_bk.text((145, 218), skin.weapon_type, (255, 255, 255))
        return skin_bk


def get_bk_image_size(
    total_size: int,
    base_size: tuple[int, int],
    img_size: tuple[int, int],
    extra_height: int = 0,
) -> tuple[int, int]:
    """获取所需背景大小且不改变图片长宽比

    参数:
        total_size: 总面积
        base_size: 初始背景大小
        img_size: 贴图大小

    返回:
        tuple[int, int]: 满足所有贴图大小
    """
    bk_w, bk_h = base_size
    img_w, _ = img_size
    is_add_title_size = False
    left_dis = 0
    right_dis = 0
    old_size = (0, 0)
    new_size = (0, 0)
    ratio = 1.1
    while 1:
        w_ = int(ratio * bk_w)
        h_ = int(ratio * bk_h)
        size = w_ * h_
        if size < total_size:
            left_dis = size
        else:
            right_dis = size
        r = w_ / (img_w + 25)
        if right_dis and r - int(r) < 0.1:
            if not is_add_title_size and extra_height:
                total_size = int(total_size + w_ * extra_height)
                is_add_title_size = True
                right_dis = 0
                continue
            if total_size - left_dis > right_dis - total_size:
                new_size = (w_, h_)
            else:
                new_size = old_size
            break
        old_size = (w_, h_)
        ratio += 0.1
    return new_size


async def build_case_image(case_name: str | None) -> BuildImage | str:
    """构造武器箱图片

    参数:
        case_name (str): 名称

    返回:
        BuildImage | str: 图片
    """
    background = random.choice(os.listdir(CASE_BACKGROUND))
    background_img = BuildImage(0, 0, background=CASE_BACKGROUND / background)
    if case_name:
        log_list = (
            await BuffSkinLog.filter(case_name__contains=case_name)
            .annotate(count=Count("id"))
            .group_by("skin_name")
            .values_list("skin_name", "count")
        )
        skin_list_ = await BuffSkin.filter(case_name__contains=case_name).all()
        skin2count = {item[0]: item[1] for item in log_list}
        case = None
        skin_list: list[BuffSkin] = []
        exists_name = []
        for skin in skin_list_:
            if skin.color == "CASE":
                case = skin
            else:
                name = skin.name + skin.skin_name
                if name not in exists_name:
                    skin_list.append(skin)
                    exists_name.append(name)
        generate_img = {}
        for skin in skin_list:
            skin_img = await generate_skin(skin, skin2count.get(skin.skin_name, 0))
            if skin_img:
                if not generate_img.get(skin.color):
                    generate_img[skin.color] = []
                generate_img[skin.color].append(skin_img)
        skin_image_list = []
        for color in COLOR2NAME:
            if generate_img.get(color):
                skin_image_list = skin_image_list + generate_img[color]
        img = skin_image_list[0]
        img_w, img_h = img.size
        total_size = (img_w + 25) * (img_h + 10) * len(skin_image_list)  # 总面积
        new_size = get_bk_image_size(total_size, background_img.size, img.size, 250)
        A = BuildImage(
            new_size[0] + 50, new_size[1], background=CASE_BACKGROUND / background
        )
        await A.filter("GaussianBlur", 2)
        if case:
            case_img = await generate_skin(
                case, skin2count.get(f"{case_name}武器箱", 0)
            )
            if case_img:
                await A.paste(case_img, (25, 25))
        w = 25
        h = 230
        skin_image_list.reverse()
        for image in skin_image_list:
            await A.paste(image, (w, h))
            w += image.width + 20
            if w + image.width - 25 > A.width:
                h += image.height + 10
                w = 25
    else:
        # log_list = (
        #     await BuffSkinLog.filter(color="CASE")
        #     .annotate(count=Count("id"))
        #     .group_by("case_name")
        #     .values_list("case_name", "count")
        # )
        # name2count = {item: 0 for item in CaseManager.CURRENT_CASES}
        # skin_list = await BuffSkin.filter(color="CASE").all()
        skin_name_list: list[str] = CaseManager.CURRENT_CASES  # type: ignore
        image_list: list[BuildImage] = []
        for skin in skin_name_list:
            if img := await generate_skin(skin, 1):
                image_list.append(img)
        if not image_list:
            return "未收录武器箱"
        w = 25
        h = 150
        img = image_list[0]
        img_w, img_h = img.size
        total_size = (img_w + 25) * (img_h + 10) * len(image_list)  # 总面积

        new_size = get_bk_image_size(total_size, background_img.size, img.size, 155)
        A = BuildImage(
            new_size[0] + 50, new_size[1], background=CASE_BACKGROUND / background
        )
        await A.filter("GaussianBlur", 2)
        bk_img = BuildImage(
            img_w, 120, color=(25, 25, 25, 100), font_size=60, font="CJGaoDeGuo.otf"
        )
        await bk_img.text(
            (0, 0),
            f"已收录 {len(image_list)} 个武器箱",
            (255, 255, 255),
            center_type="center",
        )
        await A.paste(bk_img, (10, 10), "width")
        for image in image_list:
            await A.paste(image, (w, h))
            w += image.width + 20
            if w + image.width - 25 > A.width:
                h += image.height + 10
                w = 25

    if h + img_h + 100 < A.height:
        await A.crop((0, 0, A.width, h + img_h + 100))
    await A.resize(0.5)
    return A


async def build_skin_trends(
    name: str, skin: str, abrasion: str, day: int = 7
) -> BuildImage | None:
    date = datetime.now() - timedelta(days=day)
    log_list = (
        await BuffSkinLog.filter(
            name__contains=name.upper(),
            skin_name=skin,
            abrasion__contains=abrasion,
            create_time__gt=date,
            is_stattrak=False,
        )
        .order_by("create_time")
        .limit(day * 5)
        .all()
    )
    if not log_list:
        return None
    date_list = []
    price_list = []
    for log in log_list:
        date = str(log.create_time.date())
        if date not in date_list:
            date_list.append(date)
            price_list.append(log.sell_min_price)
    graph = BuildMat(MatType.LINE)
    graph.data = price_list
    graph.title = f"{name}({skin})价格趋势({day})"
    graph.x_index = date_list
    return await graph.build()
