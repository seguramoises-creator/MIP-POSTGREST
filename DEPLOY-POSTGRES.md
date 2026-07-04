# 🐳 MSM / VISTA (SCGCPR) — Docker & despliegue en Linux · EDICIÓN PostgreSQL

Guía para construir las imágenes, correr el sistema con Docker y desplegarlo en un
servidor Linux en la nube. **Esta es la edición PostgreSQL** (motor de cálculo 100%
Python, BD PostgreSQL 14+). Para clientes que ya usan SQL Server existe una edición
gemela con la BD en contenedor SQL Server.

## Arquitectura

```
                    ┌─────────────────────────────┐
   navegador  ───►  │  frontend (nginx :80)        │
                    │  · sirve el SPA (Vite build) │
                    │  · proxy /api/v1 y /health ──┼──►  backend (uvicorn :8000)
                    └─────────────────────────────┘            │  FastAPI + psycopg2
                                                                ▼
                                                        PostgreSQL (scgcpr)
                                                   (externa/gestionada, o perfil with-db)
```

- **frontend**: imagen multi-stage (Node build → nginx). Único puerto público (**80**).
  Llama a la API *same-origin* (`/api/v1`); nginx la enruta al backend.
- **backend**: FastAPI/uvicorn con **psycopg2** (libpq embebido, sin paquetes de sistema).
  **No se publica** al exterior — solo lo alcanza el frontend dentro de la red Docker.
- **db** (opcional): **PostgreSQL 17** en contenedor (perfil `with-db`), con healthcheck
  `pg_isready` para que el backend espere a que la BD esté lista antes de migrar. Para
  producción real se recomienda una BD gestionada con respaldos (RDS, Cloud SQL, etc.).

## Archivos

| Archivo | Para qué |
|---------|----------|
| `backend/Dockerfile` · `backend/docker-entrypoint.sh` · `backend/.dockerignore` | Imagen del backend (corre migraciones + uvicorn) |
| `frontend/Dockerfile` · `frontend/nginx.conf` · `frontend/.dockerignore` | Imagen del frontend (build + nginx proxy) |
| `docker-compose.yml` | Orquestación |
| `.env.docker.example` | Variables de compose (copiar a `.env`) |
| `backend/.env` | **Config de la app** (DB, JWT, MAIL, ANTHROPIC, CORS) — NO se commitea |

---

## 1) Requisitos

- Docker Engine 24+ y el plugin `docker compose` v2.
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER && newgrp docker
  ```

## 2) Configurar la app (`backend/.env`)

Copia `backend/.env.example` → `backend/.env` y ajusta. Claves importantes para Docker:

```env
APP_ENV=production
DEBUG=false

# BD: si usas un PostgreSQL EXTERNO, pon su host/IP aquí.
# Si usas el PostgreSQL de este compose (perfil with-db): DB_SERVER=db.
DB_SERVER=db
DB_PORT=5432
DB_NAME=scgcpr
DB_USER=segura
DB_PASSWORD=Tu.Clave.Fuerte_2026

# Secreto JWT fuerte (genera uno nuevo para producción):
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET_KEY=__pega_un_secreto_largo__

# CORS: como el frontend es same-origin no es crítico, pero incluye tu dominio:
CORS_ORIGINS=["https://vista-mip.com","http://localhost"]

# Correo (Gmail App Password) y IA (opcional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=tucorreo@gmail.com
MAIL_PASSWORD=__app_password__
ANTHROPIC_API_KEY=__opcional__
EXAMEN_IA_DEMO=false
```

## 3) Levantar

**Con BD externa/gestionada** (DB_SERVER apunta a ella en `backend/.env`):
```bash
docker compose up -d --build
```

**Con PostgreSQL incluido** (self-hosted / prueba):
```bash
cp .env.docker.example .env          # define DB_NAME/DB_USER/POSTGRES_PASSWORD aquí
docker compose --profile with-db up -d --build
```
> Si usas `with-db`, en `backend/.env`: `DB_SERVER=db`, y `DB_NAME`/`DB_USER`/`DB_PASSWORD`
> deben coincidir con `DB_NAME`/`DB_USER`/`POSTGRES_PASSWORD` del `.env` raíz.

Verifica:
```bash
docker compose ps
curl -s http://localhost:8090/health   # {"status":"healthy",...}  (puerto FRONTEND_PORT)
```
Abre **http://<IP-del-servidor>:8090/** (o, tras configurar TLS, `https://vista-mip.com`).
> El frontend se publica en `FRONTEND_PORT` (default **8090**), no en 80, para no chocar
> con otros stacks del servidor. El Postgres del contenedor **no** se publica al host.

