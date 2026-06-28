"""
Corrige el bug pais_codigo en todas las paginas del frontend.
El problema: las paginas almacenan el ID numerico del pais y lo pasan
como Number(paisCodigo) a la API, pero la API espera el codigo string ('DO').
La solucion: almacenar rd.codigo directamente y quitar los Number() wrappers.
"""
import re, os

FRONTEND = r"C:\Users\Lenovo\Proyecto\MSM\frontend\src\pages"

FILES = [
    r"productividad\Productividad.tsx",
    r"ranking\Ranking.tsx",
    r"reconocimiento\Reconocimiento.tsx",
    r"coaching\Coaching.tsx",
    r"cobertura-predictiva\CoberturaPredictiva.tsx",
    r"categorizacion\Categorizacion.tsx",
    r"lsii\Lsii.tsx",
    r"reportes\Reportes.tsx",
    r"admin\CategorizacionAdmin.tsx",
    r"admin\CoberturaPredictivaAdmin.tsx",
]

REPLACEMENTS = [
    # setPaisId(String(rd.id))  →  setPaisId(rd.codigo)
    (r"setPaisId\(String\(rd\.id\)\)", "setPaisId(rd.codigo)"),
    # handlePaisChange(rd.id)   →  handlePaisChange(rd.codigo)
    (r"handlePaisChange\(rd\.id\)", "handlePaisChange(rd.codigo)"),
    # setPaisId(rd.id)  →  setPaisId(rd.codigo)   [auto-select hook]
    (r"setPaisId\(rd\.id\)", "setPaisId(rd.codigo)"),
    # setPaisId(p.pais_codigo)  queda igual — ya es string
    # Number(paisCodigo)  →  paisCodigo
    (r"Number\(paisCodigo\)", "paisCodigo"),
    # useState<number | ''>('') para paisCodigo  →  useState<string | ''>('')
    (r"useState<number \| ''>('')\s*;?\s*//.*pais", "useState<string | ''>('') ;"),
    # val: number | '' en handlePaisChange  →  val: string | ''
    (r"(handlePaisChange\s*=\s*\(val:\s*)number \| ''(\))", r"\1string | ''\2"),
    # (id: number) en useAutoSelectRD  →  (id: string)
    (r"(setPaisId:\s*\(id:\s*)number(\))", r"\1string\2"),
    # useState<number | ''>('') cuando la variable es paisCodigo
    # solo aplica si la linea menciona setPaisId o paisCodigo cerca
    (r"const \[paisCodigo,\s*setPaisId\]\s*=\s*useState<number \| ''>",
     "const [paisCodigo, setPaisId] = useState<string | ''>"),
    # setPaisId(e.target.value === '' ? '' : Number(e.target.value))
    # → setPaisId(e.target.value)
    (r"setPaisId\(e\.target\.value\s*===\s*''\s*\?\s*''\s*:\s*Number\(e\.target\.value\)\)",
     "setPaisId(e.target.value)"),
    # useAutoSelectRD type signature: (id: number) => void  →  (id: string) => void
    (r"(setPaisId:\s*\(id:\s*)number(\)\s*=>)", r"\1string\2"),
    # useAutoSelectRD first arg type: paisCodigo: number | ''  → string | ''
    (r"(paises:\s*Pais\[\]\s*\|\s*undefined,\s*paisCodigo:\s*)number \| ''",
     r"\1string | ''"),
]

def fix_file(path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    original = content
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  FIXED: {os.path.basename(path)}")
    else:
        print(f"  skip:  {os.path.basename(path)}")

for rel in FILES:
    full = os.path.join(FRONTEND, rel)
    if os.path.exists(full):
        fix_file(full)
    else:
        print(f"  NOT FOUND: {rel}")

print("\nDone. Ahora corre: npm run build en frontend y despliega.")
