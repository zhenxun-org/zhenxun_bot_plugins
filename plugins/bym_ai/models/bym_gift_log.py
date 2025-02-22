from tortoise import fields

from zhenxun.services.db_context import Model


class GiftLog(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255)
    """用户id"""
    uuid = fields.CharField(255)
    """礼物uuid"""
    type = fields.IntField()
    """类型，0：获得，1：使用"""
    create_time = fields.DatetimeField(auto_now_add=True)
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "bym_gift_log"
