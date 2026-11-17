from __future__ import annotations

import ctypes
import json
import mimetypes
import os
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from PIL import Image

ROOT = (Path.home() / "Downloads" / "Photos").resolve()
HERE = Path(__file__).resolve().parent


def capture_date(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            tags = [exif]
            try:
                tags.append(exif.get_ifd(34665))
            except (KeyError, TypeError):
                pass
            for tag_set in tags:
                value = tag_set.get(36867) or tag_set.get(36868)
                if value:
                    value = value.decode("ascii", "replace") if isinstance(value, bytes) else str(value)
                    return datetime.strptime(value[:10], "%Y:%m:%d").date().isoformat()
    except (OSError, ValueError, TypeError, KeyError, SyntaxError):
        pass
    return None


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def recycle(path: Path) -> None:
    # Send to Recycle Bin so an accidental deletion can be restored.
    operation = SHFILEOPSTRUCTW(None, 3, str(path) + "\0\0", None, 0x40 | 0x10 | 0x4, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result or operation.fAnyOperationsAborted:
        raise OSError(f"Windows file operation failed ({result})")


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = (HERE / "photo-review.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/files":
            files = []
            for path in ROOT.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    stat = path.stat()
                    files.append({
                        "path": path.relative_to(ROOT).as_posix(),
                        "name": path.name,
                        "type": path.suffix[1:].upper() or "FILE",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "date": capture_date(path),
                        "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    })
            files.sort(key=lambda item: item["path"].casefold())
            self.send_json(files)
        elif parsed.path == "/file":
            relative = parse_qs(parsed.query).get("path", [""])[0]
            try:
                path = (ROOT / relative).resolve(strict=True)
                if not path.is_relative_to(ROOT) or not path.is_file():
                    raise ValueError()
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError):
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/delete":
            self.send_error(404)
            return
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            selected = payload["paths"]
            if not isinstance(selected, list) or not selected or any(not isinstance(p, str) for p in selected):
                raise ValueError("Select at least one file.")
            removed, failed = [], []
            for relative in dict.fromkeys(selected):
                try:
                    candidate = ROOT / relative
                    if candidate.is_symlink():
                        raise ValueError("Symbolic links are not supported.")
                    path = candidate.resolve(strict=True)
                    if not path.is_relative_to(ROOT) or not path.is_file():
                        raise ValueError("Not a regular file in the photo folder.")
                    recycle(path)
                    removed.append(relative)
                except (OSError, ValueError) as error:
                    failed.append({"path": relative, "error": str(error)})
            self.send_json({"removed": removed, "failed": failed}, 207 if failed else 200)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.send_json({"error": str(error)}, 400)

    def log_message(self, *_args: object) -> None:
        pass


if __name__ == "__main__":
    if not ROOT.is_dir():
        raise SystemExit(f"Folder not found: {ROOT}")
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    threading.Timer(0.8, lambda: webbrowser.open("http://127.0.0.1:8765/")).start()
    print(f"Reviewing {ROOT}\nOpen http://127.0.0.1:8765/ — press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
