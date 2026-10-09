"""Texte DIOULA : reconnaître du dioula, réparer ce que l'écoute a mal découpé ou déformé, lire les chiffres.

Pourquoi (mesuré sur le banc du 29/09/2026) : Omnilingual entend bien les SONS, mais
  - il colle ou coupe les mots (« filatora » pour « fila tora », « kumanfakitiri » pour « kuran fakitiri ») ;
  - il déforme parfois les mots qui portent le sens (« kuran » -> « kuman », « compteur » -> « conté ») ;
  - il n'a aucune idée de la langue parlée.
Chaque réparation est prudente :
  - on ne corrige que vers un mot du lexique (lexique construit SANS les phrases de test) ;
  - la correction doit rester compatible avec le SON (« preuve sonore » : l'audio colle presque aussi bien au mot
    corrigé qu'au mot entendu) ; sinon on garde le mot entendu.
"""
import json
import re
import unicodedata
from functools import lru_cache

from .config import DONNEES

FICHIER_LEXIQUE = DONNEES / "dioula_lexique.json"
MARGE_SONORE = 4.0          # une correction est refusée si l'audio colle beaucoup moins bien (écart de log-probabilité)
MARGE_COUPURE = 6.0         # idem pour ajouter un espace (le modèle « dit » les espaces, mais faiblement)

# Mots très fréquents en français / anglais / espagnol / portugais qui existent aussi en dioula (« a », « la »...) :
# ils ne comptent pas pour décider qu'un texte est du dioula.
AMBIGUS = set("""a an de la le ne o on en me mi no so se si e i in is it of or do to be we he y el lo es
con por una uno que un une et est pas pour qui dans sur au aux ce il elle je tu nous vous mon ma mes ton ta sa son ses
the and are was you they des les du avec sans par vers chez plus tres bien mais ou donc car si cette ces leur
leurs notre nos votre vos lui eux quand comme tout tous toute fait faire etre avoir peut dois""".split())
# Mots français que les gens glissent tels quels dans le dioula : utiles au sens, mais ne prouvent pas que c'est du dioula.
# (le lexique récolté dans des traductions contient aussi des mots français restés tels quels : « salon », « du »...)
EMPRUNTS = set("""courant facture credit compteur recharger recharge climatiseur clim frigo congelateur ventilateur tele
lampe ampoule cie code carte cash francs kilowatt mois semaine salon chambre cuisine radio moto telephone television
machine fer maison argent orange money wave abidjan""".split())
# Pluriel dioula en -w (mɔgɔw, polisiw, baaraw) : signe fort, sauf ces mots anglais.
ANGLAIS_EN_W = set("now how new few know show law view allow below follow window yellow tomorrow draw low throw grow slow "
                   "flow saw raw blow snow knew drew grew threw".split())


def cle(mot):
    """Forme de comparaison d'un mot : sans tons ni accents, ɛ->e, ɔ->o, ɲ->ny, ŋ->ng, lettres doublées fusionnées."""
    t = unicodedata.normalize("NFC", (mot or "").lower()).replace("’", "'").replace("ʼ", "'")
    t = t.replace("ɛ", "e").replace("ɔ", "o").replace("ɲ", "ny").replace("ŋ", "ng")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]", "", t)
    return re.sub(r"(.)\1+", r"\1", t)


@lru_cache(maxsize=1)
def lexique():
    """{clé: {"mot", "n", "type", "sens"?}} ; les mots de plusieurs mots (« kilowati lɛrɛ ») à part."""
    d = json.loads(FICHIER_LEXIQUE.read_text(encoding="utf-8"))["mots"]
    simples, composes = {}, {}
    for mot, info in d.items():
        k = cle(mot)
        if not k:
            continue
        cible = composes if " " in mot.strip() else simples
        if k not in cible or info.get("type") == "domaine":
            cible[k] = {"mot": mot, **info}
    return simples, composes


def connu(mot, n_min=1):
    s, _ = lexique()
    i = s.get(cle(mot))
    return bool(i) and (i["n"] >= n_min or i["type"] in ("domaine", "grammaire"))


