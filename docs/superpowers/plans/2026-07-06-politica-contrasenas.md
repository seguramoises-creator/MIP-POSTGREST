# Política de Contraseñas — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans para implementar tarea por tarea. Los pasos usan checkboxes (`- [ ]`).

**Goal:** Forzar cambio de contraseña en primer login, exigir complejidad por rol, expirar contraseñas con aviso, impedir reutilización, todo parametrizable por el admin.

**Architecture:** Un servicio central `password_policy_service.py` concentra la lógica (complejidad por rol, expiración, historial). Los parámetros viven en `Config.DIM_Parametro` (patrón `config_service`, editable en vivo). `auth.py` (login/change-password) y `admin.py` (crear usuario + endpoints de config) consumen el servicio. El frontend fuerza el cambio y muestra el aviso.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic (`include_schemas=True`), passlib[bcrypt], React 18 + TS + MUI + Zustand, pytest.

## Global Constraints

- Edición **PostgreSQL** (`C:\Users\Lenovo\Proyecto\MSM-postgres`). NO tocar la edición SQL Server.
- Complejidad: mayúscula + minúscula + número + carácter especial. Longitud mínima **8** (no-admin), **12** (rol `ADMIN`). Carácter especial ∈ `!@#$%^&*()_+-=[]{};:,.<>?/|~`.
- Al vencer/primer login: se emite token, pero el frontend **fuerza** el cambio.
- No reutilizar la contraseña actual ni las últimas N (default 5).
- Defaults: expiración **on**, **90** días, aviso **7** días, historial **5**.
- Timestamps `datetime.now(timezone.utc)`, nunca `utcnow()`. Modelos SQLAlchemy 2.0. Logs con `loguru`. Migraciones con `include_schemas=True`.
- Parámetros (claves exactas): `PASSWORD_EXPIRACION_ACTIVA`, `PASSWORD_EXPIRACION_DIAS`, `PASSWORD_AVISO_DIAS`, `PASSWORD_HISTORIAL_N`, `PASSWORD_MIN_LONGITUD`, `PASSWORD_MIN_LONGITUD_ADMIN`.
- Flujo de trabajo: local → validar en navegador → deploy. Backend PG local de validación en `:8001` (config actual del entorno).

---

## Estructura de archivos

- Crear: `backend/app/services/password_policy_service.py` — lógica de política (complejidad, historial, estado).
- Crear: `backend/tests/test_password_policy_service.py` — tests unitarios.
- Modificar: `backend/app/services/config_service.py` — agregar `obtener_int`.
- Modificar: `backend/app/models/usuario.py` — columna `password_actualizado_en` + modelo `PasswordHistorial`.
- Crear: `backend/alembic/versions/<rev>_password_policy.py` — migración.
- Modificar: `backend/app/schemas/common.py` — extender `TokenResponse`.
- Modificar: `backend/app/schemas/schemas.py` — `PasswordChange` (quitar validador fijo), `UsuarioResponse` (2 campos).
- Modificar: `backend/app/api/v1/routers/auth.py` — login (flags) + change-password (política).
- Modificar: `backend/app/api/v1/routers/admin.py` — `create_usuario` (complejidad) + endpoints `/config/password-policy`.
- Modificar: `frontend/src/store/auth.store.ts`, `frontend/src/pages/auth/Login.tsx`, `frontend/src/components/layout/MainLayout.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/admin/Admin.tsx`, `frontend/src/services/api.ts` (tipos).

---

## Task 1: Servicio de complejidad + `obtener_int`

**Files:**
- Modify: `backend/app/services/config_service.py`
- Create: `backend/app/services/password_policy_service.py`
- Test: `backend/tests/test_password_policy_service.py`

**Interfaces:**
- Produces: `config_service.obtener_int(db, clave, por_defecto) -> int`; `password_policy_service.min_longitud(db, rol) -> int`; `password_policy_service.validar_complejidad(db, password, rol) -> None` (lanza `ValueError`).

- [ ] **Step 1: Test de `obtener_int` y complejidad**

