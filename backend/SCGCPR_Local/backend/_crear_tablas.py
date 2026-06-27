import sys
try:
    from app.db.database import init_db
    init_db()
    print("  Tablas creadas.")
    sys.exit(0)
except Exception as e:
    print(f"  Advertencia: {e}")
    sys.exit(0)
