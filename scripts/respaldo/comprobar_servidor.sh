#!/usr/bin/env bash
#
# comprobar_servidor.sh — ¿Este servidor puede recibir VISTA?
#
# Comprueba un servidor DESTINO contra la especificación de la sección 9 del
# "Requerimiento de Datos · VISTA · Laboratorios Mallén" y contra lo que el
# restaurador necesita para trabajar. Solo lee: no instala ni cambia nada.
#
#   Uso:  ./comprobar_servidor.sh [pruebas|produccion]
#
# Correrlo ANTES de mover el paquete de respaldo. Sirve igual para el ensayo en
# un servidor local que para validar la infraestructura que entregue Mallén.

set -uo pipefail   # sin -e: queremos ver TODAS las fallas, no morir en la primera

PERFIL="${1:-pruebas}"
if [ "$PERFIL" = "produccion" ]; then
    CPU_MIN=8;  RAM_MIN=16; DISCO_MIN=250
else
    CPU_MIN=4;  RAM_MIN=8;  DISCO_MIN=100
fi

FALLAS=0; AVISOS=0
ok()     { printf '  \033[32mOK    \033[0m %s\n' "$*"; }
falla()  { printf '  \033[31mFALLA \033[0m %s\n' "$*"; FALLAS=$((FALLAS+1)); }
aviso()  { printf '  \033[33mAVISO \033[0m %s\n' "$*"; AVISOS=$((AVISOS+1)); }
paso()   { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

printf '\033[1mComprobación de servidor para VISTA — perfil: %s\033[0m\n' "$PERFIL"
printf 'Requisitos: %s vCPU · %s GB RAM · %s GB disco (sección 9 del requerimiento)\n' \
       "$CPU_MIN" "$RAM_MIN" "$DISCO_MIN"

# --------------------------------------------------------------------------
paso "1. Sistema operativo y arquitectura"
# --------------------------------------------------------------------------
if [ -r /etc/os-release ]; then
    . /etc/os-release
    echo "         $PRETTY_NAME"
    case "$ID" in
        debian) [ "${VERSION_ID:-0}" -ge 13 ] 2>/dev/null \
                    && ok "Debian $VERSION_ID" \
                    || aviso "Debian $VERSION_ID — el requerimiento especifica Debian 13" ;;
        *)      aviso "$PRETTY_NAME — el requerimiento especifica Debian 13. Para un ensayo sirve; en Mallén, no." ;;
    esac
else
    falla "no se pudo identificar el sistema operativo"
fi

# La arquitectura es la trampa cara: las imágenes del respaldo se guardaron con
# 'docker save' para UNA arquitectura. En un servidor ARM no cargan, y el error
# aparece recién a mitad de la restauración.
ARQ="$(uname -m)"
case "$ARQ" in
    x86_64|amd64) ok "arquitectura $ARQ (la de las imágenes del respaldo)" ;;
    *) falla "arquitectura $ARQ — las imágenes del respaldo son amd64 y no correrán aquí" ;;
esac

# --------------------------------------------------------------------------
paso "2. Recursos"
# --------------------------------------------------------------------------
CPU="$(nproc 2>/dev/null || echo 0)"
[ "$CPU" -ge "$CPU_MIN" ] && ok "$CPU vCPU" || aviso "$CPU vCPU (se piden $CPU_MIN)"

RAM="$(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)"
[ "$RAM" -ge "$RAM_MIN" ] && ok "$RAM GB de RAM" || aviso "$RAM GB de RAM (se piden $RAM_MIN)"

DISCO="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
[ "${DISCO:-0}" -ge "$DISCO_MIN" ] && ok "$DISCO GB libres en /" \
    || aviso "$DISCO GB libres en / (se piden $DISCO_MIN)"
# La restauración necesita espacio para el .tar.gz, lo descomprimido y las
# imágenes ya cargadas en Docker: tres copias conviviendo un rato.
[ "${DISCO:-0}" -ge 20 ] || falla "menos de 20 GB libres: no alcanza ni para restaurar"

# --------------------------------------------------------------------------
paso "3. Docker"
# --------------------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
    V="$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    [ "${V%%.*}" -ge 24 ] 2>/dev/null && ok "Docker Engine $V" \
        || aviso "Docker $V — el requerimiento pide 24 o superior"
    if docker compose version >/dev/null 2>&1; then
        ok "Docker Compose v2 ($(docker compose version --short 2>/dev/null))"
    else
        falla "falta Docker Compose v2 (el plugin 'docker compose', no 'docker-compose')"
    fi
    # Que el binario exista no significa que se pueda usar: si el usuario no
    # está en el grupo docker, todo el restaurador falla con "permission denied".
    if docker ps >/dev/null 2>&1; then
        ok "el demonio responde y este usuario puede usarlo"
    else
        falla "no se puede hablar con el demonio: ¿está corriendo? ¿este usuario está en el grupo 'docker'?"
    fi
else
    falla "Docker no está instalado"
fi

# --------------------------------------------------------------------------
paso "4. Herramientas que usa el restaurador"
# --------------------------------------------------------------------------
for h in git tar gzip sha256sum mktemp awk sed; do
    command -v "$h" >/dev/null 2>&1 && ok "$h" || falla "falta $h"
done

# --------------------------------------------------------------------------
paso "5. Puertos"
# --------------------------------------------------------------------------
ocupado() {
    if command -v ss >/dev/null 2>&1; then ss -ltn 2>/dev/null | grep -q ":$1 "
    else netstat -ltn 2>/dev/null | grep -q ":$1 "; fi
}
for p in 80 443; do
    ocupado "$p" && aviso "puerto $p ocupado (lo usará el servidor web del host)" \
                 || ok "puerto $p libre"
done
ocupado 8090 && aviso "puerto 8090 ocupado (es el interno del contenedor web)" \
             || ok "puerto 8090 libre"
# 5432 es donde escribirá Mallén. Que esté ocupado aquí solo importa si hay otro
# PostgreSQL en el host: el del stack NO se publica, vive en la red de Docker.
ocupado 5432 && aviso "puerto 5432 ocupado — hay otro PostgreSQL en el host (no impide el stack)" \
             || ok "puerto 5432 libre"

# --------------------------------------------------------------------------
paso "6. Entorno"
# --------------------------------------------------------------------------
TZ_ACTUAL="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo '?')"
echo "         zona horaria: $TZ_ACTUAL"
[ "$TZ_ACTUAL" = "America/Santo_Domingo" ] \
    && ok "zona horaria del país de operación" \
    || aviso "el requerimiento (9.4) pide la zona del país de operación: America/Santo_Domingo"

locale 2>/dev/null | grep -qi 'utf-8' && ok "locale UTF-8" \
    || aviso "locale sin UTF-8 — la carga de Mallén viaja en UTF-8 (sección 5.1)"

# --------------------------------------------------------------------------
echo ""
if [ "$FALLAS" -eq 0 ] && [ "$AVISOS" -eq 0 ]; then
    printf '\033[32mSERVIDOR APTO — se puede restaurar VISTA aquí.\033[0m\n'
elif [ "$FALLAS" -eq 0 ]; then
    printf '\033[33mSERVIDOR APTO CON %s AVISO(S).\033[0m\n' "$AVISOS"
    echo "Los avisos no impiden restaurar; para un ensayo se puede seguir."
    echo "En el servidor de Mallén sí hay que resolverlos: son la especificación acordada."
else
    printf '\033[31m%s FALLA(S) — resolver antes de restaurar.\033[0m\n' "$FALLAS"
    exit 1
fi
