import json
from playwright.async_api import async_playwright

from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.configs.utils import AbstractTool
from zhenxun.configs.config import Config

base_config = Config.get("bym_ai")

class SendLike(AbstractTool):
    def __init__(self):
        super().__init__(
            name="website",
            description="Useful when you want to browse a website by url",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "你想访问的网站地址"
                    }
                },
                "required": [
                    "url"
                ]
            },
            func=self.website_func
        )

    async def website_func(self, url: str) -> str:
        chat_url = base_config.get("BYM_AI_CHAT_URL")
        chat_model = base_config.get("BYM_AI_CHAT_MODEL")

        if tokens := base_config.get("BYM_AI_CHAT_TOKEN"):
            if isinstance(tokens, str):
                tokens = [tokens]
        chat_token = tokens[0]

        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until='networkidle')
                text = await page.content()
                await page.close()

            text = self.clean_html(text)

            content = f"去除与主体内容无关的部分，从中整理出主体内容并转换成md格式，不需要主观描述性的语言与冗余的空白行。{text}"

            send_json = {
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "stream": False,
                "model": chat_model
            }
                    
            result = await AsyncHttpx.post(
                chat_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {chat_token}",
                },
                json=send_json,
                verify=False
            )

            res = result.json().get('choices')[0].get("message", {}).get("content", None)
            return f"this is the main content of website:\n {res}"
        except Exception as e:
            return f"failed to visit the website, error: {str(e)}"
        
    def clean_html(self, text):
        import re
        # 清理 HTML 内容
        text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<head\b[^<]*(?:(?!<\/head>)<[^<]*)*<\/head>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<figure\b[^<]*(?:(?!<\/figure>)<[^<]*)*<\/figure>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<path\b[^<]*(?:(?!<\/path>)<[^<]*)*<\/path>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<video\b[^<]*(?:(?!<\/video>)<[^<]*)*<\/video>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<audio\b[^<]*(?:(?!<\/audio>)<[^<]*)*<\/audio>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<img[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<!--[\s\S]*?-->', '', text)  # 去除注释
        text = re.sub(r'<(?!\/?(title|ul|li|td|tr|thead|tbody|blockquote|h[1-6]|H[1-6])[^>]*)\w+\s+[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<(\w+)(\s[^>]*)?>', r'<\1>', text, flags=re.IGNORECASE)
        text = re.sub(r'</(?!\/?(title|ul|li|td|tr|thead|tbody|blockquote|h[1-6]|H[1-6])[^>]*)[a-z][a-z0-9]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[\n\r]', '', text)
        text = re.sub(r'\s{2,}', ' ', text)
        text = text.replace('<!DOCTYPE html>', '')
        return text
