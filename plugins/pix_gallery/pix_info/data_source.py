import asyncio

from tortoise.expressions import Q

from zhenxun.utils._build_image import BuildImage
from zhenxun.utils._image_template import ImageTemplate

from ..config import KwType
from ..models.pix_gallery import PixGallery
from ..models.pix_keyword import PixKeyword


class InfoManage:
    @classmethod
    async def get_seek_info(cls, seek_type: KwType | None) -> BuildImage:
        """获取收录数据

        参数:
            seek_type: 类型

        返回:
            BuildImage: 图片
        """
        query = PixKeyword
        if seek_type:
            query = query.filter(kw_type=seek_type)
        result = await query.annotate().values(
            "id", "content", "kw_type", "handle_type", "seek_count"
        )
        column_name = ["ID", "内容", "类型", "处理方式", "收录次数"]
        data_list = [
            [r["id"], r["content"], r["kw_type"], r["handle_type"], r["seek_count"]]
            for r in result
        ]
        return await ImageTemplate.table_page("收录统计", None, column_name, data_list)

    @classmethod
    async def get_pix_gallery(cls, tags: list[str] | None) -> BuildImage:
        """查看pix图库

        参数:
            tags: tags列表

        返回:
            BuildImage: 图片
        """
        query = PixGallery.filter(block_level__isnull=True)
        if tags:
            for tag in tags:
                query = query.filter(
                    Q(tags__icontains=tag)
                    | Q(author__icontains=tag)
                    | Q(pid__icontains=tag)
                    | Q(uid__icontains=tag)
                    | Q(title__icontains=tag)
                )
        result = await asyncio.gather(
            *[
                query.annotate().count(),
                query.filter(nsfw_tag__not=2).annotate().count(),
                query.filter(nsfw_tag=2).annotate().count(),
                query.filter(is_ai=True).annotate().count(),
            ]
        )
        column_name = ["类型", "数量"]
        data_list = [
            ["总数", result[0]],
            ["普通", result[1]],
            ["R18", result[2]],
            ["AI", result[3]],
        ]
        return await ImageTemplate.table_page("图库统计", None, column_name, data_list)
