import re
import sys
from pathlib import Path

# Importer baoule_demandes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apps.ai_assistant.chatbot import baoule_demandes

print("=== 1. ANALYSE DU CATALOGUE DE BAOULE_DEMANDES.PY ===")
catalogue = baoule_demandes.CATALOGUE
print(f"Nombre total de demandes dans CATALOGUE : {len(catalogue)}")
all_demandes_ids = list(catalogue.keys())
print("Liste des IDs dans CATALOGUE :")
for i, d_id in enumerate(all_demandes_ids, 1):
    d = catalogue[d_id]
    print(f"  {i:02d}: id='{d_id}', groupe='{d.groupe}', type='{d.type}', libelle='{d.libelle}'")

# Pourquoi parle-t-on de 23 intentions ?
# Regardons les types/groupes ou intentions opérationnelles vs conversationnelles
metier_demandes = [d_id for d_id, d in catalogue.items() if d.type not in ("conversation", "hors_sujet", "libre")]
print(f"\nDemandes métier strictes (hors conversation, hors_sujet, libre) : {len(metier_demandes)}")
for d_id in metier_demandes:
    print(f"  - {d_id}")

# Regardons les intentions dans RAPPORT_TRADUCTION.md
rapport_path = Path(__file__).resolve().parent.parent.parent / "docs/audits/RAPPORT_TRADUCTION.md"
content = rapport_path.read_text(encoding="utf-8")

print("\n=== 2. EXTRACTION DES CAS DE TEST DANS SECTION 3.2 ===")
# Extraire les lignes des tables
pattern_row = re.compile(r"\|\s*\*\*(TC-[A-Z]+-\d+)\*\*\s*\|\s*`?([a-zA-Z0-9_]+)`?\s*\|\s*«\s*([^»]+?)\s*»\s*\|\s*([^|]+?)\s*\|\s*`([^`]+?)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
matches = pattern_row.findall(content)
print(f"Nombre total de cas de test extraits : {len(matches)}")

themes = {}
intentions_utilisees = {}
for m in matches:
    tc_id, intention, phrase_fr, entites, bci_cible, eval_sans, eval_avec = m
    prefix = tc_id.split("-")[1]
    themes[prefix] = themes.get(prefix, 0) + 1
    intentions_utilisees[intention] = intentions_utilisees.get(intention, 0) + 1

print("\nDistribution par préfixe de thème :")
for pref, count in themes.items():
    print(f"  {pref}: {count} cas")

print(f"\nNombre d'intentions distinctes utilisées dans les 64 cas : {len(intentions_utilisees)}")
for intention, count in sorted(intentions_utilisees.items()):
    in_cat = intention in catalogue
    print(f"  - {intention} : {count} cas (Présent dans baoule_demandes.py ? {in_cat})")

# Vérifier quelles intentions de baoule_demandes ne sont PAS dans le banc
absentes_de_catalogue = set(all_demandes_ids) - set(intentions_utilisees.keys())
print(f"\nIntentions de baoule_demandes.py NON utilisées dans les 64 cas ({len(absentes_de_catalogue)}) :")
for d_id in sorted(absentes_de_catalogue):
    d = catalogue[d_id]
    print(f"  - {d_id} (groupe={d.groupe}, type={d.type})")

# Inversement : intentions dans le banc qui ne sont PAS dans CATALOGUE
non_catalogue = set(intentions_utilisees.keys()) - set(all_demandes_ids)
print(f"\nIntentions du banc NON présentes comme ID dans CATALOGUE ({len(non_catalogue)}) :")
for inc in sorted(non_catalogue):
    print(f"  - {inc}")
