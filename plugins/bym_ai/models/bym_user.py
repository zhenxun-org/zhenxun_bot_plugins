from tortoise import fields

from zhenxun.services.db_context import Model

from .bym_gift_log import GiftLog


class BymUser(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255, unique=True, description="用户id")
    """用户id"""
    props: dict[str, int] = fields.JSONField(default={})  # type: ignore
    """道具"""
    usage_count: dict[str, int] = fields.JSONField(default={})  # type: ignore
    """使用道具次数"""
    platform = fields.CharField(255, null=True, description="平台")
    """平台"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "bym_user"
        table_description = "用户数据表"

    @classmethod
    async def get_user(cls, user_id: str, platform: str | None = None) -> "BymUser":
        """获取用户

        参数:
            user_id: 用户id
            platform: 平台.

        返回:
            UserConsole: UserConsole
        """
        if not await cls.exists(user_id=user_id):
            await cls.create(user_id=user_id, platform=platform)
        return await cls.get(user_id=user_id)

    @classmethod
    async def add_gift(cls, user_id: str, gift_uuid: str):
        """添加道具

        参数:
            user_id: 用户id
            gift_uuid: 道具uuid
        """
        user = await cls.get_user(user_id)
        user.props[gift_uuid] = user.props.get(gift_uuid, 0) + 1
        await GiftLog.create(user_id=user_id, gift_uuid=gift_uuid, type=0)
        await user.save(update_fields=["props"])

    @classmethod
    async def use_gift(cls, user_id: str, gift_uuid: str, num: int):
        """使用道具

        参数:
            user_id: 用户id
            gift_uuid: 道具uuid
            num: 使用数量
        """
        user = await cls.get_user(user_id)
        if user.props.get(gift_uuid, 0) < num:
            raise ValueError("道具数量不足")
        user.props[gift_uuid] -= num
        user.usage_count[gift_uuid] = user.usage_count.get(gift_uuid, 0) + num
        create_list = [
            GiftLog(user_id=user_id, gift_uuid=gift_uuid, type=1) for _ in range(num)
        ]
        await GiftLog.bulk_create(create_list)
        await user.save(update_fields=["props", "usage_count"])
