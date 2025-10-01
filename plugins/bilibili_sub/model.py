from tortoise import fields

from zhenxun.services.log import logger
from zhenxun.services.db_context import Model


class BiliSub(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """数据库自增ID，用于删除和配置"""
    uid = fields.BigIntField(unique=True)
    """B站用户UID"""
    room_id = fields.BigIntField(null=True, unique=True)
    """B站直播间ID"""
    uname = fields.CharField(255, null=True)
    """UP主/主播名称"""

    last_dynamic_timestamp = fields.BigIntField(null=True, default=0)
    """最新动态时间戳"""
    last_video_timestamp = fields.BigIntField(null=True, default=0)
    """最新视频时间戳"""
    live_status = fields.IntField(null=True, default=0)
    """直播状态 0:未开播 1:直播中"""

    push_dynamic = fields.BooleanField(default=True)
    """是否推送动态"""
    push_video = fields.BooleanField(default=True)
    """是否推送视频"""
    push_live = fields.BooleanField(default=True)
    """是否推送直播"""

    at_all_dynamic = fields.BooleanField(default=False)
    """是否在推送动态时@全体"""
    at_all_video = fields.BooleanField(default=False)
    """是否在推送视频/番剧时@全体"""
    at_all_live = fields.BooleanField(default=False)
    """是否在推送直播时@全体"""

    class Meta:
        table = "bilisub"
        table_description = "B站订阅信息表"


class BiliSubTarget(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增ID"""
    subscription = fields.ForeignKeyField("models.BiliSub", related_name="targets")
    """关联的订阅信息"""
    target_id = fields.CharField(255)
    """订阅目标ID (e.g., 'group_123456', 'private_789012')"""

    class Meta:
        table = "bilisub_target"
        table_description = "B站订阅关系表"
        unique_together = ("subscription", "target_id")

    @classmethod
    async def clean_orphaned_subs(cls):
        """清理没有任何目标订阅的BiliSub记录"""
        all_sub_ids = await BiliSub.all().values_list("id", flat=True)
        active_sub_ids = (
            await cls.all().distinct().values_list("subscription_id", flat=True)
        )
        orphaned_ids = set(all_sub_ids) - set(active_sub_ids)
        if orphaned_ids:
            deleted_count = await BiliSub.filter(id__in=list(orphaned_ids)).delete()
            logger.info(f"清理了 {deleted_count} 个孤立的B站订阅记录。")
