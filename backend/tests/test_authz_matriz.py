"""RBAC Fase 1 — T2: la matriz codificada (matrix.MATRIZ) == la tabla del spec §5.

ORACULO es una transcripción INDEPENDIENTE de la tabla del spec (escrita a mano aparte de
matrix.py) para atrapar errores de transcripción. Si alguien cambia la matriz y no el spec (o
viceversa), este test falla.
"""
from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso, RECURSOS
from app.core.authz.matrix import MATRIZ

COLS = [Rol.REPRESENTANTE_MEDICO, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA, Rol.GERENTE_MARKETING,
        Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MEDICO, Rol.PRESIDENCIA, Rol.ANALISTA_DATOS,
        Rol.FINANZAS, Rol.ADMIN]

RO = (Accion.READ, Alcance.OWN)
RT = (Accion.READ, Alcance.TEAM)
RA = (Accion.READ, Alcance.ALL)
GO = (Accion.REGISTER, Alcance.OWN)
GT = (Accion.REGISTER, Alcance.TEAM)
GA = (Accion.REGISTER, Alcance.ALL)
CF = (Accion.CONFIGURE, Alcance.ALL)
AP = (Accion.APPROVE, Alcance.ALL)
AT = (Accion.APPROVE, Alcance.TEAM)
ET = (Accion.EXPORT, Alcance.TEAM)
EA = (Accion.EXPORT, Alcance.ALL)
AD = (Accion.ADMIN, Alcance.ALL)
_ = None

# Transcripción independiente del spec §5 (una lista de 10 por recurso, en orden COLS)
ORACULO = {
    Recurso.DASHBOARD_EJECUTIVO:     [_,  RT, RA, RA, RA, RA, RA, RA, RA, AD],
    Recurso.VISITA_REGISTRAR:        [GO, _,  _,  _,  _,  _,  _,  _,  _,  AD],
    Recurso.MEDICO_PANEL:            [RO, RT, RA, RA, _,  RA, RA, RA, _,  AD],
    Recurso.CATEGORIZACION_BASICA:   [RO, RT, RA, RA, _,  RA, RA, RA, _,  AD],
    Recurso.CATEGORIZACION_DETALLE:  [_,  _,  CF, RA, _,  RA, RA, RA, _,  AD],
    Recurso.PLANEACION_CICLO:        [GO, RT, _,  _,  _,  _,  RA, RA, _,  AD],
    Recurso.COBERTURA_DIARIA:        [RO, RT, RA, RA, RA, RA, RA, RA, RA, AD],
    Recurso.COBERTURA_PREDICTIVA:    [RO, RT, RA, RA, RA, RA, RA, RA, _,  AD],
    Recurso.PARRILLA_CONFIGURAR:     [_,  _,  CF, _,  _,  _,  RA, RA, _,  AD],
    Recurso.PARRILLA_CONSULTA:       [RO, RT, RA, RA, RA, RA, RA, RA, RA, AD],
    Recurso.PRODUCTIVIDAD_COMERCIAL: [RO, RT, RA, RA, RA, _,  RA, RA, RA, AD],
    Recurso.RANKING_RKT:             [RO, RT, RA, RA, RA, _,  RA, RA, RA, AD],
    Recurso.COACHING_HOJA:           [RO, GT, _,  _,  RT, RA, RA, RA, _,  AD],
    Recurso.COACHING_KPI:            [_,  RT, _,  _,  RA, RA, RA, RA, _,  AD],
    Recurso.EXAMEN_RENDIR:           [GO, RT, _,  _,  RT, RA, RA, RA, _,  AD],
    Recurso.EXAMEN_CONFIGURAR:       [_,  RT, _,  _,  CF, CF, RA, RA, _,  AD],
    Recurso.INTELIGENCIA_MATRIZ:     [RO, RT, CF, CF, _,  RA, RA, RA, _,  AD],
    Recurso.ENCUESTA_CONFIGURAR:     [_,  _,  CF, CF, _,  RA, RA, RA, _,  AD],
    Recurso.ENCUESTA_APLICAR:        [GO, _,  RA, RA, _,  _,  RA, RA, _,  AD],
    Recurso.COSTOROI_VER:            [RO, RT, RA, RA, _,  _,  RA, RA, RA, AD],
    Recurso.COSTOROI_CONFIGURAR:     [_,  _,  _,  _,  _,  _,  AP, _,  CF, AD],
    Recurso.CONFIG_PRODUCTOS:        [_,  _,  RA, RA, _,  RA, RA, RA, RA, AD],
    Recurso.CONFIG_USUARIOS:         [_,  _,  _,  _,  _,  _,  _,  _,  _,  AD],
    Recurso.CONFIG_PARAMETROS:       [_,  _,  _,  _,  _,  _,  RA, RA, _,  AD],
    Recurso.EXPORTACION:             [_,  ET, EA, EA, EA, EA, EA, EA, EA, AD],
    # Recursos de módulos fuera de las 28 del prompt (deuda #3)
    Recurso.RECONOCIMIENTO:          [_,  _,  _,  _,  CF, _,  RA, RA, _,  AD],
    Recurso.LSII_EVALUAR:            [_,  GT, GA, _,  GA, _,  RA, RA, _,  AD],
    Recurso.LSII_ADMIN:              [_,  _,  _,  _,  CF, _,  _,  _,  _,  AD],
    Recurso.ETL_CARGAR:              [_,  _,  _,  _,  CF, _,  _,  _,  _,  AD],
    # Módulo de Farmacias (Task 5, jul-2026)
    Recurso.FARMACIA_PANEL:          [GO, RT, RA, RA, RA, RA, RA, RA, _,  AD],
    Recurso.FARMACIA_APROBAR:        [_,  AT, _,  _,  _,  _,  _,  _,  _,  AD],
    Recurso.FARMACIA_MAESTRO:        [_,  _,  _,  _,  CF, _,  _,  _,  _,  AD],
}


