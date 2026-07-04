"""Caracterización: calcular_cobertura_py == cat.sp_CalcularCoberturaPredictiva.

Compara cat.KpiCoberturaPredictiva por RepresentanteKey (columnas de negocio, no la
clave surrogate). Fecha de corte fija a mitad de ciclo para ejercitar la proyección.
Requiere BD local con datos y el SP presente.
"""
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.db.database import SessionLocal, check_db_connection

pytestmark = pytest.mark.skipif(not check_db_connection(), reason="sin BD local")


def _snap(db, ciclo_key, fecha_corte):
    return [tuple(r) for r in db.execute(text(
        "SELECT RepresentanteKey, MedicosProgramados, MedicosVisitadosUnicos, "
        "CAST(CoberturaActualPct AS DECIMAL(9,6)), CAST(CoberturaEsperadaPct AS DECIMAL(9,6)), "
        "CAST(CoberturaProyectadaPct AS DECIMAL(9,6)), CAST(BrechaActualVsEsperada AS DECIMAL(9,6)), "
        "CAST(BrechaProyectadaVsMeta AS DECIMAL(9,6)), MedicosRequeridosMeta, MedicosPendientesMeta, "
        "MedicosDiariosRequeridos, ContactosRealizados, CAST(CumplimientoContactosPct AS DECIMAL(9,6)), "
        "CAST(ContactosProyectados AS DECIMAL(12,4)), CAST(ContactosPendientes AS DECIMAL(12,4)), "
        "ContactosDiariosRequeridos, DiasHabilesTotales, DiasHabilesTranscurridos, DiasHabilesRestantes, "
        "EstadoCobertura, EstadoRitmo, EstadoPSP, ISNULL(LecturaAccionable,'') "
        "FROM cat.KpiCoberturaPredictiva WHERE CicloKey=:ck AND FechaCorte=:fc ORDER BY RepresentanteKey"),
        {"ck": ciclo_key, "fc": fecha_corte}).all()]


def test_cobertura_equivale_al_sp():
    from app.services import cobertura_predictiva_service as cps
    db = SessionLocal()
    try:
        if db.execute(text("SELECT COUNT(*) FROM sys.sql_modules WHERE object_id=OBJECT_ID('cat.sp_CalcularCoberturaPredictiva')")).scalar() == 0:
            pytest.skip("SP ya dropeado")
        c = db.execute(text("SELECT TOP 1 c.CodigoCiclo, p.CodigoPais, c.CicloKey, c.FechaInicio, c.FechaFin "
                            "FROM cat.DimCiclo c JOIN cat.DimPais p ON p.PaisKey=c.PaisKey WHERE c.Activo=1 ORDER BY c.CicloKey")).mappings().first()
        if c is None:
            pytest.skip("sin ciclo en cat.DimCiclo")
        fecha_corte = c["FechaInicio"] + timedelta(days=(c["FechaFin"] - c["FechaInicio"]).days // 2)
        params = {"cc": c["CodigoCiclo"], "cp": c["CodigoPais"], "fc": fecha_corte}

        # 1) SP -> golden
        db.execute(text("DELETE FROM cat.KpiCoberturaPredictiva WHERE CicloKey=:ck AND FechaCorte=:fc"),
                   {"ck": c["CicloKey"], "fc": fecha_corte})
        db.commit()
        db.execute(text("EXEC cat.sp_CalcularCoberturaPredictiva @CodigoCiclo=:cc, @CodigoPais=:cp, @FechaCorte=:fc"), params)
        db.commit()
        golden = _snap(db, c["CicloKey"], fecha_corte)
        assert golden, "el SP no insertó filas — revisar datos"

        # 2) Python -> comparar
        db.execute(text("DELETE FROM cat.KpiCoberturaPredictiva WHERE CicloKey=:ck AND FechaCorte=:fc"),
                   {"ck": c["CicloKey"], "fc": fecha_corte})
        db.commit()
        cps.calcular_cobertura_py(db, c["CodigoCiclo"], c["CodigoPais"], fecha_corte)
        db.commit()
        py = _snap(db, c["CicloKey"], fecha_corte)
        assert len(py) == len(golden), f"filas: py={len(py)} sp={len(golden)}"
        assert py == golden, "cobertura difiere"
    finally:
        db.close()
