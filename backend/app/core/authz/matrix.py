"""RBAC — matriz canónica (fuente de verdad). Transcripción exacta del spec §5.

MATRIZ[recurso][rol] = celda `(Accion, Alcance)` o `None` (sin acceso).
Columnas en el orden de `_ROLES` (= columnas de la tabla del spec).

Para cambiar un permiso: editar aquí → correr `scripts/seed_authz.py` → el test-oráculo
(`tests/test_authz_matriz.py`) obliga a mantener el spec §5 sincronizado.
"""
from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso

# Celdas (una acción + su alcance)
R_OWN = (Accion.READ, Alcance.OWN)
R_TEAM = (Accion.READ, Alcance.TEAM)
R_ALL = (Accion.READ, Alcance.ALL)
REG_OWN = (Accion.REGISTER, Alcance.OWN)
REG_TEAM = (Accion.REGISTER, Alcance.TEAM)
REG_ALL = (Accion.REGISTER, Alcance.ALL)
CFG = (Accion.CONFIGURE, Alcance.ALL)
APR = (Accion.APPROVE, Alcance.ALL)
EXP_TEAM = (Accion.EXPORT, Alcance.TEAM)
EXP_ALL = (Accion.EXPORT, Alcance.ALL)
ADMIN_CELL = (Accion.ADMIN, Alcance.ALL)

# Orden de roles = columnas del spec §5
_ROLES = [
    Rol.REPRESENTANTE_MEDICO, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA, Rol.GERENTE_MARKETING,
    Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MEDICO, Rol.PRESIDENCIA, Rol.ANALISTA_DATOS,
    Rol.FINANZAS, Rol.ADMIN,
]

_N = None  # sin acceso


def _fila(*celdas):
    assert len(celdas) == len(_ROLES), f"la fila debe tener {len(_ROLES)} celdas, trae {len(celdas)}"
    return {rol: c for rol, c in zip(_ROLES, celdas)}


