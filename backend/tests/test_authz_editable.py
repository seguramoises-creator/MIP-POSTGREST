"""Matriz RBAC editable (jul-2026): caché de runtime + edición desde la UI + salvaguardas.

Sin BD viva (CI corre pytest sin Postgres): se usa un doble de sesión que almacena filas por
clase de modelo y soporta filter_by/all/scalar(func.max). Cada test resetea el runtime para no
alterar los demás tests de authz (que dependen del fallback a fábrica).
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.authz import runtime, edicion, engine
from app.core.authz.constantes import Accion, Alcance, Recurso
from app.core.authz.matrix import MATRIZ
from app.models.usuario import Rol
from app.models.seguridad_rbac import RolPermiso, Recurso as RecursoModel, AuditoriaSeguridad


# ── Doble de sesión ───────────────────────────────────────────────────────────
class _Q:
    def __init__(self, rows): self._rows = list(rows)
    def all(self): return list(self._rows)
    def filter_by(self, **kw):
        return _Q([r for r in self._rows if all(getattr(r, k, None) == v for k, v in kw.items())])
    def scalar(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self): self.store = {}
    def query(self, arg):
        if isinstance(arg, type):                 # query(Modelo)
            return _Q(self.store.get(arg, []))
        # query(func.max(RolPermiso.actualizado_en)) → versión
        vals = [p.actualizado_en for p in self.store.get(RolPermiso, []) if p.actualizado_en]
        return _Q([max(vals)] if vals else [])
    def add(self, obj): self.store.setdefault(type(obj), []).append(obj)
    def delete(self, obj):
        lst = self.store.get(type(obj), [])
        if obj in lst: lst.remove(obj)
    def commit(self): pass
    def rollback(self): pass
    def flush(self): pass


@pytest.fixture(autouse=True)
def _reset_runtime():
    """Deja el runtime en fallback-a-fábrica antes y después de cada test de este módulo."""
    runtime.invalidar()
    yield
    runtime._CACHE = {}
    runtime._version = None
    runtime.invalidar()


def _perm(rol, recurso, accion, alcance, ts=None):
    return RolPermiso(rol=rol, recurso=recurso, accion=accion, alcance=alcance,
                      actualizado_en=ts or datetime(2026, 7, 18, tzinfo=timezone.utc))


ADMIN = SimpleNamespace(id=1, rol=Rol.ADMIN)


# ── Fallback a fábrica ────────────────────────────────────────────────────────
def test_celda_cae_a_fabrica_si_cache_no_cargado():
    runtime.invalidar()
    # Sin caché cargado, celda() usa matrix.MATRIZ.
    assert runtime.celda(Rol.ADMIN, Recurso.CONFIG_USUARIOS) == MATRIZ[Recurso.CONFIG_USUARIOS][Rol.ADMIN]
    assert engine.can(SimpleNamespace(rol=Rol.REPRESENTANTE_MEDICO),
                      Accion.READ, Recurso.CONFIG_USUARIOS) is None  # RM no lee usuarios


# ── Caché desde BD ────────────────────────────────────────────────────────────
def test_cargar_arma_cache_desde_bd_y_engine_lee_de_ahi():
    db = FakeSession()
    db.add(_perm("GERENTE_DISTRITO", Recurso.COBERTURA_DIARIA, "read", "team"))
    db.add(_perm("REPRESENTANTE_MEDICO", Recurso.COBERTURA_DIARIA, "read", "own"))
    runtime.cargar(db)

    # engine.can lee del caché (BD), no del código.
    gd = SimpleNamespace(rol=Rol.GERENTE_DISTRITO)
    assert engine.can(gd, Accion.READ, Recurso.COBERTURA_DIARIA) == Alcance.TEAM
    # Un rol sin fila para ese recurso queda denegado (ausencia = None).
    fin = SimpleNamespace(rol=Rol.FINANZAS)
    assert engine.can(fin, Accion.READ, Recurso.COBERTURA_DIARIA) is None


def test_refrescar_si_cambio_recarga_al_cambiar_version():
    db = FakeSession()
    db.add(_perm("GERENTE_DISTRITO", Recurso.COBERTURA_DIARIA, "read", "team",
                 ts=datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)))
    runtime.cargar(db)
    gd = SimpleNamespace(rol=Rol.GERENTE_DISTRITO)
    assert engine.can(gd, Accion.READ, Recurso.COBERTURA_DIARIA) == Alcance.TEAM

    # Cambia la BD con una versión más nueva → refrescar debe recargar.
    db.store[RolPermiso][0].alcance = "all"
    db.store[RolPermiso][0].actualizado_en = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    runtime.refrescar_si_cambio(db)
    assert engine.can(gd, Accion.READ, Recurso.COBERTURA_DIARIA) == Alcance.ALL


# ── Validación de cambios ─────────────────────────────────────────────────────
def test_validar_rechaza_columna_admin():
    with pytest.raises(edicion.CambioInvalidoError):
        edicion._validar({"rol": "ADMIN", "recurso": Recurso.COBERTURA_DIARIA,
                          "accion": "read", "alcance": "all"})


def test_validar_rechaza_valores_invalidos():
    with pytest.raises(edicion.CambioInvalidoError):
        edicion._validar({"rol": "NO_EXISTE", "recurso": Recurso.COBERTURA_DIARIA,
                          "accion": "read", "alcance": "all"})
    with pytest.raises(edicion.CambioInvalidoError):
        edicion._validar({"rol": "FINANZAS", "recurso": "recurso.inexistente",
                          "accion": "read", "alcance": "all"})
    with pytest.raises(edicion.CambioInvalidoError):
        edicion._validar({"rol": "FINANZAS", "recurso": Recurso.COBERTURA_DIARIA,
                          "accion": "read", "alcance": "galaxia"})
    with pytest.raises(edicion.CambioInvalidoError):
        edicion._validar({"rol": "FINANZAS", "recurso": Recurso.COBERTURA_DIARIA,
                          "accion": "admin", "alcance": "all"})  # 'admin' no asignable


def test_validar_acepta_valido_y_denegacion():
    assert edicion._validar({"rol": "FINANZAS", "recurso": Recurso.COBERTURA_DIARIA,
                             "accion": "read", "alcance": "all"}) == \
        ("FINANZAS", Recurso.COBERTURA_DIARIA, "read", "all")
    # accion None = denegar (borrar la celda)
    assert edicion._validar({"rol": "FINANZAS", "recurso": Recurso.COBERTURA_DIARIA,
                             "accion": None, "alcance": None})[2] is None


# ── Aplicar cambios ───────────────────────────────────────────────────────────
def test_aplicar_cambios_agrega_quita_y_audita():
    db = FakeSession()
    fin = SimpleNamespace(rol=Rol.FINANZAS)
    # Celda fija (para que el caché nunca quede vacío) + la que vamos a togglear.
    # Ambas están DENEGADAS en fábrica para FINANZAS (medico.panel y cobertura.predictiva).
    edicion.aplicar_cambios(db, ADMIN, [
        {"rol": "FINANZAS", "recurso": Recurso.MEDICO_PANEL, "accion": "read", "alcance": "all"},
    ])
    n = edicion.aplicar_cambios(db, ADMIN, [
        {"rol": "FINANZAS", "recurso": Recurso.COBERTURA_PREDICTIVA, "accion": "read", "alcance": "all"},
    ])
    assert n == 1
    assert engine.can(fin, Accion.READ, Recurso.COBERTURA_PREDICTIVA) == Alcance.ALL
    assert any(a.evento == "PERMISO_MODIFICADO" for a in db.store.get(AuditoriaSeguridad, []))

    # Denegar (accion None) → celda borrada. El caché aún tiene medico.panel (no vacío),
    # así que es una denegación genuina por ausencia de fila, no fallback a fábrica.
    edicion.aplicar_cambios(db, ADMIN, [
        {"rol": "FINANZAS", "recurso": Recurso.COBERTURA_PREDICTIVA, "accion": None, "alcance": None},
    ])
    assert engine.can(fin, Accion.READ, Recurso.COBERTURA_PREDICTIVA) is None
    assert engine.can(fin, Accion.READ, Recurso.MEDICO_PANEL) == Alcance.ALL  # la otra sigue


def test_aplicar_cambios_rechaza_admin_sin_escribir():
    db = FakeSession()
    with pytest.raises(edicion.CambioInvalidoError):
        edicion.aplicar_cambios(db, ADMIN, [
            {"rol": "ADMIN", "recurso": Recurso.COBERTURA_DIARIA, "accion": None, "alcance": None},
        ])
    assert not db.store.get(RolPermiso, [])  # nada se escribió (validación previa)


def test_matriz_actual_incluye_todos_los_roles():
    db = FakeSession()
    db.add(_perm("GERENTE_DISTRITO", Recurso.COBERTURA_DIARIA, "read", "team"))
    recursos = edicion.matriz_actual(db)
    fila = next(r for r in recursos if r["recurso"] == Recurso.COBERTURA_DIARIA)
    assert set(fila["roles"].keys()) == set(edicion.ROLES)          # 13 columnas
    assert fila["roles"]["GERENTE_DISTRITO"] == {"accion": "read", "alcance": "team"}
    assert fila["roles"]["FINANZAS"] is None                        # sin fila = None
