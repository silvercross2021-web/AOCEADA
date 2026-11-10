"""Texte WOLOF : reconnaître du wolof (face au français, dioula et baoulé),
normalisation phonétique pour le TTS, lecture des chiffres, formules et glossaire.

Capitalisé sur le banc d'essai lab_live/wolof_bench/ et calibré anti-faux-positifs :
  - Mots forts STRICTEMENT DISCRIMINANTS du Wolof (aucun mot court ambigu comme « un », « du », « la ») ;
  - Règle phonétique validée : « AOCEDA » -> « A-o-sé-da » pour le TTS Oolel-Voices ;
  - Vocabulaire métier énergie sénégalais : « kuraŋ » (courant/électricité), « koppar » (solde/argent).
"""
import re
import unicodedata

# 1. Mots très fréquents en français / anglais / autres qui existent sous forme similaire ou courte
# et qui NE DOIVENT JAMAIS à eux seuls déclencher le Wolof :
AMBIGUS = set("""a an de la le ne o on en me mi no so se si e i in is it of or do to be we he y el lo es
con por una uno que un une et est pas pour qui dans sur au aux ce il elle je tu nous vous mon ma mes ton ta sa son ses
the and are was you they des les du avec sans par vers chez plus tres bien mais ou donc car cette ces leur
leurs notre nos votre vos lui eux quand comme tout tous toute fait faire etre avoir peut dois""".split())

# 2. Mots d'emprunt français courants au Sénégal
EMPRUNTS = set("""facture courant credit compteur recharge recharger climatiseur clim frigo congelateur
ventilateur tele lampe ampoule code carte cash francs kilowatt mois semaine salon chambre cuisine
telephone television machine fer maison argent wave orange senelec dakar""".split())

# 3. Mots FORTS STRICTEMENT DISCRIMINANTS du Wolof
# Ne contient AUCUN mot court collisionnel avec le français ("du", "un") ou le dioula ("kuran", "kan")
MOTS_FORTS = {
    # Particules verbales emphatiques et pronoms exclusifs au Wolof
    "dafa", "dafay", "dama", "damay", "danga", "dangay", "danu", "danuy", "dañu", "dañuy", "dangeen",
    "dina", "dinaa", "dinga", "dingaa", "dingeen", "dinanu", "dinañu", "laay", "ngay",
    "duma", "dumay", "dunga", "dungay", "dunu", "duñuy", "dungeen",
    "yow", "moom", "ñun", "yeen", "ñoom", "seen",
    "nanga", "nangeen", "naka", "sama", "sunu",
    "ñaata", "ñata", "lan", "kañ", "lutax",
    "mangi", "yangi", "mungi", "nungi", "ñungi",
    "nekkoon", "amoon", "amna", "amul",
    "mëna", "mënoon", "bëgg", "bëggoon", "bëggna",
    "saytu", "seytu", "xamal", "dellusi", "waxoon", "waxna",
    "gisoon", "gisna", "deggoon", "jëflante",
    "fay", "takk", "jeex", "jot", "waññi", "yokk", "rekk", "jamm", "baax",
    "waaw", "waw", "deedeet", "déedéet", "dedet", "rawatina", "diisoo",
    # Mots de vocabulaire wolof incontournables
    "kuraŋ", "kuuraŋ", "kurang", "kuurang", "mbëj", "koppar", "koppal", "kër", "dëkk", "tabaski",
    "jëkkër", "nijaay", "doomu", "leegi", "léegi", "xamatu", "tuddee",
    "alhamdoulilah", "taal", "sotti", "faktiir", "konteer", "kontoor"
}
# « aoceda » et « usida » (le nom du produit) ont été RETIRÉS le 10/11/2026 : « Merci AOCEDA », « Ok AOCEDA » partaient
# en wolof (18 phrases françaises ou anglaises sur 18 au banc), et la voix wolof payante se réveillait.

# Mots forts qui existent AUSSI ailleurs (anglais « seen », « jot » ; réseau « LAN » ; prénoms « Dina », « Fay », « Sama » ;
# « taal »...) : seuls, ils ne prouvent rien. Ils ne comptent que si un AUTRE marqueur wolof les accompagne.
EQUIVOQUES = {"seen", "lan", "fay", "jot", "dina", "sama", "taal", "waw", "yow", "jamm",
              # questions courtes (« kan la », « fan la »...) : quatre lettres qui se rencontrent aussi en français mal écrit
              "kan la", "fan la", "ban la", "yan la", "man la"}
