# 提示词配方 — 把「需求」写成「结构化 spec」

稳定生图 = **强制真工具** + **结构化提示词** + **明确产出路径**。脚本管第一和第三项；这份文件管第二项：CC 怎么把用户一句话需求，翻成一份高质量、可复现的提示词 body。

## 结构化 spec（核心模板）

按需取用，不是死表。**已经很具体的需求只做规整，不要乱加东西**；笼统的需求才补细节，且只补能实质提升质量的。

```text
Use case: <下方分类 slug>
Asset type: <这张图用在哪，如 landing hero / 公众号头图 / 产品详情页>
Primary request: <用户的核心诉求，原话保留>
Scene/backdrop: <环境/背景>
Subject: <主体>
Style/medium: <照片 / 扁平插画 / 3D / 水彩 / 像素…>
Composition/framing: <景别与构图：广角/特写/俯视；主体位置；留白>
Lighting/mood: <光线 + 氛围>
Color palette: <配色>
Materials/textures: <材质/质感>
Text (verbatim): "<图上要出现的精确文字，逐字>"
Constraints: <必须保留 / 必须做到>
Avoid: <负面约束：不要 logo / 不要水印 / 不要文字…>
```

要点：
- **场景→主体→细节→约束** 的顺序写。
- 写明**用途**（广告/UI/信息图）来定调性和精细度。
- 照相写实多用**相机/构图语言**（如 `85mm, shallow depth of field, soft studio light`）。
- 文字要逐字引号给出，并指定字体感觉和位置；难词逐字母拼。
- 编辑类每轮重申不变量。

## 用途分类 slug（保持一致）

生成类：
- `photorealistic-natural` 真实生活/编辑感场景
- `product-mockup` 产品/包装/电商图
- `ui-mockup` 界面/线框（注明精细度）
- `infographic-diagram` 信息图/图解（有结构和文字）
- `scientific-educational` 教学/科普图解（带标注）
- `ads-marketing` 广告创意（受众+品牌+场景+精确文案）
- `productivity-visual` 幻灯/图表/商务可视化
- `logo-brand` logo/标记探索
- `illustration-story` 漫画/绘本/叙事插画
- `stylized-concept` 风格化概念/3D 渲染
- `historical-scene` 时代准确的世界知识场景

编辑类：
- `text-localization` 替换图内文字保版式
- `identity-preserve` 试穿/人物入景，锁脸/体/姿
- `precise-object-edit` 增删改某个元素
- `lighting-weather` 只改时间/季节/氛围
- `background-extraction` 透明背景/切图（走 `--transparent`）
- `style-transfer` 套用参考风格换主体
- `compositing` 多图合成
- `sketch-to-render` 线稿转写实

## 样例

### 落地页 hero（产品照）
```text
Use case: product-mockup
Asset type: landing page hero
Primary request: a minimal hero of a single ceramic pour-over coffee set
Style/medium: clean product photography
Composition/framing: wide composition, large negative space on the right for headline copy
Lighting/mood: soft morning studio light, calm and premium
Color palette: warm neutrals, off-white backdrop
Constraints: no logo, no text, no watermark
```

### 扁平插画（PPVI 浅色调）
```text
Use case: stylized-concept
Asset type: feature illustration on a light web section
Primary request: an abstract illustration of "a prompt turning into a picture"
Style/medium: clean flat vector-like illustration, soft long shadows
Composition/framing: centered, generous padding
Lighting/mood: bright, airy, minimal
Color palette: warm grays as base, one muted amber accent, light background
Constraints: no text, no watermark; cohesive with a light minimalist UI
```

### 精确编辑（只换背景）
```text
Use case: precise-object-edit
Asset type: product photo background swap
Primary request: replace only the background with a warm sunset gradient
Constraints: change only the background; keep the product and its edges unchanged; no text; no watermark
```

## PPVI 浅色配图小抄（给本项目的网页配图用）

- 底色浅（off-white / 浅灰），不要深色重底。
- 灰阶为基 + **一个**克制暖色点缀，别花。
- 留白充足、构图干净、玻璃/柔光质感。
- 不要图上文字（文字交给 HTML 排版），`Avoid: any text, watermark, logo`。
- 风格统一：同一批配图给同样的 `Style/medium` 和 `Color palette`。
