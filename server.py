#!/usr/bin/env python3
"""Projector — one-click screen sharing for workshops via HLS streaming."""

import http.server
import json
import os
import re
import atexit
import signal
import socket
import subprocess
import sys
import threading
import time
import shutil

CONTROL_PORT = 8000
HLS_DIR = "/tmp/projector-stream"
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

_ffmpeg_proc = None


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def list_screens():
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    screens = []
    for line in result.stderr.splitlines():
        m = re.search(r"\[(\d+)\] Capture screen (\d+)", line)
        if m:
            screens.append({"id": m.group(1), "name": f"Screen {m.group(2)}", "type": "screen"})
    return screens



def prepare_hls_dir():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)


def start_stream(source_id, framerate=30):
    """Start avfoundation capture → HLS via hardware encoder."""
    global _ffmpeg_proc
    if _ffmpeg_proc is not None:
        return True, "Already running"

    prepare_hls_dir()

    _ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg",
            "-f", "avfoundation",
            "-framerate", str(framerate),
            "-capture_cursor", "1",
            "-i", f"{source_id}:none",
            "-enc_time_base", f"1/{framerate}",
            "-c:v", "h264_videotoolbox",
            "-b:v", "3M",
            "-g", str(framerate),
            "-f", "hls",
            "-hls_time", "1",
            "-hls_list_size", "3",
            "-hls_flags", "delete_segments+independent_segments",
            "-hls_segment_filename", os.path.join(HLS_DIR, "seg%03d.ts"),
            os.path.join(HLS_DIR, "stream.m3u8"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for first segment
    for _ in range(40):
        time.sleep(0.25)
        if _ffmpeg_proc.poll() is not None:
            err = _ffmpeg_proc.stderr.read().decode(errors="replace")
            _ffmpeg_proc = None
            print(f"ffmpeg exited early. stderr:\n{err[-500:]}")
            return False, "Failed — grant Screen Recording permission to your terminal in System Settings."
        if os.path.exists(os.path.join(HLS_DIR, "stream.m3u8")):
            return True, "Started"

    # Still running but no segments — likely timestamp/duration issue
    err = ""
    try:
        _ffmpeg_proc.terminate()
        _, stderr_bytes = _ffmpeg_proc.communicate(timeout=3)
        err = stderr_bytes.decode(errors="replace")[-500:]
    except Exception:
        _ffmpeg_proc.kill()
    _ffmpeg_proc = None
    print(f"ffmpeg produced no segments. stderr:\n{err}")
    return False, "No segments generated — check screen recording permissions in System Settings."


def stop_stream():
    global _ffmpeg_proc
    if _ffmpeg_proc is not None:
        _ffmpeg_proc.kill()
        try:
            _ffmpeg_proc.wait(timeout=2)
        except Exception:
            pass
    _ffmpeg_proc = None


MIME_TYPES = {
    ".html": "text/html",
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".js": "application/javascript",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/project":
            self.serve_file(os.path.join(STATIC_DIR, "control.html"), "text/html")
        elif self.path == "/" or self.path == "/index.html":
            # Viewer — what attendees see
            if _ffmpeg_proc is not None:
                self.serve_file(os.path.join(STATIC_DIR, "viewer.html"), "text/html")
            else:
                body = b"<html><body style='font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0a;color:#888'><p>Screen sharing is not active yet. Ask the presenter to start sharing.</p></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
        elif self.path.startswith("/hls/"):
            filename = self.path[5:]
            if ".." in filename or "/" in filename:
                self.send_error(403)
                return
            filepath = os.path.join(HLS_DIR, filename)
            ext = os.path.splitext(filename)[1]
            content_type = MIME_TYPES.get(ext, "application/octet-stream")
            self.serve_file(filepath, content_type, cache=(ext == ".ts"))
        elif self.path == "/api/status":
            ip = get_local_ip()
            self.send_json({
                "running": _ffmpeg_proc is not None,
                "ip": ip,
                "viewer_url": f"http://{ip}:{CONTROL_PORT}" if _ffmpeg_proc else None,
            })
        elif self.path == "/api/sources":
            self.send_json({"screens": list_screens()})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/start":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b""
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            ok, msg = start_stream(data.get("id", "3"))
            ip = get_local_ip()
            self.send_json({
                "ok": ok, "message": msg,
                "url": f"http://{ip}:{CONTROL_PORT}" if ok else None, "ip": ip,
            })
        elif self.path == "/api/stop":
            stop_stream()
            self.send_json({"ok": True, "message": "Stopped"})
        else:
            self.send_error(404)

    def serve_file(self, filepath, content_type, cache=False):
        try:
            with open(filepath, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "max-age=60" if cache else "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), Handler)
    print(f"Projector control panel → http://localhost:{CONTROL_PORT}/project")
    print("Press Ctrl+C to stop.")

    def cleanup(*_):
        stop_stream()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda *_: (print("\nStopped."), cleanup(), os._exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), os._exit(0)))

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    thread.join()


if __name__ == "__main__":
    main()
