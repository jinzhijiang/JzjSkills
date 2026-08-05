---
name: test-device-allocator
description: 为多项目并发 AI 设备测试分配并互斥锁定 Android、iOS 和 HarmonyOS 真机或模拟器。任务要执行 Flutter run/drive、安装 app、UI 探查、截图点击或 E2E 验证时使用：先用 device_lock.py acquire 领设备，再把 device_id 显式传给每条 flutter -d、adb -s 或 hdc -t 命令，最后 release。支持优先空闲真机、复用或新建模拟器、多平台组合、宿主内存限流和 Android 模拟器 RAM 限制。acquire 默认只亮屏解锁，不改常亮或屏幕超时；构建安装后可再用 wake，长时间无人值守才显式用 --keep-awake。也用于排查设备被占用、模拟器互相污染或卡死、内存不足、设备熄屏、屏幕黑屏点不动、测试后一直亮屏或不会自动锁屏。不用于无需设备的单元或 Widget 测试、启动鸿蒙模拟器或用户手动调试自行选设备。
---

# 并发测试设备分配(device_lock)

**适用**:多个 AI 会话 / 多个项目同时要把 app 跑到真机或模拟器上做自动化测试时,先 `acquire` 领设备、测完 `release` 还锁,避免挤进同一台模拟器互相污染流程。
**不适用**:`flutter test` 单元 / Widget 测试;启动或新建鸿蒙模拟器(用 deveco-studio-emulator,本 skill 只分配**已连上**的鸿蒙目标);人工调试自选设备。

## 何时必须用(重要)

只要接下来要执行 `flutter run` / `flutter drive` / `flutter_skill launch` / 安装 APK·App 到设备,**一律先 acquire,并把返回的 `device_id` 显式传给后续每一条命令的 `-d` / `-s`**:

- 禁止不带 `-d` 让 flutter 自动挑设备——它可能挑中别的会话正在用的那台。
- 一个测试会话只 acquire 一台;同 owner+project 重复 acquire 幂等返回已持有的设备(`reused: true`),不会多占。
- 测试结束(无论成败)都要 release。忘了也有 owner 进程死亡 / TTL 超时兜底回收,但不要依赖兜底。
- 锁是**协作约定**:只对同样走本 skill 的会话生效,拦不住绕过它的进程,所以所有项目的 AI 测试流程都必须从 acquire 开始。

## 平台选择(默认 Android)

`--platform` 支持单值,也支持**逗号组合**(如 `android,harmony`);组合时同一 tier 内按所列顺序优先。

- 用户或任务**明确指定了平台** → 按指定传 `--platform android|ios|harmony`。
- **Flutter 项目未说明平台、也没有开发平台特有功能 → 默认 Android**:`acquire` 不传 `--platform` 即为 android,不要主动升级成 `any` 或 iOS。
- 项目明显只面向某一平台(如任务在改 iOS 侧代码 / 只配置了某端)→ 用对应平台。
- 两端都要测或用户明说都可以 → `--platform any`(= android + ios,**不含鸿蒙**;此时无空闲设备会优先新建 iOS 模拟器,更快)。
- Android 原生项目恒为 android;`--platform ios` 仅 macOS 可用。

### 什么时候可以用鸿蒙设备

**三个条件同时满足**才把鸿蒙放进分配池:

1. Flutter 项目**有鸿蒙模块**(仓库根有 `ohos/` 目录),且用的是 OpenHarmony 版 Flutter SDK(能 `flutter build hap`);
2. 本次开发/验证的功能**不是鸿蒙特有**的(不是只有鸿蒙才有的能力);
3. 这个功能**能在鸿蒙设备上跑起来**(没有依赖 Android/iOS 独有的插件或原生实现)。

满足时用 `--platform android,harmony`:先抢 Android 设备,Android 都被占了就用鸿蒙真机 / 已启动的鸿蒙模拟器,而不是干等或去新建模拟器。任一条不满足就别放开——普通 Flutter SDK 编不出 hap,鸿蒙设备拿到手也跑不起来。

- 本次就是在做**鸿蒙特有功能** → `--platform harmony`。
- 本 skill 只分配**已经连上**(`hdc list targets` 可见且 Connected)的鸿蒙目标:真机走 tier1,已启动的鸿蒙模拟器走 tier2。**不会**帮你启动或新建鸿蒙模拟器——那是 deveco-studio-emulator 的活,先用它把模拟器跑起来,再回来 acquire。

