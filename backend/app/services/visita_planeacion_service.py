"""Planeación del Ciclo (Parte 3 del spec). Reglas:
  P01 máx 2 visitas por médico (1 Vista + 1 Revisita)
  P02 la Revisita en semana >= semana de la Vista
  P03 Vista y Revisita no el mismo día
Patrón delete-then-insert por (vm, ciclo). Cat A sin Revisita se reporta como aviso.

**Borrador → Publicada (jul-2026).** La planeación es el DENOMINADOR de la cobertura
(`visitados / planeados`): editable a mitad de ciclo, un VM subiría su cobertura quitando
del plan a los médicos que no visitó, sin visitar a nadie más. Por eso se guarda libremente
como borrador y, al publicarla, queda CONGELADA. Solo un ADMIN puede desbloquearla, con
motivo obligatorio y dejando rastro (`PlaneacionEvento`, append-only).
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, PlaneacionCiclo, PlaneacionEvento
from app.schemas.visita import PlaneacionItem
from app.services.visita_cobertura_service import ciclo_por_defecto, CICLO_DIAS_DEFAULT
from app.services import recalculo_service


def _ahora_utc() -> datetime:
    """UTC y sin huso: la escala en que estan definidas estas columnas.

    Un valor consciente aqui volveria a dejar lo almacenado en manos de la zona de la
    sesion de PostgreSQL. Hoy la conexion la fuerza a UTC (`app/db/database.py`), asi
    que funcionaria igual — pero por una opcion de conexion, no porque el codigo lo
    diga. Esa dependencia invisible es justo la que causo el desvio."""
    return datetime.now(timezone.utc).replace(tzinfo=None)



class PlaneacionPublicadaError(Exception):
    """La planeación ya está publicada: es dato base de cálculo y no se puede modificar."""


class PlaneacionEnRevisionError(PlaneacionPublicadaError):
    """La planeación está enviada al Gerente de Distrito: congelada mientras la revisa.

    Hereda de `PlaneacionPublicadaError` a propósito: todo camino que ya traducía «no se
    puede modificar» a 409 cubre también este estado sin tener que acordarse de él."""


class TopSinPlanearError(Exception):
    """La planeación omite médicos TOP. §7.3 del requerimiento de Mallén: al
    publicar, VISTA verifica que todos los TOP del panel estén incluidos y, si
    falta alguno, no permite publicar y muestra cuáles faltan."""


#: M1 de la revisión final: con un panel entero marcado TOP, concatenar todos
#: los nombres vuelve el mensaje del 409 una cadena de miles de caracteres en
#: un snackbar. Se capa igual que las listas vecinas del frontend (`.slice(0, 30)`).
_TOPE_NOMBRES = 30


def _formatear_nombres(nombres: list[str], tope: int = _TOPE_NOMBRES) -> str:
    if len(nombres) <= tope:
        return ", ".join(nombres)
    resto = len(nombres) - tope
    return f"{', '.join(nombres[:tope])} y {resto} más"


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


def _ultimo_evento(db: Session, vm_id: int, ciclo_id: int) -> PlaneacionEvento | None:
    return (db.query(PlaneacionEvento)
            .filter(PlaneacionEvento.vm_id == vm_id, PlaneacionEvento.ciclo_id == ciclo_id)
            .order_by(PlaneacionEvento.fecha.desc(), PlaneacionEvento.id.desc()).first())


def _estado_de(ev: PlaneacionEvento | None) -> str:
    """BORRADOR | ENVIADA | PUBLICADA | DEVUELTA, a partir del último evento.

    DESBLOQUEADA no es un estado propio: devuelve la planeación a borrador."""
    if ev is None or ev.evento == "DESBLOQUEADA":
        return "BORRADOR"
    return ev.evento


def estado_actual(db: Session, vm_id: int, ciclo_id: int) -> str:
    return _estado_de(_ultimo_evento(db, vm_id, ciclo_id))


def esta_publicada(db: Session, vm_id: int, ciclo_id: int) -> bool:
    """Publicada = el último evento del (vm, ciclo) es PUBLICADA. Sin eventos → borrador."""
    return estado_actual(db, vm_id, ciclo_id) == "PUBLICADA"


def _guard_no_publicada(db: Session, vm_id: int, ciclo_id: int) -> None:
    """La planeación solo se edita en BORRADOR o DEVUELTA.

    ENVIADA también se bloquea: si el representante pudiera seguir cambiándola mientras
    su gerente la revisa, el gerente aprobaría una planeación distinta de la que leyó."""
    estado = estado_actual(db, vm_id, ciclo_id)
    if estado == "PUBLICADA":
        raise PlaneacionPublicadaError(
            "La planeación de este ciclo ya fue publicada y no puede modificarse: es el dato "
            "base con el que se calcula tu cobertura. Si hay un error, un administrador debe "
            "desbloquearla indicando el motivo.")
    if estado == "ENVIADA":
        raise PlaneacionEnRevisionError(
            "La planeación está enviada a tu Gerente de Distrito y en revisión: no se puede "
            "modificar hasta que la apruebe o te la devuelva con sus observaciones.")


def _medicos_del_ciclo(db: Session, vm_id: int, ciclo_id: int) -> list[MedicoVisita]:
    """Los médicos del panel que CUENTAN en el ciclo.

    Filtra por `cuenta_en_ciclo` y no por `activo` a secas: con `activo` se
    incluirían altas pendientes de aprobación y bajas ya efectivas, y se
    exigiría planear médicos sobre los que el representante no puede actuar.
    """
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)
    medicos = db.query(MedicoVisita).filter(MedicoVisita.vm_id == vm_id).all()
    return [m for m in medicos if cuenta_en_ciclo(m, ciclo_orden, ordenes)]


def top_sin_planear(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """Médicos TOP del ciclo que no tienen NINGUNA fila en la planeación."""
    planeados = {p.medico_id for p in db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id not in planeados]


def top_sin_revisita(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """TOP planeados pero sin Revisita. Se AVISA, no se bloquea: el §7.3 solo
    exige que estén «incluidos», pero el §3.4 dice que un TOP no puede terminar
    sin visita y revisita — planearlo solo con V es planear el incumplimiento."""
    plan_ = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    planeados = {p.medico_id for p in plan_}
    con_revisita = {p.medico_id for p in plan_ if p.tipo_visita == "R"}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id in planeados and m.id not in con_revisita]


def publicar_planeacion(db: Session, vm_id: int, ciclo_id: int | None, usuario_id: int | None) -> dict:
    """Congela la planeación del (vm, ciclo). Irreversible salvo desbloqueo del ADMIN."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    _guard_no_publicada(db, vm_id, ciclo_id)
    n = _validar_publicable(db, vm_id, ciclo_id, "publicar")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="PUBLICADA",
                            usuario_id=usuario_id, items=n))
    db.commit()
    logger.info(f"Planeación PUBLICADA vm={vm_id} ciclo={ciclo_id} items={n} por usuario={usuario_id}")
    return {"publicada": True, "items": n, "ciclo_id": ciclo_id}


