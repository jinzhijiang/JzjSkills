#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gpt_image.py — eachlabs 上的 GPT Image v2.5 一把梭：提交 → 轮询 → 落地。

用法:
  python3 gpt_image.py generate "<prompt>" [--model flare|sunburst] [--size ...] [...]
  python3 gpt_image.py edit "<prompt>" --image <本地路径|URL> [--image ...] [--mask ...]
  python3 gpt_image.py upload <本地文件>...          # 只上传，打印 public_url
  python3 gpt_image.py status <prediction_id>
  python3 gpt_image.py balance
  python3 gpt_image.py schema [flare|sunburst|<完整 slug>]

为什么要脚本而不是直接 curl:
  - 文生图的分辨率参数叫 size,编辑的叫 image_size。手写 JSON 极易串,串了直接 400。
  - 编辑的 image_urls 必须是**公网可达 URL**,本地图要先走 presign+PUT 传到 each::storage。
    脚本对 --image 自动判断:本地路径就先传,URL 直接用。
  - 预测是异步的,要轮询到终态再去 output 取 URL,再下载成本地文件。
  - 402/429 是余额与并发闸门,不是「再试一次」就能过的,脚本直接把可执行结论打出来。

stdout 只输出机读结果(--json 时是单行 JSON,否则是落地文件路径,一行一个);
人读过程信息全部走 stderr。仅用 python3 标准库。
凭据从环境变量 EACHLABS_API_KEY 读。
"""

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

API_BASE = "https://api.eachlabs.ai/v1"

MODELS = {
    "flare": {
        "text-to-image": "gpt-image-v2-5-flare-text-to-image",
        "edit": "gpt-image-v2-5-flare-edit",
    },
    "sunburst": {
        "text-to-image": "gpt-image-v2-5-sunburst-text-to-image",
        "edit": "gpt-image-v2-5-sunburst-edit",
    },
}

SIZES = [
    "1024x1024", "1536x1024", "1024x1536",
    "2048x2048", "2048x1152",
    "3840x2160", "2160x3840",
    "auto",
]
QUALITIES = ["low", "medium", "high", "xhigh", "max", "auto"]
FORMATS = ["png", "jpeg", "webp"]
BACKGROUNDS = ["opaque", "transparent", "auto"]

TERMINAL_OK = {"success"}
TERMINAL_BAD = {"error", "cancelled", "failed"}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def die(msg, code=1):
    print("错误: " + msg, file=sys.stderr, flush=True)
    sys.exit(code)


def api_key():
    key = os.environ.get("EACHLABS_API_KEY", "").strip()
    if not key:
        die("环境变量 EACHLABS_API_KEY 未设置。在 ~/.zshrc 里 export,或临时 EACHLABS_API_KEY=... 前置。")
    return key


def request(method, url, body=None, headers=None, raw_body=None, timeout=120,
            retries=2):
    """返回 (status, 解析后的 JSON 或 bytes)。不抛 HTTPError,把错误体也带回来。

    `retries` 只对**传输层**失败生效(连接被掐、SSL EOF、DNS、超时),不对 HTTP 状态码生效
    ——HTTPError 是服务端深思熟虑后的回答,重试它没有意义,429 更是越重试越糟。
    实测 api.eachlabs.ai 会不定时掐连接(`SSL: UNEXPECTED_EOF_WHILE_READING`),
    不兜住的话一批图会在中途整个挂掉,而且报错长得很像限流、容易误诊。

    ⚠️ 非幂等的请求(创建预测)必须传 retries=0:连接在服务端已受理后才断的话,
    重试会再建一个预测、再扣一次钱。
    """
    hdrs = dict(headers or {})
    data = None
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
                status = resp.getcode()
            break
        except urllib.error.HTTPError as e:      # 必须排在 URLError 前面:它是其子类
            payload = e.read()
            status = e.code
            break
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            if attempt >= retries:
                die("网络不通: %s（已重试 %d 次）" % (reason, retries))
            wait = 5 * (attempt + 1)
            log("  连接失败(%s),%ds 后重试 %d/%d …" % (reason, wait, attempt + 1, retries))
            time.sleep(wait)
    try:
        return status, json.loads(payload.decode("utf-8"))
    except Exception:
        return status, payload


def auth_headers():
    # 官方文档用 Bearer;X-API-Key 也被接受(老 skill 里那种写法),这里跟官方走。
    return {"Authorization": "Bearer " + api_key()}


def explain_http_error(status, payload, what):
    detail = ""
    if isinstance(payload, dict):
        detail = payload.get("details") or payload.get("error") or payload.get("message") or ""
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, ensure_ascii=False)
    if status == 401:
        return "401 鉴权失败:EACHLABS_API_KEY 无效或已吊销。%s" % detail
    if status == 402:
        return ("402 余额不足:%s\n"
                "  在飞的预测会按预估成本预留额度,等一个跑完或去 eachlabs.ai 充值。" % detail)
    if status == 429:
        return ("429 并发闸门(不是每秒限流):%s\n"
                "  余额 ≤ $10 时固定价模型最多 10 个在飞、计量型 2 个。等一个到终态再提交,"
                "  退避重试本身不解锁。" % detail)
    if status == 400:
        return ("400 入参不合 schema:%s\n"
                "  常见原因:文生图写了 image_size(应为 size)、编辑写了 size(应为 image_size)、"
                "  枚举值拼错、image_urls 不是公网 URL。用 `schema` 子命令对一遍。" % detail)
    return "%s 失败,HTTP %s: %s" % (what, status, detail or payload)


# ---------------------------------------------------------------- storage

def presign(content_type, file_type="image", expires_in_seconds=None):
    body = {"content_type": content_type, "file_type": file_type}
    if expires_in_seconds:
        body["expires_in_seconds"] = int(expires_in_seconds)
    status, payload = request("POST", API_BASE + "/upload/presign", body=body, headers=auth_headers())
    if status != 200:
        die(explain_http_error(status, payload, "申请 presigned URL"))
    return payload


def upload_file(path, expires_in_seconds=None):
    """本地文件 → each::storage,返回 public_url。"""
    if not os.path.isfile(path):
        die("找不到文件: %s" % path)
    size = os.path.getsize(path)
    if size > 100 * 1024 * 1024:
        die("文件 %.1f MB 超过 each::storage 的 100MB 单文件上限: %s" % (size / 1048576.0, path))
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    info = presign(ctype, "image" if ctype.startswith("image/") else "other", expires_in_seconds)
    headers = {"Content-Type": ctype}
    headers.update(info.get("required_headers") or {})
    with open(path, "rb") as f:
        raw = f.read()
    status, payload = request("PUT", info["presigned_url"], raw_body=raw, headers=headers, timeout=300)
    if status not in (200, 201, 204):
        die("上传失败,HTTP %s: %s\n  presigned URL 只活 15 分钟,过期就重新申请。" % (status, payload))
    log("  已上传 %s (%.0f KB) → %s" % (os.path.basename(path), size / 1024.0, info["public_url"]))
    return info["public_url"]


def resolve_image(ref):
    """--image / --mask 的值:URL 原样返回,本地路径先上传。"""
    if ref.startswith("http://") or ref.startswith("https://"):
        if ref.startswith("http://"):
            log("  警告:http:// 输入不一定可达,建议用 https。")
        return ref
    return upload_file(ref)


# ---------------------------------------------------------------- prediction

def create_prediction(slug, payload_input, webhook_url=None):
    body = {"model": slug, "version": "0.0.1", "input": payload_input}
    if webhook_url:
        body["webhook_url"] = webhook_url
    # retries=0:这是唯一非幂等的调用。连接若在服务端已受理后才断,重试就会多建一个
    # 预测、多扣一次钱。宁可失败,并告诉用户先去查一眼有没有已经建上。
    status, payload = request("POST", API_BASE + "/prediction", body=body,
                              headers=auth_headers(), retries=0)
    if status != 200 or not isinstance(payload, dict) or not payload.get("predictionID"):
        die(explain_http_error(status, payload, "创建预测"))
    return payload["predictionID"]


def get_prediction(pid):
    status, payload = request("GET", API_BASE + "/prediction/" + urllib.parse.quote(pid),
                              headers=auth_headers())
    if status != 200:
        die(explain_http_error(status, payload, "查询预测"))
    return payload


def poll(pid, timeout=900, interval=5):
    deadline = time.time() + timeout
    last = None
    while True:
        data = get_prediction(pid)
        st = (data.get("status") or "").lower()
        if st != last:
            log("  [%s] %s" % (datetime.now().strftime("%H:%M:%S"), st or "?"))
            last = st
        if st in TERMINAL_OK:
            return data
        if st in TERMINAL_BAD:
            logs = data.get("logs") or ""
            out = data.get("output")
            die("预测 %s 终态为 %s。\n  logs: %s\n  output: %s" % (pid, st, logs, out))
        if time.time() > deadline:
            die("等待 %ss 仍未出终态(当前 %s)。预测还在跑,稍后用 `status %s` 取结果。"
                % (timeout, st, pid))
        time.sleep(interval)


def output_urls(data):
    out = data.get("output")
    if out is None:
        return []
    if isinstance(out, str):
        return [out]
    if isinstance(out, list):
        urls = []
        for item in out:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                u = item.get("url") or item.get("image_url")
                if u:
                    urls.append(u)
        return urls
    if isinstance(out, dict):
        u = out.get("url") or out.get("image_url")
        return [u] if u else []
    return []


def download(url, out_dir, stem, index, total):
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".png"
    name = "%s%s%s" % (stem, "" if total == 1 else "-%d" % (index + 1), ext)
    dest = os.path.join(out_dir, name)
    # 图已经出来了、钱也已经花了,这一步再挂掉最冤,所以重试。GET 幂等,重试无副作用。
    req = urllib.request.Request(url, headers={"User-Agent": "gpt_image.py"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                blob = resp.read()
            with open(dest, "wb") as f:
                f.write(blob)
            break
        except (urllib.error.URLError, OSError) as e:
            if attempt == 2:
                die("下载 %s 失败: %s（已重试 2 次,图还在 CDN 上,可手动取）" % (url, e))
            log("  下载失败(%s),%ds 后重试 …" % (getattr(e, "reason", e), 5 * (attempt + 1)))
            time.sleep(5 * (attempt + 1))
    log("  落地 %s (%.0f KB)" % (dest, os.path.getsize(dest) / 1024.0))
    return dest


# ---------------------------------------------------------------- input 组装

def common_input(args, size_key):
    """size_key: 文生图是 'size',编辑是 'image_size' —— 这是两个 slug 唯一的参数名差异。"""
    data = {"prompt": args.prompt}
    if args.size:
        data[size_key] = args.size
    if args.quality:
        data["quality"] = args.quality
    if args.format:
        data["output_format"] = args.format
    if args.background:
        data["background"] = args.background
    if args.compression is not None:
        data["output_compression"] = args.compression
    if args.moderation:
        data["moderation"] = args.moderation
    if args.n and args.n != 1:
        data["num_images"] = args.n
    return data


def validate_common(args):
    if args.background == "transparent" and (args.format or "png") == "jpeg":
        die("background=transparent 需要 output_format 为 png 或 webp,jpeg 没有 alpha 通道。")
    if args.compression is not None and (args.format or "png") == "png":
        log("  提示:output_compression 对 png 无效,会被忽略。")
    if args.size and args.size not in SIZES:
        log("  提示:%s 不在 schema 枚举里,按「自定义尺寸」提交。"
            "约束:两边都是 16 的倍数、最长边 ≤3840、宽高比在 1:3 与 3:1 之间、"
            "总像素 655,360–8,294,400。不合就会 400。" % args.size)
    if len(args.prompt) > 32000:
        die("prompt %d 字符,超过 32000 上限。" % len(args.prompt))


def run_and_collect(slug, payload_input, args, stem_prefix):
    log("模型: %s" % slug)
    log("入参: %s" % json.dumps(payload_input, ensure_ascii=False)[:600])
    pid = create_prediction(slug, payload_input, args.webhook)
    log("预测 ID: %s" % pid)
    if args.no_wait:
        result = {"prediction_id": pid, "status": "submitted", "files": []}
        print(json.dumps(result, ensure_ascii=False) if args.json else pid)
        return
    data = poll(pid, timeout=args.timeout, interval=args.interval)
    urls = output_urls(data)
    if not urls:
        die("预测成功但没取到图片 URL,原始 output: %s" % json.dumps(data.get("output"), ensure_ascii=False))
    stem = "%s-%s" % (stem_prefix, datetime.now().strftime("%Y%m%d-%H%M%S"))
    files = [download(u, args.out, stem, i, len(urls)) for i, u in enumerate(urls)]
    metrics = data.get("metrics") or {}
    log("耗时 %.1fs,本次计费 $%s" % (metrics.get("predict_time") or 0, metrics.get("cost")))
    if args.json:
        print(json.dumps({"prediction_id": pid, "status": "success", "urls": urls,
                          "files": files, "metrics": metrics}, ensure_ascii=False))
    else:
        for p in files:
            print(p)


# ---------------------------------------------------------------- 子命令

def cmd_generate(args):
    validate_common(args)
    slug = MODELS[args.model]["text-to-image"]
    run_and_collect(slug, common_input(args, "size"), args, "gpt-image-%s" % args.model)


def cmd_edit(args):
    validate_common(args)
    if len(args.image) > 16:
        die("最多 16 张源图,给了 %d 张。" % len(args.image))
    slug = MODELS[args.model]["edit"]
    payload = common_input(args, "image_size")
    log("解析源图 (%d 张)…" % len(args.image))
    payload["image_urls"] = [resolve_image(x) for x in args.image]
    if args.mask:
        payload["mask_url"] = resolve_image(args.mask)
    run_and_collect(slug, payload, args, "gpt-image-%s-edit" % args.model)


def cmd_upload(args):
    for path in args.files:
        print(upload_file(path, args.expires))


def cmd_status(args):
    data = get_prediction(args.prediction_id)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_balance(args):
    status, payload = request("GET", API_BASE + "/billing/balance", headers=auth_headers())
    if status != 200:
        die(explain_http_error(status, payload, "查询余额"))
    print(json.dumps(payload, ensure_ascii=False))


def cmd_schema(args):
    target = args.target or "flare"
    if target in MODELS:
        slugs = [MODELS[target]["text-to-image"], MODELS[target]["edit"]]
    else:
        slugs = [target]
    for slug in slugs:
        # 这个端点不需要鉴权
        status, payload = request("GET", API_BASE + "/models/" + urllib.parse.quote(slug))
        if status != 200:
            die(explain_http_error(status, payload, "获取 %s 的 schema" % slug))
        print("=" * 60)
        print(slug)
        print(json.dumps(payload.get("request_schema"), ensure_ascii=False, indent=2))
        print("cost: %s" % json.dumps(payload.get("cost"), ensure_ascii=False))


def add_common(p):
    p.add_argument("prompt", help="提示词,最长 32000 字符")
    p.add_argument("--model", choices=sorted(MODELS), default="flare",
                   help="flare=快/日常(默认),sunburst=慢/高保真")
    p.add_argument("--size", help="分辨率。枚举: %s;也可写自定义 WIDTHxHEIGHT" % "/".join(SIZES))
    p.add_argument("--quality", choices=QUALITIES, help="low 草稿 / medium|high 成品 / xhigh|max 极致(更贵更慢)")
    p.add_argument("--format", choices=FORMATS, help="输出格式,默认 png")
    p.add_argument("--background", choices=BACKGROUNDS, help="transparent 需配 png 或 webp")
    p.add_argument("--compression", type=int, help="0-100,仅对 jpeg/webp 有效")
    p.add_argument("--moderation", choices=["low", "auto"], help="默认 low")
    p.add_argument("-n", "--n", type=int, default=1, help="出图张数 1-10")
    p.add_argument("--out", default=".", help="落地目录,默认当前目录")
    p.add_argument("--timeout", type=int, default=900, help="轮询超时秒数,默认 900")
    p.add_argument("--interval", type=int, default=5, help="轮询间隔秒数,默认 5")
    p.add_argument("--no-wait", action="store_true", help="只提交,打印 prediction ID 就退出")
    p.add_argument("--webhook", help="webhook_url,配了仍会轮询,除非同时给 --no-wait")
    p.add_argument("--json", action="store_true", help="stdout 输出单行 JSON")


def main():
    ap = argparse.ArgumentParser(
        prog="gpt_image.py",
        description="eachlabs 上的 GPT Image v2.5:文生图 / 图生图编辑。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="文生图")
    add_common(g)
    g.set_defaults(func=cmd_generate)

    e = sub.add_parser("edit", help="按指令编辑已有图片")
    add_common(e)
    e.add_argument("--image", action="append", required=True, metavar="本地路径|URL",
                   help="源图,可重复,最多 16 张;本地文件会自动上传到 each::storage")
    e.add_argument("--mask", metavar="本地路径|URL",
                   help="可选 inpaint 蒙版:PNG 带 alpha,尺寸与第一张源图一致,全透明处才会被改")
    e.set_defaults(func=cmd_edit)

    u = sub.add_parser("upload", help="只把本地文件传到 each::storage,打印 public_url")
    u.add_argument("files", nargs="+")
    u.add_argument("--expires", type=int, help="保留秒数,默认 180 天,范围 60 – 31536000")
    u.set_defaults(func=cmd_upload)

    s = sub.add_parser("status", help="查一个预测的状态/结果")
    s.add_argument("prediction_id")
    s.set_defaults(func=cmd_status)

    b = sub.add_parser("balance", help="查账户余额")
    b.set_defaults(func=cmd_balance)

    sc = sub.add_parser("schema", help="拉实时 request_schema 与计价")
    sc.add_argument("target", nargs="?", help="flare|sunburst|完整 slug,默认 flare")
    sc.set_defaults(func=cmd_schema)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
