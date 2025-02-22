from tortoise import fields

from zhenxun.services.db_context import Model


class LikeLog(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255, null=True)
    """用户id"""
    count = fields.IntField(default=0)
    """点赞数量"""
    create_time = fields.DatetimeField(auto_now_add=True)
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "like_log"
        table_description = "点赞日志数据表"
