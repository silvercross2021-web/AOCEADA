"""13/11/2026 : (1) connexion à DeepSeek retentée une fois, avec 20 s d'attente ; (2) milliers « 1.800. » en fin de phrase.

(1) Vu sur le PC du propriétaire : DNS en retard, 1re connexion à 15,5 s puis 0,1 s ; le délai de 10 s faisait afficher
    « Impossible de joindre le service de réponse » alors qu'un 2e essai passait.
(2) Google écrit « 1.800 » ; la voix baoulé le lit mal. Le point qui termine la phrase empêchait la correction en « 1 800 ».
"""

import pytest
import requests

from apps.ai_assistant.chatbot import baoule_relais, dioula_relais, fournisseurs, wolof_relais
from apps.ai_assistant.tests_chatbot.test_arbitrage_10_11 import Rep, sse


@pytest.fixture(autouse=True)
def _sans_attente(monkeypatch):
    monkeypatch.setattr(fournisseurs.time, "sleep", lambda s: None)


def _lire():
    return "".join(x for x in fournisseurs.flux_deepseek("s", [{"role": "user", "texte": "q"}], outils=False) if isinstance(x, str))


def test_connexion_en_echec_est_retentee_une_fois(monkeypatch):
    appels = []

    def post(url, **kw):
        appels.append(kw["timeout"])
        if len(appels) == 1:
            raise requests.exceptions.ConnectTimeout("délai de connexion dépassé")
        return Rep([sse("Bonjour."), "data: [DONE]"])
    monkeypatch.setattr(fournisseurs.requests, "post", post)
    assert _lire() == "Bonjour."
    assert len(appels) == 2
    assert appels[0] == (fournisseurs.DELAI_CONNEXION_S, 40) and fournisseurs.DELAI_CONNEXION_S == 20


def test_deux_connexions_en_echec_remontent_l_erreur_reseau(monkeypatch):
    appels = []

    def post(url, **kw):
        appels.append(1)
        raise requests.exceptions.ConnectionError("Max retries exceeded")
    monkeypatch.setattr(fournisseurs.requests, "post", post)
    with pytest.raises(requests.exceptions.ConnectionError):
        _lire()
    assert len(appels) == fournisseurs.ESSAIS_CONNEXION == 2           # pas de boucle sans fin


def test_une_reponse_refusee_n_est_pas_retentee(monkeypatch):
    appels = []

    class Refus(Rep):
        status_code, text = 402, "solde"

    def post(url, **kw):
        appels.append(1)
        return Refus([])
    monkeypatch.setattr(fournisseurs.requests, "post", post)
    with pytest.raises(RuntimeError, match="402"):
        _lire()
    assert len(appels) == 1                                            # clé refusée ou solde épuisé : réessayer ne sert à rien


def test_pire_cas_de_la_connexion_reste_sous_l_abandon():
    assert fournisseurs.ESSAIS_CONNEXION * fournisseurs.DELAI_CONNEXION_S + 1 < fournisseurs.DELAI_ABANDON_S


# ── milliers en fin de phrase ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("brut,attendu", [
    ("Climatiseur’n sika 1.800.", "Climatiseur’n sika 1 800."),          # le défaut
    ("Sika 36.600, ɔ ti.", "Sika 36 600, ɔ ti."),
    ("Sika 1.800.000.", "Sika 1 800 000."),
    ("Sika 47.700 ɔ ti.", "Sika 47 700 ɔ ti."),                         # inchangé
    ("Kilowatt 2,5 nun.", "Kilowatt 2,5 nun."),                         # vrai décimal : jamais touché
    ("Kilowatt 2,5.", "Kilowatt 2,5."),
    ("Le 13.11.2026.", "Le 13.11.2026."),                               # une date n'est pas un nombre à milliers
])
def test_milliers_baoule(monkeypatch, brut, attendu):
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: brut)
    out, _ = baoule_relais.vers_baoule("Le climatiseur coûte 1 800 francs ce mois-ci.")
    assert out == attendu


@pytest.mark.parametrize("brut,attendu", [
    ("Dese nga 9.258.", "Dese nga 9 258."),
    ("Dese nga 9.258 franc.", "Dese nga 9 258 franc."),
    ("Wattu 2,5.", "Wattu 2,5."),
])
def test_milliers_wolof(brut, attendu):
    assert wolof_relais._RE_MILLIERS.sub(lambda m: m.group(0).replace(".", " ").replace(",", " "), brut) == attendu
