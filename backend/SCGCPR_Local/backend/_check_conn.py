import sys
try:
    from app.db.database import check_db_connection
    ok = check_db_connection()
    sys.exit(0 if ok else 1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
