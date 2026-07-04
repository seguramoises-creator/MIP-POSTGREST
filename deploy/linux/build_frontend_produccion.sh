#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# MSM / SCGCPR — Build de producción del frontend (Linux/nginx)
# ═══════════════════════════════════════════════════════════════════
# Uso:
#   ./build_frontend_produccion.sh [/ruta/al/proyecto] [https://vista-mip.com]
#
# Qué hace:
#   1. Escribe frontend/.env.production con VITE_API_URL=<dominio>/api/v1
#   2. Ejecuta npm install (si falta node_modules) y npm run build
#   3. Deja el resultado en frontend/dist (nginx lo sirve directo, ver
#      deploy/linux/nginx_vista-mip.com.conf -> root /opt/msm/frontend/dist)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PROYECTO_DIR="${1:-/opt/msm}"
DOMINIO_PUBLICO="${2:-https://vista-mip.com}"
FRONTEND_DIR="$PROYECTO_DIR/frontend"

if [[ ! -d "$FRONTEND_DIR" ]]; then
    echo "ERROR: no se encontró $FRONTEND_DIR" >&2
    exit 1
fi

echo "[1/3] Escribiendo $FRONTEND_DIR/.env.production ..."
echo "VITE_API_URL=${DOMINIO_PUBLICO}/api/v1" > "$FRONTEND_DIR/.env.production"

echo "[2/3] Compilando frontend (npm run build)..."
cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
    npm install
fi
npm run build

if [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
    echo "ERROR: el build no generó dist/index.html" >&2
    exit 1
fi

echo "[3/3] Listo. Build publicado en $FRONTEND_DIR/dist"
echo "Recargue nginx si ya estaba corriendo: sudo systemctl reload nginx"
