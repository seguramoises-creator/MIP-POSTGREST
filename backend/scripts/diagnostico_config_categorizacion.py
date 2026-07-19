"""
Diagnóstico (SOLO LECTURA): ¿está configurado el motor de categorización (esquema cat.*)?

El alta de un médico con plantilla (Bloque B) calcula su categoría con las reglas de
`cat.DimReglaCategoriaMedica` + `cat.DimClasificacionMedica`. Si un país no las tiene
cargadas, TODO médico nuevo saldría como PENDIENTE (sin categoría). Este script
reporta, por país:

  - componentes activos (y cuáles son REQUERIDOS)
  - reglas vigentes por componente
  - bandas de clasificación (A/B/C/D) vigentes
  - PRUEBA EN VIVO: corre el motor con un médico de ejemplo y muestra qué devuelve

No escribe nada. Uso (dentro del contenedor):
  docker compose exec -e PYTHONPATH=/app backend python scripts/diagnostico_config_categorizacion.py
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services import categorizacion_service as cat

def _ejemplo_del_pais(db, pais_key) -> dict:
    """Arma el médico de ejemplo TOMANDO LOS VALORES DE LAS PROPIAS REGLAS del país.

    Cada criterio tiene su vocabulario cerrado (p. ej. POTENCIAL_PRESCRIPCION usa
    '10 o Mas'/'6 a 9'/…, KOL usa 'Charlista Internacional'/'Ninguno'/…). Inventar
    valores daría un falso PENDIENTE, así que se elige la regla de mayor puntaje de
    cada componente y se usa su texto (o un valor dentro de su rango numérico)."""
    filas = db.execute(text('''
        SELECT c."CodigoComponente", r."ValorMinimo", r."ValorMaximo", r."ValorTexto", r."PuntajePct"
        FROM "cat"."DimReglaCategoriaMedica" r
        JOIN "cat"."DimComponenteCategoria" c ON c."ComponenteKey" = r."ComponenteKey"
        WHERE r."PaisKey" = :pk AND r."Activo" = TRUE
        ORDER BY c."CodigoComponente", r."PuntajePct" DESC'''), {"pk": pais_key}).all()
    mejor_por_comp = {}
    for codigo, vmin, vmax, vtxt, _pct in filas:
        mejor_por_comp.setdefault(codigo, (vmin, vmax, vtxt))   # la 1ª es la de mayor puntaje
    ejemplo = {}
    for codigo, (vmin, vmax, vtxt) in mejor_por_comp.items():
        campo = cat._COMP_NUM.get(codigo) or cat._COMP_TXT.get(codigo)
        if not campo:
            continue
        ejemplo[campo] = vtxt if vtxt is not None else (vmin if vmin is not None else vmax)
    return ejemplo


def main() -> None:
    db = SessionLocal()
    try:
        paises = db.execute(text('SELECT "PaisKey", "CodigoPais" FROM "cat"."DimPais" ORDER BY "CodigoPais"')).all()
        if not paises:
            print("!! cat.DimPais VACÍO — el motor de categorización no está configurado para ningún país.")
            print("   Todo médico nuevo saldría PENDIENTE (sin categoría).")
            return

        comps = db.execute(text('SELECT "ComponenteKey", "CodigoComponente", "Requerido" '
                                'FROM "cat"."DimComponenteCategoria" WHERE "Activo"=TRUE '
                                'ORDER BY "CodigoComponente"')).mappings().all()
        req = [c["CodigoComponente"] for c in comps if c["Requerido"]]
        print(f"COMPONENTES activos: {len(comps)}  |  REQUERIDOS: {len(req)} -> {', '.join(req) or '(ninguno)'}")
        if not comps:
            print("!! Sin componentes activos: el motor no puede puntuar nada.")

        print("-" * 78)
        print(f"{'PAIS':<6} {'REGLAS':>7} {'CLASES':>7}  PRUEBA EN VIVO (médico de ejemplo)")
        print("-" * 78)
        for pais_key, codigo in paises:
            n_reglas = db.execute(text('SELECT COUNT(*) FROM "cat"."DimReglaCategoriaMedica" '
                                       'WHERE "Activo"=TRUE AND "PaisKey"=:pk'), {"pk": pais_key}).scalar()
            n_clases = db.execute(text('SELECT COUNT(*) FROM "cat"."DimClasificacionMedica" '
                                       'WHERE "Activo"=TRUE AND "PaisKey"=:pk'), {"pk": pais_key}).scalar()
            ejemplo = _ejemplo_del_pais(db, pais_key)
            r = cat.calcular_categoria_de_valores(db, codigo, ejemplo)
            pct = float(r["puntaje_pct"] or 0) * 100     # la escala interna es fracción 0-1
            if r["estado"] == "CALCULADO" and r["categoria"]:
                veredicto = f"OK -> categoria {r['categoria']} (puntaje {pct:.0f}%)"
            else:
                faltan = [d["componente"] for d in r["detalle"] if d["estado"] == "SIN_REGLA"]
                veredicto = f"PENDIENTE (puntaje {pct:.0f}%)"
                if faltan:
                    veredicto += f" — sin regla: {', '.join(faltan)}"
                elif not n_clases:
                    veredicto += " — sin bandas de clasificación (A/B/C/D)"
            print(f"{codigo:<6} {n_reglas:>7} {n_clases:>7}  {veredicto}")

        print("-" * 78)
        print("Lectura: un país con 'OK -> categoria X' ya puede clasificar médicos nuevos.")
        print("         'PENDIENTE' = falta cargar reglas/bandas para ese país; el alta")
        print("         guardaria los valores pero sin categoria hasta configurarlo.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
