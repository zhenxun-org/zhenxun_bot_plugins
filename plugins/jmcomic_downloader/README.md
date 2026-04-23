# JM 下载器

一个用于下载指定 `JM album_id` 并发送压缩包的插件。

## 功能

- 下载指定本子：`jm [album_id]`
- 自动生成加密 PDF 和 ZIP 文件
- ZIP 密码 = 本子 `album_id`
- 黑名单管理（仅超级用户）

## 使用前准备

1. 安装依赖

```bash
pip install -r zhenxun/plugins/jmcomic_downloader/requirement.txt
```

如果运行时报缺包，再补装：

```bash
pip install pikepdf pyyaml
```

2. 确保你在用 OneBot v11 适配器（插件里用到了文件上传 API）。

## 指令

本插件使用了 `to_me()` 规则，通常需要 @机器人 触发。

- `jm [album_id]`
  - 下载并发送本子压缩包
  - 示例：`jm 114514`
- `jm add [album_id]`
  - 添加黑名单（仅超级用户）
- `jm del [album_id]`
  - 移除黑名单（仅超级用户）
- `jm list`
  - 查看黑名单列表

## 文件与配置

首次启动会自动创建：

- `data/jmcomic/blacklist_config.yml`
  - `super_users`: 插件超级用户列表
  - `blacklist`: 黑名单本子 ID 列表
- `data/jmcomic/option.yml`
  - JM 下载配置（线程、目录规则、插件等）

输出目录：

- PDF: `data/jmcomic/jmcomic_pdf`
- ZIP: `data/jmcomic/jmcomic_zip`

## 超级用户说明

- 插件会自动尝试同步 NoneBot 全局 `superusers` 到本插件配置中。
- 也可以手动编辑 `blacklist_config.yml` 的 `super_users`。

## 使用说明

- 同一个 `album_id` 如果之前已生成 ZIP，会优先直接发送已有文件。
- 发出去的 ZIP 密码就是该 `album_id`。

## 常见提示

- `权限不足，只有超级用户才能...`
  - 你不是超级用户。
- `本子 xxxx 已被扔进垃圾桶里了喵`
  - 该 ID 在黑名单中。
- `本子 xxxx 飞到天堂去了喵~`
  - 本子不存在或无法访问。
- `当前有本子正在下载喵，请稍等...`
  - 有其他下载任务正在处理。

## 免责声明

请仅在合法、合规场景下使用本插件，并遵守当地法律法规与平台规则。