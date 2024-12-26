import nonebot

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ..config import KwHandleType, KwType, UidModel
from ..models.pix_keyword import PixKeyword
from ..utils import get_api

driver = nonebot.get_driver()


class KeywordManage:
    handle2cn = {"PASS": "通过", "IGNORE": "忽略", "FAIL": "未通过", "BLACK": "黑名单"}  # noqa: RUF012

    @classmethod
    async def add_keyword(cls, user_id: str, keyword: tuple[str, ...]) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            keyword: 关键词

        返回:
            str: 返回消息
        """
        return await cls.__add_content(user_id, KwType.KEYWORD, list(set(keyword)))

    @classmethod
    async def add_uid(cls, user_id: str, uids: tuple[str, ...]) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            uid: 用户uid

        返回:
            str: 返回消息
        """
        allow_uid = []
        exist_uid = []
        error_uid = []
        for u in set(uids):
            u = u.strip()
            if await PixKeyword.exists(content=u, kw_type=KwType.UID):
                exist_uid.append(u)
                continue
            try:
                if result := await cls.__check_id_exists(u, KwType.UID):
                    error_uid.append(u)
                    continue
            except Exception as e:
                logger.error(f"检测uid失败: {u}, 错误信息: {type(e)}: {e}")
            allow_uid.append(u)
        result = await cls.__add_content(user_id, KwType.UID, allow_uid)
        if exist_uid:
            result += f"\n当前UID: {','.join(exist_uid)}已收录图库中，请勿重复添加！"
        if error_uid:
            result += f"\n当前UID: {','.join(error_uid)}检测失败，"
            "请检查UID是否正确或稍后重试..."
        return result

    @classmethod
    async def add_pid(cls, user_id: str, pids: tuple[str, ...]) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            pid: 图片pid

        返回:
            str: 返回消息
        """
        allow_pid = []
        exist_pid = []
        error_pid = []
        for p in set(pids):
            p = p.strip()
            if await PixKeyword.exists(content=p, kw_type=KwType.PID):
                exist_pid.append(p)
                continue
            try:
                if result := await cls.__check_id_exists(p, KwType.PID):
                    error_pid.append(p)
                    continue
            except Exception as e:
                logger.error(f"检测pid失败: {p}, 错误信息: {type(e)}: {e}")
            allow_pid.append(p)
        result = await cls.__add_content(user_id, KwType.PID, allow_pid)
        if exist_pid:
            result += f"\n当前PID: {','.join(exist_pid)}已收录图库中，请勿重复添加！"
        if error_pid:
            result += f"\n当前PID: {','.join(error_pid)}检测失败，"
            "请检查PID是否正确或稍后重试..."
        return result

    @classmethod
    async def handle_keyword(
        cls,
        operator_id: str,
        ids: tuple[int, ...] | None,
        kw_type: KwType | None,
        handle_type: KwHandleType,
        content: tuple[str, ...] | None = None,
    ) -> str:
        """处理关键词

        参数:
            operator_id: 操作用户id
            keyword: 关键词
            kw_type: 关键词类型
            handle_type: 处理类型
            content: 内容

        返回:
            str: 返回消息
        """
        if operator_id not in driver.config.superusers:
            return "权限不足..."
        if ids:
            data = await PixKeyword.filter(id__in=ids, handle_type__isnull=True).all()
        else:
            data = await PixKeyword.get_or_none(
                content=content, kw_type=kw_type, handle_type__isnull=True
            )
            if data:
                data = [data]
        if not data:
            if handle_type == KwHandleType.BLACK and content:
                data = [
                    await PixKeyword.create(
                        content=content, kw_type=kw_type, user_id=operator_id
                    )
                ]
            else:
                return f"当前未处理的指定内容/id: {id or content} 不存在..."
        for d in data:
            d.handle_type = handle_type
            d.operator_id = operator_id
            await d.save(update_fields=["handle_type", "operator_id"])
        return f"已成功将内容/id: {id or content}设置为{cls.handle2cn[handle_type]}!"

    @classmethod
    async def add_black_pid(cls, user_id: str, pid: tuple[str, ...]) -> str:
        """添加黑名单pid

        参数:
            user_id: 用户id
            pid: 图片pid

        返回:
            str: 返回消息
        """
        return await cls.handle_keyword(
            user_id, None, KwType.PID, KwHandleType.BLACK, pid
        )

    @classmethod
    async def __add_content(
        cls, user_id: str, kw_type: KwType, content: list[str]
    ) -> str:
        """添加内容

        参数:
            user_id: 用户id
            kw_type: 类型
            content: 内容

        返回:
            str: 返回消息
        """
        for c in content:
            data = await PixKeyword.get_or_none(content=c, kw_type=kw_type)
            if data:
                status = cls.handle2cn[data.handle_type]
                return f"当前content: {c}，{kw_type}已存在，状态: {status}"
        pkd_list = []
        exists_content = await PixKeyword.filter(
            content__in=content, kw_type=kw_type
        ).values_list("content", flat=True)
        ignore_kw = []
        for c in content:
            c = c.strip()
            if c not in exists_content:
                handle_type = None
                operator_id = None
                if user_id in driver.config.superusers:
                    logger.debug("超级用户token，直接通过...", "PIX_GALLERY")
                    handle_type = KwHandleType.PASS
                pkd_list.append(
                    PixKeyword(
                        content=c,
                        kw_type=kw_type,
                        handle_type=handle_type,
                        operator_id=operator_id,
                    )
                )
            else:
                ignore_kw.append(c)
                logger.warning(f"关键词: {c} 已存在，跳过添加")
        result = f"已成功添加pix搜图{kw_type}: {content}!"


    @classmethod
    async def __check_id_exists(cls, id: str, type: KwType) -> str:
        """检查uid/pid是否存在

        参数:
            id: pid/uid
            type: pid/uid

        返回:
            bool: 是否存在
        """
        api = get_api(type)  # type: ignore
        res = await AsyncHttpx.get(api, params={"id": id})
        res.raise_for_status()
        data = res.json()
        if er := data.get("error"):
            return er.get("user_message") or er.get("message")
        if type == KwType.UID:
            model = UidModel(**data)
            if model == 0 or not model.illusts:
                return "uid不存在或uid作品为空..."
        return ""