def test_matriz_tiene_32_recursos():
    assert len(RECURSOS) == 32
    assert set(MATRIZ) == set(RECURSOS)
    assert set(ORACULO) == set(RECURSOS)


def test_cada_fila_incluye_los_10_roles_canonicos():
    for recurso, fila in MATRIZ.items():
        assert set(COLS) <= set(fila), f"{recurso}: faltan roles canónicos"


def test_matriz_coincide_con_oraculo_del_spec():
    for recurso, fila in ORACULO.items():
        for rol, esperado in zip(COLS, fila):
            actual = MATRIZ[recurso][rol]
            assert actual == esperado, f"{recurso} / {rol.value}: matriz={actual} != spec={esperado}"


def test_roles_legacy_derivados_por_regla():
    """Fase 2: DIR_COMERCIAL/CONSULTA derivados; CAPACITACION = fila propia (solo exámenes)."""
    for recurso, fila in MATRIZ.items():
        # CAPACITACION = fila propia estricta: solo examen.configurar (CFG) + examen.rendir (read all).
        if recurso == Recurso.EXAMEN_CONFIGURAR:
            assert fila[Rol.CAPACITACION] == (Accion.CONFIGURE, Alcance.ALL)
        elif recurso == Recurso.EXAMEN_RENDIR:
            assert fila[Rol.CAPACITACION] == (Accion.READ, Alcance.ALL)
        else:
            assert fila[Rol.CAPACITACION] is None
        # DIR_COMERCIAL == ANALISTA_DATOS
        assert fila[Rol.DIR_COMERCIAL] == fila[Rol.ANALISTA_DATOS]
        # CONSULTA == ANALISTA_DATOS salvo en EXPORTACION (sin export)
        if recurso == Recurso.EXPORTACION:
            assert fila[Rol.CONSULTA] is None
        else:
            assert fila[Rol.CONSULTA] == fila[Rol.ANALISTA_DATOS]


def test_matriz_cubre_los_13_roles_del_enum():
    for recurso, fila in MATRIZ.items():
        assert set(fila) == set(Rol), f"{recurso}: la fila no cubre los 13 roles del enum"
