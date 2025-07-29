from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoMatchRecord(Model):
    """CSGO比赛记录"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="match_records")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    match_id = fields.CharField(50, description="比赛ID")
    """比赛ID"""
    match_time = fields.DatetimeField(description="比赛时间")
    """比赛时间"""
    map_code = fields.CharField(50, description="地图代码")
    """地图代码"""
    map_name = fields.CharField(50, description="地图名称")
    """地图名称"""
    match_type = fields.IntField(description="比赛类型")
    """比赛类型"""
    match_result = fields.IntField(description="比赛结果(1=胜利,0=平局,-1=失败)")
    """比赛结果(1=胜利,0=平局,-1=失败)"""
    team_score = fields.IntField(description="队伍得分")
    """队伍得分"""
    enemy_score = fields.IntField(description="敌方得分")
    """敌方得分"""
    kills = fields.IntField(description="击杀数")
    """击杀数"""
    deaths = fields.IntField(description="死亡数")
    """死亡数"""
    assists = fields.IntField(description="助攻数")
    """助攻数"""
    rating = fields.FloatField(description="评分")
    """评分"""
    adr = fields.FloatField(description="场均伤害")
    """场均伤害"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_match_records"
        table_description = "CSGO比赛记录"
        indexes = [  # noqa: RUF012
            ("user_id", "match_id", "platform_type", "season_id"),
        ]
