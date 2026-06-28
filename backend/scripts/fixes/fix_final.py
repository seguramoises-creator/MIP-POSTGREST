"""
fix_final.py  — rutas Linux para el sandbox
"""
import re, shutil, os

PAGES = "/sessions/sharp-cool-rubin/mnt/MSM/frontend/src/pages"

# ── 1. Restaurar archivos truncados desde .bak_pais ─────────────────────────
TRUNCADOS = [
    "ranking/Ranking.tsx",
    "productividad/Productividad.tsx",
    "reconocimiento/Reconocimiento.tsx",
]

for rel in TRUNCADOS:
    src = os.path.join(PAGES, rel) + ".bak_pais"
    dst = os.path.join(PAGES, rel)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  RESTORED: {os.path.basename(dst)}")
    else:
        print(f"  MISSING BACKUP: {src}")

# ── 2. Fixes de pais_codigo en los 3 restaurados ─────────────────────────────
REPLACEMENTS_PAIS = [
    (r"setPaisId\(String\(rd\.id\)\)",            "setPaisId(rd.codigo)"),
    (r"handlePaisChange\(rd\.id\)",               "handlePaisChange(rd.codigo)"),
    (r"setPaisId\(rd\.id\)",                       "setPaisId(rd.codigo)"),
    (r"Number\(paisCodigo\)",                      "paisCodigo"),
    (r"useState<number \| ''>('')\s*;?\s*//.*pais","useState<string | ''>('') ;"),
    (r"(handlePaisChange\s*=\s*\(val:\s*)number \| ''(\))", r"\1string | ''\2"),
    (r"(setPaisId:\s*\(id:\s*)number(\))",         r"\1string\2"),
    (r"const \[paisCodigo,\s*setPaisId\]\s*=\s*useState<number \| ''>",
     "const [paisCodigo, setPaisId] = useState<string | ''>"),
    (r"setPaisId\(e\.target\.value\s*===\s*''\s*\?\s*''\s*:\s*Number\(e\.target\.value\)\)",
     "setPaisId(e.target.value)"),
    (r"(setPaisId:\s*\(id:\s*)number(\)\s*=>)",    r"\1string\2"),
    (r"(paises:\s*Pais\[\]\s*\|\s*undefined,\s*paisCodigo:\s*)number \| ''",
     r"\1string | ''"),
    (r"handlePaisChange\(e\.target\.value\s+as\s+number \| ''\)",
     "handlePaisChange(e.target.value as string | '')"),
]

for rel in TRUNCADOS:
    path = os.path.join(PAGES, rel)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    original = content
    for pattern, repl in REPLACEMENTS_PAIS:
        content = re.sub(pattern, repl, content)
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  FIXED pais: {os.path.basename(path)}")
    else:
        print(f"  no-change:  {os.path.basename(path)}")

# ── 3. Fix MenuItem value={p.id} → value={p.codigo} en todos ─────────────────
ALL_TSX = [
    "productividad/Productividad.tsx",
    "ranking/Ranking.tsx",
    "reconocimiento/Reconocimiento.tsx",
    "coaching/Coaching.tsx",
    "cobertura-predictiva/CoberturaPredictiva.tsx",
    "categorizacion/Categorizacion.tsx",
    "lsii/Lsii.tsx",
    "reportes/Reportes.tsx",
    "admin/CategorizacionAdmin.tsx",
    "admin/CoberturaPredictivaAdmin.tsx",
]

# Patrón genérico: key={p.id} value={p.id} en cualquier MenuItem de pais
MENU_PAT = re.compile(r'(<MenuItem\s+key=\{p\.id\}\s+)value=\{p\.id\}')

for rel in ALL_TSX:
    path = os.path.join(PAGES, rel)
    if not os.path.exists(path):
        print(f"  NOT FOUND: {rel}")
        continue
    with open(path, encoding='utf-8') as f:
        content = f.read()
    original = content
    content = MENU_PAT.sub(r'\1value={p.codigo}', content)
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        count = original.count('value={p.id}') - content.count('value={p.id}')
        print(f"  FIXED MenuItem ({count}x): {os.path.basename(path)}")
    else:
        print(f"  MenuItem OK:              {os.path.basename(path)}")

print("\nDone.")
