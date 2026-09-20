# 故障排查

本文的结论全部来自对 `gpt-image-v2-5-flare-*` 的**实测**，不是从文档抄的：
**2026-09-18** 的接口摸底（账户余额 $8.63）+ **2026-09-20** 的一次 16 张成套交付。
实测样本见文末「验证记录」。成套出图的工作流另见 [batch-recipes.md](batch-recipes.md)。

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
python3 scripts/eachlabs.py schema flare
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

**③ 批量出图时，调间隔是白费劲，充值才是解法（2026-09-20 实测）。** 上面那条"停手等 1–2 分钟"
对补一两张图够用，对连出 14 张不够用——而且**严格顺序单发也救不了**：

| 余额 | 发法 | 结果 |
|------|------|------|
| $5.94 | 顺序单发，间隔 45s | 429 |
| $5.94 | 顺序单发，间隔 90s | 429 |
| $5.94 | 循环内隔 150s 重试 | 429 |
| $5.94 | 停手约 120s，再单发一次 | 200 |
| **$25.75** | **顺序单发，间隔 15s，连发 7 张** | **零拒绝** |

也就是说在飞数为 0、间隔 90 秒仍然会被拒——闸门统计的不是"此刻在飞几个"，
把 `--gap` 从 45 调到 90 再调到 180 纯属浪费时间。**余额过 $10 这条限制直接消失**，
文档里那句"balance of $10.00 or less"是字面意义上的开关。
所以成套出图前先 `eachlabs.py balance` 看一眼；不够就充，比调参省事得多。
批量脚本仍然要能续跑，见 [batch-recipes.md](batch-recipes.md#3-批量脚本的四条骨架)。

排查有没有真的卡住的在飞任务：

```bash
curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" "https://api.eachlabs.ai/v2/executions?limit=20" \
  | python3 -c "import json,sys; [print(e['status'],'|',e.get('model'),'|',e.get('created_at')) for e in json.load(sys.stdin)['executions']]"
```

## 连接断了，不是被限流（最容易误诊的一条）

```
网络不通: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
```

`api.eachlabs.ai` 与 `oauth2.googleapis.com` 这类上游都会不定时掐连接。**它和 429 长得像
（都是"这次没成"），处置却完全相反**：断连值得立刻重试一次，429 重试等于把闸门按住。
2026-09-20 那次批量里就有两轮被当成限流白等了。

判别只能看错误文本，脚本里这样分流：

```python
blob = proc.stderr + proc.stdout
if "429" in blob:
    stop()                                    # 停手，别重试
elif any(s in blob for s in ("网络不通", "SSL", "EOF", "URLError", "timed out")):
    time.sleep(10); retry_once()              # 断连，重试一次
else:
    fail(blob)                                # 真错误，原样抛出
```

`eachlabs.py` 自身的 HTTP 层已经对断连重试；这段是给**外层批量脚本**用的，
因为它看到的只是子进程的退出码和输出。

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

`scripts/eachlabs.py` 的 `--image` / `--mask` 传本地路径会自动走完这两步。

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

**alpha 是真的，但"背景干净"不是白送的。** 模型照样会在主体后面画一张圆角卡片、一块地面
或一片投影，参数挡不住，要在提示词里点名不要：

```
Single centred object filling the frame, NOTHING else.
Completely transparent background, no backdrop, no ground, no shadow plane,
no rounded-square card behind it.
```

> 和 `codex-image` 的差别要记牢：那边的 `--transparent` 是出 `#00ff00` 绿幕再本地抠，
> 所以有"主体不能含绿色"的硬约束；**这里是原生 RGBA，没有这条约束**。

## 局部重绘（inpaint）没按预期改

`mask_url` 的规则容易记反：

- PNG，**带 alpha 通道**
- 尺寸必须和 `image_urls[0]` **完全一致**
- **全透明的区域才是要被改的地方**，不透明的区域保持原样

蒙版只作用在第一张源图上。

## 成本对不上预期

事前问不出单价：`GET /v1/models/<slug>` 的 `cost` 是
`{"type":"usage_based", "amount":null, "min":null, "max":null}`。只能事后读实际结算值，
而**两个端点给的是同一个数字、字段名却不一样**——这是查账时最容易卡住的地方：

| 端点 | 单价字段 | 耗时字段 |
|------|----------|----------|
| `GET /v1/prediction/{id}`（单条） | `metrics.cost` | `metrics.predict_time` |
| `GET /v2/executions?limit=N`（列表） | **`execution_cost`**（顶层） | **`run_time`**（顶层） |

列表端点**没有** `metrics` 字段，拿 `metrics.cost` 去读会全得 `None`，看起来像"平台不给成本"。
查一批账走列表端点，别一条条查：

```bash
curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" "https://api.eachlabs.ai/v2/executions?limit=200" \
 | python3 -c "
import json,sys,statistics as st
ex=[e for e in json.load(sys.stdin)['executions']
    if 'gpt-image' in (e.get('model') or '') and e['status']=='success']
c=[float(e['execution_cost']) for e in ex]
print(f'n={len(c)}  合计 \${sum(c):.3f}  中位 \${st.median(c):.5f}')
"
```

实测汇总（`flare` / `quality=low` / 1024×1024 为主，n=94，2026-09-18 ~ 09-20）：

| | n | 单价 min / 中位 / max | 耗时 min / 中位 / max |
|---|---|---|---|
| 文生图 | 34 | $0.00594 / **$0.00664** / $0.00795 | 6.1s / **9.3s** / 15.0s |
| 编辑 | 60 | $0.01581 / **$0.02837** / $0.06160 | 9.1s / **20.0s** / 27.2s |

三条经验：

- **分辨率不是成本主因。** 1920×1088 实测比 1024×1024 还便宜（$0.0045 vs $0.0062），
  按 token 结算、不跟像素数单调相关。`quality` 才是主旋钮。
- **编辑是文生图的 ~4 倍贵、~2 倍慢**（中位 $0.028 vs $0.0066，20.0s vs 9.3s），最贵的一次 10 倍。
  源图要当输入 token 吃进去，改得越多越贵。能用文生图重出就别用编辑改。
- **`low` 的成品经常直接能用。** 2026-09-20 那 16 张商店图标/素材全是 `low`，一张没返工，
  总共约 $0.11。先 `low` 定构图仍然是对的，但别默认"`low` 只是草稿"。

---

## 验证记录（2026-09-18，接口摸底）

- 四个 slug 的 `request_schema` 从 `GET /v1/models/<slug>` 实时拉取
- `gpt-image-v2-5-flare-text-to-image`：低画质 1024×1024 成功，图上 "EACHLABS 2.5" 文字渲染无瑕疵
- 自定义尺寸 `1920x1088` 提交成功，产物 IHDR 实测就是 1920×1088
- `background=transparent` + `-n 2`：两张都是 RGBA PNG，`output` 是长度 2 的数组
- `gpt-image-v2-5-flare-edit`：本地图经 presign+PUT 上传后送入，换背景成功且主体/文字/角度零漂移
- 上游 `eachlabs/skills` 那份 v2 skill 写的 `GET /v1/model?slug=<slug>` 实测 **404**；
  正确的是 `GET /v1/models/<slug>`
- 累计花费约 **$0.037**

## 验证记录（2026-09-20，16 张成套交付）

- 14 张商店图标 + 2 张应用内素材，`flare` / `quality=low` / 1024×1024，**一张没返工**，约 $0.11
- 429 闸门：$5.94 余额下顺序单发、间隔 45s/90s/150s 均被拒；**充值到 $25.75 后 15s 间隔连发 7 张零拒绝**
- 至少两轮失败实为 `SSL: UNEXPECTED_EOF_WHILE_READING` 断连，被误诊为限流
- `GET /v2/executions?limit=200` 的 `execution_cost` / `run_time` **94/94 有值**，
  与 `GET /v1/prediction/{id}` 的 `metrics.cost` / `metrics.predict_time` 逐位一致
  （抽验 `46bf90cb…`：两处都是 `0.006595` / `9.870955`）
- `--background transparent` 产物经 `-trim +repage -resize x192` 后仍是 `srgba`；
  商店图标经 `-alpha remove -alpha off` 后是 `srgb / alpha=Undefined`
