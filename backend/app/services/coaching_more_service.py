"""Servicio del Módulo de Coaching (Modelo de Ventas MORE).

Cálculo de promedios (simple por sección → promedio simple de secciones), validaciones
que bloquean el guardado (Sección 8 del spec), creación INMUTABLE de la hoja + su detalle,
hoja de corrección (append-only) y KPI Coaching. La generación de PDF + correo vive en
`coaching_more_pdf.py` y se dispara al guardar (best-effort).
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from loguru import logger
from sqlalchemy.orm import Session

from app.models.coaching_more_models import (
    CoachingSesion, CoachingItemEvaluado, CoachingItemCatalogo, SECCIONES_MORE,
)
from app.core.tiempo import hoy_local
from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.models.usuario import Usuario, Rol


# ─────────────────────────────────────────────────────────────────────────
# Cálculo de promedios (puro — usado por los tests con el fixture Candy Domínguez)
# ─────────────────────────────────────────────────────────────────────────

def _r2(x: float) -> float:
    """Redondeo a 2 decimales, HALF_UP (3.428.. → 3.43)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calcular_promedios(items: list[dict]) -> dict:
    """items: [{'seccion': str, 'calificacion': int}]. Devuelve:
        {'secciones': {seccion: promedio}, 'general': float}
    El promedio general = promedio SIMPLE de los promedios de sección (no ponderado
    por cantidad de ítems), en el orden de SECCIONES_MORE. Solo cuentan las secciones
    con al menos un ítem calificado."""
    por_sec: dict[str, list[int]] = {}
    for it in items:
        c = it.get("calificacion")
        if c is None:
            continue
        por_sec.setdefault(it["seccion"], []).append(int(c))
    secciones = {s: _r2(sum(v) / len(v)) for s, v in por_sec.items() if v}
    if secciones:
        general = _r2(sum(secciones.values()) / len(secciones))
    else:
        general = 0.0
    return {"secciones": secciones, "general": general}


# ─────────────────────────────────────────────────────────────────────────
# Validaciones que bloquean el guardado (Sección 8) — mensajes específicos
# ─────────────────────────────────────────────────────────────────────────

def _items_esperados(db: Session) -> int:
    return db.query(CoachingItemCatalogo).filter(CoachingItemCatalogo.activo == True).count()  # noqa: E712


def validar(db: Session, datos) -> list[str]:
    """Devuelve la lista de errores (vacía si la hoja es válida). Cada error es un
    mensaje específico por campo, no un genérico 'faltan campos'."""
    errores: list[str] = []
    if not datos.fecha_coaching:
        errores.append("Fecha del coaching es obligatoria.")
    if not datos.rm_id:
        errores.append("Selecciona el representante (RM).")
    if datos.medicos_vistos is None or datos.medicos_vistos < 0:
        errores.append("Cantidad de médicos vistos: entero mayor o igual a 0.")

    esperados = _items_esperados(db)
    calificados = [i for i in (datos.items or []) if i.calificacion in (1, 2, 3, 4)]
    if len(calificados) < esperados:
        errores.append(f"Faltan ítems del modelo MORE por calificar ({len(calificados)}/{esperados}).")
    if any(i.calificacion not in (1, 2, 3, 4) for i in (datos.items or [])):
        errores.append("Cada ítem MORE se califica de 1 a 4 (D/P/A/E).")

    # Plan de desarrollo (obligatorio por decisión de negocio) + plan de acción
    if not (datos.fortalezas or "").strip():
        errores.append("Fortalezas es obligatorio.")
    if not (datos.areas_perfeccionar or "").strip():
        errores.append("Áreas a perfeccionar es obligatorio.")
    if not (datos.plan_que_haras or "").strip():
        errores.append("Plan de Acción: ¿Qué harás? es obligatorio.")
    if not (datos.plan_como_haras or "").strip():
        errores.append("Plan de Acción: ¿Cómo lo harás? es obligatorio.")
    if not (datos.plan_como_veras or "").strip():
        errores.append("Plan de Acción: ¿Cómo te darás cuenta? es obligatorio.")
    if not datos.plan_fecha_seguimiento:
        errores.append("Fecha de seguimiento es obligatoria.")
    elif datos.fecha_coaching and datos.plan_fecha_seguimiento <= datos.fecha_coaching:
        errores.append("La fecha de seguimiento debe ser posterior a la fecha del coaching.")

    if datos.rm_acuerdo not in ("de_acuerdo", "no_de_acuerdo"):
        errores.append("Selecciona si el RM está de acuerdo o no.")
    # Regla más explícita del cliente: "no de acuerdo" exige justificación.
    if datos.rm_acuerdo == "no_de_acuerdo" and not (datos.rm_justificacion_desacuerdo or "").strip():
        errores.append('Justificación del desacuerdo (obligatoria al elegir "No estoy de acuerdo").')

    if not (datos.rm_firma_imagen or "").strip():
        errores.append("Firma del representante (obligatoria siempre).")

    return errores


