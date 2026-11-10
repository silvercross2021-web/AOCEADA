"""Tests exhaustifs et Benchmarking de latence de la logique WOLOF.
Vérification de non-régression, discrimination lexicale anti-faux-positifs,
normalisation phonétique AOCEDA et validation de bout en bout (E2E).
"""
from datetime import datetime
import time
import numpy as np
import pytest

from apps.ai_assistant.chatbot import (
    consignes,
    conversation,
    langues,
    salutations,
    securite,
    service_chat,
    service_wolof,
    voix,
    voix_wolof,
    wolof_ecoute,
    wolof_relais,
    wolof_texte
)


@pytest.fixture(autouse=True)
def base_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    monkeypatch.setattr(salutations, "maintenant", lambda: datetime(2026, 10, 9, 20, 0))
    securite.remettre_a_zero()
    yield
    securite.remettre_a_zero()


def deepseek_mock(*morceaux):
    return [("DeepSeek", "ds", lambda systeme, historique: iter(morceaux))]


# ── 1. Expert Linguistique : Détection & Discrimination Lexicale ───────────────

@pytest.mark.parametrize("texte", [
    "nanga def",
    "naka nga def",
    "dama bëgg xam sama kuraŋ",
    "kuraŋ bi fay na",
    "kuran bi dafay fay",
    "jerejef ci dimbal bi",
    "jërejëf",
    "waaw",
    "déedéet",
    "koppar yi jeex na",
])
def test_textes_wolof_nominaux_reconnus(texte):
    est_wo, score = wolof_texte.est_wolof(texte)
    assert est_wo is True
    assert score >= 0.60
    # Vérification routage service_chat
    lg, source, conf = service_chat.choisir_langue("sess-wo-" + str(abs(hash(texte)))[:8], texte, "auto", None)
    assert lg == "wo"


@pytest.mark.parametrize("texte", [
    "un",
    "de la",
    "du",
    "Éteins le ventilateur du salon.",
    "Allume la télé du salon",
    "Ma clim fait du bruit",
    "Combien me reste-t-il de crédit ?",
    "Merci beaucoup",
    "Bonjour, comment allez-vous ?",
    "si",
    "ok d'accord",
])
def test_faux_positifs_mots_courts_et_francais_strictement_ecartes(texte):
    """Vérifie que les petits mots ambigus et phrases françaises avec 'du', 'un', 'la'
    ne déclenchent JAMAIS le Wolof par erreur.
    """
    est_wo, score = wolof_texte.est_wolof(texte)
    assert est_wo is False, f"Faux positif Wolof détecté sur : '{texte}'"
    assert score == 0.0, f"Le score Wolof doit être strictement 0.0, obtenu: {score}"
    # Le routage dans service_chat ne doit jamais donner "wo"
    lg, _, _ = service_chat.choisir_langue("sess-fr-" + str(abs(hash(texte)))[:8], texte, "auto", None)
    assert lg != "wo"


@pytest.mark.parametrize("texte, attendu", [
    ("Kalata sira kura bora Burukina jamana kan.", "dyu"),
    ("N ka kuran juru banna", "dyu"),
    ("N ka kuran juru banna, n bɛ se ka mun kɛ ?", "dyu"),
    ("I ni ce kosɔbɛ", "dyu"),
    ("Aka kofi", "bci"),
    ("Mo be baoule nu", "bci"),
])
def test_anti_collision_langues_soeurs_dioula_et_baoule(texte, attendu):
    """Vérifie qu'un message Dioula ou Baoulé contenant 'kuran' ou 'kan' n'est jamais détourné vers le Wolof."""
    lg, _, _ = service_chat.choisir_langue("sess-col-" + str(abs(hash(texte)))[:8], texte, "auto", None)
    assert lg != "wo", f"'{texte}' ne doit jamais être pris pour du wolof"
    assert lg in ("dyu", "bci")


@pytest.mark.parametrize("texte", [
    "Dama bëgg payer sama facture",
    "Kuraŋ bi dafa coupé ci salon bi",
    "Nanga recharger sama compteur",
])
def test_code_switching_franco_wolof_valide(texte):
    """En milieu urbain (Dakar), les emprunts techniques coexistent avec la grammaire Wolof."""
    est_wo, score = wolof_texte.est_wolof(texte)
    assert est_wo is True
    assert score >= 0.60


