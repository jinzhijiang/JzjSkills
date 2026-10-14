#!/usr/bin/env python3
"""带 CORS 的本地静态文件服务，专供浏览器页面拉取本地文件后注入 <input type=file>。

只绑 127.0.0.1，只服务 --root 指定的目录。

    python3 cors_server.py 8912 --root /path/to/upload

关键响应头：
  Access-Control-Allow-Origin: *          跨源读取
  Access-Control-Allow-Private-Network    Chrome PNA：HTTPS 页面访问 127.0.0.1 需要

依赖：python3 标准库。
"""

import argparse
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def build_handler(root: str):
    class CORSHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            # Chrome Private Network Access：HTTPS 页面 → 127.0.0.1 属跨私有网络请求，
            # 缺这个头请求会被挡在浏览器内，服务端连日志都看不到。
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "86400")
            super().end_headers()

        def do_OPTIONS(self):  # noqa: N802 (BaseHTTPRequestHandler 命名约定)
            self.send_response(204)
            self.end_headers()

        def log_message(self, fmt, *args):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return CORSHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=8912, help="监听端口，默认 8912")
    parser.add_argument(
        "--root",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload"),
        help="要服务的目录，默认脚本同级的 upload/",
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"目录不存在：{root}", file=sys.stderr)
        return 1

    handler = build_handler(root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving {root} at http://127.0.0.1:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
