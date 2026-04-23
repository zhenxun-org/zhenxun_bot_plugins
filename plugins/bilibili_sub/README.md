# B站订阅插件（bilibili_sub）

把 B 站内容自动推送到群聊/私聊，支持：

- UP 主动态
- UP 主视频更新
- 直播开播提醒
- 番剧更新提醒

## 使用权限

- `bilisub add / del / list / config / clear`：群管理及以上可用
- `bilisub login / status / logout / checkall / forcepush`：仅超级用户可用

## 快速上手

1. 添加订阅

```bash
# 订阅 UP 主（UID）
bilisub add 732482333

# 订阅直播间（房间号，必须加 --live）
bilisub add --live 21452505

# 订阅番剧（支持番名 / ss号 / ep号）
bilisub add 葬送的芙莉莲
bilisub add ss12345
bilisub add ep987654
```

2. 查看订阅列表（会显示每条订阅的 ID）

```bash
bilisub list
```

3. 调整推送内容（按订阅 ID 设置）

```bash
# 给 ID 3 和 4 开直播、关动态，并在直播推送时 @全体
bilisub config 3 4 +live -dynamic +at:live
```

4. 删除订阅

```bash
bilisub del 3
```

5. 清空当前会话的所有订阅（会二次确认）

```bash
bilisub clear
```

## `config` 常用参数

- `+dynamic` / `-dynamic`：开/关动态推送
- `+video` / `-video`：开/关视频（番剧也走这个）
- `+live` / `-live`：开/关直播推送
- `+all` / `-all`：全部开/关
- `+at:dynamic` / `-at:dynamic`：动态时 @全体
- `+at:video` / `-at:video`：视频/番剧时 @全体
- `+at:live` / `-at:live`：直播时 @全体
- `+at:all` / `-at:all`：所有推送都 @全体

## 超级用户命令

```bash
# 扫码登录 B 站（建议先登录，减少接口风控失败）
bilisub login

# 查看当前登录状态
bilisub status

# 退出登录
bilisub logout

# 立即检查全部订阅
bilisub checkall

# 强制推送指定订阅 ID 的最新内容
bilisub forcepush 3 4
```

## 跨群管理（仅超级用户）

```bash
# 查看指定群的订阅
bilisub list -g 123456789

# 给指定群添加订阅
bilisub add 732482333 -g 123456789

# 删除指定群的订阅关系
bilisub del 3 -g 123456789

# 清空指定群
bilisub clear -g 123456789

# 清空所有群/私聊目标（高危操作）
bilisub clear --all
```

## 常见问题

- 问：番剧搜索出来多个结果怎么办？
  答：按提示回复序号选择即可，60 秒内有效。

- 问：为什么没有收到推送？
  答：先检查 `bilisub status` 是否登录有效，再确认订阅是否开启对应推送类型（`bilisub config`）。

- 问：`@全体` 没生效？
  答：需要机器人在群里是管理员/群主，且总开关 `ENABLE_AT_ALL` 已开启。