# ── 2. Règle Phonétique TTS : AOCEDA -> A-o-sé-da ─────────────────────────────

def test_regle_phonetique_aoceda():
    """Valide le respect de la règle d'or du lab pour une prononciation naturelle [s] sans palatalisation."""
    assert wolof_texte.normaliser_phonetique_tts("AOCEDA") == "A-o-sé-da"
    assert wolof_texte.normaliser_phonetique_tts("Bienvenue chez AOCEDA.") == "Bienvenue chez A-o-sé-da."
    assert wolof_texte.normaliser_phonetique_tts("aoceda dina fay") == "A-o-sé-da dina fay"
    assert wolof_texte.normaliser_phonetique_tts("Aoceda kuraŋ") == "A-o-sé-da kuraŋ"


# ── 3. Chiffres et Glossaire Métier ──────────────────────────────────────────

def test_lecture_chiffres_et_glossaire_energie():
    chiffres = wolof_texte.lire_nombres("amna fukk ak juróom kilowatts")
    valeurs = {c["texte"]: c["valeur"] for c in chiffres}
    assert valeurs.get("fukk") == 10
    assert valeurs.get("juróom") == 5

    glossaire = wolof_texte.lexique_utile("kuraŋ bi fay na, fay sama facture")
    assert "kuraŋ" in glossaire
    assert "facture" in glossaire


# ── 4. Flux Complet E2E & Auto-Correction ─────────────────────────────────────

def test_flux_e2e_service_wolof_repondre(monkeypatch):
    """Simule le flux complet de bout en bout :
    Dossier -> DeepSeek intention + réponse -> Traduction streaming vers Wolof avec règle phonétique.
    """
    # Mock de la traduction relais vers Wolof
    monkeypatch.setattr(
        wolof_relais,
        "vers_wolof",
        lambda fr: "Jërejëf, AOCEDA dina saytu kuraŋ bi." if "courant" in fr.lower() else "Waaw, ba beneen."
    )
    monkeypatch.setattr(
        wolof_relais,
        "vers_francais",
        lambda wo: {"google": "Mon électricité est coupée", "duree_s": 0.05, "erreurs": []}
    )

    deepseek_flux = deepseek_mock(
        "INTENTION : coupure de courant constatée\n",
        "CERTITUDE : haute\n\n",
        "Votre courant est surveillé par nos équipes. ",
        "Merci pour votre confiance."
    )

    session = "sess-e2e-wolof-01"
    evenements = list(service_wolof.repondre(
        session=session,
        texte="kuraŋ bi fay na",
        origine="ecrit",
        genre="femme",
        liste=deepseek_flux,
        voix_auto=False
    ))

    types = [e["type"] for e in evenements]
    assert "intention" in types
    assert "morceau" in types
    assert "francais" in types
    assert "fin" in types

    ev_fin = [e for e in evenements if e["type"] == "fin"][0]
    # Vérification que la phonétique A-o-sé-da a été injectée dans le texte final
    assert "A-o-sé-da" in ev_fin["texte"]
    assert ev_fin["intention"] == "coupure de courant constatée"
    assert ev_fin["certitude"] == "haute"


# ── 5. Benchmarking de Latence par Étape ──────────────────────────────────────

