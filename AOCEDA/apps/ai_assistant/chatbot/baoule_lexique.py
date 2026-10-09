"""CARNET DE MOTS BAOULÉ rangé par SENS (06/10/2026), construit par tests/bancs/baoule_lexique/construire_lexique.py à partir
de sources LIBRES (GATITOS et SMOL de Google en CC-BY-4.0, Common Voice, WAXAL, glossaire AOCEDA).

Retour client du 06/10/2026 : « salut » n'existe pas dans le dictionnaire, mais « bonjour » oui : il faut chercher par
le SENS, pas par le mot exact. D'où une recherche en cascade, dans cet ordre :
  1. le mot exact ;
  2. une FICHE DE SENS qui le contient (« salut » est dans la fiche « saluer », avec « bonjour », « hello ») ;
  3. le même mot à l'orthographe près (accents, pluriel, article : « la facture » = « facture ») ;
  4. en passant par l'ANGLAIS (GATITOS est anglais-baoulé) : Google donne le mot anglais, on cherche celui-ci ;
  5. sinon : le mot est noté dans la liste des mots manquants (cache/mots_manquants_baoule.jsonl), pour un locuteur.
Dans l'autre sens (comprendre), un mot baoulé entendu donne son sens français et anglais (comparaison sans tons, ɛ=e,
ɔ=o, ɲ=ny, article collé « 'n » retiré).

Tout ce qui vient d'ici est un INDICE à faire valider par un locuteur (champ « verifie ») : jamais une certitude.
"""
import json
import re
import threading
import unicodedata
from datetime import datetime
from functools import lru_cache

from . import baoule_texte
from .config import CACHE, DONNEES

FICHIER = DONNEES / "lexique_sens_baoule.json"
MANQUANTS = CACHE / "mots_manquants_baoule.jsonl"
_verrou = threading.Lock()
cle_bci = baoule_texte.cle                       # même comparaison que le reste du baoulé


def cle_fr(texte):
    """Forme de comparaison d'un mot ou d'une expression française/anglaise : minuscules, sans accents ni article,
    singulier approximatif (« les factures » -> « facture », « l'électricité » -> « electricite »)."""
    t = unicodedata.normalize("NFD", (texte or "").lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"^(le|la|les|l'|un|une|des|du|de la|de l'|the|a|an|to)\s*", "", t.strip())
    mots = [re.sub(r"(?<=\w{3})(s|x)$", "", m) for m in re.findall(r"[a-z0-9']+", t)]
    return " ".join(mots)


@lru_cache(maxsize=1)
def donnees():
    """Le carnet chargé et indexé une seule fois : {"fiches", "entrees", "mots", "par_fr", "par_en", "par_bci", ...}."""
    d = json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {"fiches": [], "entrees": [], "mots": {}}
    par_fr, par_en, par_bci = {}, {}, {}
    for e in d["entrees"]:
        for f in e["fr"]:
            par_fr.setdefault(cle_fr(f), []).append(e)
        par_en.setdefault(cle_fr(e["en"]), []).append(e)
        for b in e["bci"]:
            par_bci.setdefault(cle_bci(b), []).append(e)
    fiche_de = {}
    for f in d["fiches"]:
        for m in f["fr"] + f["en"]:
            fiche_de.setdefault(cle_fr(m), f)
        for b in f["bci"]:
            par_bci.setdefault(cle_bci(b), []).append({"en": f["en"][0], "fr": f["fr"][:3], "bci": f["bci"],
                                                       "source": "fiche de sens AOCEDA", "verifie": False, "fiche": f["id"]})
    mots = {}
    for m, n in d["mots"].items():
        k = cle_bci(m)
        if k:
            mots[k] = mots.get(k, 0) + n
    return {**d, "par_fr": par_fr, "par_en": par_en, "par_bci": par_bci, "fiche_de": fiche_de, "cles_mots": mots}


