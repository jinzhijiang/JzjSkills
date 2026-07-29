# device_lock.py CLI 完整契约

调用形式:`python3 <skill根>/scripts/device_lock.py <子命令> [参数]`。
stdout 恒为**单行 JSON**(机读);所有过程日志走 stderr。仅 python3 标准库,无第三方依赖。

## 锁注册表

- 根目录:`~/.ai-device-locks/`,环境变量 `AI_DEVICE_LOCKS_DIR` 可覆盖(测试隔离用;各会话必须一致,否则互相看不见锁)。
- 每把锁一个目录:`<根>/<sanitized-key>/meta.json`。目录名由 device_key 中非 `[A-Za-z0-9._-]` 的字符替换为 `_` 得到(如 `android-avd:Pixel_10` → `android-avd_Pixel_10`)。
- 上锁 = `mkdir` 原子创建目录(多进程同刻抢同一设备只有一个成功)。
- 解锁 / 回收 = 先原子 `rename` 为 `<dir>.reclaim-<pid>-<ts>` 墓碑再删除(rename-then-delete,并发回收只有一个赢家);超过 10 分钟的墓碑残骸会被顺手清理。

## device_key 规则

| 键 | 设备 |
|---|---|
| `android-device:<serial>` | Android 真机(wifi adb 的 `ip:port` 串号同样按真机处理) |
| `android-avd:<AVD名>` | Android 模拟器——运行与否都按 AVD 名锁,避免重启后端口(emulator-5554 → 5556)漂移;同名 AVD 系统本身禁止双开 |
| `ios-sim:<udid>` | iOS 模拟器 |
| `ios-device:<udid>` | iOS 真机(devicectl 可见且 connected/wired) |

## meta.json 字段

`allocator_version`、`device_key`、`platform`(android|ios)、`kind`(physical|emulator|simulator)、`device_id`(serial/udid;AVD 未启动时为 null,boot 后回填)、`name`(AVD 名 / 设备名)、`owner_pid`、`project`、`acquired_at`(ISO 带时区)、`ttl_hours`、`created_by_allocator`、`booted_by_allocator`、`memory_mb`(本次启动施加的 guest RAM;未指定 / 不适用为 null,幂等重启会沿用它)。

## 陈旧(stale)判定

1. `owner_pid` 已死 → 立即陈旧;
2. `owner_pid` 存活但锁龄 > `ttl_hours`(默认 8h)→ 陈旧(防会话长开泄漏);
3. meta.json 缺失 / 损坏:目录 mtime 距今 < 60s 视为持有中(并发写宽限),否则陈旧。

acquire 遇到陈旧锁自动回收后抢占;`clean` 手动回收。

## acquire

| 参数 | 默认 | 说明 |
|---|---|---|
| `--platform {android,ios,any}` | android | 平台过滤;Flutter 项目未指明平台、也没开发平台特有功能时用默认 android;两端皆可才传 any;`ios` 仅 macOS |
| `--device <id>` | — | 指定设备(serial / UDID / AVD 名),只尝试它;被占 → exit 7 |
| `--no-physical` | 关 | 排除真机(不想占用插着的手机时用) |
| `--no-create` | 关 | 只复用现有设备,无空闲直接 exit 3 |
| `--headless` | 关 | 新启动的模拟器不开窗口(Android `-no-window`;iOS 不拉起 Simulator.app) |
| `--owner <pid>` | 自动取祖父进程 | 锁持有者;AI 会话里建议显式传 `$PPID` |
| `--project <path>` | 当前目录 | 记录占用方,亦是幂等重取的匹配键 |
| `--ttl <小时>` | 8 | 本锁的最大年龄 |
| `--timeout <秒>` | Android 300 / iOS 180 | 模拟器启动等待上限 |
| `--max-emulators <N>` | 按内存自动 | 并发模拟器总数上限(Android 运行中 emulator + iOS Booted 合计;环境变量 `AI_DEVICE_MAX_EMULATORS` 亦可覆盖,显式值不受 1..4 夹取限制) |
| `--memory <MB>` | 用 AVD 自带 `hw.ramSize` | Android 模拟器 guest RAM,512-8192,越界 exit 2;同时收窄内存闸门的每台开销估算(环境变量 `AI_DEVICE_EMULATOR_MEMORY` 亦可设定,`--memory` 优先) |
| `--mem-override` | 关 | 跳过内存闸门(等效环境变量 `AI_DEVICE_MEM_OVERRIDE=1`) |

分配优先级(tier 间严格有序,tier 内确定性排序):

