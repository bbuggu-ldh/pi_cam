#!/usr/bin/env python3
import glob as _glob
import os
import socket
import subprocess
import threading
import time
from datetime import datetime

# ===== Network =====
UDP_LISTEN_PORT = 5005
ACK_PORT = 5006           # Port on main PC to receive ACK
SEND_ACK = True           # Set True to send ACK after capture

# ===== Storage =====
SAVE_DIR = "/home/pi/captures"
FILENAME_PREFIX_DEFAULT = "capture"

# ===== Capture Timing =====
DEFAULT_DELAY_SEC = 0.8   # Delay when no shoot_time is provided in message
TRIGGER_SETTLE_SEC = 0.12 # Settle time after trigger for AE/AWB stabilization

# ===== Image Quality =====
# Max resolution depends on camera model. Adjust if out of range.
# HQ (IMX477): (4056, 3040) | Camera Module 3 (IMX708): (4608, 2592)
RESOLUTION = (4056, 3040)
JPEG_QUALITY = 95         # rpicam-jpeg -q value (0-100)

# ===== Web Viewer =====
WEB_VIEWER_ENABLED = True
WEB_PORT = 8080
STREAM_WIDTH  = 1280      # live stream resolution (lower = less CPU/bandwidth)
STREAM_HEIGHT = 720
STREAM_FPS    = 15


# ── Camera management ─────────────────────────────────────────────────────────

_stream_proc = None
_stream_lock = threading.Lock()


def _kill_stream():
    """Terminate the live stream process so the camera is free for still capture."""
    global _stream_proc
    with _stream_lock:
        if _stream_proc and _stream_proc.poll() is None:
            _stream_proc.terminate()
            try:
                _stream_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _stream_proc.kill()
            _stream_proc = None


# ── Capture helpers ───────────────────────────────────────────────────────────

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def busy_wait_until(t: float) -> None:
    # Sleep for most of the wait; busy-spin for last 10ms for precision
    while True:
        remaining = t - time.time()
        if remaining <= 0:
            return
        if remaining > 0.01:
            time.sleep(remaining - 0.005)


def make_filename(prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(SAVE_DIR, f"{prefix}_{ts}.jpg")


def parse_message(data: bytes):
    """
    Supported message formats:
      - b"shoot"                               -> capture after DEFAULT_DELAY_SEC
      - b"shoot:<unix_time_float>"             -> capture at specified timestamp
      - b"shoot:<unix_time_float>:<prefix>"    -> capture with custom filename prefix
    """
    text = data.decode("utf-8", errors="ignore").strip()
    if not text.startswith("shoot"):
        return None

    parts = text.split(":")
    if len(parts) == 1:
        return time.time() + DEFAULT_DELAY_SEC, FILENAME_PREFIX_DEFAULT

    try:
        shoot_time = float(parts[1])
    except ValueError:
        shoot_time = time.time() + DEFAULT_DELAY_SEC

    prefix = parts[2] if len(parts) >= 3 and parts[2] else FILENAME_PREFIX_DEFAULT
    return shoot_time, prefix


def send_ack(to_ip: str, ok: bool, info: str):
    if not SEND_ACK:
        return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        msg = f"{'ok' if ok else 'fail'}:{info}".encode("utf-8", errors="ignore")
        s.sendto(msg, (to_ip, ACK_PORT))
        s.close()
    except Exception:
        pass


def capture_jpeg(filename: str):
    _kill_stream()  # free the camera before still capture
    cmd = [
        "rpicam-jpeg",
        "-o", filename,
        "--width",   str(RESOLUTION[0]),
        "--height",  str(RESOLUTION[1]),
        "-q",        str(JPEG_QUALITY),
        "--nopreview",
        "-t", "1",   # minimal capture timeout (ms)
    ]
    subprocess.run(cmd, check=True)


# ── Web viewer ────────────────────────────────────────────────────────────────

_WEB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pi Cam Viewer</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #111; color: #eee; font-family: sans-serif; }

    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 20px; background: #1a1a1a; border-bottom: 1px solid #333;
      position: sticky; top: 0; z-index: 10;
    }
    header h1 { font-size: 1rem; font-weight: 600; letter-spacing: 0.05em; }
    header span { font-size: 0.8rem; color: #888; }

    .auto-refresh { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #aaa; }
    .auto-refresh input { accent-color: #4af; }

    .live-btn {
      padding: 5px 12px; font-size: 0.8rem; background: #1e3a4a;
      color: #4af; border: 1px solid #2a5a7a; border-radius: 4px;
      cursor: pointer; text-decoration: none;
    }
    .live-btn:hover { background: #254a60; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 4px;
      padding: 8px;
    }

    .card {
      position: relative; overflow: hidden; aspect-ratio: 4/3;
      background: #222; cursor: pointer;
    }
    .card img {
      width: 100%; height: 100%; object-fit: cover;
      transition: transform 0.2s;
    }
    .card:hover img { transform: scale(1.04); }
    .card .label {
      position: absolute; bottom: 0; left: 0; right: 0;
      padding: 4px 6px; font-size: 0.65rem; color: #ccc;
      background: linear-gradient(transparent, rgba(0,0,0,0.7));
    }

    .empty { text-align: center; padding: 80px 20px; color: #555; }

    /* Live overlay */
    #live-overlay {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.95); z-index: 100;
      flex-direction: column; align-items: center; justify-content: center;
    }
    #live-overlay.open { display: flex; }
    #live-overlay img {
      max-width: 95vw; max-height: 88vh; object-fit: contain;
      background: #000;
    }
    #live-overlay .lo-label {
      margin-top: 10px; font-size: 0.8rem; color: #4af;
    }
    #live-close {
      position: absolute; top: 14px; right: 18px;
      font-size: 1.6rem; cursor: pointer; color: #aaa; background: none; border: none;
    }

    /* Lightbox */
    #lb {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.92); z-index: 200;
      align-items: center; justify-content: center; flex-direction: column;
    }
    #lb.open { display: flex; }
    #lb img { max-width: 95vw; max-height: 90vh; object-fit: contain; }
    #lb .lb-name { margin-top: 10px; font-size: 0.8rem; color: #888; }
    #lb-close {
      position: absolute; top: 14px; right: 18px;
      font-size: 1.6rem; cursor: pointer; color: #aaa; background: none; border: none;
    }
  </style>
