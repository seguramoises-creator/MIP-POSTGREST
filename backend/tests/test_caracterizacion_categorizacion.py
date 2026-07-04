"""Caracterización: calcular_categorias_py == cat.sp_CalcularCategoriaMedica.

Compara por columnas de negocio (ordenado por RowNumber), no por la clave surrogate
(MedicoCategoriaKey es identity y difiere entre corridas). Requiere BD local con un
lote sembrado y el SP presente.
"""
import pytest
from sqlalchemy import text

from app.db.database import SessionLocal, check_db_connection

pytestmark = pytest.mark.skipif(not check_db_connection(), reason="sin BD local")


def _clear(db, batch):
    db.execute(text("DELETE d FROM cat.FactMedicoCategoriaDetalle d "
                    "JOIN cat.FactMedicoCategoriaSnapshot f ON f.MedicoCategoriaKey=d.MedicoCategoriaKey "
                    "WHERE f.LoadBatchKey=:b"), {"b": batch})
    db.execute(text("DELETE FROM cat.FactMedicoCategoriaSnapshot WHERE LoadBatchKey=:b"), {"b": batch})
    db.commit()


def _snap(db, batch):
    return [tuple(r) for r in db.execute(text(
        "SELECT RowNumber, ISNULL(MedicoKey,-1), ISNULL(CentroMedicoKey,-1), ISNULL(GeografiaKey,-1), "
        "ISNULL(RepresentanteKey,-1), CAST(PuntajeTotalPct AS DECIMAL(18,4)), ISNULL(ClasificacionKey,-1), "
        "ISNULL(CategoriaCalculada,''), EstadoConciliacion, EstadoCalculo, ISNULL(MensajeCalculo,'') "
        "FROM cat.FactMedicoCategoriaSnapshot WHERE LoadBatchKey=:b ORDER BY RowNumber"), {"b": batch}).all()]


def _detalle(db, batch):
    return [tuple(r) for r in db.execute(text(
        "SELECT f.RowNumber, d.ComponenteKey, ISNULL(d.ReglaKey,-1), ISNULL(d.ValorEntradaTexto,''), "
        "CAST(ISNULL(d.ValorEntradaNumero,-1) AS DECIMAL(18,4)), ISNULL(d.Criterio,''), "
        "CAST(ISNULL(d.PuntajePct,-1) AS DECIMAL(18,4)), d.EstadoComponente "
        "FROM cat.FactMedicoCategoriaDetalle d "
        "JOIN cat.FactMedicoCategoriaSnapshot f ON f.MedicoCategoriaKey=d.MedicoCategoriaKey "
        "WHERE f.LoadBatchKey=:b ORDER BY f.RowNumber, d.ComponenteKey, d.ReglaKey"), {"b": batch}).all()]


def test_categorizacion_equivale_al_sp():
    from app.services import categorizacion_service as cs
    db = SessionLocal()
    try:
        if db.execute(text("SELECT COUNT(*) FROM sys.sql_modules WHERE object_id=OBJECT_ID('cat.sp_CalcularCategoriaMedica')")).scalar() == 0:
            pytest.skip("SP ya dropeado")
        batch = db.execute(text("SELECT TOP 1 LoadBatchKey FROM stg.MedicoCategoriaInput ORDER BY LoadBatchKey DESC")).scalar()
        if batch is None:
            pytest.skip("sin lote sembrado en staging")
        # 1) SP -> golden
        _clear(db, batch)
        db.execute(text("EXEC cat.sp_CalcularCategoriaMedica @LoadBatchKey=:b"), {"b": batch}); db.commit()
        g_snap, g_det = _snap(db, batch), _detalle(db, batch)
        # 2) Python -> comparar
        _clear(db, batch)
        cs.calcular_categorias_py(db, batch); db.commit()
        p_snap, p_det = _snap(db, batch), _detalle(db, batch)
        assert len(p_snap) == len(g_snap) and p_snap == g_snap, "snapshot difiere"
        assert p_det == g_det, "detalle difiere"
    finally:
        db.close()