def test_benchmarking_latence_etapes(monkeypatch):
    """Mesure chronométrée précise de chaque brique Wolof en millisecondes."""
    # 1. Benchmark détection lexicale
    t0 = time.perf_counter()
    for _ in range(100):
        wolof_texte.score_wolof("dama bëgg xam sama kuraŋ ak sama koppar ci compte bi")
    t_det_ms = ((time.perf_counter() - t0) / 100.0) * 1000.0

    # 2. Benchmark normalisation phonétique
    t0 = time.perf_counter()
    for _ in range(100):
        wolof_texte.normaliser_phonetique_tts("AOCEDA moy liggéey ci kuraŋ bi, wax ak AOCEDA.")
    t_phon_ms = ((time.perf_counter() - t0) / 100.0) * 1000.0

    # 3. Benchmark préparation dossier
    t0 = time.perf_counter()
    monkeypatch.setattr(wolof_relais, "vers_francais", lambda t: {"google": "électricité", "duree_s": 0.01})
    for _ in range(50):
        service_wolof.preparer_dossier("sess-bench", "kuraŋ bi fay na", "ecrit", traduire_aller=True)
    t_dossier_ms = ((time.perf_counter() - t0) / 50.0) * 1000.0

    print(f"\n================ BENCHMARK LATENCE WOLOF ================")
    print(f"  - Détection lexicale Wolof    : {t_det_ms:.3f} ms / requête")
    print(f"  - Normalisation phonétique    : {t_phon_ms:.3f} ms / requête")
    print(f"  - Préparation dossier complet : {t_dossier_ms:.3f} ms / requête")
    print(f"=========================================================")

    # Critères de performance stricts : chaque étape doit être < 5 ms sur CPU
    assert t_det_ms < 5.0, f"Détection trop lente : {t_det_ms} ms"
    assert t_phon_ms < 1.0, f"Phonétique trop lente : {t_phon_ms} ms"
    assert t_dossier_ms < 20.0, f"Préparation dossier trop lente : {t_dossier_ms} ms"


# ── 6. Validation Voix Wolof sur Cerebrium GPU ────────────────────────────────

def test_voix_wolof_cerebrium(monkeypatch, tmp_path):
    """Vérifie l'intégration du TTS Wolof sur Cerebrium GPU (requête, payload et mise en cache)."""
    import base64
    appels = []

    monkeypatch.setattr(voix_wolof, "cle_cache", lambda t: tmp_path / "test_wo.wav")

    class FausseReponse:
        status_code = 200
        def json(self):
            return {
                "result": {
                    "wav_b64": base64.b64encode(b"RIFFWAVE_TEST_WOLOF_CEREBRIUM").decode("utf-8"),
                    "calcul_s": 0.45,
                    "audio_s": 2.1
                }
            }

    def faux_post(url, json=None, timeout=None, headers=None):
        appels.append({"url": url, "json": json, "headers": headers})
        return FausseReponse()

    monkeypatch.setenv("CEREBRIUM_API_KEY", "test_cerebrium_key_123")
    monkeypatch.setattr("requests.post", faux_post)

    texte = "AOCEDA dina saytu kuraŋ bi"
    audio, infos = voix_wolof.obtenir(texte, genre="femme")

    # 1. Vérification de l'appel Cerebrium
    assert len(appels) == 1
    assert "voix-wolof/fabriquer" in appels[0]["url"]
    # Vérification que la phonétique A-o-sé-da a été envoyée à Cerebrium
    assert "A-o-sé-da" in appels[0]["json"]["texte"]
    assert "Bearer test_cerebrium_key_123" == appels[0]["headers"]["Authorization"]

    # 2. Vérification de la réponse
    assert audio == b"RIFFWAVE_TEST_WOLOF_CEREBRIUM"
    assert infos["mime"] == "audio/wav"

    # 3. Vérification du cache disque immédiat (2e appel = 0 appel réseau)
    audio2, infos2 = voix_wolof.obtenir(texte, genre="femme")
    assert audio2 == b"RIFFWAVE_TEST_WOLOF_CEREBRIUM"
    assert infos2["cache"] is True
    assert len(appels) == 1  # Aucun 2e appel réseau grâce au cache !


def test_routage_vocal_auto_wolof():
    """Vérifie que le routeur vocal automatique oriente un audio Wolof vers le Wolof (et non vers le Dioula)."""
    from apps.ai_assistant.chatbot import dioula_routage, service_chat

    # Phrase exacte du test utilisateur
    texte_omni = "ah usida dafay seytu sa kurang ba noppi di la xamal sa koppal"
    probs_tiny = {"sn": 0.35, "fr": 0.12, "en": 0.08}  # Whisper tiny hésitant hors langues gérées

    dec = dioula_routage.decider(probs_tiny, lambda: (texte_omni, texte_omni), langue_conversation=None)
    assert dec["langue"] == "wo"
    assert dec["chemin"] == "wolof"
    assert "texte wolof net" in dec["raison"]

    # Vérification dans service_chat
    session = "test_routage_wo_auto"
    reponse_lg, source, conf = service_chat.choisir_langue(session, texte_omni, "auto", "wo")
    assert reponse_lg == "wo"
    assert source == "entendue (vocal)"
    assert conf == 1.0


