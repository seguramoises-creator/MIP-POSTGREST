"""Tests Módulo de Visita Médica — Fase 1 (antiduplicados + validación de nombre)."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import visita_service
from app.schemas.visita import MedicoVisitaCrear


def _db_con(medicos):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = medicos
    return db


def test_duplicado_dispara_con_2_palabras():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL ANTONIO", direccion="x")])
    dups = visita_service.detectar_duplicados(db, "PEREZ VALDEZ JUAN")
    assert len(dups) == 1 and dups[0]["palabras_coinciden"] == 2


def test_duplicado_no_dispara_con_1_palabra():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    # Solo "VALDEZ" en común (1 palabra) → no se considera duplicado.
    assert visita_service.detectar_duplicados(db, "GOMEZ VALDEZ CARLOS") == []
    # Ninguna palabra en común → tampoco.
    assert visita_service.detectar_duplicados(db, "GOMEZ SUERO CARLOS") == []


def test_crear_sin_confirmar_levanta_duplicado(monkeypatch):
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    datos = MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ VALDEZ JUAN", categoria="A")
    with pytest.raises(visita_service.DuplicadoMedicoError):
        visita_service.crear_medico(db, datos, usuario_id=1)


def test_nombre_se_normaliza_a_mayusculas():
    m = MedicoVisitaCrear(vm_id=1, nombre_completo="manuel  perez garcia", categoria="a")
    assert m.nombre_completo == "MANUEL PEREZ GARCIA" and m.categoria == "A"


def test_nombre_1_palabra_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ", categoria="A")


def test_nombre_con_punto_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="DR. PEREZ GARCIA", categoria="A")


def test_categoria_invalida_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="MANUEL PEREZ", categoria="D")


# ── Registro de visita ────────────────────────────────────────────────
from app.schemas.visita import VisitaRegistrar, VisitaNoVisita


def test_visita_comentario_generico_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="VISITA OK")


def test_visita_comentario_corto_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="corto")


def test_visita_valida_normaliza_tipo():
    v = VisitaRegistrar(medico_id=1, tipo_visita="v", comentario="MEDICO SOLICITO ESTUDIO CLINICO")
    assert v.tipo_visita == "V"


def test_visita_tipo_invalido_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="X", comentario="COMENTARIO VALIDO LARGO")


def test_visita_hace_minutos_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="COMENTARIO VALIDO", hace_minutos=90)


def test_no_visita_causa_valida():
    nv = VisitaNoVisita(medico_id=1, causa="Consultorio Cerrado (sin aviso previo)")
    assert nv.causa.startswith("Consultorio")


def test_no_visita_causa_invalida_falla():
    with pytest.raises(ValueError):
        VisitaNoVisita(medico_id=1, causa="porque sí")


# ── Proyección ────────────────────────────────────────────────────────
from datetime import date
from app.services.visita_cobertura_service import _dias_habiles


def test_dias_habiles():
    assert _dias_habiles(date(2026, 6, 1), date(2026, 6, 5)) == 5   # lun→vie
    assert _dias_habiles(date(2026, 6, 1), date(2026, 6, 8)) == 6   # incluye finde
    assert _dias_habiles(None, None) == 19                          # fallback


# ── Planeación del ciclo (reglas P01/P02/P03) ─────────────────────────
from app.schemas.visita import PlaneacionItem
from app.services.visita_planeacion_service import _validar


def _it(medico_id, tipo, semana):
    return PlaneacionItem(medico_id=medico_id, tipo_visita=tipo, semana=semana)


def test_planeacion_valida_vista_y_revisita_posterior():
    _validar([_it(1, "V", 1), _it(1, "R", 3)])  # no levanta


def test_planeacion_valida_misma_semana_sin_dia():
    _validar([_it(1, "V", 2), _it(1, "R", 2)])  # V+R misma semana, sin día → ok


def test_planeacion_p01_maximo_dos_por_medico():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 1), _it(1, "R", 2), _it(1, "V", 3)])


def test_planeacion_dos_vistas_mismo_medico_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 1), _it(1, "V", 2)])


def test_planeacion_p02_revisita_antes_de_vista_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 3), _it(1, "R", 1)])


def test_planeacion_revisita_sin_vista_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "R", 2)])


def test_planeacion_p03_mismo_dia_falla():
    v = PlaneacionItem(medico_id=1, tipo_visita="V", semana=2, dia_semana="Lunes")
    r = PlaneacionItem(medico_id=1, tipo_visita="R", semana=2, dia_semana="Lunes")
    with pytest.raises(ValueError):
        _validar([v, r])


# ── Ruptura de secuencia / Cierre de ciclo ────────────────────────────
from app.services import visita_cierre_service as cs


def test_severidad_por_ciclos_sin_visita():
    assert cs._severidad(0) == "ninguna"
    assert cs._severidad(1) == "alerta"
    assert cs._severidad(2) == "grave"
    assert cs._severidad(3) == "critica"
    assert cs._severidad(7) == "critica"


def test_cierre_resetea_visitados_e_incrementa_ausentes(monkeypatch):
    # m1 visitado (contador 5 → 0); m2 sin visita (contador 2 → 3 = crítica)
    m1 = SimpleNamespace(id=1, ciclos_sin_visita=5, activo=True)
    m2 = SimpleNamespace(id=2, ciclos_sin_visita=2, activo=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [m1, m2]
    monkeypatch.setattr(cs, "_mapa_visitas", lambda db, ciclo, vm: {1: {"v": True, "r": False}})
    r = cs._resumen_cierre(db, ciclo_id=10, aplicar=True, usuario_id=None)
    assert r["panel"] == 2 and r["visitados"] == 1 and r["sin_visitar"] == 1
    assert r["ruptura_nueva"] == 1 and r["ruptura_critica"] == 1
    assert m1.ciclos_sin_visita == 0   # reseteado por haber sido visitado
    assert m2.ciclos_sin_visita == 3   # incrementado a ruptura crítica


def test_cierre_previsualizar_no_muta(monkeypatch):
    m = SimpleNamespace(id=1, ciclos_sin_visita=1, activo=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [m]
    db.query.return_value.filter.return_value.first.return_value = None  # no cerrado aún
    monkeypatch.setattr(cs, "_mapa_visitas", lambda db, ciclo, vm: {})   # nadie visitado
    monkeypatch.setattr(cs, "ciclo_por_defecto", lambda db: 10)
    r = cs.previsualizar_cierre(db, ciclo_id=10)
    assert r["sin_visitar"] == 1 and r["ya_cerrado"] is False
    assert m.ciclos_sin_visita == 1    # NO se modificó (dry-run)


def test_cierre_bloquea_si_ya_cerrado(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fecha_cierre=None)
    with pytest.raises(cs.CicloVisitaYaCerradoError):
        cs.cerrar_ciclo(db, ciclo_id=10, usuario_id=1)
