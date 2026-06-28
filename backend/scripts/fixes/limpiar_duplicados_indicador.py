# --- bootstrap: permite ejecutar este script desde backend/scripts/<bucket>/ ---
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
# ---------------------------------------------------------------------------
"""
Limpieza de duplicados en DIM_Indicador causados por el bug DO/RD.

Antes del fix en dims.py, _pais_c() no reconciliaba 'DO' (usado en la hoja
DIM_INDICADOR del Excel) con 'RD' (usado en DIM_PAIS). Eso hacía que el
import de DIM_INDICADOR cayera en el fallback "todos los países" y clonara
cada indicador de República Dominicana en los otros 5 países (CR, GT, HN,
PA, VE) en vez de insertarlo solo en RD.

Este script NO toca ningún archivo Excel. Solo opera sobre la base de datos
SCGCPR vía los modelos existentes (app.models).

Uso (desde C:\\Users\\Lenovo\\Proyecto\\MSM\\backend, con el venv activado):

    python limpiar_duplicados_indicador.py            # solo reporta (dry-run)
    python limpiar_duplicados_indicador.py --ejecutar  # reporta y borra los
                                                        # duplicados seguros

Un duplicado se considera "seguro de borrar" solo si:
  1. Tiene el mismo `codigo` que un indicador de RD.
  2. Coincide EXACTAMENTE con el indicador de RD en todos los demás campos
     (nombre, descripcion, rol, modulo, tipo_periodo, ponderacion_pct,
     escala, valor_min, valor_max, formula, peso_iup, unidad, meta_global,
     activo, orden) — es decir, es un clon byte-a-byte, no un indicador
     legítimo y distinto que ese país ya tuviera con el mismo código.
  3. No tiene filas dependientes en DIM_IndicadorTabla, DIM_MetaIndicador
     ni FACT_ResultadoIndicador. Si las tiene, se reporta pero NO se borra
     automáticamente — requiere revisión manual.
"""
import sys

from app.db.database import SessionLocal
from app.models.dimensiones import Pais, Indicador, IndicadorTabla, MetaIndicador
from app.models.hechos import ResultadoIndicador

CAMPOS_COMPARABLES = [
    "nombre", "descripcion", "rol", "modulo", "tipo_periodo",
    "ponderacion_pct", "escala", "valor_min", "valor_max", "formula",
    "peso_iup", "unidad", "meta_global", "activo", "orden",
]


def firma(ind: Indicador) -> tuple:
    return tuple(getattr(ind, c) for c in CAMPOS_COMPARABLES)


def main():
    ejecutar = "--ejecutar" in sys.argv
    db = SessionLocal()

    rd = db.query(Pais).filter(Pais.codigo == "RD").first()
    if not rd:
        print("No se encontró país con codigo='RD'. Abortando.")
        return

    indicadores = db.query(Indicador).all()
    por_codigo: dict[str, list[Indicador]] = {}
    for ind in indicadores:
        por_codigo.setdefault(ind.codigo, []).append(ind)

    paises = {p.id: p.codigo for p in db.query(Pais).all()}

    candidatos_borrar: list[Indicador] = []
    requieren_revision: list[tuple[Indicador, str]] = []

    print(f"Total indicadores en BD: {len(indicadores)}\n")

    for codigo, filas in sorted(por_codigo.items()):
        rd_filas = [f for f in filas if f.pais_id == rd.id]
        otras_filas = [f for f in filas if f.pais_id != rd.id]
        if not rd_filas or not otras_filas:
            continue

        rd_ind = rd_filas[0]
        rd_firma = firma(rd_ind)

        print(f"Código {codigo!r} — RD id={rd_ind.id}, presente también en: "
              f"{[paises.get(f.pais_id) for f in otras_filas]}")

        for f in otras_filas:
            pais_cod = paises.get(f.pais_id, f.pais_id)
            es_clon = firma(f) == rd_firma
            if not es_clon:
                print(f"    [{pais_cod}] id={f.id} — difiere de RD, NO es duplicado del bug. Se deja intacto.")
                continue

            dep_tabla = db.query(IndicadorTabla).filter(IndicadorTabla.indicador_id == f.id).count()
            dep_meta = db.query(MetaIndicador).filter(MetaIndicador.indicador_id == f.id).count()
            dep_resultado = db.query(ResultadoIndicador).filter(ResultadoIndicador.indicador_id == f.id).count()

            if dep_tabla or dep_meta or dep_resultado:
                motivo = (f"tiene dependientes (tabla={dep_tabla}, meta={dep_meta}, "
                          f"resultado={dep_resultado})")
                print(f"    [{pais_cod}] id={f.id} — clon de RD pero {motivo}. Requiere revisión manual.")
                requieren_revision.append((f, motivo))
            else:
                print(f"    [{pais_cod}] id={f.id} — clon de RD, sin dependientes. Candidato a borrar.")
                candidatos_borrar.append(f)

    print(f"\nResumen: {len(candidatos_borrar)} candidatos a borrar, "
          f"{len(requieren_revision)} requieren revisión manual.")

    if not ejecutar:
        print("\nModo reporte (dry-run). Nada fue borrado.")
        print("Para borrar los candidatos seguros, vuelve a correr con --ejecutar")
        db.close()
        return

    if not candidatos_borrar:
        print("\nNo hay candidatos seguros para borrar.")
        db.close()
        return

    for f in candidatos_borrar:
        db.delete(f)
    db.commit()
    print(f"\n{len(candidatos_borrar)} filas duplicadas eliminadas de DIM_Indicador.")
    db.close()


if __name__ == "__main__":
    main()
