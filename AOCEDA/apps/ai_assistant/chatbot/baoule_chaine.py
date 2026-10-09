"""La CHAÎNE ROBUSTE du baoulé (06/10/2026) : un message suit UN seul passage, en 4 blocs.

  A. savoir ce qui a été dit   : écoute (déjà faite) -> réparation contrôlée par le son -> deux interprètes ;
  B. savoir ce que la personne veut : raccourci oui/non (code) OU cerveau IA qui classe dans la liste fermée ;
  C. décider (le règlement)    : vérifications, note de confiance, règle de réponse (confirmer, répondre, proposer) ;
  D. répondre                  : vraies données AOCEDA -> phrases françaises -> baoulé contre-vérifié -> voix.
Autour : pannes (chaque service a un secours), mémoire (liste d'attente des phrases confirmées), journal de mesure.

Événements envoyés à la page (mêmes que l'ancien chemin, plus « boutons ») :
  langue, intention {texte, certitude, demande}, morceau {texte baoulé, traduit, controle}, francais {texte},
  boutons {oui_non, choix: [{demande, libelle}]}, fin {...}, puis bilan (journal seulement).
"""
import json
import threading
import time

from . import (baoule_comprendre, baoule_decider, baoule_demandes, baoule_memoire, baoule_repondre, conversation,
               salutations, service_dioula, voix)
from .baoule_demandes import Phrase

_variantes, _verrou = {}, threading.Lock()


def _variante(session, demande):
    """Numéro de tournure : jamais deux fois la même réponse d'affilée dans une conversation."""
    with _verrou:
        d = _variantes.setdefault(session, {})
        d[demande] = d.get(demande, -1) + 1
        if len(_variantes) > 5000:
            _variantes.clear()
        return d[demande]


def lecteur():
    """Lecture des données AOCEDA du client qui pose la question (lecture seule), une seule fois par outil et par
    message."""
    from .donnees_client import courantes
    donnees, cache = courantes(), {}

    def lire(nom, args):
        k = (nom, json.dumps(args or {}, sort_keys=True))
        if k not in cache:
            cache[k] = (donnees.executer(nom, args or {})[0] if donnees
                        else {"erreur": "Données AOCEDA indisponibles : aucun compte client pour cette question."})
        return cache[k]
    return lire


def _appareils(lire):
    r = lire("etat_capteurs", {})
    return [c["nom"] for c in r.get("capteurs", [])] if isinstance(r, dict) and "erreur" not in r else []


def _contenu(demande, details, lire, session):
    d = baoule_demandes.CATALOGUE[demande]
    if d.contenu is None:
        return baoule_demandes.CATALOGUE["hors_sujet"].contenu(details, lire, 0)
    try:
        return d.contenu(details, lire, _variante(session, demande))
    except Exception:                                   # une donnée inattendue ne doit jamais faire tomber la réponse
        return baoule_demandes.indisponible()


def _choix(ids):
    return [{"demande": i, "libelle": baoule_demandes.CATALOGUE[i].libelle} for i in ids if i in baoule_demandes.CATALOGUE]


QUESTION_VERIF = Phrase("Est-ce bien ce que vous vouliez savoir ?")
PROPOSER = Phrase("Vous parlez peut-être d'autre chose : choisissez ci-dessous.")


