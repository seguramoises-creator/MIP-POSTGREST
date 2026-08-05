"""Calendario de Coaching (Fase 4) — motor de reglas sobre el cuadrante LSII."""
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.formacion import ParametroFrecuenciaLSII
from app.models.hechos import EvaluacionReceptividad
from app.services import formacion_calendario_service as cal

BD_PRUEBA = "vista_test_calcoach"


def test_reparto_de_una_visita_cae_a_mitad_del_ciclo():
    assert cal.distribuir_semanas(1, 8) == [4]


def test_reparto_de_cuatro_visitas_queda_espaciado():
    assert cal.distribuir_semanas(4, 8) == [1, 3, 5, 7]


def test_reparto_de_dos_visitas():
    assert cal.distribuir_semanas(2, 8) == [2, 6]


def test_cero_visitas_no_agenda_nada():
    assert cal.distribuir_semanas(0, 8) == []


def test_mas_visitas_que_semanas_se_acota_al_rango():
    # Nunca propone una semana fuera de [1, semanas]; puede repetir semana.
    r = cal.distribuir_semanas(10, 4)
    assert len(r) == 10
    assert all(1 <= s <= 4 for s in r)


def test_frecuencia_arranca_en_los_valores_por_defecto(db):
    f = cal.frecuencias(db, "DO")
    assert f == {"D1": 4, "D2": 3, "D3": 2, "D4": 1}


def test_un_pais_puede_sobrescribir_una_frecuencia(db):
    cal.fijar_frecuencia(db, "DO", "D1", 6)
    assert cal.frecuencias(db, "DO")["D1"] == 6
    # Override por país: otro país conserva el arranque.
    assert cal.frecuencias(db, "PA")["D1"] == 4


def test_fijar_un_cuadrante_invalido_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D9", 1)


def test_fijar_visitas_negativas_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D1", -1)


# --- infraestructura de BD (igual patrón que test_formacion_brechas) ---
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
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
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
    for t in ('formacion."CalendarioCoachingSugerido"', 'formacion."ParametroFrecuenciaLSII"',
              '"DW"."FACT_EvaluacionReceptividad"', '"Config"."DIM_RM"',
              '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Ciclo"',
              '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.add_all([Pais(codigo="DO", nombre="República Dominicana"),
               Pais(codigo="PA", nombre="Panamá")])
    s.commit()
    yield s
    s.close()


@pytest.fixture
def equipo(db):
    """Un GD con dos RM y un ciclo con fechas de 8 semanas."""
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea); db.flush()
    gd = Gerente(pais_codigo="DO", codigo="GD-1", nombre="GD Uno", tipo="DISTRITO")
    db.add(gd); db.flush()
    rm_a = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM01", nombre="Ana")
    rm_b = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM02", nombre="Beto")
    db.add_all([rm_a, rm_b])
    ciclo = Ciclo(pais_codigo="DO", nombre="C07-2026", anio=2026, numero=7,
                  cerrado=False, fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 7, 26))
    db.add(ciclo); db.commit()
    return {"db": db, "gd": gd, "rm_a": rm_a, "rm_b": rm_b, "ciclo": ciclo, "linea": linea}


def _eval(db, rm_id, ciclo_id, nivel):
    e = EvaluacionReceptividad(pais_codigo="DO", rm_id=rm_id, ciclo_id=ciclo_id,
                               score_receptividad=50, nivel_lsii=nivel,
                               estilo_liderazgo="X", activo=True)
    db.add(e); db.commit(); return e


def test_cuadrante_vigente_toma_la_ultima_evaluacion(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, rm.id, ciclo.id, "D3")
    _eval(db, rm.id, ciclo.id, "D1")   # más reciente
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) == "D1"


def test_rm_sin_evaluacion_no_tiene_cuadrante(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_b"], equipo["ciclo"]
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) is None


def test_orden_por_roi_pone_primero_el_de_menor_roi(equipo, monkeypatch):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    monkeypatch.setattr(cal.visita_costo_service, "roi_ranking",
                        lambda _db, _c: {"items": [{"vm_id": b.id, "valor": -10.0},
                                                   {"vm_id": a.id, "valor": 30.0}]})
    assert cal.orden_por_roi(db, [a.id, b.id], 999) == [b.id, a.id]


