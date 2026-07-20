# -*- coding: utf-8 -*-
r"""Qué cuenta como carácter especial en la política de contraseñas.

Regresión jul-2026: la lista era fija ("!@#$%^&*()_+-=[]{};:,.<>?/|~") y dejaba fuera
símbolos muy a mano en teclados móviles en español. Un usuario que ponía `Clave2026¿`
veía la regla sin marcar y el botón "Cambiar contraseña" NUNCA se habilitaba.
El frontend usa /[^\p{L}\p{N}\s]/u — este test fija la misma semántica en el backend.
"""
import pytest

from app.services.password_policy_service import es_especial


@pytest.mark.parametrize("c", ["!", "@", "#", "$", "%", "&", "*", "-", "_",
                               "¿", "¡", "'", '"', "`", "\\", "€", "+", "="])
def test_simbolos_cuentan_como_especial(c):
    assert es_especial(c) is True


@pytest.mark.parametrize("c", ["a", "Z", "5", "ñ", "Ñ", "á", "É", "ü", " "])
def test_letras_digitos_y_espacio_no_son_especiales(c):
    """Los acentos y la ñ son LETRAS: no deben servir para cumplir el requisito."""
    assert es_especial(c) is False


def test_password_con_simbolo_de_teclado_movil_es_valida(monkeypatch):
    """Caso real que fallaba: contraseña con `¿` era rechazada."""
    from app.services import password_policy_service as svc
    monkeypatch.setattr(svc, "min_longitud", lambda db, rol: 8)
    svc.validar_complejidad(None, "Clave2026¿", "REPRESENTANTE_MEDICO")   # no debe lanzar


def test_password_sin_ningun_simbolo_sigue_siendo_rechazada(monkeypatch):
    from app.services import password_policy_service as svc
    monkeypatch.setattr(svc, "min_longitud", lambda db, rol: 8)
    with pytest.raises(ValueError):
        svc.validar_complejidad(None, "Clave2026ñ", "REPRESENTANTE_MEDICO")