# ── Est-ce du dioula ? ─────────────────────────────────────────────────────────
LETTRES_MANDING = re.compile(r"[ɛɔɲŋƐƆƝŊ]")
FRANCAIS_ANGLAIS = re.compile(r"\b(je|tu|il|nous|vous|est|suis|pas|mon|mes|votre|quel|comment|pourquoi|merci|bonjour|"
                              r"oui|non|d'accord|the|is|are|my|what|how|why|please|thank|yes|hello|this|that|el|mi|"
                              r"que|como|por|obrigado|gracias)\b", re.I)


def score_dioula(texte):
    """Part (0 à 1) des mots qui signent le dioula : mot dioula connu (hors mots ambigus) ou lettre ɛ ɔ ɲ ŋ.
    Renvoie (score, nb_mots_signes, nb_mots)."""
    mots = [m for m in re.findall(r"[\wɛɔɲŋ'’-]+", (texte or "").lower()) if not m.isdigit()]
    if not mots:
        return 0.0, 0, 0
    s, _ = lexique()
    signes = 0
    for m in mots:
        k = cle(m)
        info = s.get(k)
        if LETTRES_MANDING.search(m):
            signes += 1
        elif info and k not in AMBIGUS and k not in EMPRUNTS:
            signes += 1
        elif len(k) >= 4 and k.endswith("w") and k not in ANGLAIS_EN_W:     # pluriel dioula (mɔgɔw, polisiw)
            signes += 1
    francais = len(FRANCAIS_ANGLAIS.findall(texte or ""))
    score = max(0.0, (signes - francais) / len(mots))
    return round(score, 3), signes, len(mots)


def est_dioula(texte, seuil=0.34):
    """Décision texte : au moins un tiers des mots signent le dioula (et pas de français/anglais évident)."""
    score, signes, n = score_dioula(texte)
    return score >= seuil and signes >= 1, score


# ── Réparations (sur le résultat d'une écoute) ─────────────────────────────────
DEBUT_PRONOM = [(re.compile(r"^m(?=b|p)"), "n"), (re.compile(r"^ŋ(?=g|k)"), "n"), (re.compile(r"^ŋ(?=b)"), "n")]


def _distance(a, b):
    """Distance d'édition entre deux clés, confusions de sons proches (m/n/r, b/p, d/t, g/k) comptées moitié."""
    proches = {frozenset(p) for p in ("mn", "nr", "mr", "rl", "bp", "dt", "gk", "ei", "ou", "eo", "fv", "bw")}
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prec, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            cout = 0 if x == y else (0.5 if frozenset((x, y)) in proches else 1)
            prec, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prec + cout)
    return d[-1]


@lru_cache(maxsize=1)
def _index_longueurs():
    """Mots du lexique rangés par longueur : on ne compare un mot qu'aux mots de longueur voisine (±2)."""
    s, _ = lexique()
    domaine, ordinaires = {}, {}
    for kk, info in s.items():
        if info["type"] == "domaine" and len(kk) >= 4:
            domaine.setdefault(len(kk), []).append((kk, info["mot"]))
        elif info["type"] != "domaine" and info["n"] >= 3 and len(kk) >= 3:
            ordinaires.setdefault(len(kk), []).append(kk)
    return domaine, ordinaires


@lru_cache(maxsize=8192)
def _candidat_domaine(mot):
    """Mot AOCEDA le plus proche d'un mot inconnu (ou None). Tolérance selon la longueur.
    Refusé si un mot ordinaire du lexique est aussi proche (« caama » n'est pas « tama »). Résultat mémorisé."""
    k = cle(mot)
    if len(k) < 4 or k in lexique()[0]:
        return None
    domaine, ordinaires = _index_longueurs()
    meilleur, dist = None, 99
    for n in range(len(k) - 2, len(k) + 3):
        for kk, forme in domaine.get(n, ()):
            d = _distance(k, kk)
            if d < dist:
                meilleur, dist = forme, d
    limite = 1.0 if len(k) <= 5 else 1.5 if len(k) <= 8 else 2.0
    if meilleur is None or dist > limite:
        return None
    for n in range(len(k) - 2, len(k) + 3):
        if any(_distance(k, kk) <= dist for kk in ordinaires.get(n, ())):
            return None
    return meilleur


