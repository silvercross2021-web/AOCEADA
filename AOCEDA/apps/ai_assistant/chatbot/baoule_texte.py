"""Texte BAOULÉ : reconnaître du baoulé (face au dioula et au français), lire les chiffres, formules et glossaire.

Sources (29/09/2026) :
  - fréquence des mots : VRAIS textes baoulé d'apprentissage (Common Voice train + validation, WAXAL dev), 1 468
    phrases (données/baoule_lexique.json, construit par tests/bancs/baoule_logique/construire_lexique.py) ; les phrases de
    TEST ne servent qu'à mesurer ;
  - chiffres, formules, glossaire : vérifiés dans les deux sens avec Google (fr -> baoulé -> fr) et dans les vrais
    textes (tests/bancs/baoule_logique/sondage_google.json). À FAIRE VALIDER par un locuteur baoulé : ce ne sont que des
    INDICES donnés à DeepSeek (qui reçoit aussi la traduction Google), jamais une décision à eux seuls.

Pourquoi un module à part du dioula : les deux langues partagent l'écriture (ɛ ɔ) et beaucoup de petits mots
(« be », « i », « a », « kun », « ni », « su » existent dans les deux) ; on ne peut donc PAS reconnaître le baoulé à
ses lettres, seulement à ses mots propres (« nun », « kpa », « sran », « ninnge », « lika »...) et à son article
défini collé par une apostrophe (« sua'n », « klɔ'n », « ninnge'm »), qui n'existe pas en dioula.
"""
import json
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

from . import dioula_texte
from .config import DONNEES

FICHIER_LEXIQUE = DONNEES / "baoule_lexique.json"
FREQUENT = 3                  # un mot du lexique « signe » le baoulé s'il y apparaît au moins 3 fois


def apostrophes(texte):
    """Une seule apostrophe (les textes baoulé mélangent ' ’ ʼ ‘)."""
    return re.sub(r"[’ʼ‘`´]", "'", texte or "")


def mots_de(texte):
    """Mots d'un texte baoulé (« tʃ », que Google écrit parfois, devient « tch » : « tʃɛtʃɛ » = « tchɛtchɛ »)."""
    t = apostrophes(texte).lower().replace("tʃ", "tch").replace("ʃ", "ch")
    return re.findall(r"[\wɛɔɲŋ']+", t)


cle = dioula_texte.cle        # même forme de comparaison que le dioula (sans tons, ɛ->e, lettres doublées fusionnées)


@lru_cache(maxsize=1)
def lexique():
    """{clé: nombre d'apparitions} des vrais textes baoulé d'apprentissage."""
    d = json.loads(FICHIER_LEXIQUE.read_text(encoding="utf-8"))["mots"]
    out = {}
    for mot, n in d.items():
        k = cle(mot)
        if k:
            out[k] = out.get(k, 0) + n
    return out


@lru_cache(maxsize=1)
def _propres():
    """Mots baoulé fréquents qui ne sont PAS des mots dioula (ni des mots courts ambigus)."""
    dy, _ = dioula_texte.lexique()
    return {k for k, n in lexique().items()
            if n >= FREQUENT and k not in dy and k not in dioula_texte.AMBIGUS and k not in dioula_texte.EMPRUNTS and len(k) >= 2}


@lru_cache(maxsize=1)
def _propres_dioula():
    """Mots dioula du lexique (au moins 2 apparitions) qui n'existent PAS dans le baoulé : signent le dioula."""
    dy, _ = dioula_texte.lexique()
    b = lexique()
    return {k for k, info in dy.items()
            if (info.get("n", 0) >= 2 or info.get("type") in ("domaine", "grammaire")) and k not in b
            and k not in dioula_texte.AMBIGUS and k not in dioula_texte.EMPRUNTS and len(k) >= 2}


ARTICLE = re.compile(r"\w'[nm]$")          # « sua'n », « ninnge'm » : article défini baoulé
FRANCAIS_ANGLAIS = dioula_texte.FRANCAIS_ANGLAIS


