import re
import sys

print("=== STRESS-TEST DU MÉCANISME DE MASQUAGE PAR PLACEHOLDERS ===")

# 1. Regex de réparation proposée dans RAPPORT_TRADUCTION.md:
# re.sub(r"__\s*([A-Z_]+)\s*_\s*(\d+)\s*__", r"__\1_\2__", texte_traduit)
regex_reparatrice = re.compile(r"__\s*([A-Z_]+)\s*_\s*(\d+)\s*__")

test_variations_google = [
    ("__ KWH _ 1 __", True, "Espaces simples autour de _"),
    ("__   KWH   _   1   __", True, "Multiples espaces"),
    ("_ _ KWH _ 1 _ _", False, "Espace entre les doubles tirets du bas (_ _)"),
    ("__ PRIX _ FCFA _ 1 __", False, "Espace autour du tiret bas interne au tag (PRIX _ FCFA)"),
    ("__ kwh _ 1 __", False, "Minuscules produites par le traducteur (__ kwh _ 1 __)"),
    ("__ Kwh _ 1 __", False, "Casse mixte (__ Kwh _ 1 __)"),
    ("__ Prix_Fcfa _ 1 __", False, "Casse mixte sur tag composé"),
    ("__ KWH 1 __", False, "Tiret bas avant le chiffre supprimé par le traducteur"),
    ("__KWH_1__", True, "Forme intacte sans espaces"),
    ("Climatiseur'n di __ KWH _ 1 __ yɛle", True, "Intégré dans une phrase baoulé"),
    ("Climatiseur'n di__ KWH _ 1 __yɛle", True, "Collé aux mots adjacents"),
    ("__KWH_10__", True, "Nombre à deux chiffres"),
]

print("\n--- TEST 1 : VARIATIONS D'ESPACEMENT ET DE CASSE DE GOOGLE TRANSLATE ---")
for raw, expected_match, desc in test_variations_google:
    repaired = regex_reparatrice.sub(r"__\1_\2__", raw)
    matched = repaired != raw or ("__KWH_1__" in raw or "__KWH_10__" in raw)
    # Vérifions si le résultat final est bien une balise hermétique __TAG_N__
    has_canonical = bool(re.search(r"__[A-Z_]+_\d+__", repaired))
    print(f"[{'PASS' if has_canonical == expected_match else 'FAIL'}] {desc}")
    print(f"     Entrée  : {raw!r}")
    print(f"     Sortie  : {repaired!r}")
    print(f"     Valide ? {has_canonical} (Attendu: {expected_match})")


print("\n--- TEST 2 : MULTIPLES NOMBRES DÉCIMAUX ET SÉPARATEURS DE MILLIERS ---")
# Exemple : "12,5 kWh à 87,4 FCFA"
# Exemple : "de 48 000 à 56 000 francs" (espace dans les milliers)
# Exemple : "Consommation : 3,4 kWh, coût : 312 FCFA, tension : 220 V, intensité : 5,5 A"

phrases_test = [
    "12,5 kWh à 87,4 FCFA",
    "Consommation de 3,4 kWh pour 312 FCFA à 220 V",
    "Cela peut aller de 48 000 à 56 000 francs.",
    "La prise a consommé 0,6 kWh, soit 55,2 FCFA.",
    "Il fait 26,5 °C avec une puissance de 1 250,5 W."
]

# Tentons une extraction naïve vs ordonnée
def simuler_pipeline_masquage(phrase):
    tokens = {}
    cpt = {"kwh": 0, "prix": 0, "num": 0, "volt": 0, "watt": 0, "amp": 0}
    texte = phrase

    # Patterns spécifiques ordonnés
    # ATTENTION : Si l'ordre ou les regex sont mal conçus :
    # 1. kwh
    def repl_kwh(m):
        cpt["kwh"] += 1
        t = f"__KWH_{cpt['kwh']}__"
        tokens[t] = m.group(0)
        return t
    texte = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kilowattheures?|kWh)\b", repl_kwh, texte, flags=re.I)

    # 2. prix fcfa
    def repl_prix(m):
        cpt["prix"] += 1
        t = f"__PRIX_FCFA_{cpt['prix']}__"
        tokens[t] = m.group(0)
        return t
    texte = re.sub(r"\b\d+(?:[\s.,]\d+)*\s*(?:francs(?:\s+cfa)?|fcfa)\b", repl_prix, texte, flags=re.I)

    # 3. volts
    def repl_volt(m):
        cpt["volt"] += 1
        t = f"__VOLT_{cpt['volt']}__"
        tokens[t] = m.group(0)
        return t
    texte = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:volts?|V)\b", repl_volt, texte, flags=re.I)

    # 4. watts
    def repl_watt(m):
        cpt["watt"] += 1
        t = f"__WATT_{cpt['watt']}__"
        tokens[t] = m.group(0)
        return t
    texte = re.sub(r"\b\d+(?:[\s.,]\d+)*\s*(?:watts?|W)\b", repl_watt, texte, flags=re.I)

    # 5. nombres décimaux ou entiers restants
    def repl_num(m):
        cpt["num"] += 1
        t = f"__NUM_{cpt['num']}__"
        tokens[t] = m.group(0)
        return t
    texte = re.sub(r"\b\d+(?:[.,]\d+)?\b", repl_num, texte)

    return texte, tokens

for p in phrases_test:
    masque, tok = simuler_pipeline_masquage(p)
    print(f"\nPhrase  : {p}")
    print(f"Masqué  : {masque}")
    print(f"Tokens  : {tok}")


print("\n--- TEST 3 : COLLISION DE TOKENS ET EFFET DE BORD DE RÉINJECTION ---")
# Problème classique de réinjection :
# Si on remplace __NUM_1__ avant __NUM_10__
texte_avec_10_tokens = "Valeurs : " + " ".join(f"__NUM_{i}__" for i in range(1, 12))
valeurs = {f"__NUM_{i}__": f"VAL_{i}" for i in range(1, 12)}

# Remplacement naïf par .replace() séquentiel
texte_remplace_naif = texte_avec_10_tokens
for t, v in valeurs.items():
    texte_remplace_naif = texte_remplace_naif.replace(t, v)

print("Test de réinjection séquentielle (1 à 11) :")
print(f"Entrée  : {texte_avec_10_tokens}")
print(f"Sortie  : {texte_remplace_naif}")
# __NUM_10__ contient __NUM_1__, s'il est remplacé d'abord, __NUM_10__ devient VAL_10__ !
has_bug_num10 = "VAL_10__" in texte_remplace_naif or "__NUM_10__" not in texte_avec_10_tokens and "VAL_10" not in texte_remplace_naif
print(f"Collision __NUM_1__ sur __NUM_10__ ? {'OUI (BUG CRITIQUE)' if 'VAL_10__' in texte_remplace_naif or 'VAL_10' not in texte_remplace_naif else 'NON'}")

# Problème de collision avec le texte utilisateur :
user_inputs = [
    "Mon mot de passe est __SECRET_1__",
    "Regarde dans __init__.py",
    "J'ai payé __PRIX_FCFA_1__ hier",
    "Voici du texte en __gras__ et __italique__"
]
print("\nTest de collision avec texte utilisateur contenant '__' :")
for u in user_inputs:
    matched = bool(regex_reparatrice.search(u))
    print(f"User text: {u!r} -> Matché par regex réparation ? {matched}")
