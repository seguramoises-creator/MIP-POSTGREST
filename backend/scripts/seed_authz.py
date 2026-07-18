"""Siembra la matriz RBAC en la BD (Security.DIM_Recurso + FACT_RolPermiso). Idempotente.

Uso: python scripts/seed_authz.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ al path

from app.db.database import SessionLocal  # noqa: E402
from app.core.authz.seed import sembrar_todo  # noqa: E402

if __name__ == "__main__":
    db = SessionLocal()
    try:
        print(sembrar_todo(db))
    finally:
        db.close()
