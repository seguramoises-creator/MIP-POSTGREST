# Respaldo completo y portable de VISTA

Produce **un solo archivo** que, restaurado en cualquier servidor Debian con Docker,
levanta el sistema idéntico: mismas imágenes, mismos datos, mismos archivos, misma
configuración. No necesita internet ni reconstruir las imágenes en el destino.

Es el respaldo que se toma **antes de un cambio grande** y el mecanismo con el que la
solución se traslada al servidor de un cliente.

---

## Qué incluye y por qué

| Pieza | Contenido | Por qué no basta con lo demás |
|---|---|---|
| **Imágenes** | `docker save` de backend, frontend y PostgreSQL | Reconstruir en el destino exige internet, npm y pip, y una dependencia que cambió de versión da una imagen distinta a la que estaba probada |
| **Base de datos** | `pg_dump -Fc` | Copiar el volumen crudo de PGDATA solo restaura en la misma versión y arquitectura exactas de PostgreSQL |
| **Volúmenes** | uploads, reports, logs | Son archivos en disco: ningún volcado de base los contiene. Sin ellos el sistema arranca con los adjuntos históricos rotos |
| **Configuración** | `.env` de la raíz y de `backend/` | No están en git por diseño (llevan claves) |
| **Código** | `git bundle --all` | Copiar la carpeta deja un working tree sin historia ni remoto útil |
| **Manifiesto** | commit, árbol, migración *head*, huella de datos, sumas SHA-256 | Es lo que permite **demostrar** que el destino quedó igual, en vez de suponerlo |

`pg_data` se omite a propósito: el volcado lógico lo sustituye y sí es portable.

---

## Tomar el respaldo

En el servidor, con el sistema corriendo (no lo interrumpe, solo lee):

```bash
cd /opt/msm-pg && ./scripts/respaldo/respaldar_solucion.sh
```

Deja `~/respaldos-vista/vista-respaldo-AAAAMMDD-HHMM.tar.gz` más su `.sha256`.

Verificarlo antes de confiar en él — un paquete corrupto solo se descubre al
necesitarlo, que es el peor momento posible:

```bash
cd ~/respaldos-vista && tar xzf vista-respaldo-*.tar.gz && cd "$(ls -d vista-respaldo-*/ | tail -1)" && ./verificar_respaldo.sh
```

> La barra final en `vista-respaldo-*/` no es un adorno: sin ella el patrón también
> empata el `.tar.gz` y el `.sha256`, y `cd` falla con *too many arguments*.

---

## Restaurar en otro servidor

Requisitos del destino: Debian con Docker Engine 24+ y Docker Compose v2. Nada más.

```bash
tar xzf vista-respaldo-AAAAMMDD-HHMM.tar.gz
cd vista-respaldo-AAAAMMDD-HHMM
./restaurar_solucion.sh /opt/msm-pg
```

El script carga las imágenes, clona el código, restaura configuración, volúmenes y
base, levanta el stack y **compara la migración *head* y la huella de datos contra
las del origen**. Si algo no coincide, termina en error en vez de dar por buena la
restauración.

### Lo que hay que ajustar a mano en el destino

El script lo recuerda al terminar. Son las cosas propias de cada ambiente, que
justamente **no** deben heredarse:

1. **`JWT_SECRET_KEY`** en `backend/.env` — una por ambiente. Compartirla hace que un
   token emitido en uno sea válido en el otro.
2. **`CORS_ORIGINS`** — el dominio nuevo.
3. **Credenciales SMTP** — viven en la base (Admin → Correo), así que viajaron dentro
   del volcado y apuntan al buzón del origen. Cambiarlas **antes del primer correo**.
4. **nginx del host y certificado TLS** del dominio nuevo. En `configuracion/` queda
   una copia del original solo como referencia.
5. **Usuarios y contraseñas** viajan hasheados y siguen siendo válidos. Si el destino
   es de otro cliente, revisar que la lista corresponda.

---

## La huella de datos

`huella_datos.sql` calcula un md5 sobre el conteo **exacto** de filas de cada tabla.
Dos ambientes con la misma huella tienen la misma información, tabla por tabla.

Dos decisiones que la hacen útil:

- Usa `query_to_xml` y no `n_live_tup`, que es una **estimación** del planificador y
  cambia con el autovacuum sin que cambie un solo dato.
- **Excluye las tablas de auditoría.** Crecen con cualquier uso —hasta un login
  fallido escribe una fila—, así que sin la exclusión la huella nunca coincide y deja
  de distinguir una diferencia real de la simple actividad. Nunca borrar filas de
  auditoría para "cuadrar" un conteo: son *append-only* por diseño.

Para comparar dos ambientes en cualquier momento, sin respaldo de por medio:

```bash
docker compose exec -T db psql -U segura -d scgcpr -At -f - < scripts/respaldo/huella_datos.sql
```

---

## Advertencia

El paquete contiene **secretos** (claves de base de datos, JWT y SMTP) y **datos
personales reales** (médicos, representantes, correos). Material confidencial: nunca
en carpetas sincronizadas, nunca en git, y transferirlo solo por canales cifrados.
