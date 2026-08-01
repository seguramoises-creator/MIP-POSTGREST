"""Onboarding + Biblioteca — casos de aceptación 1 y 2 del §16.

Estas pruebas necesitan una base PostgreSQL real: el gating se apoya en
consultas con relaciones y esquemas, y probarlo con dobles verificaría los
dobles, no el bloqueo. Si no hay base alcanzable **se saltan**, para no romper
un entorno de integración que no la tiene.

Se ejecutan sobre una base desechable propia, nunca sobre la del proyecto.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
# Se importan TODOS los módulos de modelos, no solo los que usa la prueba:
# `create_all` resuelve las claves foráneas contra la metadata completa, y sin
# esto falla al no encontrar tablas de otros esquemas que sí son referenciadas.
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Linea, Pais, RepresentanteMedico
from app.models.formacion import BibliotecaMaterial, ProductoLinea
from app.services import formacion_biblioteca_service as biblioteca
from app.services import formacion_onboarding_service as onboarding

BD_PRUEBA = "vista_test_formacion"


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
    # Cada prueba parte de cero en las tablas que toca.
    for tabla in ("formacion.\"OnboardingPasoProgreso\"", "formacion.\"OnboardingAsignacion\"",
                  "formacion.\"OnboardingPaso\"", "formacion.\"OnboardingPlantilla\"",
                  "formacion.\"BibliotecaConfirmacion\"", "formacion.\"BibliotecaMaterial\"",
                  "formacion.\"ProductoLinea\"", '"Config"."DIM_RM"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Línea de Cardiología con dos productos principales, como el mockup.

    CardioZ lleva material obligatorio; Antihipertensivos no. Esa asimetría es
    deliberada: permite comprobar que el bloqueo por lectura afecta solo al paso
    del producto que sí lo exige.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante de Prueba")
    db.add(rm)
    cardioz = ProductoLinea(pais_codigo="DO", linea_id=linea.id,
                            nombre_producto="CardioZ", rol_en_ruta="principal")
    anti = ProductoLinea(pais_codigo="DO", linea_id=linea.id,
                         nombre_producto="Antihipertensivos", rol_en_ruta="principal")
    relacionado = ProductoLinea(pais_codigo="DO", linea_id=linea.id,
                                nombre_producto="Complemento", rol_en_ruta="relacionado")
    db.add_all([cardioz, anti, relacionado])
    db.flush()
    materiales = [
        BibliotecaMaterial(pais_codigo="DO", producto_id=cardioz.id,
                           titulo="Ficha técnica CardioZ", tipo="ficha_tecnica",
                           archivo_url="/x/1.pdf", obligatorio=True, aprobado_por_gm=True),
        BibliotecaMaterial(pais_codigo="DO", producto_id=cardioz.id,
                           titulo="Estudio clínico CardioZ", tipo="estudio_clinico",
                           archivo_url="/x/2.pdf", obligatorio=True, aprobado_por_gm=True),
        # No obligatorio: no debe bloquear nada.
        BibliotecaMaterial(pais_codigo="DO", producto_id=relacionado.id,
                           titulo="Folleto de consulta", tipo="manual",
                           archivo_url="/x/3.pdf", obligatorio=False, aprobado_por_gm=True),
    ]
    db.add_all(materiales)
    db.commit()
    plantilla = onboarding.crear_plantilla_estandar(
        db, "DO", linea.id, "Onboarding Cardiología")
    asignacion = onboarding.asignar(db, plantilla.id, rm.id, date(2026, 7, 1))
    return {"db": db, "linea": linea, "rm": rm, "cardioz": cardioz, "anti": anti,
            "materiales": materiales, "plantilla": plantilla, "asignacion": asignacion}


def _paso(estado: dict, contiene: str) -> dict:
    return next(p for p in estado["pasos"] if contiene.lower() in p["titulo"].lower())


# ---------------------------------------------------------------------------
# Constructor (§4.2 / §4.3)
# ---------------------------------------------------------------------------

def test_la_ruta_repite_el_paso_david_por_cada_producto_principal(escenario):
    """§4.3: dos productos principales → dos pasos DAVID. El 'relacionado' no
    agrega paso propio."""
    pasos = onboarding.pasos_de(escenario["db"], escenario["plantilla"].id)
    david = [p for p in pasos if "DAVID" in p.titulo]
    assert len(david) == 2
    assert {"CardioZ", "Antihipertensivos"} == {p.titulo.split(" —")[0] for p in david}
    assert not any("Complemento" in p.titulo for p in pasos)


def test_el_orden_pedagogico_se_respeta(escenario):
    """§4.2: la base científica va antes que los productos, y la visión general
    de la línea antes del detalle DAVID. El cliente lo confirmó tras dos
    correcciones; invertirlo sería enseñar el producto antes que la patología."""
    titulos = [p.titulo for p in onboarding.pasos_de(escenario["db"],
                                                     escenario["plantilla"].id)]
    pos = {t: i for i, t in enumerate(titulos)}
    farmacologia = pos["Farmacología general"]
    patologias = next(i for t, i in pos.items() if "Patologías" in t)
    vision = next(i for t, i in pos.items() if "visión general" in t)
    primer_david = min(i for t, i in pos.items() if "DAVID" in t)
    assert farmacologia < patologias < vision < primer_david
    assert titulos[-1].startswith("Checkpoint final")


# ---------------------------------------------------------------------------
# §16 caso 1 — las DOS condiciones bloquean, por separado
# ---------------------------------------------------------------------------

def test_el_examen_david_esta_bloqueado_si_falta_el_paso_previo(escenario):
    """Primera condición del caso 1: aunque el material estuviera leído, no se
    llega al DAVID sin haber pasado por la visión general de la línea."""
    db = escenario["db"]
    for m in escenario["materiales"]:
        biblioteca.confirmar_lectura(db, m.id, escenario["rm"].id)
    estado = onboarding.estado_ruta(db, escenario["asignacion"].id)
    david = _paso(estado, "CardioZ — DAVID")
    assert david["estado"] == "bloqueado"
    assert any("Falta completar antes" in b for b in david["bloqueos"])


def test_el_examen_esta_bloqueado_si_falta_la_lectura_obligatoria(escenario):
    """Segunda condición del caso 1, aislada: con TODOS los pasos previos
    completos, la lectura pendiente sigue bloqueando."""
    db = escenario["db"]
    estado = onboarding.estado_ruta(db, escenario["asignacion"].id)
    vision = _paso(estado, "visión general")
    # El paso de visión general exige el material de todos los productos.
    assert vision["estado"] == "bloqueado"
    assert any("confirmar lectura" in b for b in vision["bloqueos"])
    assert vision["material"]["confirmados"] == 0
    assert vision["material"]["total"] == 2  # los dos obligatorios de CardioZ


def test_el_material_no_obligatorio_no_bloquea(escenario):
    """§5.3: lo marcado como consulta libre no participa del gating."""
    db = escenario["db"]
    estado = onboarding.estado_ruta(db, escenario["asignacion"].id)
    vision = _paso(estado, "visión general")
    titulos = [m["titulo"] for m in vision["material"]["pendientes"]]
    assert "Folleto de consulta" not in titulos


def test_no_se_puede_completar_un_paso_bloqueado(escenario):
    """El bloqueo no es solo un adorno de la interfaz: el servicio lo hace
    cumplir, que es lo que impide saltárselo llamando a la API directamente."""
    db = escenario["db"]
    estado = onboarding.estado_ruta(db, escenario["asignacion"].id)
    vision = _paso(estado, "visión general")
    with pytest.raises(onboarding.PasoBloqueado) as e:
        onboarding.completar_paso(db, escenario["asignacion"].id, vision["paso_id"],
                                  rol_actor="sistema")
    assert "confirmar lectura" in str(e.value)


# ---------------------------------------------------------------------------
# §16 caso 2 — al confirmar el último material, se desbloquea de inmediato
# ---------------------------------------------------------------------------

def test_al_confirmar_el_ultimo_material_el_examen_se_desbloquea(escenario):
    """Caso 2 completo: el desbloqueo ocurre en la misma operación, sin proceso
    posterior ni recarga."""
    db, asignacion = escenario["db"], escenario["asignacion"]
    obligatorios = [m for m in escenario["materiales"] if m.obligatorio]

    biblioteca.confirmar_lectura(db, obligatorios[0].id, escenario["rm"].id)
    vision = _paso(onboarding.estado_ruta(db, asignacion.id), "visión general")
    assert vision["estado"] == "bloqueado", "con uno de dos aún debe bloquear"
    assert vision["material"]["confirmados"] == 1

    biblioteca.confirmar_lectura(db, obligatorios[1].id, escenario["rm"].id)
    vision = _paso(onboarding.estado_ruta(db, asignacion.id), "visión general")
    assert vision["material"]["completo"] is True
    # Los pasos anteriores siguen pendientes, así que el bloqueo que queda ya no
    # es por lectura: eso es lo que se está comprobando.
    assert not any("confirmar lectura" in b for b in vision["bloqueos"])


def test_confirmar_dos_veces_no_altera_el_progreso(escenario):
    """Un doble clic no debe contar como dos lecturas ni reventar."""
    db = escenario["db"]
    m = escenario["materiales"][0]
    primera = biblioteca.confirmar_lectura(db, m.id, escenario["rm"].id)
    segunda = biblioteca.confirmar_lectura(db, m.id, escenario["rm"].id)
    assert primera.id == segunda.id
    assert primera.timestamp_confirmacion == segunda.timestamp_confirmacion


def test_no_se_confirma_material_sin_aprobacion_de_gerencia_medica(escenario):
    """Firewall PhRMA (§2): el contenido científico no llega al RM antes de que
    Gerente Médico lo apruebe."""
    db = escenario["db"]
    sin_aprobar = BibliotecaMaterial(
        pais_codigo="DO", producto_id=escenario["cardioz"].id,
        titulo="Borrador sin revisar", tipo="manual", archivo_url="/x/9.pdf",
        obligatorio=True, aprobado_por_gm=False)
    db.add(sin_aprobar)
    db.commit()
    with pytest.raises(biblioteca.MaterialNoAprobado):
        biblioteca.confirmar_lectura(db, sin_aprobar.id, escenario["rm"].id)


def test_el_material_sin_aprobar_tampoco_bloquea_al_representante(escenario):
    """Complemento del anterior: si bloqueara, el RM quedaría atascado por algo
    que solo Gerencia Médica puede resolver."""
    db = escenario["db"]
    db.add(BibliotecaMaterial(
        pais_codigo="DO", producto_id=escenario["cardioz"].id,
        titulo="Borrador sin revisar", tipo="manual", archivo_url="/x/9.pdf",
        obligatorio=True, aprobado_por_gm=False))
    db.commit()
    progreso = biblioteca.progreso_lectura(db, escenario["rm"].id, [escenario["cardioz"].id])
    assert progreso["total"] == 2, "el borrador no debe contarse"


# ---------------------------------------------------------------------------
# §4.6 — quién marca cada paso
# ---------------------------------------------------------------------------

def test_el_representante_no_puede_marcar_el_hito_de_campo(escenario):
    """§4.6: el hito lo marca el GD, que es quien acompañó la visita. Si lo
    marcara el propio representante, el hito no probaría nada."""
    db = escenario["db"]
    hito = _paso(onboarding.estado_ruta(db, escenario["asignacion"].id), "Hito de Campo")
    with pytest.raises(onboarding.RolNoAutorizado) as e:
        onboarding.completar_paso(db, escenario["asignacion"].id, hito["paso_id"],
                                  rol_actor="representante")
    assert "gd" in str(e.value)


def test_el_checkpoint_final_lo_aprueba_capacitacion(escenario):
    db = escenario["db"]
    cp = _paso(onboarding.estado_ruta(db, escenario["asignacion"].id), "Checkpoint final")
    assert cp["quien_lo_marca"] == "capacitacion"
    with pytest.raises(onboarding.RolNoAutorizado):
        onboarding.completar_paso(db, escenario["asignacion"].id, cp["paso_id"],
                                  rol_actor="gd")


# ---------------------------------------------------------------------------
# Avance de la ruta
# ---------------------------------------------------------------------------

def test_la_ruta_avanza_y_el_progreso_refleja_lo_completado(escenario):
    db, asignacion = escenario["db"], escenario["asignacion"]
    estado = onboarding.estado_ruta(db, asignacion.id)
    primero = estado["pasos"][0]
    assert primero["estado"] == "disponible"
    onboarding.completar_paso(db, asignacion.id, primero["paso_id"],
                              rol_actor="representante")
    estado = onboarding.estado_ruta(db, asignacion.id)
    assert estado["pasos"][0]["estado"] == "completado"
    assert estado["completados"] == 1
    assert estado["progreso_pct"] > 0
    # Y el siguiente queda disponible, porque el anterior dejó de frenar.
    assert estado["pasos"][1]["estado"] == "disponible"
