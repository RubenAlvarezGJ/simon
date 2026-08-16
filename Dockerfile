# syntax=docker/dockerfile:1

# Must be declared before the first FROM to be usable in a FROM line.
#
# A floating tag, unlike the digest-pinned node stage below: no lockfile is
# generated against this image and every Python dependency is already pinned in
# requirements/, so a patch bump cannot invalidate anything.
ARG BASE_IMAGE=python:3.13-slim

# ---------------------------------------------------------------------------
# Stage 1: build the React SPA
# ---------------------------------------------------------------------------
# Pinned by digest: npm resolves vite/rolldown's optional WASM bindings
# differently between versions, so a lockfile written by one npm can fail
# `npm ci` under another. This digest is the image web/package-lock.json was
# generated inside. To move to a newer one, regenerate the lockfile there first:
#
#   docker run --rm -v "$(pwd)/web:/web" -w /web node:24-alpine@<new-digest> \
#     sh -c "npm install --package-lock-only --no-audit --no-fund"
FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS web
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

# ultralytics pulls in opencv-python, a separate distribution from the headless
# build, and the GUI one wins at import time. Reinstalling headless last leaves
# only what this image needs.
#
# --no-deps is required: --force-reinstall alone re-resolves the whole graph,
# and opencv-python-headless's open-ended numpy>=1.26.0 would then override the
# exact numpy pinned in requirements/base.txt.
#
# This version duplicates base.txt's — change both together.
RUN pip3 uninstall -y opencv-python \
 && pip3 install --force-reinstall --no-deps opencv-python-headless==4.13.0.92

COPY src/ src/
COPY server.py ./
COPY --from=web /web/dist web/dist

EXPOSE 8000

# Checks the pipeline, not just the web server: /api/health answers 200 whenever
# uvicorn is up, including after the detector thread has died, so pipeline_running
# is the field that reports whether detection is alive. This only marks the
# container unhealthy — Docker restart policies act on exit, not health.
# urllib rather than curl, which the slim image does not ship.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python3 -c "import json,urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3); sys.exit(0 if r.status==200 and json.load(r).get('pipeline_running') else 1)"

CMD ["python3", "server.py"]
