# 故障排查

本文的结论全部来自 **2026-09-18 对 `gpt-image-v2-5-flare-*` 的实测**（账户余额 $8.63），
不是从文档抄的。实测样本见文末「验证记录」。

---

## 400 —— 入参不合 schema

错误体形如 `{"status":400,"error":"…","details":…}`。按命中概率排：

| 症状 | 原因 | 修 |
|------|------|-----|
| 文生图带了 `image_size` / 编辑带了 `size` | 两份 schema 的分辨率参数名不同，且 `additionalProperties: false` | 文生图用 `size`，编辑用 `image_size`。用脚本就不会错 |
| `background: "transparent"` + `output_format: "jpeg"` | jpeg 没有 alpha 通道 | 换 `png` 或 `webp`。脚本会在发请求前拦下来 |
| 自定义尺寸被拒 | 四条约束之一没满足 | 两边都要是 **16 的倍数**、最长边 ≤3840、宽高比 1:3–3:1、总像素 655,360–8,294,400。比如 16:9 的 1080 不合法（不是 16 的倍数），要写 `1920x1088` |
| 枚举值拼错（`quality: "best"`、`format: "jpg"`） | 只收 schema 里列的字面量 | `quality` 是 low/medium/high/xhigh/max/auto；格式是 `jpeg` 不是 `jpg` |
| 编辑传了本地路径或 data-URI | `image_urls` 只收公网可达 URL | 先传 each::storage，见下面「上传」 |
| prompt 超长 | 上限 32000 字符 | 截断或拆任务 |

拿不准就对一遍线上 schema（不花钱、不需鉴权）：

```bash
python3 scripts/gpt_image.py schema flare
```

## 401 —— 鉴权

`{"error": "Invalid or missing API key"}`。检查 `EACHLABS_API_KEY` 有没有真的进到进程环境里
（`~/.zshrc` 里 export 了，但非交互 shell / 某些沙箱不会加载它）：

```bash
python3 -c "import os; k=os.environ.get('EACHLABS_API_KEY',''); print('len', len(k))"
```

`Authorization: Bearer <key>` 和 `X-API-Key: <key>` **两种写法实测都收**，官方文档写的是前者。

## 402 —— 余额不够

```json
{"status":402,"error":"payment required",
 "details":"the estimated cost of your in-flight executions exceeds your current balance ($1.00) …"}
```

在飞的预测会按**预估成本**预留额度，跑完结算再把差额退回来。所以它说的不是"你没钱了"，
而是"你正在飞的那些加起来超了"。等一个落终态，或者去充值。

> 顺带：`sound-effects` skill 里记的那个"余额充足却回 402"是 **each::sense beta 网关**
> （`eachsense-agent.core.eachlabs.run`）的毛病，和这里用的标准预测 API 无关。

## 429 —— 并发闸门，而且**重试会把它按住**

```json
{"status":429,"error":"too many requests",
 "details":"accounts with a balance of $10.00 or less are limited to 2 concurrent executions…"}
```

两件事要知道：

**① 这个模型只给 2 个并发，不是 10。** 平台按"跑之前能不能算出价"分两档：固定价模型 10 个在飞，
算不出价的 2 个。GPT Image v2.5 的 `cost` 是 `usage_based` 且金额全 `null`，属于后者。
余额涨到 $10 以上这条限制才解除。

**② 循环重试不但解不开，看起来还会一直把闸门按住。** 实测时间线：

| 时刻 | 动作 | 结果 |
|------|------|------|
| 10:27:29 | 提交第 2 个预测 | 200 |
| 10:27:39 | 第 2 个预测已 `success`，账户 **0 在飞** | — |
| 10:27–10:31 | 每 20–45 秒重试提交一次，共 7 次 | **次次 429** |
| 10:31:20 | **停手** | — |
| 10:32:49（停手 89 秒后） | 提交一次 | **200，正常跑完** |

期间 `GET /v2/executions?limit=20` 确认所有历史执行都是 `success`，没有卡住的在飞任务。
所以：**撞 429 就停手，等 1–2 分钟再发一次**，别写退避重试循环——文档自己也写了
"backoff alone does not clear a 429 concurrency cap"。

排查有没有真的卡住的在飞任务：

```bash
curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" "https://api.eachlabs.ai/v2/executions?limit=20" \
  | python3 -c "import json,sys; [print(e['status'],'|',e.get('model'),'|',e.get('created_at')) for e in json.load(sys.stdin)['executions']]"
```

## 预测成功，但代码没拿到图

`output` 的形状**取决于出了几张图**（实测）：

