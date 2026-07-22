def test_modelos_farmacia_importan_y_tienen_columnas_clave():
    from app.models.dimensiones import Farmacia
    from app.models.visita import FarmaciaVisita, FactVisitaFarmacia
    # Maestro: bloqueantes NOT NULL + cadena/sucursal + estado
    cols = Farmacia.__table__.columns
    assert cols["direccion"].nullable is False   # F23
    assert cols["encargado"].nullable is False   # F24
    assert "cadena" in cols and "sucursal" in cols and "nombre_completo" in cols
    assert cols["estado"].default.arg == "PENDIENTE_APROBACION"
    # Panel referencia al maestro (F19)
    assert "maestro_farmacia_id" in FarmaciaVisita.__table__.columns
    # Registro paralelo con FK a farmacia (Opción A)
    assert "farmacia_id" in FactVisitaFarmacia.__table__.columns
