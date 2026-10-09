"""Langue de la réponse : demande explicite de l'utilisateur + contrôle de la réponse écrite par le modèle.

1. Demande explicite (« réponds-moi en anglais », « answer in Spanish », « parle en français ») :
   elle est retenue pour la conversation et passe AVANT la détection automatique (sinon, « réponds en anglais »
   écrit en français serait détecté « français » et contredirait la demande).
   05/10/2026 (retour client) : la demande se repère sous toutes ses formes (« donne-moi les réponses en anglais »,
   « en anglais stp », « passe à l'anglais », « switch to English ») ; une question de TRADUCTION (« comment dit-on
   merci en anglais ? ») n'en est pas une ; une langue que le chatbot ne parle pas (agni, bété...) est repérée pour
   qu'on le dise honnêtement au lieu d'inventer.
2. Contrôle : dès la 1re phrase puis à la fin, on vérifie que la réponse est bien dans la langue attendue ;
   sinon on la fait refaire une fois (mesuré : un mot français s'était glissé dans une réponse en espagnol).
"""
import re
import unicodedata

from . import detection, langues

# noms des langues tels que les gens les écrivent (fr, natif, anglais, espagnol)
NOMS_ANGLAIS = {"fr": "french", "en": "english", "es": "spanish", "pt": "portuguese", "de": "german", "it": "italian",
                "nl": "dutch", "ar": "arabic", "sw": "swahili", "zh": "chinese", "ja": "japanese", "ko": "korean",
                "hi": "hindi", "bn": "bengali", "ru": "russian", "uk": "ukrainian", "pl": "polish", "tr": "turkish",
                "vi": "vietnamese", "th": "thai", "id": "indonesian", "ro": "romanian", "el": "greek", "he": "hebrew",
                "sv": "swedish", "cs": "czech", "hu": "hungarian"}
NOMS_ESPAGNOL = {"fr": "frances", "en": "ingles", "es": "espanol", "pt": "portugues", "de": "aleman", "it": "italiano",
                 "ar": "arabe"}


def _sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


_NOMS = {"dioula": "dyu", "jula": "dyu", "dyula": "dyu", "djoula": "dyu", "joula": "dyu", "diula": "dyu",
         "baoule": "bci", "baule": "bci", "baoulé": "bci", "wawle": "bci", "baole": "bci"}
for _code, (_fr, _natif, _nav) in langues.LANGUES.items():
    for _n in (_fr, _natif, NOMS_ANGLAIS.get(_code, ""), NOMS_ESPAGNOL.get(_code, "")):
        if _n:
            _NOMS[_sans_accent(_n)] = _code

# Langues qu'on peut nous demander mais que le chatbot ne parle PAS (ni voix ni écriture fiable) : on le dit, on
# n'invente jamais. Nom écrit sans accent -> nom affiché. (Le bambara et le malinké sont proches du dioula, mais ce
# ne sont pas les mêmes langues : on ne fait pas semblant.)
NON_PRISES = {"agni": "agni", "anyi": "agni", "anyin": "agni", "agny": "agni", "bete": "bété", "senoufo": "sénoufo",
              "senufo": "sénoufo", "gouro": "gouro", "yacouba": "yacouba", "attie": "attié", "abbey": "abbey",
              "abron": "abron", "guere": "guéré", "lobi": "lobi", "koulango": "koulango", "ebrie": "ébrié",
              "adioukrou": "adioukrou", "nzema": "nzema", "appolo": "appolo", "malinke": "malinké", "bambara": "bambara",
              "wolof": "wolof", "moore": "mooré", "mossi": "mooré", "lingala": "lingala", "yoruba": "yoruba",
              "haoussa": "haoussa", "hausa": "haoussa", "ewe": "éwé", "twi": "twi", "akan": "akan", "peul": "peul",
              "fulfulde": "peul", "pular": "peul", "dida": "dida", "neyo": "néyo", "godie": "godié", "toura": "toura",
              "kroumen": "kroumen", "avikam": "avikam", "alladian": "alladian", "mahou": "mahou", "koyaka": "koyaka"}

