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
│   ├── spring-testing-fundamentals/
│   │   ├── SKILL.md
│   │   └── references/                  # 部分 skill 附带参考文档，需一并保留
│   │       └── *.md
│   └── …（spring-mvc-testing、spring-webflux-testing、spring-jpa-testing、
│           spring-security-testing、spring-websocket-testing 结构同上）
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