1. **空闲真机**:Android(`adb devices` state=device,按 adb 输出序)→ iOS(devicectl connected)
2. **已在运行的空闲模拟器**:Android 运行中 emulator(按 AVD 名序)→ iOS Booted(`ai-test-*` 优先 → runtime 新 → iPhone 优先)
3. **已停止的模拟器(启动它)**:Android `emulator -list-avds`(`ai-test-*` 优先 → 字母序)→ iOS Shutdown(同 2 排序)
4. **新建**:命名 `ai-test-<时间戳>-<pid>`;`--platform any` 时先 iOS(创建+启动 ~30s,比 Android 冷启动轻)再 Android。Android 从已装 system-images 挑最高 API、`google_apis` 系 tag 优先、匹配宿主 abi(Apple Silicon → arm64-v8a);iOS 挑最新 runtime + 编号最大的 iPhone 机型

### 内存闸门(tier 3 / 4 前置检查)

启动或新建模拟器会增加宿主内存占用,过闸才执行;tier 1(真机)与 tier 2(已运行模拟器)不受影响。两项检查任一不过即拦截:

1. **并发配额**:`运行中模拟器数 < max_vms`。运行数 = adb 可见的全部 `emulator-*` 串号(含 offline——卡死的 qemu 进程仍占内存)+ iOS Booted 模拟器。`max_vms` 取值优先级:`--max-emulators` > `AI_DEVICE_MAX_EMULATORS` > 自动推导 `clamp(⌊(总内存-8GB)/每台开销⌋, 1..4)`。
2. **可用内存**:当前可用 ≥ 每台开销 + 2GB 安全垫。macOS 按 `vm_stat` 的 free+inactive+purgeable+speculative 估算,Linux 用 `MemAvailable`,Windows 用 `GlobalMemoryStatusEx`。

**每台开销**:默认 4.0GB(≈2GB guest RAM + QEMU/图形转发);`--platform android --memory <MB>` 时改为 `MB/1024 + 1.5GB`。`--platform any` / `ios` 即使传了 `--memory` 也按默认 4.0GB 估算——候选可能落到无法限内存的 iOS 模拟器上。16GB 机上的 `max_vms`:默认 2,`--memory 1024` → 3,`--memory 1536`/`2048` → 2;8GB 机恒为 1;24GB+ 触顶 4。

拦截行为:tier 3 候选被跳过(stderr 记一条日志);走到 tier 4 仍被拦 → exit 9 `MEMORY_PRESSURE`。三个豁免:`--device` 显式指定只告警不拦;幂等重取中重启自己已持有的模拟器不拦(净占用不增);内存探测失败自动放行(fail-open)。`--mem-override` / `AI_DEVICE_MEM_OVERRIDE=1` 整体跳过。

### 单台模拟器内存(`--memory`)

仅 Android。iOS 模拟器不是虚拟机(宿主原生进程按需吃内存),`simctl` 没有等价参数,传了会在 stderr 告警并忽略。

| 场景 | 行为 |
|---|---|
| tier 4 新建 AVD | `avdmanager create` 后把 `hw.ramSize=<MB>` 写进 `<AVD>.avd/config.ini`,再以 `-memory <MB>` 启动。持久生效:之后任何人(含不带 `--memory`)启动这台都按此内存 |
| tier 3 启动已停止的 AVD | 只在本次 `emulator -memory <MB>` 覆盖,**不改**用户 AVD 的 config.ini;与配置值不一致时 stderr 提示 |
| tier 1/2(真机、已在运行的模拟器) | 无效——跑起来的 VM 改不了 RAM;结果 JSON 的 `memory_mb` 为 null |
| 幂等重取需要重启已持有的 AVD | 沿用锁里记的 `memory_mb`(本次显式 `--memory` 优先),避免 RAM 反复变动 |

注意:`-memory` 与 AVD 配置不一致会作废 quickboot 快照,那次必然冷启动(acquire 从 ~30s 变 1-2 分钟)。低于 2048MB 会 stderr 告警:API 31+ 镜像的 lowmemorykiller 容易杀掉被测 app,表现为莫名的 `Lost connection to device`。`vm.heapSize`(单 app Dalvik 堆)不受本参数影响。

成功 JSON(实际为单行,此处展开示意):

```json
{
  "ok": true, "action": "acquire",
  "device_key": "android-avd:Pixel_10", "platform": "android",
  "kind": "emulator", "device_id": "emulator-5554", "name": "Pixel_10",
  "memory_mb": 1024,
  "created": false, "booted": true, "reused": false,
  "owner_pid": 4242, "project": "/path/to/app",
  "lock_dir": "/Users/me/.ai-device-locks/android-avd_Pixel_10",
  "release_cmd": "python3 /abs/path/scripts/device_lock.py release --key android-avd:Pixel_10",
  "usage": {
    "flutter_run": "flutter run -d emulator-5554",
    "flutter_drive": "flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d emulator-5554",
    "adb": "adb -s emulator-5554 <command>"
  }
}
```

