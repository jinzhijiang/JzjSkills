# 成套出图与后处理

一次要出**一组**图（成套图标、一屏里并排的几张素材）时，单张出图的经验基本不适用：
失败模式从"这张不好看"变成"**这一组不像一套**"，而 429 闸门会在半路上把批量打断。

本文结论来自 **2026-09-20 一次真实交付**：给一个 Flutter 游戏出 14 张商店图标
（12 成就 + 2 排行榜，两端商店各一份）+ 2 张应用内素材，全部 `flare` / `quality=low` / 1024×1024，
成品**一张没返工**直接上线。样本与命令见文末。

---

## 1. 一致性是提示词的属性，不是模型的属性

别指望"风格描述得差不多"就能出一套。做法是把提示词**切成两段**：

```python
# 共享段：逐字不变地拼到每一条前面
STYLE = (
    "Glossy 3D candy-jelly cartoon game icon, …: "
    "thick plum #4D1748 outlines, cream #FFF8EA highlights, soft pastel candy palette, "
    "smooth rounded shapes with a wet gloss sheen, gentle even studio lighting, subtle soft shadow. "
    "Subject centred, filling about 70% of a square frame, sitting on a plain soft pastel "
    "rounded-square background with a slight vignette. "
    "Flat simple composition, readable at small size. "
    "NO text, NO letters, NO numbers, NO words, NO watermark, NO border frame."
)
SUBJECTS = {
    "all_clear": "A tall golden candy trophy cup with a glossy plum rim, a small red jelly ball resting inside.",
    "combo_chain": "Five golden candy rings linked in a flowing chain curving across the frame, each ring glinting.",
    # …
}
prompt = f"{STYLE}\n\nSubject: {SUBJECTS[key]}"
```

要点：

- **共享段逐字复制，不要每条改几个词**。改了就是另一套风格，而差异在单看一张时看不出来，
  拼成九宫格才暴露。
- 共享段里要同时钉死 **outline 粗细 / 高光色 / 调色盘 / 打光 / 主体占画面比例 / 背景形状**。
  少钉一项，那一项就会在这一套里随机漂。
- **每条主体只描述一个具体物件**，一句话说完。需要一句以上才解释得清的图标，缩到 48px 就废了。
- 有风格锚图就把锚图的配色十六进制值直接写进共享段（上例的 `#4D1748` / `#FFF8EA`），
  比写"糖果色、可爱"有效得多。

## 2. 透明背景要**显式否定**

