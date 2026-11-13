import json
import re
from pathlib import Path

# 1. Charger phrases_types_baoule.json
base_dir = Path(__file__).resolve().parent.parent
json_path = base_dir / "apps/ai_assistant/chatbot/donnees/phrases_types_baoule.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

phrases = data.get("phrases", [])
print(f"[1] Nombre de phrases dans phrases_types_baoule.json : {len(phrases)}")

for i, p in enumerate(phrases, 1):
    print(f"  {i:02d}: fr='{p['fr']}' | relue={p.get('relue')}")

# 2. Extraire les 36 gabarits du rapport RAPPORT_TRADUCTION.md
rapport_path = base_dir.parent / "docs/audits/RAPPORT_TRADUCTION.md"
rapport_text = rapport_path.read_text(encoding="utf-8")

# Recherche de la table 4.1.2
pattern = re.compile(r"\|\s*\*\*(\d+)\*\*\s*\|\s*«\s*([^»]+?)\s*»\s*\|\s*`([^`]+?)`\s*\|\s*([^|]+?)\s*\|\s*`([^`]+?)`\s*\|")
matches = pattern.findall(rapport_text)
print(f"\n[2] Nombre de gabarits trouvés dans la table 4.1.2 de RAPPORT_TRADUCTION.md : {len(matches)}")

table_fr_list = []
for m in matches:
    num, fr, bci_old, diag, bci_new = m
    table_fr_list.append((int(num), fr.strip(), bci_old.strip(), diag.strip(), bci_new.strip()))
    print(f"  {int(num):02d}: fr='{fr.strip()}' -> bci_new='{bci_new.strip()}'")

# 3. Comparaison entre les deux listes
print("\n[3] Concordance entre JSON et RAPPORT_TRADUCTION :")
json_fr_set = {p["fr"].strip(): p for p in phrases}
rapport_fr_set = {t[1]: t for t in table_fr_list}

in_json_not_rapport = set(json_fr_set.keys()) - set(rapport_fr_set.keys())
in_rapport_not_json = set(rapport_fr_set.keys()) - set(json_fr_set.keys())

print(f"  Présents dans JSON mais PAS dans la table du rapport ({len(in_json_not_rapport)}) :")
for s in sorted(in_json_not_rapport):
    p = json_fr_set[s]
    print(f"    - fr: '{s}'")
    print(f"      bci actuel: '{p.get('bci')}'")
    print(f"      proposition: '{p.get('proposition')}'")

# 4. Recherche de termes lexicaux dans le code existant
print("\n[4] Recherche lexicale dans les fichiers chatbot :")
import glob
for fpath in glob.glob("apps/ai_assistant/chatbot/**/*.py", recursive=True) + glob.glob("apps/ai_assistant/chatbot/donnees/*.json"):
    p = Path(fpath)
    txt = p.read_text(encoding="utf-8", errors="ignore")
    if "fata" in txt.lower():
        print(f"  Trouvé 'fata' dans {p.name}")
        for line in txt.splitlines():
            if "fata" in line.lower():
                print(f"    {line.strip()[:100]}")
    if "repass" in txt.lower():
        print(f"  Trouvé 'repass' dans {p.name}")
        for line in txt.splitlines():
            if "repass" in line.lower():
                print(f"    {line.strip()[:100]}")
