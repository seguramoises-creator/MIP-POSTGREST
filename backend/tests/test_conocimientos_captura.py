"""Captura manual de notas de conocimiento y su integración al ciclo.

Sustituye al Excel para EVAL_CONOCIMIENTOS. Necesita PostgreSQL real.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, integracion_hallazgo, mapeo_externo,
    seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Ciclo, Gerente, Indicador, Linea, Pais, RepresentanteMedico
from app.models.hechos import NotaConocimiento, ResultadoIndicador
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fs
from app.services import motor_calculo_service

BD_PRUEBA = "vista_test_conoc_captura"


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
def escenario(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"DW"."FACT_NotaConocimiento"', '"DW"."FACT_ResultadoIndicador"',
                  '"Config"."DIM_Indicador"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()

    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    s.add(linea)
    s.flush()
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="g@ejemplo.com", tipo="DISTRITO")
    s.add(gerente)
    s.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             gerente_id=gerente.id, codigo="VM01",
                             nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    s.add_all([rm, ciclo])
    s.flush()
    indicadores = {}
    for codigo, escala in (("EVAL_CONOCIMIENTOS", 100), ("COB_MD_F1", 1),
                           ("VENTAS", 1)):
        i = Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                      modulo="RESULTADOS", tipo_periodo="CICLO", escala=escala,
                      ponderacion_pct=10, activo=True)
        s.add(i)
        s.flush()
        indicadores[codigo] = i
    s.commit()
    yield {"db": s, "rm": rm, "ciclo": ciclo, "linea": linea,
           "gerente": gerente, "ind": indicadores}
    s.close()


def _resultado(e, codigo):
    return (e["db"].query(ResultadoIndicador)
            .filter(ResultadoIndicador.indicador_id == e["ind"][codigo].id,
                    ResultadoIndicador.ciclo_id == e["ciclo"].id).first())


def test_capturar_y_listar_marca_quien_falta(escenario):
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), "Cardio", usuario_id=3)
    e["db"].commit()

    filas = cs.notas_del_ciclo(e["db"], "DO", e["ciclo"].id)

    assert len(filas) == 1
    assert filas[0]["rm_id"] == e["rm"].id
    assert filas[0]["notas"][0]["nota"] == Decimal("80.0000")


def test_una_nota_fuera_de_rango_se_rechaza_en_el_servicio(escenario):
    """En el servicio, no solo en el formulario: la API la puede llamar
    cualquiera."""
    e = escenario
    for mala in (Decimal("-1"), Decimal("101")):
        with pytest.raises(ValueError):
            cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, mala,
                             date(2026, 1, 15), None, usuario_id=3)


def test_corregir_EDITA_la_fila_no_anade_otra(escenario):
    """La tabla no lleva UNIQUE, así que si corregir insertara, la nota vieja
    seguiría entrando al promedio y el número saldría mal sin que nada lo
    delatara."""
    e = escenario
    fila = cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id,
                            Decimal("60"), date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    cs.corregir_nota(e["db"], fila.id, Decimal("90"), "Corregida", usuario_id=4)
    e["db"].commit()

    todas = e["db"].query(NotaConocimiento).all()
    assert len(todas) == 1
    assert todas[0].nota == Decimal("90.0000")
    # Queda quién la tocó por última vez y cuándo: es lo que hace auditable la
    # corrección, y es justo lo que una hoja de cálculo no deja.
    assert todas[0].capturado_por_usuario_id == 4
    assert todas[0].capturado_en is not None

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("90.0000")


def test_capturar_una_segunda_nota_SI_anade_fila_y_promedia(escenario):
    """La frontera con el test anterior: corregir edita, capturar añade."""
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("60"),
                     date(2026, 1, 15), "Tema A", usuario_id=3)
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("100"),
                     date(2026, 1, 20), "Tema B", usuario_id=3)
    e["db"].commit()

    assert e["db"].query(NotaConocimiento).count() == 2

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")


def test_un_rm_sin_notas_no_genera_fila(escenario):
    e = escenario
    out = cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_integrar_atraviesa_el_motor_y_puntua(escenario):
    """Afirmar solo sobre `resultado_real` es comparar el valor consigo mismo.
    EVAL_CONOCIMIENTOS tiene escala=100 y ponderación 10: una nota de 80 debe
    dar 8 puntos."""
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()
    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()

    fila = _resultado(e, "EVAL_CONOCIMIENTOS")
    assert fila.resultado_porcentaje == Decimal("80.0000")
    assert fila.puntos_obtenidos == Decimal("8.0000")
    # `pais_codigo`, `linea_id` y `gerente_id` son NOT NULL y NO vienen en la
    # nota: salen del RM. Sin esto el INSERT ni siquiera llegaría a la BD.
    assert fila.pais_codigo == "DO"
    assert fila.linea_id == e["linea"].id
    assert fila.gerente_id == e["gerente"].id


def test_integrar_dos_veces_no_duplica(escenario):
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["EVAL_CONOCIMIENTOS"].id).all())
    assert len(filas) == 1


def test_ciclo_cerrado_no_escribe_ni_borra(escenario):
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("55"), activo=True))
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["ciclo"].cerrado = True
    e["db"].commit()

    out = cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    assert out["abortado"] is True
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("55.0000")


def test_integrar_se_niega_si_el_pais_no_es_de_captura(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    with pytest.raises(fs.FuenteAjenaError):
        cs.integrar_captura(e["db"], "DO", e["ciclo"].id)

    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
