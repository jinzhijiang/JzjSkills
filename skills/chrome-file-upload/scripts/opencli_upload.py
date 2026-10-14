#!/usr/bin/env python3
"""把本地文件经 opencli Browser Bridge 分块写进用户主 Chrome 的页面，拼回 File 后注入 <input type=file>。

为什么不用别的路：
  - `opencli browser <s> upload` 靠点击 input 等文件选择框，antd / 隐藏 input 常常不弹
    （报 `Page.fileChooserOpened not received within 5s`）。
  - 本地 HTTP 服务 + 页面 fetch(127.0.0.1) 在主 Chrome 里会被本地网络访问策略直接拒（`Failed to fetch`）。
  这里把文件 base64 后按块塞进 `window.__cfu.buf[key]`，每块一次 `opencli browser <s> eval`，
  字节只走 opencli 自己的通道，不依赖文件选择框，也不碰本地网络权限。

用法：
    # 只写入并校验，文件留在 window.__cfu.files[key]，之后自己注入
    python3 opencli_upload.py --session up --file /abs/app.apk

    # 写入、校验并注入到指定的 file input；--expect-url 防止标签页被回收后写进空白页
    python3 opencli_upload.py --session up --file /abs/app.apk \\
        --expect-url open.lenovomm.com --selector '[data-cfu="apk"]'

    # input 在同源 iframe 里
    python3 opencli_upload.py --session up --file /abs/a.png \\
        --iframe 'iframe#main' --selector '#uploadapk_btn input[type=file]'

    # input 在跨源 iframe 里：先 `opencli browser <s> frames` 拿下标
    python3 opencli_upload.py --session up --file /abs/a.png --frame 1 --selector 'input[type=file]'

输出一行 JSON：size / sha256（本地与页面两侧）/ chunks / 是否注入。任一步失败以非 0 退出。

依赖：python3 标准库 + 已连通的 opencli（`opencli doctor` 里 Extension: connected）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time

DEFAULT_CHUNK = 600_000  # macOS ARG_MAX 约 1MB，单块 base64 留足余量

EXTRA_TYPES = {
    ".apk": "application/vnd.android.package-archive",
    ".aab": "application/octet-stream",
    ".hap": "application/octet-stream",
    ".app": "application/octet-stream",
    ".ipa": "application/octet-stream",
}


def find_opencli() -> str:
    for cand in (os.environ.get("OPENCLI_BIN"), shutil.which("opencli"),
                 os.path.expanduser("~/.npm-global/bin/opencli")):
        if cand and os.path.exists(cand):
            return cand
    sys.exit("opencli not found: install it or set OPENCLI_BIN")


def js_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class Page:
    def __init__(self, opencli: str, session: str, frame: str | None):
        self.base = [opencli, "browser", session, "eval"]
        if frame is not None:
            self.base += ["--frame", str(frame)]

    def eval(self, js: str, timeout: int = 120) -> str:
        r = subprocess.run(self.base + [js], capture_output=True, text=True, timeout=timeout)
        lines = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
        last = lines[-1] if lines else ""
        if r.returncode != 0 or last.startswith("✖") or not lines:
            err = (r.stderr.strip() or r.stdout.strip())[-600:]
            raise RuntimeError(f"opencli eval failed: {err}")
        return last

    def eval_json(self, js: str, timeout: int = 120) -> dict:
        out = self.eval(js, timeout)
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise RuntimeError(f"unexpected eval output: {out[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", required=True, help="opencli browser session name (e.g. up)")
    ap.add_argument("--file", required=True, help="local file path")
    ap.add_argument("--selector", help="CSS of the target input[type=file]; omit to only stage the file")
    ap.add_argument("--iframe", help="CSS of a same-origin iframe that contains the input")
    ap.add_argument("--frame", help="cross-origin iframe index from `opencli browser <s> frames`")
    ap.add_argument("--name", help="file name the page sees (default: basename)")
    ap.add_argument("--type", help="MIME type (default: guessed from extension)")
    ap.add_argument("--key", help="staging key in window.__cfu (default: derived from file name)")
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help="base64 chars per eval")
    ap.add_argument("--expect-url", help="abort unless the session page URL contains this text "
                                         "(guards against a reclaimed tab silently turning into about:blank)")
    args = ap.parse_args()

    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        sys.exit(f"no such file: {path}")
    raw = open(path, "rb").read()
    local_sha = hashlib.sha256(raw).hexdigest()
    name = args.name or os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    mime = args.type or EXTRA_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"
    key = args.key or re.sub(r"[^A-Za-z0-9_-]", "_", name)

    page = Page(find_opencli(), args.session, args.frame)
    data = base64.b64encode(raw).decode()
    chunks = [data[i:i + args.chunk] for i in range(0, len(data), args.chunk)]

    page_url = page.eval("(() => { const g = window.__cfu = window.__cfu || { buf: {}, files: {} }; "
                         f"g.buf[{js_str(key)}] = new Array({len(chunks)}); return location.href; }})()")
    if args.expect_url and args.expect_url not in page_url:
        raise RuntimeError(f"session page is {page_url[:120]!r}, expected it to contain {args.expect_url!r}; "
                           "the tab may have been reclaimed while idle")
    t0 = time.time()
    for i, part in enumerate(chunks):
        out = page.eval(f"(() => {{ window.__cfu.buf[{js_str(key)}][{i}] = \"{part}\"; return '{i}'; }})()")
        if out != str(i):
            raise RuntimeError(f"chunk {i} not acknowledged: {out[:200]}")
    push_s = round(time.time() - t0, 1)

    built = page.eval_json(f"""(async () => {{
      const g = window.__cfu; const parts = g.buf[{js_str(key)}];
      if (!parts || parts.some(p => typeof p !== 'string')) return JSON.stringify({{ error: 'missing chunks' }});
      const bin = atob(parts.join('')); const u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      let sha = null;
      if (window.crypto && crypto.subtle) {{
        sha = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', u8)))
          .map(x => x.toString(16).padStart(2, '0')).join('');
      }}
      g.files[{js_str(key)}] = new File([u8], {js_str(name)}, {{ type: {js_str(mime)}, lastModified: Date.now() }});
      delete g.buf[{js_str(key)}];
      return JSON.stringify({{ size: u8.length, sha256: sha }});
    }})()""", timeout=300)
    if built.get("error"):
        raise RuntimeError(built["error"])
    if built["size"] != len(raw):
        raise RuntimeError(f"size mismatch: page {built['size']} != local {len(raw)}")
    if built["sha256"] is not None and built["sha256"] != local_sha:
        raise RuntimeError(f"sha256 mismatch: page {built['sha256']} != local {local_sha}")

    result = {"page": page_url.split("?")[0], "file": path, "name": name, "type": mime, "key": key, "size": len(raw),
              "sha256": local_sha, "page_sha256_verified": built["sha256"] is not None,
              "chunks": len(chunks), "push_seconds": push_s, "injected": False}

    if args.selector:
        doc = "document"
        realm = "window"
        if args.iframe:
            doc = f"document.querySelector({js_str(args.iframe)}).contentDocument"
            realm = f"document.querySelector({js_str(args.iframe)}).contentWindow"
        # 异步派发 change：上传组件可能在 change 里同步干重活，同步派发会把这次 eval 拖到超时
        inj = page.eval_json(f"""(() => {{
          const d = {doc}; const w = {realm};
          const el = d && d.querySelector({js_str(args.selector)});
          if (!el) return JSON.stringify({{ error: 'selector matched nothing' }});
          if (el.tagName !== 'INPUT' || el.type !== 'file') return JSON.stringify({{ error: 'not input[type=file]', tag: el.tagName }});
          const src = window.__cfu.files[{js_str(key)}];
          const file = new w.File([src], src.name, {{ type: src.type, lastModified: Date.now() }});
          const dt = new w.DataTransfer(); dt.items.add(file);
          el.files = dt.files;
          setTimeout(() => {{
            el.dispatchEvent(new w.Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new w.Event('change', {{ bubbles: true }}));
          }}, 0);
          return JSON.stringify({{ injected: true, accept: el.accept || '' }});
        }})()""")
        if inj.get("error"):
            raise RuntimeError(f"inject failed: {inj}")
        result["injected"] = True

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