En `backend/tests/test_password_policy_service.py`. Usa la fixture de sesión de tests existente (ver `tests/conftest.py`; el patrón de otros tests como `test_examen_ia_service.py`). Si conftest expone `db`, úsala; si no, crea una sesión en memoria como los demás tests.

```python
import pytest
from app.services import password_policy_service as pp
from app.services import config_service
from app.models.usuario import Rol

def test_obtener_int_default(db):
    assert config_service.obtener_int(db, "NO_EXISTE_X", 42) == 42

def test_min_longitud_por_rol(db):
    assert pp.min_longitud(db, Rol.ADMIN) == 12
    assert pp.min_longitud(db, Rol.REPRESENTANTE_MEDICO) == 8

def test_complejidad_ok_no_admin(db):
    pp.validar_complejidad(db, "Abcdef1!", Rol.REPRESENTANTE_MEDICO)  # 8 chars, no lanza

def test_complejidad_admin_requiere_12(db):
    with pytest.raises(ValueError, match="al menos 12"):
        pp.validar_complejidad(db, "Abcdef1!", Rol.ADMIN)  # 8 < 12

@pytest.mark.parametrize("pwd,msg", [
    ("abcdef1!", "mayúscula"),
    ("ABCDEF1!", "minúscula"),
    ("Abcdefg!", "número"),
    ("Abcdefg1", "especial"),
    ("Ab1!", "al menos 8"),
])
def test_complejidad_reglas(db, pwd, msg):
    with pytest.raises(ValueError, match=msg):
        pp.validar_complejidad(db, pwd, Rol.REPRESENTANTE_MEDICO)
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_password_policy_service.py -q`
Expected: FAIL (ModuleNotFoundError / AttributeError).

- [ ] **Step 3: `obtener_int` en `config_service.py`**

Agregar al final de `backend/app/services/config_service.py`:

```python
def obtener_int(db: Session, clave: str, por_defecto: int) -> int:
    val = obtener(db, clave)
    if val is None:
        return por_defecto
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return por_defecto
```

- [ ] **Step 4: Crear `password_policy_service.py` (parte 1: complejidad)**

