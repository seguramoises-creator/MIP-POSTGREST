"""Bloqueante 1 de revisión (ago-2026): `_scope_vm` dejaba `vm_id` sin control de país,
también en LECTURA.

`_scope_vm` (visita.py) devolvía el `vm_id` recibido tal cual para cualquier rol que no
fuera REPRESENTANTE_MEDICO, sin validar que el país de ESE vm_id estuviera entre los
países permitidos del usuario que hace la llamada. El caso más grave era
`GET /visita/medicos/existentes?vm_id=`: con un solo `vm_id` de otro país, un usuario
restringido devolvía la ficha médica COMPLETA (nombre, dirección, GPS, teléfono, email,
exequátur) de todos los médicos de ese país — dato personal, no agregado.

El fix resuelve el país DEL `vm_id` recibido y llama `exigir_pais` (mismo criterio que
`_verificar_acceso_rm`/`get_productividad_rm`: el guard va en el resolvedor cuando el
identificador señala una sola entidad). Cierra lectura y escritura de una vez, porque
todos los endpoints de escritura pasan por el mismo `_scope_vm`/`_vm_registro`.

Necesita PostgreSQL real (mismo motivo que `test_frontera_pais_bypass_vm_id.py`):
ejercita `RepresentanteMedico`/`MedicoVisita` con consultas SQLAlchemy encadenadas de
verdad, no con dobles de prueba.
"""
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.routers import visita as visita_router
from app.core.config import settings
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models import visita as visita_models  # noqa: F401 — registra Visita.DIM_MedicoVisita
from app.models.alcance import UsuarioPais
from app.models.dimensiones import Ciclo, Linea, Pais, RepresentanteMedico
from app.models.visita import MedicoVisita
from app.models.usuario import Rol, Usuario
from app.schemas.visita import PlaneacionGuardar

BD_PRUEBA = "vista_test_frontera_pais_bypass_scope_vm"


def _url(nombre: str) -> str:
    return (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_SERVER}:{settings.DB_PORT}/{nombre}")


