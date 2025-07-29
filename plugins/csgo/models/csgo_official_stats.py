from typing import TYPE_CHECKING

from tortoise import fields

from zhenxun.services.db_context import Model

from .csgo_map_stats import CsgoMapStats
from .csgo_rating_history import CsgoRatingHistory
from .csgo_weapon_stats import CsgoWeaponStats

if TYPE_CHECKING:
    from .csgo_map_rate import CsgoMapRate


class CsgoOfficialStats(Model):
    """CSGO玩家官方匹配统计数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="official_stats")
    """关联用户"""
    season_id = fields.CharField(10, description="赛季ID")
    """赛季ID"""
    total_matches = fields.IntField(default=0, description="总比赛场次")
    """总比赛场次"""
    kd_ratio = fields.FloatField(default=0, description="K/D比率")
    """K/D比率"""
    win_rate = fields.FloatField(default=0, description="胜率")
    """胜率"""
    rating = fields.FloatField(default=0, description="综合评分")
    """综合评分"""
    total_kills = fields.IntField(default=0, description="总击杀数")
    """总击杀数"""
    total_deaths = fields.IntField(default=0, description="总死亡数")
    """总死亡数"""
    total_assists = fields.IntField(default=0, description="总助攻数")
    """总助攻数"""
    rws = fields.FloatField(default=0, description="RWS评分")
    """RWS评分"""
    adr = fields.FloatField(default=0, description="场均伤害")
    """场均伤害"""
    kast = fields.FloatField(default=0, description="KAST指标(百分比)")
    """KAST指标(百分比)"""
    headshot_ratio = fields.FloatField(default=0, description="爆头率")
    """爆头率"""
    entry_kill_ratio = fields.FloatField(default=0, description="首杀成功率")
    """首杀成功率"""
    awp_kill_ratio = fields.FloatField(default=0, description="AWP击杀占比")
    """AWP击杀占比"""
    flash_success_ratio = fields.FloatField(default=0, description="闪光弹成功率")
    """闪光弹成功率"""
    entry_kill_avg = fields.FloatField(default=0, description="平均首杀数")
    """平均首杀数"""
    triple_kills = fields.IntField(default=0, description="三杀次数")
    """三杀次数"""
    quad_kills = fields.IntField(default=0, description="四杀次数")
    """四杀次数"""
    penta_kills = fields.IntField(default=0, description="五杀次数")
    """五杀次数"""
    multi_kills = fields.IntField(default=0, description="多杀总数")
    """多杀总数"""
    vs3_wins = fields.IntField(default=0, description="1v3胜利次数")
    """1v3胜利次数"""
    vs4_wins = fields.IntField(default=0, description="1v4胜利次数")
    """1v4胜利次数"""
    vs5_wins = fields.IntField(default=0, description="1v5胜利次数")
    """1v5胜利次数"""
    ending_wins = fields.IntField(default=0, description="残局胜利次数")
    """残局胜利次数"""
    history_win_count = fields.IntField(default=0, description="历史胜利总场次")
    """历史胜利总场次"""
    game_hours = fields.IntField(default=0, description="游戏时长(小时)")
    """游戏时长(小时)"""
    auth_stats = fields.IntField(default=0, description="认证状态")
    """认证状态"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    # 关系字段
    map_stats: fields.ReverseRelation["CsgoMapStats"]
    map_rates: fields.ReverseRelation["CsgoMapRate"]
    weapon_stats: fields.ReverseRelation["CsgoWeaponStats"]
    rating_history: fields.ReverseRelation["CsgoRatingHistory"]

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_official_stats"
        table_description = "CSGO玩家官方匹配统计数据"
        indexes = [("user_id",), ("season_id",)]  # noqa: RUF012
