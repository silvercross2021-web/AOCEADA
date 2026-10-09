"""Tests des CORRECTIONS de l'audit du 09/10/2026 (rapport : 5 problèmes importants, 13 moyens, 16 mineurs).
Chaque test reproduit le scénario qui montrait le défaut et vérifie qu'il ne se produit plus. Sans Internet : DeepSeek,
Whisper, les oreilles, les traducteurs, Gemini et le GPU sont simulés. Les tests de la chaîne baoulé (I2, I3, voix GPU
fabriquée d'office) sont dans test_baoule_chaine.py, ceux du GPU réveillé par un faux fichier dans test_voix_gpu.py.

    env\\Scripts\\python.exe -m pytest tests\\unitaires\\test_audit_09_10.py -q
"""
import asyncio
import io
import json
import socket
import threading
import time
import wave
from concurrent.futures import Future

import numpy as np
import pytest
import requests
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import (baoule_ecoute, baoule_relais, conversation, dioula_ecoute, dioula_relais, dioula_routage, erreurs, fournisseurs, live_agent, securite, voix, voix_gpu)
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur
from apps.ai_assistant.chatbot.cles_gemini import Reserves


@pytest.fixture(autouse=True)
def base_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])          # jamais de vraie voix (Internet)
    securite.remettre_a_zero()
    yield
    securite.remettre_a_zero()


def wav_bytes(secondes, valeur=1, taux=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taux)
        w.writeframes(np.full(int(taux * secondes), valeur, dtype="<i2").tobytes())
    return buf.getvalue()


# ── I1. Bouton « Stop » / onglet fermé : la réponse s'arrête VRAIMENT et sa question est retirée ─────────────────────
def test_une_reponse_arretee_ne_retire_que_sa_propre_question():
    """Le nettoyage tardif d'une réponse arrêtée effaçait « la dernière question » : la NOUVELLE question de la personne."""
    _, q1 = conversation.poser_question("sess-id-1", "Question arrêtée")
    conversation.poser_question("sess-id-1", "Nouvelle question")
    conversation.annuler_question("sess-id-1", q1)
    assert conversation.historique("sess-id-1") == [{"role": "user", "texte": "Nouvelle question"}]
    conversation.annuler_question("sess-id-1", q1)                       # déjà retirée : rien d'autre ne bouge
    assert len(conversation.historique("sess-id-1")) == 1


def test_arret_demande_deepseek_s_arrete_sans_attendre_son_premier_mot():
    """La page coupe AVANT le 1er mot (DeepSeek lent) : la course s'arrête en ~0,1 s (avant : jusqu'à 45 s, payés)."""
    arret, ouverts = threading.Event(), []

    def lent(systeme, historique):
        ouverts.append(1)
        time.sleep(5)
        yield "trop tard"
    jeton = fournisseurs.ARRET.set(arret)
    try:
        threading.Timer(0.3, arret.set).start()
        t = time.time()
        with pytest.raises(fournisseurs.Abandon):
            list(fournisseurs.repondre_flux("s", [{"role": "user", "texte": "x"}], liste=[("DeepSeek", "ds", lent)]))
        assert time.time() - t < 1.5 and ouverts == [1]
    finally:
        fournisseurs.ARRET.reset(jeton)


def demarrer_serveur_reel():
    """Vrai serveur uvicorn (dans un fil) avec l'application ASGI d'AOCEDA (aoceda/asgi.py), sans modèle chargé."""
    import uvicorn

    from aoceda.asgi import application
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    fil = threading.Thread(target=srv.run, daemon=True)
    fil.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    return srv, fil, port


