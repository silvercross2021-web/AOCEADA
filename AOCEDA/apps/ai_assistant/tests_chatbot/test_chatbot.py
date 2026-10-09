"""Tests automatiques de la logique du chatbot (sans Internet : DeepSeek, Whisper et les voix sont simulés).

    env\\Scripts\\python.exe -m pytest tests -q
"""
import io
import json
import time
import wave

import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import consignes, conversation, detection, fournisseurs, journal, langues, securite, voix
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur


# ── Demandes DeepSeek simulées ───────────────────────────────────────────────
def ok(*morceaux):
    return lambda systeme, historique: iter(morceaux)


def panne(message="DeepSeek 503"):
    def ouvrir(systeme, historique):
        raise fournisseurs.Echec(message)
    return ouvrir


def lent(secondes, texte="trop tard"):
    def ouvrir(systeme, historique):
        time.sleep(secondes)
        yield texte
    return ouvrir


def coupe_en_route(systeme, historique):
    yield "Début de réponse"
    raise fournisseurs.Echec("connexion perdue", avant_premier_mot=False)


def evenements(liste, historique=None):
    return list(fournisseurs.repondre_flux("système", historique or [{"role": "user", "texte": "Bonjour"}], liste=liste))


@pytest.fixture(autouse=True)
def base_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    securite.remettre_a_zero()
    yield
    securite.remettre_a_zero()


# ── Cerveau : DeepSeek + course de secours ───────────────────────────────────
def test_cerveau_deepseek_seul_avec_relance(monkeypatch):
    monkeypatch.setitem(fournisseurs.CONFIG, "DEEPSEEK_API_KEY", "cle-de-test")   # même sans clé dans le .env de ce PC
    c = fournisseurs.candidats()
    assert [x[0] for x in c] == ["DeepSeek", "DeepSeek"] and c[1][1].endswith("(relance)")


def test_premiere_demande_repond():
    ev = evenements([("DeepSeek", "ds", ok("Bon", "jour")), ("DeepSeek", "ds2", ok("non"))])
    assert ev[-1]["type"] == "fin" and ev[-1]["texte"] == "Bonjour" and ev[-1]["modele"] == "ds"
    assert [e["texte"] for e in ev if e["type"] == "morceau"] == ["Bon", "jour"]


def test_panne_immediate_relance_sans_attendre(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 5)
    t = time.time()
    ev = evenements([("DeepSeek", "ds", panne()), ("DeepSeek", "ds2", ok("Réponse"))])
    assert ev[-1]["texte"] == "Réponse" and time.time() - t < 1.0   # n'attend pas les 5 s du relais


def test_relance_en_parallele_si_la_premiere_traine(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 0.3)
    t = time.time()
    ev = evenements([("DeepSeek", "ds", lent(2)), ("DeepSeek", "ds2", ok("À temps"))])
    assert ev[-1]["texte"] == "À temps" and time.time() - t < 1.5
    assert any(e.get("abandonne") and e["modele"] == "ds" for e in ev[-1]["essais"])


def test_pas_de_relance_si_la_premiere_repond_vite(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 0.5)
    ev = evenements([("DeepSeek", "ds", ok("Vite")), ("DeepSeek", "ds2", ok("jamais lancé"))])
    assert [e["modele"] for e in ev if e["type"] == "fournisseur"] == ["ds"]   # une seule demande payée


def test_seulement_la_gagnante_est_diffusee(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 0.2)
    ev = evenements([("DeepSeek", "ds", lent(0.8, "LENT")), ("DeepSeek", "ds2", ok("RAPIDE"))])
    time.sleep(1)
    assert "LENT" not in "".join(e["texte"] for e in ev if e["type"] == "morceau")


def test_panne_en_pleine_reponse_recommence():
    ev = evenements([("DeepSeek", "ds", coupe_en_route), ("DeepSeek", "ds2", ok("Réponse complète"))])
    assert "recommencer" in [e["type"] for e in ev] and ev[-1]["texte"] == "Réponse complète"


def test_reponse_vide_ne_compte_pas():
    ev = evenements([("DeepSeek", "ds", ok("  ")), ("DeepSeek", "ds2", ok("Vraie réponse"))])
    assert ev[-1]["texte"] == "Vraie réponse"


def test_demande_lente_libere_sa_place_sans_etre_eliminee(monkeypatch):
    monkeypatch.setattr(fournisseurs, "RELAIS_S", 5)
    monkeypatch.setattr(fournisseurs, "DELAI_PREMIER_MOT_S", 0.2)
    t = time.time()
    ev = evenements([("DeepSeek", "ds", lent(1.5)), ("DeepSeek", "ds2", ok("Vite"))])
    assert ev[-1]["texte"] == "Vite" and time.time() - t < 1.0


