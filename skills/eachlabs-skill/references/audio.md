# 音频：音效与 BGM

> 本节由原 `sound-effects` skill 并入（上游 [awesome-genmedia/skills](https://github.com/awesome-genmedia/skills)，
> MIT，见本 skill 根目录 `LICENSE`）。并入时删掉了走不通的 each::sense 主路径的展开示例，
> 只保留诊断结论，并补上了实跑验证过的后处理管线。

## 先讲结论：**不要走 each::sense，走标准预测 API**

上游那份 skill 的主路径是 `eachsense-agent.core.eachlabs.run`。
**实测：同一把 key，那个端点回 402 `insufficient_balance`，而标准 API 回 200。**

对照实验（2026-08-13，工作区余额 $10）：

| 请求 | 结果 |
|---|---|
| 有效 key → eachsense agent | **402** Insufficient balance |
| 有效 key → `api.eachlabs.ai` | **200** |
| 故意写错 key → eachsense agent | **401** Invalid API key |

错 key 回 401 说明**认证是通的**，是那个 beta 服务看不到 workspace 余额。
**充值不解决问题** —— 账户本来就有钱。

撞到 402 别去重查 key、别等「额度生效」、别充值，直接走标准 API。

## 模型 —— **别背 slug，现查**

```bash
python3 scripts/eachlabs.py models --output-type audio
```

2026-09-20 实测目录（**与上游旧文档不符，两处都已订正**）：

| 用途 | 模型 | 说明 |
|---|---|---|
| **音效** | `bytedance-seed-audio-1-0` | 纯文本出任意音频。参数长得像 TTS，但实测能出孤立瞬态（1.6 秒文件里一个 0.15 秒的木头敲击声），不是只会念字 |
| **音乐** | `lyria-3-5` | **只吃 `prompt`**（外加可选 `image_urls`）。最简单 |
| **音乐（要人声/歌词控制）** | `minimax-music-03` | 有 `is_instrumental`、`lyrics`、`audio_settings` |

> **两处订正：**
> 1. 上游写的 BGM 模型 **`ace-step-1-5-text-to-music` 已经不在目录里了** —— 照着用会直接失败。
> 2. 上游写「整个目录里出音频的只有三个模型」，**实测是 10 个**。
>
> 这正是「别把 slug 背死在文档里」的理由：目录会变，而文档不会自己更新。

### `duration` / `bpm` 这两个参数**不存在**

旧文档写 `ace-step` 有 `duration` 10–600 秒和可选 `bpm`。
现存的两个音乐模型**逐一查过 `request_schema`，都没有这两个字段**。
想控制长度只能在 prompt 里说，或者出来之后自己剪。

### 音效模型有个好东西：`loudness_rate`

`bytedance-seed-audio-1-0` 吃 `loudness_rate`（−50 到 100）、`pitch_rate`（±12 半音）、
`sample_rate`、`format`，还能给 `reference_audio_urls`（≤3 段）和 `reference_image_url`。

**`loudness_rate` 从源头治「出来太轻」** —— 比事后加增益好，因为加增益会把底噪一起放大。
脚本的 `sfx --loudness` 就是它。

## 后处理不可省 —— 这是**三步**，不是可选项

模型给的是约 1.6 秒、**前后带静音、电平偏低**的 wav。直接上线的后果很具体：

- **前导静音** → 游戏里点一下，要等零点几秒才出声，读作「按钮卡」
- **响度参差** → 一组音效里有的震耳有的听不见（实测一个 −14 dBFS，兄弟文件 0 dBFS）

三步：**掐头去尾** → **归一化到 −1 dBFS** → **转单声道 mp3**。

### 掐静音**不要用 ffmpeg 的 `silenceremove`**

它按**绝对 dB 阈值**判静音，而每次生成的底噪水平都不一样：
同一个 `-50dB` 阈值，有的文件被切过头，有的纹丝不动
（实测：一个留了 0.58 秒尾巴，另一个留了 0.32 秒前导）。

**从采样点自己找内容窗口**：解码成单声道 PCM，找第一个和最后一个超过**峰值 6%** 的采样点，
留几毫秒引入、尾部加个短淡出。

```bash
# START / DUR / GAIN 由采样点算出，不是拍脑袋
ffmpeg -y -ss "$START" -t "$DUR" -i raw.wav \
  -af "volume=$GAIN,afade=t=out:st=$FADE_ST:d=0.03" -ac 1 -b:a 96k out.mp3
```

增益取 `0.9 / peak`（归到 −1 dBFS 附近），**并设上限**（实测取 8 倍）——
否则遇到极轻的素材会把底噪一起放大。

### 素材太轻时：先调 `--loudness`，再改提示词，最后才是加增益

有些提示词出来的东西轻到就算 8 倍增益仍比同组低 14 dB。
这时候放大的是底噪。**重写提示词**：加上
*"clear, close-miked, well recorded, present and clearly audible (not distant or timid)"* 再生成。

## 平台也有 silence / loudness 能力，但**有同一个毛病**

视频处理 API（`eachlabs-video-api`，见 [video.md](video.md) 末节）带两个与本节直接相关的分析能力：

| 能力 | 产出 | 对本节的意义 |
|---|---|---|
| `audio_analysis` | `integrated_lufs`、`true_peak_dbtp`、`sample_peak_dbfs`、`lra`、`flat_factor`、`peak_count` | **比本地算峰值强的地方**：给的是 LUFS 与真峰值。要对齐广播响度标准时用它 |
| `silence_detect` | `{"silences": [{start, end, duration}]}` | 检测静音段 |
| `silence_remove` / `keep_ranges` | 直接切掉 | `silence_detect` 的「动手」那一半 |

**但 `silence_detect` 的 `noise_db` 是绝对 dBFS 阈值**（整数，默认 −30）——
**和上面警告过的 ffmpeg `silenceremove` 是同一个毛病**：每次生成的底噪水平不一样，
一个固定阈值对某些文件切过头、对另一些纹丝不动。

所以：

- **短音效**（1–2 秒、一批几十个）→ 仍然**按采样点自己找窗口**。本地算不花钱、不用上传、不排队。
- **长素材 / 要广播响度** → `audio_analysis` 拿 LUFS 与真峰值值得一用。
- 无论用哪个，**别把绝对 dB 阈值当成可靠判据** —— 换成「相对峰值的比例」才稳。

## 并发：音频这条线**一次只能跑一个**

标准 API 上音频模型的并发是 **1**：上一个还在飞时提交第二个会回 **429
`wait for an active execution to finish before retrying`**。
所以成批生成要**串行**，中间留短暂停顿。

（这与图像/视频的「余额 ≤$10 → 2 个在飞」是同一套闸门机制，只是数字不同。
通用行为见 SKILL.md 的「429 是并发闸门」一节。）

## 提示词

### 公式

```
Generate a sound effect: [是什么] + [材质/质感] + [环境/空间] + [时长]
```

### 音色词表

| 想要 | 写什么 |
|---|---|
| 明亮 | crisp, sharp, metallic, ringing, clear |
| 暗沉 | deep, rumbling, low, muffled, thick |
| 湿（有空间） | reverb, echo, spacious, cavernous, underwater |
| 干（贴耳） | close-mic, tight, no reverb, intimate |
| 失真 | overdriven, gritty, clipped, saturated |
| 干净 | pure, pristine, digital, polished |

### 时长一定要写

```
0.5 秒     点击、提示音
1–3 秒     撞击、转场
5–10 秒    较长的 foley、循环底噪
15–30 秒   环境声床
```

### 分层写法

一条提示词里描述多个元素：

```
"A thunderclap with: initial crack, rolling rumble that
fades over 5 seconds, light rain in the background throughout"
```

## 常见类别与典型时长

| 类别 | 例子 | 典型时长 |
|---|---|---|
| 自然 | 雨、雷、风、鸟、海浪、柴火 | 3–30 秒 |
| 撞击 | 拳击、碎裂、爆炸、闷响 | 0.5–3 秒 |
| 机械 | 启动、换挡、液压、钟摆 | 1–10 秒 |
| UI / 数字 | 提示音、按键、错误、升级 | 0.1–2 秒 |
| Foley | 脚步、衣料、纸张、倒水 | 1–5 秒 |
| 转场 | whoosh、riser、反向镲 | 0.5–3 秒 |
| 科幻 | 激光、跃迁、力场嗡鸣 | 0.5–5 秒 |
| 恐怖 | 地板吱呀、低语、心跳 | 1–10 秒 |
| 卡通 | boing、splat、滑哨 | 0.5–2 秒 |
| 环境 | 咖啡馆、办公室、车流、地铁 | 10–30 秒 |

## 几个容易犯的

- **不写时长** —— 模型自己猜，长度对不上项目
- **太笼统**（「一个很酷的声音」）—— 要写物理细节
- **指望复刻某个版权音效** —— 不可靠，描述特征而不是点名
- **不写环境** —— 出来的声音没有空间感，该写混响、房间大小、距离
- **一条塞太多同时发生的元素** —— 会糊；复杂场景分层单独生成再混
- **直接用原始输出** —— 见上面的后处理三步
- **把 402 当成要充值** —— 先看对照：错 key 回 401，说明 402 不是认证问题

## 参考实现

`flutter_color_squeeze_out` 项目的 `tool/gen_audio.py`：提示词放文件、提交轮询、
按采样点精确掐头去尾、归一化、预算检查，一把梭。