# Un seul marqueur suffit dans un message COURT (« Waaw », « Jërejëf », « Baax na ») ; au-delà, il en faut deux.
MOTS_MESSAGE_COURT = 3

# Expressions Wolof composées (discrimination absolue à 100 %)
EXPRESSIONS_WOLOF = [
    "nanga def", "naka nga def", "nangeen def", "jerejef", "jërejëf", "jërajëf",
    "jaaraama", "ba beneen", "yendul ak jamm", "fanaanal ak jamm", "jamm rekk",
    "kuraŋ bi", "kuran bi", "kurang bi", "kuraŋ gi", "kuran gi", "kuraŋ wi", "kuran wi",
    "koppar yi", "koppal yi", "kër gi", "nit ki", "xale yi", "watt wi", "dëkk bi",
    "fay na", "fayna", "takk na", "takkna", "sama kuraŋ", "sama kuran", "sama kurang",
    "sa kuraŋ", "sa kuran", "sa kurang", "sa koppar", "sa koppal",
    "ba noppi", "di la xamal", "dila xamal", "bala ngay", "bala nga",
    "amoon na", "amoon na fi", "fu mu nekk", "kenn xamatu",
    "dama bëgg", "dama begg", "dafay fay", "dina fay", "dafa fay",
    "damay fay", "lu nga wax", "lu nga def", "kuraŋ dafa fay", "kuran dafa fay",
    "kan la", "fan la", "ban la", "yan la", "man la", "man dama", "man damay", "man laay"
]

# Classificateurs consonantiques caractéristiques du Wolof (post-posés à un nom)
CLASSIFICATEURS = {"bi", "gi", "wi", "ji", "mi", "si", "ki", "ñi", "yi"}
NOMS_CLASSIFIABLES = {"kuran", "kuraŋ", "kuuran", "kuuraŋ", "koppar", "kër", "dëkk", "nit", "xale", "watt", "compteur", "facture", "ampoule", "frigo", "tele", "sama"}

# Chiffres wolof de base et multiplicateurs
CHIFFRES_WOLOF = {
    "benn": 1, "ñaar": 2, "ñatt": 3, "ñett": 3, "ñeent": 4, "ñent": 4, "juróom": 5,
    "juróom-benn": 6, "juróom-ñaar": 7, "juróom-ñatt": 8, "juróom-ñett": 8,
    "juróom-ñeent": 9, "juróom-ñent": 9, "fukk": 10,
    "ñaar fukk": 20, "ñaar-fukk": 20, "fanweer": 30, "ñeent fukk": 40, "ñeent-fukk": 40,
    "juróom fukk": 50, "juróom-fukk": 50, "téeméer": 100, "junni": 1000
}

# Lexique métier Wolof d'AOCEDA (pour enrichir le dossier d'intention DeepSeek)
GLOSSAIRE_ENERGIE = {
    "kuraŋ": "électricité / courant",
    "kuuraŋ": "électricité / courant",
    "kuran bi": "l'électricité / le courant",
    "mbëj": "électricité / courant électrique (jamais téléphone)",
    "mbëj mi": "l'électricité / le courant électrique (jamais téléphone)",
    "koppar": "argent / solde / crédit en francs CFA",
    "facture": "facture d'électricité",
    "faktiir": "facture d'électricité",
    "fay": "éteindre / couper le courant, ou payer la facture selon le contexte",
    "tëj": "couper / éteindre / fermer",
    "takk": "allumé / en marche",
    "taal": "allumer / mettre en marche",
    "saytu": "surveiller / vérifier la consommation",
    "xamal": "informer / donner le montant",
    "compteur": "compteur électrique",
    "konteer": "compteur électrique (jamais comptoir)",
    "kontoor": "compteur électrique (jamais comptoir)",
    "kontër": "compteur électrique (jamais comptoir)",
    "recharge": "recharger le crédit d'électricité",
    "sotti": "recharger / verser du crédit sur le compteur",
    "sarse": "recharger le compteur",
    "tegu ci boppam": "se couper / sauter tout seul",
    "dërëm": "unité monétaire wolof valant 5 francs CFA (ex: 100 dërëm = 500 F CFA)",
}


