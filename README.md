# JzjSkills

常用 Skills 整理，通过 Git 统一管理和复用。

## 目录结构

每个 skill 是 `skills/` 目录下的一个子目录，目录名即 skill 名称：

```
JzjSkills/
├── skills/                              # 所有 skill 存放于此目录
│   ├── gh-cli/
│   │   └── SKILL.md                     # skill 定义文件（必需）
│   ├── java-springboot/
│   │   └── SKILL.md
│   ├── flutter-use-http-package/        # flutter-* 系列均为单文件 skill
│   │   └── SKILL.md
│   ├── spring-testing-fundamentals/
│   │   ├── SKILL.md
│   │   └── references/                  # 部分 skill 附带参考文档，需一并保留
│   │       └── *.md
│   ├── test-device-allocator/           # 自建：并发测试设备分配与互斥锁
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   ├── references/                  # cli.md、troubleshooting.md
│   │   └── scripts/device_lock.py       # python3 标准库
│   ├── countly-data-analysis/           # 自建：自建 Countly 的 Read API 查询与埋点对账
│   │   ├── SKILL.md
│   │   ├── config.example.env           # 凭据模板，按项目放到 ~/.config/ai-ignore-config/<项目名>/
│   │   └── scripts/countly_query.sh     # bash + curl + python3
│   ├── git-cz/                          # 自建：统一所有项目的提交信息风格
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   ├── assets/changelog.config.js   # 全局配置模板
│   │   ├── references/                  # config、cli、troubleshooting
│   │   └── scripts/check_commit_msg.py  # python3 标准库，提交前自检 / commit-msg 钩子
│   ├── chrome-file-upload-bridge/       # 自建：绕开 MCP file_upload 限制往网页传文件
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   └── scripts/cors_server.py       # python3 标准库，带 CORS + PNA 头的本地静态服务
│   ├── springboot-jpa/                  # 自建：Spring Boot JPA 生产代码模式
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   └── references/                  # 实体、关联、查询、事务、性能 5 个文件
│   ├── codex-image/                     # 外部引入：用 codex 订阅额度生图
│   │   ├── SKILL.md
│   │   ├── LICENSE                      # MIT，随上游一并保留
│   │   ├── references/                  # prompt-recipes、boundaries
│   │   └── scripts/codex_image.py       # python3 标准库，驱动 codex exec 出图
│   ├── eachlabs-skill/                  # 自建：each::labs 的图 / 视频 / 音频三类产出
│   │   ├── SKILL.md                     # 路由 + 三条全平台共有的坑
│   │   ├── LICENSE                      # 并入的 sound-effects 带来的上游 MIT
│   │   ├── references/                  # image / video / audio / choosing-models / models / troubleshooting / batch-recipes
│   │   ├── agents/openai.yaml
│   │   ├── references/                  # models.md（四个 slug 参数表）、troubleshooting.md
│   │   └── scripts/eachlabs.py         # python3 标准库，提交→轮询→下载，本地图自动上传
│   ├── aliyun-oss-ossutil/              # 外部引入：阿里云 OSS ossutil 2.0 命令行
│   │   ├── SKILL.md
│   │   ├── LICENSE                      # MIT，取自上游仓库根目录
│   │   ├── agents/openai.yaml
│   │   ├── references/                  # install.md、sources.md
│   │   └── scripts/check_ossutil.py     # python3 标准库，校验前置条件并留存证据
│   ├── patrol-setup/                    # 外部引入：Patrol E2E 三件套，均为单文件 skill
│   │   └── SKILL.md
│   └── …（spring-mvc-testing … 等 spring-* 结构同上；
│           patrol-write-test、patrol-test-architecture 与 patrol-setup 同为单文件；
│           另有 13 个 flutter-* skill（10 个 Flutter 官方 + 3 个自建），
│           其中 flutter-setup-firebase-crashlytics 含 references/ 与 agents/）
├── scripts/
│   └── update_skills.py                 # 统一同步外部 skill（python3 标准库）
├── patches/                             # 外部 skill 的本地适配，同步后自动重打
│   └── aliyun-oss-ossutil.patch
├── skills-upstream.json                 # 外部 skill 的上游清单（脚本读写）
└── README.md
```

## 添加 Skill

1. 在 `skills/` 目录下创建以 skill 名称命名的子目录
2. 在该目录中创建 `SKILL.md`，写入 skill 的前置说明（frontmatter + 指令）
3. 提交到 Git

示例 `SKILL.md`：

```markdown
---
name: my-skill
description: 简短描述这个 skill 做什么
---

具体的指令内容...
```

## 来源表

