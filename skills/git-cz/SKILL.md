---
name: git-cz
description: 用 git-cz 统一所有项目的 Git 提交信息风格(emoji + Conventional Commits)。要写 commit message、执行 git commit、修订提交信息(--amend / rebase reword)、配置 changelog.config.js、装提交校验钩子时都先读本 skill:它给出唯一契约「{emoji}{type}{scope}: {subject}」、10 个类型与对应 emoji、正文 / BREAKING CHANGE / Closes 段落规则,并用 scripts/check_commit_msg.py 在提交前自检(纯 python3 标准库,Flutter / Java / HarmonyOS 等没有 node 的项目照样能校验)。AI 代写提交时优先 git-cz --non-interactive,不可用则按同一契约手写 git commit -F,两条路径产出逐字节一致。触发词:提交、commit、commit message、提交信息、提交规范、提交风格、统一提交、git cz、git-cz、commitizen、conventional commits、changelog.config.js、emoji 提交、commit-msg 钩子、提交校验、语义化提交。不适用于:生成 CHANGELOG.md 文件本身、PR 标题与描述、分支命名。
---

# 统一提交风格(git-cz)

所有仓库的提交信息走同一个契约。人用交互式 `git cz` 生成,AI 用非交互模式或手写生成,
两边产出必须**逐字节一致**——因为它们是同一个格式化算法的两种入口。

> 只有用户要求提交时才提交。本 skill 管的是「提交信息长什么样」,不是「要不要提交」。

## 消息契约

```
{emoji}{type}{scope}: {subject}
                                  ← 空行
{body}
                                  ← 空行
BREAKING CHANGE: 🧨 {breaking}
                                  ← 空行
✅ Closes: {issues}
```

`{emoji}` 展开为「emoji + 一个空格」,`{scope}` 为空时整体消失。完整实例:

```
🎸 feat(auth): 新增短信登录

接入 aliyun sms;失败自动降级到密码登录

BREAKING CHANGE: 🧨 移除了 loginWithCode 旧接口

✅ Closes: #42
```

只有标题是必填的。body / breaking / issues 三段按需出现,**出现就必须带各自的空行与前缀**。

## 类型表

| type | emoji | 用途 |
|---|---|---|
| `feat` | 🎸 | 新功能 |
| `fix` | 🐛 | 修复 Bug |
| `docs` | ✏️ | 仅文档变动 |
| `style` | 💄 | 代码风格、格式、空格、分号(不改行为) |
| `refactor` | 💡 | 重构:既非新功能也非 Bug 修复 |
| `perf` | ⚡️ | 性能优化 |
| `test` | 💍 | 添加或修改测试 |
| `chore` | 🤖 | 构建过程或辅助工具的变动 |
| `ci` | 🎡 | CI 相关的变动 |
| `release` | 🏹 | 发布版本 |

选型有歧义时:改了行为选 `feat`/`fix`,只挪代码不改行为选 `refactor`,只动格式选 `style`,
依赖 / 脚手架 / 配置选 `chore`。emoji 与 type 是死绑定,不能自由搭配。

## 硬约束

- 标题一行写完,`: ` 后跟主题,主题**不加结尾标点**(句号、感叹号、问号都不行)。
- 主题祈使句:「新增登录页」「修复超时崩溃」,不是「新增了…」「修复过…」。
- 主题长度 3 ~ 61 个字符(`maxMessageLength: 64` 减去 emoji 与空格占的 3)。
- 标题显示宽度建议 ≤ 72 列(**中文一个字算 2 列**,所以中文主题控制在 30 字以内)。
- 标题与正文之间必须空一行;正文与页脚之间也是。
- 正文每行 ≤ 72 列,超了自己换行(交互式 git-cz 会自动折行,手写要自己折)。
- 破坏性变更必须是 `BREAKING CHANGE: 🧨 …`,全大写、冒号后一个空格。
- `scope` 只能从配置的 `scopes` 里选;`scopes` 为空(默认)时**不写 scope**。
- Merge / Revert / fixup! / squash! 提交由 git 生成,不套这套格式。

