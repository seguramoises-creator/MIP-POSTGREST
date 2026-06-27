import pytest
from app.services import examen_ia_service as ia


def _q(**kw):
    base = {"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d"],
            "correcta": 1, "explicacion": "porque"}
    base.update(kw)
    return base


def test_validar_ok():
    out = ia.validar_preguntas_generadas([_q(), _q(tipo="caso", escenario="esc")])
    assert len(out) == 2


def test_validar_opciones_distintas_de_4_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(opciones=["a", "b", "c"])])


def test_validar_correcta_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(correcta=5)])


def test_validar_caso_sin_escenario_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(tipo="caso")])


def test_validar_correcta_booleano_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(correcta=True)])


def test_validar_no_lista_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas("no soy lista")
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([])


def test_extraer_texto_docx(tmp_path):
    from docx import Document
    doc = Document()
    doc.add_paragraph("Paracetamol reduce la fiebre.")
    p = tmp_path / "fuente.docx"
    doc.save(str(p))
    texto = ia.extraer_texto_fuente(str(p), "docx")
    assert "Paracetamol" in texto


def test_extraer_texto_plano(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("Contenido de prueba", encoding="utf-8")
    assert "prueba" in ia.extraer_texto_fuente(str(p), "texto")


def test_extraer_tipo_no_soportado_falla(tmp_path):
    with pytest.raises(ValueError):
        ia.extraer_texto_fuente("x", "rtf")


# ── Tests Fase 3 — generación con cliente inyectable ─────────────────────────
import json as _json
from unittest.mock import MagicMock


def _mock_client(payload):
    client = MagicMock()
    msg = MagicMock()
    bloque = MagicMock()
    bloque.text = _json.dumps(payload)
    msg.content = [bloque]
    client.messages.create.return_value = msg
    return client


def test_generar_preguntas_ia_parsea_y_valida():
    payload = [{"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d"],
                "correcta": 0, "explicacion": "e"}]
    client = _mock_client(payload)
    out = ia.generar_preguntas_ia("texto fuente", n_multi=1, n_casos=0, client=client)
    assert len(out) == 1 and out[0]["correcta"] == 0
    assert client.messages.create.called


def test_generar_preguntas_ia_json_invalido_falla():
    client = MagicMock()
    msg = MagicMock()
    bloque = MagicMock()
    bloque.text = "no soy json"
    msg.content = [bloque]
    client.messages.create.return_value = msg
    with pytest.raises(ValueError):
        ia.generar_preguntas_ia("t", 1, 0, client=client)
