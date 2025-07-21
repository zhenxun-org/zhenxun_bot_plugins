from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoWeaponStats(Model):
    """CSGO武器统计数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="weapon_stats")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    season_id = fields.CharField(10, description="赛季")
    """赛季"""
    weapon_code = fields.CharField(50, description="武器代码")
    """武器代码"""
    weapon_name = fields.CharField(50, description="武器名称")
    """武器名称"""
    weapon_image_url = fields.TextField(null=True, description="武器图片URL")
    """武器图片URL"""
    total_kills = fields.IntField(default=0, description="总击杀数")
    """总击杀数"""
    headshot_kills = fields.IntField(default=0, description="爆头击杀数")
    """爆头击杀数"""
    total_matches = fields.IntField(default=0, description="使用场次")
    """使用场次"""
    total_damage = fields.IntField(default=0, description="总伤害")
    """总伤害"""
    avg_damage = fields.FloatField(default=0, description="场均伤害")
    """场均伤害"""
    first_shot_hits = fields.IntField(default=0, description="首发射击命中数")
    """首发射击命中数"""
    first_shot_attempts = fields.IntField(default=0, description="首发射击尝试数")
    """首发射击尝试数"""
    first_shot_accuracy = fields.FloatField(default=0, description="首发射击命中率")
    """首发射击命中率"""
    kill_count_for_ttk = fields.IntField(default=0, description="有效击杀次数")
    """有效击杀次数"""
    total_time_to_kill = fields.IntField(default=0, description="总击杀耗时(ms)")
    """总击杀耗时(ms)"""
    avg_time_to_kill = fields.IntField(default=0, description="平均击杀耗时(ms)")
    """平均击杀耗时(ms)"""
    ttk_rating = fields.CharField(1, default="", description="耗时评级")
    """耗时评级"""
    accuracy_rating = fields.CharField(1, default="", description="命中率评级")
    """命中率评级"""
    accuracy_type = fields.IntField(
        default=1, description="精度类型(1=自动武器,2=手枪/狙击)"
    )
    """精度类型(1=自动武器,2=手枪/狙击)"""
    damage_rating = fields.CharField(1, default="", description="伤害评级")
    """伤害评级"""
    headshot_rating = fields.CharField(1, default="", description="爆头率评级")
    """爆头率评级"""
    kill_rating = fields.CharField(1, default="", description="击杀评级")
    """击杀评级"""
    spray_accuracy = fields.FloatField(null=True, description="扫射精度")
    """扫射精度"""
    headshot_rate = fields.FloatField(default=0, description="爆头率")
    """爆头率"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_weapon_stats"
        table_description = "CSGO武器统计数据"
        indexes = [  # noqa: RUF012
            ("user_id", "weapon_code", "platform_type", "season_id"),
        ]
