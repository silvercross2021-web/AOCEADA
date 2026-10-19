"""Coupure de courant dans l'appel Live : carte Oui / Non jamais annoncée à tort, et réponse « oui » / « non » à la VOIX.

Vu le 19/10/2026 : « éteindre la prise » -> l'agent répond « Veuillez appuyer sur Oui ou Non sur l'écran » alors qu'il n'avait
appelé que etat_capteurs : aucune carte n'existait. Puis la personne a demandé de pouvoir dire « oui » / « non » sans toucher.
La décision est prise par le SERVEUR d'après la voix transcrite (l'agent ne confirme jamais à sa place) ; la page fait ensuite
comme si la personne avait touché le bouton (même chemin, mêmes droits).
"""
import pytest
from google.genai import types

from apps.ai_assistant.chatbot import live_agent

from .test_live import FausseSession, FaussePage, FauxGemini, PontCoupure, appel_outil, lancer, msg, reserves, tour_parle
from .test_remontrer_carte import Enchainee


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    monkeypatch.setattr(live_agent, "CONFIRMATION_VOCALE_S", 0.0)


class ApresOutil(Enchainee):
    """Après la RÉPONSE de l'outil, tous les tours suivants se jouent d'affilée (l'agent parle, puis la personne répond...)."""
    def _apres(self):
        while self.suivants:
            self.tours.put_nowait(self.suivants.pop(0))


def vous_dit(texte):
    """La personne parle (transcription de sa voix), puis l'agent commence à répondre."""
    return [msg(server_content=types.LiveServerContent(input_transcription=types.Transcription(text=texte)))] + tour_parle("D'accord.")


def agent_dit(texte):
    return [msg(server_content=types.LiveServerContent(
        output_transcription=types.Transcription(text=texte),
        model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=b"\x00\x01" * 50, mime_type="audio/pcm"))]))),
        msg(server_content=types.LiveServerContent(turn_complete=True))]


COUPER = appel_outil("preparer_coupure", {"appareil": "prise", "action": "couper"})


def confirmations(page):
    return [d["reponse"] for d in page.recu if d["type"] == "confirmer_coupure"]


# ── Ce que dit la personne ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dit,attendu", [
    ("oui", "oui"), ("Oui, oui !", "oui"), ("vas-y", "oui"), ("je confirme", "oui"), ("Oui s'il te plaît", "oui"), ("oui merci", "oui"),
    ("euh oui bon", "oui"), ("non", "non"), ("non annule", "non"), ("Non merci, laisse tomber", "non"), ("annule", "non"),
    # jamais décidé : mélange, condition, écho de l'agent, phrase longue, autre sujet
    ("oui mais pas la prise", None), ("oui ou non ?", None), ("oui non", None), ("Veuillez appuyer sur Oui ou Non", None),
    ("éteindre la prise", None), ("merci", None), ("oui je veux que tu éteignes tout", None), ("", None), (None, None),
    # revue de sécurité (F1) : on acquiesce ou on clôt avec ces mots-là, ils ne commandent aucune coupure
    ("ok", None), ("d'accord", None), ("c'est bon", None), ("merci c'est bon", None), ("ok merci", None), ("allez", None), ("go", None),
    ("exactement", None), ("bien sûr", None), ("bon alors ok", None), ("tout à fait", None),
])
def test_reponse_vocale_nette_seulement(dit, attendu):
    assert live_agent.reponse_vocale_coupure(dit) == attendu


# ── La carte n'est jamais annoncée sans avoir été demandée ───────────────────────────────────────────
def test_invite_a_toucher_un_bouton_seulement():
    assert live_agent.INVITE_BOUTON.search("Veuillez appuyer sur Oui ou Non sur l'écran pour confirmer.")
    assert live_agent.INVITE_BOUTON.search("Touchez Non pour annuler.")
    assert not live_agent.INVITE_BOUTON.search("Dites oui pour continuer.")            # autre confirmation parlée : permise
    assert not live_agent.INVITE_BOUTON.search("J'ai appuyé sur le bouton.")


def test_carte_annoncee_sans_outil_est_coupee_et_l_agent_doit_appeler_l_outil():
    page = FaussePage()
    s = FausseSession([agent_dit("J'ai bien compris : vous voulez que je coupe la prise. Veuillez appuyer sur Oui ou Non sur l'écran."),
                       tour_parle("Je m'en occupe.")])
    a, _ = lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert any(d["type"] == "vider" for d in page.recu)                                 # le son est coupé
    textes = [e["text"] for e in s.envois if "text" in e]
    assert any("AUCUNE carte n'est à l'écran" in t and "preparer_coupure" in t for t in textes)
    assert a.stats["cartes_fantomes_bloquees"] == 1


