"""El bypass ronda 2: un `vm_id` explícito saltaba el piso de país en Cobertura.

`_cobertura_base`/`resumen_cobertura` (`visita_cobertura_service.py`) traían `permitidos`
como parámetro desde la ronda 1, y su docstring afirmaba que se aplicaba "siempre, con o
sin `vm_id` explícito" — pero el código lo aplicaba solo en la rama `else` (sin `vm_id`).
Con `vm_id` explícito, `_rm_ids_por` (donde vive el piso) nunca se llamaba: un usuario con
`FACT_UsuarioPais = {DO}` que pidiera `GET /visita/cobertura/resumen?vm_id=<VM de GT>` veía
el panel completo de ese visitador, sin que el guard de endpoint (que solo valida
`pais_codigo`, nunca lo que un `vm_id` implica) lo detectara. Mismo patrón que el bypass de
`ciclo_id` en `ranking.py` (ronda 1), con otro disfraz: un ID explícito en vez de un
parámetro omitido.

Necesita PostgreSQL real: ejercita `_rm_ids_por`/`_cobertura_base` con consultas SQLAlchemy
encadenadas de verdad sobre `Visita.DIM_MedicoVisita`/`Config.DIM_RM`, no con dobles de
prueba — mismo motivo que `test_frontera_pais_bypass_ciclo.py`.
"""
from datetime import date

import pytest
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

BD_PRUEBA = "vista_test_frontera_pais_bypass_vm_id"


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
        # Mismo motivo que el resto de `test_frontera_pais_*`/`test_alcance_scope.py`.
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
    """DO y GT, cada uno con una línea, un VM (RM) y dos médicos en su panel. Un usuario
    ADMIN restringido a `{DO}` en `FACT_UsuarioPais`."""
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
    db.flush()

    linea_do = Linea(pais_codigo="DO", codigo="A", nombre="Línea DO")
    linea_gt = Linea(pais_codigo="GT", codigo="A", nombre="Línea GT")
    db.add_all([linea_do, linea_gt])
    db.flush()

    ciclo_do = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="C01-2026",
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                     dias_laborables=20, cerrado=False, activo=True)
    db.add(ciclo_do)
    db.flush()

    vm_do = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id, codigo="VMDO1",
                                nombre="VM República Dominicana")
    vm_gt = RepresentanteMedico(pais_codigo="GT", linea_id=linea_gt.id, codigo="VMGT1",
                                nombre="VM Guatemala")
    db.add_all([vm_do, vm_gt])
    db.flush()

    # 1 médico en el panel de cada VM — suficiente para que `panel` distinga 0 de 1.
    db.add_all([
        MedicoVisita(vm_id=vm_do.id, nombre_completo="DR PANEL DO"),
        MedicoVisita(vm_id=vm_gt.id, nombre_completo="DR PANEL GT"),
    ])
    db.flush()

    usuario_do = Usuario(username="scope_do_vmid", hashed_password="x",
                         nombre_completo="Gerente de RD", rol=Rol.ADMIN)
    db.add(usuario_do)
    db.flush()
    db.add(UsuarioPais(usuario_id=usuario_do.id, pais_codigo="DO"))
    db.commit()

    return {"usuario_do": usuario_do, "ciclo_do": ciclo_do, "vm_do": vm_do, "vm_gt": vm_gt}


def _cobertura_bypass(db, current_user, vm_id, ciclo_id):
    """Llama el endpoint del router directamente (como lo haría FastAPI, pero SIN
    `pais_codigo`: el bypass es un `vm_id` explícito, sin mandar el país)."""
    return visita_router.cobertura_resumen(
        ciclo_id=ciclo_id, vm_id=vm_id, gerente_id=None, linea_id=None,
        solo_ruptura=False, pais_codigo=None, db=db, current_user=current_user,
    )


def test_vm_id_de_otro_pais_no_filtra_nada(db, escenario):
    """EL TEST QUE REPRODUCE EL HALLAZGO CRITICAL (ronda 2): un usuario con `{DO}` que pide
    la cobertura de un `vm_id` de GT no debe recibir su panel.

    CONTRATO CAMBIADO (cierre de bloqueantes, ago-2026): antes de este cierre el endpoint
    devolvía un panel VACÍO (`panel == 0`, `sin_visita == []`) — el filtro simplemente no
    encontraba nada bajo el piso de país. Desde que `_scope_vm` (`visita.py`) resuelve el
    `vm_id` y valida su país con `exigir_pais` ANTES de llegar al servicio, el mismo intento
    ahora se rechaza con 403 explícito. Se prefiere la denegación explícita al vacío porque
    un resultado vacío es ambiguo — el usuario lo lee como "no hay datos" y el desarrollador
    como un posible bug de consulta — mientras que 403 dice sin ambigüedad "no tienes acceso
    a ese país", y es coherente con `exigir_pais`, que ya responde 403 en el resto de la
    aplicación (por ejemplo, `pais_codigo` explícito fuera del piso del usuario)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _cobertura_bypass(db, escenario["usuario_do"], escenario["vm_gt"].id,
                          escenario["ciclo_do"].id)
    assert exc.value.status_code == 403


def test_vm_id_del_propio_pais_si_funciona(db, escenario):
    """Compatibilidad: el mismo usuario, pidiendo el `vm_id` de SU PROPIO país, sigue
    viendo el panel con normalidad — el piso no bloquea lo legítimo."""
    r = _cobertura_bypass(db, escenario["usuario_do"], escenario["vm_do"].id,
                          escenario["ciclo_do"].id)
    assert r["panel"] == 1
    assert [m["nombre"] for m in r["sin_visita"]] == ["DR PANEL DO"]


def test_usuario_sin_paises_asignados_si_ve_cualquier_vm_id(db, escenario):
    """Compatibilidad: sin filas en `FACT_UsuarioPais` (los usuarios existentes),
    `permitidos` es `None` y el piso no se activa — sigue viendo cualquier VM."""
    admin_sin_paises = Usuario(username="admin_sin_paises_vmid", hashed_password="x",
                               nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(admin_sin_paises)
    db.commit()
    r = _cobertura_bypass(db, admin_sin_paises, escenario["vm_gt"].id, escenario["ciclo_do"].id)
    assert r["panel"] == 1
    assert [m["nombre"] for m in r["sin_visita"]] == ["DR PANEL GT"]