@pytest.mark.parametrize("avant_premier_mot", [False, True])
def test_page_qui_coupe_la_question_est_retiree_et_deepseek_arrete(monkeypatch, avant_premier_mot):
    """Vrai serveur, vraie coupure de connexion (comme le bouton Stop) : avant, avec Starlette 1.7 / uvicorn 0.54, le
    nettoyage n'avait lieu qu'au passage du ramasse-miettes (question restée, DeepSeek payé jusqu'au bout)."""
    produits = []

    def deepseek(systeme, historique):
        if avant_premier_mot:
            time.sleep(30)
        for i in range(400):
            produits.append(i)
            time.sleep(0.05)
            yield f"Le compteur prépayé fonctionne avec du crédit, explication numéro {i}. "
    monkeypatch.setattr(fournisseurs, "candidats", lambda: [("DeepSeek", "simulé", deepseek)])
    srv, fil, port = demarrer_serveur_reel()
    try:
        session = "sess-coupure-" + ("a" if avant_premier_mot else "b")
        from apps.ai_assistant.tests_chatbot.client_test import compte_client
        jeton = compte_client()[1]
        r = requests.post(f"http://127.0.0.1:{port}/api/assistant/message", json={"session": session, "texte": "Explique-moi tout."},
                          headers={"Authorization": f"Bearer {jeton}"}, stream=True, timeout=10)
        lus = 0
        for ligne in r.iter_lines(decode_unicode=True):
            if ligne.startswith("data:"):
                lus += 1
            if lus >= (1 if avant_premier_mot else 4):
                break
        assert [m["role"] for m in conversation.historique(session)] == ["user"]      # la question est posée
        r.close()                                                                     # la page coupe
        t = time.time()
        while conversation.historique(session) and time.time() - t < 5:
            time.sleep(0.05)
        assert conversation.historique(session) == []                                 # retirée, et vite
        assert time.time() - t < 3
        n = len(produits)
        time.sleep(0.6)
        assert len(produits) <= n + 1                                                 # DeepSeek ne produit plus rien
    finally:
        srv.should_exit = True
        fil.join(10)


# ── I5. Noms d'hôte, origine des demandes, en-têtes de protection ───────────────────────────────────────────────────
def test_nom_d_hote_etranger_refuse_dns_rebinding():
    """AOCEDA : un site piégé (nom d'hôte qui pointe vers ce serveur) n'a pas le jeton du client, gardé par le navigateur
    pour la vraie adresse d'AOCEDA seulement : sans jeton, rien ne passe (au laboratoire, sans compte : contrôle de l'hôte)."""
    c = TestClient(serveur.app, jeton=False)
    assert c.get("/api/config", headers={"host": "attaquant.example"}).status_code == 401
    assert c.post("/api/nouvelle", json={"session": "sess-hote-1"}, headers={"host": "attaquant.example:8770"}).status_code == 401
    for hote in ("127.0.0.1:8770", "localhost:8770", "[::1]:8770", "192.168.1.20:8770"):
        assert TestClient(serveur.app).get("/api/config", headers={"host": hote}).status_code == 200, hote


def test_demande_venue_d_un_autre_site_refusee():
    """Une page web piégée ne peut pas poser de question payante ni réveiller le GPU : elle n'a pas le jeton du client
    (AOCEDA : connexion par jeton dans l'en-tête, jamais par cookie, donc rien à « emprunter » au navigateur)."""
    c = TestClient(serveur.app, jeton=False)
    for route, corps in (("/api/nouvelle", {"session": "sess-orig-1"}), ("/api/baoule/reveil", {"session": "sess-orig-1"}),
                         ("/api/message", {"session": "sess-orig-1", "texte": "Bonjour"})):
        assert c.post(route, json=corps, headers={"origin": "http://attaquant.example"}).status_code == 401, route
    assert c.post("/api/nouvelle", json={"session": "sess-orig-1"}, headers={"origin": "null"}).status_code == 401
    assert TestClient(serveur.app).post("/api/nouvelle", json={"session": "sess-orig-1"},
                                        headers={"origin": "http://testserver"}).status_code == 200
    r = c.post("/api/transcrire", files={"audio": ("a.wav", b"x", "audio/wav")}, data={"session": "sess-orig-1"},
               headers={"origin": "http://attaquant.example"})
    assert r.status_code == 401                                                 # multipart compris (I4)
    # et un jeton d'un AUTRE compte ne donne jamais accès à la conversation de ce client
    assert TestClient(serveur.app).post("/api/message", json={"session": "sess-orig-2", "texte": "x"}).status_code in (200,)
    autre = TestClient(serveur.app, email="autre-client@test.ci")
    assert autre.post("/api/nouvelle", json={"session": "sess-orig-2"}).status_code == 403


