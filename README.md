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

`requirements.txt` pins CUDA 13.0 builds of PyTorch (`torch==2.11.0+cu130`,
`torchvision==0.26.0+cu130`). **Those wheels are not on PyPI**, so they have to come from
PyTorch's own index first — `pip install -r requirements.txt` on its own will fail with
`No matching distribution found for torch==2.11.0+cu130`.

**NVIDIA GPU (CUDA 13.0):**

```bash
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu130
```

**CPU only, or macOS:** there is no `+cu130` wheel for you. Delete the `+cu130` suffix from
the two torch lines in `requirements.txt` (a plain `torch==2.11.0` pin is still satisfied by
an installed CUDA build, so this is safe to commit), then:

```bash
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
```

### 5. Install the remaining dependencies

```bash
pip install -r requirements.txt
```

PyTorch is already installed at this point, so pip reports it as satisfied and skips it.

### GPU / CUDA

Inference device is selected automatically at startup — `cuda` when `torch.cuda.is_available()`
returns true, otherwise `cpu`. Nothing to configure; without a usable GPU, Simon runs on CPU at
a lower frame rate.

To use the pinned CUDA 13.0 build you need:

- An NVIDIA GPU of **Turing (GTX 16-series / RTX 20-series) or newer**. CUDA 13 dropped support
  for Maxwell, Pascal and Volta, so GTX 10-series and older cards must use an older CUDA build
  (e.g. `--index-url https://download.pytorch.org/whl/cu126`) with matching torch pins.
- A recent NVIDIA driver (r580 or newer for CUDA 13.0). No separate CUDA Toolkit install is
  required — the wheels bundle their own runtime.

Verify after installing:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# 2.11.0+cu130 True
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

## Planned
- Store only footage matching a user-defined rule (e.g. when a car is detected in the driveway)
- Video playback interface
