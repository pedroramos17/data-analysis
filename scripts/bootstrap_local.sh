#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
fi

docker compose -f docker-compose.local.yml up -d --build app
docker compose -f docker-compose.local.yml exec app python manage.py migrate
docker compose -f docker-compose.local.yml exec app alembic -c alembic.ini upgrade head
docker compose -f docker-compose.local.yml exec app python manage.py seed_dev_admin --show-credentials

printf '%s\n' 'Local MVP is available at http://127.0.0.1:8000/'
