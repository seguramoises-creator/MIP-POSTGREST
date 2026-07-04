# MSM / SCGCPR — Procedimiento de Instalación y Despliegue en Producción

Dominio público objetivo: **https://vista-mip.com**

Este documento cubre dos rutas de despliegue equivalentes:

- **Ruta A — Windows Server con IIS** (ARR + URL Rewrite como proxy inverso)
- **Ruta B — Linux (VPS) con nginx** (alternativa para cualquier servidor Linux)

En ambas rutas, la aplicación Python (FastAPI/Uvicorn) corre internamente en
`127.0.0.1:8000` y el servidor web (IIS o nginx) es el único punto expuesto a
Internet, actuando como proxy inverso y terminando TLS/HTTPS.

```
Internet ──HTTPS──▶ IIS / nginx (puerto 443, dominio vista-mip.com)
                        │
                        ├─▶ archivos estáticos (frontend/dist) — servidos directo
                        │
                        └─▶ proxy inverso /api/v1/*, /health ──▶ 127.0.0.1:8000
                                                                  (Uvicorn, FastAPI)
                                                                       │
                                                                       ▼
                                                              SQL Server (SCGCPR)
```

Todos los archivos de configuración mencionados aquí están en `deploy/`:

```
deploy/
├── DEPLOYMENT.md                       ← este documento
├── windows/
│   ├── web.config                      ← config IIS (proxy + SPA + HTTPS)
│   ├── configurar_iis_arr.ps1          ← habilita ARR/proxy a nivel servidor
│   ├── instalar_servicio_backend.ps1   ← instala backend como servicio (NSSM)
│   ├── desinstalar_servicio_backend.ps1
│   ├── build_frontend_produccion.ps1   ← build Vite + publicación en IIS
│   └── generar_jwt_secret.ps1
└── linux/
    ├── msm-backend.service             ← unidad systemd
    ├── nginx_vista-mip.com.conf              ← config nginx (proxy + SPA + HTTPS)
    ├── instalar_servicio_backend.sh
    └── build_frontend_produccion.sh

backend/.env.production.example         ← plantilla de variables de entorno
```

---

## 0. Requisitos previos (ambas rutas)

- Código del proyecto copiado al servidor (ej. `git clone` o copia del ZIP) en
  `C:\Users\Lenovo\Proyecto\MSM` (Windows) o `/opt/msm` (Linux).
- Acceso a una instancia de **SQL Server** alcanzable desde el servidor de
  aplicación (puede ser la misma máquina o una instancia dedicada).
- **Python 3.13** instalado en el servidor.
- **Node.js 18+** y npm instalados (solo se necesitan para compilar el
  frontend; no se requieren en tiempo de ejecución).
- Un registro DNS tipo **A** (o **CNAME**) para `vista-mip.com` (y opcionalmente
  `www.vista-mip.com`) apuntando a la IP pública del servidor.
