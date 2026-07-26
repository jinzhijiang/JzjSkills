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

## 边界行为速查

- wifi adb(`192.168.x.x:5555`)按真机处理,key 用完整串号。
- 多个项目同一时刻 acquire:`mkdir` 原子性保证同一设备只有一个会话拿到,输家自动换下一台或新建。
- AI 忘记 release:owner 进程退出后,任意会话下次 acquire 时自动回收;或手动 `clean`。
- 长时间压测(> 8h)记得传大 `--ttl`,否则锁可能被判陈旧回收。
- 自定义 `AI_DEVICE_LOCKS_DIR` 时,同机所有会话必须用同一个值,否则互相看不见锁、互斥失效。
- 锁着的模拟器被人手动关掉:锁不会被误回收;持有者下次幂等 acquire 会自动把它重新启动。