def _validar_publicable(db: Session, vm_id: int, ciclo_id: int, verbo: str) -> int:
    """Lo que tiene que cumplir una planeación para enviarse, aprobarse o publicarse.

    Se vuelve a exigir AL APROBAR y no solo al enviar: entre un momento y otro puede
    haberse marcado un médico TOP nuevo, y aprobar entonces congelaría un plan que ya
    no cumple el §7.3."""
    n = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).count()
    if n == 0:
        raise ValueError(f"No hay planeación que {verbo}: guarda al menos un médico primero.")
    faltantes = top_sin_planear(db, vm_id, ciclo_id)
    if faltantes:
        nombres = _formatear_nombres([f["nombre"] for f in faltantes])
        raise TopSinPlanearError(
            f"No se puede {verbo}: faltan {len(faltantes)} médico(s) TOP en la "
            f"planeación del ciclo. Agrégalos y vuelve a intentarlo: {nombres}.")
    return n


def enviar_planeacion(db: Session, vm_id: int, ciclo_id: int | None, usuario_id: int | None) -> dict:
    """El representante manda su planeación a su Gerente de Distrito para aprobación.

    Desde aquí queda bloqueada para él (ENVIADA) hasta que el gerente la apruebe —y
    entonces se publica— o se la devuelva con motivo."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    _guard_no_publicada(db, vm_id, ciclo_id)
    n = _validar_publicable(db, vm_id, ciclo_id, "enviar")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="ENVIADA",
                            usuario_id=usuario_id, items=n))
    db.commit()
    logger.info(f"Planeación ENVIADA a aprobación vm={vm_id} ciclo={ciclo_id} items={n}")
    _avisar_gerente(db, vm_id, n)
    return {"estado": "ENVIADA", "items": n, "ciclo_id": ciclo_id}


def _exigir_enviada(db: Session, vm_id: int, ciclo_id: int) -> None:
    estado = estado_actual(db, vm_id, ciclo_id)
    if estado != "ENVIADA":
        raise ValueError(
            "Esta planeación no está pendiente de aprobación "
            f"(estado actual: {estado.lower()}). Solo se aprueba o devuelve una planeación enviada.")


def aprobar_planeacion(db: Session, vm_id: int, ciclo_id: int | None, usuario_id: int | None) -> dict:
    """El Gerente de Distrito aprueba: la planeación queda PUBLICADA (congelada).

    Aprobar ES publicar —mismo evento, mismo congelamiento—, así todo lo que ya
    dependía de «publicada» (cobertura, guards de edición) funciona sin cambios. Lo que
    cambia es quién la dispara: el `usuario_id` del evento es el del gerente."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    _exigir_enviada(db, vm_id, ciclo_id)
    n = _validar_publicable(db, vm_id, ciclo_id, "aprobar")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="PUBLICADA",
                            usuario_id=usuario_id, items=n))
    db.commit()
    logger.info(f"Planeación APROBADA (publicada) vm={vm_id} ciclo={ciclo_id} items={n} por gerente={usuario_id}")
    return {"estado": "PUBLICADA", "publicada": True, "items": n, "ciclo_id": ciclo_id}