def test_une_vraie_carte_a_l_ecran_n_est_pas_coupee():
    page = FaussePage()
    s = Enchainee(COUPER, [agent_dit("J'ai bien compris. Appuyez sur Oui ou Non, ou dites oui ou non, je vous écoute."), tour_parle("Voilà.")])
    a, _ = lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert not any(d["type"] == "vider" for d in page.recu) and a.stats.get("cartes_fantomes_bloquees", 0) == 0
    retour = s.reponses_outils[0].response["resultat"]
    assert "dire « oui » ou « non »" in retour["a_savoir"] and "carte_page" not in retour      # texte propre à l'appel vocal


# ── « oui » / « non » à la voix : décidé par le serveur, exécuté par la page ───────────────────────────
def test_oui_dit_a_la_voix_la_page_recoit_l_ordre_de_confirmer():
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non, ou dites oui ou non, je vous écoute."), vous_dit("oui"), tour_parle("C'est fait.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert confirmations(page) == ["oui"]


def test_non_dit_a_la_voix_annule():
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non."), vous_dit("non, laisse tomber"), tour_parle("D'accord.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert confirmations(page) == ["non"]


def test_reponse_ambigue_ou_sans_carte_ne_fait_rien():
    for dit in ("oui mais pas la prise", "oui ou non ?", "éteindre la lampe"):
        page = FaussePage()
        s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non."), vous_dit(dit), tour_parle("D'accord.")])
        lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
        assert confirmations(page) == [], dit
    page = FaussePage()                                                                  # aucune carte en attente : un « oui » ne coupe rien
    lancer(page, FauxGemini([FausseSessionSimple(vous_dit("oui"))]), reserves(), pont=PontCoupure())
    assert confirmations(page) == []


class PontExpire(PontCoupure):
    """La demande de coupure est déjà expirée (elle ne vaut que 120 s)."""
    def executer(self, nom, args):
        r, label = super().executer(nom, args)
        if "carte_page" in r:
            r["carte_page"]["expire"] = r["demande_confirmation"]["expire"] = "2000-01-01T00:00:00+00:00"
        return r, label


def test_carte_expiree_un_oui_ne_coupe_rien():
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non."), vous_dit("oui"), tour_parle("D'accord.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontExpire())
    assert confirmations(page) == []


def test_un_oui_ne_sert_qu_une_fois():
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non."), vous_dit("oui"), vous_dit("oui"), tour_parle("Fait.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert confirmations(page) == ["oui"]


class FausseSessionSimple(Enchainee):
    def __init__(self, tour):
        super().__init__(tour, [])


# ── Revue de sécurité du 19/10/2026 (Gardien) ─────────────────────────────────────────────────────────────
def un_oui_apres(*tours):
    """Carte de coupure, l'agent explique, puis les tours donnés (ce que dit la personne), puis la fin."""
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non, ou dites oui ou non, je vous écoute."), *tours, tour_parle("Fin.")])
    a, _ = lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    return page, s, a


def test_F2_le_oui_n_est_lie_qu_a_la_question_de_la_coupure():
    """Une autre phrase (3 mots ou plus) ferme la fenêtre vocale : un « oui » dit plus tard, à une autre question, ne coupe rien."""
    page, _, _ = un_oui_apres(vous_dit("et ma facture du mois dernier"), vous_dit("oui"))
    assert confirmations(page) == []


def test_F2_un_bruit_court_ne_ferme_pas_la_fenetre_vocale():
    page, _, _ = un_oui_apres(vous_dit("euh"), vous_dit("oui"))
    assert confirmations(page) == ["oui"]


def test_F2_la_voix_n_est_acceptee_que_peu_de_temps_apres_la_carte(monkeypatch):
    monkeypatch.setattr(live_agent, "FENETRE_VOIX_S", -1)                      # fenêtre déjà passée : il reste le clic
    page, _, _ = un_oui_apres(vous_dit("oui"))
    assert confirmations(page) == []


def test_F2_le_clic_sur_la_carte_ferme_l_attente_vocale():
    import asyncio
    a = live_agent.Appel(FaussePage(), lambda e: None, connecter=FauxGemini([]), reserves=reserves(), pont=PontCoupure())
    a.coupure_attendue = {"limite": 4_000_000_000, "limite_voix": 4_000_000_000, "voix": True, "base": ""}

    async def clic():
        await a.message_page({"type": "confirmation", "reponse": "oui", "appareil": "Capteur 2 - Prise", "action": "couper", "etat": "fait"})
    asyncio.run(clic())
    assert a.coupure_attendue is None


