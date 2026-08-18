"""
Router de Categorización Médica — nueva versión (jun-2026).

Usa el esquema cat.* / stg.* en PostgreSQL.
Motor de cálculo: categorizacion_service (100% Python).

Prefijo: /categorizacion
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.authz.deps import require as _require_authz
from app.core.authz.constantes import Accion as _Acc, Recurso as _Rec
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.models.dimensiones import RepresentanteMedico
from app.services import categorizacion_service as svc

router = APIRouter(prefix="/categorizacion", tags=["Categorización Médica"])

# ── RBAC por matriz editable (jul-2026) ───────────────────────────────────────
# La fila `categorizacion.operacion` se calcó del `require_roles` que había aquí, así que el
# acceso efectivo NO cambia; ahora se ajusta desde Administración → Roles y Permisos. Es un
# recurso propio, distinto de `categorizacion.detalle` (que `admin.py` usa para el motor de
# criterios/pesos): tocar aquella fila habría alterado también ese otro módulo.
# El filtro de DATOS por rol sigue siendo `_codigos_scope` más abajo — la matriz decide quién
# entra al endpoint, no cuántas filas ve.
AdminOGerProd  = Depends(_require_authz(_Acc.CONFIGURE, _Rec.CATEGORIZACION_OPERACION))
RequireAdminCat = Depends(_require_authz(_Acc.CONFIGURE, _Rec.CATEGORIZACION_OPERACION))
RequireAuth    = Depends(_require_authz(_Acc.READ, _Rec.CATEGORIZACION_OPERACION))

# Item 5 (Mallén): visión de datos por rol. Producto/MKT/Dirección + gestión + CONSULTA ven
# todo; el RM ve solo su panel; el GD solo su equipo.
_ROLES_VE_TODO = {Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL,
                  Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MARCA, Rol.CONSULTA}


def _codigos_scope(db: Session, user: Usuario):
    """Códigos de representante visibles para el usuario: None = todos; [] = ninguno."""
    if user.rol in _ROLES_VE_TODO:
        return None
    if user.rol == Rol.REPRESENTANTE_MEDICO:
        cod = db.query(RepresentanteMedico.codigo).filter(RepresentanteMedico.id == user.rm_id).scalar()
        return [cod] if cod else []
    if user.rol == Rol.GERENTE_DISTRITO:
        return [c for (c,) in db.query(RepresentanteMedico.codigo)
                .filter(RepresentanteMedico.gerente_id == user.gerente_id).all() if c]
    return []

MAX_UPLOAD_MB = 50


# ── POST /categorizacion/cargar ───────────────────────────────────────────────
@router.post("/cargar", summary="Carga Excel de Categorización Médica")
async def cargar_excel(
    archivo: UploadFile = File(..., description="Excel .xlsx con las hojas del modelo"),
    periodo: str = Form(..., description="Período YYYY-MM, ej. 2024-01"),
    _current_user: Usuario = AdminOGerProd,
    db: Session = Depends(get_db),
):
    """
    Carga el Excel de Categorización Médica completo:
    lee catálogos, inserta staging y ejecuta el SP de cálculo.
    Devuelve el resumen del lote procesado.
    """
    if not archivo.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .xlsx")

    contenido = await archivo.read()
    if len(contenido) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Archivo mayor a {MAX_UPLOAD_MB} MB")

    # Validar magic bytes xlsx (PK\x03\x04)
    if contenido[:4] != b"PK\x03\x04":
        raise HTTPException(status_code=400, detail="El archivo no es un Excel .xlsx válido")

    nombre_seguro = f"{uuid.uuid4()}_{archivo.filename[:80]}"

    try:
        resultado = svc.cargar_excel_categorizacion(
            db=db,
            excel_bytes=contenido,
            nombre_archivo=nombre_seguro,
            periodo=periodo,
            usuario=_current_user.username,
        )
        return {
            "ok": True,
            "mensaje": f"Carga completada — {resultado['total_medicos']} médicos procesados",
            **resultado,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")


# ── GET /categorizacion/plantilla ──────────────────────────────────────────────
@router.get("/plantilla", summary="Opciones válidas de los 5 criterios (alta de médico)")
def get_plantilla(
    pais_codigo: str = Query(..., min_length=1, max_length=10),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    """Alimenta el formulario de clasificación al dar de alta un médico.

    Cada criterio tiene un vocabulario CERRADO definido por las reglas del país
    (p. ej. KOL: 'Charlista Internacional'…'Ninguno'); por eso el formulario debe usar
    desplegables con estas opciones y no texto libre. **No devuelve los puntajes**: la
    categoría permanece oculta hasta que el Gerente de Distrito aprueba el alta."""
    opciones = svc.opciones_plantilla(db, pais_codigo)
    if not opciones:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El país '{pais_codigo}' no tiene configuradas las reglas de "
                   f"categorización; no se puede clasificar médicos todavía.")
    return opciones


# ── GET /categorizacion/lotes ──────────────────────────────────────────────────
@router.get("/lotes", summary="Historial de lotes de carga")
def get_lotes(
    limit: int = Query(50, ge=1, le=200),
    _current_user: Usuario = AdminOGerProd,
    db: Session = Depends(get_db),
):
    return svc.get_lotes(db, limit=limit)


# ── GET /categorizacion/resumen ────────────────────────────────────────────────
@router.get("/mi-panel", summary="Categorización del panel del representante")
def get_mi_panel(current_user: Usuario = RequireAuth, db: Session = Depends(get_db)):
    """Categorización DEL PANEL del representante — plano de asignación, no del motor.

    Son dos categorías distintas por diseño (ver §14b):
      · La **general** la calcula el motor de 5 criterios (`cat.*`), por período, y es un
        proceso aparte del administrador.
      · La **del panel** (`Visita.DIM_MedicoVisita.categoria`) es la del médico DENTRO del
        panel de ESE representante: al darlo de alta el sistema le propone la calculada y
        él la ajusta a su criterio. Es sobre este panel que programa visitas y revisitas.
        Cambiarla NO altera la categorización general (`categoria` no está en
        `_MAESTRO_SYNC` y nada escribe de vuelta a `cat.*`).

    Por eso esta vista **no depende del ciclo**: la categoría del panel es estable entre
    ciclos, tal como pide el negocio. La pantalla del RM leía el motor general —donde un
    representante dado de alta después de la última carga de Excel no existe— y salía en
    ceros aunque su panel estuviera categorizado.
    """
    if current_user.rol != Rol.REPRESENTANTE_MEDICO:
        raise HTTPException(403, "Esta vista es del panel de un representante médico.")
    if not current_user.rm_id:
        raise HTTPException(403, "Tu usuario no está vinculado a un representante médico.")
    return svc.get_panel_rm(db, current_user.rm_id)


@router.get("/resumen", summary="Resumen ejecutivo de categorización")
def get_resumen(
    periodo: Optional[str] = Query(None, description="Filtrar por período YYYY-MM"),
    pais: Optional[str] = Query(None, description="Código de país, ej. DO"),
    provincia: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    especialidad: Optional[str] = Query(None),
    representante: Optional[str] = Query(None),
    current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_resumen(
        db,
        periodo=periodo,
        pais=pais,
        provincia=provincia,
        municipio=municipio,
        especialidad=especialidad,
        representante=representante,
        codigos_rep=_codigos_scope(db, current_user),
    )


# ── GET /categorizacion/resultados ────────────────────────────────────────────
@router.get("/resultados", summary="Listado paginado de resultados de categorización")
def get_resultados(
    periodo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None, description="A, B, C o D"),
    estado_conciliacion: Optional[str] = Query(None, description="OK, DIFERENCIA, SIN_REFERENCIA"),
    representante: Optional[str] = Query(None),
    medico: Optional[str] = Query(None, description="Filtro por nombre del médico (parcial)"),
    especialidad: Optional[str] = Query(None, description="Filtro por especialidad (exacta)"),
    pais: Optional[str] = Query(None, description="Código de país, ej. DO"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_resultados(
        db,
        periodo=periodo,
        categoria=categoria,
        estado_conciliacion=estado_conciliacion,
        representante=representante,
        medico=medico,
        especialidad=especialidad,
        pais=pais,
        codigos_rep=_codigos_scope(db, current_user),
        skip=skip,
        limit=limit,
    )


# ── GET /categorizacion/por-representante ─────────────────────────────────────
@router.get("/por-representante", summary="Categorización agrupada por equipo y representante")
def get_por_representante(
    periodo: Optional[str] = Query(None),
    pais: Optional[str] = Query(None, description="Código de país, ej. DO"),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_por_representante(db, periodo=periodo, pais=pais)


# ── GET /categorizacion/por-especialidad ──────────────────────────────────────
@router.get("/por-especialidad", summary="Categorización agrupada por especialidad")
def get_por_especialidad(
    periodo: Optional[str] = Query(None),
    pais: Optional[str] = Query(None, description="Código de país, ej. DO"),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_por_especialidad(db, periodo=periodo, pais=pais)


# ── GET /categorizacion/componentes ───────────────────────────────────────────
@router.get("/componentes", summary="Catálogo de componentes y sus pesos")
def get_componentes(
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_componentes(db)


# ── GET /categorizacion/diagnostico ───────────────────────────────────────────
@router.get("/diagnostico", summary="Diagnóstico: conteos de tablas del schema cat")
def get_diagnostico(
    # Quedó SIN dependencia de autenticación (ago-2026): era el único de los 20 endpoints
    # de este router sin guard, y el router no declara `dependencies` globales, así que
    # respondía 200 a cualquiera sin token. Devuelve el mensaje crudo de las excepciones
    # (`f"ERROR: {exc}"`), o sea nombres de tablas y columnas del esquema `cat` servidos a
    # internet. Va con CONFIGURE, no con READ: es una herramienta de operación, no un dato
    # del módulo.
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    """Endpoint temporal de diagnóstico — retorna conteos de tablas clave."""
    from sqlalchemy import text as _t
    resultados: dict = {}
    tablas = [
        ("snapshot", "SELECT COUNT(*) FROM cat.FactMedicoCategoriaSnapshot"),
        ("detalle",  "SELECT COUNT(*) FROM cat.FactMedicoCategoriaDetalle"),
        ("dim_pais", "SELECT COUNT(*) FROM cat.DimPais"),
        ("dim_medico","SELECT COUNT(*) FROM cat.DimMedico"),
        ("dim_esp",  "SELECT COUNT(*) FROM cat.DimEspecialidad"),
        ("dim_rep",  "SELECT COUNT(*) FROM cat.DimRepresentanteMedico"),
        ("load_batch","SELECT COUNT(*) FROM cat.LoadBatch"),
        ("snapshot_cols", """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='FactMedicoCategoriaSnapshot'
            ORDER BY ORDINAL_POSITION
        """),
        ("periodos", "SELECT DISTINCT Periodo FROM cat.FactMedicoCategoriaSnapshot ORDER BY Periodo DESC"),
    ]
    for nombre, sql in tablas:
        try:
            rows = db.execute(_t(sql)).fetchall()
            if nombre in ("snapshot_cols", "periodos"):
                resultados[nombre] = [r[0] for r in rows]
            else:
                resultados[nombre] = rows[0][0] if rows else "?"
        except Exception as exc:
            resultados[nombre] = f"ERROR: {exc}"
    # Test de la query de detalle
    try:
        cnt = db.execute(_t("""
            SELECT COUNT(*)
            FROM cat.FactMedicoCategoriaSnapshot f
            LEFT JOIN cat.DimMedico m ON m.MedicoKey = f.MedicoKey
            LEFT JOIN cat.DimEspecialidad e ON e.EspecialidadKey = m.EspecialidadKey
            LEFT JOIN cat.DimRepresentanteMedico r ON r.RepresentanteKey = f.RepresentanteKey
        """)).scalar()
        resultados["detalle_query_count"] = cnt
    except Exception as exc:
        resultados["detalle_query_count"] = f"ERROR: {exc}"
    return resultados


# ── GET /categorizacion/filtros ───────────────────────────────────────────────
@router.get("/filtros", summary="Catálogos en cascada para filtros de detalle")
def get_filtros(
    pais: Optional[str] = Query(None),
    provincia: Optional[str] = Query(None),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    try:
        return svc.get_filtros_medicos(db, pais=pais, provincia=provincia)
    except Exception as exc:
        from loguru import logger
        logger.error(f"Error en /filtros: {exc}")
        raise


# ── GET /categorizacion/detalle-medicos ───────────────────────────────────────
@router.get("/detalle-medicos", summary="Listado paginado de médicos con filtros")
def get_detalle_medicos(
    periodo: Optional[str] = Query(None),
    pais: Optional[str] = Query(None),
    provincia: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    especialidad: Optional[str] = Query(None),
    representante: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    from loguru import logger
    try:
        resultado = svc.get_detalle_medicos(
            db, periodo=periodo, pais=pais, provincia=provincia,
            municipio=municipio, especialidad=especialidad,
            representante=representante, categoria=categoria,
            skip=skip, limit=limit,
        )
        logger.info(f"[detalle-medicos] periodo={periodo!r} total={resultado.get('total')}")
        return resultado
    except Exception as exc:
        logger.error(f"[detalle-medicos] ERROR periodo={periodo!r}: {exc}")
        raise


# ── GET /categorizacion/detalle-medicos/{key}/componentes ─────────────────────
@router.get("/detalle-medicos/{medico_categoria_key}/componentes",
            summary="Scores por componente de un médico")
def get_componentes_medico(
    medico_categoria_key: int,
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_componentes_medico(db, medico_categoria_key)


# ── Mantenimiento: Países disponibles ─────────────────────────────────────────
@router.get("/params/paises", summary="Países configurados en cat.DimPais")
def get_paises(
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    return svc.get_paises_cat(db)


# ── Mantenimiento: Clasificación (rangos A/B/C/D) ─────────────────────────────
@router.get("/params/clasificacion", summary="Rangos de clasificación A/B/C/D")
def get_clasificaciones(
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_clasificaciones(db)


@router.put("/params/clasificacion", summary="Crear o actualizar rango de clasificación")
def upsert_clasificacion(
    body: dict,
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    return svc.upsert_clasificacion(db, body)


# ── Mantenimiento: Componentes (pesos %) ──────────────────────────────────────
@router.put("/params/componentes/{componente_key}", summary="Actualizar peso de un componente")
def update_componente(
    componente_key: int,
    body: dict,
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    return svc.update_componente(db, componente_key, float(body["PesoPct"]))


# ── Mantenimiento: Reglas por componente ──────────────────────────────────────
@router.get("/params/reglas", summary="Reglas de puntuación por componente")
def get_reglas(
    componente: Optional[str] = Query(None),
    _current_user: Usuario = RequireAuth,
    db: Session = Depends(get_db),
):
    return svc.get_reglas(db, componente_codigo=componente)


@router.put("/params/reglas", summary="Crear o actualizar regla")
def upsert_regla(
    body: dict,
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    return svc.upsert_regla(db, body)


@router.delete("/params/reglas/{regla_key}", summary="Desactivar regla (soft-delete)")
def delete_regla(
    regla_key: int,
    _current_user: Usuario = RequireAdminCat,
    db: Session = Depends(get_db),
):
    return svc.delete_regla(db, regla_key)


# ── Catálogos geográficos / especialidad (dropdowns del maestro de médicos) ────
# Mantenimiento centralizado en Categorización (alta/baja lógica). Los mismos
# catálogos se leen también desde el módulo de Visita (GET /visita/provincias, etc.).
from app.services import geo_catalogo_service as _geo  # noqa: E402


@router.get("/geo/provincias", summary="Listar provincias")
def geo_listar_provincias(pais_codigo: Optional[str] = Query(None), incluir_inactivos: bool = Query(False),
                          _u: Usuario = RequireAuth, db: Session = Depends(get_db)):
    return _geo.listar_provincias(db, pais_codigo, incluir_inactivos)


@router.get("/geo/municipios", summary="Listar municipios de una provincia")
def geo_listar_municipios(provincia_id: Optional[int] = Query(None), incluir_inactivos: bool = Query(False),
                          _u: Usuario = RequireAuth, db: Session = Depends(get_db)):
    return _geo.listar_municipios(db, provincia_id, incluir_inactivos)


@router.get("/geo/centros", summary="Listar centros médicos")
def geo_listar_centros(pais_codigo: Optional[str] = Query(None), incluir_inactivos: bool = Query(False),
                       _u: Usuario = RequireAuth, db: Session = Depends(get_db)):
    return _geo.listar_centros(db, pais_codigo, incluir_inactivos)


@router.get("/geo/especialidades", summary="Listar especialidades")
def geo_listar_especialidades(incluir_inactivos: bool = Query(False),
                              _u: Usuario = RequireAuth, db: Session = Depends(get_db)):
    return _geo.listar_especialidades(db, incluir_inactivos)


@router.post("/geo/provincias", summary="Crear provincia", status_code=201)
def geo_crear_provincia(body: dict, _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        return _geo.crear_provincia(db, body["pais_codigo"], body["nombre"])
    except KeyError:
        raise HTTPException(status_code=400, detail="Faltan campos: pais_codigo, nombre")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/geo/municipios", summary="Crear municipio", status_code=201)
def geo_crear_municipio(body: dict, _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        return _geo.crear_municipio(db, int(body["provincia_id"]), body["nombre"])
    except KeyError:
        raise HTTPException(status_code=400, detail="Faltan campos: provincia_id, nombre")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/geo/centros", summary="Crear centro médico", status_code=201)
def geo_crear_centro(body: dict, _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        return _geo.crear_centro(db, body["pais_codigo"], body["nombre"])
    except KeyError:
        raise HTTPException(status_code=400, detail="Faltan campos: pais_codigo, nombre")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/geo/especialidades", summary="Crear especialidad", status_code=201)
def geo_crear_especialidad(body: dict, _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        return _geo.crear_especialidad(db, body["nombre"])
    except KeyError:
        raise HTTPException(status_code=400, detail="Falta campo: nombre")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/geo/{tipo}/{id_}", summary="Editar un elemento: renombrar y/o activar-desactivar")
def geo_editar(tipo: str, id_: int, body: dict, _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        if "activo" in body:
            _geo.set_activo(db, tipo, id_, bool(body["activo"]))
        if body.get("nombre"):
            return _geo.renombrar(db, tipo, id_, body["nombre"])
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/geo/{tipo}/{id_}", summary="Borrar un elemento (baja lógica; ?permanente=true borra físico)")
def geo_borrar(tipo: str, id_: int, permanente: bool = Query(False),
               _u: Usuario = RequireAdminCat, db: Session = Depends(get_db)):
    try:
        if permanente:
            _geo.eliminar_permanente(db, tipo, id_)
        else:
            _geo.desactivar(db, tipo, id_)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
