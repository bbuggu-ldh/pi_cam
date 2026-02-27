# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Raspberry Pi multi-camera synchronization system. A trigger client (`main_trigger.py`) runs on the main PC and sends UDP messages to multiple Raspberry Pi devices, each running `listen.py` to capture synchronized JPEG images at precisely timed moments. `listen.py` also runs a built-in web gallery (`http://<pi-ip>:8080`). `viewer_central.py` on the main PC aggregates images from all Pis into a single gallery.

**Dependencies:**
- Raspberry Pi (`listen.py`): Python standard library + `flask`; uses the `rpicam-jpeg` CLI tool (part of `rpicam-apps`) for capture — **not** called via `picamera2` Python bindings.
- Main PC (`main_trigger.py`): Python standard library only.
- Main PC (`viewer_central.py`): `flask`

## Running

On the Raspberry Pi:
```bash
python3 listen.py
```
Starts UDP listener on port 5005 **and** web gallery on port 8080.

On the main PC (trigger):
```bash
python3 main_trigger.py
```

On the main PC (central gallery for all Pis, served at `http://localhost:8081`):
```bash
python3 viewer_central.py
```

No build step, no package manager, no virtual environment setup.

## Architecture

### Network Protocol (UDP)

- Trigger messages sent to port `5005` on each Pi
- ACK responses sent back from Pi to port `5006` on the sender
- Three message formats:
  - `shoot` — capture after `DEFAULT_DELAY_SEC`
  - `shoot:<unix_time_float>` — capture at specific Unix timestamp
  - `shoot:<unix_time_float>:<prefix>` — capture with custom filename prefix

### Timing Synchronization

`main_trigger.py` computes `shoot_time = time.time() + 0.3` and broadcasts it to all Pis in the same UDP message, so all cameras target the same absolute timestamp.

`listen.py` uses a **hybrid wait** in `busy_wait_until()`: `time.sleep()` for most of the interval, then busy-spins for the last 10 ms for sub-millisecond precision. After the target time, a `TRIGGER_SETTLE_SEC` sleep allows AE/AWB to stabilize before the `rpicam-jpeg` subprocess is invoked.

### Capture Flow (`listen.py`)

1. Receive UDP packet → `parse_message()` → extract `(shoot_time, prefix)`
2. `busy_wait_until(shoot_time)` — precision wait
3. `time.sleep(TRIGGER_SETTLE_SEC)` — camera settle
4. `capture_jpeg()` — runs `rpicam-jpeg` as a subprocess
5. `send_ack()` — sends `ok:<filename>` or `fail:<error>` back to sender on port `5006`

### Key Constants in `listen.py`

All configuration is hardcoded at the top of the file:

| Constant | Value | Purpose |
|---|---|---|
| `UDP_LISTEN_PORT` | `5005` | Incoming trigger port |
| `ACK_PORT` | `5006` | ACK response port |
| `SAVE_DIR` | `/home/pi/captures` | Image output directory |
| `DEFAULT_DELAY_SEC` | `0.8` | Delay when no timestamp given |
| `TRIGGER_SETTLE_SEC` | `0.12` | Post-trigger settle time |
| `RESOLUTION` | `(4056, 3040)` | HQ camera (IMX477) resolution |
| `JPEG_QUALITY` | `95` | `rpicam-jpeg -q` value |
| `SEND_ACK` | `True` | Toggle ACK messages |
| `WEB_VIEWER_ENABLED` | `True` | Toggle built-in web gallery |
| `WEB_PORT` | `8080` | Web gallery port |

Camera Module 3 (IMX708) max resolution is `(4608, 2592)` — adjust `RESOLUTION` accordingly.

| Constant | Value | Purpose |
|---|---|---|
| `FILENAME_PREFIX_DEFAULT` | `"capture"` | Default filename prefix |

`capture_jpeg()` calls `rpicam-jpeg` with `-t 1` (1 ms timeout) to minimize pre-capture delay. This is intentional — the settle time is handled by `TRIGGER_SETTLE_SEC`, not by `rpicam-jpeg`'s own timeout.

### Concurrency model

`listen.py` runs Flask in a daemon thread (`_start_web_viewer`) alongside the main UDP listener loop. The UDP loop blocks on `sock.recvfrom()` and is unaffected by web requests. Flask uses `use_reloader=False` to prevent process forking. There is no concurrent capture support — a new trigger received during an active capture will only be processed after the current one completes.

### Target Pi IPs in `main_trigger.py` and `viewer_central.py`

Hardcoded list: `["192.168.0.3", "192.168.0.2", "192.168.0.4"]`

### Web gallery in `listen.py`

Serves captured images from `SAVE_DIR` as a dark-themed responsive grid gallery with lightbox and optional auto-refresh (every 3 s). Also exposes `/images.json` (`{ hostname, images[] }`) for use by `viewer_central.py`.

### `viewer_central.py`

Flask app on port 8081 that fetches `/images.json` from each Pi and renders a unified gallery. Tabs: "All" + one per Pi. Offline Pis are shown as offline. Images are proxied through `/img/<pi_idx>/<filename>`. Lightbox supports left/right arrow key navigation.