`--background transparent` 给的是真 alpha（见 [troubleshooting.md](troubleshooting.md#透明背景)），
但模型仍然会自作主张在主体后面画一张圆角卡片、一块地面或一片投影。光靠参数挡不住，
要在提示词里点名不要：

```
Single centred object filling the frame, NOTHING else.
Completely transparent background, no backdrop, no ground, no shadow plane,
no rounded-square card behind it.
```

> **和 `codex-image` 的关键差别**：那个 skill 的 `--transparent` 是生成 `#00ff00` 绿幕再本地抠图，
> 所以它有一条"主体不能含绿色"的硬约束。**这里没有这条约束**——这里出的是原生 RGBA，
> 主体要绿的、要洋红的都随便。
>
> 这条值得单独记，因为迁移时会下意识带上旧约束：本次实际发出去的提示词末尾就多了一句
> `No green.`（可从 `gpt_image.py status <id>` 把原 prompt 读回来核对）。它不但没用，
> 还白白掐掉了一个配色选项。

## 3. 批量脚本的四条骨架

```python
proc = subprocess.run(cmd, capture_output=True, text=True)

# ① 传输错误 ≠ 429。前者值得重试一次，后者重试等于把闸门按住。
for _ in range(2):
    blob = proc.stderr + proc.stdout
    if proc.returncode == 0 or "429" in blob:
        break
    if not any(s in blob for s in ("网络不通", "SSL", "EOF", "URLError", "timed out")):
        break
    time.sleep(10)
    proc = subprocess.run(cmd, capture_output=True, text=True)

if proc.returncode != 0:
    if "429" in proc.stderr + proc.stdout:
        sys.exit("撞闸门了。停手，去充值到 $10 以上，再用 --skip-existing 续跑。")
    sys.exit(f"生成失败\n{proc.stderr}{proc.stdout}")
```

- **① 传输错误会被误判成闸门。** 实测至少两次跑挂在
  `网络不通: [SSL: UNEXPECTED_EOF_WHILE_READING]`，当时按 429 处理、白等了两轮。
  两者的处置完全相反，必须按错误文本分流。
- **② 顺序发，且撞 429 就整个退出**，别在循环里重试——理由见 troubleshooting 的 429 一节。
- **③ 必须可续跑。** 一个 `--skip-existing`（产物已在盘上就跳过）就够了。
  闸门一定会在半路打断 14 张的批量，没有续跑就只能从头再花一遍钱。
- **④ 后台跑批量时，别用 `cmd; echo "EXIT=$?"` 取退出码。** `$?` 是**管道/复合命令里最后一条**的
  退出码——`… | tail` 之后读到的是 `tail` 的 0，一批失败的生成会显示成成功。
  本次就这么误报过一次。实测对照：

  ```bash
  magick montage a.png /does/not/exist.png -tile 2x out.png 2>/dev/null | head -1; echo $?   # → 0（错）
  magick montage a.png /does/not/exist.png -tile 2x out.png >/dev/null 2>&1;      echo $?   # → 1（对）
  ```

## 4. 后处理：两条 magick 配方

出图是 1024×1024 不透明或带 alpha 的 PNG，两种去向的处理**方向相反**，别搞混：

**应用内素材 —— 保住 alpha，裁到内容，压成 WebP**

```bash
magick src.png -trim +repage -bordercolor none -border 6 \
  -resize x192 -quality 92 -define webp:method=6 out.webp
```

`-trim +repage` 把 alpha 包围盒外的空白切掉（不 `+repage` 会留下画布偏移，Flutter 里表现为莫名其妙的留白）；
`-border 6` 补一圈透明边防止缩放时边缘被切；统一按**高**缩放（`x192`）让一排图标基线对齐，宽度各随其形。
实测产物：`168x192` 与 `199x192`，`channels=srgba`，各 ~9KB。

**商店图标 —— 去掉 alpha，压白底**

```bash
magick src.png -background white -alpha remove -alpha off -resize 512x512 out.png
```

**Apple 会拒收带 alpha 的商店图**，而且透明 PNG 在部分渲染面上会变成黑块。
`-alpha remove` 合成到背景色，`-alpha off` 才真正把通道摘掉——**两个都要**，只写前者通道还在。
验证：`magick identify -format '%[channels] %A' out.png` 要给 `srgb Undefined`。

## 5. 拼审图用的接触印相（contact sheet）

出完一套要并排看才能判断"像不像一套"：

```bash
magick montage icons/*.png -font /System/Library/Fonts/Supplemental/Arial.ttf \
  -tile 5x -geometry 200x200+6+6 sheet.png
```

⚠️ **不带 `-font` 时这台机器上必炸**，而且炸得很有迷惑性：

```
montage: unable to read font `' @ error/annotate.c/RenderFreetype/1694.
```

**退出码是 1，但 montage 文件照样正确生成了**（实测 256×128，内容无误）。
所以 `subprocess.run(..., check=True)` 会为一张好图抛异常。

根因是这个 ImageMagick 构建**一个字体都没登记**（`magick -list font | grep -c Font:` → **0**），
而 montage 默认要给每格标文件名。因此：

- `+set label` / `-label ''` / `-pointsize 0` **都不管用**（试过，照样报错）——没有字体可用，不是标签的问题。
- `-font Helvetica` 这种**字族名也不行**，字族查找表是空的。
- **只有绝对字体文件路径有效**：`-font /System/Library/Fonts/Supplemental/Arial.ttf` → `rc=0`，stderr 干净。

---

## 验证记录（2026-09-20）

- 16 张 `flare` / `quality=low` / 1024×1024，全部一次过，无返工
- 单张实测 **$0.0059–$0.0080（中位 $0.0066）/ 6.1–15.0s**（n=34，见 [models.md 计价](models.md#计价实测)）
- 余额 $5.94 时：严格顺序单发，45s / 90s 间隔仍被 429 拒；**充值到 $25.75 后，15s 间隔连发 7 张零拒绝**
- `-trim +repage … -resize x192` 产物实测 `168x192` / `199x192`，`srgba`，8.9KB / 9.4KB
- `-alpha remove -alpha off -resize 512x512` 产物实测 `512x512`，`channels=srgb alpha=Undefined`
- `magick montage` 无 `-font` → `rc=1` + 正确产物；带绝对字体路径 → `rc=0`