</head>
<body>

<header>
  <h1>Pi Cam &mdash; {{ hostname }}</h1>
  <div style="display:flex; gap:14px; align-items:center;">
    <span>{{ count }} image{{ 's' if count != 1 else '' }}</span>
    <a class="live-btn" onclick="openLive()">&#9654; Live</a>
    <label class="auto-refresh">
      <input type="checkbox" id="ar"> Auto-refresh
    </label>
  </div>
</header>

{% if images %}
<div class="grid">
  {% for img in images %}
  <div class="card" onclick="openLb('{{ img }}')">
    <img src="/img/{{ img }}" alt="{{ img }}" loading="lazy">
    <div class="label">{{ img }}</div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="empty">No images yet in {{ save_dir }}</div>
{% endif %}

<!-- Live stream overlay -->
<div id="live-overlay">
  <button id="live-close" onclick="closeLive()">&#x2715;</button>
  <img id="live-img" src="" alt="live stream">
  <div class="lo-label">Live &mdash; {{ hostname }}</div>
</div>

<!-- Lightbox -->
<div id="lb">
  <button id="lb-close" onclick="closeLb()">&#x2715;</button>
  <img id="lb-img" src="" alt="">
  <div class="lb-name" id="lb-name"></div>
</div>

<script>
  // Live stream
  let liveTimer = null;
  function openLive() {
    const img = document.getElementById('live-img');
    loadStream(img);
    document.getElementById('live-overlay').classList.add('open');
  }
  function closeLive() {
    document.getElementById('live-overlay').classList.remove('open');
    const img = document.getElementById('live-img');
    img.src = '';
    clearTimeout(liveTimer);
  }
  function loadStream(img) {
    img.src = '/stream?t=' + Date.now();
    img.onerror = () => { liveTimer = setTimeout(() => loadStream(img), 3000); };
  }

  // Lightbox
  function openLb(name) {
    document.getElementById('lb-img').src = '/img/' + name;
    document.getElementById('lb-name').textContent = name;
    document.getElementById('lb').classList.add('open');
  }
  function closeLb() {
    document.getElementById('lb').classList.remove('open');
    document.getElementById('lb-img').src = '';
  }
  document.getElementById('lb').addEventListener('click', function(e) {
    if (e.target === this) closeLb();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeLb(); closeLive(); }
  });

  // Auto-refresh
  let arTimer = null;
  document.getElementById('ar').addEventListener('change', function() {
    if (this.checked) arTimer = setInterval(() => location.reload(), 3000);
    else clearInterval(arTimer);
  });