QUESTION_BAOULE = re.compile(r"\s(ɔ|ɔn|o)\s*\?\s*$", re.I)     # « ... ɔ ? » : fin de question baoulé (dioula : « wa ? »)


def signes(texte):
    """(mots qui signent le baoulé, mots qui signent le dioula, nombre de mots) — lettres ɛ ɔ ignorées (communes)."""
    ms = [m for m in mots_de(texte) if not m.isdigit()]
    b = sum(1 for m in ms if ARTICLE.search(m) or cle(m) in _propres())
    d = sum(1 for m in ms if cle(m) in _propres_dioula() and not ARTICLE.search(m))
    if QUESTION_BAOULE.search(apostrophes(texte or "")):
        b += 1
    return b, d, len(ms)


def score_baoule(texte):
    """Part (0 à 1) des mots qui signent le baoulé, moins le français/anglais évident. Renvoie (score, b, d, n)."""
    b, d, n = signes(texte)
    if not n:
        return 0.0, 0, 0, 0
    francais = len(FRANCAIS_ANGLAIS.findall(texte or ""))
    return round(max(0.0, (b - francais) / n), 3), b, d, n


def langue_locale(texte):
    """Baoulé ou dioula (ou None) pour un texte ÉCRIT, d'après les mots propres à chaque langue.
    Renvoie (code, score_baoule, score_dioula)."""
    sb, b, d, n = score_baoule(texte)
    dioula, sd = dioula_texte.est_dioula(texte)
    if n and b > d and sb >= 0.3:
        return "bci", sb, sd
    # message court fait d'une formule baoulé (« Ɛɛ », « Tchɛtchɛ », « Aɲiho », « Yaki ») : c'est du baoulé
    # (mesuré le 29/09/2026 : « Ɛɛ. » et « Tchɛtchɛ. » étaient pris pour du dioula à cause de la lettre ɛ)
    if n and n <= 4 and d == 0 and formules_reconnues(texte) and not dioula_texte.formules_reconnues(texte):
        return "bci", max(sb, 0.5), sd
    if dioula and d >= b:
        return "dyu", sb, sd
    if n and b >= 2 and b > d:
        return "bci", sb, sd
    return None, sb, sd


SEUIL_BAOULE_NET = 0.40          # lecture baoulé seule, conversation déjà en baoulé (dioula réels : p90 = 0,26)


def baoule_net(texte_oreille_baoule):
    """La lecture de l'oreille baoulé seule suffit-elle ? (conversation déjà en baoulé). Renvoie (oui/non, part)."""
    b, d, n = signes(texte_oreille_baoule)
    part = b / n if n else 0.0
    return (n >= 2 and d == 0 and part >= SEUIL_BAOULE_NET), part


def dioula_net(texte_oreille_dioula):
    """La lecture de l'oreille dioula contient des mots propres au dioula (plus que de mots baoulé) : c'est du dioula,
    inutile de faire écouter l'oreille baoulé (~3 s gagnées)."""
    b, d, _ = signes(texte_oreille_dioula)
    return d >= 1 and d >= b


