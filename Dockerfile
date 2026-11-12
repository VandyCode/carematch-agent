# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install runtime dependencies first for Docker layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir pydantic fastapi "uvicorn[standard]" python-dotenv httpx pyyaml opentelemetry-api opentelemetry-sdk

# Copy application source
COPY app ./app
COPY tools.py memory.py README.md LICENSE ./

# Run as a non-root user for container security hardening
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8000"]
