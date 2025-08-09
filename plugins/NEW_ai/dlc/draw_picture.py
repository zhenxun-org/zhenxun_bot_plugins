import asyncio
import httpx
from zhenxun.utils.http_utils import AsyncHttpx
import os
import base64
from zhenxun.configs.path_config import TEMP_PATH
from dotenv import load_dotenv
load_dotenv()

url = "https://api.siliconflow.cn/v1/images/generations"

async def get_image(prompt):
    # 1. 优化保存路径处理
    save_dir = f'C:\\Users\\Administrator\\Desktop\\zhenxun_bot-main\\{TEMP_PATH}'
    filename = "image.png"
    save_path = os.path.join(save_dir, filename)
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": f"{prompt}",
        "image_size": "1024x1024",
        "batch_size": 1,
        "num_inference_steps": 20,
        "guidance_scale": 7.5,
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('SILICONFLOW_API_KEY')}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            download_url = data["images"][0]["url"]
            print(f"获取下载链接: {download_url}")
    except httpx.HTTPStatusError as exc:
        return f"API请求错误: {exc.response.status_code}"
    except (KeyError, IndexError,httpx.RequestError) as e:
        return f"响应数据错误: {str(e)}"
    if not download_url:
        return '下载连接获取错误'

    try:
        await AsyncHttpx.download_file(download_url,save_path)
        with open(save_path,'rb') as file:
            byte_data = file.read()
        return 'base64://'+base64.b64encode(byte_data).decode("utf-8")
    except:
        return "下载失败"


if __name__ == '__main__':
    asyncio.run(get_image('坐在椅子上正在读书的人'))