# ─────────────────────────────────────────────────────────────────────────
# Creación (INMUTABLE) — hoja normal o hoja de corrección
# ─────────────────────────────────────────────────────────────────────────

def _ciclo_pais_de_rm(db: Session, rm: RepresentanteMedico, fecha: date):
    """(ciclo_id que CONTIENE `fecha` en el país del RM, pais_codigo).

    FIX jul-2026: antes delegaba en `ciclo_por_defecto`, que devuelve el ciclo ABIERTO
    de número más alto del país. Con C12 abierto, una hoja del 10-jul quedó archivada en
    C12-2026 (diciembre), porque 12 > 7. El ciclo de una hoja lo define su FECHA, no cuál
    ciclo esté abierto. Si ninguna ventana cubre la fecha (los ciclos van del 1 al 28, así
    que los días 29-31 quedan fuera), se cae al ciclo abierto del país.
    """
    c = (db.query(Ciclo)
         .filter(Ciclo.pais_codigo == rm.pais_codigo,
                 Ciclo.fecha_inicio <= fecha, Ciclo.fecha_fin >= fecha)
         .order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).first())
    if c:
        return c.id, rm.pais_codigo
    from app.services.visita_cobertura_service import ciclo_por_defecto
    return ciclo_por_defecto(db, rm.id), rm.pais_codigo


def crear_hoja(db: Session, gd_user: Usuario, datos) -> CoachingSesion:
    """Crea una hoja de coaching NUEVA tras validar. Lanza ValueError con el detalle si falta
    algo. La hoja queda INMUTABLE (trigger de BD).

    La corrección/enmienda se retiró (jul-2026): una hoja guardada no se modifica bajo ningún
    concepto. Este guard rechaza cualquier `corrige_a_id` que llegue por una vía vieja — la
    barrera real, no solo el endpoint."""
    if getattr(datos, "corrige_a_id", None):
        raise ValueError("Las hojas de coaching son inmutables: no se pueden corregir.")
    rm = (db.query(RepresentanteMedico).filter(RepresentanteMedico.id == datos.rm_id).first()
          if datos.rm_id else None)
    # La fecha la fija el SERVIDOR (nunca el cliente) y en hora LOCAL del país del RM:
    # el día del coaching es el día laboral del GD, no el día UTC — que a partir de las
    # 8 p.m. en RD ya avanzó al siguiente.
    datos.fecha_coaching = hoy_local(db, rm.pais_codigo) if rm else date.today()

    errores = validar(db, datos)
    if errores:
        raise ValueError(" · ".join(errores))
    if not rm:
        raise ValueError("El representante (RM) no existe.")

    # Alcance: un GERENTE_DISTRITO solo evalúa RMs de su propio equipo.
    if gd_user.rol == Rol.GERENTE_DISTRITO:
        if not gd_user.gerente_id or rm.gerente_id != gd_user.gerente_id:
            raise ValueError("Este RM no pertenece a tu equipo.")

    if datos.corrige_a_id:
        orig = db.query(CoachingSesion).filter(CoachingSesion.id == datos.corrige_a_id).first()
        if not orig:
            raise ValueError("La hoja a corregir no existe.")
        if not (datos.motivo_correccion or "").strip():
            raise ValueError("Indica el motivo de la corrección.")

    prom = calcular_promedios([{"seccion": i.seccion, "calificacion": i.calificacion} for i in datos.items])
    ciclo_id, pais_codigo = _ciclo_pais_de_rm(db, rm, datos.fecha_coaching)

    sesion = CoachingSesion(
        gd_usuario_id=gd_user.id,
        gd_gerente_id=gd_user.gerente_id,
        rm_id=rm.id,
        pais_codigo=pais_codigo,
        ciclo_id=ciclo_id,
        fecha_coaching=datos.fecha_coaching,
        medicos_vistos=datos.medicos_vistos,
        evaluacion_promedio=prom["general"],
        fortalezas=datos.fortalezas.strip(),
        areas_perfeccionar=datos.areas_perfeccionar.strip(),
        plan_que_haras=datos.plan_que_haras.strip(),
        plan_como_haras=datos.plan_como_haras.strip(),
        plan_como_veras=datos.plan_como_veras.strip(),
        plan_fecha_seguimiento=datos.plan_fecha_seguimiento,
        rm_acuerdo=datos.rm_acuerdo,
        rm_justificacion_desacuerdo=(datos.rm_justificacion_desacuerdo or None),
        rm_firma_imagen=datos.rm_firma_imagen,
        rm_firma_timestamp=datetime.now(timezone.utc),
        corrige_a_id=datos.corrige_a_id,
        motivo_correccion=(datos.motivo_correccion or None),
        pdf_generado=True,   # el PDF se genera en el mismo flujo (best-effort para el correo)
        created_at=datetime.now(timezone.utc),
    )
    db.add(sesion)
    db.flush()  # obtener sesion.id para el detalle
    for i in datos.items:
        db.add(CoachingItemEvaluado(
            sesion_id=sesion.id, item_catalogo_id=i.item_catalogo_id,
            seccion=i.seccion, item_texto=i.item_texto, calificacion=i.calificacion))
    db.commit()
    db.refresh(sesion)
    logger.info(f"Coaching MORE: hoja {sesion.id} creada gd={gd_user.id} rm={rm.id} "
                f"prom={prom['general']} corrige_a={datos.corrige_a_id}")

    # PDF + correo al RM (best-effort, no bloquea el guardado)
    try:
        from app.services import coaching_more_pdf
        coaching_more_pdf.generar_y_enviar(db, sesion, prom, rm)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Coaching MORE: PDF/correo falló para hoja {sesion.id}: {exc}")

    return sesion


