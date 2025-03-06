# BYM AI 插件使用指南

本插件支持所有符合 OpenAi 接口格式的 AI 服务，以下以 Gemini 为例进行说明。
你也通过 [其他文档](https://github.com/Hoper-J/AI-Guide-and-Demos-zh_CN/blob/master/Guide/DeepSeek%20API%20%E7%9A%84%E8%8E%B7%E5%8F%96%E4%B8%8E%E5%AF%B9%E8%AF%9D%E7%A4%BA%E4%BE%8B.md) 查看配置

## 获取 API KEY

1. 进入 [Gemini API Key](https://aistudio.google.com/app/apikey?hl=zh-cn) 生成 API KEY。
2. 如果无法访问，请尝试更换代理。

## 配置设置

首次加载插件后，在 `data/config.yaml` 文件中进行以下配置（请勿复制括号内的内容）：

```yaml
bym_ai:
  # BYM_AI 配置
  BYM_AI_CHAT_URL: https://generativelanguage.googleapis.com/v1beta/chat/completions  # Gemini 官方 API，更推荐找反代
  BYM_AI_CHAT_TOKEN:
    - 你刚刚获取的 API KEY，可以有多个进行轮询
  BYM_AI_CHAT_MODEL: gemini-2.0-flash-thinking-exp-01-21  # 推荐使用的聊天模型（免费）
  BYM_AI_TOOL_MODEL: gemini-2.0-flash-exp  # 推荐使用的工具调用模型（免费，需开启 BYM_AI_CHAT_SMART）
  BYM_AI_CHAT: true  # 是否开启伪人回复
  BYM_AI_CHAT_RATE: 0.001  # 伪人回复概率（0-1）
  BYM_AI_TTS_URL:  # TTS 接口地址
  BYM_AI_TTS_TOKEN:  # TTS 接口密钥
  BYM_AI_TTS_VOICE:  # TTS 接口音色
  BYM_AI_CHAT_SMART: true  # 是否开启智能模式（必须填写 BYM_AI_TOOL_MODEL）
  ENABLE_IMPRESSION: true  # 使用签到数据作为基础好感度
  CACHE_SIZE: 40  # 缓存聊天记录数据大小（每位用户）
  ENABLE_GROUP_CHAT: true  # 在群组中时共用缓存
```

## 人设设置

在`data/bym_ai/prompt.txt`中设置你的基础人设

## 礼物开发

与商品注册类型，在`bym_ai/bym_gift/gift_reg.py`中查看写法。

例如：

```python
@gift_register(
    name="可爱的钱包",
    icon="wallet.png",
    description=f"这是{BotConfig.self_nickname}的小钱包，里面装了一些金币。",
)
async def _(user_id: str):
    rand = random.randint(100, 500)
    await UserConsole.add_gold(user_id, rand, "BYM_AI")
    return f"钱包里装了{BotConfig.self_nickname}送给你的枚{rand}金币哦~"
```