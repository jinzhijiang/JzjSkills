---
name: flutter-ui-automation
description: 用 flutter_skill 连接正在 debug 运行的 Flutter 应用（真机 / 模拟器 / 桌面），做 UI 探查、tap/输入/滑动/断言/截图与 AI 驱动 E2E 自动化。在真机或模拟器上把 app 跑起来后，凡是要做界面交互或自动化验证，优先用本工具（`inspect` + `act`，或 MCP），而不是让用户手点、也不是只靠读代码猜。内含全部 CLI 命令与 MCP 工具用法速查。不适用于纯单元 / Widget 测试（那些用 `flutter test`，参考 flutter-add-widget-test / flutter-add-integration-test）。
---

# flutter_skill UI 自动化

**适用**：连接 debug 运行的 Flutter 应用（真机 / 模拟器 / 桌面），列出可交互元素、tap/输入/滑动/断言/截图、AI 驱动 E2E。
**不适用**：纯单元 / Widget 测试（用 `flutter test`；fvm 项目用 `fvm flutter test`）。

> 底层工具是 [`flutter_skill`](https://pub.dev/packages/flutter_skill)（上游 [ai-dashboad/flutter-skill](https://github.com/ai-dashboad/flutter-skill)），经 VM Service / MCP 连接运行中的 app。本文命令基于 v0.9.36。

## 优先使用（重要）

**只要 app 已在真机或模拟器上 debug 运行，做任何 UI 交互 / 自动化验证都先用 flutter_skill，而不是让用户手动操作、也不是只读代码推断结果。** 典型触发：

- 「点某个按钮 / 进某页 / 填个表单看效果」→ `flutter_skill act tap|enter_text|...`
- 「这个页面现在长什么样 / 有没有某段文案 / 某元素在不在」→ `flutter_skill inspect` 或 `act assert_visible|screenshot`
- 「跑一遍下单 / 登录流程确认没坏」→ `inspect` 拿元素 → `act` 逐步操作 → `act assert_visible` / `act screenshot` 验收

先 `flutter_skill doctor` 确认设备已连、app 在跑；连不上再看「常见坑」。

## 前置条件

- `pubspec.yaml` 引入 `flutter_skill`（二选一）：
  - **pub.dev 版本号**（默认）：`flutter_skill: ^0.9.36`
  - **git 依赖**（需上游未合并的修复，如 OHOS/DDS 场景）：指向 fork [`jinzhijiang/flutter-skill`](https://github.com/jinzhijiang/flutter-skill)（`git: {url: https://github.com/jinzhijiang/flutter-skill.git, ref: main}`）
- `lib/main.dart` 在 `kDebugMode` 下调用 `FlutterSkillBinding.ensureInitialized()`：
  ```dart
  import 'package:flutter_skill/flutter_skill.dart';

  void main() {
    if (kDebugMode) FlutterSkillBinding.ensureInitialized();
    runApp(const MyApp());
  }
  ```
  以上两步可用 `flutter_skill init [项目路径]` 自动完成（还会生成 `.flutter-skill.yaml` 与 IDE 的 MCP 配置）。
- 应用须以 **debug** 运行（release 无法连接 VM Service）。可先用内置 `run` skill 或 `flutter run -d <device>` 跑起来。
- 探查用的客户端是 **pub 全局 CLI**：`dart pub global activate flutter_skill`（fvm 项目：`fvm dart pub global activate flutter_skill`），路径 `~/.pub-cache/bin/flutter_skill`。与 app 内那条依赖相互独立。

## 命令速查

### 原生：真机 / 模拟器 / 桌面（走 VM Service，做原生 app 自动化就用这组）

| 命令 | 用法 | 说明 |
|---|---|---|
| `init` | `flutter_skill init [path]` | 一键接入：加依赖、注入 main.dart binding、生成 `.flutter-skill.yaml` 与 MCP 配置 |
| `doctor` | `flutter_skill doctor` | 环境 / 设备体检：列 ADB 真机与模拟器、SDK、端口、MCP 状态——**先跑它确认设备已连** |
| `launch` | `flutter_skill launch [path] -d <device>` | 启动 app 并自动建立 VM Service 会话；`-d` 选设备 |
| `inspect` | `flutter_skill inspect [ws-uri]` | 列出可交互元素（带 Key/Text）。省略 URI 时自动发现运行中的 app |
| `act` | `flutter_skill act [vm-uri] <action> <params...>` | 执行交互 / 断言（原生自动化主力，动作见下表） |
| `server` | `flutter_skill server` | 启动 MCP 服务（stdio），供 IDE 接入完整原生工具集（不要在前台手动跑，会阻塞等待 MCP 输入） |

**`act <action>` 动作全集**（`inspect` 先拿到 Key 或 Text 再作为 target）：

| action | 用法 | 作用 |
|---|---|---|
| `tap` | `act tap <key\|text>` | 点击元素 |
| `enter_text` | `act enter_text <key> <text>` | 向输入框写入文本 |
| `scroll` / `scroll_to` | `act scroll <key\|text>` | 滚动到目标元素 |
| `swipe` | `act swipe [up\|down\|left\|right] [distance=300]` | 方向滑动 |
| `go_back` | `act go_back` | 返回上一页 |
| `screenshot` | `act screenshot [out.png]` | **原生截图**（走 VM Service，给路径即存 PNG；无路径打印 base64 长度） |
| `get_text` | `act get_text <key>` | 读取元素文本值 |
| `find_element` | `act find_element <key\|text>` | 存在性检查（2s 超时） |
| `wait_for_element` | `act wait_for_element <key\|text> [timeout_ms=5000]` | 等待元素出现，超时非零退出 |
| `assert_visible` | `act assert_visible <key\|text>` | 断言可见，失败抛错非零退出 |
| `assert_gone` | `act assert_gone <key\|text>` | 断言已消失 |

> 原生截图请用 `act screenshot <path>`。顶层 `flutter_skill screenshot` 是 **web 客户端**命令，需先 `serve`，对原生会报 “serve not running”。

### Web：网页 / Flutter Web（走 Chrome CDP / WebMCP）

| 命令 | 用法 | 说明 |
|---|---|---|
| `serve` | `flutter_skill serve <url> [--port=3000 --cdp-port=9222 --headless --no-launch --no-watch]` | 起 WebMCP 服务，自动发现网页元素并暴露为工具 |
| `test` | `flutter_skill test <url> [--platforms=web,android,ios,electron]` | 零配置 web 测试（单/多平台） |
| `explore` | `flutter_skill explore <url>` | AI 测试代理：自动探索并测试 |
| `monkey` | `flutter_skill monkey <url>` | 随机 fuzz 测试 |
| `plan` | `flutter_skill plan <url>` | 自动生成测试用例 |
| `security` | `flutter_skill security <url>` | 安全扫描（XSS / CSRF / 头 / 敏感数据） |
| `diff` | `flutter_skill diff <url>` | 与基线对比状态 |
| 客户端 | `nav` `snap` `screenshot` `tap` `type` `key` `eval` `title` `text` `hover` `upload` `tools` `call` `wait` | 连到**运行中的 `serve`** 发指令（与原生 `act` 是两套，别混用） |

### 其他

`quickstart`（30s 演示）、`demo`（内置示例 app）、`setup`（给 Claude Code 装工具优先级规则）、`report-error`（报 bug）、`--version`。

## MCP 接入（Cursor / Claude，原生工具更全）

IDE 里把 MCP command 指向 **pub 全局** CLI（勿用 npm 旧版，缺 `inspect` 等）：

```json
"command": "${userHome}/.pub-cache/bin/flutter_skill",
"args": ["server"]
```

连接后可用的原生 MCP 工具：

- **连接**：`list_running_apps`、`scan_and_connect`、`connect_app`、`get_connection_status`
- **探查**：`inspect_interactive`、`wait_for_element`、`get_logs`
- **交互**：`tap`、`double_tap`、`long_press`、`enter_text`、`swipe`、`scroll_to`、`screenshot`
- **断言**：`assert_visible`、`assert_text`
- **智能 / AI**：`smart_tap`、`smart_assert`、`explore_actions`
- **调试**：`hot_reload`

推荐流程：`list_running_apps` / `scan_and_connect`（`project_path` 填仓库根目录）→ 失败则 `connect_app` + DDS 的 `ws://127.0.0.1:<port>/ws`（从 `ps aux | grep dds` 的 `--vm-service-uri` 推断）→ `get_connection_status` 确认 → `inspect_interactive` → `tap` / `enter_text` / `screenshot`。

## 典型流程（真机 / 模拟器 E2E，纯 CLI）

```bash
flutter_skill doctor                          # 确认 ADB 真机 / 模拟器已连、app 在跑
# app 已 debug 运行：flutter run -d <device>  或  flutter_skill launch -d <device>
flutter_skill inspect                         # 拿到元素的 Key / Text
flutter_skill act tap "登录"                   # 交互
flutter_skill act enter_text email_field "a@b.com"
flutter_skill act tap "提交"
flutter_skill act wait_for_element "首页" 8000  # 等结果
flutter_skill act assert_visible "首页"         # 断言（失败非零退出，可直接进 CI）
flutter_skill act screenshot ./shot.png       # 原生截图存档
```

## 常见坑

| 现象 | 处理 |
|---|---|
| `scan_and_connect` 找不到应用 | Flutter 3.x 经 DDS 转发，端口可能不在 50000–50100，改用手动 `ws://…/ws` |
| `inspect` / `act` 提示无 app | 确认 `flutter run -d <device>`（fvm 项目用 `fvm flutter run`）已启动且未 crash；`doctor` 看设备是否在列 |
| 想指定设备 | 用 `flutter_skill launch -d <device>`；`inspect` / `act` 不认 `--device-id`，只接受可选的 `ws://…/ws` 或自动发现 |
| 顶层 `screenshot` 报 “serve not running” | 那是 web 客户端命令；原生截图用 `flutter_skill act screenshot <path>` |
| `inspect` MCP 工具不存在 | MCP 指向旧版 npm，改 pub 全局路径 `~/.pub-cache/bin/flutter_skill` |
| CLI 报 `Invalid kernel binary format version (expected 127, found 125)` | 全局 CLI 快照是旧 Dart 编的；换过 SDK 后用当前 SDK 重激活：`dart pub global activate flutter_skill`（fvm 项目用 `fvm dart pub global activate flutter_skill`） |
| `serve` / `explore` / `monkey` / `test` 对原生 app 无效 | 这些走 Chrome CDP（WebMCP），**只支持网页 / Flutter Web**；原生用 `inspect` + `act`（VM Service 直连） |

## 相关 skill

- 内置 **`run`**：先用它把 app 以 debug 跑起来，再连接。
- 内置 **`verify`**：运行 app 并观察行为。
- **`flutter-add-integration-test`** / **`flutter-add-widget-test`**：把临时操作沉淀为正式测试。