@pytest.fixture(scope="module")
def motor():
    try:
        admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as cx:
            cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
            cx.execute(text(f"CREATE DATABASE {BD_PRUEBA}"))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable para pruebas de integración: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"Visita"."MedicoSolicitudCambio"', '"Visita"."FactVisita"',
                  '"Visita"."CierreCicloVisita"', '"Visita"."DIM_MedicoVisita"',
                  '"Config"."DIM_RM"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Security"."FACT_UsuarioPais"',
                  '"Security"."DIM_Usuario"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """DO y GT, cada uno con una línea, un VM (RM) y un médico en su panel. Un usuario
    ADMIN restringido a `{GT}` en `FACT_UsuarioPais` — GT es su país "propio"; RD es el
    país ajeno cuyo vm_id no debería poder usar."""
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
    db.flush()

    linea_do = Linea(pais_codigo="DO", codigo="A", nombre="Línea DO")
    linea_gt = Linea(pais_codigo="GT", codigo="A", nombre="Línea GT")
    db.add_all([linea_do, linea_gt])
    db.flush()

    ciclo_gt = Ciclo(pais_codigo="GT", anio=2026, numero=1, nombre="C01-2026",
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                     dias_laborables=20, cerrado=False, activo=True)
    # Ciclo abierto de RD también: lo necesita el test de compatibilidad (usuario sin
    # países asignados), que SÍ debe poder escribir sobre el vm_id de RD con normalidad.
    ciclo_do = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="C01-2026",
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                     dias_laborables=20, cerrado=False, activo=True)
    db.add_all([ciclo_gt, ciclo_do])
    db.flush()

    vm_do = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id, codigo="VMDO1",
                                nombre="VM República Dominicana")
    # Un segundo VM en RD, sin médicos propios: es el destino de la copia — permite ver el
    # médico del PRIMER VM de RD sin que `listar_medicos_existentes` lo excluya por ya
    # estar en el panel del vm_id consultado.
    vm_do2 = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id, codigo="VMDO2",
                                 nombre="VM República Dominicana 2")
    vm_gt = RepresentanteMedico(pais_codigo="GT", linea_id=linea_gt.id, codigo="VMGT1",
                                nombre="VM Guatemala")
    db.add_all([vm_do, vm_do2, vm_gt])
    db.flush()

    # Ficha médica COMPLETA en el panel del VM de RD — es el dato personal que no debe fugarse.
    medico_secreto = MedicoVisita(
        vm_id=vm_do.id, nombre_completo="DR SECRETO RD", nombre="Secreto", apellidos="RD",
        direccion="Calle Falsa 123, Santo Domingo", telefono="809-555-0000",
        email="secreto@example.com", exequatur="EXQ-0001",
        latitud=18.4861, longitud=-69.9312,
        # APROBADO (default del modelo): habilita el flujo de "cambio propuesto" (ronda 3).
    )
    # Segundo médico de RD, PENDIENTE_ALTA: para `listar_aprobaciones`/`listar_pendientes`
    # (ronda 3) — debe desaparecer de la bandeja de un usuario acotado a GT.
    medico_pendiente = MedicoVisita(
        vm_id=vm_do.id, nombre_completo="DR PENDIENTE RD", nombre="Pendiente", apellidos="RD",
        estado_aprobacion="PENDIENTE_ALTA",
    )
    db.add_all([medico_secreto, medico_pendiente])
    db.flush()

    # Cambio propuesto pendiente sobre el médico YA aprobado de RD — para
    # `resolver_cambio_medico` (ronda 3).
    from app.models.visita import MedicoSolicitudCambio
    solicitud_cambio = MedicoSolicitudCambio(
        medico_visita_id=medico_secreto.id, cambios_json='{"telefono": "809-000-0000"}',
        estado="PENDIENTE")
    db.add(solicitud_cambio)
    db.flush()

    usuario_gt = Usuario(username="scope_gt_bloqueante1", hashed_password="x",
                         nombre_completo="Gerente de Guatemala", rol=Rol.ADMIN)
    db.add(usuario_gt)
    db.flush()
    db.add(UsuarioPais(usuario_id=usuario_gt.id, pais_codigo="GT"))
    db.commit()

    return {"usuario_gt": usuario_gt, "ciclo_gt": ciclo_gt, "ciclo_do": ciclo_do,
            "vm_do": vm_do, "vm_do2": vm_do2, "vm_gt": vm_gt,
            "linea_do": linea_do, "linea_gt": linea_gt,
            "medico_secreto": medico_secreto, "medico_pendiente": medico_pendiente,
            "solicitud_cambio": solicitud_cambio}


# ── Test 1: LECTURA — el vector más grave (ficha médica completa) ─────────────
def test_medicos_existentes_con_vm_id_de_otro_pais_da_403_y_no_filtra_ninguna_ficha(db, escenario):
    """EL TEST QUE REPRODUCE EL HALLAZGO BLOQUEANTE 1: un usuario con `{GT}` que pide
    `GET /visita/medicos/existentes?vm_id=<VM de RD>` no debe recibir NINGUNA ficha médica
    de RD — ni siquiera parcial. Debe cortar en 403 antes de tocar el servicio."""
    with pytest.raises(HTTPException) as exc:
        visita_router.listar_medicos_existentes(
            vm_id=escenario["vm_do"].id, db=db, current_user=escenario["usuario_gt"])
    assert exc.value.status_code == 403


def test_medicos_existentes_con_vm_id_del_propio_pais_si_funciona(db, escenario):
    """Compatibilidad: el mismo usuario, pidiendo el `vm_id` de SU PROPIO país (GT),
    sigue funcionando con normalidad — el piso no bloquea lo legítimo."""
    r = visita_router.listar_medicos_existentes(
        vm_id=escenario["vm_gt"].id, db=db, current_user=escenario["usuario_gt"])
    assert r == []  # GT no tiene médicos registrados todavía — lista vacía, no 403


# ── Test 2: ESCRITURA — mismo guard, otro endpoint (`_vm_registro`/`guardar_planeacion`) ──
def test_guardar_planeacion_con_vm_id_de_otro_pais_da_403(db, escenario):
    """Un usuario con `{GT}` pasando el `vm_id` de un VM de RD a un endpoint de ESCRITURA
    (Planeación del Ciclo) también debe cortar en 403 — mismo `_scope_vm` por debajo de
    `_vm_registro`."""
    with pytest.raises(HTTPException) as exc:
        visita_router.guardar_planeacion(
            datos=PlaneacionGuardar(items=[]), vm_id=escenario["vm_do"].id, ciclo_id=None,
            db=db, current_user=escenario["usuario_gt"])
    assert exc.value.status_code == 403


# ── Test 3: COMPATIBILIDAD — el pilar de la regla ("SIN FILAS = TODOS") ────────
def test_usuario_sin_paises_asignados_sigue_pudiendo_usar_cualquier_vm_id(db, escenario):
    """Compatibilidad crítica (spec §3): sin filas en `FACT_UsuarioPais` (los 37 usuarios
    existentes el día que se activa la frontera), `paises_visibles` es `None` y el piso NO
    se activa — sigue pudiendo usar el `vm_id` de cualquier país, en lectura y escritura.
    Si esto se rompe, el sistema queda inservible el día del despliegue."""
    admin_sin_paises = Usuario(username="admin_sin_paises_bloqueante1", hashed_password="x",
                               nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(admin_sin_paises)
    db.commit()

    # Lectura: vm_id de RD (el segundo VM, sin panel propio), usuario sin países asignados
    # → sin 403, ve la ficha del médico del primer VM de RD con normalidad.
    r = visita_router.listar_medicos_existentes(
        vm_id=escenario["vm_do2"].id, db=db, current_user=admin_sin_paises)
    assert "DR SECRETO RD" in [m["nombre_completo"] for m in r]

    # Escritura: mismo vm_id de RD, sin 403 (no llega a persistir nada porque items=[]).
    n = visita_router.guardar_planeacion(
        datos=PlaneacionGuardar(items=[]), vm_id=escenario["vm_do"].id, ciclo_id=None,
        db=db, current_user=admin_sin_paises)
    assert n == {"guardadas": 0}


# ── [MENOR] listar_vms sin `pais_codigo`: seguía listando VMs de TODOS los países ──
def test_listar_vms_sin_pais_codigo_aplica_el_piso_de_pais(db, escenario):
    """Un usuario con `{GT}` que llama `GET /visita/vms` SIN `pais_codigo` debe ver
    solo los VM de GT, no también los de RD."""
    nombres = {v["nombre"] for v in visita_router.listar_vms(
        pais_codigo=None, db=db, current_user=escenario["usuario_gt"])}
    assert nombres == {"VM Guatemala"}
    assert "VM República Dominicana" not in nombres


# ═════════════════════════════════════════════════════════════════════════════
# RONDA 3 — re-revisión: la enumeración exhaustiva encontró 3 rutas nombradas
# (`mi-gerente`, `costo/roi`, `planeacion/desbloquear`) más otras que aparecieron
# al barrer TODO `vm_id`/`rm_id`/`gerente_id`/`ciclo_id`/`medico_id`/`linea_id` que
# entra del cliente en visita.py. Un test por ruta cerrada — todos con el mismo
# patrón: usuario ADMIN acotado a `{GT}`, identificador de una entidad de RD →
# 403. La tabla completa de la enumeración va en el informe de cierre.
# ═════════════════════════════════════════════════════════════════════════════
import asyncio

from app.core.authz.deps import Autorizacion
from app.core.authz.constantes import Alcance
from app.schemas.visita import (
    ClasificacionCrear, MedicoVisitaCrear, MedicoVisitaActualizar, ParrillaGuardar,
    MuestrasRegistrar, ParametroCostoGuardar, CostoEstructuraGuardar,
)


def _clasificacion():
    return ClasificacionCrear(pacientes_semana=10, costo_consulta=100,
                              potencial_prescripcion="1", ubicacion_territorial="A", kol_nivel="Ninguno")


def _403(fn, *a, **kw):
    with pytest.raises(HTTPException) as exc:
        fn(*a, **kw)
    assert exc.value.status_code == 403
    return exc.value


# ── mi-gerente (señalado explícitamente) ───────────────────────────────────────
def test_mi_gerente_con_vm_id_de_otro_pais_da_403(db, escenario):
    _403(visita_router.mi_gerente, vm_id=escenario["vm_do"].id, db=db,
        current_user=escenario["usuario_gt"])


# ── Panel médico: lectura/escritura por medico_id, sin pasar por _scope_vm ─────
def test_obtener_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.obtener_medico, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_actualizar_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.actualizar_medico, medico_id=escenario["medico_secreto"].id,
        datos=MedicoVisitaActualizar(subespecialidad="Cardiología pediátrica"), db=db,
        current_user=escenario["usuario_gt"])


def test_solicitar_baja_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.solicitar_baja, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_reactivar_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.reactivar_medico, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_obtener_clasificacion_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.obtener_clasificacion, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_crear_medico_en_panel_de_otro_pais_da_403(db, escenario):
    """ADMIN (no REPRESENTANTE_MEDICO) mandando `datos.vm_id` de un VM de RD."""
    datos = MedicoVisitaCrear(vm_id=escenario["vm_do"].id, nombre_completo="NUEVO MEDICO",
                              clasificacion=_clasificacion())
    _403(visita_router.crear_medico, datos=datos, db=db, current_user=escenario["usuario_gt"])


# ── Aprobación (fix en `puede_aprobar`, cierra 4 rutas + filtra el listado) ────
def test_aprobar_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.aprobar_medico, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_rechazar_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.rechazar_medico, medico_id=escenario["medico_secreto"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_actualizar_clasificacion_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.actualizar_clasificacion, medico_id=escenario["medico_secreto"].id,
        datos=_clasificacion(), db=db, current_user=escenario["usuario_gt"])


def test_resolver_cambio_medico_de_otro_pais_da_403(db, escenario):
    _403(visita_router.resolver_cambio_medico, solicitud_id=escenario["solicitud_cambio"].id,
        aprobar=True, motivo=None, db=db, current_user=escenario["usuario_gt"])


def test_listar_aprobaciones_excluye_pendientes_de_otro_pais(db, escenario):
    """`listar_pendientes` ahora también FILTRA por país (antes solo bloqueaba el acceso
    directo): el médico PENDIENTE_ALTA de RD no debe aparecer en la bandeja de un usuario
    acotado a GT, aunque no haya pedido ningún filtro."""
    r = visita_router.listar_aprobaciones(db=db, current_user=escenario["usuario_gt"])
    nombres = {x["nombre_completo"] for x in r}
    assert "DR PENDIENTE RD" not in nombres


# ── Desbloqueo de planeación (señalado explícitamente: ADMIN no exime del país) ─
def test_desbloquear_planeacion_de_otro_pais_da_403(db, escenario):
    _403(visita_router.desbloquear_planeacion, vm_id=escenario["vm_do"].id,
        motivo="prueba", ciclo_id=None, db=db, current_user=escenario["usuario_gt"])


# ── Cierre de ciclo ─────────────────────────────────────────────────────────────
def test_previsualizar_cierre_de_otro_pais_da_403(db, escenario):
    _403(visita_router.previsualizar_cierre, ciclo_id=escenario["ciclo_do"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_cerrar_ciclo_de_otro_pais_da_403(db, escenario):
    _403(visita_router.cerrar_ciclo, ciclo_id=escenario["ciclo_do"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_historial_cierres_excluye_cierres_de_otro_pais(db, escenario):
    """`historial_cierres` no toma ningún identificador del cliente, pero mezclaba
    cierres de TODOS los países — hallazgo adicional de la ronda 3 (ver informe)."""
    from app.models.visita import CierreCicloVisita
    db.add_all([
        CierreCicloVisita(ciclo_id=escenario["ciclo_do"].id, panel=1),
        CierreCicloVisita(ciclo_id=escenario["ciclo_gt"].id, panel=2),
    ])
    db.commit()
    r = visita_router.historial_cierres(db=db, current_user=escenario["usuario_gt"])
    ciclos = {x["ciclo_id"] for x in r}
    assert escenario["ciclo_do"].id not in ciclos
    assert escenario["ciclo_gt"].id in ciclos


# ── Parrilla promocional ─────────────────────────────────────────────────────────
def test_parrilla_ultima_linea_de_otro_pais_da_403(db, escenario):
    _403(visita_router.parrilla_ultima_linea, ciclo_id=escenario["ciclo_do"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_obtener_parrilla_con_linea_id_de_otro_pais_da_403(db, escenario):
    """`linea_id` explícito saltaba entero el piso de `_scope_vm` (solo corría en la
    rama sin `linea_id`)."""
    _403(visita_router.obtener_parrilla, linea_id=escenario["linea_do"].id, ciclo_id=None,
        vm_id=None, db=db, current_user=escenario["usuario_gt"])


def test_parrilla_penetracion_con_linea_id_de_otro_pais_da_403(db, escenario):
    _403(visita_router.parrilla_penetracion, linea_id=escenario["linea_do"].id,
        ciclo_id=None, db=db, current_user=escenario["usuario_gt"])


def test_publicar_parrilla_de_otro_pais_da_403(db, escenario):
    _403(visita_router.publicar_parrilla, linea_id=escenario["linea_do"].id, ciclo_id=None,
        db=db, current_user=escenario["usuario_gt"])


def test_guardar_parrilla_de_otro_pais_da_403(db, escenario):
    datos = ParrillaGuardar(linea_id=escenario["linea_do"].id, items=[])
    _403(visita_router.guardar_parrilla, datos=datos, db=db, current_user=escenario["usuario_gt"])


def test_registrar_muestras_a_medico_de_otro_pais_da_403(db, escenario):
    """`vm_id` va del propio país del usuario (GT, pasa `_vm_registro`), pero
    `datos.medico_id` es de un médico de RD — `_exigir_pais_medico` lo detecta."""
    datos = MuestrasRegistrar(medico_id=escenario["medico_secreto"].id,
                              entregas=[{"producto": "Producto X", "cantidad": 1}])
    _403(visita_router.registrar_muestras, datos=datos, vm_id=escenario["vm_gt"].id,
        db=db, current_user=escenario["usuario_gt"])


# ── Costo & ROI — dato financiero, la sección completa ─────────────────────────
def test_obtener_parametros_costo_de_otro_pais_da_403(db, escenario):
    _403(visita_router.obtener_parametros_costo, linea_id=escenario["linea_do"].id,
        ciclo_id=None, db=db, current_user=escenario["usuario_gt"])


def test_guardar_parametros_costo_de_otro_pais_da_403(db, escenario):
    datos = ParametroCostoGuardar(linea_id=escenario["linea_do"].id, costo_visita=1, costo_muestra=1)
    _403(visita_router.guardar_parametros_costo, datos=datos, db=db,
        current_user=escenario["usuario_gt"])


def test_costo_roi_con_vm_id_de_otro_pais_da_403(db, escenario):
    """EL TEST SEÑALADO EXPLÍCITAMENTE — dato financiero (costo por contacto, ingresos,
    utilidad, ROI). Verificado también por mutación (ver informe)."""
    _403(visita_router.costo_roi, vm_id=escenario["vm_do"].id, ciclo_id=None,
        db=db, current_user=escenario["usuario_gt"])


def test_costo_ranking_de_otro_pais_da_403(db, escenario):
    _403(visita_router.costo_ranking, ciclo_id=escenario["ciclo_do"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_costo_estructura_de_otro_pais_da_403(db, escenario):
    _403(visita_router.costo_estructura, linea_id=escenario["linea_do"].id, ciclo_id=None,
        db=db, current_user=escenario["usuario_gt"])


def test_costo_hojas_de_otro_pais_da_403(db, escenario):
    _403(visita_router.costo_hojas, ciclo_id=escenario["ciclo_do"].id,
        db=db, current_user=escenario["usuario_gt"])


def test_costo_mi_linea_alcance_all_con_linea_de_otro_pais_da_403(db, escenario):
    """Alcance RBAC (ALL) y país (frontera) son ejes ortogonales: un observador ALL
    sigue acotado a `{GT}`."""
    auth = Autorizacion(usuario=escenario["usuario_gt"], alcance=Alcance.ALL)
    _403(visita_router.costo_mi_linea, ciclo_id=None, linea_id=escenario["linea_do"].id,
        db=db, _auth=auth)


def test_guardar_costo_estructura_de_otro_pais_da_403(db, escenario):
    datos = CostoEstructuraGuardar(linea_id=escenario["linea_do"].id)
    _403(visita_router.guardar_costo_estructura, datos=datos, background_tasks=_FakeBT(),
        db=db, current_user=escenario["usuario_gt"])


def test_aprobar_costo_estructura_de_otro_pais_da_403(db, escenario):
    _403(visita_router.aprobar_costo_estructura, linea_id=escenario["linea_do"].id, ciclo_id=None,
        db=db, current_user=escenario["usuario_gt"])


def test_reabrir_costo_estructura_de_otro_pais_da_403(db, escenario):
    """Mismo patrón que `/planeacion/desbloquear`: `RequireDesbloqueo` (solo ADMIN) no
    exime del país."""
    _403(visita_router.reabrir_costo_estructura, linea_id=escenario["linea_do"].id, ciclo_id=None,
        db=db, current_user=escenario["usuario_gt"])


def test_importar_costo_excel_de_otro_pais_da_403(db, escenario):
    class _FakeUpload:
        filename = "datos.xlsx"
        async def read(self):
            return b""
    exc = None
    try:
        asyncio.run(visita_router.importar_costo_excel(
            linea_id=escenario["linea_do"].id, ciclo_id=None, archivo=_FakeUpload(),
            db=db, current_user=escenario["usuario_gt"]))
    except HTTPException as e:
        exc = e
    assert exc is not None and exc.status_code == 403


class _FakeBT:
    def add_task(self, *a, **kw):
        pass


# ── Foto de visita (hallazgo adicional: mismo bug, otro identificador) ─────────
def test_obtener_foto_visita_de_otro_pais_da_403(db, escenario):
    from app.models.visita import VisitaRegistro
    from datetime import datetime, timezone
    v = VisitaRegistro(vm_id=escenario["vm_do"].id, medico_id=escenario["medico_secreto"].id,
                       ciclo_id=escenario["ciclo_do"].id, fecha_hora=datetime.now(timezone.utc),
                       ejecutada=True, tipo_visita="V")
    db.add(v)
    db.commit()
    _403(visita_router.obtener_foto_visita_endpoint, visita_id=v.id, db=db,
        current_user=escenario["usuario_gt"])
