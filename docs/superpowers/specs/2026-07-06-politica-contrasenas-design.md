# Política de Contraseñas — Diseño

**Fecha:** 2026-07-06
**Edición:** PostgreSQL (`MSM-postgres`). NO tocar la edición SQL Server salvo portado posterior explícito.
**Objetivo:** Forzar cambio de contraseña en primer login, exigir complejidad estándar (dependiente del rol), expirar contraseñas cada N días con aviso previo, impedir reutilización de contraseñas recientes, y hacer todo parametrizable en vivo por el administrador.

---

## 1. Decisiones (aprobadas por el usuario)

- **Complejidad por rol:** todos requieren mayúscula + minúscula + número + carácter especial.
  - Longitud mínima **8** para roles no-admin.
  - Longitud mínima **12** para rol `ADMIN`.
- **Al vencer o primer login:** se emite token pero el frontend **fuerza la pantalla de cambio**; el usuario no puede usar el sistema hasta cambiar la contraseña.
- **No reutilización:** se rechaza repetir la contraseña actual y las últimas N (default 5).
- **Parametrizable en vivo** por el admin (patrón `config_service` sobre `Config.DIM_Parametro`).

---

## 2. Modelo de datos

### 2.1 `Security.DIM_Usuario` (modificar)
- Agregar columna **`password_actualizado_en: datetime | None`** — fecha del último cambio de contraseña. Base para el cálculo de expiración.
- Se reutiliza la columna existente **`debe_cambiar_password: bool`** (default `True`).

### 2.2 `Security.FACT_PasswordHistorial` (nueva tabla)
| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | int PK autoincrement | |
| `usuario_id` | int, FK `Security.DIM_Usuario.id`, index | |
| `hashed_password` | String(255) | hash bcrypt de una contraseña previa |
| `creado_en` | datetime | default `now(utc)` |

Se conservan solo las últimas `PASSWORD_HISTORIAL_N` filas por usuario (poda al insertar).

### 2.3 Parámetros (`Config.DIM_Parametro` vía `config_service`)
| Clave | Tipo | Default |
|-------|------|---------|
| `PASSWORD_EXPIRACION_ACTIVA` | bool | `true` |
| `PASSWORD_EXPIRACION_DIAS` | int | `90` |
| `PASSWORD_AVISO_DIAS` | int | `7` |
| `PASSWORD_HISTORIAL_N` | int | `5` |
| `PASSWORD_MIN_LONGITUD` | int | `8` |
| `PASSWORD_MIN_LONGITUD_ADMIN` | int | `12` |

`config_service.obtener_bool` / un nuevo `obtener_int(db, clave, por_defecto)` leen estos valores; si no existe la fila, se usa el default. No requieren migración de datos (los defaults viven en código).

---

## 3. Reglas de complejidad (centralizadas)

Nuevo módulo `app/services/password_policy_service.py`:

```python
def min_longitud(db, rol) -> int:
    # ADMIN -> PASSWORD_MIN_LONGITUD_ADMIN (12); resto -> PASSWORD_MIN_LONGITUD (8)

def validar_complejidad(db, password: str, rol) -> None:
    # Lanza ValueError con mensaje claro y específico por cada regla incumplida:
    #  - longitud (según rol)
    #  - falta mayúscula / minúscula / número / carácter especial
    # Carácter especial = cualquiera en  !@#$%^&*()_+-=[]{};:,.<>?/|~
```

Se usa en:
- Creación de usuario por admin (`admin.create_usuario`) — hoy NO valida complejidad.
- Cambio de contraseña (`auth.change_password`).
- Reset de contraseña por admin (si existe/creado).

La validación de Pydantic actual en `PasswordChange` (min 12 fijo) se **reemplaza** por la validación centralizada dependiente del rol (Pydantic ya no puede validarla sola porque necesita el rol + la BD; se valida en el endpoint).

---

## 4. Estado de la contraseña y login

### 4.1 Servicio `password_policy_service.estado_password(db, usuario) -> dict`
Retorna:
```python
{
  "debe_cambiar": bool,           # primer login (debe_cambiar_password) O (expiración activa Y vencida)
  "motivo": "primer_login" | "expirada" | "por_expirar" | "ok",
  "dias_para_expirar": int | None # solo si expiración activa; None si desactivada
}
```
Cálculo de expiración: `vence = password_actualizado_en + PASSWORD_EXPIRACION_DIAS`. Si `password_actualizado_en` es `None` (usuarios previos a la migración), se trata como "debe_cambiar" en el primer login o se backfillea (ver §7). `dias_para_expirar = (vence - now).days`. Si `<= 0` → expirada. Si `<= PASSWORD_AVISO_DIAS` → por_expirar.

