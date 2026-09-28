# 校验脚本与提交命令

提交只用普通 git,不装也不调用 git-cz / commitizen / node,也没有配置文件。这里是
`check_commit_msg.py` 的全部参数,以及各场景的 git 写法。

## check_commit_msg.py

python3 标准库,不需要 node / npm。契约写死在脚本开头的常量里(`FORMAT`、`TYPES`、`SUBJECT_MAX`、
页脚前缀),不读任何配置文件;仓库里有别的工具留下的 `changelog.config.js` 也不影响它。

```
python3 <skill根>/scripts/check_commit_msg.py [--repo <仓库>] [check] [选项]
python3 <skill根>/scripts/check_commit_msg.py install-hook [--repo <仓库>] [--force]
```

| 子命令 | 作用 |
|---|---|
| `check`(默认,可省略) | 校验一条提交信息 |
| `install-hook` | 往仓库装 commit-msg 钩子(跟随 `core.hooksPath`);已有同名钩子不覆盖,`--force` 覆盖前自动备份 |

`check` 的选项:

| 选项 | 作用 |
|---|---|
| `--file <路径>` | 提交信息文件;`-` 读 stdin;都不传时读 `.git/COMMIT_EDITMSG` |
| `--message "<文本>"` | 直接传入提交信息 |
| `--strict` | 警告也当失败(如标题超过 72 列) |
| `--warn-only` | 只报不拦,恒退出 0 |
| `--json` | 机读输出 |
| `--repo <路径>` | 没给 `--file` / `--message` 时从哪个仓库读 `COMMIT_EDITMSG`,默认当前目录 |

退出码:0 通过 / 1 不通过 / 2 用法错(不在仓库里又没给 `--file` / `--message`、文件不存在)。
早先的 `show-config` 子命令已随配置文件一起去掉;`--quiet` / `--verbose` 还收,但已无作用。

## 各场景的 git 写法

```bash
# 新提交:写文件 → 过检 → 只加这次的文件 → 提交
msg=$(mktemp)
cat > "$msg" <<'EOF'
🐛 fix(player): 修复切歌时进度条回跳

进度条订阅没随曲目切换重置,旧曲目的最后一次回调把位置写回去了
EOF
python3 <skill根>/scripts/check_commit_msg.py --file "$msg" \
  && git add lib/player/progress.dart \
  && git commit -F "$msg" \
  && rm -f "$msg"

# 只改最后一条的信息:暂存区必须是空的,否则暂存的改动会一起并进去
git diff --cached --quiet && git commit --amend -F "$msg"

# 看落库的是不是想要的那条
git log -1 --format=%B
```

- 提交前 `git status --short` / `git diff --cached --stat` 确认暂存的正是这次要提交的文件。
- 消息文件一次一个(`mktemp`),别共用固定路径;同一仓库别并发提交。
- 更早的提交改信息要 `git rebase -i` 选 reword(要开编辑器,交给人做);已推送到共享分支的不改写。
- `git commit -m` 能用但不推荐:多行正文要写多个 `-m`,emoji 与引号混在一起容易被 shell 吃掉。

## 为什么不用 git-cz 的命令

早先 AI 提交的首选是 `npx git-cz --non-interactive …`,人用交互式 `git cz`。实测下来它没带来普通
git 做不到的东西,反倒多了这些坑(git-cz 4.9.0):

- 要 node / npm;Flutter、Java、HarmonyOS 项目的机器上常常没有。
- 非交互模式**不做任何校验**:类型写错直接抛 `Cannot read property 'emoji' of undefined`,
  主题超长、带句号照写不误——提交前本来就还得跑一遍 `check_commit_msg.py`。
- 暂存区为空时只打印 `No files staged!`,**退出码却是 0**,脚本判断不了到底提交了没有。
- 消息固定写进 `<git-dir>/COMMIT_EDITMSG`,两个会话同时提交会互相覆盖。
- scope 只能从配置列表里选,不能自由写模块名。
- 中文正文靠 `word-wrap` 按空格折行,折不动,还是得自己断行。

格式本身(拼装算法、页脚前缀、主题上限 61 字符)照旧沿用它;它的配置文件 `changelog.config.js`
也不再需要——规则就一套,写死在校验脚本里,省掉查找顺序、整份覆盖、没有 node 时解析 `.js` 这一整层。
