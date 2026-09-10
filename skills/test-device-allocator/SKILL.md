---
name: test-device-allocator
description: 在这台机器上碰任何 Android、iOS 或 HarmonyOS 真机/模拟器之前先领锁，避免和别的 AI 会话抢同一台设备。**只要你接下来要跑 `adb -s`、`adb install`、`adb shell input`/`screencap`、`hdc -t`、`flutter run/drive/install`、或用模拟器 MCP 点屏截图，第一条命令就必须是 `device_lock.py acquire`，而不是那条 adb**。已经用 `adb devices` 拿到了设备 id、不需要帮你挑设备时同样要走：`acquire --device <id>` 的作用是确认没人占着，被占会直接报出对方的 owner_pid 与 project。不确定要不要领？`status --device <id>` 一行就能看出来，几乎零成本。别用「现在应该没人用吧」来跳过——**别的会话在不在跑，你在自己的会话里是看不见的**。也用于排查这些症状：点击落到别的 app 上、应用反复被切到前台、截图拍到的是另一个 app、设备被占用、模拟器互相污染或卡死、内存不足、屏幕黑屏点不动、测试中途频繁锁屏、测完一直亮屏不锁屏。测完当前这步、后面没有紧接着要用设备的步骤就立刻 release。不用于无需设备的单元或 Widget 测试、启动鸿蒙模拟器、用户手动调试自行选设备。
---

# 并发测试设备分配(device_lock)

**适用**:多个 AI 会话 / 多个项目同时要把 app 跑到真机或模拟器上做自动化测试时,先 `acquire` 领设备、测完 `release` 还锁,避免挤进同一台模拟器互相污染流程。
**不适用**:`flutter test` 单元 / Widget 测试;启动或新建鸿蒙模拟器(用 deveco-studio-emulator,本 skill 只分配**已连上**的鸿蒙目标);人工调试自选设备。

## 硬规则:第一条设备命令是 acquire,不是 adb

**碰设备的第一条命令不是 `adb` / `hdc` / `flutter run`,而是 `acquire`。** 没有例外,没有前置条件。

触发它的不是「我要开始一轮设备测试了」这种有仪式感的时刻——真实情况是你会一小步一小步滑进去:
`flutter devices` 看一眼 → `adb devices` 拿到 id → `adb install` 装个包 → `adb shell input tap` 点两下。
每一步单独看都像顺手为之,合起来已经占了别人的手机好几个小时。所以判据是**动作**,不是意图:

> 只要下一条命令里出现 `adb -s` / `adb install` / `adb shell input` / `screencap` / `hdc -t` /
> `flutter run|drive|install` / **`patrol test|develop`** / 模拟器 MCP 的点击截图 /
> **patrol MCP 的 `patrol-run`**,就先 acquire。

### ⚠️ 「我已经知道要用哪台了」不是跳过的理由

这是最常见的绕过方式:`adb devices` 列出三台,挑一台就开干——毕竟不需要谁帮我挑。
但 acquire 的作用**从来不是帮你挑设备,是确认没人占着**。手上已有 id 时照样走:

```bash
python3 <skill根>/scripts/device_lock.py acquire --device <id> --project "$PWD"
```

被别人占着时它以 `EXIT_BUSY` 拒绝,并直接告诉你对方的 `owner_pid` 与 `project`,你当场就能换一台。

### ⚠️ 不要传 `--owner $PPID`

**别传 `--owner`,让脚本自己判定。** 它的 `default_owner_pid()` 会主动走到
**祖父进程**(python → shell → AI 会话),拿到的是真正长命的那个 pid。

而 AI harness 里每条命令通常是**新起的短命 shell**,`$PPID` 拿到的可能就是那个
转瞬即死的 shell。锁一落库 owner 就死了 → 判定 `dead_pid` → 变陈旧 →
**几十分钟后被别的会话正当回收**,而你还以为自己占着。

2026-08-28 真踩到:`acquire --owner $PPID` 领到的锁,owner 43726 当场死亡,
半小时后设备被另一个项目的会话拿走,期间没有任何报错。

