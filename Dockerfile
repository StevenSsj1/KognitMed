# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY doc/ ./doc/

RUN uv sync --no-dev --no-editable --link-mode=copy

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Run as non-root user
RUN groupadd -r kognitmed && useradd -r -g kognitmed kognitmed

WORKDIR /app

# Copy the venv and fix the Python path
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src
COPY --from=builder /build/doc /app/doc

# Re-link venv Python and create chroma data directory
RUN ln -sf /usr/local/bin/python3 /app/.venv/bin/python3 && \
    ln -sf /usr/local/bin/python3 /app/.venv/bin/python && \
    mkdir -p /app/.chroma && chown -R kognitmed:kognitmed /app/.chroma

# Ensure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER kognitmed

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "kognitmed.main:app", "--host", "0.0.0.0", "--port", "8000"]
