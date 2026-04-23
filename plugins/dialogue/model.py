from tortoise import fields

from zhenxun.services.db_context import Model


class DialogueRecord(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_name = fields.CharField(255, description="用户昵称")
    """用户昵称"""
    user_id = fields.CharField(255, description="用户id")
    """用户id"""
    group_id = fields.CharField(255, null=True, description="群组id")
    """群组id"""
    group_name = fields.TextField(default="", description="群组名称")
    """群组名称"""
    message_data = fields.JSONField(description="序列化后的消息内容")
    """序列化后的消息内容"""
    reply_text = fields.TextField(default="", description="管理员回复内容")
    """管理员回复内容"""
    is_replied = fields.BooleanField(default=False, description="是否已回复")
    """是否已回复"""
    reply_admin_id = fields.CharField(255, null=True, description="回复管理员id")
    """回复管理员id"""
    reply_time = fields.DatetimeField(null=True, description="回复时间")
    """回复时间"""
    platform = fields.CharField(255, null=True, description="平台")
    """平台"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "dialogue_record"
        table_description = "联系管理员消息记录表"
