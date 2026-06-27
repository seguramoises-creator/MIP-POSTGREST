#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# MSM / SCGCPR — Instalar el backend como servicio systemd (Linux)
# ═══════════════════════════════════════════════════════════════════
# Uso (como root o con sudo):
#   sudo ./instalar_servicio_backend.sh [/ruta/al/proyecto]
#
# Por defecto asume que el proyecto se despliega en /opt/msm con la
# estructura:  /opt/msm/backend  y  /opt/msm/frontend
#
# Qué hace:
#   1. Crea el usuario de servicio "msm" (sin login) si no existe
#   2. Crea el entorno virtual en backend/venv e instala requirements.txt
#   3. Crea backend/logs
#   4. Copia msm-backend.service a /etc/systemd/system/
#   5. Habilita e inicia el servicio
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PROYECTO_DIR="${1:-/opt/msm}"
SERVICE_USER="msm"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: ejecute este script con sudo/root." >&2
    exit 1
fi

BACKEND_DIR="$PROYECTO_DIR/backend"
if [[ ! -d "$BACKEND_DIR" ]]; then
    echo "ERROR: no se encontró $BACKEND_DIR" >&2
    exit 1
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    echo "ADVERTENCIA: no existe $BACKEND_DIR/.env" >&2
    echo "Copie backend/.env.production.example a backend/.env y edítelo antes de continuar." >&2
    exit 1
fi

echo "[1/5] Creando usuario de servicio '$SERVICE_USER' (si no existe)..."
id -u "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"

echo "[2/5] Creando entorno virtual e instalando dependencias..."
if [[ ! -d "$BACKEND_DIR/venv" ]]; then
    python3 -m venv "$BACKEND_DIR/venv"
fi
"$BACKEND_DIR/venv/bin/pip" install --upgrade pip
"$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

echo "[3/5] Preparando carpeta de logs y permisos..."
mkdir -p "$BACKEND_DIR/logs" "$BACKEND_DIR/uploads" "$BACKEND_DIR/processed" "$BACKEND_DIR/errors" "$BACKEND_DIR/reports"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$PROYECTO_DIR"

echo "[4/5] Instalando unidad systemd..."
sed "s#/opt/msm#$PROYECTO_DIR#g" "$SCRIPT_DIR/msm-backend.service" > /etc/systemd/system/msm-backend.service
systemctl daemon-reload

echo "[5/5] Habilitando e iniciando el servicio..."
systemctl enable msm-backend
systemctl restart msm-backend

sleep 2
systemctl status msm-backend --no-pager || true

echo ""
echo "Verifique: curl -s http://127.0.0.1:8000/health"
echo "Logs:      journalctl -u msm-backend -f"
echo "           tail -f $BACKEND_DIR/logs/service_stderr.log"
