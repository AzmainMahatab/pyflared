# 1. Setup Environment
FROM python:3.12-slim-bookworm AS builder
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

WORKDIR /app

# 2. Define the Build Argument (Default: false)
ARG USE_PREBUILT_WHEEL=false

# 3. Copy Context
# We copy everything so we have source code (if building) OR dist folder (if pre-built)
# Ensure 'dist' is NOT in .dockerignore
COPY . .

# 4. The Conditional Build Script
# This logic decides whether to run 'hatch build' or simply verify existing files.
RUN if [ "$USE_PREBUILT_WHEEL" = "true" ]; then \
        echo "🔹 MODE: PRE-BUILT ARTIFACT DETECTED"; \
        echo "   Verifying artifact existence..."; \
        # Check if any wheel exists in dist folder \
        if ! ls dist/*.whl >/dev/null 2>&1; then \
            echo "❌ ERROR: USE_PREBUILT_WHEEL=true was set, but no .whl files found in dist/."; \
            echo "   Did you forget to download the artifact in CI?"; \
            exit 1; \
        fi; \
        echo "✅ Valid artifact found."; \
    else \
        echo "🔸 MODE: BUILD FROM SOURCE"; \
        uv pip install --system hatch; \
        hatch build; \
    fi

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app

# 1. Copy ONLY the wheel from the builder stage
# Regardless of how it got there (built vs copied), it is now in /app/dist
COPY --from=builder /app/dist/*.whl ./

# 2. Install the wheel
# Using *.whl allows version-agnostic installation
#RUN uv pip install --system --no-cache *.whl
RUN uv tool install ./*linux*.whl

# 3. Cleanup & Run
RUN rm *.whl

RUN pyflared version

ENTRYPOINT ["pyflared"]
CMD ["version"]