只有你**确知**某个长命进程的 pid 时才显式传 `--owner`。

### ⚠️ 「现在应该没人在用吧」是不可能成立的判断

**别的会话在不在跑,你在自己的会话里看不见。** 任何形式的「这台看起来是空的」「同时开两个会话的概率不大」
都不是判断,是赌。不确定就花一秒:

```bash
python3 <skill根>/scripts/device_lock.py status --device <id>   # 只看这一台
python3 <skill根>/scripts/device_lock.py status --busy          # 谁占着什么
```

### 症状:一整轮跑下来「0 个测试结果」/ 装包卡到超时 / 设备从 adb 里消失

**先怀疑手机,再怀疑代码。**

失败和「没有结果」是两回事:`Failed: 2` 是测试跑了并给出了判决,值得去读代码;
而 `Total: 0` 是**一个判决都没拿到**,那多半根本没跑起来。后者常见的三种原因里,
只有一种跟你的改动有关:

| 现象 | 是什么 | 怎么办 |
|---|---|---|
| `Total: 0` + 装包超时(`ShellCommandUnresponsiveException`)/ `INSTRUMENTATION_ABORTED: System has crashed` | **设备正在掉线** | `adb devices` + `adb -s <id> shell echo ok`;换一台 |
| 跑之前就报 TLS / `HandshakeException` / 拉不到依赖 | 网络或工具链 | 重试 |
| `Total: N` 且 `Failed: M` | 真的测试失败 | 才轮到读代码 |

2026-09-09 的实际经过:一台 Pixel 2 XL 全程稳稳地报 `device`,却
**连续三轮**把 E2E 跑成 0 结果——先是装 APK 卡到 ~315s 超时,再是
`System has crashed`,最后从 `adb devices` 里彻底消失。因为报错长得像构建问题,
中间白白改了两轮配置、试了两个错误假设,~15 分钟全花在找不存在的代码 bug 上。

**代价极低的那一步永远先做**:`adb devices` 一秒钟就能把这类问题摘干净。

> `acquire` 现在会先 `adb shell echo ok` 探一句话再派设备(约 50ms),
> 报 `device` 却不答话的机器直接跳过。但**它挡不住「还答得上话、干活却已经很勉强」
> 的那一段**——上面那台掉线前就是这样。所以这条症状表仍然要用。

### 症状:点击落到别的 app / 应用反复被切走 / 截图拍到的是另一个 app

**这不是设备坏了,也不是你的 app 崩了,是另一个会话正在用这台设备。**
典型表现:你 `am start` 自己的 app,几秒后前台变成一个完全不相干的应用;
按坐标点击落进了那个应用;`screencap` 拍到的是它的界面。
先 `status --busy` 看谁占着,然后**换一台**,不要跟它抢——两个会话轮流把对方切走,谁的测试都做不完。

## 何时必须用(重要)

只要接下来要执行 `flutter run` / `flutter drive` / `patrol test` / `patrol develop` /
`flutter_skill launch` / 安装 APK·App 到设备,**一律先 acquire,并把返回的 `device_id`
显式传给后续每一条命令的 `-d` / `-s`**:

- 禁止不带 `-d` 让 flutter 自动挑设备——它可能挑中别的会话正在用的那台。
- 一个测试会话只 acquire 一台;同 owner+project 重复 acquire 幂等返回已持有的设备(`reused: true`),不会多占。
- 测试结束(无论成败)都要 release。忘了也有 owner 进程死亡 / TTL 超时兜底回收,但不要依赖兜底。
- **测完即放**:当前步骤的设备操作一结束,后面没有**紧接着**要用设备的步骤(比如接下来是改代码、分析日志、写报告),就立即 release,不要为「等会儿可能还要测」占着手机——真机占着就一直亮屏耗电,还挡住别的会话。之后真要再测,重新 acquire 即可:幂等、模拟器热复用,代价很低。只有连续多轮设备操作之间的短间隙才值得继续持有。
- 锁是**协作约定**:只对同样走本 skill 的会话生效,拦不住绕过它的进程,所以所有项目的 AI 测试流程都必须从 acquire 开始。