def baoule_ou_dioula(texte_oreille_dioula, texte_oreille_baoule, langue_conversation=None):
    """Un vocal en langue locale : baoulé ou dioula ? On a DEUX lectures du même son :
      - l'oreille dioula (Omnilingual 1B, qui connaît 1 600 langues) écrit à peu près ce qu'elle entend ;
      - l'oreille baoulé (spécialisée) écrit TOUJOURS du baoulé, même sur du dioula : son texte seul ne prouve rien.
    On compte donc les mots propres à chaque langue dans la lecture de l'oreille DIOULA, et on regarde si la lecture
    baoulé ressemble à du vrai baoulé. Seuils réglés sur de vrais vocaux (tests/bancs/baoule_logique/regler_routage.py).
    Renvoie ("bci" | "dyu" | None, raison)."""
    b_d, d_d, n_d = signes(texte_oreille_dioula)
    b_b, _, n_b = signes(texte_oreille_baoule)
    if not n_d and not n_b:
        return None, "rien entendu"
    # mesuré le 30/09/2026 sur 60 vrais vocaux baoulé : AUCUN mot propre au dioula dans leur lecture (p90 = 0) ;
    # à égalité de mots propres, c'est du dioula (7 vocaux dioula passaient en baoulé sur une égalité 1 contre 1)
    if d_d >= 1 and d_d >= b_d:
        return "dyu", f"mots dioula entendus ({d_d} contre {b_d} baoulé)"
    score = (b_b / n_b if n_b else 0.0) + (b_d / n_d if n_d else 0.0)
    seuil = (SEUIL_SANS_DIOULA if d_d == 0 else SEUIL_SCORE_BAOULE) - (BONUS_CONVERSATION if langue_conversation == "bci" else 0.0)
    if score >= seuil:
        return "bci", f"mots baoulé entendus (score {score:.2f}, seuil {seuil:.2f})"
    return None, f"indécis (score baoulé {score:.2f}, mots dioula {d_d})"


# Réglés le 30/09/2026 sur 169 vrais vocaux (tests/bancs/baoule_logique/regler_regle.py) : 1er message baoulé 98 %, dioula 95 %,
# français 88 % (les 2 ratés : un bruit et une seule lettre), anglais 100 %.
SEUIL_SCORE_BAOULE = 0.50        # des mots dioula entendus aussi : il faut beaucoup d'indices baoulé
SEUIL_SANS_DIOULA = 0.25         # aucun mot dioula entendu : un peu moins d'indices baoulé suffisent
BONUS_CONVERSATION = 0.15        # conversation déjà en baoulé : seuils abaissés d'autant


# ── Chiffres baoulé ────────────────────────────────────────────────────────────
def _nk(mot):
    """Clé des chiffres : comme cle() mais SANS fusionner les lettres doublées (« nnun » = 5, « nun » = dans)."""
    t = unicodedata.normalize("NFC", apostrophes(mot).lower()).replace("tʃ", "tc")
    t = t.replace("ɛ", "e").replace("ɔ", "o").replace("ɲ", "ny").replace("ŋ", "ng")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


UNITES = {1: ["kun", "koun", "kou"], 2: ["nnyon", "ngnon", "nnon"], 3: ["nsan"], 4: ["nnan"],
          5: ["nnun", "nnu", "nnou"], 6: ["nsien", "nsie", "nsin"], 7: ["nso"], 8: ["mocue", "motcue", "mokue", "ntcue"],
          9: ["nguele", "ngwlan", "ngwele", "nguelan"], 10: ["blu"]}
_U = {v: k for k, l in UNITES.items() for v in l}
# après « ni » / « nin » (= « et »), les formes courtes sont sûres : « abla nin nun » = 25 (« nun » seul = « dans »)
_U_APRES = {**_U, "nyon": 2, "san": 3, "nan": 4, "nun": 5, "sien": 6, "so": 7}
ET = ("ni", "nin")
# dizaines : « abla » (20) ; « abla + chiffre » = ce chiffre × 10 (« ablasan » / « abla nsan » = 30, « ablanun » = 50)
RACINES_DIZAINES = {"san": 3, "nsan": 3, "nan": 4, "nnan": 4, "nun": 5, "nnun": 5, "sien": 6, "nsien": 6, "so": 7, "nso": 7,
                    "mocue": 8, "motcue": 8, "nguele": 9, "ngwlan": 9, "cen": 3}
MULTIPLES = {"ya": 100, "yakun": 100, "akpi": 1000, "milion": 1_000_000, "miliyon": 1_000_000}