## AI 代写提交

**先自检,再提交。** 两条路径任选,产出一致:

**路径 A — git-cz 可用时(有 node)**,让工具生成,不会写错格式:

```bash
npx git-cz --non-interactive --type=feat --scope=auth --subject="新增短信登录" \
  --body="接入 aliyun sms;失败自动降级到密码登录" --issues="#42"
```

加 `--dry-run` 先看生成的消息再决定是否真提交。非交互模式下 `--scope` 不受 `scopes` 列表限制。

**路径 B — 没有 node 或不想引入依赖**,按契约手写。**不要用 `git commit -m`**
(多行与 emoji 容易被 shell 吃掉),写文件再提交:

```bash
cat > /tmp/commitmsg <<'EOF'
🎸 feat(auth): 新增短信登录

接入 aliyun sms;失败自动降级到密码登录
EOF
python3 <skill根>/scripts/check_commit_msg.py --file /tmp/commitmsg   # 必须先过检
git commit -F /tmp/commitmsg
```

## 人类交互式提交

```bash
npm install -g git-cz     # 或每次 npx git-cz,免安装
git-cz                    # 已 staged 的改动上跑;没有 staged 文件会直接报错退出
```

装了 commitizen 的项目里也可以 `git cz`。安装方式与全部 CLI 参数见
[references/cli.md](references/cli.md)。

## 让所有项目统一

git-cz 从**仓库的 git 根目录**起逐级向上查找配置,就近命中一个即停。把配置放在家目录,
本机所有仓库自动共用同一份:

```bash
cp <skill根>/assets/changelog.config.js ~/changelog.config.js
```

单个项目要加自己的 `scopes`(git-cz 的 scope 只能从列表里选,没有自由输入),
在该仓库根目录再放一份**完整**配置——就近命中即停,不做逐级合并。

给仓库装上校验钩子,人和 AI 走哪条路径都拦得住:

```bash
python3 <skill根>/scripts/check_commit_msg.py install-hook --repo <仓库路径>
```

钩子只改本地 `.git/hooks/`,不进版本库;每个克隆都要各装一次。已存在同名钩子时不会
偷偷覆盖(要覆盖加 `--force`,原文件自动备份)。

## 提交前自检

```bash
python3 <skill根>/scripts/check_commit_msg.py --file <消息文件>   # 或 --message "…" / 默认读 .git/COMMIT_EDITMSG
python3 <skill根>/scripts/check_commit_msg.py show-config          # 看当前生效的配置与来源
```

退出码 0 通过 / 1 不通过 / 2 用法错。常用参数:`--strict` 把警告也当失败、`--json` 机读、
`--warn-only` 只报不拦。它读的就是 git-cz 那份 `changelog.config.*`,规则不会和交互式生成的漂移;
没有 node 时用内置的字面量解析器读 `.js`,读不出来就**跳过校验**而不是拿默认值误判。

## 常见坑

- **改了配置但没生效**:`.git-cz.json` 优先级高于 `changelog.config.js`,同目录下前者赢;
  查找从 git 根目录起向上,放在子目录里的配置**永远不会被读到**。
- **emoji 位置**:本契约 emoji 在最前(`🎸 feat: …`),git-cz 默认模板是在冒号后
  (`feat: 🎸 …`)。抄网上例子时注意区别。
- **前导 emoji 会打断 conventional-changelog / semantic-release 的默认解析**,
  以后要自动出 CHANGELOG 得定制 `headerPattern`,或改用 `disableEmoji: true`。
- **`scopes: []` 会让交互式完全不问 scope**,不是「随便填」。
- **历史提交没有 emoji**:引入配置后新旧风格不一致是正常的,不要去改写已推送的历史。

更多细节:配置全部键与逐项理由见 [references/config.md](references/config.md),
CLI 与安装见 [references/cli.md](references/cli.md),
排错见 [references/troubleshooting.md](references/troubleshooting.md)。