@lru_cache(maxsize=1)
def _formes():
    """{clé: forme écrite la plus fréquente} (« lɛman », « leman » -> la plus courante dans les vrais textes)."""
    d, out = donnees(), {}
    for m, n in d["mots"].items():
        k = cle_bci(m)
        if k and n > out.get(k, ("", -1))[1]:
            out[k] = (m, n)
    return {k: v[0] for k, v in out.items()}


def forme(mot):
    """Forme écrite courante d'un mot baoulé connu (ou le mot tel quel)."""
    return _formes().get(cle_bci(mot), mot)


@lru_cache(maxsize=1)
def _par_longueur():
    out = {}
    for k, n in donnees()["cles_mots"].items():
        out.setdefault(len(k), []).append((k, n))
    return out


def voisins(mot, frequence_min=3):
    """Mots connus à UNE lettre près (même début), pour corriger un mot déformé : [(forme, fréquence)]."""
    k = cle_bci(mot)
    if len(k) < 5:
        return []
    out = []
    for n in (len(k) - 1, len(k), len(k) + 1):
        for c, f in _par_longueur().get(n, []):
            if f >= frequence_min and c[0] == k[0] and c != k and baoule_texte.dioula_texte._distance(c, k) <= 1:
                out.append((forme(c), f))
    return sorted(out, key=lambda x: -x[1])[:5]


def paire(a, b):
    """Nombre de fois où « a b » a été vu côte à côte dans de vrais textes baoulé (sans article, sans tons)."""
    s = baoule_texte.sans_article
    return donnees().get("paires", {}).get(f"{cle_bci(s(a))} {cle_bci(s(b))}", 0)


def connu(mot):
    """Le mot baoulé existe-t-il dans un vrai texte baoulé ou dans le carnet ? (« sika'n » = « sika » + article)."""
    k = cle_bci(baoule_texte.sans_article(baoule_texte.apostrophes(mot).lower()))
    return bool(k) and (k in donnees()["cles_mots"] or k in donnees()["par_bci"])


def frequence(mot):
    return donnees()["cles_mots"].get(cle_bci(mot), 0)


def mots_connus():
    """{clé: fréquence} de tous les mots baoulé connus (réparation de l'écoute)."""
    return donnees()["cles_mots"]


def _resultat(mot, chemin, bci, via=None, source=None, verifie=False, fiche=None):
    return {"mot": mot, "chemin": chemin, "via": via, "bci": list(dict.fromkeys(bci)), "source": source,
            "verifie": verifie, "fiche": fiche}


def _depuis_fiche(mot, fiche, chemin, via=None):
    """Mots baoulé d'une fiche : ceux de la fiche + ceux de GATITOS pour ses mots anglais."""
    d = donnees()
    bci = list(fiche["bci"])
    for en in fiche["en"]:
        for e in d["par_en"].get(cle_fr(en), []):
            bci += e["bci"]
    return _resultat(mot, chemin, bci, via=via, source="fiche de sens AOCEDA + GATITOS", fiche=fiche["id"])


