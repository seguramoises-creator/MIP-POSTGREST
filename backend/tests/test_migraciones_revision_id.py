"""Ningún revision id de Alembic puede pasar de 32 caracteres (jul-2026).

INCIDENTE que originó la regla: `0027_snapshot_loadbatchkey_not_null` (35) y
`0028_authz_categorizacion_maestro` (33) rompieron el arranque en producción. La tabla
`alembic_version.version_num` es `VARCHAR(32)`, así que Alembic ejecuta el CUERPO de la migración
y revienta al grabar la versión:

    psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)

Y como el entrypoint del contenedor NO aborta si las migraciones fallan (solo avisa y arranca
uvicorn igual), el backend quedó sirviendo con código nuevo sobre un esquema viejo — dos módulos
respondiendo 403 a todos. El fallo no se ve en local: solo aparece al tocar una BD real.

El margen era mínimo y nadie lo vigilaba: `0018_costo_estructura_aprobacion` mide exactamente 32.
"""
import re
from pathlib import Path

import pytest

# Límite de `alembic_version.version_num` (VARCHAR(32), el valor por defecto de Alembic).
MAX_REVISION_ID = 32

_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
_ARCHIVOS = sorted(_VERSIONS.glob("*.py"))
_RE_REVISION = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def test_hay_migraciones_que_revisar():
    """Si el glob deja de encontrar archivos, el resto del módulo pasaría en vacío."""
    assert _ARCHIVOS, f"no se encontraron migraciones en {_VERSIONS}"


@pytest.mark.parametrize("ruta", _ARCHIVOS, ids=lambda p: p.stem)
def test_revision_id_cabe_en_alembic_version(ruta: Path):
    m = _RE_REVISION.search(ruta.read_text(encoding="utf-8"))
    assert m, f"{ruta.name}: no se pudo leer el `revision`"
    rev = m.group(1)
    assert len(rev) <= MAX_REVISION_ID, (
        f"{ruta.name}: el revision id '{rev}' mide {len(rev)} caracteres y el máximo es "
        f"{MAX_REVISION_ID} (alembic_version.version_num es VARCHAR(32)). La migración fallaría "
        f"al grabar la versión, DESPUÉS de ejecutar su cuerpo."
    )