def cle(mot):
    """Normalise un mot pour comparaison robuste."""
    t = unicodedata.normalize("NFC", (mot or "").lower()).replace("’", "'").replace("ʼ", "'")
    t = t.replace("ŋ", "ng").replace("ñ", "ny").replace("ë", "e")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]", "", t)
    return re.sub(r"(.)\1+", r"\1", t)


def mots_de(texte):
    """Extrait la liste des mots d'un texte."""
    t = (texte or "").lower().replace("’", "'").replace("ʼ", "'")
    return re.findall(r"[\wŋñë'-]+", t)


def score_wolof(texte):
    """Calcule le score de confiance Wolof d'un texte (0.0 à 1.0).
    Règle stricte anti-failles :
    - Un texte ne contenant aucun marqueur fort Wolof donne 0.0.
    - Les mots courts ambigus français/anglais ("un", "du", "de", "la") sont strictement exclus.
    - Les collisions avec le dioula ("kuran" sans "bi", "kan") ne déclenchent pas le Wolof.
    """
    if not texte or not texte.strip():
        return 0.0, []

    t_lower = texte.lower().strip()
    mots = mots_de(t_lower)
    if not mots:
        return 0.0, []

    # Éviter les faux positifs sur les textes monosyllabiques isolés
    if len(mots) == 1 and mots[0] in AMBIGUS:
        return 0.0, []

    forts_trouves = []

    # 1. Expressions Wolof complètes (très fort discriminant), sur des MOTS ENTIERS : cherchées en simple sous-chaîne
    #    jusqu'au 10/11/2026, « le ruban la nuit » contenait « ban la » et « un fan la musique » « fan la »
    phrase = " " + " ".join(mots) + " "
    for expr in EXPRESSIONS_WOLOF:
        if f" {expr} " in phrase:
            forts_trouves.append(expr)

    # 2. Mots forts individuels stricts
    for m in mots:
        if m in MOTS_FORTS:
            forts_trouves.append(m)

    # 3. Détecter les structures [Nom + Classificateur] (ex: « kuraŋ bi », « kër gi »)
    for i in range(len(mots) - 1):
        nom_cand = mots[i]
        classif_cand = mots[i + 1]
        if classif_cand in CLASSIFICATEURS and nom_cand in NOMS_CLASSIFIABLES:
            paire = f"{nom_cand} {classif_cand}"
            if paire not in forts_trouves:
                forts_trouves.append(paire)

    # Si aucun marqueur fort certain, score nul absolu
    if not forts_trouves:
        return 0.0, []

    mots_significatifs = [m for m in mots if m not in AMBIGUS and len(m) > 1]
    denom = max(1, len(mots_significatifs))
    nets = [f for f in forts_trouves if f not in EQUIVOQUES]          # marqueurs qui n'existent qu'en wolof
    expression = any(f in EXPRESSIONS_WOLOF and f not in EQUIVOQUES for f in forts_trouves)
    court = len(mots) <= MOTS_MESSAGE_COURT
    # Un mot équivoque tout seul (« seen », « LAN », « Dina », « Fay »...) dans une phrase : pas du wolof
    if not nets and (len(forts_trouves) < 2 or not court) and len(set(forts_trouves)) < 2:
        return 0.0, []

    # Calcul du score proportionnel
    score = min(1.0, (len(forts_trouves) * 1.5) / denom)
    if expression:                                # une expression wolof entière : confiance minimale 0,85
        score = max(0.85, score)
    elif len(set(forts_trouves)) >= 2 or (nets and court):
        score = max(0.65, score)                  # deux marqueurs, ou un marqueur net dans un message court
    # sinon (UN marqueur net dans une longue phrase) : le score proportionnel seul, sans plancher. Avant le 10/11/2026
    # un seul mot donnait 0,65, au-dessus du seuil : toute phrase française qui en contenait un passait en wolof.

    return round(score, 2), forts_trouves


def est_wolof(texte):
    """Détermine si un texte est du Wolof de manière sûre.
    Renvoie (est_wolof: bool, score: float).
    """
    score, forts = score_wolof(texte)
    return (score >= 0.60 and len(forts) > 0), score


