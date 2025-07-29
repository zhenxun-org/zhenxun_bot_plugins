from typing import TYPE_CHECKING

from tortoise import fields

from zhenxun.services.db_context import Model

if TYPE_CHECKING:
    from .csgo_map_rate import CsgoMapRate
    from .csgo_official_stats import CsgoOfficialStats
    from .csgo_perfect_stats import CsgoPerfectStats
    from .csgo_video import CsgoVideo


class CsgoUser(Model):
    """CSGO用户基础信息表"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255, null=True, unique=True, description="用户id")
    """用户id"""
    steam_id = fields.CharField(255, unique=True, description="steamid")
    """steamid"""
    perfect_name = fields.CharField(50, null=True, description="玩家昵称")
    """完美世界用户名称"""
    perfect_avatar_url = fields.TextField(null=True, description="完美世界头像URL")
    """完美世界头像URL"""
    official_name = fields.CharField(50, null=True, description="官方匹配用户名称")
    """官方匹配用户名称"""
    official_avatar_url = fields.TextField(null=True, description="官方匹配头像URL")
    """官方匹配头像URL"""
    friend_code = fields.CharField(50, null=True, description="好友代码")
    """好友代码"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    # 关系字段
    perfect_stats: fields.ReverseRelation["CsgoPerfectStats"]
    official_stats: fields.ReverseRelation["CsgoOfficialStats"]
    videos: fields.ReverseRelation["CsgoVideo"]
    map_rates: fields.ReverseRelation["CsgoMapRate"]

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_users"
        table_description = "CSGO用户基础信息表"
        indexes = [("user_id",), ("steam_id",)]  # noqa: RUF012
