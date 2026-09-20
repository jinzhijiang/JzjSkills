# 视频：图生视频与帧动画

## 先讲一件最反直觉的：帧动画**不要**让图像模型直接画帧表

想做精灵表（一张图里 N×M 格，每格一帧）时，第一反应是让图像模型一次画出整张帧表。
**试过，走不通，而且失败的方式很有信息量。**

帧表里每一格是**各自独立画出来的一张图**。就算角色身份一致、格与格对齐到 0.5px，
格与格之间也**没有物理上的连续性** —— 播起来是「瞬移」，不是「移动」。
开发者的原话是「帧动画不自然，有发抖的感觉」。

这一点**调对齐、调帧时长权重都救不回来**（两样都试过）。它不是精度问题，是原理问题。

图生视频拿**同一张立绘**做动画，帧与帧在时间上本来就连贯。两个白送的好处：

- **身份零漂移** —— 全程是同一张图被动画化，不存在「每格重画」
- **`first_frame = last_frame = 中立立绘`** → **循环天然闭合**，动作必然收回原位

> 一条配套的播放规矩：**按源视频原速播**。源片是 2 秒，就别压成 0.3 秒播。
> 曾把 2 秒的片子播成 0.26–0.9 秒（最快 7.7 倍速），结果同样是「不自然」——
> 「局内反馈要短促」这个直觉对**逐帧画**的动画成立，对**时间采样**来的帧是反的。

## 模型：`last_frame` 决定一切

目录里有 **30 个 image-to-video 模型**。2026-09-20 把它们的 `request_schema` 逐个拉下来看，
**只有两个有 `last_frame`**：

| slug | `last_frame` | `duration` 起点 | `camera_motion` / `fps` | 计价 |
|---|---|---|---|---|
| `alibaba-wan-3-0-image-to-video` | **✓** | **2 秒** | — | **$0.05–$0.20 / 秒**（随分辨率） |
| `alibaba-wan-3-0-prime-image-to-video` | **✓** | 2 秒 | — | 同上量级 |
| `ltx-2-5-image-to-video-fast` | ✗ | **6 秒** | `static` 等 9 项 / 24·25·48·50 | $0.09–$0.30 / 秒 |
| `ltx-2-5-image-to-video-pro` | ✗ | 6 秒 | 8 项 / 24·25·50 | $0.12–$0.17 / 秒 |
| 其余 26 个 | ✗ | — | — | — |

所以**「做循环帧动画用 wan」不是偏好，是目录里只有这一家**。
ltx 那个诱人的 `camera_motion: 'static'` 用不上 —— 它最短 6 秒，做 2 秒循环够不着。
镜头只能靠提示词锁（下一节）。

> **计价按「秒」读，别记成一口价。** 我早先把它记成「$0.20 一支」，
> 那其实是**一支 2 秒 720P** 的实测总价；照那个数去估 10 秒 1080P 会差一个数量级。
> 选型与目录变动的完整办法见 [choosing-models.md](choosing-models.md)。

`alibaba-wan-3-0-image-to-video` 的常用参数（`duration` 枚举 `auto,2,3,…`，`resolution` 为 `480P/720P/1080P`）：

| 参数 | 说明 |
|---|---|
| `first_frame` | 起始帧（公网 URL；本地图脚本会先上传） |
| `last_frame` | 末帧。**做循环动画时设成与 `first_frame` 同一张** |
| `duration` | 秒 |
| `resolution` | `720P` 等 |
| `ratio` | 宽高比 |
| `audio` | 要不要出声轨（做帧动画时关掉） |
| `prompt_extend` | 让服务端扩写提示词。**要精确控制时关掉** |

## 提示词：把「不许变的东西」写死

图生视频最容易坏在**镜头和尺度**上 —— 模型很爱推镜、缩放、加运动模糊，
而这些对帧动画是致命的：角色一会儿大一会儿小，帧表切出来就会「呼吸」。

实测有效的写法是**先写动作，再用整段篇幅否定镜头变化**：

```
The girl jumps straight up once, happily, raising both arms above her head at
the top of the jump, then lands softly back exactly where she started and
returns to her original standing pose.

CRITICAL — HER SIZE ON SCREEN MUST NEVER CHANGE. She never moves closer to or
further from the camera. She does not grow, shrink, scale up or scale down at
any point. Her head, body and proportions stay exactly the same size in every
single frame. There is no dolly, no zoom, no push-in, no perspective change.
This is a flat side-on view, like a 2D game sprite: she only moves UP and DOWN,
never toward or away from the viewer.

The camera is completely locked off and does not move, pan, zoom or shake.
She stays centred and does not drift left or right. Her whole body including
her feet stays inside the frame at all times, even at the top of the jump.

The background must remain a completely flat, uniform, unchanging pure blue for
the entire clip: no lighting changes, no shadows, no gradients, no motion blur
in the background, nothing appears in it, no ground or floor is ever visible.
Only the girl moves.
```

