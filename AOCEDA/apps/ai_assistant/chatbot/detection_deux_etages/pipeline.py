"""Pipeline d'Intégration Unifié pour la Détection de Langue à Deux Étages d'AOCEDA.

Architecture « Acoustic-First, Lexical Guardrails » (Exigence R3) :
    1. Étage 1 (Acoustic Gate) : Analyse directe du signal audio 16 kHz brut
       via Audio LID Meta MMS élagué (variante optimisée INT8 ONNX).
       - Confiance acoustique P(L) >= 0.85 -> ASR_DEDIE (verrou immédiat posé dès le Morceau 0).
       - Confiance acoustique P(L) < 0.85  -> POOL_CONCURRENT (maintien sécurisé du pool concurrent).
    2. Étage 2 (Lexical Guardrail) : Garde-fou textuel ultra-rapide (< 1 ms CPU)
       fondé sur le Dictionnaire Lego et n-grammes de caractères pour les 5 langues.
       - Interception prioritaire absolue des ordres critiques de sécurité (COUPER, ALLUMER, OUI, NON).
       - Validation de conformité de la transcription issue de l'ASR.
       - Détection de charabia phonétique ou d'erreur d'aiguillage acoustique (mismatch)
         avec déclenchement immédiat de l'ordre d'annulation (Rollback).
    3. Découplage et activation modulaire :
       - Contrôlé par le flag `CHATBOT_DETECTION_DEUX_ETAGES` (défaut False).
       - Lorsque désactivé (False), le flux historique standard est préservé à 100 %.
       - Lorsque activé (True), le pipeline à 2 étages coordonne le routage et le contrôle.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

import numpy as np

from .etage1_audio_lid import (
    AudioLIDClassifier,
    GateDecision,
    LANGUES_CIBLES as LANGUES_ETAGE1,
    SEUIL_GATE_PAR_DEFAUT,
)
from .etage2_dictionnaire_lego import (
    ClassificateurLegoNgrammes,
    DecisionGardeFou,
    LANGUES_CIBLES as LANGUES_ETAGE2,
    normaliser_code_langue,
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Standardisation et Normalisation Bidirectionnelle des Codes de Langues
# ─────────────────────────────────────────────────────────────────────────────

# AOCEDA canonique : codes utilisés nativement dans le projet ('fr', 'en', 'wo', 'dyu', 'bci')
LANGUES_AOCEDA: Tuple[str, ...] = ("fr", "en", "wo", "dyu", "bci")

# ISO 639-3 : codes utilisés par les modèles Audio LID Meta MMS ('fra', 'eng', 'wol', 'dyu', 'bci')
LANGUES_ISO3: Tuple[str, ...] = ("fra", "eng", "wol", "dyu", "bci")

TABLE_ISO3_VERS_AOCEDA: Dict[str, str] = {
    "fra": "fr",
    "fre": "fr",
    "fr": "fr",
    "french": "fr",
    "eng": "en",
    "en": "en",
    "english": "en",
    "wol": "wo",
    "wo": "wo",
    "wolof": "wo",
    "dyu": "dyu",
    "jula": "dyu",
    "dioula": "dyu",
    "bam": "dyu",
    "bambara": "dyu",
    "bci": "bci",
    "baoule": "bci",
    "baoulé": "bci",
    "wawle": "bci",
}

TABLE_AOCEDA_VERS_ISO3: Dict[str, str] = {
    "fr": "fra",
    "fra": "fra",
    "en": "eng",
    "eng": "eng",
    "wo": "wol",
    "wol": "wol",
    "dyu": "dyu",
    "bci": "bci",
}


def normaliser_vers_aoceda(code: str) -> str:
    """Convertit tout code ou alias de langue vers le format canonique AOCEDA ('fr', 'en', 'wo', 'dyu', 'bci')."""
    if not code:
        return "fr"
    c = str(code).strip().lower()
    return TABLE_ISO3_VERS_AOCEDA.get(c, c)


def normaliser_vers_iso3(code: str) -> str:
    """Convertit tout code vers la nomenclature ISO 639-3 ('fra', 'eng', 'wol', 'dyu', 'bci')."""
    if not code:
        return "fra"
    c = str(code).strip().lower()
    return TABLE_AOCEDA_VERS_ISO3.get(c, c)


def sont_codes_equivalents(code1: str, code2: str) -> bool:
    """Indique si deux codes de langue désignent la même langue cible (ex: 'fra' et 'fr')."""
    return normaliser_vers_aoceda(code1) == normaliser_vers_aoceda(code2)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Lecture du Drapeau d'Activation (Configuration Django / Environment)
# ─────────────────────────────────────────────────────────────────────────────

def est_active() -> bool:
    """Détermine si le système de détection à deux étages est activé.

    Vérifie par ordre de priorité :
        1. Variable Django `settings.CHATBOT_DETECTION_DEUX_ETAGES`
        2. Dictionnaire de configuration `CONFIG["DETECTION_DEUX_ETAGES"]`
        3. Variable d'environnement système `CHATBOT_DETECTION_DEUX_ETAGES`
        4. Par défaut : False (préservation stricte du flux de production existant).
    """
    try:
        from django.conf import settings
        val_settings = getattr(settings, "CHATBOT_DETECTION_DEUX_ETAGES", None)
        if val_settings is not None:
            return bool(val_settings)
    except Exception:
        pass

    try:
        from apps.ai_assistant.chatbot.config import CONFIG
        val_config = CONFIG.get("DETECTION_DEUX_ETAGES", None)
        if val_config is not None:
            return bool(val_config)
    except Exception:
        pass

    val_env = os.environ.get("CHATBOT_DETECTION_DEUX_ETAGES", "").strip().lower()
    if val_env in ("1", "true", "yes", "on", "enable", "enabled"):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Structure Formalisée du Résultat Pipeline
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Résultat complet et auditable de l'évaluation à deux étages."""

    est_actif: bool
    statut: str               # "CONFIRME", "VALIDE", "ROLLBACK", "COMMANDE_CRITIQUE", "POOL_CONCURRENT", "ATTENTE_TRANSCRIPTION", "DESACTIVE"
    action: str               # "CONTINUER", "ANNULER", "EXECUTER_COMMANDE"
    langue: str               # Code canonique AOCEDA ('fr', 'en', 'wo', 'dyu', 'bci')
    langue_iso3: str          # Code ISO 639-3 ('fra', 'eng', 'wol', 'dyu', 'bci')
    aiguillage: str           # "ASR_DEDIE", "POOL_CONCURRENT", "LEGACY"
    verrou: bool              # True si la langue est certifiée et verrouillée
    charabia: bool            # True si anomalie acoustique/lexicale ou hallucination détectée
    recommencer_ecoute: bool  # True si l'écoute doit être réinitialisée sans polluer l'historique
    confiance_acoustique: float = 0.0
    score_textuel: float = 0.0
    decision_gate: Optional[GateDecision] = None
    decision_garde_fou: Optional[DecisionGardeFou] = None
    commande_critique: Optional[str] = None  # "COUPER", "ALLUMER", "OUI", "NON"
    latence_totale_ms: float = 0.0
    explication: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. Orchestrateur Unifié PipelineDeuxEtages
