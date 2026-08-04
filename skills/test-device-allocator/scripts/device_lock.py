#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""device_lock.py — 多项目并发 AI 测试的设备分配与互斥锁。

用法:
  python3 device_lock.py acquire [--platform any|android|ios|harmony|逗号组合] [--device <id>] [...]
  python3 device_lock.py release --key <device_key> | --device <id> | --all-mine
  python3 device_lock.py wake [--key <k> | --device <id> | --all-mine]
  python3 device_lock.py status
  python3 device_lock.py clean [--all]

stdout 只输出单行 JSON(机读);人读过程信息全部走 stderr。
锁注册表:~/.ai-device-locks(环境变量 AI_DEVICE_LOCKS_DIR 可覆盖)。
仅用 python3 标准库。完整契约见同 skill 的 references/cli.md。
"""

import argparse
import glob
import json
import os
import platform as platform_mod
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

ALLOCATOR_VERSION = 1
DEFAULT_TTL_HOURS = 8.0
CMD_TIMEOUT = 15               # 单条外部命令默认超时(秒)
AVD_NAME_TIMEOUT = 10
CREATE_AVD_TIMEOUT = 60
CREATE_SIM_TIMEOUT = 30
SERIAL_DISCOVER_TIMEOUT = 60   # 新模拟器串号出现的等待窗
ANDROID_BOOT_TIMEOUT = 300
IOS_BOOT_TIMEOUT = 180
RUNNING_EMU_READY_TIMEOUT = 60  # 已在运行的模拟器的就绪确认
META_GRACE_SECONDS = 60        # meta.json 缺失/损坏时的并发写宽限
TOMB_MAX_AGE = 600             # .reclaim-* 墓碑残骸清理阈(秒)
HDC_TIMEOUT = 20               # hdc list targets 等外部命令超时

# 亮屏解锁:设备熄屏/锁屏时自动化点不动屏幕,acquire 完成后统一做一次(--no-wake 关闭)。
# 每一步都是尽力而为——失败只记日志,绝不让 acquire 失败。
WAKE_CMD_TIMEOUT = 15
RESTORE_TIMEOUT = 8            # release 时还原屏幕设置的短超时(设备可能已拔线)
KEEP_AWAKE_MS = 1800000        # HarmonyOS 屏幕超时覆盖值(30 分钟)
HARMONY_LOCK_WINDOW = "SCBScreenLock"   # hidumper WMS 里的锁屏窗口名前缀
HARMONY_DEFAULT_SCREEN = (1080, 2340)   # 读不到分辨率时的上滑兜底坐标基准

EXIT_OK, EXIT_ARGS, EXIT_NO_DEVICE, EXIT_NO_SYSTEM_IMAGE = 0, 2, 3, 4
EXIT_BOOT_TIMEOUT, EXIT_ENV_MISSING, EXIT_BUSY, EXIT_INTERNAL = 5, 6, 7, 8
EXIT_MEMORY = 9

# 内存闸门:启动/新建模拟器前按宿主内存核算,避免超卖把整机拖进 swap(模拟器整体
# 冻结的常见根因)。真机与已在运行的模拟器不受影响;探测失败自动放行(fail-open)。
MEM_RESERVE_GB = 8.0    # 预留给 OS / IDE / 构建进程的基线内存
MEM_PER_VM_GB = 4.0     # 未指定 --memory 时每台的估算宿主开销(≈2GB guest RAM + 转发)
MEM_VM_OVERHEAD_GB = 1.5  # 指定 --memory 时,guest RAM 之外的宿主开销(QEMU + 图形转发)
MEM_MIN_FREE_GB = 2.0   # 启动新 VM 时,估算开销之外还需的安全垫
MEM_MAX_VMS_CAP = 4     # 自动配额上限(--max-emulators / AI_DEVICE_MAX_EMULATORS 可突破)

# --memory:Android 模拟器 guest RAM(emulator -memory / config.ini hw.ramSize)。
# iOS 模拟器不是 VM,simctl 没有等价旋钮,只能靠限制台数。
EMU_MEM_MIN_MB = 512     # emulator 本身允许到 128,但低于此系统起不来
EMU_MEM_MAX_MB = 8192    # emulator -memory 上限
EMU_MEM_WARN_MB = 2048   # 低于此,API 31+ 镜像的 lowmemorykiller 容易杀掉被测 app

_ACTION = "device_lock"


class BootFailure(Exception):
    pass


# ---------- 通用工具 ----------

def log(msg):
    print(f"[device_lock] {msg}", file=sys.stderr, flush=True)


def emit(obj):
    obj.setdefault("ok", True)
    obj.setdefault("action", _ACTION)
    print(json.dumps(obj, ensure_ascii=False), flush=True)
    sys.exit(EXIT_OK)


def fail(code, error, message, hint=None):
    obj = {"ok": False, "action": _ACTION, "error": error, "message": message}
    if hint:
        obj["hint"] = hint
    log(message + (f"(hint: {hint})" if hint else ""))
    print(json.dumps(obj, ensure_ascii=False), flush=True)
    sys.exit(code)


def run(cmd, timeout=CMD_TIMEOUT, input_text=None):
    """subprocess 包装:不抛异常,返回 (rc, stdout, stderr)。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, input=input_text)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(map(str, cmd))}"
    except Exception as e:  # noqa: BLE001
        return 125, "", str(e)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def default_owner_pid():
    """默认锁持有者:脚本祖父进程(python → shell → AI 会话进程)。"""
    ppid = os.getppid()
    rc, out, _ = run(["ps", "-o", "ppid=", "-p", str(ppid)], timeout=5)
    gp = out.strip()
    if rc == 0 and gp.isdigit() and int(gp) > 1:
        return int(gp)
    return ppid if ppid > 1 else os.getpid()


def sdk_root():
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            return v
    for cand in (os.path.expanduser("~/Library/Android/sdk"),
                 os.path.expanduser("~/Android/Sdk")):
        if os.path.isdir(cand):
            return cand
    return None


def tool(name):
    """解析 Android 工具的绝对路径(emulator/avdmanager 通常不在 PATH)。"""
    sdk = sdk_root()
    cands = []
    if sdk:
        if name == "adb":
            cands.append(os.path.join(sdk, "platform-tools", "adb"))
        elif name == "emulator":
            cands.append(os.path.join(sdk, "emulator", "emulator"))
        elif name in ("avdmanager", "sdkmanager"):
            ct = os.path.join(sdk, "cmdline-tools")
            cands.append(os.path.join(ct, "latest", "bin", name))
            if os.path.isdir(ct):
                for d in sorted(os.listdir(ct), reverse=True):
                    cands.append(os.path.join(ct, d, "bin", name))
            cands.append(os.path.join(sdk, "tools", "bin", name))
    w = shutil.which(name)
    if w:
        cands.append(w)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def host_abi():
    m = platform_mod.machine().lower()
    return "arm64-v8a" if m in ("arm64", "aarch64") else "x86_64"


def have_simctl():
    return sys.platform == "darwin" and shutil.which("xcrun") is not None


# ---------- HarmonyOS(hdc)----------

_HDC_CACHE = []  # [路径 or None];glob 探测有成本,进程内只做一次


def _hdc_candidates():
    exe = "hdc.exe" if sys.platform == "win32" else "hdc"
    rel = os.path.join("openharmony", "toolchains", exe)
    out = []
    p = os.environ.get("HDC_PATH")
    if p:
        out.append(p)
    for var in ("DEVECO_SDK_HOME", "HOS_SDK_HOME", "OHOS_SDK_HOME"):
        v = os.environ.get(var)
        if v:
            out += [os.path.join(v, "default", rel), os.path.join(v, rel),
                    os.path.join(v, "toolchains", exe)]
    studio = os.environ.get("DEVECO_STUDIO_PATH")
    if studio:
        out.append(os.path.join(studio, "sdk", "default", rel))
    w = shutil.which("hdc")
    if w:
        out.append(w)
    home = os.path.expanduser("~")
    studios = ["/Applications/DevEco-Studio.app/Contents",
               os.path.join(home, "Applications", "DevEco-Studio.app", "Contents"),
               "/opt/Huawei/DevEco Studio", os.path.join(home, "Huawei", "DevEco Studio"),
               r"C:\Program Files\Huawei\DevEco Studio",
               os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Huawei",
                            "DevEco Studio")]
    for s in studios:
        if s:
            out.append(os.path.join(s, "sdk", "default", rel))
    # 独立 SDK / command-line-tools:版本目录用 glob 展开(取最新)
    for pat in (os.path.join(home, "Library", "Huawei", "Sdk", "*", "toolchains", exe),
                os.path.join(home, "Library", "OpenHarmony", "Sdk", "*", "toolchains", exe),
                os.path.join(home, "OpenHarmony", "Sdk", "*", "toolchains", exe),
                os.path.join(home, "command-line-tools", "sdk", "default", rel)):
        out += sorted(glob.glob(pat), reverse=True)
    return out


def hdc_tool():
    """解析 hdc 绝对路径(HarmonyOS 设备连接器);找不到返回 None。"""
    if _HDC_CACHE:
        return _HDC_CACHE[0]
    found = None
    for c in _hdc_candidates():
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            found = c
            break
    _HDC_CACHE.append(found)
    return found


def hdc_devices(warnings):
    """健康的鸿蒙目标 [{serial, is_emulator}];非 Connected 的只进 warnings。

    `hdc list targets -v` 每行形如 `<connectkey>\t\tUSB\tConnected\tlocalhost`;
    无设备时输出 `[Empty]`。回环地址的目标(127.0.0.1:5555)是 DevEco 模拟器。
    """
    hdc = hdc_tool()
    if not hdc:
        return [], None
    rc, out, err = run([hdc, "list", "targets", "-v"], timeout=HDC_TIMEOUT)
    if rc != 0:
        warnings.append(f"hdc list targets 失败: {(err or out or '').strip()[:120] or rc}")
        return [], hdc
    devs = []
    for line in out.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("[Empty]"):
            continue
        serial = parts[0]
        if "Connected" not in parts[1:]:
            warnings.append(f"跳过鸿蒙目标 {serial}(状态 {' '.join(parts[1:]) or '未知'},"
                            f"未连接不参与分配)")
            continue
        devs.append({"serial": serial,
                     "is_emulator": serial.startswith(("127.0.0.1:", "localhost:"))})
    return devs, hdc


