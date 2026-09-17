#!/usr/bin/env python3
"""设计原型本地服务：禁缓存（Cache-Control: no-store），保证手机打开即最新代码。
用法：python3 serve.py [port]（默认 8123，服务本目录）"""
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    ThreadingHTTPServer(("0.0.0.0", port), NoCacheHandler).serve_forever()
