# BYM_AI (拟人聊天与人设管理插件) 使用说明

`BYM_AI` 是一个基于大语言模型的群聊拟人化交互插件，支持多群组独立人设切换、群聊随机插话、长线会话记忆总结，并支持通过 TTS 模型进行语音和文字的双重回复。

## ⚙️ 先决条件

本插件基于真寻内置的统一 AI 核心服务运行。**在配置本插件前，请确保您的全局 AI 服务已经配置完毕（可以正常调用对话和文本生成模型）。**

---

## 📝 配置文件 (`data/config.yaml`)

首次加载插件后，系统会自动在全局 `config.yaml` 文件的 `bym_ai` 节点下生成配置。您可以根据需要进行调整：

```yaml
bym_ai:
  # 1. 核心模型路由配置
  BYM_AI_CHAT_MODEL: "DeepSeek/deepseek-v4-flash" # 聊天对话模型路由 (必填)
  DEFAULT_PERSONA: "真寻"                          # 全局缺省人设名称 (与 prompts.toml 中的键对应)
  ENABLE_IMPRESSION: true                        # 是否启用群员签到好感度系统作为 AI 态度的影响因子

  # 2. 上下文记忆模式
  CONTEXT_MODE: "user"                           # 记忆模式：'user'(每个用户独立会话，默认) 或 'group'(群聊内全员共享一个上下文)

  # 3. 随机插话设置 (拟人化)
  RANDOM_REPLY:
    enable: false                                # 是否开启群聊内无需 @ 的随机拟人插话
    rate: 0.01                                   # 随机插话触发概率，范围 0.0 - 1.0 (0.01 代表约 100 句插话一次)

  # 4. 语音合成 (TTS) 回复
  TTS_CONFIG:
    enable: false                                # 是否开启语音消息回复
    model: "MiMo/mimo-v2.5-tts"                  # 语音合成使用的模型路由
    voice_id: ""                                 # 强制指定的音色 ID。留空则由底层 AI 模块自动填充默认推荐音色

  # 5. [高级] 记忆截断与上下文压缩策略
  memory_settings:
    group_history_limit: 20                      # 群聊背景消息最大缓存轮数，用于给大模型提供聊天语境
    group_vision_window: 2                       # 原样保留的多模态（图片）轮数。超出视窗的图片自动降级为 <图片> 占位符以极限节省 Token
    ltm_config:
      enable: false                              # 是否启用长期记忆 RAG（仅在 user 独立记忆模式下生效）
      embed_model: "siliconflow/BAAI/bge-m3"     # 用于长期记忆检索的向量模型
      auto_recall: false                         # 是否在每次对话前自动执行相似度搜索召回历史
    llm_summary:
      enable: true                               # 是否开启长上下文的自动总结压缩
      trigger_threshold: 0.7                     # 触发总结压缩的上下文 Token 比例阀值 (0.7 代表占用 70% 窗口时压缩)
      max_history_turns: 20                      # 触发压缩的最大历史会话轮数

  # 6. [高级] 发言门控决策与人设风控
  advanced_settings:
    guardrail:
      enable: false                              # 是否开启人设风控裁判（使用大模型裁判检查 AI 的回复是否偏离人设，严重偏离时将强制自愈重生成）
      model: "DeepSeek/deepseek-v4-flash"        # 裁判大模型路由。注意：开启此功能会使单次响应消耗的双倍的 Token
      max_attempts: 1                            # 裁判校验失败后允许 AI 自我反思重试的最大次数
    timing_gate:
      enable: false                              # 是否开启大模型发言门控（大模型会先根据上下文环境和人设判断此时“插话是否符合礼仪/逻辑”，不符合则保持静默）
      model: "DeepSeek/deepseek-v4-flash"        # 门控决策大模型路由
      only_on_random: true                       # True 表示仅在随机概率命中时执行门控；False 表示所有发言（包括主动 @）均经过门控
```

---

## 🎮 交互使用方式