# ── 6. Matrice de 30 Tests Croisés Wolof / Dioula / Baoulé / Français ─────────

MATRICE_30_PHRASES = [
    # 10 Wolof
    ("Nanga def, dama bëgg xam sama kuraŋ", "wo"),
    ("Kuraŋ bi dafay fay chaque jour", "wo"),
    ("Sama koppar jeex na ci compteur bi", "wo"),
    ("Fay sama facture de kuraŋ", "wo"),
    ("Waaw", "wo"),
    ("Déedéet", "wo"),
    ("Jerejef ci dimbal bi", "wo"),
    ("Dama bëgg recharger sama compteur", "wo"),
    ("Koppar yi jeex na", "wo"),
    ("Kuran bi fay na ci kër gi", "wo"),
    # 10 Dioula
    ("N ka kuran juru banna", "dyu"),
    ("Kuran tigɛra n ka so kɔnɔ", "dyu"),
    ("I ni sɔgɔma, n b'a fɛ ka juru san", "dyu"),
    ("Kilowati tan ni duuru tora n fɛ", "dyu"),
    ("Ɔnhɔn", "dyu"),
    ("I ni ce kosɔbɛ", "dyu"),
    ("N b'a fɛ ka recharger n ka compteur", "dyu"),
    ("Juru hakɛ jumɛn tora n fɛ wa ?", "dyu"),
    ("A ka di kosɔbɛ", "dyu"),
    ("I ni baara, n bɛ se ka kɛ cogo di ?", "dyu"),
    # 6 Baoulé
    ("Min mɛtɛri'n diman junman kun", "bci"),
    ("Amun nunnun frigo'n", "bci"),
    ("Wafa sɛ yɛ n kwla fa min facture n gua nun ɔn ?", "bci"),
    ("Andɛ'n, kuran'n waci", "bci"),
    ("Tchɛtchɛ", "bci"),
    ("Mo kpa", "bci"),
    # 4 Français
    ("Combien de crédit me reste-t-il sur mon compteur ?", "fr"),
    ("Éteins le climatiseur du salon", "fr"),
    ("Ma facture a augmenté ce mois-ci", "fr"),
    ("Merci beaucoup pour votre aide", "fr"),
]


@pytest.mark.parametrize("texte, attendu", MATRICE_30_PHRASES)
def test_matrice_30_phrases_discrimination_croisee(texte, attendu):
    """Matrice d'évaluation croisée de 30 phrases représentatives selon la spécification R1.
    Garantit l'étanchéité stricte entre Wolof, Dioula, Baoulé et Français sans faux positifs.
    """
    session = f"test-matrice-30-{abs(hash(texte)) & 0xffffff}"
    lg, source, conf = service_chat.choisir_langue(session, texte, "auto", None)
    assert lg == attendu, (
        f"ERREUR DE DISCRIMINATION sur '{texte}' : attendu '{attendu}', obtenu '{lg}' "
        f"(source: {source}, conf: {conf})"
    )


# ── 7. Benchmark de Latence et Profilage SLA (R2) ─────────────────────────────

