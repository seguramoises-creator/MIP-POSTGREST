"""RBAC Fase 2 — wiring de guards en endpoints reales (ruta de DENEGACIÓN, sin BD).

Verifica que el guard de la matriz rechaza al rol denegado ANTES de tocar la BD. Se sobreescribe
get_current_active_user; el guard require() lo usa. La ruta permitida haría queries (necesita BD),
así que aquí solo se comprueba el 403 del firewall/denegación por defecto.
"""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user


def _client(router, user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id, id=1)


def test_productividad_firewall_medico_403():
    from app.api.v1.routers.productividad import router
    r = _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/productividad")
    assert r.status_code == 403


def test_productividad_resumen_firewall_medico_403():
    from app.api.v1.routers.productividad import router
    r = _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/productividad/resumen")
    assert r.status_code == 403


def test_ranking_firewall_medico_403():
    from app.api.v1.routers.ranking import router
    assert _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/ranking").status_code == 403
    assert _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/ranking/mi-posicion").status_code == 403


def test_cobertura_predictiva_finanzas_403():
    from app.api.v1.routers.cobertura_predictiva import router
    # cobertura.predictiva: FINANZAS sin acceso (matriz)
    assert _client(router, U(Rol.FINANZAS)).get("/api/v1/cobertura-predictiva/vivo/dashboard").status_code == 403
    # RM sí pasa el guard (el scope propio lo resuelve el cuerpo)
    assert _client(router, U(Rol.REPRESENTANTE_MEDICO, rm_id=1)).get(
        "/api/v1/cobertura-predictiva/vivo/ciclos").status_code != 403


def test_coaching_more_hoja_lectura():
    from app.api.v1.routers.coaching_more import router
    # coaching.hoja: GERENTE_MARCA/FINANZAS sin lectura → 403 en listar
    assert _client(router, U(Rol.GERENTE_MARCA)).get("/api/v1/coaching-more").status_code == 403
    assert _client(router, U(Rol.FINANZAS)).get("/api/v1/coaching-more").status_code == 403
    # RM sí (lee sus propias hojas; el servicio filtra)
    assert _client(router, U(Rol.REPRESENTANTE_MEDICO, rm_id=1)).get("/api/v1/coaching-more").status_code != 403


def test_coaching_kpi_lectura():
    from app.api.v1.routers.coaching import router
    # coaching.kpi: RM sin acceso (matriz) → 403 en la lista legacy
    assert _client(router, U(Rol.REPRESENTANTE_MEDICO, rm_id=1)).get("/api/v1/coaching").status_code == 403
    # GERENTE_DISTRITO sí (read team)
    assert _client(router, U(Rol.GERENTE_DISTRITO, gerente_id=1)).get("/api/v1/coaching").status_code != 403


def test_exportacion_capada_por_lectura():
    from app.api.v1.routers.exportacion import router
    # GERENTE_MEDICO no lee ranking.rkt → no puede exportar ranking → 403
    assert _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/exportacion/ranking/excel").status_code == 403
    # RM: exportacion=none → 403
    assert _client(router, U(Rol.REPRESENTANTE_MEDICO, rm_id=1)).get("/api/v1/exportacion/ranking/pdf").status_code == 403
    # GERENTE_DISTRITO: export team (capado, filtrado) → pasa el guard
    assert _client(router, U(Rol.GERENTE_DISTRITO, gerente_id=1)).get(
        "/api/v1/exportacion/ranking/excel").status_code != 403


def test_visita_planeacion_registrar_solo_rm():
    from app.api.v1.routers.visita import router
    # planeacion.ciclo: GD NO registra (solo lee equipo) → publicar 403
    assert _client(router, U(Rol.GERENTE_DISTRITO, gerente_id=1)).post(
        "/api/v1/visita/planeacion/publicar").status_code == 403
    # GERENTE_MARCA no lee planeacion → estado 403
    assert _client(router, U(Rol.GERENTE_MARCA)).get(
        "/api/v1/visita/planeacion/estado").status_code == 403
    # RM sí registra (pasa el guard)
    assert _client(router, U(Rol.REPRESENTANTE_MEDICO, rm_id=1)).post(
        "/api/v1/visita/planeacion/publicar").status_code != 403


def test_categorizacion_detalle_config_gerente_producto():
    from app.api.v1.routers.admin import router
    # categorizacion.detalle configure: GD NO configura criterios → delete 403
    assert _client(router, U(Rol.GERENTE_DISTRITO)).delete(
        "/api/v1/admin/criterios-categoria/1").status_code == 403
    # GERENTE_MARCA (Gerente de Producto) sí → pasa el guard
    assert _client(router, U(Rol.GERENTE_MARCA)).delete(
        "/api/v1/admin/criterios-categoria/1").status_code != 403


def test_parrilla_configura_gerente_producto_no_gd():
    from app.api.v1.routers.visita import router
    # parrilla.configurar: GD NO configura (solo consulta) → publicar 403
    assert _client(router, U(Rol.GERENTE_DISTRITO, gerente_id=1)).post(
        "/api/v1/visita/parrilla/publicar", params={"linea_id": 1}).status_code == 403
    # GERENTE_MARCA (Gerente de Producto) sí configura → pasa el guard
    assert _client(router, U(Rol.GERENTE_MARCA)).post(
        "/api/v1/visita/parrilla/publicar", params={"linea_id": 1}).status_code != 403


def test_costoroi_segregacion_finanzas_configura_director_aprueba():
    from app.api.v1.routers.visita import router
    # Aprobar: FINANZAS no puede (solo configura) → 403; el Director sí pasa el guard
    assert _client(router, U(Rol.FINANZAS)).post(
        "/api/v1/visita/costo/estructura/aprobar").status_code == 403
    assert _client(router, U(Rol.PRESIDENCIA)).post(
        "/api/v1/visita/costo/estructura/aprobar").status_code != 403
    # Configurar (guardar parámetros): el Director NO configura → 403; FINANZAS sí pasa el guard
    assert _client(router, U(Rol.PRESIDENCIA)).post(
        "/api/v1/visita/costo/parametros", json={}).status_code == 403
    # Firewall Médico: GERENTE_MEDICO sin costoroi.configurar → aprobar 403
    assert _client(router, U(Rol.GERENTE_MEDICO)).post(
        "/api/v1/visita/costo/estructura/aprobar").status_code == 403
    # Reabrir: solo ADMIN; el Director no → 403
    assert _client(router, U(Rol.PRESIDENCIA)).post(
        "/api/v1/visita/costo/estructura/reabrir").status_code == 403
    assert _client(router, U(Rol.ADMIN)).post(
        "/api/v1/visita/costo/estructura/reabrir").status_code != 403