```python
"""SCGCPR — Política de contraseñas: complejidad por rol, expiración y no
reutilización (historial). Parámetros configurables en vivo vía config_service
(Config.DIM_Parametro). Sin stored procedures — 100% Python."""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.services import config_service
from app.core.security import verify_password
from app.models.usuario import Rol

# Defaults (si el parámetro no está en Config.DIM_Parametro).
DEF_EXPIRACION_ACTIVA = True
DEF_EXPIRACION_DIAS = 90
DEF_AVISO_DIAS = 7
DEF_HISTORIAL_N = 5
DEF_MIN_LONGITUD = 8
DEF_MIN_LONGITUD_ADMIN = 12

_ESPECIALES = set("!@#$%^&*()_+-=[]{};:,.<>?/|~")


def _rol_val(rol) -> str:
    return rol.value if hasattr(rol, "value") else str(rol)


def min_longitud(db: Session, rol) -> int:
    if _rol_val(rol) == Rol.ADMIN.value:
        return config_service.obtener_int(db, "PASSWORD_MIN_LONGITUD_ADMIN", DEF_MIN_LONGITUD_ADMIN)
    return config_service.obtener_int(db, "PASSWORD_MIN_LONGITUD", DEF_MIN_LONGITUD)


def validar_complejidad(db: Session, password: str, rol) -> None:
    """Lanza ValueError con mensaje claro por la primera regla incumplida."""
    n = min_longitud(db, rol)
    if len(password) < n:
        raise ValueError(f"La contraseña debe tener al menos {n} caracteres")
    if not any(c.isupper() for c in password):
        raise ValueError("Debe contener al menos una mayúscula")
    if not any(c.islower() for c in password):
        raise ValueError("Debe contener al menos una minúscula")
    if not any(c.isdigit() for c in password):
        raise ValueError("Debe contener al menos un número")
    if not any(c in _ESPECIALES for c in password):
        raise ValueError("Debe contener al menos un carácter especial (!@#$%…)")
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_password_policy_service.py -q`
Expected: PASS (los tests de complejidad y `obtener_int`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/config_service.py backend/app/services/password_policy_service.py backend/tests/test_password_policy_service.py
git commit -m "feat(password) complejidad por rol + config obtener_int"
```

---

## Task 2: Modelo + migración

**Files:**
- Modify: `backend/app/models/usuario.py`
- Create: `backend/alembic/versions/<rev>_password_policy.py`

**Interfaces:**
- Produces: `Usuario.password_actualizado_en: datetime | None`; modelo `PasswordHistorial` (tabla `Security.FACT_PasswordHistorial`, columnas `id`, `usuario_id`, `hashed_password`, `creado_en`).

- [ ] **Step 1: Agregar columna y modelo en `usuario.py`**

En la clase `Usuario`, después de `ultimo_login`:

```python
    password_actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Al final del archivo, nueva clase (junto a `TokenRevocado`):

```python
class PasswordHistorial(Base):
    """Hashes de contraseñas previas por usuario, para impedir la reutilización
    de las últimas N. Se poda al insertar (ver password_policy_service)."""
    __tablename__ = "FACT_PasswordHistorial"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))
```

(`ForeignKey`, `Integer`, `String`, `DateTime` ya están importados en el archivo.)

- [ ] **Step 2: Generar la migración**

Run: `cd backend && ./venv/Scripts/python.exe -m alembic revision -m "password policy"`
Edita el archivo generado en `backend/alembic/versions/` con este contenido de `upgrade`/`downgrade`:

```python
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.add_column('DIM_Usuario',
        sa.Column('password_actualizado_en', sa.DateTime(), nullable=True),
        schema='Security')
    # Backfill: el reloj de expiración arranca AL MIGRAR (no en created_at),
    # para no forzar cambios sorpresa tras el deploy.
    op.execute("UPDATE \"Security\".\"DIM_Usuario\" "
               "SET password_actualizado_en = (now() at time zone 'utc') "
               "WHERE password_actualizado_en IS NULL")
    op.create_table('FACT_PasswordHistorial',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['Security.DIM_Usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='Security')
    op.create_index('ix_Security_FACT_PasswordHistorial_usuario_id',
                    'FACT_PasswordHistorial', ['usuario_id'], schema='Security')

def downgrade():
    op.drop_index('ix_Security_FACT_PasswordHistorial_usuario_id',
                  table_name='FACT_PasswordHistorial', schema='Security')
    op.drop_table('FACT_PasswordHistorial', schema='Security')
    op.drop_column('DIM_Usuario', 'password_actualizado_en', schema='Security')
```

- [ ] **Step 3: Aplicar y verificar**

Run: `cd backend && ./venv/Scripts/python.exe -m alembic upgrade head`
Expected: sin error. Verifica: `./venv/Scripts/python.exe -c "from app.db.database import SessionLocal; from app.models.usuario import Usuario, PasswordHistorial; db=SessionLocal(); print(db.query(Usuario).first().password_actualizado_en); print(db.query(PasswordHistorial).count())"` → imprime una fecha y `0`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/usuario.py backend/alembic/versions/
git commit -m "feat(password) columna password_actualizado_en + tabla historial"
```

---

## Task 3: Historial + estado de expiración

**Files:**
- Modify: `backend/app/services/password_policy_service.py`
- Test: `backend/tests/test_password_policy_service.py`

**Interfaces:**
- Consumes: `Usuario`, `PasswordHistorial`, `config_service.obtener_int/obtener_bool`, `security.hash_password/verify_password`.
- Produces: `contrasena_reutilizada(db, usuario, password_plano) -> bool`; `registrar_historial(db, usuario_id, hashed) -> None`; `estado_password(db, usuario) -> dict` con claves `debe_cambiar: bool`, `motivo: str`, `dias_para_expirar: int | None`.

- [ ] **Step 1: Tests de historial y estado**

Añade a `tests/test_password_policy_service.py` (crea un usuario de prueba con la fixture; sigue el patrón de creación de usuarios de otros tests):

```python
from datetime import datetime, timezone, timedelta
from app.core.security import hash_password
from app.models.usuario import Usuario, PasswordHistorial

def _crear_user(db, pwd="Abcdef1!", rol=Rol.REPRESENTANTE_MEDICO):
    u = Usuario(username="pptest", email="p@t.com", nombre_completo="P T",
                rol=rol, hashed_password=hash_password(pwd),
                debe_cambiar_password=False,
                password_actualizado_en=datetime.now(timezone.utc))
    db.add(u); db.commit(); db.refresh(u)
    return u

def test_reutiliza_actual(db):
    u = _crear_user(db, "Abcdef1!")
    assert pp.contrasena_reutilizada(db, u, "Abcdef1!") is True
    assert pp.contrasena_reutilizada(db, u, "Zxcvbn9@") is False

def test_registrar_y_podar_historial(db):
    u = _crear_user(db)
    config_service.fijar(db, "PASSWORD_HISTORIAL_N", "3")
    for i in range(5):
        pp.registrar_historial(db, u.id, hash_password(f"Passw0rd{i}!"))
        db.commit()
    filas = db.query(PasswordHistorial).filter(PasswordHistorial.usuario_id == u.id).count()
    assert filas == 3  # podado a N

def test_estado_expirada(db):
    u = _crear_user(db)
    config_service.fijar(db, "PASSWORD_EXPIRACION_ACTIVA", "true")
    config_service.fijar(db, "PASSWORD_EXPIRACION_DIAS", "90")
    u.password_actualizado_en = datetime.now(timezone.utc) - timedelta(days=100)
    db.commit()
    est = pp.estado_password(db, u)
    assert est["debe_cambiar"] is True and est["motivo"] == "expirada"

def test_estado_por_expirar(db):
    u = _crear_user(db)
    config_service.fijar(db, "PASSWORD_EXPIRACION_ACTIVA", "true")
    config_service.fijar(db, "PASSWORD_EXPIRACION_DIAS", "90")
    config_service.fijar(db, "PASSWORD_AVISO_DIAS", "7")
    u.password_actualizado_en = datetime.now(timezone.utc) - timedelta(days=85)
    db.commit()
    est = pp.estado_password(db, u)
    assert est["motivo"] == "por_expirar" and 0 <= est["dias_para_expirar"] <= 7

def test_estado_expiracion_desactivada(db):
    u = _crear_user(db)
    config_service.fijar(db, "PASSWORD_EXPIRACION_ACTIVA", "false")
    u.password_actualizado_en = datetime.now(timezone.utc) - timedelta(days=999)
    db.commit()
    est = pp.estado_password(db, u)
    assert est["debe_cambiar"] is False and est["dias_para_expirar"] is None
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_password_policy_service.py -q`
Expected: FAIL (funciones no existen).

- [ ] **Step 3: Implementar en `password_policy_service.py`**

Agregar imports arriba: `from app.models.usuario import PasswordHistorial`. Añadir:

```python
def contrasena_reutilizada(db: Session, usuario, password_plano: str) -> bool:
    if verify_password(password_plano, usuario.hashed_password):
        return True
    n = config_service.obtener_int(db, "PASSWORD_HISTORIAL_N", DEF_HISTORIAL_N)
    if n <= 0:
        return False
    previas = (db.query(PasswordHistorial)
               .filter(PasswordHistorial.usuario_id == usuario.id)
               .order_by(PasswordHistorial.creado_en.desc())
               .limit(n).all())
    return any(verify_password(password_plano, p.hashed_password) for p in previas)


def registrar_historial(db: Session, usuario_id: int, hashed: str) -> None:
    db.add(PasswordHistorial(usuario_id=usuario_id, hashed_password=hashed))
    db.flush()
    n = config_service.obtener_int(db, "PASSWORD_HISTORIAL_N", DEF_HISTORIAL_N)
    sobrantes = (db.query(PasswordHistorial)
                 .filter(PasswordHistorial.usuario_id == usuario_id)
                 .order_by(PasswordHistorial.creado_en.desc())
                 .offset(max(0, n)).all())
    for s in sobrantes:
        db.delete(s)


def estado_password(db: Session, usuario) -> dict:
    activa = config_service.obtener_bool(db, "PASSWORD_EXPIRACION_ACTIVA", DEF_EXPIRACION_ACTIVA)
    dias_para = None
    expirada = False
    if activa and usuario.password_actualizado_en is not None:
        dias = config_service.obtener_int(db, "PASSWORD_EXPIRACION_DIAS", DEF_EXPIRACION_DIAS)
        base = usuario.password_actualizado_en
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        vence = base + timedelta(days=dias)
        dias_para = (vence - datetime.now(timezone.utc)).days
        expirada = dias_para < 0
    debe = bool(usuario.debe_cambiar_password) or expirada
    if usuario.debe_cambiar_password:
        motivo = "primer_login"
    elif expirada:
        motivo = "expirada"
    elif dias_para is not None and dias_para <= config_service.obtener_int(db, "PASSWORD_AVISO_DIAS", DEF_AVISO_DIAS):
        motivo = "por_expirar"
    else:
        motivo = "ok"
    return {"debe_cambiar": debe, "motivo": motivo, "dias_para_expirar": dias_para}
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_password_policy_service.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/password_policy_service.py backend/tests/test_password_policy_service.py
git commit -m "feat(password) historial no-reutilizacion + estado de expiracion"
```

---

## Task 4: Wire auth (login + change-password) y creación de usuario

**Files:**
- Modify: `backend/app/schemas/common.py`, `backend/app/schemas/schemas.py`
- Modify: `backend/app/api/v1/routers/auth.py`
- Modify: `backend/app/api/v1/routers/admin.py`
- Test: `backend/tests/test_auth_password_policy.py` (nuevo)

**Interfaces:**
- Consumes: `password_policy_service.{estado_password, validar_complejidad, contrasena_reutilizada, registrar_historial}`.
- Produces: `TokenResponse` con `debe_cambiar_password: bool`, `password_expira_en_dias: int | None`, `password_motivo: str`.

- [ ] **Step 1: Extender `TokenResponse` (common.py)**

```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    debe_cambiar_password: bool = False
    password_expira_en_dias: Optional[int] = None
    password_motivo: str = "ok"
```

- [ ] **Step 2: `PasswordChange` sin validador fijo + `UsuarioResponse` con 2 campos (schemas.py)**

Reemplazar la clase `PasswordChange` (líneas ~48-63) por:

```python
class PasswordChange(BaseModel):
    password_actual: str
    password_nuevo: str
    # La complejidad se valida en el endpoint (depende del rol + BD), no aquí.
```

En `UsuarioResponse`, añadir tras `ultimo_login`:

```python
    debe_cambiar_password: bool = False
    password_expira_en_dias: Optional[int] = None
```

(Nota: `password_expira_en_dias` no es columna del modelo; se setea manualmente en `/auth/me` — ver Step 4.)

- [ ] **Step 3: Test de integración de auth**

Crear `backend/tests/test_auth_password_policy.py` usando `TestClient` (patrón de otros tests de routers, ver si existe `client` fixture en conftest):

```python
from datetime import datetime, timezone, timedelta
from app.core.security import hash_password
from app.models.usuario import Usuario, Rol
from app.services import config_service

def _mk(db, pwd="Abcdef1!", debe=False, rol=Rol.REPRESENTANTE_MEDICO):
    u = Usuario(username="polu", email="polu@t.com", nombre_completo="Pol U",
                rol=rol, hashed_password=hash_password(pwd),
                debe_cambiar_password=debe,
                password_actualizado_en=datetime.now(timezone.utc))
    db.add(u); db.commit(); db.refresh(u); return u

def test_login_devuelve_debe_cambiar(client, db):
    _mk(db, debe=True)
    r = client.post("/api/v1/auth/login", data={"username":"polu","password":"Abcdef1!"})
    assert r.status_code == 200
    assert r.json()["debe_cambiar_password"] is True
    assert r.json()["password_motivo"] == "primer_login"

def test_change_password_rechaza_complejidad(client, db):
    _mk(db)
    tok = client.post("/api/v1/auth/login", data={"username":"polu","password":"Abcdef1!"}).json()["access_token"]
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"password_actual":"Abcdef1!","password_nuevo":"sinespecial1A"})
    assert r.status_code == 400 and "especial" in r.json()["detail"]

