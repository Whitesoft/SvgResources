"""SVG 备选目录本地预览服务器。

基于 http.server，提供：
- 静态文件服务（取代 `python -m http.server`）
- POST /api/pick        把项目根下某个 SVG 拷贝到 Picked/
- POST /api/open-folder 在系统资源管理器中打开 Picked/
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PICKED_DIR = ROOT / "Picked"
HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 65536


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):
        if self.path == "/api/pick":
            self._handle_pick()
        elif self.path == "/api/open-folder":
            self._handle_open_folder()
        else:
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})

    def _handle_pick(self):
        data = self._read_json()
        if not isinstance(data, dict) or not data.get("file"):
            self._send_json(400, {"ok": False, "error": "missing 'file' field"})
            return
        rel = data["file"]
        src = (ROOT / rel).resolve()
        try:
            src.relative_to(ROOT)
        except ValueError:
            self._send_json(400, {"ok": False, "error": "path is outside project root"})
            return
        if not src.is_file():
            self._send_json(404, {"ok": False, "error": "source file not found"})
            return
        try:
            PICKED_DIR.mkdir(exist_ok=True)
            dest = PICKED_DIR / src.name
            shutil.copy2(src, dest)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(200, {"ok": True, "dest": "Picked/" + src.name})

    def _handle_open_folder(self):
        try:
            PICKED_DIR.mkdir(exist_ok=True)
            path = str(PICKED_DIR)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(200, {"ok": True})


def main():
    PICKED_DIR.mkdir(exist_ok=True)
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving {ROOT} at http://{HOST}:{PORT}/")
    print(f"Picked dir: {PICKED_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
