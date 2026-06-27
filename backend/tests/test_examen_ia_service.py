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