def _apres_bouton(session, texte, action, etat, lire):
    """Réponse à un bouton (choix, oui, non) ou à un « oui / non » dit dans la conversation. Renvoie un dict de réponse.
    Liste d'attente des exemples (audit du 09/10/2026) : seule une VRAIE phrase baoulé y entre (« bci » vide pour une
    question posée en français), et un choix n'y entre que s'il faisait partie des choix PROPOSÉS après une hésitation
    (« Vous parlez peut-être d'autre chose », « Pardon, je me suis trompé ») : pas après un refus d'ordre ni un hors-sujet."""
    valeur = (action or {}).get("type") or baoule_decider.oui_non(texte)
    texte_origine = (etat or {}).get("bci", "")
    if valeur == "choix":
        dem = action.get("demande")
        if dem not in baoule_demandes.CATALOGUE:
            return None
        propose = bool(etat) and etat.get("type") == "choix" and dem in (etat.get("alternatives") or [])
        details = (etat or {}).get("details", {}) if propose else {}
        if texte_origine and propose and etat.get("apprendre"):
            baoule_memoire.ajouter_attente(texte_origine, dem, "choix", baoule_demandes.CATALOGUE[dem].libelle)
        baoule_decider.oublier(session)
        d = baoule_demandes.CATALOGUE[dem]
        if d.confirmer:
            baoule_decider.poser(session, type="confirmation", demande=dem, details=details, bci=texte_origine,
                                 alternatives=[])
            return {"phrases": [d.confirmer(details)], "demande": dem, "mode": "confirmer", "oui_non": True, "choix": [],
                    "intention": d.libelle, "certitude": "haute", "source": "bouton"}
        if d.type == "libre":
            return None
        return {"phrases": _contenu(dem, details, lire, session), "demande": dem, "mode": "direct", "oui_non": False,
                "choix": [], "intention": d.libelle, "certitude": "haute", "source": "bouton"}
    if valeur not in ("oui", "non") or not etat:
        return None
    dem, details = etat.get("demande"), etat.get("details", {})
    d = baoule_demandes.CATALOGUE.get(dem)
    baoule_decider.oublier(session)
    base = {"demande": dem, "oui_non": False, "choix": [], "certitude": "haute", "source": f"réponse « {valeur} »"}
    if etat["type"] == "confirmation" and d:
        if valeur == "oui":
            if texte_origine:
                baoule_memoire.ajouter_attente(texte_origine, dem, "oui", d.libelle)
            return {**base, "phrases": d.apres_oui(details, lire), "mode": "execute", "intention": f"{d.libelle} : confirmé"}
        alts = etat.get("alternatives") or list(baoule_demandes.DEMANDES_CHOIX_PAR_DEFAUT)
        # refus d'un ordre : la personne a pu changer d'avis, son choix suivant ne dit pas ce que voulait sa phrase
        baoule_decider.poser(session, type="choix", demande=dem, details=details, bci=texte_origine, alternatives=alts,
                             apprendre=False)
        return {**base, "phrases": [Phrase("D'accord, je ne fais rien."), PROPOSER], "mode": "annule", "choix": _choix(alts),
                "intention": f"{d.libelle} : annulé"}
    if etat["type"] == "verification" and d:
        if valeur == "oui":
            if texte_origine:
                baoule_memoire.ajouter_attente(texte_origine, dem, "oui", d.libelle)
            return {**base, "phrases": [Phrase("Très bien."), Phrase("Avez-vous une autre question ?")], "mode": "confirme",
                    "intention": f"{d.libelle} : confirmé"}
        alts = etat.get("alternatives") or list(baoule_demandes.DEMANDES_CHOIX_PAR_DEFAUT)
        # « Choisissez ce que vous vouliez savoir » : le choix suivant corrige le sens de sa phrase (exemple utile)
        baoule_decider.poser(session, type="choix", demande=dem, details=details, bci=texte_origine, alternatives=alts,
                             apprendre=True)
        return {**base, "phrases": [Phrase("Pardon, je me suis trompé."), Phrase("Choisissez ce que vous vouliez savoir.")],
                "mode": "corrige", "choix": _choix(alts), "intention": "Pas la bonne demande"}
    return None


def _comprendre(session, texte, origine, langue_question, liste, lire, historique):
    """Blocs A + B + C pour un message normal. Renvoie (réponse, journal) ; lève ComprehensionImpossible."""
    vocal = service_dioula._vocal_de(session, texte) if origine == "vocal" else None
    dossier = baoule_comprendre.preparer_dossier(texte, vocal, langue_question, historique)
    c = baoule_comprendre.classer(dossier, liste)
    controles = baoule_decider.verifier(c, dossier, _appareils(lire))
    note = baoule_decider.note_confiance(c, dossier, controles)
    dec = baoule_decider.decider(c, note)
    d = baoule_demandes.CATALOGUE[dec.demande]
    rep = {"demande": dec.demande, "mode": dec.mode, "oui_non": False, "choix": [], "certitude": note.niveau,
           "intention": c.reformulation or d.libelle, "source": "cerveau IA"}
    # « bci » = la phrase BAOULÉ de la personne (gardée pour la liste d'exemples si elle confirme) ; une question posée en
    # français ou en anglais n'est pas un exemple baoulé (audit du 09/10/2026 : « Je veux recharger cinq mille francs. »
    # était enregistré comme phrase baoulé)
    garder = dict(demande=dec.demande, details=c.details, bci="" if dossier.langue_question else dossier.repare,
                  alternatives=dec.alternatives)
    if dec.mode == "confirmer":
        rep["phrases"] = [d.confirmer(c.details)]
        rep["oui_non"] = True
        baoule_decider.poser(session, type="confirmation", **garder)
    elif dec.mode == "libre":
        question = c.reformulation or (dossier.traductions or {}).get("google") or texte
        try:
            rep["phrases"] = baoule_repondre.reponse_libre(question, liste)
        except Exception:
            rep["phrases"] = _contenu("hors_sujet", c.details, lire, session)
        if dec.alternatives:
            rep["phrases"].append(QUESTION_VERIF)
            rep["oui_non"] = True
            baoule_decider.poser(session, type="verification", **garder)
        else:
            # aucune question posée : une attente plus ancienne ne doit pas survivre (audit du 09/10/2026 : un « ɛɛ » dit
            # plus tard validait une recharge demandée deux messages avant)
            baoule_decider.oublier(session)
    else:
        rep["phrases"] = _contenu(dec.demande, c.details, lire, session)
        if dec.mode == "verifier":
            rep["phrases"].append(QUESTION_VERIF)
            rep["oui_non"] = True
            baoule_decider.poser(session, type="verification", **garder)
        elif dec.mode in ("choix", "hors_sujet"):
            if dec.mode == "choix":
                rep["phrases"] = rep["phrases"][:2] + [PROPOSER]
            rep["choix"] = _choix(dec.alternatives)
            # « choix » (pas sûr) : le bouton choisi dit ce que voulait la phrase ; « hors_sujet » : ce sont de simples idées
            baoule_decider.poser(session, type="choix", apprendre=dec.mode == "choix", **garder)
        else:
            baoule_decider.oublier(session)
    journal = {"dossier": dossier.texte, "dossier_s": dossier.duree_s, "ia": c.brut, "ia_essais": c.essais,
               "ia_s": c.duree_s, "hypotheses": c.hypotheses, "details": c.details, "controles": controles,
               "note": {"points": note.points, "niveau": note.niveau, "signaux": note.signaux},
               "decision": {"mode": dec.mode, "alternatives": dec.alternatives},
               "reparations": dossier.reparations, "traductions": dossier.traductions,
               "exemples": [(e["bci"], e["demande"], s) for e, s in dossier.exemples]}
    return rep, journal


