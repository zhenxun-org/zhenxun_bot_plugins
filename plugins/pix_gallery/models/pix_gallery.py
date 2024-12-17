from tortoise import fields

from zhenxun.services.db_context import Model


class PixGallery(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    pid = fields.CharField(255)
    """pid"""
    uid = fields.CharField(255)
    """uid"""
    author = fields.CharField(255)
    """作者"""
    title = fields.CharField(255)
    """标题"""
    width = fields.IntField()
    """宽度"""
    height = fields.IntField()
    """高度"""
    sanity_level = fields.IntField()
    """安全等级"""
    x_restrict = fields.IntField()
    """x等级"""
    total_view = fields.IntField()
    """pixiv查看数"""
    total_bookmarks = fields.IntField()
    """收藏数"""
    illust_ai_type = fields.IntField()
    """插画ai类型"""
    tags = fields.TextField()
    """tags"""
    image_urls: dict[str, str] = fields.JSONField()  # type: ignore
    """pixiv url链接"""
    img_p = fields.CharField(255)
    """图片pN"""
    nsfw_tag = fields.IntField()
    """nsfw标签,-1=未标记, 0=safe, 1=setu. 2=r18"""
    is_ai = fields.BooleanField(default=False)
    """是否ai"""
    is_multiple = fields.BooleanField(default=False)
    """是否多图"""
    block_level = fields.IntField(null=True)
    """block等级 1: 可看 2: 不可看"""
    star = fields.IntField(default=0)
    """star数量"""
    ratio = fields.FloatField(default=0)
    """宽高比"""
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    """创建时间"""

    class Meta:  # type: ignore
        table = "pix_gallery1"
        table_description = "pix图库数据表"
        unique_together = ("pid", "img_p")