def _petit(ks, j, apres_et=False):
    """Nombre de 1 à 99 à partir de ks[j]. Renvoie (valeur, nb de mots lus) ou (None, 0)."""
    if j >= len(ks):
        return None, 0
    k = ks[j]
    unites = _U_APRES if apres_et else _U
    if k in unites:
        return unites[k], 1
    if k.startswith("abla") or k.startswith("ablo"):
        reste = k[4:]
        if reste in RACINES_DIZAINES:
            return 10 * RACINES_DIZAINES[reste], 1
        if reste in ("", "on", "n"):                     # « abla », « ablã », « ablaɔn » = 20
            if j + 1 < len(ks) and ks[j + 1] in _U and 3 <= _U[ks[j + 1]] <= 9:
                return 10 * _U[ks[j + 1]], 2
            return 20, 1
    return None, 0


def _groupe(ks, i, apres_et=False):
    """Un groupe sans « ni » : chiffre/dizaine (« nsan », « abla »), ou multiple suivi de son facteur (« ya nsan » = 300,
    « akpi blu » = 10 000, « akpi ya kun » = 100 000). Renvoie (valeur, nb de mots) ou (None, 0)."""
    k = ks[i] if i < len(ks) else ""
    if k in MULTIPLES:
        m = MULTIPLES[k]
        v, n = _groupe(ks, i + 1) if i + 1 < len(ks) else (None, 0)
        if v is not None and v < m:
            return m * v, 1 + n
        return m, 1
    return _petit(ks, i, apres_et)


def _nombre(ks, i, apres_et=False):
    """Lit un nombre à partir de ks[i] : « blu ni kun » (11), « abla ni nnun » (25), « ya nsan » (300).
    Le multiple ne s'applique qu'au groupe qui le suit, « ni » AJOUTE : « akpi nnyon ni nnyon » = 2 002 (vu dans les vrais
    textes WAXAL ; Google écrit « akpi ablaɔn-nin-nun » pour 25 000, qu'on lit donc 20 005 : un nombre relu n'est
    qu'un indice, DeepSeek le fait confirmer)."""
    v, n = _groupe(ks, i, apres_et)
    if v is None:
        return None, 0
    total, j = v, i + n
    while j + 1 < len(ks) and ks[j] in ET:                    # « ... ni X » : on ajoute
        v, n = _nombre(ks, j + 1, apres_et=True)
        if v is None or v >= total:
            break
        total, j = total + v, j + 1 + n
    return total, j - i


def lire_nombres(texte):
    """Nombres dits en baoulé (et chiffres écrits) : [{"texte", "valeur"}]. Mots seuls trop ambigus ignorés
    (« kun » = un, mais aussi « un certain » ; « ya » = cent, mais aussi « mal »)."""
    mots = mots_de(texte)
    ks = [_nk(m) for m in mots]
    trouves, i = [], 0
    while i < len(ks):
        if mots[i].isdigit():
            trouves.append({"texte": mots[i], "valeur": int(mots[i])}); i += 1; continue
        v, n = _nombre(ks, i)
        if v is not None and n > 0:
            if n == 1 and ks[i] in ("kun", "koun", "kou", "ya", "blu", "abla"):
                i += 1; continue
            trouves.append({"texte": " ".join(mots[i:i + n]), "valeur": v}); i += n
        else:
            i += 1
    return trouves


