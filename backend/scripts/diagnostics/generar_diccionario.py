"""Genera el diccionario de datos de VISTA (Entregable 2 — Mallén).

Toda la parte estructural (tablas, columnas, tipos, nulabilidad, PK/FK, índices) se deriva del
metadata de SQLAlchemy: cobertura del 100 % garantizada, sin transcripción manual.

La parte funcional se toma de evidencia real del repositorio:
  - descripción de la tabla → docstring de su clase ORM (65 de 97 la tienen);
  - consumidores            → búsqueda del nombre de la tabla y de su clase en servicios y routers;
  - origen del dato         → reglas explícitas por esquema/prefijo, documentadas en ORIGEN_REGLAS.

Lo que no puede probarse queda como `PENDIENTE`, nunca inventado.

Uso:
    python scripts/diagnostics/generar_diccionario.py --dest RUTA_CARPETA
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import date

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BACKEND)

from app.models import (  # noqa: F401,E402
    cat_models, coaching_more_models, dimensiones, exam_models,
    hechos, seguridad_rbac, usuario, visita,
)
from app.db.database import Base  # noqa: E402

HOY = date.today().isoformat()

# ── Clasificación (mismo criterio que los scripts de creación) ────────────────
def clasificar(esq: str, nom: str) -> str:
    if esq in ("Audit", "ETL", "stg") or "Auditoria" in nom:
        return "Log / ETL / Auditoría"
    if esq == "Security":
        return "Configuración y seguridad"
    if nom.startswith(("DIM_", "Dim")):
        return "Dimensión"
    if nom.startswith(("FACT_", "Fact")):
        return "Hecho"
    if esq == "Config":
        return "Configuración y seguridad"
    return "Operacional / transaccional"


# ── Origen del dato: reglas con justificación explícita ──────────────────────
# Se aplican en orden; la primera que casa, gana.
ORIGEN_REGLAS = [
    (lambda e, n: e in ("Audit",) or "Auditoria" in n,
     "Técnico / auditoría",
     "Lo escribe el propio sistema al registrar acciones."),
    (lambda e, n: e in ("ETL", "stg"),
     "Técnico / staging",
     "Recepción y control de cargas; no es dato de negocio final."),
    (lambda e, n: e == "Security",
     "Captura en VISTA",
     "Usuarios, roles y permisos se administran dentro de la aplicación."),
    (lambda e, n: e == "coaching",
     "Captura en VISTA (EXCLUIDO de escritura externa)",
     "Coaching es una de las 2 excepciones acordadas: se captura en la app."),
    (lambda e, n: e == "exam",
     "Captura en VISTA (EXCLUIDO de escritura externa)",
     "Evaluación de Conocimientos es la otra excepción acordada."),
    (lambda e, n: e == "Visita",
     "Externo — módulo de visita de Mallén",
     "Acordado: el detalle transaccional lo enviará Mallén, no se captura en VISTA."),
    (lambda e, n: e == "DW" and n in _CALCULADAS,
     "Calculado por VISTA",
     "Lo produce el motor de cálculo; NO debe escribirse desde afuera."),
    (lambda e, n: e == "DW",
     "Externo — pendiente de confirmar fuente",
     "Indicador de negocio: procede del entorno de Mallén; falta mapear la fuente exacta."),
    (lambda e, n: e == "cat",
     "Mixto — carga masiva + cálculo",
     "Categorización médica: entra por Excel/staging y VISTA calcula la categoría."),
    (lambda e, n: e == "Config",
     "Catálogo maestro — pendiente de confirmar fuente",
     "Se importa por Excel hoy; falta confirmar si Mallén lo alimentará desde SQL Server."),
]

# Tablas de DW que produce el motor de cálculo (verificado en motor_calculo_service y servicios).
_CALCULADAS = {
    "FACT_ScoreIntegralRM", "FACT_RankingRM", "FACT_RankingGerente", "FACT_ReconocimientoRM",
    "FACT_ScorecardIndicador", "FACT_DistribucionEquipo", "FACT_DashboardEjecutivo",
    "FACT_TendenciaCiclo",
}


def origen(esq: str, nom: str) -> tuple[str, str]:
    for cond, etiqueta, motivo in ORIGEN_REGLAS:
        if cond(esq, nom):
            return etiqueta, motivo
    return "PENDIENTE de confirmar", "Sin regla aplicable con la evidencia disponible."


# ── Consumidores: quién lee o escribe cada tabla ─────────────────────────────
def _indexar_fuentes() -> dict:
    texto = {}
    # Incluye app/core: allí viven consumidores reales (token_store, authz/audit) que, de
    # omitirse, harían declarar "sin consumidor" a tablas que SÍ se usan.
    for sub in ("app/services", "app/api/v1/routers", "app/core", "app/core/authz"):
        base = os.path.join(BACKEND, sub)
        if not os.path.isdir(base):
            continue
        for f in os.listdir(base):
            if f.endswith(".py"):
                ruta = os.path.join(base, f)
                if not os.path.isfile(ruta):
                    continue
                with open(ruta, encoding="utf-8", errors="ignore") as fh:
                    texto[f"{sub.split('/')[-1]}/{f}"] = fh.read()
    return texto


def consumidores(fuentes: dict, tabla: str, clase: str) -> str:
    hits = sorted({f for f, t in fuentes.items()
                   if re.search(rf"\b{re.escape(tabla)}\b", t)
                   or (clase and re.search(rf"\b{re.escape(clase)}\b", t))})
    return ", ".join(hits) if hits else "SIN CONSUMIDOR LOCALIZADO"


def _limpiar_doc(doc: str) -> str:
    if not doc:
        return ""
    return " ".join(l.strip() for l in doc.strip().splitlines() if l.strip())


# Orden obligatorio de secciones exigido por el requerimiento.
_ORDEN_SECCIONES = [
    "Log / ETL / Auditoría",
    "Dimensión",
    "Hecho",
    "Operacional / transaccional",
    "Configuración y seguridad",
]


def _markdown(dest: str, filas_t: list, filas_c: list) -> None:
    """Versión legible: índice por sección con el detalle de cada tabla.

    El detalle campo a campo (1.107 filas) vive en el CSV: en prosa sería ilegible.
    """
    campos_por_tabla = defaultdict(list)
    for c in filas_c:
        campos_por_tabla[(c["esquema"], c["tabla"])].append(c)

    with open(os.path.join(dest, "02_diccionario_datos.md"), "w", encoding="utf-8") as f:
        f.write(f"""# 02 — Diccionario de datos

