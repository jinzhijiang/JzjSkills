---
name: test-device-allocator
description: 多项目并发 AI 自动化测试的设备分配与互斥锁。任何要把 Flutter / Android / iOS app 跑到真机或模拟器上做自动化测试、UI 探查、E2E 验证之前,先运行本 skill 的 scripts/device_lock.py acquire 领取一台空闲设备(优先空闲真机,其次已在运行的空闲模拟器,再启动已停止的模拟器,最后自动新建),拿到 JSON 里的 device id 后显式传给 flutter run -d / flutter drive -d / adb -s,测试完 release 释放。触发词:设备分配、分配模拟器、锁定设备、设备被占用、多项目同时测试、并发测试、抢设备、emulator、simulator、AVD、adb devices、xcrun simctl、模拟器互相污染。不适用于:单元测试与 Widget 测试(flutter test,不需要设备)、HarmonyOS 模拟器(用 deveco-studio-emulator)、用户手动开发调试自行选设备的场景。
---

# 并发测试设备分配(device_lock)

**适用**:多个 AI 会话 / 多个项目同时要把 app 跑到真机或模拟器上做自动化测试时,先 `acquire` 领设备、测完 `release` 还锁,避免挤进同一台模拟器互相污染流程。
**不适用**:`flutter test` 单元 / Widget 测试;HarmonyOS(用 deveco-studio-emulator);人工调试自选设备。

## 何时必须用(重要)

只要接下来要执行 `flutter run` / `flutter drive` / `flutter_skill launch` / 安装 APK·App 到设备,**一律先 acquire,并把返回的 `device_id` 显式传给后续每一条命令的 `-d` / `-s`**:

- 禁止不带 `-d` 让 flutter 自动挑设备——它可能挑中别的会话正在用的那台。
- 一个测试会话只 acquire 一台;同 owner+project 重复 acquire 幂等返回已持有的设备(`reused: true`),不会多占。
- 测试结束(无论成败)都要 release。忘了也有 owner 进程死亡 / TTL 超时兜底回收,但不要依赖兜底。
- 锁是**协作约定**:只对同样走本 skill 的会话生效,拦不住绕过它的进程,所以所有项目的 AI 测试流程都必须从 acquire 开始。

## 前置条件

- 仅需 `python3`(标准库,无第三方依赖)。脚本在本 skill 目录内:`python3 <skill根>/scripts/device_lock.py …`
- Android:需 Android SDK(自动探测 `ANDROID_HOME` → `ANDROID_SDK_ROOT` → `~/Library/Android/sdk`,工具用绝对路径解析,不要求在 PATH);新建 AVD 需本机已装 system image,缺了会报 `NO_SYSTEM_IMAGE` 并给出 sdkmanager 命令(**不会自动下载**)。
- iOS:仅 macOS + Xcode(`xcrun simctl`);没有则自动降级只用 Android。
- 锁注册表:`~/.ai-device-locks/`(环境变量 `AI_DEVICE_LOCKS_DIR` 可覆盖),同机所有项目共享。

## 命令速查

| 子命令 | 用途 | 常用参数 |
|---|---|---|
| `acquire` | 领取并锁定一台空闲设备,stdout 输出单行 JSON | `--platform android\|ios\|any`(默认 any)、`--device <id>` 指定设备、`--no-physical` 排除真机、`--no-create` 只复用不新建、`--headless`、`--owner $PPID`、`--project <路径>`、`--ttl <小时>`、`--timeout <秒>` |
| `release` | 释放锁(幂等,恒 exit 0) | `--key <device_key>` / `--device <id>` / `--all-mine` |
| `status` | 设备 × 锁全景(排查谁占了什么) | 无 |
| `clean` | 回收陈旧锁 | `--all` 全清(慎用) |

完整参数、JSON schema、exit code 表与锁目录布局见 [references/cli.md](references/cli.md)。

## 典型流程

