# backend/scripts/

Utilidades de desarrollo, diagnóstico y mantenimiento puntual. **No** forman parte
del runtime de la aplicación (la API es `app/`). Se ejecutan a mano cuando hace falta.

## Estructura

| Carpeta | Propósito |
|---------|-----------|
| `setup/` | Inicialización de BD y datos (`_crear_bd.py`, `_crear_tablas.py`, `crear_admin.py`, `_reset_datos.py`, …) |
| `diagnostics/` | Inspección de estado: conteos, conexión, ciclos, KPIs, ranking (`check_*.py`, `diagnostico_*.py`, `diag*.py`, `*.sql`) |
| `fixes/` | Correcciones puntuales y migraciones ad-hoc ya aplicadas (`fix_*.py`, `aplicar_migracion_*.py`, `corregir_*.ps1`, …) |

## Cómo ejecutar

Ejecutar siempre con el venv activo. Los scripts que importan el paquete `app`
llevan un *bootstrap* de `sys.path` al inicio, así funcionan desde su subcarpeta:

```powershell
cd C:\Users\Lenovo\Proyecto\MSM\backend
.\venv\Scripts\activate
python scripts\diagnostics\diagnostico_db.py
```

## Credenciales (parametrizadas)

Estos scripts **ya no tienen credenciales hardcodeadas**: leen la conexión desde
`backend/.env` (`DB_SERVER`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) mediante
un bootstrap con `python-dotenv` al inicio del archivo. Por eso son seguros de
versionar. Para correrlos, basta con tener `backend/.env` configurado y el venv activo.
