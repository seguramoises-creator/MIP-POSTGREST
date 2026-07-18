"""RBAC Fase 1 — T3: motor can() (implicación de acciones + tope de export por lectura).

Incluye la parametrizada 28×10 reusando el ORACULO del test de la matriz.
"""
import pytest
from types import SimpleNamespace

from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso, RECURSOS
from app.core.authz import engine
from tests.test_authz_matriz import ORACULO, COLS


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id)


@pytest.mark.parametrize("recurso", list(ORACULO.keys()))
@pytest.mark.parametrize("idx", range(10))
def test_can_para_cada_celda(recurso, idx):
    rol = COLS[idx]
    celda = ORACULO[recurso][idx]
    u = U(rol)
    if celda is None:
        for a in Accion:
            assert engine.can(u, a, recurso) is None
    else:
        accion, alcance = celda
        if accion == Accion.ADMIN:
            for a in Accion:
                assert engine.can(u, a, recurso) == Alcance.ALL
        else:
            assert engine.can(u, accion, recurso) == alcance


def test_configure_implica_read():
    u = U(Rol.GERENTE_MARCA)  # configura categorizacion.detalle
    assert engine.can(u, Accion.READ, Recurso.CATEGORIZACION_DETALLE) == Alcance.ALL
    assert engine.can(u, Accion.CONFIGURE, Recurso.CATEGORIZACION_DETALLE) == Alcance.ALL


def test_approve_implica_read_pero_no_configure():
    u = U(Rol.PRESIDENCIA)  # Director aprueba costoroi.configurar
    assert engine.can(u, Accion.READ, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(u, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(u, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) is None


def test_register_implica_read_mismo_alcance():
    u = U(Rol.REPRESENTANTE_MEDICO)
    assert engine.can(u, Accion.READ, Recurso.VISITA_REGISTRAR) == Alcance.OWN


def test_export_no_deriva_de_read():
    u = U(Rol.ANALISTA_DATOS)  # lee dashboard (all) pero eso no es export sobre dashboard
    assert engine.can(u, Accion.EXPORT, Recurso.DASHBOARD_EJECUTIVO) is None


def test_alcance_export_modulo_capado_por_lectura():
    gd = U(Rol.GERENTE_DISTRITO)  # export team, lee dashboard team → team
    assert engine.alcance_export_modulo(gd, Recurso.DASHBOARD_EJECUTIVO) == Alcance.TEAM
    # GD no lee config.parametros → export sobre ese módulo = None
    assert engine.alcance_export_modulo(gd, Recurso.CONFIG_PARAMETROS) is None
    # GD configura parrilla.configurar (⇒ read all) y exporta team → min = team
    assert engine.alcance_export_modulo(gd, Recurso.PARRILLA_CONFIGURAR) == Alcance.TEAM
    rm = U(Rol.REPRESENTANTE_MEDICO)  # RM no exporta nada
    assert engine.alcance_export_modulo(rm, Recurso.DASHBOARD_EJECUTIVO) is None
    ana = U(Rol.ANALISTA_DATOS)  # export all, lee medico.panel all → all
    assert engine.alcance_export_modulo(ana, Recurso.MEDICO_PANEL) == Alcance.ALL
    adm = U(Rol.ADMIN)  # admin: export efectivo = all en cualquier módulo
    assert engine.alcance_export_modulo(adm, Recurso.PARRILLA_CONFIGURAR) == Alcance.ALL


def test_admin_concede_todo():
    a = U(Rol.ADMIN)
    for recurso in RECURSOS:
        for accion in Accion:
            assert engine.can(a, accion, recurso) == Alcance.ALL


def test_firewall_medico():
    med = U(Rol.GERENTE_MEDICO)
    for recurso in (Recurso.PRODUCTIVIDAD_COMERCIAL, Recurso.RANKING_RKT,
                    Recurso.COSTOROI_VER, Recurso.COSTOROI_CONFIGURAR):
        for a in Accion:
            assert engine.can(med, a, recurso) is None, f"firewall roto en {recurso}/{a}"


def test_solo_admin_gestiona_usuarios():
    for rol in Rol:
        u = U(rol)
        esperado = Alcance.ALL if rol == Rol.ADMIN else None
        assert engine.can(u, Accion.ADMIN, Recurso.CONFIG_USUARIOS) == esperado
    # ni Presidencia (Director General) tiene lectura sobre usuarios
    assert engine.can(U(Rol.PRESIDENCIA), Accion.READ, Recurso.CONFIG_USUARIOS) is None


def test_analista_no_escribe():
    ana = U(Rol.ANALISTA_DATOS)
    for recurso in RECURSOS:
        for a in (Accion.REGISTER, Accion.CONFIGURE, Accion.APPROVE, Accion.ADMIN):
            assert engine.can(ana, a, recurso) is None


def test_finanzas_configura_director_aprueba():
    fin = U(Rol.FINANZAS)
    dire = U(Rol.PRESIDENCIA)
    assert engine.can(fin, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(fin, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) is None
    assert engine.can(dire, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(dire, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) is None


def test_puede_booleano():
    assert engine.puede(U(Rol.REPRESENTANTE_MEDICO), Accion.REGISTER, Recurso.VISITA_REGISTRAR)
    assert not engine.puede(U(Rol.REPRESENTANTE_MEDICO), Accion.CONFIGURE, Recurso.CONFIG_USUARIOS)
