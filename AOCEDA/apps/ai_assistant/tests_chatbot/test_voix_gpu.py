"""Voix baoulé sur le GPU Cerebrium (06/10/2026), avec un Cerebrium SIMULÉ (aucun appel réseau, aucun crédit dépensé).

Vérifie : un seul appel pour toutes les phrases d'une réponse, repli sur le PC si Cerebrium tombe, réveil anticipé sans
doublon, lecture du crédit sans jamais renvoyer de clé, et le trajet complet réponse baoulé -> voix prête.
"""
import base64
import io
import json
import time

import numpy as np
import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import conversation, securite, voix, voix_baoule, voix_gpu
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur


def wav(secondes=0.5, sr=24000):
    import soundfile as sf
    t = np.arange(int(sr * secondes)) / sr
    b = io.BytesIO()
    sf.write(b, (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr, format="WAV")
    return b.getvalue()


class FausseReponse:
    def __init__(self, code, donnees):
        self.status_code, self._d, self.text = code, donnees, json.dumps(donnees)[:200]

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture
def gpu(monkeypatch, tmp_path):
    """GPU allumé, Cerebrium simulé : renvoie la liste des appels (fonction, données, en-têtes)."""
    monkeypatch.setenv("CHATBOT_VOIX_BAOULE_GPU", "1")
    monkeypatch.setenv("CEREBRIUM_API_KEY", "cle-de-test-secrete")
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    for k, v in {"dernier_appel": 0.0, "reveil": None, "lots": {}, "credit": None, "credit_t": 0.0, "echecs": 0,
                 "derniere_erreur": None, "mesures": []}.items():
        monkeypatch.setitem(voix_gpu._etat, k, v)
    appels = []
    comportement = {"panne": False, "erreur_phrase": None}

    def post(url, json=None, timeout=None, headers=None):
        fonction = url.rsplit("/", 1)[1]
        appels.append((fonction, json, headers))
        if comportement["panne"]:
            return FausseReponse(502, {"erreur": "bad gateway"})
        if fonction == "reveil":
            return FausseReponse(200, {"result": {"pret": True}})
        if fonction == "fabriquer":
            return FausseReponse(200, {"result": {"wav_b64": base64.b64encode(wav()).decode(), "calcul_s": 0.3}})
        if fonction == "fabriquer_lot":
            voix_l = [{"erreur": "CUDA"} if t == comportement["erreur_phrase"] else
                      {"wav_b64": base64.b64encode(wav()).decode()} for t in json["textes"]]
            return FausseReponse(200, {"result": {"voix": voix_l}})
        return FausseReponse(404, {})
    monkeypatch.setattr(voix_gpu.requests, "post", post)
    return type("Gpu", (), {"appels": appels, "c": comportement})


def test_gpu_coupe_par_defaut_dans_les_tests():
    assert not voix_gpu.disponible()                       # conftest : jamais la vraie machine pendant les tests


def test_sans_cle_pas_de_gpu(monkeypatch):
    monkeypatch.setenv("CHATBOT_VOIX_BAOULE_GPU", "1")
    monkeypatch.setenv("CEREBRIUM_API_KEY", "")
    assert not voix_gpu.disponible()


def test_une_phrase_fabriquee_avec_la_cle(gpu):
    audio = voix_gpu.fabriquer("Kuran'n w'a wie.")
    fonction, donnees, entetes = gpu.appels[0]
    assert audio.startswith(b"RIFF") and fonction == "fabriquer" and donnees == {"texte": "Kuran'n w'a wie.", "etapes": 8}
    assert entetes["Authorization"] == "Bearer cle-de-test-secrete"


def test_toutes_les_phrases_d_une_reponse_en_un_seul_appel(gpu):
    phrases = ["Kuran'n w'a wie min awlo lɔ.", "N ti AOCEDA i ukafuɛ.", "Frigo'n yɛ ɔ o lɛ ɔ?"]
    voix_gpu.annoncer(phrases).result(timeout=5)
    audios = [voix_gpu.fabriquer(p) for p in phrases]                   # la file de voix.py les demande une par une
    assert [a[0] for a in gpu.appels] == ["fabriquer_lot"] and all(a.startswith(b"RIFF") for a in audios)
    assert gpu.appels[0][1]["textes"] == phrases
    assert voix_gpu.annoncer(phrases) is None                           # déjà demandées : pas de 2e lot


def test_phrase_en_echec_dans_le_lot_refaite_seule(gpu):
    gpu.c["erreur_phrase"] = "Deuxième."
    voix_gpu.annoncer(["Première.", "Deuxième."]).result(timeout=5)
    assert voix_gpu.fabriquer("Deuxième.").startswith(b"RIFF")
    assert [a[0] for a in gpu.appels] == ["fabriquer_lot", "fabriquer"]


def test_cerebrium_en_panne_la_voix_est_faite_sur_le_pc(gpu, monkeypatch):
    gpu.c["panne"] = True
    monkeypatch.setattr(voix_baoule, "atelier_installe", lambda: True)
    monkeypatch.setattr(voix_baoule, "_fabriquer_pc", lambda t: b"RIFF-PC")
    assert voix_baoule.fabriquer("Ɔ ti kpa.") == b"RIFF-PC" and voix_baoule._etat["dernier_moteur"] == "pc"
    assert voix_gpu._etat["derniere_erreur"] == "HTTP 502"


def test_ni_gpu_ni_atelier_erreur_claire(gpu, monkeypatch):
    gpu.c["panne"] = True
    monkeypatch.setattr(voix_baoule, "atelier_installe", lambda: False)
    with pytest.raises(voix_baoule.AtelierIndisponible, match="GPU"):
        voix_baoule.fabriquer("Ɔ ti kpa.")


def test_reveil_une_seule_fois_et_pas_si_la_machine_vient_de_servir(gpu):
    assert voix_gpu.reveiller("menu") is True
    assert voix_gpu.reveiller("vocal") is False                        # déjà en route
    voix_gpu._etat["reveil"].result(timeout=5)
    assert [a[0] for a in gpu.appels] == ["reveil"] and voix_gpu.eveille()
    assert voix_gpu.reveiller("question") is False                     # vient de servir : encore allumée


def test_reveil_sans_gpu_ne_fait_rien(monkeypatch):
    monkeypatch.setattr(voix_gpu.requests, "post", lambda *a, **k: pytest.fail("appel réseau sans GPU"))
    assert voix_gpu.reveiller("menu") is False


def test_question_baoule_reveille_le_gpu(gpu, monkeypatch):
    vu = []
    monkeypatch.setattr(voix_gpu, "reveiller", lambda raison="": vu.append(raison) or True)
    from apps.ai_assistant.chatbot import service_baoule
    gen = service_baoule.repondre("sess-gpu-rev", "Aɲiho", liste=[])
    try:
        next(gen)
    except Exception:
        pass
    assert vu == ["question en baoulé"]


def test_vocal_baoule_en_cours_reveille_le_gpu(gpu, monkeypatch):
    """Un VRAI morceau de vocal baoulé réveille le GPU ; un faux fichier non (audit du 09/10/2026 : n'importe quel envoi
    marqué baoulé réveillait la machine payante)."""
    import io
    import wave
    from apps.ai_assistant.chatbot import baoule_ecoute, dioula_ecoute
    vu = []
    monkeypatch.setattr(voix_gpu, "reveiller", lambda raison="": vu.append(raison) or True)
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio",
                        lambda a, garder_probas=True, annulation=None: dioula_ecoute.Ecoute([], None, 1.0, 0.1))
    with pytest.raises(voix.ErreurVoix):
        voix.ecouter_morceau(b"pas un wav", "sess-gpu-morc", 0, "bci")
    assert vu == []                                                    # faux fichier : la machine dort toujours
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x01" * 16000)
    voix.ecouter_morceau(buf.getvalue(), "sess-gpu-morc", 0, "bci")
    assert vu == ["vocal baoulé en cours"]


