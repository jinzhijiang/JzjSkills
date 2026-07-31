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
| 6 ENV_MISSING | 平台工具链缺失 | 装 Android SDK / Xcode;Linux 宿主不支持 iOS |
| 7 BUSY | `--device` 指定的设备被占 | 去掉 `--device` 另挑;或 `status` 看占用者是谁 |
| 8 INTERNAL | 未预期异常 | 看 stderr 的 traceback 排查 |
| 9 MEMORY_PRESSURE | 内存闸门拦截(配额已满或可用内存不足每台开销 + 2GB;0 台模拟器在跑时不触发,第一台恒放行) | 优先领真机;关闭闲置模拟器(`adb -s <id> emu kill` / `xcrun simctl shutdown <udid>`)后重试;Android 可 `--memory 1024` 压小单台换配额;确认有余量可 `--mem-override` 或调高 `--max-emulators` / `AI_DEVICE_MAX_EMULATORS` |

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
- `--memory` 只在**需要启动**模拟器时才有意义:领到真机、或复用已经跑着的模拟器时无效(跑起来的 VM 改不了 RAM),此时结果 JSON 的 `memory_mb` 为 null。
- `--memory` 只对本工具新建的 AVD 写 `config.ini`;启动用户自己的 AVD(如 Pixel_10)只覆盖本次运行,不改他们的配置。手动持久修改:改 `~/.android/avd/<名>.avd/config.ini` 的 `hw.ramSize`(纯数字按 MB 解释)。
- 改了 RAM 的那次启动一定是冷启动(quickboot 快照要求 RAM 一致),acquire 会慢 1-2 分钟;之后维持同一值就能继续吃快照。