def test_derniere_demande_lente_peut_encore_gagner(monkeypatch):
    monkeypatch.setattr(fournisseurs, "DELAI_PREMIER_MOT_S", 0.2)
    ev = evenements([("DeepSeek", "ds", panne()), ("DeepSeek", "ds2", lent(0.8, "Réponse tardive mais juste"))])
    assert ev[-1]["type"] == "fin" and ev[-1]["texte"] == "Réponse tardive mais juste"


def test_demande_muette_abandonnee(monkeypatch):
    monkeypatch.setattr(fournisseurs, "DELAI_PREMIER_MOT_S", 0.2)
    monkeypatch.setattr(fournisseurs, "DELAI_ABANDON_S", 0.6)
    ev = evenements([("DeepSeek", "ds", lent(3))])
    assert ev[-1]["type"] == "erreur" and "abandonné" in ev[-1]["essais"][0]["erreur"]


def test_tout_en_panne_message_honnete():
    ev = evenements([("DeepSeek", "ds", panne()), ("DeepSeek", "ds2", panne("DeepSeek 500"))])
    assert ev[-1]["type"] == "erreur" and "saturé" in ev[-1]["texte"] and len(ev[-1]["essais"]) == 2


def test_sans_internet_le_message_le_dit():
    coupure = "HTTPSConnectionPool(host='api.deepseek.com'): Max retries exceeded (NameResolutionError)"
    ev = evenements([("DeepSeek", "ds", panne(coupure)), ("DeepSeek", "ds2", panne(coupure))])
    assert ev[-1]["type"] == "erreur" and "connexion Internet" in ev[-1]["texte"]


# ── Consignes et langues ─────────────────────────────────────────────────────
def test_consigne_contexte_ivoirien_et_honnetete():
    s = consignes.systeme("auto")
    assert "Côte d'Ivoire" in s and "PAS de chauffage" in s and "N'invente JAMAIS" in s
    assert "Vouvoie" in s and "AUCUN pourcentage" in s and "bimestrielle" in s


def test_consigne_langue_forcee():
    assert "Réponds TOUJOURS en anglais" in consignes.systeme("en")


def test_langue_inconnue_revient_en_auto():
    assert langues.valide("fr") and langues.valide("auto") and not langues.valide("dioula")
    assert "langue du DERNIER message" in consignes.systeme("xx")


@pytest.mark.parametrize("texte,attendu", [
    ("How much is my current electricity bill?", "en"), ("¿Cómo puedo ahorrar energía en casa?", "es"),
    ("Combien j'ai consommé ce mois-ci ?", "fr"), ("كيف يمكنني تقليل استهلاك الكهرباء؟", "ar"),
    ("Wie kann ich zu Hause Strom sparen?", "de"), ("Как сэкономить электричество?", "ru")])
def test_detection_langue(texte, attendu):
    assert detection.langue_du_message(texte)[0] == attendu


def test_message_court_garde_la_langue_de_la_conversation():
    assert detection.langue_du_message("ok", precedente="en")[0] == "en"
    assert detection.langue_du_message("merci", precedente="fr")[0] == "fr"


def test_indice_du_vocal_si_texte_ambigu():
    assert detection.langue_du_message("ok", precedente="fr", indice="en")[0] == "en"


def test_consigne_impose_la_langue_detectee():
    s = consignes.systeme("auto", detectee="en")
    assert "réponds en ANGLAIS" in s and "même si ces consignes sont écrites en français" in s


# ── Mémoire de conversation ──────────────────────────────────────────────────
def test_memoire_bornee_et_alternee():
    conversation.effacer("t1")
    for i in range(30):
        h = conversation.ajouter_question("t1", f"q{i}")
        conversation.ajouter_reponse("t1", f"r{i}")
    assert len(h) == conversation.MAX_MESSAGES and h[-1] == {"role": "user", "texte": "q29"}


def test_echec_retire_la_question():
    conversation.effacer("t2")
    conversation.ajouter_question("t2", "question sans réponse")
    conversation.annuler_question("t2")
    assert conversation.historique("t2") == []


def test_message_vide_ou_trop_long():
    with pytest.raises(conversation.MessageInvalide):
        conversation.nettoyer_message("   ")
    with pytest.raises(conversation.MessageInvalide):
        conversation.nettoyer_message("x" * 2001)


