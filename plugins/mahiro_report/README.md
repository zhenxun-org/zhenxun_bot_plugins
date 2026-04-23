# 真寻日报

每天给群里发送一张「真寻日报」图片，包含：

- 一言
- B站热点
- 60 秒读世界
- IT 资讯
- 今日新番
- 节日倒计时

## 命令

- `真寻日报`
  - 立即查看当日日报
- `重置真寻日报`（仅超级用户）
  - 清除当天缓存图片，便于重新生成

## 自动任务

- 每天 `00:01`：自动预生成日报图片
- 每天 `09:01`：自动群发日报

## 配置项

- `mahiro_report.FULL_SHOW`（默认 `False`）
  - `False`：精简显示内容
  - `True`：尽量完整显示 IT 资讯和 60 秒内容
- `alapi.ALAPI_TOKEN`（可选）
  - 配置后优先使用 ALAPI 的早报数据
  - 获取地址：`https://admin.alapi.cn/user/login`

## 依赖安装

```bash
pip install -r zhenxun/plugins/mahiro_report/requirements.txt
```

## 缓存目录

日报图片会缓存到：

- `data/mahiro_report/`

同一天重复调用会复用缓存，不会重复渲染。

## 常见提示

- `真寻日报生成超时...`
  - 网络较慢或渲染超时，稍后再试
- 自动发送失败
  - 通常是上游接口波动或渲染超时，插件会在日志中记录原因