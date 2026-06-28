# -*- coding: utf-8 -*-
"""
diagnostico_recalculo.py
=========================
Diagnostica y corrige por que "Calcular IUP y Ranking" da
"0 KPIs actualizados, 0 rankings generados" a pesar de una carga ETL
exitosa (ej. Job 8: 1027/1027).

CAUSA TIPICA: el procedimiento DW.sp_CompletarPuntajesCiclo solo cuenta
filas de DW.FACT_ResultadoIndicador cuyo (pais_id, ciclo_id) coincide
EXACTO con lo que el usuario elige en pantalla. Si al cargar el Excel
esas filas quedaron grabadas con un pais_id/ciclo_id distinto (tipico
tras un reimport de paises/ciclos), el recalculo siempre da 0 aunque
la carga haya sido 100% exitosa.

USO (PowerShell, desde la carpeta backend):
    cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
    .\\venv\\Scripts\\activate
    python diagnostico_recalculo.py

Que hace, en orden:
  1. Lee la conexion desde backend\\.env (no hay que editar nada).
  2. Revisa si hay paises duplicados con codigo RD/DO.
  3. Ubica el Ciclo 3 2026 correcto para el pais activo.
  4. Compara contra donde quedaron realmente grabadas las filas de los
     RM de ese pais en DW.FACT_ResultadoIndicador.
  5. Si encuentra un mismatch, lo corrige (UPDATE) y vuelve a ejecutar
     DW.sp_RecalcularCiclo para confirmar que ya genera KPIs/rankings.
  6. Si no encuentra mismatch, revisa otras causas (resultado_real NULL,
     activo=0) e imprime un diagnostico para revision manual.

NO modifica ningun archivo Excel. Solo lee/corrige datos en SQL Server.
"""
import os
import sys

try:
    import pymssql
except ImportError:
    print("ERROR: falta el paquete 'pymssql'. Activa el venv del backend:")
    print(r"  cd C:\Users\Lenovo\Proyecto\MSM\backend")
    print(r"  .\venv\Scripts\activate")
    print("  pip install pymssql")
    sys.exit(1)


