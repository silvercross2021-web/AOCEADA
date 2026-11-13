"""13/11/2026 (2e passe) : pannes réelles corrigées (Djelia 429 en rafale, connexion Google trop courte), échecs anciens qui n'alarment plus,
vérifications « ce service répond-il encore ? », dernière valeur lue du crédit. Aucun appel réseau : tout est simulé."""
import sys
import time
import types

import pytest
import requests

from apps.ai_assistant.chatbot import credits, dioula_relais, etat_services
from apps.ai_assistant.tests_chatbot.test_etat_services import construire, tous


class Rep:
    def __init__(self, statut=200, entetes=None, contenu=b"", donnees=None):
        self.status_code, self.headers, self.content, self._d = statut, entetes or {}, contenu, donnees

    def raise_for_status(self):
        if self.status_code >= 400:
            e = requests.exceptions.HTTPError(f"{self.status_code}")
            e.response = self
            raise e

    def json(self):
        return self._d


@pytest.fixture
def sans_attente(monkeypatch):
    attentes = []
    monkeypatch.setattr(dioula_relais.time, "sleep", lambda s: attentes.append(s))
    return attentes


# ── les vraies pannes ────────────────────────────────────────────────────────────────────────────
def test_un_429_de_djelia_est_attendu_puis_reessaye(monkeypatch, sans_attente):
    reponses = [Rep(429), Rep(429), Rep(200)]
    monkeypatch.setattr(dioula_relais._http, "post", lambda *a, **k: reponses.pop(0))
    assert dioula_relais._appeler("djelia", "POST", "https://x", json={}).status_code == 200
    assert len(sans_attente) == 2 and all(0 < a <= 3 for a in sans_attente)             # a attendu entre les essais, sans insister


def test_un_429_qui_dure_finit_par_remonter(monkeypatch, sans_attente):
    monkeypatch.setattr(dioula_relais._http, "post", lambda *a, **k: Rep(429))
    r = dioula_relais._appeler("djelia", "POST", "https://x", json={})
    assert r.status_code == 429
    with pytest.raises(requests.exceptions.HTTPError):
        r.raise_for_status()


def test_une_connexion_ratee_est_retentee_une_seule_fois(monkeypatch, sans_attente):
    appels = []

    def get(*a, **k):
        appels.append(1)
        raise requests.exceptions.ConnectTimeout("lent")
    monkeypatch.setattr(dioula_relais._http, "get", get)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        dioula_relais._appeler("google", "GET", "https://x")
    assert len(appels) == 2                                                             # pas de boucle : un service injoignable n'est pas harcelé


def test_une_connexion_ratee_puis_reussie_donne_la_reponse(monkeypatch, sans_attente):
    suite = [requests.exceptions.ConnectTimeout("lent"), Rep(200)]

    def get(*a, **k):
        x = suite.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(dioula_relais._http, "get", get)
    assert dioula_relais._appeler("google", "GET", "https://x").status_code == 200


def test_la_connexion_a_google_attend_plus_de_3_secondes():
    assert dioula_relais.CONNEXION_S > 3.0                                              # vu : 3 échecs sur 16 par un délai de connexion de 3 s


def test_djelia_est_appele_a_cadence_reguliere(monkeypatch, sans_attente):
    monkeypatch.setattr(dioula_relais, "CADENCE_S", {"djelia": 0.6})
    monkeypatch.setattr(dioula_relais, "_dernier_depart", {})
    heure = [100.0]
    monkeypatch.setattr(dioula_relais.time, "time", lambda: heure[0])
    monkeypatch.setattr(dioula_relais._http, "post", lambda *a, **k: Rep(200))
    dioula_relais._appeler("djelia", "POST", "https://x", json={})
    heure[0] = 100.1                                       # 0,1 s plus tard : il faut attendre encore 0,5 s
    dioula_relais._appeler("djelia", "POST", "https://x", json={})
    assert sans_attente and abs(sans_attente[-1] - 0.5) < 0.01


