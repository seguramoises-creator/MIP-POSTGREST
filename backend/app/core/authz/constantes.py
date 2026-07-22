"""RBAC/ABAC — constantes canónicas: acciones, alcances y los 28 recursos.

Ejes separados (nunca "Ver (equipo)" como string único):
- Accion: qué se hace.
- Alcance: sobre qué universo de datos (denegación por defecto = ausencia).
- Recurso: la funcionalidad (slug estable).

Ver spec `docs/superpowers/specs/2026-07-18-rbac-abac-seguridad-design.md` §4.
"""
from enum import Enum


class Accion(str, Enum):
    READ = "read"
    REGISTER = "register"
    CONFIGURE = "configure"
    APPROVE = "approve"
    EXPORT = "export"
    ADMIN = "admin"


class Alcance(str, Enum):
    NONE = "none"
    OWN = "own"
    TEAM = "team"
    ALL = "all"


_ORDEN = {Alcance.NONE: 0, Alcance.OWN: 1, Alcance.TEAM: 2, Alcance.ALL: 3}


def alcance_min(a: Alcance, b: Alcance) -> Alcance:
    """El menor de dos alcances (para capar export por lectura)."""
    return a if _ORDEN[a] <= _ORDEN[b] else b


class Recurso:
    """Slugs estables de los 28 recursos (filas de la matriz del spec §5)."""
    DASHBOARD_EJECUTIVO = "dashboard.ejecutivo"
    VISITA_REGISTRAR = "visita.registrar"
    MEDICO_PANEL = "medico.panel"
    CATEGORIZACION_BASICA = "categorizacion.basica"
    CATEGORIZACION_DETALLE = "categorizacion.detalle"
    PLANEACION_CICLO = "planeacion.ciclo"
    COBERTURA_DIARIA = "cobertura.diaria"
    COBERTURA_PREDICTIVA = "cobertura.predictiva"
    PARRILLA_CONFIGURAR = "parrilla.configurar"
    PARRILLA_CONSULTA = "parrilla.consulta"
    PRODUCTIVIDAD_COMERCIAL = "productividad.comercial"
    RANKING_RKT = "ranking.rkt"
    FARMACIA_CONFIGURACION = "farmacia.configuracion"
    FARMACIA_VISITA = "farmacia.visita"
    FARMACIA_COBERTURA = "farmacia.cobertura"
    COACHING_HOJA = "coaching.hoja"
    COACHING_KPI = "coaching.kpi"
    EXAMEN_RENDIR = "examen.rendir"
    EXAMEN_CONFIGURAR = "examen.configurar"
    INTELIGENCIA_MATRIZ = "inteligencia.matriz"
    ENCUESTA_CONFIGURAR = "inteligencia.encuesta.configurar"
    ENCUESTA_APLICAR = "inteligencia.encuesta.aplicar"
    COSTOROI_VER = "costoroi.ver"
    COSTOROI_CONFIGURAR = "costoroi.configurar"
    CONFIG_PRODUCTOS = "config.productos"
    CONFIG_USUARIOS = "config.usuarios"
    CONFIG_PARAMETROS = "config.parametros"
    EXPORTACION = "exportacion"
    # Recursos de módulos de la app fuera de las 28 funcionalidades del prompt (deuda #3, jul-2026)
    RECONOCIMIENTO = "reconocimiento"
    LSII_EVALUAR = "lsii.evaluar"
    LSII_ADMIN = "lsii.admin"
    ETL_CARGAR = "etl.cargar"
    # Módulo de Farmacias (jul-2026, plan `2026-07-22-modulo-farmacias.md`, Task 5). NOTA: las
    # filas `FARMACIA_CONFIGURACION`/`FARMACIA_VISITA`/`FARMACIA_COBERTURA` de arriba fueron
    # reservadas especulativamente por la deuda #3 (Fase 1, cuando el módulo aún no existía) y su
    # diseño (p.ej. GERENTE_PRODUCTIVIDAD denegado en `farmacia.configuracion`) NO coincide con el
    # diseño real aprobado en el spec de Farmacias. En vez de reescribir esas filas ya cubiertas
    # por el oráculo (fuera del alcance de la Tarea 5), se agregan estos 3 recursos NUEVOS para el
    # router real; las 3 filas antiguas quedan sin consumidor (deuda a reconciliar/retirar aparte).
    FARMACIA_PANEL = "farmacia.panel"
    FARMACIA_APROBAR = "farmacia.aprobar"
    FARMACIA_MAESTRO = "farmacia.maestro"