字段说明:`created`(本次新建的模拟器)、`booted`(本次由脚本启动)、`reused`(幂等复用已持有的锁)、`memory_mb`(本次施加的 guest RAM;真机 / iOS / 复用已在运行的模拟器为 null)、`release_cmd`(可直接执行的释放命令)。

失败 JSON 统一:`{"ok": false, "action": "acquire", "error": "<错误码名>", "message": "…", "hint": "…"}`。

## release

`--key <device_key>` / `--device <id或名>` / `--all-mine [--owner <pid>]` 三选一。幂等,恒 exit 0。
输出:`{"ok": true, "action": "release", "released": [...], "not_found": [...]}`。
**只还锁,不关模拟器**(留给下个会话热复用)。

## status

无参数。输出:

```json
{"ok": true, "action": "status", "lock_root": "…",
 "memory": {"total_gb": 16.0, "available_gb": 5.2, "running_vms": 1, "max_vms": 2,
            "per_vm_gb": 4.0, "reserve_gb": 8.0, "vm_overhead_gb": 1.5,
            "can_start_new_vm": true},
 "devices": [{"key": "…", "platform": "…", "kind": "…", "device_id": "…", "name": "…",
              "state": "running|booted|stopped|shutdown|connected",
              "ram_mb": 2048,
              "lock": null | {"state": "HELD|STALE", "reason": "dead_pid|ttl_expired|…",
                               "owner_pid": 1, "owner_alive": true, "project": "…",
                               "acquired_at": "…", "age_hours": 0.5,
                               "created_by_allocator": false}}],
 "orphan_locks": [...], "warnings": [...]}
```

`orphan_locks` 是锁着但设备已消失(如 AVD 被删)的锁;unauthorized / offline 设备在 `warnings` 里。
`ram_mb` 是 AVD `config.ini` 里配置的 guest RAM(Android 模拟器专有,其余设备为 null),用来看哪台吃得多;`memory.per_vm_gb` / `vm_overhead_gb` 是闸门的默认估算基数(status 不接受 `--memory`,恒按默认 4.0GB 展示)。

## clean

不带参数:回收所有陈旧锁;`--ttl <小时>` 按指定 TTL 重新判定;`--all` 清除全部锁(确认没有会话在测试时才用)。
输出:`{"ok": true, "action": "clean", "removed": [...], "kept": [...]}`。

## exit code 表

| 码 | 名 | 含义 |
|---|---|---|
| 0 | OK | 成功 |
| 2 | — / ARGS | 参数错误(argparse);或 `--memory` / `AI_DEVICE_EMULATOR_MEMORY` 非法(非整数、不在 512-8192) |
| 3 | NO_DEVICE | 无可用候选且不允许/无法新建;或 `--device` 目标不存在 |
| 4 | NO_SYSTEM_IMAGE | Android 新建被缺镜像挡住(hint 给 sdkmanager 命令,不自动下载) |
| 5 | BOOT_TIMEOUT | 模拟器启动/就绪超时(锁已回滚,本次拉起的模拟器进程也会被关闭) |
| 6 | ENV_MISSING | 所选平台工具链缺失(无 Android SDK / 无 xcrun) |
| 7 | BUSY | `--device` 指定的设备被存活锁占用 |
| 8 | INTERNAL | 未预期异常(traceback 在 stderr) |
| 9 | MEMORY_PRESSURE | 内存闸门拦截:配额已满或可用内存不足,不再启动/新建模拟器(真机不受影响) |

## 幂等与并发语义

- 同 `owner`+`project` 重复 acquire → 返回已持有设备,`reused: true`,并刷新 `acquired_at`(续 TTL);若该设备已被手动关掉,会自动重新启动它(RAM 沿用锁里的 `memory_mb`)。
- 多会话同刻抢同一候选:`mkdir` 只有一个成功,失败方自动尝试下一候选;双方同时判定某锁陈旧时,rename 先到者才有权删除。
- 候选启动失败会先回滚锁、关掉本次拉起的模拟器进程,再换下一台;不会遗留"锁着/跑着一台起不来的设备"。
- 锁着的模拟器被人手动关机:锁仍视为持有(owner 可能重启它),不会被误回收;在 status 里表现为 `state: stopped` 且 `lock` 非空。
