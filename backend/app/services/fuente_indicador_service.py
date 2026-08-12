"""Quién alimenta EVAL_CONOCIMIENTOS en cada país.

POR QUÉ EXISTE ESTE MÓDULO
--------------------------
Tres caminos escriben el mismo indicador —los exámenes de VISTA, las notas que
Mallén deja en `ext`, y la captura manual— y los tres hacen delete-then-insert
sobre `(rm_id, indicador_id, ciclo_id)`. Sin un dueño declarado gana el último
en correr: no hay error, no hay aviso, solo un número distinto según el orden en
que alguien pulse los botones.

La regla vive AQUÍ y en ningún otro sitio. Repartir la comprobación por los tres
caminos es exactamente cómo se vuelven a desincronizar.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.dimensiones import FuenteIndicador

INDICADOR_CONOCIMIENTOS = "EVAL_CONOCIMIENTOS"

FUENTE_EXAMEN_VISTA = "EXAMEN_VISTA"
FUENTE_NOTA_EXTERNA = "NOTA_EXTERNA"
FUENTE_CAPTURA_MANUAL = "CAPTURA_MANUAL"

#: Las tres, y solo las tres. `EXCEL` NO está: no es que hoy no sea el dueño, es
#: que dejó de ser una vía (decisión del cliente, 12-ago-2026).
FUENTES: tuple[str, ...] = (FUENTE_EXAMEN_VISTA, FUENTE_NOTA_EXTERNA,
                            FUENTE_CAPTURA_MANUAL)

#: Un país sin configurar captura a mano, que es lo más parecido a lo que hacía
#: el Excel. Devolver un error obligaría a configurar antes de poder trabajar.
FUENTE_POR_DEFECTO = FUENTE_CAPTURA_MANUAL


class FuenteAjenaError(Exception):
    """Alguien que no es el dueño intentó escribir el indicador."""

    def __init__(self, pais_codigo: str, indicador_codigo: str,
                 duenio: str, intento: str):
        self.pais_codigo = pais_codigo
        self.indicador_codigo = indicador_codigo
        self.duenio = duenio
        self.intento = intento
        super().__init__(
            f"En {pais_codigo}, {indicador_codigo} lo alimenta «{duenio}»; "
            f"«{intento}» no puede escribirlo. Si esa es la decisión, cambia la "
            f"fuente en la pantalla de Conocimientos.")


def fuente_de(db: Session, pais_codigo: str,
              indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> str:
    fila = (db.query(FuenteIndicador)
            .filter(FuenteIndicador.pais_codigo == pais_codigo,
                    FuenteIndicador.indicador_codigo == indicador_codigo).first())
    return fila.fuente if fila is not None else FUENTE_POR_DEFECTO


def asegurar_duenio(db: Session, pais_codigo: str, fuente_que_escribe: str,
                    indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> None:
    """Levanta `FuenteAjenaError` si quien va a escribir no es el dueño.

    El error NOMBRA al dueño real: un «no tienes permiso» deja al operador sin
    saber qué cambiar ni dónde.
    """
    actual = fuente_de(db, pais_codigo, indicador_codigo)
    if actual != fuente_que_escribe:
        raise FuenteAjenaError(pais_codigo, indicador_codigo, actual,
                               fuente_que_escribe)


def fijar_fuente(db: Session, pais_codigo: str, fuente: str,
                 usuario_id: int | None,
                 indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> FuenteIndicador:
    """Declara el dueño. No hace commit: lo decide el llamador."""
    if fuente not in FUENTES:
        raise ValueError(
            f"«{fuente}» no es una fuente válida. Las únicas son: "
            f"{', '.join(FUENTES)}.")
    fila = (db.query(FuenteIndicador)
            .filter(FuenteIndicador.pais_codigo == pais_codigo,
                    FuenteIndicador.indicador_codigo == indicador_codigo).first())
    if fila is None:
        fila = FuenteIndicador(pais_codigo=pais_codigo,
                               indicador_codigo=indicador_codigo)
        db.add(fila)
    fila.fuente = fuente
    fila.actualizado_en = datetime.now(timezone.utc)
    fila.actualizado_por_usuario_id = usuario_id
    db.flush()
    return fila