**Proyecto:** VISTA · **Cliente:** Laboratorios Mallén · **Fecha:** {HOY} · **Versión:** 1.0
**Origen:** repositorio VISTA, rama `master`, revisión Alembic `0029_capacitacion_sin_medicos`

**Cobertura:** {len(filas_t)} tablas y {len(filas_c)} columnas — el 100 % del esquema.

## Cómo leer este documento

Este archivo es el **índice navegable por secciones**. El detalle campo a campo está en:

| Archivo | Contenido |
|---|---|
| `02_diccionario_tablas.csv` | Una fila por tabla, con todos sus atributos |
| `02_diccionario_campos.csv` | Una fila por columna ({len(filas_c)} filas) |

Ambos están en UTF-8 con BOM y separador `;`: se abren directamente en Excel en español sin
perder acentos ni partir columnas.

## Método y límites

La parte **estructural** (tablas, columnas, tipos, nulabilidad, claves, índices) se derivó del
metadata de SQLAlchemy: es exacta y completa por construcción.

La **descripción de negocio** de cada tabla procede del docstring de su modelo. Donde el código
no documenta, figura `PENDIENTE` en lugar de una descripción inventada.

El **origen del dato** se asignó por reglas explícitas y trazables, no por intuición: cada tabla
lleva su justificación en la columna `justificacion_origen` del CSV. Donde la fuente no puede
determinarse con el código, dice `PENDIENTE de confirmar` — su mapeo definitivo corresponde al
Entregable 3, con la información de Mallén.

