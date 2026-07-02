"""Semilla demo del modelo financiero Costo & ROI de Visita (línea 1, ciclo abierto).

Reproduce exactamente los valores de la maqueta de referencia:
  costo fijo/visita = 385 · costo variable/visita = 8.117 · ROI promedio = 21,14x
  pool total = 34.150.000 · riesgo de venta = 567.280 – 992.740 · headcount = 0,51

Uso:  python scripts/seed_costo_visita.py  [linea_id]   (por defecto línea 1)
Idempotente: usa el patrón delete-then-insert del propio servicio.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Importar todos los modelos para resolver relaciones ORM entre esquemas.
from app.models import usuario, dimensiones, hechos, visita  # noqa: F401
from app.db.database import SessionLocal
from app.schemas.visita import CostoEstructuraGuardar, CostoProductoItem
from app.services import visita_costo_service
from app.services.visita_cobertura_service import ciclo_por_defecto

LINEA_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1

# Estructura de costo del representante (VM representativo de la línea).
ESTRUCTURA = dict(
    moneda="RD$",
    salario_mensual=45000, cargas_pct=32, viaticos_dia=850, materiales_ciclo=3200,
    dias_campo=19, total_visitas=190, dias_mes=21,
    visitadores=8, visitas_ciclo_vm=190, ciclos_anio=11,
    coef_conservador=0.40, coef_optimista=0.70,
    psp_a=28000, psp_b=12500, psp_c=4800,
    med_sin_visitar_a=26, med_sin_visitar_b=46, med_sin_visitar_c=24,
)

# (código, costo_unit_muestra, cantidad_muestras, pool_ventas, visitas_detalladas, presupuesto_anual, precio_prom)
DATA = [
    ("ONCX-301", 480, 1496, 12_700_000, 1100, 139_680_000, 4200),
    ("CARDIEX-5", 210, 1928, 8_160_000, 1350, 89_760_000, 850),
    ("LIPITOR-20", 155, 1072, 6_120_000, 1050, 67_320_000, 620),
    ("NEUREX-10", 390, 536, 4_660_000, 800, 51_260_000, 2100),
    ("METABLOCK", 125, 352, 2_510_000, 580, 27_640_000, 480),
]


def main() -> None:
    db = SessionLocal()
    try:
        # Mismo ciclo que resuelve el endpoint (calcular_full → ciclo_por_defecto),
        # para que el seed alimente exactamente lo que ve la UI.
        ciclo_id = ciclo_por_defecto(db)
        if not ciclo_id:
            raise SystemExit("No hay ciclo abierto para sembrar.")
        productos = [
            CostoProductoItem(
                producto=cod, orden=i, costo_unitario_muestra=cu, cantidad_muestras=cm,
                pool_ventas=pool, visitas_detalladas=vd, presupuesto_anual=pa, precio_prom=pp,
            )
            for i, (cod, cu, cm, pool, vd, pa, pp) in enumerate(DATA, start=1)
        ]
        datos = CostoEstructuraGuardar(
            ciclo_id=ciclo_id, linea_id=LINEA_ID, productos=productos, **ESTRUCTURA
        )
        full = visita_costo_service.guardar_estructura(db, datos, usuario_id=None)
        print(f"Sembrado ciclo {ciclo_id} línea {LINEA_ID}: {len(DATA)} productos")
        print(f"  costo fijo/visita   = {full['fijo']['costo_fijo_visita']}")
        print(f"  costo var/visita    = {full['muestras']['costo_variable_visita']}")
        print(f"  pool total          = {full['pool']['pool_total']}")
        print(f"  ROI promedio        = {full['resumen']['roi_promedio']}x")
        print(f"  riesgo venta        = {full['impacto']['venta_riesgo_bajo']} – {full['impacto']['venta_riesgo_alto']}")
        print(f"  headcount equiv.    = {full['impacto']['headcount_equivalente']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
