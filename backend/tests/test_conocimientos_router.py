"""Router /conocimientos — Tarea 5 + Ronda de correcciones 1.

Sigue el patrón de `test_examen_consolidacion_router.py`/`test_farmacias_router.py`:
router aislado en una app mínima, `get_current_active_user` sobreescrito y, cuando
la ruta necesita datos, `get_db` con un `MagicMock`/`SimpleNamespace` doble o la
capa de servicio monkeypencheada.

Cubre lo que no vive en `test_conocimientos_captura.py` (que prueba el SERVICIO
contra PostgreSQL real):
1. El guard nuevo del router — `POST /conocimientos/notas` responde 422 si el
   `rm_id` no pertenece al `pais_codigo` del cuerpo (hallazgo de la Tarea 3,
   inalcanzable hasta que existió este endpoint).
2. `POST /conocimientos/integrar` traduce `FuenteAjenaError` a 409 (mismo
   contrato que `/examenes/consolidacion/consolidar`), hace `commit()` en el
   camino exitoso (`integrar_captura` no comitea por sí mismo) y dispara
   `recalculo_service.recalcular_ciclo` SOLO cuando la integración no abortó.
3. Los caminos 409/422 no comitean nada.
4. Una única definición de roles (`RequireCaptura`) gatea los 4 endpoints de
   escritura — no hay copias que puedan desincronizarse.
5. `PUT /conocimientos/fuente` con un `pais_codigo` inexistente da 422, no el
   500 crudo del `IntegrityError` de la FK.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

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


# ─────────────────────────────────────────────────────────────────────────
# Guard RM↔país (Tarea 3, cerrado en esta ronda)
# ─────────────────────────────────────────────────────────────────────────

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

    db = _db_con_rm("CR")
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 422
    cuerpo = r.json()["detail"]
    assert "DO" in cuerpo and "1" in cuerpo
    # El 422 corta ANTES de escribir nada.
    db.commit.assert_not_called()


def _db_con_rm_y_ciclo(rm_pais: str | None, ciclo_pais: str | None):
    """MagicMock cuyo `.get(modelo, id)` responde distinto según el modelo:
    RM de `rm_pais` (o None) y Ciclo de `ciclo_pais` (o None) — necesario
    porque `crear_nota` ahora valida los dos (`_validar_rm_del_pais` y
    `_validar_ciclo_del_pais`), a diferencia de `_db_con_rm` de arriba, que
    solo cubría el RM."""
    from app.models.dimensiones import Ciclo, RepresentanteMedico

    def _get(modelo, id_):
        if modelo is RepresentanteMedico:
            return None if rm_pais is None else SimpleNamespace(id=1, pais_codigo=rm_pais)
        if modelo is Ciclo:
            return None if ciclo_pais is None else SimpleNamespace(id=1, pais_codigo=ciclo_pais)
        return None

    db = MagicMock()
    db.get.side_effect = _get
    return db


# ─────────────────────────────────────────────────────────────────────────
# Guard ciclo↔país (IMPORTANT de la revisión final del sub-proyecto 7)
# ─────────────────────────────────────────────────────────────────────────

def test_crear_nota_ciclo_de_otro_pais_422():
    """Con el RM correcto pero el ciclo de OTRO país, el guard nuevo debe
    cortar con 422 antes de escribir nada — mismo criterio que el guard
    RM↔país de arriba."""
    from app.api.v1.routers.conocimientos import router

    db = _db_con_rm_y_ciclo(rm_pais="DO", ciclo_pais="CR")
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 422
    cuerpo = r.json()["detail"]
    assert "1" in cuerpo and "DO" in cuerpo
    db.commit.assert_not_called()


def test_crear_nota_ciclo_inexistente_422():
    from app.api.v1.routers.conocimientos import router

    db = _db_con_rm_y_ciclo(rm_pais="DO", ciclo_pais=None)
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 422
    db.commit.assert_not_called()


def test_integrar_traduce_ciclo_de_otro_pais_a_422_sin_comitear(monkeypatch):
    """`integrar_captura` también valida ciclo↔país (defensa en profundidad:
    una nota ya capturada con el par cruzado por otra vía debe rechazarse
    también al integrar, no solo al capturar)."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    def _raise(db, pais_codigo, ciclo_id):
        raise ValueError(f"El ciclo {ciclo_id} es de CR, no de {pais_codigo}.")

    monkeypatch.setattr(cs, "integrar_captura", _raise)

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 422
    assert "CR" in r.json()["detail"]
    db.commit.assert_not_called()