SUFFIXES = ("ra", "la", "na", "len", "lan", "nen", "nin", "ya", "w", "ba", "li", "ni", "baa", "ta", "tɔ", "to")
PARTICULES = {cle(x) for x in """ka ye wa bɛ be tɛ te fɛ fe ne an le la na ni ko di lo ma se ta kɔ ko yen kan dɔ bi
aw""".split()}


def flechi(mot):
    """Mot connu + suffixe dioula (« sɔrɔra » = sɔrɔ + ra, « kɔnɔmaya » = kɔnɔma + ya) : c'est un vrai mot, on n'y touche pas."""
    k = cle(mot)
    for suf in SUFFIXES:
        ks = cle(suf)
        if len(k) > len(ks) + 1 and k.endswith(ks) and connu(k[: -len(ks)], 2):
            return True
    return False


def _morceau_ok(x):
    """Un morceau de découpage : mot connu d'au moins 3 lettres, ou particule de grammaire de 1-2 lettres."""
    k = cle(x)
    return (len(k) >= 3 and connu(x, 2)) or k in PARTICULES


def _decoupages(mot):
    """Découpages possibles d'un mot collé en 2 mots (« filatora » -> « fila tora »), du plus sûr au moins sûr.
    Un morceau inconnu est permis s'il est proche d'un mot AOCEDA (« kumanfakitiri » -> « kuman » + « fakitiri »)."""
    out = []
    for i in range(1, len(mot)):
        a, b = mot[:i], mot[i:]
        if _morceau_ok(a) and _morceau_ok(b):
            out.append([a, b])
        elif len(a) >= 4 and _morceau_ok(b) and cle(b) not in PARTICULES and _candidat_domaine(a):
            out.append([a, b])
        elif len(b) >= 4 and _morceau_ok(a) and cle(a) not in PARTICULES and _candidat_domaine(b):
            out.append([a, b])
    out.sort(key=lambda p: -min(len(cle(x)) for x in p))
    return out


def reparer(ecoute):
    """Renvoie (texte_repare, liste des réparations) à partir d'un objet dioula_ecoute.Ecoute.
    Réparations tentées, dans l'ordre, pour chaque mot inconnu du lexique :
      1. pronom collé : « mbafe » -> « n bafe », « ŋga » -> « n ga » (le n se prononce m devant b, ŋ devant g/k) ;
      2. mot collé : « filatora » -> « fila tora » si l'audio accepte l'espace ;
      3. mot AOCEDA déformé : « kuman » -> « kuran » si l'audio accepte le mot corrigé."""
    sortie, faits = [], []
    for m in ecoute.mots:
        mot, t0, t1 = m["mot"], m["t0"] - 3, m["t1"] + 3
        if connu(mot) or flechi(mot) or len(mot) < 3 or not mot.isalpha() and "'" not in mot:
            sortie.append(mot); continue
        base = ecoute.score_sonore(mot, t0, t1)
        remplace, ecart = None, None
        for motif, pronom in DEBUT_PRONOM:                   # 1. pronom collé
            if motif.search(mot):
                reste = motif.sub("", mot)
                if len(reste) >= 2 and (connu(reste) or reste.startswith(("b'", "ba", "be", "bɛ", "ka", "ga"))):
                    remplace = f"{pronom} {reste}"
                break
        if remplace is None:
            for morceaux in _decoupages(mot):                # 2. mot collé
                essai = " ".join(morceaux)
                s = ecoute.score_sonore(essai, t0, t1)
                if s is not None and base is not None and s >= base - MARGE_COUPURE:
                    remplace, ecart = essai, round(s - base, 2)
                    break
        if remplace is None or not all(connu(x) for x in remplace.split()):
            morceaux = (remplace or mot).split()
            corriges = []
            for x in morceaux:                               # 3. mot AOCEDA déformé
                c = _candidat_domaine(x) if not connu(x) else None
                corriges.append(c or x)
            if corriges != morceaux:
                essai = " ".join(corriges)
                s = ecoute.score_sonore(essai, t0, t1)
                if s is not None and base is not None and s >= base - MARGE_SONORE:
                    remplace, ecart = essai, round(s - base, 2)
        if remplace and remplace != mot:
            faits.append({"entendu": mot, "repare": remplace, "ecart_sonore": ecart})
            sortie.append(remplace)
        else:
            sortie.append(mot)
    return " ".join(sortie), faits


