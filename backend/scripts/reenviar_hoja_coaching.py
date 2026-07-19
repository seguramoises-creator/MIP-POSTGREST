"""
Reenvía por correo una hoja de coaching (MORE) ya existente. Sirve para PROBAR que el
envío funciona tras el fix de configuración SMTP (antes leía el .env en vez de la BD).

SEGURIDAD — por qué exige `--a`:
    La hoja contiene la EVALUACIÓN DE DESEMPEÑO de una persona identificada. En producción
    los representantes comparten un correo placeholder ('jperez@empresa.com'), que puede
    pertenecer a un tercero. Por eso este script NO envía al correo registrado por defecto:
    hay que indicar el destinatario explícitamente. Para la prueba, usa TU propio buzón.

Uso (dentro del contenedor):
    # 1) Ver qué hojas hay del representante (NO envía nada):
    docker compose exec -e PYTHONPATH=/app backend \
        python scripts/reenviar_hoja_coaching.py --rm "ANGEL AMAURIS"

    # 2) Enviar la última hoja a TU correo:
    docker compose exec -e PYTHONPATH=/app backend \
        python scripts/reenviar_hoja_coaching.py --rm "ANGEL AMAURIS" --a tucorreo@gmail.com
"""
from __future__ import annotations
import argparse

from app.db.database import SessionLocal
from app.models.coaching_more_models import CoachingSesion, CoachingItemEvaluado
from app.models.dimensiones import RepresentanteMedico
from app.services import coaching_more_pdf
from app.services.coaching_more_service import calcular_promedios
from app.services.notification_service import mail_config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rm", required=True, help="Parte del nombre del representante")
    ap.add_argument("--a", help="Correo destino. Sin esto solo LISTA, no envía.")
    ap.add_argument("--sesion", type=int, help="Id de hoja concreta (default: la última)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        cfg = mail_config()
        print(f"SMTP efectivo: server={cfg['server'] or '(vacío)'} port={cfg['port']} "
              f"tls={cfg['tls']} from={cfg['from']}")
        if not cfg["server"]:
            print("!! Sin servidor SMTP configurado (ni en Admin → Servidor de Correo ni en .env).")
            return

        rms = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.nombre.ilike(f"%{args.rm}%")).all()
        if not rms:
            print(f"!! No hay representante que coincida con {args.rm!r}.")
            return
        if len(rms) > 1:
            print("Coinciden varios; afina el nombre:")
            for r in rms:
                print(f"   id={r.id} {r.codigo} {r.nombre}")
            return
        rm = rms[0]
        print(f"Representante: {rm.codigo} · {rm.nombre} (id={rm.id})")
        print(f"  correo registrado: {rm.email!r}")

        q = db.query(CoachingSesion).filter(CoachingSesion.rm_id == rm.id)
        if args.sesion:
            q = q.filter(CoachingSesion.id == args.sesion)
        sesiones = q.order_by(CoachingSesion.fecha_coaching.desc()).all()
        if not sesiones:
            print("!! Este representante no tiene hojas de coaching registradas.")
            return
        print(f"  hojas de coaching: {len(sesiones)}")
        for s in sesiones[:5]:
            print(f"     id={s.id} fecha={s.fecha_coaching}")

        if not args.a:
            print("\n(solo listado — agrega --a tucorreo@dominio.com para enviar)")
            return

        s = sesiones[0] if not args.sesion else sesiones[0]
        items = db.query(CoachingItemEvaluado).filter(
            CoachingItemEvaluado.sesion_id == s.id).all()
        prom = calcular_promedios(
            [{"seccion": i.seccion, "calificacion": i.calificacion} for i in items])

        pdf = coaching_more_pdf.generar_pdf(db, s, prom, rm)
        cuerpo = (f"<p>Hola {rm.nombre},</p>"
                  f"<p>Adjuntamos la hoja de coaching (Modelo MORE) del "
                  f"<b>{s.fecha_coaching.isoformat()}</b>, con evaluación promedio "
                  f"<b>{prom['general']}</b>.</p><p>— Sistema VISTA</p>")
        ok = coaching_more_pdf._enviar_pdf(
            args.a, f"[PRUEBA] Hoja de Coaching MORE — {s.fecha_coaching.isoformat()}",
            cuerpo, pdf, f"coaching_{s.id}.pdf")
        print(f"\nEnvío a {args.a}: {'OK — revisa la bandeja' if ok else 'FALLÓ (ver log arriba)'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