# ─────────────────────────────────────────────────────────────────────────────

class PipelineDeuxEtages:
    """Orchestrateur unifié pour la détection de langue à deux étages.

    Coordonne :
        - Étage 1 : Audio LID Meta MMS (INT8 ONNX) avec règle de seuil (Gate 0.85).
        - Étage 2 : Dictionnaire Lego / n-grammes de sous-mots & Garde-fou Rollback.
        - Respect de la politique de sécurité et découplage modulaire.
    """

    def __init__(
        self,
        actif: Optional[bool] = None,
        variante_acoustique: str = "int8",
        seuil_gate: float = SEUIL_GATE_PAR_DEFAUT,
    ) -> None:
        """Initialise le pipeline.

        Args:
            actif: Booléen explicite ou None (dans ce cas, lit la configuration).
            variante_acoustique: 'int8' (optimisé ONNX CPU exclusif).
            seuil_gate: Seuil de confiance acoustique pour l'aiguillage ASR direct (0.85).
        """
        self.actif: bool = est_active() if actif is None else bool(actif)
        self.variante_acoustique: str = variante_acoustique.lower()
        self.seuil_gate: float = float(seuil_gate)

        # Chargement à la demande (lazy-loading) pour préserver les ressources CPU/RAM
        self._audio_lid: Optional[AudioLIDClassifier] = None
        self._garde_fou: Optional[ClassificateurLegoNgrammes] = None

    @property
    def audio_lid(self) -> AudioLIDClassifier:
        """Accès paresseux à l'instance de l'Étage 1."""
        if self._audio_lid is None:
            self._audio_lid = AudioLIDClassifier(variante=self.variante_acoustique)
        return self._audio_lid

    @property
    def garde_fou(self) -> ClassificateurLegoNgrammes:
        """Accès paresseux à l'instance de l'Étage 2."""
        if self._garde_fou is None:
            self._garde_fou = ClassificateurLegoNgrammes()
        return self._garde_fou

    def evaluer_audio_seul(
        self,
        audio_input: Union[str, Path, bytes, np.ndarray],
        sr: Optional[int] = None,
        forcer_actif: bool = False,
    ) -> PipelineResult:
        """Évalue uniquement la tranche audio (Morceau 0) à l'Étage 1 (Audio LID).

        Permet d'orienter immédiatement vers l'ASR approprié avant que le texte ne soit transcrit.
        """
        if not self.actif and not forcer_actif:
            return PipelineResult(
                est_actif=False,
                statut="DESACTIVE",
                action="CONTINUER",
                langue="fr",
                langue_iso3="fra",
                aiguillage="LEGACY",
                verrou=False,
                charabia=False,
                recommencer_ecoute=False,
                explication="Pipeline 2 étages inactif (mode legacy standard préservé).",
            )

        t0 = time.perf_counter()
        gate = self.audio_lid.evaluer_gate(audio_input, seuil=self.seuil_gate, sr=sr)
        latence = (time.perf_counter() - t0) * 1000.0

        langue_aoceda = normaliser_vers_aoceda(gate.langue)
        langue_iso3 = normaliser_vers_iso3(gate.langue)

        if gate.decision == "ASR_DEDIE":
            statut = "ATTENTE_TRANSCRIPTION"
            aiguillage = "ASR_DEDIE"
            verrou = True
            explication = (
                f"Aiguillage sélectif immédiat vers l'ASR '{langue_aoceda}' ({langue_iso3}) "
                f"avec confiance acoustique {gate.confiance:.2f} >= {self.seuil_gate:.2f}. Verrou posé au Morceau 0."
            )
        else:
            statut = "POOL_CONCURRENT"
            aiguillage = "POOL_CONCURRENT"
            verrou = False
            explication = (
                f"Confiance acoustique {gate.confiance:.2f} < {self.seuil_gate:.2f} (mode hésitation). "
                "Maintien temporaire du pool concurrent d'écoute."
            )

        return PipelineResult(
            est_actif=True,
            statut=statut,
            action="CONTINUER",
            langue=langue_aoceda,
            langue_iso3=langue_iso3,
            aiguillage=aiguillage,
            verrou=verrou,
            charabia=False,
            recommencer_ecoute=False,
            confiance_acoustique=gate.confiance,
            score_textuel=0.0,
            decision_gate=gate,
            decision_garde_fou=None,
            commande_critique=None,
            latence_totale_ms=latence,
            explication=explication,
        )

    def evaluer_transcription_seule(
        self,
        transcription: str,
        langue_attendue: str = "fr",
        forcer_actif: bool = False,
    ) -> PipelineResult:
        """Évalue directement une transcription textuelle à l'Étage 2 (Dictionnaire Lego)."""
        if not self.actif and not forcer_actif:
            return PipelineResult(
                est_actif=False,
                statut="DESACTIVE",
                action="CONTINUER",
                langue=normaliser_vers_aoceda(langue_attendue),
                langue_iso3=normaliser_vers_iso3(langue_attendue),
                aiguillage="LEGACY",
                verrou=False,
                charabia=False,
                recommencer_ecoute=False,
                explication="Pipeline 2 étages inactif (mode legacy standard).",
            )

        t0 = time.perf_counter()
        code_attendu_aoceda = normaliser_vers_aoceda(langue_attendue)
        garde = self.garde_fou.verifier(transcription, langue_attendue=code_attendu_aoceda)
        latence = (time.perf_counter() - t0) * 1000.0

        langue_detectee_aoceda = normaliser_vers_aoceda(garde.langue_detectee)
        langue_detectee_iso3 = normaliser_vers_iso3(garde.langue_detectee)

        return PipelineResult(
            est_actif=True,
            statut=garde.statut,
            action=garde.action,
            langue=langue_detectee_aoceda if garde.statut == "COMMANDE_CRITIQUE" else code_attendu_aoceda,
            langue_iso3=langue_detectee_iso3 if garde.statut == "COMMANDE_CRITIQUE" else normaliser_vers_iso3(code_attendu_aoceda),
            aiguillage="ASR_DEDIE",
            verrou=garde.statut in ("CONFIRME", "VALIDE"),
            charabia=garde.charabia,
            recommencer_ecoute=garde.recommencer_ecoute,
            confiance_acoustique=1.0,
            score_textuel=garde.score_adequation,
            decision_gate=None,
            decision_garde_fou=garde,
            commande_critique=garde.commande_critique,
            latence_totale_ms=latence,
            explication=garde.explication,
        )

    def traiter(
        self,
        audio_input: Union[str, Path, bytes, np.ndarray],
        transcription: Optional[str] = None,
        fn_transcription: Optional[Callable[[Union[str, Path, bytes, np.ndarray], str], str]] = None,
        forcer_actif: bool = False,
        sr: Optional[int] = None,
    ) -> PipelineResult:
        """Exécute le pipeline complet de bout en bout (Étage 1 Audio LID -> ASR -> Étage 2 Garde-fou Lego).

        Args:
            audio_input: Signal audio brut (fichier WAV, octets PCM, ou array NumPy mono).
            transcription: Chaîne textuelle issue de l'ASR (si déjà disponible).
            fn_transcription: Fonction de rappel (audio, code_langue) -> texte à exécuter si transcription est None.
            forcer_actif: Si True, exécute le pipeline même si le flag de configuration global est à False.
            sr: Fréquence d'échantillonnage de l'entrée si non standard (défaut 16 kHz).

        Returns:
            PipelineResult formalisé et auditable.
        """
        # 1. Vérification du drapeau d'activation
        if not self.actif and not forcer_actif:
            return PipelineResult(
                est_actif=False,
                statut="DESACTIVE",
                action="CONTINUER",
                langue="fr",
                langue_iso3="fra",
                aiguillage="LEGACY",
                verrou=False,
                charabia=False,
                recommencer_ecoute=False,
                explication="Pipeline 2 étages inactif (CHATBOT_DETECTION_DEUX_ETAGES=False). Flux legacy préservé.",
            )

        t_debut = time.perf_counter()

        # 2. Étage 1 : Identification acoustique de langue
        gate = self.audio_lid.evaluer_gate(audio_input, seuil=self.seuil_gate, sr=sr)
        langue_acoustique_aoceda = normaliser_vers_aoceda(gate.langue)
        langue_acoustique_iso3 = normaliser_vers_iso3(gate.langue)

        # 3. Récupération de la transcription
        texte_a_verifier = transcription
        if texte_a_verifier is None and fn_transcription is not None:
            texte_a_verifier = fn_transcription(audio_input, langue_acoustique_aoceda)

        # Si aucune transcription n'est fournie (ex: fin d'étape 1 avant lancement de l'ASR)
        if texte_a_verifier is None:
            latence_ms = (time.perf_counter() - t_debut) * 1000.0
            aiguillage = "ASR_DEDIE" if gate.decision == "ASR_DEDIE" else "POOL_CONCURRENT"
            verrou = (gate.decision == "ASR_DEDIE")
            statut = "ATTENTE_TRANSCRIPTION" if verrou else "POOL_CONCURRENT"

            return PipelineResult(
                est_actif=True,
                statut=statut,
                action="CONTINUER",
                langue=langue_acoustique_aoceda,
                langue_iso3=langue_acoustique_iso3,
                aiguillage=aiguillage,
                verrou=verrou,
                charabia=False,
                recommencer_ecoute=False,
                confiance_acoustique=gate.confiance,
                score_textuel=0.0,
                decision_gate=gate,
                decision_garde_fou=None,
                commande_critique=None,
                latence_totale_ms=latence_ms,
                explication=(
                    f"Étage 1 achevé ({aiguillage}, confiance {gate.confiance:.2f}). "
                    f"En attente de transcription ASR pour validation Étage 2."
                ),
            )

        # 4. Étage 2 : Dictionnaire Lego, vérification de cohérence et garde-fou
        if gate.decision == "ASR_DEDIE":
            # Mode orienté : la langue attendue est verrouillée par l'acoustique
            garde = self.garde_fou.verifier(texte_a_verifier, langue_attendue=langue_acoustique_aoceda)
        else:
            # Mode hésitation (POOL_CONCURRENT) : l'acoustique n'a pas posé de verrou (< 0.85).
            # L'Étage 2 classifie d'abord le texte pour identifier la langue exprimée.
            cmd_critique = self.garde_fou.detecter_commande_critique(texte_a_verifier)
            if cmd_critique is not None:
                garde = self.garde_fou.verifier(texte_a_verifier, langue_attendue=cmd_critique[1])
            else:
                lg_pred, conf_pred, _ = self.garde_fou.classifier(texte_a_verifier)
                garde = self.garde_fou.verifier(texte_a_verifier, langue_attendue=lg_pred)

        latence_totale_ms = (time.perf_counter() - t_debut) * 1000.0

        langue_textuelle_aoceda = normaliser_vers_aoceda(garde.langue_detectee)
        langue_textuelle_iso3 = normaliser_vers_iso3(garde.langue_detectee)

        # ── CAS A : Commande critique de sécurité ────────────────────────────
        # Priorité absolue de sécurité : les ordres d'urgence ne sont jamais rejetés
        if garde.statut == "COMMANDE_CRITIQUE":
            return PipelineResult(
                est_actif=True,
                statut="COMMANDE_CRITIQUE",
                action="CONTINUER",
                langue=langue_textuelle_aoceda,
                langue_iso3=langue_textuelle_iso3,
                aiguillage="ASR_DEDIE",
                verrou=True,
                charabia=False,
                recommencer_ecoute=False,
                confiance_acoustique=gate.confiance,
                score_textuel=1.0,
                decision_gate=gate,
                decision_garde_fou=garde,
                commande_critique=garde.commande_critique,
                latence_totale_ms=latence_totale_ms,
                explication=f"Commande critique de sécurité prioritaire : {garde.commande_critique} ({langue_textuelle_aoceda}).",
            )

        # ── CAS B : Détection de charabia ou erreur d'aiguillage -> ROLLBACK ──
        if garde.charabia or garde.statut == "ROLLBACK":
            return PipelineResult(
                est_actif=True,
                statut="ROLLBACK",
                action="ANNULER",
                langue=langue_textuelle_aoceda if garde.langue_detectee != "inconnue" else langue_acoustique_aoceda,
                langue_iso3=langue_textuelle_iso3 if garde.langue_detectee != "inconnue" else langue_acoustique_iso3,
                aiguillage="POOL_CONCURRENT",  # Rétrogradation vers écoute élargie
                verrou=False,                  # Annulation du verrou acoustique
                charabia=True,
                recommencer_ecoute=True,
                confiance_acoustique=gate.confiance,
                score_textuel=garde.score_adequation,
                decision_gate=gate,
                decision_garde_fou=garde,
                commande_critique=None,
                latence_totale_ms=latence_totale_ms,
                explication=(
                    f"Rollback déclenché : {garde.explication} "
                    f"[Acoustique: {langue_acoustique_aoceda} ({gate.confiance:.2f}), "
                    f"Texte détecté: {langue_textuelle_aoceda}]."
                ),
            )

        # ── CAS C : Validation ou Confirmation nominale ──────────────────────
        langue_finale_aoceda = langue_acoustique_aoceda
        langue_finale_iso3 = langue_acoustique_iso3

        # Si l'Étage 1 était en mode pool concurrent (< 0.85), l'Étage 2 départage et certifie
        if gate.decision == "POOL_CONCURRENT" and garde.statut in ("CONFIRME", "VALIDE"):
            langue_finale_aoceda = langue_textuelle_aoceda
            langue_finale_iso3 = langue_textuelle_iso3
            aiguillage = "ASR_DEDIE"
            verrou = True
        else:
            aiguillage = "ASR_DEDIE"
            verrou = (gate.decision == "ASR_DEDIE")

        return PipelineResult(
            est_actif=True,
            statut=garde.statut,
            action="CONTINUER",
            langue=langue_finale_aoceda,
            langue_iso3=langue_finale_iso3,
            aiguillage=aiguillage,
            verrou=verrou,
            charabia=False,
            recommencer_ecoute=False,
            confiance_acoustique=gate.confiance,
            score_textuel=garde.score_adequation,
            decision_gate=gate,
            decision_garde_fou=garde,
            commande_critique=None,
            latence_totale_ms=latence_totale_ms,
            explication=(
                f"Détection validée avec succès pour '{langue_finale_aoceda}' ({langue_finale_iso3}) : "
                f"Acoustique P(L)={gate.confiance:.2f}, Adéquation lexicale={garde.score_adequation:.2f}."
            ),
        )

    def mesurer_latence_bout_en_bout(
        self,
        audio_input: Union[str, Path, bytes, np.ndarray],
        transcription: str,
        repetitions: int = 15,
        sr: Optional[int] = None,
    ) -> Dict[str, float]:
        """Mesure empirique précise de la latence CPU de bout en bout (Étage 1 + Étage 2)."""
        # Warmup
        for _ in range(2):
            _ = self.traiter(audio_input, transcription=transcription, forcer_actif=True, sr=sr)

        latences = []
        for _ in range(repetitions):
            t0 = time.perf_counter()
            _ = self.traiter(audio_input, transcription=transcription, forcer_actif=True, sr=sr)
            latences.append((time.perf_counter() - t0) * 1000.0)

        return {
            "variante": self.variante_acoustique,
            "latence_moyenne_ms": float(np.mean(latences)),
            "latence_mediane_ms": float(np.median(latences)),
            "latence_min_ms": float(np.min(latences)),
            "latence_max_ms": float(np.max(latences)),
            "repetitions": repetitions,
        }
