"""BLOC C : DÉCIDER (06/10/2026). Le RÈGLEMENT : du code, toujours pareil, sans IA.

1. Raccourci « oui / non » : si une question attend une réponse (« Vous voulez recharger cinq mille francs ? ») et que
   la personne répond « ɛɛ » (oui) ou « cɛcɛ » (non), le code le reconnaît seul (rapide, sans erreur d'interprétation).
2. Vérifications du choix de l'IA : le montant a-t-il vraiment été entendu ? l'appareil existe-t-il dans le compte ?
3. NOTE DE CONFIANCE calculée par le code à partir de signaux visibles (avis de l'IA, accord des interprètes, exemple
   vérifié proche, réparations, certitude de l'oreille, longueur du message...).
4. RÈGLE DE RÉPONSE : argent ou appareil -> TOUJOURS demander confirmation (rien sans « oui ») ; note haute -> réponse
   directe ; moyenne -> réponse puis « est-ce bien cela ? » ; basse -> courte réponse + 2 autres choix en boutons ;
   hors sujet -> le dire poliment.
Les valeurs des points sont un DÉPART, à régler sur de vrais vocaux de test (tests/bancs/baoule_logique/evaluer_chaine.py).
"""
import threading
import time
from dataclasses import dataclass, field

from . import baoule_demandes, baoule_texte
from .nombres_fr import nombres_dans

ATTENTE_S = 15 * 60               # une question en attente de « oui / non » expire après 15 minutes
_etats, _verrou = {}, threading.Lock()

# comparaison EXACTE (lettres doublées gardées) : « ɛɛ » = oui, mais « e » = nous (« E ti su » n'est pas qu'un oui)
_k = baoule_texte._nk
OUI = {_k(x.replace(" ", "")) for x in ["ɛɛ", "ɛɛn", "ɔɔ", "oui", "ouais", "yes", "yeah", "ok", "okay", "d'accord",
                                        "e ti su", "ɔ ti su", "eti kpa", "c'est ça", "exactement", "voilà"]}
NON = {_k(x.replace(" ", "")) for x in ["cɛcɛ", "tchɛtchɛ", "tʃɛtʃɛ", "non", "no", "pas du tout", "c'est pas ça"]}


def oui_non(texte):
    """« oui » / « non » / None pour un message COURT (3 mots au plus) : la phrase entière, ou son 1er mot suivi d'un
    seul autre (« ɛɛ kpa », « non merci »)."""
    mots = baoule_texte.mots_de(texte)
    if not mots or len(mots) > 3:
        return None
    k, premier = _k("".join(mots)), _k(mots[0])
    if k in OUI or (len(mots) <= 2 and premier in OUI):
        return "oui"
    if k in NON or (len(mots) <= 2 and premier in NON):
        return "non"
    return None


# ── état de la conversation (question en attente) ───────────────────────────────
def poser(session, **etat):
    with _verrou:
        _etats[session] = {**etat, "t": time.time()}


def en_attente(session):
    with _verrou:
        e = _etats.get(session)
        if e and time.time() - e["t"] > ATTENTE_S:
            _etats.pop(session, None)
            e = None
        return dict(e) if e else None


def oublier(session):
    with _verrou:
        _etats.pop(session, None)


# ── vérifications ──────────────────────────────────────────────────────────────
def verifier(c, dossier, appareils=()):
    """Contrôle le fond du choix de l'IA. Modifie c.details ; renvoie la liste des contrôles (journal + note)."""
    controles = []
    m = c.details.get("montant")
    if m is not None:
        entendus = {n["valeur"] for n in dossier.nombres} | nombres_dans(dossier.repare)
        if m not in entendus:
            controles.append(f"montant {m} non entendu : retiré")
            c.details["montant"] = None
    a = c.details.get("appareil")
    if a:
        trouve = baoule_demandes.trouver_appareil(a, appareils) if appareils else None
        if trouve:
            c.details["appareil_compte"] = trouve
        elif appareils:
            controles.append(f"appareil « {a} » absent du compte")
    return controles