def test_F3_l_echo_de_la_voix_de_l_agent_n_est_pas_un_oui():
    assert live_agent.est_l_echo("oui", "Appuyez sur Oui ou dites oui")
    assert not live_agent.est_l_echo("oui", "Appuyez sur Oui ou Non, ou dites oui ou non")     # la vraie réponse n'est pas la fin de sa phrase
    page = FaussePage()
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou dites oui"), vous_dit("oui"), tour_parle("Fin.")])
    lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert confirmations(page) == []                                                           # entendu = la fin de ce que l'agent vient de dire


def test_F5_seule_la_partie_dite_apres_la_carte_compte():
    import asyncio
    page = FaussePage()
    a = live_agent.Appel(page, lambda e: None, connecter=FauxGemini([]), reserves=reserves(), pont=PontCoupure())
    a.vous = "éteins la prise"                                                                 # la demande, dite avant la carte
    a._attendre_confirmation({"type": "coupure", "expire": "2099-01-01T00:00:00+00:00", "appareil": "Capteur 2 - Prise",
                              "nom": "la prise", "action": "couper"}, {})
    a.vous = "éteins la prise oui"                                                             # puis « oui » dans le même tour de parole

    async def evaluer():
        await a._confirmation_vocale("éteins la prise oui")
    asyncio.run(evaluer())
    assert [d["reponse"] for d in page.recu if d["type"] == "confirmer_coupure"] == ["oui"]


def test_F6_apres_un_oui_entendu_l_agent_peut_redire_oui_ou_non_sans_etre_coupe():
    page = FaussePage()
    redit = [msg(server_content=types.LiveServerContent(output_transcription=types.Transcription(text=" Vous pouvez appuyer sur Oui."))),
             msg(server_content=types.LiveServerContent(turn_complete=True))]
    s = ApresOutil(COUPER, [tour_parle("Appuyez sur Oui ou Non, ou dites oui ou non, je vous écoute."),
                            [msg(server_content=types.LiveServerContent(input_transcription=types.Transcription(text="oui")))] + tour_parle("D'accord.")[:-1] + redit,
                            tour_parle("Fin.")])
    a, _ = lancer(page, FauxGemini([s]), reserves(), pont=PontCoupure())
    assert confirmations(page) == ["oui"] and a.stats.get("oui_non_entendus") == ["oui"]
    assert a.stats.get("cartes_fantomes_bloquees", 0) == 0                                     # pas de nouvelle carte demandée à l'agent


def test_F4_F7_la_page_ferme_vraiment_l_appel_et_protege_les_cartes_de_coupure():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[3] / "static" / "js" / "assistant.js").read_text(encoding="utf-8")
    assert "(LIVE.fermeture && !d && !LIVE.raccroche)) return;" in js                          # raccrocher pendant son « au revoir »
    assert "LIVE.raccroche = true; LIVE.micro = false; LIVE.fermeture = false;" in js
    assert '[".c-coupure, .c-coupure *"' in js                                                 # l'agent ne clique jamais Oui sur une coupure


def test_N1_la_phrase_de_l_agent_finit_par_je_vous_ecoute_donc_un_vrai_non_n_est_pas_pris_pour_un_echo():
    """Si sa phrase finissait par « …ou non », la vraie réponse « non » ressemblerait à l'écho et serait refusée (revue de sécurité)."""
    assert live_agent.est_l_echo("non", "Appuyez sur Oui ou Non, ou dites oui ou non")                 # d'où la consigne : finir autrement
    assert not live_agent.est_l_echo("non", "Appuyez sur Oui ou Non, ou dites oui ou non, je vous écoute")
    page, _, _ = un_oui_apres(vous_dit("non"))
    assert confirmations(page) == ["non"]
    for fin in ("TERMINE ta phrase par « je vous écoute »",):
        assert fin in " ".join(live_agent.consigne("auto").split())          # (retours à la ligne de la consigne ignorés)
    a = live_agent.Appel(FaussePage(), lambda e: None, connecter=FauxGemini([]), reserves=reserves(), pont=PontCoupure())
    resultat = {}
    a._attendre_confirmation({"type": "coupure", "expire": "2099-01-01T00:00:00+00:00", "nom": "la prise", "action": "couper"}, resultat)
    assert "TERMINE ta phrase par « je vous écoute »" in resultat["a_savoir"]

