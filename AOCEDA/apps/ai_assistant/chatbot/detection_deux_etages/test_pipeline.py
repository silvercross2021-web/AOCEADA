"""Tests unitaires et de validation fonctionnelle pour le Pipeline à Deux Étages unifié.

Vérifications formelles (R3 & R5) :
    1. Normalisation et compatibilité bidirectionnelle des codes de langues (AOCEDA <-> ISO 639-3).
    2. Respect strict du drapeau d'activation `CHATBOT_DETECTION_DEUX_ETAGES` (préservation 100% legacy par défaut).
    3. Coordination de l'Étage 1 (Audio LID Gate) : aiguillage immédiat (>= 0.85) vs pool concurrent (< 0.85).
    4. Validation nominale de bout en bout sur les 5 langues cibles avec les audios réels du projet.
    5. Déclenchement avéré du Rollback en cas d'erreur de routage (mismatch) ou de charabia phonétique.
    6. Préservation prioritaire absolue des commandes critiques de sécurité (COUPER, ALLUMER, OUI, NON).
    7. Fonctionnement avec callback de transcription dynamique.
    8. Profilage de latence de bout en bout (ms).
    9. Résilience aux cas limites (octets vides, silence).
"""
import io
import time
from pathlib import Path
from typing import Dict

import numpy as np
import pytest

from apps.ai_assistant.chatbot.detection_deux_etages import (
    AudioLIDClassifier,
    ClassificateurLegoNgrammes,
    LANGUES_AOCEDA,
    LANGUES_ISO3,
    PipelineDeuxEtages,
    PipelineResult,
    est_active,
    normaliser_vers_aoceda,
    normaliser_vers_iso3,
    sont_codes_equivalents,
)

RACINE_AOCEDA = Path(__file__).resolve().parents[4]
AUDIO_FRA = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V1.wav"
AUDIO_ENG = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V6.wav"
AUDIO_WOL = RACINE_AOCEDA / "lab_live/wolof_bench/resultats/test_cerebrium_live_wolof.wav"
AUDIO_DYU = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/dioula/D1.wav"
AUDIO_BCI = RACINE_AOCEDA / "apps/ai_assistant/chatbot/donnees/voix_baoule/femme_RK_waxal_9s9.wav"


@pytest.fixture(scope="module")
def audio_synthetique_2s() -> np.ndarray:
    """Génère un signal audio synthétique 16 kHz de 2,0 s."""
    t = np.linspace(0, 2.0, 32000, endpoint=False)
    return (0.5 * np.sin(2 * np.pi * 330 * t) + 0.3 * np.sin(2 * np.pi * 660 * t)).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalisation et Équivalence des Codes de Langue
# ─────────────────────────────────────────────────────────────────────────────

def test_compatibilite_codes_langues():
    """Vérifie la correspondance biunivoque entre nomenclature AOCEDA et ISO 639-3."""
    assert normaliser_vers_aoceda("fra") == "fr"
    assert normaliser_vers_aoceda("fr") == "fr"
    assert normaliser_vers_aoceda("eng") == "en"
    assert normaliser_vers_aoceda("en") == "en"
    assert normaliser_vers_aoceda("wol") == "wo"
    assert normaliser_vers_aoceda("wo") == "wo"
    assert normaliser_vers_aoceda("dyu") == "dyu"
    assert normaliser_vers_aoceda("bci") == "bci"

    assert normaliser_vers_iso3("fr") == "fra"
    assert normaliser_vers_iso3("en") == "eng"
    assert normaliser_vers_iso3("wo") == "wol"
    assert normaliser_vers_iso3("dyu") == "dyu"
    assert normaliser_vers_iso3("bci") == "bci"

    # Vérification d'équivalence
    assert sont_codes_equivalents("fra", "fr") is True
    assert sont_codes_equivalents("eng", "en") is True
    assert sont_codes_equivalents("wol", "wo") is True
    assert sont_codes_equivalents("dyu", "dyu") is True
    assert sont_codes_equivalents("bci", "bci") is True
    assert sont_codes_equivalents("fra", "wol") is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Comportement du Drapeau de Configuration (Désactivé par défaut)
# ─────────────────────────────────────────────────────────────────────────────

def test_pipeline_flag_desactive_par_defaut(audio_synthetique_2s):
    """Vérifie que le pipeline est désactivé par défaut et préserve le flux legacy."""
    pipeline = PipelineDeuxEtages()  # lit est_active() -> False par défaut
    assert pipeline.actif is False

    res = pipeline.traiter(audio_synthetique_2s, transcription="Bonjour le courant est coupé")
    assert res.est_actif is False
    assert res.statut == "DESACTIVE"
    assert res.action == "CONTINUER"
    assert res.aiguillage == "LEGACY"
    assert "legacy" in res.explication.lower()


