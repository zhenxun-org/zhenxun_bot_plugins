from typing import TYPE_CHECKING

from tortoise import fields

from zhenxun.services.db_context import Model

from .csgo_map_stats import CsgoMapStats
from .csgo_match_record import CsgoMatchRecord
from .csgo_rating_history import CsgoRatingHistory
from .csgo_weapon_efficiency import CsgoWeaponEfficiency
from .csgo_weapon_stats import CsgoWeaponStats

if TYPE_CHECKING:
    from .csgo_map_rate import CsgoMapRate


class CsgoPerfectStats(Model):
    """CSGO玩家完美世界平台统计数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="perfect_stats")
    """关联用户"""
    season_id = fields.CharField(10, description="赛季ID")
    """赛季ID"""
    pvp_rank = fields.IntField(default=0, description="PVP排名")
    """PVP排名"""
    total_matches = fields.IntField(default=0, description="总比赛场次")
    """总比赛场次"""
    kd_ratio = fields.FloatField(default=0, description="K/D比率")
    """K/D比率"""
    win_rate = fields.FloatField(default=0, description="胜率")
    """胜率"""
    rating = fields.FloatField(default=0, description="综合评分")
    """综合评分"""
    pw_rating = fields.FloatField(default=0, description="完美世界评分")
    """完美世界评分"""
    hit_rate = fields.FloatField(default=0, description="命中率")
    """命中率"""
    common_rating = fields.FloatField(default=0, description="常规模式评分")
    """常规模式评分"""
    total_kills = fields.IntField(default=0, description="总击杀数")
    """总击杀数"""
    total_deaths = fields.IntField(default=0, description="总死亡数")
    """总死亡数"""
    total_assists = fields.IntField(default=0, description="总助攻数")
    """总助攻数"""
    mvp_count = fields.IntField(default=0, description="MVP次数")
    """MVP次数"""
    game_score = fields.IntField(default=0, description="游戏分数")
    """游戏分数"""
    rws = fields.FloatField(default=0, description="RWS评分")
    """RWS评分"""
    adr = fields.FloatField(default=0, description="场均伤害")
    """场均伤害"""
    headshot_ratio = fields.FloatField(default=0, description="爆头率")
    """爆头率"""
    entry_kill_ratio = fields.FloatField(default=0, description="首杀成功率")
    """首杀成功率"""
    double_kills = fields.IntField(default=0, description="双杀次数")
    """双杀次数"""
    triple_kills = fields.IntField(default=0, description="三杀次数")
    """三杀次数"""
    quad_kills = fields.IntField(default=0, description="四杀次数")
    """四杀次数"""
    penta_kills = fields.IntField(default=0, description="五杀次数")
    """五杀次数"""
    multi_kills = fields.IntField(default=0, description="多杀总数")
    """多杀总数"""
    vs1_wins = fields.IntField(default=0, description="1v1胜利次数")
    """1v1胜利次数"""
    vs2_wins = fields.IntField(default=0, description="1v2胜利次数")
    """1v2胜利次数"""
    vs3_wins = fields.IntField(default=0, description="1v3胜利次数")
    """1v3胜利次数"""
    vs4_wins = fields.IntField(default=0, description="1v4胜利次数")
    """1v4胜利次数"""
    vs5_wins = fields.IntField(default=0, description="1v5胜利次数")
    """1v5胜利次数"""
    ending_wins = fields.IntField(default=0, description="残局胜利次数")
    """残局胜利次数"""
    shot_rating = fields.FloatField(default=0, description="射击评分")
    """射击评分"""
    victory_rating = fields.FloatField(default=0, description="胜利评分")
    """胜利评分"""
    breach_rating = fields.FloatField(default=0, description="突破评分")
    """突破评分"""
    snipe_rating = fields.FloatField(default=0, description="狙击评分")
    """狙击评分"""
    prop_rating = fields.FloatField(default=0, description="道具评分")
    """道具评分"""
    vs1_win_rate = fields.FloatField(default=0, description="1v1胜率")
    """1v1胜率"""
    summary = fields.CharField(255, default="", description="玩家评价")
    """玩家评价"""
    avg_weapon_efficiency = fields.FloatField(default=0, description="平均武器效率")
    """平均武器效率"""
    pvp_score = fields.IntField(default=0, description="PVP分数")
    """PVP分数"""
    stars = fields.IntField(default=0, description="星级评价")
    """星级评价"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    # 关系字段
    map_stats: fields.ReverseRelation["CsgoMapStats"]
    map_rates: fields.ReverseRelation["CsgoMapRate"]
    weapon_stats: fields.ReverseRelation["CsgoWeaponStats"]
    rating_history: fields.ReverseRelation["CsgoRatingHistory"]
    match_records: fields.ReverseRelation["CsgoMatchRecord"]
    weapon_efficiency: fields.ReverseRelation["CsgoWeaponEfficiency"]

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_perfect_stats"
        table_description = "CSGO玩家完美世界平台统计数据"
        indexes = [("user_id",), ("season_id",)]  # noqa: RUF012
