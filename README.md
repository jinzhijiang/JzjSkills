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
│   ├── flutter-google-play-release/     # 自建：Flutter Google Play 安全发布
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   ├── references/                  # 审计、Console、Android 质量
│   │   └── scripts/verify_flutter_play_release.py
│   ├── git-cz/                          # 自建：统一所有项目的提交信息风格
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   ├── assets/changelog.config.js   # 全局配置模板
│   │   ├── references/                  # config、cli、troubleshooting
│   │   └── scripts/check_commit_msg.py  # python3 标准库，提交前自检 / commit-msg 钩子
│   ├── codex-image/                     # 外部引入：用 codex 订阅额度生图
│   │   ├── SKILL.md
│   │   ├── LICENSE                      # MIT，随上游一并保留
│   │   ├── references/                  # prompt-recipes、boundaries
│   │   └── scripts/codex_image.py       # python3 标准库，驱动 codex exec 出图
│   └── …（spring-mvc-testing … 等 spring-* 结构同上；
│           另有 13 个 flutter-* skill（10 个 Flutter 官方 + 3 个自建），
│           其中 flutter-setup-firebase-crashlytics 含 references/ 与 agents/）
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
| `flutter-ui-automation` | 自建 / 内部整理 | 底层工具 [ai-dashboad/flutter-skill](https://github.com/ai-dashboad/flutter-skill)（本机用 [jinzhijiang](https://github.com/jinzhijiang/flutter-skill) fork） | — | 2026-07-06 | 自建；记录 `flutter_skill` 连接/探查用法，由 flutter_todo `.agents/skills` 移入并泛化为通用 Flutter 版 |
| `flutter-setup-firebase-crashlytics` | 自建 / 内部整理 | [Firebase Flutter 官方文档](https://firebase.google.com/docs/flutter/setup) | — | 2026-07-18 | 自建；默认完整接入 Firebase Core、Google Analytics 与 Crashlytics，并要求设备上报验证和临时崩溃入口清理 |
| `flutter-use-fvm` | 自建 / FVM 官方文档整理 | [FVM Documentation](https://fvm.app/documentation/getting-started/overview) | — | 2026-07-18 | 自建；强制 Flutter/Dart 命令通过 `fvm flutter` / `fvm dart` 执行，并按需覆盖完整配置、命令、IDE/CI 与故障排查 |
| `flutter-google-play-release` | 自建 / Google Play 上架实操整理 | — | — | 2026-07-30 | 自建；Flutter Android 首发与更新的证据审计、商店资料、政策声明、IARC、AAB、质量建议和最终送审确认门 |
| `git-cz` | 自建 / 基于 [streamich/git-cz](https://github.com/streamich/git-cz) 整理 | [streamich/git-cz](https://github.com/streamich/git-cz)（npm `git-cz@4.9.0`，Unlicense） | — | 2026-08-04 | 自建；统一所有项目的提交信息风格：消息契约、`assets/changelog.config.js` 全局模板、`scripts/check_commit_msg.py`（python3 标准库，无 node 也能校验，可装成 commit-msg 钩子） |
| `codex-image` | [xntj-ai/codex-image](https://github.com/xntj-ai/codex-image) | [仓库根目录即 skill](https://github.com/xntj-ai/codex-image) | MIT | 2026-08-04 | 原样引入（上游 `9b4e0bc`）；仓库根目录本身就是 skill，取 `SKILL.md` + `references/`（2 个文件）+ `scripts/codex_image.py`，并保留 `LICENSE`；未引入上游 `README.md`、`.gitignore` |
| `test-device-allocator` | 自建 / 内部整理 | — | — | 2026-08-04 | 自建；多项目并发 AI 测试的真机/模拟器分配与互斥锁：`scripts/device_lock.py`（python3 标准库，acquire/wake/release/status/clean），锁注册表 `~/.ai-device-locks/`，无空闲设备时自动新建 Android/iOS 模拟器；支持把已连接的 HarmonyOS 真机/模拟器纳入分配池（`--platform android,harmony`），并在 acquire 后自动亮屏解锁、release 时还原屏幕设置 |

## 更新已引入的 Skill

外部来源的 skill（见上方「来源表」）可按以下方式同步上游更新。

**单文件 skill**（仅 `SKILL.md`，如 `java-springboot`）——把 `github.com/…/blob/…` 换成 `raw.githubusercontent.com` 直接覆盖：

```bash
curl -sSL https://raw.githubusercontent.com/github/awesome-copilot/main/skills/java-springboot/SKILL.md \
  -o skills/java-springboot/SKILL.md
```

**含 `references/` 的多文件 skill**（如 `spring-*-testing`）——同步整个目录，确保参考文档一并更新：

```bash
# 浅克隆上游到临时目录，再整目录同步（--delete 会移除上游已删除的文件）
git clone --depth 1 https://github.com/spring-ai-community/spring-testing-skills /tmp/sts
rsync -a --delete /tmp/sts/skills/spring-jpa-testing/ skills/spring-jpa-testing/
```

**仓库根目录即 skill**（如 `codex-image`）——上游整个仓库就是一个 skill，同步时排除仓库级文件：

```bash
git clone --depth 1 https://github.com/xntj-ai/codex-image /tmp/codex-image
rsync -a --delete --exclude='.git/' --exclude='README.md' --exclude='.gitignore' \
  /tmp/codex-image/ skills/codex-image/
```

**成套引入的同源 skill**（如 10 个 `flutter-*`）——浅克隆上游后，一次性覆盖全部同前缀目录：

```bash
git clone --depth 1 https://github.com/flutter/skills /tmp/flutter-skills
# 仅覆盖 skills/ 下的 flutter-* 目录，不引入上游的 resources/、tool/、.agents/ 等基建
cp -R /tmp/flutter-skills/skills/flutter-* skills/
```

> 注意：这里用 `cp -R` 而非 `rsync --delete`——`skills/` 目录下混有其他来源的 skill，整目录 `--delete` 会误删它们。
>
> `flutter-ui-automation` 是自建 skill、并非 flutter/skills 成员，上游没有同名目录，上面的 `cp -R flutter-*` 不会覆盖它；它的维护独立进行。

完成后用 `git diff` 查看上游变更，确认无误再提交。若本地对某 skill 做过定制修改，请手动合并，避免被覆盖。

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
