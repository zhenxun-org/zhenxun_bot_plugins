from aiohttp import web, ClientSession
import json
# from .__init__ import _


async def websocket_handler(request):
    # 进行WebSocket连接
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    print("新客户端已连接")

    try:
        # 被动接收消息
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                messages = json.loads(msg.data)
                if messages["post_type"] in ["message"]:
                    print(f"收到消息: {messages}")
                    get_url = ""
                    message = ""
                    if messages["message_type"] == "group":
                        for msgs in messages["message"]:
                            print(f"\n\n\n{messages['message']}\n\n\n")
                            if msgs["type"] == "reply":
                                payload = {"message_id": msgs["data"]["id"]}
                                async with ClientSession() as session:
                                    async with session.post(
                                        url="http://127.0.0.1:3000/get_msg",
                                        json=payload,
                                        headers={"Content-Type": "application/json"},
                                    ) as resp:
                                        result = await resp.json()
                                        messages["message"].append(
                                            result["data"]["message"][0]
                                        )
                                        print(
                                            f"引用内容: {result}typ: {type(result['data']['message'][0])}"
                                        )
                                        continue

                            elif msgs["type"] == "text":
                                print(type(msgs["data"]["text"]))
                                message += str(msgs["data"]["text"])
                            elif msgs["type"] == "image":
                                get_url = str(msgs["data"]["url"])

                        print(
                            f"收到来自{messages['group_id']}的{messages['sender']['nickname']}消息:{message}{get_url}"
                        )
                        # await _(group_id=messages['group_id'], user_id=messages['user_id'],uname=messages['sender']['nickname'],message=msg)
                        if message[:4] == "echo":
                            await send_message(
                                messages["group_id"],
                                f"{message[4:]}",
                                "/send_group_msg",
                            )

                else:
                    pass
                    # 处理消息逻辑
                    # await ws.send_str(f"Echo: {message}")
                # await ws.send_str(f"Echo: {msg.data}")
            elif msg.type == web.WSMsgType.ERROR:
                print(f"连接错误: {ws.exception()}")
                break
    finally:
        print("客户端已断开")

    return ws


async def send_message(group_id, message, function: str):
    """发送消息到指定群组"""
    url = f"http://localhost:3000{function}"
    payload = {
        "group_id": group_id,
        "message": [{"type": "text", "data": {"text": message}}],
    }
    headers = {"Content-Type": "application/json"}
    async with ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            print(payload)
            result = await resp.json()
            print(f"发送到群组{group_id}的消息: {message}")
            return result


# 创建并启动服务器
app = web.Application()
app.router.add_get("/", websocket_handler)
web.run_app(app, host="localhost", port=8082)
# {'self_id': 2879569168, 'user_id': 297985436, 'time': 1754620084, 'message_id': 1000886449, 'message_seq': 1000886449, 'real_id': 1000886449, 'real_seq': '177976', 'message_type': 'group', 'sender': {'user_id': 297985436, 'nickname': 'Dvin🇨🇳', 'card': '', 'role': 'member'}, 'raw_me essage': '我的账号信息', 'font': 14, 'sub_type': 'normal', 'message': [{'type': 'text', 'data': {'text': '我的账号信息'}}], 'message_format': 'array', 'post_type': 'message', 'group_id': 893561044}