## 前置条件

- 仅需 `python3`(标准库,无第三方依赖)。脚本在本 skill 目录内:`python3 <skill根>/scripts/device_lock.py …`
- Android:需 Android SDK(自动探测 `ANDROID_HOME` → `ANDROID_SDK_ROOT` → `~/Library/Android/sdk`,工具用绝对路径解析,不要求在 PATH);新建 AVD 需本机已装 system image,缺了会报 `NO_SYSTEM_IMAGE` 并给出 sdkmanager 命令(**不会自动下载**)。
- iOS:仅 macOS + Xcode(`xcrun simctl`);没有则自动降级只用 Android。
- HarmonyOS:需 `hdc`(自动探测 `HDC_PATH` → `DEVECO_SDK_HOME` → PATH → DevEco Studio 安装目录 `…/sdk/default/openharmony/toolchains/hdc` → 独立 SDK / command-line-tools);找不到时,`--platform harmony` 报 `ENV_MISSING`,组合里则只是跳过鸿蒙并告警。
- 锁注册表:`~/.ai-device-locks/`(环境变量 `AI_DEVICE_LOCKS_DIR` 可覆盖),同机所有项目共享。

## 命令速查

| 子命令 | 用途 | 常用参数 |
|---|---|---|
| `acquire` | 领取并锁定一台空闲设备,stdout 输出单行 JSON | `--platform android\|ios\|harmony\|any\|逗号组合`(默认 android)、`--device <id>` 指定设备、`--no-physical` 排除真机、`--no-create` 只复用不新建、`--headless`、`--owner $PPID`、`--project <路径>`、`--ttl <小时>`、`--timeout <秒>`、`--max-emulators <N>` 并发模拟器上限、`--memory <MB>` 单台 guest RAM(仅 Android)、`--mem-override` 跳过内存闸门、`--no-wake` 不亮屏解锁、`--keep-awake` 显式临时常亮 |
| `wake` | 把设备重新亮屏解锁(构建/安装后或测试中途熄屏时用) | 不带参数=本会话持有的设备;或 `--key` / `--device` / `--all-mine`;长时间无人值守才传 `--keep-awake` |
| `release` | 释放锁(幂等,恒 exit 0);如显式开过常亮则尽力还原 | `--key <device_key>` / `--device <id>` / `--all-mine` |
| `status` | 设备 × 锁全景(排查谁占了什么) | 无 |
| `clean` | 回收陈旧锁 | `--all` 全清(慎用) |

完整参数、JSON schema、exit code 表与锁目录布局见 [references/cli.md](references/cli.md)。

## 典型流程

```bash
SKILL_DIR=<本 skill 根目录>          # 例:~/.claude/skills/test-device-allocator
cd <被测项目根目录>

# 1. 领设备(默认 android,真机最优先;全被占时自动新建模拟器并等它就绪)
#    要测 iOS 传 --platform ios;两端皆可传 --platform any
#    带 ohos 模块、本次功能不是鸿蒙特有的 Flutter 项目:--platform android,harmony
OUT=$(python3 "$SKILL_DIR/scripts/device_lock.py" acquire --owner $PPID --project "$PWD")
DEVICE_ID=$(echo "$OUT"  | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_id"])')
DEVICE_KEY=$(echo "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_key"])')

# 2. 显式指定设备构建、安装、运行(全链路都带 -d / -s / -t)
flutter run -d "$DEVICE_ID"                     # 或 flutter_skill launch -d "$DEVICE_ID"
# … flutter_skill inspect / act …,或:
# flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d "$DEVICE_ID"
# Android 原生项目:adb -s "$DEVICE_ID" install app.apk 等
# 鸿蒙:hdc -t "$DEVICE_ID" install entry-default.hap 等

# 3. 构建/安装完成后、开始截图或点击前再点亮一次(不用重新 acquire)
python3 "$SKILL_DIR/scripts/device_lock.py" wake --key "$DEVICE_KEY"

# 4. 测完释放(失败也要释放)
python3 "$SKILL_DIR/scripts/device_lock.py" release --key "$DEVICE_KEY"
```

- acquire 失败时 exit code 非 0,stdout JSON 带 `error/message/hint`:`NO_SYSTEM_IMAGE`(4)→ 按 hint 跑 sdkmanager 装镜像后重试;`BUSY`(7)→ 指定的设备被占,去掉 `--device` 让脚本另挑;`MEMORY_PRESSURE`(9)→ 宿主内存不够再开一台模拟器,优先真机/已运行设备或按 hint 释放内存。
- fvm 项目按 flutter-use-fvm 规则把 `flutter` 换成 `fvm flutter`;`device_lock.py` 本身不经 fvm。

