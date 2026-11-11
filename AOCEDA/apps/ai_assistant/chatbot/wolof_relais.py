"""Relais WOLOF <-> FRANÇAIS : DeepSeek raisonne et utilise les outils en français ;
on passe par le français à l'aller et au retour via l'API Google Traduction (code 'wo').

Capitalisé sur le banc d'essai lab_live/wolof_bench/ :
- Google Client5 gère nativement le Wolof ('wo') avec une latence mesurée de ~200 ms ;
- Même mécanique que le Dioula et le Baoulé : coupe-circuit après 3 pannes, mémoire des requêtes,
  connexion HTTP réutilisée (Keep-Alive).
"""
import re
import time
from . import dioula_relais, wolof_texte
from .dioula_relais import RelaisIndisponible

DELAI_ALLER_S = 2.5
DELAI_TOTAL_RETOUR_S = 7.0

# Enregistrement des traducteurs Wolof dans le registre central
dioula_relais.SERVICES.update({
    ("google", "wo_vers_fr"): (dioula_relais._google, "wo", "fr"),
    ("google", "vers_wo"): (dioula_relais._google, "fr", "wo"),
})

# Catalogue aller instantané (0 ms, 0 requête réseau) pour les formules courtes fréquentes
PHRASES_ALLER_WOLOF = {
    "nanga def": "Bonjour, comment allez-vous ?",
    "naka nga def": "Bonjour, comment allez-vous ?",
    "nangeen def": "Bonjour, comment allez-vous ?",
    "salaamaalekum": "Bonjour",
    "waaw": "Oui",
    "waw": "Oui",
    "deedeet": "Non",
    "déedéet": "Non",
    "dedet": "Non",
    "jerejef": "Merci",
    "jërejëf": "Merci",
    "jerejef lool": "Merci beaucoup",
    "jërejëf lool": "Merci beaucoup",
    "baax na": "D'accord, c'est bien",
    "waaw baax na": "Oui, d'accord",
    "jamm rekk": "Tout va bien",
    "ba beneen": "Au revoir",
}

# Catalogue des phrases fréquentes d'AOCEDA au retour (latence = 0 ms, 0 requête réseau)
PHRASES_COURANTES_WOLOF = {
    "bonjour": "Nanga def.",
    "bonsoir": "Nanga def.",
    "merci": "Jërejëf.",
    "merci beaucoup": "Jërejëf lool.",
    "merci pour votre confiance": "Jërejëf ci sa kóolute.",
    "de rien": "Amul solo.",
    "au revoir": "Ba beneen.",
    "a bientot": "Ba beneen yoon.",
    "a bientôt": "Ba beneen yoon.",
    "oui": "Waaw.",
    "non": "Déedéet.",
    "d'accord": "Waaw, baax na.",
    "daccord": "Waaw, baax na.",
    "bienvenue chez aoceda": "Dalal ak jamm ci AOCEDA.",
    "comment puis-je vous aider": "Nan la la mëna dimbali ?",
    "comment puis-je vous aider aujourd'hui": "Nan la la mëna dimbali tey ?",
    "votre solde est suffisant": "Sa koppar doy na.",
    "votre compteur est actif": "Sa compteur mi ngi dox.",
    "le courant est retabli": "Kuraŋ bi dellusi na.",
    "le courant est rétabli": "Kuraŋ bi dellusi na.",
    "le courant est coupe": "Kuraŋ bi dafa fay.",
    "le courant est coupé": "Kuraŋ bi dafa fay.",
    "je comprends votre demande": "Dégg naa li nga laaj.",
    "je comprends votre situation": "Dégg naa sa mbir.",
    "voici votre consommation": "Lii mooy li nga jëfandikoo.",
    "voici quelques conseils simples": "Lii mooy ay xelal yu yomb.",
    "je verifie vos donnees": "Maa ngi xool say jumtukaay.",
    "je vérifie vos données": "Maa ngi xool say jumtukaay.",
    "attention a votre credit": "Moytul ci sa kredi kuuraŋ.",
    "attention à votre crédit": "Moytul ci sa kredi kuuraŋ.",
}

