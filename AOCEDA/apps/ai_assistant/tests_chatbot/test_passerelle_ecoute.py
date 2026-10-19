"""Passerelle d'écoute (19/10/2026) : en mode Automatique, le vocal est écouté PENDANT la parole, avant même de connaître
la langue (Whisper tiny et les deux oreilles en même temps sur les premiers morceaux, puis UNE seule fois la langue sûre) ;
mots très courts relus par Whisper ; langue corrigée par la personne (« Changer ») ; règles de décision corrigées après
le rejeu de 169 vrais vocaux. Sans Internet ni vrai modèle : oreilles, Whisper et ses probabilités sont simulés."""
import io
import wave

import numpy as np
import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import baoule_ecoute, dioula_ecoute, dioula_routage, voix
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur


def wav_bytes(secondes):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.full(int(16000 * secondes), 1, dtype="<i2").tobytes())
    return buf.getvalue()


def ecoute(texte):
    mots = [{"mot": m, "certitude": 0.9, "t0": 2 * i, "t1": 2 * i + 1} for i, m in enumerate(texte.split())]
    return dioula_ecoute.Ecoute(mots, np.zeros((10, 3), dtype="float32"), 1.0, 0.1, texte)


class FausseOreille:
    def __init__(self, textes):
        self.textes, self.appels = list(textes), []

    def transcrire_audio(self, audio, garder_probas=True, annulation=None):
        self.appels.append(round(len(audio) / 16000, 1))
        return ecoute(self.textes[min(len(self.appels), len(self.textes)) - 1])


@pytest.fixture
def moteurs(monkeypatch):
    """Oreilles dioula / baoulé, Whisper tiny (probabilités) et Whisper small simulés ; GPU jamais réveillé."""
    m = type("M", (), {})()
    m.dyu, m.bci = FausseOreille(["x"]), FausseOreille(["x"])
    m.probs = {"ja": 0.4, "fr": 0.1}
    m.whisper = []
    monkeypatch.setattr(voix, "_oreille", lambda lg: m.bci if lg == "bci" else m.dyu)
    monkeypatch.setattr(voix, "_probs_tiny", lambda audio: dict(m.probs))
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(baoule_ecoute, "disponible", lambda: True)
    monkeypatch.setattr(voix, "reveiller_voix_baoule", lambda *a, **k: False)

    def whisper_texte(audio, langue, annulation=None, vad=True):
        m.whisper.append((round(len(audio) / 16000, 1), langue, vad))
        return f"{len(audio) // 16000}s", langue or "fr", 1.0
    monkeypatch.setattr(voix, "_whisper_texte", whisper_texte)
    monkeypatch.setitem(voix._morceaux, "sessions", {})
    return m


def morceau(session, rang, secondes, conv=None):
    r = voix.ecouter_morceau(wav_bytes(secondes), session, rang, "auto", conv)
    voix._morceaux["sessions"][session]["liste"][rang][1].result(timeout=10)   # écouté pendant la parole
    return r


def test_dioula_reconnu_pendant_la_parole_puis_une_seule_oreille(moteurs):
    moteurs.dyu.textes = ["n ka kuran juru banna", "a tora joli", "a bɛ dɔgɔya", "kosɛbɛ"]
    moteurs.bci.textes = ["n ka kuran", "a tora"]
    assert "langue" not in morceau("sess-pa-1", 0, 2.5)                # 1er morceau : les deux oreilles en même temps
    assert "langue" not in morceau("sess-pa-1", 1, 2)                  # un seul morceau fini : pas encore de verrou
    assert morceau("sess-pa-1", 2, 2)["langue"] == "dyu"                # 2 morceaux d'accord : seulement l'oreille dioula
    r = voix.transcrire_serveur(wav_bytes(7.5), None, None, "sess-pa-1", 3)
    assert r["langue"] == "dyu" and "kuran" in r["texte"] and r["temps"]["langue_verrouillee"] == "dyu"
    assert r["temps"]["morceaux_reutilises"] == 3 and r["routage"]["chemin"] == "omni"
    assert moteurs.dyu.appels == [2.5, 2.0, 2.0, 1.0]                   # à la fin, seulement la dernière seconde
    assert moteurs.bci.appels == [2.5, 2.0]                             # l'oreille baoulé s'arrête une fois sûr