## 平台选择(默认 Android)

`--platform` 支持单值,也支持**逗号组合**(如 `android,harmony`);组合时同一 tier 内按所列顺序优先。

- 用户或任务**明确指定了平台** → 按指定传 `--platform android|ios|harmony`。
- **Flutter 项目未说明平台、也没有开发平台特有功能 → 默认 Android**:`acquire` 不传 `--platform` 即为 android,不要主动升级成 `any` 或 iOS。**项目支持鸿蒙时例外**:默认改用 `--platform android,harmony`,鸿蒙真机可直接用于测试(见下节)。
- 项目明显只面向某一平台(如任务在改 iOS 侧代码 / 只配置了某端)→ 用对应平台。
- 两端都要测或用户明说都可以 → `--platform any`(= android + ios,**不含鸿蒙**;此时无空闲设备会优先新建 iOS 模拟器,更快)。
- Android 原生项目恒为 android;`--platform ios` 仅 macOS 可用。

### Flutter 项目支持鸿蒙 → 鸿蒙真机可直接用于测试

只要 Flutter 项目**支持鸿蒙**——仓库根有 `ohos/` 目录,且用的是 OpenHarmony 版 Flutter SDK(能 `flutter build hap`)——就默认把鸿蒙放进分配池:`acquire --platform android,harmony`。鸿蒙真机是与 Android 同级的测试目标:Android 设备被占、或内存闸门不允许再开模拟器时,直接跑到鸿蒙真机 / 已启动的鸿蒙模拟器上验证,而不是干等。

两种情况收窄平台,不用组合:

- 本次功能**依赖 Android/iOS 独有的插件或原生实现**(鸿蒙上跑不起来)→ 只用对应平台。
- 本次就是在做**鸿蒙特有功能** → `--platform harmony`。

不支持鸿蒙的项目(没有 `ohos/` 目录,或普通 Flutter SDK)别放开——编不出 hap,鸿蒙设备拿到手也跑不起来。

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
| `acquire` | 领取并锁定一台空闲设备,stdout 输出单行 JSON | `--platform android\|ios\|harmony\|any\|逗号组合`(默认 android)、`--device <id>` 指定设备、`--no-physical` 排除真机、`--no-create` 只复用不新建、`--headless`、`--project <路径>`、`--ttl <小时>`、`--timeout <秒>`、`--max-emulators <N>` 并发模拟器上限、`--memory <MB>` 单台 guest RAM(仅 Android)、`--mem-override` 跳过内存闸门、`--no-wake` 不亮屏解锁、`--screen-timeout <分钟>` 真机自动锁屏时长(默认 10,0=不改)、`--keep-awake` 显式临时常亮 |
| `wake` | 把设备重新亮屏解锁(构建/安装后或测试中途熄屏时用) | 不带参数=本会话持有的设备;或 `--key` / `--device` / `--all-mine`;`--screen-timeout <分钟>`;长时间无人值守才传 `--keep-awake` |
| `release` | 释放锁(幂等,恒 exit 0);真机收尾:Home 退出被测 app → 自动锁屏统一设为 1 分钟 → 熄屏落锁。**`--device` 指向没有锁记录的设备时照样收尾**(记进 `tidied`),用来收拾绕过 acquire 或崩在半路留下的孤儿设备 | `--key <device_key>` / `--device <id>` / `--all-mine`、`--no-lock` 不按 Home 也不熄屏(留在当前界面) |
| `status` | 设备 × 锁全景(排查谁占了什么) | `--device <id>` 只看这一台(碰设备前的一秒确认)、`--busy` 只列被别人锁着的 |
| `clean` | 回收陈旧锁 | `--all` 全清(慎用) |

完整参数、JSON schema、exit code 表与锁目录布局见 [references/cli.md](references/cli.md)。

## 典型流程

