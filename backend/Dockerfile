# ─────────────────────────────────────────────────────────────
# Backend MSM / VISTA (SCGCPR) — FastAPI + uvicorn (pymssql/FreeTDS)
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# pymssql requiere FreeTDS (libsybdb) en runtime; gcc por si toca compilar.
RUN apt-get update && apt-get install -y --no-install-recommends \
        freetds-dev freetds-bin gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    # Fix conocido (CLAUDE.md §21): passlib 1.7.4 + bcrypt 4.x lanza
    # "password cannot be longer than 72 bytes". Forzar bcrypt 3.2.2.
    && pip install "bcrypt==3.2.2"

COPY . .

# Directorios de runtime (se montan como volúmenes en compose para persistir)
RUN mkdir -p uploads processed errors reports logs \
    && chmod +x docker-entrypoint.sh

EXPOSE 8000

# El entrypoint corre migraciones Alembic (opcional) y arranca uvicorn.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
