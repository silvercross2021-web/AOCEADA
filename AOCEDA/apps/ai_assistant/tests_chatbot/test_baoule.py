"""Tests automatiques du BAOULÉ (étape 3), sans Internet : DeepSeek, Google, OmniVoice et l'écoute sont simulés
(sauf le test marqué « modèle », qui charge le vrai modèle d'écoute baoulé s'il est présent).

    env\\Scripts\\python.exe -m pytest tests -q
"""
import io
from datetime import datetime
import wave
from concurrent.futures import Future

import numpy as np
import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import (baoule_ecoute, baoule_relais, baoule_texte, conversation, dioula_ecoute, dioula_relais, dioula_routage, garde_langue, langues, salutations, securite, service_chat, voix, voix_baoule)
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur


VRAI_PREPARER = voix.preparer


@pytest.fixture(autouse=True)
def base_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])        # aucune voix fabriquée pendant les tests
    monkeypatch.setattr(voix_baoule, "disponible", lambda: False)    # jamais le vrai OmniVoice (sauf test qui le simule)
    # ces tests vérifient l'ANCIEN chemin libre (gardé en secours de la chaîne robuste : tests/unitaires/test_baoule_chaine.py)
    monkeypatch.setenv("CHATBOT_BAOULE_CHAINE", "0")
    monkeypatch.setattr(salutations, "maintenant", lambda: datetime(2026, 10, 9, 20, 0))   # 20 h : 1re réponse « Anun o. »
    securite.remettre_a_zero()
    yield
    securite.remettre_a_zero()


def bci(texte_francais):
    return f"Ɔ ti kpa {len(texte_francais)} lika'n."


@pytest.fixture
def google(monkeypatch):
    """Google simulé : aller = traduction française ; retour = une phrase baoulé par phrase française."""
    vu = {"aller": [], "retour": []}

    def traduire(service, sens, texte):
        if sens == "bci_vers_fr":
            vu["aller"].append(texte)
            return "Comment recharger mon compteur ?"
        if sens == "vers_bci":
            vu["retour"].append(texte)
            return "?" + bci(texte)                     # « ? » parasite de Google au début : doit être retiré
        raise AssertionError(sens)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    return vu


def appels_successifs(*reponses):
    compteur = {"n": 0}

    def ouvrir(systeme, historique):
        compteur["n"] += 1
        compteur.setdefault("dossiers", []).append(historique[-1]["texte"])
        compteur.setdefault("systemes", []).append(systeme)
        return iter(reponses[min(compteur["n"], len(reponses)) - 1])
    return [("DeepSeek", "ds", ouvrir)], compteur


# ── Langue ─────────────────────────────────────────────────────────────────────
def test_baoule_dans_le_menu_mais_pas_dans_les_langues_directes():
    assert langues.valide("bci") and langues.est_relais("bci") and "bci" not in langues.LANGUES
    assert any(l["code"] == "bci" and "Baoulé" in l["nom"] for l in langues.liste_pour_page())


@pytest.mark.parametrize("texte", ["Min mɛtɛri'n diman junman kun.", "Amun nunnun frigo'n.",
                                   "Wafa sɛ yɛ n kwla fa min mɛtɛri'n n gua nun ɔn ?", "Andɛ'n, ɔ ti cɛn dan.",
                                   "Kɛ ɔ fɛ i aeroport su lele mon fa ju Hôtel Ivoire lɔ'n", "Ɛɛ.", "Tchɛtchɛ.", "Tʃɛtʃɛ"])
def test_textes_baoule_reconnus(texte):
    assert baoule_texte.langue_locale(texte)[0] == "bci"
    assert service_chat.choisir_langue("sess-bci-" + str(abs(hash(texte)))[:10], texte, "auto", None)[0] == "bci"


@pytest.mark.parametrize("texte", ["N ka kuran juru banna, n bɛ se ka mun kɛ ?", "I ni ce kosɔbɛ", "Yala aw b'a fɛ ka frigo datugu wa?"])
def test_dioula_reste_du_dioula(texte):
    assert service_chat.choisir_langue("sess-dy2-" + str(abs(hash(texte)))[:10], texte, "auto", None)[0] == "dyu"