```bash
SKILL_DIR=<本 skill 根目录>          # 例:~/.claude/skills/test-device-allocator
cd <被测项目根目录>

# 1. 领设备(默认 android,真机最优先;全被占时自动新建模拟器并等它就绪)
#    要测 iOS 传 --platform ios;两端皆可传 --platform any
#    支持鸿蒙的 Flutter 项目(有 ohos/ + OpenHarmony 版 SDK)默认:--platform android,harmony
OUT=$(python3 "$SKILL_DIR/scripts/device_lock.py" acquire --project "$PWD")
DEVICE_ID=$(echo "$OUT"  | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_id"])')
DEVICE_KEY=$(echo "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["device_key"])')

# 2. 显式指定设备构建、安装、运行(全链路都带 -d / -s / -t)
flutter run -d "$DEVICE_ID"                     # 或 flutter_skill launch -d "$DEVICE_ID"
# … flutter_skill inspect / act …,或:
# flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d "$DEVICE_ID"
# Android 原生项目:adb -s "$DEVICE_ID" install app.apk 等
# 鸿蒙:hdc -t "$DEVICE_ID" install entry-default.hap 等

# 3. 真机自动锁屏已被放宽到 10 分钟;构建超长时可在截图/点击前再点亮一次
python3 "$SKILL_DIR/scripts/device_lock.py" wake --key "$DEVICE_KEY"

# 4. 测完立即释放(失败也要释放;没有紧接的下一步就别继续占着设备)
#    真机收尾:Home 退出被测 app → 自动锁屏统一 1 分钟 → 熄屏落锁
python3 "$SKILL_DIR/scripts/device_lock.py" release --key "$DEVICE_KEY"
```

- acquire 失败时 exit code 非 0,stdout JSON 带 `error/message/hint`:`NO_SYSTEM_IMAGE`(4)→ 按 hint 跑 sdkmanager 装镜像后重试;`BUSY`(7)→ 指定的设备被占,去掉 `--device` 让脚本另挑;`MEMORY_PRESSURE`(9)→ 宿主内存不够再开一台模拟器,优先真机/已运行设备或按 hint 释放内存。
- fvm 项目按 flutter-use-fvm 规则把 `flutter` 换成 `fvm flutter`;`device_lock.py` 本身不经 fvm。

## 亮屏解锁与自动锁屏时长(持锁期间放宽,release 收尾归位)

设备熄屏或停在锁屏时,自动化根本点不动:截图全黑、tap 落空、driver 找不到 widget。acquire 拿到设备后会自动做一次**唤醒 → 解锁**,**真机再把自动锁屏时长临时放宽到 10 分钟**——默认 1 分钟的手机在构建、pub get、drive 启动这些没有输入事件的空档里会反复熄屏落锁,每次都要重新唤醒。结果放在返回 JSON 的 `screen` 字段(`state` / `locked` / `actions` / `notes` / `restore`)。

| 平台 | 唤醒 | 解锁 | 放宽自动锁屏(仅真机,默认开) | 显式 `--keep-awake` 才做 |
|---|---|---|---|---|
| Android | `input keyevent KEYCODE_WAKEUP` | `wm dismiss-keyguard` | `settings put system screen_off_timeout 600000` | `svc power stayon true` |
| HarmonyOS | `power-shell wakeup` | 锁屏窗口还在就 `uinput` 上滑(分辨率从 hidumper 读) | `power-shell timeout -o 600000` | 同一旋钮,取 `-o 1800000` |
| iOS 模拟器 | 不需要(不会熄屏,也没锁屏) | — | — | — |
| iOS 真机 | 无法程序控制 | 无法程序解锁 | 不支持 | 不支持;UI 测试前手动解锁 |

