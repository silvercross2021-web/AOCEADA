"""Relais du chat quand DeepSeek ne répond plus (13/11/2026) : d'autres modèles par OpenRouter, chacun avec sa clé plafonnée.
Aucun appel réel : tout est simulé."""
import pytest

from apps.ai_assistant.chatbot import fournisseurs
from apps.ai_assistant.tests_chatbot.test_arbitrage_10_11 import Rep, sse

CLES = dict(OPENROUTER_KEY_DEEPSEEK="k-ds", OPENROUTER_KEY_GEMINI="k-ge", OPENROUTER_API_KEY="k-qw", OPENROUTER_KEY_CLAUDE="k-cl")


def _evenements(liste):
    return list(fournisseurs.repondre_flux("systeme", [{"role": "user", "texte": "question"}], liste=liste))


def _panne(message):
    def ouvrir(systeme, historique):
        raise RuntimeError(message)
        yield  # pragma: no cover
    return ouvrir


def _reponse(texte, secours=False, attente=0.0, compteur=None):
    def ouvrir(systeme, historique):
        if compteur is not None:
            compteur.append(1)
        if attente:
            import time
            time.sleep(attente)
        yield texte
    ouvrir.secours = secours
    return ouvrir


# ── la liste des candidats ──────────────────────────────────────────────────────────────────────
def test_sans_cle_openrouter_seulement_deepseek(monkeypatch):
    monkeypatch.setitem(fournisseurs.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    assert [c[0] for c in fournisseurs.candidats()] == ["DeepSeek", "DeepSeek"]


def test_les_relais_suivent_l_ordre_du_moins_cher_au_plus_cher(monkeypatch, settings):
    monkeypatch.setitem(fournisseurs.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    for nom, valeur in CLES.items():
        setattr(settings, nom, valeur)
    liste = fournisseurs.candidats()
    assert [(c[0], c[1]) for c in liste[2:]] == [("OpenRouter", "deepseek/deepseek-v4-flash"), ("OpenRouter", "google/gemini-3.5-flash-lite"),
                                                  ("OpenRouter", "qwen/qwen3.7-flash"), ("OpenRouter", "anthropic/claude-haiku-4.5")]
    assert all(getattr(c[2], "secours", False) for c in liste[2:]) and not any(getattr(c[2], "secours", False) for c in liste[:2])


def test_un_relais_sans_cle_est_ignore(monkeypatch, settings):
    monkeypatch.setitem(fournisseurs.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    settings.OPENROUTER_KEY_GEMINI = "k-ge"
    assert [c[1] for c in fournisseurs.candidats()[2:]] == ["google/gemini-3.5-flash-lite"]


# ── la course ───────────────────────────────────────────────────────────────────────────────────
def test_les_relais_repondent_quand_deepseek_echoue():
    ev = _evenements([("DeepSeek", "m", _panne("DeepSeek 500 : panne")), ("DeepSeek", "m (relance)", _panne("DeepSeek 500 : panne")),
                      ("OpenRouter", "deepseek/deepseek-v4-flash", _reponse("Bonjour.", secours=True))])
    fin = ev[-1]
    assert fin["type"] == "fin" and fin["texte"] == "Bonjour." and fin["fournisseur"] == "OpenRouter"
    assert [e["fournisseur"] for e in fin["essais"] if "erreur" in e] == ["DeepSeek", "DeepSeek"]      # les pannes sont notées


def test_la_chaine_passe_au_relais_suivant_si_le_premier_relais_echoue():
    ev = _evenements([("DeepSeek", "m", _panne("DeepSeek 500")), ("DeepSeek", "m (relance)", _panne("DeepSeek 500")),
                      ("OpenRouter", "a", _panne("OpenRouter 402 : solde")), ("OpenRouter", "b", _reponse("Salut.", secours=True))])
    assert ev[-1]["texte"] == "Salut." and ev[-1]["modele"] == "b"


def test_un_relais_payant_ne_part_pas_pour_une_simple_lenteur(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 0.05)
    monkeypatch.setattr(fournisseurs, "DELAI_PREMIER_MOT_S", 30)
    lancements = []
    ev = _evenements([("DeepSeek", "m", _reponse("Lent mais bon.", attente=0.4)), ("DeepSeek", "m (relance)", _reponse("Lent aussi.", attente=0.4)),
                      ("OpenRouter", "a", _reponse("PAYANT", secours=True, compteur=lancements))])
    assert ev[-1]["texte"] in ("Lent mais bon.", "Lent aussi.")
    assert lancements == []                                           # aucun centime dépensé


def test_un_relais_part_si_deepseek_ne_dit_rien_trop_longtemps(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 0.05)
    monkeypatch.setattr(fournisseurs, "DELAI_PREMIER_MOT_S", 0.2)
    ev = _evenements([("DeepSeek", "m", _reponse("Très lent.", attente=1.5)), ("DeepSeek", "m (relance)", _reponse("Très lent aussi.", attente=1.5)),
                      ("OpenRouter", "a", _reponse("Je réponds.", secours=True))])
    assert ev[-1]["texte"] == "Je réponds." and ev[-1]["fournisseur"] == "OpenRouter"


def test_si_tout_tombe_le_message_dit_que_ce_n_est_pas_passager():
    ev = _evenements([("DeepSeek", "m", _panne("DeepSeek 402 : solde")), ("OpenRouter", "a", _panne("OpenRouter 402 : solde"))])
    assert ev[-1]["type"] == "erreur" and "pas passager" in ev[-1]["texte"]


# ── le format de la demande à un relais ─────────────────────────────────────────────────────────
def test_un_relais_est_appele_avec_son_adresse_sa_cle_et_son_modele(monkeypatch):
    vus = {}

    def post(url, **kw):
        vus.update(url=url, auth=kw["headers"]["Authorization"], modele=kw["json"]["model"])
        return Rep([sse("Bonjour."), "data: [DONE]"])
    monkeypatch.setattr(fournisseurs.requests, "post", post)
    texte = "".join(x for x in fournisseurs.flux_deepseek("s", [{"role": "user", "texte": "q"}], outils=False, url=fournisseurs.URL_OPENROUTER,
                                                         cle="k-ds", modele="deepseek/deepseek-v4-flash", nom="OpenRouter") if isinstance(x, str))
    assert texte == "Bonjour."
    assert vus == {"url": "https://openrouter.ai/api/v1/chat/completions", "auth": "Bearer k-ds", "modele": "deepseek/deepseek-v4-flash"}


@pytest.mark.parametrize("statut", [401, 402, 403])
def test_un_relais_refuse_est_ignore_dix_minutes(monkeypatch, settings, statut):
    class Refus(Rep):
        status_code, text = statut, "refusé"
    monkeypatch.setattr(fournisseurs.requests, "post", lambda url, **kw: Refus([]))
    monkeypatch.setitem(fournisseurs.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    settings.OPENROUTER_KEY_DEEPSEEK = "k-ds"
    assert len(fournisseurs.candidats()) == 3
    with pytest.raises(RuntimeError, match=str(statut)):
        list(fournisseurs.flux_deepseek("s", [{"role": "user", "texte": "q"}], outils=False, url=fournisseurs.URL_OPENROUTER, cle="k-ds",
                                        modele="deepseek/deepseek-v4-flash", nom="OpenRouter"))
    assert len(fournisseurs.candidats()) == 2                          # plus de relais : on ne perd pas 1 s par question à retenter
    fournisseurs._hors_service.clear()
    assert len(fournisseurs.candidats()) == 3


def test_deepseek_direct_refuse_n_est_pas_mis_hors_service(monkeypatch):
    class Refus(Rep):
        status_code, text = 402, "solde"
    monkeypatch.setattr(fournisseurs.requests, "post", lambda url, **kw: Refus([]))
    with pytest.raises(RuntimeError, match="DeepSeek 402"):
        list(fournisseurs.flux_deepseek("s", [{"role": "user", "texte": "q"}], outils=False))
    assert fournisseurs._hors_service == {}
