from typing import Tuple
import numpy as np
from PIL import Image
from wordcloud import WordCloud
from io import BytesIO
from zhenxun.services.log import logger


def adjust_color_brightness(
    r: int,
    g: int,
    b: int,
    is_white_bg: bool,
    white_bg_max_brightness: float = 0.7,
    black_bg_min_brightness: float = 0.3,
) -> Tuple[int, int, int]:
    """
    根据背景颜色调整RGB颜色的亮度
    使用更准确的亮度计算和平滑过渡

    Args:
        r, g, b: RGB颜色值
        is_white_bg: 是否为白色背景
        white_bg_max_brightness: 白底最高亮度阈值
        black_bg_min_brightness: 黑底最低亮度阈值

    Returns:
        调整后的RGB颜色值
    """
    r_float, g_float, b_float = r / 255.0, g / 255.0, b / 255.0

    luminance = 0.2126 * r_float + 0.7152 * g_float + 0.0722 * b_float

    adjustment_factor = 1.0

    if is_white_bg:
        if luminance > white_bg_max_brightness * 0.9:
            adjustment_factor = white_bg_max_brightness / max(luminance, 0.01)
        elif luminance > white_bg_max_brightness * 0.8:
            interp_factor = (luminance - white_bg_max_brightness * 0.8) / (
                white_bg_max_brightness * 0.1
            )
            target_factor = white_bg_max_brightness / max(luminance, 0.01)
            adjustment_factor = 1.0 + interp_factor * (target_factor - 1.0)
    else:
        if luminance < black_bg_min_brightness * 1.1:
            adjustment_factor = black_bg_min_brightness / max(luminance, 0.01)
        elif luminance < black_bg_min_brightness * 1.2:
            interp_factor = (black_bg_min_brightness * 1.2 - luminance) / (
                black_bg_min_brightness * 0.1
            )
            target_factor = black_bg_min_brightness / max(luminance, 0.01)
            adjustment_factor = 1.0 + interp_factor * (target_factor - 1.0)

    if abs(adjustment_factor - 1.0) > 0.01:
        r_new = min(r_float * adjustment_factor, 1.0)
        g_new = min(g_float * adjustment_factor, 1.0)
        b_new = min(b_float * adjustment_factor, 1.0)
        return (int(r_new * 255), int(g_new * 255), int(b_new * 255))
    else:
        return (r, g, b)