## 4) Migraciones y datos iniciales

- Las **migraciones** corren solas al arrancar el backend (`RUN_MIGRATIONS=1`).
  El backend espera al healthcheck de la BD (`with-db`) antes de migrar.
  Manualmente: `docker compose exec backend python -m alembic upgrade head`
- **Primera carga de datos** (BD vacía): crea el admin y carga catálogos:
  ```bash
  docker compose exec backend python scripts/setup/crear_admin_pg.py
  # luego desde la web: /dims (importar DIM_MIP_FINAL.xlsx) y /etl (FACT_MIP_FINAL.xlsx)
  ```
  > `crear_admin_pg.py` siembra el usuario `admin` / `Admin1234!` vía SQLAlchemy
  > (sin dependencias de SQL Server). Cambia la contraseña tras el primer login.

---

## 5) Despliegue en el servidor Linux de la nube

```bash
# 1. En el servidor (Ubuntu/Debian): instalar Docker (ver §1)
# 2. Clonar el repo y entrar
git clone <tu-repo> /opt/msm && cd /opt/msm
# 3. Configurar backend/.env (paso 2) con la BD/JWT/MAIL reales de producción
nano backend/.env
# 4. Construir y levantar
docker compose up -d --build       # (o --profile with-db si la BD va en contenedor)
# 5. Apuntar el DNS de vista-mip.com → IP del servidor
```

### TLS / HTTPS (vista-mip.com)
El frontend escucha en **80**. Pon un **terminador TLS delante**. Opción recomendada
(usa el nginx del host + Let's Encrypt, ya existe `deploy/linux/nginx_vista-mip.com.conf`):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
# server block para vista-mip.com:  proxy_pass http://127.0.0.1:8090;  (el contenedor frontend, FRONTEND_PORT)
sudo certbot --nginx -d vista-mip.com -d www.vista-mip.com
```
> Alternativa "todo-en-uno": añadir un contenedor **Caddy** como reverse-proxy con
> HTTPS automático (`caddy reverse-proxy`), apuntando a `frontend:80`.

---

## 6) Operación

```bash
docker compose logs -f backend          # logs del backend
docker compose logs -f frontend         # logs de nginx
docker compose restart backend          # reiniciar un servicio
docker compose down                     # parar (mantiene volúmenes/datos)
docker compose exec backend sh          # shell dentro del backend

# Actualizar a una versión nueva del código:
git pull && docker compose up -d --build

# Respaldo de la BD (perfil with-db):
docker compose exec db pg_dump -U segura scgcpr | gzip > scgcpr_backup.sql.gz
# Restaurar:
gunzip -c scgcpr_backup.sql.gz | docker compose exec -T db psql -U segura -d scgcpr

# Respaldo de subidas/reportes (volúmenes):
docker run --rm -v msm_backend_uploads:/data -v "$PWD":/bk alpine \
  tar czf /bk/uploads_backup.tgz -C /data .
```

## 7) Notas

- **Secretos**: `backend/.env` y el `.env` raíz están en `.gitignore` — nunca se commitean
  ni se hornean en la imagen (se inyectan en runtime vía `env_file`).
- **Persistencia**: `uploads`, `reports`, `logs` y la BD (`with-db`) viven en volúmenes Docker.
- **bcrypt**: el Dockerfile fija `bcrypt==3.2.2` (fix passlib, CLAUDE.md §21).
- **Subidas grandes**: `client_max_body_size 100M` en nginx (Excel ETL/DIMs hasta 50 MB).
- **Motor de cálculo**: 100% Python (sin stored procedures). El baseline
  `0001_baseline_postgres` crea los 9 esquemas y todas las tablas desde los modelos ORM.