@dataclass
class Note:
    points: int
    niveau: str                       # haute | moyenne | basse
    signaux: list = field(default_factory=list)


def note_confiance(c, dossier, controles=()):
    """Note recalculée par le code. Chaque signal est gardé (affiché dans le journal et le menu Tests)."""
    base = {"haute": 3, "moyenne": 2, "basse": 1}[c.certitude]
    signaux = [(f"avis de l'IA : {c.certitude}", base)]
    dem = baoule_demandes.CATALOGUE[c.demande]
    tr = dossier.traductions or {}
    if tr.get("accord") is not None:
        if tr["accord"] >= 0.5:
            signaux.append((f"les deux interprètes concordent ({tr['accord']:.2f})", +1))
        elif tr["accord"] < 0.2:
            signaux.append((f"les deux interprètes divergent ({tr['accord']:.2f})", -1))
    if not dossier.langue_question and not tr.get("google") and not tr.get("niutrans"):
        signaux.append(("aucun interprète n'a répondu", -1))
    for ex, s in dossier.exemples[:1]:
        if s >= 0.8 and ex["demande"] == c.demande:
            signaux.append((f"exemple vérifié très proche ({s:.0%}) de la même demande", +1))
        elif s >= 0.8:
            signaux.append((f"exemple vérifié très proche ({s:.0%}) d'une AUTRE demande ({ex['demande']})", -1))
    if dossier.mots and len(dossier.reparations) / dossier.mots >= 0.3:
        signaux.append(("beaucoup de mots réparés", -1))
    if dossier.certitude_ecoute is not None and dossier.certitude_ecoute < 0.6:
        signaux.append((f"oreille peu sûre ({dossier.certitude_ecoute:.2f})", -1))
    if dossier.mots and dossier.mots < 3 and dem.type not in ("conversation", "hors_sujet"):
        signaux.append(("message très court", -1))
    if c.hypotheses[0]["probabilite"] < 50:
        signaux.append((f"l'IA hésite ({c.hypotheses[0]['probabilite']} %)", -1))
    if any("montant" in x for x in controles):
        signaux.append(("montant non entendu", -1))
    points = sum(v for _, v in signaux)
    niveau = "haute" if points >= 3 else "moyenne" if points == 2 else "basse"
    return Note(points, niveau, signaux)


@dataclass
class Decision:
    mode: str                         # confirmer | direct | verifier | choix | hors_sujet | libre
    demande: str
    alternatives: list = field(default_factory=list)


def alternatives(c, nombre=2):
    """Les autres hypothèses de l'IA (utiles), complétées par les demandes les plus courantes."""
    # un bouton doit mener à une réponse précise : ni conversation, ni hors sujet, ni « autre question » (vu le 06/10/2026 :
    # le bouton « Autre question sur l'électricité » ne menait à rien)
    out = [h["demande"] for h in c.hypotheses[1:]
           if baoule_demandes.CATALOGUE[h["demande"]].type not in ("conversation", "hors_sujet", "libre")
           and h["demande"] != c.demande]
    for d in baoule_demandes.DEMANDES_CHOIX_PAR_DEFAUT:
        if d not in out and d != c.demande:
            out.append(d)
    return out[:nombre]


def decider(c, note):
    dem = baoule_demandes.CATALOGUE[c.demande]
    if dem.type in ("argent", "action"):
        return Decision("confirmer", c.demande, alternatives(c))
    if dem.type == "hors_sujet":
        return Decision("hors_sujet", c.demande, alternatives(c))
    if dem.type == "conversation":
        return Decision("direct", c.demande)
    if note.niveau == "basse":
        return Decision("choix", c.demande, alternatives(c))
    if dem.type == "libre":
        return Decision("libre", c.demande, alternatives(c) if note.niveau != "haute" else [])
    return Decision("direct" if note.niveau == "haute" else "verifier", c.demande, alternatives(c))
