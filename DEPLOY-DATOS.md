# Runbook — Deploy de código y migración de datos (local → servidor)

Servidor: `ssh moises@2.25.177.90`, directorio `/opt/msm-pg`, stack Docker (`--profile with-db`).
La app queda en `https://vista-mip.com` (nginx del frontend en `:8095` → proxy `/api/v1` → backend).

---

## A) Deploy de solo código (lo habitual)

```bash
ssh moises@2.25.177.90
cd /opt/msm-pg
git pull
docker compose --profile with-db up -d --build   # migraciones Alembic corren solas al arrancar
```
Luego en el navegador: **hard refresh** (Ctrl+Shift+R) para descartar el frontend cacheado.

Verificación:
```bash
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').status)"  # 200
docker compose exec db psql -U segura -d scgcpr -c "SELECT version_num FROM alembic_version;"                                        # head
```

---

## B) Copiar TODOS los datos locales al servidor (reemplaza la BD del servidor)

⚠️ **Destructivo**: el paso 4 borra la BD actual del servidor y la reemplaza por tu copia local.
Haz respaldo del servidor antes si tiene datos que conservar.

**1. Generar el dump en tu PC (Windows)** — pg_dump 17:
```powershell
cd C:\Users\Lenovo\Proyecto\MSM-postgres\backend
$env:PGPASSWORD = (python -c "from app.core.config import settings; print(settings.DB_PASSWORD)")
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h 127.0.0.1 -p 5432 -U segura -Fc --no-owner --no-acl -f ..\scgcpr.dump scgcpr
Remove-Item Env:PGPASSWORD
```

**2. Transferir el dump** (terminal LOCAL, no dentro del SSH):
```powershell
cd C:\Users\Lenovo\Proyecto\MSM-postgres
scp scgcpr.dump moises@2.25.177.90:/opt/msm-pg/
```

**3. Respaldo del servidor (opcional pero recomendado)**:
```bash
docker compose exec db pg_dump -U segura -Fc scgcpr > /opt/msm-pg/backup_servidor_$(date +%F).dump
```

**4. Restaurar en el servidor**:
```bash
cd /opt/msm-pg
docker compose cp scgcpr.dump db:/tmp/scgcpr.dump
docker compose stop backend
docker compose exec db psql -U segura -d postgres -c "DROP DATABASE IF EXISTS scgcpr WITH (FORCE);"
docker compose exec db psql -U segura -d postgres -c "CREATE DATABASE scgcpr OWNER segura;"
docker compose exec db pg_restore -U segura -d scgcpr --no-owner --no-acl /tmp/scgcpr.dump
docker compose start backend   # alembic verá el head del dump = no-op
```

**5. Verificar**:
```bash
docker compose exec db psql -U segura -d scgcpr -c "SELECT (SELECT COUNT(*) FROM \"Visita\".\"FactVisita\") AS visitas, (SELECT COUNT(*) FROM \"Config\".\"DIM_Ciclo\" WHERE cerrado=false) AS ciclos_abiertos;"
```

> El dump `scgcpr.dump` NO se versiona (está en `.gitignore`). Contiene datos; no lo commitees.

---

## Correcciones de datos puntuales (ya incorporadas al dump si se generó después de aplicarlas)

- `scripts/fix_medico_alta.py` — corrige el `ciclo_alta_id` de los médicos importados (artefacto que
  dejaba el panel de Cobertura Visita en 0). Correr **una vez** en el servidor si NO copiaste el dump:
  `docker compose exec backend python scripts/fix_medico_alta.py`
- `scripts/seed_visita_demo_do.py` — SOLO datos demo. **No** correr en producción real.