**release 收尾(仅真机,依次三步)**:① **按 Home 退出被测 app**(Android `input keyevent KEYCODE_HOME`、鸿蒙 `uinput -K -d 1 -u 1`)——被测 app 常设「保持屏幕常亮」flag,留它在前台,自动锁屏会被一直顶住,哪怕先熄了屏、下次被点亮又常亮到底白白耗电;② 把自动锁屏时长**统一设为 1 分钟**(不回写原值——测试机的省电收尾常态,10 分钟的放宽值绝不留在设备上);③ **熄屏落锁**(Android `input keyevent KEYCODE_SLEEP`,回读仍亮再用 `KEYCODE_POWER` 兜底;鸿蒙 `power-shell suspend`)——`--keep-awake` 设过的常亮也在这一步统一关掉,测完的手机不会一直亮着停在解锁态;个别 ROM 无视电源键注入,此时靠第②步的 1 分钟超时自动熄屏。设备本身把锁屏设成「无」时,只会熄屏、不出现锁屏界面。熄屏后又自己亮起来,多半是 USB 供电抖动触发的插拔唤醒,见 `references/troubleshooting.md`。

- **全程尽力而为**:任何一步失败都只记 stderr 日志,不会让 acquire / release 失败。
- **改过才收尾**:放宽过超时的设备记进锁 meta 的 `screen_restore`(列表,同一 type 只记第一次)。`release` / 陈旧锁回收 / `clean` 走同一套收尾:Android 自动锁屏统一设 1 分钟;鸿蒙用 `power-shell timeout -r` 撤销瞬态覆盖、交还系统设置(它的 OverrideTimeout 是系统托管的,没有可回写的持久时长);`--keep-awake` 设过的 `stay_on_while_plugged_in` **统一写 0**(同样不回写原值:回写会自锁死——设备上一旦残留 `7`,下次 `--keep-awake` 读到的「原值」就是 `7`,收尾又写回去,常亮再也清不掉)。acquire 传过 `--screen-timeout 0` / `--no-wake` 就没有设置收尾债,但 release 默认仍会 Home + 熄屏(`--no-lock` 才跳过)。
- **模拟器不改设置**:模拟器熄屏不影响 adb/hdc 操作,不值得为它留还原债;`release` 也不给它熄屏,留着让下个会话热复用。
- 设了 **PIN / 图案 / 密码**的真机系统不允许程序解锁,`screen.locked` 会是 `true` 并给出提示,此时需要人手解一次。
- 10 分钟仍不够(超长构建)时,完成后、开始 UI 交互前调一次 `wake --key "$DEVICE_KEY"`;交互中的点击会继续刷新系统计时。改时长用 `--screen-timeout <分钟>`,`0` = 完全不碰设备设置。
- 只有长时间无人值守、期间又可能没有输入事件的测试才传 `--keep-awake`(彻底不熄屏,比放宽超时更进一步)。`wake --device` 找不到对应锁时会拒绝 `--keep-awake`,也不会放宽超时——没有 meta 就没人负责还原。
- 完全不想碰屏幕时传 `--no-wake`(连放宽超时一起跳过);`release --no-lock` 则只还原设置、不熄屏。

## 分配策略与锁语义

优先级(tier 间严格有序):**空闲真机** > 已在运行的空闲模拟器 > 启动已停止的 AVD / 模拟器 > 新建(`ai-test-*` 命名;`--platform any` 时先建 iOS 模拟器,更快)。多平台组合(`android,harmony`)时,**tier 优先于平台**——鸿蒙真机(tier1)会排在 Android 已运行模拟器(tier2)前面;同一 tier 内才按 `--platform` 里写的顺序。鸿蒙只有 tier1/tier2(本 skill 不启动、不新建鸿蒙模拟器)。

