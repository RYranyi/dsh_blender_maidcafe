#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve.py —— 日式女仆咖啡馆 · 本地预览服务器（纯 Python 标准库，零依赖）

为什么需要它：
  index.html 用 ES module + fetch 加载 GLB/HDRI/JSON，
  浏览器的 file:// 协议会因 CORS 拒绝所有 module 与 fetch 请求
  —— 所以「双击 index.html」必然白屏，必须走 http://。

用法（三种任选）：
  1) 双击 启动预览.bat          （Windows 一键，自动选 Python/Node）
  2) python serve.py            （默认端口 8000，自动开浏览器）
  3) python serve.py 8080       （指定端口）
  python serve.py 8080 --no-browser   （不开浏览器）

然后浏览器打开：
  http://127.0.0.1:8000/index.html

自动化验收参数（定格到任意时段/天气）：
  http://127.0.0.1:8000/index.html?debug=1&auto=1&time=21.5&weather=storm
"""
import argparse
import http.server
import mimetypes
import os
import socket
import socketserver
import sys
import threading
import webbrowser
from functools import partial

ROOT = os.path.dirname(os.path.abspath(__file__))

# 补齐 MIME（Windows 注册表里 .glb/.webp/.hdr/.ogg 常常缺失，缺了浏览器会拒收）
EXTRA_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".hdr": "application/octet-stream",
    ".exr": "application/octet-stream",
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}
for _ext, _type in EXTRA_MIME.items():
    mimetypes.add_type(_type.split(";")[0], _ext)


class Handler(http.server.SimpleHTTPRequestHandler):
    """静态文件服务：禁缓存 + 支持 Range（视频/GLB 拖动更稳）。"""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        # 本地调试：改完刷新立刻生效
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in EXTRA_MIME:
            return EXTRA_MIME[ext]
        return super().guess_type(path)

    def log_message(self, fmt, *args):
        # 精简日志：只记 404/5xx，避免刷屏
        try:
            code = int(args[1]) if len(args) > 1 else 200
        except (ValueError, IndexError):
            code = 200
        if code >= 400:
            sys.stderr.write("  [%s] %s\n" % (code, args[0] if args else ""))


def find_free_port(preferred):
    for p in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("找不到可用端口，请手动指定：python serve.py 9000")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("port", nargs="?", type=int, default=8000, help="端口（默认 8000）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--bind", default="127.0.0.1", help="监听地址（默认仅本机）")
    args = ap.parse_args()

    port = find_free_port(args.port)
    url = "http://%s:%d/index.html" % (args.bind, port)
    demo = "http://%s:%d/index.html?debug=1&auto=1&time=21.5&weather=storm" % (args.bind, port)

    os.chdir(ROOT)
    handler = partial(Handler, directory=ROOT)

    print("")
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║   日式女仆咖啡馆 · 本地预览服务器                     ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print("")
    print("   根目录： %s" % ROOT)
    print("   地址：   %s" % url)
    print("")
    print("   直接体验（自动进入 + 夜晚雷阵雨）：")
    print("            %s" % demo)
    print("")
    print("   Ctrl+C 停止服务")
    print("")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    socketserver.TCPServer.allow_reuse_address = True

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    try:
        with Server((args.bind, port), handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。\n")
    except OSError as e:
        print("\n  [错误] 无法启动服务器：%s" % e)
        print("         换个端口试试：python serve.py 8080\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
