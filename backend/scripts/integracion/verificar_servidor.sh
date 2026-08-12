#!/usr/bin/env bash
# Verifica si un servidor cumple los requisitos de VISTA (§9 del Requerimiento
# de Datos · VISTA · Laboratorios Mallén).
#
# SOLO LEE. No instala, no modifica configuración, no abre puertos.
# Se puede correr las veces que haga falta y con el sistema en uso.
#
#   bash verificar_servidor.sh              # ambiente de calidad (por defecto)
#   bash verificar_servidor.sh produccion   # exige el dimensionamiento mayor
#
# Algunas comprobaciones necesitan root (reglas de firewall, unidades de disco).
# Sin sudo el script sigue y marca esos puntos como "no verificable", nunca los
# da por buenos.

set -uo pipefail

AMBIENTE="${1:-calidad}"
if [ "$AMBIENTE" = "produccion" ]; then
    MIN_CPU=8; MIN_RAM_GB=16; MIN_DISCO_GB=250
else
    MIN_CPU=4; MIN_RAM_GB=8;  MIN_DISCO_GB=100
fi

OK=0; ADV=0; MAL=0; SIN=0

c_ok()  { printf '  \033[32m[ OK ]\033[0m  %s\n' "$1"; OK=$((OK+1)); }
c_adv() { printf '  \033[33m[AVISO]\033[0m %s\n' "$1"; ADV=$((ADV+1)); }
c_mal() { printf '  \033[31m[FALLA]\033[0m %s\n' "$1"; MAL=$((MAL+1)); }
c_sin() { printf '  \033[90m[ ?  ]\033[0m  %s\n' "$1"; SIN=$((SIN+1)); }
titulo(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

puedo_root() { [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; }

printf '\033[1mVerificación de servidor para VISTA — ambiente: %s\033[0m\n' "$AMBIENTE"
printf 'Host: %s   Fecha: %s\n' "$(hostname)" "$(date -Is)"

# ── §9.1 Dimensionamiento ────────────────────────────────────────────────────
titulo "§9.1 Dimensionamiento (mínimo para $AMBIENTE: ${MIN_CPU} vCPU, ${MIN_RAM_GB} GB RAM, ${MIN_DISCO_GB} GB disco)"

CPU=$(nproc 2>/dev/null || echo 0)
[ "$CPU" -ge "$MIN_CPU" ] \
    && c_ok "Procesador: ${CPU} vCPU" \
    || c_mal "Procesador: ${CPU} vCPU — se requieren ${MIN_CPU}"

RAM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
[ "$RAM_GB" -ge "$MIN_RAM_GB" ] \
    && c_ok "Memoria: ${RAM_GB} GB" \
    || c_mal "Memoria: ${RAM_GB} GB — se requieren ${MIN_RAM_GB} GB"

# El disco que importa es el que aloja los volúmenes de Docker, no siempre /.
DIR_DOCKER=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
[ -d "$DIR_DOCKER" ] || DIR_DOCKER=/var
DISCO_GB=$(df -BG --output=size "$DIR_DOCKER" 2>/dev/null | tail -1 | tr -dc '0-9')
LIBRE_GB=$(df -BG --output=avail "$DIR_DOCKER" 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "${DISCO_GB:-}" ] && [ "$DISCO_GB" -ge "$MIN_DISCO_GB" ]; then
    c_ok "Disco en ${DIR_DOCKER}: ${DISCO_GB} GB totales, ${LIBRE_GB} GB libres"
elif [ -n "${DISCO_GB:-}" ]; then
    c_mal "Disco en ${DIR_DOCKER}: ${DISCO_GB} GB — se requieren ${MIN_DISCO_GB} GB"
else
    c_sin "Disco: no se pudo medir ${DIR_DOCKER}"
fi

# SSD vs disco mecánico: 0 = SSD/NVMe, 1 = rotacional.
DISPO=$(df --output=source "$DIR_DOCKER" 2>/dev/null | tail -1 | sed 's|/dev/||; s|[0-9]*$||; s|p$||')
ROT="/sys/block/${DISPO}/queue/rotational"
if [ -r "$ROT" ]; then
    [ "$(cat "$ROT")" = "0" ] \
        && c_ok "Almacenamiento: SSD/NVMe (${DISPO})" \
        || c_adv "Almacenamiento: disco rotacional (${DISPO}) — el §9.1 pide SSD"
else
    c_sin "Almacenamiento: no se pudo determinar si es SSD (normal en virtualizados)"
fi

# ── Sistema operativo ────────────────────────────────────────────────────────
titulo "Sistema operativo (§9.1: Debian 13)"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    if [ "${ID:-}" = "debian" ] && [ "${VERSION_ID:-}" = "13" ]; then
        c_ok "Sistema: ${PRETTY_NAME}"
    elif [ "${ID:-}" = "debian" ]; then
        c_adv "Sistema: ${PRETTY_NAME} — el §9.1 especifica Debian 13"
    else
        c_adv "Sistema: ${PRETTY_NAME} — el §9.1 especifica Debian 13; VISTA corre en contenedores, así que otra distribución suele funcionar, pero se sale de lo acordado"
    fi
else
    c_sin "Sistema: sin /etc/os-release"
fi

TZ_ACT=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "desconocida")
if [ "$TZ_ACT" = "UTC" ] || [ "$TZ_ACT" = "Etc/UTC" ]; then
    c_adv "Zona horaria: ${TZ_ACT} — el §9.4 pide la del país de operación (p. ej. America/Santo_Domingo)"
else
    c_ok "Zona horaria: ${TZ_ACT} (§9.4)"
fi

# ── §9.1 y §9.2 Docker ───────────────────────────────────────────────────────
titulo "§9.1/§9.2 Contenedores (Docker Engine 24+ y Compose v2)"

if command -v docker >/dev/null 2>&1; then
    DV=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "")
    if [ -n "$DV" ]; then
        MAYOR=${DV%%.*}
        [ "$MAYOR" -ge 24 ] 2>/dev/null \
            && c_ok "Docker Engine ${DV}" \
            || c_mal "Docker Engine ${DV} — se requiere 24 o superior"
    else
        c_mal "Docker instalado pero el demonio no responde (¿servicio detenido, o falta permiso?)"
    fi

    # Lo que exige el §9.1 es el PLUGIN (`docker compose`, subcomando), no la
    # herramienta vieja `docker-compose`. El número no sirve para decidirlo:
    # Debian numera su paquete aparte de upstream (p. ej. 5.1.4), así que
    # comparar contra "2" daría un falso negativo. Lo que se comprueba es que el
    # subcomando exista y responda.
    CV=$(docker compose version --short 2>/dev/null || echo "")
    if [ -n "$CV" ]; then
        c_ok "Docker Compose como plugin — 'docker compose' responde (versión del paquete: ${CV})"
    elif command -v docker-compose >/dev/null 2>&1; then
        c_mal "Solo está el docker-compose antiguo — el §9.1 requiere el plugin 'docker compose' (v2)"
    else
        c_mal "Falta Docker Compose (plugin v2)"
    fi

    docker ps >/dev/null 2>&1 \
        && c_ok "El usuario '$(id -un)' puede usar Docker sin sudo" \
        || c_adv "El usuario '$(id -un)' NO puede usar Docker sin sudo — el despliegue pedirá contraseña en cada paso"
