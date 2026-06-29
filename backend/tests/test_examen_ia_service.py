import pytest
from app.services import examen_ia_service as ia


def _q(**kw):
    base = {"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d", "e"],
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


def test_validar_vf_ok_con_2_opciones():
    out = ia.validar_preguntas_generadas([_q(tipo="vf", opciones=["Verdadero", "Falso"], correcta=0)])
    assert out[0]["tipo"] == "vf" and len(out[0]["opciones"]) == 2


def test_validar_vf_con_4_opciones_falla():
    # un vf DEBE tener exactamente 2 opciones
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(tipo="vf", opciones=["a", "b", "c", "d"], correcta=0)])


def test_validar_vf_correcta_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(tipo="vf", opciones=["Verdadero", "Falso"], correcta=2)])


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
    payload = [{"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d", "e"],
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


# ── Tests Fase 3 — persistencia de preguntas ────────────────────────────────

def test_persistir_preguntas_marca_correcta(monkeypatch):
    db = MagicMock()
    agregados = []
    db.add.side_effect = lambda obj: agregados.append(obj)
    # Patch the query for existing count to return 0
    db.query.return_value.filter.return_value.count.return_value = 0
    n = ia.persistir_preguntas(db, examen_id=1, preguntas=[
        {"tipo": "multi", "texto": "¿?", "escenario": None,
         "opciones": ["a", "b", "c", "d"], "correcta": 2, "explicacion": "e"}])
    assert n == 1
    # PreguntaOpcion objects are attached to pregunta.opciones (not added to db directly)
    # Collect all opciones from all preguntas that were added
    from app.models.exam_models import Pregunta
    preguntas_agregadas = [o for o in agregados if isinstance(o, Pregunta)]
    assert len(preguntas_agregadas) == 1
    opciones = preguntas_agregadas[0].opciones
    # la opción en índice 2 es la correcta
    assert any(getattr(o, "es_correcta", False) and o.indice_original == 2 for o in opciones)


# ── Tests Fase 3 Fix — magic bytes IA + JSON robusto ────────────────────────

from app.api.v1.routers.examenes import _validar_magic_bytes_ia


class TestMagicBytesIA:
    """Regression locks for the IA-specific magic-byte validator.

    The critical security case is the INVERTED check: an Excel/ZIP file
    renamed to .pdf must be REJECTED (this is the bug that existed before
    the fix — the old ETL validator accepted it).
    """

    def test_pdf_valido(self):
        content = b"%PDF-1.7 blah blah"
        assert _validar_magic_bytes_ia(content, ".pdf") is True

    def test_docx_valido(self):
        content = b"PK\x03\x04 fake ooxml content"
        assert _validar_magic_bytes_ia(content, ".docx") is True

    def test_pptx_valido(self):
        content = b"PK\x03\x04 fake pptx content"
        assert _validar_magic_bytes_ia(content, ".pptx") is True

    def test_txt_valido(self):
        content = b"hola mundo, esto es texto plano"
        assert _validar_magic_bytes_ia(content, ".txt") is True

    def test_txt_con_nul_rechazado(self):
        # A binary file renamed to .txt should be rejected (NUL in first 1024 bytes)
        content = b"PK\x03\x04\x00\x00binary data"
        assert _validar_magic_bytes_ia(content, ".txt") is False

    def test_zip_renombrado_pdf_rechazado(self):
        # CRITICAL: Excel/ZIP magic bytes with .pdf extension must be REJECTED
        content = b"PK\x03\x04 this is an xlsx renamed to pdf"
        assert _validar_magic_bytes_ia(content, ".pdf") is False

    def test_ole2_renombrado_pdf_rechazado(self):
        # OLE2 (legacy .xls) renamed to .pdf must be REJECTED
        content = b"\xd0\xcf\x11\xe0 legacy xls data"
        assert _validar_magic_bytes_ia(content, ".pdf") is False

    def test_extension_desconocida_rechazada(self):
        content = b"PK\x03\x04 whatever"
        assert _validar_magic_bytes_ia(content, ".rtf") is False


class TestExtraerJsonRobusto:
    """Regression locks for the robust _extraer_json implementation."""

    def test_fenced_json(self):
        respuesta = '```json\n[{"tipo": "multi"}]\n```'
        data = ia._extraer_json(respuesta)
        assert isinstance(data, list) and data[0]["tipo"] == "multi"

    def test_fenced_sin_lang(self):
        respuesta = '```\n[{"tipo": "caso"}]\n```'
        data = ia._extraer_json(respuesta)
        assert data[0]["tipo"] == "caso"

    def test_bare_array(self):
        respuesta = 'Aquí están las preguntas:\n[{"tipo": "multi"}]\nFin.'
        data = ia._extraer_json(respuesta)
        assert isinstance(data, list)

    def test_bare_object(self):
        respuesta = 'Resultado: {"tipo": "multi"}'
        data = ia._extraer_json(respuesta)
        assert data["tipo"] == "multi"

    def test_texto_invalido_lanza_valueerror(self):
        with pytest.raises(ValueError):
            ia._extraer_json("esto no es JSON ni array ni nada válido")
