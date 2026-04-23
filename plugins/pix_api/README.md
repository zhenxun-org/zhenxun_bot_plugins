# pix_api 使用说明

`pix_api` 是一个 Pixiv 图片检索与管理插件，支持：

- 按标签随机/批量取图
- 查看图片信息、原图
- 收藏/取消收藏与收藏排行
- 图片屏蔽与 NSFW 等级调整
- 标签统计与图库数量统计

## 使用前准备

这个插件依赖一个可用的 `pix-api` 服务，请先配置：

- `pix.pix_api`：pix-api 地址（例如 `http://pix.zhenxun.org`）
- `pix.TOKEN`：接口 token（不填时插件会在启动时尝试自动获取）

可选配置：

- `pix.PIX_IMAGE_SIZE`：下载尺寸，默认 `large`
- `pix.TIMEOUT`：请求超时秒数，默认 `10`
- `pix.SHOW_INFO`：发图时是否附带标题/作者/pid 信息
- `pix.MAX_ONCE_NUM2FORWARD`：单次发图达到该数量时改为合并转发
- `pix.ALLOW_GROUP_R18`：是否允许群内普通用户使用 R18 参数
- `pix.FORCE_NSFW`：强制 NSFW 等级（如 `[0, 1]`）
- `pixiv.PIXIV_SMALL_NGINX_URL` / `pixiv.PIXIV_NGINX_URL`：反代地址

## 用户命令

- `pix [标签...] [-n 数量] [-r] [-noai] [--nsfw 0 1 2] [--ratio x,y]`
- `pix图库 [标签...]`
- `pixtag [数量]`
- `pix收藏`
- `pix排行 [数量] [-r]`

说明：

- `pix` 一次最多 `10` 张。
- `pix排行` 与 `pixtag` 一次最多 `30` 条。
- `--ratio x,y` 里 `x`、`y` 必须是数字，且满足 `0 < x <= y`。

## 引用回复命令

先引用机器人发出的 Pix 图片消息，再发送：

- `/original`：获取原图
- `/info`：查看图片信息
- `/star`：收藏该图
- `/unstar`：取消收藏
- `/block [1|2] [--all]`：屏蔽图片（默认等级 2）
- `/block -u`：按作者 uid 屏蔽
- `/nsfw [0|1|2]`：设置该图 NSFW 等级

## 管理命令

- `pix添加 u <uid...>`：添加作者 UID
- `pix添加 p <pid...>`：添加图片 PID

## 常见问题

- 提示 API 出错或超时：
  - 先确认 `pix_api` 服务可访问，再检查 `TOKEN` 是否有效。
- 群里无法使用 R18：
  - 这是默认限制，需开启 `ALLOW_GROUP_R18` 或使用私聊/超管账号。
- 引用命令提示找不到图片信息：
  - 可能引用了非 Pix 消息，或缓存已过期（会定时清理）。