```bash
SKILL_DIR=<本 skill 根目录>          # 例:~/.claude/skills/test-device-allocator
cd <被测项目根目录>

# 1. 领设备(真机最优先;全被占时自动新建模拟器并等它就绪)
OUT=$(python3 "$SKILL_DIR/scripts/device_lock.py" acquire --platform any --owner $PPID --project "$PWD")
DEVICE_ID=$(echo "$OUT"  | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_id"])')
DEVICE_KEY=$(echo "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_key"])')

# 2. 显式指定设备跑测试(全链路都带 -d / -s)
flutter run -d "$DEVICE_ID"                     # 或 flutter_skill launch -d "$DEVICE_ID"
# … flutter_skill inspect / act …,或:
# flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d "$DEVICE_ID"
# Android 原生项目:adb -s "$DEVICE_ID" install app.apk 等

# 3. 测完释放(失败也要释放)
python3 "$SKILL_DIR/scripts/device_lock.py" release --key "$DEVICE_KEY"
```

- acquire 失败时 exit code 非 0,stdout JSON 带 `error/message/hint`:`NO_SYSTEM_IMAGE`(4)→ 按 hint 跑 sdkmanager 装镜像后重试;`BUSY`(7)→ 指定的设备被占,去掉 `--device` 让脚本另挑。
- fvm 项目按 flutter-use-fvm 规则把 `flutter` 换成 `fvm flutter`;`device_lock.py` 本身不经 fvm。

## 分配策略与锁语义

优先级(tier 间严格有序):**空闲真机** > 已在运行的空闲模拟器 > 启动已停止的 AVD / 模拟器 > 新建(`ai-test-*` 命名;`--platform any` 时先建 iOS 模拟器,更快)。

- 上锁 = 原子创建 `~/.ai-device-locks/<key>/`,内含 meta.json(owner_pid、project、时间、TTL)。
- 陈旧回收:owner 进程已死 → 立即可回收;存活但锁龄超 TTL(默认 8h)→ 可回收。长时间压测传大 `--ttl`。
- **release 只还锁,模拟器保持运行**,给下个会话热复用;彻底关机 / 删除 `ai-test-*` 模拟器的手动命令见 [references/troubleshooting.md](references/troubleshooting.md)。

## 与其他 skill 配合

- **flutter-ui-automation**:先 acquire → `flutter run -d $DEVICE_ID`(debug)起 app → 再 `inspect` / `act`。多 app 并发时它的自动发现不可靠,launch 必须带 `-d`。
- **flutter-add-integration-test**:其 Android `flutter drive` 示例不带 `-d`,并发场景必须补上 `-d $DEVICE_ID`。
- **flutter-use-fvm**:flutter / dart 命令按其规则加 `fvm` 前缀。

## 常见坑

| 现象 | 处理 |
|---|---|
| acquire 卡 1-5 分钟 | 正在冷启动模拟器(Android 上限 300s / iOS 180s)。急用可 `--no-create` 或 `--device` 指定现成设备 |
| exit 4 `NO_SYSTEM_IMAGE` | 复制 JSON `hint` 里的 sdkmanager 命令装镜像,再重跑 acquire |
| exit 7 `BUSY` | `--device` 指定的设备被别的会话占用;去掉 `--device` 另挑,或 `status` 看占用者 |
| adb 里设备 unauthorized / offline | 不参与分配;真机上确认 USB 调试授权弹窗 |
| 忘了 release / 会话崩了 | 下次 acquire 自动回收死 pid 的锁;不放心跑 `clean` |
| flutter 挑错设备 | 说明有命令没带 `-d`;全链路显式传 device id |
| Linux 宿主要 iOS | 不支持,`--platform ios` 报 exit 6;`any` 自动只用 Android |

## 相关 skill

- flutter-ui-automation:拿到设备、app 跑起来之后的 UI 探查与自动化操作
- flutter-add-integration-test:把验证过的流程沉淀为正式集成测试
- flutter-use-fvm:fvm 项目的命令前缀规则
- deveco-studio-emulator:HarmonyOS 模拟器另走一套(不归本 skill 管)
