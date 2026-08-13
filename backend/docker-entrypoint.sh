#!/bin/sh
# Entrypoint del backend:
#   1. Espera a que la BD responda (arranque en paralelo con el contenedor de PG).
#   2. Corre las migraciones Alembic (si RUN_MIGRATIONS=1, por defecto).
#   3. En una instalación NUEVA, siembra la matriz de autorización.
#   4. Ejecuta el comando (uvicorn).
#
# ANTES esto hacía `alembic upgrade head || echo AVISO` y arrancaba igual. Eso
# convierte una instalación fallida en una aplicación que responde: la API queda
# en pie contra una base incompleta y el fallo es una línea de log que nadie
# lee. Al instalar en el servidor de un cliente, eso es lo peor que puede pasar
# — parece que funcionó. Ahora se distingue "la BD todavía no está lista"
# (se reintenta) de "la migración falló" (se aborta el arranque).
set -e

ESPERA_MAX="${DB_ESPERA_MAX:-30}"   # intentos de ~2s antes de rendirse

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] Esperando a la base de datos…"
  i=0
  until python -c "
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings
try:
    create_engine(settings.DATABASE_URL).connect().execute(text('SELECT 1'))
except Exception as e:
    print(e, file=sys.stderr); sys.exit(1)
" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge "$ESPERA_MAX" ]; then
      echo "[entrypoint] ERROR: la base de datos no respondió tras $((ESPERA_MAX * 2))s. Abortando." >&2
      exit 1
    fi
    sleep 2
  done
  echo "[entrypoint] Base de datos lista."

  echo "[entrypoint] Aplicando migraciones: alembic upgrade head…"
  if ! python -m alembic upgrade head; then
    echo "[entrypoint] ERROR: las migraciones fallaron. NO se arranca la API contra una base incompleta." >&2
    echo "[entrypoint] Revisa el error de arriba y vuelve a intentar con:" >&2
    echo "[entrypoint]   docker compose exec backend python -m alembic upgrade head" >&2
    exit 1
  fi

  # Siembra de la matriz RBAC, SOLO en una instalación nueva.
  #
  # Hace falta porque una matriz PARCIAL es peor que una vacía: el motor solo
  # cae a los valores de fábrica cuando la tabla está completamente vacía
  # (authz/runtime.py). Las migraciones dejan 3 de los 35 recursos sembrados, y
  # con esas 3 filas el caché ya no está vacío: todo lo demás queda denegado
  # para todos, en silencio y sin ningún error.
  #
  # La condición NO puede ser "DIM_Recurso vacía" (nunca lo está tras migrar) ni
  # "faltan recursos del código" (volvería a correr al añadir uno nuevo). Se usa
  # "no hay usuarios": nadie pudo personalizar permisos sin poder entrar. Es lo
  # que hace la siembra segura, porque `sembrar_todo` sincroniza con borrado y
  # una denegación se representa por AUSENCIA de fila — correrla sobre una
  # matriz ya ajustada volvería a conceder lo que alguien revocó a propósito.
  if python -c "
import sys
from app.db.database import SessionLocal
from app.models.usuario import Usuario
db = SessionLocal()
try:
    sys.exit(0 if db.query(Usuario).count() == 0 else 1)
finally:
    db.close()
" 2>/dev/null; then
    echo "[entrypoint] Instalación nueva: sembrando la matriz de autorización…"
    python scripts/seed_authz.py
  fi
fi

exec "$@"
