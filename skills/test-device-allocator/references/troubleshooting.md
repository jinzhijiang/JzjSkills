# 环境准备与故障排查

## Android 环境

- SDK 探测顺序:`ANDROID_HOME` → `ANDROID_SDK_ROOT` → `~/Library/Android/sdk`(macOS)→ `~/Android/Sdk`(Linux)。
- 工具按绝对路径解析,**不要求在 PATH**:adb=`<SDK>/platform-tools/adb`、emulator=`<SDK>/emulator/emulator`、avdmanager/sdkmanager=`<SDK>/cmdline-tools/latest/bin/`。
- 新建 AVD 需已安装 system image(脚本不自动下载)。安装示例(Apple Silicon 用 arm64-v8a,Intel 用 x86_64):

```bash
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" "system-images;android-36;google_apis;arm64-v8a"
yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses
```

- 真机 `unauthorized`:手机上点掉「允许 USB 调试」弹窗;`offline`:重插线或 `adb kill-server && adb start-server`。

## iOS 环境

- 仅 macOS + Xcode;`xcrun simctl list` 能跑即可。
- 没有可用 runtime:Xcode → Settings → Platforms 下载 iOS runtime。
- iOS 真机需 wired/connected 且已配对(`xcrun devicectl list devices` 可见);把 Flutter app 跑上真机还需开发者模式与签名,由被测项目自行保证。

## HarmonyOS 环境

- 需要 `hdc`。探测顺序:`HDC_PATH` → `DEVECO_SDK_HOME` / `HOS_SDK_HOME` / `OHOS_SDK_HOME` → `DEVECO_STUDIO_PATH` → `PATH` → DevEco Studio 常见安装目录 → 独立 SDK / command-line-tools(版本目录取最新)。典型位置:

```bash
# macOS
/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc
# Windows
"{DevEco Studio安装目录}\sdk\default\openharmony\toolchains\hdc.exe"
# 探测不到时手动指定
export HDC_PATH=/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc
```

- 只有 `hdc list targets -v` 里状态含 `Connected` 的目标才参与分配;其余进 `warnings`。真机看不到就检查 USB 调试授权、换线、`hdc kill -r` 重启服务。
- 本 skill **不启动、不新建**鸿蒙模拟器。要用模拟器先用 deveco-studio-emulator 把它跑起来,跑起来后它会以 `127.0.0.1:<port>` 出现在 hdc 目标列表里,再 acquire 就能领到(tier2)。
- 鸿蒙必须显式点名:`--platform harmony` 或 `--platform android,harmony`。`--platform any` **不含**鸿蒙——标准 Flutter SDK 编不出 hap,把鸿蒙设备分给普通项目只会白白浪费一轮。
- 把 Flutter app 跑上鸿蒙设备需要 OpenHarmony 版 Flutter SDK 和项目里的 `ohos/` 模块,由被测项目自行保证;本 skill 只负责把设备分给你。

## 设备熄屏 / 锁屏

**症状**:截图全黑或停在锁屏、`tap` 点了没反应、flutter_driver 找不到 widget、明明 app 起来了却"看不见"。

**处置**:

1. acquire 会做一次唤醒 + 解锁,真机还会把自动锁屏时长放宽到 10 分钟。先看返回 JSON 的 `screen` 字段:`state` 应为 `awake`、`locked` 应为 `false`,真机的 `actions` 里应有 `screen_off_timeout=600000ms`(鸿蒙是 `power-shell timeout -o 600000`)。
2. 构建/安装超过 10 分钟仍会睡过去;开始截图/点击前,以及测试中途又睡过去时,运行 `python3 <skill根>/scripts/device_lock.py wake --key <device_key>` 再点一次,不用重新 acquire。需要更长可 acquire 时传 `--screen-timeout 30`。
3. `screen.locked` 是 `true` → 设备设了 PIN / 图案 / 密码,系统不允许程序解锁,需要人工解一次。
4. `screen.notes` 里有"改不动屏幕超时" → 放宽失败(权限或 ROM 限制),按第 2 条用 `wake` 顶着测,或 `--keep-awake` 撑住整段。
5. `screen.attempted` 是 `false`:`reason` 会说明原因——`disabled_by_--no-wake`(自己关掉的)、`ios_simulator_no_lockscreen`(不需要)、`ios_physical_manual_unlock`(iOS 真机只能在 UI 测试前手动解锁)、`adb_missing` / `hdc_missing`(工具链没找到)。
6. 手动等价命令:

```bash
# Android
adb -s <id> shell input keyevent KEYCODE_WAKEUP
adb -s <id> shell wm dismiss-keyguard
adb -s <id> shell settings get system screen_off_timeout      # 先存原值
adb -s <id> shell settings put system screen_off_timeout 600000
# 只有确实需要无人值守长测试时才使用(必须记住原值并还原)
adb -s <id> shell svc power stayon true

# HarmonyOS
hdc -t <id> shell power-shell wakeup
hdc -t <id> shell uinput -T -m 540 1870 540 580 300    # 上滑解锁,坐标按分辨率折算
hdc -t <id> shell power-shell timeout -o 600000        # 撤销用 timeout -r,别回写读到的 OverrideTimeout
```

7. 改过的设置都记在锁 meta 的 `screen_restore` 里,`release` / 回收陈旧锁 / `clean` 时尽力还原;完全不想动设备就 acquire 传 `--no-wake`,只想跳过放宽超时传 `--screen-timeout 0`。

## 测试后手机一直亮屏 / 不会自动锁屏

正常路径下 `release` 会还原时长并把真机熄屏。会话崩在半路时按下面两项自查:

```bash
adb -s <id> shell settings get system screen_off_timeout        # 600000 = 遗留的放宽值
adb -s <id> shell settings put system screen_off_timeout 60000  # 改回 1 分钟(或用户自己的值)
adb -s <id> shell settings get global stay_on_while_plugged_in  # 7 = --keep-awake 遗留的常亮
adb -s <id> shell settings put global stay_on_while_plugged_in 0
```

`dumpsys power` 里的 `mStayOn=true` 同样指向常亮。鸿蒙查 `hidumper -s PowerManagerService -a -s` 的 `OverrideTimeout`,撤销用 `hdc -t <id> shell power-shell timeout -r`——注意设备进入 SLEEP 后系统自己会挂一个 `OverrideTimeout=10000ms`,那是正常的,不用管。

下次任意 acquire 起手的陈旧锁清扫会自动做这些还原,所以多数情况不需要手动介入;也不要在没有原值或用户确认时对所有设备批量重置。

## 测试后手机意外熄屏 / 锁屏了

`release` 会主动把真机熄屏落锁(Android `KEYCODE_SLEEP`、鸿蒙 `power-shell suspend`),这是有意为之:测完的手机不该一直亮着停在解锁态。要保留亮屏就传 `release --no-lock`。模拟器不受影响(不熄屏、不关机)。

## 手动清理

本 skill 的 release **不关模拟器**(留给下个会话热复用)。需要彻底清理时:

```bash
# 关闭某台 Android 模拟器
adb -s emulator-5554 emu kill

# 查看并删除本 skill 创建的 AVD(名字都是 ai-test-*)
"$ANDROID_HOME/emulator/emulator" -list-avds | grep '^ai-test-'
"$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" delete avd -n ai-test-XXXXXXXX-XXXXXX-XXXX

# 关闭 / 删除 iOS 模拟器(ai-test-* 为本 skill 创建)
xcrun simctl shutdown all
xcrun simctl list devices | grep ai-test-
xcrun simctl delete <udid>

# 清空锁注册表(确认没有会话正在测试时才用)
python3 <skill根>/scripts/device_lock.py clean --all
```

## 常见错误对照

| exit / error | 场景 | 处理 |
|---|---|---|
| 3 NO_DEVICE | 无空闲设备且 `--no-create`;或 `--device` 目标不存在 | 等他人 release / `status` 查占用 / 核对设备 id |
| 4 NO_SYSTEM_IMAGE | 新建 AVD 缺镜像 | 按 JSON `hint` 里的 sdkmanager 命令安装后重试 |
| 5 BOOT_TIMEOUT | 模拟器启动/就绪超时(锁已回滚) | 加大 `--timeout`;查内存/虚拟化;手动启动一次看具体报错 |
| 6 ENV_MISSING | 平台工具链缺失 | 装 Android SDK / Xcode / DevEco Studio(hdc,或设 `HDC_PATH`);Linux 宿主不支持 iOS;组合平台里缺一个只跳过并告警,不报错 |
| 7 BUSY | `--device` 指定的设备被占 | 去掉 `--device` 另挑;或 `status` 看占用者是谁 |
| 8 INTERNAL | 未预期异常 | 看 stderr 的 traceback 排查 |
| 9 MEMORY_PRESSURE | 内存闸门拦截(配额已满、可用内存低于 6GB 硬下限——第一台也拦,或不足每台开销 + 2GB) | 优先领真机;关闭闲置模拟器(`adb -s <id> emu kill` / `xcrun simctl shutdown <udid>`)、退出大进程释放内存后重试;Android 可 `--memory 1024` 压小单台换配额(硬下限不受影响);确认有余量可 `--mem-override` 或调高 `--max-emulators` / `AI_DEVICE_MAX_EMULATORS` |

