# changelog.config.js 完整契约

以下均按 git-cz **4.9.0** 的实际源码(`lib/defaults.js`、`lib/getConfig.js`、
`lib/formatCommitMessage.js`、`lib/questions/*`)整理,不是从文档推测的。

## 配置查找顺序

`getConfig(root)` 里的 `root` 是 **`git rev-parse --show-toplevel` 的结果**,
自它起逐级向上直到文件系统根,每一层按下表顺序找,**命中一个立即返回,不做合并**:

| 顺序 | 文件 | 说明 |
|---|---|---|
| 1 | `.git-cz.json` | JSON,优先级最高 |
| 2 | `changelog.config.js` | CommonJS,`module.exports = {…}` |
| 3 | `changelog.config.cjs` | 同上 |
| 4 | `changelog.config.json` | JSON |
| 5 | `package.json` → `config.commitizen.changelog` | 前四个都没有时才看 |

三个推论:

- **放在子目录里的配置永远不会被读到**——查找只向上不向下。
- `~/changelog.config.js` 会被家目录下所有仓库共享,这是「全机统一」的实现方式。
- 项目级配置是**整份覆盖**,不是逐键合并。项目里只想加 `scopes` 也得把整份配置抄过去。

命中的覆盖项与内置默认值做一层浅合并:`{...defaults, ...overrides}`。
`types` 这种嵌套对象是**整体替换**,自定义 `types` 后默认的 10 个类型全部消失。

## 全部支持的键

只有这 12 个键会被读取,写别的键不会报错但也不起作用。

| 键 | 默认值 | 作用 |
|---|---|---|
| `disableEmoji` | 未设置(等价 false) | true 时标题不带 emoji,且 `breakingChangePrefix` / `closedIssuePrefix` 一并不输出 |
| `format` | `'{type}{scope}: {emoji}{subject}'` | 标题模板,占位符仅这 4 个 |
| `list` | `['test','feat','fix','chore','docs','refactor','style','ci','perf']` | 交互式选择器里出现的类型**与顺序**;不在此列表的类型选不到 |
| `types` | 10 个内置类型 | 类型 → `{description, emoji, value}` |
| `scopes` | `[]` | 可选 scope 列表;**只能选、不能自由输入** |
| `questions` | `['type','scope','subject','body','breaking','issues','lerna']` | 要问哪几问、按什么顺序问 |
| `messages` | 无 | 按问题名覆盖提问文案,如 `{type: '选择类型:'}` |
| `maxMessageLength` | `64` | 主题输入框上限,**实际生效值是它减 3** |
| `minMessageLength` | `3` | 主题下限,少于它无法提交 |
| `breakingChangePrefix` | `'🧨 '` | 接在 `BREAKING CHANGE: ` 之后 |
| `closedIssueMessage` | `'Closes: '` | 关闭 issue 的文案 |
| `closedIssuePrefix` | `'✅ '` | 接在 `closedIssueMessage` 之前 |

`defaultType` / `defaultScope` / `defaultSubject` 之类的键**不存在**,别抄。

### 额外的自定义键

git-cz 对认不出的键是**原样带着走**(`{...defaults, ...overrides}` 之后没人读它),
所以可以借配置文件放本 skill 自己的开关,不会影响 git-cz 任何行为:

| 键 | 默认 | 谁读 | 作用 |
|---|---|---|---|
| `requireChineseSubject` | `false` | 只有 `check_commit_msg.py` | true 时主题必须含中文(否则报错),正文疑似全英文时告警 |

判定方式是「主题里至少有一个 CJK 字符」,不是「不许出现英文」——
`新增 flutter_bloc 状态管理`、`修复 iOS 14 下的崩溃` 都正常通过。
模板里已置为 `true`;没有配置文件的仓库默认 `false`,不会平白拦下英文提交。

## 标题拼装算法

`formatCommitMessage` 的实际逻辑,手写提交信息时照这个来:

```js
emoji  = types[type].emoji
scope  = answers.scope ? '(' + answers.scope.trim() + ')' : ''
head   = format.replace('{emoji}', disableEmoji ? '' : emoji + ' ')   // 注意补的那个空格
              .replace('{scope}',  scope)
              .replace('{subject}', subject.trim())
              .replace('{type}',   type)
```

正文与页脚:

```js
msg = head
if (body)     msg += '\n\n' + wrap(body, 72)
if (breaking) msg += '\n\nBREAKING CHANGE: ' + (disableEmoji ? '' : breakingChangePrefix) + wrap(breaking, 72)
if (issues)   msg += '\n\n' + (disableEmoji ? '' : closedIssuePrefix) + closedIssueMessage + wrap(issues, 72)
```

`wrap` 是 `word-wrap`,宽度 72、`trim: true`。**中文没有空格,word-wrap 折不动**,
所以中文正文得自己控制每行长度。

## 长度限制的真相

`lib/questions/subject.js`:

```js
// Minus 3 chars are for emoji + space.
maxLength: config.maxMessageLength - 3,
```

- 限制的是**主题字段本身**,不含 type、scope、冒号;所以 `maxMessageLength: 64` ⇒ 主题 ≤ 61 字符。
- 按 JS 字符数(UTF-16 码元)计,不是终端列宽。61 个汉字 = 61 字符 = **122 列**,
  远超 git 惯例的 72 列。这是 git-cz 管不了的部分,由 `check_commit_msg.py` 按显示列宽补一道警告。
- 主题的 `filter` 会自动 trim 并**剥掉结尾的英文句点**(循环剥,`a...` → `a`);
  中文句号「。」不在此列,得自己不写。

## 逐项说明:模板相对原配置改了什么

`assets/changelog.config.js` 相对最初那份配置的差异,以及为什么:

| 改动 | 原因 |
|---|---|
| `list` 补上 `release`,并按使用频率重排 | `types` 里定义了 `release` 却没进 `list`,交互式**永远选不到**它。`list` 的顺序就是选择器的显示顺序 |
| 新增 `messages` | 原生提问文案是英文,与中文提交信息割裂。键名与 `questions` 一一对应 |
| 显式写出 `breakingChangePrefix` / `closedIssueMessage` / `closedIssuePrefix` | 原来靠默认值,页脚长什么样得去翻源码;写出来配置文件才自解释 |
| `test` 描述从「添加测试」改为「添加或修改测试」 | 改测试也走 `test`,原描述会让人误以为只有新增才算 |
| `scopes` 保持 `[]` 并加注释 | git-cz 的 scope 只能选不能输入,`scopes: []` 时这一问被**整个跳过**。全局模板列不出对所有项目都成立的 scope,交给项目级配置 |
| `questions` 保留 `'scope'` | 与 `scopes: []` 并不冲突——空列表时自动跳过,项目级配置补上 `scopes` 就自动生效,不用再改 `questions` |
| 保留 `questions` 中已去掉的 `'lerna'` | 默认值里有 `lerna`,非 lerna monorepo 用不到,去掉是对的 |
| 新增 `requireChineseSubject: true` | 提交信息要中文写。git-cz 没有这个能力,由 `check_commit_msg.py` 补上 |
| 大量注释 | 上面这些坑都写在旁边,免得下次重新踩 |

`disableEmoji: false`、`format: '{emoji}{type}{scope}: {subject}'`、
`maxMessageLength: 64` / `minMessageLength: 3` 维持原样。

## 与 conventional-changelog 生态的兼容性

标题把 emoji 放在最前面(`🎸 feat: …`),而 `conventional-changelog` /
`semantic-release` / `standard-version` 的默认 parser 认的是
`/^(\w*)(?:\((.*)\))?: (.*)$/`——**开头多一个 emoji 就整条匹配不上**,
自动生成的 CHANGELOG 会把这些提交全部归到「其他」或直接丢弃。

三个选择,按代价从低到高:

1. 不用这套工具自动出 CHANGELOG(手写 / 用 `git log` 直出),现状不用改;
2. 给 parser 定制 `headerPattern`,例如
   `/^(?:\S+\s)?(\w*)(?:\((.*)\))?: (.*)$/`,`headerCorrespondence: ['type','scope','subject']`;
3. 改用 git-cz 默认的 `format: '{type}{scope}: {emoji}{subject}'`,emoji 挪到冒号后,
   开头就是标准的 `type(scope): `,主流 parser 直接认。

commitlint 同理:`@commitlint/config-conventional` 会因为前导 emoji 报
`subject may not be empty` / `type may not be empty`,得配 `parserPreset` 才能共存。
本 skill 的 `check_commit_msg.py` 不依赖这些 parser,所以不受影响。