def test_baoule_vocal_court_decide_a_la_fin_sur_tout_le_texte(moteurs):
    moteurs.dyu.textes = ["sran nga be o lɛ", "kuran'n w'a wie"]
    moteurs.bci.textes = ["sran nga be o awlo'n nun", "kuran'n w'a wie", "aniɛn'n"]
    morceau("sess-pa-2", 0, 3)
    r = voix.transcrire_serveur(wav_bytes(5), None, None, "sess-pa-2", 1)
    assert r["langue"] == "bci" and "baoule" in r and r["temps"]["morceaux_reutilises"] == 1
    assert moteurs.dyu.appels == [3.0, 2.0] and moteurs.bci.appels == [3.0, 2.0]   # rien n'est réécouté en entier


def test_francais_reconnu_puis_whisper_transcrit_au_fil_de_la_parole(moteurs):
    moteurs.probs = {"fr": 0.97}
    morceau("sess-pa-3", 0, 2)
    assert morceau("sess-pa-3", 1, 2)["langue"] == "w:fr"
    r = voix.transcrire_serveur(wav_bytes(5), None, None, "sess-pa-3", 2)
    assert r["langue"] == "fr" and r["texte"] == "2s 2s 1s" and r["routage"]["chemin"] == "whisper"
    assert sorted(moteurs.whisper) == [(1.0, "fr", True), (2.0, "fr", True), (2.0, "fr", True)]
    assert moteurs.dyu.appels == [] and moteurs.bci.appels == []        # les oreilles locales n'ont jamais servi


def test_debut_incertain_puis_francais_net(moteurs, monkeypatch):
    suite = iter([{"ja": 0.4}, {"fr": 0.97}, {"fr": 0.97}])
    monkeypatch.setattr(voix, "_probs_tiny", lambda audio: next(suite))
    morceau("sess-pa-8", 0, 3)
    morceau("sess-pa-8", 1, 2)
    assert morceau("sess-pa-8", 2, 2)["langue"] == "w:fr"               # le début (oreilles locales) passe à Whisper
    r = voix.transcrire_serveur(wav_bytes(8), None, None, "sess-pa-8", 3)
    assert r["langue"] == "fr" and r["texte"] == "3s 2s 2s 1s"
    assert moteurs.dyu.appels == [3.0]


def test_tiny_hesite_whisper_transcrit_quand_meme_pendant_la_parole(moteurs):
    """19/10/2026 (vrai vocal de 12 s) : français à l'accent ivoirien, tiny à 0,11 seulement -> rien n'était transcrit
    pendant la parole, Whisper retranscrivait TOUT le vocal après la fin (7,3 s d'attente). Whisper small transcrit
    maintenant aussi chaque morceau, au cas où ; la décision « français » reprend ce texte tel quel."""
    moteurs.probs = {"ja": 0.3, "fr": 0.11}
    moteurs.dyu.textes = ["il me reste combien de crédit", "sur mon compteur électrique", "merci"]
    moteurs.bci.textes = moteurs.dyu.textes
    morceau("sess-pa-9", 0, 3)
    morceau("sess-pa-9", 1, 3)
    r = voix.transcrire_serveur(wav_bytes(7), None, None, "sess-pa-9", 2)
    assert r["langue"] == "fr" and r["temps"].get("whisper_pendant_parole") == "fr" and r["temps"].get("whisper_anticipe")
    assert r["texte"] == "3s 3s 1s"
    assert all(duree <= 3.0 for duree, _, _ in moteurs.whisper)        # jamais tout le vocal après la fin


def test_langue_pas_sure_decision_sur_les_ecoutes_deja_faites(moteurs):
    moteurs.dyu.textes = ["ab", "cd", "ef"]
    moteurs.bci.textes = ["ab", "cd", "ef"]
    morceau("sess-pa-4", 0, 2)
    assert "langue" not in morceau("sess-pa-4", 1, 2)
    voix.transcrire_serveur(wav_bytes(5), None, None, "sess-pa-4", 2)
    assert moteurs.dyu.appels == [2.0, 2.0, 1.0] and moteurs.bci.appels == [2.0, 2.0, 1.0]   # jamais le vocal entier


def test_morceau_manquant_le_vocal_est_reecoute_en_entier(moteurs, monkeypatch):
    monkeypatch.setitem(voix._whisper, "detecteur", type("D", (), {"detect_language": lambda self, a: (
        "ja", 0.4, [("ja", 0.4)])})())
    moteurs.dyu.textes = ["n ka kuran juru banna"]
    morceau("sess-pa-5", 0, 2)
    morceau("sess-pa-5", 2, 2)                                          # le n° 1 n'est jamais arrivé
    r = voix.transcrire_serveur(wav_bytes(6), None, None, "sess-pa-5", 3)
    assert "morceaux_reutilises" not in r["temps"] and 6.0 in moteurs.dyu.appels