记录每个 skill 的来源，方便日后回溯与更新。外部引入的 skill 一律**原样引入、不做本地改动**，以便下载新版后直接用 `git diff` 对比同步。

| Skill | 来源 | 源地址 | 许可证 | 引入日期 | 备注 |
|-------|------|--------|--------|----------|------|
| `gh-cli` | 自建 / 内部整理 | — | — | — | 无外部上游，自行维护 |
| `java-springboot` | [github/awesome-copilot](https://github.com/github/awesome-copilot) | [skills/java-springboot/SKILL.md](https://github.com/github/awesome-copilot/blob/main/skills/java-springboot/SKILL.md) | MIT | 2026-07-01 | 原样引入，未修改内容 |
| `spring-testing-fundamentals` | [spring-ai-community/spring-testing-skills](https://github.com/spring-ai-community/spring-testing-skills) | [skills/spring-testing-fundamentals/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-testing-fundamentals) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（2 个文件） |
| `spring-mvc-testing` | 同上 | [skills/spring-mvc-testing/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-mvc-testing) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（1 个文件） |
| `spring-webflux-testing` | 同上 | [skills/spring-webflux-testing/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-webflux-testing) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（1 个文件） |
| `spring-jpa-testing` | 同上 | [skills/spring-jpa-testing/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-jpa-testing) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（4 个文件） |
| `spring-security-testing` | 同上 | [skills/spring-security-testing/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-security-testing) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（1 个文件） |
| `spring-websocket-testing` | 同上 | [skills/spring-websocket-testing/](https://github.com/spring-ai-community/spring-testing-skills/tree/main/skills/spring-websocket-testing) | Apache-2.0 | 2026-07-01 | 原样引入；含 `references/`（1 个文件） |
| `flutter-add-integration-test` | [flutter/skills](https://github.com/flutter/skills)（Flutter 官方） | [skills/flutter-add-integration-test/](https://github.com/flutter/skills/tree/main/skills/flutter-add-integration-test) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-add-widget-preview` | 同上 | [skills/flutter-add-widget-preview/](https://github.com/flutter/skills/tree/main/skills/flutter-add-widget-preview) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-add-widget-test` | 同上 | [skills/flutter-add-widget-test/](https://github.com/flutter/skills/tree/main/skills/flutter-add-widget-test) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-apply-architecture-best-practices` | 同上 | [skills/flutter-apply-architecture-best-practices/](https://github.com/flutter/skills/tree/main/skills/flutter-apply-architecture-best-practices) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-build-responsive-layout` | 同上 | [skills/flutter-build-responsive-layout/](https://github.com/flutter/skills/tree/main/skills/flutter-build-responsive-layout) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-fix-layout-issues` | 同上 | [skills/flutter-fix-layout-issues/](https://github.com/flutter/skills/tree/main/skills/flutter-fix-layout-issues) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-implement-json-serialization` | 同上 | [skills/flutter-implement-json-serialization/](https://github.com/flutter/skills/tree/main/skills/flutter-implement-json-serialization) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-setup-declarative-routing` | 同上 | [skills/flutter-setup-declarative-routing/](https://github.com/flutter/skills/tree/main/skills/flutter-setup-declarative-routing) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-setup-localization` | 同上 | [skills/flutter-setup-localization/](https://github.com/flutter/skills/tree/main/skills/flutter-setup-localization) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-use-http-package` | 同上 | [skills/flutter-use-http-package/](https://github.com/flutter/skills/tree/main/skills/flutter-use-http-package) | BSD-3-Clause | 2026-07-01 | 原样引入，仅含 `SKILL.md` |
| `flutter-setup-firebase-crashlytics` | 自建 / 内部整理 | [Firebase Flutter 官方文档](https://firebase.google.com/docs/flutter/setup) | — | 2026-07-18 | 自建；默认完整接入 Firebase Core、Google Analytics 与 Crashlytics，并要求设备上报验证和临时崩溃入口清理 |
| `flutter-use-fvm` | 自建 / FVM 官方文档整理 | [FVM Documentation](https://fvm.app/documentation/getting-started/overview) | — | 2026-07-18 | 自建；强制 Flutter/Dart 命令通过 `fvm flutter` / `fvm dart` 执行，并按需覆盖完整配置、命令、IDE/CI 与故障排查 |
| `git-cz` | 自建 / 基于 [streamich/git-cz](https://github.com/streamich/git-cz) 整理 | [streamich/git-cz](https://github.com/streamich/git-cz)（npm `git-cz@4.9.0`，Unlicense） | — | 2026-08-04 | 自建；统一所有项目的提交信息风格：消息契约、`assets/changelog.config.js` 全局模板、`scripts/check_commit_msg.py`（python3 标准库，无 node 也能校验，可装成 commit-msg 钩子） |
| `codex-image` | [xntj-ai/codex-image](https://github.com/xntj-ai/codex-image) | [仓库根目录即 skill](https://github.com/xntj-ai/codex-image) | MIT | 2026-08-04 | 原样引入（上游 `9b4e0bc`）；仓库根目录本身就是 skill，取 `SKILL.md` + `references/`（2 个文件）+ `scripts/codex_image.py`，并保留 `LICENSE`；未引入上游 `README.md`、`.gitignore` |
| `patrol-setup` | [leancodepl/patrol](https://github.com/leancodepl/patrol)（Patrol 官方） | [skills/patrol-setup/](https://github.com/leancodepl/patrol/tree/master/skills/patrol-setup) | Apache-2.0 | 2026-08-04 | 原样引入（上游 `cf2a783`，主分支为 `master`），仅含 `SKILL.md`；Flutter 项目首次接入 Patrol（仅覆盖 Android） |
| `patrol-write-test` | 同上 | [skills/patrol-write-test/](https://github.com/leancodepl/patrol/tree/master/skills/patrol-write-test) | Apache-2.0 | 2026-08-04 | 原样引入，仅含 `SKILL.md`；此前已在 `~/.cc-switch/skills` 中（2026-07-17 装入），内容与上游一致，本次纳入仓库管理 |
| `patrol-test-architecture` | 同上 | [skills/patrol-test-architecture/](https://github.com/leancodepl/patrol/tree/master/skills/patrol-test-architecture) | Apache-2.0 | 2026-08-04 | 原样引入，仅含 `SKILL.md`；同上，此前已装入本机，本次纳入仓库管理 |
| `aliyun-oss-ossutil` | [cinience/alicloud-skills](https://github.com/cinience/alicloud-skills) | [skills/storage/oss/aliyun-oss-ossutil/](https://github.com/cinience/alicloud-skills/tree/main/skills/storage/oss/aliyun-oss-ossutil) | MIT | 2026-08-04 | 引入上游 `b22dc0a`；上游按 `storage/oss/` 分层存放，这里拍平为 `skills/aliyun-oss-ossutil/`，因此改了两处写死的旧路径（`SKILL.md` 的校验命令、`scripts/check_ossutil.py` 改为按 `__file__` 自定位），其余原样；`LICENSE` 取自上游仓库根目录 |
| `countly-data-analysis` | 自建 / 内部整理 | — | — | 2026-08-05 | 自建；原在 `flutter_todo/.agents/skills/`，因笔笔记账也接入 Countly 而收拢到这里并去项目化：凭据按 **git 根目录名**解析（`~/.config/ai-ignore-config/<项目名>/countly.env`），避免从 A 项目静默查到 B 项目的数据；`scripts/countly_query.sh` 提供 list / event / range / views / crash / summary |
| `publish-app-huawei` | — | — | — | 2026-09-03 | **已迁出**：与 flutter_todo 里那份合并后移到独立仓库 [publish-app-skills](https://github.com/jinzhijiang/publish-app-skills)，与其余 11 个应用市场发版 skill 一起管理 |
| `chrome-file-upload-bridge` | 自建 / 内部整理 | — | — | 2026-08-10 | 自建；从笔笔记账上架 OPPO 的实操中提炼：MCP `file_upload` 对 <10MB 的文件会吞掉 `paths` 参数、>10MB 又撞它自己的 10MB 上限，computer-use 对浏览器只给 read 权限点不了系统文件框，三者叠加等于不可用。解法是本地起 `scripts/cors_server.py`（带 `Access-Control-Allow-Private-Network`，否则 HTTPS 页面发往 127.0.0.1 的请求会永远 pending），再用 `javascript_tool` 执行 `fetch → new File → DataTransfer → dispatch change` 注入，字节不过 MCP 桥所以没有体积上限；含首次放行提示、顶层 `await` 撞 45s CDP 超时的规避、注入后 `input.files` 被组件清空属正常等坑 |
| `test-device-allocator` | 自建 / 内部整理 | — | — | 2026-08-07 | 自建；多项目并发 AI 测试的真机/模拟器分配与互斥锁：`scripts/device_lock.py`（python3 标准库，acquire/wake/release/status/clean），锁注册表 `~/.ai-device-locks/`，无空闲设备时自动新建 Android/iOS 模拟器；支持把已连接的 HarmonyOS 真机/模拟器纳入分配池（`--platform android,harmony`）；acquire 会亮屏解锁并把**真机**自动锁屏放宽到 10 分钟（`--screen-timeout` 可调），release 还原原值并熄屏落锁，长时间无人值守才显式用 `--keep-awake` |

| `springboot-jpa` | 自建 / 综合多方整理 | [vibeeval jpa-patterns](https://github.com/vibeeval/vibecosystem/blob/main/skills/jpa-patterns/SKILL.md)、[Amplicode spring-data-jpa](https://github.com/Amplicode/spring-skills/tree/main/skills/spring-data-jpa)、[Spring Data JPA 官方文档](https://docs.spring.io/spring-data/jpa/reference/jpa.html) | — | 2026-08-21 | 自建；写生产 JPA 代码的决策手册（测试归 `spring-jpa-testing`，通用工程惯例归 `java-springboot`）。综合三方资料**重写而非引入**：vibeeval 的 jpa-patterns（codelably、affaan-m/ECC 两个仓库是它的中文转译，内容相同）覆盖面广但每节都浅；Amplicode 的 spring-data-jpa 取其「先探测项目既有约定再写码」思想与实体实现规则（proxy-safe equals/hashCode、Set vs List、显式命名），但其 repository/transaction 参考在上游是 0 字节占位文件且 SKILL.md 绑定自家 IntelliJ MCP 插件，不可原样引入；API 细节以 Spring Data JPA 4.1.0 官方文档校准（标注 3.1+/4.0+ 版本门槛）。SKILL.md 给默认决策表 + 高频事故速查，细节沉到 references/ 5 个文件（实体设计、关联与 N+1、Repository 与查询、事务与锁、性能与配置） |
| `eachlabs-skill` | 自建 / 参照 [eachlabs/skills](https://github.com/eachlabs/skills) 的 `gpt-image-v2` 改写，并**并入**原 [awesome-genmedia/skills](https://github.com/awesome-genmedia/skills) 的 `sound-effects` | [skills/gpt-image-v2/](https://github.com/eachlabs/skills/tree/main/skills/gpt-image-v2)、[sound-effects/](https://github.com/awesome-genmedia/skills/tree/main/sound-effects)、[each::labs 文档](https://docs.eachlabs.ai) | MIT（音频部分） | 2026-09-20 | 自建。**2026-09-20 由 `eachlabs-skill` 改名并扩成三类产出**：图 / 视频 / 音频。改名的理由是它早已不只是出图 —— 三类共用同一套提交-轮询机制、同一个并发闸门，拆成多个 skill 会让同一批事实重复多遍且容易漂。**并入 `sound-effects`**（原上游 skill，MIT 保留在本 skill 根 `LICENSE`，`skills-upstream.json` 里标 `retired`+`merged_into`，同步脚本已加挡板 —— 否则下次全量同步会把删掉的目录重建出来）。并入时订正上游两处过时：它写的 BGM 模型 `ace-step-1-5-text-to-music` **已不在目录里**，「出音频的只有三个模型」**实测是 10 个**；现存音乐模型 `lyria-3-5` / `minimax-music-03` **都没有 `duration`/`bpm`**。新增 `references/video.md`（图生视频与帧动画）与 `references/image.md`，脚本 `scripts/eachlabs.py` 加 `video` / `sfx` / `bgm` / `models` 四个子命令。**2026-09-20 二次复核**：用 each::labs 的**文档 MCP** + `GET /v1/models` 实查，把 30 个 image-to-video 模型的 schema 逐个拉下来比对 —— 结论是**只有 `alibaba-wan-3-0` 系有 `last_frame`**，所以「做循环帧动画用 wan」不是偏好而是唯一选项；同时订正了三处：视频计价是**按秒、随分辨率**（$0.05–$0.20/秒）不是「一支 $0.20」、`ltx-2-5-*` 的 `duration` 枚举确从 **6** 起、平台另有 `eachlabs-video-api`（44 个处理能力，含 `storyboard_sprites` / `silence_detect` / `audio_analysis`）而其 `silence_detect` 的 `noise_db` 是绝对 dBFS 阈值、**与 ffmpeg `silenceremove` 同一个毛病**。新增 `references/choosing-models.md` 回答「怎么选」与「目录变了怎么办」（changelog RSS / 目录 diff / fallback chain / Replay） |

## 更新已引入的 Skill

外部来源的 skill（见上方「来源表」）由 `scripts/update_skills.py` 统一同步，清单是仓库根的 `skills-upstream.json`。

```bash
python3 scripts/update_skills.py --list      # 哪些 skill 归脚本管
python3 scripts/update_skills.py --check     # 只问上游有没有新提交，不改文件
python3 scripts/update_skills.py             # 同步全部外部 skill
```

也可以只同步一部分：

```bash
python3 scripts/update_skills.py patrol-setup patrol-write-test   # 按 skill 名
python3 scripts/update_skills.py --source patrol                  # 按上游来源
python3 scripts/update_skills.py --no-deploy                      # 只更新仓库，不部署
```

单个 skill 的同步流程：**浅克隆上游（按需 sparse）→ `rsync --delete` 覆盖 → 补 `extra` 文件（如 `LICENSE`）→ 打本地适配 patch → 部署到 `~/.cc-switch/skills` 并补 `~/.claude/skills` 符号链接**。全部成功后把上游 commit 回写进清单，下次 `--check` 才能判断是否真有更新。脚本只改文件、不提交，结束时打印 `git diff --stat` 由人确认。

几个要点：

- **自建 skill 不登记在清单里，脚本永远不碰。** 这也是 `cp -R skills/flutter-*` 那种前缀通配的替代品——`flutter-setup-firebase-crashlytics`、`flutter-use-fvm` 这 2 个自建 flutter skill 不会因为上游哪天加了同名目录而被静默覆盖。
- **本地适配存成 patch**（见 `patches/`），同步后自动重打。若上游改动了被 patch 的位置导致打不上，脚本会**报错退出（exit 1）且不部署**，此时工作区里是未打补丁的上游原样，按提示手工合并后重新生成 patch：

  ```bash
  git diff -R --src-prefix=a/ --dst-prefix=b/ -- skills/<name> > patches/<name>.patch
  # 放弃本次同步则：git checkout -- skills/<name>
  ```

- **新引入一个外部 skill 时，记得在 `skills-upstream.json` 里加一条**，否则它不会被后续的统一更新覆盖到。字段：`src`（上游内的路径）、`exclude`（rsync 排除项）、`extra`（附带文件，如仓库根的 `LICENSE`）、`patch`（本地适配）。

清单里 `commit` 为 `null` 表示引入时没记上游版本，基线未知，同步一次即可补上。

<details>
<summary>手动同步（脚本跑不了时的兜底）</summary>

```bash
# 单文件 skill（如 java-springboot）
curl -sSL https://raw.githubusercontent.com/github/awesome-copilot/main/skills/java-springboot/SKILL.md \
  -o skills/java-springboot/SKILL.md

# 含 references/ 的多文件 skill（如 spring-*-testing）
git clone --depth 1 https://github.com/spring-ai-community/spring-testing-skills /tmp/sts
rsync -a --delete /tmp/sts/skills/spring-jpa-testing/ skills/spring-jpa-testing/

# 仓库根目录即 skill（如 codex-image），排除仓库级文件
git clone --depth 1 https://github.com/xntj-ai/codex-image /tmp/codex-image
rsync -a --delete --exclude='.git/' --exclude='README.md' --exclude='.gitignore' \
  /tmp/codex-image/ skills/codex-image/

# skill 只是大仓库一个角落（如 patrol-*，主分支是 master）
git clone --depth 1 --filter=blob:none --sparse https://github.com/leancodepl/patrol /tmp/patrol
git -C /tmp/patrol sparse-checkout set skills
cp -R /tmp/patrol/skills/patrol-* skills/

# 上游分层、本地拍平（如 aliyun-oss-ossutil），同步后要重打本地 patch
git clone --depth 1 https://github.com/cinience/alicloud-skills /tmp/alicloud-skills
rsync -a --delete /tmp/alicloud-skills/skills/storage/oss/aliyun-oss-ossutil/ skills/aliyun-oss-ossutil/
cp /tmp/alicloud-skills/LICENSE skills/aliyun-oss-ossutil/LICENSE
git apply -p1 patches/aliyun-oss-ossutil.patch
```

手动同步后别忘了自己部署：`rsync -a --delete skills/<name>/ ~/.cc-switch/skills/<name>/`，新 skill 还要补 `~/.claude/skills/<name>` 符号链接。

</details>

## 使用方式

其他项目想使用这里的 skills 时，将本仓库链接到目标项目的 `.claude/skills`：

### 方式一：软链接（推荐）

```bash
ln -s /path/to/JzjSkills /path/to/target-project/.claude/skills
```

### 方式二：Git Submodule

```bash
cd target-project
git submodule add <本仓库地址> .claude/skills
```

## 注意事项

- Skill 目录名即 skill 名称，调用时使用 `/skill-name` 或对话中自动匹配
- 全局 skills 位于 `~/.claude/skills/`，项目级 skills 位于项目 `.claude/skills/`
- 项目级 skills 优先级高于全局 skills
