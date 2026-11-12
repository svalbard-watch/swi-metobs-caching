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

# Stage 3: Runtime
FROM python:${PYTHON_VERSION}-slim
ARG APP_VERSION
ARG PYTHON_VERSION
# The project reserves uids above 9000. Every SWI image that shares a volume with this one
# (the other cron jobs, mapproxy, the read-only data services) uses the same uid and gid,
# so files written here are owned by the same user everywhere.
ARG APP_UID=9001
ARG APP_GID=9001
WORKDIR /swi

# Apply the Debian security updates published since the base image was built (e.g. zlib1g
# CVE-2026-76844 and CVE-2026-85091 are fixed in 1.3.1-1+deb13u1), then install Git.
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Copy only necessary files from the builder stage
COPY --from=builder /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# The job never installs packages at runtime: remove pip (and its vendored copies of
# urllib3, msgpack, ...) so they are neither exposed nor flagged by image scanners.
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null || true

# Unprivileged user with a home directory (git and entrypoint.sh write there)
RUN groupadd --gid "${APP_GID}" swi \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin swi

# run-cron.sh clones the station configuration into ./config and the job writes into two
# volumes. Create the mount points owned by the job user: an empty named volume inherits the
# ownership of the directory it is mounted on, so a fresh volume is writable without any
# runtime chown.
RUN mkdir -p /swi/data/historical /swi/data/realtime \
    && chown -R swi:swi /swi

# Copy the current directory to /swi (the code stays owned by root: the job can create
# files here, not edit its own code)
COPY . .

# Make the entrypoint scripts executable
RUN chmod +x /swi/entrypoint.sh /swi/run-cron.sh

USER swi

# Use the entrypoint script - supports DOCKER_CRON=1 to stay alive between runs so an
# external scheduler can re-trigger the job via `docker exec <container> run-cron`
ENTRYPOINT ["./entrypoint.sh"]