def test_entetes_de_protection_et_politique_de_contenu():
    """La page de l'assistant garde la politique de contenu du laboratoire ; elle s'affiche dans AOCEDA seulement
    (frame-ancestors 'self' : le cadre de la page « Assistant IA »). L'API ne s'affiche nulle part."""
    r = TestClient(serveur.app).get("/")
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp and "ws://testserver" in csp and "object-src 'none'" in csp
    assert "https://fonts.googleapis.com" in csp and "blob:" in csp
    assert r.headers["x-frame-options"] == "SAMEORIGIN" and r.headers["x-content-type-options"] == "nosniff"
    assert "microphone=(self)" in r.headers["permissions-policy"]
    r = TestClient(serveur.app).get("/api/config")
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert "ws://ev il" not in securite.politique_contenu("ev il\r\nX: y")     # nom d'hôte bizarre : jamais recopié


def test_erreur_imprevue_message_propre_avec_entetes_et_detail_dans_le_journal(monkeypatch):
    monkeypatch.setattr(serveur.langues, "liste_pour_page", lambda: (_ for _ in ()).throw(RuntimeError("détail interne")))
    r = TestClient(serveur.app, raise_server_exceptions=False).get("/api/config")
    assert r.status_code == 500 and "détail interne" not in r.text and r.json()["erreur"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert "détail interne" in erreurs.FICHIER.read_text(encoding="utf-8")


# ── m1. Bouton baoulé mal formé : plus d'erreur 500 ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("action", [{"type": "choix", "demande": ["credit_restant"]}, {"type": "choix", "demande": {"a": 1}},
                                    {"type": ["oui"]}, {"type": "choix"}])
def test_action_mal_formee_ignoree_jamais_d_erreur_500(monkeypatch, action):
    monkeypatch.setattr(fournisseurs, "candidats", lambda: [("DeepSeek", "simulé", lambda s, h: iter(["Bonjour."]))])
    r = TestClient(serveur.app).post("/api/message", json={"session": "sess-action-1", "texte": "bonjour", "action": action})
    assert r.status_code == 200 and '"type": "fin"' in r.text


# ── m6. Limites de débit sur les routes qui calculent ou lisent beaucoup ─────────────────────────────────────────────
def test_limites_sur_decoupage_tests_et_etat_live(monkeypatch):
    monkeypatch.setitem(securite.LIMITES, "decoupage", (2, 60))
    monkeypatch.setitem(securite.LIMITES, "lecture", (2, 60))
    c = TestClient(serveur.app)
    corps = {"session": "sess-limite-1", "texte": "Bonjour. Au revoir."}
    assert [c.post("/api/voix/morceaux", json=corps).status_code for _ in range(3)] == [200, 200, 429]
    assert [c.get("/api/live/etat").status_code for _ in range(2)] == [200, 200]
    assert c.get("/api/tests").status_code == 429                               # même famille « lecture »


# ── m5 / I5. Partage public : adresse et en-tête du tunnel crus seulement pendant un VRAI partage ───────────────────
def test_tunnel_ferme_brutalement_son_adresse_n_est_plus_acceptee(tmp_path, monkeypatch):
    f = tmp_path / "partage_public.json"
    f.write_text(json.dumps({"hotes": ["abc.trycloudflare.com"], "pid": 999_999}), encoding="utf-8")
    monkeypatch.setattr(securite, "PARTAGE_PUBLIC", f)
    assert not securite.hote_accepte("abc.trycloudflare.com")                   # programme 999999 : il ne tourne pas
    # AOCEDA : sans jeton du client, rien ne passe par ce nom non plus
    r = TestClient(serveur.app, jeton=False).get("/api/config", headers={"host": "abc.trycloudflare.com"})
    assert r.status_code == 401