def test_change_password_rechaza_reutilizar(client, db):
    _mk(db)
    tok = client.post("/api/v1/auth/login", data={"username":"polu","password":"Abcdef1!"}).json()["access_token"]
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"password_actual":"Abcdef1!","password_nuevo":"Abcdef1!"})
    assert r.status_code == 400 and "reutiliz" in r.json()["detail"].lower()

def test_change_password_ok_limpia_flag(client, db):
    u = _mk(db, debe=True)
    tok = client.post("/api/v1/auth/login", data={"username":"polu","password":"Abcdef1!"}).json()["access_token"]
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"password_actual":"Abcdef1!","password_nuevo":"Nuev0Pass!x"})
    assert r.status_code == 200
    db.refresh(u)
    assert u.debe_cambiar_password is False and u.password_actualizado_en is not None
```

- [ ] **Step 4: Ejecutar (falla), luego wire `auth.py`**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_auth_password_policy.py -q` → FAIL.

En `auth.py`, import: `from app.services import password_policy_service`.

En `login`, antes del `return TokenResponse(...)`, calcular estado y pasarlo:

```python
    estado = password_policy_service.estado_password(db, user)
    return TokenResponse(
        access_token  = access_token,
        refresh_token = refresh_token,
        expires_in    = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        debe_cambiar_password = estado["debe_cambiar"],
        password_expira_en_dias = estado["dias_para_expirar"],
        password_motivo = estado["motivo"],
    )
```

