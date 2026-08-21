"""
Exporta la CONFIGURACIÓN de un país a un .sql que se aplica en otra instalación.

POR QUÉ EXISTE. Una instalación nueva (el servidor de calidad de un cliente, un
país que se suma) arranca sin indicadores y sin reglas de categorización. Nada de
eso lo crea la integración: el sincronizador trae las dimensiones que el cliente
envía, pero los pesos del score y el vocabulario de categorización son
configuración de negocio que ya está decidida en la instalación que funciona.
Volver a teclearla es lento y, peor, silencioso cuando se teclea distinto: un
`escala` mal puesto no da error, da notas cien veces más bajas.

QUÉ EXPORTA (de un solo país):
  Config.DIM_Pais                  la ficha del país
  Config.DIM_Indicador             los indicadores con su ponderación y escala
  cat.DimPais                      el país en el esquema de categorización
  cat.DimComponenteCategoria       los componentes (globales, no por país)
  cat.DimClasificacionMedica       las bandas A/B/C/D
  cat.DimReglaCategoriaMedica      las reglas y su vocabulario cerrado

QUÉ **NO** EXPORTA: nada operativo — ni médicos, ni visitas, ni ciclos, ni
usuarios. Solo catálogos de configuración.

EL SQL GENERADO ES IDEMPOTENTE: cada fila va con `WHERE NOT EXISTS` sobre su
llave natural, así que aplicarlo dos veces no duplica y aplicarlo sobre una base
a medias completa lo que falte sin tocar lo que ya está.

LAS LLAVES SUBROGADAS NO VIAJAN. `PaisKey`/`ComponenteKey` son seriales y en el
destino valen otra cosa; el SQL las resuelve con subconsultas sobre la llave
natural (`CodigoPais`, `CodigoComponente`). Copiar el número tal cual habría
enlazado las reglas al país equivocado — sin error, con resultados.

Uso:
  # en la instalación que YA está configurada
  python scripts/exportar_config_pais.py DO > config-DO.sql
  # en la instalación nueva
  psql -U segura -d scgcpr -f config-DO.sql
"""
from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import text

from app.db.database import SessionLocal