# ── I4. GPU payant : plafond de dépense par jour ─────────────────────────────────────────────────────────────────────
def test_plafond_du_jour_du_gpu(monkeypatch):
    monkeypatch.setenv("CEREBRIUM_API_KEY", "cle-de-test")
    monkeypatch.setenv("CHATBOT_VOIX_BAOULE_GPU", "1")
    monkeypatch.setenv("CHATBOT_GPU_MINUTES_JOUR", "2")
    assert voix_gpu.disponible()
    with voix_gpu._budget["verrou"]:
        voix_gpu._minutes_du_jour().update({1, 2})                               # 2 minutes déjà allumées, plus tôt
    assert voix_gpu.budget_epuise() and not voix_gpu.disponible()
    with pytest.raises(voix_gpu.GpuIndisponible, match="plafond"):
        voix_gpu._appeler("fabriquer", {"texte": "x"})
    assert voix_gpu.reveiller("menu") is False                                  # plus de réveil non plus


def test_minutes_comptees_et_gardees_sur_le_disque(monkeypatch):
    monkeypatch.setenv("CEREBRIUM_API_KEY", "cle-de-test")
    voix_gpu._compter_minutes()
    d = json.loads(voix_gpu.FICHIER_BUDGET.read_text(encoding="utf-8"))
    assert len(d["minutes"]) == 2 and d["jour"] == voix_gpu._budget["jour"]
    voix_gpu._budget.update(jour=None, minutes=set())                            # « redémarrage du serveur »
    with voix_gpu._budget["verrou"]:
        assert len(voix_gpu._minutes_du_jour()) == 2


# ── m10. Lot GPU trop long : secours possible (plus de TimeoutError non rattrapée) ──────────────────────────────────
def test_lot_gpu_trop_long_devient_gpu_indisponible(monkeypatch):
    monkeypatch.setattr(voix_gpu, "DELAI_S", -14.8)                              # attente du lot : 0,2 s
    voix_gpu._etat["lots"]["Phrase en attente."] = Future()
    try:
        with pytest.raises(voix_gpu.GpuIndisponible, match="à temps"):
            voix_gpu.fabriquer("Phrase en attente.")
    finally:
        voix_gpu._etat["lots"].pop("Phrase en attente.", None)


# ── M12. Voix baoulé : jamais coupée en plein mot, jamais fabriquée deux fois ───────────────────────────────────────
def test_phrases_baoule_coupees_a_un_espace_et_courtes_collees():
    longue = " ".join(["Kuran'n w'a wie min awlo lɔ"] * 12) + "."            # 340 caractères, aucune virgule
    ph = voix.phrases_baoule("Ɔ ti kpa. " + longue)
    assert all(len(p) <= voix.PHRASE_BAOULE_MAX for p in ph)
    assert ph[0].startswith("Ɔ ti kpa. Kuran'n")                               # la phrase courte est collée à la suivante
    mots = set(" ".join(["Kuran'n w'a wie min awlo lɔ"] * 12).split()) | {"Ɔ", "ti", "kpa.", "lɔ."}
    assert all(set(p.split()) <= mots for p in ph)                              # aucun mot coupé en deux
    assert " ".join(ph) == voix.texte_pour_voix("Ɔ ti kpa. " + longue)


def test_lot_gpu_annonce_avec_la_cle_que_la_voix_demandera(monkeypatch):
    annonces = []
    monkeypatch.setattr(voix_gpu, "disponible", lambda: True)
    monkeypatch.setattr(voix_gpu, "annoncer", lambda phrases: annonces.extend(phrases))
    monkeypatch.setattr(voix, "voix_baoule_prete", lambda p: None)
    texte = " ".join(["Kuran'n w'a wie min awlo lɔ"] * 12) + "."
    voix.annoncer_baoule(texte)
    assert annonces == [voix.texte_pour_voix(p) for p in voix.phrases_baoule(texte)]   # même clé que demander_baoule
    assert all(a == voix.texte_pour_voix(a) for a in annonces)


# ── M7. Vocal Automatique : une phrase claire dans une autre langue n'est pas du baoulé ─────────────────────────────
def test_phrase_allemande_claire_pas_prise_pour_du_baoule():
    d = dioula_routage.decider({"de": 0.98, "en": 0.01}, lambda: ("wie kann ich zu hause strom sparen",) * 2,
                               None, lire_baoule=lambda: "wie kan i su ause strom spara")
    assert d["langue"] == "de" and d["chemin"] == "whisper-force"