def test_la_raison_d_un_echec_est_dite_en_mots_simples():
    r429 = requests.exceptions.HTTPError("429")
    r429.response = Rep(429)
    assert "429" in dioula_relais._raison(r429)
    assert "lente" in dioula_relais._raison(requests.exceptions.ConnectTimeout())
    assert "impossible" in dioula_relais._raison(requests.exceptions.ConnectionError())


def test_les_traducteurs_notent_la_raison_du_dernier_echec(monkeypatch):
    monkeypatch.setitem(dioula_relais._etat, "djelia", {"pannes": 0, "coupe_jusqu_a": 0.0})

    def en_echec(*a, **k):
        raise requests.exceptions.ConnectTimeout("lent")
    monkeypatch.setitem(dioula_relais.SERVICES, ("djelia", "vers_dyu"), (en_echec, "fra_Latn", "bam_Latn"))
    with pytest.raises(dioula_relais.RelaisIndisponible):
        dioula_relais.traduire("djelia", "vers_dyu", "phrase jamais vue 13/11")
    e = dioula_relais.etat()["djelia"]
    assert e["pannes"] == 1 and "lente" in e["derniere_raison"]


# ── un échec ancien, jamais réessayé, n'alarme plus ──────────────────────────────────────────────
def test_echec_recent_a_surveiller_echec_ancien_incertain_echec_suivi_d_un_succes_ok():
    t = time.time()
    s = tous(construire(traducteurs={"djelia": {"disponible": True, "pannes": 1, "derniere_panne": t - 60, "derniere_raison": "trop de demandes (429)"}}))["trad_djelia"]
    assert s["etat"] == "attention" and "429" in s["detail"]
    s = tous(construire(traducteurs={"djelia": {"disponible": True, "pannes": 1, "derniere_panne": t - 3600, "derniere_raison": "connexion trop lente"}}))["trad_djelia"]
    assert s["etat"] == "inconnu" and "incertain" in s["detail"]
    s = tous(construire(traducteurs={"djelia": {"disponible": True, "pannes": 0, "derniere_panne": t - 120, "dernier_ok": t - 30}}))["trad_djelia"]
    assert s["etat"] == "ok"


def test_une_voix_en_echec_ancien_est_incertaine():
    t = time.time()
    assert tous(construire(essais={"Djelia (voix bambara)": {"ok": False, "t": t - 3600, "raison": "403"}}))["voix_djelia"]["etat"] == "inconnu"
    assert tous(construire(essais={"Djelia (voix bambara)": {"ok": False, "t": t - 60, "raison": "403"}}))["voix_djelia"]["etat"] == "attention"


# ── « répond-il encore ? » ────────────────────────────────────────────────────────────────────────
def sonde(ok=True, de_suite=0, detail="répond"):
    return {"ok": ok, "t": time.time(), "ms": 800, "detail": detail, "de_suite": de_suite}


def test_une_verification_reussie_confirme_un_service_jamais_essaye():
    s = tous(construire(sondes={"voix_djelia": sonde()}))["voix_djelia"]
    assert s["etat"] == "ok" and s["verifie"]["ok"] and s["verifie"]["ms"] == 800


def test_un_rate_est_a_surveiller_deux_de_suite_indisponible():
    assert tous(construire(sondes={"voix_djelia": sonde(False, 1, "connexion trop lente")}))["voix_djelia"]["etat"] == "attention"
    s = tous(construire(sondes={"voix_djelia": sonde(False, 2, "connexion trop lente")}))["voix_djelia"]
    assert s["etat"] == "ko" and s["verifie"]["de_suite"] == 2


def test_une_verification_ne_reveille_pas_un_service_non_configure(settings):
    settings.KOOMA_API_KEY = ""
    assert "verifie" not in tous(construire(sondes={"voix_kooma": sonde()}))["voix_kooma"]