# ── Formules et glossaire (indices pour DeepSeek, à faire valider par un locuteur) ─
FORMULES = [  # (formule, sens)
    ("ɛɛn", "oui"), ("ɛɛ", "oui"), ("ɔɔ", "oui"), ("cɛcɛ", "non"), ("tchɛtchɛ", "non"),
    ("amu kula", "merci"), ("n yo wɔ kula", "merci beaucoup"), ("aɲiho", "bonjour"), ("awossi o", "bonsoir"),
    # salutations de l'heure (N'Zi 2024, N'Guessan 2023 : voir chatbot/salutations.py) : matin / mi-journée / soir
    ("arɛ o", "bonjour (réponse à un bonjour du matin)"), ("manti", "bonjour (de 11 h à 17 h)"),
    ("aanti o", "bonjour (réponse, de 11 h à 17 h)"), ("mo wonti", "bon après-midi"), ("anun o", "bonsoir (dit en premier)"),
    ("e ti su", "d'accord"), ("ɔ ti su", "d'accord, c'est bon"), ("eti kpa", "c'est bien, d'accord (accord, pas une salutation)"), ("yaki", "pardon, désolé"), ("n kpata wɔ", "s'il vous plaît"),
    ("n wunmɛn i wlɛ", "je n'ai pas compris"), ("n kunndɛ kɛ", "je veux"), ("n kunndɛman kɛ", "je ne veux pas"),
    ("amun kunndɛ kɛ", "voulez-vous (question)"), ("ye tɛ wo nu", "au revoir"),
    # donné par un locuteur (le client) le 05/10/2026 : c'est une QUESTION, pas une demande de couper le courant
    ("yo kuran yafɔsɛ", "« le courant est monté ? » (QUESTION de la personne : ce n'est PAS une demande de couper le courant)"),
    ("kuran yafɔsɛ", "« le courant est monté ? » (QUESTION de la personne : ce n'est PAS une demande de couper le courant)"),
]
GLOSSAIRE = {
    "kuran": "électricité, courant", "sika": "argent (en Côte d'Ivoire : francs CFA, JAMAIS des dollars)",
    "kalɛ": "crédit, dette, facture", "mɛtɛri": "compteur", "kannin": "lumière, éclairage, lampe", "kpaja": "allumer, s'allumer",
    "kaci": "changer, tourner (« kaci ... kannin'n » = allumer la lumière)", "nunnun": "éteindre, couper (un appareil)",
    "kpɛ": "couper", "kplɛ": "couper", "yaci": "laisser (« yaci i » = laisse-le)", "ekun": "de nouveau (remettre en marche)",
    "wie": "finir, s'épuiser (« kuran'n w'a wie » = il n'y a plus de courant)", "tua": "payer", "to": "acheter, payer",
    "fa ... man": "donner", "sua": "maison, pièce", "awlo": "maison, chez soi", "frigo": "réfrigérateur",
    "frigidɛr": "réfrigérateur", "televiziɔn": "télévision", "blalɛ": "fer à repasser", "klimatizɛ": "climatiseur",
    "ventilatɛ": "ventilateur", "ventilatɛri": "ventilateur", "aparɛti": "appareil", "motɛri": "appareil, machine",
    "di aliɛ": "consommer (mot à mot : manger)", "dili aliɛ": "consommer (mot à mot : manger)",
    "aliɛ dilɛ": "consommation (mot à mot : le fait de manger)", "nɲɛ": "combien", "n'gnɛ": "combien", "benin": "quel, lequel",
    "n'zu": "quoi", "ngue ti": "pourquoi", "wafa sɛ": "comment", "wan": "qui", "blɛ benin": "quand",
    "kwla": "pouvoir", "fata": "falloir, devoir", "kunndɛ": "vouloir", "uka": "aider", "andɛ": "aujourd'hui",
    "annunman": "hier", "ayinman": "demain", "anglo": "mois", "le mɔcuɛ": "semaine", "kɔnguɛ": "nuit", "do": "chaleur",
    "kpa": "bien ; beaucoup", "kpanngban": "beaucoup", "dan": "grand, beaucoup", "ndɛndɛ": "vite",
    "sran": "personne", "ninnge": "chose(s)", "lika": "endroit", "junman": "travail, fonctionner", "bubulɛ": "panne",
    "yafɔsɛ": "monter (« kuran yafɔsɛ » = le courant est monté ; en question : « le courant est monté ? »)",
    "yafɔsuɛ": "monter (« kuran yafɔsɛ » = le courant est monté ; en question : « le courant est monté ? »)",
    "man": "NÉGATION collée au verbe (« kunndɛman » = ne veut pas, « diman junman » = ne fonctionne pas)",
}
_FORM = [(cle(f.replace(" ", "")), f, s) for f, s in FORMULES]
_GLOSS = {cle(k.replace(" ", "")): (k, v) for k, v in GLOSSAIRE.items()}
OUI_NON = {k for k, f, s in _FORM if s in ("oui", "non")}


