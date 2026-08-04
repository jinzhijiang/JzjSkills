# 能力边界卡 — codex 内置生图

权威来源：codex 自带 `~/.codex/skills/.system/imagegen/SKILL.md` + 本人实测（本卡是面向「CC 调用」场景的浓缩）。走 codex 内置 `image_gen` 工具，吃 ChatGPT/codex 订阅额度。**注意**：具体图像模型版本 codex 未公开；doc 里的 `gpt-image-2` 是 **CLI fallback（要 API key）**那条路的模型，不能等同订阅内置路径。

## 一句话

`codex exec` → 模型调用内置 `image_gen` 工具 → 图片存到 `$CODEX_HOME/generated_images/<session>/ig_*.png` → 复制到你指定路径。**不需要 OPENAI_API_KEY，不计 API 费用，吃订阅额度。** 实测（Plus 账号、纯出图）：每张 ≈ 2% 的 5 小时窗口、≈ 0.5% 的 7 天窗口 → **冲刺约 50 张/5h，天天出约 30 张/天**（周额度是瓶颈）。整数精度估算，当量级看；和写代码共用额度。

## 尺寸与分辨率（实测，别信 4K）

内置工具**不接受尺寸参数**，提示词只能**粗调长宽比**，分辨率它自己定。**实测：固定约 1.57MP（≈ 1536×1024 的像素量），按你要的长宽比重排**——强制要 4K 也没用：

| 你要求 | 实际产出 | 像素量 |
|---|---|---|
| `3840x2160`（4K横） | `1672x941` | ~1.57MP |
| `2304x3456`（4K竖） | `1024x1536` | ~1.57MP |
| `1536x1024` | `1536x1024` | ~1.57MP |
| `1024x1024` | `1254x1254` | ~1.57MP |

- **分辨率上限 ≈ 1.57MP，最大边实测 ~1672px——不是 4K。**
- 长宽比能粗调（16:9 / 2:3 / 1:1 …），但总像素就那么多。
- doc 里 `3840px / 16 的倍数 / ≤3:1 / 0.65–8.3MP` 那套是 **CLI fallback（gpt-image-2 + API key）**的规格，**不适用**订阅内置路径。
- 要真 4K / 精确像素：只能走 CLI fallback（API 计费，违背订阅初衷，本 skill 不做），或生成后自己超分放大（放大 ≠ 原生细节）。

## 质量

- 实测覆盖**扁平插画**和**照相写实**两端，质量高（见 demo）。
- 长宽比能引导，分辨率恒定 ~1.57MP（见上）；需要更大尺寸就生成后超分放大。
- 文字渲染：短文字可行，但**长文字/精确排版不可靠**——需要精确文字排版的海报用 `poster-toolkit`，不要硬塞这里。

## 透明背景

- 内置工具**不支持原生透明背景**。
- 内置方案（本 skill 的 `--transparent`）：生成纯 `#00ff00` 色键背景 → 本地 `remove_chroma_key.py` 抠成 alpha PNG。需要 **Pillow**（`python -m pip install pillow`）。
- 适合：边缘清晰的实心主体（图标、贴纸、产品切图）。
- **不适合**色键抠图：毛发/羽毛/烟雾/玻璃/液体/半透明/反光/柔和阴影。这类要真·透明只能走 CLI `gpt-image-1.5 --background transparent`，但那**需要 OPENAI_API_KEY = API 计费**，违背「吃订阅额度」初衷 → 本 skill 不做，只在此备注。

## 编辑（edit）

- 内置编辑只作用于**已在 codex 对话上下文里的图**（附件图，或本轮先前生成的图）。
- 编辑本地文件：先让 codex `view_image` 加载该文件进上下文，再编辑。
- **不能**对任意文件路径做「盲改」。
- 编辑时每轮都要重申不变量（`只改 X，保持 Y 不变`），减少漂移。

## 多图 / 变体

- 多个**不同**资产：一资产一次调用（脚本调多次，每次不同 `--out`）。
- 同一提示的**变体**：内置路径也是多次调用；不要指望一次出多张。
- **并发安全靠 session-id 定位（实证设计）**：codex 内置工具 / 模型自己的复制逻辑是「取 generated_images 里**最新**的图」、跨 session 共享——裸用会被别的 codex session（兄弟 CC 项目、桌面 App）正在生成的图抢走（实测被并行的另一个项目串过图）。脚本改为按**本次 codex session-id** 定位（`generated_images/<session-id>/`，靠 cwd 匹配 rollout 拿到 session-id），并发也只拿自己那张。另有 `~/.codex/.codex_image.lock` **courtesy 锁**礼让仍用「最新」逻辑的旧版兄弟进程；等不到锁也不报错（session-id 仍正确）。别手动绕开锁去并行。

## 失败模式与排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 没有产出文件 | 模型问问题了 / 拒绝了 / 超时 | 看脚本 JSON 的 `codex_stdout_tail`；加强提示词重试一次 |
| 产出不是 PNG / 尺寸极小 | 模型用代码画了（违约） | 重试，提示词里更强调「严禁代码绘制」 |
| 文件只在 generated_images 没复制出来 | 模型忘了复制 | 脚本已自动兜底复制；正常不会发生 |
| `codex CLI not found` | 没装 / 没登录 | `codex login`，确认 `codex --version` |
| 透明抠图失败 | 没装 Pillow / 主体含绿色 | 装 Pillow；换主体不含 #00ff00 或改用 #ff00ff 色键 |

## 前置条件

- `codex --version` 能跑（已装 codex CLI）。
- `codex login` 已用 **ChatGPT 订阅账号**登录（不是 API key 模式），这样才吃订阅额度。
- codex 的 model 支持 image_gen（默认 config 的 model 即可，实测 `gpt-5.x` 系列可用）。