Reemplazar el cuerpo de `change_password` (tras verificar `password_actual`) por:

```python
    if not verify_password(datos.password_actual, current_user.hashed_password):
        _registrar_auditoria(db, current_user, "CHANGE_PASSWORD", request, False,
                             "Contraseña actual incorrecta")
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
    try:
        password_policy_service.validar_complejidad(db, datos.password_nuevo, current_user.rol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if password_policy_service.contrasena_reutilizada(db, current_user, datos.password_nuevo):
        raise HTTPException(status_code=400, detail="No puedes reutilizar una contraseña reciente")
    password_policy_service.registrar_historial(db, current_user.id, current_user.hashed_password)
    current_user.hashed_password = hash_password(datos.password_nuevo)
    current_user.password_actualizado_en = datetime.now(timezone.utc)
    current_user.debe_cambiar_password = False
    db.commit()
    _registrar_auditoria(db, current_user, "CHANGE_PASSWORD", request, True)
    return Msg(message="Contraseña actualizada correctamente")
```

En `get_me`, setear el campo calculado antes de responder (cambiar la firma para recibir `db`):

```python
@router.get("/me", response_model=UsuarioResponse, summary="Usuario actual")
def get_me(current_user: Usuario = Depends(get_current_active_user),
           db: Session = Depends(get_db)):
    estado = password_policy_service.estado_password(db, current_user)
    resp = UsuarioResponse.model_validate(current_user)
    resp.password_expira_en_dias = estado["dias_para_expirar"]
    resp.debe_cambiar_password = estado["debe_cambiar"]
    return resp
```