def devolver_planeacion(db: Session, vm_id: int, ciclo_id: int | None,
                        usuario_id: int | None, motivo: str) -> dict:
    """El Gerente de Distrito la devuelve con observaciones: vuelve a ser editable.

    El motivo es obligatorio: devolver sin decir qué corregir obliga al representante
    a adivinar, y la próxima versión llega con el mismo problema."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    if not (motivo or "").strip():
        raise ValueError("Indica qué debe corregir el representante (queda registrado).")
    _exigir_enviada(db, vm_id, ciclo_id)
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="DEVUELTA",
                            usuario_id=usuario_id, motivo=motivo.strip()[:300]))
    db.commit()
    logger.info(f"Planeación DEVUELTA vm={vm_id} ciclo={ciclo_id} por gerente={usuario_id}: {motivo}")
    return {"estado": "DEVUELTA", "ciclo_id": ciclo_id}


def _avisar_gerente(db: Session, vm_id: int, items: int) -> None:
    """Correo al Gerente de Distrito: tiene una planeación por aprobar. Best-effort:
    un fallo de correo nunca revierte el envío, que ya quedó registrado."""
    try:
        from app.models.dimensiones import Gerente, RepresentanteMedico
        from app.models.usuario import Usuario
        from app.services import notification_service
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
        if not rm or not rm.gerente_id:
            return
        ger = db.query(Gerente).filter(Gerente.id == rm.gerente_id).first()
        correo = ger.email if (ger and ger.email) else None
        if not correo:
            ug = db.query(Usuario).filter(Usuario.gerente_id == rm.gerente_id).first()
            correo = ug.email if ug else None
        if correo:
            notification_service.notificar_planeacion_por_aprobar(
                correo, ger.nombre if ger else "Gerente", rm.nombre, items)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Aviso de planeación enviada al GD falló (no bloquea) vm={vm_id}: {e}")


def equipo_planeaciones(db: Session, rm_ids: list[int], ciclo_id: int | None) -> list[dict]:
    """Una fila por representante con el estado de su planeación: la bandeja del gerente.

    Incluye a quien todavía no planeó (BORRADOR con 0 médicos): esconderlo haría creer
    al gerente que su equipo está completo cuando falta gente por empezar."""
    from app.models.dimensiones import RepresentanteMedico
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.id.in_(rm_ids or [-1]),
                   RepresentanteMedico.activo.is_(True))
           .order_by(RepresentanteMedico.codigo).all())
    filas = []
    for rm in rms:
        cid = ciclo_id or ciclo_por_defecto(db, rm.id)
        if cid is None:
            continue
        plan = db.query(PlaneacionCiclo).filter(
            PlaneacionCiclo.vm_id == rm.id, PlaneacionCiclo.ciclo_id == cid).all()
        ev = _ultimo_evento(db, rm.id, cid)
        estado = _estado_de(ev)
        filas.append({
            "vm_id": rm.id, "codigo": rm.codigo, "nombre": rm.nombre, "ciclo_id": cid,
            "estado": estado,
            "fecha_estado": ev.fecha.isoformat() if ev and estado != "BORRADOR" else None,
            "motivo": ev.motivo if ev and estado == "DEVUELTA" else None,
            "panel": len(_medicos_del_ciclo(db, rm.id, cid)),
            "medicos_planeados": len({p.medico_id for p in plan if p.tipo_visita == "V"}),
            "vistas": sum(1 for p in plan if p.tipo_visita == "V"),
            "revisitas": sum(1 for p in plan if p.tipo_visita == "R"),
        })
    return filas


def detalle_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> dict:
    """La planeación leída como la revisa un gerente: un renglón por médico, con su
    semana de Vista y de Revisita, más los médicos del panel que quedaron fuera."""
    from app.models.dimensiones import Especialidad
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        return {"ciclo_id": None, "estado": "BORRADOR", "medicos": [], "sin_planear": []}
    medicos = {m.id: m for m in _medicos_del_ciclo(db, vm_id, ciclo_id)}
    esp = {e.id: e.nombre for e in db.query(Especialidad).all()}
    por_medico: dict[int, dict] = {}
    for p in db.query(PlaneacionCiclo).filter(
            PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all():
        m = medicos.get(p.medico_id) or db.get(MedicoVisita, p.medico_id)
        d = por_medico.setdefault(p.medico_id, {
            "medico_id": p.medico_id,
            "nombre": m.nombre_completo if m else f"Médico {p.medico_id}",
            "categoria": m.categoria if m else None,
            "especialidad": esp.get(m.especialidad_id) if m else None,
            "top": bool(m and m.es_top),
            "semana_v": None, "dia_v": None, "semana_r": None, "dia_r": None})
        sufijo = "r" if p.tipo_visita == "R" else "v"
        d[f"semana_{sufijo}"] = p.semana
        d[f"dia_{sufijo}"] = p.dia_semana
    sin_planear = [{"medico_id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                    "top": bool(m.es_top)}
                   for m in medicos.values() if m.id not in por_medico]
    ev = _ultimo_evento(db, vm_id, ciclo_id)
    return {
        "ciclo_id": ciclo_id, "estado": _estado_de(ev),
        "motivo": ev.motivo if ev and ev.evento == "DEVUELTA" else None,
        "medicos": sorted(por_medico.values(), key=lambda d: (d["semana_v"] or 9, d["nombre"])),
        "sin_planear": sorted(sin_planear, key=lambda d: (not d["top"], d["categoria"] or "Z", d["nombre"])),
    }


def desbloquear_planeacion(db: Session, vm_id: int, ciclo_id: int | None,
                           usuario_id: int | None, motivo: str) -> dict:
    """Devuelve la planeación a borrador. **Solo ADMIN** (lo exige el router) y con motivo:
    sin él, desbloquear sería una vía silenciosa para maquillar la cobertura."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    if not (motivo or "").strip():
        raise ValueError("Indica el motivo del desbloqueo (queda registrado).")
    if not esta_publicada(db, vm_id, ciclo_id):
        raise ValueError("La planeación de este ciclo no está publicada.")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="DESBLOQUEADA",
                            usuario_id=usuario_id, motivo=motivo.strip()))
    db.commit()
    logger.warning(f"Planeación DESBLOQUEADA vm={vm_id} ciclo={ciclo_id} por usuario={usuario_id}: {motivo}")
    return {"publicada": False, "ciclo_id": ciclo_id}


