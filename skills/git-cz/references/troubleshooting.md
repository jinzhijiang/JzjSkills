# 排错

## 提交类

**`git commit -F` 报 `nothing to commit` / `no changes added to commit`**

暂存区是空的,先 `git add <文件>`。脚本里要确认真的提交了,就比对提交前后的
`git rev-parse HEAD`,或看 `git log -1`。

**中文正文一行太长**

git 不会替你折行。手动断行,每行 ≤ 72 列(中文一个字 2 列,约 36 个汉字);
超了 `check_commit_msg.py` 会告警,`--strict` 下直接拒绝。

**emoji 在终端里显示成方块或错位**

终端字体缺 emoji 字形。不影响仓库里存的字节,`git log` 换个终端就正常。

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
python3 <skill根>/scripts/check_commit_msg.py --file .git/COMMIT_EDITMSG
```

- 报「标题不符合格式」但看着没问题 → 多半是全角冒号「:」写成了半角以外的字符,
  或 `: ` 后面漏了空格、多了空格。
- 报「主题超长」→ 上限 61 个字符(按字符数,不是列宽)。
- 报「主题要用中文写」→ 契约要求主题里至少有一个中文字符。确实要写英文提交的仓库,别装这个钩子。
- 只有「标题 N 列 > 72 列」这类警告是不拦截的(除非加了 `--strict`)。
- 确实是规则太严 → 改 `check_commit_msg.py` 开头的契约常量并同步 SKILL.md,不要给钩子加例外。

**临时绕过钩子**

`git commit --no-verify`。仅限救火,别养成习惯——绕过一次,统一性就破一次。

## 与其他工具共存

**commitlint / conventional-changelog / semantic-release 不认这些提交**

标题开头的 emoji 会让它们的默认 parser(`^(\w*)(?:\((.*)\))?: (.*)$`)整条匹配失败,
自动生成的 CHANGELOG 会把这些提交归到「其他」或直接丢掉;`@commitlint/config-conventional`
会报 `subject may not be empty` / `type may not be empty`。给 parser 定制:

```js
headerPattern: /^(?:\S+\s)?(\w*)(?:\((.*)\))?: (.*)$/,
headerCorrespondence: ['type', 'scope', 'subject'],
```

commitlint 走 `parserPreset` 配同样的 `headerPattern`。本 skill 的校验脚本不依赖这些 parser,不受影响。

**仓库里有别的工具留下的 `changelog.config.js` / `.git-cz.json`**

不影响校验:规则写死在 `check_commit_msg.py` 里,不读任何配置文件。那些文件只对还在用 git-cz 命令的人有意义。

**husky**

husky 接管了 `core.hooksPath`。让 `.husky/commit-msg` 里调用本脚本即可:

```sh
python3 <skill根>/scripts/check_commit_msg.py --file "$1"
```

**多个 AI 会话同时提交同一个仓库**

同一仓库串行提交。消息文件一次一个(`mktemp`),别共用 `/tmp/commitmsg` 这类固定路径——
并发会话会互相覆盖,提交出去的是别人的消息。