def test_autre_langue_mal_entendue_par_whisper_reste_un_indice_faible():
    """Whisper peu sûr (0,3) : le baoulé est encore essayé (les vrais vocaux baoulé font souvent hésiter Whisper)."""
    vu = []
    dioula_routage.decider({"de": 0.3, "sw": 0.2}, lambda: ("wie kann ich zu hause strom sparen",) * 2, None,
                           lire_baoule=lambda: vu.append(1) or "")
    assert vu == [1]


# ── M8. Écoutes anticipées ARRÊTÉES dès qu'elles ne servent plus ────────────────────────────────────────────────────
class FauxDetecteur:
    def __init__(self, probs):
        self.probs = probs

    def detect_language(self, audio):
        top = max(self.probs, key=self.probs.get)
        return top, self.probs[top], list(self.probs.items())


def test_vocal_francais_dans_une_conversation_dioula_l_oreille_dioula_est_arretee(monkeypatch):
    arretee, debut = threading.Event(), threading.Event()

    def oreille(audio, garder_probas=True, annulation=None):
        debut.set()
        for _ in range(200):                                                     # 10 s de « calcul »
            if annulation is not None and annulation.annulee:
                arretee.set()
                raise dioula_ecoute.Annulee()
            time.sleep(0.05)
        return dioula_ecoute.Ecoute([], None, 1.0, 10.0)
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", oreille)
    monkeypatch.setitem(voix._whisper, "detecteur", FauxDetecteur({"fr": 0.98, "en": 0.01}))
    monkeypatch.setitem(voix._whisper, "modele", object())
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(voix, "_whisper_texte", lambda audio, langue, annulation=None: ("Bonjour, ma facture.", langue, 1.0))
    t = time.time()
    r = voix.transcrire(wav_bytes(2), None, langue_conversation="dyu", session="sess-anticipe-1")
    assert r["langue"] == "fr" and r["texte"] == "Bonjour, ma facture."
    assert arretee.wait(2) or not debut.is_set()                                  # arrêtée (ou jamais commencée)
    assert time.time() - t < 3


def test_anticipees_arreter_une_tache_pas_encore_commencee():
    a = voix._Anticipees()
    bloque = threading.Event()
    lancees = []
    # 2 places dans la réserve d'écoute : on les occupe pour que la tâche testée reste en file
    occupees = [voix._pool_ecoute().submit(bloque.wait, 5) for _ in range(voix.TRANSCRIPTIONS_SIMULTANEES)]
    try:
        a.lancer("dyu", lambda audio, annulation=None: lancees.append(1), None)
        a.arreter("dyu")
        assert "dyu" not in a
    finally:
        bloque.set()
        for f in occupees:
            f.result(5)
    time.sleep(0.1)
    assert lancees == []                                                         # elle n'a jamais démarré


def test_annulation_arrete_un_vrai_calcul_onnx_en_cours():
    """onnxruntime : RunOptions.terminate arrête le calcul EN COURS (oreille baoulé, plus petite : ~0,4 Go)."""
    if not baoule_ecoute.disponible():
        pytest.skip("modèle baoulé absent")
    audio = (0.1 * np.sin(2 * np.pi * 220 * np.arange(16000 * 14) / 16000)).astype("float32")
    a, res = dioula_ecoute.Annulation(), {}

    def ecoute():
        try:
            baoule_ecoute.transcrire_audio(audio, annulation=a)
            res["fin"] = "terminée"
        except dioula_ecoute.Annulee:
            res["fin"] = "annulée"
    baoule_ecoute.charger()
    fil = threading.Thread(target=ecoute)
    fil.start()
    time.sleep(0.15)
    t = time.time()
    a.annuler()
    fil.join(30)
    assert res["fin"] == "annulée" and time.time() - t < 5                    # 14 s de son : jamais fini en 0,15 s
    with pytest.raises(dioula_ecoute.Annulee):                                   # déjà annulée : ne calcule même pas
        baoule_ecoute.transcrire_audio(audio, annulation=a)


