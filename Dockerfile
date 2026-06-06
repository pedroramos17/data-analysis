FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=public_monitor.settings

ARG REQUIREMENTS_FILE=requirements.txt

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r "${REQUIREMENTS_FILE}"

COPY . .

RUN mkdir -p /app/data/lake /app/media /app/exports /app/models \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz/ || exit 1

CMD ["sh", "-c", "gunicorn public_monitor.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --access-logfile - --error-logfile -"]
