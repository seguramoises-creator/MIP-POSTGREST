"""
Prueba SOLO LECTURA de la formula PROPUESTA para Ranking Regional/Anual (NO
implementada todavia en iup_service.py -- este script no modifica nada, solo
calcula con datos reales para validar antes de aplicar el cambio de verdad).

Formula propuesta:
    kpi_score    = SUM(puntos_obtenidos * ponderacion_pct) / SUM(ponderacion_pct)
                   -- exactamente la misma formula que ya usa el Ranking Mensual
                   real (motor_calculo_service.generar_ranking), sobre los 8 KPIs
                   reales (Gestion + Resultados juntos, ponderados por "Peso (pts)").
    consistencia = promedio de FACT_ScoreIntegralRM.score_total de hasta los 3
                   ciclos previos mas recientes (excluyendo el actual) -- igual
                   que ya calcula iup_service._get_puntaje_consistencia hoy.
    score_final  = kpi_score * (1 - peso_consistencia) + consistencia * peso_consistencia
                   peso_consistencia = 0.15 (el mismo valor ya configurado en BD).

Reemplaza por completo Comercial/Coaching/Capacitacion (que siempre dan 0 en
datos reales, ver verificar_tablas_legacy_comercial.py).

Uso:
    docker compose exec backend python scripts/diagnostics/probar_formula_propuesta.py DO C01-2026 C02-2026 C03-2026
"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.database import SessionLocal
from app.models.dimensiones import Ciclo, RepresentanteMedico, Indicador
from app.models.hechos import ResultadoIndicador, ScoreIntegralRM
from app.services.iup_service import _obtener_pesos

PESO_CONSISTENCIA_DEFAULT = Decimal("0.15")


def kpi_score(db, rm_id, pais_codigo, ciclo_id):
    """Misma formula que motor_calculo_service.generar_ranking (Mensual real)."""
    filas = (
        db.query(ResultadoIndicador, Indicador)
        .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
        .filter(
            ResultadoIndicador.rm_id == rm_id,
            ResultadoIndicador.pais_codigo == pais_codigo,
            ResultadoIndicador.ciclo_id == ciclo_id,
            ResultadoIndicador.activo == True,  # noqa: E712
            ResultadoIndicador.puntos_obtenidos.isnot(None),
        )
        .all()
    )
    if not filas:
        return None
    puntos = Decimal(0)
    pond = Decimal(0)
    for ri, ind in filas:
        puntos += Decimal(str(ri.puntos_obtenidos or 0))
        pond += Decimal(str(ind.ponderacion_pct or 0))
    if pond == 0:
        return None
    return (puntos * Decimal(100) / pond)


def consistencia_hasta(db, rm_id, pais_codigo, ciclo_orden_actual, ordenes_por_id, ciclos_ids_previos):
    """Promedio de score_total de FACT_ScoreIntegralRM en los ciclos previos dados."""
    if not ciclos_ids_previos:
        return Decimal(0)
    rows = (
        db.query(ScoreIntegralRM.score_total, ScoreIntegralRM.ciclo_id)
        .filter(
            ScoreIntegralRM.rm_id == rm_id,
            ScoreIntegralRM.pais_codigo == pais_codigo,
            ScoreIntegralRM.ciclo_id.in_(ciclos_ids_previos),
        )
        .all()
    )
    if not rows:
        return Decimal(0)
    vals = [Decimal(str(r.score_total or 0)) for r in rows]
    return sum(vals) / Decimal(len(vals))


def main():
    if len(sys.argv) < 3:
        print("Uso: probar_formula_propuesta.py <PAIS_CODIGO> <NOMBRE_CICLO_1> [NOMBRE_CICLO_2 ...]")
        sys.exit(1)

    pais_codigo = sys.argv[1].upper()
    nombres_ciclos = sys.argv[2:]

    db = SessionLocal()
    try:
        pesos = _obtener_pesos(db)
        peso_cons = pesos.get("CONSISTENCIA", PESO_CONSISTENCIA_DEFAULT)
        print(f"Peso de Consistencia vigente: {peso_cons}  (KPIs se llevan el resto: {Decimal(1) - peso_cons})")
        print()

        ciclos = []
        for nombre in nombres_ciclos:
            c = (
                db.query(Ciclo)
                .filter(Ciclo.pais_codigo == pais_codigo)
                .filter((Ciclo.nombre == nombre) | (Ciclo.nombre_canonico == nombre))
                .first()
            )
            if not c:
                print(f"AVISO: no se encontro el ciclo '{nombre}' para {pais_codigo}, se omite.")
                continue
            ciclos.append(c)
        ciclos.sort(key=lambda c: (c.anio, c.numero))

        if not ciclos:
            print("Ningun ciclo valido.")
            sys.exit(1)

        rms = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.pais_codigo == pais_codigo, RepresentanteMedico.activo == True  # noqa: E712
        ).all()

        for i, ciclo in enumerate(ciclos):
            previos = [c.id for c in ciclos[:i]][-3:]  # hasta 3 ciclos previos de ESTA lista
            print(f"=== {ciclo.nombre} (id={ciclo.id}) — ciclos previos considerados: "
                  f"{[c.nombre for c in ciclos[:i]][-3:] or 'ninguno'} ===")
            filas_mostradas = 0
            for rm in rms:
                ks = kpi_score(db, rm.id, pais_codigo, ciclo.id)
                if ks is None:
                    continue  # sin datos de KPI este ciclo para este RM
                cons = consistencia_hasta(db, rm.id, pais_codigo, ciclo.numero, {}, previos)
                score_final = ks * (Decimal(1) - peso_cons) + cons * peso_cons
                score_final = max(Decimal(0), min(score_final, Decimal(100)))
                print(f"  {rm.nombre:<35} kpi_score={float(ks):>7.2f}  consistencia={float(cons):>7.2f}  "
                      f"-> SCORE PROPUESTO={float(score_final):>7.2f}")
                filas_mostradas += 1
            if filas_mostradas == 0:
                print("  (ningun RM con datos de KPI en este ciclo)")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