四条各自在防一件事：

1. **尺度** —— 「size on screen must never change」+ 列举所有同义的镜头动作
2. **镜头** —— locked off / no pan / no zoom / no shake
3. **出框** —— 「whole body including her feet stays inside the frame at all times」
   （跳跃动作尤其容易把脚甩出画）
4. **背景** —— 要抠图就让底色**全程恒定**，否则逐帧抠出来的边缘会抖

## 抽帧做精灵表：两条不能破的不变量

### ① 所有行共用**同一个裁切窗口与同一条地面基线**

窗口逐行各算各的，行与行的角色大小、脚底高度就会不同 —— 切换动作时人会突然变大、
或者上下跳一下。窗口必须在**全部片子的全部帧**上统一算。

一个具体的坑：**跳跃那一行的纵向位移会被裁掉**。如果按「这一行的内容包围盒」定窗口，
跳起来的部分正好在窗口外。所以窗口取全局并集，不取逐行。

### ② 对齐用**下半身质心**，不用包围盒中心

包围盒会随手臂动：挥手时手往右上伸，盒向右变宽，按盒居中就把身体往左推 —— **手越抬身体越滑**。
腿脚不随手臂动，拿下半身质心当锚点，身体才钉得住。

实测对比（同一批素材）：

| 对齐方式 | 身体漂移 |
|---|---|
| 按包围盒中心 | **12.5–26 px** |
| 按下半身质心 | **0.5–1.5 px** |

> **这里有个指标读反了的教训。** 按包围盒中心对齐时，「包围盒中心离散度」这个指标
> 读数最漂亮（0.5px）—— 因为那正是它被优化的那个量 —— 而身体实际正被推走 26px。
> **选指标先问：结果变糟时这个数会变大还是变小？答不上来的别用。**

## 一条完整的链

```
立绘母版 ──抠图──> 铺到纯色底的 _input_frame.png
                          │
      prompt_<动作>.txt ──图生视频──> <动作>.mp4（2s / 60 帧）
                          │
                  videos_to_sheet（统一窗口 + 质心对齐）
                          │
                    sprite_sheet.webp
```

**母版是那几支 `.mp4`，不是最终帧表。** 帧表是从它们确定性生成的 ——
随时可以换帧数、换排布重生成，而重跑一支片子要真金白银（2 秒 720P 实测约 $0.20，按秒计）。

参考实现在 `flutter_color_squeeze_out` 项目：
`tool/eachlabs_video.py`（提交轮询下载）、`tool/videos_to_sheet.py`（合表）、
`tool/check_sprite_sheet.py`（按网格切开量对齐）。

## 验收：量之前先想清楚量什么

做完帧表**必查网格线本身**：格边界是不是落在空白处。
曾经出过「头顶飘着一双鞋」——上一排的鞋子漏进了下一排的格子里，
而当时的检查器报「✓ 全部通过」，因为它测的是**格内对齐**，前提假设是网格切对了。

同样地，**四个指标全部没量到「播起来抖」这件事**（包围盒离散、质心离散、
相邻帧差、动作时长分段），其中一个还读反了。装到设备上让人看，比再加第五个指标快。

**指标只能定位，不能判定。**


## 平台自带的视频处理：`eachlabs-video-api`

除了生成，平台还有一个**视频处理 API**（模型 slug `eachlabs-video-api`，**44 个能力**：
转码、剪切、字幕、水印、叠加、HLS/DASH 打包、缩略图与 sprite，外加四个分析能力
`probe` / `scene_detect` / `silence_detect` / `audio_analysis`）。
同一把 key、同一套提交-轮询，按秒计费 `billed_seconds × $0.0015`。

```json
{"model": "eachlabs-video-api",
 "input": {"capability": "trim", "input_url": "…", "params": {"start": 3.0, "duration": 12.5}}}
```

### 和本页的帧表管线是什么关系

有一个 `storyboard_sprites` 能力：**按固定间隔采一帧，打包成一张平铺表 + 一份 WebVTT 索引。**

| | `storyboard_sprites` | 本页的 `videos_to_sheet` 管线 |
|---|---|---|
| 单支片子抽帧打包 | ✅ | ✅ |
| **多支片子共用同一裁切窗口** | ❌ 一次只吃一支 | ✅ 这是不变量① |
| **按下半身质心对齐** | ❌ | ✅ 这是不变量② |
| 网格上限 | `columns`/`rows` **各 ≤20**，超出部分**静默截断** | 无 |

所以它**解决打包，不解决对齐**。做游戏精灵表（多动作、要求角色大小与脚底高度跨行一致）
仍然要本地管线；但只要一支片子、不在意跨片一致性，用它更省事。

`probe` 在这里也有用：`storyboard_sprites` 超格会**静默截断不报错**，
所以按时长算网格之前先 `probe` 一下拿真实时长。
