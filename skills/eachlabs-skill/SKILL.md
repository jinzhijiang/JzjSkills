---
name: eachlabs-skill
description: 用 each::labs 的预测 API 生成**图片 / 视频 / 音频**。图片走 GPT Image v2.5 四个 slug（Flare 快 / Sunburst 细 × 文生图 / 编辑），视频走图生视频（首末帧、时长、分辨率），音频走音效与 BGM。Use when 要出图、海报、产品图、封面、带精确文字的图、图标成套素材；要按指令改图（换背景、局部重绘 inpaint、多图合成、保持主体一致）；要出视频片段或**用图生视频抽帧做帧动画/精灵表**；要出音效、foley、UI 音、环境音、BGM；或提到 eachlabs、each::labs、gpt-image-v2-5、EACHLABS_API_KEY、each::sense。脚本 scripts/eachlabs.py 把提交→轮询→下载一把梭，本地文件自动传 each::storage。NOT for 纯矢量 SVG / 代码能画的图标、走 codex 订阅额度出图（用 codex-image）。
allowed-tools: Bash(python3 *), Bash(curl *), Bash(ffmpeg *), Bash(ffprobe *), Bash(magick *), WebFetch
---

# each::labs

一个平台，三类产出。**所有模型共用同一套机制**：一个 key、异步提交、轮询取结果。
差别只在 slug 与 input schema。

```
          ┌── 图片  GPT Image v2.5（文生图 / 改图）  → references/image.md
EACHLABS ─┼── 视频  图生视频（首末帧 / 时长 / 分辨率）→ references/video.md
          └── 音频  音效 + BGM                        → references/audio.md
```

凭据只有一个环境变量 `EACHLABS_API_KEY`（脚本直接读；本机在 `~/.zshenv`）。

## 先读这一节：三条坑是全平台共有的

下面三条与你做图、做视频还是做音频无关，**每一类都会撞上**。

### ① `output` 的形状会变

目录里 `output_type` 一律写 `array`，但实测**只出一个产物时是字符串**：

```json
"output": "https://cdn-us.eachlabs.ai/….png"     // num_images=1
"output": ["https://…a.png", "https://…b.png"]   // num_images≥2
```

解析两种都要兜住，否则 `output[0]` 会给你一个字符 `h`。
（上游 `eachlabs/skills` 那份 v2 skill 写的「output（URL 数组）」，照抄会炸。）

### ② 429 是**并发闸门**，不是每秒限流 —— 解法是充值，不是调间隔

算不出事前价的模型（`cost.type=usage_based` 且金额全 `null`）在**余额 ≤ $10 时只给 2 个在飞**。
429 的 `details` 会写明数字。两个反直觉的点都是实测：

- **循环重试解不开它，还会一直把它按住**：0 个在飞时每 20–45 秒重试一次，连撞 7 次 429；
  停手 89 秒后单发一次就过。
- **严格顺序单发也不保险**：$5.94 余额下间隔 45s / 90s / 150s 一律被拒；
  **充到 $25.75 后 15s 间隔连发 7 张零拒绝**。

所以：补一两个产物就停手等 1–2 分钟；要连出一整套，先 `balance` 看一眼，不够就充。
**别写指数退避循环，也别花时间调间隔。**

### ③ SSL 瞬断与 429 是两回事，处理方式相反

`[SSL: UNEXPECTED_EOF_WHILE_READING]` 这类是**瞬时**故障，等 15–25 秒就好，不用等两分钟。

但它有个后果要防：**瞬断若发生在轮询阶段，那条预测还在服务端飞着、占着并发位** ——
紧接着的重试会吃 429。所以瞬断之后别立刻重发，等一等；轮询循环本身也要兜住异常，
否则一支已经跑完的片子会因为一次查状态失败而丢掉。

## 脚本

```bash
S=~/.claude/skills/eachlabs-skill/scripts/eachlabs.py   # 仓库内为 skills/eachlabs-skill/scripts/eachlabs.py

# ── 图片 ──
python3 $S generate "提示词…" --quality low --size 1024x1024 --out ./out
python3 $S edit "只换背景，杯子角度与标签一个字不要变" --image ./mug.png --out ./out
python3 $S edit "把这块改成一扇开着的窗" --image ./room.png --mask ./mask.png

# ── 视频（图生视频）──
python3 $S video "她原地跳一次然后落回起点" --first-frame ./pose.png \
    --duration 2 --resolution 720P --out ./jump.mp4

# ── 音频 ──
python3 $S sfx "木栓敲厚木板一下，温暖干燥，0.12 秒" --out ./tap.wav
python3 $S bgm "轻快的农场背景音乐，原声吉他，中速" --out ./bgm.wav
                                   # 注意:两个音乐模型都**没有 duration/bpm**,长度只能在 prompt 里说

# ── 通用 ──
python3 $S upload ./a.png          # 只上传，打印 public_url
python3 $S status <prediction_id>
python3 $S balance
python3 $S schema flare            # 拉实时 schema 与计价（不花钱、不需鉴权）
python3 $S models --output-type video   # 按产出类型筛模型(目录会变,别背 slug)
```

