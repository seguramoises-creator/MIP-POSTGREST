"""Simulacro de Venta con IA (Fase 8) — motor sobre la capa de IA (mockeada)."""
import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Gerente, Linea, Pais, RepresentanteMedico
from app.services import formacion_simulacro_service as sim

BD_PRUEBA = "vista_test_simulacro"


@pytest.mark.parametrize("ratio, esperado", [
    (1.0, 4), (0.90, 4), (0.89, 3), (0.70, 3), (0.69, 2),
    (0.50, 2), (0.49, 1), (0.0, 1),
])
def test_la_escala_dpae_respeta_los_cortes(ratio, esperado):
    assert sim.escala(ratio) == esperado


def test_las_fases_calificadas_son_tres():
    assert sim.FASES == ("Apertura", "Desarrollo", "Cierre")


# --- infraestructura de BD (patrón de test_formacion_calendario) ---
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
    for t in ('formacion."SimulacroResultado"', 'formacion."SimulacroRonda"',
              'formacion."SimulacroSesion"', '"Config"."DIM_RM"',
              '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.add(Pais(codigo="DO", nombre="República Dominicana")); s.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología"); s.add(linea); s.flush()
    gd = Gerente(pais_codigo="DO", codigo="GD-1", nombre="GD Uno", tipo="DISTRITO"); s.add(gd); s.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                             codigo="VM01", nombre="Ana"); s.add(rm); s.commit()
    yield s, rm, gd
    s.close()


# Escenario canónico que devuelve la IA mockeada (reutilizado por varias pruebas).
ESCENARIO_OK = {
    "rondas": [
        {"fase_more": "Apertura", "objecion_texto": "No tengo tiempo hoy.",
         "opciones": {"A": "Insistir", "B": "Acordar 2 minutos y ser concreto", "C": "Irse"},
         "opcion_correcta": "B", "retroalimentacion": "Respetar el tiempo abre la puerta."},
        {"fase_more": "Desarrollo", "tecnica_objecion": "Sentir-Sintió-Descubrió",
         "objecion_texto": "Su producto es caro.",
         "opciones": {"A": "Bajar el precio", "B": "Reconocer y mostrar valor clínico", "C": "Callar"},
         "opcion_correcta": "B", "retroalimentacion": "El valor se argumenta, no se descuenta."},
        {"fase_more": "Cierre", "objecion_texto": "Lo pensaré.",
         "opciones": {"A": "Cerrar con un compromiso concreto", "B": "Despedirse sin más"},
         "opcion_correcta": "A", "retroalimentacion": "Un cierre pide un siguiente paso claro."},
    ]
}


class _TextoStub:
    """Adaptador de texto de prueba: devuelve el JSON que se le configure."""
    def __init__(self, payload): self._payload = payload
    def generar_texto(self, prompt, max_tokens=4000): return self._payload


class _VozStub:
    def sintetizar(self, texto, voz=None):
        from app.services.ia.base import Audio
        return Audio(en_navegador=True, aviso="prueba")


def test_parsea_escenario_con_fences_markdown():
    crudo = "```json\n" + json.dumps(ESCENARIO_OK) + "\n```"
    rondas = sim.parsear_escenario(crudo)
    assert [r["fase_more"] for r in rondas] == ["Apertura", "Desarrollo", "Cierre"]
    assert rondas[1]["tecnica_objecion"] == "Sentir-Sintió-Descubrió"


def test_rechaza_escenario_sin_opcion_correcta_valida():
    malo = {"rondas": [{"fase_more": "Apertura", "objecion_texto": "x",
                        "opciones": {"A": "s"}, "opcion_correcta": "Z",
                        "retroalimentacion": "r"}]}
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario(json.dumps(malo))


def test_rechaza_desarrollo_sin_tecnica():
    malo = {"rondas": [{"fase_more": "Desarrollo", "objecion_texto": "x",
                        "opciones": {"A": "s", "B": "t"}, "opcion_correcta": "A",
                        "retroalimentacion": "r"}]}
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario(json.dumps(malo))


def test_rechaza_json_no_json():
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario("esto no es json")


def test_iniciar_persiste_las_tres_rondas_sin_filtrar_la_correcta(db, monkeypatch):
    s, rm, _ = db
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub(json.dumps(ESCENARIO_OK)))
    r = sim.iniciar(s, rm.id, estilo="Analitico", medico="Dr. Peralta", genero="M")
    assert r["sesion"]["estilo"] == "Analitico"
    assert len(r["rondas"]) == 3
    serial = json.dumps(r["rondas"])
    assert "opcion_correcta" not in serial and "retroalimentacion" not in serial
    # Las opciones sí viajan (sin ellas no hay nada que elegir).
    assert set(r["rondas"][0]["opciones"]) >= {"A", "B"}


def test_iniciar_reintenta_una_vez_y_luego_falla(db, monkeypatch):
    s, rm, _ = db
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub("basura no json"))
    with pytest.raises(sim.SimulacroIAError):
        sim.iniciar(s, rm.id, estilo="Directivo", medico="Dra. Reyes", genero="F")


def _iniciar_ok(s, rm, monkeypatch):
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub(json.dumps(ESCENARIO_OK)))
    return sim.iniciar(s, rm.id, estilo="Amistoso", medico="Dra. Fermín", genero="F")


def test_responder_correcto_revela_correcta_y_retro(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    ronda_id = r["rondas"][0]["id"]      # Apertura, correcta = B
    res = sim.responder(s, ronda_id, "B")
    assert res["es_correcta"] is True
    assert res["opcion_correcta"] == "B"
    assert "puerta" in res["retroalimentacion"]


def test_responder_incorrecto_tambien_revela(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    res = sim.responder(s, r["rondas"][0]["id"], "A")
    assert res["es_correcta"] is False
    assert res["opcion_correcta"] == "B"


def test_no_se_responde_dos_veces(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    rid = r["rondas"][0]["id"]
    sim.responder(s, rid, "A")
    with pytest.raises(ValueError):
        sim.responder(s, rid, "B")


def test_un_rm_ajeno_no_puede_responder(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    with pytest.raises(sim.PermisoError):
        sim.responder(s, r["rondas"][0]["id"], "B", rm_id_scope=rm.id + 999)