def test_reponse_baoule_complete_voix_prete_en_un_appel(gpu):
    """Trajet complet : réponse baoulé écrite -> lot annoncé -> la page demande la voix -> un seul audio continu."""
    import soundfile as sf
    reponse = "N kwlá nunnunman frigo'n min bɔbɔ. Amun tɛ su kɛ ɛɛ annzɛ cɛcɛ."
    voix.annoncer_baoule(reponse)
    for _ in range(100):
        etat, tache, _, (faites, total) = voix.demander_baoule_reponse(reponse)
        if etat == "prete":
            break
        time.sleep(0.05)
    son, sr = sf.read(io.BytesIO(tache.result()[0]))
    assert etat == "prete" and total == 2 and abs(len(son) / sr - (1.0 + voix.PAUSE_ENTRE_PHRASES_S)) < 0.05
    assert [a[0] for a in gpu.appels] == ["fabriquer_lot"]


def test_api_voix_baoule_dit_le_moteur_pour_redemander_vite(gpu, monkeypatch):
    monkeypatch.setattr(voix, "demander_baoule_reponse", lambda t: ("preparation", None, 1, (0, 2)))
    conversation.autoriser_voix("sess-gpu-api", ["Ɔ ti kpa."])
    r = TestClient(serveur.app).post("/api/voix", json={"session": "sess-gpu-api", "texte": "Ɔ ti kpa.", "langue": "bci"})
    assert r.status_code == 202 and r.json()["moteur"] == "gpu" and r.json()["attente_s"] in (3, 35)


