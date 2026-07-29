#!/usr/bin/env bash
#
# restaurar_solucion.sh — Levanta VISTA desde un respaldo completo, en un
# servidor Debian limpio con Docker. No necesita internet ni reconstruir nada.
#
#   Uso:  ./restaurar_solucion.sh [directorio_destino]
#   Ej.:  ./restaurar_solucion.sh /opt/msm-pg
#
# Correr DESDE la carpeta del respaldo ya descomprimido.
#
# DESTRUCTIVO en el destino: si ahi ya existe una base con el mismo nombre, la
# borra y la reemplaza. Pide confirmacion escrita antes de hacerlo.

set -euo pipefail

RESPALDO="$(cd "$(dirname "$0")" && pwd)"
DESTINO="${1:-/opt/msm-pg}"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
paso()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------
paso "0. Comprobaciones previas"
# --------------------------------------------------------------------------
command -v docker >/dev/null || { rojo "No hay docker en este servidor."; exit 1; }
docker compose version >/dev/null 2>&1 || { rojo "No hay 'docker compose' v2."; exit 1; }
[ -f "$RESPALDO/MANIFIESTO.txt" ] || { rojo "No parece un respaldo: falta MANIFIESTO.txt"; exit 1; }

echo "--- Origen del respaldo ---"
sed -n '1,20p' "$RESPALDO/MANIFIESTO.txt"
echo "---------------------------"

paso "0b. Integridad del paquete"
( cd "$RESPALDO" && sha256sum -c SUMAS.sha256 --quiet ) \
    && verde "    Sumas de verificacion correctas." \
    || { rojo "    EL RESPALDO ESTA CORRUPTO. No continuar."; exit 1; }

PREFIJO="$(basename "$DESTINO" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
BD="$(grep -E '^DB_NAME=' "$RESPALDO/configuracion/env.backend" | cut -d= -f2- | tr -d '\r')"
USR="$(grep -E '^DB_USER=' "$RESPALDO/configuracion/env.backend" | cut -d= -f2- | tr -d '\r')"
echo ""
echo "    Destino          : $DESTINO"
echo "    Proyecto compose : $PREFIJO"
echo "    Base de datos    : $BD (usuario $USR)"
echo ""
rojo "Si en el destino ya existe la base '$BD', SE BORRARA y sera reemplazada."
printf "Escribe 'restaurar' para continuar: "
read -r confirmacion
[ "$confirmacion" = "restaurar" ] || { echo "Cancelado."; exit 1; }

# --------------------------------------------------------------------------
paso "1. Imagenes Docker"
# --------------------------------------------------------------------------
gunzip -c "$RESPALDO/imagenes/imagenes.tar.gz" | docker load
verde "    Imagenes cargadas (no hace falta reconstruir nada)."

# --------------------------------------------------------------------------
paso "2. Codigo fuente"
# --------------------------------------------------------------------------
if [ -d "$DESTINO/.git" ]; then
    echo "    Ya hay un repositorio en $DESTINO; no se toca el codigo."
else
    mkdir -p "$(dirname "$DESTINO")"
    git clone "$RESPALDO/codigo/repositorio.bundle" "$DESTINO"
    ( cd "$DESTINO" && git checkout "$(cat "$RESPALDO/codigo/commit.txt")" 2>/dev/null || true )
    # El bundle apunta al archivo del respaldo, que no existira siempre: se
    # quita para que nadie intente un 'git pull' contra una ruta muerta.
    ( cd "$DESTINO" && git remote remove origin 2>/dev/null || true )
    verde "    Codigo clonado en el commit $(cat "$RESPALDO/codigo/commit.txt" | cut -c1-7)."
fi
if [ -f "$RESPALDO/codigo/cambios_sin_commitear.patch" ]; then
    ( cd "$DESTINO" && git apply "$RESPALDO/codigo/cambios_sin_commitear.patch" ) \
        && echo "    Cambios sin commitear del origen: aplicados." \
        || rojo "    No pude aplicar cambios_sin_commitear.patch — revisalo a mano."
fi

# --------------------------------------------------------------------------
paso "3. Configuracion"
# --------------------------------------------------------------------------
cp "$RESPALDO/configuracion/docker-compose.yml" "$DESTINO/docker-compose.yml"
cp "$RESPALDO/configuracion/env.backend" "$DESTINO/backend/.env"
[ -f "$RESPALDO/configuracion/env.raiz" ] && cp "$RESPALDO/configuracion/env.raiz" "$DESTINO/.env"
chmod 600 "$DESTINO/backend/.env" "$DESTINO/.env" 2>/dev/null || true
verde "    Configuracion en su sitio."

cd "$DESTINO"
if [ ! -f .env ] && [ -z "${POSTGRES_PASSWORD:-}" ]; then
    rojo "    Falta POSTGRES_PASSWORD (no habia .env en la raiz del origen)."
    rojo "    Exportalo antes de seguir:  export POSTGRES_PASSWORD='...'"
    exit 1
