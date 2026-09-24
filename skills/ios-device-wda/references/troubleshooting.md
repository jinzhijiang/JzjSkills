# 排障：症状 → 原因 → 解法

以下均来自 2026-09-24 在 iPad 9（iPadOS 26.6.1）+ Xcode 26.6 + WDA v16.12.10 上的实测。

## 启动与连接

| 症状 | 原因 | 解法 |
|---|---|---|
| `idevicescreenshot` 报 `Could not start screenshotr service: Invalid service` | iOS 17 起截图服务不再走 libimobiledevice 用的 lockdown 通道，开发者磁盘镜像挂上了也没用 | 别再试它，用本 skill |
| 想截图 / 点屏，翻遍 `xcrun devicectl` 找不到 | devicectl 只有装卸 App、进程、拷文件、方向、通知，没有截图和输入 | 同上 |
| `start` 这条命令被 auto 模式拦下（Blocked by fast classifier） | 它可能克隆、编译、运行第三方 WDA 代码，审查按最坏情况判；而且判定不稳定，同一条命令这次放行、下次拦下 | **不要换写法绕开**。`launch-cmd` 把命令交给用户在终端跑，再 `attach`；长期可请用户加 Bash 允许规则匹配 `python3 ~/.claude/skills/ios-device-wda/scripts/wda.py` |
| 编译报 `Signing for "WebDriverAgentRunner" requires a development team` / 描述文件错误 | 没取到团队，或 bundle id 与团队下已有的冲突 | `--team <TEAMID>`；bundle id 换成团队下唯一的（`config set bundle_id …`）。不要用 WDA 原生的 `com.facebook.*` |
| 编译成功，启动时 `Unable to find a destination` | 设备没连好：锁屏、没信任这台电脑、开发者模式关着 | `wda.py doctor` 看 `开发者模式` 与 `连接`；解锁设备，在「设置 → 隐私与安全性 → 开发者模式」打开 |
| 设备上弹「不受信任的开发者」 | 个人免费团队签的包 | 设置 → 通用 → VPN 与设备管理 → 信任该开发者；付费团队一般不会出现 |
| `start` 后很久没就绪，`xcodebuild.log` 停在 `Test Suite … started` | WDA 已起来但端口转发没通 | `wda.py status` 看 `iproxy_pid` 是否存活；`wda.py stop` 后重来；没有 iproxy 就 `brew install libimobiledevice` |
| 另一个会话 / 终端正在跑 WDA，这边再 `start` | 同一台设备只能跑一个 XCTest 会话，新起的会把旧的顶掉 | `start` 会先探测，已在跑就直接接上；**别**手动再跑一遍 `xcodebuild test` |
| 设备锁 `BUSY` | 别的会话正在用这台设备（装包、验证中） | 等它 release；`device_lock.py status --device <udid>` 看是谁。不要因为 WDA 在跑就去点 |

## 操作

| 症状 | 原因 | 解法 |
|---|---|---|
| 主屏上 `find` / `click` 什么都查不到，`source` 里只有 `DockFolderViewService` | iPadOS 26 上 WDA 自动检测活动 App 时误选了 Dock 的 DockFolderViewService | 加 `--app springboard`；进了某个 App 就用 `--app <它的 bundle id>` 或不加 |
| 点的位置总偏 | 把截图像素当成了点 | 用 `screenshot` 打印的系数换算：`点 = 小图坐标 × 系数`（原图则 `÷ 缩放`） |
| 主屏「编辑」菜单、长按菜单点完就消失，`find` 找不到菜单项 | SpringBoard 的弹出菜单在元素查询（`find` / `click` / `source`）时会被收起 | 点完菜单项**先截图**，别紧跟 `find`；菜单里的项按截图坐标 `tap` |
| `click --label X` 返回成功，画面没变化 | 匹配到了被遮住的同名控件（如小组件库面板背后 Dock 上的同名 App 图标） | 面板里的项用截图坐标 `tap`；或 `find` 看匹配到几个、各自位置，再 `--index` |
| 左滑列表项没出删除按钮 | 不是每个 App 都支持左滑；很多列表是长按出菜单 | 先查 App 代码 / 截图确认交互方式，再长按 `hold` |
| `press home` 后停在第 1 页或今日视图，不是刚才那页 | 在主屏上按 Home 会回到第 1 页 / 今日视图 | 回主屏后用水平 `swipe` 翻到目标页，截图确认页码点 |
| 中文输入法下 `type "abc"` 打出一串拼音候选 | 字母进了输入法组字 | 先点键盘地球键切英文再 `type`，测完切回来；中文内容尽量避免直接 `type` |
| 删除 / 确认类按钮 `tap` 被 auto 模式拦 | 不可撤销的操作要用户确认 | 告诉用户要删什么，等明确答复；或请用户自己点 |
| 需要等页面动画，但 shell 里 `sleep` 被拦 | 本环境禁止前台 sleep 空等 | 用动作的 `--then-shot <秒>`，等待在脚本里完成 |

## Siri / App 快捷指令

| 症状 | 原因 | 解法 |
|---|---|---|
| `siri` 之后截图只有主屏 | 回应卡片约 5–8 秒后自动收起 | `--then-shot 2`~`4` |
| Siri 回落成「打开 App」或反问用哪个 App | 刚装 / 覆盖安装，短语索引还没好；或 App 快捷指令本身有问题 | 等几分钟或先打开一次 App 再试；看 `idevicesyslog` 里 linkd 的报错 |
| 卡片文字是英文 key（如 `Overdue`、`And 3 more`） | Siri 卡片（`ShowsSnippetView`）由 Siri 的界面进程渲染，`Text("字面量")` 按 Siri 的 bundle 查不到翻译 | App 侧改成先 `String(localized:)` 再交给 `Text`（这是被测 App 的 bug，不是 WDA 的） |
| 同一句话这次在 App 进程执行、下次在扩展执行 | linkd 策略：App 进程活着就派给 App，否则派给 App Intents 扩展 | 两条路都要测：先 `app terminate <bundleId>` 再 `siri`，就是扩展路径 |

## 收尾

| 症状 | 原因 | 解法 |
|---|---|---|
| `stop` 说「不是本脚本启动的」 | WDA 是用户在终端起的 | 请用户在那个终端 Ctrl+C |
| 主屏多了一个 WebDriverAgent 图标 | WDA 的测试宿主 App（`<bundle id>.xctrunner`） | 可以留着下次用；不想要就 `stop --uninstall` |
| 删小组件再加回来后图标顺序变了 | 主屏自动重排 | 告诉用户哪些图标挪了；要复原就逐个长按拖回去 |
