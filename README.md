# Simon

A video surveillance application that uses OpenCV and YOLO11 for local, real-time object tracking and detection.

## Screenshots

### Home
![Command Center](docs/images/home_view.png)

### Zone Editor
![Zone Editor](docs/images/zone_view.png)

### Rule Editor
![Rule Editor](docs/images/rule_view.png)

## Prerequisites

- **Python 3.11 – 3.13** (developed and tested on 3.13).
- Git
- `pip` (comes with Python)
- **Node.js >= 20.19 (or >= 22.12) and npm** — only needed to build the web frontend.
- *(Optional)* An **NVIDIA GPU** for CUDA inference. See [GPU / CUDA](#gpu--cuda) below.
- *(Optional)* **ffmpeg on your `PATH`** — only needed to record footage from an RTSP camera.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/RubenAlvarezGJ/simon.git
cd simon
```

### 2. Create a Python virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

```powershell
venv\Scripts\Activate.ps1   # Windows PowerShell
```

```bash
source venv/bin/activate    # macOS/Linux
```

### 4. Install PyTorch

There's no single `requirements.txt` pinning a PyTorch build anymore — dependencies live in a
per-hardware-target `requirements/` directory, and the two torch files simply point at PyTorch's
own package index with an unpinned `torch`/`torchvision`, so pip resolves whatever build that
index currently serves for your platform. Pick one:

**NVIDIA GPU (CUDA):**

```bash
pip install -r requirements/torch-cuda.txt
```

**CPU only, or macOS:**

```bash
pip install -r requirements/torch-cpu.txt
```

### 5. Install the remaining dependencies

```bash
pip install -r requirements/dev.txt
```

PyTorch is already installed at this point, so pip reports it as satisfied and skips it.
`requirements/dev.txt` pulls in `requirements/base.txt` (the runtime dependencies) plus `pytest` /
`pytest-asyncio` / `httpx` for running the test suite.

### GPU / CUDA

Inference device is selected automatically at startup — `cuda` when `torch.cuda.is_available()`
returns true, otherwise `cpu`. Nothing to configure; without a usable GPU, Simon runs on CPU at
a lower frame rate. You can also force it with `--device cpu`/`--device cuda`
(`SIMON_DEVICE` under Docker — see [Containerized deployment](#containerized-deployment-docker)
below); an explicit `cuda` request on a machine without CUDA logs a warning and falls back to CPU
rather than failing outright.

`requirements/torch-cuda.txt` installs from PyTorch's CUDA index
(`--index-url https://download.pytorch.org/whl/cu124`) with no version pin to edit by hand — you
need a recent-enough NVIDIA driver for whatever CUDA 12.4 wheel pip resolves; no separate CUDA
Toolkit install is required, the wheels bundle their own runtime.

Verify after installing:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## Running locally

```bash
python server.py
python server.py --source 0
python server.py --source videos/clip.mp4 --host 0.0.0.0 --port 9000
python server.py --source rtsp://user:pass@camera.local:554/stream
```

Then open http://127.0.0.1:8000 (the default; the third example above serves on port 9000
instead). `--source` takes a camera index, a file path, or an RTSP URL. `server.py` serves the
built frontend from `web/dist` if it's present, so build the frontend first (below).

Run `python server.py --help` for the full flag list, including footage retention limits.

### First run

Zone and rule configs live in `src/config/`; a fresh clone starts with
none. Until you create them, Simon runs in bypass mode: detection and tracking work, but no
rules fire and no alerts are sent. Create zones in the **Zone Editor** tab and rules in the
**Rule Editor** tab — saving writes the config and hot-reloads the running pipeline, no restart
needed.

### Build the frontend

```bash
cd web
npm install
npm run build      # bundles into web/dist, which server.py serves
```

### Frontend dev server (optional, hot reload)

```bash
cd web
npm run dev
```

Run `server.py` alongside the dev server - Vite proxies `/api` → http://localhost:8000.

## Footage recording (optional)