- Certificado TLS para `vista-mip.com`:
  - Producción: certificado de una CA pública (ej. Let's Encrypt, gratuito)
  - Pruebas internas: certificado autofirmado (instrucciones en cada ruta)

---

## 1. Configurar el backend para producción (ambas rutas)

1. Copie la plantilla de entorno:
   - Windows: `copy backend\.env.production.example backend\.env`
   - Linux: `cp backend/.env.production.example backend/.env`

2. Edite `backend/.env` y complete:
   - `DB_SERVER`, `DB_USER`, `DB_PASSWORD` → credenciales reales de la BD de producción
   - `JWT_SECRET_KEY` → genere uno fuerte y único:
     - Windows: `deploy\windows\generar_jwt_secret.ps1`
     - Linux/macOS: `openssl rand -base64 48`
   - Confirme `APP_ENV=production`, `DEBUG=false`
   - Confirme `CORS_ORIGINS=["https://vista-mip.com","https://www.vista-mip.com"]`
   - Confirme `ALLOWED_HOSTS=["vista-mip.com","www.vista-mip.com","localhost","127.0.0.1"]`

   > **Crítico:** si `vista-mip.com` no está en `ALLOWED_HOSTS`, el middleware
   > `TrustedHostMiddleware` (activo solo cuando `APP_ENV=production`)
   > rechazará con HTTP 400 **todas** las peticiones que lleguen con
   > `Host: vista-mip.com`. Esto ya viene configurado por defecto en
   > `app/core/config.py`, pero verifíquelo si cambia el dominio.

3. Cree el entorno virtual e instale dependencias (si no existe):
   ```
   cd backend
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt      (Windows)
   venv/bin/pip install -r requirements.txt          (Linux)
   ```
   En Windows recuerde el fix conocido de bcrypt (sección 17 de CLAUDE.md):
   `venv\Scripts\pip install bcrypt==3.2.2`

4. Inicialice/migre la base de datos si es la primera vez:
   ```
   venv\Scripts\python _crear_tablas.py
   venv\Scripts\python _crear_bd.py
   venv\Scripts\python -m alembic upgrade head
   ```

5. Pruebe el arranque manualmente antes de instalarlo como servicio:
   ```
   venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   Verifique `http://127.0.0.1:8000/health` responde `{"status":"healthy",...}`,
   luego deténgalo con Ctrl+C y continúe con la ruta de su servidor.

---

## Ruta A — Windows Server + IIS (ARR + URL Rewrite)

### A.1 Instalar IIS y los módulos ARR / URL Rewrite

1. Si IIS no está instalado, instale el rol **Web Server (IIS)** desde
   *Server Manager → Add Roles and Features* (o ejecute el paso 1 de
   `deploy\windows\configurar_iis_arr.ps1`, que lo hace automáticamente
   en Windows Server).
2. Descargue e instale (requieren instalador gráfico, no se pueden scriptear
   sin Web Platform Installer):
   - **Application Request Routing 3.0**: https://www.iis.net/downloads/microsoft/application-request-routing
   - **URL Rewrite Module 2.1**: https://www.iis.net/downloads/microsoft/url-rewrite
3. Reinicie IIS tras instalar ambos módulos: `iisreset`

### A.2 Habilitar el proxy de ARR a nivel de servidor

Ejecute como Administrador, **una sola vez por servidor**:
```powershell
cd C:\Users\Lenovo\Proyecto\MSM\deploy\windows
.\configurar_iis_arr.ps1
```
Esto habilita `system.webServer/proxy` y, de forma crítica, `preserveHostHeader=True`
(sin esto, IIS reemplaza el encabezado `Host` por `127.0.0.1:8000` antes de
reenviar al backend, y `ALLOWED_HOSTS` lo rechazaría).

Alternativa manual (IIS Manager): nodo del servidor → *Application Request
Routing Cache* → *Server Proxy Settings* → marcar **Enable proxy**, y en
*Advanced Settings* confirmar `preserveHostHeader = True`.

### A.3 Instalar el backend como servicio de Windows (NSSM)

1. Descargue NSSM desde https://nssm.cc/download y extraiga `nssm.exe`
   (use la versión `win64`) a, por ejemplo, `C:\Tools\nssm\nssm.exe`.
2. Ejecute como Administrador:
   ```powershell
   cd C:\Users\Lenovo\Proyecto\MSM\deploy\windows
   .\instalar_servicio_backend.ps1 -NssmPath "C:\Tools\nssm\nssm.exe"
   ```
3. Verifique: abra `http://127.0.0.1:8000/health` en el propio servidor —
   debe responder JSON con `"status":"healthy"`.
4. El servicio se llama `MSM-Backend`; gestiónelo con:
   ```
   C:\Tools\nssm\nssm.exe restart MSM-Backend
   C:\Tools\nssm\nssm.exe stop MSM-Backend
   Get-Service MSM-Backend
   ```
   Logs en `backend\logs\service_stdout.log` / `service_stderr.log`.

### A.4 Compilar el frontend y publicarlo en IIS

```powershell
cd C:\Users\Lenovo\Proyecto\MSM\deploy\windows
.\build_frontend_produccion.ps1 -DominioPublico "https://vista-mip.com" -DestinoIIS "C:\inetpub\wwwroot\mip"
```
Esto compila el frontend con `VITE_API_URL=https://vista-mip.com/api/v1` (en vez
del valor de desarrollo `http://127.0.0.1:8000/api/v1`) y copia el resultado
junto con `web.config` a `C:\inetpub\wwwroot\mip`.

### A.5 Crear el sitio en IIS Manager

1. *Sites → Add Website*:
   - **Site name**: `vista-mip.com`
   - **Physical path**: `C:\inetpub\wwwroot\mip`
   - **Binding**: Type `https`, Host name `vista-mip.com`, puerto `443`,
     seleccione el certificado SSL (ver A.6)
2. Agregue un segundo binding `http`/puerto `80`/host `vista-mip.com` — necesario
   para que la regla "Redirigir HTTP a HTTPS" del `web.config` pueda
   procesar la petición antes de redirigir (si no, el navegador nunca llega
   a IIS en el puerto 80).
3. Repita los bindings para `www.vista-mip.com` si aplica.
4. Confirme que el *Application Pool* del sitio usa **"No Managed Code"**
   (el sitio es estático + proxy, no necesita .NET CLR).

### A.6 Certificado TLS

- **Producción (CA pública)**: solicite/importe el certificado de `vista-mip.com`
  en el almacén de certificados del servidor (*Server Certificates* en IIS
  Manager → *Import* o *Create Certificate Request*), luego selecciónelo en
  el binding HTTPS del paso A.5. Si usa un proveedor compatible con ACME,
  puede automatizar la renovación con `win-acme` (https://www.win-acme.com/).
- **Pruebas internas (autofirmado)**:
  ```powershell
  New-SelfSignedCertificate -DnsName "vista-mip.com","www.vista-mip.com" `
      -CertStoreLocation "cert:\LocalMachine\My" -NotAfter (Get-Date).AddYears(2)
  ```
  Luego selecciónelo en el binding HTTPS. Los navegadores mostrarán una
  advertencia de certificado no confiable — esperado en este escenario.

### A.7 DNS

Cree un registro **A** para `vista-mip.com` (y `www.vista-mip.com` si aplica) apuntando
a la IP pública del servidor Windows. Verifique propagación con
`nslookup vista-mip.com` desde una máquina externa.

### A.8 Verificación end-to-end

```
https://vista-mip.com/                  → debe cargar el SPA (login de MSM)
https://vista-mip.com/health            → {"status":"healthy",...}
https://vista-mip.com/api/v1/docs       → Swagger UI
http://vista-mip.com/                   → debe redirigir (301) a https://vista-mip.com/
```
Pruebe un login real y navegue 2-3 pantallas que llamen a la API para
confirmar que el proxy reenvía correctamente `/api/v1/*`.

---

## Ruta B — Linux (VPS) + nginx

### B.1 Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx nodejs npm
```
(En distribuciones basadas en RHEL/CentOS use `dnf`/`yum` con los paquetes equivalentes.)

### B.2 Copiar el proyecto y configurar el backend

```bash
sudo mkdir -p /opt/msm
sudo cp -r /ruta/al/repo/* /opt/msm/
cd /opt/msm/backend
cp .env.production.example .env
nano .env   # complete DB_*, JWT_SECRET_KEY, etc. (ver sección 1 de este documento)
```

### B.3 Instalar el backend como servicio systemd

```bash
cd /opt/msm/deploy/linux
chmod +x instalar_servicio_backend.sh build_frontend_produccion.sh
sudo ./instalar_servicio_backend.sh /opt/msm
```
Verifique:
```bash
curl -s http://127.0.0.1:8000/health
sudo systemctl status msm-backend
```

### B.4 Compilar el frontend

```bash
./build_frontend_produccion.sh /opt/msm https://vista-mip.com
```
El build queda en `/opt/msm/frontend/dist`, que es exactamente el `root`
configurado en `nginx_vista-mip.com.conf`.

### B.5 Configurar nginx

```bash
sudo cp /opt/msm/deploy/linux/nginx_vista-mip.com.conf /etc/nginx/sites-available/vista-mip.com.conf
sudo ln -s /etc/nginx/sites-available/vista-mip.com.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # evita conflicto con el sitio por defecto
sudo nginx -t
```

### B.6 Certificado TLS con Let's Encrypt

```bash
sudo certbot --nginx -d vista-mip.com -d www.vista-mip.com
```
Certbot edita automáticamente `vista-mip.com.conf` con las rutas del certificado
y configura la renovación automática (vía systemd timer / cron).

```bash
sudo systemctl reload nginx
```

### B.7 DNS

Igual que en la Ruta A: registro **A** de `vista-mip.com` (y `www.vista-mip.com`) hacia
la IP pública del VPS.

### B.8 Verificación end-to-end

```bash
curl -I https://vista-mip.com/
curl -s https://vista-mip.com/health
curl -s https://vista-mip.com/api/v1/openapi.json | head -c 200
```

---

## 2. Actualizaciones posteriores (ambas rutas)

Cada vez que se despliegue una nueva versión del código:

1. Backend: actualizar el código, `pip install -r requirements.txt` si
   cambiaron dependencias, aplicar migraciones (`alembic upgrade head`),
   y reiniciar el servicio:
   - Windows: `nssm restart MSM-Backend`
   - Linux: `sudo systemctl restart msm-backend`
2. Frontend: volver a ejecutar el script de build correspondiente
   (`build_frontend_produccion.ps1` / `.sh`) — **necesario incluso si solo
   cambió el backend pero se modificó `VITE_API_URL` o el dominio**.

---

## 3. Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `400 Bad Request` en todas las rutas tras activar producción | `Host` recibido no está en `ALLOWED_HOSTS`, o IIS no preserva el Host header | Verificar `ALLOWED_HOSTS` en `.env`; en IIS confirmar `preserveHostHeader=True` (paso A.2) |
| El SPA carga pero las llamadas a la API fallan (CORS) | `CORS_ORIGINS` no incluye `https://vista-mip.com` | Editar `backend/.env`, agregar el origen exacto (con esquema), reiniciar el servicio |
| El frontend llama a `127.0.0.1:8000` en vez de `vista-mip.com` desde el navegador | El build se hizo sin `VITE_API_URL` de producción (build viejo) | Re-ejecutar `build_frontend_produccion.ps1`/`.sh` con el dominio correcto |
| `JWT_SECRET_KEY inseguro en producción` al arrancar | Se dejó el valor de desarrollo o uno corto | Generar uno nuevo (`generar_jwt_secret.ps1` o `openssl rand -base64 48`) |
| 502/504 al llamar `/api/v1/*` desde el dominio público | El backend no está corriendo en `127.0.0.1:8000`, o el firewall local bloquea loopback | `Get-Service MSM-Backend` / `systemctl status msm-backend`; revisar logs en `backend/logs/` |
| Rutas de React Router (ej. `/dashboard/ejecutivo`) dan 404 al refrescar la página | Falta la regla de SPA fallback | Confirmar que `web.config`/`nginx_vista-mip.com.conf` están realmente publicados en el sitio activo |
| Subida de Excel grande falla con 413 | Límite de tamaño del proxy menor a `ETL_MAX_FILE_SIZE_MB` | Ajustar `maxAllowedContentLength` (web.config) o `client_max_body_size` (nginx) |

---

## 4. Notas de seguridad

- `backend/.env` de producción contiene credenciales reales — nunca lo
  versione en git ni lo comparta fuera del servidor.
- El validador en `app/core/config.py` impide arrancar en producción con
  un `JWT_SECRET_KEY` por defecto o débil; trátelo como una contraseña.
- Considere restringir el acceso directo a `127.0.0.1:8000` únicamente a
  localhost (ya es el comportamiento por defecto al usar `--host 127.0.0.1`
  en los scripts de este repositorio) para que la única vía de entrada sea
  el proxy inverso con HTTPS.