## 亮屏解锁(默认无持久副作用)

设备熄屏或停在锁屏时,自动化根本点不动:截图全黑、tap 落空、driver 找不到 widget。acquire 拿到设备后会自动做一次**唤醒 → 解锁**,结果放在返回 JSON 的 `screen` 字段(`state` / `locked` / `actions` / `notes`)。**默认不改设备的常亮或屏幕超时设置**,所以 agent 即使漏掉 release,手机也会按用户原有设置自动锁屏。

| 平台 | 唤醒 | 解锁 | 只有显式 `--keep-awake` 才做(release 时尽力还原) |
|---|---|---|---|
| Android | `input keyevent KEYCODE_WAKEUP` | `wm dismiss-keyguard` | `svc power stayon true` |
| HarmonyOS | `power-shell wakeup` | 锁屏窗口还在就 `uinput` 上滑(分辨率从 hidumper 读) | `power-shell timeout -o 1800000` |
| iOS 模拟器 | 不需要(不会熄屏,也没锁屏) | — | — |
| iOS 真机 | 无法程序控制 | 无法程序解锁 | 不支持;在 UI 测试前手动解锁 |

- **全程尽力而为**:任何一步失败都只记 stderr 日志,不会让 acquire 失败。
- 设了 **PIN / 图案 / 密码**的真机系统不允许程序解锁,`screen.locked` 会是 `true` 并给出提示,此时需要人手解一次。
- 构建/安装可能长于用户的锁屏超时;完成后、真正开始 UI 交互前调一次 `wake --key "$DEVICE_KEY"`。交互中的点击会继续刷新系统计时。
- 只有长时间无人值守、期间又可能没有输入事件的测试才传 `--keep-awake`;改过的原值记在锁 meta 里,`release` / 陈旧锁回收 / `clean` 时尽力还原。`wake --device` 找不到对应锁时会拒绝 `--keep-awake`,避免无处记录原值。
- 完全不想碰屏幕时传 `--no-wake`。旧版 `--no-keep-awake` 保留为兼容参数,新默认本来就不会常亮。

## 分配策略与锁语义

优先级(tier 间严格有序):**空闲真机** > 已在运行的空闲模拟器 > 启动已停止的 AVD / 模拟器 > 新建(`ai-test-*` 命名;`--platform any` 时先建 iOS 模拟器,更快)。多平台组合(`android,harmony`)时,**tier 优先于平台**——鸿蒙真机(tier1)会排在 Android 已运行模拟器(tier2)前面;同一 tier 内才按 `--platform` 里写的顺序。鸿蒙只有 tier1/tier2(本 skill 不启动、不新建鸿蒙模拟器)。

- **内存闸门(启动模拟器数量随宿主内存自适应)**:后两个 tier(启动已停止 / 新建)执行前做双重检查——并发配额 `clamp((总内存-8GB)/每台开销, 1..4)`(默认每台按 4GB 估算,16GB 机 → 最多 2 台,含 iOS Booted;卡死 offline 的模拟器进程也计入)+ 当前可用内存 ≥ 每台开销 + 2GB。**0 台模拟器在运行时,可用内存检查只告警不拦截**——闸门防的是并发互踩,第一台恒放行;因此 `MEMORY_PRESSURE` 只会在已有模拟器在跑时出现。macOS 可用内存按内核 memorystatus 水位(`sysctl kern.memorystatus_level`,把压缩器与文件缓存的可回收量算在内)估算,vm_stat 口径兜底。不过闸则跳过这两个 tier,真机与已运行模拟器不受影响;全部无路可走时报 `MEMORY_PRESSURE`(exit 9)。`--device` 显式指定时只告警不拦截;幂等重取重启自己已持有的模拟器不拦截;探测失败自动放行。覆盖手段:`--max-emulators <N>` / 环境变量 `AI_DEVICE_MAX_EMULATORS`、`--mem-override` / `AI_DEVICE_MEM_OVERRIDE=1`。
- **单台内存(`--memory <MB>`,仅 Android)**:传了就走 `emulator -memory`,新建的 AVD 同时写进 `config.ini` 的 `hw.ramSize`(启动已有 AVD 只覆盖本次,不动它的配置)。每台开销随之改为 `guest RAM + 1.5GB`,所以压小内存能换配额:16GB 机上默认 2 台,`--memory 1024` → 3 台。低于 2048MB 会告警(API 31+ 镜像的 lowmemorykiller 可能杀掉被测 app);RAM 与 AVD 配置不一致会作废 quickboot 快照,那次是冷启动。iOS 模拟器不是 VM,simctl 没有等价旋钮,只能靠限台数。
- 上锁 = 原子创建 `~/.ai-device-locks/<key>/`,内含 meta.json(owner_pid、project、时间、TTL)。
- 陈旧回收:owner 进程已死 → 立即可回收;存活但锁龄超 TTL(默认 8h)→ 可回收。每次 acquire 起手会**全局清扫**所有陈旧锁(不限本次要用的设备),死锁不会在注册表里躺尸。长时间压测传大 `--ttl`。
- **release 只还锁,模拟器保持运行**,给下个会话热复用;彻底关机 / 删除 `ai-test-*` 模拟器的手动命令见 [references/troubleshooting.md](references/troubleshooting.md)。

