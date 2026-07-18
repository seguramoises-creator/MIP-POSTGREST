"""RBAC Fase 1 — T1: roles nuevos + modelos de seguridad (nivel ORM/enum, sin BD)."""
from app.models.usuario import Rol, Usuario
from app.models.seguridad_rbac import Recurso, RolPermiso, AuditoriaSeguridad


def test_roles_nuevos_en_enum():
    for r in ("GERENTE_MARKETING", "GERENTE_MEDICO", "ANALISTA_DATOS", "FINANZAS"):
        assert hasattr(Rol, r), f"falta el rol {r}"


def test_roles_previos_intactos():
    for r in ("ADMIN", "PRESIDENCIA", "DIR_COMERCIAL", "GERENTE_PRODUCTIVIDAD",
              "GERENTE_DISTRITO", "GERENTE_MARCA", "REPRESENTANTE_MEDICO", "CONSULTA",
              "CAPACITACION"):
        assert hasattr(Rol, r)


def test_usuario_tiene_roles_actualizado_en():
    assert "roles_actualizado_en" in Usuario.__table__.columns


def test_modelos_seguridad_en_esquema_security():
    assert Recurso.__table__.schema == "Security"
    assert RolPermiso.__table__.schema == "Security"
    assert AuditoriaSeguridad.__table__.schema == "Security"


def test_rolpermiso_llave_unica():
    uniques = [c for c in RolPermiso.__table__.constraints
               if c.__class__.__name__ == "UniqueConstraint"]
    cols = {tuple(col.name for col in u.columns) for u in uniques}
    assert ("rol", "recurso", "accion") in cols
