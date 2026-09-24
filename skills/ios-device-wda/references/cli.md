# wda.py 命令参考

```bash
python3 ~/.claude/skills/ios-device-wda/scripts/wda.py [--udid UDID] <子命令> [参数]
```

- `--udid`：只连着一台 iOS 真机时可省略；也认环境变量 `WDA_UDID`。
  省略时先看本机已接上的 WDA（只有一台就用它，省掉每次 1–2 秒的 `devicectl` 查询），再看连着的真机。
- **坐标一律是点（pt）**。iPad 9 为 810×1080，iPhone 多为 390×844 等；截图像素 = 点 × 缩放（2 或 3）。

## 生命周期

| 子命令 | 作用 | 参数 |
|---|---|---|
| `devices` | 列出 iOS 真机：UDID、名称、系统、开发者模式、连接方式；可用的打 ✓ | — |
| `doctor` | 检查 Xcode、iproxy、设备、WDA 源码、签名团队、是否已有可免编译的产物 | — |
| `start` | 已在跑 → 接上；否则编译（仅首次或签名 / Xcode / WDA 版本变了）→ 后台启动 → USB 端口转发 → 建会话 | `--team` `--bundle-id` `--rebuild` `--timeout`（默认 120s） |
| `attach` | 只接上已在运行的 WDA（用户在终端起的），不编译也不启动 | `--timeout`（默认 60s） |
| `launch-cmd` | 打印启动 WDA 的一行命令（带 `\| tee` 到日志），给用户在终端运行 | `--team` `--bundle-id` |
| `status` | WDA 是否就绪、版本、设备 IP、各进程是否存活、当前会话 | — |
| `stop` | 停掉本脚本起的 WDA 与 iproxy，清空状态 | `--uninstall` 同时卸载 `<bundle id>.xctrunner` |
| `config show` / `config set <键> <值>` | 键：`team_id` `bundle_id` `wda_dir` `wda_ref` | — |

## 动作

以下命令都可加 `--then-shot <秒>`：动作后等几秒再截一张图（页面动画、Siri 回应）；
`--max <像素>` 控制随图另存的小图（默认 1200，`0` 不缩）。

| 子命令 | 作用 |
|---|---|
| `screenshot [--out 路径] [--max N]` | 截图。打印原图与小图路径、`像素 = 点 × 缩放`，以及 `小图坐标 × 系数 = 点` |
| `tap X Y` | 点一下（按住 80ms） |
| `hold X Y [--ms 1200]` | 长按（主屏图标 / 小组件菜单、列表项菜单） |
| `swipe X1 Y1 X2 Y2 [--ms 400]` | 滑动；翻主屏页用水平滑，滚列表用竖直滑 |
| `type 文本` | 往当前焦点逐字输入（先点输入框；中文输入法下打字母会进拼音候选，见排障） |
| `press home\|volumeUp\|volumeDown` | 按键 |
| `siri 文本` | 用文字触发 Siri，等同用户说了这句话 |
| `app launch\|activate\|terminate\|state <bundleId>` | 启动 / 切到前台 / 结束 / 查状态（1 未运行 · 2 后台挂起 · 3 后台运行 · 4 前台） |
| `find --label L \| --id ID \| --predicate P [--app 包名]` | 打印匹配元素：类型、label、位置、中心点 |
| `click --label … [--index N] [--app 包名]` | 点第 N 个匹配元素（默认第 0 个）；匹配多个时会提示 |
| `alert text\|accept\|dismiss` | 系统弹窗 |
| `source [--format description\|xml\|json] [--out 路径] [--app 包名]` | 导出元素树 |
| `window` | 屏幕尺寸（点）与方向 |

`--app`：临时指定查询范围的 App（通过 `/appium/settings` 的 `defaultActiveApplication`，查完恢复 `auto`）。
主屏、小组件、系统菜单用 `--app springboard`（= `com.apple.springboard`）。

NSPredicate 例：`"type == 'XCUIElementTypeButton' AND label CONTAINS '添加'"`、`"label BEGINSWITH '移除'"`。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 用法问题：多台设备没给 `--udid`、找不到签名团队、配置键不对 |
| 3 | 没有可用的 iOS 真机 |
| 4 | WDA 没就绪（没启动、启动失败、超时） |
| 5 | WDA 请求失败（元素没找到、会话异常等） |

## 文件

| 路径 | 内容 |
|---|---|
| `~/.config/ios-device-wda/config.json` | `team_id` `bundle_id` `wda_dir`（默认 `~/Projects/tools/WebDriverAgent`）`wda_ref`（默认 `v16.12.10`） |
| `~/.cache/ios-device-wda/<udid>/state.json` | 当前 URL、端口、会话、`runner_pid`、`iproxy_pid` |
| `~/.cache/ios-device-wda/<udid>/build.log` | 最近一次编译日志 |
| `~/.cache/ios-device-wda/<udid>/xcodebuild.log` | WDA 运行日志（`launch-cmd` 给用户的命令也 `tee` 到这里，`attach` 会读它找失败原因和局域网地址） |
| `~/.cache/ios-device-wda/<udid>/shots/` | 截图（原图 + `_s1200` 小图） |
| `<wda_dir>/.wda-build-signature` | 编译指纹（Xcode 版本、WDA 版本、团队、bundle id），不一致就重编 |

## 用到的 WDA 接口（直接 curl 调试时参考）

`GET /status` · `POST /session` · `GET /screenshot` · `GET /session/:id/window/size` · `POST /session/:id/actions`（W3C 触摸）·
`POST /session/:id/wda/keys` · `POST /wda/homescreen` · `POST /session/:id/wda/pressButton` · `POST /session/:id/wda/siri/activate` ·
`POST /session/:id/wda/apps/{launch,activate,terminate,state}` · `POST /session/:id/elements` · `GET /session/:id/element/:eid/rect` ·
`POST /session/:id/element/:eid/click` · `GET /source?format=` · `/session/:id/alert/{text,accept,dismiss}`