# MATRIZ[recurso][rol] = (accion, alcance) | None
#                                   RM       GD        MARCA    MKT      PROD     MED      PRES     ANAL     FIN      ADMIN
MATRIZ: dict[str, dict] = {
    Recurso.DASHBOARD_EJECUTIVO:     _fila(_N,      R_TEAM,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),  # el RM NO entra al ejecutivo (tiene sus propias pantallas); GD=agregado empresa + su equipo (scope_gd)
    Recurso.VISITA_REGISTRAR:        _fila(REG_OWN, _N,       _N,      _N,      _N,      _N,      _N,      _N,      _N,      ADMIN_CELL),
    Recurso.MEDICO_PANEL:            _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.CATEGORIZACION_BASICA:   _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.CATEGORIZACION_DETALLE:  _fila(_N,      _N,       CFG,     R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.PLANEACION_CICLO:        _fila(REG_OWN, R_TEAM,   _N,      _N,      _N,      _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.COBERTURA_DIARIA:        _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.COBERTURA_PREDICTIVA:    _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.PARRILLA_CONFIGURAR:     _fila(_N,      _N,       CFG,     _N,      _N,      _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),  # decisión jul-2026: configura el Gerente de Producto (GERENTE_MARCA), no el GD
    Recurso.PARRILLA_CONSULTA:       _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.PRODUCTIVIDAD_COMERCIAL: _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.RANKING_RKT:             _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.COACHING_HOJA:           _fila(R_OWN,   REG_TEAM, _N,      _N,      R_TEAM,  R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.COACHING_KPI:            _fila(_N,      R_TEAM,   _N,      _N,      R_ALL,   R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.EXAMEN_RENDIR:           _fila(REG_OWN, R_TEAM,   _N,      _N,      R_TEAM,  R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),  # GD ve resultados de su equipo (Exámenes — Equipo; decisión jul-2026 = app gobierna)
    Recurso.EXAMEN_CONFIGURAR:       _fila(_N,      R_TEAM,   _N,      _N,      CFG,     CFG,     R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.INTELIGENCIA_MATRIZ:     _fila(R_OWN,   R_TEAM,   CFG,     CFG,     _N,      R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.ENCUESTA_CONFIGURAR:     _fila(_N,      _N,       CFG,     CFG,     _N,      R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.ENCUESTA_APLICAR:        _fila(REG_OWN, _N,       R_ALL,   R_ALL,   _N,      _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.COSTOROI_VER:            _fila(R_OWN,   R_TEAM,   R_ALL,   R_ALL,   _N,      _N,      R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.COSTOROI_CONFIGURAR:     _fila(_N,      _N,       _N,      _N,      _N,      _N,      APR,     _N,      CFG,     ADMIN_CELL),
    Recurso.CONFIG_PRODUCTOS:        _fila(_N,      _N,       R_ALL,   R_ALL,   _N,      R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.CONFIG_USUARIOS:         _fila(_N,      _N,       _N,      _N,      _N,      _N,      _N,      _N,      _N,      ADMIN_CELL),
    Recurso.CONFIG_PARAMETROS:       _fila(_N,      _N,       _N,      _N,      _N,      _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.EXPORTACION:             _fila(_N,      EXP_TEAM, EXP_ALL, EXP_ALL, EXP_ALL, EXP_ALL, EXP_ALL, EXP_ALL, EXP_ALL, ADMIN_CELL),
    # Recursos de módulos fuera de las 28 del prompt (deuda #3, jul-2026), alineados con sus guards actuales.
    #                                   RM       GD        MARCA    MKT      PROD     MED      PRES     ANAL     FIN      ADMIN
    Recurso.RECONOCIMIENTO:          _fila(_N,      _N,       _N,      _N,      CFG,     _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.LSII_EVALUAR:            _fila(_N,      REG_TEAM, REG_ALL, _N,      REG_ALL, _N,      R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.LSII_ADMIN:              _fila(_N,      _N,       _N,      _N,      CFG,     _N,      _N,      _N,      _N,      ADMIN_CELL),
    Recurso.ETL_CARGAR:              _fila(_N,      _N,       _N,      _N,      CFG,     _N,      _N,      _N,      _N,      ADMIN_CELL),
    # Módulo de Farmacias (jul-2026, Task 5 del plan `2026-07-22-modulo-farmacias.md`).
    #   - farmacia.panel: espejo de medico.panel — VM lee/solicita su propio panel (register
    #     implica read own); GD lee el de su equipo; GERENTE_PRODUCTIVIDAD (a diferencia de
    #     medico.panel, aquí SÍ) + resto de gerencias leen todo; FINANZAS sin acceso.
    #   - farmacia.aprobar: SOLO Gerente de Distrito (su equipo) + ADMIN aprueban/rechazan altas.
    #   - farmacia.maestro: SOLO GERENTE_PRODUCTIVIDAD + ADMIN administran el maestro directo
    #     (mismo patrón exacto que LSII_ADMIN/ETL_CARGAR: una única gerencia configura).
    #                                   RM       GD        MARCA    MKT      PROD     MED      PRES     ANAL     FIN      ADMIN
    Recurso.FARMACIA_PANEL:          _fila(REG_OWN, R_TEAM, R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   R_ALL,   _N,      ADMIN_CELL),
    Recurso.FARMACIA_APROBAR:        _fila(_N,      (Accion.APPROVE, Alcance.TEAM), _N, _N, _N, _N, _N, _N, _N,   ADMIN_CELL),
    Recurso.FARMACIA_MAESTRO:        _fila(_N,      _N,       _N,      _N,      CFG,     _N,      _N,      _N,      _N,      ADMIN_CELL),
    # Categorización + Maestro de Médicos (jul-2026): filas calcadas del acceso que `categorizacion.py`
    # y `maestro_medicos.py` ya concedían con `require_roles`, para que cablearlos a la matriz no le
    # quite (ni le dé) acceso a nadie. Verificado endpoint por endpoint en `test_authz_wiring_calcado.py`.
    #   - categorizacion.operacion: LEER lo podía cualquier autenticado; CONFIGURAR (params, geo,
    #     carga Excel) solo ADMIN+GERENTE_PRODUCTIVIDAD. RM=own y GD=team calcan el filtro de datos
    #     interno `_codigos_scope`; ANALISTA_DATOS va R_ALL porque de él se derivan DIR_COMERCIAL y
    #     CONSULTA, que hoy sí ven todo (`_ROLES_VE_TODO`).
    #   - medico.maestro / .editar: van separados porque el maestro CREA más restringido de lo que
    #     EDITA (alta = ADMIN+GERPROD; edición = +GD+GERENTE_MARCA) y una celda no puede expresar
    #     dos acciones distintas para el mismo rol.
    #                                   RM       GD        MARCA    MKT      PROD     MED      PRES     ANAL     FIN      ADMIN
    Recurso.CATEGORIZACION_OPERACION: _fila(R_OWN, R_TEAM,  R_ALL,   R_ALL,   CFG,     R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.MEDICO_MAESTRO:          _fila(R_ALL,   R_ALL,   R_ALL,   R_ALL,   CFG,     R_ALL,   R_ALL,   R_ALL,   R_ALL,   ADMIN_CELL),
    Recurso.MEDICO_MAESTRO_EDITAR:   _fila(_N,      CFG,      CFG,     _N,      CFG,     _N,      _N,      _N,      _N,      ADMIN_CELL),
}

# ── Roles legacy fuera de la matriz canónica de 10 columnas (Fase 2) ──────────────────────────
# Decisión jul-2026 (spec §2 + ajuste de deuda):
#   - CAPACITACION  := FILA PROPIA mínima (coordinador de exámenes): configura/publica/consolida
#                      exámenes y ve sus resultados; NADA gerencial. NO hereda de
#                      GERENTE_PRODUCTIVIDAD (evita que gane LSII/ETL/reconocimiento/ranking, etc.).
#   - DIR_COMERCIAL := misma fila que ANALISTA_DATOS (lectura total + export, sin escritura).
#   - CONSULTA      := igual que ANALISTA_DATOS pero SIN capacidad de export (solo lectura total).
_CAPACITACION_ROW = {
    Recurso.EXAMEN_CONFIGURAR: CFG,   # su función central (Exámenes)
    Recurso.EXAMEN_RENDIR: R_ALL,     # ve los resultados rendidos para consolidar
    # NADA más. Se probó (25-jul-2026) darle la lectura de `categorizacion.operacion` y
    # `medico.maestro` para no quitarle lo que ya tenía —cuando esos routers usaban
    # `require_roles`, leerlos solo exigía estar autenticado—, pero el cliente lo rechazó al
    # verlo en pantalla: con la navegación alineada a esos recursos, a CAPACITACION le aparecía
    # el módulo "Médicos" (Categorización + Maestro), que no le corresponde. Vuelve a exámenes y
    # nada más, como decía el diseño original. Ver migración 0029.
}
for _recurso, _fila_dict in MATRIZ.items():
    _fila_dict[Rol.CAPACITACION] = _CAPACITACION_ROW.get(_recurso)  # None por defecto (denegado)
    _fila_dict[Rol.DIR_COMERCIAL] = _fila_dict[Rol.ANALISTA_DATOS]
    _fila_dict[Rol.CONSULTA] = (None if _recurso == Recurso.EXPORTACION
                                else _fila_dict[Rol.ANALISTA_DATOS])

