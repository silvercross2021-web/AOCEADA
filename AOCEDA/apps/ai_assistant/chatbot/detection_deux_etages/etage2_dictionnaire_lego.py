"""Étage 2 : Dictionnaire Lego / Sous-mots n-grammes & Garde-fou Rollback.

Architecture hybride « Acoustic-First, Lexical Guardrails » (R2) :
  1. Classificateur textuel ultra-rapide (< 1 ms CPU) fondé sur les briques lexicales
     et n-grammes de caractères (ordre 2, 3 et 4) pour les 5 langues cibles d'AOCEDA :
     - fr / fra (Français)
     - en / eng (Anglais)
     - wo / wol (Wolof)
     - dyu (Dioula / Bambara)
     - bci (Baoulé)
  2. Vérification linguistique de la transcription issue de l'ASR de l'Étage 1.
  3. Détection de charabia phonétique ou d'aiguillage acoustique erroné avec
     déclenchement d'un ordre de Rollback immédiat (action='ANNULER', recommencer_ecoute=True).
  4. Préservation stricte et prioritaire des commandes critiques de sécurité
     (ex. couper, allumer, oui, non).

Exécution 100 % pure Python / NumPy, zéro dépendance C supplémentaire.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalisation des codes de langues cibles (ISO 639-1, 639-2/3 et alias)
# ─────────────────────────────────────────────────────────────────────────────

LANGUES_CIBLES: Tuple[str, ...] = ("fr", "en", "wo", "dyu", "bci")

ALIAS_LANGUES: Dict[str, str] = {
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "en": "en",
    "eng": "en",
    "english": "en",
    "anglais": "en",
    "wo": "wo",
    "wol": "wo",
    "wolof": "wo",
    "dyu": "dyu",
    "dioula": "dyu",
    "jula": "dyu",
    "bambara": "dyu",
    "bam": "dyu",
    "bci": "bci",
    "baoule": "bci",
    "baoulé": "bci",
    "wawle": "bci",
}


def normaliser_code_langue(code: str) -> str:
    """Normalise un code ou identifiant de langue vers le code canonique interne."""
    if not code:
        return "fr"
    cle = str(code).strip().lower()
    return ALIAS_LANGUES.get(cle, cle)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Structure de décision du Garde-Fou
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionGardeFou:
    """Résultat de la vérification de conformité linguistique et du garde-fou."""

    statut: str  # "VALIDE", "CONFIRME", "ROLLBACK", "COMMANDE_CRITIQUE", "NEUTRE"
    langue_attendue: str  # Langue présumée (ex: issue de l'Étage 1 Audio LID)
    langue_detectee: str  # Langue prédominante observée dans le texte
    score_adequation: float  # [0.0, 1.0] adéquation du texte à la langue attendue
    scores_langues: Dict[str, float] = field(default_factory=dict)
    charabia: bool = False  # True si charabia phonétique ou mauvaise orientation ASR
    action: str = "CONTINUER"  # "CONTINUER", "ANNULER", "CONFIRMER", "EXECUTER_COMMANDE"
    recommencer_ecoute: bool = False  # Signal pour relancer l'écoute sans polluer l'historique
    explication: str = ""
    commande_critique: Optional[str] = None  # "COUPER", "ALLUMER", "OUI", "NON"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Commandes critiques de sécurité (Inviolables et Prioritaires)
# ─────────────────────────────────────────────────────────────────────────────

COMMANDES_SECURITE: Dict[str, Dict[str, List[str]]] = {
    "COUPER": {
        "fr": ["couper", "coupe", "coupez", "eteins", "éteins", "eteignez", "éteignez", "eteindre", "éteindre", "arrete le courant", "arrête le courant", "arrete le compteur", "arrête le compteur"],
        "en": ["cut", "turn off", "switch off", "power off", "shutdown", "shut off"],
        "wo": ["fay", "fay ko", "tëj", "tej", "dina fay", "dafay fay"],
        "dyu": ["a tige", "a tigɛ", "tige", "tigɛ", "a dabali", "dabali"],
        "bci": ["kpe", "kpɛ", "kpe nun", "kpe'n"],
    },
    "ALLUMER": {
        "fr": ["allumer", "allume", "allumez", "rallumer", "rallume", "remets", "remettez"],
        "en": ["turn on", "switch on", "power on", "light on"],
        "wo": ["taal", "taal ko", "takk", "takk na"],
        "dyu": ["a mene", "a mɛnɛ", "mene", "mɛnɛ"],
        "bci": ["cie", "kaci"],
    },
    "OUI": {
        "fr": ["oui", "ouais", "d'accord", "dac", "absolument", "tout a fait", "tout à fait", "je confirme", "confirmer"],
        "en": ["yes", "yeah", "yep", "sure", "confirm", "i confirm", "agree"],
        "wo": ["waaw", "waw"],
        "dyu": ["awɔ", "awo", "ɔnhɔn", "onhon"],
        "bci": ["ɛɛn", "een", "in-in"],
    },
    "NON": {
        "fr": ["non", "pas du tout", "refuser", "annuler", "arrete", "arrête"],
        "en": ["no", "nope", "cancel", "stop", "refuse"],
        "wo": ["deedeet", "déedéet", "dedet"],
        "dyu": ["ɔn ɔn", "on on", "a to yen", "ayi"],
        "bci": ["nan", "aoto", "n-in"],
    },
}

# Particules et formules négatives bloquant formellement les ordres critiques d'urgence
REGEX_NEGATION_ORDRE: re.Pattern = re.compile(
    r"\b(ne|n['’]|pas|jamais|surtout\s+pas|"
    r"don['’]?t|dont|do\s+not|never|not|can['’]?t|cannot|"
    r"bul|buleen|bula|"
    r"kana|kanna)\b",
    re.IGNORECASE | re.UNICODE
)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Briques Lego : Expressions composites discriminantes (100 % de certitude)
# ─────────────────────────────────────────────────────────────────────────────

EXPRESSIONS_LEGO: Dict[str, List[str]] = {
    "wo": [
        "nanga def", "naka nga def", "nangeen def", "jerejef", "jërejëf", "jërajëf",
        "jamm rekk", "yendul ak jamm", "fanaanal ak jamm", "kuraŋ bi", "kuran bi",
        "kurang bi", "kuraŋ gi", "kuran gi", "kuraŋ wi", "kuran wi", "koppar yi",
        "fay na", "fayna", "takk na", "takkna", "sama kuraŋ", "sama kuran", "sama kurang",
        "sa kuraŋ", "sa kuran", "sa kurang", "sa koppar", "dama bëgg", "dama begg",
        "dafay fay", "dina fay", "dafa fay", "damay fay", "lu nga wax", "lu nga def",
        "kuraŋ dafa fay", "kuran dafa fay", "waaw", "déedéet", "deedeet", "amoon na",
        "kenn xamatu", "mbëj mi", "faktiir bi", "konteer bi"
    ],
    "dyu": [
        "i ni sogoma", "i ni sɔgɔma", "i ni tile", "i ni wula", "i ni su", "aw ni baara",
        "i ni baara", "i ni ce", "aw ni ce", "kuran juru banna", "kuran juru",
        "kuran fakitiri", "kuran fakiti", "n ka kuran", "ne b'a fɛ", "ne b'a fe",
        "n bɛ se", "n be se", "ka dɔ bɔ", "ka do bo", "cogo di", "mun kɛ", "mun ke",
        "kilowati lere", "kilowati lɛrɛ", "bi naani ni fila", "a to yen", "ɔn ɔn",
        "awɔ", "a tige", "a tigɛ", "recharger ni wave", "kuran recharger"
    ],
    "bci": [
        "aniho", "aɲiho", "are o", "arɛ o", "manti", "aanti o", "anun o", "awossin o",
        "awossi'n o", "kuran wie", "kouran wie", "kuran wa wie", "kuran w'a wie",
        "min kuran", "min kuran'n", "sua'n", "klɔ'n", "klo'n", "ninnge'm",
        "ti kekle", "kɔnptɛr", "konpter", "kredit", "faktir", "sika", "wewa", "alye",
        "sran", "ninnge", "lika nun", "be wa", "akan nun"
    ],
    "fr": [
        "bonjour", "bonsoir", "merci beaucoup", "s'il vous plait", "s'il vous plaît",
        "facture d'électricité", "facture d'electricite", "compteur d'électricité",
        "compteur electrique", "compteur électrique", "reduire ma facture",
        "réduire ma facture", "combien de credit", "combien de crédit",
        "coupure de courant", "panne de courant", "climatiseur", "consommation",
        "disjoncteur", "delestage", "délestage", "recharger mon compteur", "code de recharge"
    ],
    "en": [
        "good morning", "good afternoon", "good evening", "thank you", "please",
        "electricity bill", "power bill", "electric meter", "reduce my bill",
        "how much credit", "power outage", "blackout", "air conditioner",
        "power consumption", "electricity consumption", "meter balance",
        "recharge my meter", "turn off the power", "cut the power"
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Briques Morphosyntaxiques et Affixes distinctifs
# ─────────────────────────────────────────────────────────────────────────────

# Article défini baoulé suffixé par apostrophe : sua'n, klɔ'n, ninnge'm, etc.
REGEX_ARTICLE_BAOULE = re.compile(r"\b\w+['’][nm]\b", re.UNICODE | re.IGNORECASE)

# Formules interrogatives baoulé en fin de phrase
REGEX_QUESTION_BAOULE = re.compile(r"\s(ɔ|ɔn|o)\s*\?\s*$", re.UNICODE | re.IGNORECASE)

# Pluriel dioula en -w (au moins 3 caractères avant le w, hors mots anglais usuels)
REGEX_PLURIEL_DIOULA = re.compile(r"\b[a-zɛɔɲŋ]{3,}w\b", re.UNICODE | re.IGNORECASE)

# Classificateurs wolof post-posés à un nom
REGEX_CLASSIFICATEUR_WOLOF = re.compile(
    r"\b(kuran|kuraŋ|kuuran|kuuraŋ|koppar|koppal|kër|ker|dëkk|dekk|nit|xale|watt|compteur|konteer|facture|faktiir)\s+(bi|gi|wi|ji|mi|si|ki|ñi|yi)\b",
    re.UNICODE | re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Vocabulaire Métier et Mots Forts discriminants par Langue
# ─────────────────────────────────────────────────────────────────────────────

MOTS_FORTS_LANGUES: Dict[str, Set[str]] = {
    "wo": {
        "dafa", "dafay", "dama", "damay", "danga", "dangay", "danu", "danuy", "dañu", "dañuy", "dangeen",
        "dina", "dinaa", "dinga", "dingaa", "dingeen", "dinanu", "dinañu", "laay", "ngay",
        "duma", "dumay", "dunga", "dungay", "dunu", "duñuy", "dungeen", "yow", "moom", "ñun", "yeen",
        "ñoom", "seen", "nanga", "nangeen", "naka", "sama", "sunu", "ñaata", "ñata", "lan", "kañ",
        "lutax", "mangi", "yangi", "mungi", "nungi", "ñungi", "nekkoon", "amoon", "amna", "amul",
        "mëna", "mënoon", "bëgg", "bëggoon", "bëggna", "saytu", "seytu", "xamal", "dellusi", "waxoon",
        "waxna", "gisoon", "gisna", "deggoon", "jëflante", "fay", "takk", "jeex", "jot", "waññi",
        "yokk", "rekk", "jamm", "baax", "waaw", "waw", "deedeet", "déedéet", "dedet", "rawatina",
        "kuraŋ", "kuuraŋ", "kurang", "mbëj", "koppar", "koppal", "kër", "dëkk", "leegi", "léegi",
        "taal", "sotti", "faktiir", "konteer", "kontoor", "jerejef", "jërejëf",
        # Cardinaux wolof
        "benn", "ñaar", "naar", "ñatt", "natt", "ñeent", "neent", "juróom", "juroom",
        "fukk", "fukki", "fanweer", "téeméer", "teemeer", "junne", "junni",
    },
    "dyu": {
        "sɔgɔma", "sogoma", "tile", "wula", "baara", "kuran", "fakitiri", "fakiti", "kilowati",
        "juru", "banna", "mɔgɔw", "baaraw", "polisiw", "mɔgɔ", "muso", "kɛ", "dɔ", "fɛ", "ye",
        "bɛ", "tɛ", "ka", "la", "ma", "kɔ", "kan", "ne", "an", "aw", "ale", "olu",
        "mun", "cogo", "di", "lɛrɛ", "lere", "dibi", "dɔgɔ", "tora", "sara", "sɔrɔ",
        "tigɛ", "tige", "dabali", "awɔ", "awo", "ɔn", "mɛnɛ", "mene", "janto",
        # Cardinaux dioula / bambara
        "kelen", "fila", "saba", "naani", "duru", "wɔɔrɔ", "wooro", "wolonwula",
        "seegin", "kɔnɔntɔ", "kononto", "tan", "mugen", "mugan", "kɛmɛ", "keme",
    },
    "bci": {
        "aɲiho", "aniho", "arɛ", "are", "manti", "aanti", "anun", "awossi", "awossin",
        "kuran", "kouran", "kredit", "faktir", "faktiri", "konptɛr", "kɔnptɛr", "konpter",
        "sika", "wewa", "alye", "kpa", "sran", "ninnge", "lika", "nun", "wie", "kekle",
        "sua", "klɔ", "klo", "okan", "akan", "bue", "cien", "cie", "kpɛ", "kpe", "nan",
        "ɛɛn", "een", "min", "kilowati", "kilowatt",
        # Cardinaux baoulé
        "kun", "nnyɔn", "nnyon", "nsan", "nnan", "nnun", "nsien", "nso",
        "mɔcuɛ", "mocue", "nguan", "blu", "ablu", "ya", "akpi",
    },
    "fr": {
        "facture", "compteur", "électricité", "electricite", "courant", "recharge", "recharger",
        "consommation", "consommer", "climatiseur", "climatisation", "appareil", "puissance",
        "tension", "ampère", "disjoncteur", "panne", "coupure", "délestage", "kilowatt", "solde",
        "payer", "paiement", "combien", "réduire", "reduire", "pourquoi", "comment", "bonjour",
        "bonsoir", "merci", "éteindre", "allumer", "vérifier", "alerte", "tension", "relevé",
        # Cardinaux français
        "un", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
        "onze", "douze", "treize", "quatorze", "quinze", "seize", "vingt", "trente", "quarante",
        "cinquante", "soixante", "cent", "mille", "million",
    },
    "en": {
        "bill", "meter", "electricity", "electric", "power", "consumption", "consume", "recharge",
        "balance", "current", "conditioner", "appliance", "voltage", "outage", "blackout", "breaker",
        "cut", "switch", "turn", "reduce", "check", "how", "what", "why", "when", "please",
        "thank", "hello", "morning", "afternoon", "evening", "kilowatt", "kwh", "light", "payment",
        # Cardinaux anglais
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "twenty", "thirty",
        "forty", "fifty", "sixty", "hundred", "thousand", "million",
        # Termes morphologiques exemptés phonotactiquement
        "strength", "strengths", "length", "lengths", "twelfth", "twelfths", "and",
        "catchphrase", "birthplace", "witchcraft", "watchstrap",
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Sous-mots n-grammes de caractères calibrés (Ordre 2, 3 et 4)
# ─────────────────────────────────────────────────────────────────────────────

# Table des n-grammes discriminants avec poids logarithmiques associés
# Format: {ngram: {langue: poids}}
NGRAMMES_POIDS: Dict[str, Dict[str, float]] = {
    # ── WOLOF ──
    "dafa": {"wo": 2.5}, "daf": {"wo": 1.8}, "afay": {"wo": 2.2}, "dama": {"wo": 2.0},
    "amay": {"wo": 1.8}, "dina": {"wo": 2.0}, "inga": {"wo": 1.5}, "nanga": {"wo": 3.0},
    "anga": {"wo": 1.8}, "jere": {"wo": 2.5}, "rejef": {"wo": 3.0}, "jëre": {"wo": 3.0},
    "ërej": {"wo": 3.0}, "rejëf": {"wo": 3.0}, "kuraŋ": {"wo": 3.0}, "uraŋ": {"wo": 2.5},
    "mbëj": {"wo": 3.0}, "bëj": {"wo": 2.2}, "kopp": {"wo": 2.2}, "oppar": {"wo": 2.5},
    "waaw": {"wo": 3.0}, "déed": {"wo": 3.0}, "éedé": {"wo": 3.0}, "déet": {"wo": 3.0},
    "rekk": {"wo": 2.8}, "ekk": {"wo": 1.4}, "jamm": {"wo": 2.8}, "sayt": {"wo": 2.2},
    "aytu": {"wo": 2.0}, "xama": {"wo": 2.2}, "amal": {"wo": 1.5}, "bëgg": {"wo": 3.0},
    "_nan": {"wo": 1.8}, "def_": {"wo": 2.0}, "ëkk": {"wo": 2.0}, "_bi_": {"wo": 1.5},

    # ── DIOULA / BAMBARA ──
    "sɔgɔ": {"dyu": 3.0}, "ɔgɔm": {"dyu": 3.0}, "gɔma": {"dyu": 3.0}, "tile": {"dyu": 2.2},
    "wula": {"dyu": 2.2}, "kuran": {"dyu": 1.5, "bci": 1.2, "wo": 1.0}, "faki": {"dyu": 2.5},
    "kiti": {"dyu": 2.2}, "tiri": {"dyu": 2.0}, "juru": {"dyu": 2.8}, "bann": {"dyu": 2.5},
    "anna": {"dyu": 1.5}, "mɔgɔ": {"dyu": 2.8}, "baar": {"dyu": 2.2}, "aara": {"dyu": 1.8},
    "lɛrɛ": {"dyu": 2.8}, "kilo": {"dyu": 1.5, "bci": 1.5, "fr": 1.0, "en": 1.0}, "wati": {"dyu": 2.5, "bci": 2.5},
    "bɛ_": {"dyu": 2.0}, "tɛ_": {"dyu": 2.0}, "tigɛ": {"dyu": 2.8}, "dabali": {"dyu": 2.8},
    "awɔ": {"dyu": 3.0}, "ɔnhɔ": {"dyu": 3.0}, "ɔn_ɔ": {"dyu": 3.0},

    # ── BAOULÉ ──
    "sua'": {"bci": 3.0}, "ua'n": {"bci": 3.0}, "klɔ'": {"bci": 3.0}, "lɔ'n": {"bci": 3.0},
    "kɔnp": {"bci": 3.0}, "ɔnpt": {"bci": 3.0}, "ptɛr": {"bci": 3.0}, "kpa_": {"bci": 2.5},
    "_kpa": {"bci": 2.5}, "sran": {"bci": 2.8}, "ninn": {"bci": 2.5}, "nnge": {"bci": 2.5},
    "lika": {"bci": 2.2}, "nun_": {"bci": 2.0}, "w'a_": {"bci": 2.8}, "_w'a": {"bci": 2.8},
    "aɲih": {"bci": 3.0}, "ɲiho": {"bci": 3.0}, "mant": {"bci": 2.5}, "anti": {"bci": 1.5},
    "wewa": {"bci": 2.8}, "alye": {"bci": 2.8}, "kour": {"bci": 2.0}, "oura": {"bci": 1.2},
    "kred": {"bci": 2.0}, "fakt": {"bci": 2.0}, "ɛɛn": {"bci": 3.0}, "cie_": {"bci": 2.2},

    # ── FRANÇAIS ──
    "fact": {"fr": 2.2}, "actu": {"fr": 1.8}, "ctur": {"fr": 1.8}, "ture": {"fr": 1.8},
    "comp": {"fr": 2.0}, "ompt": {"fr": 2.0}, "mpte": {"fr": 2.0}, "pteur": {"fr": 2.5},
    "elec": {"fr": 1.8, "en": 1.2}, "lect": {"fr": 1.8, "en": 1.2}, "ectr": {"fr": 1.8, "en": 1.2},
    "ctri": {"fr": 1.8, "en": 1.2}, "icit": {"fr": 2.2, "en": 1.5}, "cour": {"fr": 2.0},
    "oura": {"fr": 1.4}, "rant": {"fr": 1.8}, "cons": {"fr": 1.5, "en": 1.2}, "onso": {"fr": 2.0},
    "somm": {"fr": 2.2}, "mati": {"fr": 1.8}, "atio": {"fr": 1.8, "en": 1.5}, "tion": {"fr": 1.8, "en": 1.5},
    "clim": {"fr": 2.2}, "lima": {"fr": 1.8}, "appa": {"fr": 2.0}, "pare": {"fr": 2.0},
    "reil": {"fr": 2.2}, "disj": {"fr": 2.8}, "onct": {"fr": 2.5}, "eur_": {"fr": 1.8},
    "pann": {"fr": 2.2}, "dele": {"fr": 2.2}, "lest": {"fr": 2.2}, "stag": {"fr": 2.0},
    "sold": {"fr": 2.2}, "paye": {"fr": 2.2}, "comb": {"fr": 2.5}, "bien": {"fr": 2.2},
    "bonj": {"fr": 2.5}, "onjo": {"fr": 2.5}, "njour": {"fr": 2.8}, "pour": {"fr": 2.0},
    "avec": {"fr": 2.0}, "dans": {"fr": 2.0}, "votr": {"fr": 2.0}, "quel": {"fr": 2.0},

    # ── ANGLAIS ──
    "_bil": {"en": 2.5}, "bill": {"en": 2.8}, "ill_": {"en": 2.0}, "mete": {"en": 2.5},
    "eter": {"en": 2.2}, "powe": {"en": 2.5}, "ower": {"en": 2.2}, "sump": {"en": 2.5},
    "umpt": {"en": 2.5}, "outa": {"en": 2.8}, "tage": {"en": 2.2}, "curr": {"en": 2.2},
    "rren": {"en": 2.0}, "bala": {"en": 2.2}, "lanc": {"en": 2.0}, "ance": {"en": 1.8},
    "appl": {"en": 2.0}, "lian": {"en": 2.0}, "chec": {"en": 2.2}, "heck": {"en": 2.2},
    "what": {"en": 2.5}, "how_": {"en": 2.5}, "plea": {"en": 2.5}, "ease": {"en": 2.0},
    "than": {"en": 2.5}, "hank": {"en": 2.5}, "hell": {"en": 2.5}, "ello": {"en": 2.2},
    "good": {"en": 2.5}, "morn": {"en": 2.5}, "even": {"en": 2.2}, "shut": {"en": 2.5},
    "the_": {"en": 2.2}, "your": {"en": 2.2}, "have": {"en": 2.0}, "this": {"en": 2.0},
}


# ─────────────────────────────────────────────────────────────────────────────
# 8. Moteur de Détection de Charabia et Déviations Phonétiques
# ─────────────────────────────────────────────────────────────────────────────

# Mots anglais légitimes contenant un amas de 5 consonnes consécutives (violation apparente)
MOTS_EXEMPTES_AMAS_CONSONNES: Set[str] = {
    "strength", "strengths", "length", "lengths", "twelfth", "twelfths",
    "catchphrase", "birthplace", "witchcraft", "watchstrap",
    "rhythm", "rhythms", "crypt", "crypts", "lynx", "myths", "tryst", "psych",
    "dryly", "shyly", "spryly", "slyly",
}

# Alphabets et scripts non autorisés (étrangers aux 5 langues cibles d'AOCEDA)
SCRIPTS_NON_AUTORISES: re.Pattern = re.compile(
    r"[\u0370-\u03FF"  # Grec et copte
    r"\u0400-\u04FF"  # Cyrillique
    r"\u0590-\u05FF"  # Hébreu
    r"\u0600-\u06FF"  # Arabe
    r"\u0900-\u097F"  # Devanagari (Hindi, Sanskrit, etc.)
    r"\u0E00-\u0E7F"  # Thaï
    r"\u4E00-\u9FFF"  # CJK unifié (Chinois / Japonais)
    r"\uAC00-\uD7AF]"  # Hangul (Coréen)
)


def est_chaine_numerique_ou_sts(texte: str) -> bool:
    """Détecte si le texte est un code compteur STS (ex: 20 chiffres), un numéro
    de série de compteur ou une saisie purement numérique / monétaire.
    Permet d'accepter ces saisies sans déclencher de rollback intempestif.
    """
    if not texte or not texte.strip():
        return False
    t = texte.strip()

    # Tout script non autorisé disqualifie immédiatement la chaîne
    if SCRIPTS_NON_AUTORISES.search(t):
        return False

    chiffres = re.findall(r"\d", t)
    nb_chiffres = len(chiffres)
    if nb_chiffres == 0:
        return False

    # Extraire les mots environnants en remplaçant chiffres et ponctuation par des espaces
    # pour préserver l'intégrité des expressions multi-mots (ex: 'compteur no 14253678901')
    sans_chiffres = re.sub(r"[\d\.,\-#/*:;()_+°]", " ", t.lower())
    mots_sans_chiffres = [m for m in re.split(r"\s+", sans_chiffres.strip()) if m]
    mots_autorises = {
        "code", "token", "sts", "compteur", "meter", "numero", "numéro",
        "number", "num", "no", "n", "recharge",
    }

    # 1. Code STS standard (20 chiffres, groupés par 4 ou 5 ou continus, avec ou sans mot-clé autorisé)
    if nb_chiffres == 20:
        if not mots_sans_chiffres or all(m in mots_autorises for m in mots_sans_chiffres):
            return True
        return False

    # 2. Numéro de compteur ou série longue (>= 8 chiffres)
    if nb_chiffres >= 8:
        if not mots_sans_chiffres or all(m in mots_autorises for m in mots_sans_chiffres):
            return True
        return False

    # 3. Entrée purement numérique (montant, quantité : ex '5000', '20 000', '15', '0')
    if not mots_sans_chiffres:
        return True

    return False


def detecter_charabia_intrinsèque(texte: str) -> Tuple[bool, str]:
    """Analyse un texte pour détecter des déformations phonétiques graves, des boucles
    répétitives d'hallucination ASR ou des violations des règles phonotactiques.
    Renvoie (est_charabia, raison).
    """
    if not texte or not texte.strip():
        return True, "Texte vide ou composé uniquement d'espaces."

    t = texte.strip()

    # 1. Écritures non autorisées (Grec, Cyrillique, Hébreu, Arabe, Devanagari, Thaï, CJK, Coréen)
    # Exécuté impérativement AVANT toute immunité accordée aux chaînes numériques ou tokens STS.
    if SCRIPTS_NON_AUTORISES.search(t):
        return True, "Caractères non autorisés détectés (alphabet étranger hors langues cibles)."

    # 2. Immunité pour les codes compteurs STS et séquences purement numériques
    if est_chaine_numerique_ou_sts(t):
        return False, ""

    # 3. Texte trop court sans caractère alphabétique ou numérique
    alphanumeriques = re.findall(r"[\wɛɔɲŋ]", t, re.UNICODE)
    if len(alphanumeriques) == 0:
        return True, "Aucun caractère alphabétique identifiable."

    # 4. Caractères de répétition anormale (ex: "aaaaaa", "to to to to to")
    mots = [m for m in re.findall(r"[\wɛɔɲŋ'’-]+", t.lower()) if m]
    if len(mots) >= 4:
        # Taux de diversité lexicale (ratio type/token)
        ratio_diversite = len(set(mots)) / len(mots)
        if ratio_diversite < 0.35:
            return True, f"Boucle d'hallucination ASR détectée (ratio diversité {ratio_diversite:.2f} < 0.35)."

    # Répétition d'un même caractère consécutif >= 5 fois (ex: "kkkkk", "zzzzz")
    if re.search(r"([a-zA-Zɛɔɲŋ])\1{4,}", t):
        return True, "Répétition anormale de caractères consécutifs."

    # 5. Violations phonotactiques sévères : 5 consonnes consécutives sans voyelle
    # Les langues ouest-africaines et véhiculaires ont une structure syllabique ouverte (CV, CVC).
    # Des amas consonantiques comme "krxtp" ou "strpst" trahissent un bruit acoustique.
    # Exemption des termes anglais légitimes (strengths, lengths, twelfths, catchphrase, birthplace).
    consonnes_strictes = re.compile(r"[bcdfghjklmnpqrstvwxzɲŋ]{5,}", re.IGNORECASE)
    voyelles = re.compile(r"[aeiouɛɔ]", re.IGNORECASE)
    mots_texte = re.findall(r"[a-zA-Zɛɔɲŋ'’-]+", t.lower())
    for mot in mots_texte:
        mot_pur = re.sub(r"['’-]", "", mot)
        if mot_pur in MOTS_EXEMPTES_AMAS_CONSONNES:
            continue
        if consonnes_strictes.search(mot_pur):
            return True, "Amas consonantique invraisemblable (violation phonotactique)."
        # Mot de 5 lettres ou plus sans aucune voyelle authentique (ex: qwrtyp)
        if len(mot_pur) >= 5 and not voyelles.search(mot_pur):
            return True, "Amas consonantique invraisemblable (violation phonotactique)."

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# 9. Classificateur Textuel Lego & Garde-Fou Étage 2
# ─────────────────────────────────────────────────────────────────────────────

class ClassificateurLegoNgrammes:
    """Classificateur de sous-mots n-grammes ultra-rapide (< 1 ms CPU)

    et détecteur de charabia phonétique avec déclenchement de Rollback immédiat.
    """

    def __init__(self) -> None:
        self.langues: Tuple[str, ...] = LANGUES_CIBLES
        self._preparer_dictionnaires()

    def _preparer_dictionnaires(self) -> None:
        """Précalcule et indexe les structures pour un accès en temps constant O(1)."""
        self.expressions = EXPRESSIONS_LEGO
        self.mots_forts = MOTS_FORTS_LANGUES
        self.ngrams = NGRAMMES_POIDS

    def _extraire_ngrams(self, texte: str) -> List[str]:
        """Extrait les n-grammes de caractères de longueurs 2, 3 et 4 avec balises de mot."""
        mots = re.findall(r"[\wɛɔɲŋ'’-]+", texte.lower(), re.UNICODE)
        resultats: List[str] = []
        for mot in mots:
            m = f"_{mot}_"
            taille = len(m)
            # Bigrammes
            for i in range(taille - 1):
                resultats.append(m[i:i + 2])
            # Trigrammes
            for i in range(taille - 2):
                resultats.append(m[i:i + 3])
            # 4-grammes
            for i in range(taille - 3):
                resultats.append(m[i:i + 4])
        return resultats

    def detecter_commande_critique(self, texte: str) -> Optional[Tuple[str, str]]:
        """Identifie si le texte correspond à un ordre impératif de sécurité.

        Renvoie (type_commande, langue_commande) ou None.
        Les ordres critiques sont impératifs et concis (<= 4 mots). Les énoncés descriptifs
        ou conversationnels (ex: 'kuran bi dafa fay ci kër gi') ne sont pas des ordres.
        Sécurisation stricte : les ordres d'action (notamment COUPER) sont formellement bloqués si
        une particule négative immédiate est présente ('coupe pas', 'ne coupe pas', 'don't cut', 'never turn off').
        """
        t = texte.lower().strip()
        mots = [re.sub(r"[^\wɛɔɲŋ]", "", m) for m in re.findall(r"[\wɛɔɲŋ'’-]+", t)]
        mots = [m for m in mots if m]
        if not mots or len(mots) > 4:
            return None

        texte_normalise = " ".join(mots)
        a_negation = bool(REGEX_NEGATION_ORDRE.search(t))

        for cmd, par_lg in COMMANDES_SECURITE.items():
            # Blocage formel des ordres critiques d'action en présence d'une particule négative
            if cmd in ("COUPER", "ALLUMER") and a_negation:
                continue

            for lg, variantes in par_lg.items():
                for v in variantes:
                    v_mots = [re.sub(r"[^\wɛɔɲŋ]", "", m) for m in re.findall(r"[\wɛɔɲŋ'’-]+", v.lower())]
                    v_norm = " ".join([m for m in v_mots if m])
                    # Correspondance exacte ou début d'ordre impératif (ex: 'coupe le compteur')
                    if texte_normalise == v_norm or texte_normalise.startswith(f"{v_norm} "):
                        return cmd, lg
        return None

    def calculer_scores_langues(self, texte: str) -> Dict[str, float]:
        """Calcule la distribution de score d'adéquation pour chaque langue cible."""
        scores: Dict[str, float] = {lg: 0.0 for lg in self.langues}
        t_lower = texte.lower().strip()

        # 1. Vérification prioritaire des expressions Lego (score direct élevé)
        for lg, exprs in self.expressions.items():
            for exp in exprs:
                if exp in t_lower:
                    scores[lg] += 8.0

        # 2. Détection des motifs syntaxiques et morphologiques spécifiques
        # Baoulé : article défini apostrophé (sua'n, klɔ'n, ninnge'm)
        if REGEX_ARTICLE_BAOULE.search(texte):
            scores["bci"] += 5.0
        if REGEX_QUESTION_BAOULE.search(texte):
            scores["bci"] += 4.0

        # Dioula : pluriel en -w (mɔgɔw, polisiw)
        if REGEX_PLURIEL_DIOULA.search(t_lower):
            scores["dyu"] += 4.0

        # Wolof : classificateurs post-posés (kuran bi, koppar yi, etc.)
        if REGEX_CLASSIFICATEUR_WOLOF.search(t_lower):
            scores["wo"] += 6.0

        # 3. Mots forts du lexique métier
        mots = re.findall(r"[\wɛɔɲŋ'’-]+", t_lower, re.UNICODE)
        for m in mots:
            m_net = re.sub(r"[^\wɛɔɲŋ]", "", m)
            for lg, lexique in self.mots_forts.items():
                if m_net in lexique or m in lexique:
                    scores[lg] += 3.0

        # 4. Sous-mots n-grammes de caractères (ordre 2, 3 et 4)
        ngrams_extraits = self._extraire_ngrams(texte)
        for ng in ngrams_extraits:
            if ng in self.ngrams:
                for lg, poids in self.ngrams[ng].items():
                    scores[lg] += poids

        # 5. Normalisation probabiliste (Softmax vectorisé NumPy)
        arr_scores = np.array([scores[lg] for lg in self.langues], dtype=np.float64)
        max_s = np.max(arr_scores)

        # Si tous les scores sont nuls ou non finis (bruit pur)
        if np.isnan(max_s) or np.isinf(max_s) or max_s <= 0.01:
            proba = np.ones(len(self.langues), dtype=np.float64) / len(self.langues)
        else:
            exp_s = np.exp(arr_scores - max_s)
            somme_exp = np.sum(exp_s)
            if np.isnan(somme_exp) or np.isinf(somme_exp) or somme_exp <= 0:
                proba = np.ones(len(self.langues), dtype=np.float64) / len(self.langues)
            else:
                proba = exp_s / somme_exp
                if np.isnan(proba).any() or np.isinf(proba).any():
                    proba = np.ones(len(self.langues), dtype=np.float64) / len(self.langues)

        return {lg: float(round(p, 4)) for lg, p in zip(self.langues, proba)}

    def classifier(self, texte: str) -> Tuple[str, float, Dict[str, float]]:
        """Classifie le texte parmi les 5 langues cibles.

        Renvoie (meilleure_langue, confiance, scores_detailles).
        Si aucun signal linguistique probant n'est détecté (score_max <= 0.22),
        renvoie de façon symétrique ('inconnue', score_max, scores).
        """
        scores = self.calculer_scores_langues(texte)
        score_max = max(scores.values()) if scores else 0.0
        if score_max <= 0.22:
            return "inconnue", score_max, scores
        meilleure_lg = max(scores, key=scores.get)
        confiance = scores[meilleure_lg]
        return meilleure_lg, confiance, scores

    def verifier(self, texte: str, langue_attendue: str) -> DecisionGardeFou:
        """Vérifie la cohérence de la transcription issue de l'ASR face à la langue attendue

        et déclenche immédiatement un Rollback si une anomalie ou un charabia est détecté.
        """
        code_attendu = normaliser_code_langue(langue_attendue)

        # 1. Préservation prioritaire absolue des ordres critiques de sécurité
        cmd = self.detecter_commande_critique(texte)
        if cmd is not None:
            cmd_type, cmd_lg = cmd
            return DecisionGardeFou(
                statut="COMMANDE_CRITIQUE",
                langue_attendue=code_attendu,
                langue_detectee=cmd_lg,
                score_adequation=1.0,
                scores_langues=self.calculer_scores_langues(texte),
                charabia=False,
                action="CONTINUER",
                recommencer_ecoute=False,
                explication=f"Commande critique de sécurité identifiée : {cmd_type} ({cmd_lg}).",
                commande_critique=cmd_type,
            )

        # 2. Vérification de charabia intrinsèque (bruit, boucle d'hallucination, violation phonotactique)
        est_charabia, raison_charabia = detecter_charabia_intrinsèque(texte)
        if est_charabia:
            return DecisionGardeFou(
                statut="ROLLBACK",
                langue_attendue=code_attendu,
                langue_detectee="inconnue",
                score_adequation=0.0,
                scores_langues={lg: 0.0 for lg in self.langues},
                charabia=True,
                action="ANNULER",
                recommencer_ecoute=True,
                explication=f"Charabia ou corruption acoustique détectée : {raison_charabia}",
                commande_critique=None,
            )

        # 2.5 Validation des chaînes numériques et codes compteurs STS
        # (ex: 20 chiffres d'affilée, recharge de 5000, etc.)
        if est_chaine_numerique_ou_sts(texte):
            scores = self.calculer_scores_langues(texte)
            score_max = max(scores.values()) if scores else 0.0
            langue_detectee = max(scores, key=scores.get) if score_max > 0.35 else code_attendu
            return DecisionGardeFou(
                statut="VALIDE",
                langue_attendue=code_attendu,
                langue_detectee=langue_detectee,
                score_adequation=1.0,
                scores_langues=scores,
                charabia=False,
                action="CONTINUER",
                recommencer_ecoute=False,
                explication="Code compteur STS ou séquence numérique valide (accepté sans rollback).",
                commande_critique=None,
            )

        # 3. Calcul de la distribution de probabilités sur les 5 langues
        scores = self.calculer_scores_langues(texte)
        score_max = max(scores.values()) if scores else 0.0

        # Traitement symétrique du biais zéro-évidence : si aucun signal probant n'est détecté
        # (S_max <= 0.22), ne pas privilégier arbitrairement "fr" par ordre d'itération du dict.
        if score_max <= 0.22:
            langue_predite = "inconnue"
        else:
            langue_predite = max(scores, key=scores.get)

        score_attendu = scores.get(code_attendu, 0.0)
        score_predit = scores.get(langue_predite, score_max)

        # 4. Analyse de conformité et détection d'aiguillage acoustique erroné (Mismatch)
        # Seuil d'adéquation minimal requis pour valider la langue attendue
        SEUIL_ADEQUATION_MIN = 0.30
        SEUIL_CONFLIT_SEVERITE = 0.65

        # Cas A : La langue attendue domine ou possède une adéquation satisfaisante
        if (langue_predite == code_attendu and langue_predite != "inconnue") or score_attendu >= SEUIL_ADEQUATION_MIN:
            statut = "CONFIRME" if score_attendu >= 0.70 else "VALIDE"
            return DecisionGardeFou(
                statut=statut,
                langue_attendue=code_attendu,
                langue_detectee=langue_predite,
                score_adequation=score_attendu,
                scores_langues=scores,
                charabia=False,
                action="CONTINUER",
                recommencer_ecoute=False,
                explication=f"Transcription cohérente avec la langue attendue '{code_attendu}' (score : {score_attendu:.2f}).",
                commande_critique=None,
            )

        # Cas B : Conflit linguistique franc — L'ASR transcrit dans une autre langue
        # (ex. Locuteur Wolof dirigé vers ASR Dioula produisant des fragments incohérents)
        if score_predit >= SEUIL_CONFLIT_SEVERITE and langue_predite not in (code_attendu, "inconnue"):
            return DecisionGardeFou(
                statut="ROLLBACK",
                langue_attendue=code_attendu,
                langue_detectee=langue_predite,
                score_adequation=score_attendu,
                scores_langues=scores,
                charabia=True,
                action="ANNULER",
                recommencer_ecoute=True,
                explication=(
                    f"Aiguillage acoustique erroné ou charabia détecté : attendu '{code_attendu}' (adéquation {score_attendu:.2f}), "
                    f"mais fort signal linguistique '{langue_predite}' (confiance {score_predit:.2f})."
                ),
                commande_critique=None,
            )

        # Cas C : Score attendu trop faible sans qu'aucune autre langue ne soit claire (bruit textuel ou zéro-évidence)
        return DecisionGardeFou(
            statut="ROLLBACK",
            langue_attendue=code_attendu,
            langue_detectee=langue_predite,
            score_adequation=score_attendu,
            scores_langues=scores,
            charabia=True,
            action="ANNULER",
            recommencer_ecoute=True,
            explication=(
                f"Adéquation linguistique insuffisante pour '{code_attendu}' (score {score_attendu:.2f} < {SEUIL_ADEQUATION_MIN}). "
                "Transcription non certifiée, relance de l'écoute nécessaire."
            ),
            commande_critique=None,
        )


# Instance singleton globale pour exécution ultra-rapide réentrante
_CLASSIFICATEUR_INSTANCE = ClassificateurLegoNgrammes()


def verifier_transcription_et_garde_fou(texte: str, langue_attendue: str) -> DecisionGardeFou:
    """Point d'entrée officiel pour la validation linguistique Étage 2 et le Garde-Fou Rollback."""
    return _CLASSIFICATEUR_INSTANCE.verifier(texte, langue_attendue)


def classifier_langue_lego(texte: str) -> Tuple[str, float, Dict[str, float]]:
    """Point d'entrée officiel pour la classification textuelle rapide parmi les 5 langues cibles."""
    return _CLASSIFICATEUR_INSTANCE.classifier(texte)


def detecter_charabia(texte: str) -> Tuple[bool, str]:
    """Point d'entrée pour la détection intrinsèque de charabia ou bruit textuel."""
    return detecter_charabia_intrinsèque(texte)


def verifier_code_sts_ou_numerique(texte: str) -> bool:
    """Point d'entrée pour tester si une chaîne est un code STS ou une saisie numérique valide."""
    return est_chaine_numerique_ou_sts(texte)
