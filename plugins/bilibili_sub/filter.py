import asyncio
import json
from playwright.async_api import async_playwright
from zhenxun.services.log import logger
import os

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
cookies_path = os.path.join(current_dir, "cookies.json")

async def check_page_elements(url):
    """
    使用无头浏览器和 Cookie 检查页面中的元素是否被拦截，并导出所有页面元素。

    :param url: 要检查的页面 URL
    :param cookies_path: Cookie 文件的路径
    :return: 是否包含被拦截的元素
    """
    try:
        # 读取 cookies.json 文件
        with open(cookies_path, 'r') as f:
            cookies = json.load(f)

        # 修复 sameSite 字段
        for cookie in cookies:
            if cookie.get("sameSite", "").lower() == "unspecified":
                cookie["sameSite"] = "Lax"  # 或者 "Strict" 或 "None"

        async with async_playwright() as p:
            # 启动无头浏览器
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()

            # 添加 Cookie 到浏览器上下文中
            await context.add_cookies(cookies)

            # 创建新页面
            page = await context.new_page()

            # 要拦截的元素的类名
            class_names = ["opus-text-rich-hl", "goods-shop", "bili-dyn-card-goods", "dyn-goods", "dyn-goods__mark"]
            max_attempts = 3  # 最大刷新次数
            attempt = 0

            while attempt < max_attempts:
                # 加载页面
                await page.goto(url)
                await page.wait_for_load_state('networkidle')  # 等待页面完全加载

                # 检查页面中是否包含被拦截的元素
                found_blocked_element = False
                for class_name in class_names:
                    if await page.locator(f".{class_name}").count() > 0:
                        logger.info(f"页面中包含被拦截的元素: {class_name}")
                        found_blocked_element = True
                        break

                if not found_blocked_element:
                    attempt += 1
                    logger.info(f"刷新页面，尝试次数: {attempt}")
                    continue  # 如果发现被拦截元素，刷新页面重新检查
                else:
                    # 如果三次都没有发现被拦截元素，返回 True
                    await browser.close()
                    return True

            # 如果三次检查中都发现了被拦截元素，返回 False
            await browser.close()
            return False

    except Exception as e:
        logger.error(f"检查页面元素时出错: {e}")
        return False

async def main():
    url = input("请输入要检查的页面 URL: ")
    result = await check_page_elements(url)
    print(f"页面是否包含被拦截的元素: {result}")

if __name__ == "__main__":
    asyncio.run(main())