def test_crear_nota_rm_del_pais_correcto_pasa_el_guard_y_comitea(monkeypatch):
    """Con el RM del país correcto, la petición atraviesa el guard nuevo,
    llega a `capturar_nota` (monkeypencheado para no tocar BD real) y el
    router comitea el resultado."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    llamado = {}

    def _fake_capturar(db, pais_codigo, ciclo_id, rm_id, nota, fecha, tema, usuario_id):
        llamado["ok"] = True
        return SimpleNamespace(id=99)

    monkeypatch.setattr(cs, "capturar_nota", _fake_capturar)

    db = _db_con_rm("DO")
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/notas", json=BODY_BASE)

    assert r.status_code == 200, r.text
    assert r.json() == {"id": 99}
    assert llamado.get("ok") is True
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────
# PUT /fuente — pais_codigo inexistente
# ─────────────────────────────────────────────────────────────────────────

def test_cambiar_fuente_pais_inexistente_422_no_500(monkeypatch):
    """La FK de `pais_codigo` revienta con `IntegrityError` (en el `flush`
    dentro de `fijar_fuente` o en el `commit`); el router debe traducirlo a
    422 con un mensaje de negocio, no dejarlo caer al 500 genérico."""
    from app.api.v1.routers.conocimientos import router
    from app.services import fuente_indicador_service as fs

    def _raise(db, pais_codigo, fuente, usuario_id):
        raise IntegrityError("INSERT ...", {}, Exception("fk violation: pais_codigo"))

    monkeypatch.setattr(fs, "fijar_fuente", _raise)

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).put(
        "/api/v1/conocimientos/fuente", json={"pais_codigo": "ZZ", "fuente": "CAPTURA_MANUAL"})

    assert r.status_code == 422
    assert "ZZ" in r.json()["detail"]
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Única definición de roles — los 4 endpoints de escritura comparten guard
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metodo,ruta,body", [
    ("put", "/api/v1/conocimientos/fuente", {"pais_codigo": "DO", "fuente": "CAPTURA_MANUAL"}),
    ("post", "/api/v1/conocimientos/notas", BODY_BASE),
    ("put", "/api/v1/conocimientos/notas/1", {"nota": 80, "tema": None}),
    ("post", "/api/v1/conocimientos/integrar?pais_codigo=DO&ciclo_id=1", None),
])
def test_rol_no_autorizado_403_en_escritura(metodo, ruta, body):
    """`RequireCaptura` es la ÚNICA definición de la lista de roles; probar
    los 4 endpoints de escritura contra un rol ajeno (REPRESENTANTE_MEDICO)
    prueba que ninguno quedó con una copia desincronizada del chequeo."""
    from app.api.v1.routers.conocimientos import router

    client = _client(router, U(Rol.REPRESENTANTE_MEDICO), MagicMock())
    r = getattr(client, metodo)(ruta, json=body) if body is not None else getattr(client, metodo)(ruta)

    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# POST /integrar — 409, commit, y disparo condicional del recálculo
# ─────────────────────────────────────────────────────────────────────────

def test_integrar_traduce_fuente_ajena_a_409_sin_comitear(monkeypatch):
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs

    def _raise(db, pais_codigo, ciclo_id):
        raise fuentes.FuenteAjenaError(pais_codigo, fuentes.INDICADOR_CONOCIMIENTOS,
                                       fuentes.FUENTE_EXAMEN_VISTA, fuentes.FUENTE_CAPTURA_MANUAL)

    monkeypatch.setattr(cs, "integrar_captura", _raise)

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 409
    cuerpo = r.json()["detail"]
    assert fuentes.FUENTE_EXAMEN_VISTA in cuerpo
    assert "DO" in cuerpo
    # 409: no se escribió nada, no hay nada que comitear.
    db.commit.assert_not_called()


def test_integrar_exito_comitea_y_dispara_recalculo(monkeypatch):
    """`integrar_captura` no hace commit propio (lo decide el llamador, igual
    que `capturar_nota`/`corregir_nota`/`fijar_fuente`): sin el `db.commit()`
    del router, el delete-then-insert se perdería al cerrarse la sesión. Y,
    tras integrar con éxito, el router debe disparar
    `recalculo_service.recalcular_ciclo` — si no, la fila queda escrita pero
    sin `puntos_obtenidos` hasta que alguien recalcule por otra vía, mientras
    la pantalla ya dijo "N representantes integrados"."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs
    from app.services import recalculo_service as rs

    monkeypatch.setattr(cs, "integrar_captura",
                        lambda db, pais_codigo, ciclo_id: {"abortado": False, "rms_integrados": 3})

    recalculo_llamado = {}

    def _fake_recalcular(db, ciclo_id, pais_codigo):
        recalculo_llamado["args"] = (ciclo_id, pais_codigo)
        return {"ciclo_id": ciclo_id, "abortado": False}

    monkeypatch.setattr(rs, "recalcular_ciclo", _fake_recalcular)

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 200, r.text
    assert recalculo_llamado["args"] == (7, "DO")
    # Un commit tras `integrar_captura`, otro tras `recalcular_ciclo` — ambos
    # escriben sin comitear por sí mismos.
    assert db.commit.call_count == 2


def test_integrar_abortado_NO_dispara_recalculo(monkeypatch):
    """Si `integrar_captura` abortó (ciclo cerrado), no escribió nada — disparar
    el recálculo igual sería trabajo de sobra sobre una escritura vacía."""
    from app.api.v1.routers.conocimientos import router
    from app.services import conocimientos_service as cs
    from app.services import recalculo_service as rs

    monkeypatch.setattr(cs, "integrar_captura",
                        lambda db, pais_codigo, ciclo_id: {
                            "abortado": True, "motivo": "ciclo_cerrado", "rms_integrados": 0})

    recalculo = MagicMock()
    monkeypatch.setattr(rs, "recalcular_ciclo", recalculo)

    db = MagicMock()
    r = _client(router, U(Rol.ADMIN), db).post(
        "/api/v1/conocimientos/integrar", params={"pais_codigo": "DO", "ciclo_id": 7})

    assert r.status_code == 200, r.text
    assert r.json()["abortado"] is True
    recalculo.assert_not_called()
    # Solo el commit de después de `integrar_captura` (que no escribió nada,
    # así que este commit cierra una transacción vacía — inofensivo).
    db.commit.assert_called_once()
