"""Tests del alcance de datos en Costo & ROI (jul-2026).

Regla del cliente: "este dato es meramente gerencial, no debe ser visto por el representante.
De esta pantalla solo deben tener acceso a las unidades que hay que producir por contacto por
producto de su línea para lograr el 100% de su presupuesto, y al impacto económico que la
cobertura está teniendo en el presupuesto de su línea".
"""
import inspect

from app.api.v1.routers import visita as router_vis
from app.services import visita_costo_service as svc


def _fuente(fn):
    return inspect.getsource(fn)


# ── Los endpoints financieros ya NO admiten al representante ──────────────────

def test_estructura_financiera_completa_es_solo_gestion():
    """`/costo/estructura` trae salarios, costos, ROI de la fuerza de venta y presupuesto
    total. Antes usaba RequireVisita (incluye al representante) — era una fuga."""
    assert "current_user=RequireFinanciero" in _fuente(router_vis.costo_estructura)


def test_parametros_de_costo_son_solo_gestion():
    """Salario, viáticos, materiales: dato financiero."""
    assert "current_user=RequireFinanciero" in _fuente(router_vis.obtener_parametros_costo)


def test_roi_por_vm_es_solo_gestion():
    assert "current_user=RequireFinanciero" in _fuente(router_vis.costo_roi)


def test_require_financiero_no_incluye_al_representante():
    fuente = inspect.getsource(router_vis)
    linea = [l for l in fuente.splitlines() if "RequireFinanciero = Depends" in l][0]
    # La constante y las 4 líneas siguientes (por si el listado de roles envuelve).
    bloque = fuente.split("RequireFinanciero = Depends", 1)[1][:200]
    assert "REPRESENTANTE_MEDICO" not in bloque


# ── La vista del representante es un recorte, no el modelo completo ───────────

def test_mi_linea_exige_ser_representante():
    assert 'if _rol(current_user) != "REPRESENTANTE_MEDICO"' in _fuente(router_vis.costo_mi_linea)


def _salida_representante(monkeypatch):
    """Ejecuta `vista_representante` sobre un `calcular_full` de mentira con TODO lo gerencial,
    y devuelve lo que realmente sale. Prueba comportamiento, no texto del código."""
    full_completo = {
        "ciclo_id": 41, "linea_id": 2, "moneda": "RD$", "configurado": True,
        "fijo": {"costo_fijo_total": 999999, "salario_ciclo": 50000, "costo_fijo_visita": 300},
        "muestras": {"costo_variable_visita": 12},
        "pool": {"pool_total": 88888, "productos": [{"pool_ventas": 88888}]},
        "plan_anual": {"presupuesto_total": 500000, "presupuesto_por_vm": 5000,
                       "contactos_anio": 2090, "productiv_obj_contacto": 239,
                       "productos": [{"producto": "PROD-X", "presupuesto_anual": 500000,
                                      "precio_prom": 100.0, "productiv_obj_contacto": 239,
                                      "unidades_obj_contacto": 2.4, "cumplimiento_pct": 80,
                                      "retorno_real": 191}]},
        "resumen": {"costo_total_visita": 312, "roi_promedio": 3.1, "productos": []},
        "impacto": {"categorias": [{"categoria": "A", "medicos_sin_visitar": 251}],
                    "venta_riesgo_bajo": 1000, "venta_riesgo_alto": 2000,
                    "total_medicos_sin_visitar": 251, "headcount_equivalente": 1.3},
    }
    monkeypatch.setattr(svc, "calcular_full", lambda db, c, l: full_completo)
    return svc.vista_representante(None, 41, 2)


def _todas_las_claves(obj):
    """Todas las claves de dict, recorriendo listas y sub-dicts."""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k); out |= _todas_las_claves(v)
    elif isinstance(obj, list):
        for it in obj:
            out |= _todas_las_claves(it)
    return out


def test_vista_representante_solo_expone_las_dos_piezas_autorizadas(monkeypatch):
    """Comportamiento real: NINGUNA cifra gerencial aparece en la salida."""
    r = _salida_representante(monkeypatch)
    assert "unidades_por_contacto" in r and "impacto_cobertura" in r
    claves = _todas_las_claves(r)
    for prohibido in ("costo_fijo_total", "salario_ciclo", "costo_fijo_visita",
                      "roi_promedio", "costo_total_visita", "presupuesto_total",
                      "presupuesto_por_vm", "headcount_equivalente", "pool_total"):
        assert prohibido not in claves, f"se filtró {prohibido!r} al representante"


def test_las_unidades_no_arrastran_cifras_de_negocio_de_la_linea(monkeypatch):
    """De cada producto solo salen producto/unidades/cumplimiento; nunca el dinero de la línea."""
    r = _salida_representante(monkeypatch)
    metas = r["unidades_por_contacto"]
    assert metas and set(metas[0].keys()) == {"producto", "unidades_obj_contacto", "cumplimiento_pct"}
    for prohibido in ("presupuesto_anual", "precio_prom", "retorno_real", "productiv_obj_contacto"):
        assert prohibido not in metas[0]