def wolof_net(texte):
    """Vérifie si le texte porte nettement la marque du Wolof.
    Renvoie (est_net: bool, score: float, mots_trouves: list).
    """
    score, forts = score_wolof(texte)
    est_w, _ = est_wolof(texte)
    # lecture d'une oreille (texte approximatif) : seuil bas, mais jamais sur un seul mot équivoque (score nul alors)
    return (est_w or (score >= 0.25 and len(forts) >= 1)), score, forts


def normaliser_phonetique_tts(texte):
    """Règle d'or validée dans le lab :
    Remplace toute occurrence du sigle « AOCEDA » par « A-o-sé-da »
    pour garantir une prononciation parfaite avec le son [s] pur et sans heurts palataux.
    """
    if not texte:
        return ""
    return re.sub(r"\bAOCEDA\b", "A-o-sé-da", texte, flags=re.IGNORECASE)


# Lexique atomique normalisé pour le lecteur de nombres composés wolof (avec liaison -i et variantes sans accent)
_UNITES_BASE = {
    "benn": 1, "benni": 1,
    "ñaar": 2, "ñaari": 2, "naar": 2, "naari": 2,
    "ñatt": 3, "ñatti": 3, "ñett": 3, "ñetti": 3, "natt": 3, "natti": 3, "nett": 3, "netti": 3,
    "ñeent": 4, "ñeenti": 4, "ñent": 4, "ñenti": 4, "neent": 4, "neenti": 4, "nent": 4, "nenti": 4,
}
_JUROOM_FORMES = {"juróom", "juróomi", "juroom", "juroomi"}
_MULTIPLICATEURS = {
    "fukk": 10, "fukki": 10,
    "fanweer": 30, "fanweeri": 30,
    "téeméer": 100, "téeméeri": 100, "teemeer": 100, "teemeeri": 100,
    "junni": 1000, "junne": 1000,
    "milyoŋ": 1000000, "tamndareet": 1000000,
}


def _mot_num_wolof(m):
    """Renvoie la valeur numérique d'un mot ou composé à trait d'union wolof (ex: 'juróom-ñaari' -> 7, 'ñaar-fukki' -> 20), ou None."""
    if m in _UNITES_BASE:
        return ("u", _UNITES_BASE[m])
    if m in _JUROOM_FORMES:
        return ("j5", 5)
    if m in _MULTIPLICATEURS:
        val = _MULTIPLICATEURS[m]
        return ("d30", 30) if val == 30 else ("m", val)
    if "-" in m:
        morceaux = [p for p in m.split("-") if p]
        # ex: juróom-ñaari (7), juróom-ñaar-fukki (70), ñaar-fukki (20)
        if len(morceaux) == 2 and morceaux[0] in _JUROOM_FORMES and morceaux[1] in _UNITES_BASE:
            return ("u", 5 + _UNITES_BASE[morceaux[1]])
        if len(morceaux) == 2 and morceaux[0] in _UNITES_BASE and morceaux[1] in ("fukk", "fukki"):
            return ("d", _UNITES_BASE[morceaux[0]] * 10)
        if len(morceaux) == 2 and morceaux[0] in _JUROOM_FORMES and morceaux[1] in ("fukk", "fukki"):
            return ("d", 50)
        if (len(morceaux) == 3 and morceaux[0] in _JUROOM_FORMES
                and morceaux[1] in _UNITES_BASE and morceaux[2] in ("fukk", "fukki")):
            return ("d", (5 + _UNITES_BASE[morceaux[1]]) * 10)
    return None


def _evaluer_groupe_num(jetons_num):
    """Évalue une suite contiguë de jetons numériques wolof (avec 'ak' éventuels)."""
    total = 0
    courant = 0
    i = 0
    while i < len(jetons_num):
        genre, val = jetons_num[i]
        if genre == "ak":
            i += 1
            continue
        # "juróom" suivi d'une unité séparée par un espace (ex: "juróom ñaari") = 5 + u
        if genre == "j5" and i + 1 < len(jetons_num) and jetons_num[i + 1][0] == "u":
            val = 5 + jetons_num[i + 1][1]
            i += 1
        if genre == "m":
            if val == 10:
                courant = (courant * 10) if 1 < courant < 10 else (courant + 10)
            elif val == 100:
                courant = (courant * 100) if 1 <= courant < 10 else (courant + 100)
            elif val >= 1000:
                total += (courant if courant > 0 else 1) * val
                courant = 0
        else:
            courant += val
        i += 1
    return total + courant