| `num_images` | `output` | |
|---|---|---|
| 1（默认） | **字符串** | `"https://cdn-us.eachlabs.ai/uploads/….png"` |
| ≥2 | **数组** | `["https://…", "https://…"]` |

模型目录里 `output_type` 一律写 `array`，别信它。`isinstance(o, str)` 要单独兜一手，
否则 `output[0]` 会给你字符串的第一个字符 `h`。

## 上传本地图（编辑必经之路）

两步，且第二步的 header 要一字不差：

```bash
# 1) 拿 presigned URL
curl -s -X POST https://api.eachlabs.ai/v1/upload/presign \
  -H "Content-Type: application/json" -H "Authorization: Bearer $EACHLABS_API_KEY" \
  -d '{"content_type":"image/png","file_type":"image"}'
# → {"presigned_url":"…","public_url":"https://cdn-us.eachlabs.ai/uploads/….png","required_headers":{"x-amz-meta-file-id":"…"}}

# 2) PUT 原始字节，required_headers 原样带上
curl -X PUT "$PRESIGNED_URL" -H "Content-Type: image/png" \
  -H "x-amz-meta-file-id: <上一步返回的值>" --data-binary @./photo.png
```

| 症状 | 原因 |
|------|------|
| PUT 回 403 `SignatureDoesNotMatch` | `required_headers` 漏了或改了值；`Content-Type` 与 presign 时申报的不一致 |
| PUT 回 403，且离拿到 URL 已超 15 分钟 | presigned URL 只活 **15 分钟**，重新申请一个 |
| 文件传上去了但模型说取不到 | 确认用的是 `public_url` 而不是 `presigned_url`（后者带签名会过期） |

上限 100MB/文件，默认保留 180 天（`expires_in_seconds` 可调，60 秒 – 365 天）。
`public_url` 里的 id 猜不出来，但**拿到链接的人都能看**——当公开链接对待。

`scripts/gpt_image.py` 的 `--image` / `--mask` 传本地路径会自动走完这两步。

## 透明背景

`background: "transparent"` + `output_format: "png"`（或 `webp`）实测出的确实是
**color_type=6 的 RGBA PNG**，alpha 通道是真的。验证一张图有没有 alpha，不用装 Pillow：

```bash
python3 -c "
import struct,sys
raw=open(sys.argv[1],'rb').read()
w,h,d,c=struct.unpack('>IIBB', raw[16:26])
print(f'{w}x{h} color_type={c}', '带 alpha' if c in (4,6) else '不带 alpha')
" out.png
```

出来是 `color_type=2`（无 alpha）时，先查是不是 `output_format` 落到了 jpeg。

## 局部重绘（inpaint）没按预期改

`mask_url` 的规则容易记反：

- PNG，**带 alpha 通道**
- 尺寸必须和 `image_urls[0]` **完全一致**
- **全透明的区域才是要被改的地方**，不透明的区域保持原样

蒙版只作用在第一张源图上。

## 成本对不上预期

事前问不出单价：`GET /v1/models/<slug>` 的 `cost` 是 `{"type":"usage_based", "amount":null, "min":null, "max":null}`。
只能事后从 `GET /v1/prediction/{id}` 的 `metrics.cost` 读实际结算值。

实测（flare、`quality=low`）：

| 配置 | 耗时 | 结算 |
|------|------|------|
| 文生图 1024x1024 ×1 | 7.5s | $0.00615 |
| 文生图 1920x1088 ×1 | 9.7s | $0.004515 |
| 文生图 1024x1024 ×2（透明背景） | 8.7s | $0.01201 |
| 编辑 1024x1024 ×1（1 张源图） | 11.0s | $0.014372 |

两条经验：**分辨率不是成本主因**（1920×1088 比 1024×1024 还便宜），
**编辑比文生图贵**（源图要当输入 token 吃进去）。省钱就先用 `low` 定构图。

---

## 验证记录（2026-09-18）

- 四个 slug 的 `request_schema` 从 `GET /v1/models/<slug>` 实时拉取
- `gpt-image-v2-5-flare-text-to-image`：低画质 1024×1024 成功，图上 "EACHLABS 2.5" 文字渲染无瑕疵
- 自定义尺寸 `1920x1088` 提交成功，产物 IHDR 实测就是 1920×1088
- `background=transparent` + `-n 2`：两张都是 RGBA PNG，`output` 是长度 2 的数组
- `gpt-image-v2-5-flare-edit`：本地图经 presign+PUT 上传后送入，换背景成功且主体/文字/角度零漂移
- 上游 `eachlabs/skills` 那份 v2 skill 写的 `GET /v1/model?slug=<slug>` 实测 **404**；
  正确的是 `GET /v1/models/<slug>`
- 累计花费约 **$0.037**
