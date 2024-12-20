import nonebot

from zhenxun.utils.http_utils import AsyncHttpx

from ..config import KwHandleType, KwType
from ..models.pix_gallery import PixGallery
from ..models.pix_keyword import PixKeyword
from ..utils import get_api

driver = nonebot.get_driver()


class KeywordManage:
    handle2cn = {"PASS": "通过", "IGNORE": "忽略", "FAIL": "未通过", "BLACK": "黑名单"}  # noqa: RUF012

    @classmethod
    async def add_keyword(cls, user_id: str, keyword: str) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            keyword: 关键词

        返回:
            str: 返回消息
        """
        return await cls.__add_content(user_id, KwType.KEYWORD, keyword)

    @classmethod
    async def add_uid(cls, user_id: str, uid: str) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            uid: 用户uid

        返回:
            str: 返回消息
        """
        if not await cls.__check_id_exists(uid, KwType.UID):
            return "当前UID不存在，请检查UID是否正确..."
        return await cls.__add_content(user_id, KwType.UID, uid)

    @classmethod
    async def add_pid(cls, user_id: str, pid: str) -> str:
        """添加关键词

        参数:
            user_id: 用户id
            pid: 图片pid

        返回:
            str: 返回消息
        """
        if await PixGallery.exists(pid=pid, img_p="p0"):
            return f"当前pid: {pid}已收录图库中，请勿重复添加！"
        if not await cls.__check_id_exists(pid, KwType.PID):
            return "当前PID不存在，请检查PID是否正确..."
        return await cls.__add_content(user_id, KwType.PID, pid)

    @classmethod
    async def handle_keyword(
        cls,
        operator_id: str,
        id: int | None,
        kw_type: KwType | None,
        handle_type: KwHandleType,
        content: str | None = None,
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
        if id:
            data = await PixKeyword.get_or_none(id=id, handle_type__isnull=True)
        else:
            data = await PixKeyword.get_or_none(
                content=content, kw_type=kw_type, handle_type__isnull=True
            )
        if not data:
            if handle_type == KwHandleType.BLACK and content:
                data = await PixKeyword.create(
                    content=content, kw_type=kw_type, user_id=operator_id
                )
            else:
                return f"当前未处理的指定内容/id: {id or content} 不存在..."
        data.handle_type = handle_type
        data.operator_id = operator_id
        await data.save(update_fields=["handle_type", "operator_id"])
        return f"已成功将内容/id: {id or content}设置为{cls.handle2cn[handle_type]}!"

    @classmethod
    async def add_black_pid(cls, user_id: str, pid: str) -> str:
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
    async def __add_content(cls, user_id: str, kw_type: KwType, content: str) -> str:
        """添加内容

        参数:
            user_id: 用户id
            kw_type: 类型
            content: 内容

        返回:
            str: 返回消息
        """
        data = await PixKeyword.get_or_none(content=content, kw_type=kw_type)
        if data:
            return f"当前{kw_type}已存在，状态: {cls.handle2cn[data.handle_type]}"
        pkd = PixKeyword(
            user_id=user_id,
            content=content,
            kw_type=kw_type,
        )
        result = f"已成功添加pix搜图{kw_type}: {content}!"
        if user_id in driver.config.superusers:
            pkd.handle_type = KwHandleType.PASS
        else:
            result += "\n请等待管理员通过该关键词！"
        await pkd.save()
        return result

    @classmethod
    async def __check_id_exists(cls, id: str, type: KwType) -> bool:
        """检查uid/pid是否存在

        参数:
            id: pid/uid
            type: pid/uid

        返回:
            bool: 是否存在
        """
        api = get_api(type)
        data = (await AsyncHttpx.get(api, params={"id": id})).json()
        return not data.get("error")
