"""Remontrer la carte de données pendant l'appel Live.

Vu par le client : l'agent montre des statistiques, on lui coupe la parole (la page ferme la carte dès que la personne reprend
la parole), on lui demande de répondre ou de « remontrer » : il disait « je vous affiche » mais rien n'apparaissait, parce que
une carte n'arrive que lorsqu'un OUTIL de données est appelé. L'outil `remontrer_carte` rejoue la dernière carte montrée, sans
rien recalculer ; la consigne dit de l'appeler avant de dire « je vous l'affiche ».
"""
from apps.ai_assistant.chatbot import live_agent

from .test_live import (FausseSession, FaussePage, FauxGemini, PontCoupure, appel_outil, lancer, reserves, tour_parle)

SPECS = []


class Enchainee(FausseSession):
    """Un tour de plus APRÈS chaque réponse d'outil (comme le vrai appel : le modèle ne rappelle un outil qu'une fois le précédent rendu)."""
    def __init__(self, premier, suivants):
        super().__init__([premier])
        self.suivants = list(suivants)

    def _apres(self):
        if self.suivants:
            self.tours.put_nowait(self.suivants.pop(0))


def test_remontrer_carte_est_proposee_a_gemini_sans_argument():
    d = {x.name: x.parameters_json_schema for x in live_agent.declarations(SPECS)}
    assert "remontrer_carte" in d and d["remontrer_carte"]["properties"] == {} and d["remontrer_carte"]["required"] == []


def test_la_consigne_interdit_de_dire_je_vous_l_affiche_sans_appel():
    c = live_agent.consigne("auto")
    assert "remontrer_carte" in c and "sans appel, rien n'apparaît à l'écran" in c
    assert "REPRENDS ton explication après une interruption" in c


def test_la_derniere_carte_est_rejouee_a_la_page_sans_recalcul():
    page = FaussePage()
    s = Enchainee(appel_outil("conso_periode", {"date_debut": "2026-10-01"}), [appel_outil("remontrer_carte"), tour_parle("Voilà.")])
    lancer(page, FauxGemini([s]), reserves())
    cartes = [d for d in page.recu if d["type"] == "outil"]
    assert [c["nom"] for c in cartes] == ["conso_periode", "remontrer_carte"]
    assert cartes[1]["carte"] == cartes[0]["carte"] and cartes[1]["carte"]["type"] == "conso" and cartes[1]["carte"]["kwh"] == 127.63
    retour = s.reponses_outils[1].response["resultat"]                     # Gemini apprend que la carte est revenue
    assert retour["ok"] and retour["montree"] == "Consommation" and "de nouveau à l'écran" in retour["a_savoir"]


def test_remontrer_sans_rien_avoir_montre_dit_la_verite():
    page = FaussePage()
    s = FausseSession([appel_outil("remontrer_carte"), tour_parle("Je n'ai encore rien montré.")])
    lancer(page, FauxGemini([s]), reserves())
    assert not [d for d in page.recu if d["type"] == "outil"]               # rien ne s'affiche
    assert "Aucune carte" in s.reponses_outils[0].response["resultat"]["erreur"]


def test_une_demande_de_coupure_ne_se_rejoue_jamais():
    """La carte Oui / Non d'une coupure expire et appartient à la personne : « remontre » ne doit pas la redemander."""
    page = FaussePage()
    s = Enchainee(appel_outil("preparer_coupure", {"appareil": "prise", "action": "couper"}),
                  [appel_outil("remontrer_carte"), tour_parle("Je n'ai rien d'autre à montrer.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert [d["nom"] for d in page.recu if d["type"] == "outil"] == ["preparer_coupure"]   # une seule carte : la demande d'origine
    assert "Aucune carte" in s.reponses_outils[1].response["resultat"]["erreur"]
