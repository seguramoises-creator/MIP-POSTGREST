"""Modelo de datos de la Ampliación del Módulo de Formación.

Estas pruebas cuidan invariantes que el requerimiento marca como REQUISITOS DE
DISEÑO, no como detalles de implementación: si alguien las rompe, el módulo
sigue arrancando pero deja de cumplir lo acordado con el cliente.

No necesitan base de datos: leen la metadata de SQLAlchemy, que es la misma
fuente de la que sale la migración.
"""
import pytest

from app.db.database import Base
from app.models import formacion, ia_conexion  # noqa: F401

TABLAS = {n.split(".", 1)[1]: t for n, t in Base.metadata.tables.items()
          if n.startswith("formacion.")}
IA = Base.metadata.tables["Security.DIM_IAConexion"]


def _unicos(tabla):
    """Conjuntos de columnas con restricción de unicidad (constraint o índice)."""
    conjuntos = [{c.name for c in u.columns}
          for u in tabla.constraints if type(u).__name__ == "UniqueConstraint"]
    conjuntos += [{c.name for c in i.columns} for i in tabla.indexes if i.unique]
    return conjuntos


def test_estan_las_tablas_de_las_nueve_piezas():
    """Las 9 piezas del §0 se reparten en estas tablas. Dos NO vienen en el
    requerimiento y se agregaron por necesidad — ver docstring de formacion.py:
    OnboardingPasoProgreso (trazabilidad de quién marcó cada paso) y
    RefuerzoCapsula (sin pregunta con identidad no hay 'pregunta más acertada')."""
    esperadas = {
        "ProductoLinea", "OnboardingPlantilla", "OnboardingPaso",
        "OnboardingAsignacion", "OnboardingPasoProgreso",
        "BibliotecaMaterial", "BibliotecaConfirmacion",
        "ParametroFrecuenciaLSII", "CalendarioCoachingSugerido",
        "RankingFormacionPuntos",
        "RefuerzoCampana", "RefuerzoRondaProgramada", "RefuerzoCapsula",
        "RefuerzoRespuesta",
        "SimulacroSesion", "SimulacroRonda", "SimulacroResultado",
        "ParametroFormacion", "PlanCierreBrecha",
    }
    assert set(TABLAS) == esperadas


def test_participacion_y_acierto_son_columnas_separadas():
    """§10.8, requisito de diseño explícito: las dos métricas NUNCA se mezclan en
    un solo número. Una respuesta rápida y equivocada debe poder verse como alta
    participación y bajo acierto a la vez."""
    c = TABLAS["RefuerzoRespuesta"].c
    assert "pct_puntaje_participacion" in c
    assert "es_acierto" in c
    # Y el insumo de cada una: el tiempo alimenta participación (§10.6), la
    # opción elegida alimenta acierto (§10.7).
    assert "tiempo_respuesta_seg" in c
    assert "opcion_seleccionada" in c


def test_el_reto_guarda_la_opcion_correcta_y_su_explicacion():
    """§10.7: la corrección es instantánea, en la misma interacción. Eso exige
    que la respuesta correcta y el porqué ya estén guardados junto a la cápsula,
    no que se calculen después."""
    c = TABLAS["RefuerzoCapsula"].c
    assert "opcion_correcta" in c
    assert "explicacion" in c


def test_una_confirmacion_de_lectura_por_material_y_representante():
    """§5.3: sin este único, un RM podría confirmar dos veces el mismo material
    e inflar su progreso hasta desbloquear un examen sin haber leído el resto."""
    assert {"material_id", "rm_id"} in _unicos(TABLAS["BibliotecaConfirmacion"])


def test_una_respuesta_por_capsula_y_representante():
    """Sin este único, reintentar una cápsula permitiría mejorar el % de aciertos
    a base de repetir hasta acertar."""
    assert {"capsula_id", "rm_id"} in _unicos(TABLAS["RefuerzoRespuesta"])


def test_el_material_puede_marcarse_obligatorio_y_lo_es_por_defecto():
    """§5.3: el cliente pidió que la lectura obligatoria sea la norma, no la
    excepción — el checkbox viene activado."""
    col = TABLAS["BibliotecaMaterial"].c["obligatorio"]
    assert col.nullable is False
    assert col.default.arg is True


def test_el_material_se_sube_una_vez_y_sirve_en_tres_lugares():
    """§4.3: el mismo archivo alimenta el examen, la Biblioteca y la Ayuda Visual
    de Coaching. Si no se pudiera enlazar a los tres, habría que subirlo tres
    veces y se desincronizarían."""
    c = TABLAS["BibliotecaMaterial"].c
    assert "usado_en_examen_id" in c
    assert "usado_en_coaching_av" in c


def test_el_firewall_phrma_queda_registrado():
    """§2: el contenido científico que sube Capacitación debe quedar aprobado por
    Gerente Médico antes de publicarse a los RM."""
    assert "aprobado_por_gm" in TABLAS["BibliotecaMaterial"].c
    assert "aprobado_por_gm" in TABLAS["RefuerzoCampana"].c


