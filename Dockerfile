# Setup Environment
FROM python:3.12-slim-bookworm AS builder
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Set PATH so that 'hatch' is found immediately after install
ENV PATH="/root/.local/bin:$PATH"
# Install Build Tools BEFORE copying source code
# This layer will now be cached forever, regardless of code changes.
RUN uv tool install hatch

WORKDIR /app

# Define the Build Argument (Default: false)
ARG USE_PREBUILT_WHEEL=false

# Copy Context (Code changes reflect here). All layers before it will be cached regardless of code changes
COPY . .

# The Conditional Build Script
RUN if [ "$USE_PREBUILT_WHEEL" = "true" ]; then \
        echo "🔹 MODE: PRE-BUILT ARTIFACT DETECTED"; \
        if ! ls dist/*.whl >/dev/null 2>&1; then \
            echo "❌ ERROR: No .whl files found in dist/."; \
            exit 1; \
        fi; \
        echo "✅ Valid artifact found."; \
    else \
        echo "🔸 MODE: BUILD FROM SOURCE"; \
        # 'hatch' is already installed and cached from the step above! \
        hatch build; \
    fi

FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV PATH="/root/.local/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/dist/*.whl ./
RUN uv tool install ./*linux*.whl
RUN rm *.whl # Remove whls to save image size
ENTRYPOINT ["pyflared"]
CMD ["--help"]