# ── Chiffres dioula ────────────────────────────────────────────────────────────
UNITES = {"kelen": 1, "kele": 1, "fila": 2, "fla": 2, "fla ": 2, "saba": 3, "naani": 4, "nani": 4, "duuru": 5, "duru": 5,
          "woro": 6, "wɔɔrɔ": 6, "wolonwula": 7, "wolonfila": 7, "seegin": 8, "segin": 8, "sɛgin": 8, "konnonton": 9,
          "kɔnɔntɔn": 9, "kononton": 9}
DIZAINES = {"tan": 10, "mugan": 20, "muwan": 20}
MULTIPLES = {"keme": 100, "kɛmɛ": 100, "waa": 1000, "wa": 1000, "ba": 1000, "milyon": 1_000_000, "miliyɔn": 1_000_000}
_U = {cle(k): v for k, v in UNITES.items()}
_D = {cle(k): v for k, v in DIZAINES.items()}
_M = {cle(k): v for k, v in MULTIPLES.items()}


def _nombre_depuis(mots, i):
    """Lit un nombre dioula à partir de mots[i]. Renvoie (valeur, nb_mots_lus) ou (None, 0).
    Formes : « tan ni fila » (12), « bi naani ni fila » (42), « kɛmɛ fila » (200), « waa duuru » (5 000)."""
    def petit(j):                                         # 1 à 99
        k = cle(mots[j]) if j < len(mots) else ""
        if k in _U:
            return _U[k], 1
        if k in _D:
            v, n = _D[k], 1
        elif k in ("bi", "bin") and j + 1 < len(mots) and cle(mots[j + 1]) in _U:
            v, n = 10 * _U[cle(mots[j + 1])], 2
        else:
            return None, 0
        if j + n + 1 < len(mots) and cle(mots[j + n]) == "ni" and cle(mots[j + n + 1]) in _U:
            v, n = v + _U[cle(mots[j + n + 1])], n + 2
        return v, n

    total, j = None, i
    k = cle(mots[j]) if j < len(mots) else ""
    if k in _M and j + 1 < len(mots):                     # « kɛmɛ fila » = 200, « waa duuru » = 5 000
        v, n = petit(j + 1)
        if v is None:                                     # après « waa », un chiffre mal entendu (« duu ») reste lisible
            kk = cle(mots[j + 1])
            proches = [u for uk, u in _U.items() if len(kk) >= 2 and (uk.startswith(kk) or _distance(kk, uk) <= 1)]
            if len(set(proches)) != 1:
                return None, 0
            v, n = proches[0], 1
        total, j = _M[k] * v, j + 1 + n
    else:
        v, n = petit(j)
        if v is None:
            return None, 0
        total, j = v, j + n
    while j + 1 < len(mots) and cle(mots[j]) == "ni":       # « ... ni tan » : on ajoute
        v, n = _nombre_depuis(mots, j + 1)
        if v is None:
            break
        total, j = total + v, j + 1 + n
    return total, j - i


def lire_nombres(texte):
    """Nombres dits en dioula (et chiffres écrits) : [{"texte", "valeur", "unite"}]. « dɔrɔmɛ » = 5 F CFA."""
    mots = re.findall(r"[\wɛɔɲŋ'’]+", texte or "")
    trouves, i = [], 0
    while i < len(mots):
        if mots[i].isdigit():
            trouves.append({"texte": mots[i], "valeur": int(mots[i])}); i += 1; continue
        if cle(mots[i]) in ("bi", "bin", "ni") and not (cle(mots[i]) in ("bi", "bin") and i + 1 < len(mots)
                                                        and cle(mots[i + 1]) in _U):
            i += 1; continue
        v, n = _nombre_depuis(mots, i)
        if v is not None and n > 0:
            if n == 1 and cle(mots[i]) in ("ba", "wa", "tan") :     # mots trop ambigus seuls
                i += 1; continue
            t = {"texte": " ".join(mots[i:i + n]), "valeur": v}
            suite = cle(mots[i + n]) if i + n < len(mots) else ""
            avant = cle(mots[i - 1]) if i > 0 else ""
            if suite in ("dorome", "tama") or avant in ("dorome", "tama"):
                t.update({"valeur_fcfa": v * 5, "unite": "dɔrɔmɛ (×5 F CFA)"})
            trouves.append(t); i += n
        else:
            i += 1
    return trouves


