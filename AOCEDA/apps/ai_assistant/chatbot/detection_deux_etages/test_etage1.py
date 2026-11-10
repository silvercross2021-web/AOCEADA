"""Tests unitaires et d'intégration pour l'Étage 1 Audio LID 5 langues.

Vérifie :
    1. Les formats d'entrée (chemin WAV, bytes, tableau NumPy mono/stéréo, rééchantillonnage).
    2. La validité et la sanité des distributions probabilistes (5 langues cibles, somme = 1.0, valeurs [0, 1]).
    3. Les deux variantes acoustiques FP32 (PyTorch) et INT8 (ONNX Runtime CPU).
    4. La règle de décision Gate (seuil >= 0.85 -> ASR_DEDIE avec verrou=True, < 0.85 -> POOL_CONCURRENT avec verrou=False).
    5. Le profilage de latence CPU (ms) et d'empreinte mémoire vive (Mo).
    6. L'exécution sur les audios réels du corpus AOCEDA pour les 5 langues cibles.
    7. Les cas limites (silence, signal court, padding).
"""

import io
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from apps.ai_assistant.chatbot.detection_deux_etages.etage1_audio_lid import (
    AudioFeatureExtractor,
    AudioLIDClassifier,
    GateDecision,
    LANGUES_CIBLES,
    SEUIL_GATE_PAR_DEFAUT,
    VarianteINT8ONNX,
)

# Chemins des audios de test dans le projet (parents[4] correspond à la racine AOCEDA)
RACINE_AOCEDA = Path(__file__).resolve().parents[4]
AUDIO_FRA = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V1.wav"
AUDIO_ENG = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V6.wav"
AUDIO_WOL = RACINE_AOCEDA / "lab_live/wolof_bench/resultats/test_cerebrium_live_wolof.wav"
AUDIO_DYU = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/dioula/D1.wav"
AUDIO_BCI = RACINE_AOCEDA / "apps/ai_assistant/chatbot/donnees/voix_baoule/femme_RK_waxal_9s9.wav"


