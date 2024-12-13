from tortoise import fields

from zhenxun.builtin_plugins.pix_gallery.config import KwHandleType, KwType
from zhenxun.services.db_context import Model


class PixKeyword(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    content = fields.CharField(255, unique=True)
    """内容"""
    kw_type = fields.CharEnumField(KwType, description="关键词类型")
    """关键词类型"""
    handle_type = fields.CharEnumField(KwHandleType, null=True, description="处理类型")
    """处理类型"""
    operator_id = fields.CharField(255, null=True)
    """处理人id"""
    seek_count = fields.IntField(default=0, description="搜索次数")
    """搜索次数"""
    is_available = fields.BooleanField(default=True, description="是否可用")
    """是否可用"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""
    update_time = fields.DatetimeField(null=True, description="更新时间")
    """更新时间"""

    class Meta:  # type: ignore
        table = "pix_keyword1"
        table_description = "pix关键词数据表"
        unique_together = ("content", "kw_type")
