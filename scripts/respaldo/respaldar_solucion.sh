#!/usr/bin/env bash
#
# respaldar_solucion.sh — Respaldo COMPLETO y PORTABLE de VISTA.
#
# Produce UN paquete que, restaurado en cualquier servidor Debian con Docker,
# levanta el sistema identico: mismas imagenes, mismos datos, mismos archivos,
# misma configuracion. No requiere internet ni reconstruir las imagenes en el
# destino.
#
# NO modifica nada: solo lee. Es seguro correrlo con el sistema en produccion.
#
#   Uso:   ./respaldar_solucion.sh [directorio_del_proyecto] [directorio_destino]
#   Ej.:   ./respaldar_solucion.sh /opt/msm-pg ~/respaldos
#
# El paquete resultante CONTIENE SECRETOS (.env con claves de BD, JWT y SMTP) y
# DATOS PERSONALES REALES (medicos, representantes, correos). Tratarlo como
# material confidencial: nunca en carpetas sincronizadas, nunca en git.

set -euo pipefail

# Resolver la ruta del propio script ANTES de cualquier 'cd': mas abajo se
# entra al directorio del proyecto, y a partir de ahi un $0 relativo ya no
# apunta a ningun lado.
AQUI="$(cd "$(dirname "$0")" && pwd)"

PROYECTO="${1:-/opt/msm-pg}"
DESTINO="${2:-$HOME/respaldos-vista}"
SELLO="$(date +%Y%m%d-%H%M)"
NOMBRE="vista-respaldo-$SELLO"
TRABAJO="$DESTINO/$NOMBRE"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
paso()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------
paso "0. Comprobaciones previas"
# --------------------------------------------------------------------------
command -v docker >/dev/null || { rojo "No hay docker en este servidor."; exit 1; }
docker compose version >/dev/null 2>&1 || { rojo "No hay 'docker compose' v2."; exit 1; }
[ -f "$PROYECTO/docker-compose.yml" ] || { rojo "No encuentro $PROYECTO/docker-compose.yml"; exit 1; }

cd "$PROYECTO"

# El nombre de proyecto de compose prefija los volumenes. Por defecto es el
# nombre del directorio, pero puede haberse fijado a mano: en vez de deducirlo,
# se DESCUBRE del volumen de datos, que siempre existe si el stack corrio.
PREFIJO="$(docker volume ls --format '{{.Name}}' | grep -E '_pg_data$' | head -1 | sed 's/_pg_data$//')"
if [ -z "$PREFIJO" ]; then
    PREFIJO="$(basename "$PROYECTO" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
    echo "    Aviso: no hay volumen *_pg_data; asumo el prefijo '$PREFIJO'."
fi
echo "    Proyecto compose: $PREFIJO"

if ! docker compose ps --status running --format '{{.Service}}' | grep -q db; then
    rojo "El contenedor 'db' no esta corriendo: no se puede volcar la base."
    rojo "Levantalo primero:  docker compose --profile with-db up -d"
    exit 1
fi

mkdir -p "$TRABAJO"/{codigo,configuracion,base_datos,imagenes,volumenes}
echo "    Destino: $TRABAJO"

# --------------------------------------------------------------------------
paso "1. Codigo fuente (con historia completa)"
# --------------------------------------------------------------------------
# Un 'git bundle' es el repositorio entero en un archivo: en el destino se
# clona y se sigue versionando con normalidad, a diferencia de copiar la
# carpeta, que deja un working tree sin remoto util.
git bundle create "$TRABAJO/codigo/repositorio.bundle" --all
git rev-parse HEAD              > "$TRABAJO/codigo/commit.txt"
git rev-parse 'HEAD^{tree}'     > "$TRABAJO/codigo/arbol.txt"
git status --porcelain          > "$TRABAJO/codigo/sin_commitear.txt"
SIN_COMMIT="$(wc -l < "$TRABAJO/codigo/sin_commitear.txt" | tr -d ' ')"
if [ "$SIN_COMMIT" != "0" ]; then
    # Los cambios no commiteados no viajan en el bundle: se guardan aparte para
    # no perderlos (asi se descubrio en jul-2026 un endurecimiento de puertos
    # que solo existia en el servidor).
    git diff HEAD > "$TRABAJO/codigo/cambios_sin_commitear.patch"
    echo "    OJO: $SIN_COMMIT archivo(s) modificados sin commitear (guardados como .patch)"