## 与其他 skill 配合

- **flutter-add-integration-test**:其 Android `flutter drive` 示例不带 `-d`,并发场景必须补上 `-d $DEVICE_ID`。
- **flutter-use-fvm**:flutter / dart 命令按其规则加 `fvm` 前缀。

## 常见坑

| 现象 | 处理 |
|---|---|
| acquire 卡 1-5 分钟 | 正在冷启动模拟器(Android 上限 300s / iOS 180s)。急用可 `--no-create` 或 `--device` 指定现成设备 |
| exit 4 `NO_SYSTEM_IMAGE` | 复制 JSON `hint` 里的 sdkmanager 命令装镜像,再重跑 acquire |
| exit 7 `BUSY` | `--device` 指定的设备被别的会话占用;去掉 `--device` 另挑,或 `status` 看占用者 |
| exit 9 `MEMORY_PRESSURE` | 已有模拟器在跑、宿主内存不够再开一台(0 台在跑时不会出现此错)。优先领真机;或关闭闲置模拟器(`adb -s <id> emu kill`)后重试;Android 可 `--memory 1024` 压小单台换配额;确认有余量可 `--mem-override` 或调 `--max-emulators` |
| 模拟器画面停帧 / adb 挂死 / `Lost connection to device` | 多为宿主内存超卖把 QEMU 拖进 swap(渲染管线冻结)。杀掉对应 qemu 进程冷启动,减少并发模拟器数;内存闸门就是为预防它 |
| adb 里设备 unauthorized / offline | 不参与分配;真机上确认 USB 调试授权弹窗 |
| 截图全黑 / 点击没反应 / driver 找不到 widget | 默认保留系统自动锁屏;构建/安装后或测试中途跑 `wake --key $DEVICE_KEY` 再点亮;`screen.locked=true` 说明设了 PIN,需人工解一次 |
| 测试后手机一直亮屏 / 不会自动锁屏 | 新版默认不再修改常亮设置;Android 可用 `adb -s <id> shell settings get global stay_on_while_plugged_in` 查看,`7` 通常表示充电时全部常亮。确认是测试遗留后用 `settings put global stay_on_while_plugged_in 0` 恢复;不要在不知道原值时自动批量重置用户设备 |
| 鸿蒙设备不参与分配 | 只有 `hdc list targets -v` 里 **Connected** 的目标才算;还要显式 `--platform harmony` 或 `android,harmony`(`any` 不含鸿蒙) |
| exit 6 `ENV_MISSING` 且提到 hdc | 没装 DevEco Studio,或 hdc 不在常见位置:设 `HDC_PATH` 指向 hdc 可执行文件 |
| 忘了 release / 会话崩了 | 下次任意 acquire 起手全局回收死 pid / 超 TTL 的锁;不放心跑 `clean` |
| flutter 挑错设备 | 说明有命令没带 `-d`;全链路显式传 device id |
| Linux 宿主要 iOS | 不支持,`--platform ios` 报 exit 6;`any` 自动只用 Android |

## 相关 skill

- flutter-add-integration-test:把验证过的流程沉淀为正式集成测试
- flutter-use-fvm:fvm 项目的命令前缀规则
- deveco-studio-emulator:启动 / 新建 / 管理鸿蒙模拟器(本 skill 只分配已连上的鸿蒙目标,不负责把它跑起来)