def _secours(session, texte, origine, genre, liste, source_langue, langue_question, raison):
    """L'ANCIEN chemin libre prend le relais (sans répéter l'événement « langue », déjà envoyé)."""
    from . import service_baoule
    for ev in service_baoule.repondre_libre(session, texte, origine, genre, liste, source_langue=source_langue,
                                            langue_question=langue_question):
        if ev["type"] == "bilan":
            ev["chaine"] = {"secours": raison[:200]}
        if ev["type"] != "langue":
            yield ev


def repondre(session, texte, origine="ecrit", genre="femme", liste=None, source_langue="baoulé", langue_question=None,
             action=None, lire=None, voix_auto=True):
    """La chaîne, protégée : une erreur IMPRÉVUE n'arrête jamais la réponse en silence (vu le 06/10/2026 : « Réponse
    interrompue » sans aucune trace). Avant la 1re phrase : l'ancien chemin prend le relais ; après : un vrai message
    d'erreur. Dans les deux cas, le détail est écrit dans journaux/erreurs.log.
    voix_auto : la page va lire la réponse toute seule (lecture automatique) -> sa voix part tout de suite sur le GPU ;
    sinon elle n'est fabriquée que si quelqu'un appuie sur Écouter (GPU payant)."""
    phrase_envoyee = False
    try:
        for ev in _repondre(session, texte, origine, genre, liste, source_langue, langue_question, action, lire, voix_auto):
            phrase_envoyee = phrase_envoyee or ev["type"] == "morceau"
            yield ev
    except Exception as e:
        from . import erreurs
        erreurs.noter("chaîne baoulé", e, texte)
        if phrase_envoyee:
            yield {"type": "erreur", "texte": "La réponse s'est arrêtée à cause d'un problème technique. Réessayez.",
                   "essais": []}
            return
        yield from _secours(session, texte, origine, genre, liste, source_langue, langue_question,
                            f"erreur imprévue : {type(e).__name__} : {e}")


