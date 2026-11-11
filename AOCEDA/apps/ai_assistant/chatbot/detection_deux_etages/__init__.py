"""Sous-module detection_deux_etages d'AOCEDA.

Architecture « Acoustic-First, Lexical Guardrails » :
    - Étage 1 : Identification acoustique de la langue (Audio LID Meta MMS 5 langues optimisé INT8 ONNX).
    - Étage 2 : Dictionnaire Lego / sous-mots n-grammes validés et garde-fou Rollback.
    - Pipeline : Orchestrateur unifié (`est_active()` lit CHATBOT_DETECTION_DEUX_ETAGES, faux par défaut).

ÉTAT AU 10/11/2026 : EXPÉRIMENTAL, BRANCHÉ NULLE PART. Aucun module du flux de production (`voix.py`, `service_chat.py`,
`dioula_routage.py`) n'appelle ce paquet ; seuls ses propres tests et `outils/banc_adversaire_detection.py` l'utilisent. Activer le
drapeau ne change donc rien. Ne pas le brancher sans l'avoir mesuré sur des audios INÉDITS : l'audit du 10/11/2026 a trouvé son
étage audio à environ 41 % sur des enregistrements jamais vus (ses 95 % portaient sur des données d'entraînement), contre 75 % pour
la détection de la production. Voir docs/architecture/decisions/0005-standards-interface-ia-et-detection-deux-etages.md.
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