# « réponds / donne-moi les réponses / parle / passe / reviens ... en X, au X, à l'X » ; « answer / speak / switch ... in /
# to X » ; « responde / habla ... en X »
_VERBES = (r"reponds?|repondez|repondre|reponses?|parle[sz]?|parler|ecris|ecrivez|ecrire|continue[sz]?|continuer|passe[sz]?|"
           r"passer|reviens|revenez|revenir|dis|dites|traduis|traduisez|utilise[sz]?|"
           r"answers?|reply|respond|speak|talk|write|continue|switch|change|go back|use|"
           r"responde|respondeme|contesta|habla|escribe|cambia")
_VERBE = re.compile(rf"\b(?:{_VERBES})\b", re.I)
_LIEN = re.compile(r"(?:\b(?:en|in|au|to|el|al|a la)\s+|\ba l')([a-z]+)", re.I)
# « parle anglais », « parle l'agni », « speak English » (mais « je parle anglais au travail » : pas une demande)
_PARLE = re.compile(r"\b(?:parle[rsz]?|parlez|speak|talk|habla)\s+(?:le\s+|l'|en\s+)?([a-z]+)", re.I)
_SUJET = re.compile(r"\b(?:je|j|nous|on|il|elle|ils|elles|i|we|he|she|they)\s*['\s]\s*$", re.I)
# « tu comprends l'agni ? », « do you know Baoule? » : une question sur ce qu'il sait faire, jamais un changement
_CONNAIT = re.compile(r"\b(?:comprends|comprenez|comprendre|connais|connaissez|connaitre|understand|know)\s+"
                      r"(?:le\s+|la\s+|l')?([a-z]+)", re.I)
# message court : « En anglais s'il te plaît », « in English please », « Anglais ! »
_COURT = re.compile(r"(?:^|\s)(?:en|in)\s+([a-z]+)", re.I)
# question de traduction : « comment dit-on merci en anglais ? » n'est pas une demande de changer de langue
_TRADUCTION = re.compile(r"\bcomment (?:on )?(?:dit|dire|traduit|ecrit|s'ecrit|appelle)|\bcomment dit-on\b|\bque veut dire\b|"
                         r"\bca veut dire quoi\b|\btradu(?:is|isez|ire|ction)\b|\bhow (?:do|would) (?:you|i) say\b|"
                         r"\bwhat(?:'s| is| does)\b.{0,30}\b(?:mean|in)\b|\btranslat", re.I)

# en dioula : « jula la » / « julakan na » (= en dioula), « fɔ jula la » (= parle dioula)
_DEMANDE_DIOULA = re.compile(r"\b(jula|dioula|julakan|dyula)\s*(la|na)\b|\b(parle[sz]?|parler|speak|talk)\s+(le\s+)?(dioula|jula|dyula)\b", re.I)


# en baoulé : « parle baoulé », « speak baoule », « wawle nun » (= en baoulé)
_DEMANDE_BAOULE = re.compile(r"\b(parle[sz]?|parler|speak|talk)\s+(le\s+)?(baoule|baule|wawle)\b|\b(wawle|baule)\s*(nun|su)\b", re.I)


def _mot_langue(mot):
    """« anglais » -> ("en", None) ; « agni » -> (None, "agni") ; autre mot -> None."""
    m = (mot or "").lower()
    if m in _NOMS:
        return _NOMS[m], None
    if m in NON_PRISES:
        return None, NON_PRISES[m]
    return None


def _premiere(motif, t, filtre=None):
    for m in motif.finditer(t):
        if filtre and not filtre(m):
            continue
        r = _mot_langue(m.group(1))
        if r:
            return r
    return None


