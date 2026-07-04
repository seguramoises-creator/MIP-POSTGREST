"""Caracterización: el motor Python produce EXACTAMENTE lo mismo que los SPs DW.*.

Requiere BD SQL Server local con datos sembrados y los SPs presentes (aún no dropeados).
Se salta solo si no hay BD.
"""
import pytest
from sqlalchemy import text

from app.db.database import SessionLocal, check_db_connection

pytestmark = pytest.mark.skipif(not check_db_connection(), reason="sin BD local")


def _snap_ranking(db, ciclo_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT rm_id, CAST(score_total AS DECIMAL(10,4)), posicion_global, posicion_linea, "
        "CAST(elegible AS INT), ISNULL(categoria_id,-1), ISNULL(posicion_anterior,-1) "
        "FROM DW.FACT_RankingRM WHERE ciclo_id=:c AND tipo_ranking='MENSUAL' ORDER BY rm_id"),
        {"c": ciclo_id}).all()]


def _snap_score(db, ciclo_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT rm_id, CAST(score_total AS DECIMAL(10,4)), ISNULL(categoria_id,-1), "
        "CAST(elegible_reconocimiento AS INT) FROM DW.FACT_ScoreIntegralRM "
        "WHERE ciclo_id=:c ORDER BY rm_id"), {"c": ciclo_id}).all()]


def _snap_puntos(db, ciclo_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT id, CAST(resultado_porcentaje AS DECIMAL(18,6)), CAST(puntos_obtenidos AS DECIMAL(18,6)) "
        "FROM DW.FACT_ResultadoIndicador WHERE ciclo_id=:c AND activo=1 ORDER BY id"),
        {"c": ciclo_id}).all()]


def _ciclos_abiertos_con_datos(db):
    return [r[0] for r in db.execute(text(
        "SELECT DISTINCT ri.ciclo_id FROM DW.FACT_ResultadoIndicador ri "
        "JOIN Config.DIM_Ciclo c ON c.id=ri.ciclo_id "
        "WHERE ri.activo=1 AND ri.resultado_real IS NOT NULL AND c.cerrado=0")).all()]


def _sp_existe(db):
    return db.execute(text(
        "SELECT COUNT(*) FROM sys.sql_modules WHERE object_id=OBJECT_ID('DW.sp_RecalcularCiclo')")).scalar() > 0


def test_motor_dw_equivale_al_sp():
    from app.services import motor_calculo_service as mc
    db = SessionLocal()
    try:
        if not _sp_existe(db):
            pytest.skip("SPs ya dropeados — caracterización no aplica")
        ciclos = _ciclos_abiertos_con_datos(db)
        if not ciclos:
            pytest.skip("sin datos sembrados en FACT_ResultadoIndicador (ciclo abierto)")
        comparados = 0
        for ciclo_id in ciclos[:5]:
            # 1) SP -> golden
            db.execute(text("EXEC DW.sp_RecalcularCiclo @ciclo_id=:c, @pais_codigo=NULL"), {"c": ciclo_id})
            db.commit()
            g_rank, g_score, g_pts = _snap_ranking(db, ciclo_id), _snap_score(db, ciclo_id), _snap_puntos(db, ciclo_id)
            # 2) Python -> sobrescribe
            mc.recalcular_ciclo_py(db, ciclo_id, None)
            p_rank, p_score, p_pts = _snap_ranking(db, ciclo_id), _snap_score(db, ciclo_id), _snap_puntos(db, ciclo_id)
            assert p_pts == g_pts, f"puntos difieren en ciclo {ciclo_id}"
            assert p_score == g_score, f"score integral difiere en ciclo {ciclo_id}"
            assert p_rank == g_rank, f"ranking difiere en ciclo {ciclo_id}"
            comparados += 1
        assert comparados > 0
    finally:
        db.close()
