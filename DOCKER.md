# 🐳 MSM / VISTA (SCGCPR) — Docker & despliegue en Linux

Guía para construir las imágenes, correr el sistema con Docker y desplegarlo en un
servidor Linux en la nube.

## Arquitectura

```
                    ┌─────────────────────────────┐
   navegador  ───►  │  frontend (nginx :80)        │
                    │  · sirve el SPA (Vite build) │
                    │  · proxy /api/v1 y /health ──┼──►  backend (uvicorn :8000)
                    └─────────────────────────────┘            │  FastAPI + pymssql
                                                                ▼
                                                        SQL Server (SCGCPR)
                                                   (externa/gestionada, o perfil with-db)
```

- **frontend**: imagen multi-stage (Node build → nginx). Único puerto público (**80**).
  Llama a la API *same-origin* (`/api/v1`); nginx la enruta al backend.
- **backend**: FastAPI/uvicorn con pymssql (FreeTDS). **No se publica** al exterior —
  solo lo alcanza el frontend dentro de la red Docker.
- **db** (opcional): SQL Server 2022 en contenedor (perfil `with-db`). Para producción
  real se recomienda una BD gestionada con respaldos.

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

# BD: si usas una SQL Server EXTERNA, pon su host/IP aquí.
# Si usas el SQL Server de este compose (perfil with-db): DB_SERVER=db, DB_USER=sa.
DB_SERVER=db
DB_PORT=1433
DB_NAME=SCGCPR
DB_USER=sa
DB_PASSWORD=Tu.Clave.Fuerte_2026

# Secreto JWT fuerte (genera uno nuevo para producción):
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET_KEY=__pega_un_secreto_largo__

# CORS: como el frontend es same-origin no es crítico, pero incluye tu dominio:
CORS_ORIGINS=["https://sistemamip.com","http://localhost"]

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

**Con SQL Server incluido** (self-hosted / prueba):
```bash
cp .env.docker.example .env          # define MSSQL_SA_PASSWORD aquí
docker compose --profile with-db up -d --build
```
> Si usas `with-db`, en `backend/.env`: `DB_SERVER=db`, `DB_USER=sa`,
> `DB_PASSWORD` = el mismo `MSSQL_SA_PASSWORD`.

Verifica:
```bash
docker compose ps
curl -s http://localhost/health        # {"status":"healthy",...}
```
Abre **http://localhost/** (o la IP del servidor).

## 4) Migraciones y datos iniciales

- Las **migraciones** corren solas al arrancar el backend (`RUN_MIGRATIONS=1`).
  Manualmente: `docker compose exec backend python -m alembic upgrade head`
- **Primera carga de datos** (BD vacía): crea el admin y carga catálogos:
  ```bash
  docker compose exec backend python scripts/setup/crear_admin.py
  # luego desde la web: /dims (importar DIM_MIP_FINAL.xlsx) y /etl (FACT_MIP_FINAL.xlsx)
  ```
- **Migrar tu BD actual** (recomendado): respalda tu `SCGCPR` local (.bak) y restáuralo
  en la BD de destino (gestionada o el contenedor `db`), para no perder los datos ya cargados.

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
# 5. Apuntar el DNS de sistemamip.com → IP del servidor
```

### TLS / HTTPS (sistemamip.com)
El frontend escucha en **80**. Pon un **terminador TLS delante**. Opción recomendada
(usa el nginx del host + Let's Encrypt, ya existe `deploy/linux/nginx_sistemamip.com.conf`):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
# nginx del host: reverse-proxy 443 → http://127.0.0.1:80 (el contenedor frontend)
# (deja el bloque location / -> proxy_pass http://127.0.0.1:80; y /api/v1 igual,
#  o más simple: proxy_pass http://127.0.0.1:80 para TODO, ya que el contenedor enruta)
sudo certbot --nginx -d sistemamip.com -d www.sistemamip.com
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
