#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_dashes.py — Détecteur de caractères « tirets longs » et signes typographiques
« qui font IA » dans TOUT le projet AOCEDA.

Usage :
    python detect_dashes.py            # rapport complet
    python detect_dashes.py --prose    # ne montre que les tirets de PROSE (encadrés d'espaces)
    python detect_dashes.py --code static/js   # limite le scan à un sous-dossier

Ce que ça détecte (avec fichier:ligne:colonne + extrait de contexte) :
  —  U+2014 tiret cadratin (em dash)      -> le vrai « tic d'IA » quand il sert de ponctuation
  –  U+2013 tiret demi-cadratin (en dash) -> normal dans les plages de dates, signalé quand même
  ―  U+2015 barre horizontale
  ‒  U+2012 tiret numéral
  −  U+2212 signe moins
  ⸺ ⸻ U+2E3A/2E3B tirets doubles/triples
  …  U+2026 points de suspension (autre tic fréquent) — informatif

Le « — » ENCADRÉ D'ESPACES ( — ) = ponctuation de prose = à remplacer.
Le « — » COLLÉ (ex. '—', >—<, '— W') = valeur vide / placeholder = convention standard, OK.
"""
import os
import sys
import unicodedata

# La console Windows (cp1252) ne sait pas afficher —, ―, … : on force l'UTF-8 en sortie.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))

# Dossiers ignorés (générés, dépendances, binaires, historiques)
EXCLUDE_DIRS = {'__pycache__', 'migrations', 'staticfiles', 'node_modules',
                'venv', '.venv', '.git', '.agents', '.idea', '.vscode', 'maquette',
                'design-references',   # docs de référence tierces (des milliers de — légitimes)
                '_backup_presync',     # dossier de sauvegarde (copies, pas le code vivant)
                '.claude'}             # commandes/skills Claude, pas le projet
# Fichiers ignorés : minifiés / bundles vendor + le détecteur lui-même (il décrit les —)
def _skip_file(fn):
    low = fn.lower()
    return '.min.' in low or low.endswith(('.bundle.js', '.pack.js')) or low == 'detect_dashes.py'
# Extensions texte à scanner (source de l'app + docs). Pas les données/binaires.
EXTS = ('.html', '.js', '.css', '.py', '.md')

# Caractères ciblés : code point -> libellé court
TARGETS = {
    '—': 'em-dash —',
    '–': 'en-dash –',
    '―': 'barre ―',
    '‒': 'figure ‒',
    '−': 'moins −',
    '⸺': '2-em ⸺',
    '⸻': '3-em ⸻',
    '…': 'ellipse …',
}


def classify(line, col, ch):
    """Retourne 'PROSE' (à corriger) / 'placeholder' / 'autre' pour un em-dash."""
    if ch != '—':
        return 'autre'
    before = line[col - 1] if col > 0 else ' '
    after = line[col + 1] if col + 1 < len(line) else ' '
    if before == ' ' and after == ' ':
        return 'PROSE'          # ponctuation encadrée d'espaces = à remplacer
    return 'placeholder'         # collé = valeur vide standard, OK


def scan(base):
    from collections import Counter
    per_char = Counter()
    prose_hits = []
    other_hits = []
    files_touched = set()

    per_file = Counter()
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
        for fn in fns:
            if not fn.endswith(EXTS) or _skip_file(fn):
                continue
            path = os.path.join(dp, fn)
            try:
                with open(path, encoding='utf-8', newline='') as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            if not any(t in text for t in TARGETS):
                continue
            rel = os.path.relpath(path, ROOT)
            for lineno, line in enumerate(text.splitlines(), 1):
                for col, ch in enumerate(line):
                    if ch in TARGETS:
                        per_char[ch] += 1
                        if ch == '—':
                            per_file[rel] += 1
                        files_touched.add(rel)
                        kind = classify(line, col, ch)
                        snippet = line.strip()[:110]
                        rec = (rel, lineno, col + 1, TARGETS[ch], snippet)
                        if kind == 'PROSE':
                            prose_hits.append(rec)
                        elif ch != '—':  # en-dash / ellipse / etc. → "autre"
                            other_hits.append(rec)
    return per_char, prose_hits, other_hits, files_touched, per_file


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    prose_only = '--prose' in sys.argv
    base = os.path.join(ROOT, args[0]) if args else ROOT

    per_char, prose_hits, other_hits, files_touched, per_file = scan(base)

    print('=' * 78)
    print(f'Scan de : {base}')
    print(f'Fichiers concernés : {len(files_touched)}')
    print('-' * 78)
    print('Totaux par caractère :')
    for ch, lbl in TARGETS.items():
        if per_char.get(ch):
            print(f'   {per_char[ch]:4d}  {lbl}  (U+{ord(ch):04X} {unicodedata.name(ch, "?")})')
    print('=' * 78)

    print('\nTop fichiers par nombre de « — » :')
    for rel, n in per_file.most_common(15):
        print(f'   {n:4d}  {rel}')
    print('=' * 78)

    print(f'\n### TIRETS DE PROSE « — » (encadrés d\'espaces) = À CORRIGER : {len(prose_hits)}')
    for rel, ln, col, lbl, snip in prose_hits:
        print(f'  {rel}:{ln}:{col}  {snip}')
    if not prose_hits:
        print('  (aucun — le texte de prose est propre)')

    if not prose_only:
        print(f'\n### AUTRES tirets/signes (en-dash, ellipse, etc.) = souvent OK, à vérifier : {len(other_hits)}')
        for rel, ln, col, lbl, snip in other_hits:
            print(f'  [{lbl}] {rel}:{ln}:{col}  {snip}')
        print('\n(Note : les « — » COLLÉS type \'—\' / >—< / \'— W\' sont des valeurs vides'
              ' standard, volontairement gardés — non listés ci-dessus.)')

    # Code de sortie : 1 s'il reste des tirets de PROSE (utile en pré-commit/CI)
    sys.exit(1 if prose_hits else 0)


if __name__ == '__main__':
    main()
