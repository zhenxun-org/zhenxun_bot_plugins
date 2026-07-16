# 漫画翻译 (Manga Translator)

真寻 (ZhenXun) QQ 机器人插件 — 基于 Cotrans API 的图片/漫画翻译。

## 功能

- 发送漫画/图片，自动识别文字区域并翻译
- 支持 19 种目标语言
- 支持多种翻译引擎 (Google、GPT-3.5、DeepL 等)
- 后台队列 + 超时通知

## 安装

```bash
# 将本目录放入真寻的 plugins/ 目录下
# 安装依赖
pip install Pillow httpx
```

## 使用

```
漫画翻译 -t CHS -s L        # 指定语言和尺寸后发送图片
图片翻译 <task_id>          # 查询任务进度
翻译漫画                     # 先发命令，再发图片
```

### 参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `-t` | 目标语言 | CHS/CHT/ENG/JPN/KOR/FRA/DEU/RUS/ESP/PTB/ITA/NLD/PLK/HUN/ROM/TRK/UKR/VIN/CSY |
| `-s` | 处理尺寸 | S/M/L/X (默认 L) |
| `--translator` | 翻译引擎 | google/gpt3.5/youdao/baidu/deepl/papago/offline/none/original |

## 致谢

- 原版插件概念来自  (manga-image-translator 插件)
- 翻译服务由 [Cotrans](https://cotrans.touhou.ai/) (VoileLabs) 提供

## 许可

MIT