@pytest.fixture(scope="module")
def audio_synthetique_2s() -> np.ndarray:
    """Génère un signal audio synthétique de 2,0 s (32000 échantillons à 16 kHz)."""
    t = np.linspace(0, 2.0, 32000, endpoint=False)
    # Signal multiton avec composantes de voix humaine
    sig = (0.4 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
    return sig


# ── 1. Tests de l'extracteur acoustique (NumPy & Soundfile) ──────────────────

def test_feature_extractor_audio_formats(audio_synthetique_2s):
    """Vérifie l'extraction de caractéristiques depuis différents formats (array, bytes, WAV)."""
    extractor = AudioFeatureExtractor()

    # 1.1 Entrée tableau NumPy mono 16 kHz
    feats_arr = extractor.extraire_features(audio_synthetique_2s)
    assert isinstance(feats_arr, np.ndarray)
    assert feats_arr.shape[0] == 162  # 80 Mel + 1 Énergie + 81 Deltas
    assert feats_arr.shape[1] > 0
    assert not np.isnan(feats_arr).any()
    assert not np.isinf(feats_arr).any()

    # 1.2 Entrée flux binaire bytes (WAV FLOAT sans perte)
    bio_float = io.BytesIO()
    sf.write(bio_float, audio_synthetique_2s, 16000, subtype="FLOAT", format="WAV")
    feats_float = extractor.extraire_features(bio_float.getvalue())
    assert feats_float.shape == feats_arr.shape
    assert np.allclose(feats_float, feats_arr, atol=1e-3)

    # 1.3 Entrée flux binaire bytes (WAV PCM 16-bit standard)
    bio_pcm = io.BytesIO()
    sf.write(bio_pcm, audio_synthetique_2s, 16000, format="WAV")
    feats_pcm = extractor.extraire_features(bio_pcm.getvalue())
    assert feats_pcm.shape == feats_arr.shape
    assert not np.isnan(feats_pcm).any()
    assert not np.isinf(feats_pcm).any()

    # 1.3 Entrée stéréo (2 canaux) rééchantillonnée
    audio_stereo = np.column_stack([audio_synthetique_2s, audio_synthetique_2s])
    feats_stereo = extractor.extraire_features(audio_stereo, sr=16000)
    assert feats_stereo.shape == feats_arr.shape

    # 1.4 Entrée avec fréquence d'échantillonnage non standard (ex: 22050 Hz)
    audio_22k = extractor.reechantillonner(audio_synthetique_2s, 16000)
    feats_22k = extractor.extraire_features(audio_22k, sr=22050)
    assert feats_22k.shape[0] == 162


def test_feature_extractor_fichier_reel():
    """Vérifie le chargement et l'extraction directe depuis un fichier WAV existant."""
    extractor = AudioFeatureExtractor()
    if AUDIO_FRA.exists():
        feats = extractor.extraire_features(str(AUDIO_FRA))
        assert feats.shape[0] == 162
        assert feats.shape[1] > 100
        assert not np.isnan(feats).any()


# ── 2. Tests de sanité des distributions probabilistes ───────────────────────

def test_audio_lid_classifier_defaut_int8(audio_synthetique_2s):
    """Vérifie que AudioLIDClassifier s'initialise par défaut avec le moteur INT8 ONNX."""
    classifier = AudioLIDClassifier()
    assert classifier.variante_nom == "int8"
    assert isinstance(classifier.moteur, VarianteINT8ONNX)

    dist = classifier.predire_probabilites(audio_synthetique_2s)
    assert isinstance(dist, dict)
    assert set(dist.keys()) == set(LANGUES_CIBLES)

    somme_probs = sum(dist.values())
    assert math.isclose(somme_probs, 1.0, rel_tol=1e-4)

    for lg, p in dist.items():
        assert 0.0 <= p <= 1.0, f"Probabilité hors bornes pour {lg}: {p}"


def test_distribution_sanity_int8(audio_synthetique_2s):
    """Vérifie que la VarianteINT8ONNX fournit une distribution softmax normalisée sur les 5 langues."""
    variante_int8 = VarianteINT8ONNX()
    dist = variante_int8.predire_probabilites(audio_synthetique_2s)

    assert isinstance(dist, dict)
    assert set(dist.keys()) == set(LANGUES_CIBLES)

    somme_probs = sum(dist.values())
    assert math.isclose(somme_probs, 1.0, rel_tol=1e-4)

    for lg, p in dist.items():
        assert 0.0 <= p <= 1.0, f"Probabilité hors bornes pour {lg}: {p}"


# ── 3. Tests de rejet explicite du modèle retiré FP32 ────────────────────────

def test_rejet_explicite_variante_fp32():
    """Vérifie que la demande explicite de 'fp32' est formellement rejetée avec ValueError."""
    with pytest.raises(ValueError, match="FP32"):
        AudioLIDClassifier(variante="fp32")


# ── 4. Tests de la règle de décision Gate (Seuil acoustique) ─────────────────

def test_gate_rule_seuil_atteint(audio_synthetique_2s):
    """Vérifie que lorsque max P(L) >= seuil, la décision est ASR_DEDIE avec verrou=True."""
    classifier = AudioLIDClassifier(variante="int8")

    # Avec un seuil bas garanti (ex: 0.10), la décision doit être ASR_DEDIE
    res: GateDecision = classifier.evaluer_gate(audio_synthetique_2s, seuil=0.10)

    assert res.decision == "ASR_DEDIE"
    assert res.verrou is True
    assert res.confiance >= 0.10
    assert res.langue in LANGUES_CIBLES
    assert res.variante == "int8"
    assert res.latence_ms > 0.0


def test_gate_rule_seuil_non_atteint(audio_synthetique_2s):
    """Vérifie que lorsque max P(L) < seuil, la décision est POOL_CONCURRENT avec verrou=False."""
    classifier = AudioLIDClassifier(variante="int8")

    # Avec un seuil délibérément inaccessible (0.999), la décision doit être POOL_CONCURRENT
    res: GateDecision = classifier.evaluer_gate(audio_synthetique_2s, seuil=0.999)

    assert res.decision == "POOL_CONCURRENT"
    assert res.verrou is False
    assert res.confiance < 0.999
    assert res.langue in LANGUES_CIBLES


def test_gate_seuil_standard_085():
    """Vérifie le respect du seuil par défaut de 0.85 sur les décisions de classification."""
    classifier = AudioLIDClassifier(variante="int8")
    assert SEUIL_GATE_PAR_DEFAUT == 0.85

    # Test avec fichier réel si présent
    if AUDIO_FRA.exists():
        res = classifier.classifier(str(AUDIO_FRA))
        if res.confiance >= 0.85:
            assert res.decision == "ASR_DEDIE"
            assert res.verrou is True
        else:
            assert res.decision == "POOL_CONCURRENT"
            assert res.verrou is False


# ── 5. Tests d'équivalence des formats d'entrée ──────────────────────────────

def test_equivalence_formats_entree():
    """Vérifie qu'un chemin de fichier, ses octets WAV et son tableau NumPy donnent le même résultat."""
    if not AUDIO_FRA.exists():
        pytest.skip("Fichier AUDIO_FRA introuvable pour le test d'équivalence.")

    classifier = AudioLIDClassifier(variante="int8")

    # 1. Chemin
    res_path = classifier.classifier(str(AUDIO_FRA))

    # 2. Octets
    with open(AUDIO_FRA, "rb") as f:
        octets = f.read()
    res_bytes = classifier.classifier(octets)

    # 3. Tableau NumPy
    data, sr = sf.read(str(AUDIO_FRA), dtype="float32")
    res_array = classifier.classifier(data, sr=sr)

    assert res_path.langue == res_bytes.langue == res_array.langue
    assert math.isclose(res_path.confiance, res_bytes.confiance, rel_tol=1e-3)
    assert math.isclose(res_path.confiance, res_array.confiance, rel_tol=1e-3)


# ── 6. Tests de profilage (Latence et Empreinte Mémoire) ─────────────────────

def test_mesurer_latence_et_memoire(audio_synthetique_2s):
    """Vérifie que la méthode de benchmarking renvoie des métriques CPU et RAM cohérentes pour INT8."""
    classifier = AudioLIDClassifier(variante="int8")

    # Profilage INT8
    prof_int8 = classifier.mesurer_latence_et_memoire(audio_synthetique_2s, variante="int8", repetitions=5)
    assert prof_int8["variante"] == "int8"
    assert prof_int8["latence_moyenne_ms"] > 0.0
    assert prof_int8["latence_moyenne_ms"] < 250.0  # Moins de 250 ms sur CPU standard
    assert prof_int8["memoire_allouee_mo"] >= 0.0
    assert prof_int8["repetitions"] == 5

    # Rejet explicite de FP32
    with pytest.raises(ValueError):
        classifier.mesurer_latence_et_memoire(audio_synthetique_2s, variante="fp32")


# ── 7. Tests d'exécution sur les 5 langues réelles du projet ──────────────────

@pytest.mark.parametrize(
    "langue_attendue, chemin_fichier",
    [
        ("fra", AUDIO_FRA),
        ("eng", AUDIO_ENG),
        ("wol", AUDIO_WOL),
        ("dyu", AUDIO_DYU),
        ("bci", AUDIO_BCI),
    ],
)
def test_audios_reels_corpus_projet(langue_attendue, chemin_fichier):
    """Vérifie l'exécution sans erreur sur les enregistrements réels des 5 langues cibles."""
    if not chemin_fichier.exists():
        pytest.skip(f"Audio absent pour {langue_attendue} : {chemin_fichier}")

    classifier = AudioLIDClassifier(variante="int8")
    decision = classifier.classifier(str(chemin_fichier))

    assert isinstance(decision, GateDecision)
    assert decision.langue in LANGUES_CIBLES
    assert decision.decision in ("ASR_DEDIE", "POOL_CONCURRENT")
    assert math.isclose(sum(decision.distribution.values()), 1.0, rel_tol=1e-4)


# ── 8. Tests des cas limites (Silence et Signaux Courts) ──────────────────────

def test_cas_limite_silence_absolu():
    """Vérifie qu'un signal de silence absolu ne provoque pas de division par zéro ni de crash."""
    silence = np.zeros(32000, dtype=np.float32)
    classifier = AudioLIDClassifier(variante="int8")

    res = classifier.classifier(silence)
    assert res.decision in ("ASR_DEDIE", "POOL_CONCURRENT")
    assert not math.isnan(res.confiance)
    assert not math.isnan(sum(res.distribution.values()))


def test_cas_limite_signal_tres_court():
    """Vérifie qu'un chunk audio très court (< 0,5 s) est automatiquement paddé et classé."""
    court = np.sin(2 * np.pi * 440 * np.linspace(0, 0.2, 3200)).astype(np.float32)
    classifier = AudioLIDClassifier(variante="int8")

    res = classifier.classifier(court)
    assert res.langue in LANGUES_CIBLES
    assert res.confiance > 0.0


def test_cas_limite_octets_vides():
    """Vérifie que des octets vides b'' ne font pas crasher l'extracteur et retournent du silence."""
    classifier = AudioLIDClassifier(variante="int8")
    res = classifier.classifier(b"")
    assert res.decision in ("ASR_DEDIE", "POOL_CONCURRENT")
    assert not math.isnan(res.confiance)


def test_cas_limite_pcm_brut_sans_entete():
    """Vérifie la robustesse face à un flux d'octets PCM brut 16-bit sans conteneur WAV."""
    raw_pcm = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000)) * 16000).astype(np.int16).tobytes()
    classifier = AudioLIDClassifier(variante="int8")
    res = classifier.classifier(raw_pcm)
    assert res.langue in LANGUES_CIBLES
    assert res.confiance > 0.0


def test_cas_limite_fichier_inexistant():
    """Vérifie qu'un chemin de fichier inexistant lève proprement FileNotFoundError."""
    classifier = AudioLIDClassifier(variante="int8")
    with pytest.raises(FileNotFoundError):
        classifier.classifier("fichier_inexistant_xyz_123.wav")
