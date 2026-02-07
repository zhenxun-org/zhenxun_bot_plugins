import asyncio
from pathlib import Path

from nonebot_plugin_htmlrender import get_browser

from zhenxun.services.log import logger
from zhenxun.utils.image_utils import BuildImage

from ..config import (
    SCREENSHOT_ELEMENT_ARTICLE,
    SCREENSHOT_ELEMENT_OPUS,
    SCREENSHOT_TIMEOUT,
)
from ..utils.exceptions import ScreenshotError


class ScreenshotService:
    """截图服务"""

    @staticmethod
    async def _resize_image(path: Path, scale: float = 0.8) -> None:
        """调整图像大小"""
        try:
            img = BuildImage.open(path)

            orig_width, orig_height = img.size
            new_width = int(orig_width * scale)
            await img.resize(width=new_width)
            await img.save(path)
            logger.debug(
                f"调整截图大小: {path.name}, 宽度从 {orig_width} 调整为 {new_width}",
                "B站解析",
            )
        except Exception as e:
            logger.warning(f"调整图像大小失败 {path}: {e}", "B站解析")

    @staticmethod
    async def take_screenshot(url: str, element_selector: str) -> bytes:
        """获取网页元素的截图（已注入Cookie）"""
        from ..config import get_credential

        browser = await get_browser()
        if not browser:
            raise ScreenshotError("Browser is not available.")

        context = None
        page = None
        screenshot_bytes = None

        try:
            credential = get_credential()
            playwright_cookies = []
            if credential and credential.has_sessdata():
                cookies_dict = credential.get_cookies()
                playwright_cookies = [
                    {"name": k, "value": v, "domain": ".bilibili.com", "path": "/"}
                    for k, v in cookies_dict.items()
                ]
                logger.debug(
                    f"已加载 {len(playwright_cookies)} 个B站Cookies用于截图", "B站截图"
                )
            else:
                logger.warning("未找到有效的B站登录凭证，截图可能会失败", "B站截图")

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )

            if playwright_cookies:
                await context.add_cookies(playwright_cookies)  # type: ignore

            page = await context.new_page()

            await page.goto(
                url,
                wait_until="networkidle",
                timeout=SCREENSHOT_TIMEOUT * 1000,
            )

            login_popup_selectors = [
                ".bili-mini-login-container",
                ".login-panel",
                ".unlogin-popover",
            ]
            header_selectors = ["#bili-header-m", ".fixed-header", ".bili-header__bar"]

            try:
                js_code = """
                (function() {
                    const loginSelectors = %s;
                    loginSelectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => el && el.remove());
                    });
                    const headerSelectors = %s;
                    headerSelectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => el && (el.style.display = 'none'));
                    });
                    const floatingElements = document.querySelectorAll('.fixed-element, .floating, .popup, .modal, [style*="position: fixed"]');
                    floatingElements.forEach(el => {
                        if (el && !el.matches('%s')) {
                            el.style.display = 'none';
                        }
                    });
                    return 'Attempted to clean up page for screenshot';
                })();
                """ % (
                    str(login_popup_selectors),
                    str(header_selectors),
                    element_selector,
                )

                result = await page.evaluate(js_code)
                logger.debug(f"执行页面清理 JS 结果: {result}", "B站截图")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"移除/隐藏元素 JS 执行失败: {e}", "B站截图")

            element = await page.query_selector(element_selector)
            if not element:
                logger.debug(
                    f"初始 query_selector 未找到 '{element_selector}'，尝试 wait_for_selector"
                )
                try:
                    wait_timeout = 15000
                    logger.debug(
                        f"使用 wait_for_selector 等待: '{element_selector}', 超时: {wait_timeout}ms"
                    )
                    element = await page.wait_for_selector(
                        element_selector, timeout=wait_timeout, state="visible"
                    )
                    logger.debug(f"wait_for_selector 成功找到 '{element_selector}'")
                except Exception as e:
                    logger.error(f"等待选择器 '{element_selector}' 超时或失败: {e}")
                    try:
                        debug_path = Path("./debug_screenshot.png").resolve()
                        await page.screenshot(path=str(debug_path), full_page=True)
                        logger.error(f"已保存当前页面截图到 {debug_path} 用于调试。")
                    except Exception as ss_err:
                        logger.error(f"保存调试截图失败: {ss_err}")
                    raise ScreenshotError(
                        f"未找到元素 '{element_selector}' 或超时: {e}"
                    )

            if element:
                await asyncio.sleep(0.5)
                screenshot_bytes = await element.screenshot(
                    type="png",
                    timeout=SCREENSHOT_TIMEOUT * 500,
                    animations="disabled",
                )
                logger.info(f"截图成功: {url}, element: {element_selector}")

        except Exception as e:
            logger.error(f"截图失败 for {url}: {e}")
            raise ScreenshotError(
                f"截图失败: {e}",
                cause=e,
                context={"url": url, "selector": element_selector},
            )
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

        if not screenshot_bytes:
            raise ScreenshotError(f"未能获取截图字节: {url}")
        return screenshot_bytes

    @staticmethod
    async def get_article_screenshot(cv_id: str, url: str) -> bytes:
        """获取专栏文章截图"""
        logger.debug(f"获取专栏截图: {cv_id}, URL: {url}", "B站解析")

        selector = SCREENSHOT_ELEMENT_ARTICLE
        logger.debug(f"使用专栏截图选择器: '{selector}'")

        return await ScreenshotService.take_screenshot(url, selector)

    @staticmethod
    async def get_opus_screenshot(opus_id: str, url: str) -> bytes:
        """获取动态截图"""
        logger.debug(f"获取动态截图: {opus_id}, URL: {url}", "B站解析")

        selector = SCREENSHOT_ELEMENT_OPUS
        logger.debug(f"使用动态截图选择器: '{selector}'")

        if "t.bilibili.com" in url:
            url = f"https://www.bilibili.com/opus/{opus_id}"
        return await ScreenshotService.take_screenshot(url, selector)