# ── Glossaire et formules (donnés à DeepSeek : il ne connaît pas bien le dioula) ─
# Mesuré le 29/09/2026 : sans eux, « i ni ce kosɔbɛ » (merci beaucoup) était compris « bonjour », et
# « 42 kilowattheures tora n fɛ » (il me RESTE 42) était compris comme une question.
GLOSSAIRE = {
    "hakɛ": "quantité, montant (hakɛ jumɛn = combien)", "joli": "combien", "jumɛn": "quel, lequel", "juman": "quel",
    "mun": "quoi", "mun na": "pourquoi", "cogo di": "comment", "tuma jumɛn": "quand", "yala": "est-ce que (ouvre une question)",
    "wa": "EN FIN DE PHRASE : marque une question oui/non", "tora": "reste, est resté (« X tora n fɛ » = il me reste X, affirmation)",
    "san": "acheter", "sara": "payer", "kɛ": "faire", "taa": "aller", "dɔn": "savoir, connaître", "b'a fɛ": "vouloir (n b'a fɛ = je veux)",
    "se": "pouvoir (bɛ se ka = peut)", "dun": "manger, consommer", "dumu": "manger, consommer", "dumuni": "nourriture, consommation",
    "caman": "beaucoup", "caaman": "beaucoup", "ca": "être nombreux, être élevé", "kosɛbɛ": "beaucoup, très", "dɔɔni": "un peu",
    "kalo": "mois", "dɔgɔkun": "semaine", "tile": "jour", "kunun": "hier", "sini": "demain", "su": "nuit, soir",
    "sufɛ": "la nuit", "sɔgɔma": "matin", "so": "maison", "soo": "maison", "sibon": "chambre", "kɔnɔ": "dans, à l'intérieur",
    "kɛnɛma": "dehors", "tɛ": "ne ... pas (négation)", "ma": "ne ... pas (au passé)", "ye": "a fait (passé) ; est",
    "n ka": "mon, ma ; « i ka + verbe » = fais (ordre)", "aw ye": "EN DÉBUT DE PHRASE + verbe : ordre poli (« aw ye X faga » = éteignez X)",
    "i ka": "ton, ta ; « i ka + verbe » = fais (ordre)", "a ka": "son, sa", "an": "nous", "aw": "vous", "u": "ils, elles",
    "fɛ": "chez, auprès de", "bolo": "en possession de", "dɛmɛ": "aider", "sɔngɔ": "prix", "gɛlɛn": "difficile, cher",
    "kura": "nouveau", "baara": "travail ; fonctionner", "tiɲɛna": "est en panne, s'est abîmé", "funteni": "chaleur",
    "sumaya": "fraîcheur", "nɛnɛ": "froid", "faamu": "comprendre",
}
FORMULES = [  # (formule, sens) ; reconnues même mal entendues (« ini ke kuso be » = i ni ce kosɔbɛ)
    ("i ni ce", "merci (formule de politesse ; parfois salutation)"), ("aw ni ce", "merci (à plusieurs)"),
    ("i ni sɔgɔma", "bonjour (le matin)"), ("i ni tile", "bonjour (la journée)"),
    ("i ni wula", "bonsoir"), ("i ni su", "bonsoir, bonne nuit"), ("hɛrɛ sira wa", "as-tu bien dormi ? (salutation)"),
    ("aw ni sɔgɔma", "bonjour (à plusieurs, le matin)"), ("aw ni tile", "bonjour (à plusieurs, la journée)"),
    ("aw ni wula", "bonsoir (à plusieurs)"), ("aw ni su", "bonsoir (à plusieurs, la nuit)"),
    ("i ka kɛnɛ wa", "tu vas bien ? (salutation)"), ("tɔɔrɔ si tɛ", "pas de problème, ça va"), ("hɛrɛ tɛ", "ça ne va pas"),
    ("kosɛbɛ", "beaucoup, très"), ("ɔnhɔn", "oui"), ("awɔ", "oui"), ("ɔwɔ", "oui"), ("ɔn ɔn", "non"), ("ayi", "non"),
    ("a tigɛ", "coupe-le"), ("a faga", "éteins-le"), ("a mana", "allume-le"), ("a mɛnɛ", "allume-le"), ("a to yen", "laisse-le"),
    ("a to", "laisse-le"), ("a ka di", "c'est bien, d'accord"), ("i ni baara", "merci pour le travail, bon courage"),
    ("hakɛ to", "pardon, excusez-moi"), ("sabali", "pardon, patience"), ("n ma a faamu", "je n'ai pas compris"),
    ("n b'a fɛ", "je veux"), ("n tɛ a fɛ", "je ne veux pas"),
]


