# 🎬 B站内容解析插件 (parse_bilibili)

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/your-repo/parse_bilibili)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

一个功能强大的B站内容解析插件，支持视频、直播、专栏/动态、番剧等多种B站内容的解析和下载功能。

## ✨ 主要特性

- 🔍 **智能解析**：自动识别并解析多种B站内容类型
- 📥 **视频下载**：支持高质量视频下载，自动合并音视频
- 🖼️ **图片渲染**：将解析结果渲染为精美图片
- 🔐 **账号登录**：支持B站账号登录，获取更高清晰度
- ⚡ **高性能**：异步处理，队列化下载管理
- 🛡️ **稳定可靠**：完善的错误处理和重试机制



## 🚀 功能特点

### 🔍 1. 智能被动解析

自动监听消息中的B站链接，智能解析并发送精美的内容卡片。

**📺 支持内容类型**
- 🎥 视频 (av/BV号)
- 📺 直播间
- 📝 专栏文章 (cv号)
- 💬 动态 (t.bili/opus)
- 🎬 番剧/影视 (ss/ep号)
- 👤 用户空间 (space)

**🔗 链接支持**
- ✅ 完整链接 (bilibili.com)
- ✅ 短链接 (b23.tv)
- ✅ 小程序/卡片解析（可配置）
- ✅ 智能缓存（5分钟内不重复解析）

### 📥 2. 智能视频下载

高质量视频下载，支持多种触发方式和智能优化。

**💬 命令格式**
```bash
bili下载 [链接/ID]    # 直接下载指定视频
b站下载 [链接/ID]    # 别名命令
bili下载             # 引用消息下载
```

**🎯 智能特性**
- ✅ 多格式支持：链接、av/BV号、引用消息
- ✅ 智能质量调整：超过100MB自动降低分辨率
- ✅ 缓存机制：已下载视频直接从缓存发送
- ✅ 质量配置：360P/480P/720P/1080P可选
- ✅ 错误重试：网络异常自动重试
- ✅ 队列管理：并发控制，避免资源冲突

### ⚡ 3. 自动下载管理

管理员可灵活控制群聊的自动下载功能。

**🎛️ 控制命令**
```bash
bili自动下载 on     # 开启当前群聊自动下载
bili自动下载 off    # 关闭当前群聊自动下载
```

**🔧 智能限制**
- ⏱️ 时长限制：默认仅下载10分钟内视频
- 📏 大小控制：超大视频自动降质
- 🎯 精准触发：仅对解析到的视频生效

### 🖼️ 4. 高清封面获取

一键获取B站内容的原始高清封面图片。

**🎨 使用方法**
```bash
bili封面    # 获取高清封面图片
b站封面    # 别名命令
```

**📋 功能特点**
- 🎯 **引用触发**：引用包含B站链接的消息后发送命令
- 📺 **内容支持**：视频(av/BV)和番剧(ss/ep)
- 🖼️ **原始质量**：返回最高分辨率封面，无尺寸限制
- ⚡ **快速响应**：直接获取，无需下载视频

### 🔐 5. 账号登录管理

超级用户专享功能，解锁更多内容和高清晰度。

**🔑 登录命令**
```bash
bili登录    # 扫码登录B站账号
bili状态    # 查询登录状态
```

**🎁 登录优势**
- 🔓 **内容解锁**：访问需登录的内容
- 📺 **高清视频**：获取更高分辨率下载
- 🔄 **自动刷新**：凭证自动续期，长期有效
- 📊 **状态监控**：实时查看凭证有效性

---

## 🛠️ 安装配置

### 📦 依赖要求

**Python 依赖**
```bash
# 自动安装（推荐）
pip install -r requirements.txt

# 手动安装核心依赖
pip install aiohttp>=3.9.0
pip install bilibili-api-python>=16.0.0
```

> ⚠️ **重要提示**：必须安装 `bilibili-api-python`，而不是 `bilibili-api`

### 🎬 FFmpeg 配置

视频下载功能需要 FFmpeg 支持，请根据系统选择安装方式：

<details>
<summary>🪟 Windows 安装</summary>

