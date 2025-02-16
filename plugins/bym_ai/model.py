from tortoise import fields

from zhenxun.services.db_context import Model


class BymChat(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255)
    """用户id"""
    group_id = fields.CharField(255, null=True)
    """群组id"""
    plain_text = fields.TextField()
    """消息文本"""
    result = fields.TextField()
    """回复内容"""
    is_reset = fields.BooleanField(default=False)
    """是否当前重置会话"""
    create_time = fields.DatetimeField(auto_now_add=True)
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "bym_chat"
        table_description = "Bym聊天记录表"