def test_api_reveil(gpu, monkeypatch):
    securite.remettre_a_zero()
    monkeypatch.setattr(voix_gpu, "reveiller", lambda raison="": raison == "menu baoulé")
    r = TestClient(serveur.app).post("/api/baoule/reveil", json={"session": "sess-gpu-rev2"})
    assert r.status_code == 200 and r.json()["reveil"] is True and r.json()["moteur"] == "gpu"


COUT = {"coupons": [{"coupon_name": "Card Added", "amount_cents": 2500, "amount_cents_remaining": 2500}],
        "summary": {"combined_cost_before_discounts_cents": 55.1, "total_gpu_seconds": 1023.5, "total_build_count": 2}}


def test_credit_lu_et_aucune_cle_renvoyee(gpu, monkeypatch):
    monkeypatch.setenv("CEREBRIUM_SERVICE_ACCOUNT_TOKEN", "jeton-gestion-secret")
    vu = {}
    monkeypatch.setattr(voix_gpu.requests, "get",
                        lambda url, headers=None, timeout=None: vu.update(url=url, h=headers) or FausseReponse(200, COUT))
    c = voix_gpu.credit(forcer=True)
    assert c["ok"] and c["offert_usd"] == 25.0 and c["depense_mois_usd"] == 0.55 and c["restant_usd"] == 24.45
    assert c["conversations_restantes"] == 1222 and c["heures_restantes"] == 24.0 and c["gpu_minutes_mois"] == 17.1
    assert vu["url"].endswith("/projects/p-a50fe161/cost") and vu["h"]["Authorization"] == "Bearer jeton-gestion-secret"
    texte = json.dumps(c)
    assert "secret" not in texte and "cle-de-test" not in texte


def test_credit_sans_connexion_dit_pourquoi(gpu, monkeypatch, tmp_path):
    monkeypatch.delenv("CEREBRIUM_SERVICE_ACCOUNT_TOKEN", raising=False)
    monkeypatch.setattr(voix_gpu, "CONFIG_CLI", tmp_path / "absent.yaml")
    c = voix_gpu.credit(forcer=True)
    assert not c["ok"] and "cerebrium login" in c["raison"]


def jwt(expire_dans):
    charge = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + expire_dans}).encode()).decode().rstrip("=")
    return f"aaa.{charge}.bbb"


def test_connexion_expiree_renouvelee_par_l_outil_cerebrium(gpu, monkeypatch, tmp_path):
    monkeypatch.delenv("CEREBRIUM_SERVICE_ACCOUNT_TOKEN", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"accesstoken: {jwt(-100)}\nproject: p-a50fe161\n", encoding="utf-8")
    outil = tmp_path / "cerebrium.exe"
    outil.write_bytes(b"")
    monkeypatch.setattr(voix_gpu, "CONFIG_CLI", cfg)
    monkeypatch.setattr(voix_gpu, "OUTIL_CLI", outil)
    neuf = jwt(3600)
    lances = []

    def renouveler(cmd, **k):                                           # l'outil réécrit le jeton
        lances.append(cmd[1:3])
        cfg.write_text(f"accesstoken: {neuf}\n", encoding="utf-8")
    monkeypatch.setattr(voix_gpu.subprocess, "run", renouveler)
    assert voix_gpu._jeton_gestion() == neuf and lances == [["projects", "list"]]


def test_api_credit_sans_cle(gpu, monkeypatch):
    securite.remettre_a_zero()
    monkeypatch.setattr(voix_gpu, "credit", lambda forcer=False: {"ok": True, "restant_usd": 24.45, "forcer": forcer})
    r = TestClient(serveur.app, administrateur=True).get("/api/gpu/credit?forcer=1")
    assert r.status_code == 200 and r.json() == {"ok": True, "restant_usd": 24.45, "forcer": True}
    # relecture forcée (elle peut lancer l'outil cerebrium du serveur) : réservée à l'administrateur d'AOCEDA (au
    # laboratoire : à ce PC) ; un client a le crédit gardé
    r = TestClient(serveur.app).get("/api/gpu/credit?forcer=1")
    assert r.status_code == 200 and r.json()["forcer"] is False