fi

# --------------------------------------------------------------------------
paso "2. Configuracion y secretos"
# --------------------------------------------------------------------------
cp docker-compose.yml "$TRABAJO/configuracion/"
# Dos .env distintos y ambos hacen falta: el de la raiz alimenta las variables
# del compose (POSTGRES_PASSWORD, FRONTEND_PORT) y el de backend/ es la config
# de la aplicacion (BD, JWT, SMTP, claves de API).
[ -f .env ]         && cp .env         "$TRABAJO/configuracion/env.raiz"    || echo "    (sin .env en la raiz)"
[ -f backend/.env ] && cp backend/.env "$TRABAJO/configuracion/env.backend" || rojo "    FALTA backend/.env"
# El nginx del host termina el TLS y no vive en el proyecto: se copia como
# REFERENCIA (el destino tendra otro dominio y otro certificado).
for sitio in /etc/nginx/sites-available/*; do
    [ -f "$sitio" ] && cp "$sitio" "$TRABAJO/configuracion/nginx-$(basename "$sitio").referencia" 2>/dev/null || true
done

# --------------------------------------------------------------------------
paso "3. Base de datos (volcado logico)"
# --------------------------------------------------------------------------
BD="$(grep -E '^DB_NAME=' backend/.env | cut -d= -f2- | tr -d '\r' || echo scgcpr)"
USR="$(grep -E '^DB_USER=' backend/.env | cut -d= -f2- | tr -d '\r' || echo segura)"
echo "    Base '$BD', usuario '$USR'"
# -Fc = formato comprimido de pg_restore (permite restaurar selectivo y listar
# el contenido sin restaurar). 'exec -T' evita que Docker asigne un TTY, que
# corrompe el binario del volcado con traducciones de fin de linea.
docker compose exec -T db pg_dump -U "$USR" -Fc "$BD" > "$TRABAJO/base_datos/$BD.dump"
docker compose exec -T db psql -U "$USR" -d "$BD" -At \
    -c "SELECT version_num FROM alembic_version;" > "$TRABAJO/base_datos/migracion_head.txt"
docker compose exec -T db psql -U "$USR" -d "$BD" -At \
    -f - < "$AQUI/huella_datos.sql" > "$TRABAJO/base_datos/huella.txt"
echo "    Migracion:  $(cat "$TRABAJO/base_datos/migracion_head.txt")"
echo "    Huella:     $(cat "$TRABAJO/base_datos/huella.txt")"

# --------------------------------------------------------------------------
paso "4. Imagenes Docker"
# --------------------------------------------------------------------------
# Guardarlas es lo que hace el respaldo portable de verdad: el destino levanta
# EXACTAMENTE lo mismo que estaba corriendo, sin reconstruir (sin internet, sin
# npm/pip, sin riesgo de que una dependencia haya cambiado de version).
IMAGENES="$(docker compose config --images 2>/dev/null | sort -u | tr '\n' ' ')"
[ -z "$IMAGENES" ] && IMAGENES="msm-backend:latest msm-frontend:latest postgres:17"
echo "    $IMAGENES"
# shellcheck disable=SC2086
docker save $IMAGENES | gzip -1 > "$TRABAJO/imagenes/imagenes.tar.gz"
echo "$IMAGENES" > "$TRABAJO/imagenes/lista.txt"
# shellcheck disable=SC2086
docker image inspect $IMAGENES --format '{{.RepoTags}} {{.Id}} {{.Created}}' \
    > "$TRABAJO/imagenes/detalle.txt" 2>/dev/null || true

# --------------------------------------------------------------------------
paso "5. Volumenes de archivos"
# --------------------------------------------------------------------------
# uploads/reports/logs NO estan en el volcado de la base: son archivos en disco
# (Excel cargados, certificados PDF generados, bitacora). Sin ellos el sistema
# arranca pero con los adjuntos historicos rotos.
#
# pg_data se OMITE a proposito: el volcado logico del paso 3 lo sustituye y es
# portable, mientras que copiar PGDATA crudo solo restaura en la misma version
# y arquitectura exactas de PostgreSQL.
for vol in backend_uploads backend_reports backend_logs; do
    if docker volume inspect "${PREFIJO}_${vol}" >/dev/null 2>&1; then
        docker run --rm \
            -v "${PREFIJO}_${vol}:/origen:ro" \
            -v "$TRABAJO/volumenes:/destino" \
            postgres:17 tar czf "/destino/${vol}.tar.gz" -C /origen . 2>/dev/null || true
        if [ -s "$TRABAJO/volumenes/${vol}.tar.gz" ]; then
            echo "    $vol  ->  $(du -h "$TRABAJO/volumenes/${vol}.tar.gz" | cut -f1)"
        else
            rojo "    $vol  NO se pudo empaquetar — revisar antes de confiar en el respaldo"
        fi
    else
        echo "    $vol  (no existe, se omite)"
    fi
done

# --------------------------------------------------------------------------
paso "6. Manifiesto y sumas de verificacion"
# --------------------------------------------------------------------------
{
    echo "RESPALDO COMPLETO DE VISTA"
    echo "=========================="
    echo "Fecha            : $(date -Is)"
    echo "Servidor origen  : $(hostname)"
    echo "Sistema          : $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -a)"
    echo "Directorio       : $PROYECTO"
    echo "Proyecto compose : $PREFIJO"
    echo "Docker           : $(docker --version)"
    echo ""
    echo "CODIGO"
    echo "  Commit         : $(cat "$TRABAJO/codigo/commit.txt")"
    echo "  Arbol          : $(cat "$TRABAJO/codigo/arbol.txt")"
    echo "  Sin commitear  : $SIN_COMMIT archivo(s)"
    echo ""
    echo "BASE DE DATOS"
    echo "  Nombre         : $BD"
    echo "  Migracion head : $(cat "$TRABAJO/base_datos/migracion_head.txt")"
    echo "  Huella         : $(cat "$TRABAJO/base_datos/huella.txt")"
    echo ""
    echo "IMAGENES"
    sed 's/^/  /' "$TRABAJO/imagenes/detalle.txt" 2>/dev/null || echo "  $IMAGENES"
    echo ""
    echo "COMO SE VERIFICA QUE EL DESTINO QUEDO IGUAL"
    echo "  Tras restaurar, correr scripts/respaldo/verificar_respaldo.sh y"
    echo "  comparar la huella y la migracion head contra las de arriba."
} > "$TRABAJO/MANIFIESTO.txt"

( cd "$TRABAJO" && find . -type f ! -name SUMAS.sha256 -exec sha256sum {} + | sort -k2 > SUMAS.sha256 )

# --------------------------------------------------------------------------
paso "7. Empaquetado"
# --------------------------------------------------------------------------
cp "$AQUI/restaurar_solucion.sh" "$AQUI/verificar_respaldo.sh" \
   "$AQUI/huella_datos.sql" "$TRABAJO/" 2>/dev/null || true
chmod +x "$TRABAJO"/*.sh 2>/dev/null || true

tar czf "$DESTINO/$NOMBRE.tar.gz" -C "$DESTINO" "$NOMBRE"
sha256sum "$DESTINO/$NOMBRE.tar.gz" > "$DESTINO/$NOMBRE.tar.gz.sha256"
rm -rf "$TRABAJO"

echo ""
verde "RESPALDO COMPLETO"
echo "  Archivo : $DESTINO/$NOMBRE.tar.gz"
echo "  Tamano  : $(du -h "$DESTINO/$NOMBRE.tar.gz" | cut -f1)"
echo "  SHA-256 : $(cut -d' ' -f1 "$DESTINO/$NOMBRE.tar.gz.sha256")"
echo ""
echo "Contiene secretos y datos personales reales: guardalo como confidencial."
echo "Para restaurarlo en otro servidor:"
echo "  tar xzf $NOMBRE.tar.gz && cd $NOMBRE && ./restaurar_solucion.sh /ruta/destino"