1. 访问 [FFmpeg 官网](https://ffmpeg.org/download.html)
2. 下载 Windows 版本并解压
3. 将 `ffmpeg.exe` 所在目录添加到系统 PATH
4. 验证安装：`ffmpeg -version`

</details>

<details>
<summary>🍎 macOS 安装</summary>

```bash
# 使用 Homebrew（推荐）
brew install ffmpeg

# 验证安装
ffmpeg -version
```

</details>

<details>
<summary>🐧 Linux 安装</summary>

```bash
# Debian/Ubuntu
sudo apt update && sudo apt install ffmpeg

# CentOS/RHEL/Fedora
sudo yum install ffmpeg
# 或
sudo dnf install ffmpeg

# 验证安装
ffmpeg -version
```

</details>

### ⚙️ 配置选项

通过机器人配置系统自定义插件行为：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_BILIBILI_PARSE` | `True` | 🔄 被动解析进群默认开关状态 |
| `CACHE_TTL` | `5` | ⏰ 解析缓存时间（分钟），0=关闭缓存 |
| `ENABLE_MINIAPP_PARSE` | `True` | 📱 是否解析小程序/卡片中的B站链接 |
| `RENDER_AS_IMAGE` | `True` | 🖼️ 是否将解析结果渲染为图片 |
| `AUTO_DOWNLOAD_MAX_DURATION` | `10` | ⏱️ 自动下载最大时长（分钟），0=无限制 |
| `MANUAL_DOWNLOAD_MAX_DURATION` | `20` | 🎯 手动下载最大时长（分钟），超级用户不受限 |
| `VIDEO_DOWNLOAD_QUALITY` | `64` | 📺 视频下载质量（16=360P, 32=480P, 64=720P, 80=1080P） |
| `PROXY` | `None` | 🌐 下载代理设置 |

---

## 📖 使用指南

### 🔍 被动解析示例

发送任意B站链接，机器人自动解析：

```text
用户: https://www.bilibili.com/video/BV1xx411c7mD
机器人: [自动发送精美的视频信息卡片]
```

### 📥 视频下载示例

**直接下载**
```bash
bili下载 https://www.bilibili.com/video/BV1xx411c7mD
bili下载 BV1xx411c7mD
bili下载 av12345678
```

**引用下载**
```bash
[引用包含B站链接的消息]
bili下载
```

### 🖼️ 封面获取示例

```bash
[引用包含B站链接的消息]
bili封面
# 或
b站封面
```

### ⚡ 自动下载控制

```bash
bili自动下载 on     # 开启自动下载
bili自动下载 off    # 关闭自动下载
```

### 🔐 账号管理

```bash
bili登录    # 扫码登录
bili状态    # 查看状态
```

---

## ⚠️ 重要提示

### 🔧 技术要求
- ✅ **FFmpeg 必需**：视频下载功能依赖 FFmpeg
- ✅ **登录推荐**：高清视频可能需要B站账号登录
- ✅ **存储空间**：确保有足够空间存储临时文件

### 📋 使用规范
- 🎯 **封面命令**：只能通过引用消息触发，不支持直接传参
- 📺 **内容限制**：封面功能仅支持视频和番剧
- ⏱️ **时长限制**：自动下载默认限制10分钟内视频
- 📏 **大小控制**：超过100MB自动降低分辨率

### 🛡️ 合规使用
- 🚫 **会员内容**：仅使用官方API，不支持会员专享内容
- 🌐 **频率控制**：避免频繁大量下载导致IP限制
- 🔄 **自动清理**：临时文件会在过期后自动清理

---

## 🔧 故障排除

<details>
<summary>❌ 视频下载失败</summary>

**可能原因及解决方案：**
- 🔧 **FFmpeg 未安装**：确保 FFmpeg 已正确安装并添加到 PATH
- 🔐 **需要登录**：高清视频可能需要B站账号登录
- 🌐 **网络问题**：检查网络连接是否正常
- 👑 **会员内容**：本插件不支持会员专享内容下载

</details>

<details>
<summary>⏰ 视频发送超时</summary>

**优化建议：**
- 📏 降低 `VIDEO_DOWNLOAD_QUALITY` 配置值
- ⏱️ 增加 `SEND_VIDEO_TIMEOUT` 超时时间
- 🔄 增加 `SEND_VIDEO_MAX_RETRIES` 重试次数

</details>

<details>
<summary>🔍 解析结果不显示</summary>

**检查项目：**
- ✅ 确认对应内容类型解析已启用
- 🕐 检查缓存设置（可能短时间内重复解析被跳过）
- 🔗 确认链接格式正确

</details>

<details>
<summary>⚡ 自动下载不工作</summary>

**排查步骤：**
- 🎛️ 确认当前群聊已开启自动下载
- ⏱️ 检查视频时长是否超过限制（默认10分钟）
- 💾 确认存储空间充足

</details>

<details>
<summary>🖼️ 封面命令无响应</summary>

**注意事项：**
- 📝 必须使用引用消息方式触发
- 🔗 确认引用消息包含有效B站链接
- 📺 确认内容类型为视频或番剧
- 🌐 检查网络连接状态

</details>

---

## 📄 许可证

本插件基于 [MIT 许可证](LICENSE) 开源。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这个插件！

## 📞 支持

如果遇到问题，请：
1. 查看上方的故障排除指南
2. 检查 [Issues](https://github.com/your-repo/issues) 中是否有类似问题
3. 提交新的 Issue 并提供详细信息

---

## 📋 更新日志

### v1.5.4

♻️ **重构解析下载架构，优化用户体验**

**✨ 架构优化**
- 新增 DownloadManager 和 DownloadService，实现下载任务队列化管理
- 独立 CoverService 封面服务，提升模块化设计
- 统一 API 重试机制，使用 @Retry.api 装饰器增强网络健壮性
- 移除 NetworkService，统一使用 AsyncHttpx 简化网络层

**🚀 功能增强**
- 支持更灵活的 URL 格式，包括 bvid 参数链接
- 优化 FFmpeg 合并策略：流复制优先，重编码兜底
- 截图服务注入登录凭证，支持需登录页面访问
- 改进错误提示，提供更友好的用户反馈

**🧹 代码清理**
- 移除未使用的导入和旧重试机制代码
- 简化文件下载合并逻辑
- 统一异常处理，优化日志输出
- 精简依赖列表，移除不必要的库
- 整理导入

**🔧 漏洞修复**
- 修复因 B 站 CDN 错误导致的下载失败问题

---

<div align="center">

**⭐ 如果这个插件对你有帮助，请给个 Star 支持一下！**

</div>