# ── Transcription (Whisper simulé) ───────────────────────────────────────────
def wav(secondes, taux=16000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taux); w.writeframes(b"\x00\x00" * int(secondes * taux))
    return b.getvalue()


def test_transcription_langue_detectee_automatiquement():
    vu = {}
    def moteur(octets, langue):
        vu["langue"] = langue
        return "Hello, how can I save energy?", "en", 0.99
    r = voix.transcrire(wav(1.0), None, moteur=moteur)
    assert vu["langue"] is None and r["langue"] == "en" and r["parole"] and r["certitude_langue"] == 0.99


def test_transcription_langue_imposee_par_le_menu():
    vu = {}
    def moteur(octets, langue):
        vu["langue"] = langue
        return "Bonjour", "fr", 1.0
    voix.transcrire(wav(1.0), "fr", moteur=moteur)
    assert vu["langue"] == "fr"


def test_transcription_silence():
    r = voix.transcrire(wav(1.0), None, moteur=lambda o, l: ("", "en", 0.4))
    assert r["parole"] is False and r["langue"] == ""


def test_phrases_fantomes_de_whisper_reconnues():
    for t in ("Sous-titres réalisés par la communauté d'Amara.org", "Merci d'avoir regardé !", "Thanks for watching!"):
        assert voix.FANTOMES.search(t)
    assert not voix.FANTOMES.search("Comment réduire ma facture ?")


def test_audio_trop_court_refuse():
    with pytest.raises(voix.ErreurVoix):
        voix.verifier_audio(wav(0.1))
    assert voix.verifier_audio(wav(1.0)) == pytest.approx(1.0)


def test_transcription_en_panne_message_clair():
    def moteur(o, l):
        raise RuntimeError("modèle absent")
    with pytest.raises(voix.ErreurVoix):
        voix.transcrire(wav(1.0), None, moteur=moteur)


# ── Voix « Écouter » ─────────────────────────────────────────────────────────
CATALOGUE = [{"nom": "fr-FR-DeniseNeural", "region": "fr-FR", "genre": "Female"},
             {"nom": "fr-FR-VivienneMultilingualNeural", "region": "fr-FR", "genre": "Female"},
             {"nom": "fr-FR-RemyMultilingualNeural", "region": "fr-FR", "genre": "Male"},
             {"nom": "en-US-AvaMultilingualNeural", "region": "en-US", "genre": "Female"},
             {"nom": "es-MX-JorgeNeural", "region": "es-MX", "genre": "Male"}]


def test_choix_de_la_voix_selon_langue_et_genre(monkeypatch):
    monkeypatch.setitem(voix._catalogue, "voix", CATALOGUE)
    assert voix.choisir_voix("fr", "femme") == "fr-FR-VivienneMultilingualNeural"   # multilingue = plus naturelle
    assert voix.choisir_voix("fr", "homme") == "fr-FR-RemyMultilingualNeural"
    assert voix.choisir_voix("en", "homme") == "en-US-AvaMultilingualNeural"        # pas d'homme : la meilleure dispo
    assert voix.choisir_voix("es", "homme") == "es-MX-JorgeNeural"                  # autre région de la même langue