</script>
</body>
</html>"""


def _mjpeg_frames(proc):
    """Parse raw MJPEG stdout into individual JPEG frames."""
    buf = b""
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buf += chunk
        while True:
            start = buf.find(b'\xff\xd8')
            if start == -1:
                buf = b""
                break
            end = buf.find(b'\xff\xd9', start + 2)
            if end == -1:
                if start > 0:
                    buf = buf[start:]
                break
            yield buf[start:end + 2]
            buf = buf[end + 2:]


def _start_web_viewer():
    try:
        from flask import Flask, abort, jsonify, render_template_string, send_file, Response
    except ImportError:
        print("[viewer] Flask not installed — web viewer disabled.")
        return

    web = Flask(__name__)

    @web.route("/")
    def index():
        files = sorted(
            _glob.glob(os.path.join(SAVE_DIR, "*.jpg")),
            key=os.path.getmtime,
            reverse=True,
        )
        images = [os.path.basename(f) for f in files]
        return render_template_string(
            _WEB_HTML,
            images=images,
            count=len(images),
            save_dir=SAVE_DIR,
            hostname=socket.gethostname(),
        )

    @web.route("/images.json")
    def images_json():
        files = sorted(
            _glob.glob(os.path.join(SAVE_DIR, "*.jpg")),
            key=os.path.getmtime,
            reverse=True,
        )
        images = [os.path.basename(f) for f in files]
        return jsonify({"hostname": socket.gethostname(), "images": images})

    @web.route("/img/<filename>")
    def serve_image(filename):
        if "/" in filename or ".." in filename:
            abort(400)
        path = os.path.join(SAVE_DIR, filename)
        if not os.path.isfile(path):
            abort(404)
        return send_file(path, mimetype="image/jpeg")

    @web.route("/stream")
    def stream():
        global _stream_proc

        def generate():
            global _stream_proc
            _kill_stream()
            cmd = [
                "rpicam-vid",
                "-t", "0",
                "--codec", "mjpeg",
                "--width",     str(STREAM_WIDTH),
                "--height",    str(STREAM_HEIGHT),
                "--framerate", str(STREAM_FPS),
                "--nopreview",
                "-o", "-",
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            with _stream_lock:
                _stream_proc = proc
            try:
                for frame in _mjpeg_frames(proc):
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                           + frame + b'\r\n')
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                with _stream_lock:
                    if _stream_proc is proc:
                        _stream_proc = None

        return Response(
            generate(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={'Cache-Control': 'no-cache'},
        )

    print(f"[viewer] Starting on http://0.0.0.0:{WEB_PORT}")
    web.run(host="0.0.0.0", port=WEB_PORT, debug=False, use_reloader=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ensure_dir(SAVE_DIR)

    if WEB_VIEWER_ENABLED:
        t = threading.Thread(target=_start_web_viewer, daemon=True)
        t.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", UDP_LISTEN_PORT))

    hostname = socket.gethostname()
    print(f"[{hostname}] Listening UDP :{UDP_LISTEN_PORT}")
    print(f"[{hostname}] Save dir: {SAVE_DIR}")
    print(f"[{hostname}] Resolution: {RESOLUTION}, JPEG q={JPEG_QUALITY}")

    while True:
        data, addr = sock.recvfrom(1024)
        parsed = parse_message(data)
        if not parsed:
            continue

        shoot_time, prefix = parsed
        from_ip = addr[0]

        dt = shoot_time - time.time()
        print(f"[{hostname}] Trigger from {addr}, shoot in {dt:.3f}s, prefix={prefix}")

        busy_wait_until(shoot_time)

        if TRIGGER_SETTLE_SEC > 0:
            time.sleep(TRIGGER_SETTLE_SEC)

        filename = make_filename(prefix)

        try:
            capture_jpeg(filename)
            print(f"[{hostname}] Captured: {filename}")
            send_ack(from_ip, True, filename)
        except Exception as e:
            print(f"[{hostname}] Capture failed: {e}")
            send_ack(from_ip, False, str(e))


if __name__ == "__main__":
    main()