Simon can archive the raw camera stream to disk alongside detection, in 60-second segments
under `footage/`. This requires **ffmpeg on your `PATH`** and an **RTSP source** — recording is
skipped for camera-index and file sources, since it stream-copies (`-c copy`) rather than
re-encodes.

A retention manager prunes `footage/` on an interval so it never grows without bound:

| Flag                    | Default | Meaning                                        |
| ----------------------- | ------- | ---------------------------------------------- |
| `--footage`             | `footage` | Directory holding recorded footage           |
| `--max-footage-gb`      | `10`    | Size budget in GB (`0` = unlimited)             |
| `--footage-ttl-hours`   | `24`    | Delete segments older than this (`0` = no TTL)  |
| `--footage-sweep-mins`  | `1`     | Minutes between cleanup sweeps                  |
| `--no-footage-cleanup`  | —       | Never delete footage autonomously  |

## Telegram notifications (optional)

Simon can push alerts to a Telegram chat. This is optional though, without it the pipeline runs
normally.

### 1. Create a bot

In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the
prompts. It replies with an HTTP API token, this is your `TELEGRAM_BOT_TOKEN`.

### 2. Get your chat ID

Start a chat with your new bot and send it any message, then get your numeric chat ID either way:

- Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` (with your token) and read
  `result[].message.chat.id`, or
- Message [@userinfobot](https://t.me/userinfobot), which replies with your ID.

This is your `CHAT_ID`. For a group chat, add the bot to the group and use the group's chat id
(it will be negative).

### 3. Create a `.env` file

In the project root, create a `.env` file. It's git-ignored, so
the secrets stay out of version control:

```
TELEGRAM_BOT_TOKEN=<YOUR_TOKEN_HERE>
CHAT_ID=<YOUR_ID_HERE>
```

### 4. Restart the server

Restart `server.py`.

### Current notification behavior

Alerts are routed by each rule's `severity` (set in the Rule
Editor tab):

| Severity   | Telegram behavior                        |
| ---------- | ---------------------------------------- |
| `low`      | Not sent (recorded locally only)  |
| `high`     | Sent silently (no notification sound)    |
| `critical` | Sent with an audible notification        |

## Containerized deployment (Docker)

Simon ships a parameterized `Dockerfile` and a `docker-compose.yml` with three build targets.
Only one target runs per machine.

| Target | Machine |
| ------ | ------- |
| `cpu`    | Mini PC / any x86_64 host with no GPU |
| `gpu`    | x86_64 laptop or desktop with an NVIDIA GPU and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed on the host |
| `jetson` | NVIDIA Jetson Orin (aarch64, JetPack 6.x). Builds only on Jetson hardware itself — confirm the L4T base image tag against your flashed JetPack release before building |

### First-time setup

```bash
mkdir -p src/config footage logs
```

`docker-compose.yml` bind-mounts these into the container (`src/config` for the Zone/Rule
editors, `footage` for recorded video, `logs` for the alert JSONL log), along with the existing
`models/` directory. They need to exist on the host before the first `docker compose up`, or
Docker creates them as `root`-owned directories on first use.

If you want Telegram alerts, create the `.env` file described above
([Telegram notifications](#telegram-notifications-optional)) in the project root first —
`docker-compose.yml` references it via `env_file: .env`, which injects it into the container
**at start time only**. `.env` is listed in `.dockerignore`, so it is never copied into an image
layer or baked into anything you'd `docker push`.

### Build and run

```bash
docker compose build cpu && docker compose up -d cpu
docker compose build gpu && docker compose up -d gpu
```

(`jetson` follows the same pattern, but only builds on Jetson hardware.) Then open
`http://<host>:8000` — or whatever port you've mapped, see the port gotcha below.

### `SIMON_*` environment variables