# ─────────────────────────────────────────────────────────────────────────
# Lectura (con alcance por rol) + serialización
# ─────────────────────────────────────────────────────────────────────────

def _rm_ids_de_gd(db: Session, gerente_id: int) -> list[int]:
    return [r[0] for r in db.query(RepresentanteMedico.id)
            .filter(RepresentanteMedico.gerente_id == gerente_id).all()]


def listar_hojas(db: Session, current_user: Usuario, rm_id: int | None = None,
                 ciclo_id: int | None = None) -> list[dict]:
    """GD ve las hojas de su equipo; RM ve solo las suyas; ADMIN/otros ven todo."""
    q = db.query(CoachingSesion)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO:
        q = q.filter(CoachingSesion.rm_id == (current_user.rm_id or -1))
    elif current_user.rol == Rol.GERENTE_DISTRITO:
        ids = _rm_ids_de_gd(db, current_user.gerente_id) if current_user.gerente_id else [-1]
        q = q.filter(CoachingSesion.rm_id.in_(ids or [-1]))
    if rm_id:
        q = q.filter(CoachingSesion.rm_id == rm_id)
    if ciclo_id:
        q = q.filter(CoachingSesion.ciclo_id == ciclo_id)
    return [_serializar(db, s, resumen=True)
            for s in q.order_by(CoachingSesion.fecha_coaching.desc(), CoachingSesion.id.desc()).all()]


def obtener_hoja(db: Session, sesion_id: int, current_user: Usuario) -> dict | None:
    s = db.query(CoachingSesion).filter(CoachingSesion.id == sesion_id).first()
    if not s:
        return None
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and s.rm_id != (current_user.rm_id or -1):
        raise PermissionError("Solo puedes ver tus propias hojas de coaching.")
    if current_user.rol == Rol.GERENTE_DISTRITO:
        if not current_user.gerente_id or s.rm_id not in _rm_ids_de_gd(db, current_user.gerente_id):
            raise PermissionError("Esta hoja no pertenece a tu equipo.")
    return _serializar(db, s, resumen=False)


