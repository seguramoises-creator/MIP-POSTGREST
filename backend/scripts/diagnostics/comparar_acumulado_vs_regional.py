"""
Diagnostico SOLO LECTURA: compara, para un representante, el "TOTAL ACUM" que
se ve en Productividad/Ranking Actual (promedio de su score Mensual a traves
de los ciclos del anio) contra el score que calcula el motor de Regional/
Historico Anual (kpi_score del ciclo actual * 0.85 + consistencia * 0.15).

Sirve para explicar por que ambos numeros, aunque relacionados, no coinciden.

Uso:
    docker compose exec backend python scripts/diagnostics/comparar_acumulado_vs_regional.py DO "BIELKA ESTEVEZ"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from decimal import Decimal

from app.db.database import SessionLocal
from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.models.hechos import RankingRM
from app.services.iup_service import calcular_iup


def main():
    if len(sys.argv) < 3:
        print("Uso: comparar_acumulado_vs_regional.py <PAIS_CODIGO> <NOMBRE_RM>")
        sys.exit(1)

    pais_codigo = sys.argv[1].upper()
    nombre_buscado = sys.argv[2].upper()

    db = SessionLocal()
    try:
        rm = (
            db.query(RepresentanteMedico)
            .filter(RepresentanteMedico.pais_codigo == pais_codigo)
            .filter(RepresentanteMedico.nombre.ilike(f"%{nombre_buscado}%"))
            .first()
        )
        if not rm:
            print(f"No se encontro un representante que coincida con '{nombre_buscado}' en {pais_codigo}.")
            sys.exit(1)

        print(f"Representante: {rm.nombre} (rm_id={rm.id})")
        print()

        # Todos los ciclos MENSUAL con score_total real para este RM, en orden.
        filas = (
            db.query(RankingRM.ciclo_id, RankingRM.score_total, Ciclo.nombre, Ciclo.anio, Ciclo.numero)
            .join(Ciclo, Ciclo.id == RankingRM.ciclo_id)
            .filter(
                RankingRM.rm_id == rm.id,
                RankingRM.pais_codigo == pais_codigo,
                RankingRM.tipo_ranking == "MENSUAL",
            )
            .order_by(Ciclo.anio.asc(), Ciclo.numero.asc())
            .all()
        )

        if not filas:
            print("Este representante no tiene Ranking Mensual calculado en ningun ciclo.")
            sys.exit(1)

        print("=== Score Mensual por ciclo (motor_calculo_service, el que ve en 'Ranking Actual') ===")
        acumulado_por_ciclo = []
        for ciclo_id, score, nombre_ciclo, anio, numero in filas:
            acumulado_por_ciclo.append(Decimal(str(score or 0)))
            promedio_acum = sum(acumulado_por_ciclo) / Decimal(len(acumulado_por_ciclo))
            print(f"  {nombre_ciclo:<12} score_mensual={float(score):>7.2f}   "
                  f"TOTAL ACUM hasta aqui (promedio de {len(acumulado_por_ciclo)} ciclo(s))={float(promedio_acum):>7.2f}")

        print()
        print("=== Score de Regional/Historico Anual por ciclo (iup_service.calcular_iup) ===")
        for ciclo_id, _, nombre_ciclo, anio, numero in filas:
            r = calcular_iup(db, rm_id=rm.id, pais_codigo=pais_codigo, ciclo_id=ciclo_id)
            print(f"  {nombre_ciclo:<12} kpi_score={float(r['iup_kpis']):>7.2f}  "
                  f"consistencia={float(r['iup_consistencia']):>7.2f}  "
                  f"-> SCORE REGIONAL/ANUAL={float(r['score_total']):>7.2f}")

        print()
        print("NOTA: 'TOTAL ACUM' promedia el score Mensual de TODOS los ciclos por igual "
              "(incluye los ciclos mas viejos, aunque el representante haya mejorado despues). "
              "El score de Regional/Anual usa 85% el desempeno del ciclo ACTUAL (kpi_score) + "
              "15% el promedio de los 3 ciclos ANTERIORES (consistencia) -- por eso pesa mas lo "
              "reciente y puede quedar mas alto (o mas bajo) que el promedio acumulado plano.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
