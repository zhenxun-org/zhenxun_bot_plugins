from tortoise import fields

from zhenxun.services.db_context import Model


class GiftStore(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    uuid = fields.CharField(255)
    """道具uuid"""
    name = fields.CharField(255)
    """道具名称"""
    icon = fields.CharField(255, null=True)
    """道具图标"""
    description = fields.TextField(default="")
    """道具描述"""
    count = fields.IntField(default=0)
    """礼物送出次数"""
    create_time = fields.DatetimeField(auto_now_add=True)
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "bym_gift_store"
        table_description = "礼物列表"
