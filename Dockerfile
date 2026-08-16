# syntax=docker/dockerfile:1

# BASE_IMAGE must be declared before the first FROM to be usable in a FROM line.
ARG BASE_IMAGE=python:3.13-slim

# ---------------------------------------------------------------------------
# Stage 1: build the React SPA
# ---------------------------------------------------------------------------
# node:24-alpine matches the host toolchain (Node 24.13.0 / npm 11.6.2) that
# generates web/package-lock.json for this Vite 8 + rolldown frontend. node:20-alpine's
# older npm (10.8.2) desyncs the optional rolldown WASM bindings and fails `npm ci`.
FROM node:24-alpine AS web
WORKDIR /web

# Copy manifests first so npm ci is cached independently of source changes.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE}

# Selects which torch to install. The jetson file is empty because the L4T base
# image already ships a torch built against that JetPack's CUDA.
ARG TORCH_REQS=requirements/torch-cpu.txt

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ffmpeg is required by VideoRecorder, which stream-copies RTSP to disk.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

# Torch first, in its own layer. If ultralytics is installed first, pip resolves
# torch from the default index and pulls the wrong wheel. This is also the slow
# layer and the one that changes least, so it caches well.
RUN pip3 install -r ${TORCH_REQS}

RUN pip3 install -r requirements/base.txt

# ultralytics hard-depends on the separately-named opencv-python distribution,
# so pip installs the GUI build alongside our headless one and the GUI build
# wins at import time. Re-assert headless last.
#
# NOTE: this pin duplicates requirements/base.txt's opencv-python-headless
# pin. The two must be bumped together — if they drift, the image ends up
# running a different headless build than the one base.txt installed and the
# version pytest was run against on the host.
RUN pip3 uninstall -y opencv-python \
 && pip3 install --force-reinstall opencv-python-headless==4.13.0.92

COPY src/ src/
COPY server.py ./
COPY --from=web /web/dist web/dist

EXPOSE 8000

# python:*-slim ships no curl, so use urllib rather than installing one for this.
# Assert pipeline_running, not just HTTP 200: /api/health returns 200 even when the
# detector thread has died (e.g. a bad models/ mount), so a status-only check can
# never fail. Docker restart policies act on exit, not health, so this cannot loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python3 -c "import json,urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3); sys.exit(0 if r.status==200 and json.load(r).get('pipeline_running') else 1)"

CMD ["python3", "server.py"]
