---
name: ios-device-wda
description: 让 AI 自己动手操作 iOS 真机（iPhone / iPad）——截图、点击、长按、滑动、输入、按 Home、启停 App、读元素树，以及**用文字触发 Siri / App 快捷指令短语**，底层是 Appium 的 WebDriverAgent（WDA）。只要接下来要「看」或「点」iOS 真机屏幕——装完包验 UI、验桌面小组件、验 Siri 与快捷指令、复现只在真机出现的问题、截图给用户看——就用它：`wda.py start` 一条命令起 WDA 并接管（已在跑就直接接上），之后每个动作一条命令。iOS 17+ 上 `idevicescreenshot` 报 `Invalid service`、`xcrun devicectl` 既不能截图也不能点，这是让 AI 自己操作 iOS 真机的办法。不用于：iOS 模拟器（用模拟器 MCP）、Android / 鸿蒙（adb / hdc / Patrol）、只需装包或看日志（devicectl / idevicesyslog 就够）。
---

# iOS 真机自动操作（WebDriverAgent）

**适用**：AI 需要亲眼看、亲手点 iOS 真机——验 UI、桌面小组件、Siri / 快捷指令、系统弹窗，截图给用户确认。
**不适用**：模拟器（模拟器 MCP 更快）；Android / 鸿蒙；只装包、看日志、拷沙盒文件（`xcrun devicectl` 就行）。

所有命令都这样调用（固定写法，方便用户加一条权限规则整体放行）：

```bash
python3 ~/.claude/skills/ios-device-wda/scripts/wda.py <子命令> …
```

下文用 `wda.py` 简写。完整参数见 [references/cli.md](references/cli.md)，出问题先查 [references/troubleshooting.md](references/troubleshooting.md)。

## 硬规则

1. **先领设备锁，再碰设备**（`test-device-allocator` skill）：
   `python3 ~/.claude/skills/test-device-allocator/scripts/device_lock.py acquire --platform ios --device <udid> --project "$PWD"`，
   用完 `release`。锁被别的会话占着（`BUSY`）就等，**不要**因为 WDA 恰好在跑就直接去点——对方可能正在装包、改设置。
2. **坐标是「点」（pt），不是截图像素。** `screenshot` 会打印换算系数：读小图时 `点 = 小图坐标 × 系数`。
3. **不可撤销的操作先问用户**：删数据、发消息、下单、改系统设置、移除用户自己的内容。auto 模式本来也会拦这类点击。
4. **动了用户的环境，收尾时恢复并说明**：删 / 加小组件、切输入法、切系统语言、挪了主屏图标。恢复不了的（比如图标顺序）如实告诉用户。

## 起 WDA

```bash
wda.py doctor        # 检查 Xcode、iproxy、设备（开发者模式 / 连接）、WDA 源码、签名团队
wda.py start         # 已在跑 → 直接接上；没在跑 → 编译（仅首次，1–3 分钟）+ 后台启动 + USB 端口转发 + 建会话
```

- 签名团队按这个顺序取：`--team` → `config` 里的 `team_id` → **当前目录下 Xcode 工程的 `DEVELOPMENT_TEAM`**。
  在 App 仓库根目录下运行，通常什么都不用配。bundle id 默认 `com.webdriveragent.<team>.runner`，可 `config set bundle_id` 固定。
- 连接走 USB（`iproxy` 把 `127.0.0.1:81xx` 转到设备的 8100），不依赖 Mac 和手机在同一网络。

### 启动被 auto 模式拦下时（常见）

编译、运行第三方 WDA 代码可能被 auto 模式的权限审查拦下，而且**判定不稳定**：09-24 实测同一条单独的 `start`，一次放行了完整的编译 + 启动，隔几分钟原样再跑就被拦；和别的命令用 `&&` 串成一条时更容易被拦。所以 `start` 要单独执行；真被拦了，**不要换写法绕开，也不要原样重试**，改成交给用户：

1. `wda.py launch-cmd` 打印一行命令，放进 ```bash 代码块给用户，请他在终端运行（它会一直运行，别关）；
2. 用户回复后 `wda.py attach` 接上（它会等 WDA 就绪、建会话）。

想稳定地全自动，只能请用户在 Claude 设置里加一条 Bash 允许规则，匹配上面的固定写法
`python3 ~/.claude/skills/ios-device-wda/scripts/wda.py`（**你不要替用户改设置文件**）。

## 常用动作

| 要做的事 | 命令 |
|---|---|
| 截图（另存一张最长边 1200 的小图，读小图省 token） | `wda.py screenshot` |
| 点 / 长按 / 滑动（点坐标） | `wda.py tap 200 300` · `wda.py hold 200 300 --ms 1200` · `wda.py swipe 700 600 100 600` |
| 动作后等页面稳定再截图 | 任意动作加 `--then-shot 1.5` |
| 输入文字（焦点要在输入框里） | `wda.py type "hello"` |
| 回主屏 / 音量键 | `wda.py press home` |
| 启动 / 切前台 / 结束 / 查状态 | `wda.py app launch com.example.app` |
| 用文字触发 Siri（含 App 快捷指令短语） | `wda.py siri "玩清单今天有什么待办" --then-shot 3` |
| 按无障碍信息找元素（打印位置，单位点） | `wda.py find --label 编辑` · `--predicate "label CONTAINS '添加'"` |
| 点元素 | `wda.py click --label 完成` |
| 主屏 / 小组件 / 系统菜单里找元素 | 加 `--app springboard`（否则 WDA 常误把 Dock 的服务进程当活动 App，什么都查不到） |
| 系统弹窗 | `wda.py alert text` · `alert accept` · `alert dismiss` |
| 导出元素树 | `wda.py source --out /tmp/tree.txt` |

**截图驱动是主路**：先截图，从图上读坐标，换算成点再 tap，然后 `--then-shot` 确认结果。`find` / `click` 适合系统界面和原生控件；
Flutter 这类自绘界面的元素树往往不全，靠截图坐标更稳。

## 验 Siri / App 快捷指令

- `siri "<短语>"` 等于用户对 Siri 说了这句话，**能直接触发 App 快捷指令**，不用人开口。
- 回应卡片约 5–8 秒后自动收起：用 `--then-shot 2` 到 `--then-shot 4` 截它。
- 卡片上看不出意图在哪个进程执行，要配合 `idevicesyslog -u <udid>` 看 `Invoking <Intent>.perform()`：
  App 进程还活着时，linkd 会把意图派给 App 进程；没在跑时才派给 App Intents 扩展。
- 刚装完或覆盖安装后，短语可能要过几分钟才被认出来（回落成「打开 App」）。

## 收尾

```bash
wda.py stop                 # 停掉本脚本起的 WDA 与端口转发（用户在终端起的 WDA，请用户自己 Ctrl+C）
wda.py stop --uninstall     # 连设备上的 WebDriverAgentRunner 一起卸载（下次 start 会重装）
```

然后 `device_lock.py release`。WDA 留着不关也可以，下次 `start` 秒接；但要把设备锁还掉。
