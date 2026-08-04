/**
 * git-cz 统一提交风格配置(全局模板)
 *
 * 放置位置:`~/changelog.config.js` 即可让本机所有仓库共用
 * (git-cz 从**仓库的 git 根目录**起逐级向上查找,就近命中一个即停)。
 * 某个项目要覆盖(通常只为了加 scopes),在该仓库根目录再放一份完整配置。
 *
 * 校验:`python3 <skill根>/scripts/check_commit_msg.py` 会读取同一份配置,
 * 两边不会漂移。
 */
module.exports = {
  // false = 保留 emoji。改成 true 后全仓库不再输出 emoji,
  // 且 BREAKING CHANGE / Closes 前缀里的 🧨 ✅ 也一并消失。
  disableEmoji: false,

  // {emoji} 会被展开成「emoji + 一个空格」,所以结果是 `🎸 feat(scope): 主题`。
  // 可用占位符仅 {emoji} {type} {scope} {subject};scope 为空时 {scope} 展开成空串。
  format: '{emoji}{type}{scope}: {subject}',

  // 交互式选择器里出现的类型**和顺序**;不在 list 里的类型选不到。
  // 注意 release 必须列进来,否则 types 里定义了也永远选不中。
  list: [
    'feat',
    'fix',
    'docs',
    'style',
    'refactor',
    'perf',
    'test',
    'chore',
    'ci',
    'release',
  ],

  // 实际限制的是 subject 输入框:上限 = maxMessageLength - 3(留给 emoji + 空格),
  // 即 61 个字符,且按字符数而非终端列宽计——中文写满 61 字会到 122 列。
  // 真正的宽度约束由 check_commit_msg.py 按显示列宽把关(标题 ≤ 72 列)。
  maxMessageLength: 64,
  minMessageLength: 3,

  // 去掉了默认的 'lerna'(非 lerna monorepo 用不到)。
  // 'scope' 留着:scopes 为空时 git-cz 会自动跳过这一问,项目级配置补上 scopes 就自动生效。
  questions: ['type', 'scope', 'subject', 'body', 'breaking', 'issues'],

  // git-cz 的 scope 是**从列表里选**,没有自由输入。
  // 空数组 = 交互式完全不问 scope(全局模板保持为空);
  // 需要 scope 的项目在自己仓库的配置里列出可选值,例如:
  //   scopes: ['auth', 'player', 'ci', 'deps'],
  scopes: [],

  types: {
    feat:     { description: '新功能',                             emoji: '🎸', value: 'feat' },
    fix:      { description: '修复 Bug',                           emoji: '🐛', value: 'fix' },
    docs:     { description: '仅文档变动',                         emoji: '✏️', value: 'docs' },
    style:    { description: '代码风格、格式、空格、分号等',        emoji: '💄', value: 'style' },
    refactor: { description: '重构(既非新功能也非 Bug 修复)',     emoji: '💡', value: 'refactor' },
    perf:     { description: '性能优化',                           emoji: '⚡️', value: 'perf' },
    test:     { description: '添加或修改测试',                     emoji: '💍', value: 'test' },
    chore:    { description: '构建过程或辅助工具的变动',           emoji: '🤖', value: 'chore' },
    ci:       { description: 'CI 相关的变动',                      emoji: '🎡', value: 'ci' },
    release:  { description: '发布版本',                           emoji: '🏹', value: 'release' },
  },

  // 交互式提问文案(git-cz 原文案是英文,这里换成中文;键名与 questions 一一对应)。
  messages: {
    type: '选择本次提交的类型:',
    scope: '选择影响范围(scope):',
    subject: '一句话描述这次改动(祈使句、不加句号):',
    body: '补充说明:改了什么、为什么这么改(可留空)\n ',
    breaking: '列出破坏性变更(没有就回车跳过)\n  BREAKING CHANGE:',
    issues: '关联并关闭的 issue,如 #123(没有就回车跳过):',
  },

  // 页脚前缀;disableEmoji: true 时 🧨 / ✅ 自动省略,Closes: 保留。
  breakingChangePrefix: '🧨 ',
  closedIssueMessage: 'Closes: ',
  closedIssuePrefix: '✅ ',

  // ↓ git-cz 本身不认识这个键(它只是被原样带着走,不影响任何行为),
  //   由本 skill 的 check_commit_msg.py 读取:要求主题与正文用中文书写。
  //   type / scope / 技术名词 / 标识符 / 路径不受影响。
  requireChineseSubject: true,
};
