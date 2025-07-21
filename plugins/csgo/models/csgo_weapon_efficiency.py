from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoWeaponEfficiency(Model):
    """CSGO武器效率记录"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="weapon_efficiency")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    efficiency_value = fields.FloatField(default=0, description="效率值")
    """效率值"""
    record_index = fields.IntField(description="记录索引")
    """记录索引"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_weapon_efficiency"
        table_description = "CSGO武器效率记录"
        indexes = [  # noqa: RUF012
            ("user_id", "record_index", "platform_type", "season_id"),
        ]
