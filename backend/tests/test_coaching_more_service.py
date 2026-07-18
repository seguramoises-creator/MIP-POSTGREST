"""Tests del Módulo de Coaching (MORE): cálculo de promedios (fixture Candy Domínguez)
y reglas de bloqueo del guardado (Sección 8 del spec)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import coaching_more_service as svc


# ── Cálculo de promedios (puro) ───────────────────────────────────────────────

def _fixture_items():
    """26 ítems con las calificaciones que producen los promedios de sección del
    Excel real de Candy Domínguez → promedio general 3.43."""
    data = {
        "Planificación": [4, 4, 4, 3],            # 3.75
        "Apertura": [4, 4, 4, 3],                  # 3.75
        "Desarrollo de la Visita": [3, 3, 3],      # 3.00
        "AV: Ayuda Visual": [3, 2, 3, 2],          # 2.50
        "Conocimientos Científicos": [4, 4, 4],    # 4.00
        "Cierre": [3, 4, 3, 3],                    # 3.25
        "Seguimiento": [4, 4, 4, 3],               # 3.75
    }
    items = []
    for sec, vals in data.items():
        for v in vals:
            items.append({"seccion": sec, "calificacion": v})
    return items


def test_promedio_general_fixture_candy():
    r = svc.calcular_promedios(_fixture_items())
    assert r["general"] == pytest.approx(3.43, abs=0.01)


def test_promedios_de_seccion_fixture():
    r = svc.calcular_promedios(_fixture_items())["secciones"]
    assert r["Planificación"] == pytest.approx(3.75, abs=0.01)
    assert r["Desarrollo de la Visita"] == pytest.approx(3.00, abs=0.01)
    assert r["AV: Ayuda Visual"] == pytest.approx(2.50, abs=0.01)
    assert r["Conocimientos Científicos"] == pytest.approx(4.00, abs=0.01)


def test_promedio_sin_items():
    assert svc.calcular_promedios([])["general"] == 0.0


# ── Validaciones que bloquean el guardado (Sección 8) ─────────────────────────

def _item(sec, cal):
    return SimpleNamespace(seccion=sec, calificacion=cal, item_texto="x", item_catalogo_id=None)


def _datos_validos():
    items = [SimpleNamespace(seccion=i["seccion"], calificacion=i["calificacion"],
                             item_texto="x", item_catalogo_id=None) for i in _fixture_items()]
    return SimpleNamespace(
        rm_id=1, fecha_coaching=date(2026, 7, 10), medicos_vistos=9, items=items,
        fortalezas="aperturas y sondeos", areas_perfeccionar="cierre",
        plan_que_haras="practicarlo", plan_como_haras="con MORE", plan_como_veras="mejora en cierre",
        plan_fecha_seguimiento=date(2026, 7, 17), rm_acuerdo="de_acuerdo",
        rm_justificacion_desacuerdo=None, rm_firma_imagen="data:image/png;base64,AAA",
    )


@pytest.fixture(autouse=True)
def _items26(monkeypatch):
    # El catálogo activo tiene 26 ítems (evita tocar la BD en los tests).
    monkeypatch.setattr(svc, "_items_esperados", lambda db: 26)


def test_hoja_valida_sin_errores():
    assert svc.validar(None, _datos_validos()) == []


def test_falta_firma_bloquea():
    d = _datos_validos(); d.rm_firma_imagen = ""
    errs = svc.validar(None, d)
    assert any("Firma" in e for e in errs)


def test_no_de_acuerdo_sin_justificacion_bloquea():
    d = _datos_validos(); d.rm_acuerdo = "no_de_acuerdo"; d.rm_justificacion_desacuerdo = ""
    errs = svc.validar(None, d)
    assert any("Justificación" in e for e in errs)


def test_no_de_acuerdo_con_justificacion_ok():
    d = _datos_validos(); d.rm_acuerdo = "no_de_acuerdo"; d.rm_justificacion_desacuerdo = "no fue justo"
    assert svc.validar(None, d) == []


def test_items_incompletos_bloquea():
    d = _datos_validos(); d.items = d.items[:20]  # solo 20 de 26
    errs = svc.validar(None, d)
    assert any("Faltan ítems" in e for e in errs)


def test_fortalezas_obligatoria():
    d = _datos_validos(); d.fortalezas = "  "
    errs = svc.validar(None, d)
    assert any("Fortalezas" in e for e in errs)


def test_fecha_seguimiento_debe_ser_posterior():
    d = _datos_validos(); d.plan_fecha_seguimiento = d.fecha_coaching  # igual, no posterior
    errs = svc.validar(None, d)
    assert any("posterior" in e for e in errs)


def test_plan_accion_obligatorio():
    d = _datos_validos(); d.plan_que_haras = ""
    errs = svc.validar(None, d)
    assert any("¿Qué harás?" in e for e in errs)


# ── Inmutabilidad total: no se corrige/modifica una hoja guardada ─────────────

def test_crear_hoja_rechaza_cualquier_correccion():
    """Regla del cliente (jul-2026): una hoja guardada NO se modifica ni se corrige BAJO NINGÚN
    concepto. `crear_hoja` rechaza cualquier `corrige_a_id` — la barrera del servicio, no solo
    del endpoint retirado."""
    d = _datos_validos(); d.corrige_a_id = 4
    with pytest.raises(ValueError, match="inmutables"):
        svc.crear_hoja(MagicMock(), SimpleNamespace(rol=None, id=1), d)


def test_el_endpoint_de_correccion_esta_retirado():
    import inspect
    from app.api.v1.routers import coaching_more
    fuente = inspect.getsource(coaching_more.corregir)
    assert "410" in fuente and "inmutables" in fuente


# ── Ciclo de la hoja: lo define la FECHA, no cuál ciclo esté abierto ───────────

def test_ciclo_de_la_hoja_es_el_que_contiene_la_fecha():
    """Regresión: una hoja del 10-jul quedó archivada en C12-2026 porque diciembre
    estaba abierto y `ciclo_por_defecto` toma el ciclo abierto de número más alto."""
    c07 = SimpleNamespace(id=41, pais_codigo="DO")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = c07
    rm = SimpleNamespace(id=47, pais_codigo="DO")

    ciclo_id, pais = svc._ciclo_pais_de_rm(db, rm, date(2026, 7, 10))

    assert (ciclo_id, pais) == (41, "DO")


def test_sin_ciclo_que_cubra_la_fecha_cae_al_ciclo_abierto(monkeypatch):
    """Los ciclos van del 1 al 28: un coaching del 30 no lo cubre ninguna ventana."""
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    import app.services.visita_cobertura_service as vcs
    monkeypatch.setattr(vcs, "ciclo_por_defecto", lambda _db, vm_id: 41)
    rm = SimpleNamespace(id=47, pais_codigo="DO")

    ciclo_id, pais = svc._ciclo_pais_de_rm(db, rm, date(2026, 7, 30))

    assert (ciclo_id, pais) == (41, "DO")