# ── m9. Décision « baoulé » sans lecture baoulé : plus de KeyError (le vocal passe au dioula) ────────────────────────
def test_decision_baoule_sans_oreille_baoule_passe_au_dioula(monkeypatch):
    monkeypatch.setitem(voix._whisper, "detecteur", FauxDetecteur({"sw": 0.3, "fr": 0.2}))
    monkeypatch.setitem(voix._whisper, "modele", object())
    monkeypatch.setattr(voix, "whisper", lambda: None)
    monkeypatch.setattr(baoule_ecoute, "disponible", lambda: False)
    mots = [{"mot": m, "certitude": 0.9, "t0": 2 * i, "t1": 2 * i + 1} for i, m in enumerate("n ka kuran banna".split())]
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio",
                        lambda a, garder_probas=True, annulation=None: dioula_ecoute.Ecoute(mots, None, 1.0, 0.1, "n ka kuran banna"))
    monkeypatch.setattr(dioula_routage, "decider", lambda *a, **k: {"langue": "bci", "chemin": "baoule", "raison": "test"})
    r = voix.transcrire(wav_bytes(2), None, langue_conversation="bci", session="sess-sans-baoule")
    assert r["langue"] == "dyu" and r["texte"] and "baoulé indisponible" in r["routage"]["raison"]


# ── m8. Messages d'erreur exacts, jamais le détail technique ────────────────────────────────────────────────────────
def test_wav_flottant_accepte_fichier_trop_lourd_bien_nomme():
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000 * 2, dtype="float32"), 16000, format="WAV", subtype="FLOAT")
    assert abs(voix.verifier_audio(buf.getvalue()) - 2.0) < 0.01
    with pytest.raises(voix.ErreurVoix, match="trop lourd"):
        voix.verifier_audio(b"RIFF" + b"\x00" * (voix.AUDIO_MAX_OCTETS + 10))


def test_panne_de_transcription_message_propre_detail_dans_le_journal():
    def moteur(octets, langue):
        raise RuntimeError("chemin interne C:\\secret")
    with pytest.raises(voix.ErreurVoix) as e:
        voix.transcrire(wav_bytes(1), moteur=moteur)
    assert "secret" not in str(e.value) and "Transcription impossible" in str(e.value)
    assert "secret" in erreurs.FICHIER.read_text(encoding="utf-8")


# ── m16. Traductions : pas de variante entre parenthèses, milliers à la française ──────────────────────────────────
def test_parentheses_ajoutees_par_le_traducteur_retirees():
    s = dioula_relais.sans_parentheses_ajoutees
    assert s("Payez votre facture à la CIE.", "I ka i ka fakitiri sara (sara) CIE la.") == "I ka i ka fakitiri sara CIE la."
    assert s("Le compteur (prépayé) marche.", "Kɔntɛri (sara) bɛ baara.") == "Kɔntɛri (sara) bɛ baara."   # déjà dans l'original


def test_milliers_du_baoule_ecrits_a_la_francaise(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda service, sens, texte: "Sika nga ɔ ka'n yɛ 47.700 ɔ, ɔ nin 2,5 kpa.")
    bci, _ = baoule_relais.vers_baoule("Il vous reste quarante-sept mille sept cents francs.")
    assert "47 700" in bci and "2,5" in bci


# ── M5, m2, m3, m4, m7. Appel Live ─────────────────────────────────────────────────────────────────────────────────
from apps.ai_assistant.tests_chatbot.test_live import FausseSession, FauxGemini, FaussePage, FauxPont, lancer, reserves, tour_parle  # noqa: E402


