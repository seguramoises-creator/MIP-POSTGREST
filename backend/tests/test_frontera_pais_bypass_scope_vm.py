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
    for tabla in ('"Visita"."DIM_MedicoVisita"', '"Config"."DIM_RM"', '"Config"."DIM_Ciclo"',
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
    db.add(MedicoVisita(
        vm_id=vm_do.id, nombre_completo="DR SECRETO RD", nombre="Secreto", apellidos="RD",
        direccion="Calle Falsa 123, Santo Domingo", telefono="809-555-0000",
        email="secreto@example.com", exequatur="EXQ-0001",
        latitud=18.4861, longitud=-69.9312,
    ))
    db.flush()

    usuario_gt = Usuario(username="scope_gt_bloqueante1", hashed_password="x",
                         nombre_completo="Gerente de Guatemala", rol=Rol.ADMIN)
    db.add(usuario_gt)
    db.flush()
    db.add(UsuarioPais(usuario_id=usuario_gt.id, pais_codigo="GT"))
    db.commit()

    return {"usuario_gt": usuario_gt, "ciclo_gt": ciclo_gt, "vm_do": vm_do, "vm_do2": vm_do2,
            "vm_gt": vm_gt}


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
    assert [m["nombre_completo"] for m in r] == ["DR SECRETO RD"]

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
