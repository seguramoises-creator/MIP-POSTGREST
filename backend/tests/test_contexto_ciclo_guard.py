"""
Guard de escritura (ciclo cerrado → 409) en endpoints de captura.

Sigue el patrón de esta suite (ver test_visita_service.py): tests unitarios
de servicio con `MagicMock`/`SimpleNamespace` + `monkeypatch`, sin BD real ni
TestClient (esta suite no usa fixtures `db_session`/`client`/`ciclo_abierto`/
`ciclo_cerrado` — no existen en conftest.py; se construyen aquí los dobles
mínimos necesarios para cada caso).

Cobertura:
  1) Guard central `recalculo_service.validar_ciclo_abierto` (caracterización).
  2) Servicios de captura que antes NO llamaban al guard:
     - visita_registro_service.registrar_visita / registrar_no_visita
     - visita_planeacion_service.guardar_planeacion
     - lsii_service.registrar_evaluacion
     - visita_parrilla_service.registrar_muestras
     - visita_costo_service.guardar_parametros
  3) Traducción HTTP 409 en los routers (lsii.py, visita.py) para el
     ValueError("...cerrado...") que levanta el guard.

Nota sobre Categorización Médica: `categorizacion_service.py` /
`categorizacion.py` en esta edición Postgres NO usan `Config.DIM_Ciclo` en
absoluto — el flujo (`/categorizacion/cargar` → `cargar_excel_categorizacion`)
está indexado por `periodo` (string libre) dentro del esquema `cat`/`stg`,
sin relación con `ciclo_id`/`cerrado`. No hay endpoint `/categorizacion/calcular`
ni `/recalcular` en este repo. Por lo tanto no aplica ningún guard de ciclo
ahí; se deja constancia explícita en vez de forzar un guard sin sentido.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import recalculo_service


# ══════════════════════════════════════════════════════════════════════
# 1) Guard central — caracterización (ya existía, pin de regresión)
# ══════════════════════════════════════════════════════════════════════

def _fake_db_con_ciclo(ciclo):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ciclo
    return db


def test_validar_ciclo_abierto_rechaza_cerrado():
    """El guard central levanta CicloCerradoError en un ciclo cerrado."""
    ciclo_cerrado = SimpleNamespace(id=10, nombre="CICLO-10", cerrado=True)
    db = _fake_db_con_ciclo(ciclo_cerrado)
    with pytest.raises(recalculo_service.CicloCerradoError):
        recalculo_service.validar_ciclo_abierto(db, 10)


def test_validar_ciclo_abierto_ok_abierto():
    """El guard devuelve el ciclo cuando está abierto."""
    ciclo_abierto = SimpleNamespace(id=11, nombre="CICLO-11", cerrado=False)
    db = _fake_db_con_ciclo(ciclo_abierto)
    c = recalculo_service.validar_ciclo_abierto(db, 11)
    assert c.id == 11
    assert c.cerrado is False


# ══════════════════════════════════════════════════════════════════════
# 2) Registro de visita — visita_registro_service
# ══════════════════════════════════════════════════════════════════════

def test_registrar_visita_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_registro_service as rs
    from app.schemas.visita import VisitaRegistrar

    db = MagicMock()
    monkeypatch.setattr(rs, "_medico_del_vm", lambda d, vm, m: None)
    monkeypatch.setattr(rs, "ciclo_por_defecto", lambda d, vm=None: 5)

    def _cerrado(d, c):
        raise rs.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(rs.recalculo_service, "validar_ciclo_abierto", _cerrado)

    datos = VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="visita normal de rutina")
    with pytest.raises(ValueError, match="cerrado"):
        rs.registrar_visita(db, vm_id=1, datos=datos, usuario_id=1)


def test_registrar_no_visita_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_registro_service as rs
    from app.schemas.visita import VisitaNoVisita

    db = MagicMock()
    monkeypatch.setattr(rs, "_medico_del_vm", lambda d, vm, m: None)
    monkeypatch.setattr(rs, "ciclo_por_defecto", lambda d, vm=None: 5)

    def _cerrado(d, c):
        raise rs.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(rs.recalculo_service, "validar_ciclo_abierto", _cerrado)

    datos = VisitaNoVisita(medico_id=1, causa="Médico en Vacaciones")
    with pytest.raises(ValueError, match="cerrado"):
        rs.registrar_no_visita(db, vm_id=1, datos=datos, usuario_id=1)


# ══════════════════════════════════════════════════════════════════════
# 3) Planeación del ciclo — visita_planeacion_service
# ══════════════════════════════════════════════════════════════════════

def test_guardar_planeacion_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_planeacion_service as ps

    db = MagicMock()
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda d, vm=None: 5)

    def _cerrado(d, c):
        raise ps.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(ps.recalculo_service, "validar_ciclo_abierto", _cerrado)

    with pytest.raises(ValueError, match="cerrado"):
        ps.guardar_planeacion(db, vm_id=1, ciclo_id=5, items=[], usuario_id=1)


# ══════════════════════════════════════════════════════════════════════
# 4) LSII — registrar_evaluacion
# ══════════════════════════════════════════════════════════════════════

def test_lsii_registrar_evaluacion_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.lsii_service as ls

    db = MagicMock()

    def _cerrado(d, c):
        raise ls.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(ls.recalculo_service, "validar_ciclo_abierto", _cerrado)

    with pytest.raises(ValueError, match="cerrado"):
        ls.registrar_evaluacion(
            db,
            pais_codigo="DO",
            rm_id=1,
            ciclo_id=5,
            selecciones=[],
        )


# ══════════════════════════════════════════════════════════════════════
# 5) Muestras (parrilla) y parámetros de costo — guards añadidos en auditoría
# ══════════════════════════════════════════════════════════════════════

def test_registrar_muestras_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_parrilla_service as ps
    from app.schemas.visita import MuestraItem

    db = MagicMock()
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda d, vm=None: 5)

    def _cerrado(d, c):
        raise ps.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(ps.recalculo_service, "validar_ciclo_abierto", _cerrado)

    with pytest.raises(ValueError, match="cerrado"):
        ps.registrar_muestras(db, vm_id=1, ciclo_id=5, medico_id=9,
                              entregas=[MuestraItem(producto="X1", cantidad=2)], usuario_id=1)


def test_guardar_parametros_costo_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_costo_service as cs
    from app.schemas.visita import ParametroCostoGuardar

    db = MagicMock()
    monkeypatch.setattr(cs, "ciclo_por_defecto", lambda d, vm=None: 5)

    def _cerrado(d, c):
        raise cs.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(cs.recalculo_service, "validar_ciclo_abierto", _cerrado)

    datos = ParametroCostoGuardar(ciclo_id=5, linea_id=1, costo_visita=10, costo_muestra=1, costo_fijo_ciclo=100)
    with pytest.raises(ValueError, match="cerrado"):
        cs.guardar_parametros(db, datos, usuario_id=1)


# ══════════════════════════════════════════════════════════════════════
# 6) Traducción HTTP 409 en los routers
# ══════════════════════════════════════════════════════════════════════
# Esta suite no usa TestClient/FastAPI app real (no hay tal fixture en
# conftest.py); se ejercen directamente las funciones-endpoint (son
# funciones Python normales decoradas con @router.post/get) pasándoles los
# dobles de FastAPI (Depends ya resueltos) para verificar que el
# ValueError del guard se traduce a HTTPException(409).

def test_lsii_router_evaluar_traduce_409(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.routers import lsii as lsii_router
    from app.schemas.schemas import EvaluacionLsiiCreate

    def _falla_cerrado(db, **kwargs):
        raise ValueError("El ciclo está cerrado — solo lectura")
    monkeypatch.setattr(lsii_router.lsii_service, "registrar_evaluacion", _falla_cerrado)

    data = EvaluacionLsiiCreate(
        pais_codigo="DO", rm_id=1, ciclo_id=5,
        selecciones=[{"dimension_codigo": "COMPROMISO", "opcion_id": 1}],
    )
    current_user = SimpleNamespace(id=1)
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        lsii_router.evaluar(data, db=db, current_user=current_user)
    assert exc_info.value.status_code == 409


def test_visita_router_registrar_traduce_409(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.routers import visita as visita_router
    from app.schemas.visita import VisitaRegistrar

    import app.services.visita_registro_service as rs

    def _falla_cerrado(*a, **k):
        raise ValueError("El ciclo está cerrado — solo lectura")
    monkeypatch.setattr(rs, "registrar_visita", _falla_cerrado)

    datos = VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="visita normal de rutina")
    current_user = SimpleNamespace(id=1, rol=SimpleNamespace(value="ADMIN"))
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        visita_router.registrar_visita(datos, vm_id=1, db=db, current_user=current_user)
    assert exc_info.value.status_code == 409


def test_visita_router_planeacion_traduce_409(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.routers import visita as visita_router
    from app.schemas.visita import PlaneacionGuardar

    import app.services.visita_planeacion_service as vps

    def _falla_cerrado(*a, **k):
        raise ValueError("El ciclo está cerrado — solo lectura")
    monkeypatch.setattr(vps, "guardar_planeacion", _falla_cerrado)

    datos = PlaneacionGuardar(items=[])
    current_user = SimpleNamespace(id=1, rol=SimpleNamespace(value="ADMIN"))
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        visita_router.guardar_planeacion(datos, vm_id=1, ciclo_id=5, db=db, current_user=current_user)
    assert exc_info.value.status_code == 409