def leer_env(ruta):
    valores = {}
    if not os.path.exists(ruta):
        return valores
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    env = leer_env(os.path.join(aqui, ".env"))

    server = env.get("DB_SERVER", "127.0.0.1")
    port = env.get("DB_PORT", "1433")
    database = env.get("DB_NAME", "SCGCPR")
    user = env.get("DB_USER", "segura")
    password = env.get("DB_PASSWORD", "")

    print(f"Conectando a {server}:{port}/{database} como {user}...")
    try:
        conn = pymssql.connect(
            server=server, port=str(port), database=database,
            user=user, password=password, as_dict=True,
        )
    except Exception as e:
        print(f"ERROR conectando a SQL Server: {e}")
        sys.exit(1)
    cur = conn.cursor()

    # ── 1. Paises con codigo RD/DO ──────────────────────────────────────
    cur.execute("""
        SELECT id, codigo, nombre, activo
        FROM Config.DIM_Pais
        WHERE UPPER(codigo) IN ('RD', 'DO')
        ORDER BY id
    """)
    paises = cur.fetchall()
    print("\n=== Paises con codigo RD/DO ===")
    for p in paises:
        print(f"  id={p['id']:<5} codigo={p['codigo']:<6} nombre={p['nombre']:<25} activo={p['activo']}")
    if len(paises) > 1:
        print("  *** ALERTA: hay MAS DE UN pais con codigo RD/DO — posible causa raiz. ***")

    if not paises:
        print("ERROR: no se encontro ningun pais con codigo RD/DO. Abortando.")
        conn.close()
        return

    activos = [p for p in paises if p["activo"]] or paises
    pais_rd = activos[0]
    pais_rd_id = pais_rd["id"]
    print(f"  -> Usando pais_id={pais_rd_id} ({pais_rd['codigo']}) como referencia.")

    # ── 2. Ciclo 3 2026 (anio=2026, numero=3) ───────────────────────────
    cur.execute("""
        SELECT id, pais_id, anio, numero, nombre, cerrado
        FROM Config.DIM_Ciclo
        WHERE anio = 2026 AND numero = 3
        ORDER BY pais_id
    """)
    ciclos_3_2026 = cur.fetchall()
    print("\n=== Ciclos con anio=2026 numero=3 (todos los paises) ===")
    for c in ciclos_3_2026:
        marca = "  <-- pais de referencia" if c["pais_id"] == pais_rd_id else ""
        print(f"  id={c['id']:<5} pais_id={c['pais_id']:<5} nombre={c['nombre']:<20} cerrado={c['cerrado']}{marca}")

    ciclo_correcto = next((c for c in ciclos_3_2026 if c["pais_id"] == pais_rd_id), None)
    if not ciclo_correcto:
        print(f"ERROR: no existe 'Ciclo 3 2026' para pais_id={pais_rd_id}. Importa los ciclos primero.")
        conn.close()
        return
    ciclo_correcto_id = ciclo_correcto["id"]
    print(f"  -> Ciclo 3 2026 correcto para {pais_rd['codigo']}: ciclo_id={ciclo_correcto_id}")

    # ── 3. RMs de ese pais ───────────────────────────────────────────────
    cur.execute("""
        SELECT id, codigo, pais_id
        FROM Config.DIM_RM
        WHERE pais_id = %s AND activo = 1
    """, (pais_rd_id,))
    rms = cur.fetchall()
    rm_ids = [r["id"] for r in rms]
    print(f"\n=== RMs activos de {pais_rd['codigo']} (pais_id={pais_rd_id}): {len(rm_ids)} ===")
    if not rm_ids:
        print("ERROR: no hay RMs para este pais. Abortando.")
        conn.close()
        return

    # ── 4. Donde quedaron realmente las filas de estos RMs ──────────────
    fmt_ids = ",".join(str(i) for i in rm_ids)
    cur.execute(f"""
        SELECT ri.pais_id AS fila_pais_id, ri.ciclo_id AS fila_ciclo_id,
               c.pais_id AS ciclo_pais_id, c.anio, c.numero, c.nombre AS ciclo_nombre,
               COUNT(*) AS filas
        FROM DW.FACT_ResultadoIndicador ri
        LEFT JOIN Config.DIM_Ciclo c ON c.id = ri.ciclo_id
        WHERE ri.rm_id IN ({fmt_ids})
        GROUP BY ri.pais_id, ri.ciclo_id, c.pais_id, c.anio, c.numero, c.nombre
        ORDER BY c.anio, c.numero
    """)
    grupos = cur.fetchall()
    print("\n=== Distribucion real de filas FACT_ResultadoIndicador para estos RMs ===")
    for g in grupos:
        print(f"  fila.pais_id={g['fila_pais_id']:<5} fila.ciclo_id={g['fila_ciclo_id']:<5} "
              f"-> ciclo='{g['ciclo_nombre']}' (anio={g['anio']}, numero={g['numero']}, ciclo.pais_id={g['ciclo_pais_id']}) "
              f"= {g['filas']} filas")

    filas_correctas = sum(
        g["filas"] for g in grupos
        if g["fila_pais_id"] == pais_rd_id and g["fila_ciclo_id"] == ciclo_correcto_id
    )
    print(f"\n  Filas YA en (pais_id={pais_rd_id}, ciclo_id={ciclo_correcto_id}) correctos: {filas_correctas}")

    candidatos = [
        g for g in grupos
        if g["anio"] == 2026 and g["numero"] == 3
        and not (g["fila_pais_id"] == pais_rd_id and g["fila_ciclo_id"] == ciclo_correcto_id)
    ]

    if candidatos:
        print("\n*** CAUSA ENCONTRADA: filas del ciclo 3/2026 grabadas con (pais_id, ciclo_id) ***")
        print("*** distinto al que usa la pantalla 'Calcular IUP y Ranking'.                 ***")
        total_corregidas = 0
        for c in candidatos:
            print(f"  -> Corrigiendo {c['filas']} filas: pais_id {c['fila_pais_id']} -> {pais_rd_id}, "
                  f"ciclo_id {c['fila_ciclo_id']} -> {ciclo_correcto_id}")
            cur.execute(f"""
                UPDATE DW.FACT_ResultadoIndicador
                SET pais_id = %s, ciclo_id = %s
                WHERE pais_id = %s AND ciclo_id = %s AND rm_id IN ({fmt_ids})
            """, (pais_rd_id, ciclo_correcto_id, c["fila_pais_id"], c["fila_ciclo_id"]))
            total_corregidas += c["filas"]
        conn.commit()
        print(f"  Correccion aplicada y confirmada (COMMIT). Total corregido: {total_corregidas} filas.")
    elif filas_correctas == 0:
        print("\nNo se encontraron filas para Ciclo 3 2026 en NINGUN pais/ciclo para estos RMs.")
        print("El ETL no inserto nada para estos RMs en este ciclo. Revisar el Job de carga (no es un")
        print("problema de pais_id/ciclo_id — revisar mapa_ind / indicador_codigo en etl_service.py).")
        conn.close()
        return
    else:
        print("\nLas filas ya estaban en (pais_id, ciclo_id) correctos. Revisando otras causas...")
        cur.execute(f"""
            SELECT
                SUM(CASE WHEN resultado_real IS NULL THEN 1 ELSE 0 END) AS sin_valor,
                SUM(CASE WHEN activo = 0 THEN 1 ELSE 0 END) AS inactivas,
                COUNT(*) AS total
            FROM DW.FACT_ResultadoIndicador
            WHERE pais_id = %s AND ciclo_id = %s AND rm_id IN ({fmt_ids})
        """, (pais_rd_id, ciclo_correcto_id))
        chk = cur.fetchone()
        print(f"  total={chk['total']}  resultado_real NULL={chk['sin_valor']}  activo=0={chk['inactivas']}")
        if chk["sin_valor"] or chk["inactivas"]:
            print("  *** Causa: filas sin resultado_real o inactivas. Revisar carga ETL. ***")
        else:
            print("  No se detecto causa automatizable. Revisar manualmente con el equipo de BD.")

    # ── 5. Re-ejecutar el recalculo para confirmar ──────────────────────
    print(f"\n=== Re-ejecutando DW.sp_RecalcularCiclo (ciclo_id={ciclo_correcto_id}, pais_id={pais_rd_id}) ===")
    cur.execute(
        "EXEC DW.sp_RecalcularCiclo @ciclo_id = %s, @pais_id = %s",
        (ciclo_correcto_id, pais_rd_id),
    )
    resultado = cur.fetchone()
    conn.commit()
    print(f"  abortado={resultado['abortado']}  "
          f"filas_kpi_actualizadas={resultado['filas_kpi_actualizadas']}  "
          f"rankings_generados={resultado['rankings_generados']}")
    if resultado["filas_kpi_actualizadas"]:
        print("\n>>> LISTO. Vuelve a 'Calcular IUP y Ranking' en la pantalla ETL — ya deberia mostrar resultados. <<<")
    else:
        print("\n>>> Sigue en 0. El mismatch de pais/ciclo no era la unica causa — revisar mensaje de arriba. <<<")

    conn.close()


if __name__ == "__main__":
    main()
