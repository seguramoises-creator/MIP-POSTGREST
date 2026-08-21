"""
Diagnóstico (SOLO LECTURA): ¿está VISTA listo para recibir el primer lote de Mallén?

POR QUÉ EXISTE. La integración por `ext` casi nunca falla con un error: el
sincronizador CREA las nueve dimensiones que Mallén envía (país, línea, gerente,
representante, ciclo, especialidad, médico, farmacia, producto), así que un lote
entra sin protestar aunque VISTA no tenga nada configurado. Lo que falla después
es el CÁLCULO, y falla en silencio: sin indicadores dados de alta no hay puntos,
y sin puntos el ranking sale vacío o en cero — un resultado que parece un dato,
no un error.

Este script comprueba, por país, lo que el sincronizador NO crea y el cálculo sí
necesita. No escribe nada.

Uso (dentro del contenedor):
  docker compose exec -e PYTHONPATH=/app backend python scripts/diagnostico_integracion_listo.py

Antes del PRIMER lote la base no tiene países todavía (los crea el propio envío),
así que se le pasan los códigos que Mallén va a enviar y los revisa igual:
  ... scripts/diagnostico_integracion_listo.py DO GT HN
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services.integracion_indicadores_service import CODIGOS

OK, MAL, AVISO = "  [OK]   ", "  [FALTA]", "  [aviso]"


def _paises(db) -> list[str]:
    """Los países a revisar: los que ya existen en VISTA MÁS los que Mallén
    anunció en `ext`. La unión importa — un país que solo está en `ext` todavía
    no tiene configuración, y es justo el que hay que preparar.

    Puede devolver LISTA VACÍA, y es el caso normal antes del primer lote: VISTA
    no tiene países porque los crea el propio envío. `main` lo trata aparte —
    un checklist sin nada que revisar tiene que decirlo, porque si se calla la
    ausencia de fallos se lee como que no falta nada."""
    filas = db.execute(text('''
        SELECT codigo FROM "Config"."DIM_Pais"
        UNION
        SELECT DISTINCT pais_codigo FROM "ext"."dimpais"
        ORDER BY 1''')).all()
    return [f[0] for f in filas]


def _indicadores(db, pais: str) -> None:
    """Los cinco indicadores que calcula la integración.

    Dos comprobaciones distintas y ambas necesarias:

    - `ponderacion_pct` es el peso del indicador Y el divisor del ranking
      (`SUM(puntos) * 100 / SUM(ponderacion_pct)`). En cero, ese indicador
      aporta cero por mucho que el representante cubra el 100%.
    - `escala` debe ser 1. La integración escribe la cobertura como FRACCIÓN
      (0.85 = 85%) y el motor la multiplica por 100 solo cuando `escala == 1`.
      Con escala 100 ese 0.85 se lee como 0.85 puntos sobre 100: el
      representante que cubrió casi todo aparece con nota de cero.
    """
    filas = db.execute(text('''
        SELECT codigo, ponderacion_pct, escala
        FROM "Config"."DIM_Indicador"
        WHERE pais_codigo = :p AND codigo = ANY(:c)'''),
        {"p": pais, "c": list(CODIGOS)}).all()
    hay = {f[0]: (f[1], f[2]) for f in filas}

    faltan = [c for c in CODIGOS if c not in hay]
    if faltan:
        print(f"{MAL} indicadores sin dar de alta: {', '.join(faltan)}")
    sin_peso = [c for c, (p, _) in hay.items() if not p]
    if sin_peso:
        print(f"{MAL} indicadores con ponderación 0 (no suman al score): {', '.join(sin_peso)}")
    mala_escala = [c for c, (_, e) in hay.items() if e != 1]
    if mala_escala:
        print(f"{MAL} indicadores con escala != 1 (la cobertura se leerá 100 veces "
              f"más baja): {', '.join(mala_escala)}")
    if hay and not (faltan or sin_peso or mala_escala):
        total = sum(p for p, _ in hay.values())
        print(f"{OK} los {len(hay)} indicadores de la integración, ponderación suma {total}")


def _categorizacion(db, pais: str) -> None:
    """Sin reglas `cat.*` los médicos entran pero quedan SIN CLASIFICAR. No
    rompe la carga: rompe la categoría A/B/C/D de todo el país."""
    reglas, bandas = db.execute(text('''
        SELECT (SELECT COUNT(*) FROM "cat"."DimReglaCategoriaMedica" r
                JOIN "cat"."DimPais" p ON p."PaisKey" = r."PaisKey"
                WHERE p."CodigoPais" = :p AND r."Activo" = TRUE),
               (SELECT COUNT(*) FROM "cat"."DimClasificacionMedica" c
                JOIN "cat"."DimPais" p ON p."PaisKey" = c."PaisKey"
                WHERE p."CodigoPais" = :p)'''), {"p": pais}).one()
    if reglas and bandas:
        print(f"{OK} categorización: {reglas} reglas, {bandas} bandas A/B/C/D")
    else:
        print(f"{MAL} categorización sin configurar ({reglas} reglas, {bandas} bandas): "
              f"los médicos de este país quedarán sin categoría")


def _ciclos(db, pais: str) -> None:
    """Un ciclo CERRADO rechaza la integración (misma regla que el recálculo:
    los ciclos cerrados son historia inmutable). Solo importa si Mallén va a
    enviar datos de un período ya cerrado."""
    fila = db.execute(text('''
        SELECT COUNT(*) FILTER (WHERE NOT cerrado), COUNT(*) FILTER (WHERE cerrado)
        FROM "Config"."DIM_Ciclo" WHERE pais_codigo = :p'''), {"p": pais}).one()
    abiertos, cerrados = fila
    if abiertos:
        print(f"{OK} ciclos: {abiertos} abierto(s), {cerrados} cerrado(s)")
    elif cerrados:
        print(f"{AVISO} los {cerrados} ciclos están cerrados — un lote sobre "
              f"cualquiera de ellos será rechazado")
    else:
        print(f"{AVISO} sin ciclos: los creará el propio lote de Mallén, abiertos")


def _meta_cobertura(db, pais: str) -> None:
    """No bloquea nada — sin parámetro se usa 90%. Se reporta para que el 90%
    sea una decisión y no una sorpresa."""
    n = db.execute(text('SELECT COUNT(*) FROM "Config"."DIM_ParametroCobertura" '
                        'WHERE pais_codigo = :p'), {"p": pais}).scalar()
    print(f"{OK if n else AVISO} meta de cobertura: "
          + (f"{n} parámetro(s)" if n else "sin configurar, se usará el 90% por defecto"))


def _permisos_ext(db) -> None:
    """Mallén escribe con su propio usuario. Sin permisos su ODBC falla al
    conectar, mucho antes de que VISTA vea nada."""
    n = db.execute(text('''
        SELECT COUNT(DISTINCT table_name) FROM information_schema.role_table_grants
        WHERE table_schema = 'ext' AND grantee = 'mallen_etl' ''')).scalar()
    total = db.execute(text("SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema = 'ext'")).scalar()
    if n and n >= total:
        print(f"{OK} usuario mallen_etl con permisos sobre las {total} tablas de ext")
    elif n:
        print(f"{MAL} mallen_etl solo tiene permisos sobre {n} de {total} tablas de ext")
    else:
        print(f"{MAL} el usuario mallen_etl no tiene permisos sobre ext "
              f"(¿se corrió crear_esquema_ext.sql?)")


def _correo() -> None:
    """El aviso de lote recibido es la única forma de enterarse sin mirar. Sin
    servidor de correo la integración funciona igual, pero en silencio.

    Se pregunta a `mail_config()`, NO a `settings.MAIL_SERVER`: la config que
    vale es la que el ADMIN guarda desde la pantalla de Administración (vive en
    la BD), y el `.env` es solo su respaldo. Leer el `.env` daría «sin correo»
    en cualquier servidor configurado por la interfaz — que son casi todos."""
    from app.services.notification_service import mail_config
    cfg = mail_config()
    if cfg["server"]:
        print(f"{OK} correo configurado ({cfg['server']}): "
              f"llegará el aviso de lote recibido")
    else:
        print(f"{AVISO} sin servidor de correo: no habrá aviso cuando llegue un lote")


def main() -> None:
    # Los códigos se pueden pasar por argumento para revisar países que TODAVÍA
    # NO EXISTEN en la base. Es lo que hace falta antes del primer lote: los
    # países los crea el envío de Mallén, pero los indicadores hay que darlos de
    # alta antes, y para eso hay que saber qué códigos van a llegar.
    pedidos = [a.strip().upper() for a in sys.argv[1:] if a.strip()]

    db = SessionLocal()
    try:
        print("\n=== GENERAL ===")
        _permisos_ext(db)
        _correo()

        paises = pedidos or _paises(db)
        if not paises:
            print("\n=== SIN PAÍSES QUE REVISAR ===")
            print("  VISTA no tiene ningún país y `ext` tampoco trae ninguno, así que")
            print("  NO SE REVISÓ NADA por país — que es donde está casi todo el")
            print("  checklist. Esto es lo normal antes del primer lote: los países los")
            print("  crea el propio envío de Mallén.")
            print("\n  Para revisar de todos modos, pasa los códigos que va a enviar:")
            print("    ... python - DO GT HN < backend/scripts/diagnostico_integracion_listo.py")
            print()
            return

        if pedidos:
            print(f"\n(revisando los países indicados: {', '.join(pedidos)})")
        for pais in paises:
            print(f"\n=== {pais} ===")
            _indicadores(db, pais)
            _categorizacion(db, pais)
            _ciclos(db, pais)
            _meta_cobertura(db, pais)
        print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
