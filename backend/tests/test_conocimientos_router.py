"""Router /conocimientos — Tarea 5.

Sigue el patrón de `test_examen_consolidacion_router.py`/`test_farmacias_router.py`:
router aislado en una app mínima, `get_current_active_user` sobreescrito y, cuando
la ruta necesita datos, `get_db` con un `MagicMock`/`SimpleNamespace` doble o la
capa de servicio monkeypencheada.

Cubre dos cosas que no viven en `test_conocimientos_captura.py` (que prueba el
SERVICIO contra PostgreSQL real):
1. El guard nuevo del router — `POST /conocimientos/notas` responde 422 si el
   `rm_id` no pertenece al `pais_codigo` del cuerpo (hallazgo de la Tarea 3,
   inalcanzable hasta que existió este endpoint).
2. `POST /conocimientos/integrar` traduce `FuenteAjenaError` a 409 (mismo
   contrato que `/examenes/consolidacion/consolidar`) y hace `commit()` en el
   camino exitoso — `integrar_captura` no comitea por sí mismo.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.models.usuario import Rol
from app.services import fuente_indicador_service as fuentes


def U(rol, id=1):
    return SimpleNamespace(rol=rol, id=id, activo=True)


def _client(router, user, db=None):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: user
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def _db_con_rm(pais_codigo_real: str | None):
    """MagicMock cuyo `.get(RepresentanteMedico, id)` devuelve un RM de
    `pais_codigo_real`, o None si no existe."""
    db = MagicMock()
    if pais_codigo_real is None:
        db.get.return_value = None
    else:
        db.get.return_value = SimpleNamespace(id=1, pais_codigo=pais_codigo_real)
    return db


BODY_BASE = {"pais_codigo": "DO", "ciclo_id": 1, "rm_id": 1,
             "nota": 80, "fecha_evaluacion": "2026-01-15", "tema": None}


def test_crear_nota_rm_inexistente_422():
    from app.api.v1.routers.conocimientos import router

    r = _client(router, U(Rol.ADMIN), _db_con_rm(None)).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 422
    assert "DO" in r.json()["detail"]


def test_crear_nota_rm_de_otro_pais_422():
    """El hallazgo de la Tarea 3: `capturar_nota` no valida el país del RM —
    `integrar_captura` filtra por el `pais_codigo` del parámetro mientras
    `_upsert_resultado` resuelve por `rm.pais_codigo` real. Sin este guard en
    el router, un llamador podría colar un RM de otro país."""
    from app.api.v1.routers.conocimientos import router

    r = _client(router, U(Rol.ADMIN), _db_con_rm("CR")).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 422
    cuerpo = r.json()["detail"]
    assert "DO" in cuerpo and "1" in cuerpo


def test_crear_nota_rm_del_pais_correcto_pasa_el_guard(monkeypatch):
    """Con el RM del país correcto, la petición atraviesa el guard nuevo y
    llega a `capturar_nota` (aquí monkeypencheado para no tocar BD real)."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    llamado = {}

    def _fake_capturar(db, pais_codigo, ciclo_id, rm_id, nota, fecha, tema, usuario_id):
        llamado["ok"] = True
        return SimpleNamespace(id=99)

    monkeypatch.setattr(cs, "capturar_nota", _fake_capturar)

    r = _client(router, U(Rol.ADMIN), _db_con_rm("DO")).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 200, r.text
    assert r.json() == {"id": 99}
    assert llamado.get("ok") is True


def test_integrar_traduce_fuente_ajena_a_409(monkeypatch):
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    def _raise(db, pais_codigo, ciclo_id):
        raise fuentes.FuenteAjenaError(pais_codigo, fuentes.INDICADOR_CONOCIMIENTOS,
                                       fuentes.FUENTE_EXAMEN_VISTA, fuentes.FUENTE_CAPTURA_MANUAL)

    monkeypatch.setattr(cs, "integrar_captura", _raise)

    r = _client(router, U(Rol.ADMIN), MagicMock()).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 409
    cuerpo = r.json()["detail"]
    assert fuentes.FUENTE_EXAMEN_VISTA in cuerpo
    assert "DO" in cuerpo


def test_integrar_comitea_en_exito(monkeypatch):
    """`integrar_captura` no hace commit propio (lo decide el llamador, igual
    que `capturar_nota`/`corregir_nota`/`fijar_fuente`): sin el `db.commit()`
    del router, el delete-then-insert se perdería al cerrarse la sesión."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    monkeypatch.setattr(cs, "integrar_captura",
                        lambda db, pais_codigo, ciclo_id: {"abortado": False, "rms_integrados": 3})

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 200, r.text
    assert r.json()["rms_integrados"] == 3
    db.commit.assert_called_once()