class TestBenchmarkChaineWolof:
    """Benchmark automatisé étape par étape de la latence Wolof vérifiant les SLAs."""

    def test_benchmark_micro_etapes_sla(self):
        import time
        from apps.ai_assistant.chatbot import wolof_texte, service_wolof, wolof_relais

        texte_wo = "kuraŋ bi dafa fay ci kër gi, dama bëgg fay sama facture"

        # 1. Étape Détection lexicale CPU (SLA < 2.0 ms)
        t0 = time.perf_counter()
        for _ in range(100):
            est_wo, score = wolof_texte.est_wolof(texte_wo)
        t_detect = ((time.perf_counter() - t0) / 100.0) * 1000.0
        assert est_wo is True
        assert t_detect < 2.0, f"Latence détection ({t_detect:.2f} ms) dépasse le SLA de 2.0 ms"

        # 2. Étape Normalisation phonétique TTS (SLA < 0.5 ms)
        phrase_tts = "AOCEDA dina saytu sa kuraŋ"
        t0 = time.perf_counter()
        for _ in range(100):
            norm = wolof_texte.normaliser_phonetique_tts(phrase_tts)
        t_norm = ((time.perf_counter() - t0) / 100.0) * 1000.0
        assert "A-o-sé-da" in norm
        assert t_norm < 0.5, f"Latence phonétique ({t_norm:.2f} ms) dépasse le SLA de 0.5 ms"

        # 3. Étape Préparation Dossier sans appel réseau (SLA < 10.0 ms)
        t0 = time.perf_counter()
        dossier = service_wolof.preparer_dossier("sess-bench-sla", texte_wo, "ecrit", traduire_aller=False)
        t_dossier = (time.perf_counter() - t0) * 1000.0
        assert dossier is not None
        assert t_dossier < 10.0, f"Latence dossier ({t_dossier:.2f} ms) dépasse le SLA de 10.0 ms"

        # 4. Étape Traduction retour en cache LRU / catalogue (SLA < 1.0 ms)
        wolof_relais.vers_wolof("Bonjour")  # Amorçage cache
        t0 = time.perf_counter()
        for _ in range(100):
            res_trad = wolof_relais.vers_wolof("Bonjour")
        t_trad = ((time.perf_counter() - t0) / 100.0) * 1000.0
        assert "Nanga def" in res_trad or "Jamm" in res_trad
        assert t_trad < 1.0, f"Latence traduction retour en cache ({t_trad:.2f} ms) dépasse 1.0 ms"


# ── 8. Combinaison Google Traduction + DeepSeek & Nombres Composés (100 %) ─────

def test_nombres_composes_wolof_7500_et_18():
    """Vérifie l'évaluation exacte des nombres composés wolof et de la construction à nom intercalé."""
    n1 = wolof_texte.lire_nombres("Dama sotti juróom-ñaari junni ak juróomi téeméer ci sama compteur demb")
    assert n1 and n1[0]["valeur"] == 7500

    n2 = wolof_texte.lire_nombres("Ñaata laay fay bu dee dama lekk fukki kilowattheure ak juróom-ñatt ?")
    assert n2 and n2[0]["valeur"] == 18

    n3 = wolof_texte.lire_nombres("Sama faktiir mooy ñaar-fukki junni ak juróomi junni")
    assert n3 and n3[0]["valeur"] == 25000


def test_dossier_combine_google_et_deepseek_par_defaut(monkeypatch):
    """Garantit que TRADUIRE_ALLER est actif par défaut et que le dossier réunit Wolof + Google + Nombres + Glossaire."""
    assert service_wolof.TRADUIRE_ALLER is True
    monkeypatch.setattr(
        wolof_relais,
        "vers_francais",
        lambda wo: {"google": "J'ai versé 7 500 sur mon compteur hier", "duree_s": 0.12, "erreurs": []},
    )
    q = "Dama sotti juróom-ñaari junni ak juróomi téeméer ci sama konteer demb"
    d = service_wolof.preparer_dossier("sess-comb-01", q, "ecrit")
    assert "Traduction automatique Google (wolof -> français)" in d["texte"]
    assert "7500" in d["texte"]
    assert "sotti" in d["lexique"]
    assert "konteer" in d["lexique"]


