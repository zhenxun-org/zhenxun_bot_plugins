import asyncio
from asyncio import Semaphore, Task, sleep
from copy import deepcopy
from datetime import datetime
import random
from typing import Literal

from tortoise.expressions import F
from tortoise.functions import Concat

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ..config import (
    KeywordModel,
    KwHandleType,
    KwType,
    NoneModel,
    PidModel,
    UidModel,
    base_config,
)
from ..exceptions import (
    NotFindPageException,
    OAuthException,
)
from ..models.pix_gallery import PixGallery
from ..models.pix_keyword import PixKeyword
from ..utils import get_api


class PixSeekManage:
    @classmethod
    async def start_seek(
        cls,
        seek_type: Literal["u", "p", "k", "a"],
        num: int | None,
        only_not_update: bool = True,
    ) -> tuple[int, int]:
        """获取关键词数据

        参数:
            seek_type: 搜索类型
            num: 数量
            only_not_update: 仅仅搜索未更新过的数据.

        返回:
            tuple[int, int]: 保存数量, 重复数据
        """
        query = PixKeyword.filter(handle_type=KwHandleType.PASS, is_available=True)
        if seek_type == "u":
            query = query.filter(kw_type=KwType.UID)
        elif seek_type == "p":
            query = PixKeyword.filter(kw_type=KwType.PID)
        elif seek_type == "k":
            query = PixKeyword.filter(kw_type=KwType.KEYWORD)
        if only_not_update:
            query = query.filter(seek_count=0).annotate().order_by("-create_time")
        else:
            query = query.annotate().order_by("seek_count")
        if num:
            query = query.limit(num)
        data_list = await query.all()
        if not data_list:
            raise ValueError("没有需要收录的数据...")
        return await cls.seek(data_list)

    @classmethod
    async def __seek(
        cls, content: str, t: KwType, api: str, params: dict, semaphore: Semaphore
    ) -> PidModel | UidModel | KeywordModel | NoneModel:
        """搜索关键词

        参数:
            content: 内容
            t: 关键词类型
            api: api
            params: 参数
            semaphore: 信号量
        """
        async with semaphore:
            logger.debug(f"访问API: {api}, 参数: {params}")
            res = None
            json_data = None
            try:
                rand = random.randint(0, 10)
                logger.debug(f"访问随机休眠: {rand}")
                await asyncio.sleep(rand)
                res = await AsyncHttpx.get(api, params=params)
                json_data = res.json()
                if er := json_data.get("error"):
                    if msg := er.get("message"):
                        if "Error occurred at the OAuth process" in msg:
                            raise OAuthException()
                    if msg := er.get("user_message"):
                        if "尚无此页" in msg:
                            raise NotFindPageException()
                if res.status_code != 200:
                    logger.warning(
                        f"PIX搜索失败,api:{api},"
                        f"params:{params},httpCode: {res.status_code}"
                    )
                    return NoneModel(content=content, kw_type=t, error="status_code")
                logger.debug(f"访问成功 api: {api}, 参数: {params}")
                if t == KwType.PID:
                    return PidModel(**json_data["illust"])
                elif t == KwType.UID:
                    u = UidModel(**json_data)
                    if u.next_url and u.illusts:
                        params["page"] += 1
                        await sleep(1)
                        r = await cls.__seek(content, t, api, params, semaphore)
                        if isinstance(r, UidModel):
                            u.illusts.extend(r.illusts)
                    if not u.illusts:
                        return NoneModel(
                            content=content, kw_type=t, error="not_find_illusts"
                        )
                    return u
                else:
                    return KeywordModel(**res.json(), keyword=content)
            except OAuthException as e:
                logger.warning(
                    f"PIX搜索数据问题 {content}-{t}: {json_data or ''} & {type(e)}: {e}"
                )
                return NoneModel(content=content, kw_type=t, error="oauth")
            except NotFindPageException as e:
                logger.warning(
                    f"PIX搜索数据问题 {content}-{t}: {json_data or ''} & {type(e)}: {e}"
                )
                return NoneModel(content=content, kw_type=t, error="not_find_page")
            except Exception as e:
                logger.warning(
                    f"PIX搜索数据问题 {content}-{t}: {json_data or ''} & {type(e)}: {e}"
                )
                return NoneModel(content=content, kw_type=t, error=str(e))

    @classmethod
    async def get_exists_id(cls) -> list[str]:
        """获取已存在的pid以及img_P

        返回:
            list[str]: pid_img_p
        """
        return await PixGallery.annotate(t=Concat("pid", "_", F("img_p"))).values_list(
            "t", flat=True
        )  # type: ignore

    @classmethod
    async def seek(cls, data_list: list[PixKeyword]) -> tuple[int, int]:
        """搜索关键词

        参数:
            data_list: 数据列表

        返回:
            tuple[int, int]: 保存数量, 重复数据
        """
        task_list = []
        semaphore = asyncio.Semaphore(1000)
        for data in data_list:
            logger.debug(f"PIX开始收录 {data.kw_type}: {data.content}")
            if data.kw_type == KwType.PID:
                task_list.append(cls.seek_pid(data.content, semaphore))
            elif data.kw_type == KwType.UID:
                task_list.append(cls.seek_uid(data.content, semaphore))
            elif data.kw_type == KwType.KEYWORD:
                for page in range(1, 30):
                    logger.debug(
                        f"PIX开始收录 {data.kw_type}: {data.content} | page: {page}"
                    )
                    task_list.append(cls.seek_keyword(data.content, page, semaphore))
        return await cls._run_to_db(task_list, data_list)

    @classmethod
    async def _run_to_db(
        cls, task_list: list[Task], data_list: list[PixKeyword]
    ) -> tuple[int, int]:
        result = await asyncio.gather(*task_list)
        now = datetime.now()
        num = len(data_list)
        for r in result:
            if isinstance(r, KeywordModel):
                for data in data_list:
                    if data.content == r.keyword and data.kw_type == KwType.KEYWORD:
                        logger.debug(f"PIX收录 {r.keyword} 的数据: {len(r.illusts)}")
                        data.seek_count += 1
                        data.update_time = now
                        break
            elif isinstance(r, PidModel):
                for data in data_list:
                    if data.content == str(r.id) and data.kw_type == KwType.PID:
                        logger.debug(
                            f"PIX收录 {r.id} "
                            f"的数据: {len(r.meta_pages) if r.meta_pages else 1}"
                        )
                        data.seek_count += 1
                        data.update_time = now
                        break
            elif isinstance(r, UidModel):
                for data in data_list:
                    if data.content == str(r.user.id) and data.kw_type == KwType.UID:
                        logger.debug(f"PIX收录 {r.user.id} 的数据: {len(r.illusts)}")
                        data.seek_count += 1
                        data.update_time = now
                        break
            elif isinstance(r, NoneModel):
                num -= 1
                logger.debug(f"pix 过滤无效Model: {r.content}:{r.kw_type}")
                if r.error in ["oauth", "not_find_page", "not_find_illusts"]:
                    for data in data_list:
                        if data.content == r.content and data.kw_type == r.kw_type:
                            logger.debug(
                                f"PIX收录 {r.content}:{r.kw_type} 标记不可用..."
                            )
                            data.is_available = False
                            data.update_time = now
                            break
        logger.debug(f"共收录: {num} 条数据.")
        await PixKeyword.bulk_update(
            data_list, fields=["seek_count", "update_time", "is_available"]
        )
        return await cls.data_to_db(result)

    @classmethod
    async def data_to_db(
        cls, data_list: list[KeywordModel | PidModel | UidModel]
    ) -> tuple[int, int]:
        """将数据保存到数据库

        参数:
            data_list: 数据列表

        返回:
            tuple[int, int]: 保存数量, 重复数据
        """
        model_list: list[PixGallery] = []
        for data in data_list:
            if isinstance(data, PidModel):
                model_list.extend(cls.pid2model(data))
            elif isinstance(data, UidModel):
                model_list.extend(cls.uid2model(data))
            elif isinstance(data, KeywordModel):
                model_list.extend(cls.keyword2model(data))
        exists = await cls.get_exists_id()
        model_list_s = []
        in_list = []
        exists_count = 0
        for model in model_list:
            k = f"{model.pid}_{model.img_p}"
            if model and k not in exists and k not in in_list:
                in_list.append(f"{model.pid}_{model.img_p}")
                model_list_s.append(model)
            else:
                logger.debug(f"pix收录已存在: {model.pid}_{model.img_p}...")
                exists_count += 1
        if model_list_s:
            logger.debug(f"pix收录保存数据数量: {len(model_list_s)}")
            await PixGallery.bulk_create(model_list_s, 10)
        return len(model_list_s), exists_count

    @classmethod
    def keyword2model(cls, model: KeywordModel) -> list[PixGallery]:
        data_list = []
        for illust in model.illusts:
            if illust.total_bookmarks >= base_config.get("SEARCH_HIBIAPI_BOOKMARKS"):
                data_list.extend(cls.pid2model(illust))
            else:
                logger.debug(
                    f"pix PID:{illust.id}"
                    f" 收录收藏数不足: {illust.total_bookmarks},已跳过"
                )
        return data_list

    @classmethod
    def uid2model(cls, model: UidModel) -> list[PixGallery]:
        data_list = []
        for illust in model.illusts:
            if illust.total_bookmarks >= base_config.get("SEARCH_HIBIAPI_BOOKMARKS"):
                if len(illust.meta_pages or []) > 5:
                    logger.debug(f"pix PID: {illust.id} 图片数量大于5, 已跳过")
                    continue
                data_list.extend(cls.pid2model(illust))
            else:
                logger.debug(
                    f"pix PID: {illust.id}"
                    f" 收录收藏数不足: {illust.total_bookmarks}, 已跳过"
                )
        return data_list

    @classmethod
    def pid2model(cls, model: PidModel, img_p: int = 0) -> list[PixGallery]:
        data_list = []
        data_json = model.dict()
        del data_json["id"]
        data_json["pid"] = model.id
        data_json["uid"] = model.user.id
        data_json["author"] = model.user.name
        data_json["tags"] = model.tags_text
        if "r18" in model.tags_text.lower() or "r-18" in model.tags_text.lower():
            data_json["nsfw_tag"] = 2
        else:
            data_json["nsfw_tag"] = 0
        data_json["is_ai"] = (
            "ai," in model.tags_text.lower() or "ai画图," in model.tags_text.lower()
        )
        data_json["img_p"] = img_p
        if model.meta_pages:
            for meta_page in model.meta_pages:
                copy_data = deepcopy(data_json)
                copy_data["img_p"] = img_p
                copy_data["image_urls"] = meta_page["image_urls"]
                copy_data["is_multiple"] = True
                img_p += 1
                logger.debug(f"pix收录: {copy_data}")
                data_list.append(PixGallery(**copy_data))
        else:
            data_json["img_p"] = img_p
            logger.debug(f"pix收录: {data_json}")
            data_list.append(PixGallery(**data_json))
        return data_list

    @classmethod
    def seek_pid(cls, pid: str, semaphore: Semaphore) -> Task:
        api = get_api(KwType.PID)
        params = {"id": pid}
        return asyncio.create_task(cls.__seek(pid, KwType.PID, api, params, semaphore))

    @classmethod
    def seek_uid(cls, uid: str, semaphore: Semaphore) -> Task:
        api = get_api(KwType.UID)
        params = {"id": uid, "page": 1}
        return asyncio.create_task(cls.__seek(uid, KwType.UID, api, params, semaphore))

    @classmethod
    def seek_keyword(cls, keyword: str, page: int, semaphore: Semaphore) -> Task:
        api = get_api(KwType.KEYWORD)
        params = {"word": keyword, "page": page}
        return asyncio.create_task(
            cls.__seek(keyword, KwType.KEYWORD, api, params, semaphore)
        )
