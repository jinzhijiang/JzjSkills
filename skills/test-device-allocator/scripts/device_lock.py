#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""device_lock.py — 多项目并发 AI 测试的设备分配与互斥锁。

用法:
  python3 device_lock.py acquire [--platform any|android|ios] [--device <id>] [...]
  python3 device_lock.py release --key <device_key> | --device <id> | --all-mine
  python3 device_lock.py status
  python3 device_lock.py clean [--all]

stdout 只输出单行 JSON(机读);人读过程信息全部走 stderr。
锁注册表:~/.ai-device-locks(环境变量 AI_DEVICE_LOCKS_DIR 可覆盖)。
仅用 python3 标准库。完整契约见同 skill 的 references/cli.md。
"""

import argparse
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

EXIT_OK, EXIT_ARGS, EXIT_NO_DEVICE, EXIT_NO_SYSTEM_IMAGE = 0, 2, 3, 4
EXIT_BOOT_TIMEOUT, EXIT_ENV_MISSING, EXIT_BUSY, EXIT_INTERNAL = 5, 6, 7, 8
EXIT_MEMORY = 9

# 内存闸门:启动/新建模拟器前按宿主内存核算,避免超卖把整机拖进 swap(模拟器整体
# 冻结的常见根因)。真机与已在运行的模拟器不受影响;探测失败自动放行(fail-open)。
MEM_RESERVE_GB = 8.0    # 预留给 OS / IDE / 构建进程的基线内存
MEM_PER_VM_GB = 4.0     # 每台模拟器的估算宿主开销(约 2GB guest RAM + QEMU/图形转发)
MEM_MIN_FREE_GB = 2.0   # 启动新 VM 时,估算开销之外还需的安全垫
MEM_MAX_VMS_CAP = 4     # 自动配额上限(--max-emulators / AI_DEVICE_MAX_EMULATORS 可突破)

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

    macOS 的 free 页远低估真实可用量,按 free+inactive+purgeable+speculative 估算。
    """
    try:
        if sys.platform == "darwin":
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


