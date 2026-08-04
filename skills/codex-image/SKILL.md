---
name: codex-image
description: 用 codex 订阅额度生成/编辑位图图片（照片、插画、产品图、海报主视觉、概念图、纹理、透明切图），走 codex 内置 image_gen 工具，无需 OPENAI_API_KEY、不计 API 费用。Use when 用户要生成图片/配图/插画/产品图/概念图/网页或海报底图、要"用 codex/gpt-image 生图""白嫖订阅额度出图""批量出图变体""把这张图改成…"。NOT for 纯 SVG/矢量图标、用代码/HTML/canvas 能直接画的简单图形、需要精确可编辑文字排版的海报（用 poster-toolkit）。
---

# codex-image

让 Claude Code 稳定地用 **codex 的订阅额度**生成图片：CC 把需求写成结构化提示词，脚本驱动 `codex exec` 调用内置 `image_gen` 工具出图，吃 ChatGPT 订阅额度，**不需要 API key、不计 API 费用**。

## 原理（一张图说清）

```
用户需求
  └─ CC 写成结构化提示词 (references/prompt-recipes.md)
       └─ scripts/codex_image.py
            └─ codex exec --sandbox workspace-write  ← 内置 image_gen 工具
                 └─ 自动存到 $CODEX_HOME/generated_images/<session>/ig_*.png
                      └─ 复制到你指定的 --out，校验是真 PNG
```

订阅额度计费（rate-limit id `codex`），不碰 `OPENAI_API_KEY`。实测 Plus 纯出图：每张 ≈2% 的 5h 窗口 / ≈0.5% 的 7d 窗口 → 约 **50 张/5h、~30 张/天**（周额度封顶，和写代码共用）。

## 稳定生图的三个支点

1. **强制真工具** — 提示词带固定契约头：必须调内置 image_gen，严禁用代码/PowerShell/SVG/canvas 画。脚本自动加，不靠运气。
2. **结构化提示词** — 按 `references/prompt-recipes.md` 的 spec 把需求写清楚（用途→主体→细节→约束），质量才稳。
3. **明确产出 + 校验** — 提示词写死输出绝对路径；脚本在 `generated_images` 兜底定位、复制、解析 PNG 头校验尺寸。

## 前置检查（第一次用先确认）

- `codex --version` 能跑。
- `codex login` 已用 **ChatGPT 订阅账号**登录（不是 API key 模式）——否则不吃订阅额度。
- 细节见 `references/boundaries.md` 的「前置条件」。

## 工作流

### 1. 把需求写成提示词 body

读 `references/prompt-recipes.md`，按结构化 spec 写。原则：
- 用户需求已经很具体 → 只规整，不乱加。
- 笼统 → 补能实质提升质量的细节（构图、光线、用途、配色）。
- 写进一个文件（放 scratchpad），避免 shell 转义。

### 2. 调脚本出图（后台跑，约 30–90 秒/图）

```bash
python "~/.claude/skills/codex-image/scripts/codex_image.py" \
  --out "<绝对输出路径>.png" \
  --prompt-file "<scratchpad/prompt.txt>" \
  --size "1536x1024"
```

- `--size` 见 `references/boundaries.md` 尺寸表（不传则模型自定；尺寸只能靠提示词引导，工具不收尺寸参数）。
- `--workdir` 默认取输出文件所在目录；一般不用传。
- 透明切图加 `--transparent`（色键抠图，需 Pillow，见下）。
- 脚本输出一段 JSON：`ok / out / width / height / bytes / source`。

### 3. 校验（必做，不要直接信「成功」）

看脚本 JSON：
- `ok: true` 且 `width/height` 合理 → 成。必要时把图读出来肉眼看主体/风格/文字对不对。
- `ok: false` → 看 `error` 和 `codex_stdout_tail`：
  - 没产出/模型在问问题 → 提示词更明确，重试一次。
  - 不是有效 PNG / 尺寸极小 → 模型可能用代码画了，重试并强化「严禁代码绘制」。
- 重试**最多一次**就换思路或找用户，别空转烧额度。

## 多图 / 变体

一资产一次调用，每次不同 `--out`（内置工具不能一次出多张）。批量时循环调脚本。**并发安全**：脚本按本次 codex **session-id** 定位产出（`generated_images/<session-id>/`），就算别的 codex session（兄弟 CC 项目 / 桌面 App）同时在生图也只拿自己那张——因为 codex 自己的复制逻辑是「取最新的图」、跨 session 共享会串图（已实证）。另有 courtesy 文件锁礼让旧版进程，等不到也不报错。

## 透明背景切图

`--transparent`：生成纯 `#00ff00` 色键背景 → 脚本调 codex 自带 `remove_chroma_key.py` 抠成 alpha PNG。
- 需要 Pillow：`python -m pip install pillow`。
- 适合边缘清晰的实心主体（图标/贴纸/产品切图）。
- 毛发/烟雾/玻璃/反光等复杂主体色键抠不干净——这类真透明只能走 CLI gpt-image-1.5（要 API key，违背订阅初衷，不做）。详见 `references/boundaries.md`。

## 编辑已有图

内置编辑只作用于 codex 上下文里的图。改本地文件时，提示词要先让 codex `view_image` 加载该文件再改，并逐轮重申不变量（`只改 X，保持 Y 不变`）。脚本默认走生成路径；编辑场景可直接用 `codex exec` 手写提示词，或把编辑指令写进 body 让模型先 view_image 再生成。

## 关键边界（详见 references/boundaries.md）

- 尺寸/分辨率：实测**固定 ~1.57MP**（≈1536×1024，按长宽比重排），最大边 ~1672px——**不是 4K**。doc 里 ≤3840/16倍数那套是 CLI+API 规格，不适用订阅路径。
- 质量：扁平插画↔照相写实都强；**长文字/精确排版不可靠**（用 poster-toolkit）。
- 透明：无原生透明，靠色键抠图。
- 计费：订阅额度，无 API 费用。

## 参考文件

- `references/prompt-recipes.md` — 结构化提示词模板、用途分类、样例、PPVI 浅色配图小抄。
- `references/boundaries.md` — 尺寸/质量/透明/编辑/计费/失败排查/前置条件。
- `scripts/codex_image.py` — 执行器。`--help` 看全部参数；`--print-prompt` 可只打印最终提示词调试。
