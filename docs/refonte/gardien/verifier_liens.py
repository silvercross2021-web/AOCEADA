"""Vérifie que chaque lien relatif des fichiers Markdown du dépôt pointe vers un fichier ou dossier existant.

Usage : python docs/refonte/gardien/verifier_liens.py   (depuis la racine du dépôt)
Ignore : liens http(s), mailto, ancres seules, et les dossiers d'historique (docs/refonte/0*, _a_supprimer, rapports/).
Code de sortie 1 si un lien est cassé.
"""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

RACINE = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
LIEN = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IGNORES = ("_a_supprimer/", "apps/ai_assistant/rapports/", "docs/memoire/", "docs/archives/")

fichiers = subprocess.check_output(["git", "ls-files", "-z", "*.md"], cwd=RACINE, text=True).split("\0")
fichiers += subprocess.check_output(["git", "ls-files", "-z", "--others", "--exclude-standard", "*.md"],
                                    cwd=RACINE, text=True).split("\0")
casses = []
total = 0
for f in sorted(set(x for x in fichiers if x)):
    if f.startswith(IGNORES):
        continue
    chemin = RACINE / f
    if not chemin.exists():
        continue
    texte = chemin.read_text(encoding="utf-8", errors="replace")
    texte = re.sub(r"```.*?```", "", texte, flags=re.S)
    for m in LIEN.finditer(texte):
        cible = m.group(1)
        if cible.startswith(("http://", "https://", "mailto:", "#")):
            continue
        cible = unquote(cible.split("#")[0])
        if not cible:
            continue
        total += 1
        if not (chemin.parent / cible).exists():
            casses.append((f, m.group(1)))

print(f"{total} liens relatifs vérifiés, {len(casses)} cassé(s)")
for f, c in casses:
    print(f"  CASSÉ : {f} -> {c}")
sys.exit(1 if casses else 0)
