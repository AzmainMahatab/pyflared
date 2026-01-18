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
RUN uv run scripts/build.py

# ============================================================================
# Final Stage - Using Alpine for smaller image size
# The wheel uses generic linux_* tag which pip can install anywhere.
# ============================================================================
FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app

COPY --from=builder /app/dist/*.whl ./

# Install the generic linux wheel - works on any Linux since cloudflared is static
RUN set -ex; \
    ARCH=$(uname -m); \
    pip install --no-cache-dir ./*linux_${ARCH}*.whl; \
    rm -f *.whl

ENTRYPOINT ["pyflared"]
CMD ["--help"]