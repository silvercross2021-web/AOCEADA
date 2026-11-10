"""Sous-module detection_deux_etages d'AOCEDA.

Architecture « Acoustic-First, Lexical Guardrails » :
    - Étage 1 : Identification acoustique de la langue (Audio LID Meta MMS 5 langues optimisé INT8 ONNX).
    - Étage 2 : Dictionnaire Lego / sous-mots n-grammes validés et garde-fou Rollback.
    - Pipeline : Orchestrateur unifié activable via CHATBOT_DETECTION_DEUX_ETAGES.
"""
from .etage1_audio_lid import (
    AudioFeatureExtractor,
    AudioLIDClassifier,
    GateDecision,
    LANGUES_CIBLES as LANGUES_ACOUSTIQUES,
    SEUIL_GATE_PAR_DEFAUT,
    VarianteINT8ONNX,
)
from .etage2_dictionnaire_lego import (
    ClassificateurLegoNgrammes,
    DecisionGardeFou,
    LANGUES_CIBLES as LANGUES_TEXTUELLES,
    classifier_langue_lego,
    detecter_charabia,
    normaliser_code_langue,
    verifier_transcription_et_garde_fou,
)
from .pipeline import (
    LANGUES_AOCEDA,
    LANGUES_ISO3,
    PipelineDeuxEtages,
    PipelineResult,
    est_active,
    normaliser_vers_aoceda,
    normaliser_vers_iso3,
    sont_codes_equivalents,
)

__all__ = [
    # Étage 1 Audio LID
    "AudioFeatureExtractor",
    "AudioLIDClassifier",
    "GateDecision",
    "LANGUES_ACOUSTIQUES",
    "SEUIL_GATE_PAR_DEFAUT",
    "VarianteINT8ONNX",
    # Étage 2 Dictionnaire Lego
    "ClassificateurLegoNgrammes",
    "DecisionGardeFou",
    "LANGUES_TEXTUELLES",
    "classifier_langue_lego",
    "detecter_charabia",
    "normaliser_code_langue",
    "verifier_transcription_et_garde_fou",
    # Pipeline Unifié
    "LANGUES_AOCEDA",
    "LANGUES_ISO3",
    "PipelineDeuxEtages",
    "PipelineResult",
    "est_active",
    "normaliser_vers_aoceda",
    "normaliser_vers_iso3",
    "sont_codes_equivalents",
]
