# Módulo de Visita v2 — Config por ciclo + GPS/Foto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer la configuración por ciclo de Parrilla y Costo/ROI (con histórico en solo-lectura) y capturar GPS + foto por visita (almacenada como BLOB en SQL Server).

**Architecture:** Parte A reutiliza el `ciclo_id` que los servicios/endpoints ya aceptan, añadiendo selector de ciclo en el frontend y guards de "ciclo cerrado" en las escrituras. Parte B/C agrega columnas GPS/foto a `Visita.FactVisita`, endpoints multipart para la foto (BLOB), y captura de geolocalización + cámara en el registro.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic idempotente (`include_schemas=True`), pymssql/SQL Server (`LargeBinary`=VARBINARY(MAX)), pytest (unit con `MagicMock`/`monkeypatch`), React 18 + TS + Vite + MUI v6, axios, `navigator.geolocation`, `<input capture>`.

## Global Constraints

- Modelos: `Mapped[tipo]` + `mapped_column()`. Nunca `Column()` antiguo.
- Timestamps: `datetime.now(timezone.utc)`. Nunca `utcnow()`.
- Logs: `from loguru import logger`. Nunca `print()`.
- Ciclo cerrado = inmutable: guard `recalculo_service.validar_ciclo_abierto(db, ciclo_id)` (lanza `recalculo_service.CicloCerradoError`). En los servicios de Visita, convertir a `ValueError` para que el endpoint responda 400.
- Migraciones Alembic idempotentes (verificar columna antes de crear).
- Foto: BLOB en SQL Server (`LargeBinary`); validar **magic bytes** (JPEG `\xff\xd8\xff`, PNG `\x89PNG\r\n`) y **tamaño ≤ 3 MB**. Foto **opcional**.
- Firmas backend existentes (NO cambiar contrato salvo lo indicado):
  - `visita_parrilla_service.guardar_parrilla(db, ciclo_id, linea_id, items, usuario_id)`
  - `visita_parrilla_service.publicar_parrilla(db, ciclo_id, linea_id, usuario_id)`
  - `visita_costo_service.guardar_estructura(db, datos, usuario_id)` (resuelve `datos.ciclo_id or ciclo_por_defecto(db)`)
  - `visita_costo_service.importar_excel(db, contenido, ciclo_id, linea_id, usuario_id)`
  - `visita_registro_service.registrar_visita(db, vm_id, datos, usuario_id)`
  - Endpoint `POST /visita/registrar` devuelve `{"id","tipo","hora"}`; `_vm_registro(current_user, vm_id)` resuelve el VM.
- Tests backend: unit con `MagicMock`/`monkeypatch` (patrón de `tests/test_visita_service.py`).

---

### Task 1: Guards de ciclo cerrado (Parrilla + Costo)

**Files:**
- Modify: `backend/app/services/visita_parrilla_service.py` (`guardar_parrilla`, `publicar_parrilla`)
- Modify: `backend/app/services/visita_costo_service.py` (`guardar_estructura`, `importar_excel`)
- Modify: `backend/tests/test_visita_service.py`

**Interfaces:**
- Consumes: `recalculo_service.validar_ciclo_abierto(db, ciclo_id)`, `recalculo_service.CicloCerradoError`, `ciclo_por_defecto(db)`.
- Produces: helper `_guard_ciclo_abierto(db, ciclo_id)` en cada servicio que levanta `ValueError("El ciclo está cerrado — solo lectura")` si el ciclo está cerrado.

- [ ] **Step 1: Escribir el test (parrilla)**

En `tests/test_visita_service.py` añadir:

```python
def test_guardar_parrilla_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_parrilla_service as ps
    from unittest.mock import MagicMock
    db = MagicMock()
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda d: 5)
    def _cerrado(d, c):
        raise ps.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(ps.recalculo_service, "validar_ciclo_abierto", _cerrado)
    import pytest
    with pytest.raises(ValueError):
        ps.guardar_parrilla(db, ciclo_id=5, linea_id=1, items=[], usuario_id=1)
```

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_visita_service.py -k parrilla_rechaza -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'recalculo_service'` o no lanza)

- [ ] **Step 3: Implementar el guard en `visita_parrilla_service.py`**

Añadir el import y el helper cerca de la cabecera:

```python
from app.services import recalculo_service