## 模拟器卡死(内存超卖)

**症状**:模拟器画面停帧(截图内容不再变化)、对它的 `adb shell` 挂起、`flutter run` 报 `Lost connection to device`;卡死前 guest 日志常见大量 `Skipped NN frames`、`Davey! duration=…`、binder 调用超秒、`SurfaceSyncGroup` 超时。

**根因**:宿主并发跑多台模拟器 + 构建(Gradle/Xcode)时内存超卖,macOS/Linux 把 QEMU 的 guest RAM 换页到 swap,vCPU 与图形转发(gfxstream)线程等换入而停摆——进程不死、只冻画面,看起来就是"卡死"。16GB 机器上 2 台模拟器 + 一次冷构建即可触发。

**处置**:
1. 冻住的模拟器救不回来,直接冷关:`adb -s <id> emu kill`;没响应就 `pkill -f qemu-system`(或按 pid 杀)。
2. `adb kill-server && adb start-server` 只能修 adb 连接,救不了 QEMU 本体。
3. 减少并发:内存闸门(见 cli.md)默认就按宿主内存限流;16GB 机器建议同时最多 1-2 台,并发会话优先领真机。
4. 减少单台占用:acquire 传 `--memory 1024`(仅 Android),每台开销从 4.0GB 降到 2.5GB,16GB 机上配额随之从 2 台变 3 台。代价是 guest 内存紧张——低于 2048MB 时 API 31+ 镜像的 lowmemorykiller 可能杀掉被测 app,重 app 别压太狠。
5. `status` 输出里的 `memory` 字段可直接看 `available_gb` / `running_vms` / `can_start_new_vm`,`devices[].ram_mb` 看每台 AVD 配了多少 guest RAM。

## 边界行为速查

- wifi adb(`192.168.x.x:5555`)按真机处理,key 用完整串号。
- 多个项目同一时刻 acquire:`mkdir` 原子性保证同一设备只有一个会话拿到,输家自动换下一台或新建。
- AI 忘记 release:owner 进程退出后,任意会话下次 acquire 时自动回收;或手动 `clean`。
- 长时间压测(> 8h)记得传大 `--ttl`,否则锁可能被判陈旧回收。
- 自定义 `AI_DEVICE_LOCKS_DIR` 时,同机所有会话必须用同一个值,否则互相看不见锁、互斥失效。
- 锁着的模拟器被人手动关掉:锁不会被误回收;持有者下次幂等 acquire 会自动把它重新启动(此重启不过内存闸门——净占用不增)。
- offline / 卡死的模拟器串号计入内存配额(qemu 进程还活着就仍占内存);想释放配额先把它冷关掉。
- 内存探测失败(极少见)时闸门自动放行,不会因此拿不到设备。
- 鸿蒙候选永远不需要启动,**不过内存闸门**;但已在跑的鸿蒙模拟器会计入闸门的运行中模拟器数(它也是 QEMU 虚拟机)。只有 `--platform` 里点了 harmony 时才去查(否则会为纯 Android 的 acquire 平白拉起 hdc 服务);`status` 只要装了 hdc 就会枚举。
- 亮屏解锁、放宽超时、release 的还原与熄屏全程 fail-soft:任何一步失败都只写 stderr,acquire / wake / release 不会因此失败(release 恒 exit 0)。
- 屏幕设置只改真机、只改一次:同一 type 的原值在锁 meta 里只记第一次,重复 acquire / wake 不会把原值污染成我们自己设的值。
- `--memory` 只在**需要启动**模拟器时才有意义:领到真机、或复用已经跑着的模拟器时无效(跑起来的 VM 改不了 RAM),此时结果 JSON 的 `memory_mb` 为 null。
- `--memory` 只对本工具新建的 AVD 写 `config.ini`;启动用户自己的 AVD(如 Pixel_10)只覆盖本次运行,不改他们的配置。手动持久修改:改 `~/.android/avd/<名>.avd/config.ini` 的 `hw.ramSize`(纯数字按 MB 解释)。
- 改了 RAM 的那次启动一定是冷启动(quickboot 快照要求 RAM 一致),acquire 会慢 1-2 分钟;之后维持同一值就能继续吃快照。