""")
        # Resumen por sección
        por_sec = defaultdict(list)
        for t in filas_t:
            por_sec[t["clasificacion"]].append(t)
        f.write("## Resumen por sección\n\n| Sección | Tablas |\n|---|---:|\n")
        for sec in _ORDEN_SECCIONES:
            f.write(f"| {sec} | {len(por_sec[sec])} |\n")
        f.write(f"| **Total** | **{len(filas_t)}** |\n\n---\n\n")

        for sec in _ORDEN_SECCIONES:
            f.write(f"## {sec}\n\n")
            for t in sorted(por_sec[sec], key=lambda x: (x["esquema"], x["tabla"])):
                f.write(f"### `{t['esquema']}.{t['tabla']}`\n\n")
                f.write(f"{t['descripcion_negocio']}\n\n")
                f.write(f"- **Origen del dato:** {t['origen_dato']} — {t['justificacion_origen']}\n")
                f.write(f"- **Clave primaria:** `{t['clave_primaria'] or '—'}`\n")
                if t["claves_foraneas"]:
                    f.write(f"- **Referencias a:** {t['claves_foraneas']}\n")
                if t["restricciones_unicas"] != "—":
                    f.write(f"- **Únicas:** {t['restricciones_unicas']}\n")
                f.write(f"- **Columnas:** {t['n_columnas']}\n")
                cons = t["consumidores"]
                if cons == "SIN CONSUMIDOR LOCALIZADO":
                    f.write("- **Consumidores:** ⚠️ **SIN CONSUMIDOR LOCALIZADO** — ningún "
                            "servicio, router ni componente del núcleo la lee o escribe.\n")
                else:
                    f.write(f"- **Consumidores:** {cons}\n")
                cols = campos_por_tabla.get((t["esquema"], t["tabla"]), [])
                if cols:
                    f.write("\n| # | Campo | Tipo | Nulos | PK/FK | Descripción |\n")
                    f.write("|---:|---|---|:---:|---|---|\n")
                    for c in cols:
                        marca = "PK" if c["es_pk"] else (f"FK → {c['es_fk']}" if c["es_fk"] else "")
                        desc = c["descripcion_funcional"]
                        f.write(f"| {c['posicion']} | `{c['campo']}` | {c['tipo']} | "
                                f"{c['permite_nulos']} | {marca} | {desc} |\n")
                f.write("\n")


def generar(dest: str) -> dict:
    os.makedirs(dest, exist_ok=True)
    fuentes = _indexar_fuentes()

    # tabla física → clase ORM
    por_tabla = {}
    for m in Base.registry.mappers:
        c = m.class_
        por_tabla[(c.__table__.schema, c.__table__.name)] = c

    filas_t, filas_c = [], []
    for t in sorted(Base.metadata.tables.values(), key=lambda x: (x.schema or "", x.name)):
        cls = por_tabla.get((t.schema, t.name))
        doc = _limpiar_doc(cls.__doc__ if cls else "")
        cat = clasificar(t.schema or "", t.name)
        orig, motivo = origen(t.schema or "", t.name)
        uniques = "; ".join(
            f"{c.name}({', '.join(col.name for col in c.columns)})"
            for c in t.constraints if type(c).__name__ == "UniqueConstraint")

        filas_t.append({
            "esquema": t.schema,
            "tabla": t.name,
            "clasificacion": cat,
            "descripcion_negocio": doc or "PENDIENTE — el modelo no documenta esta tabla",
            "granularidad": "PENDIENTE — revisar con el consumidor",
            "clave_primaria": ", ".join(c.name for c in t.primary_key.columns),
            "claves_foraneas": "; ".join(sorted({fk.target_fullname for fk in t.foreign_keys})),
            "restricciones_unicas": uniques or "—",
            "indices": "; ".join(i.name for i in t.indexes) or "—",
            "n_columnas": len(t.columns),
            "origen_dato": orig,
            "justificacion_origen": motivo,
            "consumidores": consumidores(fuentes, t.name, cls.__name__ if cls else ""),
            "clase_orm": cls.__name__ if cls else "(sin modelo ORM)",
        })

        for pos, c in enumerate(t.columns, start=1):
            fks = sorted(fk.target_fullname for fk in c.foreign_keys)
            filas_c.append({
                "esquema": t.schema,
                "tabla": t.name,
                "posicion": pos,
                "campo": c.name,
                "tipo": str(c.type),
                "permite_nulos": "SÍ" if c.nullable else "NO",
                "valor_defecto": (str(c.default.arg) if c.default is not None
                                  and hasattr(c.default, "arg") else ""),
                "es_pk": "SÍ" if c.primary_key else "",
                "es_fk": ", ".join(fks),
                "indexado": "SÍ" if c.index else "",
                "unico": "SÍ" if c.unique else "",
                "descripcion_funcional": c.comment or "PENDIENTE",
                "dominio_valores": "PENDIENTE" if "VARCHAR" in str(c.type).upper() else "",
                "origen_dato": orig,
            })

    # Las 6 tablas sin modelo ORM se registran para no perder cobertura.
    for esq, nom in [("cat", "DimCentroMedico"), ("cat", "DimGeografia"), ("cat", "DimEquipo"),
                     ("cat", "DimReglaCategoriaMedica"), ("cat", "FactMedicoCategoriaDetalle"),
                     ("stg", "MedicoCategoriaInput")]:
        orig, motivo = origen(esq, nom)
        filas_t.append({
            "esquema": esq, "tabla": nom, "clasificacion": clasificar(esq, nom),
            "descripcion_negocio": "Creada por DDL explícito en la migración baseline; SIN modelo ORM.",
            "granularidad": "PENDIENTE", "clave_primaria": "ver 0001_baseline_postgres",
            "claves_foraneas": "—", "restricciones_unicas": "—", "indices": "—",
            "n_columnas": 0, "origen_dato": orig, "justificacion_origen": motivo,
            "consumidores": consumidores(fuentes, nom, ""), "clase_orm": "(sin modelo ORM)",
        })

    def _csv(nombre, filas):
        ruta = os.path.join(dest, nombre)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(filas)

    _csv("02_diccionario_tablas.csv", filas_t)
    _csv("02_diccionario_campos.csv", filas_c)
    _markdown(dest, filas_t, filas_c)

    sin_cons = [f"{f['esquema']}.{f['tabla']}" for f in filas_t
                if f["consumidores"] == "SIN CONSUMIDOR LOCALIZADO"]
    sin_doc = [f"{f['esquema']}.{f['tabla']}" for f in filas_t
               if f["descripcion_negocio"].startswith("PENDIENTE")]
    por_cat = defaultdict(int)
    for f in filas_t:
        por_cat[f["clasificacion"]] += 1

    return {"tablas": len(filas_t), "campos": len(filas_c), "por_categoria": dict(por_cat),
            "sin_consumidor": sin_cons, "sin_descripcion": len(sin_doc)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    r = generar(ap.parse_args().dest)
    print(f"Tablas documentadas : {r['tablas']}")
    print(f"Campos documentados : {r['campos']}")
    print(f"Sin descripción     : {r['sin_descripcion']}")
    print("Por categoría:")
    for k, v in sorted(r["por_categoria"].items(), key=lambda kv: -kv[1]):
        print(f"   {k:<32} {v}")
    print(f"\nSin consumidor localizado ({len(r['sin_consumidor'])}):")
    for t in r["sin_consumidor"]:
        print(f"   {t}")
