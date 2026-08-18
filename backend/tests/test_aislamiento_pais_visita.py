"""
Aislamiento multipaís en selectores y agregados "de gestión" (cuando nadie elige un
VM/gerente específico) del módulo Visita y de Coaching (MORE). Antes mezclaban datos
de TODOS los países cuando ADMIN/GERENTE_PRODUCTIVIDAD consultaban el agregado sin
`vm_id`/`gerente_id`/`linea_id`. Ya se arregló el caso más crítico (cierre de ciclo,
commit 8427bb0); este archivo cubre el resto:

  - `/visita/vms`, `/coaching-more/vms` (selectores de VM)
  - `/visita/lineas` + `visita_parrilla_service.listar_lineas` (selector de línea)
  - `visita_cobertura_service`: `_rm_ids_por`, `_cobertura_base`, `resumen_cobertura`,
    `ciclo_por_defecto`, `ranking_visitadores`
  - `visita_service.listar_medicos` (Panel Médico agregado)
  - los routers `/visita/medicos`, `/visita/cobertura/resumen`, `/visita/cobertura/ranking`
    (verifican que el parámetro `pais_codigo` llega al servicio)

Convención de dobles de `db`: como `test_visita_service.py` (`_db_cierre`), pero aquí el
doble APLICA DE VERDAD los filtros (inspecciona la expresión SQLAlchemy real —columna y
valor— en vez de solo registrar que `.filter()` fue llamado), para que el test compruebe
que un país realmente EXCLUYE los registros de otro país y no solo que el código "intentó"
filtrar.
"""
import operator as _op
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.dimensiones import Especialidad, Gerente, Linea, Medico, RepresentanteMedico
from app.models.usuario import Rol
from app.models.visita import MedicoVisita, VisitaRegistro
from app.services import visita_cobertura_service as cob
from app.services import visita_parrilla_service as parrilla_svc
from app.services import visita_service as vs
from app.api.v1.routers import coaching_more as coaching_more_router
from app.api.v1.routers import visita as visita_router
from app.api.v1.routers import maestro_medicos as mm_router
from app.api.v1.routers import examenes as examenes_router


# ── Doble de Session.query() con filtrado REAL sobre las expresiones SQLAlchemy ───
def _valor_derecho(cond):
    right = cond.right
    tname = type(right).__name__
    if tname == "True_":
        return True
    if tname == "False_":
        return False
    return right.value


def _match(record, cond) -> bool:
    key = cond.left.key
    val = _valor_derecho(cond)
    op = getattr(cond, "operator", None)
    actual = getattr(record, key, None)
    if op is _op.eq:
        return actual == val
    if op is _op.ge:
        return actual is not None and actual >= val
    if op is _op.le:
        return actual is not None and actual <= val
    nombre_op = getattr(op, "__name__", "")
    if nombre_op in ("in_op", "in_"):
        return actual in val
    if nombre_op in ("not_in_op", "notin_op"):
        return actual not in val
    raise AssertionError(f"operador no soportado en el doble de test: {op}")


def _es(args, *columnas) -> bool:
    """True si `args` (los args posicionales de una llamada a `db.query(...)`) son
    EXACTAMENTE esas columnas/entidades, comparadas por IDENTIDAD.

    Nunca usar `args == (Columna,)`: en una columna/atributo SQLAlchemy, `==` construye
    una expresión SQL binaria (no compara objetos Python) y revienta si el otro lado no
    es una columna o un valor literal — por eso la comparación tiene que ser `is`."""
    return len(args) == len(columnas) and all(a is c for a, c in zip(args, columnas))


