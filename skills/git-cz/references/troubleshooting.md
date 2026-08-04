# 排错

## 配置类

**改了 `changelog.config.js` 但没生效**

按顺序排查:

```bash
python3 <skill根>/scripts/check_commit_msg.py show-config --repo <仓库>   # 头一行 stderr 就是命中的文件
```

- 同目录下有 `.git-cz.json` → 它优先级更高,`changelog.config.js` 被无视。
- 配置放在了子目录 → 查找只从 git 根目录**向上**走,子目录里的永远读不到。
- 上层目录(比如 `~`)有另一份配置 → 就近命中即停,离 git 根更近的那份赢。
- 项目级配置只写了 `scopes` 一个键 → 是**整份覆盖**不是合并,其余键会退回 git-cz 默认值
  (于是 `format` 变回 `{type}{scope}: {emoji}{subject}`,emoji 跑到冒号后面去了)。

**`show-config` 报「读不出」**

本机没有 node,且配置文件里有变量、`require(...)`、函数或模板字符串——内置的字面量
解析器只认纯字面量。两条路:装 node,或把配置改写成等价的 `.git-cz.json`。
这种情况下校验会**跳过**而不是用默认值硬判,不会误伤合法提交。

**交互式里选不到某个类型**

该类型没写进 `list`。`types` 定义了但不在 `list` 里 = 定义了个选不到的类型。

**交互式不问 scope**

`scopes: []`。git-cz 的 scope 只能从列表里选,不支持自由输入,空列表时这一问被整个跳过。
要 scope 就在项目的配置里列出可选值。

## 提交类

**`No files staged!` 然后什么也没发生**

git-cz 只提交暂存区内容,先 `git add`。注意它此时**退出码仍是 0**,
脚本要靠 `git rev-parse HEAD` 前后比对来判断是否真的提交了。

**`Cannot read property 'emoji' of undefined`**

`--type=` 传了 `types` 里不存在的类型。非交互模式不校验类型名。

**中文正文没有自动折行**

git-cz 用 `word-wrap` 按空格折行,中文没空格所以折不动。手动断行,每行 ≤ 72 列
(中文一个字 2 列,约 36 个汉字)。

**emoji 在终端里显示成方块或错位**

终端字体缺 emoji 字形。不影响仓库里存的字节,`git log` 换个终端就正常。
真要规避,改 `disableEmoji: true`(全仓库统一改,别一半带一半不带)。

**已经推送的提交信息写错了**

没推送:`git commit --amend`(改最后一条)或 `git rebase -i` reword。
已推送到共享分支:**不要改写历史**,新提交里说明即可。

## 钩子类

**钩子没触发**

- `.git/hooks/commit-msg` 要有可执行权限(`install-hook` 会自动 chmod 755)。
- 仓库配了 `core.hooksPath` 指向别处 → `install-hook` 会跟随该配置写入,但如果是
  husky 之类工具管理的目录,注意别和它自己的钩子打架。
- 提交时带了 `--no-verify` → 所有 commit-msg 钩子都被跳过。
- 钩子只存在于本地 `.git/`,**不进版本库**,每个克隆都要各装一次。

**钩子把合法提交拦下来了**

先手工复现看具体报什么:

```bash
python3 <skill根>/scripts/check_commit_msg.py --file .git/COMMIT_EDITMSG --verbose
```

- 报「标题不符合格式」但看着没问题 → 多半是全角冒号「:」写成了半角以外的字符,
  或 `: ` 后面漏了空格、多了空格。
- 报「主题超长」→ 上限是 `maxMessageLength - 3`,默认 61 个字符。
- 报「主题要用中文写」→ `requireChineseSubject: true` 要求主题里至少有一个中文字符。
  某个仓库确实要写英文提交,就在该仓库的配置里关掉它(整份配置抄过去再改这一个键)。
- 只有「标题 N 列 > 72 列」这类警告是不拦截的(除非加了 `--strict`)。
- 确实是规则太严 → 改配置,不要给钩子加例外;规则和配置必须是同一份。

**临时绕过钩子**

`git commit --no-verify`。仅限救火,别养成习惯——绕过一次,统一性就破一次。

## 与其他工具共存

**commitlint / conventional-changelog / semantic-release 不认这些提交**

标题开头的 emoji 会让它们的默认 parser 整条匹配失败。解决方案见
[config.md](config.md#与-conventional-changelog-生态的兼容性)。

**husky**

husky 接管了 `core.hooksPath`。让 `.husky/commit-msg` 里调用本脚本即可:

```sh
python3 <skill根>/scripts/check_commit_msg.py --file "$1"
```

**多个 AI 会话同时提交同一个仓库**

git-cz 把消息写在 `<git-dir>/COMMIT_EDITMSG`,并发会互相覆盖。同一仓库串行提交,
或走 `git commit -F <自己的临时文件>` 这条路径。
