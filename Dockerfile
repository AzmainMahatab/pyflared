# Setup Environment
FROM python:3.12-slim-bookworm AS builder
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Install Build Tools BEFORE copying source code
# This layer will now be cached forever, regardless of code changes.
RUN uv pip install --system hatch

WORKDIR /app

# Define the Build Argument (Default: false)
ARG USE_PREBUILT_WHEEL=false
# Set it as ENV so Python can read it
ENV USE_PREBUILT_WHEEL=$USE_PREBUILT_WHEEL

# Copy Context (Code changes reflect here). All layers before it will be cached regardless of code changes
COPY . .

# python build script instead of Bash logic
RUN python scripts/build.py

# ============================================================================
# Final Stage
# ============================================================================
FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app

COPY --from=builder /app/dist/*.whl ./

# Dynamically detect architecture and install the matching wheel
# uname -m returns: x86_64, aarch64, armv7l, etc.
RUN set -ex; \
    ARCH=$(uname -m); \
    uv pip install --system ./*manylinux*${ARCH}*.whl; \
    rm -f *.whl

ENTRYPOINT ["pyflared"]
CMD ["--help"]