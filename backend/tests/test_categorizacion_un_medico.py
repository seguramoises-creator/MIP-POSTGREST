"""Motor de categorización de UN médico (alta desde el Panel) — Bloque B.

Prueba `_puntuar` (pura, sin BD): debe sumar el PuntajePct de la mejor regla de cada
componente REQUERIDO y ubicar la clase por el rango de puntaje — exactamente como el
bucle de `calcular_categorias_py` (Excel), para que un médico dé la misma categoría
por cualquiera de los dos caminos.
"""
from app.services import categorizacion_service as svc


def _comp(key, codigo, requerido=True):
    return {"ComponenteKey": key, "CodigoComponente": codigo, "Requerido": requerido}


def _regla(key, comp, pct, vmin=None, vmax=None, vtxt=None, criterio=None):
    return {"ReglaKey": key, "ComponenteKey": comp, "ValorMinimo": vmin, "ValorMaximo": vmax,
            "ValorTexto": vtxt, "Criterio": criterio, "PuntajePct": pct}


# 5 componentes: 2 numéricos + 3 de texto (mismo mapeo que el Excel).
COMPS = [_comp(1, "PACIENTES_SEMANA"), _comp(2, "PODER_ADQUISITIVO"),
         _comp(3, "POTENCIAL_PRESCRIPCION"), _comp(4, "UBICACION_TERRITORIAL_CM"), _comp(5, "KOL")]

REGLAS = {
    1: [_regla(10, 1, 30, vmin=50), _regla(11, 1, 10, vmin=0, vmax=49)],
    2: [_regla(20, 2, 20, vmin=1000), _regla(21, 2, 5, vmin=0, vmax=999)],
    3: [_regla(30, 3, 10, vtxt="Alto"), _regla(31, 3, 2, vtxt="Bajo")],
    4: [_regla(40, 4, 30, vtxt="Alta"), _regla(41, 4, 5, vtxt="Mala")],
    5: [_regla(50, 5, 10, vtxt="SI"), _regla(51, 5, 0, vtxt="NO")],
}
CLASES = [
    {"ClasificacionKey": 1, "Clase": "A", "PuntajeMinPct": 80, "PuntajeMaxPct": 100},
    {"ClasificacionKey": 2, "Clase": "B", "PuntajeMinPct": 60, "PuntajeMaxPct": 79},
    {"ClasificacionKey": 3, "Clase": "C", "PuntajeMinPct": 30, "PuntajeMaxPct": 59},
    {"ClasificacionKey": 4, "Clase": "D", "PuntajeMinPct": 0, "PuntajeMaxPct": 29},
]


def test_medico_tope_da_categoria_A():
    r = svc._puntuar(COMPS, REGLAS, CLASES, {
        "PacientesSemana": 80, "CostoConsulta": 1500, "RecetasSemana": "Alto",
        "UbicacionTerritorialCM": "Alta", "KOL": "SI"})
    assert r["puntaje_pct"] == 100 and r["categoria"] == "A" and r["estado"] == "CALCULADO"


def test_medico_bajo_da_categoria_D():
    r = svc._puntuar(COMPS, REGLAS, CLASES, {
        "PacientesSemana": 10, "CostoConsulta": 500, "RecetasSemana": "Bajo",
        "UbicacionTerritorialCM": "Mala", "KOL": "NO"})
    assert r["puntaje_pct"] == 22 and r["categoria"] == "D"


def test_valor_de_texto_es_case_insensitive():
    """El matcheo de texto reusa _regla_aplica (compara en mayúsculas), como el Excel."""
    r = svc._puntuar(COMPS, REGLAS, CLASES, {
        "PacientesSemana": 80, "CostoConsulta": 1500, "RecetasSemana": "alto",
        "UbicacionTerritorialCM": "ALTA", "KOL": "si"})
    assert r["categoria"] == "A"


def test_sin_regla_para_un_requerido_queda_PENDIENTE_sin_categoria():
    """Config incompleta → NO se inventa categoría: el GD lo ve como no clasificable."""
    r = svc._puntuar(COMPS, REGLAS, CLASES, {
        "PacientesSemana": 80, "CostoConsulta": 1500, "RecetasSemana": "Inexistente",
        "UbicacionTerritorialCM": "Alta", "KOL": "SI"})
    assert r["estado"] == "PENDIENTE"
    assert any(d["estado"] == "SIN_REGLA" for d in r["detalle"])


def test_componente_no_requerido_no_bloquea_el_calculo():
    comps = COMPS[:4] + [_comp(5, "KOL", requerido=False)]
    r = svc._puntuar(comps, REGLAS, CLASES, {
        "PacientesSemana": 80, "CostoConsulta": 1500, "RecetasSemana": "Alto",
        "UbicacionTerritorialCM": "Alta", "KOL": "Inexistente"})
    assert r["estado"] == "CALCULADO" and r["puntaje_pct"] == 90 and r["categoria"] == "A"


# ── Contrato plantilla ↔ alta de médico ───────────────────────────────────────
def test_los_campos_de_la_plantilla_son_los_que_espera_el_alta():
    """El formulario se arma con `campo` de la plantilla y envía esas mismas claves al
    endpoint de alta. Si divergen, el usuario llena los 5 criterios y GUARDAR nunca se
    habilita (bug jul-2026: la plantilla devolvía los nombres internos del Excel
    —'PacientesSemana', 'RecetasSemana'…— en vez de los de ClasificacionCrear)."""
    from app.schemas.visita import ClasificacionCrear
    assert set(svc._CAMPO_API.values()) == set(ClasificacionCrear.model_fields.keys())


def test_campo_api_cubre_los_componentes_del_motor():
    """Todo componente que el motor puntúa debe ser capturable desde el formulario."""
    componentes = set(svc._COMP_NUM) | set(svc._COMP_TXT)
    assert componentes == set(svc._CAMPO_API)
