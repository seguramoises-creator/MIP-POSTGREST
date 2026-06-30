#!/bin/sh
# Entrypoint del backend: corre migraciones Alembic (si RUN_MIGRATIONS=1, por
# defecto) y luego ejecuta el comando (uvicorn). No bloquea el arranque si las
# migraciones fallan (p. ej. BD aún levantando) — se pueden re-correr a mano.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] Aplicando migraciones: alembic upgrade head…"
  python -m alembic upgrade head || \
    echo "[entrypoint] AVISO: las migraciones fallaron (¿BD lista?). Continúo; córrelas con: docker compose exec backend python -m alembic upgrade head"
fi

exec "$@"
