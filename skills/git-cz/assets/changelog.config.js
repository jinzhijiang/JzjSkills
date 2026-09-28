/**
 * 统一提交风格配置(全局模板,格式沿用 git-cz)
 *
 * 放置位置:`~/changelog.config.js` 即可让本机所有仓库共用
 * (从**仓库的 git 根目录**起逐级向上查找,就近命中一个即停)。
 * 某个项目要覆盖(通常只为了限定 scopes),在该仓库根目录再放一份完整配置。
 *
 * 提交用普通 git 命令,不需要装 git-cz;这份配置由
 * `python3 <skill根>/scripts/check_commit_msg.py` 读取,是校验规则的唯一来源。
 */
module.exports = {
  // false = 保留 emoji。改成 true 后全仓库不再输出 emoji,
  // 且 BREAKING CHANGE / Closes 前缀里的 💥 ✅ 也一并消失。
  disableEmoji: false,

  // {emoji} 会被展开成「emoji + 一个空格」,所以结果是 `✨ feat(scope): 主题`。
  // 可用占位符仅 {emoji} {type} {scope} {subject};scope 为空时 {scope} 展开成空串。
  format: '{emoji}{type}{scope}: {subject}',

  // 允许使用的类型;不在 list 里的类型校验报错。
  // 注意 release 必须列进来,否则 types 里定义了也用不了。
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

  // 限制的是主题本身:上限 = maxMessageLength - 3(留给 emoji + 空格),
  // 即 61 个字符,且按字符数而非终端列宽计——中文写满 61 字会到 122 列。
  // 真正的宽度约束由 check_commit_msg.py 按显示列宽把关(标题 ≤ 72 列)。
  maxMessageLength: 64,
  minMessageLength: 3,

  // 空数组 = 不限制 scope,可以自由写模块名(如 `feat(auth): …`),也可以不写。
  // 哪个项目要约束可选值,在自己仓库的配置里列出来,校验会拦列表外的,例如:
  //   scopes: ['auth', 'player', 'ci', 'deps'],
  scopes: [],

  types: {
    feat:     { description: '新功能',                             emoji: '✨', value: 'feat' },
    fix:      { description: '修复 Bug',                           emoji: '🐛', value: 'fix' },
    docs:     { description: '仅文档变动',                         emoji: '📝', value: 'docs' },
    style:    { description: '代码风格、格式、空格、分号等',        emoji: '🎨', value: 'style' },
    refactor: { description: '重构(既非新功能也非 Bug 修复)',     emoji: '♻️', value: 'refactor' },
    perf:     { description: '性能优化',                           emoji: '⚡️', value: 'perf' },
    test:     { description: '添加或修改测试',                     emoji: '✅', value: 'test' },
    chore:    { description: '构建过程或辅助工具的变动',           emoji: '🔧', value: 'chore' },
    ci:       { description: 'CI 相关的变动',                      emoji: '👷', value: 'ci' },
    release:  { description: '发布版本',                           emoji: '🔖', value: 'release' },
  },

  // 页脚前缀;disableEmoji: true 时 💥 / ✅ 自动省略,Closes: 保留。
  breakingChangePrefix: '💥 ',
  closedIssueMessage: 'Closes: ',
  closedIssuePrefix: '✅ ',

  // 本 skill 自己的键(git-cz 不认识它):由 check_commit_msg.py 读取,
  // 要求主题与正文用中文书写;type / scope / 技术名词 / 标识符 / 路径不受影响。
  requireChineseSubject: true,
};
