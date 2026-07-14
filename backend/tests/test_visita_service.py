"""Tests Módulo de Visita Médica — Fase 1 (antiduplicados + validación de nombre)."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import visita_service
from app.schemas.visita import MedicoVisitaCrear


def _db_con(medicos):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = medicos
    return db


def test_duplicado_dispara_con_2_palabras():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL ANTONIO", direccion="x")])
    dups = visita_service.detectar_duplicados(db, "PEREZ VALDEZ JUAN")
    assert len(dups) == 1 and dups[0]["palabras_coinciden"] == 2


def test_duplicado_no_dispara_con_1_palabra():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    # Solo "VALDEZ" en común (1 palabra) → no se considera duplicado.
    assert visita_service.detectar_duplicados(db, "GOMEZ VALDEZ CARLOS") == []
    # Ninguna palabra en común → tampoco.
    assert visita_service.detectar_duplicados(db, "GOMEZ SUERO CARLOS") == []


def test_crear_sin_confirmar_levanta_duplicado(monkeypatch):
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    datos = MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ VALDEZ JUAN", categoria="A")
    with pytest.raises(visita_service.DuplicadoMedicoError):
        visita_service.crear_medico(db, datos, usuario_id=1)


def test_nombre_se_normaliza_a_mayusculas():
    m = MedicoVisitaCrear(vm_id=1, nombre_completo="manuel  perez garcia", categoria="a")
    assert m.nombre_completo == "MANUEL PEREZ GARCIA" and m.categoria == "A"


def test_nombre_1_palabra_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ", categoria="A")


def test_nombre_con_punto_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="DR. PEREZ GARCIA", categoria="A")


def test_categoria_invalida_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="MANUEL PEREZ", categoria="Z")


def test_categoria_d_es_valida():
    m = MedicoVisitaCrear(vm_id=1, nombre_completo="MANUEL PEREZ", categoria="d")
    assert m.categoria == "D"


# ── Aprobación de alta/baja (gating de cobertura) ─────────────────────
from app.services.visita_aprobacion_service import cuenta_en_ciclo

# ciclos: 10 -> orden 2026*1000+3=2026003 ; 11 -> 2026004 (siguiente)
_ORD = {10: 2026003, 11: 2026004}


def _med(**kw):
    base = dict(activo=True, estado_aprobacion="APROBADO", ciclo_alta_id=None, ciclo_baja_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_medico_existente_cuenta_siempre():
    assert cuenta_en_ciclo(_med(), _ORD[10], _ORD) is True


def test_pendiente_alta_no_cuenta():
    assert cuenta_en_ciclo(_med(estado_aprobacion="PENDIENTE_ALTA", ciclo_alta_id=10), _ORD[10], _ORD) is False


def test_rechazado_no_cuenta():
    assert cuenta_en_ciclo(_med(estado_aprobacion="RECHAZADO"), _ORD[10], _ORD) is False


def test_alta_aprobada_cuenta_en_el_mismo_ciclo_de_solicitud():
    # v2 (jul-2026): aprobada con alta en ciclo 10 → cuenta desde el MISMO ciclo 10.
    m = _med(estado_aprobacion="APROBADO", ciclo_alta_id=10)
    assert cuenta_en_ciclo(m, _ORD[10], _ORD) is True
    assert cuenta_en_ciclo(m, _ORD[11], _ORD) is True


def test_baja_pendiente_cuenta_en_ciclo_actual_no_en_el_siguiente():
    # Baja solicitada en ciclo 10: cuenta en 10, deja de contar en 11.
    m = _med(estado_aprobacion="PENDIENTE_BAJA", ciclo_baja_id=10)
    assert cuenta_en_ciclo(m, _ORD[10], _ORD) is True
    assert cuenta_en_ciclo(m, _ORD[11], _ORD) is False


def test_inactivo_no_cuenta():
    assert cuenta_en_ciclo(_med(activo=False), _ORD[10], _ORD) is False


# ── Registro de visita ────────────────────────────────────────────────
from app.schemas.visita import VisitaRegistrar, VisitaNoVisita


def test_visita_comentario_generico_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="VISITA OK")


def test_visita_comentario_corto_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="corto")


def test_visita_valida_normaliza_tipo():
    v = VisitaRegistrar(medico_id=1, tipo_visita="v", comentario="MEDICO SOLICITO ESTUDIO CLINICO")
    assert v.tipo_visita == "V"


def test_visita_tipo_invalido_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="X", comentario="COMENTARIO VALIDO LARGO")


def test_visita_hace_minutos_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        VisitaRegistrar(medico_id=1, tipo_visita="V", comentario="COMENTARIO VALIDO", hace_minutos=90)


def test_no_visita_causa_valida():
    nv = VisitaNoVisita(medico_id=1, causa="Consultorio Cerrado (sin aviso previo)")
    assert nv.causa.startswith("Consultorio")


def test_no_visita_causa_invalida_falla():
    with pytest.raises(ValueError):
        VisitaNoVisita(medico_id=1, causa="porque sí")


# ── Proyección ────────────────────────────────────────────────────────
from datetime import date
from app.services.visita_cobertura_service import _dias_habiles


def test_dias_habiles():
    assert _dias_habiles(date(2026, 6, 1), date(2026, 6, 5)) == 5   # lun→vie
    assert _dias_habiles(date(2026, 6, 1), date(2026, 6, 8)) == 6   # incluye finde
    assert _dias_habiles(None, None) == 19                          # fallback


# ── Planeación del ciclo (reglas P01/P02/P03) ─────────────────────────
from app.schemas.visita import PlaneacionItem
from app.services.visita_planeacion_service import _validar


def _it(medico_id, tipo, semana):
    return PlaneacionItem(medico_id=medico_id, tipo_visita=tipo, semana=semana)


def test_planeacion_valida_vista_y_revisita_posterior():
    _validar([_it(1, "V", 1), _it(1, "R", 3)])  # no levanta


def test_planeacion_valida_misma_semana_sin_dia():
    _validar([_it(1, "V", 2), _it(1, "R", 2)])  # V+R misma semana, sin día → ok


def test_planeacion_p01_maximo_dos_por_medico():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 1), _it(1, "R", 2), _it(1, "V", 3)])


def test_planeacion_dos_vistas_mismo_medico_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 1), _it(1, "V", 2)])


def test_planeacion_p02_revisita_antes_de_vista_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "V", 3), _it(1, "R", 1)])


def test_planeacion_revisita_sin_vista_falla():
    with pytest.raises(ValueError):
        _validar([_it(1, "R", 2)])


def test_planeacion_p03_mismo_dia_falla():
    v = PlaneacionItem(medico_id=1, tipo_visita="V", semana=2, dia_semana="Lunes")
    r = PlaneacionItem(medico_id=1, tipo_visita="R", semana=2, dia_semana="Lunes")
    with pytest.raises(ValueError):
        _validar([v, r])


# ── Ruptura de secuencia / Cierre de ciclo ────────────────────────────
from app.services import visita_cierre_service as cs


def test_severidad_por_ciclos_sin_visita():
    assert cs._severidad(0) == "ninguna"
    assert cs._severidad(1) == "alerta"
    assert cs._severidad(2) == "grave"
    assert cs._severidad(3) == "critica"
    assert cs._severidad(7) == "critica"


def _patch_gating(monkeypatch):
    """El cierre filtra médicos vigentes vía visita_aprobacion_service; en los tests
    unitarios lo neutralizamos (cuenta = activo)."""
    import app.services.visita_aprobacion_service as aps
    monkeypatch.setattr(aps, "ordenes_ciclo", lambda db: {})
    monkeypatch.setattr(aps, "cuenta_en_ciclo", lambda m, o, ords: m.activo)


def test_cierre_resetea_visitados_e_incrementa_ausentes(monkeypatch):
    # m1 visitado (contador 5 → 0); m2 sin visita (contador 2 → 3 = crítica)
    m1 = SimpleNamespace(id=1, ciclos_sin_visita=5, activo=True)
    m2 = SimpleNamespace(id=2, ciclos_sin_visita=2, activo=True)
    db = MagicMock()
    db.query.return_value.all.return_value = [m1, m2]
    _patch_gating(monkeypatch)
    monkeypatch.setattr(cs, "_mapa_visitas", lambda db, ciclo, vm: {1: {"v": True, "r": False}})
    r = cs._resumen_cierre(db, ciclo_id=10, aplicar=True, usuario_id=None)
    assert r["panel"] == 2 and r["visitados"] == 1 and r["sin_visitar"] == 1
    assert r["ruptura_nueva"] == 1 and r["ruptura_critica"] == 1
    assert m1.ciclos_sin_visita == 0   # reseteado por haber sido visitado
    assert m2.ciclos_sin_visita == 3   # incrementado a ruptura crítica


def test_cierre_previsualizar_no_muta(monkeypatch):
    m = SimpleNamespace(id=1, ciclos_sin_visita=1, activo=True)
    db = MagicMock()
    db.query.return_value.all.return_value = [m]
    db.query.return_value.filter.return_value.first.return_value = None  # no cerrado aún
    _patch_gating(monkeypatch)
    monkeypatch.setattr(cs, "_mapa_visitas", lambda db, ciclo, vm: {})   # nadie visitado
    monkeypatch.setattr(cs, "ciclo_por_defecto", lambda db: 10)
    r = cs.previsualizar_cierre(db, ciclo_id=10)
    assert r["sin_visitar"] == 1 and r["ya_cerrado"] is False
    assert m.ciclos_sin_visita == 1    # NO se modificó (dry-run)


def test_cierre_bloquea_si_ya_cerrado(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fecha_cierre=None)
    with pytest.raises(cs.CicloVisitaYaCerradoError):
        cs.cerrar_ciclo(db, ciclo_id=10, usuario_id=1)


# ── Parrilla promocional / Muestras ───────────────────────────────────
from app.schemas.visita import ParrillaItem, MuestraItem, MuestrasRegistrar
from app.services import visita_parrilla_service as ps


def test_parrilla_item_normaliza_producto():
    p = ParrillaItem(producto="  amox   500 ")
    assert p.producto == "amox 500"


def test_muestra_item_cantidad_minima_falla():
    with pytest.raises(ValueError):
        MuestraItem(producto="X1", cantidad=0)


def test_muestras_requiere_al_menos_una_entrega():
    with pytest.raises(ValueError):
        MuestrasRegistrar(medico_id=1, entregas=[])


def test_parrilla_producto_duplicado_falla(monkeypatch):
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda db: 5)
    db = MagicMock()
    items = [ParrillaItem(producto="Amoxicilina"), ParrillaItem(producto="AMOXICILINA")]
    with pytest.raises(ValueError):
        ps.guardar_parrilla(db, 5, 1, items, usuario_id=1)


def test_muestras_medico_de_otro_panel_falla(monkeypatch):
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda db: 5)
    monkeypatch.setattr(ps, "_guard_ciclo_abierto", lambda db, ciclo_id: None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=9, vm_id=2)
    with pytest.raises(ValueError):
        ps.registrar_muestras(db, vm_id=1, ciclo_id=5, medico_id=9,
                              entregas=[MuestraItem(producto="X1", cantidad=2)], usuario_id=1)


# ── Costo & ROI ───────────────────────────────────────────────────────
from app.services.visita_costo_service import _calcular_roi


def test_roi_calculo_rentable():
    # 100 contactos*50 + 200 muestras*20 + 5000 fijo = 5000+4000+5000 = 14000
    # ingresos 21000 -> utilidad 7000, ROI 50%
    r = _calcular_roi(contactos=100, medicos=40, muestras=200,
                      costo_visita=50, costo_muestra=20, costo_fijo=5000, ingresos=21000)
    assert r["costo_total"] == 14000.0
    assert r["costo_por_contacto"] == 140.0
    assert r["costo_por_medico"] == 350.0
    assert r["utilidad"] == 7000.0
    assert r["roi_pct"] == 50.0
    assert r["ratio_ingreso_costo"] == 1.5
    assert r["rentable"] is True


def test_roi_no_rentable_da_roi_negativo():
    r = _calcular_roi(10, 5, 0, costo_visita=100, costo_muestra=0, costo_fijo=0, ingresos=400)
    # costo 1000, ingresos 400 -> utilidad -600, ROI -60%
    assert r["costo_total"] == 1000.0 and r["utilidad"] == -600.0
    assert r["roi_pct"] == -60.0 and r["rentable"] is False


def test_roi_sin_costo_devuelve_none():
    r = _calcular_roi(0, 0, 0, 0, 0, 0, ingresos=0)
    assert r["costo_total"] == 0.0
    assert r["roi_pct"] is None and r["ratio_ingreso_costo"] is None and r["rentable"] is None


# ── Visita v2: guards de ciclo cerrado + GPS/foto ─────────────────────────
def test_guardar_parrilla_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_parrilla_service as ps
    from unittest.mock import MagicMock
    import pytest
    db = MagicMock()
    monkeypatch.setattr(ps, "ciclo_por_defecto", lambda d: 5)

    def _cerrado(d, c):
        raise ps.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(ps.recalculo_service, "validar_ciclo_abierto", _cerrado)
    with pytest.raises(ValueError):
        ps.guardar_parrilla(db, ciclo_id=5, linea_id=1, items=[], usuario_id=1)


def test_guardar_estructura_rechaza_ciclo_cerrado(monkeypatch):
    import app.services.visita_costo_service as cs
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    import pytest
    db = MagicMock()
    monkeypatch.setattr(cs, "ciclo_por_defecto", lambda d: 5)

    def _cerrado(d, c):
        raise cs.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(cs.recalculo_service, "validar_ciclo_abierto", _cerrado)
    datos = SimpleNamespace(ciclo_id=5, linea_id=1, productos=[])
    with pytest.raises(ValueError):
        cs.guardar_estructura(db, datos, usuario_id=1)


def test_registrar_visita_persiste_gps(monkeypatch):
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    db = MagicMock()
    monkeypatch.setattr(rs, "_medico_del_vm", lambda d, vm, m: None)
    monkeypatch.setattr(rs, "ciclo_por_defecto", lambda d, vm=None: 7)
    monkeypatch.setattr(rs, "_guard_ciclo_abierto", lambda d, c: None)
    capturado = {}
    db.add.side_effect = lambda obj: capturado.__setitem__("obj", obj)
    datos = SimpleNamespace(medico_id=3, tipo_visita="V", comentario="ok visita larga",
                            hace_minutos=0, productos=[], latitud=18.47, longitud=-69.9)
    rs.registrar_visita(db, vm_id=1, datos=datos, usuario_id=1)
    assert float(capturado["obj"].latitud) == 18.47
    assert float(capturado["obj"].longitud) == -69.9


def test_guardar_foto_rechaza_no_imagen():
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    import pytest
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()
    with pytest.raises(ValueError):
        rs.guardar_foto_visita(db, 1, b"NOTIMAGE", "image/jpeg")


def test_guardar_foto_acepta_jpeg():
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    db = MagicMock()
    v = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = v
    rs.guardar_foto_visita(db, 1, b"\xff\xd8\xff\xe0resto", "image/jpeg")
    assert v.foto == b"\xff\xd8\xff\xe0resto"
    assert v.foto_mime == "image/jpeg"


def test_guardar_foto_rechaza_grande():
    import app.services.visita_registro_service as rs
    from unittest.mock import MagicMock
    import pytest
    db = MagicMock()
    big = b"\xff\xd8\xff" + b"x" * (rs.MAX_FOTO_BYTES + 1)
    with pytest.raises(ValueError):
        rs.guardar_foto_visita(db, 1, big, "image/jpeg")


def test_actualizar_medico_ignora_activo():
    """Regresión: editar un médico NUNCA debe tocar `activo` (alta/baja va por
    aprobación). Antes, el endpoint asignaba `datos.activo = None`, lo que marcaba
    el campo como 'set' en Pydantic y generaba UPDATE activo=NULL (viola NOT NULL)."""
    from types import SimpleNamespace
    from app.schemas.visita import MedicoVisitaActualizar
    from app.services import visita_service
    medico = SimpleNamespace(id=1, activo=True, categoria="B",
                             dias_consulta=None, horario_consulta=None, frecuencia_visita=None)
    db = SimpleNamespace(commit=lambda: None, refresh=lambda _x: None)
    datos = MedicoVisitaActualizar(activo=False, categoria="A",
                                   dias_consulta="Lunes, Miércoles", horario_consulta="Todo el día",
                                   frecuencia_visita="F2")
    visita_service.actualizar_medico(db, medico, datos, usuario_id=1)
    assert medico.activo is True                      # activo NO cambió
    assert medico.categoria == "A"                    # el resto sí se aplicó
    assert medico.dias_consulta == "Lunes, Miércoles"
    assert medico.horario_consulta == "Todo el día"
    assert medico.frecuencia_visita == "F2"


def test_actualizar_medico_nombre_solo_valida_si_cambia():
    """El nombre heredado no conforme (con punto) NO debe bloquear editar otros
    campos si el nombre no cambia; pero cambiarlo a uno inválido sí debe fallar."""
    from types import SimpleNamespace
    import pytest
    from app.schemas.visita import MedicoVisitaActualizar
    from app.services import visita_service
    db = SimpleNamespace(commit=lambda: None, refresh=lambda _x: None)

    # (a) nombre heredado con punto, sin cambiarlo → edita otros campos sin error
    medico = SimpleNamespace(id=1, activo=True, nombre_completo="DR. PEREZ GARCIA",
                             categoria="B", frecuencia_visita=None)
    datos = MedicoVisitaActualizar(nombre_completo="DR. PEREZ GARCIA", frecuencia_visita="F2")
    visita_service.actualizar_medico(db, medico, datos, usuario_id=1)
    assert medico.nombre_completo == "DR. PEREZ GARCIA"   # intacto
    assert medico.frecuencia_visita == "F2"               # el resto se aplicó

    # (b) cambiar el nombre a uno inválido (con punto) → ValueError
    medico2 = SimpleNamespace(id=1, activo=True, nombre_completo="DR. PEREZ GARCIA")
    datos2 = MedicoVisitaActualizar(nombre_completo="DR. NUEVO")
    with pytest.raises(ValueError):
        visita_service.actualizar_medico(db, medico2, datos2, usuario_id=1)


def test_medico_pendiente_no_visitable():
    """Regresión: un médico PENDIENTE_ALTA no puede recibir visita hasta ser aprobado."""
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    import pytest
    import app.services.visita_registro_service as rs
    db = MagicMock()
    pend = SimpleNamespace(id=5, vm_id=3, activo=True, estado_aprobacion="PENDIENTE_ALTA")
    db.query.return_value.filter.return_value.first.return_value = pend
    with pytest.raises(ValueError, match="pendiente de aprob"):
        rs._medico_del_vm(db, 3, 5)
    # Aprobado sí pasa
    aprob = SimpleNamespace(id=5, vm_id=3, activo=True, estado_aprobacion="APROBADO")
    db.query.return_value.filter.return_value.first.return_value = aprob
    assert rs._medico_del_vm(db, 3, 5) is aprob