def traduire_mot(mot, langue="fr", vers_anglais=None):
    """Mot ou expression française (ou anglaise) -> mots baoulé, par la cascade décrite en tête du module.
    `vers_anglais` : fonction mot français -> mot anglais (Google), appelée seulement en dernier recours.
    Renvoie {"mot", "chemin", "via", "bci", "source", "verifie", "fiche"} ; chemin = exact | sens | orthographe |
    anglais | absent."""
    d = donnees()
    k = cle_fr(mot)
    index = d["par_fr"] if langue == "fr" else d["par_en"]
    fiche = d["fiche_de"].get(k)
    if fiche:                                  # 1-2. une fiche de sens contient le mot : ses mots d'abord (les plus sûrs),
        principal = fiche["fr"][0] if langue == "fr" else fiche["en"][0]          # puis ceux de GATITOS pour ce mot
        exact = k in index or cle_fr(principal) == k
        r = _depuis_fiche(mot, fiche, "exact" if exact else "sens", via=None if exact else principal)
        r["bci"] = list(dict.fromkeys(r["bci"] + [b for e in index.get(k, []) for b in e["bci"]]))
        return r
    if k in index:                                                       # 1. exact
        es = index[k]
        return _resultat(mot, "exact", [b for e in es for b in e["bci"]], source=es[0]["source"])
    proches = [c for c in index if c and (c.startswith(k + " ") or k.startswith(c + " "))] if len(k) >= 4 else []
    if proches:                                                          # 3. orthographe / expression voisine
        c = min(proches, key=len)
        return _resultat(mot, "orthographe", [b for e in index[c] for b in e["bci"]], via=c, source=index[c][0]["source"])
    if langue == "fr" and vers_anglais:                                  # 4. par l'anglais
        try:
            en = vers_anglais(mot)
        except Exception:
            en = None
        if en and cle_fr(en) in d["par_en"]:
            es = d["par_en"][cle_fr(en)]
            return _resultat(mot, "anglais", [b for e in es for b in e["bci"]], via=en, source=es[0]["source"])
        if en and cle_fr(en) in d["fiche_de"]:
            return _depuis_fiche(mot, d["fiche_de"][cle_fr(en)], "anglais", via=en)
    noter_manquant(mot, langue)                                          # 5. absent : pour le locuteur
    return _resultat(mot, "absent", [])


def sens(mot_bci):
    """Sens d'un mot baoulé entendu : [{"fr", "en", "source"}] (vide si inconnu)."""
    d = donnees()
    m = baoule_texte.sans_article(baoule_texte.apostrophes(mot_bci).lower())
    out = []
    for e in d["par_bci"].get(cle_bci(m), [])[:4]:
        out.append({"fr": e["fr"][:3], "en": e["en"], "source": e["source"]})
    return out


def sens_du_texte(texte, maximum=25):
    """Sens des mots d'un texte baoulé (glossaire AOCEDA d'abord, puis carnet). {mot: "sens fr (anglais : ...)"}."""
    out = dict(baoule_texte.lexique_utile(texte))
    deja = {cle_bci(k) for k in out}
    for m in baoule_texte.mots_de(texte):
        m = baoule_texte.sans_article(m.strip("'"))
        k = cle_bci(m)
        if len(k) < 3 or k in deja or len(out) >= maximum:
            continue
        s = sens(m)
        if s:
            fr = ", ".join(x for x in dict.fromkeys(f for e in s for f in e["fr"]) if x)
            en = ", ".join(dict.fromkeys(e["en"] for e in s))
            out[m] = f"{fr} (anglais : {en})" if fr else en
            deja.add(k)
    return out


def noter_manquant(mot, langue="fr"):
    """Mot cherché sans résultat : gardé pour qu'un locuteur le complète (une ligne par mot, sans doublon récent)."""
    with _verrou:
        MANQUANTS.parent.mkdir(parents=True, exist_ok=True)
        deja = set()
        if MANQUANTS.exists():
            deja = {json.loads(l)["mot"] for l in MANQUANTS.read_text(encoding="utf-8").splitlines()[-500:] if l.strip()}
        if mot not in deja:
            with open(MANQUANTS, "a", encoding="utf-8") as f:
                f.write(json.dumps({"mot": mot, "langue": langue, "date": datetime.now().isoformat(timespec="seconds")},
                                   ensure_ascii=False) + "\n")


def mots_manquants(limite=200):
    if not MANQUANTS.exists():
        return []
    return [json.loads(l) for l in MANQUANTS.read_text(encoding="utf-8").splitlines() if l.strip()][-limite:]


# ── Questions de vocabulaire (« comment dit-on salut en baoulé ? ») ──────────────
_Q_FR = [r"comment (?:est-ce qu'on |on |)(?:dit|dire|dit-on|dis|dit on|écrit|ecrit)[- ]?(?:on )?[«\"']?\s*(.+?)\s*[»\"']?\s+en baoul[ée]",
         r"(?:que veut dire|ça veut dire quoi|ca veut dire quoi|que signifie|signification de|sens de)\s+[«\"']?\s*(.+?)\s*[»\"']?(?:\s+en baoul[ée])?\s*\??$",
         r"[«\"']?(.+?)[»\"']?\s+en baoul[ée]\s*(?:se dit comment|c'est comment|c'est quoi|on dit comment)",
         r"(?:traduis|traduire|traduction de)\s+[«\"']?\s*(.+?)\s*[»\"']?\s+en baoul[ée]"]