@pytest.mark.parametrize("texte", ["Éteins le ventilateur du salon.", "Combien me reste-t-il de crédit ?", "Merci beaucoup"])
def test_francais_reste_du_francais(texte):
    assert service_chat.choisir_langue("sess-fr2-" + str(abs(hash(texte)))[:10], texte, "auto", None)[0] == "fr"


def test_oui_court_dans_une_conversation_en_baoule():
    conversation.noter_langue("sess-bci-conv", "bci")
    assert service_chat.choisir_langue("sess-bci-conv", "ɔɔ", "auto", None)[0] == "bci"


@pytest.mark.parametrize("texte", ["réponds-moi en baoulé", "parle baoulé", "answer in baoule", "wawle nun"])
def test_demande_explicite_de_baoule(texte):
    assert garde_langue.demande_explicite(texte) == "bci"


# ── Texte baoulé : formules et nombres ─────────────────────────────────────────
def test_oui_non_exacts():
    assert ("ɛɛ", "oui") in baoule_texte.formules_reconnues("Ɛɛ.")
    assert any(s == "non" for _, s in baoule_texte.formules_reconnues("Tʃɛtʃɛ, yaci i lɛ."))
    assert not any(s == "oui" for _, s in baoule_texte.formules_reconnues("E ti su"))    # « e » = nous, pas « oui »


@pytest.mark.parametrize("texte, valeur", [("blu ni kun", 11), ("Blu ni kun gua nsan su ɔ yo blu ni nnan", 11),
                                           ("akpi nnyon ni nnyon", 2002), ("abla ni nnun", 25), ("ya nsan", 300),
                                           ("sika akpi nnun", 5000), ("N tuali sika akpi blu annunman", 10000),
                                           ("akpi nɲɔn", 2000), ("ablasan", 30), ("5000 francs", 5000)])
def test_nombres_baoule(texte, valeur):
    assert baoule_texte.lire_nombres(texte)[0]["valeur"] == valeur


def test_mots_seuls_ambigus_pas_lus_comme_nombres():
    assert baoule_texte.lire_nombres("Sran kun ɔ ti lɔ") == []            # « kun » = un certain


def test_glossaire_donne_le_sens_des_mots_aoceda():
    g = baoule_texte.lexique_utile("Min mɛtɛri'n diman junman kun, kuran'n w'a wie")
    assert "mɛtɛri" in g and "kuran" in g and "compteur" in g["mɛtɛri"]


# ── Baoulé ou dioula, à l'oral ─────────────────────────────────────────────────
def lecteur(latin, libre=None):
    return lambda: (latin, libre if libre is not None else latin)


def test_routage_vocal_baoule():
    d = dioula_routage.decider({"yo": 0.3, "sw": 0.2}, lecteur("min meteri'n di man junman kun"),
                               lire_baoule=lambda: "min mɛtɛri'n diman junman kun")
    assert d["langue"] == "bci" and d["chemin"] == "baoule"


def test_routage_vocal_dioula_avec_oreille_baoule():
    d = dioula_routage.decider({"yo": 0.3, "sw": 0.2}, lecteur("n ka kuran juru banna n bɛ se ka mun kɛ"),
                               lire_baoule=lambda: "n ka kuran jru bana be se ka mun ke")
    assert d["langue"] == "dyu" and d["chemin"] == "omni"


def test_routage_conversation_baoule_douteux_reste_baoule():
    d = dioula_routage.decider({"ko": 0.3}, lecteur("a a"), langue_conversation="bci", lire_baoule=lambda: "ɛɛ")
    assert d["langue"] == "bci"


def test_routage_whisper_sur_passe_avant_tout():
    appels = []
    d = dioula_routage.decider({"fr": 0.98}, lecteur("x"), lire_baoule=lambda: appels.append(1) or "x")
    assert d["chemin"] == "whisper" and appels == []                   # aucune écoute locale : 0 seconde perdue


def test_routage_sans_oreille_baoule_inchange():
    assert dioula_routage.decider({"ja": 0.3}, lecteur("n ka kuran juru banna"))["langue"] == "dyu"