class BrightnessAdjustedWordCloud(WordCloud):
    """
    亮度调整的词云类，继承自WordCloud
    在生成图像时对颜色进行亮度调整，确保在不同背景下文字清晰可见
    """

    def __init__(
        self,
        white_bg_max_brightness: float = 0.7,
        black_bg_min_brightness: float = 0.3,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.white_bg_max_brightness = white_bg_max_brightness
        self.black_bg_min_brightness = black_bg_min_brightness
        self.is_white_bg = self.background_color == "white"

    def to_image(self) -> Image.Image:
        """
        重写to_image方法，在生成图像前调整颜色亮度
        使用向量化操作提高性能
        """
        original_image = super().to_image()

        if original_image.mode != "RGBA":
            original_image = original_image.convert("RGBA")

        img_array = np.array(original_image)

        shape = img_array.shape
        logger.debug(f"图像尺寸: {shape[1]}x{shape[0]}")

        result = img_array.copy()

        if self.is_white_bg:
            bg_mask = np.all(img_array[:, :, :3] == 255, axis=2)
            alpha_mask = img_array[:, :, 3] > 0
            mask = np.logical_and(~bg_mask, alpha_mask)
        else:
            bg_mask = np.all(img_array[:, :, :3] == 0, axis=2)
            alpha_mask = img_array[:, :, 3] > 0
            mask = np.logical_and(~bg_mask, alpha_mask)

        rgb = result[:, :, :3].astype(np.float32) / 255.0

        luminance = (
            0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        )

        adjustment_factor = np.ones_like(luminance)

        if self.is_white_bg:
            high_brightness_mask = np.logical_and(
                mask, luminance > self.white_bg_max_brightness * 0.9
            )

            if np.any(high_brightness_mask):
                adjustment_factor[high_brightness_mask] = (
                    self.white_bg_max_brightness
                    / np.maximum(luminance[high_brightness_mask], 0.01)
                )

                transition_mask = np.logical_and(
                    mask,
                    np.logical_and(
                        luminance > self.white_bg_max_brightness * 0.8,
                        luminance <= self.white_bg_max_brightness * 0.9,
                    ),
                )

                if np.any(transition_mask):
                    trans_luminance = luminance[transition_mask]
                    interp_factor = (
                        trans_luminance - self.white_bg_max_brightness * 0.8
                    ) / (self.white_bg_max_brightness * 0.1)
                    target_factor = self.white_bg_max_brightness / np.maximum(
                        trans_luminance, 0.01
                    )
                    adjustment_factor[transition_mask] = 1.0 + interp_factor * (
                        target_factor - 1.0
                    )
        else:
            low_brightness_mask = np.logical_and(
                mask, luminance < self.black_bg_min_brightness * 1.1
            )

            if np.any(low_brightness_mask):
                adjustment_factor[low_brightness_mask] = (
                    self.black_bg_min_brightness
                    / np.maximum(luminance[low_brightness_mask], 0.01)
                )

                transition_mask = np.logical_and(
                    mask,
                    np.logical_and(
                        luminance >= self.black_bg_min_brightness * 1.1,
                        luminance < self.black_bg_min_brightness * 1.2,
                    ),
                )

                if np.any(transition_mask):
                    trans_luminance = luminance[transition_mask]
                    interp_factor = (
                        self.black_bg_min_brightness * 1.2 - trans_luminance
                    ) / (self.black_bg_min_brightness * 0.1)
                    target_factor = self.black_bg_min_brightness / np.maximum(
                        trans_luminance, 0.01
                    )
                    adjustment_factor[transition_mask] = 1.0 + interp_factor * (
                        target_factor - 1.0
                    )

        needs_adjustment = np.abs(adjustment_factor - 1.0) > 0.01
        if np.any(needs_adjustment):
            adjust_mask = np.logical_and(mask, needs_adjustment)

            factor_3d = np.expand_dims(adjustment_factor, axis=2)
            factor_3d = np.repeat(factor_3d, 3, axis=2)

            rgb[adjust_mask] *= factor_3d[adjust_mask]

            rgb = np.clip(rgb, 0, 1)

            result[:, :, :3] = (rgb * 255).astype(np.uint8)

        adjusted_image = Image.fromarray(result)
        return adjusted_image


def optimize_wordcloud_image(
    image_bytes: bytes,
    is_white_bg: bool,
    white_bg_max_brightness: float = 0.7,
    black_bg_min_brightness: float = 0.3,
) -> bytes:
    """
    优化词云图像的亮度 - 使用NumPy向量化操作提高性能
    针对中等分辨率图像进行了优化

    Args:
        image_bytes: 原始词云图像的二进制数据
        is_white_bg: 是否为白色背景
        white_bg_max_brightness: 白底最高亮度阈值
        black_bg_min_brightness: 黑底最低亮度阈值

    Returns:
        优化后的词云图像的二进制数据
    """
    try:
        img = Image.open(BytesIO(image_bytes))

        logger.debug(f"图像大小: {img.size}, 图像模式: {img.mode}")

        if img.mode != "RGBA":
            logger.debug("图像不是RGBA模式，尝试转换为RGBA模式")
            try:
                img = img.convert("RGBA")
                logger.debug(f"转换后图像模式: {img.mode}")
            except Exception as e:
                logger.warning(f"转换图像为RGBA模式失败: {e}")
                return image_bytes

        img_array = np.array(img)

        if len(img_array.shape) < 3 or img_array.shape[2] != 4:
            logger.warning(f"图像维度不正确: {img_array.shape}，跳过亮度优化")
            return image_bytes

        height, width, _ = img_array.shape
        logger.debug(f"图像尺寸: {width}x{height}")

        result = img_array.copy()

        if is_white_bg:
            bg_mask = np.all(img_array[:, :, :3] == 255, axis=2)
            alpha_mask = img_array[:, :, 3] > 0
            mask = np.logical_and(~bg_mask, alpha_mask)
        else:
            bg_mask = np.all(img_array[:, :, :3] == 0, axis=2)
            alpha_mask = img_array[:, :, 3] > 0
            mask = np.logical_and(~bg_mask, alpha_mask)

        pixel_count = np.sum(mask)
        logger.debug(f"找到 {pixel_count} 个需要处理的像素")

        if pixel_count == 0:
            logger.debug("没有需要处理的像素，跳过亮度优化")
            return image_bytes

        rgb = result[:, :, :3].astype(np.float32) / 255.0

        luminance = (
            0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        )

        adjustment_factor = np.ones_like(luminance)

        if is_white_bg:
            high_brightness_mask = np.logical_and(
                mask, luminance > white_bg_max_brightness * 0.9
            )

            high_count = np.sum(high_brightness_mask)
            logger.debug(f"找到 {high_count} 个亮度过高的像素需要调整")

            if high_count > 0:
                transition_mask = np.logical_and(
                    mask,
                    np.logical_and(
                        luminance > white_bg_max_brightness * 0.8,
                        luminance <= white_bg_max_brightness * 0.9,
                    ),
                )

                adjustment_factor[high_brightness_mask] = (
                    white_bg_max_brightness
                    / np.maximum(luminance[high_brightness_mask], 0.01)
                )

                if np.any(transition_mask):
                    trans_luminance = luminance[transition_mask]
                    interp_factor = (
                        trans_luminance - white_bg_max_brightness * 0.8
                    ) / (white_bg_max_brightness * 0.1)
                    target_factor = white_bg_max_brightness / np.maximum(
                        trans_luminance, 0.01
                    )
                    adjustment_factor[transition_mask] = 1.0 + interp_factor * (
                        target_factor - 1.0
                    )
        else:
            low_brightness_mask = np.logical_and(
                mask, luminance < black_bg_min_brightness * 1.1
            )

            low_count = np.sum(low_brightness_mask)
            logger.debug(f"找到 {low_count} 个亮度过低的像素需要调整")

            if low_count > 0:
                transition_mask = np.logical_and(
                    mask,
                    np.logical_and(
                        luminance >= black_bg_min_brightness * 1.1,
                        luminance < black_bg_min_brightness * 1.2,
                    ),
                )

                adjustment_factor[low_brightness_mask] = (
                    black_bg_min_brightness
                    / np.maximum(luminance[low_brightness_mask], 0.01)
                )

                if np.any(transition_mask):
                    trans_luminance = luminance[transition_mask]
                    interp_factor = (
                        black_bg_min_brightness * 1.2 - trans_luminance
                    ) / (black_bg_min_brightness * 0.1)
                    target_factor = black_bg_min_brightness / np.maximum(
                        trans_luminance, 0.01
                    )
                    adjustment_factor[transition_mask] = 1.0 + interp_factor * (
                        target_factor - 1.0
                    )

        needs_adjustment = np.abs(adjustment_factor - 1.0) > 0.01
        if np.any(needs_adjustment):
            adjust_mask = np.logical_and(mask, needs_adjustment)

            factor_3d = np.expand_dims(adjustment_factor, axis=2)
            factor_3d = np.repeat(factor_3d, 3, axis=2)

            rgb[adjust_mask] *= factor_3d[adjust_mask]

            rgb = np.clip(rgb, 0, 1)

            result[:, :, :3] = (rgb * 255).astype(np.uint8)

            logger.debug(f"已调整 {np.sum(adjust_mask)} 个像素的亮度")
        else:
            logger.debug("没有像素需要调整亮度")

        adjusted_image = Image.fromarray(result)

        bytes_io = BytesIO()
        adjusted_image.save(bytes_io, format="PNG")
        return bytes_io.getvalue()

    except Exception as e:
        logger.error(f"优化词云图像亮度失败: {e}", exc_info=True)
        return image_bytes