def langue_demandee(texte):
    """Langue que la personne DEMANDE (ou dont elle parle) dans ce message. Renvoie {"code", "non_prise", "changer"} :
    code = langue du chatbot (fr, en..., dyu, bci) ; non_prise = nom d'une langue qu'il ne parle pas (« agni ») ;
    changer = vraie demande de répondre désormais dans cette langue (False pour une question de traduction, « comment
    dit-on merci en anglais ? », ou sur ce qu'il sait faire, « tu comprends le baoulé ? »)."""
    t = _sans_accent(texte or "").replace("’", "'")
    trouve, changer = None, True
    for v in _VERBE.finditer(t):                             # verbe, puis « en / in / au / to / à l' X » juste après
        fenetre = re.split(r"[.?!\n]", t[v.end(): v.end() + 50])[0]
        trouve = _premiere(_LIEN, fenetre)
        if trouve:
            break
    # « parle anglais » ; « je parle anglais au travail » : il le dit, il ne le demande pas
    trouve = trouve or _premiere(_PARLE, t, lambda m: not _SUJET.search(t[:m.start()]))
    mots = re.findall(r"\w+", t)
    if not trouve and len(mots) <= 6:
        trouve = _premiere(_COURT, t)
        if not trouve and 1 <= len(mots) <= 2:               # « Anglais ! », « English please »
            trouve = next(filter(None, (_mot_langue(x) for x in mots)), None)
    if not trouve and _DEMANDE_DIOULA.search(t):
        trouve = ("dyu", None)
    if not trouve and _DEMANDE_BAOULE.search(t):
        trouve = ("bci", None)
    if not trouve:
        trouve, changer = _premiere(_CONNAIT, t), False
    code, non_prise = trouve or (None, None)
    if _TRADUCTION.search(t):
        changer = False
    return {"code": code, "non_prise": non_prise, "changer": bool(code) and changer}


def demande_explicite(texte):
    """Code de la langue demandée explicitement dans le message (pour toutes les réponses suivantes), ou None.
    Une question de traduction ou sur ce que sait faire le chatbot n'en est pas une."""
    d = langue_demandee(texte)
    return d["code"] if d["changer"] else None


def article(nom):
    """« l'agni », « le bété »."""
    return f"l'{nom}" if _sans_accent(nom)[:1] in "aeiouy" else f"le {nom}"


def note_langue_non_prise(nom):
    """Ajoutée à la consigne quand on demande une langue que le chatbot ne parle pas : ne JAMAIS l'inventer."""
    a = article(nom)
    return (f"\n\nDEMANDE DE LANGUE : l'utilisateur demande {a} (une réponse en {nom}, ou des mots en {nom}). Tu NE sais PAS "
            f"écrire {a} : n'écris AUCUN mot en {nom} (pas même une salutation), ne fais jamais semblant. Dis-le honnêtement "
            "en une phrase, précise que l'assistant AOCEDA comprend et répond en dioula et en baoulé, puis réponds à sa "
            "question s'il y en a une.")


MIN_LETTRES = 40          # en dessous, le texte est trop court pour juger sa langue sans se tromper
CONFIANCE_ERREUR = 0.9    # on ne fait refaire la réponse que si on est SÛR qu'elle est dans une autre langue


def mauvaise_langue(texte, attendue):
    """Renvoie la langue trouvée si la réponse n'est manifestement pas dans la langue attendue, sinon None."""
    if not attendue or attendue not in langues.LANGUES:
        return None
    if len(re.findall(r"\w", texte or "")) < MIN_LETTRES:
        return None
    code, confiance = detection.detecter(texte)
    if code and code != attendue and code in langues.LANGUES and confiance >= CONFIANCE_ERREUR:
        return code
    return None


def rappel(attendue):
    """Ordre ajouté à la consigne quand on fait refaire une réponse partie dans la mauvaise langue."""
    nom = langues.nom(attendue).lower()
    return (f"\n\nIMPORTANT : ta réponse précédente n'était PAS en {nom}. Réécris-la ENTIÈREMENT en {nom} "
            f"({langues.LANGUES[attendue][1]}), chaque mot en {nom}.")
