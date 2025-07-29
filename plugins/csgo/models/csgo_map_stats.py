from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoMapStats(Model):
    """CSGO地图统计数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="map_stats")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    map_name_zh = fields.CharField(50, description="地图名称")
    """地图名称"""
    map_name = fields.CharField(50, description="地图名称")
    """地图名称"""
    map_image_url = fields.TextField(null=True, description="地图图片URL")
    """地图图片URL"""
    map_logo_url = fields.TextField(null=True, description="地图Logo URL")
    """地图Logo URL"""
    total_matches = fields.IntField(default=0, description="总比赛场次")
    """总比赛场次"""
    win_count = fields.IntField(default=0, description="胜利场次")
    """胜利场次"""
    total_kills = fields.IntField(default=0, description="总击杀数")
    """总击杀数"""
    total_damage = fields.IntField(default=0, description="总伤害量")
    """总伤害量"""
    rating_sum = fields.FloatField(default=0, description="评分总和")
    """评分总和"""
    rws_sum = fields.FloatField(default=0, description="RWS总和")
    """RWS总和"""
    total_deaths = fields.IntField(default=0, description="总死亡数")
    """总死亡数"""
    first_kills = fields.IntField(default=0, description="首杀次数")
    """首杀次数"""
    first_deaths = fields.IntField(default=0, description="首死次数")
    """首死次数"""
    headshot_kills = fields.IntField(default=0, description="爆头击杀数")
    """爆头击杀数"""
    mvp_count = fields.IntField(default=0, description="MVP次数")
    """MVP次数"""
    triple_kills = fields.IntField(default=0, description="三杀次数")
    """三杀次数"""
    quad_kills = fields.IntField(default=0, description="四杀次数")
    """四杀次数"""
    penta_kills = fields.IntField(default=0, description="五杀次数")
    """五杀次数"""
    vs3_wins = fields.IntField(default=0, description="1v3胜利次数")
    """1v3胜利次数"""
    vs4_wins = fields.IntField(default=0, description="1v4胜利次数")
    """1v4胜利次数"""
    vs5_wins = fields.IntField(default=0, description="1v5胜利次数")
    """1v5胜利次数"""
    is_scuffle = fields.BooleanField(default=False, description="是否为混战模式")
    """是否为混战模式"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_map_stats"
        table_description = "CSGO地图统计数据"
        indexes = [  # noqa: RUF012
            ("user_id", "map_name", "platform_type", "season_id"),
        ]
