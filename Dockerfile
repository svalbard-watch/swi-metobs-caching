ARG PYTHON_VERSION=3.14
ARG APP_VERSION=3.X.X

# Stage 1: Dependency resolution
FROM astral/uv:python${PYTHON_VERSION}-bookworm-slim AS uv
WORKDIR /swi
COPY pyproject.toml uv.lock ./
# Export the locked, hashed set: the image installs exactly what uv.lock pins.
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt

# Stage 2: Build
FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /swi
COPY --from=uv /swi/requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Stage 3: Runtime, on the shared cron base image (swi-cron-base). It provides the unprivileged
# swi user (uid/gid 9001, shared with the other SWI images that use the same volumes), /swi, the
# run lock, the entrypoint and the healthcheck; see https://github.com/svalbard-watch/swi-cron-base
# Its tag must match the Python version of the builder stage above.
FROM ghcr.io/svalbard-watch/swi-cron-base:1.0.0-py3.14
ARG PYTHON_VERSION

# Git (for the station configuration) needs root; the base image ends with USER swi.
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy only necessary files from the builder stage
COPY --from=builder /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# prepare-config.sh clones the station configuration into ./config and the job writes into two
# volumes. Create the mount points owned by the job user: an empty named volume inherits the
# ownership of the directory it is mounted on, so a fresh volume is writable without any
# runtime chown.
RUN mkdir -p /swi/data/historical /swi/data/realtime \
    && chown -R swi:swi /swi/data

# Copy the current directory to /swi (the code stays owned by root: the job can create
# files here, not edit its own code)
COPY . .

# run-cron (from the base image) first refreshes the station configuration, then runs the job,
# one run at a time.
ENV SWI_CRON_PRE_COMMAND="bash /swi/prepare-config.sh" \
    SWI_CRON_COMMAND="python3 /swi/main.py"

USER swi
