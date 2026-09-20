# 怎么选模型，以及目录变了怎么办

> 这份是 2026-09-20 用 each::labs 的 **MCP 文档服务**加 `GET /v1/models` 实查后写的。
> 之前那版 skill 的模型是「我用过哪个就写哪个」，没做过普查 —— 那是不够的。

## 一、判据是**有没有你要的旋钮**，不是「哪个更好」

同一类里几十个模型，靠「哪个质量高」是选不下去的（也没法验证）。
**能验证的是：它的 `request_schema` 里有没有你这次非要不可的那个字段。**

一个实例。做循环帧动画的关键是 `last_frame`（末帧设成与首帧同一张，动作必然收回原位）。
把 30 个 image-to-video 模型的 schema 逐个拉下来看：

| 有 `last_frame` | 结果 |
|---|---|
| `alibaba-wan-3-0-image-to-video` | ✓ |
| `alibaba-wan-3-0-prime-image-to-video` | ✓ |
| **其余 28 个** | **都没有** |

所以「做循环动画用 wan」不是偏好，是**目录里只有这一家**。这种结论只能查出来，
背不出来，也猜不出来。

### 现成的查法

```bash
# 1) 按产出类型列出候选
python3 scripts/eachlabs.py models --output-type video --grep image-to-video

# 2) 把候选的 schema 拉下来,只看你关心的那几个字段
python3 - <<'PY'
import json, urllib.request, concurrent.futures as cf
SLUGS = ["...", "..."]                 # 上一步的输出
KEYS  = ["last_frame", "duration", "fps", "camera_motion", "seed"]   # 你这次非要不可的
def one(s):
    with urllib.request.urlopen(f"https://api.eachlabs.ai/v1/models/{s}") as f:
        return s, (json.load(f).get("request_schema") or {}).get("properties") or {}
with cf.ThreadPoolExecutor(8) as ex:
    for s, p in ex.map(one, SLUGS):
        print(f"{s:46s}", " ".join("✓" if k in p else "·" for k in KEYS))
PY
```

这段跑一次几秒钟，比读任何一份「模型推荐」都可靠 —— **因为它查的是此刻的目录**。

## 二、几条已经查实的选型规则

### image-to-video

| 需求 | 选谁 | 依据 |
|---|---|---|
| **循环闭合**（首末帧同图） | `alibaba-wan-3-0-image-to-video` / `-prime` | 30 个里只有这两个有 `last_frame` |
| **镜头锁死 + 精确帧率** | `ltx-2-5-image-to-video-fast` / `-pro` | 只有 ltx 系有 `camera_motion`（含 `static`）与 `fps`（24/25/48/50） |
| **短片段（<6 秒）** | **不能用 ltx** | `ltx-2-5-*` 的 `duration` 枚举从 **6** 起；wan 从 **2** 起 |

做精灵表要的是「循环闭合 + 2 秒」，两条都指向 wan —— 而 ltx 那个诱人的 `camera_motion: static`
**用不上**，因为它最短 6 秒。镜头只能靠提示词锁（写法见 [video.md](video.md)）。

### 音频

| 需求 | 选谁 |
|---|---|
| 音效 / foley / UI 音 | `bytedance-seed-audio-1-0`（有 `loudness_rate`，从源头治「太轻」） |
| 音乐，只要 prompt | `lyria-3-5` |
| 音乐，要器乐/歌词控制 | `minimax-music-03`（有 `is_instrumental`、`lyrics`） |

**两个音乐模型都没有 `duration` / `bpm`** —— 别照旧文档传。

### 图像

四个 slug 的取舍见 [image.md](image.md)，那边是 `flare`（快）对 `sunburst`（细）的二选一，
没有能力差异，只有快慢。

## 三、计价要按**单位**读，不能记成一口价

`cost.unit` 是 `second` 的模型，价格随时长和分辨率线性涨：

```
alibaba-wan-3-0-image-to-video   $0.05–$0.20 / 秒（随分辨率）
ltx-2-5-image-to-video-fast      $0.09–$0.30 / 秒
ltx-2-5-image-to-video-pro       $0.12–$0.17 / 秒
```

> **一个我自己写错过的地方。** 早先记成「wan $0.20 一支」——那是一支 **2 秒 720P** 的实测总价。
> 照那个数去估 10 秒 1080P 会差一个数量级。**记录实测值时一定连着单位和档位一起记。**

图像模型是 `usage_based` 且事前金额全 `null`（算不出价），这类的并发上限也更低 ——
见 SKILL.md 的「429 是并发闸门」。

## 四、目录变了怎么办

**前提：目录一直在变，而文档不会自己更新。** 已经踩到的两个实例：

- 上游 sound-effects 文档写的 BGM 模型 `ace-step-1-5-text-to-music` **已经不在目录里**，照抄会直接失败
- 它写「出音频的只有三个模型」，实测是 **10 个**
- `GET /v1/model?slug=` 这个路由已被移除（2026-09-14 changelog），正确是 `GET /v1/models/{slug}`

所以别把 slug 背死在文档里。四条可操作的：

### ① 订 changelog

<https://docs.eachlabs.ai/changelog> 带 RSS。模型上下线、路由变更、计价变更都在这里。
本 skill 里凡是写死 slug 的地方，都标了实测日期 —— **日期过老就该重查**。

### ② 定期 diff 目录

```bash
python3 scripts/eachlabs.py models --output-type video  > /tmp/video.now
diff /tmp/video.prev /tmp/video.now
```

关心哪一类就 diff 哪一类。消失的 slug 比新增的更要紧 —— 那是会让线上直接失败的。

### ③ 配 fallback chain（模型挂了自动顶上）

平台支持**直连模型的回退链**：主模型失败时按你指定的顺序试备选，第一个成功的完成原请求。
在 [AI Models](https://www.eachlabs.ai/ai-models) 页面给模型建命名链，
然后在异步预测里加 `"fallback_selector": "你的链名"`。

对「目录变动」的意义：**主模型哪天下线或抽风，请求不会整条失败。**

### ④ 换模型前用 Replay 验，别直接切

平台的 **Replay** 能把过去成功执行的样本在候选模型上重跑，拿**你自己的真实输入**
对比产出与成本，还能设软性成本上限。

这比「读评测再拍板」靠谱得多 —— 评测用的是别人的输入。

## 五、这个 skill 只覆盖了平台的一部分

查文档时发现平台有五个产品面，本 skill（含脚本）只做了第一个：

| 产品 | 是什么 | 本 skill |
|---|---|---|
| **each::api** | 直连模型，异步预测 | ✅ 全部内容 |
| **each::video** | `eachlabs-video-api`，**44 个视频处理能力**（转码/剪切/字幕/水印/HLS/sprite/分析） | ⚠️ 见 [video.md](video.md) 末节 |
| each::workflows | 多步流水线，带 fallback 与版本 | ❌ 未覆盖 |
| each::sense | 自动选模型的 agent 接口 | ⚠️ 只记了它 402 的诊断，见 [audio.md](audio.md) |
| LLM Router | 300+ LLM 的统一端点 | ❌ 未覆盖 |

**关于 each::sense 的一条保留意见**：本 skill 里「它回 402、别用」的结论来自 **2026-08-13**，
是个 beta 服务的临时故障。**这个结论有保质期** —— 真要用之前先拿一次调用验一下，
别当成永久事实。