def test_voix_changee_pendant_la_connexion_est_appliquee():
    """La page passe à « Homme » pendant que ça sonne : avant, la session gardait la voix de femme."""
    page = FaussePage()

    class SessionLente(FausseSession):
        async def __aenter__(self):
            await asyncio.sleep(0.3)                                             # connexion lente : la page agit pendant
            return self

    class Gemini(FauxGemini):
        def __call__(self, cle, modele, config):
            if not self.appels:
                page.dire({"type": "voix", "genre": "homme"})
            return super().__call__(cle, modele, config)
    gemini = Gemini([SessionLente([]), FausseSession([tour_parle("Bonjour, voix d'homme.")])])
    a, _ = lancer(page, gemini, reserves(), fin_apres=1)
    voix_sessions = [c["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] for _, _, c in gemini.appels]
    assert voix_sessions == ["Kore", "Charon"] and a.genre == "homme"


def test_derniers_sous_titres_envoyes_avant_la_fin():
    page = FaussePage()
    a = live_agent.Appel(page, lambda e: None, reserves=reserves(), pont=FauxPont())
    a.vous, a.agent = "Merci, au revoir.", "Au revoir, bonne journée."
    asyncio.run(a.terminer())
    ordre = [(d["type"], d.get("qui"), d.get("fini")) for d in page.recu]
    assert ordre.index(("sous_titre", "agent", True)) < ordre.index(("fin", None, None))
    assert ordre.index(("sous_titre", "vous", True)) < ordre.index(("fin", None, None))


class PageQuiFerme(FaussePage):
    async def close(self, code=1000):
        self.recu.append({"type": "_fermee", "code": code})


@pytest.mark.parametrize("premier", [[1, 2], "debut", {"type": "autre"}, 42])
def test_premier_message_mal_forme_connexion_refermee_proprement(premier):
    page = PageQuiFerme()
    page.entree.put_nowait({"type": "websocket.receive", "text": json.dumps(premier)})
    asyncio.run(live_agent.Appel(page, lambda e: None, reserves=reserves(), pont=FauxPont()).servir())
    assert page.recu == [{"type": "_fermee", "code": 1008}]


def test_page_d_une_ancienne_version_message_puis_fermeture_propre():
    page = PageQuiFerme()
    page.dire({"type": "debut", "version": "ancienne"})
    asyncio.run(live_agent.Appel(page, lambda e: None, reserves=reserves(), pont=FauxPont(), version="nouvelle").servir())
    assert page.recu[0]["recharger"] and page.recu[-1] == {"type": "_fermee", "code": 1000}


def test_places_d_appel_une_par_visiteur_et_jamais_prise_sans_debut(monkeypatch):
    monkeypatch.setattr(live_agent, "_places", {"total": 0, "par_adresse": {}})
    assert live_agent._prendre_place("41.66.18.1") is None
    assert "déjà en cours" in live_agent._prendre_place("41.66.18.1")           # un seul appel par visiteur
    assert live_agent._prendre_place("41.66.18.2") is None
    assert "Trop d'appels" in live_agent._prendre_place("41.66.18.3")            # 2 en tout
    live_agent._rendre_place("41.66.18.1"); live_agent._rendre_place("41.66.18.2")
    assert live_agent._places == {"total": 0, "par_adresse": {}}
    # une connexion muette (jamais de « debut ») ne prend aucune place
    monkeypatch.setattr(live_agent, "ATTENTE_DEBUT_S", 0.2)
    page = PageQuiFerme()
    asyncio.run(live_agent.Appel(page, lambda e: None, reserves=reserves(), pont=FauxPont(), adresse="41.66.18.9").servir())
    assert live_agent._places["total"] == 0 and page.recu == [{"type": "_fermee", "code": 1008}]


def test_appel_refuse_quand_les_places_sont_prises(monkeypatch):
    monkeypatch.setattr(live_agent, "_places", {"total": live_agent.MAX_APPELS, "par_adresse": {}})
    page = PageQuiFerme()
    page.dire({"type": "debut"})
    asyncio.run(live_agent.Appel(page, lambda e: None, reserves=Reserves(["k"], ["m"]), pont=FauxPont()).servir())
    assert page.recu[0]["type"] == "erreur" and "Trop d'appels" in page.recu[0]["texte"]
    assert live_agent._places["total"] == live_agent.MAX_APPELS                 # rien pris, rien rendu en trop


# ── M11. Planificateur : consigne (mots recopiés tels quels, autres noms des écrans, choix évident) ─────────────────
def test_consigne_du_planificateur_et_de_l_agent():
    from apps.ai_assistant.chatbot import agent_actions
    s = agent_actions.SYSTEME
    assert "sans les traduire" in s and "« paramètres »" in s and "thème opposé" in s
    assert "lui demande pas de préciser" in " ".join(live_agent.consigne("auto").split())
