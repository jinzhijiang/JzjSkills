# GPT Image v2.5 —— 四个 slug 的完整参数表

所有 slug 都走 `POST https://api.eachlabs.ai/v1/prediction`，`output_type` 在目录里标的是 `array`。
本文档的 schema 于 **2026-09-18** 从 `GET https://api.eachlabs.ai/v1/models/<slug>` 实时拉取。
schema 随时可能变，**以线上为准**：

```bash
python3 scripts/gpt_image.py schema flare       # 打印文生图 + 编辑两份 schema 与计价
python3 scripts/gpt_image.py schema sunburst
curl -s https://api.eachlabs.ai/v1/models/gpt-image-v2-5-flare-edit | python3 -m json.tool
```

`GET /v1/models/<slug>` **不需要鉴权**，随便查不花钱。
注意上游 `eachlabs/skills` 里那个 v2 skill 写的 `GET /v1/model?slug=<slug>` 是错的，实测回 404。

---

## 选型

| slug | 类别 | 官方描述要点 | p50 耗时 |
|------|------|--------------|----------|
| `gpt-image-v2-5-flare-text-to-image` | Text to Image | 日常通用款，快、质量高，支持透明背景 | 60s（实测 low/1024 只要 7.5s） |
| `gpt-image-v2-5-flare-edit` | Image to Image | 只改被点名的地方，跨风格、跨多轮保持主体一致 | 60s |
| `gpt-image-v2-5-sunburst-text-to-image` | Text to Image | 高保真款，细节更细，**换来更长的生成时间** | 目录未给 |
| `gpt-image-v2-5-sunburst-edit` | Image to Image | 精确可控编辑，反复修改也保持主体/结构/构图 | 目录未给 |

Flare 与 Sunburst 的**参数完全一样**，只有取舍不同：Flare 快，Sunburst 细。
默认用 Flare；只有当成品要放大看、或 Flare 出来的细节不够时才换 Sunburst。

---

## 文生图（`*-text-to-image`）

必填：`prompt`。

| 参数 | 类型 | 默认 | 取值 | 说明 |
|------|------|------|------|------|
| `prompt` | string | — | ≤ **32000** 字符 | 画面描述 |
| `size` | string | `1024x1024` | 见下方尺寸表 | **注意：文生图叫 `size`** |
| `quality` | string | `auto` | `low` `medium` `high` `xhigh` `max` `auto` | low 出草稿；xhigh/max 更贵更慢 |
| `output_format` | string | `png` | `jpeg` `png` `webp` | jpeg 比 png 快；透明背景必须 png/webp |
| `background` | string | `auto` | `opaque` `transparent` `auto` | `transparent` 要求 format 为 png/webp |
| `output_compression` | int | — | 0–100 | 只对 jpeg/webp 生效，png 忽略 |
| `num_images` | int | `1` | 1–10 | 一次出几张 |
| `moderation` | string | `low` | `low` `auto` | `low` 更宽松，`auto` 是标准过滤 |

## 编辑（`*-edit`）

必填：`prompt` + `image_urls`。

| 参数 | 类型 | 默认 | 取值 | 说明 |
|------|------|------|------|------|
| `prompt` | string | — | ≤ 32000 字符 | 编辑指令 |
| `image_urls` | string[] | — | 1–**16** 个 URL | **公网可达 URL**，不收 data-URI / localhost |
| `image_size` | string | `1024x1024` | 同尺寸表 | **注意：编辑叫 `image_size`，不是 `size`** |
| `mask_url` | string | — | URL | 可选 inpaint 蒙版：PNG 带 alpha、尺寸与 `image_urls[0]` 一致，**全透明处才会被改** |
| `quality` / `output_format` / `background` / `output_compression` / `num_images` / `moderation` | | | 同文生图 | |

> 文生图 `size` vs 编辑 `image_size` 是这两个 schema 唯一的差异，也是手写 JSON 最容易踩的坑。
> `additionalProperties: false`，传错名字就是 400。`scripts/gpt_image.py` 统一用 `--size`，内部按子命令映射。

---

## 尺寸表

枚举里列的：

| 档位 | 取值 |
|------|------|
| 1K | `1024x1024`（方）、`1536x1024`（横）、`1024x1536`（竖） |
| 2K | `2048x2048`、`2048x1152` |
| 4K | `3840x2160`、`2160x3840` — **超过 2560x1440 官方标注为实验性** |
| 自动 | `auto`（模型自己挑） |

**自定义尺寸**：schema 的 enum 里还有一个 `custom`，但实测**直接写 `WIDTHxHEIGHT` 就能用**
（2026-09-18 实测 `size: "1920x1088"` → 成功，产物 IHDR 确认就是 1920×1088）。约束：

- 两边都是 **16 的倍数**
- 最长边 ≤ **3840px**
- 宽高比在 **1:3 – 3:1** 之间
- 总像素 **655,360 – 8,294,400**

不满足就 400。常用的合法值：`1920x1088`（≈16:9，1080 不是 16 的倍数，要凑到 1088）、
`1088x1920`（竖版短视频）、`1440x1440`。

---

## 计价（实测）

目录里 `cost` 是 `usage_based` 且 `amount/min/max` 全为 `null`（"Usage-based pricing"），
**事前问不出单价**，只能事后从预测的 `metrics.cost` 读。实测样本：

| 配置 | 耗时 | 结算成本 |
|------|------|----------|
| flare / text-to-image / `quality=low` / 1024x1024 | 7.5s | **$0.00615** |
| flare / text-to-image / `quality=low` / 1920x1088 | 9.7s | **$0.004515** |

注意第二行比第一行**便宜**——计价按 token 走，不跟像素数单调相关，别用分辨率去估价。
`quality` 才是成本的主要旋钮（`xhigh`/`max` 官方明说更贵）。

每次预测跑完，`GET /v1/prediction/{id}` 的 `metrics` 里有 `predict_time` 与 `cost`，
`gpt_image.py` 会把这两个值打到 stderr。

---

## 返回值形状（有坑）

目录 `output_type` 写的是 `array`，但 **`num_images=1` 时 `output` 实测是一个字符串**，不是数组：

```json
{ "status": "success",
  "output": "https://cdn-us.eachlabs.ai/uploads/a036c0fc-....png",
  "metrics": { "predict_time": 7.498207, "cost": 0.00615 } }
```

写解析代码时两种都要兜住（上游那份 v2 skill 直接写"output（URL 数组）"，照抄会炸）。
`gpt_image.py` 的 `output_urls()` 已经同时处理 str / list / dict。

产物 URL 落在 `cdn-us.eachlabs.ai`，公开可读（链接即权限），默认保留 180 天。

---

## 状态机

`GET /v1/prediction/{id}` 的 `status`：

| 值 | 含义 | 该做什么 |
|----|------|----------|
| `created` | 排队中，还没开跑 | 继续轮询 |
| `starting` | 正在初始化 | 继续轮询 |
| `processing` | 模型在跑 | 继续轮询 |
| `success` | 成功 | 读 `output` |
| `error` | 失败 | 读 `logs` / `output` 里的错误信封 |
| `cancelled` | 被取消 | — |

取消：`POST /v1/prediction/{id}/cancel`（尽力而为，不保证真能打断上游）。

同步接口 `POST /v1/prediction/run`（提交即等结果）只对"开了同步执行"的模型有效，
GPT Image v2.5 **未验证**是否在列，不在列会回 400。默认还是走异步 + 轮询。