_RE_ETOILES_MD = re.compile(r"\*{1,3}|_{2}")
_RE_MILLIERS = re.compile(r"(?<![\d.,])(\d{1,3})(?:[.,](\d{3}))+(?![\d.,])")
_RE_PM = re.compile(r"\b(\d{1,2})\s*p\.?\s*m\.?\b", re.I)
_RE_AM = re.compile(r"\b(\d{1,2})\s*a\.?\s*m\.?\b", re.I)
_RE_HEURE_NUIT_FAUSSE = re.compile(r"\b((?:7|8|9|10|11|18|19|20|21|22|23)\s*waxtu\s+ci\s+)bëccëg\b", re.I)
_RE_WAXTU_NUM_KW = re.compile(r"\bwaxtu\s+(\d+(?:[.,]\d+)?)\s*kilowatt(?:s|heure|heures)?\b", re.I)
_RE_WAXTU_KW = re.compile(r"\b(?:waxtu[- ]+kilowatt|kilowatt[- ]+waxtu)\b", re.I)


def _nettoyer(texte):
    """Nettoie la ponctuation parasite, les étoiles Markdown et les espaces multiples."""
    t = _RE_ETOILES_MD.sub("", texte or "")
    t = re.sub(r"^\s*[?¿]+\s*", "", t).strip()
    return re.sub(r"\s+", " ", t)


