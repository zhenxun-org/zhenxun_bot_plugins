# BYM_AI 使用说明

`BYM_AI` 是一个“拟人聊天”插件，支持：

- `@机器人` 正常对话
- 群聊随机“插话式”回复
- 自定义人设（prompt）
- 可选 TTS 语音回复
- 可选智能工具调用（例如送礼物）

## 先决条件

本插件使用项目内置的统一 LLM 服务，不再单独在 `bym_ai` 里配置 `CHAT_URL/TOKEN`。

请先确保你已经把全局 AI 服务配置好（能正常调用模型）。

## 配置项（`data/config.yaml`）

首次加载插件后，在 `bym_ai:` 下配置：

```yaml
bym_ai:
  BYM_AI_CHAT_MODEL: gemini-2.5-flash-lite  # 聊天模型（必填）
  BYM_AI_CHAT: true                          # 是否开启群内随机拟人回复
  BYM_AI_CHAT_RATE: 0.05                     # 随机回复概率，范围 0-1
  BYM_AI_CHAT_SMART: false                   # 是否开启智能工具调用

  ENABLE_IMPRESSION: true                    # 是否启用好感度文本（依赖签到数据）
  ENABLE_GROUP_CHAT: true                    # 群聊是否共用上下文
  GROUP_CACHE_SIZE: 40                       # 群聊缓存长度
  CACHE_SIZE: 40                             # 私聊缓存长度

  BYM_AI_TTS_URL:                            # 可选：TTS 接口地址
  BYM_AI_TTS_TOKEN:                          # 可选：TTS 密钥
  BYM_AI_TTS_VOICE:                          # 可选：TTS 音色
```

## 使用方式

1. 直接 `@机器人 + 文字`，会进行对话。
2. 不 `@` 也可能随机回复（由 `BYM_AI_CHAT` 与 `BYM_AI_CHAT_RATE` 控制）。
3. 如果只 `@机器人` 不带文字，会返回一条打招呼内容。

## 超级用户命令

- `重置所有会话`
  - 清空所有会话上下文（数据库会话会打重置标记）
- `重载prompt`
  - 重新加载人设文件，改完人设后可立即生效

建议在群里 `@机器人 重载prompt` 执行。

## 人设文件

人设文件路径：`data/bym_ai/prompt.txt`

- 修改这个文件可自定义机器人说话风格
- 修改后执行：`重载prompt`

## 智能工具说明（可选）

开启 `BYM_AI_CHAT_SMART: true` 后，模型可以调用已注册的智能工具。

当前插件内置了“送礼物”工具；你也可以在其他插件里通过 `smart_tools` 注册新工具供 BYM_AI 调用。

## TTS 说明（可选）

配置好 `BYM_AI_TTS_URL / BYM_AI_TTS_TOKEN / BYM_AI_TTS_VOICE` 后，机器人文本回复后会附带语音消息。

## 常见问题

- 没有任何回复
  - 先确认 `BYM_AI_CHAT_MODEL` 已填写
  - 再确认全局 AI 服务配置可用

- 只在 `@` 时回复，不会随机插话
  - 检查 `BYM_AI_CHAT` 是否为 `true`
  - 检查 `BYM_AI_CHAT_RATE` 是否过小（如 `0.001`）

- 改了 prompt 没生效
  - 执行一次 `重载prompt`

- 智能工具不触发
  - 确认 `BYM_AI_CHAT_SMART: true`
  - 确认对应工具已注册且可被加载
