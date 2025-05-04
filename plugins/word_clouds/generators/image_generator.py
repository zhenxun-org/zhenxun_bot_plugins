import os
import random
from io import BytesIO
from typing import Dict, Optional
import numpy as np
from PIL import Image as IMG
from wordcloud import WordCloud
from ..utils.file_utils import ensure_resources
from ..config import WordCloudConfig, base_config
from .base_generator import BaseGenerator
from ..utils.colormap_utils import (
    get_colormap_category,
    get_dark_bg_colormaps,
    get_white_bg_colormaps,
)
from zhenxun.services.log import logger


class ImageWordCloudGenerator(BaseGenerator):
    """图片词云生成器"""

    async def generate(self, word_frequencies: Dict[str, float]) -> Optional[bytes]:
        """生成词云图片

        template_type=1使用蒙版图片，否则使用纯色背景
        背景颜色只能是'white'或'black'，默认蒙版用白色，纯色用黑色
        """
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
        self, bg_color: Optional[str], is_mask_mode: bool
    ) -> tuple[str, str, list]:
        """获取背景颜色和颜色映射，返回(背景颜色,日志前缀,颜色映射列表)"""
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
        """获取WordCloud选项配置"""
        wordcloud_options = {}
        options = base_config.get("WORD_CLOUDS_ADDITIONAL_OPTIONS", {})
        wordcloud_options.update(options if isinstance(options, dict) else {})

        base_options = {
            "font_path": str(WordCloudConfig.get_font_path()),
            "background_color": user_bg,
            "width": base_config.get("WORD_CLOUDS_WIDTH", 1920),
            "height": base_config.get("WORD_CLOUDS_HEIGHT", 1080),
            "colormap": colormap,
            "max_words": base_config.get("WORD_CLOUDS_MAX_WORDS", 2000),
            "min_font_size": base_config.get("WORD_CLOUDS_MIN_FONT_SIZE", 4),
            "max_font_size": 300,
            "relative_scaling": base_config.get("WORD_CLOUDS_RELATIVE_SCALING", 0.3),
            "prefer_horizontal": base_config.get("WORD_CLOUDS_PREFER_HORIZONTAL", 0.7),
            "collocations": base_config.get("WORD_CLOUDS_COLLOCATIONS", True),
        }

        if mask is not None:
            base_options["mask"] = mask

        wordcloud_options.update(base_options)
        return wordcloud_options

    async def _generate_wordcloud_image(
        self, word_frequencies: Dict[str, float], wordcloud_options: dict
    ) -> Optional[bytes]:
        """生成词云图片并返回二进制数据"""
        try:
            wc = WordCloud(**wordcloud_options)
            wc.generate_from_frequencies(word_frequencies)

            bytes_io = BytesIO()
            img = wc.to_image()
            img.save(bytes_io, format="PNG")
            return bytes_io.getvalue()
        except Exception as e:
            logger.error(f"生成词云图片失败: {e}")
            return None

    async def _generate_with_mask(
        self, word_frequencies: Dict[str, float], bg_color: Optional[str] = None
    ) -> Optional[bytes]:
        """使用蒙版图片生成词云"""
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
        self, word_frequencies: Dict[str, float], bg_color: Optional[str] = None
    ) -> Optional[bytes]:
        """生成纯色背景词云"""
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
        """随机获取一个模板图片路径"""
        template_dir = str(WordCloudConfig.get_template_dir())
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
