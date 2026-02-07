from io import BytesIO
import os
import random

from nonebot.utils import run_sync
import numpy as np
from PIL import Image as IMG
from wordcloud import WordCloud

from zhenxun.services.log import logger

from .config import WordCloudConfig, base_config
from .utils.brightness_utils import optimize_wordcloud_image
from .utils.colormap_utils import (
    get_colormap_category,
    get_dark_bg_colormaps,
    get_white_bg_colormaps,
)
from .utils.file_utils import ensure_resources


class WordCloudGenerator:
    """图片词云生成器"""

    async def generate(self, word_frequencies: dict[str, float]) -> bytes | None:
        """生成词云图片"""
        if not await ensure_resources():
            return None

        bg_color = base_config.get("WORD_CLOUDS_BACKGROUND_COLOR", None)
        if bg_color and bg_color not in ["white", "black"]:
            bg_color = None
            logger.warning(
                "WORD_CLOUDS_BACKGROUND_COLOR配置无效，只能是'white'或'black'，将使用默认值"
            )

        template_type = base_config.get("WORD_CLOUDS_TEMPLATE", 1)
        if template_type == 1:
            return await self._generate_with_mask(word_frequencies, bg_color)
        else:
            return await self._generate_plain(word_frequencies, bg_color)

    async def _get_background_and_colormap(
        self, bg_color: str | None, is_mask_mode: bool
    ) -> tuple[str, str, list]:
        """获取背景颜色和颜色映射"""
        log_prefix = "使用蒙版图片生成词云" if is_mask_mode else "生成纯色背景词云"

        if bg_color and bg_color in ["white", "black"]:
            user_bg = bg_color
            logger.debug(f"{log_prefix}，背景颜色设置为: {user_bg}")
        else:
            user_bg = "white" if is_mask_mode else "black"
            logger.debug(f"{log_prefix}，使用默认{user_bg}色背景")

        is_white_bg = user_bg == "white"

        if is_white_bg:
            colormaps = base_config.get("WORD_CLOUDS_COLORMAP_WHITE_BG", [])
            if not colormaps:
                colormaps = get_white_bg_colormaps()
            logger.debug("使用白色背景专用的colormap列表")
        else:
            colormaps = base_config.get("WORD_CLOUDS_COLORMAP_BLACK_BG", [])
            if not colormaps:
                colormaps = get_dark_bg_colormaps()
            logger.debug("使用黑色背景专用的colormap列表")

        return user_bg, log_prefix, colormaps

    async def _get_wordcloud_options(
        self, user_bg: str, colormap: str, mask=None
    ) -> dict:
        """获取WordCloud选项"""
        wordcloud_options = {}
        options = base_config.get("WORD_CLOUDS_ADDITIONAL_OPTIONS", {})
        wordcloud_options.update(options if isinstance(options, dict) else {})

        resolution_factor = WordCloudConfig.RESOLUTION_FACTOR

        base_width = base_config.get("WORD_CLOUDS_WIDTH", 1920)
        base_height = base_config.get("WORD_CLOUDS_HEIGHT", 1080)
        high_res_width = int(base_width * resolution_factor)
        high_res_height = int(base_height * resolution_factor)

        logger.debug(
            f"使用高分辨率生成词云: {high_res_width}x{high_res_height} "
            f"(倍数: {resolution_factor})"
        )

        base_options = {
            "font_path": str(WordCloudConfig.get_font_path()),
            "background_color": user_bg,
            "width": high_res_width,
            "height": high_res_height,
            "colormap": colormap,
            "max_words": base_config.get("WORD_CLOUDS_MAX_WORDS", 2000),
            "min_font_size": base_config.get("WORD_CLOUDS_MIN_FONT_SIZE", 4)
            * resolution_factor,
            "max_font_size": 300 * resolution_factor,
            "relative_scaling": base_config.get("WORD_CLOUDS_RELATIVE_SCALING", 0.3),
            "prefer_horizontal": base_config.get("WORD_CLOUDS_PREFER_HORIZONTAL", 0.7),
            "collocations": base_config.get("WORD_CLOUDS_COLLOCATIONS", True),
            "mode": "RGBA",
        }

        if mask is not None:
            base_options["mask"] = mask

        wordcloud_options.update(base_options)
        return wordcloud_options

    async def _generate_wordcloud_image(
        self, word_frequencies: dict[str, float], wordcloud_options: dict
    ) -> bytes | None:
        """生成词云图片"""
        try:
            bg_color = wordcloud_options.get("background_color", "black")
            is_white_bg = bg_color == "white"

            white_bg_max_brightness = base_config.get(
                "WORD_CLOUDS_WHITE_BG_MAX_BRIGHTNESS", 0.7
            )
            black_bg_min_brightness = base_config.get(
                "WORD_CLOUDS_BLACK_BG_MIN_BRIGHTNESS", 0.3
            )
            logger.debug(
                f"亮度阈值配置: 白底最高亮度={white_bg_max_brightness}, 黑底最低亮度={black_bg_min_brightness}"
            )

            resolution_factor = WordCloudConfig.RESOLUTION_FACTOR
            base_width = base_config.get("WORD_CLOUDS_WIDTH", 1920)
            base_height = base_config.get("WORD_CLOUDS_HEIGHT", 1080)
            target_width = base_width
            target_height = base_height

            return await self._generate_wordcloud_image_sync(
                word_frequencies,
                wordcloud_options,
                is_white_bg,
                white_bg_max_brightness,
                black_bg_min_brightness,
                resolution_factor,
                target_width,
                target_height,
            )

        except Exception as e:
            logger.error(f"生成词云图片失败: {e}")
            return None

    @run_sync
    def _generate_wordcloud_image_sync(
        self,
        word_frequencies: dict[str, float],
        wordcloud_options: dict,
        is_white_bg: bool,
        white_bg_max_brightness: float,
        black_bg_min_brightness: float,
        resolution_factor: float,
        target_width: int,
        target_height: int,
    ) -> bytes | None:
        """在线程池中同步生成词云图片"""
        try:
            logger.debug("生成高分辨率词云...")
            wc = WordCloud(**wordcloud_options)
            wc.generate_from_frequencies(word_frequencies)

            img = wc.to_image()

            image_dpi = WordCloudConfig.IMAGE_DPI
            image_quality = WordCloudConfig.IMAGE_QUALITY

            if img.mode != "RGBA":
                logger.debug("转换图像为RGBA模式以支持亮度优化")
                img = img.convert("RGBA")

            bytes_io = BytesIO()
            img.save(
                bytes_io,
                format="PNG",
                dpi=(image_dpi, image_dpi),
                quality=image_quality,
                optimize=True,
            )
            high_res_image_bytes = bytes_io.getvalue()

            logger.debug(f"优化词云图像亮度，背景: {'白色' if is_white_bg else '黑色'}")
            brightness_optimized_bytes = optimize_wordcloud_image(
                high_res_image_bytes,
                is_white_bg,
                white_bg_max_brightness,
                black_bg_min_brightness,
            )

            if resolution_factor != 1.0:
                logger.debug(f"调整图像尺寸至目标大小: {target_width}x{target_height}")
                from PIL import Image

                img = Image.open(BytesIO(brightness_optimized_bytes))
                img = img.resize(
                    (target_width, target_height), Image.Resampling.LANCZOS
                )

                if img.mode != "RGBA":
                    logger.debug("调整大小后转换图像为RGBA模式")
                    img = img.convert("RGBA")

                bytes_io = BytesIO()
                img.save(
                    bytes_io,
                    format="PNG",
                    dpi=(image_dpi, image_dpi),
                    quality=image_quality,
                    optimize=True,
                )
                final_bytes = bytes_io.getvalue()
            else:
                final_bytes = brightness_optimized_bytes

            logger.debug(
                f"词云生成完成，最终图像质量: DPI={image_dpi}, 质量={image_quality}"
            )
            return final_bytes
        except Exception as e:
            logger.error(f"生成词云图片失败: {e}")
            return None

    async def _generate_with_mask(
        self, word_frequencies: dict[str, float], bg_color: str | None = None
    ) -> bytes | None:
        """使用蒙版生成词云"""
        template_path = self._get_random_template()
        mask = np.array(IMG.open(template_path))

        user_bg, log_prefix, colormaps = await self._get_background_and_colormap(
            bg_color, is_mask_mode=True
        )

        colormap = random.choice(colormaps)

        colormap_category = get_colormap_category(colormap)
        logger.debug(
            f"{log_prefix}，随机选择的colormap: {colormap} (类别: {colormap_category})"
        )

        wordcloud_options = await self._get_wordcloud_options(user_bg, colormap, mask)

        return await self._generate_wordcloud_image(word_frequencies, wordcloud_options)

    async def _generate_plain(
        self, word_frequencies: dict[str, float], bg_color: str | None = None
    ) -> bytes | None:
        """生成纯色词云"""
        user_bg, log_prefix, colormaps = await self._get_background_and_colormap(
            bg_color, is_mask_mode=False
        )

        colormap = random.choice(colormaps)

        colormap_category = get_colormap_category(colormap)
        logger.debug(
            f"{log_prefix}，随机选择的colormap: {colormap} (类别: {colormap_category})"
        )

        wordcloud_options = await self._get_wordcloud_options(user_bg, colormap)

        return await self._generate_wordcloud_image(word_frequencies, wordcloud_options)

    def _get_random_template(self) -> str:
        """获取随机模板路径"""
        template_dir = WordCloudConfig.get_template_dir()
        if not os.path.exists(template_dir) or not os.listdir(template_dir):
            logger.warning(f"词云模板目录 '{template_dir}' 为空或不存在，使用默认模板")
            return str(template_dir / "default.png")
        path_dir = os.listdir(template_dir)
        valid_files = [
            f for f in path_dir if os.path.isfile(os.path.join(template_dir, f))
        ]
        if not valid_files:
            logger.warning(
                f"词云模板目录 '{template_dir}' 中没有有效的图片文件，使用默认模板"
            )
            return str(template_dir / "default.png")
        path = random.choice(valid_files)
        return f"{template_dir}/{path}"