def test_les_modeles_retires_sont_detectes(monkeypatch, settings):
    """sonder() : OpenRouter et Google disent quels modèles existent encore ; le compteur d'échecs de suite est gardé."""
    settings.GEMINI_API_KEY = "cle-g"
    settings.METEO_EN_LIGNE = False
    settings.KOOMA_API_KEY = ""
    from apps.ai_assistant.chatbot import facture

    def get(url, **k):
        if "openrouter" in url:
            return Rep(200, donnees={"data": [{"id": "deepseek/deepseek-v4-flash"}, {"id": "qwen/qwen3.7-flash"}]})
        return Rep(200, donnees={"models": [{"name": "models/gemini-3.8-live"}, {"name": f"models/{facture.MODELES[0]}"}]})
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(dioula_relais, "_appeler", lambda *a, **k: Rep(200, {"content-type": "audio/mp4"}, b"x" * 2000))
    monkeypatch.setattr(dioula_relais, "_google", lambda *a, **k: "i ni ce")
    faux = types.ModuleType("edge_tts")

    async def list_voices():
        return [1]
    faux.list_voices = list_voices
    monkeypatch.setitem(sys.modules, "edge_tts", faux)
    compteurs, live, relais = {}, ["gemini-3.8-live", "gemini-3.1-flash-live-preview"], ["deepseek/deepseek-v4-flash", "google/gemini-3.5-flash-lite"]
    s = etat_services.sonder(live, relais, delai_s=2, compteurs=compteurs)
    assert s["live0"]["ok"] and not s["live1"]["ok"] and "retiré" in s["live1"]["detail"]
    assert s["relais1"]["ok"] and not s["relais2"]["ok"] and s["agent"]["ok"]
    assert s["facture"]["ok"] and s["voix_djelia"]["ok"] and s["voix_fr"]["ok"] and s["trad_google"]["ok"]
    s = etat_services.sonder(live, relais, delai_s=2, compteurs=compteurs)
    assert s["live1"]["de_suite"] == 2 and s["live0"]["de_suite"] == 0


def test_les_verifications_ne_bloquent_pas_la_page_et_ne_partent_pas_dans_les_tests(monkeypatch, settings):
    assert credits._sondes_a_jour(True) == {}                                           # désactivées par conftest
    settings.CHATBOT_SONDES = True

    def lent(live, relais, delai_s=10, sorties=None, compteurs=None):
        sorties["voix_djelia"] = sonde()
        time.sleep(0.6)
        sorties["voix_fr"] = sonde()
    monkeypatch.setattr(etat_services, "sonder", lent)
    monkeypatch.setattr(credits, "ATTENTE_SONDES_S", 0.2)
    pris = credits._sondes_a_jour(False)
    assert "voix_djelia" in pris and "voix_fr" not in pris                              # la page n'attend pas la fin
    credits._sondes["fil"].join(2)
    assert "voix_fr" in credits._sondes_a_jour(False)                                   # gardées 5 minutes, sans nouvelle vérification


# ── dernière valeur lue du crédit ─────────────────────────────────────────────────────────────────
def test_une_lecture_de_credit_qui_echoue_montre_la_derniere_valeur_datee(monkeypatch, settings):
    settings.DEEPSEEK_API_KEY = "cle-de-test"                    # sans clé (nouveau PC), DeepSeek est « non configuré » et n'a pas de crédit à montrer
    lectures = [{"ok": True, "disponible": True, "solde": 2.45}, {"ok": False, "raison": "ConnectTimeout"}]
    monkeypatch.setattr(credits, "_lire_deepseek", lambda: lectures.pop(0))
    premiere = credits._deepseek()
    assert premiere["solde"] == 2.45 and "ancien_a" not in premiere
    seconde = credits._deepseek()
    assert seconde["ok"] and seconde["solde"] == 2.45 and seconde["ancien_a"]
    s = tous(construire(ds=seconde))["deepseek"]
    assert "valeur lue à" in s["detail"] and s["credit"]["restant"] == 2.45


def test_sans_valeur_ancienne_la_lecture_echouee_reste_illisible(monkeypatch):
    monkeypatch.setattr(credits, "_lire_deepseek", lambda: {"ok": False, "raison": "x"})
    assert credits._deepseek()["ok"] is False


def test_une_lecture_de_credit_est_retentee_si_la_connexion_echoue(monkeypatch):
    appels = []

    def get(url, **k):
        appels.append(1)
        if len(appels) == 1:
            raise requests.exceptions.ConnectionError("x")
        return Rep(200, donnees={})
    monkeypatch.setattr(credits.requests, "get", get)
    assert credits._get("https://x").status_code == 200 and len(appels) == 2