# ---------- 内存感知 ----------

def _win_memory_status():
    """Windows: (total_bytes, avail_bytes);失败返回 None。"""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_uint32),
                        ("dwMemoryLoad", ctypes.c_uint32),
                        ("ullTotalPhys", ctypes.c_uint64),
                        ("ullAvailPhys", ctypes.c_uint64),
                        ("ullTotalPageFile", ctypes.c_uint64),
                        ("ullAvailPageFile", ctypes.c_uint64),
                        ("ullTotalVirtual", ctypes.c_uint64),
                        ("ullAvailVirtual", ctypes.c_uint64),
                        ("ullAvailExtendedVirtual", ctypes.c_uint64)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return st.ullTotalPhys, st.ullAvailPhys
    except Exception:  # noqa: BLE001
        pass
    return None


def mem_total_gb():
    """宿主物理内存(GB);探测失败返回 None(闸门 fail-open)。"""
    try:
        if sys.platform == "darwin":
            rc, out, _ = run(["sysctl", "-n", "hw.memsize"], timeout=5)
            if rc == 0 and out.strip().isdigit():
                return int(out.strip()) / 1024 ** 3
        elif sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 1024 ** 2
        elif sys.platform == "win32":
            st = _win_memory_status()
            if st:
                return st[0] / 1024 ** 3
    except Exception:  # noqa: BLE001
        pass
    return None


def mem_available_gb():
    """当前可用内存(GB),口径尽量贴近 Linux MemAvailable;失败返回 None。

    macOS 首选内核 memorystatus 水位(`sysctl kern.memorystatus_level`,即
    memory_pressure 报告的 free percentage):压缩器与文件缓存的可回收量都在
    口径内。vm_stat 的 free+inactive+purgeable+speculative 显著低估——机器
    正常干活时它常年只剩 1-3GB,曾把 16GB 宿主上「0 台模拟器在跑」的首台
    申请都判成 MEMORY_PRESSURE——降为兜底。
    """
    try:
        if sys.platform == "darwin":
            total = mem_total_gb()
            rc, out, _ = run(["sysctl", "-n", "kern.memorystatus_level"],
                             timeout=5)
            if rc == 0 and total:
                level = out.strip()
                if level.isdigit() and 0 < int(level) <= 100:
                    return total * int(level) / 100.0
            rc, out, _ = run(["vm_stat"], timeout=5)
            if rc != 0:
                return None
            m = re.search(r"page size of (\d+) bytes", out)
            page_size = int(m.group(1)) if m else 16384
            pages = {}
            for line in out.splitlines():
                mm = re.match(r"^(Pages [a-z ]+?)\s*:\s+(\d+)\.", line.strip())
                if mm:
                    pages[mm.group(1)] = int(mm.group(2))
            wanted = ("Pages free", "Pages inactive", "Pages purgeable",
                      "Pages speculative")
            if not any(k in pages for k in wanted):
                return None
            return sum(pages.get(k, 0) for k in wanted) * page_size / 1024 ** 3
        elif sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / 1024 ** 2
        elif sys.platform == "win32":
            st = _win_memory_status()
            if st:
                return st[1] / 1024 ** 3
    except Exception:  # noqa: BLE001
        pass
    return None


def per_vm_gb(memory_mb=None):
    """每台模拟器的估算宿主开销:显式 --memory 时按 guest RAM + 固定开销推导。"""
    if not memory_mb:
        return MEM_PER_VM_GB
    return round(memory_mb / 1024.0 + MEM_VM_OVERHEAD_GB, 1)