def test_mots_tres_courts_relus_par_whisper(moteurs, monkeypatch):
    monkeypatch.setattr(voix, "_whisper_texte", lambda audio, langue, annulation=None, vad=True: ("Oui.", "fr", 1.0))
    un_s = np.zeros(16000, dtype="float32")
    r = voix._mot_court(un_s, {"chemin": "omni", "texte_omni": "w"}, None, {})
    assert r["langue"] == "fr" and r["texte"] == "Oui." and r["routage"]["chemin"] == "court"
    r = voix._mot_court(un_s, {"chemin": "omni", "texte_omni": "w"}, "dyu", {})
    assert r["langue"] == "dyu" and r["texte"] == "Oui."                # « oui » glissé dans une conversation en dioula
    assert voix._mot_court(un_s, {"chemin": "silence", "texte_omni": ""}, None, {})["langue"] == "fr"
    assert voix._mot_court(np.zeros(16000 * 3, dtype="float32"), {"chemin": "omni", "texte_omni": "w"}, None, {}) is None
    assert voix._mot_court(un_s, {"chemin": "omni", "texte_omni": "kuran"}, None, {}) is None   # vraie lecture locale


def test_langue_corrigee_par_la_personne_sans_verification_whisper(moteurs, monkeypatch):
    vu = []
    monkeypatch.setitem(voix._whisper, "detecteur", type("D", (), {"detect_language": lambda self, a: vu.append(1) or (
        "fr", 0.99, [("fr", 0.99)])})())
    moteurs.dyu.textes = ["n ka kuran juru banna"]
    r = voix.transcrire_serveur(wav_bytes(3), "dyu", None, "sess-pa-6", 0, forcer=True)
    assert r["langue"] == "dyu" and vu == []                            # pas de « Whisper sûr : français »
    r = voix.transcrire_serveur(wav_bytes(3), "dyu", None, "sess-pa-6", 0)
    assert r["langue"] == "fr" and vu == [1]                            # sans correction : la vérification reste


def test_page_morceau_automatique_et_correction(monkeypatch):
    vu = {}
    monkeypatch.setattr(voix, "ecouter_morceau", lambda o, s, r, l="dyu", c=None, parle=None: vu.update(langue=l) or {"rang": r, "duree_s": 2})
    c = TestClient(serveur.app)
    r = c.post("/api/transcrire/morceau", files={"audio": ("m.wav", wav_bytes(2), "audio/wav")},
               data={"session": "sess-pa-7", "rang": "0", "langue": "auto"})
    assert r.status_code == 200 and vu["langue"] == "auto"
    pris = {}
    monkeypatch.setattr(voix, "transcrire", lambda *a, **k: pris.update(k) or {"texte": "x", "langue": "dyu", "parole": True})
    c.post("/api/transcrire", files={"audio": ("v.wav", wav_bytes(2), "audio/wav")},
           data={"session": "sess-pa-7", "langue": "dyu", "forcer": "1"})
    assert pris == {"forcer": True}
    pris.clear()
    c.post("/api/transcrire", files={"audio": ("v.wav", wav_bytes(2), "audio/wav")},
           data={"session": "sess-pa-7", "langue": "auto", "forcer": "1"})
    assert pris == {}                                                   # « forcer » sans langue choisie : ignoré


# ── Règles de décision corrigées (rejouées sur 169 vrais vocaux du laboratoire) ────────────────────────────────────
def test_dioula_dans_une_conversation_en_baoule():
    d = dioula_routage.decider({"ja": 0.27}, lambda: ("yala fiemine yó be duruni cama", "yala fiemine yó be duruni cama"),
                               "bci", lire_baoule=lambda: "yala fiɛmin yo be duruni kama")
    assert d["langue"] == "dyu" and d["raison"].startswith("traces de dioula")


def test_autre_langue_lue_nettement_n_est_plus_du_dioula_par_defaut():
    d = dioula_routage.decider({"it": 0.94, "sw": 0.01}, lambda: ("ninasalio kiasi gani kwenye mita yangu",) * 2, None,
                               lire_baoule=lambda: "ninasalio kiasi gani kwenye mita yangu")
    assert d["langue"] == "sw" and "aucun mot local" in d["raison"]
    d = dioula_routage.decider({"ja": 0.3}, lambda: ("n ka kuran juru banna",) * 2, None, lire_baoule=lambda: "n ka kuran")
    assert d["langue"] == "dyu"                                         # le vrai dioula ne change pas
