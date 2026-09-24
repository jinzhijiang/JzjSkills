#!/usr/bin/env python3
"""ios-device-wda：用 WebDriverAgent（WDA）让 AI 自己操作 iOS 真机。

一条 `start` 起 WDA 并接管（已在跑就直接接上），之后截图 / 点击 / 滑动 / 输入 / 按键 /
启停 App / 读元素树 / 用文字触发 Siri。坐标一律是「点」（pt），不是截图像素——
screenshot 会打印「小图坐标 × 系数 = 点」的换算系数。

只用 python3 标准库。外部依赖：Xcode（xcodebuild、xcrun devicectl）、libimobiledevice 的 iproxy
（USB 端口转发；没有时退回 WDA 打印的局域网地址）。

配置 ~/.config/ios-device-wda/config.json（team_id / bundle_id / wda_dir / wda_ref）；
每台设备的运行状态与日志在 ~/.cache/ios-device-wda/<udid>/。
完整参数见 references/cli.md，排障见 references/troubleshooting.md。
"""

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

WDA_REPO = "https://github.com/appium/WebDriverAgent.git"
WDA_REF = "v16.12.10"  # 实测过：iPadOS 26.6.1 + Xcode 26.6
DEFAULT_WDA_DIR = "~/Projects/tools/WebDriverAgent"
DEVICE_PORT = 8100
CONFIG_PATH = Path.home() / ".config" / "ios-device-wda" / "config.json"
CACHE_DIR = Path.home() / ".cache" / "ios-device-wda"
CONFIG_KEYS = ("team_id", "bundle_id", "wda_dir", "wda_ref")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_DEVICE = 3
EXIT_NOT_READY = 4
EXIT_WDA_ERROR = 5

SERVER_URL_RE = re.compile(r"ServerURLHere->(http://[^<\s]+)<-ServerURLHere")
TEAM_RE = re.compile(r"DEVELOPMENT_TEAM = ([A-Z0-9]{10});")
RUNNER_FAIL_RE = re.compile(
    r"Testing failed|\*\* TEST (?:EXECUTE )?FAILED \*\*|Code Signing Error|xcodebuild: error|"
    r"Unable to find a destination|requires a provisioning profile|Failed to install"
)


class WdaError(Exception):
    def __init__(self, message, code=EXIT_WDA_ERROR):
        super().__init__(message)
        self.code = code


def say(message=""):
    print(message, flush=True)


def tail(path, lines=20):
    try:
        return "\n".join(Path(path).read_text(errors="ignore").splitlines()[-lines:])
    except OSError:
        return "(读不到日志)"


# ---------------------------------------------------------------- 配置与状态

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_config():
    return load_json(CONFIG_PATH, {})


def device_dir(udid):
    path = CACHE_DIR / udid
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_state(udid):
    return load_json(device_dir(udid) / "state.json", {})


def save_state(udid, state):
    save_json(device_dir(udid) / "state.json", state)


# ---------------------------------------------------------------- 设备

