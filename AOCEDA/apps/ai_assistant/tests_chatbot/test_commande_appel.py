"""Boutons de l'appel Live commandés par la voix (demande du client : « dis-lui de passer en écran, d'activer la caméra… »).

L'outil `commande_appel(bouton, etat)` est proposé à Gemini, décrit dans la consigne, et sa demande est transmise telle quelle à
la page (qui fait le geste : micro, caméra, écran, clavier). Le Raccrocher passe par `terminer_appel`, qui existait déjà.
La page elle-même (static/js/assistant.js) est vérifiée dans un navigateur : voir docs/refonte/00-journal.md.
"""
from pathlib import Path

from apps.ai_assistant.chatbot import live_agent

from .test_live import FausseSession, FaussePage, FauxGemini, appel_outil, lancer, reserves, tour_parle

SPECS = []


def test_commande_appel_est_proposee_a_gemini_avec_ses_quatre_boutons():
    d = {x.name: x.parameters_json_schema for x in live_agent.declarations(SPECS)}
    assert "commande_appel" in d and "terminer_appel" in d
    p = d["commande_appel"]
    assert p["required"] == ["bouton"]                                           # « etat » omis = bascule
    assert p["properties"]["bouton"]["enum"] == ["micro", "camera", "ecran", "ecrire"]
    assert p["properties"]["etat"]["enum"] == ["activer", "desactiver"]


def test_la_consigne_dit_de_commander_les_boutons_et_de_ne_pas_dire_c_est_fait_sans_ok():
    c = live_agent.consigne("auto")
    assert "commande_appel(bouton, etat)" in c
    assert "Ne dis jamais « c'est fait » sans « ok »" in c
    assert "a_faire" in c and "Muet" in c                                        # partage d'écran exigeant un appui ; micro coupé
    assert "commande_appel(ecran, activer)" in c
    assert "réservé à la personne (effacer l'historique)" in c                   # le micro, la caméra... ne le sont plus


def test_la_demande_est_transmise_a_la_page_et_sa_reponse_revient_a_gemini():
    reponse = {"ok": False, "a_faire": "le navigateur exige que la personne touche elle-même le bouton « Écran »"}
    page = FaussePage(reponses={"commande_appel": reponse})
    s = FausseSession([appel_outil("commande_appel", {"bouton": "ecran", "etat": "activer"})], apres_outil=tour_parle("Touchez Écran."))
    lancer(page, FauxGemini([s]), reserves())
    envoyes = [d for d in page.recu if d["type"] == "page"]
    assert envoyes and envoyes[0]["nom"] == "commande_appel" and envoyes[0]["args"] == {"bouton": "ecran", "etat": "activer"}
    retours = [r for r in s.reponses_outils if r]
    assert any("a_faire" in str(r) for r in retours)                             # Gemini reçoit la raison : il ne dit pas « c'est fait »


def test_la_page_sait_executer_commande_appel_et_ne_garde_plus_que_l_interdit_necessaire():
    js = (Path(__file__).resolve().parents[3] / "static" / "js" / "assistant.js").read_text(encoding="utf-8")
    assert "commande_appel: async ({ bouton, etat })" in js
    assert 'new Set(["lire_ecran", "afficher_appel", "ecran_entier", "carte", "commande_appel"])' in js   # l'appel n'est pas réduit d'abord
    assert "function microLive(actif)" in js and 'onclick = () => microLive(!LIVE.micro)' in js        # même geste que le bouton
    assert "navigator.userActivation" in js                                      # le partage d'écran exige un vrai appui (navigateur)
