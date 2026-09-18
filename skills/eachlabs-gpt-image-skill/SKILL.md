---
name: eachlabs-gpt-image-skill
description: 用 each::labs 的预测 API 调 OpenAI GPT Image v2.5 出图与改图，四个 slug（Flare 快款 / Sunburst 高保真款 × 文生图 / 编辑）。Use when 要生成图片、海报、产品图、封面、带精确文字的图，或要按指令改一张已有图（换背景、局部重绘 inpaint、多图合成、保持主体一致），或提到 gpt-image、GPT Image 2.5、gpt-image-v2-5、eachlabs 生图、each::labs 图片 API、EACHLABS_API_KEY 出图。脚本 scripts/gpt_image.py 把提交→轮询→下载一把梭，本地图自动传到 each::storage。NOT for 纯矢量 SVG / 代码能画的图标、走 codex 订阅额度出图（用 codex-image）、音频与视频生成（用 sound-effects）。
---

# GPT Image v2.5（each::labs）

OpenAI 的 GPT Image v2.5，跑在 each::labs 的预测 API 上。异步：**提交 → 轮询 → 从 output 取 URL → 下载**。
凭据只有一个环境变量 `EACHLABS_API_KEY`（已在 `~/.zshrc` 里 export，脚本直接读）。

## 1. 先选 slug（四选一）

| 想要 | slug | 说明 |
|------|------|------|
| 从文字出图，日常 | `gpt-image-v2-5-flare-text-to-image` | **默认选它**。快、质量已经够用 |
| 从文字出图，要极致细节 | `gpt-image-v2-5-sunburst-text-to-image` | 更细，但更慢 |
| 改一张已有图 | `gpt-image-v2-5-flare-edit` | 只动被点名的地方，主体/构图不飘 |
| 改图，要极致细节 | `gpt-image-v2-5-sunburst-edit` | 同上，更细更慢 |

两个档位的**参数完全一样**，只差快慢与精细度。先 Flare，不够再 Sunburst。
完整参数表、尺寸约束、计价与返回值形状见 [references/models.md](references/models.md)。

## 2. 用脚本（推荐）

```bash
S=~/.claude/skills/eachlabs-gpt-image-skill/scripts/gpt_image.py   # 仓库里则是 skills/eachlabs-gpt-image-skill/scripts/gpt_image.py

# 文生图
python3 $S generate "提示词…" --quality low --size 1024x1024 --out ./out

# 改图：本地文件会自动传到 each::storage 再送进去
python3 $S edit "把背景换成清晨的原木工作台，杯子的角度、光影、标签一个字都不要变" \
  --image ./mug.png --quality high --out ./out

# 局部重绘：mask 是 PNG 带 alpha，尺寸与第一张源图一致，全透明处才会被改
python3 $S edit "把这块区域改成一扇开着的窗" --image ./room.png --mask ./mask.png

# 其它
python3 $S upload ./a.png          # 只上传，打印 public_url
python3 $S status <prediction_id>  # 查一个预测
python3 $S balance                 # 查余额
python3 $S schema flare            # 拉实时 schema 与计价（不花钱、不需鉴权）
```

常用开关：`--model flare|sunburst`、`--quality low|medium|high|xhigh|max`、`--format png|jpeg|webp`、
`--background transparent`、`-n 3`、`--no-wait`（只提交，拿 ID 就走）、`--json`（stdout 单行 JSON 便于串联）。

脚本存在的理由，就是下面这四个坑它都替你兜了。

## 3. 四个必知的坑

**① 文生图叫 `size`，编辑叫 `image_size`。** 这是两份 schema 唯一的差异。
`additionalProperties: false`，名字传错直接 400，且错误信息不会告诉你传错了哪个。

**② `output` 的形状跟着出图张数变。** 目录里 `output_type` 一律写 `array`，但实测
`num_images=1`（默认）时是**字符串** `"output": "https://cdn-us.eachlabs.ai/…png"`，
`num_images≥2` 时才是数组。解析两种都要兜住，否则 `output[0]` 会给你一个字符 `h`。
（上游 `eachlabs/skills` 那份 v2 skill 写的"output（URL 数组）"，照抄会炸。）

**③ 编辑的源图必须是公网可达 URL。** 不吃 data-URI，不吃 localhost，不吃本地路径。
本地图走 each::storage 两步上传：`POST /v1/upload/presign` 拿 `presigned_url` + `public_url`，
再把原始字节 `PUT` 上去（`required_headers` 要一字不差带上）。presigned URL 只活 **15 分钟**。
脚本的 `--image` 自动判断：URL 直接用，本地路径先传。

**④ 余额 ≤ $10 时，这个模型只给 2 个并发。** GPT Image v2.5 事前定不了价
（`cost.type=usage_based` 且金额全 `null`），属于平台口中"跑之前算不出钱"的那一类，
并发上限是 **2**（不是固定价模型的 10）。429 的 `details` 会写明数字。
更坑的是**循环重试解不开它、看起来还会一直把它按住**：实测在 0 在飞的情况下每 20–45 秒重试一次，
连撞 7 次 429；停手 89 秒后再发一次就过了。所以撞 429 就**停手等 1–2 分钟**，别写退避重试循环。

## 4. 不想用脚本，直接 curl

```bash
# 提交（version 字段官方已标注 deprecated/ignored，带着无害）
PID=$(curl -s -X POST https://api.eachlabs.ai/v1/prediction \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EACHLABS_API_KEY" \
  -d '{
    "model": "gpt-image-v2-5-flare-text-to-image",
    "input": {
      "prompt": "极简海报，纸质纹理，居中粗衬线大字 \"BREW LAB\"，一只陶瓷杯冒着热气",
      "size": "1024x1536", "quality": "high"
    }
  }' | python3 -c "import json,sys; print(json.load(sys.stdin)['predictionID'])")

# 轮询到终态
until S=$(curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" \
     "https://api.eachlabs.ai/v1/prediction/$PID" \
     | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])"); \
     [ "$S" = "success" ] || [ "$S" = "error" ] || [ "$S" = "cancelled" ]; do sleep 5; done

# 取结果（output 可能是 str 也可能是 list）
curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" "https://api.eachlabs.ai/v1/prediction/$PID" \
  | python3 -c "import json,sys; o=json.load(sys.stdin)['output']; print(o if isinstance(o,str) else o[0])"
```

鉴权官方写 `Authorization: Bearer`，实测 `X-API-Key` 也收（老 skill 里那种写法），跟官方走就行。
不想轮询就传 `webhook_url`，30 秒内回 2xx。

## 5. 提示词要点

- **图上要出字**：把原文用英文双引号裹起来，并点名字体气质（`bold serif` / `条幅粗黑体`）。
  v2.5 的文字渲染很稳——实测 `quality=low` 出的 "EACHLABS 2.5" 卡片一个字符都没糊。
- **构图**：主体、取景、镜头、光线分开写，别堆形容词。
- **写实**：给物理线索（"45° 斜射硬光，边缘衰减柔和"）比写"高质量、大师作品"有用。
- **改图**：把**不许变的东西**写清楚——"杯子的角度、标签朝向、玻璃上的反光保持完全一致，只换背景"。
- **省钱**：`quality=low` 先出草稿定构图，满意了再用同一段提示词跑 `high`/`xhigh`。
  实测 low 的 1024×1024 只要 **$0.006 / 7.5 秒**，而且成品往往已经能直接用。

## 6. 出问题看这里

[references/troubleshooting.md](references/troubleshooting.md)：400 / 401 / 402 / 429、
预测成功但没有图、透明背景出来是黑的、自定义尺寸被拒、上传 403 签名不匹配。
