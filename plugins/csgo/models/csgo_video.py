from tortoise import fields

from zhenxun.services.db_context import Model


class CsgoVideo(Model):
    """CSGO玩家视频数据"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user = fields.ForeignKeyField("models.CsgoUser", related_name="videos")
    """关联用户"""
    platform_type = fields.IntField(
        description="平台类型：1-完美世界，2-官方匹配", default=1
    )
    """平台类型：1-完美世界，2-官方匹配"""
    video_id = fields.CharField(50, description="视频ID(vid)")
    """视频ID(vid)"""
    match_id = fields.CharField(50, description="比赛ID")
    """比赛ID"""
    title = fields.CharField(255, null=True, description="视频标题")
    """视频标题"""
    short_title = fields.CharField(100, null=True, description="短标题")
    """短标题"""
    match_round = fields.IntField(description="比赛回合数")
    """比赛回合数"""
    match_time = fields.DatetimeField(description="比赛时间")
    """比赛时间"""
    map_name = fields.CharField(50, description="地图名称")
    """地图名称"""
    map_url = fields.TextField(description="地图图片URL")
    """地图图片URL"""
    kill_count = fields.IntField(default=0, description="击杀数")
    """击杀数"""
    versus_count = fields.IntField(default=0, description="对阵人数(如1v3)")
    """对阵人数(如1v3)"""
    video_status = fields.IntField(default=0, description="视频状态码")
    """视频状态码"""
    video_reason = fields.CharField(255, null=True, description="视频状态原因")
    """视频状态原因"""
    review_status = fields.IntField(default=0, description="审核状态")
    """审核状态"""
    review_reason = fields.CharField(255, null=True, description="审核原因")
    """审核原因"""
    platform = fields.IntField(default=0, description="平台标识")
    """平台标识"""
    video_type = fields.IntField(default=0, description="视频类型")
    """视频类型"""
    is_weekend_league = fields.BooleanField(default=False, description="是否周末联赛")
    """是否周末联赛"""
    is_album = fields.BooleanField(default=False, description="是否合集")
    """是否合集"""
    is_video_cut = fields.BooleanField(default=False, description="是否剪辑版")
    """是否剪辑版"""
    width = fields.IntField(default=0, description="视频宽度")
    """视频宽度"""
    height = fields.IntField(default=0, description="视频高度")
    """视频高度"""
    size = fields.BigIntField(default=0, description="文件大小(字节)")
    """文件大小(字节)"""
    duration = fields.CharField(20, description="时长(秒)")
    """时长(秒)"""
    format = fields.CharField(20, description="视频格式")
    """视频格式"""
    definition = fields.CharField(20, description="清晰度标识")
    """清晰度标识"""
    play_url = fields.TextField(description="播放地址URL")
    """播放地址URL"""
    local_path = fields.TextField(null=True, description="本地缓存路径")
    """本地缓存路径"""
    is_cached = fields.BooleanField(default=False, description="是否已缓存到本地")
    """是否已缓存到本地"""
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    """更新时间"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "csgo_videos"
        table_description = "CSGO玩家视频数据"
        indexes = [  # noqa: RUF012
            ("video_id",),
            ("match_id",),
            ("user_id", "video_id"),
        ]
