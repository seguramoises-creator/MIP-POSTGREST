"""RBAC Fase 1 — T5: seed idempotente + auditoría (con doble de sesión que almacena filas).

No usa BD viva (CI corre pytest sin Postgres). El doble `_FakeSession` guarda las instancias
añadidas en listas por clase de modelo, de modo que la idempotencia se ejerce de verdad: una
segunda pasada ve lo que la primera insertó.
"""
from types import SimpleNamespace

from app.core.authz import seed
from app.core.authz.audit import registrar_evento_seguridad
from app.core.authz.constantes import RECURSOS
from app.models.usuario import Rol
from app.models.seguridad_rbac import Recurso, RolPermiso, AuditoriaSeguridad


class _FakeSession:
    def __init__(self):
        self._store = {}  # clase -> list[instancia]

    def query(self, modelo):
        rows = list(self._store.get(modelo, []))
        return SimpleNamespace(all=lambda: rows)

    def add(self, obj):
        self._store.setdefault(type(obj), []).append(obj)

    def delete(self, obj):
        self._store.get(type(obj), []).remove(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


def test_seed_idempotente():
    db = _FakeSession()
    r1 = seed.sembrar_todo(db)
    # Atado al catálogo (no a un número fijo): el conteo exacto lo verifica
    # `test_authz_matriz.test_matriz_tiene_35_recursos`, que es su sitio.
    assert r1["recursos_nuevos"] == len(RECURSOS)
    assert r1["permisos_cambios"] > 0
    n_rec = len(db._store[Recurso])
    n_perm = len(db._store[RolPermiso])
    assert n_rec == len(RECURSOS)

    # segunda pasada: nada nuevo, nada cambia
    r2 = seed.sembrar_todo(db)
    assert r2 == {"recursos_nuevos": 0, "permisos_cambios": 0}
    assert len(db._store[Recurso]) == n_rec
    assert len(db._store[RolPermiso]) == n_perm


def test_seed_permisos_reflejan_matriz():
    db = _FakeSession()
    seed.sembrar_todo(db)
    filas = [p for p in db._store[RolPermiso] if p.recurso == "config.usuarios"]
    assert {(p.rol, p.accion, p.alcance) for p in filas} == {("ADMIN", "admin", "all")}


def test_seed_no_persiste_sin_acceso():
    db = _FakeSession()
    seed.sembrar_todo(db)
    # config.usuarios solo tiene 1 fila (ADMIN); los 9 roles "sin acceso" no generan filas
    filas = [p for p in db._store[RolPermiso] if p.recurso == "config.usuarios"]
    assert len(filas) == 1


def test_seed_recupera_alcance_cambiado():
    db = _FakeSession()
    seed.sembrar_todo(db)
    # simulamos deriva: alteramos el alcance de una fila y re-sembramos
    fila = next(p for p in db._store[RolPermiso]
                if p.recurso == "cobertura.diaria" and p.rol == "REPRESENTANTE_MEDICO")
    fila.alcance = "all"  # estaba en "own"
    r = seed.sembrar_todo(db)
    assert r["permisos_cambios"] == 1
    assert fila.alcance == "own"  # restaurado a la matriz


def test_registra_evento_seguridad():
    db = _FakeSession()
    actor = SimpleNamespace(id=1, rol=Rol.ADMIN)
    registrar_evento_seguridad(db, actor, "ROL_ASIGNADO", objetivo="user:5",
                               detalle="rol_anterior=CONSULTA rol_nuevo=FINANZAS")
    filas = db._store[AuditoriaSeguridad]
    assert len(filas) == 1
    assert filas[0].evento == "ROL_ASIGNADO"
    assert filas[0].actor_rol == "ADMIN"
    assert filas[0].objetivo == "user:5"
