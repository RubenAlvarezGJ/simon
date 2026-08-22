# Simon

[![CI](https://github.com/RubenAlvarezGJ/simon/actions/workflows/ci.yml/badge.svg)](https://github.com/RubenAlvarezGJ/simon/actions/workflows/ci.yml)

A video surveillance application that uses OpenCV and YOLO for local, real-time object tracking and detection.

Docker is the recommended way to run Simon — [Installation (Docker)](#installation-docker).
If you prefer a bare-metal setup — [Running from source](#running-from-source).

## Screenshots

### Home
![Camera](docs/images/home_view.png)

### Zone Editor
![Zone Editor](docs/images/zone_view.png)

### Rule Editor
![Rule Editor](docs/images/rule_view1.png)
![Rule Editor](docs/images/rule_view2.png)
![Rule Editor](docs/images/rule_view3.png)

## Installation (Docker)

**This is the recommended way to run Simon.** The only things you need on the host are Git and
Docker — the image installs Python, PyTorch, and ffmpeg, and builds the web frontend itself. The
one exception is the `gpu` target, which also needs a host NVIDIA driver and, on Linux, the
NVIDIA Container Toolkit — see [GPU / CUDA](#gpu--cuda).

Simon ships a parameterized `Dockerfile` and a `docker-compose.yml` with three build targets.
Only one target runs per machine.

| Target | Machine |
| ------ | ------- |
| `cpu`    | Mini PC / any x86_64 host with no GPU |
| `gpu`    | x86_64 laptop or desktop with an NVIDIA GPU — [GPU / CUDA](#gpu--cuda) |
| `jetson` | NVIDIA Jetson Orin (aarch64, JetPack 6.x). Builds only on Jetson hardware itself — confirm the L4T base image tag against your flashed JetPack release before building |

### First-time setup

```bash
git clone https://github.com/RubenAlvarezGJ/simon.git
cd simon
mkdir -p src/config footage logs
```

`docker-compose.yml` bind-mounts these into the container (`src/config` for the Zone/Rule
editors, `footage` for recorded video, `logs` for the alert JSONL log), along with the existing
`models/` directory. They need to exist on the host before the first `docker compose up`, or
Docker creates them as `root`-owned directories on first use.

The clone matters for more than the source: detector weights are **not** baked into the image,
they reach the container through the `./models` bind mount. They're committed to the repo, so a
normal clone has them — but `docker compose up` from a directory without `models/` will fail to
load the detector.

If you want Telegram alerts, create the `.env` file described in
[Telegram notifications](#telegram-notifications-optional) below, in the project root, before
starting — `docker-compose.yml` references it via `env_file: [{path: .env, required: false}]`,
which injects it into the container **at start time only** and is genuinely optional: `.env`
absent is fine and `docker compose up` still starts (Telegram alerts just stay inert). `.env` is
also listed in `.dockerignore`, so even when present it is never copied into an image layer or
baked into anything you'd `docker push`.

### Build and run

```bash
docker compose build cpu && docker compose up -d cpu
docker compose build gpu && docker compose up -d gpu
docker compose build jetson && docker compose up -d jetson # only builds on Jetson hardware.
```

Then open `http://<host>:8000` — or whatever port you've mapped, see [Networking](#networking) below. Then head to
[First run](#first-run).

`docker-compose.yml` also sets `TZ` (currently `America/Los_Angeles`), which fixes the container
clock and therefore the timestamps on alert log entries and footage segment filenames. Change it
to your own zone.

### Environment variables

Every one of Simon's CLI flags except `--no-footage-cleanup` also reads a `SIMON_*` environment
variable for its default, and the table below is that full set (`python server.py --help`
documents both spellings). `docker-compose.yml` only *sets* four of them under its shared
`environment:` block — `SIMON_HOST`, `SIMON_SOURCE`, `SIMON_MODEL`, and `SIMON_DEVICE` (which the
`cpu` service pins to `cpu`). The rest are understood but unset, so they fall back to the defaults
shown here; add them to `environment:` if you need to change one.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIMON_SOURCE` | `0` | Camera index, file path, or RTSP URL |
| `SIMON_MODEL` | `models/yolo11s.pt` | Path to detector weights |
| `SIMON_DEVICE` | `auto` | `auto`, `cpu`, or `cuda` — see [GPU / CUDA](#gpu--cuda) |
| `SIMON_HOST` | `127.0.0.1` | Bind host |
| `SIMON_PORT` | `8000` | Bind port |
| `SIMON_ZONES` | `src/config/zones.json` | Zones config path |
| `SIMON_RULES` | `src/config/rules.json` | Rules config path |
| `SIMON_ALERTS_LOG` | `logs/alerts.jsonl` | JSONL alert log path |
| `SIMON_STATIC_DIR` | `web/dist` | Directory served as the SPA |
| `SIMON_FOOTAGE` | `footage` | See [Footage recording](#footage-recording-optional) |
| `SIMON_MAX_FOOTAGE_GB` | `10` | See [Footage recording](#footage-recording-optional) |
| `SIMON_FOOTAGE_TTL_HOURS` | `24` | See [Footage recording](#footage-recording-optional) |
| `SIMON_FOOTAGE_SWEEP_MINS` | `1` | See [Footage recording](#footage-recording-optional) |
| `SIMON_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

`--no-footage-cleanup` (disables the retention manager entirely) has **no `SIMON_*` equivalent** —
unlike every other flag above, it's a plain on/off switch with no environment backing, so a
container can't turn footage retention off through `environment:`; you'd have to override the
compose service's `command:` instead.

**Set `SIMON_*` variables as real environment variables — not in `.env`.** The `environment:`
block shown above works; a `SIMON_*` value placed only in `.env` does not.

`.env` is loaded by `TelegramSink`, which is constructed once the pipeline starts. By then
`server.py` has already read every `SIMON_*` default straight from the process environment, so
anything living only in `.env` arrives too late to be seen. `TELEGRAM_BOT_TOKEN` and `CHAT_ID`
are unaffected — `TelegramSink` reads those itself, which is exactly what `.env` is for.

### Networking

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

- **Footage only accumulates for `rtsp://` (or `rtsps://`) sources.** `VideoRecorder` is only
  constructed when `SIMON_SOURCE` is an RTSP URL; camera-index and file sources record nothing to
  `footage/` by design. To confirm this is what happened rather than a failure, look for this
  line in the startup logs:

  ```
  FastAPI lifespan: recorder autostart skipped; source '...' is not an RTSP URL
  ```

- **A file-path source eventually flips the container `unhealthy` — this is expected.** The
  healthcheck reads the `pipeline_running` field from `/api/health` rather than settling for an
  HTTP 200, because that endpoint answers 200 whenever the web server is up, including when the
  detector thread has died from something like a bad `SIMON_MODEL` path. A file source that
  reaches the end of the stream stops the pipeline legitimately, so `pipeline_running` goes
  `false` and the container is marked unhealthy. An RTSP source never ends, so this is specific
  to files. Note too that the pipeline decodes a file as fast as the queue allows rather than at
  playback speed, so a clip finishes in a fraction of its running time.
- **Host port 8000 may already be bound by something else** on your machine (a VPN client, WSL
  port-forwarding, another service). If `docker compose up` fails to bind the port, remap the host
  side in `docker-compose.yml`, e.g. `"8001:8000"`.



## Running from source

Running Simon directly on the host, without a container. This is the path to use if you'd rather not run Docker at all — but it puts the Python, Node,
and PyTorch setup on you, which [Installation (Docker)](#installation-docker) above handles
for you.

### Prerequisites

- **Python 3.11 – 3.13** (developed and tested on 3.13).
- Git
- `pip` (comes with Python)
- **Node.js >= 20.19 (or >= 22.12) and npm** — only needed to build the web frontend.
- *(Optional)* An **NVIDIA GPU** for CUDA inference. See [GPU / CUDA](#gpu--cuda) below.
- *(Optional)* **ffmpeg on your `PATH`** — only needed to record footage from an RTSP camera.

### 1. Clone the repository

Skip if you already cloned for the Docker path.

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

Dependencies live in a `requirements/` directory split by hardware target, so PyTorch is
installed on its own rather than through one combined file. The two torch files point at
PyTorch's package index with `torch`/`torchvision` left unpinned, letting pip resolve the build
that index serves for your platform. Pick one:

**NVIDIA GPU (CUDA):**

```bash
pip install -r requirements/torch-cuda.txt
```

**CPU only, or macOS:**

```bash
pip install -r requirements/torch-cpu.txt
```

There is a third file, `requirements/torch-jetson.txt`, but it installs nothing — torch ships
inside the Jetson base image. It exists only so the `jetson` container target can share the same
build argument as the others; local installs always pick one of the two above.

### 5. Install the remaining dependencies

```bash
pip install -r requirements/dev.txt
```

PyTorch is already installed at this point, so pip reports it as satisfied and skips it.
`requirements/dev.txt` pulls in `requirements/base.txt` (the runtime dependencies) plus `pytest` /
`pytest-asyncio` / `httpx` for running the test suite.

### 6. Build the frontend

```bash
cd web
npm install
npm run build      # bundles into web/dist, which server.py serves
```

**Careful with `npm install` here.** The container build runs `npm ci` inside a digest-pinned
`node:24-alpine` image. That pin exists because npm resolves the optional per-platform WASM
bindings vite/rolldown depend on differently between npm versions, so a `web/package-lock.json`
written by one npm can fail `npm ci` under another.

Running `npm install` with your host's npm can rewrite the lockfile into a form the pinned image
rejects, which breaks the container build even though everything still works locally. If you
change frontend dependencies, regenerate the lockfile inside the pinned image instead — the
`Dockerfile`'s stage-1 comment has the exact command — and commit it together with any digest
change.

### Running the server

```bash
python server.py
python server.py --source 0
python server.py --source videos/clip.mp4 --host 0.0.0.0 --port 9000
python server.py --source rtsp://user:pass@camera.local:554/stream
```

Then open http://127.0.0.1:8000 (the default; the third example above serves on port 9000
instead). `--source` takes a camera index, a file path, or an RTSP URL. `server.py` serves the
built frontend from `web/dist` if it's present, so run step 6 above before starting the server.

Run `python server.py --help` for the full flag list, including footage retention limits. Every
flag also has a `SIMON_*` environment equivalent — the table under
[`SIMON_*` environment variables](#environment-variables) lists all of them with their
defaults.

### Frontend dev server (optional, hot reload)

```bash
cd web
npm run dev
```

Run `server.py` alongside the dev server - Vite proxies `/api` → http://localhost:8000.

## Running the tests

The Python suite runs on `pytest`, which comes with `requirements/dev.txt`. With the virtual environment activated, run it from the **project root** so
`pytest.ini` is picked up:

```bash
python -m pytest
```

Expect **263 passed, 1 skipped**. The skip is normal: one test class smoke-tests an optional
`rules.json` placed next to `src/logic_layer/tests/`, and skips itself when that file isn't
there.

If `python -m pytest` picks up the wrong interpreter (a common Windows issue when several
Pythons are installed), call the virtual environment's Python directly:

```powershell
venv\Scripts\python.exe -m pytest    # Windows PowerShell
```

```bash
venv/bin/python -m pytest            # macOS/Linux
```

### Running a subset

Tests live in a `tests/` directory inside each layer, so a path narrows the run to that layer:

```bash
python -m pytest src/logic_layer/tests          # logic layer only (127 tests)
python -m pytest src/alert_layer/tests          # alert layer only (45 tests)
python -m pytest src/cv_layer/tests             # CV layer only (15 tests)
python -m pytest src/recorder/tests             # recorder layer only (11 tests)
python -m pytest src/web_layer/tests            # web layer only (66 tests)

python -m pytest src/web_layer/tests/test_routes.py            # a single file
python -m pytest src/web_layer/tests/test_routes.py -k health  # tests matching a name
python -m pytest -v                                            # one line per test
```

The frontend has no test suite yet; `cd web && npm run lint` is the equivalent check there.

## GPU / CUDA

Inference device is selected automatically at startup — `cuda` when `torch.cuda.is_available()`
returns true, otherwise `cpu`. Nothing to configure; without a usable GPU, Simon runs on CPU at
a lower frame rate. You can force it with `--device cpu`/`--device cuda`, or the matching
`SIMON_DEVICE` variable (which is how the `cpu` compose service pins itself). `cuda:1` and other
indexed forms work too, for choosing a specific GPU on a multi-GPU host.

An explicit `cuda` request on a machine without CUDA logs a warning and falls back to CPU rather
than failing outright. **`auto` makes that same fallback silently** — so on a machine you expect
to be using the GPU, confirm it in the startup log rather than assuming:

```
Detector: weights=models/yolo11s.pt device=cuda
```

`requirements/torch-cuda.txt` installs from PyTorch's CUDA index
(`--index-url https://download.pytorch.org/whl/cu124`) with no version pin to edit by hand. Those
wheels bundle their own CUDA runtime as `nvidia-*` packages, so **no CUDA Toolkit and no cuDNN
install is required** on any platform. The host NVIDIA driver is the one piece that can never
come from pip or from an image — it is kernel-level.

### What to install

| Setup | Required on the host |
| ----- | -------------------- |
| Docker Desktop on Windows (WSL2 backend) | Windows NVIDIA driver only |
| Docker Engine on Linux — or inside a WSL2 distro | Driver **and** the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) |
| From source, Windows or Linux | Driver only — the toolkit is a container-runtime component and is never needed here |
| Jetson Orin (either path) | Nothing; JetPack flashes the driver, CUDA and the container runtime together |

Driver floor for the CUDA 12.4 wheels is **551.61 on Windows** and **550.54 on Linux**. Older
drivers (528.33 / 525.60) often still work through CUDA minor-version compatibility, but aren't
worth relying on.

## Configuration

Both optional, and both apply however you started Simon.

### Footage recording (optional)

Simon can archive the raw camera stream to disk alongside detection, in 60-second segments
under `footage/`. This requires **ffmpeg on your `PATH`** (already present in the container).
ffmpeg stream-copies the segments (`-c copy`) rather than re-encoding them, so recording costs
almost no CPU and never touches the detection pipeline's own decode.

Recording is **RTSP-only**: the recorder is started only when the source is an `rtsp://` or
`rtsps://` URL. Camera-index and file sources record nothing.

A retention manager prunes `footage/` on an interval so it never grows without bound:

| Flag                    | Default | Meaning                                        |
| ----------------------- | ------- | ---------------------------------------------- |
| `--footage`             | `footage` | Directory holding recorded footage           |
| `--max-footage-gb`      | `10`    | Size budget in GB (`0` = unlimited)             |
| `--footage-ttl-hours`   | `24`    | Delete segments older than this (`0` = no TTL)  |
| `--footage-sweep-mins`  | `1`     | Minutes between cleanup sweeps                  |
| `--no-footage-cleanup`  | —       | Never delete footage autonomously  |

Under Docker these are set through the matching `SIMON_*` variables instead — see
[`SIMON_*` environment variables](#environment-variables).

### Telegram notifications (optional)

Simon can push alerts to a Telegram chat. This is optional though, without it the pipeline runs
normally.

#### 1. Create a bot

In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the
prompts. It replies with an HTTP API token, this is your `TELEGRAM_BOT_TOKEN`.

#### 2. Get your chat ID

Start a chat with your new bot and send it any message, then get your numeric chat ID either way:

- Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` (with your token) and read
  `result[].message.chat.id`, or
- Message [@userinfobot](https://t.me/userinfobot), which replies with your ID.

This is your `CHAT_ID`. For a group chat, add the bot to the group and use the group's chat id
(it will be negative).

#### 3. Create a `.env` file

In the project root, create a `.env` file. It's git-ignored, so
the secrets stay out of version control:

```
TELEGRAM_BOT_TOKEN=<YOUR_TOKEN_HERE>
CHAT_ID=<YOUR_ID_HERE>
```

`.env` is read once when the pipeline starts, so restart to pick it up — `docker compose up -d
--force-recreate <target>` for a container, or restart `server.py` when running from source.

#### Current notification behavior

Alerts are routed by each rule's `severity` (set in the Rule
Editor tab):

| Severity   | Telegram behavior                        |
| ---------- | ---------------------------------------- |
| `low`      | Not sent (recorded locally only)  |
| `high`     | Sent silently (no notification sound)    |
| `critical` | Sent with an audible notification        |

Those three are the only recognized values. A rule carrying anything else isn't rejected — it's
coerced to `high`, so a typo'd severity still fires, just at the default level.

## First run

Applies however you started Simon. Zone and rule configs live in `src/config/`; a fresh clone
starts with none. Until you create them, Simon runs in bypass mode: detection and tracking work,
but no rules fire and no alerts are sent. Create zones in the **Zone Editor** tab and rules in the
**Rule Editor** tab — saving writes the config and hot-reloads the running pipeline, no restart
needed.

## Planned
- Store only footage matching a user-defined rule (e.g. when a car is detected in the driveway)
- Video playback interface
- Support for multiple camera sources