- [ ] **Step 5: `create_usuario` valida complejidad (admin.py)**

En `create_usuario` (línea ~707), tras la verificación de username duplicado:

```python
    from app.services import password_policy_service
    from datetime import datetime, timezone
    try:
        password_policy_service.validar_complejidad(db, data.password, data.rol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    payload = data.model_dump()
    payload["hashed_password"] = hash_password(payload.pop("password"))
    payload["debe_cambiar_password"] = True
    payload["password_actualizado_en"] = datetime.now(timezone.utc)
    obj = Usuario(**payload)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj
```

- [ ] **Step 6: Ejecutar (pasa) + regresión**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_auth_password_policy.py tests/test_password_policy_service.py -q`
Expected: PASS. Luego regresión general: `./venv/Scripts/python.exe -m pytest -q` (verificar que no rompió otros tests de auth/usuarios).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ backend/app/api/v1/routers/auth.py backend/app/api/v1/routers/admin.py backend/tests/test_auth_password_policy.py
git commit -m "feat(password) login expone estado; change-password aplica politica; alta valida"
```

---

## Task 5: Endpoints admin de parámetros

**Files:**
- Modify: `backend/app/api/v1/routers/admin.py`
- Test: `backend/tests/test_auth_password_policy.py` (añadir)

**Interfaces:**
- Produces: `GET /admin/config/password-policy`, `PUT /admin/config/password-policy` (solo ADMIN).