else
    c_mal "Docker no está instalado"
fi

# ── §9.2 PostgreSQL ──────────────────────────────────────────────────────────
titulo "§9.2 Base de datos (PostgreSQL 17 en contenedor con volumen persistente)"

if docker image inspect postgres:17 >/dev/null 2>&1; then
    c_ok "La imagen postgres:17 ya está en el servidor"
elif docker pull --quiet postgres:17 >/dev/null 2>&1; then
    c_ok "La imagen postgres:17 se puede descargar (hay salida a un registro)"
else
    c_adv "No se pudo obtener postgres:17 — si el servidor no tiene salida a internet, las imágenes hay que transportarlas con 'docker save'/'docker load'"
fi

PG_HOST=$(command -v psql >/dev/null 2>&1 && psql --version 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo "")
if [ -n "$PG_HOST" ]; then
    c_adv "Hay un PostgreSQL ${PG_HOST} instalado en el host además del contenedor — revisa que no ocupe el 5432 (ver la sección de puertos)"
fi

# ── §9.3 Red y puertos ───────────────────────────────────────────────────────
titulo "§9.3 Red y puertos"

# `ss`/`netstat` solo revelan QUÉ proceso escucha si se corre como root; sin
# privilegio la columna sale vacía. Se intenta con sudo para poder nombrarlo:
# decir "ocupado por ''" obliga al administrador a investigar por su cuenta.
if command -v ss >/dev/null 2>&1; then
    if puedo_root; then ESCUCHA=$(sudo -n ss -Hlntp 2>/dev/null); else ESCUCHA=$(ss -Hlntp 2>/dev/null); fi