# (slug, nombre legible, módulo) — orden = filas del spec §5
RECURSOS_META: dict[str, tuple[str, str]] = {
    Recurso.DASHBOARD_EJECUTIVO: ("Dashboard Ejecutivo", "Visión general"),
    Recurso.VISITA_REGISTRAR: ("Registrar visita médica", "Registro de visita"),
    Recurso.MEDICO_PANEL: ("Catálogo de médicos y contacto", "Panel médico"),
    Recurso.CATEGORIZACION_BASICA: ("Categorización básica (A/B/C)", "Panel médico"),
    Recurso.CATEGORIZACION_DETALLE: ("Categorización detalle y pesos", "Panel médico"),
    Recurso.PLANEACION_CICLO: ("Planeación del ciclo", "Planeación y cobertura"),
    Recurso.COBERTURA_DIARIA: ("Cobertura diaria / Ruptura", "Planeación y cobertura"),
    Recurso.COBERTURA_PREDICTIVA: ("Cobertura predictiva", "Planeación y cobertura"),
    Recurso.PARRILLA_CONFIGURAR: ("Parrilla de muestras: configurar", "Comercial"),
    Recurso.PARRILLA_CONSULTA: ("Parrilla de muestras: consulta", "Comercial"),
    Recurso.PRODUCTIVIDAD_COMERCIAL: ("Productividad comercial", "Comercial"),
    Recurso.RANKING_RKT: ("Ranking general (RKT)", "Comercial"),
    Recurso.FARMACIA_CONFIGURACION: ("Configuración de farmacias", "Farmacias"),
    Recurso.FARMACIA_VISITA: ("Registro de visita a farmacia", "Farmacias"),
    Recurso.FARMACIA_COBERTURA: ("Cobertura de farmacias", "Farmacias"),
    Recurso.COACHING_HOJA: ("Hoja de acompañamiento GD→RM", "Coaching (MORE)"),
    Recurso.COACHING_KPI: ("KPI Coaching de equipo", "Coaching (MORE)"),
    Recurso.EXAMEN_RENDIR: ("Rendir examen de producto", "Formación / Exámenes"),
    Recurso.EXAMEN_CONFIGURAR: ("Configurar/publicar exámenes", "Formación / Exámenes"),
    Recurso.INTELIGENCIA_MATRIZ: ("Matriz de Potencial y Adopción", "Inteligencia de mercado"),
    Recurso.ENCUESTA_CONFIGURAR: ("Encuestas: crear y publicar", "Inteligencia de mercado"),
    Recurso.ENCUESTA_APLICAR: ("Encuestas: aplicar en visita", "Inteligencia de mercado"),
    Recurso.COSTOROI_VER: ("Ver Costo por Visita y ROI", "Costo y ROI"),
    Recurso.COSTOROI_CONFIGURAR: ("Configurar costos/pool/presupuesto", "Costo y ROI"),
    Recurso.CONFIG_PRODUCTOS: ("Catálogo de productos y precios", "Configuración del sistema"),
    Recurso.CONFIG_USUARIOS: ("Usuarios y asignación de roles", "Configuración del sistema"),
    Recurso.CONFIG_PARAMETROS: ("Parámetros generales", "Configuración del sistema"),
    Recurso.EXPORTACION: ("Exportar datos y reportes", "Exportación"),
    Recurso.RECONOCIMIENTO: ("Reconocimientos / Premios", "Reconocimiento"),
    Recurso.LSII_EVALUAR: ("Evaluación LSII (Receptividad)", "LSII"),
    Recurso.LSII_ADMIN: ("Configuración catálogo LSII", "LSII"),
    Recurso.ETL_CARGAR: ("Carga de datos (ETL)", "Datos"),
    Recurso.FARMACIA_PANEL: ("Panel de farmacias del VM", "Farmacias (maestro/panel)"),
    Recurso.FARMACIA_APROBAR: ("Aprobación de altas de farmacia (VM→GD)", "Farmacias (maestro/panel)"),
    Recurso.FARMACIA_MAESTRO: ("Maestro de farmacias: CRUD directo", "Farmacias (maestro/panel)"),
}

RECURSOS: list[str] = list(RECURSOS_META.keys())