def lit(v) -> str:
    """Un valor Python como literal SQL. Las comillas se duplican (el estándar);
    no se usa `psycopg2.adapt` a propósito, para que el .sql sea legible y
    revisable a ojo antes de aplicarlo en el servidor de otro."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


# Cada entrada: (esquema, tabla, columnas a copiar, columnas de la llave natural).
# Las columnas se declaran EXPLÍCITAS y se comparan contra el esquema real antes
# de exportar: si alguien añade una columna y no la añade aquí, el script aborta
# en vez de generar un SQL que la deja fuera en silencio.
TABLAS = {
    "pais": ("Config", "DIM_Pais",
             ["codigo", "nombre", "moneda", "zona_horaria", "activo"], ["codigo"]),
    "indicador": ("Config", "DIM_Indicador",
                  ["pais_codigo", "codigo", "nombre", "descripcion", "rol", "modulo",
                   "tipo_periodo", "ponderacion_pct", "peso_iup", "escala", "unidad",
                   "formula", "meta_global", "valor_min", "valor_max", "orden",
                   "activo"],
                  ["pais_codigo", "codigo"]),
    "cat_pais": ("cat", "DimPais",
                 ["PaisIdOrigen", "CodigoPais", "NombrePais", "Moneda", "ZonaHoraria",
                  "Activo"], ["CodigoPais"]),
    "componente": ("cat", "DimComponenteCategoria",
                   ["CodigoComponente", "NombreComponente", "TipoEvaluacion",
                    "PesoComponentePct", "Requerido", "Activo"], ["CodigoComponente"]),
    "banda": ("cat", "DimClasificacionMedica",
              ["Clase", "PuntajeMinPct", "PuntajeMaxPct", "OrdenClase",
               "VigenteDesde", "VigenteHasta", "Activo"], ["Clase"]),
    "regla": ("cat", "DimReglaCategoriaMedica",
              ["CodigoRegla", "Detalle", "ValorMinimo", "ValorMaximo", "ValorTexto",
               "Criterio", "PesoComponentePct", "PuntajePct", "VigenteDesde",
               "VigenteHasta", "Activo"], ["CodigoRegla"]),
}


def _verificar_esquema(db) -> None:
    """Aborta si la tabla real tiene columnas que este script no conoce.

    Es la diferencia entre una exportación incompleta y un error: sin esto, una
    columna nueva (un campo de configuración añadido más adelante) se quedaría
    fuera del .sql y el país destino arrancaría con ese campo en su valor por
    defecto, que nadie eligió."""
    ignorar = {"id", "PaisKey", "ComponenteKey", "ClasificacionKey", "ReglaKey",
               "FechaCargaUtc", "created_at", "updated_at"}
    problemas = []
    for _clave, (esquema, tabla, cols, _nat) in TABLAS.items():
        reales = {r[0] for r in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :e AND table_name = :t"), {"e": esquema, "t": tabla})}
        if not reales:
            problemas.append(f'{esquema}.{tabla}: la tabla no existe')
            continue
        faltan = reales - set(cols) - ignorar
        if faltan:
            problemas.append(f'{esquema}.{tabla}: columnas no contempladas -> '
                             f'{", ".join(sorted(faltan))}')
    if problemas:
        print("ABORTADO: el esquema cambió y la exportación quedaría incompleta.",
              file=sys.stderr)
        for p in problemas:
            print("  " + p, file=sys.stderr)
        print("\n  Añade esas columnas a TABLAS en este script y vuelve a correrlo.",
              file=sys.stderr)
        sys.exit(1)


# Tablas del esquema `cat` con `FechaCargaUtc` NOT NULL y SIN valor por defecto.
# Se sella al APLICAR, no se copia del origen: la columna dice «cuándo entró esta
# fila en esta base», así que la fecha del servidor de origen sería un dato falso.
SELLA_FECHA = {("cat", "DimPais"), ("cat", "DimComponenteCategoria"),
               ("cat", "DimClasificacionMedica"), ("cat", "DimReglaCategoriaMedica")}
AHORA_UTC = "(NOW() AT TIME ZONE 'UTC')"


def _insert(esquema: str, tabla: str, cols: list[str], valores: list[str],
            natural: list[str]) -> str:
    """`INSERT ... SELECT ... WHERE NOT EXISTS` — la forma idempotente que no
    necesita que exista un UNIQUE en el destino (varias de estas tablas no lo
    tienen, así que `ON CONFLICT` no serviría)."""
    cond = " AND ".join(f'x."{c}" = {valores[cols.index(c)]}' for c in natural)
    if (esquema, tabla) in SELLA_FECHA:
        cols, valores = cols + ["FechaCargaUtc"], valores + [AHORA_UTC]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    return (f'INSERT INTO "{esquema}"."{tabla}" ({col_sql})\n'
            f'SELECT {", ".join(valores)}\n'
            f'WHERE NOT EXISTS (SELECT 1 FROM "{esquema}"."{tabla}" x WHERE {cond});')


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/exportar_config_pais.py <CODIGO_PAIS>", file=sys.stderr)
        sys.exit(2)
    pais = sys.argv[1].strip().upper()

    # UTF-8 SIEMPRE, sin depender del entorno. Redirigir la salida en Windows la
    # codifica con la página de códigos de la consola (cp1252) y los acentos
    # salen rotos. No es cosmético: los criterios de categorización tienen
    # vocabulario CERRADO ("Presidente de Sociedad, Charlista"), y un valor que
    # no coincide carácter por carácter no matchea ninguna regla — el médico
    # queda sin clasificar, sin que nada dé error.
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:      # pragma: no cover — stdout sustituido en pruebas
        pass

    db = SessionLocal()
    try:
        _verificar_esquema(db)
        out: list[str] = [
            f"-- Configuración del país {pais}, exportada de una instalación en marcha.",
            "-- Idempotente: se puede aplicar más de una vez sin duplicar.",
            "-- No contiene datos operativos (ni médicos, ni visitas, ni usuarios).",
            "BEGIN;",
        ]

        def volcar(clave: str, where: str, params: dict, extra_cols=None,
                   extra_vals=None, alias: str = ""):
            """`alias` califica las columnas del SELECT. Es obligatorio cuando
            `where` trae un JOIN: varias de estas tablas comparten nombres de
            columna (`Activo`, `VigenteDesde`) y sin calificar son ambiguas."""
            esquema, tabla, cols, natural = TABLAS[clave]
            pre = f'{alias}.' if alias else ""
            filas = db.execute(text(
                f'SELECT {", ".join(pre + chr(34) + c + chr(34) for c in cols)} '
                f'FROM "{esquema}"."{tabla}" {where}'), params).all()
            if not filas:
                print(f"AVISO: {esquema}.{tabla} no tiene filas para {pais}",
                      file=sys.stderr)
            out.append(f"\n-- {esquema}.{tabla} ({len(filas)} fila(s))")
            for f in filas:
                c = list(cols) + list(extra_cols or [])
                v = [lit(x) for x in f] + list(extra_vals or [])
                out.append(_insert(esquema, tabla, c, v, natural))
            return len(filas)

        # El país primero: los indicadores tienen FK a `Config.DIM_Pais.codigo`.
        volcar("pais", "WHERE codigo = :p", {"p": pais})
        volcar("indicador", "WHERE pais_codigo = :p", {"p": pais})
        volcar("cat_pais", 'WHERE "CodigoPais" = :p', {"p": pais})
        # Los componentes son GLOBALES (no llevan PaisKey): sin ellos las reglas
        # no tienen a qué colgarse en el destino.
        volcar("componente", "", {})

        # `PaisKey` se resuelve en el destino, no se copia — ver la nota de cabecera.
        pk = (f'(SELECT "PaisKey" FROM "cat"."DimPais" WHERE "CodigoPais" = {lit(pais)})')
        volcar("banda",
               'c JOIN "cat"."DimPais" p ON p."PaisKey" = c."PaisKey" '
               'WHERE p."CodigoPais" = :p',
               {"p": pais}, extra_cols=["PaisKey"], extra_vals=[pk], alias="c")

        # La regla necesita ADEMÁS su componente, también por llave natural.
        esquema, tabla, cols, natural = TABLAS["regla"]
        filas = db.execute(text(f'''
            SELECT {", ".join('r."' + c + '"' for c in cols)}, co."CodigoComponente"
            FROM "cat"."DimReglaCategoriaMedica" r
            JOIN "cat"."DimPais" p ON p."PaisKey" = r."PaisKey"
            JOIN "cat"."DimComponenteCategoria" co ON co."ComponenteKey" = r."ComponenteKey"
            WHERE p."CodigoPais" = :p'''), {"p": pais}).all()
        if not filas:
            print(f"AVISO: cat.DimReglaCategoriaMedica sin reglas para {pais}",
                  file=sys.stderr)
        out.append(f"\n-- {esquema}.{tabla} ({len(filas)} fila(s))")
        for f in filas:
            comp = f[-1]
            ck = ('(SELECT "ComponenteKey" FROM "cat"."DimComponenteCategoria" '
                  f'WHERE "CodigoComponente" = {lit(comp)})')
            c = list(cols) + ["PaisKey", "ComponenteKey"]
            v = [lit(x) for x in f[:-1]] + [pk, ck]
            # La llave natural de una regla incluye su componente: el mismo
            # CodigoRegla puede repetirse entre componentes distintos.
            out.append(_insert(esquema, tabla, c, v, ["CodigoRegla", "ComponenteKey"]))

        out.append("\nCOMMIT;")
        print("\n".join(out))
    finally:
        db.close()


if __name__ == "__main__":
    main()