else
    if puedo_root; then ESCUCHA=$(sudo -n netstat -lntp 2>/dev/null); else ESCUCHA=$(netstat -lntp 2>/dev/null); fi
fi

ocupado() { printf '%s\n' "$ESCUCHA" | grep -qE "[:.]$1[[:space:]]"; }
quien() {
    local p
    p=$(printf '%s\n' "$ESCUCHA" | grep -E "[:.]$1[[:space:]]" \
        | grep -oE '"[^"]+"' | head -1 | tr -d '"')
    [ -n "$p" ] && printf 'por %s' "$p" || printf 'por un proceso no identificable sin root'
}

for P in 80 443; do
    if ocupado "$P"; then
        c_adv "Puerto ${P} ocupado $(quien "$P") — el servidor web del host debe terminar el TLS ahí (§9.2); confirma que sea ese servicio y no otro"
    else
        c_ok "Puerto ${P} libre para el servidor web del host"
    fi
done

if ocupado 5432; then
    c_mal "Puerto 5432 YA OCUPADO $(quien 5432). Es el puerto por el que Mallén escribe la integración (§9.3): hay que liberarlo, o publicar el contenedor en otro puerto y acordarlo con ellos. Este conflicto ya rompió un despliegue antes."
else
    c_ok "Puerto 5432 libre para la base de VISTA"
fi

ocupado 22 && c_ok "SSH escuchando (§9.3: solo desde la VPN)" \
           || c_adv "No se detecta SSH en el 22 — ¿administración por otro puerto?"

# La cadena DOCKER-USER es la única que Docker respeta: ufw NO filtra el
# tráfico a puertos publicados por contenedores.
if puedo_root; then
    REGLAS=$(sudo -n iptables -S DOCKER-USER 2>/dev/null | grep -c 5432 || true)
    if [ "${REGLAS:-0}" -gt 0 ]; then
        c_ok "Hay ${REGLAS} regla(s) en DOCKER-USER para el 5432"
    else
        c_adv "Sin reglas en DOCKER-USER para el 5432 — el §9.3 exige que solo lo alcance la IP del SQL Server. OJO: ufw NO sirve aquí, Docker se salta sus reglas"
    fi
    command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active" \
        && c_adv "ufw está activo: recuerda que NO filtra los puertos publicados por Docker; usa DOCKER-USER"
else
    c_sin "Reglas de firewall: hace falta root para leerlas"
fi

# ── §9.4 Requisitos adicionales ──────────────────────────────────────────────
titulo "§9.4 Requisitos adicionales"

SMTP_OK=0
for HP in "smtp.gmail.com 587" "smtp.office365.com 587"; do
    set -- $HP
    if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$1/$2" 2>/dev/null; then
        c_ok "Salida SMTP disponible ($1:$2)"
        SMTP_OK=1; break
    fi
done
[ "$SMTP_OK" -eq 0 ] && c_adv "Sin salida SMTP a los proveedores probados — el §9.4 pide servidor de correo saliente o cuenta SMTP para las notificaciones. Puede ser un relay interno: confírmalo con Mallén"

if timeout 5 bash -c "cat < /dev/null > /dev/tcp/1.1.1.1/443" 2>/dev/null; then
    c_ok "El servidor tiene salida a internet"
else
    c_adv "Sin salida a internet — las imágenes de Docker habrá que transportarlas, y el certificado TLS no podrá renovarse solo"
fi

printf '\n\033[1mResumen: %d OK · %d avisos · %d fallas · %d no verificables\033[0m\n' "$OK" "$ADV" "$MAL" "$SIN"
if [ "$MAL" -gt 0 ]; then
    printf 'Hay requisitos INCUMPLIDOS. El despliegue no debería empezar hasta resolverlos.\n'
    exit 1
fi
printf 'Sin incumplimientos. Revisa los avisos antes de desplegar.\n'
