# JzjSkills

个人常用 Claude Code Skills 集合，通过 Git 统一管理和复用。

## 目录结构

每个 skill 是项目根目录下的一个子目录，目录名即 skill 名称：

```
JzjSkills/
├── gh-cli/           # skill: gh-cli
│   └── SKILL.md      # skill 定义文件（必需）
├── my-skill-b/
│   └── SKILL.md
└── README.md
```

## 添加 Skill

1. 在项目根目录下创建以 skill 名称命名的子目录
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
