from datetime import datetime
from typing import ClassVar

from nonebot_plugin_alconna import Text, UniMessage, UniMsg
from pydantic import BaseModel

from .model import DialogueRecord


class DialogueData(BaseModel):
    id: int
    """记录id"""
    name: str
    """用户名称"""
    user_id: str
    """用户id"""
    group_id: str | None
    """群组id"""
    group_name: str | None
    """群组名称"""
    message: UniMessage
    """消息内容"""
    reply_text: str
    """回复内容"""
    is_replied: bool
    """是否已回复"""
    reply_admin_id: str | None
    """回复管理员id"""
    create_time: datetime
    """创建时间"""
    reply_time: datetime | None
    """回复时间"""
    platform: str | None
    """平台"""

    class Config:
        arbitrary_types_allowed = True


class DialogueManager:
    MAX_CACHE_SIZE: ClassVar[int] = 500

    @classmethod
    async def add(
        cls,
        name: str,
        uid: str,
        gid: str | None,
        group_name: str | None,
        message: UniMsg,
        platform: str | None,
    ) -> int:
        record = await DialogueRecord.create(
            user_name=name,
            user_id=uid,
            group_id=gid,
            group_name=group_name or "",
            message_data=message.dump(True),
            platform=platform,
        )
        await cls._trim_cache()
        return int(record.id)

    @classmethod
    async def remove(cls, index: int):
        await DialogueRecord.filter(id=index).delete()

    @classmethod
    async def get(cls, k: int) -> DialogueData | None:
        if record := await DialogueRecord.get_or_none(id=k):
            return cls._to_data(record)
        return None

    @classmethod
    async def list_by_platform(
        cls, platform: str | None, pending_only: bool = True
    ) -> list[DialogueData]:
        query = DialogueRecord.all().order_by("id")
        if platform:
            query = query.filter(platform=platform)
        if pending_only:
            query = query.filter(is_replied=False)
        records = await query
        return [cls._to_data(record) for record in records]

    @classmethod
    async def list_by_platform_page(
        cls,
        platform: str | None,
        pending_only: bool = True,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[DialogueData], int, int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 50)

        query = DialogueRecord.all()
        if platform:
            query = query.filter(platform=platform)
        if pending_only:
            query = query.filter(is_replied=False)

        total = await query.count()
        if total == 0:
            return [], 0, 0

        total_pages = (total + page_size - 1) // page_size
        page = min(page, total_pages)
        offset = (page - 1) * page_size

        records = await query.order_by("id").offset(offset).limit(page_size)
        return [cls._to_data(record) for record in records], total, total_pages

    @classmethod
    async def mark_replied(cls, record_id: int, reply_text: str, admin_id: str):
        await DialogueRecord.filter(id=record_id).update(
            reply_text=reply_text,
            is_replied=True,
            reply_admin_id=admin_id,
            reply_time=datetime.now(),
        )

    @classmethod
    def build_report_message(cls, data: DialogueData) -> UniMessage:
        result = UniMessage()
        result.append(Text("*****一份交流报告*****\n"))
        result.append(Text(f"Id: {data.id}\n"))
        result.append(Text(f"昵称: {data.name}({data.user_id})\n"))
        if data.group_id:
            result.append(Text(f"群组: {data.group_name or ''}({data.group_id})\n"))
        result.append(Text("消息:\n"))
        result.extend(data.message)
        return result

    @classmethod
    def _to_data(cls, record: DialogueRecord) -> DialogueData:
        message = cls._load_message(record.message_data)
        return DialogueData(
            id=record.id,
            name=record.user_name,
            user_id=record.user_id,
            group_id=record.group_id,
            group_name=record.group_name,
            message=message,
            reply_text=record.reply_text or "",
            is_replied=bool(record.is_replied),
            reply_admin_id=record.reply_admin_id,
            create_time=record.create_time,
            reply_time=record.reply_time,
            platform=record.platform,
        )

    @classmethod
    def _load_message(cls, payload) -> UniMessage:
        try:
            return UniMessage().load(payload)
        except Exception:
            msg = UniMessage()
            msg.append(Text("[原始消息解析失败]"))
            return msg

    @classmethod
    async def _trim_cache(cls):
        total = await DialogueRecord.all().count()
        overflow = total - cls.MAX_CACHE_SIZE
        if overflow <= 0:
            return
        old_ids = (
            await DialogueRecord.all()
            .order_by("id")
            .limit(overflow)
            .values_list(
                "id",
                flat=True,
            )
        )
        if old_ids:
            await DialogueRecord.filter(id__in=list(old_ids)).delete()