### 4.2 `POST /auth/login` (modificar respuesta)
`TokenResponse` (o un modelo extendido) agrega:
- `debe_cambiar_password: bool`
- `password_expira_en_dias: int | None`
- `password_motivo: str`

El token se emite igual (para poder llamar a `change-password`). El backend NO bloquea; el frontend fuerza el cambio.

### 4.3 `GET /auth/me` (modificar)
`UsuarioResponse` expone `debe_cambiar_password` y `password_expira_en_dias` para que el layout muestre el banner en cualquier recarga.

---

## 5. Cambio de contraseña

`POST /auth/change-password` (modificar):
1. Verifica contraseña actual (ya lo hace).
2. `validar_complejidad(db, password_nuevo, current_user.rol)`.
3. **No reutilización:** rechaza si `password_nuevo` coincide (verify) con la contraseña actual o con cualquiera de las últimas `PASSWORD_HISTORIAL_N` en `FACT_PasswordHistorial`.
4. Guarda: mueve el hash anterior al historial (poda > N), setea `hashed_password`, `password_actualizado_en = now`, `debe_cambiar_password = False`.
5. Revoca tokens (ya lo hace) + auditoría (ya lo hace).

Mensajes de error claros y accionables (para el "aviso como debe ser").

---

## 6. Frontend

- **`Login.tsx`:** tras login, si `debe_cambiar_password` → navega a la pantalla de cambio forzoso y no permite salir hasta cambiarla. Guarda el estado en el store de auth.
- **Pantalla de cambio forzoso** (reutiliza el diálogo existente de `MainLayout` o una ruta `/cambiar-password`): muestra **los requisitos según el rol** (longitud correcta) y valida en vivo.
- **Banner de aviso** (en `MainLayout`): si `password_expira_en_dias != null && <= PASSWORD_AVISO_DIAS`, muestra "Tu contraseña vence en N día(s). Cámbiala." con acción directa.
- **Admin — nueva pestaña "Política de contraseñas"** (tab en `Admin.tsx`, patrón de los otros tabs): formulario para los 6 parámetros (§2.3), con toggle de expiración on/off. Consume nuevos endpoints admin GET/PUT.

---

## 7. Migración

Alembic (con `include_schemas=True`):
1. `add_column` `Security.DIM_Usuario.password_actualizado_en` (nullable).
2. **Backfill:** `UPDATE Security.DIM_Usuario SET password_actualizado_en = <ahora> WHERE password_actualizado_en IS NULL` — los usuarios existentes inician su ciclo de expiración **en la fecha de la migración** (no en su creación), para NO forzar un cambio sorpresa justo tras el deploy. Su primer vencimiento será a los `PASSWORD_EXPIRACION_DIAS` de migrar.
3. `create_table` `Security.FACT_PasswordHistorial`.
No se siembran parámetros (defaults en código); el admin puede ajustarlos luego.

---

## 8. Endpoints admin (parámetros)

Siguiendo el patrón de `/admin/config/examen-ia-demo`:
- `GET /admin/config/password-policy` → devuelve los 6 parámetros vigentes.
- `PUT /admin/config/password-policy` → actualiza (valida rangos: días > 0, historial ≥ 0, longitudes ≥ 8). Solo `ADMIN`.

---

## 9. Testing (pytest)

- `validar_complejidad`: cada regla incumplida (longitud por rol ADMIN vs no-admin, falta mayús/minús/número/especial) y caso válido.
- No reutilización: rechaza actual y últimas N; acepta una nueva.
- `estado_password`: primer_login, expirada, por_expirar (dentro del aviso), ok; y con expiración desactivada (`dias_para_expirar = None`, nunca fuerza por expiración).
- Login: respuesta incluye los flags correctos; poda de historial > N.
- Endpoints admin de parámetros: get/put y validación de rangos.

---

## 10. Fuera de alcance (YAGNI)

- 2FA / MFA.
- Recuperación de contraseña por correo ("olvidé mi contraseña").
- Expiración/complejidad distinta por cada rol más allá de ADMIN vs resto.
- Portado a la edición SQL Server (se hará después, explícitamente, si se pide).