def auto_max_vms(total_gb, memory_mb=None):
    """按总内存推导并发模拟器上限:(总量-预留)/每台开销,夹在 [1, CAP]。"""
    if total_gb is None:
        return None
    return max(1, min(MEM_MAX_VMS_CAP,
                      int((total_gb - MEM_RESERVE_GB) // per_vm_gb(memory_mb))))


def env_max_vms():
    v = os.environ.get("AI_DEVICE_MAX_EMULATORS", "").strip()
    try:
        return int(v) if v else None
    except ValueError:
        return None


def running_vm_count(include_harmony=False):
    """当前在跑的模拟器总数(Android emulator 串号 + iOS Booted [+ 鸿蒙模拟器])。

    offline/卡死的 emulator 串号也计入——进程还活着就仍占着内存。鸿蒙模拟器同样是
    QEMU 虚拟机、同样抢宿主内存,但只在本次确实要分配鸿蒙设备时才查(否则会为纯
    Android 的 acquire 平白拉起 hdc 服务)。
    """
    n = 0
    adb = tool("adb")
    if adb:
        n += len(all_emulator_serials(adb))
    if have_simctl():
        booted, _ = ios_sims()
        n += len(booted)
    if include_harmony and hdc_tool():
        n += sum(1 for d in hdc_devices([])[0] if d["is_emulator"])
    return n


def mem_policy(max_override=None, ignore=False, memory_mb=None, include_harmony=False):
    """评估内存闸门,返回 dict。enabled=False 表示不拦截(显式覆盖或探测失败)。

    memory_mb 为本次将施加的 guest RAM(仅 --platform android 传入):每台开销按它
    推导,压小内存就能多跑一台。
    """
    vm_gb = per_vm_gb(memory_mb)
    info = {"enabled": True, "blocked": False, "reason": None,
            "total_gb": None, "available_gb": None,
            "running_vms": None, "max_vms": None,
            "per_vm_gb": vm_gb, "memory_mb": memory_mb,
            "need_gb": round(vm_gb + MEM_MIN_FREE_GB, 1)}
    if ignore or os.environ.get("AI_DEVICE_MEM_OVERRIDE", "").lower() in ("1", "true", "yes"):
        info["enabled"] = False
        return info
    total, avail = mem_total_gb(), mem_available_gb()
    info["total_gb"] = None if total is None else round(total, 1)
    info["available_gb"] = None if avail is None else round(avail, 1)
    max_vms = max_override if max_override is not None else env_max_vms()
    if max_vms is None:
        max_vms = auto_max_vms(total, memory_mb)
    info["max_vms"] = max_vms
    if max_vms is None and avail is None:
        info["enabled"] = False  # 全部探测失败,放行
        return info
    running = running_vm_count(include_harmony)
    info["running_vms"] = running
    sized = f"(按每台 {vm_gb}GB" + (f" / guest RAM {memory_mb}MB)" if memory_mb else ")")
    if max_vms is not None and running >= max_vms:
        info["blocked"] = True
        info["reason"] = (f"并发配额已满:宿主内存 {info['total_gb']}GB 对应上限 "
                          f"{max_vms} 台模拟器{sized},当前已有 {running} 台在运行")
    elif avail is not None and avail < vm_gb + MEM_MIN_FREE_GB:
        if running == 0:
            # 闸门的使命是防「并发」模拟器互相拖垮;一台都没跑时不拦第一台,
            # 只告警。操作系统吃满内存是常态(缓存/压缩器),静态阈值在
            # running=0 时必然误杀,而配额下限本就是 1。
            info["warning"] = (f"可用内存偏紧:约 {info['available_gb']}GB,"
                               f"估算需 {info['need_gb']}GB{sized};当前 0 台"
                               f"模拟器在运行,放行第一台")
        else:
            info["blocked"] = True
            info["reason"] = (f"可用内存不足:当前约 {info['available_gb']}GB,"
                              f"再启动一台估算需 {info['need_gb']}GB{sized}")
    return info


MEM_HINT = ("优先领真机或复用已在运行的空闲模拟器;关闭闲置模拟器释放内存"
            "(adb -s <id> emu kill / xcrun simctl shutdown <udid>)后重试;"
            "Android 可用 --memory <MB> 压低单台 guest RAM 换取配额(如 1024);"
            "确认内存有余量时可 --mem-override 跳过,或用 --max-emulators / "
            "环境变量 AI_DEVICE_MAX_EMULATORS 调整上限")


# ---------- 锁层 ----------

def lock_root():
    root = os.environ.get("AI_DEVICE_LOCKS_DIR") or os.path.expanduser("~/.ai-device-locks")
    os.makedirs(root, exist_ok=True)
    return root


def sanitize(key):
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def lock_dir(key):
    return os.path.join(lock_root(), sanitize(key))


def write_meta(dirpath, meta):
    tmp = os.path.join(dirpath, "meta.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(dirpath, "meta.json"))


def try_lock(key, meta):
    d = lock_dir(key)
    try:
        os.mkdir(d)
    except FileExistsError:
        return False
    except OSError as e:
        log(f"无法创建锁目录 {d}: {e}")
        return False
    write_meta(d, meta)
    return True


def read_meta(path):
    try:
        with open(os.path.join(path, "meta.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_lock(key):
    return read_meta(lock_dir(key))


def update_lock(key, **updates):
    d = lock_dir(key)
    meta = read_meta(d)
    if meta is None:
        return None
    meta.update(updates)
    write_meta(d, meta)
    return meta


def lock_age_hours(meta, path):
    ts = (meta or {}).get("acquired_at")
    if ts:
        try:
            then = datetime.fromisoformat(ts)
            return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0
        except (ValueError, TypeError):
            pass
    try:
        return (time.time() - os.stat(path).st_mtime) / 3600.0
    except OSError:
        return None


def eval_lock(path, meta, ttl_override=None):
    """返回 (state, reason):FREE / HELD / STALE。"""
    if not os.path.isdir(path):
        return "FREE", None
    if meta is None:
        try:
            age = time.time() - os.stat(path).st_mtime
        except OSError:
            return "FREE", None
        return ("HELD", "meta_pending") if age < META_GRACE_SECONDS else ("STALE", "corrupt_meta")
    if not pid_alive(meta.get("owner_pid")):
        return "STALE", "dead_pid"
    ttl = ttl_override if ttl_override is not None else meta.get("ttl_hours", DEFAULT_TTL_HOURS)
    age_h = lock_age_hours(meta, path)
    if age_h is not None and age_h > ttl:
        return "STALE", "ttl_expired"
    return "HELD", None


def reclaim_path(path):
    """rename-then-delete:多进程同时回收时只有 rename 赢家真正删除。"""
    tomb = f"{path}.reclaim-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        os.rename(path, tomb)
    except OSError:
        return False
    shutil.rmtree(tomb, ignore_errors=True)
    return True


def release_lock(key):
    """还锁,并把 acquire 为「防熄屏」改过的设备设置还原回去(尽力而为)。"""
    d = lock_dir(key)
    if not os.path.isdir(d):
        return False
    meta = read_meta(d)
    if not reclaim_path(d):
        return False
    if restore_screen(meta):
        log(f"{key}: 已还原屏幕超时设置")
    return True


def list_locks():
    """[(dir_name, meta_or_None, abs_path)];顺手清理过期 .reclaim-* 墓碑。"""
    root = lock_root()
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        if ".reclaim-" in name:
            try:
                if time.time() - os.stat(p).st_mtime > TOMB_MAX_AGE:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
            continue
        out.append((name, read_meta(p), p))
    return out


def find_my_lock(owner, project):
    for _, meta, path in list_locks():
        if not meta:
            continue
        if meta.get("owner_pid") == owner and meta.get("project") == project:
            state, _ = eval_lock(path, meta)
            if state == "HELD":
                return meta
    return None


def acquire_lock_with_reclaim(key, meta):
    if try_lock(key, meta):
        return True
    d = lock_dir(key)
    state, reason = eval_lock(d, read_meta(d))
    if state == "STALE":
        log(f"回收陈旧锁 {key}({reason})")
        if reclaim_path(d) and try_lock(key, meta):
            return True
    elif state == "FREE":
        return try_lock(key, meta)
    return False


def sweep_stale_locks():
    """acquire 起手的全局陈旧锁回收:owner 已死 / 超 TTL 的锁就地清掉。

    [acquire_lock_with_reclaim] 只在轮到那台设备时才回收它的锁;真机永远
    排第一,挂在停止态模拟器上的死锁曾因此躺过 48 小时——status 一直显示
    「被占用」,与事实相悖。并发安全:reclaim_path 先原子 rename 再删,
    两个会话同时清扫只有一个赢家,输家静默跳过。
    """
    removed = []
    for dirname, meta, path in list_locks():
        state, reason = eval_lock(path, meta)
        if state == "STALE" and reclaim_path(path):
            removed.append(f"{(meta or {}).get('device_key', dirname)}({reason})")
            restore_screen(meta)   # 会话崩了也别把人家手机永久设成常亮
    if removed:
        log(f"回收陈旧锁: {', '.join(removed)}")


# ---------- 枚举层 ----------

def adb_devices(warnings):
    """健康设备 [{serial, is_emulator}];unauthorized/offline 只进 warnings。"""
    adb = tool("adb")
    if not adb:
        return [], None
    rc, out, err = run([adb, "devices"], timeout=CMD_TIMEOUT)
    if rc != 0:
        warnings.append(f"adb devices 失败: {(err or '').strip() or rc}")
        return [], adb
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("*"):
            continue
        serial, state = parts[0], parts[1]
        if state != "device":
            warnings.append(f"跳过 {serial}(state={state},未授权或离线不参与分配)")
            continue
        devs.append({"serial": serial, "is_emulator": serial.startswith("emulator-")})
    return devs, adb


def all_emulator_serials(adb):
    rc, out, _ = run([adb, "devices"], timeout=CMD_TIMEOUT)
    if rc != 0:
        return set()
    out_set = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if parts and parts[0].startswith("emulator-"):
            out_set.add(parts[0])
    return out_set


def avd_for_serial(adb, serial):
    rc, out, _ = run([adb, "-s", serial, "emu", "avd", "name"], timeout=AVD_NAME_TIMEOUT)
    if rc != 0:
        return None
    for line in out.splitlines():
        s = line.strip()
        if s and s != "OK":
            return s
    return None


AVD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def list_avds():
    emu = tool("emulator")
    if not emu:
        return []
    rc, out, _ = run([emu, "-list-avds"], timeout=CMD_TIMEOUT)
    if rc != 0:
        return []
    return [s for s in (line.strip() for line in out.splitlines())
            if s and AVD_NAME_RE.match(s)]


def avd_home():
    """AVD 存放目录:ANDROID_AVD_HOME → <ANDROID_SDK_HOME|ANDROID_USER_HOME|~>/.android/avd。"""
    v = os.environ.get("ANDROID_AVD_HOME")
    if v and os.path.isdir(v):
        return v
    for base in (os.environ.get("ANDROID_SDK_HOME"), os.environ.get("ANDROID_USER_HOME"),
                 os.path.expanduser("~")):
        if not base:
            continue
        d = (base if os.path.basename(base) == ".android"
             else os.path.join(base, ".android"))
        d = os.path.join(d, "avd")
        if os.path.isdir(d):
            return d
    return None


def avd_config_path(name):
    home = avd_home()
    if not home or not AVD_NAME_RE.match(name or ""):
        return None
    p = os.path.join(home, f"{name}.avd", "config.ini")
    return p if os.path.isfile(p) else None


def parse_ram_mb(value):
    """config.ini 的 hw.ramSize 可写成 2048 / 2048M / 2G,统一归一到 MB。"""
    m = re.match(r"^\s*(\d+)\s*([MmGg]?)", value or "")
    if not m:
        return None
    n = int(m.group(1))
    return n * 1024 if m.group(2).lower() == "g" else n


def avd_ram_mb(name):
    """AVD 配置里的 guest RAM(MB);读不到返回 None。"""
    path = avd_config_path(name)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().startswith("hw.ramSize"):
                    return parse_ram_mb(line.split("=", 1)[-1])
    except OSError:
        return None
    return None


def set_avd_ram_mb(name, mb):
    """把 hw.ramSize 写进 config.ini(只对本工具新建的 AVD 用,别改用户的)。"""
    path = avd_config_path(name)
    if not path:
        return False, "找不到 config.ini"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        out, done = [], False
        for line in lines:
            if line.strip().startswith("hw.ramSize"):
                if done:
                    continue
                out.append(f"hw.ramSize={mb}")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(f"hw.ramSize={mb}")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.replace(tmp, path)
        return True, None
    except OSError as e:
        return False, str(e)


def simctl_json(*args):
    """CoreSimulator 服务繁忙时(如模拟器刚启动)会瞬时失败,重试一次。"""
    if not have_simctl():
        return None
    for attempt in range(2):
        rc, out, _ = run(["xcrun", "simctl", "list", "-j", *args], timeout=30)
        if rc == 0:
            try:
                return json.loads(out)
            except ValueError:
                pass
        if attempt == 0:
            time.sleep(2)
    return None


IOS_RUNTIME_RE = re.compile(r"SimRuntime\.iOS-(\d+)-(\d+)")


def runtime_version(identifier):
    m = IOS_RUNTIME_RE.search(identifier or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def ios_sims():
    """(booted, shutdown);组内排序:ai-test-* 优先 → runtime 新 → iPhone 优先。"""
    data = simctl_json("devices")
    if not data:
        return [], []
    booted, shutdown = [], []
    for runtime_key, devices in (data.get("devices") or {}).items():
        if "SimRuntime.iOS" not in runtime_key:
            continue
        for d in devices:
            if not d.get("isAvailable") or not d.get("udid"):
                continue
            item = {"udid": d["udid"], "name": d.get("name", ""),
                    "rv": runtime_version(runtime_key)}
            (booted if d.get("state") == "Booted" else shutdown).append(item)

    def order(it):
        return (0 if it["name"].startswith("ai-test-") else 1,
                -it["rv"][0], -it["rv"][1],
                0 if "iPhone" in it["name"] else 1, it["name"])

    booted.sort(key=order)
    shutdown.sort(key=order)
    return booted, shutdown


def ios_physicals(warnings):
    if not have_simctl():
        return []
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        rc, _, err = run(["xcrun", "devicectl", "list", "devices",
                          "--json-output", tmp], timeout=30)
        if rc != 0:
            warnings.append(f"devicectl 枚举 iOS 真机失败(忽略): {(err or '').strip()[:120]}")
            return []
        with open(tmp, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        warnings.append(f"devicectl 输出解析失败(忽略): {e}")
        return []
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    out = []
    for d in (data.get("result") or {}).get("devices") or []:
        conn = d.get("connectionProperties") or {}
        tunnel = (conn.get("tunnelState") or "").lower()
        transport = (conn.get("transportType") or "").lower()
        hw = d.get("hardwareProperties") or {}
        udid = hw.get("udid") or d.get("identifier")
        name = (d.get("deviceProperties") or {}).get("name") \
            or hw.get("marketingName") or "iOS Device"
        if not udid:
            continue
        if tunnel == "connected" or (transport == "wired" and tunnel != "unavailable"):
            out.append({"udid": udid, "name": name})
    return out


# ---------- 亮屏解锁 ----------
#
# 设备熄屏 / 停在锁屏时,自动化测试点不动屏幕(截图全黑、tap 落空、flutter_driver
# 找不到 widget)。acquire 拿到设备后统一走一次:唤醒 → 解锁 → 顺手把屏幕超时拉长,
# 免得测到一半又睡过去;拉长的设置记进锁的 meta,release 时还原回去。
# 设了 PIN / 图案 / 密码的真机无法程序解锁(系统限制),此时只提示、不报错。


def _android_dump(adb, serial, service, pattern):
    """在设备侧 grep,避免把整份 dumpsys 拉回宿主。"""
    rc, out, _ = run([adb, "-s", serial, "shell",
                      f"dumpsys {service} | grep -E '{pattern}'"], timeout=WAKE_CMD_TIMEOUT)
    return out if rc == 0 else ""


def android_power_state(adb, serial):
    """awake / asleep / dozing …;读不到返回 None。"""
    m = re.search(r"mWakefulness=(\w+)", _android_dump(adb, serial, "power", "mWakefulness"))
    return m.group(1).lower() if m else None


def android_locked(adb, serial):
    """True=锁屏中,False=已解锁,None=判不出。"""
    out = _android_dump(adb, serial, "window",
                        "isKeyguardShowing|mDreamingLockscreen|mShowingLockscreen")
    for pat in ("isKeyguardShowing", "mDreamingLockscreen", "mShowingLockscreen"):
        m = re.search(pat + r"=(true|false)", out)
        if m:
            return m.group(1) == "true"
    return None


def android_setting(adb, serial, ns, key):
    rc, out, _ = run([adb, "-s", serial, "shell", "settings", "get", ns, key],
                     timeout=WAKE_CMD_TIMEOUT)
    v = (out or "").strip()
    return v if rc == 0 and v.isdigit() else None


def wake_android(adb, serial, keep_awake):
    info = {"platform": "android", "attempted": True, "actions": [], "notes": []}
    state = android_power_state(adb, serial)
    info["state_before"] = state
    if state != "awake":
        # KEYCODE_WAKEUP 只唤醒,不像 KEYCODE_POWER 那样会把亮着的屏幕按灭
        run([adb, "-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            timeout=WAKE_CMD_TIMEOUT)
        info["actions"].append("input keyevent KEYCODE_WAKEUP")
        time.sleep(1)
    locked = android_locked(adb, serial)
    if locked is not False:
        run([adb, "-s", serial, "shell", "wm", "dismiss-keyguard"], timeout=WAKE_CMD_TIMEOUT)
        info["actions"].append("wm dismiss-keyguard")
        time.sleep(1)
        locked = android_locked(adb, serial)
        if locked:
            info["notes"].append("keyguard 仍在(多半设了 PIN/图案/密码,系统不允许程序解锁),"
                                 "请手动解锁后重试")
    info["locked"] = locked
    if keep_awake:
        prev = android_setting(adb, serial, "global", "stay_on_while_plugged_in")
        rc, _, _ = run([adb, "-s", serial, "shell", "svc", "power", "stayon", "true"],
                       timeout=WAKE_CMD_TIMEOUT)
        if rc == 0:
            info["actions"].append("svc power stayon true")
            if prev is not None:
                info["restore"] = {"type": "android_stayon", "prev": prev}
    info["state"] = android_power_state(adb, serial)
    return info


def harmony_power(hdc, serial):
    """(电源状态, 当前 OverrideTimeout 毫秒);读不到的项为 None。"""
    rc, out, _ = run([hdc, "-t", serial, "shell", "hidumper", "-s",
                      "PowerManagerService", "-a", "-s"], timeout=WAKE_CMD_TIMEOUT)
    if rc != 0:
        return None, None
    m = re.search(r"Current State:\s*(\w+)", out or "")
    o = re.search(r"OverrideTimeout=(\d+)ms", out or "")
    return (m.group(1).lower() if m else None), (int(o.group(1)) if o else None)


def harmony_windows(hdc, serial):
    """(可见窗口名列表, (宽,高));读不到返回 (None, None)。

    hidumper WMS 的 -a 输出中,表头之后到第一条纯虚线之间是按 ZOrder 排的可见窗口,
    虚线之后(ZOrd=-1)是不可见窗口。锁屏窗口 SCBScreenLock* 出现在可见段 = 正锁着。
    """
    rc, out, _ = run([hdc, "-t", serial, "shell", "hidumper", "-s",
                      "WindowManagerService", "-a", "-a"], timeout=WAKE_CMD_TIMEOUT)
    if rc != 0 or "WindowName" not in (out or ""):
        return None, None
    visible, size, started = [], None, False
    for line in out.splitlines():
        if not started:
            started = "WindowName" in line and "ZOrd" in line
            continue
        if line.strip() and set(line.strip()) == {"-"}:
            break                                   # 可见段到此为止
        m = re.match(r"^(\S+)\s", line)
        if m:
            visible.append(m.group(1))
        r = re.search(r"\[\s*\d+\s+\d+\s+(\d+)\s+(\d+)\s*\]", line)
        if r:
            wh = (int(r.group(1)), int(r.group(2)))
            if size is None or wh[0] * wh[1] > size[0] * size[1]:
                size = wh                           # 全屏窗口的尺寸即屏幕分辨率
    return visible, size


def harmony_locked(windows):
    if windows is None:
        return None
    return any(w.startswith(HARMONY_LOCK_WINDOW) for w in windows)


def wake_harmony(hdc, serial, keep_awake):
    info = {"platform": "harmony", "attempted": True, "actions": [], "notes": []}
    state, override_prev = harmony_power(hdc, serial)
    info["state_before"] = state
    if state is None:
        info["notes"].append("读不到电源状态(hidumper PowerManagerService),仍尝试唤醒")
    if state != "awake":
        run([hdc, "-t", serial, "shell", "power-shell", "wakeup"], timeout=WAKE_CMD_TIMEOUT)
        info["actions"].append("power-shell wakeup")
        time.sleep(1)
    windows, size = harmony_windows(hdc, serial)
    locked = harmony_locked(windows)
    if locked:
        w, h = size or HARMONY_DEFAULT_SCREEN
        x, y1, y2 = w // 2, int(h * 0.8), int(h * 0.25)
        run([hdc, "-t", serial, "shell", "uinput", "-T", "-m",
             str(x), str(y1), str(x), str(y2), "300"], timeout=WAKE_CMD_TIMEOUT)
        info["actions"].append(f"uinput 上滑解锁 ({x},{y1})→({x},{y2})")
        time.sleep(1.5)
        locked = harmony_locked(harmony_windows(hdc, serial)[0])
        if locked:
            info["notes"].append("上滑后仍在锁屏(多半设了 PIN/密码),请手动解锁后重试")
    info["locked"] = locked
    if keep_awake:
        rc, out, _ = run([hdc, "-t", serial, "shell", "power-shell", "timeout",
                          "-o", str(KEEP_AWAKE_MS)], timeout=WAKE_CMD_TIMEOUT)
        if rc == 0 and "Override" in (out or ""):
            info["actions"].append(f"power-shell timeout -o {KEEP_AWAKE_MS}")
            info["restore"] = {"type": "harmony_timeout", "prev": override_prev}
    info["state"] = harmony_power(hdc, serial)[0]
    return info


def wake_device(platform_, kind, device_id, keep_awake=True):
    """亮屏 + 解锁 + 防再次熄屏;返回可直接塞进结果 JSON 的 dict。"""
    if not device_id:
        return {"attempted": False, "reason": "no_device_id"}
    if platform_ == "android":
        adb = tool("adb")
        return (wake_android(adb, device_id, keep_awake) if adb
                else {"attempted": False, "reason": "adb_missing"})
    if platform_ == "harmony":
        hdc = hdc_tool()
        return (wake_harmony(hdc, device_id, keep_awake) if hdc
                else {"attempted": False, "reason": "hdc_missing"})
    if kind == "simulator":     # iOS 模拟器不会熄屏,也没有锁屏
        return {"attempted": False, "reason": "ios_simulator_no_lockscreen"}
    return {"attempted": False, "reason": "ios_physical_manual_unlock",
            "notes": ["iOS 真机无法程序解锁:请手动解锁,并把「设置 → 显示与亮度 → "
                      "自动锁定」设为「永不」"]}


def safe_wake(platform_, kind, device_id, keep_awake):
    """亮屏是锦上添花:任何异常都吞掉,绝不让 acquire 因此失败。"""
    try:
        info = wake_device(platform_, kind, device_id, keep_awake)
    except Exception as e:  # noqa: BLE001
        return {"attempted": False, "reason": f"error: {e}"}
    if info.get("attempted"):
        acted = ", ".join(info.get("actions") or []) or "无需操作"
        locked = info.get("locked")
        lock_txt = {True: "仍锁屏", False: "已解锁", None: "锁屏状态未知"}[locked]
        log(f"屏幕: {info.get('state') or '状态未知'} / {lock_txt}({acted})")
    for n in info.get("notes") or []:
        log(f"屏幕: {n}")
    return info


def record_screen_restore(key, screen):
    """把待还原的原值记进锁,**只记第一次**。

    重复 wake(测试中途反复熄屏)时若覆写,第二次读到的"原值"已经是我们自己设的
    常亮值,release 就会把设备永久留在常亮状态。
    """
    r = (screen or {}).get("restore")
    if not r or not key:
        return
    meta = read_lock(key)
    if meta is None or meta.get("screen_restore"):
        return
    update_lock(key, screen_restore=r)


def restore_screen(meta):
    """release / 回收陈旧锁时还原 acquire 改过的屏幕超时设置(尽力而为)。"""
    r = (meta or {}).get("screen_restore")
    dev = (meta or {}).get("device_id")
    if not isinstance(r, dict) or not dev:
        return None
    try:
        if r.get("type") == "android_stayon":
            adb = tool("adb")
            if not adb:
                return None
            rc, _, _ = run([adb, "-s", dev, "shell", "settings", "put", "global",
                            "stay_on_while_plugged_in", str(r.get("prev", "0"))],
                           timeout=RESTORE_TIMEOUT)
            return "android_stayon" if rc == 0 else None
        if r.get("type") == "harmony_timeout":
            hdc = hdc_tool()
            if not hdc:
                return None
            prev = r.get("prev")
            tail = ["-o", str(prev)] if prev else ["-r"]
            rc, _, _ = run([hdc, "-t", dev, "shell", "power-shell", "timeout"] + tail,
                           timeout=RESTORE_TIMEOUT)
            return "harmony_timeout" if rc == 0 else None
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------- 候选组装 ----------

def cand(tier, platform_, kind, key, name, device_id, needs_boot):
    return {"tier": tier, "platform": platform_, "kind": kind, "key": key,
            "name": name, "device_id": device_id, "needs_boot": needs_boot}


def gather_candidates(platforms, no_physical, warnings):
    """按优先级组装候选:tier1 真机 > tier2 已运行模拟器 > tier3 已停止模拟器。

    platforms 是有序列表(如 ["android", "harmony"]):tier 之间严格有序,同一 tier
    内按这个顺序排——所以 `--platform android,harmony` = 先 Android 后鸿蒙。
    """
    t1, t2, t3 = [], [], []
    for plat in platforms:
        if plat == "android":
            devs, adb = adb_devices(warnings)
            running_avds = {}
            for d in devs:
                if d["is_emulator"]:
                    avd = avd_for_serial(adb, d["serial"])
                    if avd:
                        running_avds[avd] = d["serial"]
                    else:
                        warnings.append(f"{d['serial']} 无法反查 AVD 名,跳过该实例")
                elif not no_physical:
                    t1.append(cand(1, "android", "physical",
                                   f"android-device:{d['serial']}",
                                   d["serial"], d["serial"], False))
            for avd in sorted(running_avds):
                t2.append(cand(2, "android", "emulator", f"android-avd:{avd}",
                               avd, running_avds[avd], False))
            for avd in sorted(list_avds(),
                              key=lambda a: (0 if a.startswith("ai-test-") else 1, a)):
                if avd not in running_avds:
                    t3.append(cand(3, "android", "emulator", f"android-avd:{avd}",
                                   avd, None, True))
        elif plat == "ios" and have_simctl():
            if not no_physical:
                for d in ios_physicals(warnings):
                    t1.append(cand(1, "ios", "physical", f"ios-device:{d['udid']}",
                                   d["name"], d["udid"], False))
            booted, shutdown = ios_sims()
            for s in booted:
                t2.append(cand(2, "ios", "simulator", f"ios-sim:{s['udid']}",
                               s["name"], s["udid"], False))
            for s in shutdown:
                t3.append(cand(3, "ios", "simulator", f"ios-sim:{s['udid']}",
                               s["name"], s["udid"], True))
        elif plat == "harmony":
            # 鸿蒙只分配「已经连着的」目标:真机 tier1、已启动的模拟器 tier2。
            # 启动/新建鸿蒙模拟器归 deveco-studio-emulator 管,本 skill 不碰,
            # 因此鸿蒙候选永远 needs_boot=False,不触发内存闸门。
            for d in hdc_devices(warnings)[0]:
                if d["is_emulator"]:
                    t2.append(cand(2, "harmony", "emulator",
                                   f"harmony-emu:{d['serial']}",
                                   d["serial"], d["serial"], False))
                elif not no_physical:
                    t1.append(cand(1, "harmony", "physical",
                                   f"harmony-device:{d['serial']}",
                                   d["serial"], d["serial"], False))
    return t1 + t2 + t3


PLATFORM_CHOICES = ("android", "ios", "harmony", "any")


def parse_platforms(spec):
    """--platform 解析:单值或逗号组合,返回去重后的有序列表。

    `any` 只展开成 android+ios,**不含 harmony**:标准 Flutter SDK 编不出 hap,
    把鸿蒙设备塞给「两端皆可」的项目会直接跑不起来。要用鸿蒙必须显式点名
    (`--platform harmony` 或 `--platform android,harmony`)。
    """
    raw = [s.strip().lower() for s in (spec or "android").split(",") if s.strip()]
    out = []
    for item in raw:
        if item not in PLATFORM_CHOICES:
            fail(EXIT_ARGS, "ARGS",
                 f"--platform 未知取值 {item!r}(可选 {'/'.join(PLATFORM_CHOICES)},"
                 f"支持逗号组合如 android,harmony)")
        for p in (("android", "ios") if item == "any" else (item,)):
            if p not in out:
                out.append(p)
    return out


# ---------- 创建层 ----------

def tag_rank(tag):
    if tag.startswith("google_apis") and "playstore" not in tag:
        return 0
    if "playstore" in tag:
        return 1
    if tag == "default":
        return 2
    return 3


def pick_system_image():
    """从已安装的 system-images 里挑:最高 API → google_apis 系 tag → 宿主 abi。"""
    sdk = sdk_root()
    base = os.path.join(sdk, "system-images") if sdk else None
    if not base or not os.path.isdir(base):
        return None
    abi = host_abi()
    found = []
    for api_dir in os.listdir(base):
        m = re.match(r"android-(\d+(?:\.\d+)?)", api_dir)
        if not m:
            continue
        api_path = os.path.join(base, api_dir)
        if not os.path.isdir(api_path):
            continue
        for tag in os.listdir(api_path):
            if os.path.isdir(os.path.join(api_path, tag, abi)):
                found.append((-float(m.group(1)), tag_rank(tag),
                              f"system-images;{api_dir};{tag};{abi}"))
    if not found:
        return None
    found.sort()
    return found[0][2]


def create_avd(name, pkg, memory_mb=None):
    avdmanager = tool("avdmanager")
    rc, out, err = run([avdmanager, "create", "avd", "-n", name, "-k", pkg, "--force"],
                       timeout=CREATE_AVD_TIMEOUT, input_text="no\n")
    if rc != 0:
        return False, ((err or out) or "").strip()[:300]
    if memory_mb:
        # 落到 config.ini,后续任何人启动这台(含不带 --memory)都按此内存跑
        ok, werr = set_avd_ram_mb(name, memory_mb)
        log(f"{name} guest RAM 设为 {memory_mb}MB" if ok
            else f"{name} 写入 hw.ramSize 失败({werr}),本次仅靠 -memory 生效")
    return True, None


def pick_sim_recipe():
    """最新 iOS runtime + 该 runtime 下编号最大的 iPhone(同编号取名最短)。"""
    data = simctl_json("runtimes")
    if not data:
        return None
    runtimes = [r for r in data.get("runtimes") or []
                if r.get("isAvailable") and "SimRuntime.iOS" in (r.get("identifier") or "")]
    if not runtimes:
        return None
    runtimes.sort(key=lambda r: runtime_version(r["identifier"]), reverse=True)
    rt = runtimes[0]
    dts = rt.get("supportedDeviceTypes") or []
    iphones = [d for d in dts if "iPhone" in (d.get("name") or "")] or dts
    if not iphones:
        return None

    def rankdt(d):
        nums = re.findall(r"\d+", d.get("name") or "")
        return (int(nums[0]) if nums else 0, -len(d.get("name") or ""))

    iphones.sort(key=rankdt, reverse=True)
    return iphones[0]["identifier"], rt["identifier"], iphones[0].get("name", "iPhone")


def create_sim(name, devtype, runtime):
    rc, out, err = run(["xcrun", "simctl", "create", name, devtype, runtime],
                       timeout=CREATE_SIM_TIMEOUT)
    if rc != 0:
        return None, ((err or out) or "").strip()[:300]
    lines = [s.strip() for s in out.strip().splitlines() if s.strip()]
    return (lines[-1] if lines else None), None


# ---------- 启动 / 就绪层 ----------

def boot_avd(avd, headless, timeout, memory_mb=None):
    emu, adb = tool("emulator"), tool("adb")
    if not emu or not adb:
        raise BootFailure("缺少 emulator/adb(检查 Android SDK)")
    before = all_emulator_serials(adb)
    cmd = [emu, "-avd", avd, "-no-audio", "-no-boot-anim"]
    if headless:
        cmd.append("-no-window")
    if memory_mb:
        cmd += ["-memory", str(memory_mb)]
        configured = avd_ram_mb(avd)
        if configured and configured != memory_mb:
            log(f"{avd} 配置的 {configured}MB 本次被 -memory {memory_mb} 覆盖"
                f"(仅本次运行,不改 config.ini);RAM 变了 quickboot 快照失效,本次冷启动")
    log(f"启动 Android 模拟器 {avd}"
        + (f"(guest RAM {memory_mb}MB,约 30-120s)…" if memory_mb else "(约 30-120s)…"))
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        raise BootFailure(f"emulator 进程启动失败: {e}")
    serial = None
    try:
        deadline = time.time() + SERIAL_DISCOVER_TIMEOUT
        while serial is None and time.time() < deadline:
            time.sleep(2)
            for s in sorted(all_emulator_serials(adb) - before):
                if avd_for_serial(adb, s) == avd:
                    serial = s
                    break
        if serial is None:
            raise BootFailure(f"{SERIAL_DISCOVER_TIMEOUT}s 内未发现 {avd} 的新模拟器串号")
        log(f"{avd} → {serial},等待 sys.boot_completed …")
        wait_android_booted(adb, serial, timeout, avd)
        return serial
    except BootFailure:
        _kill_launched_emulator(proc, adb, serial, avd)
        raise


def _kill_launched_emulator(proc, adb, serial, avd):
    """启动失败回滚:关掉本次拉起的模拟器,不遗留后台进程。"""
    log(f"回滚:关闭本次启动失败的模拟器 {avd}" + (f"({serial})" if serial else ""))
    if serial:
        run([adb, "-s", serial, "emu", "kill"], timeout=10)
        for _ in range(5):
            if proc.poll() is not None:
                return
            time.sleep(1)
    if proc.poll() is None:
        proc.kill()


def wait_android_booted(adb, serial, timeout, label):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc, out, _ = run([adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                         timeout=10)
        if rc == 0 and out.strip() == "1":
            return
        time.sleep(2)
    raise BootFailure(f"{label}({serial}) 等待启动完成超时({timeout}s)")


def boot_sim(udid, headless, timeout):
    rc, out, err = run(["xcrun", "simctl", "boot", udid], timeout=30)
    combined = (out or "") + (err or "")
    we_booted = rc == 0  # rc!=0 且含 Booted = 它本来就开着,失败时不要替人关机
    if rc != 0 and "Booted" not in combined:
        raise BootFailure(f"simctl boot 失败: {combined.strip()[:200]}")
    rc, out, err = run(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=timeout)
    if rc != 0:
        if we_booted:
            log(f"回滚:关闭本次启动失败的模拟器 {udid}")
            run(["xcrun", "simctl", "shutdown", udid], timeout=30)
        raise BootFailure(f"simctl bootstatus 未就绪: {((err or out) or '').strip()[:200]}")
    if not headless and sys.platform == "darwin":
        run(["open", "-g", "-a", "Simulator"], timeout=10)


# ---------- 命令层 ----------

def script_path():
    return os.path.abspath(__file__)


def build_result(c, owner, project, created, booted, reused):
    dev = c["device_id"]
    usage = {"flutter_run": f"flutter run -d {dev}",
             "flutter_drive": ("flutter drive --driver=test_driver/integration_test.dart "
                               f"--target=integration_test/app_test.dart -d {dev}")}
    if c["platform"] == "android":
        usage["adb"] = f"adb -s {dev} <command>"
    elif c["platform"] == "harmony":
        usage["hdc"] = f"{hdc_tool() or 'hdc'} -t {dev} <command>"
        usage["note"] = ("鸿蒙设备需用 OpenHarmony 版 Flutter SDK(flutter build hap),"
                         "且项目要有 ohos 模块")
    return {"ok": True, "action": "acquire",
            "device_key": c["key"], "platform": c["platform"], "kind": c["kind"],
            "device_id": dev, "name": c["name"],
            "memory_mb": c.get("memory_mb"),
            "created": created, "booted": booted, "reused": reused,
            "owner_pid": owner, "project": project,
            "lock_dir": lock_dir(c["key"]),
            "release_cmd": f"python3 {script_path()} release --key {c['key']}",
            "usage": usage}


def make_meta(c, owner, project, ttl, created=False, booted=False):
    return {"allocator_version": ALLOCATOR_VERSION,
            "device_key": c["key"], "platform": c["platform"], "kind": c["kind"],
            "device_id": c["device_id"], "name": c["name"],
            "owner_pid": owner, "project": project,
            "acquired_at": now_iso(), "ttl_hours": ttl,
            "created_by_allocator": created, "booted_by_allocator": booted,
            "memory_mb": c.get("memory_mb")}


def timeout_for(args, platform_):
    if args.timeout:
        return args.timeout
    return ANDROID_BOOT_TIMEOUT if platform_ == "android" else IOS_BOOT_TIMEOUT


def resolve_memory_mb(cli_value):
    """--memory > AI_DEVICE_EMULATOR_MEMORY > 不指定(用 AVD 自带的 hw.ramSize)。"""
    raw = cli_value
    src = "--memory"
    if raw is None:
        env = os.environ.get("AI_DEVICE_EMULATOR_MEMORY", "").strip()
        if not env:
            return None
        src = "AI_DEVICE_EMULATOR_MEMORY"
        try:
            raw = int(env)
        except ValueError:
            fail(EXIT_ARGS, "ARGS", f"{src} 不是整数: {env!r}")
    if raw < EMU_MEM_MIN_MB or raw > EMU_MEM_MAX_MB:
        fail(EXIT_ARGS, "ARGS",
             f"{src} 需在 {EMU_MEM_MIN_MB}-{EMU_MEM_MAX_MB} MB 之间,收到 {raw}")
    if raw < EMU_MEM_WARN_MB:
        log(f"警告:guest RAM {raw}MB 低于 {EMU_MEM_WARN_MB}MB,"
            f"API 31+ 镜像可能触发 lowmemorykiller 杀掉被测 app"
            f"(表现为莫名的 Lost connection to device)")
    return raw


def emu_memory_for(c, memory_mb):
    """-memory 只对 Android 模拟器有意义;真机与 iOS 模拟器没有这个旋钮。"""
    if memory_mb and c["platform"] == "android" and c["kind"] == "emulator":
        return memory_mb
    return None


def reuse_existing(meta, args, warnings):
    """幂等重取:确认已持有的设备仍就绪(必要时重新启动)。

    重启已持有的模拟器不过内存闸门:它只是恢复之前的占用,总量不增。
    """
    c = {"tier": 0, "platform": meta["platform"], "kind": meta["kind"],
         "key": meta["device_key"], "name": meta.get("name"),
         "device_id": meta.get("device_id"), "needs_boot": False,
         "memory_mb": meta.get("memory_mb")}
    if meta["platform"] == "harmony":
        # 鸿蒙设备本 skill 不负责启动:还在线就继续用,断了就当场放弃、另行分配
        if not any(d["serial"] == c["device_id"] for d in hdc_devices(warnings)[0]):
            raise BootFailure(f"鸿蒙设备 {c['device_id']} 已不在 hdc 目标列表(断连或关机)")
        return c
    if meta["kind"] == "physical":
        return c
    if meta["platform"] == "android":
        adb = tool("adb")
        if not adb:
            raise BootFailure("adb 不可用")
        devs, _ = adb_devices(warnings)
        for d in devs:
            if d["is_emulator"] and avd_for_serial(adb, d["serial"]) == meta.get("name"):
                c["device_id"] = d["serial"]
                return c
        # 重启已持有的 AVD:沿用当初的内存设定,避免 RAM 变动再作废一次快照
        c["memory_mb"] = emu_memory_for(c, args.memory or meta.get("memory_mb"))
        c["device_id"] = boot_avd(meta["name"], args.headless, timeout_for(args, "android"),
                                  c["memory_mb"])
        update_lock(c["key"], device_id=c["device_id"], booted_by_allocator=True,
                    memory_mb=c["memory_mb"])
        return c
    boot_sim(meta["device_id"], args.headless, timeout_for(args, "ios"))
    return c


def flush_warnings(warnings):
    for w in warnings:
        log(w)


def finish_acquire(c, owner, project, created, booted, reused, args, warnings):
    """收尾:亮屏解锁 → 输出结果 JSON(亮屏失败不影响分配结果)。"""
    if args.no_wake:
        screen = {"attempted": False, "reason": "disabled_by_--no-wake"}
    else:
        screen = safe_wake(c["platform"], c["kind"], c.get("device_id"),
                           not args.no_keep_awake)
        record_screen_restore(c["key"], screen)
    result = build_result(c, owner, project, created, booted, reused)
    result["screen"] = screen
    flush_warnings(warnings)
    emit(result)


def resolve_acquire_platforms(args, warnings):
    """解析 --platform,并剔除本机工具链缺失的平台(只剩一个平台时直接报错)。"""
    platforms = parse_platforms(args.platform)
    for plat, ok, why in (
            ("ios", have_simctl(),
             "本机没有 xcrun/simctl,无法分配 iOS 设备(iOS 仅支持 macOS + Xcode)"),
            ("harmony", hdc_tool() is not None,
             "找不到 hdc(HarmonyOS 设备连接器),无法分配鸿蒙设备")):
        if plat in platforms and not ok:
            if platforms == [plat]:
                hint = ("装 DevEco Studio,或设环境变量 HDC_PATH 指向 hdc 可执行文件"
                        "(通常在 <DevEco 安装目录>/sdk/default/openharmony/toolchains/hdc)"
                        if plat == "harmony" else None)
                fail(EXIT_ENV_MISSING, "ENV_MISSING", why, hint=hint)
            platforms.remove(plat)
            warnings.append(f"{why},本次跳过该平台")
    return platforms


def cmd_acquire(args):
    owner = args.owner or default_owner_pid()
    project = os.path.abspath(args.project or os.getcwd())
    warnings = []
    sweep_stale_locks()
    platforms = resolve_acquire_platforms(args, warnings)
    args.memory = resolve_memory_mb(args.memory)
    if args.memory and platforms == ["ios"]:
        warnings.append("--memory 仅对 Android 模拟器生效,iOS 模拟器不是 VM,本次忽略")

    # 幂等重取:同 owner + project 的存活锁直接复用,不多占设备
    mine = find_my_lock(owner, project)
    if mine and (not args.device or args.device in (mine.get("device_id"), mine.get("name"))):
        log(f"已持有 {mine['device_key']},幂等复用")
        try:
            c = reuse_existing(mine, args, warnings)
            update_lock(c["key"], acquired_at=now_iso())
            finish_acquire(c, owner, project,
                           created=mine.get("created_by_allocator", False),
                           booted=mine.get("booted_by_allocator", False), reused=True,
                           args=args, warnings=warnings)
        except BootFailure as e:
            log(f"已持设备恢复失败({e}),释放后重新分配")
            release_lock(mine["device_key"])

    explicit = bool(args.device)
    # 只有纯 Android 才能确定新起的是 Android 模拟器,按 --memory 收窄每台开销;
    # 混了 ios 时可能落到无法限内存的 iOS 模拟器上,仍按保守默认估算。
    gate = mem_policy(max_override=args.max_emulators, ignore=args.mem_override,
                      memory_mb=args.memory if platforms == ["android"] else None,
                      include_harmony="harmony" in platforms)
    mem_blocked = False
    cands = gather_candidates(platforms,
                              False if explicit else args.no_physical, warnings)
    if explicit:
        matches = [c for c in cands
                   if args.device in (c["device_id"], c["name"]) or c["key"] == args.device]
        if not matches:
            visible = ", ".join(sorted({str(c["device_id"] or c["name"])
                                        for c in cands})) or "无"
            fail(EXIT_NO_DEVICE, "NO_DEVICE",
                 f"找不到设备 {args.device}(当前可见: {visible})",
                 hint="运行 status 查看设备与锁全景")
        cands = matches[:1]

    mem_warned = False
    for c in cands:
        if c["needs_boot"] and gate["enabled"] and gate["blocked"]:
            if explicit:
                log(f"内存闸门告警({gate['reason']}),但按 --device 指定强制继续")
            else:
                if not mem_blocked:
                    log(f"内存闸门:跳过启动停止态模拟器({gate['reason']})")
                mem_blocked = True
                continue
        if c["needs_boot"] and gate.get("warning") and not mem_warned:
            # 只在真要启动模拟器时提示;领到真机/已运行模拟器则与内存无关。
            log(f"内存闸门:{gate['warning']}")
            mem_warned = True
        # 只有真要启动它时才谈内存;复用已在跑的模拟器改不了它的 RAM
        c["memory_mb"] = emu_memory_for(c, args.memory) if c["needs_boot"] else None
        meta = make_meta(c, owner, project, args.ttl)
        if not acquire_lock_with_reclaim(c["key"], meta):
            if explicit:
                held = read_lock(c["key"]) or {}
                fail(EXIT_BUSY, "BUSY",
                     f"设备 {args.device} 正被占用(owner_pid={held.get('owner_pid')}, "
                     f"project={held.get('project')})",
                     hint="去掉 --device 让脚本另挑一台;或 status 查看、clean 清陈旧锁")
            continue
        try:
            booted = False
            if c["needs_boot"]:
                if c["platform"] == "android":
                    c["device_id"] = boot_avd(c["name"], args.headless,
                                              timeout_for(args, "android"),
                                              c["memory_mb"])
                else:
                    boot_sim(c["device_id"], args.headless, timeout_for(args, "ios"))
                booted = True
                update_lock(c["key"], device_id=c["device_id"], booted_by_allocator=True)
            elif c["platform"] == "android" and c["kind"] == "emulator":
                wait_android_booted(tool("adb"), c["device_id"],
                                    RUNNING_EMU_READY_TIMEOUT, c["name"])
        except BootFailure as e:
            release_lock(c["key"])
            if explicit:
                fail(EXIT_BOOT_TIMEOUT, "BOOT_TIMEOUT", f"{c['name']} 启动失败: {e}")
            log(f"{c['name']} 启动失败({e}),换下一个候选")
            continue
        finish_acquire(c, owner, project, created=False, booted=booted, reused=False,
                       args=args, warnings=warnings)

    if args.no_create:
        if mem_blocked:
            fail(EXIT_MEMORY, "MEMORY_PRESSURE",
                 f"停止态模拟器被内存闸门拦下,且 --no-create 禁止新建({gate['reason']})",
                 hint=MEM_HINT)
        fail(EXIT_NO_DEVICE, "NO_DEVICE", "没有空闲设备,且 --no-create 禁止新建",
             hint="等待其他会话 release;或 status 查看占用")

    if gate["enabled"] and gate["blocked"]:
        fail(EXIT_MEMORY, "MEMORY_PRESSURE",
             f"不再启动/新建模拟器:{gate['reason']}", hint=MEM_HINT)
    if gate.get("warning") and not mem_warned:
        log(f"内存闸门:{gate['warning']}")
        mem_warned = True

    # 只有 Android / iOS 能由本 skill 新建;鸿蒙模拟器交给 deveco-studio-emulator。
    # `--platform any` 保持「先建 iOS(更快)再建 Android」。
    creatable = [p for p in platforms if p in ("android", "ios")]
    any_spec = "any" in [s.strip().lower() for s in (args.platform or "").split(",")]
    create_order = ([p for p in ("ios", "android") if p in creatable] if any_spec
                    else creatable)
    if not create_order:
        fail(EXIT_NO_DEVICE, "NO_DEVICE",
             "没有空闲的鸿蒙设备,且本 skill 不负责启动/新建鸿蒙模拟器",
             hint="连上鸿蒙真机,或用 deveco-studio-emulator skill 先把鸿蒙模拟器跑起来"
                  "再重试;也可以加上 Android:--platform android,harmony")

    last_env_fail = None
    for plat in create_order:
        name = f"ai-test-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        if plat == "ios":
            recipe = pick_sim_recipe()
            if not recipe:
                last_env_fail = "没有可用 iOS simulator runtime(Xcode → Settings → Platforms 安装)"
                continue
            devtype, runtime, dtname = recipe
            log(f"无空闲设备,新建 iOS 模拟器 {name}({dtname})…")
            udid, err = create_sim(name, devtype, runtime)
            if not udid:
                last_env_fail = f"simctl create 失败: {err}"
                continue
            c = cand(4, "ios", "simulator", f"ios-sim:{udid}", name, udid, True)
            try_lock(c["key"], make_meta(c, owner, project, args.ttl, created=True))
            try:
                boot_sim(udid, args.headless, timeout_for(args, "ios"))
            except BootFailure as e:
                release_lock(c["key"])
                fail(EXIT_BOOT_TIMEOUT, "BOOT_TIMEOUT",
                     f"新建 iOS 模拟器 {name} 启动失败: {e}")
            update_lock(c["key"], booted_by_allocator=True)
            finish_acquire(c, owner, project, created=True, booted=True, reused=False,
                           args=args, warnings=warnings)
        else:
            if not tool("adb") or not tool("emulator") or not tool("avdmanager"):
                last_env_fail = "Android SDK 不完整(需要 platform-tools、emulator、cmdline-tools)"
                continue
            pkg = pick_system_image()
            if not pkg:
                sm = tool("sdkmanager") or "sdkmanager"
                fail(EXIT_NO_SYSTEM_IMAGE, "NO_SYSTEM_IMAGE",
                     "本机没有已安装的 Android system image,无法新建 AVD(本工具不自动下载)",
                     hint=f'"{sm}" "system-images;android-36;google_apis;{host_abi()}" '
                          f'安装后重试;许可证问题先 yes | "{sm}" --licenses')
            log(f"无空闲设备,新建 Android AVD {name}({pkg})…")
            ok, err = create_avd(name, pkg, args.memory)
            if not ok:
                fail(EXIT_INTERNAL, "INTERNAL", f"avdmanager create 失败: {err}",
                     hint="若提示许可证未接受: yes | sdkmanager --licenses")
            c = cand(4, "android", "emulator", f"android-avd:{name}", name, None, True)
            c["memory_mb"] = args.memory
            try_lock(c["key"], make_meta(c, owner, project, args.ttl, created=True))
            try:
                c["device_id"] = boot_avd(name, args.headless, timeout_for(args, "android"),
                                          c["memory_mb"])
            except BootFailure as e:
                release_lock(c["key"])
                fail(EXIT_BOOT_TIMEOUT, "BOOT_TIMEOUT", f"新建 AVD {name} 启动失败: {e}")
            update_lock(c["key"], device_id=c["device_id"], booted_by_allocator=True)
            finish_acquire(c, owner, project, created=True, booted=True, reused=False,
                           args=args, warnings=warnings)

    platform_hint = ("默认平台是 android;要用 iOS 模拟器传 --platform ios,两端皆可传 "
                     "--platform any;Flutter 项目有 ohos 模块、且本次功能不是鸿蒙特有的,"
                     "可以放开到 --platform android,harmony"
                     if platforms == ["android"] else None)
    if last_env_fail:
        fail(EXIT_ENV_MISSING, "ENV_MISSING", f"无空闲设备且无法新建: {last_env_fail}",
             hint=platform_hint)
    fail(EXIT_NO_DEVICE, "NO_DEVICE", "无空闲设备且无法新建模拟器", hint=platform_hint)


def cmd_release(args):
    released, not_found = [], []
    keys = []
    if args.key:
        keys = [args.key]
    elif args.device:
        for _, meta, _ in list_locks():
            if meta and args.device in (meta.get("device_id"), meta.get("name")):
                keys.append(meta.get("device_key"))
        if not keys:
            not_found.append(args.device)
    else:  # --all-mine
        owner = args.owner or default_owner_pid()
        keys = [m.get("device_key") for _, m, _ in list_locks()
                if m and m.get("owner_pid") == owner]
    for k in keys:
        if k and release_lock(k):
            released.append(k)
        else:
            not_found.append(k)
    if released:
        log(f"已释放: {', '.join(released)}(模拟器保持运行,供下个会话复用)")
    emit({"ok": True, "action": "release", "released": released, "not_found": not_found})


def infer_device(device_id, warnings):
    """没有锁记录时,从当前连着的设备反查它属于哪个平台。"""
    for d in adb_devices(warnings)[0]:
        if d["serial"] == device_id:
            return {"platform": "android",
                    "kind": "emulator" if d["is_emulator"] else "physical",
                    "device_id": device_id, "name": device_id}
    if hdc_tool():
        for d in hdc_devices(warnings)[0]:
            if d["serial"] == device_id:
                return {"platform": "harmony",
                        "kind": "emulator" if d["is_emulator"] else "physical",
                        "device_id": device_id, "name": device_id}
    for s in ios_sims()[0]:
        if s["udid"] == device_id:
            return {"platform": "ios", "kind": "simulator",
                    "device_id": device_id, "name": s["name"]}
    return None


def cmd_wake(args):
    """把设备重新点亮解锁——测到一半熄屏时调它,不用重新 acquire。"""
    warnings = []
    targets = []
    if args.key:
        m = read_lock(args.key)
        if not m:
            fail(EXIT_NO_DEVICE, "NO_DEVICE", f"找不到锁 {args.key}",
                 hint="用 status 看当前有哪些锁")
        targets.append(m)
    elif args.device:
        targets = [m for _, m, _ in list_locks()
                   if m and args.device in (m.get("device_id"), m.get("name"))]
        if not targets:
            guessed = infer_device(args.device, warnings)
            if not guessed:
                fail(EXIT_NO_DEVICE, "NO_DEVICE",
                     f"设备 {args.device} 既不在锁记录里,也不在当前连着的设备中",
                     hint="用 status 看设备与锁全景")
            targets.append(guessed)
    else:   # 默认:本会话(owner+project)持有的设备;--all-mine 则按 owner 全取
        owner = args.owner or default_owner_pid()
        project = os.path.abspath(args.project or os.getcwd())
        if args.all_mine:
            targets = [m for _, m, _ in list_locks() if m and m.get("owner_pid") == owner]
        else:
            mine = find_my_lock(owner, project)
            if mine:
                targets.append(mine)
        if not targets:
            fail(EXIT_NO_DEVICE, "NO_DEVICE", "本会话没有持有任何设备锁",
                 hint="先 acquire;或用 --device <id> 指定要点亮的设备")

    results = []
    for m in targets:
        screen = safe_wake(m.get("platform"), m.get("kind"), m.get("device_id"),
                           not args.no_keep_awake)
        record_screen_restore(m.get("device_key"), screen)
        results.append({"device_key": m.get("device_key"), "platform": m.get("platform"),
                        "device_id": m.get("device_id"), "name": m.get("name"),
                        "screen": screen})
    flush_warnings(warnings)
    emit({"ok": True, "action": "wake", "results": results})


def cmd_status(args):
    warnings = []
    devices = []
    seen_dirs = set()

    def lock_view(key):
        d = lock_dir(key)
        if not os.path.isdir(d):
            return None
        seen_dirs.add(os.path.basename(d))
        meta = read_meta(d)
        state, reason = eval_lock(d, meta)
        view = {"state": state}
        if reason:
            view["reason"] = reason
        if meta:
            age = lock_age_hours(meta, d)
            view.update({"owner_pid": meta.get("owner_pid"),
                         "owner_alive": pid_alive(meta.get("owner_pid")),
                         "project": meta.get("project"),
                         "acquired_at": meta.get("acquired_at"),
                         "age_hours": None if age is None else round(age, 2),
                         "created_by_allocator": meta.get("created_by_allocator", False)})
        return view

    def add(key, platform_, kind, device_id, name, dstate, ram_mb=None):
        devices.append({"key": key, "platform": platform_, "kind": kind,
                        "device_id": device_id, "name": name, "state": dstate,
                        "ram_mb": ram_mb, "lock": lock_view(key)})

    devs, adb = adb_devices(warnings)
    running_avds = {}
    for d in devs:
        if d["is_emulator"]:
            avd = avd_for_serial(adb, d["serial"])
            if avd:
                running_avds[avd] = d["serial"]
            else:
                warnings.append(f"{d['serial']} 无法反查 AVD 名")
        else:
            add(f"android-device:{d['serial']}", "android", "physical",
                d["serial"], d["serial"], "running")
    for avd, serial in sorted(running_avds.items()):
        add(f"android-avd:{avd}", "android", "emulator", serial, avd, "running",
            avd_ram_mb(avd))
    for avd in sorted(list_avds()):
        if avd not in running_avds:
            add(f"android-avd:{avd}", "android", "emulator", None, avd, "stopped",
                avd_ram_mb(avd))
    for d in ios_physicals(warnings):
        add(f"ios-device:{d['udid']}", "ios", "physical", d["udid"], d["name"], "connected")
    harmony_vms = 0
    if hdc_tool():
        for d in hdc_devices(warnings)[0]:
            if d["is_emulator"]:
                harmony_vms += 1
                add(f"harmony-emu:{d['serial']}", "harmony", "emulator",
                    d["serial"], d["serial"], "running")
            else:
                add(f"harmony-device:{d['serial']}", "harmony", "physical",
                    d["serial"], d["serial"], "connected")
    booted, shutdown = ios_sims()
    for s in booted:
        add(f"ios-sim:{s['udid']}", "ios", "simulator", s["udid"], s["name"], "booted")
    for s in shutdown:
        add(f"ios-sim:{s['udid']}", "ios", "simulator", s["udid"], s["name"], "shutdown")

    orphans = []
    for dirname, meta, path in list_locks():
        if dirname in seen_dirs:
            continue
        state, reason = eval_lock(path, meta)
        orphans.append({"lock_dir": path,
                        "device_key": (meta or {}).get("device_key", dirname),
                        "state": state, "reason": reason,
                        "owner_pid": (meta or {}).get("owner_pid"),
                        "project": (meta or {}).get("project")})
    total, avail = mem_total_gb(), mem_available_gb()
    max_vms = env_max_vms()
    if max_vms is None:
        max_vms = auto_max_vms(total)
    running_vms = len(running_avds) + len(booted) + harmony_vms
    # 与 mem_policy 同规则:0 台在跑时可用内存检查不拦第一台。
    quota_ok = max_vms is None or running_vms < max_vms
    avail_ok = (running_vms == 0 or avail is None
                or avail >= per_vm_gb() + MEM_MIN_FREE_GB)
    memory = {"total_gb": None if total is None else round(total, 1),
              "available_gb": None if avail is None else round(avail, 1),
              "running_vms": running_vms, "max_vms": max_vms,
              "per_vm_gb": per_vm_gb(), "reserve_gb": MEM_RESERVE_GB,
              "vm_overhead_gb": MEM_VM_OVERHEAD_GB,
              "can_start_new_vm": quota_ok and avail_ok}
    emit({"ok": True, "action": "status", "lock_root": lock_root(),
          "memory": memory,
          "devices": devices, "orphan_locks": orphans, "warnings": warnings})


def cmd_clean(args):
    removed, kept = [], []
    for dirname, meta, path in list_locks():
        label = (meta or {}).get("device_key", dirname)
        if args.all:
            stale = True
        else:
            state, _ = eval_lock(path, meta, args.ttl)
            stale = state == "STALE"
        if stale and reclaim_path(path):
            removed.append(label)
            restore_screen(meta)
        else:
            kept.append(label)
    emit({"ok": True, "action": "clean", "removed": removed, "kept": kept})


def main():
    global _ACTION
    ap = argparse.ArgumentParser(
        prog="device_lock.py",
        description="多项目并发 AI 测试的设备分配与互斥锁(stdout 为单行 JSON,日志走 stderr)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("acquire", help="领取并锁定一台空闲设备")
    a.add_argument("--platform", default="android",
                   metavar="{android,ios,harmony,any,逗号组合}",
                   help="平台(默认 android;两端皆可用 any=android+ios;鸿蒙需显式点名,"
                        "如 harmony 或 android,harmony——同 tier 内按所列顺序优先)")
    a.add_argument("--device", help="指定设备(serial / UDID / AVD 名),只尝试它")
    a.add_argument("--no-physical", action="store_true", help="排除真机")
    a.add_argument("--no-create", action="store_true", help="只复用现有设备,不新建")
    a.add_argument("--headless", action="store_true", help="新启动的模拟器不显示窗口")
    a.add_argument("--owner", type=int, help="锁持有者 pid(默认取会话进程,建议传 $PPID)")
    a.add_argument("--project", help="占用方项目路径(默认当前目录)")
    a.add_argument("--ttl", type=float, default=DEFAULT_TTL_HOURS,
                   help="锁最大年龄(小时,默认 8)")
    a.add_argument("--timeout", type=int,
                   help="启动等待秒数(默认 Android 300 / iOS 180)")
    a.add_argument("--max-emulators", type=int,
                   help="并发模拟器总数上限(含 iOS Booted;默认按宿主内存自动推导,"
                        "环境变量 AI_DEVICE_MAX_EMULATORS 亦可覆盖)")
    a.add_argument("--mem-override", action="store_true",
                   help="跳过内存闸门(等效 AI_DEVICE_MEM_OVERRIDE=1)")
    a.add_argument("--memory", type=int, metavar="MB",
                   help=f"Android 模拟器 guest RAM({EMU_MEM_MIN_MB}-{EMU_MEM_MAX_MB} MB;"
                        "新建的 AVD 写进 config.ini,启动已有 AVD 只本次覆盖);"
                        "内存闸门的每台开销随之变小,压小可多跑一台。"
                        "环境变量 AI_DEVICE_EMULATOR_MEMORY 亦可设定;iOS 模拟器不支持")
    a.add_argument("--no-wake", action="store_true",
                   help="不做亮屏解锁(默认会唤醒并尝试解锁分配到的设备)")
    a.add_argument("--no-keep-awake", action="store_true",
                   help="亮屏但不修改屏幕超时/常亮设置(默认会拉长,release 时还原)")

    w = sub.add_parser("wake", help="把设备重新亮屏解锁(测试中途熄屏时用)")
    wg = w.add_mutually_exclusive_group()
    wg.add_argument("--key", help="按 device_key 指定")
    wg.add_argument("--device", help="按 device id / 名称指定(不在锁里也能点亮)")
    wg.add_argument("--all-mine", action="store_true", help="本 owner 持有的全部设备")
    w.add_argument("--owner", type=int, help="锁持有者 pid(默认取会话进程)")
    w.add_argument("--project", help="项目路径(默认当前目录,用于定位本会话的锁)")
    w.add_argument("--no-keep-awake", action="store_true",
                   help="只亮屏解锁,不修改屏幕超时/常亮设置")

    r = sub.add_parser("release", help="释放锁(幂等,恒 exit 0)")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--key", help="acquire 返回的 device_key")
    g.add_argument("--device", help="按 device id / 名称释放")
    g.add_argument("--all-mine", action="store_true", help="释放本会话持有的全部锁")
    r.add_argument("--owner", type=int, help="配合 --all-mine(默认取会话进程)")

    sub.add_parser("status", help="设备 × 锁全景")

    c = sub.add_parser("clean", help="回收陈旧锁")
    c.add_argument("--all", action="store_true", help="清除全部锁(慎用)")
    c.add_argument("--ttl", type=float, help="按此 TTL(小时)重新判定陈旧")

    args = ap.parse_args()
    _ACTION = args.cmd
    try:
        {"acquire": cmd_acquire, "release": cmd_release, "wake": cmd_wake,
         "status": cmd_status, "clean": cmd_clean}[args.cmd](args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        fail(EXIT_INTERNAL, "INTERNAL", "被中断")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc(file=sys.stderr)
        fail(EXIT_INTERNAL, "INTERNAL", f"未预期异常: {e}")


if __name__ == "__main__":
    main()
