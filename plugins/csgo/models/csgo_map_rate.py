from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoMapRate(Model):
    """CSGO地图胜率数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="map_rates")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    map_name_zh = fields.CharField(50, description="地图中文名称")
    """地图中文名称"""
    map_name = fields.CharField(50, description="地图英文名称")
    """地图英文名称"""
    map_url = fields.TextField(null=True, description="地图图片URL")
    """地图图片URL"""
    match_count = fields.IntField(default=0, description="比赛场次")
    """比赛场次"""
    win_count = fields.IntField(default=0, description="胜利场次")
    """胜利场次"""
    win_rate = fields.FloatField(default=0, description="胜率")
    """胜率"""
    t_win_rate = fields.FloatField(default=0, description="T阵营胜率")
    """T阵营胜率"""
    ct_win_rate = fields.FloatField(default=0, description="CT阵营胜率")
    """CT阵营胜率"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_map_rates"
        table_description = "CSGO地图胜率数据"
        indexes = [  # noqa: RUF012
            ("user_id", "map_name", "platform_type"),
        ]
