import google.generativeai as genai
from tavily import AsyncTavilyClient
import os
from dotenv import load_dotenv
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
chat = genai.GenerativeModel("gemini-2.0-flash")


async def search(question):
    tavily_client = AsyncTavilyClient(
        api_key=os.getenv("TAVILY_API_KEY")#在https://www.tavily.com/申请key
    )
    response = await tavily_client.search(f"{question}", max_results=3)
    # print(response)
    responses = await chat.generate_content_async(
        f"你需要对以下信息进行总结，不要加入自己的看法只要总结就行100字以内最好\n需要总结的内容\n{response}"
    )
    responses = "搜索结果:" + responses.text
    return responses


# print(responses.text)