def _corriger_metier_wolof(texte_francais, texte_wolof):
    """Corrige de façon déterministe (0,05 ms) les faux-amis récurrents de Google Traduction (fr -> wo)
    dans le domaine électrique sénégalais, tout en préservant la grammaire wolof authentique de Google."""
    if not texte_wolof:
        return texte_wolof
    fr_low = (texte_francais or "").lower()
    out = dioula_relais.sans_parentheses_ajoutees(texte_francais, texte_wolof)

    # 1. Séparateurs de milliers à l'anglaise (« 2,500 » -> « 2 500 », sans toucher aux décimaux « 14,5 »)
    out = _RE_MILLIERS.sub(lambda m: m.group(0).replace(".", " ").replace(",", " "), out)

    # 1 bis. « francs » traduit « dërëm » : le dërëm vaut 5 francs, « 350 dërëm » dit donc 1 750 francs (vu le
    #    10/11/2026 : un montant multiplié par cinq). Le chiffre de la phrase française est en francs : on garde « francs ».
    if re.search(r"\bfrancs?\b|\bF\s?CFA\b|\bFCFA\b", texte_francais or "", flags=re.I):
        out = re.sub(r"\bd[eë]r[eë]m\b", "francs", out, flags=re.I)

    # 2. « crédit » électrique traduit à tort « leble » (dette / prêt bancaire)
    if any(m in fr_low for m in ("crédit", "credit", "prépay", "prepay", "solde", "recharg", "compteur")):
        out = re.sub(r"\bleble\b", "kredi kuuraŋ", out, flags=re.I)

    # 3. « kilowattheures » traduit littéralement « waxtu kilowatt » / « kilowatt-waxtu »
    out = _RE_WAXTU_NUM_KW.sub(r"\1 kilowattheure", out)
    out = _RE_WAXTU_KW.sub("kilowattheure", out)

    # 4. Heures du soir traduites en anglais (« 6 p.m. ») ou en « ci bëccëg » (de jour) pour 19h-22h
    out = _RE_PM.sub(r"\1 waxtu ci ngoon", out)
    out = _RE_AM.sub(r"\1 waxtu ci suba", out)
    if any(m in fr_low for m in ("soir", "nuit", "18", "19", "20", "21", "22", "23")):
        out = _RE_HEURE_NUIT_FAUSSE.sub(r"\1guddi", out)

    # 5. Anglicismes résiduels de Google en wolof
    out = re.sub(r"\bstandby\b", "veille", out, flags=re.I)
    if "tranche" in fr_low:
        out = re.sub(r"\bbracket\b", "tranche", out, flags=re.I)

    # 6. Ponctuation et labels idiomatiques
    out = re.sub(r"\s+([.,;!?])", r"\1", out)
    out = re.sub(r"\bTips\s*:?", "Xelal :", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def vers_francais(texte_wolof, delai_s=DELAI_ALLER_S):
    """Wolof -> Français (catalogue instantané 0 ms + Google Traduction via session Keep-Alive et cache mémoire).
    Renvoie {"google": texte_fr, "duree_s": float, "erreurs": list}.
    """
    if not texte_wolof or not texte_wolof.strip():
        return {"google": None, "duree_s": 0.0, "erreurs": []}
    propre = texte_wolof.strip()
    cle_rapide = re.sub(r"[^\w\sŋñë]", "", propre.lower()).strip()
    if cle_rapide in PHRASES_ALLER_WOLOF:
        return {"google": PHRASES_ALLER_WOLOF[cle_rapide], "duree_s": 0.0, "erreurs": []}

    t0 = time.time()
    erreurs = []
    for _ in range(2):
        reste = delai_s - (time.time() - t0)
        if reste < 0.4:
            break
        tache = dioula_relais._services.submit(dioula_relais.traduire, "google", "wo_vers_fr", propre)
        try:
            out = _nettoyer(tache.result(timeout=reste))
            if out:
                return {"google": out, "duree_s": round(time.time() - t0, 2), "erreurs": []}
        except Exception as e:
            erreurs.append(str(e)[:120])
    return {"google": None, "duree_s": round(time.time() - t0, 2), "erreurs": erreurs or ["echec traduction"]}


def vers_wolof(texte_francais, delai_s=DELAI_TOTAL_RETOUR_S):
    """Français -> Wolof (catalogue instantané 0 ms + Google Traduction avec cache mémoire + correction métier énergie).
    Renvoie le texte wolof. Lève RelaisIndisponible si la traduction échoue, reste en français ou change un nombre :
    la phrase est alors affichée en français avec la mention « non traduit » (avant le 10/11/2026, le français était
    renvoyé comme si c'était du wolof, et la voix wolof le lisait)."""
    if not texte_francais or not texte_francais.strip():
        return ""
    texte_clean = _nettoyer(texte_francais)
    if not texte_clean:
        return ""
    cle = re.sub(r"[^\w\s]", "", texte_clean.lower()).strip()
    if cle in PHRASES_COURANTES_WOLOF:
        return PHRASES_COURANTES_WOLOF[cle]
    from .heures_fr import heures_sur_12h
    texte_clean = heures_sur_12h(texte_clean)             # « à 18 h » -> « à 6 heures du soir » (Google passe sur 12 h sans le dire)
    tache = dioula_relais._services.submit(dioula_relais.traduire, "google", "vers_wo", texte_clean)
    try:
        trad = _nettoyer(tache.result(timeout=delai_s))
    except RelaisIndisponible:
        raise
    except Exception as e:
        raise RelaisIndisponible(f"google : {str(e)[:80] or 'trop lent'}")
    if not trad or dioula_relais._reste_en_francais(texte_clean, trad):
        raise RelaisIndisponible("google : traduction restée en français")
    trad = _corriger_metier_wolof(texte_clean, trad)
    lus = [n["valeur"] for n in wolof_texte.lire_nombres(trad)]
    perdus = dioula_relais.nombres_perdus(texte_clean, trad, lus) or dioula_relais.chiffres_en_lettres_perdus(texte_clean, trad, lus, ("poñ", "pon "))
    if perdus:
        raise RelaisIndisponible(f"google : nombre changé ({', '.join(perdus)})")
    from . import controle_sens
    if controle_sens.a_controler(texte_clean):          # état ou ordre de coupure : le SENS doit survivre (10/11/2026, défaut D6)
        try:
            retour = _nettoyer(dioula_relais.traduire("google", "wo_vers_fr", trad))
        except RelaisIndisponible:
            retour = None
        ecarts = controle_sens.ecarts(texte_clean, retour)
        if ecarts:
            raise RelaisIndisponible(f"google : sens douteux ({', '.join(ecarts)})")
    return trad


def lancer_vers_wolof(texte_francais):
    """Traduit une phrase en wolof en arrière-plan sur le pool dédié (8 fils) et normalise AOCEDA -> A-o-sé-da."""
    return dioula_relais._pool.submit(
        lambda: (wolof_texte.normaliser_phonetique_tts(vers_wolof(texte_francais)), "google")
    )


def prechauffer():
    """Pré-ouvre la connexion HTTP pour éviter la latence froide."""
    try:
        dioula_relais.traduire("google", "wo_vers_fr", "Nanga def")
    except RelaisIndisponible:
        pass