1. **直接艾特**：在群里 `@机器人 + 聊天内容`，机器人必定会进行对话。
2. **随机插话**：不艾特机器人时，系统会根据 `RANDOM_REPLY` 的概率，决定是否对群员的发言进行插话。
3. **表情或无字艾特**：如果只 `@机器人` 但不输入任何文字，或只发送表情，机器人会根据人设进行打招呼或吐槽。

---

## 🛠️ 超级用户指令 (SUPERUSER)

管理员可以使用 `bym` 统一命令行入口，对插件的记忆、配置以及人设进行无缝热管理：

### 1. 记忆管理
*   `bym clear`：清理你在当前私聊或群聊环境下的个人短期记忆。
*   `bym clear @用户...`：清理指定群员在当前群组内的个人记忆。
*   `bym clear -g` / `bym clear --group`：清理当前群组下的所有共享/缓存记忆。
*   `bym clear -a` / `bym clear --all`：彻底清空整个插件数据库下的所有记忆（需要二次确认）。

### 2. 状态与配置查询
*   `bym show [-g <群号>]` 或发送 `查看配置`：查询指定群组当前生效的 AI 人设名称、是否开启随机回复、触发概率以及记忆模式。

### 3. 动态配置快捷指令 (设置属性)
本插件支持通过群组配置指令进行实时设置，且支持使用以下快捷短语：
*   `bym设置 人设 <人设名> [-g <群号> / --all]`：修改指定群组（或所有群组）的 AI 扮演人设。
*   `bym设置 概率 <0.0-1.0> [-g <群号> / --all]`：修改目标群组的拟人随机插话触发概率。
*   `bym设置 回复 <on/off> [-g <群号> / --all]`：开启或关闭指定群组的随机拟人插话。
*   `bym设置 模式 <user/group> [-g <群号> / --all]`：修改记忆隔离模式（`user` 为用户独立记忆，`group` 为群内共享记忆）。

### 4. 人设管理 (JIT 热重载)
*   `bym prompt list` 或 `查看人设`：生成当前 prompts.toml 磁盘中所有可用的人设列表表格图片。
*   `bym prompt reload` 或 `重载人设`：强制从硬盘重新读取 prompts.toml 配置文件并刷新内存缓存。
*   `bym prompt add <人设名称>`：交互式引导添加新的人设设定。
*   `bym prompt edit <人设名称>`：交互式引导修改已有人设设定。
*   `bym prompt del <人设名称>`：删除指定的人设（正在使用此人设的群组会自动安全回退至系统默认人设）。

---

## 🗃️ 人设配置文件说明

人设配置文件路径：`data/bym_ai/prompts.toml`

*   本插件采用标准的 TOML 格式管理多个人设，默认内置了“真寻（傲娇嘴硬）”和“奈奈（冷淡技术宅）”两个极具特色的人设。
*   **推荐修改方式**：直接在群聊中向机器人发送 `bym prompt add/edit/del` 指令，按照机器人的向导多行回复人设，插件会自动处理转义、安全落盘并实时刷新缓存，**无需手动重启机器人**。
*   **手动修改方式**：直接用文本编辑器编辑 `prompts.toml` 文件的内容，修改完成后，需要在机器人中发送 `bym prompt reload` 使其重新载入内存。

---

## ❓ 常见问题排查 (FAQ)

*   **没有得到任何回复？**
    *   请先检查 `config.yaml` 里的 `BYM_AI_CHAT_MODEL` 是否已经正确填写。
    *   检查日志输出，确认全局 AI 服务是否工作正常。

*   **只在艾特 `@` 时回复，绝对不会随机插话？**
    *   请确认 `RANDOM_REPLY.enable` 是否已设为 `true`。
    *   检查该群组的 `random_reply_enable` 状态是否被快捷指令修改为了 `False`（可发送 `bym show` 查看）。
    *   检查 `RANDOM_REPLY.rate` 触发概率是否设置得过小。

*   **修改了 prompts.toml 提示词，但是没有变化？**
    *   手动修改 TOML 文件后，必须在群聊或私聊中向机器人发送一次 `bym prompt reload` 或 `重载人设` 才能让其更新内存。如果是通过交互指令修改的，则会自动热更新。