- [ ] **Step 1: Test**

Añadir a `tests/test_auth_password_policy.py` (usa un token ADMIN; crea un admin con `_mk(db, rol=Rol.ADMIN, pwd="Admin1234!X@")`):

```python
def test_password_policy_get_put(client, db):
    _mk(db, rol=Rol.ADMIN, pwd="Admin1234!Xx")
    tok = client.post("/api/v1/auth/login", data={"username":"polu","password":"Admin1234!Xx"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.get("/api/v1/admin/config/password-policy", headers=h)
    assert r.status_code == 200 and r.json()["expiracion_dias"] == 90
    r2 = client.put("/api/v1/admin/config/password-policy", headers=h,
                    json={"expiracion_activa": False, "expiracion_dias": 60})
    assert r2.status_code == 200 and r2.json()["expiracion_dias"] == 60 and r2.json()["expiracion_activa"] is False
```

- [ ] **Step 2: Ejecutar (falla), luego implementar**

Run: `pytest tests/test_auth_password_policy.py::test_password_policy_get_put -q` → FAIL.

En `admin.py`, tras el bloque de `examen-ia-demo`:

```python
@router.get("/config/password-policy", summary="Política de contraseñas vigente")
def get_password_policy(db: Session = Depends(get_db), _=AdminOnly):
    return {
        "expiracion_activa": _cfg.obtener_bool(db, "PASSWORD_EXPIRACION_ACTIVA", True),
        "expiracion_dias":   _cfg.obtener_int(db, "PASSWORD_EXPIRACION_DIAS", 90),
        "aviso_dias":        _cfg.obtener_int(db, "PASSWORD_AVISO_DIAS", 7),
        "historial_n":       _cfg.obtener_int(db, "PASSWORD_HISTORIAL_N", 5),
        "min_longitud":      _cfg.obtener_int(db, "PASSWORD_MIN_LONGITUD", 8),
        "min_longitud_admin": _cfg.obtener_int(db, "PASSWORD_MIN_LONGITUD_ADMIN", 12),
    }


@router.put("/config/password-policy", summary="Actualizar política de contraseñas")
def set_password_policy(body: dict, db: Session = Depends(get_db), _=AdminOnly):
    def _int(clave, k, minimo):
        if k in body:
            try:
                v = int(body[k])
            except (ValueError, TypeError):
                raise HTTPException(400, f"{k} debe ser un entero")
            if v < minimo:
                raise HTTPException(400, f"{k} debe ser >= {minimo}")
            _cfg.fijar(db, clave, str(v))
    if "expiracion_activa" in body:
        _cfg.fijar(db, "PASSWORD_EXPIRACION_ACTIVA", "true" if body["expiracion_activa"] else "false")
    _int("PASSWORD_EXPIRACION_DIAS", "expiracion_dias", 1)
    _int("PASSWORD_AVISO_DIAS", "aviso_dias", 0)
    _int("PASSWORD_HISTORIAL_N", "historial_n", 0)
    _int("PASSWORD_MIN_LONGITUD", "min_longitud", 8)
    _int("PASSWORD_MIN_LONGITUD_ADMIN", "min_longitud_admin", 8)
    return get_password_policy(db, _)
```

- [ ] **Step 3: Ejecutar (pasa) + commit**

Run: `pytest tests/test_auth_password_policy.py -q` → PASS.

```bash
git add backend/app/api/v1/routers/admin.py backend/tests/test_auth_password_policy.py
git commit -m "feat(password) endpoints admin de politica de contrasenas"
```

---