def auto_max_vms(total_gb):
    """按总内存推导并发模拟器上限:(总量-预留)/每台开销,夹在 [1, CAP]。"""
    if total_gb is None:
        return None
    return max(1, min(MEM_MAX_VMS_CAP,
                      int((total_gb - MEM_RESERVE_GB) // MEM_PER_VM_GB)))


def env_max_vms():
    v = os.environ.get("AI_DEVICE_MAX_EMULATORS", "").strip()
    try:
        return int(v) if v else None
    except ValueError:
        return None


def running_vm_count():
    """当前在跑的模拟器总数(Android emulator 串号 + iOS Booted)。

    offline/卡死的 emulator 串号也计入——进程还活着就仍占着内存。
    """
    n = 0
    adb = tool("adb")
    if adb:
        n += len(all_emulator_serials(adb))
    if have_simctl():
        booted, _ = ios_sims()
        n += len(booted)
    return n


def mem_policy(max_override=None, ignore=False):
    """评估内存闸门,返回 dict。enabled=False 表示不拦截(显式覆盖或探测失败)。"""
    info = {"enabled": True, "blocked": False, "reason": None,
            "total_gb": None, "available_gb": None,
            "running_vms": None, "max_vms": None,
            "need_gb": round(MEM_PER_VM_GB + MEM_MIN_FREE_GB, 1)}
    if ignore or os.environ.get("AI_DEVICE_MEM_OVERRIDE", "").lower() in ("1", "true", "yes"):
        info["enabled"] = False
        return info
    total, avail = mem_total_gb(), mem_available_gb()
    info["total_gb"] = None if total is None else round(total, 1)
    info["available_gb"] = None if avail is None else round(avail, 1)
    max_vms = max_override if max_override is not None else env_max_vms()
    if max_vms is None:
        max_vms = auto_max_vms(total)
    info["max_vms"] = max_vms
    if max_vms is None and avail is None:
        info["enabled"] = False  # 全部探测失败,放行
        return info
    running = running_vm_count()
    info["running_vms"] = running
    if max_vms is not None and running >= max_vms:
        info["blocked"] = True
        info["reason"] = (f"并发配额已满:宿主内存 {info['total_gb']}GB 对应上限 "
                          f"{max_vms} 台模拟器,当前已有 {running} 台在运行")
    elif avail is not None and avail < MEM_PER_VM_GB + MEM_MIN_FREE_GB:
        info["blocked"] = True
        info["reason"] = (f"可用内存不足:当前约 {info['available_gb']}GB,"
                          f"再启动一台估算需 {info['need_gb']}GB")
    return info


MEM_HINT = ("优先领真机或复用已在运行的空闲模拟器;关闭闲置模拟器释放内存"
            "(adb -s <id> emu kill / xcrun simctl shutdown <udid>)后重试;"
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
    d = lock_dir(key)
    if not os.path.isdir(d):
        return False
    return reclaim_path(d)


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


# ---------- 候选组装 ----------

def cand(tier, platform_, kind, key, name, device_id, needs_boot):
    return {"tier": tier, "platform": platform_, "kind": kind, "key": key,
            "name": name, "device_id": device_id, "needs_boot": needs_boot}


def gather_candidates(platform_filter, no_physical, warnings):
    """按优先级组装候选:tier1 真机 > tier2 已运行模拟器 > tier3 已停止模拟器。"""
    want_android = platform_filter in ("android", "any")
    want_ios = platform_filter in ("ios", "any") and have_simctl()
    t1, t2, t3 = [], [], []
    if want_android:
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
    if want_ios:
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
    return t1 + t2 + t3


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


def create_avd(name, pkg):
    avdmanager = tool("avdmanager")
    rc, out, err = run([avdmanager, "create", "avd", "-n", name, "-k", pkg, "--force"],
                       timeout=CREATE_AVD_TIMEOUT, input_text="no\n")
    if rc != 0:
        return False, ((err or out) or "").strip()[:300]
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

def boot_avd(avd, headless, timeout):
    emu, adb = tool("emulator"), tool("adb")
    if not emu or not adb:
        raise BootFailure("缺少 emulator/adb(检查 Android SDK)")
    before = all_emulator_serials(adb)
    cmd = [emu, "-avd", avd, "-no-audio", "-no-boot-anim"]
    if headless:
        cmd.append("-no-window")
    log(f"启动 Android 模拟器 {avd}(约 30-120s)…")
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
    return {"ok": True, "action": "acquire",
            "device_key": c["key"], "platform": c["platform"], "kind": c["kind"],
            "device_id": dev, "name": c["name"],
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
            "created_by_allocator": created, "booted_by_allocator": booted}


def timeout_for(args, platform_):
    if args.timeout:
        return args.timeout
    return ANDROID_BOOT_TIMEOUT if platform_ == "android" else IOS_BOOT_TIMEOUT


def reuse_existing(meta, args, warnings):
    """幂等重取:确认已持有的设备仍就绪(必要时重新启动)。

    重启已持有的模拟器不过内存闸门:它只是恢复之前的占用,总量不增。
    """
    c = {"tier": 0, "platform": meta["platform"], "kind": meta["kind"],
         "key": meta["device_key"], "name": meta.get("name"),
         "device_id": meta.get("device_id"), "needs_boot": False}
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
        c["device_id"] = boot_avd(meta["name"], args.headless, timeout_for(args, "android"))
        update_lock(c["key"], device_id=c["device_id"], booted_by_allocator=True)
        return c
    boot_sim(meta["device_id"], args.headless, timeout_for(args, "ios"))
    return c


def flush_warnings(warnings):
    for w in warnings:
        log(w)


def cmd_acquire(args):
    owner = args.owner or default_owner_pid()
    project = os.path.abspath(args.project or os.getcwd())
    warnings = []
    if args.platform == "ios" and not have_simctl():
        fail(EXIT_ENV_MISSING, "ENV_MISSING",
             "本机没有 xcrun/simctl,无法分配 iOS 设备(iOS 仅支持 macOS + Xcode)")

    # 幂等重取:同 owner + project 的存活锁直接复用,不多占设备
    mine = find_my_lock(owner, project)
    if mine and (not args.device or args.device in (mine.get("device_id"), mine.get("name"))):
        log(f"已持有 {mine['device_key']},幂等复用")
        try:
            c = reuse_existing(mine, args, warnings)
            update_lock(c["key"], acquired_at=now_iso())
            flush_warnings(warnings)
            emit(build_result(c, owner, project,
                              created=mine.get("created_by_allocator", False),
                              booted=mine.get("booted_by_allocator", False), reused=True))
        except BootFailure as e:
            log(f"已持设备恢复失败({e}),释放后重新分配")
            release_lock(mine["device_key"])

    explicit = bool(args.device)
    gate = mem_policy(max_override=args.max_emulators, ignore=args.mem_override)
    mem_blocked = False
    cands = gather_candidates(args.platform,
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

    for c in cands:
        if c["needs_boot"] and gate["enabled"] and gate["blocked"]:
            if explicit:
                log(f"内存闸门告警({gate['reason']}),但按 --device 指定强制继续")
            else:
                if not mem_blocked:
                    log(f"内存闸门:跳过启动停止态模拟器({gate['reason']})")
                mem_blocked = True
                continue
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
                                              timeout_for(args, "android"))
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
        flush_warnings(warnings)
        emit(build_result(c, owner, project, created=False, booted=booted, reused=False))

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

    if args.platform == "any":
        create_order = ["ios", "android"] if have_simctl() else ["android"]
    else:
        create_order = [args.platform]

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
            flush_warnings(warnings)
            emit(build_result(c, owner, project, created=True, booted=True, reused=False))
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
            ok, err = create_avd(name, pkg)
            if not ok:
                fail(EXIT_INTERNAL, "INTERNAL", f"avdmanager create 失败: {err}",
                     hint="若提示许可证未接受: yes | sdkmanager --licenses")
            c = cand(4, "android", "emulator", f"android-avd:{name}", name, None, True)
            try_lock(c["key"], make_meta(c, owner, project, args.ttl, created=True))
            try:
                c["device_id"] = boot_avd(name, args.headless, timeout_for(args, "android"))
            except BootFailure as e:
                release_lock(c["key"])
                fail(EXIT_BOOT_TIMEOUT, "BOOT_TIMEOUT", f"新建 AVD {name} 启动失败: {e}")
            update_lock(c["key"], device_id=c["device_id"], booted_by_allocator=True)
            flush_warnings(warnings)
            emit(build_result(c, owner, project, created=True, booted=True, reused=False))

    platform_hint = ("默认平台是 android;要用 iOS 模拟器传 --platform ios,两端皆可传 --platform any"
                     if args.platform == "android" else None)
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

    def add(key, platform_, kind, device_id, name, dstate):
        devices.append({"key": key, "platform": platform_, "kind": kind,
                        "device_id": device_id, "name": name, "state": dstate,
                        "lock": lock_view(key)})

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
        add(f"android-avd:{avd}", "android", "emulator", serial, avd, "running")
    for avd in sorted(list_avds()):
        if avd not in running_avds:
            add(f"android-avd:{avd}", "android", "emulator", None, avd, "stopped")
    for d in ios_physicals(warnings):
        add(f"ios-device:{d['udid']}", "ios", "physical", d["udid"], d["name"], "connected")
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
    running_vms = len(running_avds) + len(booted)
    memory = {"total_gb": None if total is None else round(total, 1),
              "available_gb": None if avail is None else round(avail, 1),
              "running_vms": running_vms, "max_vms": max_vms,
              "per_vm_gb": MEM_PER_VM_GB, "reserve_gb": MEM_RESERVE_GB,
              "can_start_new_vm": ((max_vms is None or running_vms < max_vms)
                                   and (avail is None
                                        or avail >= MEM_PER_VM_GB + MEM_MIN_FREE_GB))}
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
    a.add_argument("--platform", choices=["android", "ios", "any"], default="android",
                   help="平台(默认 android;Flutter 项目未指明平台时按默认走,两端皆可用 any)")
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
        {"acquire": cmd_acquire, "release": cmd_release,
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
