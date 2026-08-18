"""Frontera por país — LAS RUTAS QUE ESCRIBEN LA FRONTERA MISMA.

`PUT /admin/usuarios/{id}/paises` y `PUT /admin/gerentes/{id}/lineas` no LEEN
`FACT_UsuarioPais` como dato de entrada: la ESCRIBEN. Mientras estuvieran sin guard,
blindar las otras veinte rutas no servía de nada — quien quisiera saltarse el límite no
necesitaba encontrar un hueco, solo ampliarse el suyo y usar las rutas ya cerradas con
total legitimidad. Es la cerradura floja contra la llave maestra colgada al lado.

La escalada más corta era la LISTA VACÍA: por convención del spec §3 significa "todos los
países", así que un ADMIN acotado a DO que se fijara `[]` a sí mismo quedaba sin
restricción — y sin pasar por ninguna resta de conjuntos que lo delatara.

Patrón cruzado, como el resto de la familia: actor ADMIN acotado a `{DO}` intentando
alcanzar entidades de GT. El caso "sin filas → sin filtro" está aislado en su propio test
y verifica lo CONTRARIO, para descartar el falso verde de que el filtro nunca corrió.

Necesita PostgreSQL real.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.routers import admin as admin_router
from app.core.config import settings
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models.alcance import GerenteLinea, UsuarioPais
from app.models.dimensiones import Gerente, Linea, Pais
from app.models.usuario import Rol, Usuario

BD_PRUEBA = "vista_test_frontera_pais_gestion_alcance"


def _url(nombre: str) -> str:
    return (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_SERVER}:{settings.DB_PORT}/{nombre}")


@pytest.fixture(scope="module")
def motor():
    try:
        admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as cx:
            cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
            cx.execute(text(f"CREATE DATABASE {BD_PRUEBA}"))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable para pruebas de integración: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"Config"."DIM_GerenteLinea"', '"Security"."FACT_UsuarioPais"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"',
                  '"Security"."DIM_Usuario"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """DO y GT, cada uno con su línea y su gerente. Tres usuarios:

    - `actor_do`   — ADMIN acotado a `{DO}`: el que intenta la escalada.
    - `victima_gt` — usuario acotado a `{GT}`: entidad ajena, no debe poder tocarla.
    - `global_`    — ADMIN sin filas: ve todos los países, no debe quedar bloqueado.
    """
    db.add_all([Pais(codigo="DO", nombre="República Dominicana"),
                Pais(codigo="GT", nombre="Guatemala")])
    db.flush()
    lin_do = Linea(pais_codigo="DO", codigo="L-DO", nombre="Línea DO")
    lin_gt = Linea(pais_codigo="GT", codigo="L-GT", nombre="Línea GT")
    db.add_all([lin_do, lin_gt])
    db.flush()
    ger_do = Gerente(pais_codigo="DO", codigo="G-DO", nombre="Gerente DO", tipo="DISTRITO")
    ger_gt = Gerente(pais_codigo="GT", codigo="G-GT", nombre="Gerente GT", tipo="DISTRITO")
    db.add_all([ger_do, ger_gt])

    def _u(username: str) -> Usuario:
        return Usuario(username=username, email=f"{username}@x.com",
                       hashed_password="x", nombre_completo=username, rol=Rol.ADMIN, activo=True)

    actor_do, victima_gt, global_ = _u("actor_do"), _u("victima_gt"), _u("global")
    db.add_all([actor_do, victima_gt, global_])
    db.flush()
    db.add_all([UsuarioPais(usuario_id=actor_do.id, pais_codigo="DO"),
                UsuarioPais(usuario_id=victima_gt.id, pais_codigo="GT")])
    db.commit()
    return {"actor_do": actor_do, "victima_gt": victima_gt, "global": global_,
            "ger_do": ger_do, "ger_gt": ger_gt, "lin_do": lin_do, "lin_gt": lin_gt}


# ── La escalada corta: la lista vacía ────────────────────────────────────────────

def test_lista_vacia_no_puede_quitarse_la_propia_restriccion(db, escenario):
    """EL TEST QUE DEFINE EL DISEÑO. Lista vacía = "todos los países" (spec §3). Un ADMIN
    acotado a DO fijándose `[]` a sí mismo quedaba sin restricción, y no lo delataba
    ninguna resta de conjuntos: `set() - {"DO"}` es vacío, así que una comprobación
    ingenua de "no otorgues fuera de tu alcance" lo habría dejado pasar."""
    actor = escenario["actor_do"]
    with pytest.raises(HTTPException) as exc:
        admin_router.put_paises_usuario(actor.id, {"paises": []}, db=db, actor=actor)
    assert exc.value.status_code == 403
    # y su restricción sigue intacta en la BD, no a medio borrar
    assert {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == actor.id).all()} == {"DO"}


def test_no_puede_otorgarse_un_pais_ajeno(db, escenario):
    actor = escenario["actor_do"]
    with pytest.raises(HTTPException) as exc:
        admin_router.put_paises_usuario(actor.id, {"paises": ["DO", "GT"]}, db=db, actor=actor)
    assert exc.value.status_code == 403
    assert {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == actor.id).all()} == {"DO"}


def test_no_puede_reacotar_a_un_usuario_de_otro_pais(db, escenario):
    """No es escalada de sus propios permisos, pero manipula a alguien que no le
    corresponde: un ADMIN de DO reasignando los países de un usuario de GT."""
    actor, victima = escenario["actor_do"], escenario["victima_gt"]
    with pytest.raises(HTTPException) as exc:
        admin_router.put_paises_usuario(victima.id, {"paises": ["DO"]}, db=db, actor=actor)
    assert exc.value.status_code == 403
    assert {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == victima.id).all()} == {"GT"}


def test_no_puede_leer_los_paises_de_un_usuario_ajeno(db, escenario):
    actor, victima = escenario["actor_do"], escenario["victima_gt"]
    with pytest.raises(HTTPException) as exc:
        admin_router.get_paises_usuario(victima.id, db=db, actor=actor)
    assert exc.value.status_code == 403


def test_un_usuario_sin_restriccion_queda_fuera_del_alcance_de_un_admin_acotado(db, escenario):
    """Sin filas = ve todos los países. Un ADMIN acotado no debe poder acotarlo:
    estaría decidiendo sobre alguien de mayor alcance que él."""
    actor, glob = escenario["actor_do"], escenario["global"]
    with pytest.raises(HTTPException) as exc:
        admin_router.put_paises_usuario(glob.id, {"paises": ["DO"]}, db=db, actor=actor)
    assert exc.value.status_code == 403


# ── Lo que SÍ debe seguir funcionando ────────────────────────────────────────────

def test_admin_global_no_queda_bloqueado(db, escenario):
    """El contrario del falso verde: sin filas en FACT_UsuarioPais no hay filtro, y el
    superadmin sigue pudiendo otorgar cualquier cosa, incluida la lista vacía."""
    glob, victima = escenario["global"], escenario["victima_gt"]
    r = admin_router.put_paises_usuario(victima.id, {"paises": ["DO", "GT"]}, db=db, actor=glob)
    assert r["paises"] == ["DO", "GT"]
    r = admin_router.put_paises_usuario(victima.id, {"paises": []}, db=db, actor=glob)
    assert r["paises"] == []


def test_admin_acotado_si_puede_operar_dentro_de_su_pais(db, escenario):
    """El guard no debe volver inútil la gestión legítima: un ADMIN de DO sobre un
    usuario de DO, otorgando DO, pasa."""
    actor = escenario["actor_do"]
    otro_do = Usuario(username="otro_do", email="otro_do@x.com", hashed_password="x",
                      nombre_completo="Otro DO", rol=Rol.ADMIN, activo=True)
    db.add(otro_do)
    db.flush()
    db.add(UsuarioPais(usuario_id=otro_do.id, pais_codigo="DO"))
    db.commit()
    assert admin_router.put_paises_usuario(
        otro_do.id, {"paises": ["DO"]}, db=db, actor=actor)["paises"] == ["DO"]


# ── La ruta hermana: líneas de un gerente ────────────────────────────────────────

def test_no_puede_reasignar_lineas_de_un_gerente_de_otro_pais(db, escenario):
    actor, ger_gt, lin_gt = escenario["actor_do"], escenario["ger_gt"], escenario["lin_gt"]
    with pytest.raises(HTTPException) as exc:
        admin_router.put_lineas_gerente(ger_gt.id, {"lineas": [lin_gt.id]}, db=db, actor=actor)
    assert exc.value.status_code == 403
    assert db.query(GerenteLinea).filter(GerenteLinea.gerente_id == ger_gt.id).count() == 0


def test_no_puede_leer_lineas_de_un_gerente_de_otro_pais(db, escenario):
    actor, ger_gt = escenario["actor_do"], escenario["ger_gt"]
    with pytest.raises(HTTPException) as exc:
        admin_router.get_lineas_gerente(ger_gt.id, db=db, actor=actor)
    assert exc.value.status_code == 403


def test_si_puede_reasignar_lineas_de_un_gerente_de_su_pais(db, escenario):
    actor, ger_do, lin_do = escenario["actor_do"], escenario["ger_do"], escenario["lin_do"]
    r = admin_router.put_lineas_gerente(ger_do.id, {"lineas": [lin_do.id]}, db=db, actor=actor)
    assert r["lineas"] == [lin_do.id]


def test_gerente_inexistente_no_sirve_para_sondear(db, escenario):
    """Un id inventado devuelve el mismo 403 que uno ajeno: no distingue "no existe" de
    "no autorizado", así que no se puede enumerar el catálogo desde fuera."""
    with pytest.raises(HTTPException) as exc:
        admin_router.get_lineas_gerente(999999, db=db, actor=escenario["actor_do"])
    assert exc.value.status_code == 403
