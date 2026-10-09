"""Orchestrateur d'une question : langue -> historique -> DeepSeek -> contrôle de langue -> préparation de la voix.

Le serveur web ne fait plus que transmettre : toute la logique d'une question est ici (et pourra être
branchée telle quelle dans AOCEDA).

Choix de la langue de la réponse, par ordre de priorité (05/10/2026, retour client : « si je lui dis de répondre en
anglais, toutes ses réponses doivent être en anglais, même si je parle français, jusqu'à ce que je change ») :
  1. langue demandée explicitement dans CE message (« réponds-moi en anglais »), même si le menu dit autre chose ;
  2. langue demandée plus tôt dans la conversation, retenue tant que la personne ne change ni de demande ni de menu
     (un changement de menu l'efface : c'est le dernier choix qui compte) ;
  3. langue choisie dans le menu de la page ;
  4. langue détectée du message (écrit) ou entendue au micro (vocal) ;
  5. langue précédente de la conversation (messages courts : « ok », « merci »).
Une langue que le chatbot ne parle pas (« réponds en agni ») : on le dit honnêtement, on n'invente jamais.
Le DIOULA et le BAOULÉ (langues relais : DeepSeek ne les parle pas bien) partent vers service_dioula / service_baoule,
qui passent par le français.
"""
import time

from . import (baoule_decider, baoule_lexique, baoule_relais, baoule_texte, consignes, conversation, detection,
               dioula_texte, fournisseurs, garde_langue, langues, salutations, service_baoule, service_dioula, voix)

SERVICES_RELAIS = {"dyu": service_dioula, "bci": service_baoule}

MAX_REFAITES = 1   # une réponse partie dans la mauvaise langue est refaite une seule fois


def choisir_langue(session, texte, langue_menu, indice):
    """Renvoie (langue_reponse, source, confiance)."""
    demandee = garde_langue.demande_explicite(texte)
    conversation.noter_menu(session, langue_menu)             # menu changé depuis le dernier message : demande oubliée
    if demandee:
        conversation.noter_langue(session, demandee, imposee=True)
        return demandee, "demandée", 1.0
    imposee = conversation.langue_imposee(session)
    if imposee and langue_menu in langues.RELAIS and imposee != langue_menu and parle_relais(texte, indice) == langue_menu:
        # menu sur baoulé (ou dioula) ET la personne parle cette langue : c'est elle qui compte, l'ancienne demande tombe
        # (05/10, soir : un verrou « français » faisait répondre en français à des messages en baoulé, menu Baoulé)
        conversation.oublier_langue_imposee(session)
        imposee = None
    if imposee:
        return imposee, "demandée plus tôt", 1.0
    if langue_menu != "auto":
        return langue_menu, "menu", 1.0
    if indice in langues.RELAIS:
        return indice, "entendue (vocal)", 1.0
    dioula, score = dioula_texte.est_dioula(texte)
    locale, score_bci, _ = baoule_texte.langue_locale(texte)
    precedente = conversation.langue(session)
    code, confiance, source = detection.langue_du_message(texte, precedente, indice)
    # py3langid très sûr d'une langue directe et signal dioula faible, sans lettre ɛ ɔ ɲ ŋ : c'est cette langue
    # (mesuré : « Éteins le ventilateur du salon » était pris pour du dioula, py3langid disait français à 0,98)
    sur_d_autre = (code in langues.LANGUES and code != "sw" and source == "détectée" and confiance >= 0.95
                   and score < 0.6 and score_bci < 0.6 and not dioula_texte.LETTRES_MANDING.search(texte or ""))
    if not sur_d_autre:
        # baoulé et dioula partagent l'écriture (ɛ ɔ) et beaucoup de petits mots : on tranche sur leurs mots PROPRES
        # (baoule_texte.langue_locale) avant la détection du dioula, qui compte aussi les lettres
        if locale in ("bci", "dyu"):
            return locale, "détectée", score_bci if locale == "bci" else score
        # « ɛɛ », « a ka di », « merci » dans une conversation en langue locale : on reste dans cette langue
        if precedente in langues.RELAIS and (dioula or score > 0 or score_bci > 0 or source in ("conversation", "inconnue")):
            return precedente, "conversation", max(score, score_bci)
    if dioula and not sur_d_autre:
        return "dyu", "détectée", score
    # traces de dioula et py3langid perdu (ou « swahili », qu'il confond avec le dioula) : dioula
    if score > 0 and not sur_d_autre and (code is None or code == "sw" or source in ("détectée (faible)", "inconnue")):
        return "dyu", "détectée (traces)", score
    return code, source, confiance