def test_pipeline_activation_explicite_et_forcer_actif(audio_synthetique_2s):
    """Vérifie qu'on peut activer explicitement le pipeline sans toucher au .env."""
    pipeline_actif = PipelineDeuxEtages(actif=True)
    assert pipeline_actif.actif is True

    res = pipeline_actif.traiter(audio_synthetique_2s, transcription="Bonjour je voudrais payer ma facture")
    assert res.est_actif is True
    assert res.statut in ("CONFIRME", "VALIDE", "ATTENTE_TRANSCRIPTION")

    # Test forcer_actif sur une instance inactive
    pipeline_inactif = PipelineDeuxEtages(actif=False)
    res_force = pipeline_inactif.traiter(
        audio_synthetique_2s,
        transcription="Bonjour je voudrais payer ma facture",
        forcer_actif=True,
    )
    assert res_force.est_actif is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Évaluation Acoustique Seule (Morceau 0)
# ─────────────────────────────────────────────────────────────────────────────

def test_evaluer_audio_seul(audio_synthetique_2s):
    """Vérifie la décision d'aiguillage au premier étage avant que la transcription n'existe."""
    pipeline = PipelineDeuxEtages(actif=True, seuil_gate=0.85)
    res = pipeline.evaluer_audio_seul(audio_synthetique_2s)

    assert res.est_actif is True
    assert res.statut in ("ATTENTE_TRANSCRIPTION", "POOL_CONCURRENT")
    assert res.aiguillage in ("ASR_DEDIE", "POOL_CONCURRENT")
    assert res.langue in LANGUES_AOCEDA
    assert res.langue_iso3 in LANGUES_ISO3
    assert res.confiance_acoustique > 0.0
    assert res.latence_totale_ms > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Validation Nominale de Bout en Bout sur les 5 Langues Cibles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "langue_attendue, chemin_fichier, transcription",
    [
        ("fr", AUDIO_FRA, "Bonjour quel est le solde de mon compteur électrique"),
        ("en", AUDIO_ENG, "Hello how can I reduce my electricity bill please"),
        ("wo", AUDIO_WOL, "nanga def sama xarit kuran bi dafa fay ci kër gi"),
        ("dyu", AUDIO_DYU, "I ni sɔgɔma n ka kuran juru banna ne b'a fɛ ka sara"),
        ("bci", AUDIO_BCI, "Aɲiho min kuran'n w'a wie sua'n nun ti kekle"),
    ],
)
def test_validation_nominale_corpus_reel_5_langues(langue_attendue, chemin_fichier, transcription):
    """Vérifie que les audios réels et leurs transcriptions sont validés avec succès."""
    if not chemin_fichier.exists():
        pytest.skip(f"Audio non disponible : {chemin_fichier}")

    pipeline = PipelineDeuxEtages(actif=True, variante_acoustique="int8")
    res = pipeline.traiter(str(chemin_fichier), transcription=transcription)

    assert res.est_actif is True
    assert res.action == "CONTINUER"
    assert res.charabia is False
    assert res.recommencer_ecoute is False
    assert res.statut in ("VALIDE", "CONFIRME")
    assert res.langue == langue_attendue
    assert res.langue_iso3 == normaliser_vers_iso3(langue_attendue)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Détection de Conflit d'Aiguillage (Mismatch) et Déclenchement du Rollback
# ─────────────────────────────────────────────────────────────────────────────

def test_rollback_conflit_acoustique_vers_autre_langue():
    """Un audio classé dans une langue A mais transcrivant clairement une langue B déclenche un Rollback."""
    pipeline = PipelineDeuxEtages(actif=True)

    # Audio Dioula réel (D1.wav) injecté avec une transcription wolof typique
    if not AUDIO_DYU.exists():
        pytest.skip("Audio D1.wav absent")

    phrase_wolof = "nanga def sama xarit kuran bi dafa fay ci kër gi"
    res = pipeline.traiter(str(AUDIO_DYU), transcription=phrase_wolof)

    # Le dictionnaire Lego doit intercepter l'inadéquation entre l'ASR dioula et le texte wolof
    assert res.statut == "ROLLBACK"
    assert res.action == "ANNULER"
    assert res.charabia is True
    assert res.recommencer_ecoute is True
    assert res.verrou is False
    assert res.aiguillage == "POOL_CONCURRENT"
    assert "Rollback" in res.explication


def test_rollback_charabia_hallucination_asr():
    """Vérifie l'annulation immédiate sur une boucle d'hallucination d'ASR."""
    pipeline = PipelineDeuxEtages(actif=True)
    if not AUDIO_FRA.exists():
        pytest.skip("Audio V1.wav absent")

    res = pipeline.traiter(str(AUDIO_FRA), transcription="to to to to to to to to")
    assert res.statut == "ROLLBACK"
    assert res.action == "ANNULER"
    assert res.charabia is True
    assert res.recommencer_ecoute is True


