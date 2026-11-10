"""Batterie Complète de Tests Approfondis sur Cas Extrêmes — Détection de Langue à Deux Étages.

Couvre de façon exhaustive et automatisée les 35 cas de figure extrêmes formalisés
dans la matrice d'audit (Milestone M3, Requirement R3) sur 7 dimensions critiques :
    1. Dimension 1 : Argot / Nouchi et expressions idiomatiques (ARG-01 à ARG-05)
    2. Dimension 2 : Variations dialectales et régionales (DIA-01 à DIA-05)
    3. Dimension 3 : Alternance codique / Code-switching (CSW-01 à CSW-04)
    4. Dimension 4 : Chiffres composés et montants d'énergie (NUM-01 à NUM-05)
    5. Dimension 5 : Bruit acoustique et signaux dégradés (NOI-01 à NOI-04)
    6. Dimension 6 : Segments audio ultra-courts et interjections (SHO-01 à SHO-09)
    7. Dimension 7 : Requêtes critiques et ordres de sécurité électrique (SEC-01 à SEC-07)

Vérifie également l'intégration de bout en bout dans le pipeline unifié,
la conformité aux garde-fous de coupure physique (AGENTS.md) et la latence sub-milliseconde.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pytest

from apps.ai_assistant.chatbot.detection_deux_etages import (
    AudioLIDClassifier,
    ClassificateurLegoNgrammes,
    DecisionGardeFou,
    PipelineDeuxEtages,
    PipelineResult,
    normaliser_vers_aoceda,
    normaliser_vers_iso3,
)

RACINE_AOCEDA = Path(__file__).resolve().parents[4]
AUDIO_FRA = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V1.wav"
AUDIO_ENG = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/questions/V6.wav"
AUDIO_WOL = RACINE_AOCEDA / "lab_live/wolof_bench/resultats/test_cerebrium_live_wolof.wav"
AUDIO_DYU = RACINE_AOCEDA / "apps/ai_assistant/rapports/audios/dioula/D1.wav"
AUDIO_BCI = RACINE_AOCEDA / "apps/ai_assistant/chatbot/donnees/voix_baoule/femme_RK_waxal_9s9.wav"


def injecter_bruit_snr(signal: np.ndarray, snr_db: float) -> np.ndarray:
    """Injecte un bruit blanc gaussien stationnaire à un ratio SNR donné en dB."""
    puissance_signal = np.mean(signal ** 2)
    if puissance_signal <= 1e-9:
        return signal
    puissance_bruit = puissance_signal / (10.0 ** (snr_db / 10.0))
    rng = np.random.default_rng(42)
    bruit = rng.normal(0, np.sqrt(puissance_bruit), signal.shape).astype(signal.dtype)
    return np.clip(signal + bruit, -1.0, 1.0)


@pytest.fixture(scope="module")
def classifier_lego() -> ClassificateurLegoNgrammes:
    """Instance partagée du classificateur Lego Étage 2."""
    return ClassificateurLegoNgrammes()


@pytest.fixture(scope="module")
def pipeline() -> PipelineDeuxEtages:
    """Instance configurée du pipeline à deux étages (INT8 ONNX)."""
    return PipelineDeuxEtages(actif=True, variante_acoustique="int8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dimension 1 : Argot / Nouchi et Expressions Idiomatiques (ARG-01 à ARG-05)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension1ArgotNouchi:
    """Validation de la résilience face à l'argot local (nouchi, familier, urbain)."""

    def test_arg01_nouchi_compteur_ivoirien(self, classifier_lego):
        """ARG-01 : 'Mon kpa est gâté, y'a pas drap sur le compteur' (Nouchi FR)."""
        texte = "Mon kpa est gâté, y'a pas drap sur le compteur"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut in ("VALIDE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.charabia is False
        assert res.score_adequation >= 0.30

    def test_arg02_nouchi_courant_djai(self, classifier_lego):
        """ARG-02 : 'Le djai de mon courant est fini chap-chap' (Nouchi FR)."""
        texte = "Le djai de mon courant est fini chap-chap"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "fr"
        assert res.charabia is False

    def test_arg03_argot_francais_thune_jus(self, classifier_lego):
        """ARG-03 : 'J'ai plus de thune pour payer le jus, mon compteur déconne' (Argot FR)."""
        texte = "J'ai plus de thune pour payer le jus, mon compteur déconne"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "fr"
        assert res.charabia is False

    def test_arg04_argot_anglais_busted_pronto(self, classifier_lego):
        """ARG-04 : 'Power is totally busted bro, top up my meter pronto' (Argot EN)."""
        texte = "Power is totally busted bro, top up my meter pronto"
        res = classifier_lego.verifier(texte, langue_attendue="en")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "en"
        assert res.charabia is False

    def test_arg05_wolof_urbain_derem_kuran(self, classifier_lego):
        """ARG-05 : 'Dama amul benn dërëm ci sama kuraŋ' (Wolof Urbain)."""
        texte = "Dama amul benn dërëm ci sama kuraŋ"
        res = classifier_lego.verifier(texte, langue_attendue="wo")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "wo"
        assert res.charabia is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dimension 2 : Variations Dialectales et Régionales (DIA-01 à DIA-05)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension2VariationsDialectales:
    """Validation sur les variantes dialectales ouest-africaines."""

    def test_dia01_dioula_standard_ci(self, classifier_lego):
        """DIA-01 : 'I ni sɔgɔma, n ka kuran juru banna' (Dioula standard CI)."""
        texte = "I ni sɔgɔma, n ka kuran juru banna"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "dyu"
        assert res.charabia is False

    def test_dia02_bambara_malien_kurani(self, classifier_lego):
        """DIA-02 : 'I ni sogoma, n ka kurani juru banna, wari banna' (Bambara ML)."""
        texte = "I ni sogoma, n ka kurani juru banna, wari banna"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "dyu"
        assert res.charabia is False

    def test_dia03_mandingue_nord_tike(self, classifier_lego):
        """DIA-03 : 'A tike kuran juru banna' (Variante Mandingue occlusive sourde /k/)."""
        texte = "A tike kuran juru banna"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "dyu"
        assert res.charabia is False

    def test_dia04_wolof_dakarois_courant_coupe(self, classifier_lego):
        """DIA-04 : 'Sama courant bi dafa coupé ci kër gi' (Wolof urbain dakarisé)."""
        texte = "Sama courant bi dafa coupé ci kër gi"
        res = classifier_lego.verifier(texte, langue_attendue="wo")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "wo"
        assert res.charabia is False

    def test_dia05_baoule_regional_kouran_suan(self, classifier_lego):
        """DIA-05 : 'Aniho, min kouran wa wie sua'n nun' (Baoulé avec graphie francisée)."""
        texte = "Aniho, min kouran wa wie sua'n nun"
        res = classifier_lego.verifier(texte, langue_attendue="bci")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "bci"
        assert res.charabia is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dimension 3 : Alternance Codique / Code-Switching (CSW-01 à CSW-04)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension3CodeSwitching:
    """Validation de l'immunité au faux rejet lors de l'alternance de langues."""

    def test_csw01_francais_dioula_dominant(self, classifier_lego):
        """CSW-01 : 'Bonjour monsieur, n ka kuran juru banna, comment je peux faire ?'"""
        texte = "Bonjour monsieur, n ka kuran juru banna, comment je peux faire ?"
        # Si orienté Dioula (corps de la demande), validation sans rollback
        res_dyu = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res_dyu.statut in ("VALIDE", "CONFIRME")
        assert res_dyu.action == "CONTINUER"
        assert res_dyu.charabia is False

    def test_csw02_francais_baoule_dominant(self, classifier_lego):
        """CSW-02 : 'Allô AOCEDA, min kuran'n w'a wie, je n'ai plus de lumière à la maison'"""
        texte = "Allô AOCEDA, min kuran'n w'a wie, je n'ai plus de lumière à la maison"
        res_bci = classifier_lego.verifier(texte, langue_attendue="bci")
        assert res_bci.statut in ("VALIDE", "CONFIRME")
        assert res_bci.action == "CONTINUER"
        assert res_bci.charabia is False

    def test_csw03_bilinguisme_equilibre_recharge_wave(self, classifier_lego, pipeline):
        """CSW-03 : 'Je veux recharger mon compteur avec Wave, n bɛ se ka wari sara di ?'"""
        texte = "Je veux recharger mon compteur avec Wave, n bɛ se ka wari sara di ?"
        # En mode hésitation/pool concurrent, le pipeline valide la demande
        res = pipeline.evaluer_transcription_seule(texte, langue_attendue="fr", forcer_actif=True)
        assert res.statut in ("VALIDE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.charabia is False

    def test_csw04_francais_courtoisie_wolof(self, classifier_lego):
        """CSW-04 : 'Est-ce que je peux avoir ma facture d'électricité en ligne ? Jerejef'"""
        texte = "Est-ce que je peux avoir ma facture d'électricité en ligne ? Jerejef"
        res_fr = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res_fr.statut == "CONFIRME"
        assert res_fr.action == "CONTINUER"
        assert res_fr.langue_detectee == "fr"
        assert res_fr.charabia is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dimension 4 : Chiffres Composés et Montants d'Énergie (NUM-01 à NUM-05)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension4ChiffresEtMontants:
    """Validation de la numération complexe, vigésimale et tokens STS."""

    def test_num01_cardinaux_français_mille_cinq_cents(self, classifier_lego):
        """NUM-01 : 'Trois mille cinq cents francs CFA de recharge' (FR)."""
        texte = "Trois mille cinq cents francs CFA de recharge"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "fr"
        assert res.charabia is False

    def test_num02_quatre_vingt_dix_huit_kwh(self, classifier_lego):
        """NUM-02 : 'Quatre-vingt-dix-huit kilowattheures consommés hier' (FR vigésimal)."""
        texte = "Quatre-vingt-dix-huit kilowattheures consommés hier"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut in ("VALIDE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "fr"
        assert res.charabia is False

    def test_num03_dioula_vigesimal_kwh(self, classifier_lego):
        """NUM-03 : 'Kilowati lɛrɛ bi naani ni fila tora n fɛ' (42 kWh restants en Dioula)."""
        texte = "Kilowati lɛrɛ bi naani ni fila tora n fɛ"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut == "CONFIRME"
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "dyu"
        assert res.charabia is False

    def test_num04_dioula_montant_monetaire_traditionnel(self, classifier_lego):
        """NUM-04 : 'Wari ba fila ni kemɛ saba' (2 300 FCFA en numération traditionnelle)."""
        texte = "Wari ba fila ni kemɛ saba"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut in ("VALIDE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.langue_detectee == "dyu"
        assert res.charabia is False

    def test_num05_format_chiffres_bruts_et_compteur(self, classifier_lego):
        """NUM-05 : '3 500 FCFA sur mon compteur 04289123' (Format chiffres bruts)."""
        texte = "3 500 FCFA sur mon compteur 04289123"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut in ("VALIDE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.charabia is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Dimension 5 : Bruit Acoustique et Signaux Dégradés (NOI-01 à NOI-04)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension5BruitEtDegradation:
    """Validation de la robustesse face au bruit et à la corruption acoustique."""

    def test_noi01_audio_bruite_snr_5db_maintien_pool_puis_validation(self, pipeline):
        """NOI-01 : Requête Dioula avec injection de bruit de fond SNR 5 dB."""
        if not AUDIO_DYU.exists():
            pytest.skip("Audio D1.wav non disponible localement.")

        signal_brut = pipeline.audio_lid.extractor.charger_audio(AUDIO_DYU)
        signal_bruite = injecter_bruit_snr(signal_brut, snr_db=5.0)
        res_audio = pipeline.evaluer_audio_seul(signal_bruite, forcer_actif=True)
        # Bruit abaisse la certitude acoustique -> POOL_CONCURRENT ou ASR_DEDIE
        assert res_audio.aiguillage in ("POOL_CONCURRENT", "ASR_DEDIE")

        # La transcription issue du décodage est validée par l'Étage 2
        res_complet = pipeline.evaluer_transcription_seule(
            "N be se ka do bo n ka kuran fakitiri", langue_attendue="dyu", forcer_actif=True
        )
        assert res_complet.statut in ("VALIDE", "CONFIRME")
        assert res_complet.action == "CONTINUER"
        assert res_complet.charabia is False

    def test_noi02_audio_bruite_climatiseur_snr_0db(self, pipeline):
        """NOI-02 : Vocal Français bruité par ronronnement à SNR 0 dB."""
        if not AUDIO_FRA.exists():
            pytest.skip("Audio V1.wav non disponible localement.")

        signal_brut = pipeline.audio_lid.extractor.charger_audio(AUDIO_FRA)
        signal_bruite = injecter_bruit_snr(signal_brut, snr_db=0.0)
        res_audio = pipeline.evaluer_audio_seul(signal_bruite, forcer_actif=True)
        assert res_audio.statut in ("ATTENTE_TRANSCRIPTION", "POOL_CONCURRENT")

        # Validation de la transcription textuelle associée
        res_complet = pipeline.evaluer_transcription_seule(
            "bonjour comment reduire facture electricite", langue_attendue="fr", forcer_actif=True
        )
        assert res_complet.statut == "CONFIRME"
        assert res_complet.action == "CONTINUER"

    def test_noi03_bruit_de_souffle_amas_consonnes_rollback(self, classifier_lego):
        """NOI-03 : Bruit de souffle / frottement -> amas consonantique 'skzkxtrvm fgbhjkqlpm'."""
        texte = "skzkxtrvm fgbhjkqlpm"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "ROLLBACK"
        assert res.action == "ANNULER"
        assert res.charabia is True
        assert res.recommencer_ecoute is True

    def test_noi04_hallucination_boucle_repetitive_rollback(self, classifier_lego):
        """NOI-04 : Boucle d'hallucination ASR répétitive 'to to to to to to to to'."""
        texte = "to to to to to to to to"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "ROLLBACK"
        assert res.action == "ANNULER"
        assert res.charabia is True
        assert res.recommencer_ecoute is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. Dimension 6 : Segments Audio Très Courts (< 1s, Interjections) (SHO-01 à SHO-09)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension6SegmentsAudioCourts:
    """Validation de la sanctuarisation des réponses courtes et interjections."""

    @pytest.mark.parametrize("texte,langue_attendue,cmd_attendue", [
        ("Oui", "fr", "OUI"),
        ("Non", "fr", "NON"),
        ("Waaw", "wo", "OUI"),
        ("Déedéet", "wo", "NON"),
        ("Awɔ", "dyu", "OUI"),
        ("Ɔn ɔn", "dyu", "NON"),
        ("Ɛɛn", "bci", "OUI"),
        ("Nan", "bci", "NON"),
    ])
    def test_sho01_a_08_monosyllabes_approbation_refus(self, classifier_lego, texte, langue_attendue, cmd_attendue):
        """SHO-01 à SHO-08 : Monosyllabes d'approbation et de refus dans les 5 langues."""
        res = classifier_lego.verifier(texte, langue_attendue=langue_attendue)
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.action == "CONTINUER"
        assert res.commande_critique == cmd_attendue
        assert res.charabia is False

    def test_sho09_interjection_hesitation_euh_rollback(self, classifier_lego):
        """SHO-09 : Interjection d'hésitation 'Euh...' -> Rollback sans pollution d'historique."""
        texte = "Euh..."
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "ROLLBACK"
        assert res.action == "ANNULER"
        assert res.charabia is True
        assert res.recommencer_ecoute is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Dimension 7 : Ordres Critiques et Sécurité Électrique (SEC-01 à SEC-07)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimension7SecuriteElectrique:
    """Validation stricte des ordres impératifs de sécurité et coupure."""

    def test_sec01_coupure_urgence_francais(self, classifier_lego):
        """SEC-01 : 'Couper le courant immédiatement' (Ordre direct FR)."""
        texte = "Couper le courant immédiatement"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.action == "CONTINUER"

    def test_sec02_panique_repetition_coupe_coupe(self, classifier_lego):
        """SEC-02 : Répétition d'urgence 'Coupe coupe coupe coupe' (non bloquée par anti-boucle)."""
        texte = "Coupe coupe coupe coupe"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.action == "CONTINUER"

    def test_sec03_coupure_wolof_fay_ko(self, classifier_lego):
        """SEC-03 : 'Fay ko léegi' (Ordre impératif Wolof)."""
        texte = "Fay ko léegi"
        res = classifier_lego.verifier(texte, langue_attendue="wo")
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.action == "CONTINUER"

    def test_sec04_coupure_dioula_a_tige(self, classifier_lego):
        """SEC-04 : 'A tigɛ sisan' (Ordre impératif Dioula D9 réel)."""
        texte = "A tigɛ sisan"
        res = classifier_lego.verifier(texte, langue_attendue="dyu")
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.action == "CONTINUER"

    def test_sec05_coupure_baoule_kpe_nun(self, classifier_lego):
        """SEC-05 : 'Kpe nun kpa' (Ordre impératif Baoulé)."""
        texte = "Kpe nun kpa"
        res = classifier_lego.verifier(texte, langue_attendue="bci")
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.action == "CONTINUER"

    def test_sec06_alerte_disjoncteur_incendie(self, classifier_lego):
        """SEC-06 : 'Le disjoncteur a sauté, danger incendie éteignez tout' (Alerte électrique)."""
        texte = "Le disjoncteur a sauté, danger incendie éteignez tout"
        res = classifier_lego.verifier(texte, langue_attendue="fr")
        assert res.statut in ("COMMANDE_CRITIQUE", "CONFIRME")
        assert res.action == "CONTINUER"
        assert res.charabia is False

    def test_sec07_priorite_securite_sur_mismatch_hostile(self, classifier_lego):
        """SEC-07 : Ordre Dioula 'a tigɛ' alors que la langue attendue était Anglais ('en')."""
        texte = "a tigɛ"
        res = classifier_lego.verifier(texte, langue_attendue="en")
        # RÈGLE VITALE : La sécurité physique l'emporte sur le mismatch linguistique
        assert res.statut == "COMMANDE_CRITIQUE"
        assert res.commande_critique == "COUPER"
        assert res.langue_detectee == "dyu"
        assert res.action == "CONTINUER"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Intégration E2E, Pipeline et Benchmark de Latence
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationEtLatenceCasExtremes:
    """Validation de l'intégration globale du pipeline et du respect des contraintes de latence."""

    def test_benchmark_latence_sub_milliseconde_sur_cas_extremes(self, classifier_lego):
        """Vérifie que la latence moyenne d'évaluation sur les 35 cas reste < 1.0 ms CPU."""
        corpus_35_cas = [
            ("Mon kpa est gâté, y'a pas drap sur le compteur", "fr"),
            ("Le djai de mon courant est fini chap-chap", "fr"),
            ("J'ai plus de thune pour payer le jus, mon compteur déconne", "fr"),
            ("Power is totally busted bro, top up my meter pronto", "en"),
            ("Dama amul benn dërëm ci sama kuraŋ", "wo"),
            ("I ni sɔgɔma, n ka kuran juru banna", "dyu"),
            ("I ni sogoma, n ka kurani juru banna, wari banna", "dyu"),
            ("A tike kuran juru banna", "dyu"),
            ("Sama courant bi dafa coupé ci kër gi", "wo"),
            ("Aniho, min kouran wa wie sua'n nun", "bci"),
            ("Bonjour monsieur, n ka kuran juru banna, comment je peux faire ?", "dyu"),
            ("Allô AOCEDA, min kuran'n w'a wie, je n'ai plus de lumière à la maison", "bci"),
            ("Je veux recharger mon compteur avec Wave, n bɛ se ka wari sara di ?", "fr"),
            ("Est-ce que je peux avoir ma facture d'électricité en ligne ? Jerejef", "fr"),
            ("Trois mille cinq cents francs CFA de recharge", "fr"),
            ("Quatre-vingt-dix-huit kilowattheures consommés hier", "fr"),
            ("Kilowati lɛrɛ bi naani ni fila tora n fɛ", "dyu"),
            ("Wari ba fila ni kemɛ saba", "dyu"),
            ("3 500 FCFA sur mon compteur 04289123", "fr"),
            ("skzkxtrvm fgbhjkqlpm", "fr"),
            ("to to to to to to to to", "fr"),
            ("Oui", "fr"),
            ("Non", "fr"),
            ("Waaw", "wo"),
            ("Déedéet", "wo"),
            ("Awɔ", "dyu"),
            ("Ɔn ɔn", "dyu"),
            ("Ɛɛn", "bci"),
            ("Nan", "bci"),
            ("Euh...", "fr"),
            ("Couper le courant immédiatement", "fr"),
            ("Coupe coupe coupe coupe", "fr"),
            ("Fay ko léegi", "wo"),
            ("A tigɛ sisan", "dyu"),
            ("Kpe nun kpa", "bci"),
            ("Le disjoncteur a sauté, danger incendie éteignez tout", "fr"),
            ("a tigɛ", "en"),
        ]

        t0 = time.perf_counter()
        nb_repetitions = 50
        for _ in range(nb_repetitions):
            for t, lg in corpus_35_cas:
                classifier_lego.verifier(t, langue_attendue=lg)

        duree_totale = time.perf_counter() - t0
        nb_evals = len(corpus_35_cas) * nb_repetitions
        latence_moyenne_ms = (duree_totale / nb_evals) * 1000.0

        assert latence_moyenne_ms < 1.0, f"Latence trop élevée : {latence_moyenne_ms:.3f} ms >= 1.0 ms"

    def test_pipeline_traiter_e2e_sans_crash_sur_tous_les_cas(self, pipeline):
        """Vérifie que pipeline.traiter s'exécute sans aucun crash sur les cas extrêmes."""
        signal_silence = np.zeros(32000, dtype=np.float32)

        cas_tests = [
            ("Mon kpa est gâté, y'a pas drap sur le compteur", "fr"),
            ("Dama amul benn dërëm ci sama kuraŋ", "wo"),
            ("I ni sɔgɔma, n ka kuran juru banna", "dyu"),
            ("Aniho, min kouran wa wie sua'n nun", "bci"),
            ("Couper le courant immédiatement", "fr"),
            ("skzkxtrvm fgbhjkqlpm", "fr"),
            ("Oui", "fr"),
        ]

        for t, lg in cas_tests:
            res = pipeline.traiter(
                audio_input=signal_silence,
                transcription=t,
                forcer_actif=True,
            )
            assert isinstance(res, PipelineResult)
            assert res.statut in ("CONFIRME", "VALIDE", "ROLLBACK", "COMMANDE_CRITIQUE")
            assert res.action in ("CONTINUER", "ANNULER")
            assert res.latence_totale_ms > 0.0
