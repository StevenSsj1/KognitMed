# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY src/ ./src/

RUN uv sync --no-dev --no-editable

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Run as non-root user
RUN groupadd -r kognitmed && useradd -r -g kognitmed kognitmed

WORKDIR /app

# Copy only the installed packages and app source
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src

# Ensure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER kognitmed

EXPOSE 8000

CMD ["uvicorn", "kognitmed.main:app", "--host", "0.0.0.0", "--port", "8000"]