def _proche_dans(cles_mots, cle_formule, nb_mots_formule):
    """La formule apparaît-elle (à peu près) dans le texte, en commençant et finissant sur des limites de mots ?
    Les mots peuvent être collés ou coupés autrement (« ini ke » = « i ni ce »). Tolérance selon la longueur."""
    n = len(cle_formule)
    tol = 0 if (n <= 4 or cle_formule in OUI_NON) else 1 if n <= 8 else 2   # oui/non : exacts (« ɔn ɔn » n'est pas « ɔnhɔn »)
    for i in range(len(cles_mots)):
        bloc = ""
        for j in range(i, min(len(cles_mots), i + nb_mots_formule + 2)):
            bloc = re.sub(r"(.)\1+", r"\1", bloc + cles_mots[j])     # lettres doublées au recollage (« ni iche »)
            if len(bloc) > n + tol:
                break
            debut_ok = bloc[0] == cle_formule[0] or {bloc[0], cle_formule[0]} <= {"m", "n"}   # n se dit m devant b
            if debut_ok and abs(len(bloc) - n) <= tol and _distance(bloc, cle_formule) <= tol:
                return True
    return False


def formules_reconnues(texte):
    """Formules dioula courantes présentes dans le texte (même mal entendues ou collées)."""
    cles_mots = [cle(m) for m in re.findall(r"[\wɛɔɲŋ'’]+", (texte or "").lower())]
    cles_mots = [k for k in cles_mots if k]
    trouvees, vues = [], set()
    for formule, sens in FORMULES:
        k = cle(formule.replace(" ", ""))
        if sens not in vues and _proche_dans(cles_mots, k, len(formule.split())):
            trouvees.append((formule, sens)); vues.add(sens)
    return trouvees


_GLOSS = {cle(k.replace(" ", "")): (k, v) for k, v in GLOSSAIRE.items()}
OUI_NON = {cle(f.replace(" ", "")) for f, sens in FORMULES if sens in ("oui", "non")}


# ── Lexique pour DeepSeek ──────────────────────────────────────────────────────
def lexique_utile(*textes, maximum=30):
    """Mots AOCEDA et mots courants présents (ou presque) dans les textes, avec leur sens : donné à DeepSeek."""
    s, comp = lexique()
    vus = {}
    for t in textes:
        mots = re.findall(r"[\wɛɔɲŋ'’]+", (t or "").lower())
        for i, m in enumerate(mots):
            for k in (cle(m), cle(m + (mots[i + 1] if i + 1 < len(mots) else ""))):
                info = s.get(k) or comp.get(k)
                if info and info["type"] == "domaine" and "sens" in info:
                    vus[info["mot"]] = info["sens"]
                elif k in _GLOSS:
                    vus.setdefault(_GLOSS[k][0], _GLOSS[k][1])
            c = _candidat_domaine(m)
            if c and "sens" in s[cle(c)]:
                vus.setdefault(c, s[cle(c)]["sens"] + f" (entendu « {m} »)")
    return dict(list(vus.items())[:maximum])