def test_correction_metier_retour_wolof():
    """Vérifie le nettoyage Markdown et la correction déterministe des faux-amis Google (fr -> wo)."""
    assert wolof_relais._nettoyer("**7 500 francs CFA**") == "7 500 francs CFA"

    c1 = wolof_relais._corriger_metier_wolof(
        "Il vous reste 7 500 francs CFA de crédit sur votre compteur.",
        "Des na 7,500 CFA ci leble ci sa kontër.",
    )
    assert "7 500" in c1
    assert "kredi kuuraŋ" in c1
    assert "leble" not in c1

    c2 = wolof_relais._corriger_metier_wolof(
        "Pour 18 kilowattheures selon la tranche.",
        "Ngir 18 waxtu kilowatt ci bracket bi.",
    )
    assert "18 kilowattheure" in c2
    assert "tranche" in c2
    assert "waxtu kilowatt" not in c2

    c3 = wolof_relais._corriger_metier_wolof(
        "La consommation est forte le soir entre 18 heures et 22 heures.",
        "Tips: diggante 6 p.m. ak 10 waxtu ci bëccëg, dindi standby.",
    )
    assert "Xelal :" in c3
    assert "6 waxtu ci ngoon" in c3
    assert "10 waxtu ci guddi" in c3
    assert "veille" in c3


def test_pre_annonce_voix_wolof_pendant_flux(monkeypatch):
    """Vérifie que la salutation ET la 1re phrase traduite sont pré-annoncées tout de suite au GPU Wolof."""
    annonces = []
    monkeypatch.setattr(voix, "annoncer_wolof", lambda texte, genre="femme": annonces.append(texte))
    monkeypatch.setattr(voix_wolof, "reveiller_voix_wolof", lambda raison="": True)
    monkeypatch.setattr(
        wolof_relais,
        "vers_francais",
        lambda wo: {"google": "Mon courant est coupé", "duree_s": 0.01, "erreurs": []},
    )
    monkeypatch.setattr(
        wolof_relais,
        "vers_wolof",
        lambda fr: "Sa kuraŋ dafa fay." if "coupé" in fr else "Fayal klimaa bi.",
    )

    flux = deepseek_mock(
        "INTENTION : coupure de courant\n",
        "CERTITUDE : haute\n\n",
        "Votre courant est coupé. ",
        "Éteignez le climatiseur.",
    )
    list(service_wolof.repondre("sess-preannonce-wo", "kuraŋ bi fay na", origine="ecrit", liste=flux, voix_auto=True))

    # 1. Salutation (« Nanga def. »), 2. 1re phrase pendant le flux (« Sa kuraŋ dafa fay. »), 3. Suite (« Fayal klimaa bi. »)
    assert len(annonces) == 3
    assert len(set(annonces)) == 3
    assert "Sa kuraŋ dafa fay." in annonces




# ── 9. Corrections de l'audit du 10/11/2026 ────────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "Bonjour AOCEDA, quelle est ma consommation ?", "Merci AOCEDA", "Ok AOCEDA", "Coupe le climatiseur, AOCEDA",
    "I have seen my bill, it is too high", "Have you seen my bill?", "Can you jot down my consumption?",
    "Ma box LAN consomme combien ?", "Ma fille Dina a payé la facture", "Le ruban la nuit", "C'est un fan la musique",
    "Fay est mon voisin", "Lan est mon solde ?"])
def test_phrase_francaise_ou_anglaise_jamais_prise_pour_du_wolof(phrase):
    """Avant : « AOCEDA », « seen », « lan », « fay »... suffisaient (18 phrases sur 18 partaient en wolof, voix payante
    réveillée). Les expressions sont maintenant cherchées en mots entiers (« ruban la » ne contient plus « ban la »)."""
    assert wolof_texte.est_wolof(phrase)[0] is False


@pytest.mark.parametrize("phrase", [
    "Nanga def", "Waaw", "Jërejëf", "Dama bëgg xam sama facture", "Fay kuraŋ bi", "Sama koppar jeex na",
    "Naka sama kuraŋ bi ?", "Kuraŋ bi dafa fay", "Dina fay facture bi suba", "Waaw, fay ko", "Baax na"])
def test_vrai_wolof_toujours_reconnu(phrase):
    assert wolof_texte.est_wolof(phrase)[0] is True