fi

# --------------------------------------------------------------------------
paso "4. Volumenes de archivos"
# --------------------------------------------------------------------------
for vol in backend_uploads backend_reports backend_logs; do
    if [ -f "$RESPALDO/volumenes/${vol}.tar.gz" ]; then
        docker volume create "${PREFIJO}_${vol}" >/dev/null
        docker run --rm \
            -v "${PREFIJO}_${vol}:/destino" \
            -v "$RESPALDO/volumenes:/origen:ro" \
            postgres:17 tar xzf "/origen/${vol}.tar.gz" -C /destino
        echo "    $vol restaurado"
    fi
done

# --------------------------------------------------------------------------
paso "5. Base de datos"
# --------------------------------------------------------------------------
# Se levanta SOLO la base: si arrancara tambien el backend, Alembic correria
# sus migraciones sobre una base vacia y despues el volcado chocaria con el
# esquema recien creado.
docker compose --profile with-db up -d db
echo -n "    Esperando a PostgreSQL"
for _ in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U "$USR" >/dev/null 2>&1; then break; fi
    echo -n "."; sleep 2
done
echo ""

docker compose exec -T db psql -U "$USR" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$BD\" WITH (FORCE);"
docker compose exec -T db psql -U "$USR" -d postgres \
    -c "CREATE DATABASE \"$BD\" OWNER \"$USR\";"
docker compose exec -T db pg_restore -U "$USR" -d "$BD" --no-owner --no-acl \
    < "$RESPALDO/base_datos/$BD.dump"
verde "    Base restaurada."

# --------------------------------------------------------------------------
paso "6. Arranque completo"
# --------------------------------------------------------------------------
docker compose --profile with-db up -d
echo -n "    Esperando al backend"
for _ in $(seq 1 60); do
    if docker compose exec -T backend python -c \
        "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
        break
    fi
    echo -n "."; sleep 2
done
echo ""

# --------------------------------------------------------------------------
paso "7. Verificacion"
# --------------------------------------------------------------------------
HEAD_ORIGEN="$(cat "$RESPALDO/base_datos/migracion_head.txt")"
HEAD_DESTINO="$(docker compose exec -T db psql -U "$USR" -d "$BD" -At -c 'SELECT version_num FROM alembic_version;')"
HUELLA_ORIGEN="$(cat "$RESPALDO/base_datos/huella.txt")"
HUELLA_DESTINO="$(docker compose exec -T db psql -U "$USR" -d "$BD" -At -f - < "$RESPALDO/huella_datos.sql")"

echo "    Migracion  origen : $HEAD_ORIGEN"
echo "    Migracion destino : $HEAD_DESTINO"
echo "    Huella     origen : $HUELLA_ORIGEN"
echo "    Huella    destino : $HUELLA_DESTINO"
echo ""

if [ "$HEAD_ORIGEN" = "$HEAD_DESTINO" ] && [ "$HUELLA_ORIGEN" = "$HUELLA_DESTINO" ]; then
    verde "RESTAURACION VERIFICADA: el destino es identico al origen."
else
    rojo "DIFERENCIAS DETECTADAS: revisar antes de dar por buena la restauracion."
    exit 1
fi

cat <<'PENDIENTES'

Falta ajustar a mano lo que es propio de CADA ambiente y no debe heredarse:

  1. JWT_SECRET_KEY en backend/.env  — cada ambiente lleva la suya. Compartirla
     hace que un token emitido en uno sea valido en el otro.
  2. ALLOWED_HOSTS en backend/.env   — EL QUE MAS DUELE OLVIDAR. En produccion
     esta activo TrustedHostMiddleware: toda peticion cuyo encabezado Host no
     figure en la lista se rechaza con 400 ANTES de llegar a la aplicacion. Con
     el dominio nuevo fuera de la lista, el sitio carga pero el login responde
     "Credenciales incorrectas" —el frontend muestra eso ante cualquier fallo—,
     y se pierde el rato buscando el problema en los usuarios. Ojo: por un tunel
     SSH a localhost SI funciona, porque localhost esta permitido; el fallo solo
     aparece al poner el servidor web del host delante.
  3. CORS_ORIGINS en backend/.env    — el dominio nuevo.
  4. Credenciales SMTP               — viven en la BASE (Admin > Correo), asi
     que viajaron en el volcado: apuntan al buzon del origen. Cambiarlas ANTES
     del primer correo o el sistema escribira desde la cuenta equivocada.
  5. nginx del host + certificado TLS del dominio nuevo (en configuracion/ hay
     una copia del original, solo como referencia).
  6. Contrasenas de los usuarios: viajaron hasheadas y siguen siendo validas.
     Si el ambiente nuevo es de otro cliente, revisar que corresponda.
PENDIENTES