class _FakeQuery:
    """Doble de una query encadenada. `proj`, si viene, es la tupla de nombres de
    atributo que `.all()` proyecta como tuplas (para `db.query(Modelo.col)` o
    `db.query(Modelo.col1, Modelo.col2)`); sin `proj`, `.all()` devuelve los objetos
    completos (para `db.query(Modelo)`)."""

    def __init__(self, records, proj=None):
        self._records = list(records)
        self._proj = proj

    def filter(self, *conds):
        registros = self._records
        for c in conds:
            registros = [r for r in registros if _match(r, c)]
        return _FakeQuery(registros, self._proj)

    def order_by(self, *a, **k):
        return self

    def group_by(self, *a, **k):
        return self

    def distinct(self):
        vistos, salida = set(), []
        for r in self._records:
            clave = tuple(getattr(r, a) for a in self._proj) if self._proj else id(r)
            if clave not in vistos:
                vistos.add(clave)
                salida.append(r)
        return _FakeQuery(salida, self._proj)

    def offset(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def all(self):
        if self._proj:
            return [tuple(getattr(r, a) for a in self._proj) for r in self._records]
        return self._records

    def first(self):
        return self._records[0] if self._records else None

    def count(self):
        return len(self._records)

    def scalar(self):
        """Para queries `db.query(func.count(...))...scalar()`: el conteo tras filtrar."""
        return len(self._records)


def _rm(id, gerente_id=None, linea_id=None, pais_codigo=None, nombre=None, **extra):
    base = dict(id=id, gerente_id=gerente_id, linea_id=linea_id, pais_codigo=pais_codigo,
                nombre=nombre or f"RM{id}", activo=True, email=None,
                coaching_min_dia=None, zona=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _linea(id, nombre, pais_codigo, activo=True):
    return SimpleNamespace(id=id, nombre=nombre, pais_codigo=pais_codigo, activo=activo)


def _gerente(id, tipo="DISTRITO", pais_codigo=None, activo=True, nombre=None):
    return SimpleNamespace(id=id, nombre=nombre or f"Gerente{id}", tipo=tipo,
                           activo=activo, pais_codigo=pais_codigo)


def _medico(id, pais_codigo, activo=True, estado_validacion="APROBADO", **extra):
    from datetime import datetime, timezone
    base = dict(id=id, pais_codigo=pais_codigo, nombre=f"Dr {id}", codigo=None, cedula=None,
                especialidad_id=None, provincia_id=None, estado_validacion=estado_validacion,
                activo=activo, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    base.update(extra)
    return SimpleNamespace(**base)


def _med(id, vm_id, categoria="A", es_top=False):
    # `es_top` (prioridad TOP del SFA de Mallén) es un criterio ORTOGONAL a
    # `categoria`: el §11.5 del requerimiento avisa que "marcar TOP no es marcar
    # categoría A". Por eso viaja como campo aparte y su default es False —
    # ausencia de dato NO es TOP.
    return SimpleNamespace(
        id=id, vm_id=vm_id, categoria=categoria, codigo=None,
        nombre_completo=f"Dr {id}", especialidad_id=None,
        centro_trabajo=None, provincia=None, municipio=None,
        ciclos_sin_visita=0, activo=True, es_top=es_top,
        estado_aprobacion="APROBADO", ciclo_alta_id=None, ciclo_baja_id=None)


def _patch_gating_cob(monkeypatch):
    """Neutraliza el filtro de vigencia por ciclo (igual que `_patch_gating` en
    test_visita_service.py): cuenta = activo."""
    import app.services.visita_aprobacion_service as aps
    monkeypatch.setattr(aps, "ordenes_ciclo", lambda db: {})
    monkeypatch.setattr(aps, "cuenta_en_ciclo", lambda m, o, ords: m.activo)


# ── /visita/vms ─────────────────────────────────────────────────────────────
def test_router_visita_vms_filtra_por_pais():
    rms = [_rm(1, pais_codigo="DO"), _rm(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms)
    out = visita_router.listar_vms(pais_codigo="DO", db=db, current_user=SimpleNamespace())
    assert [r["id"] for r in out] == [1]


def test_router_visita_vms_sin_pais_no_restringe():
    """Compatibilidad: sin `pais_codigo` sigue viendo TODOS los VMs (el frontend aún no
    manda el filtro en todas las pantallas)."""
    rms = [_rm(1, pais_codigo="DO"), _rm(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms)
    out = visita_router.listar_vms(pais_codigo=None, db=db, current_user=SimpleNamespace())
    assert {r["id"] for r in out} == {1, 2}


# ── /coaching-more/vms ────────────────────────────────────────────────────────
def test_coaching_more_vms_filtra_por_pais():
    rms = [_rm(1, pais_codigo="DO"), _rm(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms)
    user = SimpleNamespace(rol=Rol.ADMIN, gerente_id=None)
    out = coaching_more_router.vms(pais_codigo="DO", db=db, current_user=user)
    assert [r["id"] for r in out] == [1]


def test_coaching_more_vms_combina_gerente_distrito_y_pais():
    """El auto-filtro de GERENTE_DISTRITO (a su propio equipo) y el nuevo filtro de
    `pais_codigo` deben aplicar JUNTOS, no uno excluir al otro."""
    rms = [_rm(1, gerente_id=5, pais_codigo="DO"),
           _rm(2, gerente_id=5, pais_codigo="GT"),
           _rm(3, gerente_id=9, pais_codigo="DO")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms)
    user = SimpleNamespace(rol=Rol.GERENTE_DISTRITO, gerente_id=5)
    out = coaching_more_router.vms(pais_codigo="DO", db=db, current_user=user)
    assert [r["id"] for r in out] == [1]


def test_coaching_more_vms_sin_pais_no_restringe():
    rms = [_rm(1, pais_codigo="DO"), _rm(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms)
    user = SimpleNamespace(rol=Rol.ADMIN, gerente_id=None)
    out = coaching_more_router.vms(pais_codigo=None, db=db, current_user=user)
    assert {r["id"] for r in out} == {1, 2}


# ── /visita/lineas + visita_parrilla_service.listar_lineas ─────────────────────
def test_listar_lineas_service_filtra_por_pais():
    lineas = [_linea(1, "Linea DO", "DO"), _linea(2, "Linea GT", "GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(lineas)
    out = parrilla_svc.listar_lineas(db, pais_codigo="DO")
    assert [l["id"] for l in out] == [1]


def test_listar_lineas_service_sin_pais_no_restringe():
    lineas = [_linea(1, "Linea DO", "DO"), _linea(2, "Linea GT", "GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(lineas)
    out = parrilla_svc.listar_lineas(db)
    assert {l["id"] for l in out} == {1, 2}


def test_router_listar_lineas_pasa_pais_codigo(monkeypatch):
    """El router ahora también pasa `permitidos` (piso de país, ver `_scope.paises_visibles`)
    como tercer argumento posicional a `visita_parrilla_service.listar_lineas`. Con
    `pais_codigo` explícito el router no calcula el piso (queda en `None`) — lo que este
    test sigue comprobando es que el `pais_codigo` pedido se propaga tal cual al servicio."""
    llamada = {}

    def fake_listar(db, pais_codigo=None, permitidos=None):
        llamada["pais_codigo"] = pais_codigo
        llamada["permitidos"] = permitidos
        return []
    monkeypatch.setattr(parrilla_svc, "listar_lineas", fake_listar)
    visita_router.listar_lineas(pais_codigo="DO", db=MagicMock(), current_user=SimpleNamespace())
    assert llamada["pais_codigo"] == "DO"


# ── visita_cobertura_service._rm_ids_por ────────────────────────────────────────
def test_rm_ids_por_sin_ningun_filtro_devuelve_none():
    db = MagicMock()
    assert cob._rm_ids_por(db, None, None) is None
    assert cob._rm_ids_por(db, None, None, None) is None
    db.query.assert_not_called()


def test_rm_ids_por_pais_excluye_otro_pais():
    rms = [_rm(1, pais_codigo="DO"), _rm(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms, proj=("id",))
    assert cob._rm_ids_por(db, None, None, "DO") == [1]


def test_rm_ids_por_combina_gerente_y_pais():
    rms = [_rm(1, gerente_id=5, pais_codigo="DO"),
           _rm(2, gerente_id=5, pais_codigo="GT"),
           _rm(3, gerente_id=9, pais_codigo="DO")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms, proj=("id",))
    assert cob._rm_ids_por(db, 5, None, "DO") == [1]


def test_rm_ids_por_compatibilidad_llamada_de_2_posicionales():
    """`visita_cierre_service.estado_ruptura` llama `_rm_ids_por(db, gerente_id,
    linea_id)` sin `pais_codigo` — debe seguir devolviendo lo mismo que antes."""
    rms = [_rm(1, gerente_id=5, pais_codigo="DO"), _rm(2, gerente_id=5, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(rms, proj=("id",))
    assert sorted(cob._rm_ids_por(db, 5, None)) == [1, 2]


# ── visita_cobertura_service._cobertura_base ────────────────────────────────────
def test_cobertura_base_agregado_filtra_por_pais(monkeypatch):
    """Sin vm_id/gerente_id/linea_id (ADMIN viendo "todos los visitadores"), el panel
    agregado de Cobertura debe acotarse por `pais_codigo` si se indica."""
    _patch_gating_cob(monkeypatch)
    monkeypatch.setattr(cob, "_mapa_visitas", lambda db, ciclo, vm: {})
    rms = [_rm(100, pais_codigo="DO"), _rm(200, pais_codigo="GT")]
    medicos = [_med(1, vm_id=100), _med(2, vm_id=200)]

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if _es(args, RepresentanteMedico.id):
            return _FakeQuery(rms, proj=("id",))
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    r = cob._cobertura_base(db, ciclo_id=10, vm_id=None, pais_codigo="DO")
    assert r["panel"] == 1
    assert [m["id"] for m in r["sin_visita"]] == [1]  # solo el médico del VM de DO


def test_cobertura_base_sin_filtro_no_restringe(monkeypatch):
    """Compatibilidad: sin gerente_id/linea_id/pais_codigo, el agregado sigue viendo TODO
    (comportamiento previo al fix)."""
    _patch_gating_cob(monkeypatch)
    monkeypatch.setattr(cob, "_mapa_visitas", lambda db, ciclo, vm: {})
    medicos = [_med(1, vm_id=100), _med(2, vm_id=200)]
    db = MagicMock()
    db.query.return_value = _FakeQuery(medicos)  # única consulta posible: MedicoVisita
    r = cob._cobertura_base(db, ciclo_id=10, vm_id=None)
    assert r["panel"] == 2


# ── visita_cobertura_service.ciclo_por_defecto ──────────────────────────────────
def test_ciclo_por_defecto_usa_pais_codigo_sin_vm(monkeypatch):
    llamado = {}

    def fake_ciclo_abierto(db, pais_codigo):
        llamado["pais"] = pais_codigo
        return SimpleNamespace(id=77) if pais_codigo == "DO" else None
    monkeypatch.setattr(cob, "_ciclo_abierto", fake_ciclo_abierto)
    cid = cob.ciclo_por_defecto(MagicMock(), vm_id=None, pais_codigo="DO")
    assert cid == 77
    assert llamado["pais"] == "DO"


def test_ciclo_por_defecto_vm_tiene_prioridad_sobre_pais(monkeypatch):
    """Con `vm_id`, se usa el país DEL VM (nunca el `pais_codigo` del parámetro,
    redundante o potencialmente inconsistente si vinieran distintos)."""
    rm = SimpleNamespace(id=5, pais_codigo="DO")
    db = MagicMock()
    db.query.return_value = _FakeQuery([rm])

    llamado = {}

    def fake_ciclo_abierto(db, pais_codigo):
        llamado["pais"] = pais_codigo
        return SimpleNamespace(id=99)
    monkeypatch.setattr(cob, "_ciclo_abierto", fake_ciclo_abierto)
    cid = cob.ciclo_por_defecto(db, vm_id=5, pais_codigo="GT")
    assert cid == 99
    assert llamado["pais"] == "DO"  # el país del VM manda, no el parámetro


# ── visita_cobertura_service.resumen_cobertura ──────────────────────────────────
def test_resumen_cobertura_sin_ciclo_id_usa_pais_en_ciclo_por_defecto(monkeypatch):
    llamado = {}

    def fake_ciclo_por_defecto(db, vm_id=None, pais_codigo=None):
        llamado["pais"] = pais_codigo
        return None  # sin ciclo abierto -> corte temprano
    monkeypatch.setattr(cob, "ciclo_por_defecto", fake_ciclo_por_defecto)
    r = cob.resumen_cobertura(MagicMock(), ciclo_id=None, pais_codigo="DO")
    assert llamado["pais"] == "DO"
    assert r["ciclo_id"] is None


def test_resumen_cobertura_propaga_pais_a_partes_internas(monkeypatch):
    """`resumen_cobertura` debe pasar `pais_codigo` a `_cobertura_base` (panel principal)
    y a los 2 usos de `_rm_ids_por` (ruptura y acompañamiento) — y la ruptura debe quedar
    acotada al país cuando ADMIN/gerencias consultan "todos los visitadores"."""
    _patch_gating_cob(monkeypatch)

    llamados_base = []

    def fake_base(db, ciclo_id, vm_id, gerente_id=None, linea_id=None,
                  solo_ruptura=False, pais_codigo=None, permitidos=None):
        llamados_base.append(pais_codigo)
        return {"panel": 0, "visitados": 0, "con_revisita": 0, "sin_visitar": 0,
                "pct_cobertura": 0, "pct_completa": 0, "pct_gap": 0,
                "categorias": {}, "sin_visita": [], "falta_revisita": []}
    monkeypatch.setattr(cob, "_cobertura_base", fake_base)

    llamados_rm = []

    def fake_rm_ids_por(db, gerente_id, linea_id, pais_codigo=None, permitidos=None):
        llamados_rm.append(pais_codigo)
        return [100] if pais_codigo == "DO" else None
    monkeypatch.setattr(cob, "_rm_ids_por", fake_rm_ids_por)

    m_do = _med(1, vm_id=100)
    m_do.ciclos_sin_visita = 5
    m_gt = _med(2, vm_id=200)
    m_gt.ciclos_sin_visita = 5

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery([m_do, m_gt])
        if _es(args, VisitaRegistro):
            return _FakeQuery([])
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    r = cob.resumen_cobertura(db, ciclo_id=10, pais_codigo="DO")
    assert llamados_base == ["DO"]
    assert llamados_rm == ["DO", "DO"]  # ruptura + acompañamiento
    assert [m["id"] for m in r["ruptura"]] == [1]  # solo el VM 100 (DO); el 200 (GT) excluido


def test_resumen_cobertura_sin_pais_no_restringe(monkeypatch):
    """Compatibilidad: llamar sin `pais_codigo` (como hoy el frontend) no invoca
    `_rm_ids_por` con un país y no restringe nada nuevo."""
    _patch_gating_cob(monkeypatch)

    def fake_base(db, ciclo_id, vm_id, gerente_id=None, linea_id=None,
                  solo_ruptura=False, pais_codigo=None, permitidos=None):
        assert pais_codigo is None
        return {"panel": 2, "visitados": 0, "con_revisita": 0, "sin_visitar": 2,
                "pct_cobertura": 0, "pct_completa": 0, "pct_gap": 100,
                "categorias": {}, "sin_visita": [], "falta_revisita": []}
    monkeypatch.setattr(cob, "_cobertura_base", fake_base)

    m1 = _med(1, vm_id=100)
    m2 = _med(2, vm_id=200)

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery([m1, m2])
        if _es(args, VisitaRegistro):
            return _FakeQuery([])
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    r = cob.resumen_cobertura(db, ciclo_id=10)
    assert r["panel"] == 2


# ── visita_cobertura_service.ranking_visitadores ────────────────────────────────
def test_ranking_visitadores_filtra_por_pais(monkeypatch):
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db, vm_id=None, pais_codigo=None: 10)
    monkeypatch.setattr(
        cob, "_rm_ids_por",
        lambda db, g, l, pais_codigo=None, permitidos=None: [100] if pais_codigo == "DO" else None)
    monkeypatch.setattr(
        cob, "_cobertura_base",
        lambda db, ciclo_id, vm: {"pct_completa": 50, "sin_visitar": 0, "pct_cobertura": 80})

    medicovisita_vm = [SimpleNamespace(vm_id=100, activo=True),
                       SimpleNamespace(vm_id=200, activo=True)]
    rms = [_rm(100, nombre="VM DO"), _rm(200, nombre="VM GT")]

    def query(*args):
        if _es(args, MedicoVisita.vm_id):
            return _FakeQuery(medicovisita_vm, proj=("vm_id",))
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.nombre):
            return _FakeQuery(rms, proj=("id", "nombre"))
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.zona):
            return _FakeQuery(rms, proj=("id", "zona"))
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    r = cob.ranking_visitadores(db, ciclo_id=None, metrica="cobertura", pais_codigo="DO")
    assert [it["vm_id"] for it in r["items"]] == [100]


def test_ranking_visitadores_sin_pais_no_restringe(monkeypatch):
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db, vm_id=None, pais_codigo=None: 10)
    monkeypatch.setattr(
        cob, "_cobertura_base",
        lambda db, ciclo_id, vm: {"pct_completa": 50, "sin_visitar": 0, "pct_cobertura": 80})

    medicovisita_vm = [SimpleNamespace(vm_id=100, activo=True),
                       SimpleNamespace(vm_id=200, activo=True)]
    rms = [_rm(100, nombre="VM DO"), _rm(200, nombre="VM GT")]

    def query(*args):
        if _es(args, MedicoVisita.vm_id):
            return _FakeQuery(medicovisita_vm, proj=("vm_id",))
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.nombre):
            return _FakeQuery(rms, proj=("id", "nombre"))
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.zona):
            return _FakeQuery(rms, proj=("id", "zona"))
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    r = cob.ranking_visitadores(db, ciclo_id=None, metrica="cobertura")
    assert sorted(it["vm_id"] for it in r["items"]) == [100, 200]


# ── visita_service.listar_medicos ───────────────────────────────────────────────
def test_listar_medicos_service_filtra_panel_agregado_por_pais(monkeypatch):
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db: None)  # evita _mapa_visitas

    rms = [_rm(100, pais_codigo="DO"), _rm(200, pais_codigo="GT")]
    medicos = [_med(1, vm_id=100), _med(2, vm_id=200)]

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if _es(args, RepresentanteMedico.id):
            return _FakeQuery(rms, proj=("id",))
        if args and args[0] is RepresentanteMedico.id and len(args) == 2:
            # db.query(RepresentanteMedico.id, RepresentanteMedico.linea_id)
            return _FakeQuery(rms, proj=("id", "linea_id"))
        if args and args[0] is Especialidad.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is Linea.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is VisitaRegistro.medico_id:
            return _FakeQuery([], proj=None)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    out = vs.listar_medicos(db, vm_id=None, pais_codigo="DO", lite=True)
    assert [m["id"] for m in out] == [1]  # solo el médico del panel de un VM de DO


def test_listar_medicos_service_sin_pais_no_restringe(monkeypatch):
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db: None)
    medicos = [_med(1, vm_id=100), _med(2, vm_id=200)]

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if args and args[0] is RepresentanteMedico.id and len(args) == 2:
            return _FakeQuery([], proj=("id", "linea_id"))
        if args and args[0] is Especialidad.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is Linea.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is VisitaRegistro.medico_id:
            return _FakeQuery([], proj=None)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    out = vs.listar_medicos(db, vm_id=None, lite=True)
    assert {m["id"] for m in out} == {1, 2}


def test_listar_medicos_service_con_vm_id_y_pais_contradictorio_no_ve_nada(monkeypatch):
    """Ronda 2 (hallazgo Critical de revisión, ago-2026): `vm_id` YA NO tiene prioridad
    exclusiva sobre `pais_codigo`/`permitidos` — se aplican los DOS con AND. Si el `vm_id`
    pedido no pertenece al país filtrado (aquí el 100 es de DO, se filtra por GT), el panel
    queda vacío en vez de devolver el médico igual."""
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db: None)
    medicos = [_med(1, vm_id=100)]
    rms_gt = []  # el RM 100 es de DO: no aparece al filtrar por GT

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if _es(args, RepresentanteMedico.id):
            return _FakeQuery(rms_gt, proj=("id",))
        if args and args[0] is RepresentanteMedico.id and len(args) == 2:
            return _FakeQuery([], proj=("id", "linea_id"))
        if args and args[0] is Especialidad.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is Linea.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is VisitaRegistro.medico_id:
            return _FakeQuery([], proj=None)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    out = vs.listar_medicos(db, vm_id=100, pais_codigo="GT", lite=True)
    assert out == []


def test_listar_medicos_service_con_vm_id_y_pais_coincidente_si_ve(monkeypatch):
    """Compatibilidad: `vm_id` + `pais_codigo` que SÍ coinciden (el VM es de ese país)
    siguen funcionando con normalidad — el AND no bloquea lo legítimo."""
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db: None)
    medicos = [_med(1, vm_id=100)]
    rms_do = [_rm(100, pais_codigo="DO")]

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if _es(args, RepresentanteMedico.id):
            return _FakeQuery(rms_do, proj=("id",))
        if args and args[0] is RepresentanteMedico.id and len(args) == 2:
            return _FakeQuery([], proj=("id", "linea_id"))
        if args and args[0] is Especialidad.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is Linea.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is VisitaRegistro.medico_id:
            return _FakeQuery([], proj=None)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    out = vs.listar_medicos(db, vm_id=100, pais_codigo="DO", lite=True)
    assert [m["id"] for m in out] == [1]


def test_listar_medicos_service_con_vm_id_y_permitidos_contradictorio_no_ve_nada(monkeypatch):
    """El caso REAL del hallazgo: sin `pais_codigo` explícito (el cliente no lo manda) pero
    con `permitidos` restringido — el piso se aplica igual, aunque nadie pidió país."""
    monkeypatch.setattr(cob, "ciclo_por_defecto", lambda db: None)
    medicos = [_med(1, vm_id=100)]
    rms_do = []  # el 100 es de GT: no aparece al filtrar por permitidos={DO}

    def query(*args):
        if _es(args, MedicoVisita):
            return _FakeQuery(medicos)
        if _es(args, RepresentanteMedico.id):
            return _FakeQuery(rms_do, proj=("id",))
        if args and args[0] is RepresentanteMedico.id and len(args) == 2:
            return _FakeQuery([], proj=("id", "linea_id"))
        if args and args[0] is Especialidad.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is Linea.id:
            return _FakeQuery([], proj=("id", "nombre"))
        if args and args[0] is VisitaRegistro.medico_id:
            return _FakeQuery([], proj=None)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query

    out = vs.listar_medicos(db, vm_id=100, permitidos={"DO"}, lite=True)
    assert out == []


# ── Routers: verifican que pais_codigo llega al servicio ────────────────────────
def test_router_visita_medicos_pasa_pais_codigo(monkeypatch):
    llamada = {}

    def fake_listar(db, vm_id=None, incluir_inactivos=False, lite=False, pais_codigo=None,
                    permitidos=None):
        llamada["pais_codigo"] = pais_codigo
        return []
    monkeypatch.setattr(vs, "listar_medicos", fake_listar)
    user = SimpleNamespace(rol="ADMIN")
    visita_router.listar_medicos(vm_id=None, pais_codigo="DO", db=MagicMock(), current_user=user)
    assert llamada["pais_codigo"] == "DO"


def test_router_cobertura_resumen_pasa_pais_codigo(monkeypatch):
    llamada = {}

    def fake_resumen(db, ciclo_id, vm_id, gerente_id, linea_id, solo_ruptura, pais_codigo,
                     permitidos=None):
        llamada["pais_codigo"] = pais_codigo
        return {}
    monkeypatch.setattr(cob, "resumen_cobertura", fake_resumen)
    user = SimpleNamespace(rol="ADMIN")
    visita_router.cobertura_resumen(pais_codigo="DO", db=MagicMock(), current_user=user)
    assert llamada["pais_codigo"] == "DO"


def test_router_cobertura_ranking_pasa_pais_codigo(monkeypatch):
    llamada = {}

    def fake_ranking(db, ciclo_id, metrica, pais_codigo, permitidos=None):
        llamada["pais_codigo"] = pais_codigo
        return {}
    monkeypatch.setattr(cob, "ranking_visitadores", fake_ranking)
    user = SimpleNamespace(rol="ADMIN")
    visita_router.cobertura_ranking(metrica="cobertura", pais_codigo="DO",
                                    db=MagicMock(), current_user=user)
    assert llamada["pais_codigo"] == "DO"


# ── /visita/gerentes (Hallazgo 1) ────────────────────────────────────────────
def test_router_visita_gerentes_filtra_por_pais():
    gerentes = [_gerente(1, pais_codigo="DO"), _gerente(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(gerentes)
    out = visita_router.listar_gerentes(pais_codigo="DO", db=db, current_user=SimpleNamespace())
    assert [g["id"] for g in out] == [1]


def test_router_visita_gerentes_sin_pais_no_restringe():
    """Compatibilidad: sin `pais_codigo` sigue viendo TODOS los gerentes."""
    gerentes = [_gerente(1, pais_codigo="DO"), _gerente(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(gerentes)
    out = visita_router.listar_gerentes(pais_codigo=None, db=db, current_user=SimpleNamespace())
    assert {g["id"] for g in out} == {1, 2}


# ── /medicos/maestro y /medicos/maestro/kpis (Hallazgo 2) ───────────────────────
def test_router_maestro_medicos_listar_filtra_por_pais():
    medicos = [_medico(1, pais_codigo="DO"), _medico(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(medicos)
    out = mm_router.listar(pais_codigo="DO", skip=0, limit=300, db=db, _u=SimpleNamespace())
    assert [m.id for m in out] == [1]


def test_router_maestro_medicos_listar_sin_pais_no_restringe():
    """Compatibilidad: sin `pais_codigo` sigue viendo médicos de TODOS los países."""
    medicos = [_medico(1, pais_codigo="DO"), _medico(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.return_value = _FakeQuery(medicos)
    out = mm_router.listar(pais_codigo=None, skip=0, limit=300, db=db, _u=SimpleNamespace())
    assert {m.id for m in out} == {1, 2}


def _query_kpis(medicos):
    """`kpis()` hace 2 tipos de consulta: `func.count(Medico.id)...` (varias veces,
    filtradas) y `db.query(MedicoVisita.maestro_medico_id)...` (asignados, aquí vacía
    a propósito para no tener que fabricar el operador `isnot(None)` en el doble)."""
    def query(*args):
        if _es(args, MedicoVisita.maestro_medico_id):
            return _FakeQuery([], proj=("maestro_medico_id",))
        return _FakeQuery(medicos)
    return query


def test_router_maestro_medicos_kpis_filtra_por_pais():
    medicos = [_medico(1, pais_codigo="DO"), _medico(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.side_effect = _query_kpis(medicos)
    out = mm_router.kpis(pais_codigo="DO", db=db, _u=SimpleNamespace())
    assert out["total"] == 1
    assert out["activos"] == 1


def test_router_maestro_medicos_kpis_sin_pais_no_restringe():
    """Compatibilidad: sin `pais_codigo` los KPIs siguen contando TODOS los países."""
    medicos = [_medico(1, pais_codigo="DO"), _medico(2, pais_codigo="GT")]
    db = MagicMock()
    db.query.side_effect = _query_kpis(medicos)
    out = mm_router.kpis(pais_codigo=None, db=db, _u=SimpleNamespace())
    assert out["total"] == 2


# ── /examenes/evaluados (Hallazgo 6) ─────────────────────────────────────────────
def test_router_examenes_evaluados_filtra_por_pais():
    rms = [_rm(1, pais_codigo="DO", nombre="RM1"), _rm(2, pais_codigo="GT", nombre="RM2")]
    gers = [_gerente(10, pais_codigo="DO"), _gerente(20, pais_codigo="GT")]

    def query(*args):
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.nombre):
            return _FakeQuery(rms)
        if _es(args, Gerente.id, Gerente.nombre, Gerente.tipo):
            return _FakeQuery(gers)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query
    out = examenes_router.listar_evaluados(pais_codigo="DO", db=db, current_user=SimpleNamespace())
    assert [r["id"] for r in out["rms"]] == [1]
    assert [g["id"] for g in out["gerentes"]] == [10]


def test_router_examenes_evaluados_sin_pais_no_restringe():
    """Compatibilidad: sin `pais_codigo` el selector de asignación sigue viendo
    RM/gerentes de TODOS los países (comportamiento previo al fix)."""
    rms = [_rm(1, pais_codigo="DO", nombre="RM1"), _rm(2, pais_codigo="GT", nombre="RM2")]
    gers = [_gerente(10, pais_codigo="DO"), _gerente(20, pais_codigo="GT")]

    def query(*args):
        if _es(args, RepresentanteMedico.id, RepresentanteMedico.nombre):
            return _FakeQuery(rms)
        if _es(args, Gerente.id, Gerente.nombre, Gerente.tipo):
            return _FakeQuery(gers)
        raise AssertionError(args)
    db = MagicMock()
    db.query.side_effect = query
    out = examenes_router.listar_evaluados(pais_codigo=None, db=db, current_user=SimpleNamespace())
    assert {r["id"] for r in out["rms"]} == {1, 2}
    assert {g["id"] for g in out["gerentes"]} == {10, 20}