def lire_nombres(texte):
    """Reconnaît les nombres composés ET simples écrits en wolof (ex: 'juróom-ñaari junni ak juróomi téeméer' = 7500,
    'fukki kilowattheure ak juróom-ñatt' = 18) pour assister DeepSeek avec une précision arithmétique de 100 %."""
    if not texte or not texte.strip():
        return []
    t_lower = texte.lower().replace("’", "'").replace("ʼ", "'")
    matches = list(re.finditer(r"[\wŋñë-]+", t_lower))
    if not matches:
        return []

    # 1. Repérage des groupes numériques wolof (ex: "juróom-ñaari junni ak juróomi téeméer")
    groupes = []
    n = len(matches)
    i = 0
    while i < n:
        info = _mot_num_wolof(matches[i].group(0))
        if info is None:
            i += 1
            continue
        debut_idx = i
        fin_idx = i
        seq = [info]
        j = i + 1
        while j < n:
            mot_j = matches[j].group(0)
            info_j = _mot_num_wolof(mot_j)
            if info_j is not None:
                seq.append(info_j)
                fin_idx = j
                j += 1
            elif mot_j == "ak" and j + 1 < n and _mot_num_wolof(matches[j + 1].group(0)) is not None:
                seq.append(("ak", 0))
                j += 1
            else:
                break
        val_g = _evaluer_groupe_num(seq)
        groupes.append({
            "i0": debut_idx,
            "i1": fin_idx,
            "c0": matches[debut_idx].start(),
            "c1": matches[fin_idx].end(),
            "valeur": val_g,
            "nb_mots": fin_idx - debut_idx + 1,
        })
        i = fin_idx + 1

    # 2. Règle syntaxique wolof : nom inséré entre la dizaine/centaine (-i) et « ak + reste »
    #    ex: « fukki kilowattheure ak juróom-ñatt » -> 10 + 8 = 18
    fusionnes = []
    k = 0
    while k < len(groupes):
        g = groupes[k]
        if k + 1 < len(groupes):
            suiv = groupes[k + 1]
            ecart = suiv["i0"] - g["i1"] - 1
            # 2 mots entre les deux groupes dont le dernier est « ak » (1 nom d'unité + « ak »)
            if ecart == 2 and matches[suiv["i0"] - 1].group(0) == "ak" and g["valeur"] >= 10 > 0 and suiv["valeur"] < g["valeur"]:
                fusionnes.append({
                    "c0": g["c0"],
                    "c1": suiv["c1"],
                    "valeur": g["valeur"] + suiv["valeur"],
                    "compose": True,
                })
                k += 2
                continue
        fusionnes.append({
            "c0": g["c0"],
            "c1": g["c1"],
            "valeur": g["valeur"],
            "compose": g["nb_mots"] > 1,
        })
        k += 1

    trouves = []
    vus = set()
    # D'abord les nombres composés complets (prioritaires pour DeepSeek)
    for fg in fusionnes:
        extrait = t_lower[fg["c0"]:fg["c1"]]
        if extrait not in vus:
            trouves.append({"texte": extrait, "valeur": fg["valeur"]})
            vus.add(extrait)

    # Puis les correspondances élémentaires (compatibilité ascendante et repères unitaires)
    for nom, val in CHIFFRES_WOLOF.items():
        if nom not in vus and re.search(r"\b" + re.escape(nom) + r"\b", t_lower):
            trouves.append({"texte": nom, "valeur": val})
            vus.add(nom)
    return trouves


def lexique_utile(texte):
    """Extrait les définitions du glossaire énergie pour les mots présents dans le message."""
    t_lower = (texte or "").lower()
    utile = {}
    for mot, defn in GLOSSAIRE_ENERGIE.items():
        if re.search(r"\b" + re.escape(mot) + r"\b", t_lower):
            utile[mot] = defn
    return utile
