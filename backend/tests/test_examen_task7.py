"""Tests para Task 7: generar_reporte, _resolver_evaluado, listar_pendientes,
listar_historial, iniciar_para_evaluado, _reconstruir_mapa_opcion.

Usa el patrón FakeQuery de conftest.py — sin BD real.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import examen_intento_service as svc
from tests.conftest import FakeQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intento(fecha_fin=None, mapa=None, rm_id=5, gerente_id=None):
    return SimpleNamespace(
        id=10,
        asignacion_id=3,
        evaluado_tipo="RM" if rm_id else "GERENTE",
        evaluado_rm_id=rm_id,
        evaluado_gerente_id=gerente_id,
        fecha_fin=fecha_fin,
        score=80.0 if fecha_fin else None,
        aprobado=True if fecha_fin else None,
        fecha_inicio=datetime(2026, 6, 27, 10, 0, tzinfo=timezone.utc),
        mapa_presentacion_json=mapa,
        tiempo_usado_seg=None,
    )


def _asig(estado="pendiente", rm_id=5, gerente_id=None):
    return SimpleNamespace(
        id=3,
        examen_id=7,
        evaluado_tipo="RM" if rm_id else "GERENTE",
        evaluado_rm_id=rm_id,
        evaluado_gerente_id=gerente_id,
        estado=estado,
        intentos_max=None,
        intentos_usados=0,
        fecha_limite=None,
    )


def _examen():
    return SimpleNamespace(
        id=7, nombre="Examen Test", producto="Producto X",
        nota_minima=70, estado="activo",
        rand_preguntas=False, rand_opciones=False,
        tiempo_limite_min=30,
    )


def _pregunta(pid=1):
    return SimpleNamespace(
        id=pid, texto=f"Pregunta {pid}", explicacion=f"Explicacion {pid}",
        activo=True,
    )


def _opcion(id, texto, es_correcta=False, indice_original=0, pregunta_id=1):
    return SimpleNamespace(
        id=id, texto_opcion=texto, es_correcta=es_correcta,
        indice_original=indice_original, pregunta_id=pregunta_id,
    )


def _respuesta(pregunta_id=1, opcion_id=101, indice_presentado=0, es_correcta=True, mapa=None):
    return SimpleNamespace(
        id=1,
        pregunta_id=pregunta_id,
        opcion_elegida_id=opcion_id,
        indice_opcion_presentada=indice_presentado,
        es_correcta=es_correcta,
        mapa_opciones_json=json.dumps(mapa) if mapa else None,
    )


# ---------------------------------------------------------------------------
# generar_reporte
# ---------------------------------------------------------------------------

class TestGenerarReporte:
    def test_intento_no_encontrado(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="no encontrado"):
            svc.generar_reporte(db, 999)

    def test_intento_no_entregado(self):
        db = MagicMock()
        intento = _intento(fecha_fin=None)
        db.query.return_value.filter.return_value.first.return_value = intento
        with pytest.raises(ValueError, match="no ha sido entregado"):
            svc.generar_reporte(db, 10)

    def test_reporte_shape_happy_path(self):
        """generar_reporte retorna la estructura ReporteIntento correcta."""
        db = MagicMock()
        intento = _intento(fecha_fin=datetime(2026, 6, 27, 11, 0, tzinfo=timezone.utc))
        asig = _asig()
        examen = _examen()
        pregunta = _pregunta(1)
        opcion_elegida = _opcion(101, "Opcion A", es_correcta=True, indice_original=0)
        opcion_correcta = _opcion(101, "Opcion A", es_correcta=True, indice_original=0)
        respuesta = _respuesta(pregunta_id=1, opcion_id=101, es_correcta=True)

        db.query.side_effect = [
            FakeQuery(first_result=intento),        # IntentoExamen
            FakeQuery(first_result=asig),            # AsignacionExamen
            FakeQuery(first_result=examen),          # Examen
            FakeQuery(all_result=[respuesta]),        # IntentoRespuesta (list)
            FakeQuery(all_result=[pregunta]),         # Pregunta.count() → 1
            FakeQuery(first_result=pregunta),        # Pregunta (per-respuesta)
            FakeQuery(first_result=opcion_elegida),  # opcion elegida
            FakeQuery(first_result=opcion_correcta), # opcion correcta
        ]

        result = svc.generar_reporte(db, 10)

        assert result["intento_id"] == 10
        assert result["examen_nombre"] == "Examen Test"
        assert result["producto"] == "Producto X"
        assert result["nota_minima"] == 70
        assert result["total"] == 1
        assert result["correctas"] == 1
        assert result["aprobado"] is True
        assert len(result["respuestas"]) == 1
        r = result["respuestas"][0]
        assert r["es_correcta"] is True
        assert r["texto_elegido"] == "Opcion A"
        assert r["texto_correcto"] == "Opcion A"
        # Correcta debe estar presente — esto es un reporte post-entrega (RN-07)
        assert "texto_correcto" in r

    def test_reporte_no_expone_correcta_como_campo_booleano_separado(self):
        """El reporte SÍ expone texto_correcto (RN-07 feedback), pero via texto, no via
        es_correcta de opcion (ese es el campo de la respuesta del evaluado)."""
        db = MagicMock()
        intento = _intento(fecha_fin=datetime(2026, 6, 27, 11, 0, tzinfo=timezone.utc))
        asig = _asig()
        examen = _examen()
        pregunta = _pregunta(1)
        opcion_correcta = _opcion(101, "La respuesta correcta", es_correcta=True)
        opcion_elegida = _opcion(102, "Respuesta incorrecta", es_correcta=False)
        respuesta = _respuesta(pregunta_id=1, opcion_id=102, es_correcta=False)

        db.query.side_effect = [
            FakeQuery(first_result=intento),
            FakeQuery(first_result=asig),
            FakeQuery(first_result=examen),
            FakeQuery(all_result=[respuesta]),
            FakeQuery(all_result=[pregunta]),         # count=1
            FakeQuery(first_result=pregunta),
            FakeQuery(first_result=opcion_elegida),
            FakeQuery(first_result=opcion_correcta),
        ]

        result = svc.generar_reporte(db, 10)
        r = result["respuestas"][0]

        assert r["es_correcta"] is False
        assert r["texto_correcto"] == "La respuesta correcta"
        assert r["texto_elegido"] == "Respuesta incorrecta"
        assert result["correctas"] == 0


# ---------------------------------------------------------------------------
# _resolver_evaluado (via router helper — tested as pure function)
# ---------------------------------------------------------------------------

class TestResolverEvaluado:
    """Tests para el helper _resolver_evaluado del router (importado directamente)."""

    def _call(self, current_user):
        from app.api.v1.routers.examenes import _resolver_evaluado
        from fastapi import HTTPException
        return _resolver_evaluado(current_user)

    def test_resuelve_rm(self):
        user = SimpleNamespace(rm_id=42, gerente_id=None)
        tipo, eid = self._call(user)
        assert tipo == "RM"
        assert eid == 42

    def test_resuelve_gerente_cuando_no_tiene_rm_id(self):
        user = SimpleNamespace(rm_id=None, gerente_id=7)
        tipo, eid = self._call(user)
        assert tipo == "GERENTE"
        assert eid == 7

    def test_prioriza_rm_sobre_gerente(self):
        """Si el usuario tiene ambos (inusual), RM tiene precedencia."""
        user = SimpleNamespace(rm_id=3, gerente_id=9)
        tipo, eid = self._call(user)
        assert tipo == "RM"
        assert eid == 3

    def test_403_si_ninguno(self):
        from fastapi import HTTPException
        user = SimpleNamespace(rm_id=None, gerente_id=None)
        with pytest.raises(HTTPException) as exc:
            self._call(user)
        assert exc.value.status_code == 403

    def test_403_si_sin_atributos(self):
        from fastapi import HTTPException
        user = SimpleNamespace()  # sin rm_id ni gerente_id
        with pytest.raises(HTTPException) as exc:
            self._call(user)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# listar_pendientes
# ---------------------------------------------------------------------------

class TestListarPendientes:
    def test_filtra_por_rm(self):
        db = MagicMock()
        asig = _asig(rm_id=5)
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = [asig]
        resultado = svc.listar_pendientes(db, "RM", 5)
        assert resultado == [asig]

    def test_filtra_por_gerente(self):
        db = MagicMock()
        asig = _asig(rm_id=None, gerente_id=8)
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = [asig]
        resultado = svc.listar_pendientes(db, "GERENTE", 8)
        assert resultado == [asig]

    def test_devuelve_lista_vacia_si_sin_pendientes(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = []
        resultado = svc.listar_pendientes(db, "RM", 99)
        assert resultado == []


# ---------------------------------------------------------------------------
# _reconstruir_mapa_opcion
# ---------------------------------------------------------------------------

class TestReconstruirMapaOpcion:
    def test_usa_mapa_persistido(self):
        """Si el intento tiene mapa_presentacion_json, lo usa directamente."""
        mapa = {"1": {"0": {"opcion_id": 201, "indice_original": 2}}}
        intento = SimpleNamespace(
            id=10, mapa_presentacion_json=json.dumps(mapa)
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = intento

        opcion_id, ind_pres, ind_orig = svc._reconstruir_mapa_opcion(db, 10, 1, 0)
        assert opcion_id == 201
        assert ind_pres == 0
        assert ind_orig == 2

    def test_fallback_sin_mapa(self):
        """Sin mapa, busca por indice_original == indice_presentado."""
        intento = SimpleNamespace(id=10, mapa_presentacion_json=None)
        opcion = SimpleNamespace(id=301, indice_original=1)

        db = MagicMock()
        db.query.side_effect = [
            FakeQuery(first_result=intento),
            FakeQuery(first_result=opcion),
        ]

        opcion_id, ind_pres, ind_orig = svc._reconstruir_mapa_opcion(db, 10, 1, 1)
        assert opcion_id == 301
        assert ind_pres == 1
        assert ind_orig == 1

    def test_fallback_indice_invalido_lanza_error(self):
        """Si el indice no existe ni en mapa ni en DB → ValueError."""
        intento = SimpleNamespace(id=10, mapa_presentacion_json=None)
        db = MagicMock()
        db.query.side_effect = [
            FakeQuery(first_result=intento),
            FakeQuery(first_result=None),   # opcion no encontrada
        ]
        with pytest.raises(ValueError, match="no válido"):
            svc._reconstruir_mapa_opcion(db, 10, 1, 99)

    def test_intento_no_encontrado_lanza_error(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="no encontrado"):
            svc._reconstruir_mapa_opcion(db, 999, 1, 0)


# ---------------------------------------------------------------------------
# iniciar_para_evaluado — scope enforcement
# ---------------------------------------------------------------------------

class TestIniciarParaEvaluado:
    def test_403_si_sin_asignacion(self):
        """PermissionError si no hay asignación pendiente para el evaluado en ese examen."""
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        with pytest.raises(PermissionError):
            svc.iniciar_para_evaluado(db, examen_id=7, evaluado_tipo="RM",
                                       evaluado_id=99, contexto={})
