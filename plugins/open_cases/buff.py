import asyncio
import random
import re
import time
from datetime import datetime

from httpx import Response
from retrying import retry
from zhenxun.configs.config import Config
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.utils import cn2py

from .config import (
    BASE_PATH,
    BUFF_SELL_URL,
    BUFF_URL,
    CASE2ID,
    KNIFE2ID,
    NAME2COLOR,
    BuffItem,
    BuffResponse,
    UpdateType,
)
from .exception import CallApiError, NotLoginRequired
from .models.buff_skin import BuffSkin
from .models.buff_skin_log import BuffSkinLog

base_config = Config.get("open_cases")


class CaseManager:
    CURRENT_CASES = []  # noqa: RUF012

    @classmethod
    async def reload(cls):
        cls.CURRENT_CASES = await BuffSkin.filter(color="CASE").values_list(
            "case_name", flat=True
        ) or list(
            set(
                await BuffSkin.filter(case_name__not="未知武器箱")
                .annotate()
                .group_by("case_name")
                .values_list("case_name", flat=True)
            )
        )
        logger.debug(f"加载武器箱: {cls.CURRENT_CASES}")


class BuffUpdateManager:
    @classmethod
    async def update_skin(cls, name: str) -> str:
        """更新皮肤或武器箱

        参数:
            name: 皮肤或武器箱名称

        返回:
            str: 返回消息
        """
        if name in CASE2ID:
            update_type = UpdateType.CASE
        elif name in KNIFE2ID:
            update_type = UpdateType.WEAPON_TYPE
        else:
            return "未在指定武器箱或指定武器类型内"
        buff_response = await cls.search_skin(name, 1, update_type)
        skin_list = cls.__item2skin(name, buff_response.items, update_type)
        for page in range(2, buff_response.total_page + 1):
            rand_time = random.randint(20, 50)
            logger.debug(f"访问随机等待时间: {rand_time}", "开箱更新")
            await asyncio.sleep(rand_time)
            buff_response = await cls.search_skin(name, page, update_type)
            skin_list += cls.__item2skin(name, buff_response.items, update_type)
        return await cls.__skin_to_db(name, skin_list, update_type)

    @classmethod
    async def __skin_to_db(
        cls, name: str, skin_list: list[BuffSkin], update_type: UpdateType
    ):  # sourcery skip: low-code-quality
        """将BuffSkin列表存入数据库

        参数:
            skin_list: BuffSkin列表
        """
        create_list, update_list = [], []
        log_list = []
        weapon2case = {}
        if update_type == UpdateType.WEAPON_TYPE:
            db_data = await BuffSkin.filter(name__contains=name).values(
                "name", "skin_name", "case_name"
            )
            weapon2case = {
                item["name"] + item["skin_name"]: item["case_name"]
                for item in db_data
                if item["case_name"] != "未知武器箱"
            }
        db_skin_ids = await BuffSkin.annotate().values_list("skin_id", flat=True)
        unique_items = {item.skin_id: item for item in skin_list}.values()
        for skin in list(unique_items):
            case_name = None
            if update_type == UpdateType.CASE:
                case_name = name.replace("武器箱", "").replace(" ", "").strip()
            if skin.case_name:
                skin.case_name = (
                    skin.case_name.replace("”", "")
                    .replace("“", "")
                    .replace("武器箱", "")
                    .replace(" ", "")
                )
            key = skin.name + skin.skin_name
            # name = skin.name + skin.skin_name + skin.abrasion
            if update_type == UpdateType.WEAPON_TYPE and not skin.case_name:
                case_name = weapon2case.get(key)
                if not case_name:
                    case_name = ",".join(await cls.__call_case_name(skin.skin_id))
                    weapon2case[key] = case_name
                    rand = random.randint(10, 20)
                    logger.debug(
                        f"获取 {skin.name} | {skin.skin_name}"
                        f" 皮肤所属武器箱: {case_name}, 访问随机等待时间: {rand}",
                        "开箱更新",
                    )
                    await asyncio.sleep(rand)
            if not case_name:
                case_name = "未知武器箱"
            if skin.case_name == "反恐精英20周年":
                skin.case_name = "CS20"
            log_list.append(cls.__add_log(skin))
            await cls.download_image(skin)
            if skin.skin_id not in db_skin_ids:
                create_list.append(skin)
            else:
                update_list.append(skin)
        if create_list:
            logger.debug(
                f"更新武器箱/皮肤: [<u><e>{name}</e></u>],"
                f" 创建 {len(create_list)} 个皮肤!"
            )
            await BuffSkin.bulk_create(set(create_list), 10)
        if update_list:
            update_list = await cls.__handle_update(name, update_list)
            logger.debug(
                f"更新武器箱/皮肤: [<u><c>{name}</c></u>],"
                f" 更新 {len(create_list)} 个皮肤!"
            )
            await BuffSkin.bulk_update(
                update_list,
                [
                    "steam_price",
                    "buy_max_price",
                    "buy_num",
                    "sell_min_price",
                    "sell_num",
                    "sell_reference_price",
                    "update_time",
                ],
                10,
            )
        if log_list:
            logger.debug(
                f"更新武器箱/皮肤: [<u><e>{name}</e></u>],"
                f" 新增 {len(log_list)} 条皮肤日志!"
            )
            await BuffSkinLog.bulk_create(log_list)
        if name not in CaseManager.CURRENT_CASES:
            CaseManager.CURRENT_CASES.append(name)  # type: ignore
        return f"""更新武器箱/皮肤: [{name}] 成功, 共更新 {len(update_list)} 个皮肤,
    新创建 {len(create_list)} 个皮肤!"""

    @classmethod
    async def __handle_update(
        cls, name: str, update_list: list[BuffSkin]
    ) -> list[BuffSkin]:
        """处理更新

        参数:
            update_list: BuffSkin列表
        """
        abrasion_list = []
        name_list = []
        skin_name_list = []
        for skin in update_list:
            if skin.abrasion not in abrasion_list:
                abrasion_list.append(skin.abrasion)
            if skin.name not in name_list:
                name_list.append(skin.name)
            if skin.skin_name not in skin_name_list:
                skin_name_list.append(skin.skin_name)
        db_data = await BuffSkin.filter(
            case_name__contains=name,
            skin_name__in=skin_name_list,
            name__in=name_list,
            abrasion__in=abrasion_list,
        ).all()
        _update_list = []
        for data in db_data:
            for skin in update_list:
                if (
                    data.name == skin.name
                    and data.skin_name == skin.skin_name
                    and data.abrasion == skin.abrasion
                ):
                    data.steam_price = skin.steam_price
                    data.buy_max_price = skin.buy_max_price
                    data.buy_num = skin.buy_num
                    data.sell_min_price = skin.sell_min_price
                    data.sell_num = skin.sell_num
                    data.sell_reference_price = skin.sell_reference_price
                    data.update_time = skin.update_time
                    _update_list.append(data)
        return _update_list

    @classmethod
    async def download_image(cls, skin: BuffSkin):
        """下载皮肤图片

        参数:
            skin: BuffSkin
        """
        file_name = f"{skin.name}-{skin.skin_name}-{skin.abrasion}"
        for case_name in skin.case_name.split(","):
            file_path = BASE_PATH / cn2py(case_name) / f"{cn2py(file_name)}.jpg"
            if not file_path.exists():
                logger.debug(
                    f"下载皮肤 {f'{skin.name}-{skin.skin_name}'}"
                    f" 图片: {skin.img_url}...",
                    "开箱更新",
                )
                await AsyncHttpx.download_file(skin.img_url, file_path)
                rand_time = random.randint(1, 10)
                # await asyncio.sleep(rand_time)
                await asyncio.sleep(1)
                logger.debug(f"图片下载随机等待时间: {rand_time}", "开箱更新")
            else:
                logger.debug(
                    f"皮肤 {f'{skin.name}-{skin.skin_name}'} 图片已存在...", "开箱更新"
                )

    @classmethod
    def __add_log(cls, skin: BuffSkin) -> BuffSkinLog:
        """添加日志

        参数:
            skin: BuffSkin

        返回:
            BuffSkinLog: BuffSkinLog
        """
        return BuffSkinLog(
            name=skin.name,
            case_name=skin.case_name,
            skin_name=skin.skin_name,
            is_stattrak=skin.is_stattrak,
            abrasion=skin.abrasion,
            color=skin.color,
            steam_price=skin.steam_price,
            weapon_type=skin.weapon_type,
            buy_max_price=skin.buy_max_price,
            buy_num=skin.buy_num,
            sell_min_price=skin.sell_min_price,
            sell_num=skin.sell_num,
            sell_reference_price=skin.sell_reference_price,
            create_time=datetime.now(),
        )

    @classmethod
    async def __get_case_name(cls, t: str):
        if not t.isdigit():
            return (
                t.replace("”", "")
                .replace("“", "")
                .replace("武器箱", "")
                .replace(" ", "")
            )
        else:
            return await cls.__call_case_name(t)

    @classmethod
    def __item2skin(
        cls, name: str, items: list[BuffItem], update_type: UpdateType
    ) -> list[BuffSkin]:
        """将BuffItem转为BuffSkin

        参数:
            name: 更新名称
            items: BuffItem列表
            update_type: 更新类型

        返回:
            list[BuffSkin]: BuffSkin列表
        """
        data_list = []
        for item in items:
            logger.debug(
                f"武器箱: [<u><e>{name}</e></u>] 正在收录皮肤:"
                f" [<u><c>{item.name}</c></u>]...",
                "开箱更新",
            )
            weapon_name = (
                item.name.split("|")[0]
                .replace("（★ StatTrak™）", "")
                .replace("（StatTrak™）", "")
                .replace("（★）", "")
                .strip()
            )
            case_name = None
            if update_type == UpdateType.CASE:
                case_name = name
            skin_name = item.short_name.split("|")[-1].strip()
            abrasion = "CASE"
            is_stattrak = False
            tags = item.goods_info.tags
            skin_color = NAME2COLOR[tags["rarity"].localized_name]
            weapon_type = tags["type"].localized_name
            if weapon_type in ["音乐盒", "印花", "探员"]:
                continue
            elif weapon_type in ["手套", "匕首"]:
                skin_color = "KNIFE"
            elif weapon_type in ["武器箱"]:
                skin_color = "CASE"
                skin_name = item.short_name
            if weapon_type not in ["武器箱"]:
                abrasion = tags["exterior"].localized_name
                is_stattrak = "StatTrak" in tags["quality"].localized_name
            data_list.append(
                BuffSkin(
                    case_name=case_name,
                    skin_name=skin_name,
                    skin_id=item.id,
                    name=weapon_name,
                    buy_max_price=item.buy_max_price,
                    buy_num=item.buy_num,
                    abrasion=abrasion,
                    color=skin_color,
                    is_stattrak=is_stattrak,
                    weapon_type=weapon_type,
                    img_url=item.goods_info.original_icon_url,
                    steam_price=item.goods_info.steam_price,
                    sell_min_price=item.sell_min_price,
                    sell_num=item.sell_num,
                    sell_reference_price=item.sell_reference_price,
                    create_time=datetime.now(),
                    update_time=datetime.now(),
                )
            )
        return data_list

    @classmethod
    @retry(stop_max_attempt_number=3)
    async def __call_buff_api(cls, params: dict) -> Response | None:
        """调用buff api

        参数:
            params: 参数

        返回:
            Response | None: 返回响应
        """
        cookie = {"session": base_config.get("COOKIE")}
        proxy = None
        if ip := base_config.get("BUFF_PROXY"):
            proxy = {"http://": ip, "https://": ip}
        try:
            response = await AsyncHttpx.get(
                BUFF_URL,
                proxy=proxy,
                params=params,
                cookies=cookie,  # type: ignore
            )
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error("尝试访问武器箱/皮肤第发生错误...", "开箱更新", e=e)
        return None

    @classmethod
    @retry(stop_max_attempt_number=3)
    async def __call_case_name(cls, skin_id: str) -> list[str]:
        """调用buff api

        参数:
            skin_id: 皮肤id

        返回:
            list[str]: 皮肤所属武器箱
        """
        proxy = None
        if ip := base_config.get("BUFF_PROXY"):
            proxy = {"http://": ip, "https://": ip}
        try:
            response = await AsyncHttpx.get(f"{BUFF_SELL_URL}/{skin_id}", proxy=proxy)
            response.raise_for_status()
            if r := re.search('<meta name="description"(.*?)>', response.text):
                return [
                    s.replace("”", "")
                    .replace("“", "")
                    .replace('"', "")
                    .replace("'", "")
                    .replace("武器箱", "")
                    .replace(" ", "")
                    for s in r[1].split(",")
                    if "武器箱" in s
                ]
        except Exception as e:
            logger.error("访问皮肤所属武器箱异常...", "开箱更新", e=e)
        return []

    @classmethod
    async def search_skin(
        cls, name: str, page: int, update_type: UpdateType
    ) -> BuffResponse:
        logger.debug(
            f"尝试访问武器箱/皮肤: [<u><e>{name}</e></u>] 页数: [<u><y>{page}</y></u>]",
            "开箱更新",
        )
        params = {
            "game": "csgo",
            "page_num": page,
            "page_size": 80,
            "_": time.time(),
            "use_suggestio": 0,
        }
        if update_type == UpdateType.CASE:
            params["itemset"] = CASE2ID[name]
        elif update_type == UpdateType.WEAPON_TYPE:
            params["category"] = KNIFE2ID[name]
        if not (response := await cls.__call_buff_api(params)):
            raise CallApiError("尝试访问武器箱/皮肤第发生错误...")
        response_data = response.json()
        if response_data["code"] == "Login Required":
            raise NotLoginRequired()
        if response_data["code"] != "OK":
            raise CallApiError(f"访问发生异常: {response_data['code']} ...")
        return BuffResponse(**response_data["data"])
