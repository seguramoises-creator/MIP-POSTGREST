#!/usr/bin/env bash
#
# verificar_respaldo.sh — Comprueba que un respaldo esta completo y sano SIN
# restaurarlo. Correrlo al terminar el respaldo y otra vez antes de moverlo:
# un paquete corrupto solo se descubre al necesitarlo, que es el peor momento.
#
#   Uso:  ./verificar_respaldo.sh [carpeta_del_respaldo]

set -euo pipefail

RESPALDO="${1:-$(cd "$(dirname "$0")" && pwd)}"
FALLOS=0

rojo()  { printf '\033[31m  FALLA  %s\033[0m\n' "$*"; FALLOS=$((FALLOS+1)); }
verde() { printf '\033[32m  OK     %s\033[0m\n' "$*"; }
paso()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

[ -f "$RESPALDO/MANIFIESTO.txt" ] || { printf '\033[31mNo es un respaldo: falta MANIFIESTO.txt\033[0m\n'; exit 1; }

paso "1. Piezas obligatorias"
for archivo in MANIFIESTO.txt SUMAS.sha256 codigo/repositorio.bundle \
               configuracion/docker-compose.yml configuracion/env.backend \
               imagenes/imagenes.tar.gz; do
    [ -s "$RESPALDO/$archivo" ] && verde "$archivo" || rojo "$archivo (falta o vacio)"
done
DUMP="$(find "$RESPALDO/base_datos" -name '*.dump' -size +1k 2>/dev/null | head -1)"
[ -n "$DUMP" ] && verde "base_datos/$(basename "$DUMP")" || rojo "no hay volcado de base de datos"

paso "2. Sumas de verificacion"
( cd "$RESPALDO" && sha256sum -c SUMAS.sha256 --quiet ) \
    && verde "todos los archivos coinciden con su suma" \
    || rojo "hay archivos alterados o truncados"

paso "3. El repositorio se puede leer"
git bundle verify "$RESPALDO/codigo/repositorio.bundle" >/dev/null 2>&1 \
    && verde "repositorio.bundle integro" \
    || rojo "repositorio.bundle corrupto"

paso "4. El volcado se puede leer"
# pg_restore --list lee el indice del volcado sin escribir nada: si responde,
# el archivo es un volcado valido y no un tar a medias.
if [ -n "$DUMP" ]; then
    if command -v pg_restore >/dev/null 2>&1; then
        TABLAS="$(pg_restore --list "$DUMP" 2>/dev/null | grep -c 'TABLE DATA' || true)"
    else
        TABLAS="$(docker run --rm -i -v "$(dirname "$DUMP"):/d:ro" postgres:17 \
                  pg_restore --list "/d/$(basename "$DUMP")" 2>/dev/null | grep -c 'TABLE DATA' || true)"
    fi
    [ "${TABLAS:-0}" -gt 50 ] && verde "volcado legible ($TABLAS tablas con datos)" \
                              || rojo "el volcado no se pudo leer o trae muy pocas tablas ($TABLAS)"
fi

paso "5. Las imagenes estan completas"
IMG="$(gunzip -c "$RESPALDO/imagenes/imagenes.tar.gz" 2>/dev/null | tar t 2>/dev/null | grep -c 'manifest.json' || true)"
[ "${IMG:-0}" -ge 1 ] && verde "archivo de imagenes descomprime y trae manifiesto" \
                      || rojo "el archivo de imagenes esta corrupto"
# Las tres tienen que estar. La de PostgreSQL es la que mas facil se escapa:
# el servicio 'db' vive en un perfil de compose y no aparece en la lista de
# imagenes si el perfil no se activa al armar el respaldo.
for esperada in backend frontend postgres; do
    grep -q "$esperada" "$RESPALDO/imagenes/lista.txt" 2>/dev/null \
        && verde "imagen de $esperada incluida" \
        || rojo "FALTA la imagen de $esperada — el respaldo no podria levantar el sistema"
done

paso "6. Los secretos que hacen falta estan"
for clave in DB_NAME DB_USER DB_PASSWORD JWT_SECRET_KEY; do
    grep -qE "^${clave}=.+" "$RESPALDO/configuracion/env.backend" \
        && verde "$clave presente" || rojo "$clave vacio o ausente en env.backend"
done

echo ""
if [ "$FALLOS" -eq 0 ]; then
    printf '\033[32mRESPALDO INTEGRO — apto para mover a otro servidor.\033[0m\n'
    echo ""
    grep -E 'Huella|Migracion head|Commit ' "$RESPALDO/MANIFIESTO.txt" | sed 's/^/  /'
else
    printf '\033[31m%s COMPROBACION(ES) FALLIDAS — no confiar en este respaldo.\033[0m\n' "$FALLOS"
    exit 1
fi