## Task 6: Frontend (forzar cambio + banner + tab admin)

**Files:**
- Modify: `frontend/src/store/auth.store.ts`, `frontend/src/pages/auth/Login.tsx`,
  `frontend/src/components/layout/MainLayout.tsx`, `frontend/src/App.tsx`,
  `frontend/src/pages/admin/Admin.tsx`
- Verificación: navegador (no hay setup de tests de front en este repo).

**Interfaces:**
- Consumes: respuesta de `/auth/login` (`debe_cambiar_password`, `password_expira_en_dias`, `password_motivo`) y `/auth/me`.

- [ ] **Step 1: Store guarda el estado de contraseña**

En `auth.store.ts`, agregar al estado: `debeCambiarPassword: boolean`, `passwordExpiraEnDias: number | null`, `passwordMotivo: string`, y setterlos en el login. Al hacer login, leer estos 3 campos de la respuesta y guardarlos. En `logout`, resetear a `false/null/'ok'`.

- [ ] **Step 2: Login redirige a cambio forzoso**

En `Login.tsx`, tras un login exitoso: si `response.debe_cambiar_password` → `navigate('/cambiar-password')`; si no, navegar al destino normal (dashboard/landing por rol).

- [ ] **Step 3: Ruta y pantalla de cambio forzoso**

En `App.tsx`, agregar ruta `/cambiar-password` (dentro del layout autenticado) que renderice un componente `CambiarPassword` (nuevo, en `frontend/src/pages/auth/CambiarPassword.tsx`). Reusar la lógica del diálogo existente en `MainLayout` (llamada `POST /auth/change-password`). La pantalla muestra los **requisitos** (mín. según rol: 12 si ADMIN, si no 8; + mayúscula, minúscula, número, especial) y valida en vivo. Al éxito: setear `debeCambiarPassword=false` en el store y navegar al dashboard.

Guard: en `MainLayout` (o en el wrapper de rutas protegidas), si `debeCambiarPassword === true` y la ruta actual no es `/cambiar-password`, redirigir a `/cambiar-password` (no puede navegar a otro lado hasta cambiarla).

- [ ] **Step 4: Banner de aviso**

En `MainLayout.tsx`, si `passwordMotivo === 'por_expirar'` (o `passwordExpiraEnDias != null && passwordExpiraEnDias <= 7`), mostrar un `<Alert severity="warning">` arriba del `Outlet`: "Tu contraseña vence en {passwordExpiraEnDias} día(s). Cámbiala." con un botón que abra `/cambiar-password`. Refrescar el estado con `/auth/me` al montar el layout.

- [ ] **Step 5: Tab admin "Política de contraseñas"**

En `Admin.tsx`, agregar un tab nuevo (patrón de los tabs existentes) que:
- GET `/admin/config/password-policy` al montar → rellena el formulario.
- Campos: switch `expiracion_activa`, números `expiracion_dias`, `aviso_dias`, `historial_n`, `min_longitud`, `min_longitud_admin`.
- Botón Guardar → PUT `/admin/config/password-policy` con los valores; toast de éxito.

- [ ] **Step 6: Build + verificación en navegador**

Run: `cd frontend && npm run build` (debe compilar sin errores TS).
Verificación manual en `http://localhost:3000` (stack local → :8001):
1. Crear un usuario nuevo (Admin → Usuarios) con contraseña temporal válida.
2. Login con ese usuario → debe redirigir a `/cambiar-password` y no dejar navegar.
3. Intentar una contraseña sin especial / repetida → ver el aviso claro.
4. Cambiarla por una válida → entra al dashboard.
5. Admin → Política de contraseñas: bajar `expiracion_dias` y ver que el aviso aparece según corresponda.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(password) frontend: cambio forzoso, banner de vencimiento y tab admin"
```

---

## Notas de cierre

- Tras validar en local (navegador), deploy: `git pull` en el servidor + `alembic upgrade head` dentro del contenedor backend (o al arrancar) + `docker compose --profile with-db up -d --build backend`. La migración corre contra el Postgres del servidor.
- La edición SQL Server (`MSM`) NO se toca en este plan.
