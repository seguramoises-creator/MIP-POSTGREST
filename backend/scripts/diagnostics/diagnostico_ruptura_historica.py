"""
Auditoria SOLO LECTURA — impacto real del bug critico de aislamiento por pais en el
cierre de ciclo de Visita (corregido en jul-2026, commit 8427bb0).

Antes del fix, `_resumen_cierre` procesaba TODOS los medicos del sistema (sin filtrar
por pais) en cada cierre de ciclo. Un medico de un pais distinto al del ciclo cerrado
nunca podia tener una visita registrada bajo ese ciclo ajeno, asi que cada cierre de
CUALQUIER pais incrementaba por error `MedicoVisita.ciclos_sin_visita` de TODOS los
medicos de los demas paises.

Este script NO asume el tamano del exceso: para cada medico, RECALCULA desde cero cual
deberia ser su `ciclos_sin_visita` HOY, simulando en orden cronologico SOLO los cierres
legitimos (los de su propio pais) desde su alta, usando las visitas reales registradas
(Visita.FactVisita) para decidir reset (tuvo visita ese ciclo) vs incremento (no tuvo).
Compara ese valor recalculado contra el valor actualmente guardado — la diferencia es
la contaminacion real y verificable causada por el bug, no una estimacion.

No escribe nada en la base de datos.

Uso:
    docker compose exec backend python scripts/diagnostics/diagnostico_ruptura_historica.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.database import SessionLocal
from app.models.visita import MedicoVisita, CierreCicloVisita
from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
from app.services.visita_cobertura_service import _mapa_visitas


def main():
    db = SessionLocal()
    try:
        ordenes = ordenes_ciclo(db)

        # FIX: solo cuentan los ciclos que de verdad tuvieron un cierre real
        # (CierreCicloVisita) — no "todos los ciclos que existen", que incluye
        # ciclos futuros/nunca cerrados y habria inflado el calculo por igual
        # para todo el mundo (bug detectado en la primera corrida de este script).
        cierres = db.query(CierreCicloVisita).all()
        ciclos_de_cierres = {
            c.id: c for c in db.query(Ciclo).filter(
                Ciclo.id.in_([cc.ciclo_id for cc in cierres])
            ).all()
        }
        ciclos_por_pais: dict[str, list] = {}
        for cc in cierres:
            ciclo = ciclos_de_cierres.get(cc.ciclo_id)
            if not ciclo:
                continue
            ciclos_por_pais.setdefault(ciclo.pais_codigo, []).append(ciclo)
        for lista in ciclos_por_pais.values():
            lista.sort(key=lambda c: (c.anio, c.numero))

        print("Cierres reales encontrados por pais:")
        for pais, lista in sorted(ciclos_por_pais.items()):
            nombres = ", ".join(c.nombre for c in lista)
            print(f"  {pais}: {len(lista)} cierre(s) -> {nombres}")
        print()

        rms_pais = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.pais_codigo).all())
        medicos = db.query(MedicoVisita).all()

        # Cache de mapas de visita por ciclo (evita recalcular si varios medicos comparten pais)
        mapa_cache: dict[int, dict] = {}

        def mapa_de(ciclo_id: int) -> dict:
            if ciclo_id not in mapa_cache:
                mapa_cache[ciclo_id] = _mapa_visitas(db, ciclo_id, None)
            return mapa_cache[ciclo_id]

        contaminados = []
        sin_pais = 0

        for m in medicos:
            pais = rms_pais.get(m.vm_id)
            if not pais:
                sin_pais += 1
                continue
            secuencia = ciclos_por_pais.get(pais, [])

            recalculado = 0
            ultimo_ciclo_evaluado = None
            for ciclo in secuencia:
                orden = ordenes.get(ciclo.id)
                if not cuenta_en_ciclo(m, orden, ordenes):
                    continue
                ultimo_ciclo_evaluado = ciclo
                tuvo = m.id in mapa_de(ciclo.id)
                recalculado = 0 if tuvo else recalculado + 1

            if recalculado != m.ciclos_sin_visita:
                contaminados.append({
                    "medico_id": m.id,
                    "nombre": m.nombre_completo,
                    "pais": pais,
                    "vm_id": m.vm_id,
                    "actual": m.ciclos_sin_visita,
                    "recalculado": recalculado,
                    "exceso": m.ciclos_sin_visita - recalculado,
                    "ultimo_ciclo": ultimo_ciclo_evaluado.nombre if ultimo_ciclo_evaluado else None,
                })

        print(f"Medicos analizados: {len(medicos)}  (sin pais resuelto: {sin_pais})")
        print(f"Medicos con ciclos_sin_visita CONTAMINADO: {len(contaminados)}")
        print()

        if contaminados:
            por_pais: dict[str, int] = {}
            for c in contaminados:
                por_pais[c["pais"]] = por_pais.get(c["pais"], 0) + 1
            print("Contaminados por pais:")
            for pais, n in sorted(por_pais.items(), key=lambda x: -x[1]):
                print(f"  {pais}: {n} medicos")
            print()

            print("Detalle (ordenado por mayor exceso):")
            for c in sorted(contaminados, key=lambda x: -x["exceso"])[:50]:
                print(
                    f"  medico_id={c['medico_id']:>6}  {c['nombre']:<35} pais={c['pais']}  "
                    f"actual={c['actual']:>3}  deberia_ser={c['recalculado']:>3}  "
                    f"exceso={c['exceso']:>3}  (ultimo ciclo evaluado: {c['ultimo_ciclo']})"
                )
            if len(contaminados) > 50:
                print(f"  ... y {len(contaminados) - 50} mas (lista completa arriba truncada a 50)")
        else:
            print("Ningun medico tiene un ciclos_sin_visita distinto al recalculado — "
                  "no se detecto contaminacion vigente (probablemente porque ya fueron "
                  "visitados desde entonces, lo que resetea el contador a 0 sin importar "
                  "el historial previo).")

    finally:
        db.close()


if __name__ == "__main__":
    main()
