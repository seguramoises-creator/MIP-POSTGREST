#!/usr/bin/env bash
# ===========================================================================
# VISTA · Laboratorios Mallén — certificado TLS para PostgreSQL
# ===========================================================================
# El §8.1 del Requerimiento de Datos exige que la integración conecte con
# `sslmode=require`. Sin TLS en el servidor, el ETL de Mallén falla al conectar.
#
# `sslmode=require` CIFRA pero NO VERIFICA la identidad del servidor, así que un
# certificado autofirmado es suficiente y es lo que genera este script. Si algún
# día se pasa a `verify-ca` o `verify-full`, hará falta un certificado emitido
# por una CA en la que confíe el servidor de SQL Server — y este script ya no
# sirve para eso.
#
# Correr en el SERVIDOR (Debian), desde la raíz del repo, ANTES de levantar el
# stack con el perfil with-db:
#     bash backend/scripts/integracion/generar_certificado_pg.sh
#
# El docker-compose detecta el certificado solo: si existe, arranca PostgreSQL
# con TLS; si no, arranca sin él.
# ===========================================================================
set -euo pipefail

DESTINO="${1:-certs/postgres}"
DIAS="${DIAS_VALIDEZ:-825}"     # 825 días: el máximo que aceptan los clientes modernos
CN="${CERT_CN:-vista-db}"

mkdir -p "$DESTINO"
ABS_DESTINO="$(cd "$DESTINO" && pwd)"

if [ -f "$DESTINO/server.key" ]; then
    echo "Ya existe $DESTINO/server.key — no se sobrescribe."
    echo "Si quieres regenerarlo, muévelo o bórralo primero (y reinicia el contenedor db)."
    exit 0
fi

# ---------------------------------------------------------------------------
# Se genera DENTRO de un contenedor postgres:17, no en el host. Dos razones:
#   1. No hace falta openssl instalado en el servidor.
#   2. PostgreSQL SE NIEGA A ARRANCAR si la clave privada tiene permisos laxos, y
#      el montaje conserva los del host: la clave debe quedar 0600 y propiedad
#      del uid 999 (el usuario `postgres` de la imagen oficial). Hacerlo desde
#      dentro evita necesitar `sudo` en el host — el contenedor ya corre como
#      root. Sin ese chown, el contenedor entra en bucle de reinicio con un
#      error poco evidente.
# ---------------------------------------------------------------------------
echo "Generando certificado autofirmado para PostgreSQL (CN=$CN, $DIAS días)..."
docker run --rm -v "$ABS_DESTINO:/certs" postgres:17 bash -c "
    openssl req -new -x509 -nodes -days $DIAS -subj '/CN=$CN' \
        -keyout /certs/server.key -out /certs/server.crt 2>/dev/null
    chmod 600 /certs/server.key
    chmod 644 /certs/server.crt
    chown 999:999 /certs/server.key /certs/server.crt
"

echo
echo "Listo:"
ls -l "$DESTINO"
echo
echo "Ahora reinicia la base para que tome el certificado:"
echo "    docker compose --profile with-db up -d db"
echo
echo "Y comprueba que quedó activo (debe imprimir 'on'):"
echo "    docker compose exec -T db psql -U \${DB_USER:-segura} -d \${DB_NAME:-scgcpr} -Atc 'SHOW ssl;'"