def test_el_paso_declara_si_bloquea_y_quien_lo_marca():
    """§4.5 dejó ABIERTO si la secuencia es estricta o admite pasos en paralelo
    (punto abierto 1). El campo existe desde ya para no necesitar migración
    cuando el cliente decida. Y §4.6 reparte quién marca cada paso entre cuatro
    roles distintos."""
    c = TABLAS["OnboardingPaso"].c
    assert "bloqueante" in c
    assert "quien_lo_marca" in c


def test_el_producto_declara_su_papel_en_la_ruta():
    """§4.3: cada producto 'principal' agrega un paso DAVID a la ruta; un
    'relacionado' solo aporta material. Es lo que da forma a la ruta."""
    assert "rol_en_ruta" in TABLAS["ProductoLinea"].c


def test_el_calendario_guarda_el_cuadrante_del_momento():
    """§7.5: es un snapshot a propósito. El cuadrante del RM cambia con el
    tiempo, y sin esta foto no se podría auditar por qué se sugirió esa
    frecuencia."""
    assert "cuadrante_al_generar" in TABLAS["CalendarioCoachingSugerido"].c


def test_los_umbrales_no_estan_incrustados_en_el_codigo():
    """§12.3 y §17.5: tanto la frecuencia por cuadrante como los umbrales de las
    5 reglas son valores ilustrativos del mockup, pendientes de confirmar. Tienen
    que vivir en tabla para poder cambiarlos sin desplegar."""
    assert "visitas_por_ciclo" in TABLAS["ParametroFrecuenciaLSII"].c
    assert {"pais_codigo", "clave"} in _unicos(TABLAS["ParametroFormacion"])


def test_el_ranking_desglosa_sus_cuatro_componentes():
    """§8.2: el RM debe poder ver de dónde sale su posición, no solo el total."""
    c = TABLAS["RankingFormacionPuntos"].c
    for comp in ("puntos_certificacion", "puntos_examenes",
                 "puntos_refuerzo", "puntos_onboarding", "puntos_total"):
        assert comp in c


def test_el_simulacro_usa_la_misma_escala_que_coaching():
    """§9.3 paso 5: la calificación va en D/P/A/E (1-4) igual que Coaching, para
    que los resultados de los dos módulos sean comparables."""
    c = TABLAS["SimulacroResultado"].c
    for k in ("calificacion_apertura", "calificacion_desarrollo",
              "calificacion_cierre", "calificacion_general"):
        assert k in c


def test_la_ronda_del_simulacro_se_ancla_a_una_fase_more():
    """§9.2.5: cada ronda pertenece a una de las 4 fases, y dentro de Desarrollo
    a una de las 6 técnicas nombradas. No se inventa contenido del modelo."""
    c = TABLAS["SimulacroRonda"].c
    assert "fase_more" in c
    assert "tecnica_objecion" in c


# ---------------------------------------------------------------------------
# §20 — Conexiones de IA
# ---------------------------------------------------------------------------

def test_la_conexion_de_ia_separa_etiqueta_humana_de_tipo_tecnico():
    """§20.4: `nombre` es la etiqueta que el cliente pidió para 'digitar el
    nombre de la IA'; `proveedor_tipo` es lo que decide qué adaptador corre. Si
    fueran el mismo campo, renombrar una conexión cambiaría el adaptador."""
    assert "nombre" in IA.c
    assert "proveedor_tipo" in IA.c


def test_las_credenciales_de_ia_no_se_guardan_en_claro():
    """§20.6, no negociable: cifradas en reposo. El nombre de la columna lo deja
    explícito para que nadie escriba ahí un valor plano por descuido."""
    assert "credencial_1_cifrada" in IA.c
    assert "credencial_2_cifrada" in IA.c
    planas = [n for n in IA.c.keys()
              if n in ("api_key", "password", "contrasena", "secret", "token")]
    assert not planas, planas


def test_la_segunda_credencial_es_opcional():
    """§20.4 punto 5: la mayoría de proveedores usan solo una API Key. Forzar dos
    credenciales obligaría a inventar un 'usuario' que en OpenAI o Anthropic no
    existe."""
    assert IA.c["credencial_2_cifrada"].nullable is True


def test_el_endpoint_es_editable_incluso_en_proveedores_conocidos():
    """§20.4 punto 4: Azure OpenAI exige un endpoint propio por cuenta, y hay
    clientes con instancias regionales. Un endpoint fijo por proveedor los
    dejaría fuera."""
    assert "endpoint_url" in IA.c


def test_no_se_puede_activar_sin_haber_verificado():
    """§20.4 punto 8: no se permite guardar como activa una conexión que nunca
    pasó 'Probar conexión'. El campo es el que permite exigirlo en el servicio."""
    assert "verificada" in IA.c
    assert "activa" in IA.c


@pytest.mark.parametrize("tabla", ["OnboardingPasoProgreso", "BibliotecaConfirmacion",
                                   "RefuerzoRespuesta"])
def test_las_marcas_de_tiempo_criticas_existen(tabla):
    """Mismo criterio de integridad que `fecha_coaching` en Coaching: la hora la
    pone el servidor y no el cliente, porque de ella dependen el puntaje de
    participación y la prueba de que se leyó el material."""
    c = TABLAS[tabla].c
    assert any("timestamp" in n or "completado_en" in n for n in c.keys())