def formules_reconnues(texte):
    """Formules baoulé courantes présentes dans le texte (même collées).
    Oui/non : mot EXACT, lettres doublées comprises (« ɛɛ » = oui, mais « e » = nous : « E ti su » n'est pas un oui)."""
    mots = mots_de(texte)
    ks = [cle(m) for m in mots]
    exacts = {_nk(m) for m in mots}
    trouvees, vues = [], set()
    for k, f, s in _FORM:
        if s in vues:
            continue
        if s in ("oui", "non"):
            if _nk(f) in exacts:
                trouvees.append((f, s)); vues.add(s)
            continue
        n = len(f.split())
        for i in range(len(ks)):
            bloc = "".join(ks[i:i + n])
            tol = 0 if len(k) <= 5 else 1
            if bloc and abs(len(bloc) - len(k)) <= tol and dioula_texte._distance(bloc, k) <= tol:
                trouvees.append((f, s)); vues.add(s)
                break
    return trouvees


def sans_article(mot):
    """« mɛtɛri'n » (le compteur) -> « mɛtɛri » : l'article défini collé cache sinon le mot du glossaire."""
    return re.sub(r"'[nm]$", "", mot)


def lexique_utile(*textes, maximum=30):
    """Mots du glossaire présents dans les textes (avec leur sens) : donné à DeepSeek."""
    vus = {}
    for t in textes:
        ms = [sans_article(m) for m in mots_de(t)]
        for i, m in enumerate(ms):
            for k in (cle(m), cle(m + (ms[i + 1] if i + 1 < len(ms) else ""))):
                if k in _GLOSS:
                    vus.setdefault(_GLOSS[k][0], _GLOSS[k][1])
    return dict(list(vus.items())[:maximum])


def reparer(ecoute):
    """Écoute baoulé -> (texte, réparations). 06/10/2026 : réparation CONTRÔLÉE PAR LE SON avec le carnet de mots de
    sources libres (baoule_reparation) ; avant, simple nettoyage (lexique trop petit). Même forme que dioula_texte.reparer."""
    from . import baoule_reparation
    texte, faits = baoule_reparation.reparer(ecoute)
    return re.sub(r"\s+", " ", texte).strip(), faits


# ── Phrases de RÉFÉRENCE (05/10/2026, demande du client) ─────────────────────────
# Une quinzaine de questions AOCEDA en baoulé dont le sens est connu (chatbot/donnees/phrases_reference_baoule.json) : la
# plus proche du message entendu est donnée à DeepSeek comme INDICE. Seuil mesuré : une phrase de la banque abîmée comme
# par l'écoute (un mot en moins, deux lettres fausses) ressemble à 0,76-0,96 ; de vraies phrases hors banque à 0,67 au plus.
FICHIER_REFERENCES = DONNEES / "phrases_reference_baoule.json"
SEUIL_PHRASE = 0.72


@lru_cache(maxsize=1)
def _references():
    try:
        return [(p, [cle(sans_article(m)) for m in mots_de(p["bci"])])
                for p in json.loads(FICHIER_REFERENCES.read_text(encoding="utf-8"))["phrases"]]
    except (OSError, ValueError, KeyError):
        return []


def phrase_proche(texte, seuil=SEUIL_PHRASE):
    """Phrase de référence la plus proche du message : (phrase, ressemblance 0-1) ou None (sous le seuil, ou message
    d'un seul mot : trop court pour trancher)."""
    m1 = [cle(sans_article(m)) for m in mots_de(texte)]
    if len(m1) < 2:
        return None
    a, meilleure = "".join(m1), None
    for p, m2 in _references():
        r = max(SequenceMatcher(None, a, "".join(m2)).ratio(), len(set(m1) & set(m2)) / max(1, len(set(m1) | set(m2))))
        if meilleure is None or r > meilleure[1]:
            meilleure = (p, r)
    return meilleure if meilleure and meilleure[1] >= seuil else None