def _serializar(db: Session, s: CoachingSesion, resumen: bool) -> dict:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == s.rm_id).first()
    gd = db.query(Usuario).filter(Usuario.id == s.gd_usuario_id).first()
    tiene_correccion = db.query(CoachingSesion.id).filter(CoachingSesion.corrige_a_id == s.id).first() is not None
    base = {
        "id": s.id, "fecha_coaching": s.fecha_coaching.isoformat(),
        "rm_id": s.rm_id, "rm_nombre": rm.nombre if rm else None,
        "gd_nombre": (gd.nombre_completo if gd else None),
        "medicos_vistos": s.medicos_vistos,
        "evaluacion_promedio": float(s.evaluacion_promedio),
        "rm_acuerdo": s.rm_acuerdo,
        "ciclo_id": s.ciclo_id,
        "ciclo_nombre": (db.query(Ciclo.nombre).filter(Ciclo.id == s.ciclo_id).scalar()
                         if s.ciclo_id else None),
        "corrige_a_id": s.corrige_a_id,
        "es_correccion": s.corrige_a_id is not None,
        "tiene_correccion": tiene_correccion,   # → mostrar como "enmendada"
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if resumen:
        return base
    items = (db.query(CoachingItemEvaluado)
             .filter(CoachingItemEvaluado.sesion_id == s.id).all())
    prom = calcular_promedios([{"seccion": i.seccion, "calificacion": i.calificacion} for i in items])
    secciones = [{"seccion": sec, "promedio": prom["secciones"].get(sec),
                  "items": [{"texto": i.item_texto, "calificacion": i.calificacion}
                            for i in items if i.seccion == sec]}
                 for sec in SECCIONES_MORE if any(i.seccion == sec for i in items)]
    base.update({
        "fortalezas": s.fortalezas, "areas_perfeccionar": s.areas_perfeccionar,
        "plan_que_haras": s.plan_que_haras, "plan_como_haras": s.plan_como_haras,
        "plan_como_veras": s.plan_como_veras,
        "plan_fecha_seguimiento": s.plan_fecha_seguimiento.isoformat(),
        "rm_justificacion_desacuerdo": s.rm_justificacion_desacuerdo,
        "rm_firma_imagen": s.rm_firma_imagen,
        "motivo_correccion": s.motivo_correccion,
        "secciones": secciones,
    })
    return base


# ─────────────────────────────────────────────────────────────────────────
# KPI Coaching (Sección 11) — hojas completadas por ciclo, por GD y equipo
# ─────────────────────────────────────────────────────────────────────────

META_HOJAS_POR_RM = 1  # meta configurable: 1 hoja por RM por ciclo (Sección 11)


def kpi_coaching(db: Session, ciclo_id: int | None, pais_codigo: str | None = None) -> dict:
    """Contador de hojas completadas en el ciclo, total equipo y desglose por GD.
    Solo cuenta hojas NO enmendadas (las correcciones reemplazan a su original)."""
    q = db.query(CoachingSesion)
    if ciclo_id:
        q = q.filter(CoachingSesion.ciclo_id == ciclo_id)
    if pais_codigo:
        q = q.filter(CoachingSesion.pais_codigo == pais_codigo)
    hojas = q.all()
    # excluir originales que ya tienen una hoja de corrección
    enmendadas = {h.corrige_a_id for h in hojas if h.corrige_a_id}
    vigentes = [h for h in hojas if h.id not in enmendadas]

    por_gd: dict[int, dict] = {}
    for h in vigentes:
        d = por_gd.setdefault(h.gd_usuario_id, {"gd_usuario_id": h.gd_usuario_id, "hojas": 0, "gd_nombre": None})
        d["hojas"] += 1
    for gd_id, d in por_gd.items():
        u = db.query(Usuario).filter(Usuario.id == gd_id).first()
        d["gd_nombre"] = u.nombre_completo if u else f"GD #{gd_id}"

    rms_con_hoja = {h.rm_id for h in vigentes}
    # universo de RMs para la meta (por país si se indicó)
    rq = db.query(RepresentanteMedico.id).filter(RepresentanteMedico.activo == True)  # noqa: E712
    if pais_codigo:
        rq = rq.filter(RepresentanteMedico.pais_codigo == pais_codigo)
    total_rms = rq.count()

    return {
        "ciclo_id": ciclo_id,
        "hojas_completadas": len(vigentes),
        "rms_con_coaching": len(rms_con_hoja),
        "total_rms": total_rms,
        "meta_hojas": total_rms * META_HOJAS_POR_RM,
        "pct_avance": round(len(rms_con_hoja) / total_rms * 100, 1) if total_rms else 0.0,
        "por_gd": sorted(por_gd.values(), key=lambda x: -x["hojas"]),
    }