def test_voix_secours_kokoro_si_microsoft_echoue(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    def microsoft():
        raise RuntimeError("bloqué")
    audio, infos = voix.synthetiser("Bonjour.", "fr", moteurs=[("Microsoft", "v1", "audio/mpeg", microsoft),
                                                               ("Kokoro", "k", "audio/wav", lambda: b"RIFF" + b"0" * 2000)])
    assert infos["moteur"] == "Kokoro" and audio.startswith(b"RIFF") and "bloqué" in infos["erreurs"][0]


def test_voix_mise_en_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    appels = []
    def m():
        appels.append(1); return b"ID3" + b"0" * 2000
    for _ in range(2):
        audio, infos = voix.synthetiser("Bonjour.", "fr", moteurs=[("Microsoft", "v1", "audio/mpeg", m)])
    assert len(appels) == 1 and infos["cache"] is True


def test_toutes_les_voix_en_panne(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    def p():
        raise RuntimeError("x")
    with pytest.raises(voix.ErreurVoix):
        voix.synthetiser("Bonjour.", "fr", moteurs=[("Microsoft", "v1", "audio/mpeg", p)])


def test_texte_pour_voix_retire_le_markdown():
    t = voix.texte_pour_voix("**Conseils** :\n- Éteignez la télé\n- Réglez la clim à 26 degrés 😀")
    assert "*" not in t and "-" not in t and "😀" not in t and "Éteignez la télé." in t


def test_decoupage_premier_morceau_premiere_phrase():
    texte = "Première phrase courte. " + " ".join(f"Phrase numéro {i} un peu plus longue que les autres." for i in range(12))
    m = voix.decouper(texte)
    assert m[0] == "Première phrase courte." and all(len(x) <= 320 for x in m)
    assert " ".join(m) == voix.texte_pour_voix(texte)   # rien de perdu


def test_premiere_phrase_reconnue_pendant_l_ecriture():
    assert voix.premier_morceau_si_complet("Réglez la clim à 26") is None              # phrase pas finie
    assert voix.premier_morceau_si_complet("Réglez la clim à 26 degrés :\n- Fermez") is None
    partiel = "Réglez la clim à 26 degrés.\n- Fermez les port"
    complet = "Réglez la clim à 26 degrés.\n- Fermez les portes.\n- Éteignez la télé."
    assert voix.premier_morceau_si_complet(partiel) == voix.decouper(complet)[0]   # même morceau qu'à la fin -> même voix en cache


# ── Transcription en 2 temps (modèles simulés) ───────────────────────────────
class FauxDetecteur:
    def __init__(self, langue, certitude):
        self.r = (langue, certitude, [])
    def detect_language(self, audio):
        return self.r


class FauxModele:
    def __init__(self):
        self.langue_recue = "pas appelé"
    def transcribe(self, audio, language=None, **k):
        self.langue_recue = language
        seg = type("S", (), {"text": " Bonjour.", "no_speech_prob": 0.1})()
        return [seg], type("I", (), {"language": "fr", "language_probability": 0.97})()


def _whisper_simule(monkeypatch, detecteur):
    import faster_whisper.audio
    modele = FauxModele()
    monkeypatch.setattr(faster_whisper.audio, "decode_audio", lambda f: "audio")
    monkeypatch.setitem(voix._whisper, "detecteur", detecteur)
    monkeypatch.setitem(voix._whisper, "modele", modele)
    return modele


def test_tiny_trouve_la_langue_small_transcrit_en_la_connaissant(monkeypatch):
    modele = _whisper_simule(monkeypatch, FauxDetecteur("fr", 0.98))
    texte, langue, certitude, prise = voix._whisper_transcrire(b"x", None)
    assert modele.langue_recue == "fr" and langue == "fr" and certitude == 0.98 and texte == "Bonjour."


def test_tiny_hesite_small_cherche_seul(monkeypatch):
    modele = _whisper_simule(monkeypatch, FauxDetecteur("pt", 0.4))
    texte, langue, certitude, prise = voix._whisper_transcrire(b"x", None)
    assert modele.langue_recue is None and langue == "fr" and certitude == 0.97


def test_langue_du_menu_saute_la_detection(monkeypatch):
    det = FauxDetecteur("en", 0.99)
    det.detect_language = lambda a: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé"))
    modele = _whisper_simule(monkeypatch, det)
    voix._whisper_transcrire(b"x", "es")
    assert modele.langue_recue == "es"


# ── Voix préparées à l'avance (genre choisi d'abord, jamais en double) ─────────
def test_preparer_genre_choisi_d_abord_puis_l_autre(monkeypatch):
    appels = []
    monkeypatch.setattr(voix, "obtenir", lambda t, l=None, g="femme": appels.append((t, g)) or (b"a", {}))
    monkeypatch.setitem(voix._atelier, "pool", None)
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setitem(voix._atelier, "pool", ThreadPoolExecutor(max_workers=1))   # 1 ouvrier : l'ordre est visible
    for t in voix.preparer(["Bonjour.", "Fermez les portes."], "fr", "homme"):
        t.result(timeout=5)
    assert appels == [("Bonjour.", "homme"), ("Fermez les portes.", "homme"), ("Bonjour.", "femme"), ("Fermez les portes.", "femme")]


def test_meme_voix_jamais_fabriquee_deux_fois(monkeypatch):
    import threading
    appels, depart = [], threading.Event()
    def lent(t, l=None, g="femme", moteurs=None):
        appels.append(g); depart.wait(1); return b"a", {"moteur": "m"}
    monkeypatch.setattr(voix, "synthetiser", lent)
    taches = [voix._pool().submit(voix.obtenir, "Bonjour.", "fr", "femme") for _ in range(3)]
    time.sleep(0.3); depart.set()
    assert all(t.result(timeout=5)[0] == b"a" for t in taches) and appels == ["femme"]


# ── Langue : demande explicite et contrôle de la réponse ──────────────────────
from apps.ai_assistant.chatbot import garde_langue, securite, service_chat


@pytest.mark.parametrize("texte,attendu", [
    ("Réponds-moi en anglais s'il te plaît", "en"), ("Can you answer in Spanish from now on?", "es"),
    ("Parle en français stp", "fr"), ("Responde en inglés por favor", "en"), ("Répondez en arabe", "ar"),
    ("Comment réduire ma facture ?", None), ("Je suis en France", None),
    # 05/10/2026 : toutes les façons de le demander
    ("Donne-moi les réponses en anglais", "en"), ("Je veux toutes les réponses en anglais maintenant", "en"),
    ("En anglais s'il te plaît", "en"), ("Anglais !", "en"), ("passe à l'anglais", "en"), ("switch to English", "en"),
    ("can you please talk to me in English from now on", "en"), ("Reviens au français", "fr"),
    # pas des demandes : il le dit, ou c'est une question de traduction / sur ce qu'il sait faire
    ("Je parle anglais au travail mais pas à la maison", None), ("Comment dit-on merci en anglais ?", None),
    ("Est-ce que tu comprends le baoulé ?", None), ("Je paie en francs CFA chaque mois", None)])
def test_demande_explicite_de_langue(texte, attendu):
    assert garde_langue.demande_explicite(texte) == attendu


@pytest.mark.parametrize("texte,nom", [("Parle agni s'il te plaît", "agni"), ("Dis-moi bonjour en agni", "agni"),
                                       ("Tu comprends l'agni ?", "agni"), ("Réponds en bété", "bété"),
                                       ("Comment réduire ma facture ?", None), ("Parle-moi en baoulé", None)])
def test_langue_que_le_chatbot_ne_parle_pas_reperee(texte, nom):
    assert garde_langue.langue_demandee(texte)["non_prise"] == nom


def test_demande_dans_le_message_l_emporte_sur_le_menu_jusqu_au_prochain_choix():
    """Retour client du 05/10/2026 : « réponds en anglais » -> toutes les réponses en anglais, même si je parle français et
    même si le menu dit autre chose, jusqu'à ce que JE change (nouvelle demande ou nouveau menu)."""
    C = service_chat.choisir_langue
    assert C("sess-verrou", "Réponds en anglais maintenant", "fr", None)[:2] == ("en", "demandée")
    assert C("sess-verrou", "Combien consomme un réfrigérateur par jour ?", "fr", None)[:2] == ("en", "demandée plus tôt")
    assert C("sess-verrou", "Et la télévision, elle consomme beaucoup ?", "auto", None)[:2] == ("fr", "détectée")   # menu changé
    assert C("sess-verrou", "Parle en espagnol", "auto", None)[:2] == ("es", "demandée")
    assert C("sess-verrou", "Comment dit-on merci en anglais ?", "auto", None)[0] == "es"    # traduction : pas un changement


def test_langue_imposee_rappelee_au_bout_du_dernier_message_sans_le_garder(monkeypatch):
    """Vrai DeepSeek, 05/10/2026 : menu passé à l'espagnol après des échanges en français et en anglais -> il répondait en
    français même refait. Le rappel est mis au bout du dernier message envoyé au modèle, pas dans la conversation."""
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    vu = []
    def ouvrir(systeme, historique):
        vu.append(historique)
        yield "Un refrigerador consume de forma continua, pero mucho menos que un aire acondicionado."
    evenements_service("sess-rappel", "Et un réfrigérateur ?", [("DeepSeek", "s", ouvrir)], langue_menu="es")
    assert vu[0][-1]["texte"] == "Et un réfrigérateur ?\n\n(Réponds en espagnol, Español.)"
    assert conversation.historique("sess-rappel")[0]["texte"] == "Et un réfrigérateur ?"     # rien de gardé
    evenements_service("sess-rappel2", "Et un frigo ?", [("DeepSeek", "s", ouvrir)])            # Automatique : pas de rappel
    assert vu[1][-1]["texte"] == "Et un frigo ?"


def test_menu_baoule_et_on_parle_baoule_l_ancienne_demande_tombe():
    """Vu le 05/10 (soir) : verrou « français » + menu Baoulé + vocal en baoulé -> réponses en français (« je réponds
    uniquement en français »). Le menu et la langue parlée concordent : c'est le baoulé."""
    C = service_chat.choisir_langue
    conversation.noter_menu("sess-bci-verrou", "bci")
    conversation.noter_langue("sess-bci-verrou", "fr", imposee=True)
    assert C("sess-bci-verrou", "wɔka niɛ yafo", "bci", "bci")[:2] == ("bci", "menu")      # vocal entendu en baoulé
    assert conversation.langue_imposee("sess-bci-verrou") is None
    conversation.noter_langue("sess-bci-verrou", "fr", imposee=True)
    assert C("sess-bci-verrou", "Combien consomme un frigo ?", "bci", None)[0] == "fr"     # en français : la demande tient


def test_langue_non_prise_dite_honnetement_dans_la_consigne(monkeypatch):
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    vu = {}
    def ouvrir(systeme, historique):
        vu["systeme"] = systeme
        yield "Je ne sais pas écrire l'agni, mais je comprends le dioula et le baoulé."
    ev = evenements_service("sess-agni", "Réponds-moi en agni s'il te plaît", [("DeepSeek", "s", ouvrir)])
    assert ev[0]["code"] == "fr" and ev[0]["non_prise"] == "agni"
    assert "n'écris AUCUN mot en agni" in vu["systeme"] and "dioula et en baoulé" in vu["systeme"]


def test_reponse_dans_la_mauvaise_langue_reperee():
    fr = "Réglez votre climatiseur autour de vingt-six degrés et fermez bien les portes et les fenêtres."
    assert garde_langue.mauvaise_langue(fr, "en") == "fr"
    assert garde_langue.mauvaise_langue(fr, "fr") is None
    assert garde_langue.mauvaise_langue("Tokyo.", "en") is None          # trop court pour juger : on ne touche pas


def evenements_service(session, texte, liste, langue_menu="auto"):
    return [e for e in service_chat.repondre(session, texte, langue_menu, None, "femme", liste=liste)]


def test_langue_demandee_retenue_pour_la_suite(monkeypatch):
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    ev = evenements_service("sess-langue1", "Réponds-moi en anglais s'il te plaît", [("DeepSeek", "s", ok("Sure, I will answer in English."))])
    assert ev[0]["code"] == "en" and ev[0]["source"] == "demandée"
    ev = evenements_service("sess-langue1", "Et le frigo, il consomme beaucoup ?", [("DeepSeek", "s", ok("A fridge runs all day long."))])
    assert ev[0]["code"] == "en" and ev[0]["source"] == "demandée plus tôt"


def test_reponse_refaite_si_mauvaise_langue(monkeypatch):
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    reponses = iter(["Réglez votre climatiseur autour de vingt-six degrés, fermez les portes et les fenêtres et éteignez la télévision.",
                     "Set your air conditioner to about twenty-six degrees and close the doors and windows."])
    def ouvrir(systeme, historique):
        yield next(reponses)
    ev = evenements_service("sess-langue2", "How can I save energy with my air conditioner at home?", [("DeepSeek", "s", ouvrir)])
    assert any(e["type"] == "recommencer" and "refaite" in e["raison"] for e in ev)
    assert ev[-2]["type"] == "fin" and ev[-2]["texte"].startswith("Set your") and ev[-1]["refaites"] == 1
    assert conversation.historique("sess-langue2")[-1]["texte"].startswith("Set your")   # seule la bonne réponse est gardée


def test_arret_de_la_reponse_nettoie_l_historique(monkeypatch):
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    arrets = []
    def long(systeme, historique):
        for i in range(100):
            yield f"mot{i} "
            time.sleep(0.01)
    gen = service_chat.repondre("sess-stop1", "Explique-moi tout", "fr", None, "femme", liste=[("DeepSeek", "s", long)])
    for ev in gen:
        if ev["type"] == "morceau":
            break
    gen.close()                                              # l'utilisateur clique sur « Stop »
    assert conversation.historique("sess-stop1") == []       # pas de question orpheline dans l'historique


# ── Plusieurs utilisateurs : file d'attente de Whisper bornée ────────────────
def test_file_d_attente_bornee(monkeypatch):
    import threading
    monkeypatch.setattr(voix, "MAX_EN_ATTENTE", 0)
    monkeypatch.setitem(voix._whisper, "en_attente", 0)
    with pytest.raises(voix.ServeurOccupe):
        voix.transcrire(wav(1.0), None, moteur=lambda o, l: ("x", "fr", 1.0))


def test_deux_transcriptions_en_meme_temps(monkeypatch):
    import threading
    monkeypatch.setitem(voix._whisper, "places", threading.BoundedSemaphore(2))
    en_cours, maxi = [0], [0]
    verrou = threading.Lock()
    def moteur(o, l):
        with verrou:
            en_cours[0] += 1; maxi[0] = max(maxi[0], en_cours[0])
        time.sleep(0.3)
        with verrou:
            en_cours[0] -= 1
        return "Bonjour", "fr", 1.0
    fils = [threading.Thread(target=voix.transcrire, args=(wav(1.0), None, moteur)) for _ in range(3)]
    [f.start() for f in fils]; [f.join() for f in fils]
    assert maxi[0] == 2                                       # jamais plus de 2 calculs Whisper à la fois


def test_langue_non_prise_en_charge_signalee(monkeypatch):
    modele = _whisper_simule(monkeypatch, FauxDetecteur("yo", 0.9))
    texte, langue, certitude, prise = voix._whisper_transcrire(b"x", None)
    assert texte == "" and langue == "yo" and prise is False and modele.langue_recue == "pas appelé"


def test_audio_non_wav_ou_trop_long_refuse():
    with pytest.raises(voix.ErreurVoix):
        voix.verifier_audio(b"ID3" + b"0" * 5000)              # mp3 ou autre : refusé
    with pytest.raises(voix.ErreurVoix):
        voix.verifier_audio(wav(62))                           # > 60 s


# ── Sécurité ─────────────────────────────────────────────────────────────────
def test_limite_de_debit(monkeypatch):
    monkeypatch.setitem(securite.LIMITES, "message", (2, 60))
    securite.verifier("message", "sess-debit1", "1.2.3.4")
    securite.verifier("message", "sess-debit1", "1.2.3.4")
    with pytest.raises(securite.TropDeDemandes):
        securite.verifier("message", "sess-debit1", "1.2.3.4")
    with pytest.raises(securite.TropDeDemandes):
        securite.verifier("message", "autre-session", "1.2.3.4")   # même adresse IP : bloquée aussi


# ── API du serveur ───────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(fournisseurs, "candidats", lambda: [("DeepSeek", "simulé", ok("Réponse ", "simulée"))])
    monkeypatch.setattr(voix, "preparer", lambda morceaux, langue=None, genre="femme": PREPARES.append((list(morceaux), langue, genre)) or [])
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal_tests.jsonl")
    return TestClient(serveur.app)


PREPARES = []


def lire_flux(r):
    return [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]


def test_api_prepare_la_voix_pendant_et_apres_l_ecriture(client, monkeypatch):
    monkeypatch.setattr(fournisseurs, "candidats", lambda: [("DeepSeek", "simulé", ok("Réglez la clim à 26 degrés.", "\n- Fermez", " les portes.", "\n- Éteignez la télé."))])
    PREPARES.clear()
    lire_flux(client.post("/api/message", json={"session": "session-voix1", "texte": "Comment économiser ?", "langue": "fr", "genre": "homme"}))
    assert PREPARES[0] == (["Réglez la clim à 26 degrés."], "fr", "homme")               # pendant l'écriture, genre choisi
    assert PREPARES[1] == (["Fermez les portes. Éteignez la télé."], "fr", "homme")      # le reste, à la fin


def test_api_message_flux_et_memoire(client):
    ev = lire_flux(client.post("/api/message", json={"session": "session-api1", "texte": "Bonjour", "langue": "fr"}))
    assert ev[-1]["texte"] == "Réponse simulée" and not any(e["type"] == "bilan" for e in ev)
    assert conversation.historique("session-api1")[-1] == {"role": "model", "texte": "Réponse simulée"}


def test_api_annonce_la_langue_de_reponse(client):
    ev = lire_flux(client.post("/api/message", json={"session": "session-api4", "texte": "How can I save energy at home?"}))
    assert ev[0]["type"] == "langue" and ev[0]["code"] == "en" and conversation.langue("session-api4") == "en"


def test_api_refuse_message_vide_et_session_invalide(client):
    assert client.post("/api/message", json={"session": "session-api2", "texte": "  "}).status_code == 400
    assert client.post("/api/message", json={"session": "../x", "texte": "a"}).status_code == 422
    assert client.post("/api/message", json={"session": "court", "texte": "a"}).status_code == 422


def test_api_trop_de_messages(client, monkeypatch):
    monkeypatch.setitem(securite.LIMITES, "message", (2, 60))
    for _ in range(2):
        assert client.post("/api/message", json={"session": "session-debit", "texte": "Bonjour"}).status_code == 200
    r = client.post("/api/message", json={"session": "session-debit", "texte": "Bonjour"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_api_nouvelle_conversation(client):
    client.post("/api/message", json={"session": "session-api3", "texte": "Bonjour"})
    client.post("/api/nouvelle", json={"session": "session-api3"})
    assert conversation.historique("session-api3") == []


def test_api_transcription_audio_trop_court(client):
    r = client.post("/api/transcrire", files={"audio": ("v.wav", wav(0.1), "audio/wav")}, data={"langue": "auto", "session": "session-tr1"})
    assert r.status_code == 400 and "court" in r.json()["erreur"]


def test_api_transcription_exige_une_session(client):
    r = client.post("/api/transcrire", files={"audio": ("v.wav", wav(1.0), "audio/wav")}, data={"langue": "auto"})
    assert r.status_code == 422


def test_api_transcription_serveur_occupe(client, monkeypatch):
    def occupe(o, l, *autres):           # (octets, langue, moteur, langue de la conversation, session)
        raise voix.ServeurOccupe("occupé")
    monkeypatch.setattr(voix, "transcrire", occupe)
    r = client.post("/api/transcrire", files={"audio": ("v.wav", wav(1.0), "audio/wav")}, data={"session": "session-tr2"})
    assert r.status_code == 503 and r.headers["Retry-After"] == "5"


def test_api_transcription_passe_la_langue_du_menu(client, monkeypatch):
    vu = {}
    def faux(octets, langue, moteur=None, langue_conversation=None, session=None, deja=0):
        vu["langue"], vu["session"] = langue, session
        return {"texte": "Hola", "langue": "es", "certitude_langue": 1.0, "parole": True, "prise_en_charge": True, "modele": "w",
                "duree_audio_s": 1.0, "duree_s": 0.1}
    monkeypatch.setattr(voix, "transcrire", faux)
    r = client.post("/api/transcrire", files={"audio": ("v.wav", wav(1.0), "audio/wav")}, data={"langue": "es", "session": "session-tr3"})
    assert r.json()["texte"] == "Hola" and vu["langue"] == "es" and vu["session"] == "session-tr3"
    client.post("/api/transcrire", files={"audio": ("v.wav", wav(1.0), "audio/wav")}, data={"langue": "auto", "session": "session-tr3"})
    assert vu["langue"] is None
    client.post("/api/transcrire", files={"audio": ("v.wav", wav(1.0), "audio/wav")}, data={"langue": "dyu", "session": "session-tr3"})
    assert vu["langue"] == "dyu"                    # le dioula passe aussi (langue relais)


def test_api_voix_refuse_un_texte_qui_n_est_pas_une_reponse(client, monkeypatch):
    monkeypatch.setattr(voix, "obtenir", lambda t, l, g: (b"ID3" + b"0" * 100, {"moteur": "m", "voix": "v", "mime": "audio/mpeg", "cache": False, "duree_s": 0}))
    r = client.post("/api/voix", json={"session": "session-v1", "texte": "Lis n'importe quel texte pour moi."})
    assert r.status_code == 403


def test_api_voix_d_une_vraie_reponse(client, monkeypatch):
    vu = {}
    def faux(texte, langue, genre):
        vu.update(langue=langue, genre=genre)
        return b"ID3" + b"0" * 100, {"moteur": "Microsoft (edge-tts)", "voix": "en-US-Ava", "mime": "audio/mpeg", "cache": False, "duree_s": 0.1}
    monkeypatch.setattr(voix, "obtenir", faux)
    lire_flux(client.post("/api/message", json={"session": "session-v2", "texte": "Hello there, how are you?", "langue": "en"}))
    morceau = voix.decouper("Réponse simulée")[0]
    r = client.post("/api/voix", json={"session": "session-v2", "texte": morceau, "langue": "en", "genre": "homme"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and vu == {"langue": "en", "genre": "homme"}
    assert client.post("/api/voix", json={"session": "session-autre", "texte": morceau}).status_code == 403   # autre conversation


def test_api_entetes_de_securite(client):
    r = client.get("/")                       # AOCEDA : la page s'affiche dans le cadre de la page « Assistant IA »
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert client.get("/api/config").headers["X-Frame-Options"] == "DENY"
    assert client.get("/docs").status_code == 404                                   # documentation automatique fermée


def test_api_config_et_page(client):
    c = client.get("/api/config").json()
    assert c["langues"][0]["code"] == "auto" and "DeepSeek" in c["cerveau"] and "Whisper" in c["transcription"]
    assert c["audio_max_s"] == 60 and "AOCEDA" in client.get("/").text