def _repondre(session, texte, origine="ecrit", genre="femme", liste=None, source_langue="baoulé", langue_question=None,
              action=None, lire=None, voix_auto=True):
    t0 = time.time()
    lire = lire or lecteur()
    yield {"type": "langue", "code": "bci", "source": source_langue, "confiance": 1.0}
    historique = conversation.historique(session)
    etat = baoule_decider.en_attente(session)
    journal = {}
    rep = _apres_bouton(session, texte, action, etat, lire) if (action or etat) else None
    if rep is None:
        # ni un oui/non ni un bouton : c'est une NOUVELLE question, la question en attente tombe (elle ne doit jamais être
        # validée plus tard par un « ɛɛ » qui répondrait à autre chose)
        baoule_decider.oublier(session)
        try:
            rep, journal = _comprendre(session, texte, origine, langue_question, liste, lire, historique)
        except baoule_comprendre.ComprehensionImpossible as e:
            # SECOURS : le cerveau IA n'a pas répondu dans le format (deux fois) -> ancien chemin libre
            yield from _secours(session, texte, origine, genre, liste, source_langue, langue_question, str(e))
            return
    yield {"type": "intention", "texte": rep["intention"], "certitude": rep["certitude"], "demande": rep["demande"]}

    resultats, premiere = [], None
    # 1re réponse de la conversation, ou la personne salue : la salutation de l'heure en tête, directement en baoulé
    # (09/10/2026) : « Aɲiho » / « Manti » / « Anun o » ; si la personne a salué, la formule de RÉPONSE (« Arɛ o » /
    # « Aanti o » / « Awossi'n o »). Une salutation écrite par le cerveau IA (réponse libre) est alors retirée : jamais deux fois
    recu = salutations.salutation_recue("bci", texte)                  # « Anun o » -> on répond « Awossi'n o »
    salue = rep["demande"] == "saluer" or recu is not None
    if not historique or (salue and rep.get("source") == "cerveau IA"):
        bci, fr = salutations.locale("bci", reponse=salue, genre=genre, moment_recu=recu)
        if rep["phrases"]:
            p0 = rep["phrases"][0]
            reste = salutations.retirer_salutation(p0.fr).strip()
            rep["phrases"] = ([Phrase(reste, p0.nombres, p0.cles, p0.sens)] if reste else []) + rep["phrases"][1:]
        resultats.append({"fr": fr, "bci": bci, "controle": "formule", "retour": None, "manques": [], "service": "formule"})
        yield {"type": "morceau", "texte": bci, "traduit": True, "controle": "formule"}
        yield {"type": "francais", "texte": fr}
    for r in baoule_repondre.traduire_flux(rep["phrases"]):             # chaque phrase part dès qu'elle est prête
        resultats.append(r)
        if premiere is None:
            premiere = round(time.time() - t0, 2)
        sep = " " if len(resultats) > 1 else ""
        yield {"type": "morceau", "texte": sep + r["bci"], "traduit": r["controle"] != "non_traduite", "controle": r["controle"]}
        yield {"type": "francais", "texte": sep + r["fr"]}
    if rep["oui_non"] or rep["choix"]:
        yield {"type": "boutons", "oui_non": rep["oui_non"], "choix": rep["choix"]}

    reponse_bci = " ".join(r["bci"] for r in resultats).strip()
    reponse_fr = " ".join(r["fr"] for r in resultats).strip()
    non_traduit = sum(1 for r in resultats if r["controle"] == "non_traduite")
    douteuses = sum(1 for r in resultats if r["controle"] == "douteuse")
    non_verifiees = sum(1 for r in resultats if r["controle"] == "non_verifiee")
    reponse = [r for r in resultats if r["controle"] != "formule"]       # la salutation n'est pas une traduction
    langue_voix = "fr" if reponse and non_traduit == len(reponse) else "bci"
    if langue_voix == "fr" and len(reponse) < len(resultats):          # tout en français : « Bonsoir. » en français aussi
        resultats[0] = {**resultats[0], "bci": resultats[0]["fr"]}
        reponse_bci = " ".join(r["bci"] for r in resultats).strip()
    conversation.ajouter_question(session, f"[baoulé] « {texte} » -> {rep['intention']}")
    conversation.ajouter_reponse(session, reponse_fr)
    conversation.noter_langue(session, "bci")
    morceaux = voix.decouper(reponse_bci)
    conversation.autoriser_voix(session, morceaux + [voix.texte_pour_voix(reponse_bci)])
    if langue_voix == "bci" and reponse_bci:
        if voix_auto:                                # GPU : la voix part tout de suite, prête quand la page la lit seule
            voix.annoncer_baoule(reponse_bci)
    else:
        voix.preparer(morceaux, langue_voix, genre)
    fin = {"type": "fin", "texte": reponse_bci, "francais": reponse_fr, "intention": rep["intention"],
           "certitude": rep["certitude"], "demande": rep["demande"], "mode": rep["mode"], "premiere_phrase_s": premiere,
           "total_s": round(time.time() - t0, 2), "traducteurs": [r["service"] for r in resultats], "relance": False,
           "non_traduit": non_traduit, "douteuses": douteuses, "non_verifiees": non_verifiees, "langue_voix": langue_voix,
           "controles": [r["controle"] for r in resultats], "fournisseur": "chaîne robuste", "modele": "baoulé"}
    yield fin
    yield {"type": "bilan", "langue_reponse": "bci", "source_langue": source_langue, "refaites": 0, "fin": fin,
           "duree_s": round(time.time() - t0, 2), "dossier": journal.get("dossier", ""), "intention": rep["intention"],
           "certitude": rep["certitude"], "traduction_aller_s": journal.get("dossier_s"),
           "chaine": {**{k: v for k, v in journal.items() if k != "dossier"}, "mode": rep["mode"], "source": rep["source"],
                      "demande": rep["demande"], "retours": [{"fr": r["fr"], "retour": r["retour"], "manques": r["manques"],
                                                              "controle": r["controle"]} for r in resultats]}}