def _guard_ciclo_abierto(db, ciclo_id):
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")
```

En `guardar_parrilla`, tras resolver `ciclo_id = ciclo_id or ciclo_por_defecto(db)`, llamar `_guard_ciclo_abierto(db, ciclo_id)`. Igual en `publicar_parrilla`.

- [ ] **Step 4: Escribir el test (costo)**

```python
def test_guardar_estructura_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_costo_service as cs
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    db = MagicMock()
    monkeypatch.setattr(cs, "ciclo_por_defecto", lambda d: 5)
    def _cerrado(d, c):
        raise cs.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(cs.recalculo_service, "validar_ciclo_abierto", _cerrado)
    import pytest
    datos = SimpleNamespace(ciclo_id=5, linea_id=1, productos=[])
    with pytest.raises(ValueError):
        cs.guardar_estructura(db, datos, usuario_id=1)
```

- [ ] **Step 5: Implementar el guard en `visita_costo_service.py`**

Añadir `from app.services import recalculo_service` y el mismo helper `_guard_ciclo_abierto`. En `guardar_estructura`, tras `ciclo_id = datos.ciclo_id or ciclo_por_defecto(db)`, llamar `_guard_ciclo_abierto(db, ciclo_id)`. En `importar_excel`, tras `ciclo_id = ciclo_id or ciclo_por_defecto(db)`, igual.

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_visita_service.py -k "rechaza_ciclo_cerrado" -v`
Expected: PASS (2)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/visita_parrilla_service.py backend/app/services/visita_costo_service.py backend/tests/test_visita_service.py
git commit -m "feat(visita) guards de ciclo cerrado en Parrilla y Costo (solo lectura)"
```

---

### Task 2: Migración + modelo GPS/Foto en `FactVisita`

**Files:**
- Modify: `backend/app/models/visita.py` (clase `VisitaRegistro`)
- Create: `backend/alembic/versions/d4b8f1a6c290_factvisita_gps_foto.py`

**Interfaces:**
- Produces: columnas `latitud`, `longitud`, `foto`, `foto_mime` en `Visita.FactVisita`.

- [ ] **Step 1: Añadir columnas al modelo** `VisitaRegistro` (tras `causa_no_visita`):

```python
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    foto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    foto_mime: Mapped[str | None] = mapped_column(String(40), nullable=True)
```

Asegurar el import: `from sqlalchemy import ... LargeBinary` (verificar que `Numeric`, `String` ya estén importados en el archivo).

- [ ] **Step 2: Crear la migración** `d4b8f1a6c290_factvisita_gps_foto.py`:

```python
"""FactVisita: GPS (lat/long) + foto (BLOB) por visita

Revision ID: d4b8f1a6c290
Revises: <PONER_HEAD_ACTUAL>
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "d4b8f1a6c290"
down_revision = None  # reemplazar por el head actual (Step 3)
branch_labels = None
depends_on = None

_COLS = {
    "latitud": sa.Numeric(10, 7),
    "longitud": sa.Numeric(10, 7),
    "foto": sa.LargeBinary(),
    "foto_mime": sa.String(length=40),
}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c["name"] for c in insp.get_columns("FactVisita", schema="Visita")}
    for nombre, tipo in _COLS.items():
        if nombre not in existentes:
            op.add_column("FactVisita", sa.Column(nombre, tipo, nullable=True), schema="Visita")


def downgrade():
    for nombre in _COLS:
        op.drop_column("FactVisita", nombre, schema="Visita")
```

- [ ] **Step 3: Fijar `down_revision`**

Run: `cd backend && python -m alembic heads`
Copiar el id al `down_revision`.

- [ ] **Step 4: Aplicar**

Run: `cd backend && python -m alembic upgrade head`
Expected: sin errores; `python -m alembic current` muestra `d4b8f1a6c290`.

- [ ] **Step 5: Verificar el modelo**

Run: `cd backend && python -c "from app.models.visita import VisitaRegistro as V; print('foto' in V.__table__.columns, 'latitud' in V.__table__.columns)"`
Expected: `True True`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/visita.py backend/alembic/versions/d4b8f1a6c290_factvisita_gps_foto.py
git commit -m "feat(visita) FactVisita: columnas GPS (lat/long) + foto BLOB"
```

---

### Task 3: `registrar_visita` con lat/long + schema

**Files:**
- Modify: `backend/app/schemas/visita.py` (`VisitaRegistrar`)
- Modify: `backend/app/services/visita_registro_service.py` (`registrar_visita`)
- Modify: `backend/tests/test_visita_service.py`

**Interfaces:**
- Produces: `VisitaRegistrar.latitud/longitud`; `registrar_visita` persiste lat/long.

- [ ] **Step 1: Añadir campos al schema** `VisitaRegistrar` (junto a `hace_minutos`):

```python
    latitud: float | None = None
    longitud: float | None = None
```

- [ ] **Step 2: Test**

```python
def test_registrar_visita_persiste_gps(monkeypatch):
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    db = MagicMock()
    monkeypatch.setattr(rs, "_medico_del_vm", lambda d, vm, m: None)
    monkeypatch.setattr(rs, "ciclo_por_defecto", lambda d: 7)
    capturado = {}
    def _add(obj): capturado["obj"] = obj
    db.add.side_effect = _add
    datos = SimpleNamespace(medico_id=3, tipo_visita="V", comentario="ok visita larga",
                            hace_minutos=0, productos=[], latitud=18.47, longitud=-69.9)
    rs.registrar_visita(db, vm_id=1, datos=datos, usuario_id=1)
    assert float(capturado["obj"].latitud) == 18.47
    assert float(capturado["obj"].longitud) == -69.9
```

- [ ] **Step 3: Run — falla**

Run: `cd backend && pytest tests/test_visita_service.py -k persiste_gps -v`
Expected: FAIL (`AttributeError: ... 'latitud'` en el objeto construido)

- [ ] **Step 4: Implementar** — en `registrar_visita`, pasar lat/long al construir `VisitaRegistro`:

```python
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita=datos.tipo_visita, fecha_hora=fecha_hora,
        comentario=datos.comentario, productos=productos, ejecutada=True,
        registrado_por=usuario_id,
        latitud=getattr(datos, "latitud", None), longitud=getattr(datos, "longitud", None),
    )
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_visita_service.py -k persiste_gps -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/visita.py backend/app/services/visita_registro_service.py backend/tests/test_visita_service.py
git commit -m "feat(visita) registrar visita captura GPS (lat/long)"
```

---

### Task 4: Servicio de foto (guardar/obtener + validación)

**Files:**
- Modify: `backend/app/services/visita_registro_service.py` (funciones nuevas)
- Modify: `backend/tests/test_visita_service.py`

**Interfaces:**
- Produces:
  - `guardar_foto_visita(db, visita_id: int, contenido: bytes, mime: str) -> None`
  - `obtener_foto_visita(db, visita_id: int) -> tuple[bytes, str] | None`
  - `MAX_FOTO_BYTES = 3 * 1024 * 1024`

- [ ] **Step 1: Test de validación**

```python
def test_guardar_foto_rechaza_no_imagen(monkeypatch):
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    import pytest
    db = MagicMock()
    v = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = v
    with pytest.raises(ValueError):
        rs.guardar_foto_visita(db, 1, b"NOTIMAGE", "image/jpeg")


def test_guardar_foto_acepta_jpeg(monkeypatch):
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    db = MagicMock()
    v = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = v
    rs.guardar_foto_visita(db, 1, b"\xff\xd8\xff\xe0resto", "image/jpeg")
    assert v.foto == b"\xff\xd8\xff\xe0resto"
    assert v.foto_mime == "image/jpeg"
```

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_visita_service.py -k foto -v`
Expected: FAIL (funciones no existen)

- [ ] **Step 3: Implementar** al final de `visita_registro_service.py`:

```python
from app.models.visita import VisitaRegistro  # (ya importado arriba; no duplicar)

MAX_FOTO_BYTES = 3 * 1024 * 1024
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n"


def _es_imagen(contenido: bytes) -> bool:
    return contenido[:3] == _MAGIC_JPEG or contenido[:6] == _MAGIC_PNG


def guardar_foto_visita(db, visita_id: int, contenido: bytes, mime: str) -> None:
    """Valida (magic bytes JPEG/PNG + tamaño ≤ 3MB) y guarda la foto como BLOB."""
    if len(contenido) > MAX_FOTO_BYTES:
        raise ValueError("La foto excede el tamaño máximo (3 MB)")
    if not _es_imagen(contenido):
        raise ValueError("El archivo no es una imagen JPEG/PNG válida")
    v = db.query(VisitaRegistro).filter(VisitaRegistro.id == visita_id).first()
    if v is None:
        raise ValueError("Visita no encontrada")
    v.foto = contenido
    v.foto_mime = mime or "image/jpeg"
    db.commit()


def obtener_foto_visita(db, visita_id: int):
    v = db.query(VisitaRegistro).filter(VisitaRegistro.id == visita_id).first()
    if v is None or not v.foto:
        return None
    return bytes(v.foto), (v.foto_mime or "image/jpeg")
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_visita_service.py -k foto -v`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/visita_registro_service.py backend/tests/test_visita_service.py
git commit -m "feat(visita) servicio de foto de visita (BLOB + validacion magic bytes/tamano)"
```

---

### Task 5: Endpoints de foto (POST/GET)

**Files:**
- Modify: `backend/app/api/v1/routers/visita.py`

**Interfaces:**
- Consumes: `guardar_foto_visita`, `obtener_foto_visita`, `_vm_registro`, `RequireVisita`.
- Produces: `POST /visita/{visita_id}/foto` (multipart), `GET /visita/{visita_id}/foto`.

- [ ] **Step 1: Añadir imports** — verificar que `UploadFile, File` ya estén (sí, línea 7) y añadir `from fastapi import Response` (o `from fastapi.responses import Response`).

- [ ] **Step 2: Endpoints** (tras el endpoint `/no-visita`):

```python
@router.post("/{visita_id}/foto", response_model=dict, status_code=status.HTTP_201_CREATED)
async def subir_foto_visita(
    visita_id: int, archivo: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=RequireVisita,
):
    """Sube la foto del centro para una visita (JPEG/PNG, ≤ 3 MB). Se guarda como BLOB."""
    from app.services import visita_registro_service
    contenido = await archivo.read()
    try:
        visita_registro_service.guardar_foto_visita(
            db, visita_id, contenido, archivo.content_type or "image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"id": visita_id, "bytes": len(contenido)}


@router.get("/{visita_id}/foto")
def obtener_foto_visita_endpoint(
    visita_id: int, db: Session = Depends(get_db), current_user=RequireVisita,
):
    """Devuelve la imagen de la visita (BLOB). 404 si no tiene foto."""
    from fastapi import Response
    from app.services import visita_registro_service
    data = visita_registro_service.obtener_foto_visita(db, visita_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin foto")
    contenido, mime = data
    return Response(content=contenido, media_type=mime)
```

- [ ] **Step 3: Verificar arranque + rutas**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if r.path.endswith('/foto')])"`
Expected: incluye `/api/v1/visita/{visita_id}/foto`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/visita.py
git commit -m "feat(visita) endpoints POST/GET /visita/{id}/foto (BLOB)"
```

---

### Task 6: Frontend service — ciclo params + foto

**Files:**
- Modify: `frontend/src/services/visita.service.ts`

**Interfaces:**
- Produces: `costoEstructura(cicloId?, lineaId?)`, `guardarCostoEstructura(datos con ciclo_id)`, `importarCostoExcel(file, cicloId?, lineaId?)`, funciones de parrilla con `cicloId`, `subirFotoVisita(visitaId, file)`, `urlFotoVisita(visitaId)`.

- [ ] **Step 1: Ajustar firmas de Costo** (añadir `ciclo_id` como query param):

```ts
export const costoEstructura = (cicloId?: number, lineaId?: number) =>
  api.get<CostoFull>('/visita/costo/estructura', { params: { ...(cicloId && { ciclo_id: cicloId }), ...(lineaId && { linea_id: lineaId }) } }).then(r => r.data);
export const guardarCostoEstructura = (datos: CostoEstructuraInput & { productos: CostoProdInput[] }) =>
  api.post<CostoFull>('/visita/costo/estructura', datos).then(r => r.data); // datos.ciclo_id incluido
export const importarCostoExcel = (file: File, cicloId?: number, lineaId?: number) => {
  const fd = new FormData(); fd.append('archivo', file);
  return api.post<CostoFull & { importados: number }>('/visita/costo/importar', fd,
    { params: { ...(cicloId && { ciclo_id: cicloId }), ...(lineaId && { linea_id: lineaId }) }, headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};
```

- [ ] **Step 2: Ajustar firmas de Parrilla** (añadir `cicloId` opcional a obtener/penetración/publicar; `ParrillaGuardar` ya tiene `ciclo_id`). Localizar las funciones `obtenerParrilla`/`parrillaPenetracion`/`publicarParrilla` y añadir `cicloId?` que se pasa como `ciclo_id` en `params`.

- [ ] **Step 3: Añadir funciones de foto** al final del archivo:

```ts
export const subirFotoVisita = (visitaId: number, file: File) => {
  const fd = new FormData(); fd.append('archivo', file);
  return api.post(`/visita/${visitaId}/foto`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};
export const urlFotoVisita = (visitaId: number) => `/visita/${visitaId}/foto`;
```

- [ ] **Step 4: Ajustar el tipo de registro** — en el tipo `VisitaRegistrar`/payload de `registrar`, añadir `latitud?: number | null; longitud?: number | null;`.

- [ ] **Step 5: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores (los llamadores se actualizan en Tasks 7-9)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/visita.service.ts
git commit -m "feat(visita) service: ciclo params (costo/parrilla) + foto de visita"
```

---

### Task 7: Frontend `CostoRoiVisita.tsx` — selector de ciclo

**Files:**
- Modify: `frontend/src/pages/visita/CostoRoiVisita.tsx`

**Interfaces:**
- Consumes: `GET /admin/ciclos` (vía `api`), `costoEstructura(cicloId, lineaId)`, `guardarCostoEstructura`, `importarCostoExcel(file, cicloId, lineaId)`.

- [ ] **Step 1: Estado + fetch de ciclos.** Añadir `const [cicloId, setCicloId] = useState<number|''>('')` y `const [ciclos, setCiclos] = useState<{id:number;nombre:string;cerrado:boolean}[]>([])`; cargar con `api.get('/admin/ciclos')`. Derivar `const cicloSel = ciclos.find(c => c.id === cicloId); const cerrado = !!cicloSel?.cerrado;`

- [ ] **Step 2: Selector de Ciclo** junto al de Línea:

```tsx
<TextField select size="small" label="Ciclo" value={cicloId} sx={{ minWidth: 200 }}
           onChange={(e) => setCicloId(Number(e.target.value))}>
  {ciclos.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}{c.cerrado ? ' (cerrado)' : ''}</MenuItem>)}
</TextField>
{cerrado && <Chip size="small" color="default" label="Ciclo cerrado — solo lectura" />}
```

- [ ] **Step 3: Pasar `cicloId`** a `costoEstructura(cicloId||undefined, lineaParam)`, a `guardarCostoEstructura({ ...est, ciclo_id: cicloId||null, linea_id: lineaParam??null, productos: prods })`, y a `importarCostoExcel(file, cicloId||undefined, lineaParam)`. Añadir `cicloId` a las deps de `cargar`.

- [ ] **Step 4: Solo-lectura** — cuando `cerrado`, deshabilitar los botones Guardar/Importar y los inputs editables: añadir `disabled={cerrado}` a `Guardar y recalcular`, `Importar Excel` y a los `TextField` de edición (usar una constante `const editable = esGestor && !cerrado`).

- [ ] **Step 5: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/visita/CostoRoiVisita.tsx
git commit -m "feat(visita) Costo & ROI: selector de ciclo + solo-lectura en cerrados"
```

---

### Task 8: Frontend `ParrillaVisita.tsx` — selector de ciclo

**Files:**
- Modify: `frontend/src/pages/visita/ParrillaVisita.tsx`

**Interfaces:**
- Consumes: `GET /admin/ciclos`, `obtenerParrilla(cicloId, lineaId)`, `publicarParrilla(lineaId, cicloId)`, guardar con `ciclo_id`.

- [ ] **Step 1: Estado + fetch de ciclos** (igual patrón que Task 7): `cicloId`, `ciclos`, `cerrado`.

- [ ] **Step 2: Selector de Ciclo** en la cabecera (reemplaza el texto fijo "Ciclo actual" por el selector + chip de cerrado).

- [ ] **Step 3: Pasar `cicloId`** a la carga de parrilla y penetración, al guardar (incluir `ciclo_id` en el payload `ParrillaGuardar`) y a publicar.

- [ ] **Step 4: Solo-lectura** — cuando `cerrado`, deshabilitar edición/guardar/publicar (además del `soloLectura` existente por rol).

- [ ] **Step 5: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/visita/ParrillaVisita.tsx
git commit -m "feat(visita) Parrilla: selector de ciclo + solo-lectura en cerrados"
```

---

### Task 9: Frontend `RegistrarVisita.tsx` — GPS + cámara

**Files:**
- Modify: `frontend/src/pages/visita/RegistrarVisita.tsx`

**Interfaces:**
- Consumes: `registrar` (con `latitud`/`longitud`), `subirFotoVisita(visitaId, file)`.

- [ ] **Step 1: Estado** para GPS y foto:

```tsx
const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
const [foto, setFoto] = useState<File | null>(null);
const [fotoPreview, setFotoPreview] = useState<string | null>(null);
```

- [ ] **Step 2: Botón de ubicación**:

```tsx
<Button size="small" startIcon={<span>📍</span>} onClick={() => {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
    () => alert('No se pudo obtener la ubicación (permiso denegado o sin señal).'),
    { enableHighAccuracy: true, timeout: 8000 });
}}>Capturar ubicación</Button>
{gps && <Typography variant="caption">📍 {gps.lat.toFixed(5)}, {gps.lng.toFixed(5)}</Typography>}
```

- [ ] **Step 3: Captura de foto (opcional)**:

```tsx
<Button size="small" component="label" startIcon={<span>📷</span>}>
  Foto del centro
  <input hidden type="file" accept="image/*" capture="environment"
    onChange={(e) => { const f = e.target.files?.[0] || null; setFoto(f);
      setFotoPreview(f ? URL.createObjectURL(f) : null); }} />
</Button>
{fotoPreview && <Box component="img" src={fotoPreview} sx={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 1, ml: 1 }} />}
```

- [ ] **Step 4: Enviar en el guardado** — en el handler de registrar, incluir `latitud: gps?.lat ?? null, longitud: gps?.lng ?? null` en el payload; tras recibir `{ id }`, si `foto`: `await subirFotoVisita(id, foto)` (envuelto en try/catch que solo avisa "visita registrada; foto no subida" sin fallar el registro). Limpiar `gps/foto/fotoPreview` tras éxito.

- [ ] **Step 5: Íconos en "Registradas hoy"** — si la visita trae `latitud`/`foto`, mostrar 📍/📷 (si el endpoint de listado no devuelve esos flags, mostrar solo lo disponible; no romper).

- [ ] **Step 6: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/visita/RegistrarVisita.tsx
git commit -m "feat(visita) registro: captura de GPS + foto del centro (camara)"
```

---

### Task 10: Verificación E2E + documentación

**Files:**
- Modify: `CLAUDE.md` (§22 fila del Módulo de Visita — añadir config por ciclo + GPS/foto)

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && pytest -q`
Expected: todos verdes (incluye los nuevos).

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npx tsc -b --noEmit && npx vite build`
Expected: sin errores.

- [ ] **Step 3: E2E (backend arriba)** — con un ciclo abierto: registrar visita con `latitud/longitud` (POST `/visita/registrar`), subir foto JPEG (POST `/visita/{id}/foto` → 201), recuperarla (GET `/visita/{id}/foto` → 200 image/jpeg), y verificar que `POST /visita/costo/estructura` sobre un ciclo cerrado devuelve 400. Verificar en navegador el selector de ciclo (cerrado en solo-lectura) y el flujo de registro con foto (subida por archivo).

- [ ] **Step 4: Actualizar CLAUDE.md** (Visita: Parrilla/Costo con selector de ciclo + histórico solo-lectura; FactVisita con GPS/foto BLOB + endpoints) y commit.

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md) Visita v2: config por ciclo + GPS/foto por visita"
```

---

## Self-Review

**Spec coverage:**
- §3 Parte A (selector ciclo + guards) → Tasks 1, 6, 7, 8 ✓
- §4 Parte B (GPS/foto backend: esquema, schema, servicio, endpoints) → Tasks 2, 3, 4, 5 ✓
- §5 Parte C (frontend GPS/cámara) → Task 9 ✓
- §6 pruebas → tests en cada task + Task 10 ✓
- §7 fuera de alcance (sin vínculo DIM_CentroMedico, sin resize) → respetado (no hay tasks) ✓

**Placeholder scan:** los pasos de frontend (Tasks 7-9) describen ediciones sobre archivos existentes con el código exacto a insertar; Task 8 reutiliza el patrón explícito de Task 7 (mismo código de selector/estado, repetido en su Step 2). Sin "TODO/TBD" en código.

**Type consistency:**
- `_guard_ciclo_abierto(db, ciclo_id)` usado en Task 1 (ambos servicios) ✓
- `guardar_foto_visita(db, visita_id, contenido, mime)` / `obtener_foto_visita(db, visita_id) -> tuple[bytes,str]|None` consistentes en Tasks 4, 5 ✓
- `subirFotoVisita(visitaId, file)` / `urlFotoVisita(visitaId)` consistentes en Tasks 6, 9 ✓
- `costoEstructura(cicloId?, lineaId?)` / `importarCostoExcel(file, cicloId?, lineaId?)` consistentes en Tasks 6, 7 ✓
- Columnas `latitud/longitud/foto/foto_mime` consistentes en Tasks 2, 3, 4 ✓