# ── Google (relais baoulé) ─────────────────────────────────────────────────────
def test_point_d_interrogation_parasite_retire(google):
    out, service = baoule_relais.vers_baoule("Comment recharger ?")
    assert not out.startswith("?") and service == "google"


def test_oui_ou_non_jamais_traduit_oui_ou_oui(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: "Amun se kɛ ɛɛ annzɛ ɛɛ.")
    out, _ = baoule_relais.vers_baoule("Confirmez par oui ou non.")
    assert out == "Amun se kɛ ɛɛ annzɛ cɛcɛ."


def test_traduction_restee_en_francais_refusee(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: t)
    with pytest.raises(dioula_relais.RelaisIndisponible):
        baoule_relais.vers_baoule("Rechargez votre compteur avant ce soir, s'il vous plaît.")


# ── Service baoulé (DeepSeek et Google simulés) ────────────────────────────────
def test_question_ecrite_en_baoule_de_bout_en_bout(google):
    liste, compteur = appels_successifs(["INTENTION : recharger le compteur\nCERTITUDE : haute\n\n"
                                         "Achetez du crédit. Tapez le code sur le compteur."])
    ev = list(service_chat.repondre("sess-bci-001", "Wafa sɛ yɛ n kwla fa min mɛtɛri'n n gua nun ɔn ?", "bci", None,
                                    "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    assert ev[0] == {"type": "langue", "code": "bci", "source": "menu", "confiance": 1.0}
    assert fin["intention"] == "recharger le compteur" and fin["langue_voix"] == "bci"
    assert fin["texte"] == "Anun o. " + bci("Achetez du crédit.") + " " + bci("Tapez le code sur le compteur.")
    assert fin["francais"] == "Bonsoir. Achetez du crédit. Tapez le code sur le compteur."
    assert "Traduction automatique Google (baoulé -> français) : « Comment recharger mon compteur ? »" in compteur["dossiers"][0]
    assert "compteur" in compteur["dossiers"][0] and "BAOULÉ" in compteur["systemes"][0]
    assert conversation.langue("sess-bci-001") == "bci"


def test_pas_compris_baoule_reponse_de_deepseek_pas_de_phrase_fixe(google):
    # retour client 30/09/2026 : « N wunmɛn i wlɛ kpa... » à chaque fois, même avec une intention devinée
    liste, compteur = appels_successifs(["INTENTION : ?\nCERTITUDE : basse\n\n"
                                         "Vous parlez peut-être du courant. Est-ce une coupure ou le crédit ?"])
    ev = list(service_chat.repondre("sess-bci-002", "hh gg", "bci", None, "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    assert compteur["n"] == 1 and "fixe" not in fin                      # traduction déjà au dossier : pas de relance
    assert fin["texte"] == "Anun o. " + bci("Vous parlez peut-être du courant.") + " " + bci("Est-ce une coupure ou le crédit ?")


def test_google_bci_vers_fr_reessaie_une_fois(monkeypatch):
    essais = []

    def capricieux(service, sens, texte):                 # 1er appel raté (vu le 30/09/2026 sur « ne tianyi »)
        essais.append(1)
        if len(essais) == 1:
            raise dioula_relais.RelaisIndisponible("google : erreur passagère")
        return "et Tianyi"
    monkeypatch.setattr(dioula_relais, "traduire", capricieux)
    r = baoule_relais.vers_francais("ne tianyi")
    assert r["google"] == "et Tianyi" and len(essais) == 2 and len(r["erreurs"]) == 1


def test_google_bci_vers_fr_vide_reessaye_puis_none(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: "  ")
    r = baoule_relais.vers_francais("ne tianyi")
    assert r["google"] is None and r["erreurs"] == ["google : traduction vide"] * 2


def test_google_en_panne_reponse_en_francais_voix_francaise(monkeypatch):
    def panne(service, sens, texte):
        raise dioula_relais.RelaisIndisponible("google : hors ligne")
    monkeypatch.setattr(dioula_relais, "traduire", panne)
    monkeypatch.setattr(baoule_relais, "DELAI_TOTAL_RETOUR_S", 1.0)
    liste, _ = appels_successifs(["INTENTION : salutation\nCERTITUDE : haute\n\nBonjour à vous. Comment puis-je vous aider ?"])
    ev = list(service_chat.repondre("sess-bci-003", "Aɲiho", "bci", None, "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    # tout est resté en français : la salutation aussi (« Bonsoir. », pas « Awossi'n o. » lu avec la voix française),
    # et le « Bonjour à vous » du cerveau IA est retiré en entier (pas de « À vous. » qui traîne)
    assert fin["texte"] == "Bonsoir. Comment puis-je vous aider ?" and fin["non_traduit"] == 1 and fin["langue_voix"] == "fr"


def test_nombre_relu_donne_a_deepseek(google):
    liste, compteur = appels_successifs(["INTENTION : recharger 5000\nCERTITUDE : moyenne\n\nConfirmez-vous ?"])
    list(service_chat.repondre("sess-bci-004", "N kunndɛ kɛ ń fá sika akpi nnun ń mán.", "bci", None, "femme", liste=liste))
    assert "« akpi nnun » = 5000" in compteur["dossiers"][0] and "je veux" in compteur["dossiers"][0]


# ── Voix baoulé (OmniVoice simulé) ─────────────────────────────────────────────
def test_voix_baoule_une_seule_fois_en_file_puis_sur_le_disque(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    fabriquees = []

    def fabriquer(texte):
        fabriquees.append(texte)
        return b"RIFF" + b"\x00" * 2000
    monkeypatch.setattr(voix_baoule, "fabriquer", fabriquer)
    etat, tache, rang = voix.demander_baoule("Ɔ ti kpa.")
    etat2, tache2, _ = voix.demander_baoule("Ɔ ti kpa.")                 # 2e demande pendant la fabrication
    assert etat == "preparation" and rang >= 1 and (tache2 is tache or etat2 == "prete")
    tache.result(timeout=5)
    etat3, tache3, _ = voix.demander_baoule("Ɔ ti kpa.")
    assert etat3 == "prete" and tache3.result()[1]["cache"] and fabriquees == ["Ɔ ti kpa."]


def test_voix_baoule_en_panne_signalee_sans_relancer_en_boucle(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    essais = []

    def panne(texte):
        essais.append(texte)
        raise voix_baoule.AtelierIndisponible("modèle introuvable")
    monkeypatch.setattr(voix_baoule, "fabriquer", panne)
    etat, tache, _ = voix.demander_baoule("Ɔ ti kpa kpa.")
    with pytest.raises(Exception):
        tache.result(timeout=5)
    for _ in range(3):                                          # la page redemande toutes les 10 s
        assert voix.demander_baoule("Ɔ ti kpa kpa.")[0] == "echec"
    assert len(essais) == 1                                     # pas de relance à chaque demande


def test_api_voix_baoule_en_preparation_puis_prete(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    monkeypatch.setattr(voix_baoule, "disponible", lambda: True)
    f = Future()
    monkeypatch.setattr(voix, "demander_baoule_reponse", lambda t: ("preparation", None, 2, (1, 3)))
    client = TestClient(serveur.app)
    conversation.autoriser_voix("sess-voix-bci", ["Ɔ ti kpa."])
    r = client.post("/api/voix", json={"session": "sess-voix-bci", "texte": "Ɔ ti kpa.", "langue": "bci"})
    assert r.status_code == 202 and r.json()["etat"] == "preparation" and r.json()["attente_s"] > 0
    assert r.json()["phrases_pretes"] == 1 and r.json()["phrases"] == 3
    f.set_result((b"RIFF" + b"\x00" * 100, {"moteur": "OmniVoice", "voix": "rk", "mime": "audio/wav"}))
    monkeypatch.setattr(voix, "demander_baoule_reponse", lambda t: ("prete", f, 0, (3, 3)))
    r = client.post("/api/voix", json={"session": "sess-voix-bci", "texte": "Ɔ ti kpa.", "langue": "bci"})
    assert r.status_code == 200 and r.content.startswith(b"RIFF")


def wav_ton(secondes, sr=24000):
    import soundfile as sf
    t = np.arange(int(sr * secondes)) / sr
    buf = io.BytesIO()
    sf.write(buf, (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr, format="WAV")
    return buf.getvalue()


def test_reponse_baoule_en_un_seul_audio_continu(tmp_path, monkeypatch):
    """Bug vu le 30/09/2026 : la 1re phrase se lisait, puis plusieurs minutes de silence (on croyait l'audio coupé)."""
    import soundfile as sf
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    fabriquees = []
    monkeypatch.setattr(voix_baoule, "fabriquer", lambda t: fabriquees.append(t) or wav_ton(1.0))
    reponse = "N kwlá nunnunman frigo'n min bɔbɔ. Amun tɛ su kɛ ɛɛ annzɛ cɛcɛ."
    assert voix.phrases_baoule(reponse) == ["N kwlá nunnunman frigo'n min bɔbɔ.", "Amun tɛ su kɛ ɛɛ annzɛ cɛcɛ."]
    etat, _, _, (faites, total) = voix.demander_baoule_reponse(reponse)
    assert etat == "preparation" and total == 2
    import time as _t
    for _ in range(50):
        etat, tache, _, (faites, total) = voix.demander_baoule_reponse(reponse)
        if etat == "prete":
            break
        _t.sleep(0.1)
    audio, infos = tache.result()
    son, sr = sf.read(io.BytesIO(audio))
    assert etat == "prete" and abs(len(son) / sr - (2.0 + voix.PAUSE_ENTRE_PHRASES_S)) < 0.05     # 2 phrases collées
    assert fabriquees == voix.phrases_baoule(reponse)                           # chaque phrase fabriquée UNE fois
    assert voix.demander_baoule_reponse(reponse)[0] == "prete" and len(fabriquees) == 2   # ensuite : instantané


def test_page_demande_la_reponse_baoule_entiere(google):
    client = TestClient(serveur.app)
    r = client.post("/api/voix/morceaux", json={"session": "sess-morc-rep", "texte": "Ɔ ti kpa. Amun tɛ su.", "langue": "bci"})
    assert r.json()["morceaux"] == ["Ɔ ti kpa. Amun tɛ su."]
    liste, _ = appels_successifs(["INTENTION : salutation\nCERTITUDE : haute\n\nBonjour. Je vous aide."])
    ev = list(service_chat.repondre("sess-aut-bci", "Aɲiho", "bci", None, "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    assert conversation.voix_autorisee("sess-aut-bci", voix.texte_pour_voix(fin["texte"]))   # réponse entière autorisée


def test_api_voix_baoule_refusee_pour_un_texte_pas_ecrit_par_le_chatbot():
    client = TestClient(serveur.app)
    r = client.post("/api/voix", json={"session": "sess-voix-bci2", "texte": "Texte inventé.", "langue": "bci"})
    assert r.status_code == 403


# ── Écoute baoulé (modèle simulé) ──────────────────────────────────────────────
def fausse_ecoute(texte, trames=10):
    mots = [{"mot": m, "certitude": 0.9, "t0": 2 * i, "t1": 2 * i + 1} for i, m in enumerate(texte.split())]
    return dioula_ecoute.Ecoute(mots, np.zeros((trames, 3), dtype="float32"), 1.0, 0.1, texte)


def wav_bytes(secondes, valeur=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.full(int(16000 * secondes), valeur, dtype="<i2").tobytes())
    return buf.getvalue()


def test_baoule_du_menu_ecoute_par_l_oreille_baoule(monkeypatch):
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("min mɛtɛri'n diman junman"))
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: pytest.fail("oreille dioula utilisée"))
    r = voix.transcrire(wav_bytes(2), "bci", session="sess-tr-bci")
    assert r["langue"] == "bci" and r["texte"] == "min mɛtɛri'n diman junman" and r["baoule"]["brut"] == r["texte"]


def test_morceaux_baoule_ecoutes_pendant_la_parole(monkeypatch):
    ecoutes = iter(["min mɛtɛri'n", "diman junman", "kun"])
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute(next(ecoutes)))
    voix.ecouter_morceau(wav_bytes(2), "sess-morc-bci", 0, "bci")
    voix.ecouter_morceau(wav_bytes(2), "sess-morc-bci", 1, "bci")
    e = voix._reprendre_morceaux("sess-morc-bci", 2, np.zeros(16000 * 5, dtype="float32"), "bci")
    assert e.texte == "min mɛtɛri'n diman junman kun"


def test_morceaux_d_une_autre_langue_jamais_reutilises(monkeypatch):
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("n ka"))
    voix.ecouter_morceau(wav_bytes(2), "sess-morc-mix", 0, "dyu")
    assert voix._reprendre_morceaux("sess-morc-mix", 1, np.zeros(16000 * 3, dtype="float32"), "bci") is None


def test_api_morceau_baoule(monkeypatch):
    vu = {}
    monkeypatch.setattr(voix, "ecouter_morceau", lambda o, s, r, l="dyu": vu.update(langue=l) or {"rang": r, "duree_s": 2})
    client = TestClient(serveur.app)
    r = client.post("/api/transcrire/morceau", files={"audio": ("m.wav", wav_bytes(2), "audio/wav")},
                    data={"session": "sess-api-morc", "rang": 0, "langue": "bci"})
    assert r.status_code == 200 and vu["langue"] in ("bci", "dyu")


def test_formule_courte_effacee_par_whisper_reprise_de_l_oreille(monkeypatch):
    class FauxWhisper:
        def detect_language(self, audio):
            return "fr", 0.35, [("fr", 0.35), ("pt", 0.3)]
    monkeypatch.setitem(voix._whisper, "detecteur", FauxWhisper())
    monkeypatch.setitem(voix._whisper, "modele", object())
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(voix, "_whisper_texte", lambda audio, langue, annulation=None: ("", langue, 1.0))     # filtre de silence
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("non merci"))
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("non merci"))
    r = voix.transcrire(wav_bytes(2))
    assert r["texte"] == "non merci" and r["langue"] == "fr" and r["parole"]


class WhisperSur:
    def __init__(self, langue, p):
        self.langue, self.p = langue, p

    def detect_language(self, audio):
        return self.langue, self.p, [(self.langue, self.p)]


def test_menu_baoule_mais_on_parle_francais_whisper_ecrit_le_francais(monkeypatch):
    monkeypatch.setitem(voix._whisper, "detecteur", WhisperSur("fr", 0.98))
    monkeypatch.setitem(voix._whisper, "modele", object())
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(voix, "_whisper_texte", lambda audio, langue, annulation=None: ("Qu'est-ce que tu peux faire ?", langue, 1.0))
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: pytest.fail("oreille baoulé sur du français"))
    r = voix.transcrire(wav_bytes(2), "bci", session="sess-menu-fr")
    assert r["langue"] == "fr" and r["texte"] == "Qu'est-ce que tu peux faire ?" and r["routage"]["chemin"] == "menu-whisper"


def test_menu_baoule_et_on_parle_baoule_oreille_baoule(monkeypatch):
    monkeypatch.setitem(voix._whisper, "detecteur", WhisperSur("yo", 0.3))
    monkeypatch.setitem(voix._whisper, "modele", object())
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(baoule_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("amun nunnun frigo'n"))
    assert voix.transcrire(wav_bytes(2), "bci", session="sess-menu-bci")["langue"] == "bci"


def test_question_francaise_reponse_baoule_pas_de_traduction_de_la_question(google):
    liste, compteur = appels_successifs(["INTENTION : ce que l'assistant sait faire\nCERTITUDE : haute\n\nJe vous aide."])
    ev = list(service_chat.repondre("sess-fr-bci", "Qu'est-ce que tu peux faire concrètement ?", "bci", "fr", "femme",
                                    liste=liste, origine="vocal"))
    fin = next(e for e in ev if e["type"] == "fin")
    assert google["aller"] == [] and "en FRANÇAIS" in compteur["dossiers"][0] and fin["langue_voix"] == "bci"
    assert fin["texte"] == "Anun o. " + bci("Je vous aide.")      # la réponse reste en baoulé (menu)


def test_voix_baoule_abandonnee_si_plus_personne_n_attend(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    monkeypatch.setattr(voix, "ABANDON_S", -1)                         # « plus personne n'attend » tout de suite
    fabriquees = []
    monkeypatch.setattr(voix_baoule, "fabriquer", lambda t: fabriquees.append(t) or b"RIFF" + b"\x00" * 100)
    _, tache, _ = voix.demander_baoule("Ɔ ti kpa ekun.")
    with pytest.raises(voix.VoixAbandonnee):
        tache.result(timeout=5)
    assert fabriquees == []                                            # aucune minute de processeur dépensée
    monkeypatch.setattr(voix, "ABANDON_S", 45)
    _, tache, _ = voix.demander_baoule("Ɔ ti kpa ekun.")               # redemandée : elle repart
    tache.result(timeout=5)
    assert fabriquees == ["Ɔ ti kpa ekun."]


def test_reponse_baoule_ne_lance_aucune_voix_toute_seule(monkeypatch):
    demandes = []
    monkeypatch.setattr(voix, "demander_baoule", lambda *a, **k: demandes.append(a))
    assert VRAI_PREPARER(["Ɔ ti kpa."], "bci") == [] and demandes == []   # seulement à la demande (Écouter)


# ── Volume remonté (bug trouvé sur de vraies voix baoulé) ──────────────────────
def test_vocal_tres_faible_remonte_mais_pas_le_silence():
    t = np.arange(16000) / 16000
    faible = (0.002 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    assert abs(float(np.abs(dioula_ecoute.remonter_volume(faible)).max()) - dioula_ecoute.VOLUME_CIBLE) < 1e-3
    assert float(np.abs(dioula_ecoute.remonter_volume(np.zeros(16000, dtype="float32"))).max()) == 0.0
    normal = (0.4 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    assert np.array_equal(dioula_ecoute.remonter_volume(normal), normal)


# ── Modèle d'écoute baoulé réel (si présent sur le disque) ─────────────────────
@pytest.mark.skipif(not baoule_ecoute.disponible(), reason="modèle baoulé absent")
def test_modele_baoule_reel_silence_et_son():
    e = baoule_ecoute.transcrire_audio(np.zeros(16000, dtype="float32"))
    assert e.texte == "" and e.mots == []
    t = np.arange(16000 * 2) / 16000
    e = baoule_ecoute.transcrire_audio((0.1 * np.sin(2 * np.pi * 220 * t)).astype("float32"))
    assert isinstance(e.texte, str) and 0.0 <= e.certitude <= 1.0 and e.moteur is baoule_ecoute.MOTEUR


def test_le_courant_est_monte_question_donnee_par_le_client():
    """05/10/2026 : « yo kuran yafɔsɛ » = « le courant est monté ? » (une question), pas « coupe le courant »."""
    from apps.ai_assistant.chatbot import baoule_texte
    for t in ("yo kuran yafɔsɛ", "yo kuran yafɔsuɛ", "kuran yafɔsɛ"):
        assert any("le courant est monté ?" in s for _, s in baoule_texte.formules_reconnues(t)), t
    assert "monter" in baoule_texte.lexique_utile("ya fɔsuɛ")["yafɔsuɛ"]


def test_phrase_de_reference_reconnue_meme_abimee_et_pas_au_hasard():
    from apps.ai_assistant.chatbot import baoule_texte
    p = baoule_texte.phrase_proche("Wafa sɛ yɛ n kwla fa min mɛtɛri n gua nun")          # « recharger mon compteur »
    assert p and "recharger" in p[0]["sens"] and p[1] >= 0.72
    assert baoule_texte.phrase_proche("yo kuran yafɔsuɛ")[0]["verifiee"]
    for t in ("bukina faso togo liberia mali gine", "mi kpanngɔ i jam be ti kukluku", "awon ki kpa", "kuran"):
        assert baoule_texte.phrase_proche(t) is None, t


def test_jamais_pas_compris_et_jamais_la_meme_reponse():
    from apps.ai_assistant.chatbot import consignes
    for c in (consignes.systeme_baoule(), consignes.systeme_dioula()):
        assert "JAMAIS de phrase du type « je n'ai pas compris »" in c and "Même si tu as mal compris, tu RÉPONDS" in c
        assert "Ne répète JAMAIS une de tes réponses précédentes" in c and "suis la règle du « pas compris »" not in c