常用开关：`--model`、`--quality low|medium|high|xhigh|max`、`--format png|jpeg|webp`、
`--background transparent`、`-n 3`、`--no-wait`（只提交拿 ID）、`--json`（单行 JSON 便于串联）。

## 三类各自怎么做

| 要做什么 | 读哪份 | 一句话 |
|---|---|---|
| 出图 / 改图 / 成套素材 | [references/image.md](references/image.md) | 四个 slug；文生图叫 `size`、改图叫 `image_size`；透明背景要显式否定衬底 |
| 视频片段 / **帧动画与精灵表** | [references/video.md](references/video.md) | 循环闭合要 `last_frame`，而 **30 个 image-to-video 里只有 2 个有** |
| 音效 / BGM | [references/audio.md](references/audio.md) | 走标准预测 API，不走 each::sense；**后处理不可省** |
| **选哪个模型 / 目录变了怎么办** | [references/choosing-models.md](references/choosing-models.md) | 判据是「有没有你要的旋钮」，不是「哪个更好」 |

完整参数表、尺寸约束、计价与返回值形状见 [references/models.md](references/models.md)。
出问题见 [references/troubleshooting.md](references/troubleshooting.md)。
一次出一整套（共享风格段、可续跑、magick 后处理）见 [references/batch-recipes.md](references/batch-recipes.md)。

## 不想用脚本，直接 curl

```bash
PID=$(curl -s -X POST https://api.eachlabs.ai/v1/prediction \
  -H "Content-Type: application/json" -H "Authorization: Bearer $EACHLABS_API_KEY" \
  -d '{"model":"gpt-image-v2-5-flare-text-to-image",
       "input":{"prompt":"…","size":"1024x1536","quality":"high"}}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['predictionID'])")

until S=$(curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" \
     "https://api.eachlabs.ai/v1/prediction/$PID" \
     | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])"); \
     [ "$S" = "success" ] || [ "$S" = "error" ] || [ "$S" = "cancelled" ]; do sleep 5; done

curl -s -H "Authorization: Bearer $EACHLABS_API_KEY" "https://api.eachlabs.ai/v1/prediction/$PID" \
  | python3 -c "import json,sys; o=json.load(sys.stdin)['output']; print(o if isinstance(o,str) else o[0])"
```

鉴权官方写 `Authorization: Bearer`，实测 `X-API-Key` 也收。
不想轮询就传 `webhook_url`，30 秒内回 2xx。

## 本地文件要先上传

编辑图、图生视频的源图**必须是公网可达 URL** —— 不吃 data-URI、不吃 localhost、不吃本地路径。
两步走 each::storage：`POST /v1/upload/presign` 拿 `presigned_url` + `public_url`，
再把原始字节 `PUT` 上去（`required_headers` 要一字不差带上）。**presigned URL 只活 15 分钟。**
脚本的 `--image` / `--first-frame` 自动判断：URL 直接用，本地路径先传。

## 平台还有别的面，本 skill 只做了直连模型这一面

| 产品 | 是什么 | 本 skill |
|---|---|---|
| **each::api** | 直连模型、异步预测 | ✅ 本 skill 全部内容 |
| **each::video** | `eachlabs-video-api`，**44 个视频处理能力**（剪切/字幕/水印/HLS/sprite/`probe`/`silence_detect`/`audio_analysis`），按秒 `$0.0015` | ⚠️ 见 [video.md](references/video.md) 末节 |
| each::workflows | 多步流水线，带 fallback 与版本 | ❌ |
| each::sense | 自动选模型的 agent 接口 | ⚠️ 只记了 402 诊断（**结论有保质期**，见 audio.md） |
| LLM Router | 300+ LLM 的统一端点 | ❌ |

文档本身有 **MCP 服务**（`docs.eachlabs.ai`），能直接 `rg` / `cat` 官方文档与 OpenAPI —— 
**查 slug、查 schema、查 changelog 走它，比猜快得多**。本页的模型结论就是这么查出来的。

## 一条选型判据

**产出要不要「时间上连贯」？** 要，就走视频；不要，才走图像。

成套图标、海报、单张立绘 → 图像。
帧动画、精灵表、任何「同一个东西在动」→ **视频再抽帧**，理由见 video.md 开头那节。