def test_ecoute_wolof_certitude_jamais_inventee():
    """Le modèle ne donne aucune probabilité : certitude None (« non mesurée »), jamais 0,95 / 0,80 inventés."""
    from apps.ai_assistant.chatbot import wolof_ecoute
    e = wolof_ecoute.EcouteWolof([{"mot": "waaw", "certitude": None, "t0": 0, "t1": 5}], None, 1.0, 0.1, texte_libre="waaw")
    assert e.certitude is None and e.texte == "waaw"


def test_garde_de_parole_ecarte_le_bruit_garde_la_parole():
    from apps.ai_assistant.chatbot import wolof_ecoute
    rng = np.random.default_rng(1)
    t = np.arange(48000) / 16000
    bruits = {"silence": np.zeros(48000), "souffle": rng.standard_normal(48000) * 1e-3,
              "bruit blanc": rng.standard_normal(48000) * 0.03, "50 Hz": 0.2 * np.sin(2 * np.pi * 50 * t)}
    for nom, b in bruits.items():
        assert not wolof_ecoute.parole_presente(b.astype(np.float32)), nom
    # signal à enveloppe de parole : syllabes (porteuse 150 Hz) séparées de pauses
    syll = np.sin(2 * np.pi * 150 * t) * np.clip(np.sin(2 * np.pi * 1.5 * t), 0, None) ** 2
    assert wolof_ecoute.parole_presente((0.3 * syll + rng.standard_normal(48000) * 1e-4).astype(np.float32))


@pytest.mark.parametrize("texte", ["aaa aaa aaa aaa aaa", "masin di sini masin di sini masin di sini masin di sini",
                                   "a b c a b c a b c a b c"])
def test_texte_en_boucle_est_ecarte(texte):
    from apps.ai_assistant.chatbot import wolof_ecoute
    assert wolof_ecoute._en_boucle(texte)


def test_texte_normal_n_est_pas_une_boucle():
    from apps.ai_assistant.chatbot import wolof_ecoute
    assert not wolof_ecoute._en_boucle("nanga def ba beneen yendul ak jamm")


def test_traduction_wolof_ratee_leve_au_lieu_de_rendre_du_francais(monkeypatch):
    """Avant : le français était renvoyé comme du wolof et lu par la voix wolof. Maintenant : RelaisIndisponible,
    la phrase est affichée en français, marquée « non traduit »."""
    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: t)           # le traducteur rend le français tel quel
    with pytest.raises(dioula_relais.RelaisIndisponible):
        wolof_relais.vers_wolof("Votre consommation de la semaine dernière est stable.")

    def panne(s, sens, t):
        raise dioula_relais.RelaisIndisponible("google en panne")
    monkeypatch.setattr(dioula_relais, "traduire", panne)
    with pytest.raises(dioula_relais.RelaisIndisponible):
        wolof_relais.vers_wolof("Votre consommation de la semaine dernière est stable.")


def test_traduction_wolof_nombre_change_refusee_dirham_devient_francs(monkeypatch):
    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: "Sa koppar mooy 350 dërëm, ndax dafa tang.")
    assert "350 francs" in wolof_relais.vers_wolof("Votre solde est de 350 francs, car il fait chaud.")   # 350 dërëm = 1 750 F
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: "Sa koppar mooy 89 francs, ndax dafa tang.")
    with pytest.raises(dioula_relais.RelaisIndisponible):                             # 79 devenu 89
        wolof_relais.vers_wolof("Votre solde est de 79 francs, car il fait chaud.")


def test_voix_wolof_texte_long_coupe_en_morceaux_jamais_tronque():
    from apps.ai_assistant.chatbot import voix_wolof
    texte = "Nanga def, sa kuraŋ bi dafa baax. " * 20                                  # 680 caractères
    morceaux = voix_wolof.decouper_long(texte)
    assert len(morceaux) >= 2 and all(len(m) <= voix_wolof.MAX_CAR for m in morceaux)
    assert " ".join(morceaux).split() == texte.split()                                 # rien de perdu, aucun mot coupé


def test_page_dit_la_verite_sur_le_wolof(monkeypatch):
    from apps.ai_assistant.chatbot import wolof_ecoute
    monkeypatch.setattr(wolof_ecoute, "dossier", lambda: None)
    assert wolof_ecoute.disponible() is False