- **内存闸门(启动模拟器数量随宿主内存自适应)**:后两个 tier(启动已停止 / 新建)执行前做双重检查——并发配额 `clamp((总内存-8GB)/每台开销, 1..4)`(默认每台按 4GB 估算,16GB 机 → 最多 2 台,含 iOS Booted;卡死 offline 的模拟器进程也计入)+ 可用内存下限。可用内存有 **6GB 硬下限:低于 6GB 一律不启动/新建模拟器,第一台也拦**(`MEMORY_PRESSURE`,exit 9);其上再看动态估算(可用 ≥ 每台开销 + 2GB),动态估算在 0 台模拟器运行时只告警不拦截——那一层防的是并发互踩。macOS 可用内存按内核 memorystatus 水位(`sysctl kern.memorystatus_level`,把压缩器与文件缓存的可回收量算在内)估算,vm_stat 口径兜底。不过闸则跳过这两个 tier,真机与已运行模拟器不受影响;全部无路可走时报 `MEMORY_PRESSURE`(exit 9)。`--device` 显式指定时只告警不拦截(含硬下限);幂等重取重启自己已持有的模拟器不拦截;探测失败自动放行。覆盖手段:`--max-emulators <N>` / 环境变量 `AI_DEVICE_MAX_EMULATORS`、`--mem-override` / `AI_DEVICE_MEM_OVERRIDE=1`(整体跳过,含硬下限)。
- **单台内存(`--memory <MB>`,仅 Android)**:传了就走 `emulator -memory`,新建的 AVD 同时写进 `config.ini` 的 `hw.ramSize`(启动已有 AVD 只覆盖本次,不动它的配置)。每台开销随之改为 `guest RAM + 1.5GB`,所以压小内存能换配额:16GB 机上默认 2 台,`--memory 1024` → 3 台。低于 2048MB 会告警(API 31+ 镜像的 lowmemorykiller 可能杀掉被测 app);RAM 与 AVD 配置不一致会作废 quickboot 快照,那次是冷启动。iOS 模拟器不是 VM,simctl 没有等价旋钮,只能靠限台数。
- 上锁 = 原子创建 `~/.ai-device-locks/<key>/`,内含 meta.json(owner_pid、project、时间、TTL)。
- 陈旧回收:owner 进程已死 → 立即可回收;存活但锁龄超 TTL(默认 8h)→ 可回收。每次 acquire 起手会**全局清扫**所有陈旧锁(不限本次要用的设备),死锁不会在注册表里躺尸。长时间压测传大 `--ttl`。
- **release 只还锁,模拟器保持运行**,给下个会话热复用;彻底关机 / 删除 `ai-test-*` 模拟器的手动命令见 [references/troubleshooting.md](references/troubleshooting.md)。

## Patrol 两个特有的注意点

**① 不要再手动 `svc power stayon true`。** Patrol 的 `pump` / `waitUntilVisible` 是帧同步的,
设备熄屏后 Flutter 停止产帧 → 无限等待,所以社区文档普遍教人先开常亮。但 `acquire` 已经做了
唤醒 + 解锁 + 把自动锁屏放宽到 10 分钟,`release` 还会归位;手动 `stayon true` 会把
`stay_on_while_plugged_in` 永久写成 7 且无人还原,正是本文排障表里「测试后手机一直亮屏」那一条。
构建超长导致中途熄屏,用 `wake --key "$DEVICE_KEY"`,不要开常亮。

**② patrol MCP 不认设备锁。** `patrol-run` / `patrol-screenshot` **没有设备参数**,
多台设备连着时:`patrol-run` 取「第一台」——很可能不是你 acquire 到的那台;
`patrol-screenshot` 直接报 `more than one device/emulator` 失败。

所以多设备场景下:

- 跑测试用 CLI 并显式指定:`patrol test -t <file> -d "$DEVICE_ID"`;
- 需要截图用 `adb -s "$DEVICE_ID" exec-out screencap -p > x.png`;
- 只有确认在场设备只有一台(或 `.mcp.json` 的 `PATROL_FLAGS` 里写死了 `-d`)时,
  才用 patrol MCP 的 `patrol-run`。

## 与其他 skill 配合

- **flutter-add-integration-test**:其 Android `flutter drive` 示例不带 `-d`,并发场景必须补上 `-d $DEVICE_ID`。
- **flutter-use-fvm**:flutter / dart 命令按其规则加 `fvm` 前缀。

## 常见坑