def list_devices():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / "devices.json"
    result = subprocess.run(
        ["xcrun", "devicectl", "list", "devices", "--json-output", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise WdaError("xcrun devicectl list devices 失败：" + (result.stderr or result.stdout).strip()[-300:],
                       EXIT_NO_DEVICE)
    devices = []
    for item in load_json(out, {}).get("result", {}).get("devices", []):
        hardware = item.get("hardwareProperties", {})
        if hardware.get("platform") != "iOS" or hardware.get("reality") != "physical":
            continue
        props, conn = item.get("deviceProperties", {}), item.get("connectionProperties", {})
        devices.append({
            "udid": hardware.get("udid"),
            "name": props.get("name"),
            "model": hardware.get("marketingName") or hardware.get("deviceType"),
            "os": props.get("osVersionNumber"),
            "developer_mode": props.get("developerModeStatus"),
            "paired": conn.get("pairingState"),
            "tunnel": conn.get("tunnelState"),
            "transport": conn.get("transportType"),
        })
    return devices


def is_reachable_device(device):
    return device["tunnel"] == "connected" or device["transport"] in ("wired", "localNetwork")


def attached_udids():
    """本机状态里 WDA 仍就绪的设备（动作类命令走这条快路，省掉每次 1–2 秒的 devicectl）。"""
    udids = []
    for state_file in CACHE_DIR.glob("*/state.json"):
        url = load_json(state_file, {}).get("url")
        if url and wda_status(url, timeout=2):
            udids.append(state_file.parent.name)
    return udids


def pick_udid(args):
    if getattr(args, "udid", None):
        return args.udid
    if os.environ.get("WDA_UDID"):
        return os.environ["WDA_UDID"]
    attached = attached_udids()
    if len(attached) == 1:
        return attached[0]
    candidates = [d for d in list_devices() if is_reachable_device(d)]
    if len(candidates) == 1:
        return candidates[0]["udid"]
    if not candidates:
        raise WdaError("没有连着的 iOS 真机：插线、解锁、在弹窗里信任这台电脑后重试（xcrun devicectl list devices 可查）。",
                       EXIT_NO_DEVICE)
    listing = "\n".join(f"  {d['udid']}  {d['name']}  iOS {d['os']}" for d in candidates)
    raise WdaError("连着多台 iOS 真机，用 --udid 指定一台：\n" + listing, EXIT_USAGE)


# ---------------------------------------------------------------- 签名与 WDA 源码

def detect_team_from_project(start=None, max_depth=4):
    """在当前目录往下找 *.xcodeproj，取出现最多的 DEVELOPMENT_TEAM。"""
    start = Path(start or Path.cwd())
    skip = {"Pods", "node_modules", "build", "DerivedData", ".dart_tool", ".git", "ohos", "android"}
    counts = {}
    for root, dirs, files in os.walk(start):
        depth = len(Path(root).relative_to(start).parts)
        dirs[:] = [] if depth >= max_depth else [d for d in dirs if d not in skip and not d.startswith(".")]
        if root.endswith(".xcodeproj") and "project.pbxproj" in files:
            text = Path(root, "project.pbxproj").read_text(errors="ignore")
            for team in TEAM_RE.findall(text):
                counts[team] = counts.get(team, 0) + 1
    return max(counts, key=counts.get) if counts else None


def resolve_signing(args, config):
    team = (getattr(args, "team", None) or os.environ.get("WDA_TEAM_ID") or config.get("team_id")
            or detect_team_from_project())
    if not team:
        raise WdaError("不知道用哪个开发者团队给 WDA 签名：加 --team <TEAMID>，或 `config set team_id <TEAMID>`"
                       "（当前目录下也没找到带 DEVELOPMENT_TEAM 的 Xcode 工程）。", EXIT_USAGE)
    bundle = (getattr(args, "bundle_id", None) or os.environ.get("WDA_BUNDLE_ID") or config.get("bundle_id")
              or f"com.webdriveragent.{team.lower()}.runner")
    return team, bundle


def wda_dir(config):
    return Path(os.path.expanduser(os.environ.get("WDA_DIR") or config.get("wda_dir") or DEFAULT_WDA_DIR))


def ensure_source(config):
    directory = wda_dir(config)
    if (directory / "WebDriverAgent.xcodeproj").is_dir():
        return directory
    ref = config.get("wda_ref", WDA_REF)
    say(f"WDA 源码不在 {directory}，克隆 {WDA_REPO} @ {ref} …")
    directory.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "clone", "--depth", "1", "--branch", ref, WDA_REPO, str(directory)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise WdaError("克隆 WDA 失败：" + result.stderr.strip()[-400:])
    return directory


def build_signature(directory, team, bundle):
    xcode = " ".join(subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True).stdout.split())
    ref = subprocess.run(["git", "-C", str(directory), "describe", "--tags", "--always"],
                         capture_output=True, text=True).stdout.strip()
    return f"{xcode}|{ref}|{team}|{bundle}"


def find_xctestrun(directory):
    runs = sorted((directory / "DerivedData" / "Build" / "Products").glob("*.xctestrun"),
                  key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def usable_xctestrun(directory, team, bundle):
    """编译产物还能直接用吗：Xcode 版本、WDA 版本、团队、bundle id 任一变了都要重编。"""
    run = find_xctestrun(directory)
    marker = directory / ".wda-build-signature"
    if run and marker.exists() and marker.read_text().strip() == build_signature(directory, team, bundle):
        return run
    return None


def xcodebuild_args(directory, udid, team, bundle):
    return ["-project", str(directory / "WebDriverAgent.xcodeproj"), "-scheme", "WebDriverAgentRunner",
            "-destination", f"id={udid}", "-derivedDataPath", str(directory / "DerivedData"),
            "-allowProvisioningUpdates", f"DEVELOPMENT_TEAM={team}",
            f"PRODUCT_BUNDLE_IDENTIFIER={bundle}", "CODE_SIGN_STYLE=Automatic"]


def build_runner(directory, udid, team, bundle, log_path):
    say(f"编译 WDA（首次约 1–3 分钟）… 日志 {log_path}")
    with open(log_path, "w") as log:
        result = subprocess.run(["xcodebuild", "build-for-testing"] + xcodebuild_args(directory, udid, team, bundle),
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise WdaError("WDA 编译失败，日志末尾：\n" + tail(log_path, 25))
    run = find_xctestrun(directory)
    if not run:
        raise WdaError("编译成功却没找到 .xctestrun：" + str(directory / "DerivedData" / "Build" / "Products"))
    (directory / ".wda-build-signature").write_text(build_signature(directory, team, bundle))
    return run


def launch_runner(xctestrun, udid, log_path):
    """后台起 WDA（新会话组，工具调用结束后照样活着）。返回 pid（= 进程组 id）。"""
    log = open(log_path, "w")
    process = subprocess.Popen(
        ["xcodebuild", "test-without-building", "-xctestrun", str(xctestrun), "-destination", f"id={udid}"],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
    )
    return process.pid


# ---------------------------------------------------------------- 进程与端口

def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_group(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port(preferred=None):
    for port in ([preferred] if preferred else []) + list(range(8100, 8200)):
        if port_free(port):
            return port
    raise WdaError("127.0.0.1:8100–8199 没有空闲端口")


def start_iproxy(udid, port, log_path):
    if not shutil.which("iproxy"):
        return None
    process = subprocess.Popen(["iproxy", f"{port}:{DEVICE_PORT}", "-u", udid],
                               stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, start_new_session=True)
    return process.pid


# ---------------------------------------------------------------- HTTP

def http(method, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raw = error.read()
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {"value": {"error": "non-json response", "message": raw[:200].decode(errors="ignore")}}


def is_error(payload):
    value = payload.get("value") if isinstance(payload, dict) else None
    return isinstance(value, dict) and "error" in value


def error_text(payload):
    value = payload.get("value", {})
    return f"{value.get('error')}: {str(value.get('message', '')).strip()[:300]}"


def wda_status(url, timeout=3):
    try:
        value = http("GET", url + "/status", timeout=timeout).get("value", {})
        return value if value.get("ready") else None
    except (OSError, ValueError):
        return None


def wait_ready(url, timeout, runner_pid=None, runner_log=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = wda_status(url)
        if status:
            return status
        if runner_pid and not pid_alive(runner_pid):
            raise WdaError("WDA 进程已退出，日志末尾：\n" + tail(runner_log, 30), EXIT_NOT_READY)
        if runner_log and RUNNER_FAIL_RE.search(tail(runner_log, 60)):
            raise WdaError("WDA 启动失败，日志末尾：\n" + tail(runner_log, 30), EXIT_NOT_READY)
        time.sleep(1)
    hint = ("\n日志末尾：\n" + tail(runner_log, 20)) if runner_log else ""
    raise WdaError(f"{timeout}s 内 WDA 没有就绪（{url}/status）" + hint, EXIT_NOT_READY)


def lan_url_from_log(log_path):
    found = SERVER_URL_RE.findall(tail(log_path, 4000)) if log_path else []
    return found[-1] if found else None


def connect(udid, state, timeout, runner_pid=None, runner_log=None):
    """确保 state['url'] 指向一个就绪的 WDA。优先 USB（iproxy），没有 iproxy 时退回局域网地址。"""
    if state.get("url") and wda_status(state["url"]):
        return state["url"]
    ddir = device_dir(udid)
    if shutil.which("iproxy"):
        port = state.get("port")
        if not (port and pid_alive(state.get("iproxy_pid"))):
            port = pick_port(port)
            state["iproxy_pid"] = start_iproxy(udid, port, ddir / "iproxy.log")
            state["port"] = port
        url = f"http://127.0.0.1:{port}"
    else:
        url = lan_url_from_log(runner_log or state.get("runner_log"))
        if not url:
            raise WdaError("没有 iproxy（brew install libimobiledevice），日志里也没有 WDA 的局域网地址。", EXIT_NOT_READY)
    state["url"] = url
    save_state(udid, state)
    wait_ready(url, timeout, runner_pid, runner_log)
    return url


# ---------------------------------------------------------------- WDA 客户端

class Wda:
    def __init__(self, udid):
        self.udid = udid
        self.state = load_state(udid)
        self.url = self.state.get("url")
        if not self.url or not wda_status(self.url):
            raise WdaError("还没接上 WDA（或它已经停了）：先跑 `wda.py start`。", EXIT_NOT_READY)

    def new_session(self):
        payload = http("POST", self.url + "/session", {"capabilities": {"alwaysMatch": {}}}, timeout=90)
        session_id = payload.get("sessionId") or (payload.get("value") or {}).get("sessionId")
        if not session_id:
            raise WdaError("建会话失败：" + json.dumps(payload, ensure_ascii=False)[:300])
        self.state["session_id"] = session_id
        save_state(self.udid, self.state)
        return session_id

    def call(self, method, path, body=None, session=True, timeout=60):
        for attempt in range(2):
            prefix = ""
            if session:
                prefix = "/session/" + (self.state.get("session_id") or self.new_session())
            payload = http(method, self.url + prefix + path, body, timeout)
            if not is_error(payload):
                return payload.get("value")
            if session and attempt == 0 and "invalid session" in error_text(payload).lower():
                self.new_session()
                continue
            raise WdaError(f"{method} {path} 失败 → {error_text(payload)}")
        return None


def png_size(path):
    with open(path, "rb") as handle:
        header = handle.read(24)
    return struct.unpack(">II", header[16:24])


def take_screenshot(wda, out=None, max_side=1200):
    shots = device_dir(wda.udid) / "shots"
    shots.mkdir(exist_ok=True)
    out = Path(out) if out else shots / (datetime.now().strftime("%H%M%S_%f")[:-3] + ".png")
    out.write_bytes(base64.b64decode(wda.call("GET", "/screenshot", session=False, timeout=60)))
    px_w, px_h = png_size(out)
    size = wda.call("GET", "/window/size")
    scale = px_w / size["width"]
    say(f"截图 {out}  {px_w}×{px_h}px = {size['width']:g}×{size['height']:g}pt（缩放 {scale:g}）")
    if abs(px_h / size["height"] - scale) > 0.05:
        say("  注意：宽高缩放不一致，截图方向可能与当前界面不同")
    if max_side and max(px_w, px_h) > max_side:
        small = out.with_name(out.stem + f"_s{max_side}.png")
        subprocess.run(["sips", "-Z", str(max_side), str(out), "--out", str(small)], capture_output=True)
        factor = (px_w / png_size(small)[0]) / scale
        say(f"小图 {small}  —— 小图坐标 × {factor:.3f} = 点坐标（tap 用点）")
        return small
    say(f"截图坐标 ÷ {scale:g} = 点坐标（tap 用点）")
    return out


def then_shot(wda, args):
    delay = getattr(args, "then_shot", None)
    if delay is not None:
        time.sleep(delay)
        take_screenshot(wda, max_side=args.max)


def touch(x, y, hold_ms):
    return {"actions": [{
        "type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"},
        "actions": [
            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
            {"type": "pointerDown", "button": 0},
            {"type": "pause", "duration": hold_ms},
            {"type": "pointerUp", "button": 0},
        ],
    }]}


def swipe_actions(x1, y1, x2, y2, duration_ms):
    return {"actions": [{
        "type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"},
        "actions": [
            {"type": "pointerMove", "duration": 0, "x": x1, "y": y1},
            {"type": "pointerDown", "button": 0},
            {"type": "pointerMove", "duration": duration_ms, "x": x2, "y": y2},
            {"type": "pointerUp", "button": 0},
        ],
    }]}


APP_ALIASES = {"springboard": "com.apple.springboard", "home": "com.apple.springboard"}


class ActiveApp:
    """临时指定 WDA 查询元素时的「活动 App」，结束后恢复自动检测。

    主屏 / 小组件 / 系统菜单要用 springboard：iPadOS 26 上 WDA 的自动检测常把 Dock 的
    DockFolderViewService 当成活动 App，于是主屏上的东西一个都查不到。
    """

    def __init__(self, wda, app):
        self.wda = wda
        self.app = APP_ALIASES.get(app, app) if app else None

    def __enter__(self):
        if self.app:
            self.wda.call("POST", "/appium/settings", {"settings": {"defaultActiveApplication": self.app}})
        return self

    def __exit__(self, *exc):
        if self.app:
            self.wda.call("POST", "/appium/settings", {"settings": {"defaultActiveApplication": "auto"}})
        return False


def locator(args):
    if args.label is not None:
        return {"using": "predicate string", "value": f"label == {json.dumps(args.label, ensure_ascii=False)}"}
    if args.id is not None:
        return {"using": "accessibility id", "value": args.id}
    return {"using": "predicate string", "value": args.predicate}


def find_elements(wda, args):
    found = wda.call("POST", "/elements", locator(args)) or []
    elements = []
    for item in found:
        element_id = item.get("ELEMENT") or next(iter(item.values()))
        rect = wda.call("GET", f"/element/{element_id}/rect")
        label = wda.call("GET", f"/element/{element_id}/attribute/label")
        kind = wda.call("GET", f"/element/{element_id}/name")
        elements.append({"id": element_id, "type": kind, "label": label, "rect": rect})
    return elements


# ---------------------------------------------------------------- 子命令

def cmd_devices(args):
    for device in list_devices():
        mark = "✓" if is_reachable_device(device) else " "
        say(f"{mark} {device['udid']}  {device['name']}  {device['model']}  iOS {device['os']}  "
            f"开发者模式={device['developer_mode']}  连接={device['transport']}/{device['tunnel']}")


def cmd_start(args):
    udid = pick_udid(args)
    config, state = load_config(), load_state(udid)
    try:
        connect(udid, state, timeout=5)
        say(f"WDA 已在运行，已接上：{state['url']}（设备 {udid}）")
    except WdaError:
        team, bundle = resolve_signing(args, config)
        directory = ensure_source(config)
        ddir = device_dir(udid)
        xctestrun = None if args.rebuild else usable_xctestrun(directory, team, bundle)
        if not xctestrun:
            xctestrun = build_runner(directory, udid, team, bundle, ddir / "build.log")
        runner_log = ddir / "xcodebuild.log"
        state.update(runner_pid=launch_runner(xctestrun, udid, runner_log), runner_log=str(runner_log),
                     team_id=team, bundle_id=bundle, started_at=datetime.now().isoformat(timespec="seconds"),
                     session_id=None)
        save_state(udid, state)
        say(f"已后台启动 WDA（pid {state['runner_pid']}），等它就绪…")
        connect(udid, state, timeout=args.timeout, runner_pid=state["runner_pid"], runner_log=runner_log)
    wda = Wda(udid)
    wda.new_session()
    size = wda.call("GET", "/window/size")
    say(f"就绪：{wda.url}  会话 {wda.state['session_id']}  屏幕 {size['width']:g}×{size['height']:g}pt")


def cmd_attach(args):
    udid = pick_udid(args)
    state = load_state(udid)
    runner_log = state.get("runner_log") or str(device_dir(udid) / "xcodebuild.log")
    connect(udid, state, timeout=args.timeout, runner_log=runner_log if Path(runner_log).exists() else None)
    wda = Wda(udid)
    wda.new_session()
    size = wda.call("GET", "/window/size")
    say(f"已接上：{wda.url}  会话 {wda.state['session_id']}  屏幕 {size['width']:g}×{size['height']:g}pt")


def cmd_launch_cmd(args):
    """打印启动 WDA 的命令，给用户在自己终端里跑（auto 模式拦下后台启动时用）。"""
    udid = pick_udid(args)
    config = load_config()
    team, bundle = resolve_signing(args, config)
    directory = wda_dir(config)
    log_path = device_dir(udid) / "xcodebuild.log"
    xctestrun = usable_xctestrun(directory, team, bundle) if directory.exists() else None
    if xctestrun:
        cmd = ["xcodebuild", "test-without-building", "-xctestrun", str(xctestrun), "-destination", f"id={udid}"]
        line = shlex.join(cmd)
    else:
        prefix = "" if directory.exists() else (
            f"git clone --depth 1 --branch {config.get('wda_ref', WDA_REF)} {WDA_REPO} {shlex.quote(str(directory))} && ")
        line = prefix + f"cd {shlex.quote(str(directory))} && " + shlex.join(
            ["xcodebuild", "test"] + xcodebuild_args(directory, udid, team, bundle))
    say(f"{line} 2>&1 | tee {shlex.quote(str(log_path))}")


def cmd_status(args):
    udid = pick_udid(args)
    state = load_state(udid)
    url = state.get("url")
    status = wda_status(url) if url else None
    say(f"设备 {udid}")
    say(f"  WDA：{'就绪 ' + url if status else '未就绪'}")
    if status:
        say(f"  WDA {status.get('build', {}).get('version')} · iOS {status.get('os', {}).get('version')}"
            f" · 设备局域网 IP {status.get('ios', {}).get('ip')}")
    for key in ("runner_pid", "iproxy_pid"):
        if state.get(key):
            say(f"  {key}={state[key]}（{'存活' if pid_alive(state[key]) else '已退出'}）")
    if state.get("session_id"):
        say(f"  会话 {state['session_id']}")
    return EXIT_OK if status else EXIT_NOT_READY


def cmd_stop(args):
    udid = pick_udid(args)
    state = load_state(udid)
    if state.get("runner_pid") and pid_alive(state["runner_pid"]):
        kill_group(state["runner_pid"])
        say(f"已停 WDA（pid {state['runner_pid']}）")
    elif state.get("url") and wda_status(state["url"]):
        say("WDA 不是本脚本启动的（没有 pid）：去启动它的终端按 Ctrl+C。")
    if state.get("iproxy_pid") and pid_alive(state["iproxy_pid"]):
        kill_group(state["iproxy_pid"])
        say(f"已停端口转发（pid {state['iproxy_pid']}）")
    if args.uninstall:
        bundle = (state.get("bundle_id") or resolve_signing(args, load_config())[1]) + ".xctrunner"
        result = subprocess.run(["xcrun", "devicectl", "device", "uninstall", "app", "--device", udid, bundle],
                                capture_output=True, text=True)
        say(("已卸载 " if result.returncode == 0 else "卸载失败 ") + bundle)
    save_state(udid, {})


def cmd_doctor(args):
    ok = True
    xcode = subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True)
    say(("✓ " if xcode.returncode == 0 else "✗ ") + (" ".join(xcode.stdout.split()) or "没有 Xcode"))
    ok &= xcode.returncode == 0
    say(("✓ iproxy " + shutil.which("iproxy")) if shutil.which("iproxy")
        else "✗ 没有 iproxy：brew install libimobiledevice（没有也能跑，但只能走局域网）")
    try:
        devices = list_devices()
    except WdaError as error:
        devices, ok = [], False
        say("✗ " + str(error))
    for device in devices:
        good = is_reachable_device(device) and device["developer_mode"] == "enabled"
        say(f"{'✓' if good else '✗'} {device['name']} {device['udid']} iOS {device['os']} "
            f"开发者模式={device['developer_mode']} 连接={device['transport']}/{device['tunnel']}")
    if not devices:
        say("✗ 没有 iOS 真机")
    config = load_config()
    directory = wda_dir(config)
    say(("✓ " if (directory / "WebDriverAgent.xcodeproj").exists() else "✗ ") + f"WDA 源码 {directory}"
        + ("" if directory.exists() else "（start 时自动克隆）"))
    try:
        team, bundle = resolve_signing(args, config)
        say(f"✓ 签名 团队 {team}  bundle id {bundle}")
        if directory.exists():
            run = usable_xctestrun(directory, team, bundle)
            say(("✓ 可免编译启动 " + run.name) if run else "· 首次 start 会先编译（约 1–3 分钟）")
    except WdaError as error:
        ok = False
        say("✗ " + str(error))
    say(f"· 配置 {CONFIG_PATH}{'' if CONFIG_PATH.exists() else '（不存在，用默认/自动识别）'}")
    return EXIT_OK if ok else EXIT_USAGE


def cmd_config(args):
    config = load_config()
    if args.action == "set":
        if args.key not in CONFIG_KEYS:
            raise WdaError(f"只认这些键：{', '.join(CONFIG_KEYS)}", EXIT_USAGE)
        config[args.key] = args.value
        save_json(CONFIG_PATH, config)
    say(json.dumps(config, ensure_ascii=False, indent=2))


def with_wda(func):
    def runner(args):
        wda = Wda(pick_udid(args))
        result = func(wda, args)
        then_shot(wda, args)
        return result
    return runner


@with_wda
def cmd_screenshot(wda, args):
    take_screenshot(wda, args.out, args.max)


@with_wda
def cmd_tap(wda, args):
    wda.call("POST", "/actions", touch(args.x, args.y, 80))


@with_wda
def cmd_hold(wda, args):
    wda.call("POST", "/actions", touch(args.x, args.y, args.ms))


@with_wda
def cmd_swipe(wda, args):
    wda.call("POST", "/actions", swipe_actions(args.x1, args.y1, args.x2, args.y2, args.ms))


@with_wda
def cmd_type(wda, args):
    wda.call("POST", "/wda/keys", {"value": list(args.text)})


@with_wda
def cmd_press(wda, args):
    if args.button == "home":
        wda.call("POST", "/wda/homescreen", {}, session=False)
    else:
        wda.call("POST", "/wda/pressButton", {"name": args.button})


@with_wda
def cmd_siri(wda, args):
    wda.call("POST", "/wda/siri/activate", {"text": args.text}, timeout=90)
    say("已把文字交给 Siri；回应卡片约 5 秒后自动收起，用 --then-shot 2~4 截它")


@with_wda
def cmd_app(wda, args):
    endpoint = {"launch": "/wda/apps/launch", "activate": "/wda/apps/activate",
                "terminate": "/wda/apps/terminate", "state": "/wda/apps/state"}[args.action]
    value = wda.call("POST", endpoint, {"bundleId": args.bundle_id}, timeout=90)
    if args.action == "state":
        names = {0: "未知", 1: "未运行", 2: "后台挂起", 3: "后台运行", 4: "前台运行"}
        say(f"{args.bundle_id}：{names.get(value, value)}")


@with_wda
def cmd_source(wda, args):
    with ActiveApp(wda, args.app):
        value = wda.call("GET", f"/source?format={args.format}", timeout=120)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
        say(f"元素树已写入 {args.out}（{len(text)} 字符）")
    else:
        say(text)


@with_wda
def cmd_find(wda, args):
    with ActiveApp(wda, args.app):
        elements = find_elements(wda, args)
    if not elements:
        say("没找到" + ("" if args.app else "（在主屏 / 系统界面上？加 --app springboard 再试）"))
    for element in elements:
        r = element["rect"]
        say(f"{element['type']} | {element['label']} | x={r['x']:g} y={r['y']:g} w={r['width']:g} h={r['height']:g}"
            f" | 中心 ({r['x'] + r['width'] / 2:g}, {r['y'] + r['height'] / 2:g}) | id={element['id']}")


@with_wda
def cmd_click(wda, args):
    with ActiveApp(wda, args.app):
        found = wda.call("POST", "/elements", locator(args)) or []
        if len(found) <= args.index:
            hint = "" if args.app else "；在主屏 / 系统界面上就加 --app springboard"
            raise WdaError(f"没找到第 {args.index} 个匹配元素（共 {len(found)} 个）{hint}", EXIT_WDA_ERROR)
        if len(found) > 1:
            say(f"注意：匹配到 {len(found)} 个，点第 {args.index} 个；被遮住的同名控件也会被匹配，拿不准就用截图坐标 tap")
        element_id = found[args.index].get("ELEMENT") or next(iter(found[args.index].values()))
        wda.call("POST", f"/element/{element_id}/click", {})


@with_wda
def cmd_alert(wda, args):
    if args.action == "text":
        say(str(wda.call("GET", "/alert/text")))
    else:
        wda.call("POST", f"/alert/{args.action}", {})


@with_wda
def cmd_window(wda, args):
    size = wda.call("GET", "/window/size")
    say(f"{size['width']:g}×{size['height']:g}pt  方向 {wda.call('GET', '/orientation')}")


# ---------------------------------------------------------------- 入口

def add_after(parser):
    parser.add_argument("--then-shot", type=float, metavar="秒", help="动作后等几秒再截图（页面动画、Siri 回应）")
    parser.add_argument("--max", type=int, default=1200, help="另存一张最长边不超过该像素的小图，默认 1200；0 = 不缩")


def add_app(parser):
    parser.add_argument("--app", help="在哪个 App 里查元素（bundle id）；主屏、小组件、系统菜单用 springboard")


def add_locator(parser):
    add_app(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--label", help="按无障碍 label 精确匹配")
    group.add_argument("--id", help="按 accessibility id")
    group.add_argument("--predicate", help="NSPredicate，例：\"type == 'XCUIElementTypeButton' AND label CONTAINS '添加'\"")


def build_parser():
    parser = argparse.ArgumentParser(prog="wda.py", description="用 WebDriverAgent 操作 iOS 真机（坐标单位：点）")
    parser.add_argument("--udid", help="设备 UDID；只连着一台时可省略（也认环境变量 WDA_UDID）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出 iOS 真机").set_defaults(func=cmd_devices)
    sub.add_parser("doctor", help="检查前置条件").set_defaults(func=cmd_doctor)

    p = sub.add_parser("start", help="起 WDA 并接管（已在跑就直接接上）")
    p.add_argument("--team", help="开发者团队 ID（默认：配置 → 当前目录 Xcode 工程）")
    p.add_argument("--bundle-id", help="WDA 的 bundle id（默认：配置 → com.webdriveragent.<team>.runner）")
    p.add_argument("--rebuild", action="store_true", help="强制重新编译")
    p.add_argument("--timeout", type=int, default=120, help="等 WDA 就绪的秒数，默认 120")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("attach", help="接上已在运行的 WDA（例如用户在自己终端里启动的）")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("launch-cmd", help="打印启动 WDA 的命令（给用户在终端跑）")
    p.add_argument("--team")
    p.add_argument("--bundle-id")
    p.set_defaults(func=cmd_launch_cmd)

    sub.add_parser("status", help="WDA 与端口转发的状态").set_defaults(func=cmd_status)

    p = sub.add_parser("stop", help="停掉本脚本启动的 WDA 与端口转发")
    p.add_argument("--uninstall", action="store_true", help="顺带从设备上卸载 WebDriverAgentRunner")
    p.add_argument("--team")
    p.add_argument("--bundle-id")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("config", help="查看/设置配置（team_id / bundle_id / wda_dir / wda_ref）")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("screenshot", help="截图（另存小图并打印换算系数）")
    p.add_argument("--out", help="原图保存路径")
    p.add_argument("--max", type=int, default=1200)
    p.set_defaults(func=cmd_screenshot, then_shot=None)

    for name, func, help_text in (("tap", cmd_tap, "点一下"), ("hold", cmd_hold, "长按")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("x", type=float)
        p.add_argument("y", type=float)
        if name == "hold":
            p.add_argument("--ms", type=int, default=1200, help="按住毫秒数，默认 1200")
        add_after(p)
        p.set_defaults(func=func)

    p = sub.add_parser("swipe", help="滑动")
    for coord in ("x1", "y1", "x2", "y2"):
        p.add_argument(coord, type=float)
    p.add_argument("--ms", type=int, default=400, help="滑动时长，默认 400")
    add_after(p)
    p.set_defaults(func=cmd_swipe)

    p = sub.add_parser("type", help="往当前焦点输入文字（中文输入法下打字母会进拼音候选）")
    p.add_argument("text")
    add_after(p)
    p.set_defaults(func=cmd_type)

    p = sub.add_parser("press", help="按键")
    p.add_argument("button", choices=["home", "volumeUp", "volumeDown"])
    add_after(p)
    p.set_defaults(func=cmd_press)

    p = sub.add_parser("siri", help="用文字触发 Siri（可直接触发 App 快捷指令短语）")
    p.add_argument("text")
    add_after(p)
    p.set_defaults(func=cmd_siri)

    p = sub.add_parser("app", help="启动 / 切前台 / 结束 / 查状态")
    p.add_argument("action", choices=["launch", "activate", "terminate", "state"])
    p.add_argument("bundle_id")
    add_after(p)
    p.set_defaults(func=cmd_app)

    p = sub.add_parser("source", help="导出元素树")
    p.add_argument("--format", choices=["description", "xml", "json"], default="description")
    p.add_argument("--out")
    add_app(p)
    p.set_defaults(func=cmd_source, then_shot=None, max=1200)

    p = sub.add_parser("find", help="查元素并打印位置（点）")
    add_locator(p)
    p.set_defaults(func=cmd_find, then_shot=None, max=1200)

    p = sub.add_parser("click", help="点匹配到的元素")
    add_locator(p)
    p.add_argument("--index", type=int, default=0)
    add_after(p)
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("alert", help="系统弹窗：读文字 / 接受 / 拒绝")
    p.add_argument("action", choices=["text", "accept", "dismiss"])
    add_after(p)
    p.set_defaults(func=cmd_alert)

    p = sub.add_parser("window", help="屏幕尺寸（点）与方向")
    p.set_defaults(func=cmd_window, then_shot=None, max=1200)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
        return result if isinstance(result, int) else EXIT_OK
    except WdaError as error:
        print("✗ " + str(error), file=sys.stderr, flush=True)
        return error.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
