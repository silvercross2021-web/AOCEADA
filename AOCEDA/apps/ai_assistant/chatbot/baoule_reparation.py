"""RÉPARATION de l'écoute baoulé CONTRÔLÉE PAR LE SON (06/10/2026), sans aucun entraînement.

L'oreille baoulé colle parfois deux mots (« amunlɛman » au lieu de « amun lɛman ») ou déforme une lettre. Pour chaque
mot qu'aucun vrai texte baoulé ne connaît (carnet baoule_lexique : 5 000+ mots de sources libres), on essaie :
  1. de le COUPER en deux mots connus (« amunlɛman » -> « amun lɛman », « anyan » -> « a nyan ») ;
  2. de le remplacer par un mot connu à UNE lettre près (mots assez longs et fréquents seulement).
Chaque essai est « réécouté » : Ecoute.score_sonore mesure à quel point l'audio de ce passage colle à la nouvelle
écriture (même calcul que pour le dioula, dioula_texte.reparer). La réparation n'est gardée que si le son l'accepte
presque aussi bien que ce que l'oreille avait écrit (marges du dioula, mesurées le 29/09/2026). Sinon : rien ne change.
Chaque réparation est rendue visible (page : « réparé : amunlɛman → amun lɛman »).
"""
from . import baoule_lexique, dioula_texte

MARGE_SONORE = dioula_texte.MARGE_SONORE         # remplacement d'un mot
# ajout d'un espace : 3,0 pour le baoulé (6,0 pour le dioula). Réglé le 06/10/2026 sur 120 vrais vocaux de test : à 6,0,
# 16 bonnes coupures et 5 mauvaises ; à 3,0, 15 bonnes et 2 mauvaises. Vérifié ensuite sur les 175 AUTRES vocaux de
# test (tests/bancs/baoule_lexique/evaluer_reparation.py validation), jamais vus pendant le réglage.
MARGE_COUPURE = 3.0
cle = baoule_lexique.cle_bci
# petits mots baoulé qui vivent seuls (pronoms, particules) : ils peuvent former un morceau d'une coupure
PETITS = {cle(x) for x in "n a e i ɔ o be bɛ y ɲ min wɔ yɛ kɛ nin ni su nun lɔ".split()}
ESSAIS_MAX = 6
PREFERENCE_NETTE = 1.0  # coupure jamais vue en vrai baoulé : seulement si le son la préfère nettement


SOLIDE = 3            # un mot vu au moins 3 fois dans les vrais textes est un vrai mot : on n'y touche pas
COURANT = 10          # un mot rare (1-2 fois : peut-être une coquille) n'est coupé qu'en mots COURANTS


def _morceau_ok(x, exigeant=False):
    k = cle(x)
    return k in PETITS or (len(k) >= 2 and baoule_lexique.frequence(x) >= (COURANT if exigeant else 2))


def _decoupages(mot, exigeant=False):
    """Coupures possibles en 2 mots connus, les plus équilibrées d'abord (au moins un morceau de 3 lettres)."""
    out = []
    if "'" in mot:                       # article collé (« sran'mun », « sika'n ») : c'est un seul mot, jamais coupé
        return out
    for i in range(1, len(mot)):
        a, b = mot[:i].strip("'"), mot[i:].strip("'")
        if a and b and _morceau_ok(a, exigeant) and _morceau_ok(b, exigeant) and max(len(cle(a)), len(cle(b))) >= 3:
            out.append(f"{a} {b}")
    return sorted(out, key=lambda e: -min(len(x) for x in e.split()))[:ESSAIS_MAX]


def _score(ecoute, chaine, t0, t1):
    """Score sonore ; si l'oreille n'écrit pas une lettre (ɲ, ŋ), on la mesure comme elle l'écrit (ny, ng)."""
    try:
        s = ecoute.score_sonore(chaine, t0, t1)
        if s is None:
            s = ecoute.score_sonore(chaine.replace("ɲ", "ny").replace("ŋ", "ng"), t0, t1)
        return s
    except Exception:             # mesure impossible (modèle pas chargé, lettre inconnue) : on ne répare pas, on ne plante pas
        return None


def reparer(ecoute):
    """Renvoie (texte réparé, [{"entendu", "repare", "type", "ecart_sonore"}]). Ne touche jamais à un mot connu."""
    sortie, faits = [], []
    for i, m in enumerate(ecoute.mots):
        mot = baoule_lexique.baoule_texte.apostrophes(m["mot"]).strip("'") or m["mot"]
        frequence = baoule_lexique.frequence(baoule_lexique.baoule_texte.sans_article(mot))
        rare = 0 < frequence < SOLIDE
        if (len(cle(mot)) < 3 or frequence >= SOLIDE or (frequence == 0 and baoule_lexique.connu(mot))
                or not mot.replace("'", "").isalpha()):
            sortie.append(mot)
            continue
        t0, t1 = m.get("t0", 0) - 3, m.get("t1", 0) + 3
        base = _score(ecoute, mot, t0, t1)
        meilleur = None
        if base is not None:
            for essai in _decoupages(mot, exigeant=rare):                      # 1. mot collé
                s = _score(ecoute, essai, t0, t1)
                # mesuré le 06/10/2026 sur 40 vrais vocaux : le son seul accepte aussi de mauvaises coupures en petits
                # mots courants (« kpa nti », « su wan ») ; il faut que la PAIRE existe dans de vrais textes baoulé,
                # ou que le son préfère franchement la coupure
                vue = baoule_lexique.paire(*essai.split(" ", 1)) > 0
                if (s is not None and (vue and s >= base - MARGE_COUPURE or s >= base + PREFERENCE_NETTE)
                        and (meilleur is None or s > meilleur[1])):
                    meilleur = (essai, s, "coupure")
            if meilleur is None and not rare:
                avant = sortie[-1].split()[-1] if sortie else None
                apres = ecoute.mots[i + 1]["mot"] if i + 1 < len(ecoute.mots) else None
                for v, _ in baoule_lexique.voisins(mot):                       # 2. mot déformé
                    s = _score(ecoute, v, t0, t1)
                    vue = (avant and baoule_lexique.paire(avant, v) > 0) or (apres and baoule_lexique.paire(v, apres) > 0)
                    if (s is not None and (vue and s >= base - MARGE_SONORE or s >= base + PREFERENCE_NETTE)
                            and (meilleur is None or s > meilleur[1])):
                        meilleur = (v, s, "lettre")
        if meilleur:
            faits.append({"entendu": mot, "repare": meilleur[0], "type": meilleur[2], "ecart_sonore": round(meilleur[1] - base, 2)})
            sortie.append(meilleur[0])
        else:
            sortie.append(mot)
    return " ".join(sortie), faits
