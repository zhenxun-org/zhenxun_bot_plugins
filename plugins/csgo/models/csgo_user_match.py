from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoPerfectWorldMatch(Model):
    """CSGO完美世界比赛数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField(
        "models.CsgoUser", related_name="perfect_world_matches"
    )
    """关联用户"""
    match_id = fields.CharField(50, description="比赛ID")
    """比赛ID"""
    mode = fields.CharField(50, description="比赛模式", null=True)
    """比赛模式"""
    map_name = fields.CharField(50, description="地图名称")
    """地图名称"""
    map_logo = fields.CharField(255, description="地图图标URL", null=True)
    """地图图标URL"""
    score1 = fields.IntField(description="队伍1得分")
    """队伍1得分"""
    score2 = fields.IntField(description="队伍2得分")
    """队伍2得分"""
    team = fields.IntField(description="玩家所在队伍", default=1)
    """玩家所在队伍"""
    win_team = fields.IntField(description="获胜队伍", default=1)
    """获胜队伍"""
    kill = fields.IntField(description="击杀数")
    """击杀数"""
    death = fields.IntField(description="死亡数")
    """死亡数"""
    assist = fields.IntField(description="助攻数")
    """助攻数"""
    rating = fields.FloatField(description="Rating PRO评分")
    """Rating PRO评分"""
    we = fields.FloatField(description="WE值", null=True)
    """WE值"""
    mvp = fields.BooleanField(description="是否为MVP", default=False)
    """是否为MVP"""
    k4 = fields.IntField(description="四杀次数", default=0)
    """四杀次数"""
    k5 = fields.IntField(description="五杀次数", default=0)
    """五杀次数"""
    start_time = fields.DatetimeField(description="比赛开始时间")
    """比赛开始时间"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_perfect_world_matches"
        table_description = "CSGO完美世界比赛数据"
        indexes = [  # noqa: RUF012
            ("user_id", "match_id"),
        ]