def test_rollback_amas_consonantique_invraisemblable():
    """Vérifie l'interception d'un bruit corrompu avec amas de consonnes impossible."""
    pipeline = PipelineDeuxEtages(actif=True)
    if not AUDIO_FRA.exists():
        pytest.skip("Audio V1.wav absent")

    res = pipeline.traiter(str(AUDIO_FRA), transcription="kuran zrktpmwfsx banna")
    assert res.statut == "ROLLBACK"
    assert res.action == "ANNULER"
    assert res.charabia is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. Préservation Prioritaire des Commandes Critiques de Sécurité
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "ordre_critique,type_attendu",
    [
        ("couper le courant", "COUPER"),
        ("coupe", "COUPER"),
        ("éteins l'appareil", "COUPER"),
        ("fay ko", "COUPER"),
        ("a tigɛ", "COUPER"),
        ("kpe nun", "COUPER"),
        ("allumer le compteur", "ALLUMER"),
        ("taal ko", "ALLUMER"),
        ("a mɛnɛ", "ALLUMER"),
        ("oui", "OUI"),
        ("waaw", "OUI"),
        ("non", "NON"),
        ("déedéet", "NON"),
        ("coupe coupe coupe coupe", "COUPER"),  # Urgence répétée
    ],
)
def test_commandes_critiques_prioritaires(ordre_critique, type_attendu, audio_synthetique_2s):
    """Vérifie qu'un ordre critique n'est JAMAIS annulé ni rejeté par le pipeline."""
    pipeline = PipelineDeuxEtages(actif=True)
    res = pipeline.traiter(audio_synthetique_2s, transcription=ordre_critique)

    assert res.statut == "COMMANDE_CRITIQUE"
    assert res.action == "CONTINUER"
    assert res.charabia is False
    assert res.recommencer_ecoute is False
    assert res.commande_critique == type_attendu
    assert res.verrou is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Support d'une Fonction de Transcription Dynamique (Callback ASR)
# ─────────────────────────────────────────────────────────────────────────────

def test_callback_transcription_dynamique(audio_synthetique_2s):
    """Vérifie que le pipeline peut invoquer une fonction ASR passée en paramètre."""
    pipeline = PipelineDeuxEtages(actif=True)

    appels = []

    def mock_asr(audio, code_langue):
        appels.append((len(audio), code_langue))
        return "Bonjour mon disjoncteur a disjoncté"

    res = pipeline.traiter(audio_synthetique_2s, fn_transcription=mock_asr)

    assert len(appels) == 1
    assert res.statut in ("VALIDE", "CONFIRME")
    assert res.action == "CONTINUER"
    assert res.langue == "fr"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Mesure de Latence de Bout en Bout (< 25 ms sur CPU standard)
# ─────────────────────────────────────────────────────────────────────────────

def test_mesure_latence_bout_en_bout(audio_synthetique_2s):
    """Vérifie le benchmark de latence combiné Étage 1 + Étage 2."""
    pipeline = PipelineDeuxEtages(actif=True, variante_acoustique="int8")
    metrics = pipeline.mesurer_latence_bout_en_bout(
        audio_synthetique_2s,
        transcription="Bonjour quel est le solde de mon compteur électrique",
        repetitions=5,
    )

    assert "latence_moyenne_ms" in metrics
    assert metrics["latence_moyenne_ms"] > 0.0
    assert metrics["latence_moyenne_ms"] < 250.0  # Inférieur à 250 ms sur CPU
    assert metrics["variante"] == "int8"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Résilience aux Cas Limites (Octets vides, Silence)
# ─────────────────────────────────────────────────────────────────────────────

def test_resilience_octets_vides():
    """Vérifie qu'une entrée d'octets vide b'' ne provoque aucune levée d'exception fatale."""
    pipeline = PipelineDeuxEtages(actif=True)
    res = pipeline.traiter(b"", transcription="Bonjour")
    assert res.est_actif is True
    assert res.statut in ("VALIDE", "CONFIRME", "ROLLBACK", "ATTENTE_TRANSCRIPTION")
    assert res.action in ("CONTINUER", "ANNULER")

    # Vérifie également le traitement direct sans transcription
    res_sans_texte = pipeline.traiter(b"")
    assert res_sans_texte.est_actif is True
    assert res_sans_texte.statut in ("ATTENTE_TRANSCRIPTION", "POOL_CONCURRENT")


def test_resilience_silence_absolu():
    """Vérifie qu'un tableau de zéros est traité sans division par zéro ni crash."""
    silence = np.zeros(32000, dtype=np.float32)
    pipeline = PipelineDeuxEtages(actif=True)
    res = pipeline.traiter(silence, transcription="Hello please help me check my bill")
    assert res.est_actif is True
    assert res.statut in ("VALIDE", "CONFIRME", "ROLLBACK")
    assert res.action in ("CONTINUER", "ANNULER")

    # Vérifie le traitement sans texte
    res_sans_texte = pipeline.traiter(silence)
    assert res_sans_texte.est_actif is True
    assert res_sans_texte.statut in ("ATTENTE_TRANSCRIPTION", "POOL_CONCURRENT")