`docker-compose.yml` sets these under each service's `environment:` block. This is the full set
`server.py` understands — every flag also has a `--`-prefixed CLI equivalent (`python server.py
--help` documents both):

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIMON_SOURCE` | `0` | Camera index, file path, or RTSP URL |
| `SIMON_MODEL` | `models/yolo11s.pt` | Path to detector weights |
| `SIMON_DEVICE` | `auto` | `auto`, `cpu`, or `cuda` |
| `SIMON_HOST` | `127.0.0.1` | Bind host |
| `SIMON_PORT` | `8000` | Bind port |
| `SIMON_ZONES` | `src/config/zones.json` | Zones config path |
| `SIMON_RULES` | `src/config/rules.json` | Rules config path |
| `SIMON_ALERTS_LOG` | `logs/alerts.jsonl` | JSONL alert log path |
| `SIMON_STATIC_DIR` | `web/dist` | Directory served as the SPA |
| `SIMON_FOOTAGE` | `footage` | Directory holding recorded footage |
| `SIMON_MAX_FOOTAGE_GB` | `10` | Footage size budget in GB (`0` = unlimited) |
| `SIMON_FOOTAGE_TTL_HOURS` | `24` | Delete footage older than this many hours (`0` = no TTL) |
| `SIMON_FOOTAGE_SWEEP_MINS` | `1` | Minutes between footage-cleanup sweeps |
| `SIMON_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

`--no-footage-cleanup` (disables the retention manager entirely) has **no `SIMON_*` equivalent** —
unlike every other flag above, it's a plain on/off switch with no environment backing, so a
container can't turn footage retention off through `environment:`; you'd have to override the
compose service's `command:` instead.

**Set `SIMON_*` variables as real environment variables — not in `.env`.** `docker-compose.yml`'s
`environment:` block (as shown above) works correctly; putting a `SIMON_*` value only in `.env`
does not. Only `TelegramSink` calls `load_dotenv()`, and it does so lazily, on the alert-dispatch
worker thread, well after `server.py`'s argument parsing has already read every `SIMON_*` default
from the environment via `os.getenv(...)`. A `SIMON_*` value that exists only in `.env` is never
seen. `TELEGRAM_BOT_TOKEN` / `CHAT_ID` don't have this problem — they're the only two variables
`TelegramSink` itself reads, so `.env` is exactly where they belong.

### Networking gotchas

- **`localhost` inside a container is the container**, not your host machine. If your RTSP camera
  (or anything else `SIMON_SOURCE` needs to reach) runs on the host, point it at
  `host.docker.internal` (Docker Desktop) or the host's LAN IP instead — the compose file's
  default, `rtsp://host.docker.internal:8554/cam`, already does this.
- **`SIMON_HOST` must be `0.0.0.0`** (already set in `docker-compose.yml`). The server's own
  default, `127.0.0.1`, only accepts connections from inside the container itself, so the
  published port would never actually respond from outside.
- **No USB webcam passthrough on Docker Desktop for Windows.** A numeric `SIMON_SOURCE` (camera
  index) will not see a USB camera through Docker Desktop's Windows/WSL2 backend. Use an RTSP
  source instead, or run on native Linux Docker if you need a camera index.

### What to expect operationally

- **Footage only accumulates for `rtsp://` sources.** `VideoRecorder` is only constructed when
  `SIMON_SOURCE` is an RTSP URL; camera-index and file sources record nothing to `footage/` by
  design (look for the startup log line `recorder autostart skipped; source '...' is not an RTSP
  URL` to confirm this is what happened, not a failure).
- **A file-path source eventually flips the container `unhealthy` — this is expected.** The
  healthcheck asserts the `pipeline_running` field in `/api/health`, not just an HTTP 200
  (`/api/health` returns 200 even when the detector thread has died, e.g. from a bad `SIMON_MODEL`
  path, so a status-only check could never catch that). When a file source hits end-of-stream the
  pipeline legitimately stops and `pipeline_running` goes `false`; a production RTSP source
  doesn't end, so this only shows up with file sources. Also note the pipeline decodes a file as
  fast as the queue allows rather than at the file's real playback rate, so a clip finishes in a
  fraction of its nominal duration.
- **Host port 8000 may already be bound by something else** on your machine (a VPN client, WSL
  port-forwarding, another service). If `docker compose up` fails to bind the port, remap the host
  side in `docker-compose.yml`, e.g. `"8001:8000"`.

## Planned
- Store only footage matching a user-defined rule (e.g. when a car is detected in the driveway)
- Video playback interface