| 现象 | 处理 |
|---|---|
| acquire 卡 1-5 分钟 | 正在冷启动模拟器(Android 上限 300s / iOS 180s)。急用可 `--no-create` 或 `--device` 指定现成设备 |
| exit 4 `NO_SYSTEM_IMAGE` | 复制 JSON `hint` 里的 sdkmanager 命令装镜像,再重跑 acquire |
| exit 7 `BUSY` | `--device` 指定的设备被别的会话占用;去掉 `--device` 另挑,或 `status` 看占用者 |
| exit 9 `MEMORY_PRESSURE` | 宿主可用内存低于 6GB 硬下限(第一台也拦),或已有模拟器在跑、内存不够再开一台。优先领真机;或关闭闲置模拟器(`adb -s <id> emu kill`)、退出大进程释放内存后重试;Android 可 `--memory 1024` 压小单台换配额(硬下限不受影响);确认有余量可 `--mem-override` 或调 `--max-emulators` |
| 一整轮跑完 `Total: 0`(不是 `Failed: N`)/ 装包 `ShellCommandUnresponsiveException` / `INSTRUMENTATION_ABORTED` | **真机正在掉线,不是代码问题**。`adb devices` + `adb -s <id> shell echo ok` 一秒钟摘干净;确认后 `release` 再 `acquire` 换一台。acquire 的探测挡得住「不答话」,挡不住「答得上话但装包要几百秒」 |
| 模拟器画面停帧 / adb 挂死 / `Lost connection to device` | 多为宿主内存超卖把 QEMU 拖进 swap(渲染管线冻结)。杀掉对应 qemu 进程冷启动,减少并发模拟器数;内存闸门就是为预防它 |
| adb 里设备 unauthorized / offline | 不参与分配;真机上确认 USB 调试授权弹窗 |
| 截图全黑 / 点击没反应 / driver 找不到 widget | 真机持锁期间自动锁屏已放宽到 10 分钟;更长的构建后跑 `wake --key $DEVICE_KEY` 再点亮;`screen.locked=true` 说明设了 PIN,需人工解一次 |
| 测试后手机一直亮屏 / 不会自动锁屏 | 正常路径下 `release` 会按 Home 退出 app、把自动锁屏设为 1 分钟并熄屏。若会话崩在半路:被测 app 若还在前台,先 `adb -s <id> shell input keyevent KEYCODE_HOME`(app 的常亮 flag 会顶住自动锁屏);`settings get system screen_off_timeout` 查(`600000` 即为遗留的放宽值,改回 `60000`);`stay_on_while_plugged_in=7`(`dumpsys power` 里 `mStayOn=true`)是常亮,插着 USB 就永不熄屏,改回 `0`。下次 acquire 起手的陈旧锁回收也会自动收尾。**已熄屏又反复自己亮起来**是另一回事(供电抖动的插拔唤醒),见 `references/troubleshooting.md` |
| 测试后手机意外熄屏了 / 回到了桌面 | `release` 的正常收尾就是 Home 退出 app → 熄屏落锁;想留在 app 界面继续看就传 `release --no-lock` |
| 鸿蒙设备不参与分配 | 只有 `hdc list targets -v` 里 **Connected** 的目标才算;还要显式 `--platform harmony` 或 `android,harmony`(`any` 不含鸿蒙) |
| exit 6 `ENV_MISSING` 且提到 hdc | 没装 DevEco Studio,或 hdc 不在常见位置:设 `HDC_PATH` 指向 hdc 可执行文件 |
| 忘了 release / 会话崩了 | 下次任意 acquire 起手全局回收死 pid / 超 TTL 的锁;不放心跑 `clean` |
| flutter 挑错设备 | 说明有命令没带 `-d`;全链路显式传 device id |
| Linux 宿主要 iOS | 不支持,`--platform ios` 报 exit 6;`any` 自动只用 Android |

## 相关 skill

- **patrol-setup / patrol-write-test**:Patrol 的真机执行同样从 acquire 开始,见上一节两个注意点。
- flutter-add-integration-test:把验证过的流程沉淀为正式集成测试
- flutter-use-fvm:fvm 项目的命令前缀规则
- deveco-studio-emulator:启动 / 新建 / 管理鸿蒙模拟器(本 skill 只分配已连上的鸿蒙目标,不负责把它跑起来)
