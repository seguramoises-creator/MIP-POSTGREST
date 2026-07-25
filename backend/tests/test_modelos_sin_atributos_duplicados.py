"""Ningún modelo ORM debe declarar el mismo atributo dos veces (jul-2026).

REGRESIÓN: `cat.FactMedicoCategoriaSnapshot` declaraba `load_batch_key` DOS veces en el
cuerpo de la clase — arriba con `nullable=False` y otra vez al final, junto al
`relationship`, como `Mapped[Optional[int]]` sin `nullable`. Python conserva solo la última
asignación del cuerpo de clase, así que SQLAlchemy nunca vio la primera: la columna quedó
nullable, al revés de lo declarado. Y como el baseline crea las tablas con
`Base.metadata.create_all()`, esa contradicción se materializó en la BD real.

Es un fallo silencioso — no hay error, ni warning, ni test que falle: solo el modelo
mintiendo sobre su propio esquema. Se detecta por AST, sobre el cuerpo de cada clase de
`app/models/*.py`, para cubrir la clase de bug entera y no solo el caso que la destapó.
"""
import ast
from pathlib import Path

import pytest

_MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "models"
_ARCHIVOS = sorted(p for p in _MODELS_DIR.glob("*.py") if p.name != "__init__.py")


def _atributos_duplicados(cuerpo_clase) -> list[str]:
    """Nombres asignados más de una vez directamente en el cuerpo de la clase."""
    vistos, duplicados = set(), []
    for nodo in cuerpo_clase:
        # `x: Mapped[int] = mapped_column(...)` (AnnAssign) y `x = relationship(...)` (Assign)
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombres = [nodo.target.id]
        elif isinstance(nodo, ast.Assign):
            nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
        else:
            continue
        for nombre in nombres:
            if nombre in vistos:
                duplicados.append(nombre)
            vistos.add(nombre)
    return duplicados


@pytest.mark.parametrize("ruta", _ARCHIVOS, ids=lambda p: p.name)
def test_modelo_no_declara_el_mismo_atributo_dos_veces(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    hallazgos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ClassDef):
            for dup in _atributos_duplicados(nodo.body):
                hallazgos.append(f"{ruta.name}::{nodo.name}.{dup}")
    assert not hallazgos, (
        "Atributo declarado dos veces en el cuerpo de la clase; Python conserva solo la "
        "última y la primera se pierde sin aviso: " + ", ".join(hallazgos)
    )


def test_loadbatchkey_del_snapshot_es_not_null():
    """El caso concreto que originó la regla: un snapshot siempre pertenece a un lote."""
    from app.models.cat_models import FactMedicoCategoriaSnapshot

    columna = FactMedicoCategoriaSnapshot.__table__.c["LoadBatchKey"]
    assert columna.nullable is False