def estado_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> dict:
    """Estado + historial de publicación (para que la UI sepa qué mostrar y el admin audite)."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        return {"ciclo_id": None, "publicada": False, "historial": []}
    eventos = (db.query(PlaneacionEvento)
               .filter(PlaneacionEvento.vm_id == vm_id, PlaneacionEvento.ciclo_id == ciclo_id)
               .order_by(PlaneacionEvento.fecha.desc(), PlaneacionEvento.id.desc()).all())
    ultimo = eventos[0] if eventos else None
    estado = _estado_de(ultimo)
    return {
        "ciclo_id": ciclo_id,
        "estado": estado,
        "publicada": estado == "PUBLICADA",
        "publicada_en": ultimo.fecha.isoformat() if estado == "PUBLICADA" else None,
        "enviada_en": ultimo.fecha.isoformat() if estado == "ENVIADA" else None,
        # Lo que el gerente pidió corregir: el representante lo lee al abrir su plan.
        "motivo_devolucion": ultimo.motivo if estado == "DEVUELTA" else None,
        "historial": [{"evento": e.evento, "fecha": e.fecha.isoformat(),
                       "usuario_id": e.usuario_id, "motivo": e.motivo, "items": e.items}
                      for e in eventos],
    }


def _validar(items: list[PlaneacionItem]) -> None:
    por_medico: dict[int, list[PlaneacionItem]] = {}
    for it in items:
        por_medico.setdefault(it.medico_id, []).append(it)
    for mid, grupo in por_medico.items():
        if len(grupo) > 2:
            raise ValueError(f"Máximo 2 visitas por médico (médico {mid} tiene {len(grupo)})")
        tipos = [g.tipo_visita for g in grupo]
        if tipos.count("V") > 1 or tipos.count("R") > 1:
            raise ValueError(f"Un médico solo puede tener 1 Vista y 1 Revisita (médico {mid})")
        if "V" in tipos and "R" in tipos:
            v = next(g for g in grupo if g.tipo_visita == "V")
            r = next(g for g in grupo if g.tipo_visita == "R")
            if r.semana < v.semana:
                raise ValueError(f"La Revisita debe ir en semana >= la Vista (médico {mid})")
            if r.semana == v.semana and r.dia_semana and v.dia_semana and r.dia_semana == v.dia_semana:
                raise ValueError(f"Vista y Revisita no pueden ser el mismo día (médico {mid})")
        if "R" in tipos and "V" not in tipos:
            raise ValueError(f"No se puede planear Revisita sin Vista (médico {mid})")


def guardar_planeacion(db: Session, vm_id: int, ciclo_id: int | None,
                       items: list[PlaneacionItem], usuario_id: int | None) -> int:
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    # Publicada = congelada. El guard va ANTES del delete-then-insert: sin él, un re-guardado
    # borraria el plan publicado y lo reescribiria, moviendo el denominador de la cobertura.
    _guard_no_publicada(db, vm_id, ciclo_id)
    _validar(items)
    db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).delete(synchronize_session=False)
    for it in items:
        db.add(PlaneacionCiclo(
            vm_id=vm_id, ciclo_id=ciclo_id, medico_id=it.medico_id, tipo_visita=it.tipo_visita,
            semana=it.semana, dia_semana=it.dia_semana, hora_estimada=it.hora_estimada,
            fecha_creacion=_ahora_utc(), modificado_por=usuario_id))
    db.commit()
    logger.info(f"Planeación guardada VM={vm_id} ciclo={ciclo_id}: {len(items)} ítems")
    return len(items)


def listar_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> list[dict]:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    filas = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    return [{"medico_id": f.medico_id, "tipo_visita": f.tipo_visita, "semana": f.semana,
             "dia_semana": f.dia_semana, "hora_estimada": f.hora_estimada} for f in filas]


def resumen_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> dict:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    medicos = db.query(MedicoVisita).filter(
        MedicoVisita.vm_id == vm_id, MedicoVisita.activo == True).all()  # noqa: E712
    panel = len(medicos)
    cat_a = {m.id for m in medicos if m.categoria == "A"}
    plan = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    con_vista = {p.medico_id for p in plan if p.tipo_visita == "V"}
    con_revisita = {p.medico_id for p in plan if p.tipo_visita == "R"}
    cat_a_sin_revisita = len(cat_a - con_revisita)
    total = len(plan)
    sin_planear = top_sin_planear(db, vm_id, ciclo_id)
    sin_revisita = top_sin_revisita(db, vm_id, ciclo_id)
    return {
        "ciclo_id": ciclo_id, "panel": panel, "total_planeadas": total,
        "medicos_planeados": len(con_vista),
        "cobertura_planeada_pct": round(len(con_vista) / panel * 100, 1) if panel else 0.0,
        "cat_a_sin_revisita": cat_a_sin_revisita,
        "carga_por_dia": round(total / CICLO_DIAS_DEFAULT, 1),
        "top_sin_planear": sin_planear,
        "top_sin_revisita": sin_revisita,
    }
