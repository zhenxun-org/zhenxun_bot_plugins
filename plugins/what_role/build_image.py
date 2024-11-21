from zhenxun.utils._build_image import BuildImage
from zhenxun.utils.image_utils import text2image


class ConstructImage:
    def __init__(
        self, model: str, image: BuildImage, result_list: list[list[BuildImage | str]]
    ):
        self.model = model
        self.image = image
        self.result_list = result_list

    async def construct_title_image(self, bottom_width: int) -> BuildImage:
        """构造头部图片

        返回:
            BuildImage: 图片
        """
        model_str = f"模型: {self.model}"
        width, height = self.image.size
        max_int = max(width, height)
        ra = min(1500, bottom_width) if width < bottom_width else 1500
        if max_int < ra:
            ratio = ra / max_int
            await self.image.resize(ratio)
            width, height = self.image.size
        font_width, _ = BuildImage.get_text_size(model_str)
        width = max(width, font_width)
        inner = BuildImage(width + 40, height + 70, "#FFFBFC")
        await inner.circle_corner()
        await self.image.circle_corner()
        await inner.paste(self.image, (20, 10))
        await inner.text(
            (30, height + 10),
            model_str,
            font="HYWenHei-85W.ttf",
            font_size=50,
        )
        background = BuildImage(width + 58, height + 90, "#F7A0B5")
        await background.circle_corner()
        await background.paste(inner, (8, 10))
        return background

    async def construct_result_image(
        self, image: BuildImage, result: list[str]
    ) -> BuildImage:
        """构造出处图片

        参数:
            image: 识别头像
            result: 识别信息

        返回:
            BuildImage: 图片
        """
        image_border = BuildImage(image.width + 10, image.height + 10, "#F7A0B5")
        await image_border.paste(image, (2, 2), "center")
        img_list = []
        for r in result:
            img: BuildImage = await text2image(r, font_size=40, color="#FFFBFC")
            img_list.append(img)
        b_img = await BuildImage.auto_paste(img_list, 1, 50, 20, color="#FFFBFC")
        await b_img.circle_corner(point_list=["lb", "rb"])
        bottom_background = BuildImage(b_img.width + 10, b_img.height + 5, "#F7A0B5")
        await bottom_background.paste(b_img, (5, 0))
        top_background = BuildImage(
            bottom_background.width - 10, image_border.height + 40, "#FFFBFC"
        )
        await top_background.paste(image_border, center_type="center")
        background = BuildImage(
            bottom_background.width,
            top_background.height + bottom_background.height,
            "#F7A0B5",
        )
        await top_background.circle_corner(point_list=["lt", "rt"])
        await bottom_background.circle_corner(point_list=["lb", "rb"])
        await background.circle_corner()
        await background.paste(top_background, (5, 5))
        await background.paste(bottom_background, (0, top_background.height))
        return background

    async def to_image(self) -> BuildImage:
        """构造图片

        返回:
            BuildImage: 图片
        """
        image_list = []
        for r in self.result_list:
            await r[0].resize(width=400, height=400)  # type: ignore
            image_list.append(await self.construct_result_image(r[0], r[1:]))  # type: ignore
        info_image = await BuildImage.auto_paste(
            image_list, len(image_list), padding=10
        )
        await info_image.circle_corner()
        title_image = await self.construct_title_image(info_image.width)
        width = max(title_image.width, info_image.width) + 20
        result = BuildImage(
            width,
            title_image.height + info_image.height + 250,
            "#FFFBFC",
            font="CJGaoDeGuo.otf",
            font_size=140,
        )
        await result.text((0, 50), "角色识别总览", "#F7A0B5", center_type="width")
        await result.paste(title_image, (0, 200), center_type="width")
        await result.paste(
            info_image, (0, title_image.height + 250), center_type="width"
        )
        await result.circle_corner()
        background = BuildImage(result.width + 60, result.height + 60, "#F7A0B5")
        await background.paste(result, (30, 30))
        w, h = background.size
        if w > 2000 or h > 2000:
            await background.resize(0.5)
        return background
