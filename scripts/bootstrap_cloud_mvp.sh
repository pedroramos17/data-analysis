#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.cloud ]; then
  cp .env.cloud.example .env.cloud
  printf '%s\n' 'Created .env.cloud from .env.cloud.example; edit secrets before public deployment.'
fi

COMPOSE_PROFILES=minio,scheduler CLOUD_ENV_FILE=.env.cloud docker compose --env-file .env.cloud -f docker-compose.cloud-mvp.yml up -d --build
CLOUD_ENV_FILE=.env.cloud docker compose --env-file .env.cloud -f docker-compose.cloud-mvp.yml exec app python manage.py migrate
CLOUD_ENV_FILE=.env.cloud docker compose --env-file .env.cloud -f docker-compose.cloud-mvp.yml exec app alembic -c alembic.ini upgrade head
CLOUD_ENV_FILE=.env.cloud docker compose --env-file .env.cloud -f docker-compose.cloud-mvp.yml exec app python manage.py check

printf '%s\n' 'Cloud MVP stack is running. Check /healthz/ before exposing traffic.'
