from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoRatingHistory(Model):
    """CSGO评分历史记录"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="rating_history")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    rating_type = fields.CharField(20, description="评分类型")
    """评分类型"""
    rating_value = fields.FloatField(description="评分值")
    """评分值"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_rating_history"
        table_description = "CSGO评分历史记录"
        indexes = [  # noqa: RUF012
            ("user_id", "rating_type", "platform_type", "create_time"),
        ]
