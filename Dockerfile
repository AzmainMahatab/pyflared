# Setup Environment
FROM python:3.12-slim-bookworm AS builder
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Set PATH so that 'hatch' is found immediately after install
#ENV PATH="/root/.local/bin:$PATH"
# Install Build Tools BEFORE copying source code
# This layer will now be cached forever, regardless of code changes.
# RUN uv tool install hatch
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

FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
#ENV PATH="/root/.local/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/dist/*.whl ./
#RUN uv tool install ./*linux*.whl
RUN uv pip install --system ./*linux*.whl
RUN rm *.whl # Remove whls to save image size
ENTRYPOINT ["pyflared"]
CMD ["--help"]