# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Raspberry Pi multi-camera synchronization system. A trigger client (`main_trigger.py`) runs on the main PC and sends UDP messages to multiple Raspberry Pi devices, each running `listen.py` to capture synchronized JPEG images at precisely timed moments.

**Dependencies (Raspberry Pi only):** `picamera2` (Raspberry Pi camera library), Python standard library (`os`, `socket`, `time`, `datetime`).

## Running

On the Raspberry Pi (listener):
```bash
python3 listen.py
```

On the main PC (trigger):
```bash
python3 main_trigger.py
```

No build step, no package manager, no virtual environment setup documented.

## Architecture

### Network Protocol (UDP)

- Trigger messages sent to port `5005` on each Pi
- ACK responses sent back from Pi to port `5006` on the sender
- Three message formats supported:
  - `shoot` — capture after default delay
  - `shoot:<unix_time_float>` — capture at specific timestamp
  - `shoot:<unix_time_float>:<prefix>` — capture with custom filename prefix

### Timing Synchronization

All Raspberry Pis receive the same target timestamp (`now + 0.3s` from the trigger client). `listen.py` uses **busy-wait polling** (`while time.monotonic() < target`) for sub-millisecond precision rather than `time.sleep()`. After the target time, a settle period (`TRIGGER_SETTLE_SEC = 0.12s`) allows camera exposure/AWB to stabilize before capture.

### Key Constants in `listen.py`

All configuration is hardcoded at the top of the file:

| Constant | Value | Purpose |
|---|---|---|
| `UDP_LISTEN_PORT` | `5005` | Incoming trigger port |
| `ACK_PORT` | `5006` | ACK response port |
| `SAVE_DIR` | `/home/pi/captures` | Image output directory |
| `DEFAULT_DELAY_SEC` | `0.8` | Delay when no timestamp given |
| `TRIGGER_SETTLE_SEC` | `0.12` | Post-trigger settle time |
| `RESOLUTION` | `(4056, 3040)` | HQ camera resolution |
| `JPEG_QUALITY` | `95` | JPEG encoder quality |
| `SEND_ACK` | `True` | Toggle ACK messages |

### Target Pi IPs in `main_trigger.py`

Hardcoded list: `["192.168.0.4", "192.168.0.102", "192.168.0.103"]`