def parle_relais(texte, indice):
    """Le message est-il en baoulé ou en dioula ? (« bci » / « dyu » / None) : la voix l'a entendu dans cette langue, ou
    le texte a ses mots propres."""
    if indice in langues.RELAIS:
        return indice
    locale = baoule_texte.langue_locale(texte)[0]
    if locale in langues.RELAIS:
        return locale
    return "dyu" if dioula_texte.est_dioula(texte)[0] else None


def langue_de_la_question(texte, indice):
    """Réponse demandée en dioula/baoulé, mais question posée dans une langue directe (français, anglais...) ?
    Renvoie ce code, sinon None. (Vu le 30/09/2026 : menu Baoulé + question dite en français -> la question était
    « traduite » du baoulé vers le français et présentée à DeepSeek comme du baoulé.)"""
    if indice in langues.LANGUES:
        return indice
    code, confiance = detection.detecter(texte)
    if (code in langues.LANGUES and confiance >= 0.95 and baoule_texte.langue_locale(texte)[0] is None
            and not dioula_texte.est_dioula(texte)[0] and not dioula_texte.LETTRES_MANDING.search(texte or "")):
        return code
    return None


def repondre(session, texte, langue_menu="auto", indice=None, genre="femme", liste=None, origine="ecrit", action=None,
             voix_auto=True):
    """Générateur d'événements pour la page (mêmes événements que fournisseurs.repondre_flux, plus
    {"type": "langue"} au début). Enregistre la conversation et prépare la voix.
    `liste` remplace les fournisseurs (tests). `action` : bouton cliqué sous une réponse baoulé (oui, non, choix).
    `voix_auto` : la page va lire la réponse toute seule (la voix baoulé, payante sur le GPU, part alors tout de suite).
    À la fin, l'événement « bilan » (non envoyé à la page) résume."""
    if action and (action.get("type") == "choix" or baoule_decider.en_attente(session) is not None):
        # bouton sous une réponse baoulé : son texte (« Mon crédit ») est en français, mais la conversation reste en baoulé
        yield from service_baoule.repondre(session, texte, origine, genre, liste, source_langue="bouton", action=action,
                                           voix_auto=voix_auto)
        return
    langue_reponse, source, confiance = choisir_langue(session, texte, langue_menu, indice)
    if langues.est_relais(langue_reponse):
        args = {"action": action, "voix_auto": voix_auto} if langue_reponse == "bci" else {}
        yield from SERVICES_RELAIS[langue_reponse].repondre(session, texte, origine, genre, liste, source_langue=source,
                                                            langue_question=langue_de_la_question(texte, indice), **args)
        return
    historique, question_id = conversation.poser_question(session, texte)
    if source not in ("menu", "demandée", "demandée plus tôt"):
        conversation.noter_langue(session, langue_reponse)
    forcee = langue_reponse if source in ("menu", "demandée", "demandée plus tôt") else None
    systeme = consignes.systeme(forcee or "auto", detectee=None if forcee else langue_reponse)
    # 1re réponse de la conversation : « Bonjour » / « Bonsoir » selon l'heure, dans la langue de la réponse ; ensuite,
    # plus de salutation, sauf pour rendre la sienne à la personne qui salue (09/10/2026, demande du client)
    systeme += (salutations.consigne_debut(texte=texte) if len(historique) == 1
                else salutations.consigne_suite(texte))
    non_prise = garde_langue.langue_demandee(texte)["non_prise"]
    if non_prise:                                    # « réponds en agni » : on le dit, on n'invente jamais
        systeme += garde_langue.note_langue_non_prise(non_prise)
    # « comment dit-on salut en baoulé ? » : ce que dit VRAIMENT le carnet de mots (recherche par le sens, sources
    # libres) ; le cerveau IA ne doit inventer aucun mot baoulé (06/10/2026)
    vocabulaire = baoule_lexique.note_vocabulaire(texte, baoule_relais.vers_anglais)
    if vocabulaire:
        systeme += vocabulaire
    if forcee in langues.LANGUES and historique:
        # mesuré le 05/10/2026 (vrai DeepSeek) : menu passé à l'espagnol après des échanges en français et en anglais ->
        # réponse en français, même refaite avec la consigne. Le rappel placé à la fin du DERNIER message (juste avant
        # la réponse) suffit ; il n'est envoyé qu'au modèle, jamais gardé dans la conversation.
        nom = langues.nom(forcee).lower()
        historique = historique[:-1] + [{**historique[-1], "texte": f"{historique[-1]['texte']}\n\n(Réponds en {nom}, "
                                                                     f"{langues.LANGUES[forcee][1]}.)"}]
    lg_voix = langue_reponse if langue_reponse in langues.LANGUES else None
    yield {"type": "langue", "code": langue_reponse, "source": source, "confiance": round(confiance or 0, 2),
           **({"non_prise": non_prise} if non_prise else {})}

    fin, refaites, t0 = None, 0, time.time()
    try:
        while True:
            ecrit, premier_prepare, controle_fait, refaire = "", None, False, None
            flux = fournisseurs.repondre_flux(systeme, historique, liste=liste)
            try:
                for ev in flux:
                    if ev["type"] == "morceau":
                        ecrit += ev["texte"]
                        if not controle_fait and len(ecrit) >= 120:       # contrôle dès le début de la réponse
                            controle_fait = True
                            refaire = garde_langue.mauvaise_langue(ecrit, langue_reponse)
                            if refaire and refaites < MAX_REFAITES:
                                break
                            refaire = None
                        if premier_prepare is None:    # 1re phrase finie : sa voix se prépare déjà (genre choisi d'abord)
                            premier_prepare = voix.premier_morceau_si_complet(ecrit)
                            if premier_prepare:
                                conversation.autoriser_voix(session, [premier_prepare])
                                voix.preparer([premier_prepare], lg_voix, genre)
                    elif ev["type"] == "recommencer":
                        ecrit, premier_prepare = "", None
                    elif ev["type"] == "fin":
                        refaire = garde_langue.mauvaise_langue(ev["texte"], langue_reponse)
                        if refaire and refaites < MAX_REFAITES:
                            break
                        refaire = None
                        conversation.ajouter_reponse(session, ev["texte"])
                        morceaux = voix.decouper(ev["texte"])
                        conversation.autoriser_voix(session, morceaux)
                        voix.preparer([m for m in morceaux if m != premier_prepare], lg_voix, genre)
                        fin = ev
                    elif ev["type"] == "erreur":
                        conversation.annuler_question(session, question_id)
                        fin = ev
                    yield ev
            finally:
                flux.close()                    # arrête vraiment la demande DeepSeek en cours
            if refaire and not fin:
                refaites += 1
                systeme = systeme + garde_langue.rappel(langue_reponse)
                yield {"type": "recommencer", "raison": f"réponse partie en « {refaire} » au lieu de « {langue_reponse} » : refaite"}
                continue
            break
    finally:
        if fin is None:                          # réponse arrêtée par l'utilisateur ou connexion coupée : CETTE question
            conversation.annuler_question(session, question_id)
    yield {"type": "bilan", "langue_reponse": langue_reponse, "source_langue": source, "refaites": refaites,
           "fin": fin, "duree_s": round(time.time() - t0, 2)}
