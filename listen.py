#!/usr/bin/env python3
import os
import socket
import subprocess
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


def main():
    ensure_dir(SAVE_DIR)

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