def test_rm_sin_roi_previo_queda_al_final(equipo, monkeypatch):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    monkeypatch.setattr(cal.visita_costo_service, "roi_ranking",
                        lambda _db, _c: {"items": [{"vm_id": a.id, "valor": 5.0}]})
    # b no tiene ROI previo → al final; a primero.
    assert cal.orden_por_roi(db, [a.id, b.id], 999) == [a.id, b.id]


def test_sin_ciclo_anterior_conserva_orden_estable(equipo):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    assert cal.orden_por_roi(db, [a.id, b.id], None) == [a.id, b.id]


def test_ciclo_anterior_es_el_previo_del_mismo_pais(equipo):
    db, ciclo = equipo["db"], equipo["ciclo"]
    # fecha_inicio/fecha_fin son NOT NULL en DIM_Ciclo — hay que darlas.
    prev = Ciclo(pais_codigo="DO", nombre="C06-2026", anio=2026, numero=6, cerrado=True,
                 fecha_inicio=date(2026, 4, 1), fecha_fin=date(2026, 5, 26))
    db.add(prev); db.commit()
    assert cal.ciclo_anterior_id(db, ciclo) == prev.id


def test_generar_agenda_segun_frecuencia_y_separa_sin_evaluar(equipo):
    db, gd, a, b, ciclo = (equipo["db"], equipo["gd"], equipo["rm_a"],
                           equipo["rm_b"], equipo["ciclo"])
    _eval(db, a.id, ciclo.id, "D1")   # D1 → 4 visitas
    # b queda sin evaluación LSII
    r = cal.generar(db, gd.id, ciclo.id, persistir=False)
    assert r["semanas"] == 8
    celdas_a = [c for c in r["celdas"] if c["rm_id"] == a.id]
    assert len(celdas_a) == 4
    assert {c["semana"] for c in celdas_a} == {1, 3, 5, 7}
    assert all(c["cuadrante"] == "D1" for c in celdas_a)
    assert [s["rm_id"] for s in r["sin_evaluar"]] == [b.id]


def test_generar_persiste_y_regenerar_conserva_lo_publicado(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D4")   # D4 → 1 visita
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    from app.models.formacion import CalendarioCoachingSugerido as CC
    celda = db.query(CC).filter(CC.gd_id == gd.id).one()
    celda.publicado = True; db.commit()
    # Regenerar no debe borrar la celda publicada NI duplicar al RM ya agendado.
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    assert db.query(CC).filter(CC.gd_id == gd.id, CC.publicado.is_(True)).count() == 1
    assert db.query(CC).filter(CC.gd_id == gd.id).count() == 1, "no se duplica el RM preservado"


def test_generar_persiste_devuelve_solo_lo_insertado_no_lo_preservado(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D4")   # D4 → 1 visita
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    from app.models.formacion import CalendarioCoachingSugerido as CC
    celda = db.query(CC).filter(CC.gd_id == gd.id).one()
    celda.publicado = True; db.commit()
    # Regenerar: la celda de "a" está preservada (publicada), por lo tanto no se
    # reinserta. El dict devuelto debe reflejar eso — no debe traer al RM preservado.
    r = cal.generar(db, gd.id, ciclo.id, persistir=True)
    assert [c for c in r["celdas"] if c["rm_id"] == a.id] == []


def test_generar_sobre_ciclo_cerrado_aborta(equipo):
    from app.services.recalculo_service import CicloCerradoError
    db, gd, ciclo = equipo["db"], equipo["gd"], equipo["ciclo"]
    ciclo.cerrado = True; db.commit()
    with pytest.raises(CicloCerradoError):
        cal.generar(db, gd.id, ciclo.id, persistir=True)


def test_mover_celda_la_marca_editada(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D4")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    celda = cal.listar(db, gd.id, ciclo.id)[0]
    m = cal.mover_celda(db, celda.id, semana=2, dia_semana="viernes")
    assert m.semana == 2 and m.dia_semana == "viernes" and m.editado_manualmente is True


def test_publicar_marca_todas_las_celdas(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D1")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    n = cal.publicar(db, gd.id, ciclo.id)
    assert n == 4
    assert all(c.publicado for c in cal.listar(db, gd.id, ciclo.id))


def test_publicar_sobre_ciclo_cerrado_aborta(equipo):
    from app.services.recalculo_service import CicloCerradoError
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D1")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    ciclo.cerrado = True; db.commit()
    with pytest.raises(CicloCerradoError):
        cal.publicar(db, gd.id, ciclo.id)