_Q_EN = [r"how (?:do you|do i|to|can i) say\s+[\"']?(.+?)[\"']?\s+in baoul[ée]",
         r"what(?:'s| is) (?:the word for\s+)?[\"']?(.+?)[\"']?\s+in baoul[ée]",
         r"translate\s+[\"']?(.+?)[\"']?\s+(?:in|into|to) baoul[ée]",
         r"what does\s+[\"']?(.+?)[\"']?\s+mean"]


def question_vocabulaire(texte):
    """« Comment dit-on salut en baoulé ? » -> ("fr", "salut") ; « que veut dire aɲiho ? » -> ("bci", "aɲiho") ;
    « how do you say hello in Baoulé » -> ("en", "hello"). None si ce n'est pas une question de vocabulaire."""
    t = (texte or "").strip().rstrip(" ?!.")
    for motifs, langue in ((_Q_FR, "fr"), (_Q_EN, "en")):
        for i, motif in enumerate(motifs):
            m = re.search(motif, t, re.I)
            if m:
                mot = m.group(1).strip(" «»\"'?").strip()
                if not mot or len(mot.split()) > 5:
                    continue
                demande_sens = (langue == "fr" and i == 1) or (langue == "en" and i == 3)
                return ("bci" if demande_sens else langue), mot
    return None


def note_vocabulaire(texte, vers_anglais=None):
    """Pour le cerveau IA : ce que dit VRAIMENT le carnet sur la question de vocabulaire (ou None), pour qu'il n'invente
    aucun mot baoulé."""
    q = question_vocabulaire(texte)
    if not q:
        return None
    langue, mot = q
    if langue == "bci":
        s = sens(mot)
        if not s:
            return (f"\n\nCARNET DE MOTS BAOULÉ (sources libres) : « {mot} » n'y figure pas. Dis-le honnêtement ; n'invente "
                    "aucun sens.")
        lignes = "; ".join(f"{', '.join(e['fr']) or e['en']} (anglais : {e['en']}, source {e['source']})" for e in s)
        return (f"\n\nCARNET DE MOTS BAOULÉ (sources libres, à faire confirmer par un locuteur) : « {mot} » = {lignes}. "
                "Donne ce sens et précise que c'est à confirmer par un locuteur.")
    r = traduire_mot(mot, langue, vers_anglais)
    if not r["bci"]:
        return (f"\n\nCARNET DE MOTS BAOULÉ (sources libres) : aucun mot baoulé trouvé pour « {mot} » (ni par le sens, ni "
                "par l'anglais). Dis honnêtement que tu ne connais pas ce mot en baoulé ; n'invente JAMAIS de mot baoulé.")
    chemin = {"exact": "", "sens": f" (trouvé par le sens, comme « {r['via']} »)",
              "orthographe": f" (trouvé avec « {r['via']} »)", "anglais": f" (trouvé en passant par l'anglais « {r['via']} »)"}
    return (f"\n\nCARNET DE MOTS BAOULÉ (sources libres, à faire confirmer par un locuteur) : « {mot} » se dit "
            f"{' ou '.join('« ' + b + ' »' for b in r['bci'][:4])}{chemin.get(r['chemin'], '')} ; source : {r['source']}. "
            "Donne UNIQUEMENT ces mots baoulé (n'en invente aucun autre), explique en une phrase le chemin si ce n'est pas "
            "le mot exact, et précise que c'est à confirmer par un locuteur.")


def etat():
    d = donnees()
    return {"entrees": len(d["entrees"]), "fiches": len(d["fiches"]), "mots_connus": len(d["cles_mots"]),
            "paires": len(d.get("paires", {})), "mots_manquants": len(mots_manquants()), "version": d.get("version"),
            "sources": d.get("sources", [])}
