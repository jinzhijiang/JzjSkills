# git-cz 安装与 CLI 完整契约

对应 git-cz 4.9.0(npm 上最新,2022-05 发布;License: Unlicense)。

## 安装

| 方式 | 命令 | 适用 |
|---|---|---|
| 免安装 | `npx git-cz` | 偶尔用;每次要联网或命中 npm 缓存 |
| 全局 | `npm install -g git-cz` → `git-cz` / `gitcz` | **推荐**,非 Node 项目(Flutter / Java / HarmonyOS)也能用 |
| 项目内 + commitizen | `npm i -D git-cz`,`package.json` 里配 `config.commitizen.path = "git-cz"` → `git cz` | Node 项目,想把工具版本锁进仓库 |
| 全局 + commitizen | `npm i -g commitizen git-cz` → `git cz` | 想统一用 `git cz` 这个入口 |

npm 包里还带了 `binaries/cli-macos`、`cli-linux`、`cli-win.exe` 三个自包含可执行文件,
完全没有 node 的机器可以直接拷这个文件用。

命令名 `git-cz` 带连字符时可以直接跑;`git cz`(空格)要经过 commitizen 或
在 PATH 里放一个名为 `git-cz` 的可执行文件——后者 git 会自动识别成子命令。

## 参数

```
git-cz [options] [-- 透传给 git commit 的参数]

  -h, --help          用法
  -v, --version       版本号
  --disable-emoji     本次不加 emoji(覆盖配置)
  --format <模板>     本次覆盖标题模板
  --dry-run           只打印将要执行的命令和消息,不提交
  --hook              把消息写进 .git/COMMIT_EDITMSG 后退出,不执行 git commit
  --non-interactive   非交互模式

非交互模式参数(不传就走默认值):
  --type      默认 chore
  --subject   默认 "automated commit"
  --scope     不受配置里 scopes 列表限制
  --body
  --breaking
  --issues
  --lerna
```

**任何未列出的参数原样透传给 `git commit`**。所以这些都能用:

```bash
git-cz --amend                       # → git commit --file … --amend
git-cz -e                            # → git commit --file … -e(生成后再打开编辑器改)
git-cz --no-verify                   # 跳过钩子
git-cz -a                            # 自动 stage 已跟踪文件
```

交互式回答与命令行参数可以混用:`--type=fix` 传了就不再问类型,只问剩下的。

## 非交互模式(AI 提交路径 A)

```bash
git-cz --non-interactive --type=feat --scope=auth --subject="新增短信登录" \
  --body="接入 aliyun sms;失败自动降级到密码登录" \
  --breaking="移除了 loginWithCode 旧接口" --issues="#42"
```

产出(格式与段落布局已实测;emoji 随配置的 `types` / `breakingChangePrefix` 变,
下面是装了本 skill 的 `changelog.config.js` 之后的样子):

```
✨ feat(auth): 新增短信登录

接入 aliyun sms;失败自动降级到密码登录

BREAKING CHANGE: 💥 移除了 loginWithCode 旧接口

✅ Closes: #42
```

先看不提交:把 `--non-interactive` 换成 `--dry-run --non-interactive`,
它会打印将执行的 git 命令和完整消息。

**非交互模式不做任何校验**:`--type=不存在的类型` 会直接抛
`Cannot read property 'emoji' of undefined`;主题超长、带句号也照写不误
(`minMessageLength` / `maxMessageLength` 只作用于交互式输入框)。所以提交前仍要跑
`check_commit_msg.py`。

## 执行流程与三个坑

1. 读配置(见 [config.md](config.md)),`--disable-emoji` / `--format` 覆盖之。
2. **暂存区检查**:除非透传了 `--amend`、`-a` 或 `--allow-empty`,否则会执行
   `git diff HEAD --staged --quiet --exit-code`,没有暂存内容就打印 `No files staged!` 并退出。
   ⚠️ **这种情况下退出码是 0**——脚本不能靠退出码判断是否提交成功,
   要比对 `git rev-parse HEAD` 前后是否变化,或直接看 `git log -1`。
3. 交互提问或套用非交互参数 → 拼装消息。
4. 消息写入 `<git-dir>/COMMIT_EDITMSG`。`--hook` 到这一步就退出(供
   `prepare-commit-msg` 钩子使用),否则执行
   `git commit --file <git-dir>/COMMIT_EDITMSG <透传参数>`。

⚠️ 消息落的是 `COMMIT_EDITMSG` 这个 git 自己也在用的文件,所以别在同一个仓库里
并发跑两个 git-cz。

⚠️ `git-cz --hook` 与本 skill 的 `check_commit_msg.py install-hook` 装的是**不同**的钩子:
前者是 `prepare-commit-msg`(生成消息),后者是 `commit-msg`(校验消息)。两个可以共存。

## 交互式的行为细节

- 类型、scope 两问是 **autocomplete**:边打字边模糊过滤,回车选中。
- 主题用的是 `limitedInput`,右上角实时显示剩余字符数;超出上限**打不进去**。
- scope 这一问在 `scopes` 为空数组时**整个跳过**,不会退化成自由输入。
- `questions` 数组决定问哪几问和顺序;删掉某一问,对应字段恒为空。
- `messages` 可按问题名覆盖提问文案。
- 主题会自动 trim,并循环剥掉结尾的英文句点。
