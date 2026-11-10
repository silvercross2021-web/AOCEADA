"""Tests unitaires et banc de performance pour l'Étage 2 : Dictionnaire Lego & Garde-fou Rollback.

Vérifications requises (R2) :
  1. Benchmark de latence (< 1 ms par évaluation sur CPU standard, mesuré sur 100+ itérations).
  2. Précision de classification sur les 5 langues cibles (fr, en, wo, dyu, bci).
  3. Détection rigoureuse du charabia phonétique et des erreurs d'aiguillage acoustique (Rollback).
  4. Préservation absolue des commandes critiques de sécurité (couper, allumer, oui, non).
  5. Résolution des collisions lexicales sur les termes énergétiques partagés (kuran, courant).
  6. Tolérance aux codes de langue ISO (2 lettres et 3 lettres).
"""
import time
import pytest

from apps.ai_assistant.chatbot.detection_deux_etages.etage2_dictionnaire_lego import (
    ClassificateurLegoNgrammes,
    DecisionGardeFou,
    classifier_langue_lego,
    detecter_charabia,
    est_chaine_numerique_ou_sts,
    normaliser_code_langue,
    verifier_transcription_et_garde_fou,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalisation des codes de langues
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entree,attendu", [
    ("fr", "fr"),
    ("fra", "fr"),
    ("French", "fr"),
    ("en", "en"),
    ("eng", "en"),
    ("English", "en"),
    ("wo", "wo"),
    ("wol", "wo"),
    ("Wolof", "wo"),
    ("dyu", "dyu"),
    ("dioula", "dyu"),
    ("bam", "dyu"),
    ("bambara", "dyu"),
    ("bci", "bci"),
    ("baoule", "bci"),
    ("baoulé", "bci"),
    ("wawle", "bci"),
])
def test_normalisation_codes_langues(entree, attendu):
    assert normaliser_code_langue(entree) == attendu


# ─────────────────────────────────────────────────────────────────────────────
# 2. Précision de classification sur les 5 langues cibles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,langue_attendue", [
    # ── WOLOF ──
    ("nanga def sama xarit", "wo"),
    ("kuraŋ bi dafa fay", "wo"),
    ("dama bëgg xam sama koppar", "wo"),
    ("jerejef ci dimbal bi", "wo"),
    ("kuran bi dafay fay ci kër gi", "wo"),
    ("sama faktiir bi dafa cher", "wo"),
    ("waaw man dama bëgg fay kuraŋ", "wo"),
    ("déedéet duma sotti leegi", "wo"),

    # ── DIOULA / BAMBARA ──
    ("I ni sɔgɔma, n ka kuran juru banna", "dyu"),
    ("Ne b'a fɛ ka n' ka kuran recharger ni Wave ye", "dyu"),
    ("N' be se ka dɔ bɔ n' ka kuran fakitiri la cogo di ?", "dyu"),
    ("Kilowati lɛrɛ bi naani ni fila tora n fɛ", "dyu"),
    ("Aw ni baara, kuran juru bɛ se ka sara min ?", "dyu"),
    ("Ɔn ɔn, a to yen fɔlɔ", "dyu"),

    # ── BAOULÉ ──
    ("Aɲiho, min kuran'n w'a wie", "bci"),
    ("Sua'n nun kuran'n ti kekle kpa", "bci"),
    ("Min faktir'n nun ninnge'm suan", "bci"),
    ("Kɔnptɛr'n ti kekle kpa ɔ ?", "bci"),
    ("Arɛ o, sika ninnge'm su kɔ", "bci"),
    ("Manti, n bue wewa nun", "bci"),

    # ── FRANÇAIS ──
    ("Bonjour, quel est le solde de mon compteur électrique ?", "fr"),
    ("Comment je peux réduire ma facture d'électricité ce mois-ci ?", "fr"),
    ("Il y a eu une coupure de courant et le disjoncteur a sauté", "fr"),
    ("Mon climatiseur consomme beaucoup trop d'électricité", "fr"),
    ("Est-ce que je peux payer ma facture par Orange Money ?", "fr"),

    # ── ANGLAIS ──
    ("Good morning, how can I reduce my electricity bill?", "en"),
    ("There is a power outage in my neighborhood, the breaker tripped", "en"),
    ("How much credit is left on my electric meter?", "en"),
    ("My air conditioner power consumption is too high", "en"),
    ("Please tell me how to recharge my meter balance", "en"),
])
def test_classification_phrases_representatives(phrase, langue_attendue):
    langue_predite, score, scores_detailles = classifier_langue_lego(phrase)
    assert langue_predite == langue_attendue, f"Échec classification: '{phrase}' prédit '{langue_predite}' au lieu de '{langue_attendue}'"
    assert score >= 0.50, f"Confiance trop basse ({score}) pour '{phrase}'"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validation nominale de l'Étage 2 (ASR concordant)
# ─────────────────────────────────────────────────────────────────────────────

def test_validation_nominale_transcription_concordante():
    # Français
    dec_fr = verifier_transcription_et_garde_fou("Bonjour, je voudrais recharger mon compteur", "fr")
    assert dec_fr.statut in ("VALIDE", "CONFIRME")
    assert dec_fr.charabia is False
    assert dec_fr.action == "CONTINUER"
    assert dec_fr.recommencer_ecoute is False
    assert dec_fr.score_adequation >= 0.70

    # Wolof avec code ISO-3 "wol"
    dec_wo = verifier_transcription_et_garde_fou("nanga def, kuran bi dafa fay", "wol")
    assert dec_wo.statut in ("VALIDE", "CONFIRME")
    assert dec_wo.charabia is False
    assert dec_wo.action == "CONTINUER"
    assert dec_wo.recommencer_ecoute is False

    # Dioula avec code "dyu"
    dec_dyu = verifier_transcription_et_garde_fou("I ni sɔgɔma, n ka kuran juru banna", "dyu")
    assert dec_dyu.statut in ("VALIDE", "CONFIRME")
    assert dec_dyu.charabia is False
    assert dec_dyu.action == "CONTINUER"

    # Baoulé avec code "bci"
    dec_bci = verifier_transcription_et_garde_fou("Aɲiho, min kuran'n w'a wie", "bci")
    assert dec_bci.statut in ("VALIDE", "CONFIRME")
    assert dec_bci.charabia is False
    assert dec_bci.action == "CONTINUER"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Détection du Charabia Phonétique & Déclenchement du Rollback
# ─────────────────────────────────────────────────────────────────────────────

def test_interception_conflit_acoustique_wolof_vers_dioula():
    """Cas typique d'erreur de routage Étage 1 : un locuteur wolof est routé vers l'ASR dioula."""
    phrase_wolof_transcrite = "nanga def sama kuran bi dafa fay ci kër gi"
    decision = verifier_transcription_et_garde_fou(phrase_wolof_transcrite, langue_attendue="dyu")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True
    assert decision.langue_detectee == "wo"
    assert "Aiguillage acoustique erroné" in decision.explication or "Conflit" in decision.explication


def test_interception_conflit_acoustique_francais_vers_baoule():
    """Un locuteur français envoyé à tort vers l'ASR baoulé."""
    phrase_fr = "Bonjour monsieur comment je fais pour payer ma facture d'électricité"
    decision = verifier_transcription_et_garde_fou(phrase_fr, langue_attendue="bci")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True
    assert decision.langue_detectee == "fr"


def test_interception_charabia_boucle_hallucination_asr():
    """Détection de boucles d'hallucinations d'ASR (ex: 'to to to to to to')."""
    texte_boucle = "to to to to to to to to"
    decision = verifier_transcription_et_garde_fou(texte_boucle, langue_attendue="fr")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True
    assert "hallucination" in decision.explication.lower() or "charabia" in decision.explication.lower()


def test_interception_charabia_repetition_caracteres():
    """Répétition anormale de lettres consécutives."""
    texte_corrompu = "kredit aaaaaaaa faktir"
    decision = verifier_transcription_et_garde_fou(texte_corrompu, langue_attendue="bci")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True


def test_interception_amas_consonantique_impossible():
    """Amas de consonnes impossible en phonologie naturelle."""
    texte_bruit = "kuran zrktpmwfsx banna"
    decision = verifier_transcription_et_garde_fou(texte_bruit, langue_attendue="dyu")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True


def test_interception_texte_vide_ou_ponctuation_seule():
    """Entrées vides, bruitées ou uniquement ponctuées."""
    assert verifier_transcription_et_garde_fou("", "fr").statut == "ROLLBACK"
    assert verifier_transcription_et_garde_fou("   ", "wo").statut == "ROLLBACK"
    assert verifier_transcription_et_garde_fou("??? ... !!!", "dyu").statut == "ROLLBACK"


def test_interception_script_etranger_non_conforme():
    """Écritures non latines (ex. Cyrillique ou CJK) générées par accident."""
    texte_cyrillique = "Здравствуйте электричество"
    decision = verifier_transcription_et_garde_fou(texte_cyrillique, langue_attendue="fr")

    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Préservation des Commandes Critiques de Sécurité
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ordre,type_attendu", [
    ("couper le courant", "COUPER"),
    ("coupe", "COUPER"),
    ("éteins l'appareil", "COUPER"),
    ("turn off the power", "COUPER"),
    ("fay ko", "COUPER"),
    ("a tigɛ", "COUPER"),
    ("kpe nun", "COUPER"),
    ("allumer le compteur", "ALLUMER"),
    ("taal ko", "ALLUMER"),
    ("a mɛnɛ", "ALLUMER"),
    ("oui", "OUI"),
    ("yes", "OUI"),
    ("waaw", "OUI"),
    ("awɔ", "OUI"),
    ("non", "NON"),
    ("no", "NON"),
    ("déedéet", "NON"),
    ("ɔn ɔn", "NON"),
])
def test_preservation_commandes_critiques(ordre, type_attendu):
    decision = verifier_transcription_et_garde_fou(ordre, langue_attendue="fr")
    assert decision.statut == "COMMANDE_CRITIQUE"
    assert decision.charabia is False
    assert decision.action == "CONTINUER"
    assert decision.commande_critique == type_attendu


# ─────────────────────────────────────────────────────────────────────────────
# 6. Résolution des collisions lexicales (terme 'kuran' partagé)
# ─────────────────────────────────────────────────────────────────────────────

def test_desambiguisation_collision_kuran():
    """Le lemme 'kuran' existe en Wolof, Dioula et Baoulé.

    Les briques syntaxiques environnantes doivent lever l'ambiguïté sans collision bloquante.
    """
    # Cas Wolof : classificateur post-posé "bi" ou marqueur "dafa"
    lg_wo, _, _ = classifier_langue_lego("kuran bi dafa fay")
    assert lg_wo == "wo"

    # Cas Dioula : syntagme verbal "juru banna"
    lg_dyu, _, _ = classifier_langue_lego("kuran juru banna")
    assert lg_dyu == "dyu"

    # Cas Baoulé : article défini apostrophé "kuran'n" ou prédicat "w'a wie"
    lg_bci, _, _ = classifier_langue_lego("min kuran'n w'a wie")
    assert lg_bci == "bci"

    # Cas Français : article défini français "le courant"
    lg_fr, _, _ = classifier_langue_lego("le courant est coupé")
    assert lg_fr == "fr"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Benchmark de Latence CPU (< 1 ms par évaluation sur 100+ itérations)
# ─────────────────────────────────────────────────────────────────────────────

def test_benchmark_latence_sub_milliseconde():
    phrases_echantillons = [
        "nanga def sama kuran bi dafa fay ci kër gi",
        "I ni sɔgɔma, n ka kuran juru banna ne b'a fɛ ka recharger",
        "Aɲiho, min kuran'n w'a wie sua'n nun ti kekle",
        "Bonjour, je voudrais connaître la consommation de mon climatiseur",
        "Hello, can you help me check my electricity meter balance please",
        "couper le courant",
        "to to to to to to to to",
    ]

    nb_iterations = 350
    t_debut = time.perf_counter()

    for i in range(nb_iterations):
        phrase = phrases_echantillons[i % len(phrases_echantillons)]
        _ = verifier_transcription_et_garde_fou(phrase, langue_attendue="fr")

    duree_totale_s = time.perf_counter() - t_debut
    latence_moyenne_ms = (duree_totale_s / nb_iterations) * 1000.0

    print(f"\n[BENCHMARK ÉTAGE 2] {nb_iterations} évaluations exécutées en {duree_totale_s:.4f} s.")
    print(f"[BENCHMARK ÉTAGE 2] Latence moyenne par évaluation : {latence_moyenne_ms:.4f} ms.")

    # La latence doit impérativement être inférieure à 1.0 ms (cible ~0.1 - 0.5 ms)
    assert latence_moyenne_ms < 1.0, f"Dépassement du seuil de latence : {latence_moyenne_ms:.3f} ms >= 1.0 ms"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tests des cas limites : Ponctuation et Répétitions d'Urgence
# ─────────────────────────────────────────────────────────────────────────────

def test_ponctuation_et_points_suspension_non_charabia():
    """Vérifie que des points de suspension en fin de mot ne sont pas faussement pris pour un amas consonantique."""
    res_fr = verifier_transcription_et_garde_fou("Mon courant....", "fr")
    assert res_fr.charabia is False
    assert res_fr.statut in ("VALIDE", "CONFIRME")
    assert res_fr.action == "CONTINUER"

    res_en = verifier_transcription_et_garde_fou("What is the bill....", "en")
    assert res_en.charabia is False
    assert res_en.action == "CONTINUER"


def test_commandes_urgence_multiples_non_bloquees_par_hallucination():
    """Vérifie qu'un ordre d'urgence répété ('coupe coupe coupe coupe') n'est pas bloqué par le filtre d'hallucination."""
    res = verifier_transcription_et_garde_fou("coupe coupe coupe coupe", "fr")
    assert res.statut == "COMMANDE_CRITIQUE"
    assert res.commande_critique == "COUPER"
    assert res.action == "CONTINUER"
    assert res.charabia is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. Audit & Hardening M2 : Symétrie Zéro-Évidence (Élimination du Biais FR)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lg", ["fr", "en", "wo", "dyu", "bci"])
def test_symetrie_zero_evidence_texte_neutre(lg):
    """Vérifie le traitement symétrique d'un texte sans signal (score max <= 0.22).

    Aucune langue (en particulier 'fr') ne doit être indûment validée sans preuve.
    """
    texte_neutre = "xyzqwk pmwtlk"
    langue_pred, conf, scores = classifier_langue_lego(texte_neutre)
    assert langue_pred == "inconnue"
    assert conf <= 0.22

    decision = verifier_transcription_et_garde_fou(texte_neutre, langue_attendue=lg)
    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"
    assert decision.recommencer_ecoute is True
    assert decision.langue_detectee == "inconnue"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Audit & Hardening M2 : Intégration des Nombres et Cardinaux dans les 5 Langues
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,langue_attendue", [
    # Français
    ("cinq mille", "fr"),
    ("deux cent cinquante", "fr"),
    ("trois", "fr"),
    # Anglais
    ("five thousand", "en"),
    ("twenty hundred", "en"),
    ("three", "en"),
    # Wolof
    ("benn kuraŋ", "wo"),
    ("ñaar fukk", "wo"),
    ("juróom benn", "wo"),
    # Dioula
    ("kelen saba", "dyu"),
    ("fila tan", "dyu"),
    ("kɛmɛ mugan", "dyu"),
    # Baoulé
    ("kun nnyɔn", "bci"),
    ("nsan blu", "bci"),
    ("nnan ya", "bci"),
])
def test_reconnaissance_cardinaux_5_langues(phrase, langue_attendue):
    """Vérifie la reconnaissance des nombres et cardinaux usuels dans les 5 langues."""
    langue_predite, score, _ = classifier_langue_lego(phrase)
    assert langue_predite == langue_attendue
    assert score >= 0.40


# ─────────────────────────────────────────────────────────────────────────────
# 11. Audit & Hardening M2 : Chaînes Numériques et Codes Compteurs STS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", [
    "0421 8952 1478 2365 9812",
    "04218952147823659812",
    "0421-8952-1478-2365-9812",
    "code 0421 8952 1478 2365 9812",
    "token 0421 8952 1478 2365 9812",
    "5000",
    "20 000",
    "14253678901",
])
@pytest.mark.parametrize("lg", ["fr", "en", "wo", "dyu", "bci"])
def test_chaine_numerique_et_token_sts_compteur(token, lg):
    """Vérifie que les codes STS de 20 chiffres, numéros de compteur et montants

    sont acceptés sans déclencher de rollback intempestif, pour les 5 langues.
    """
    decision = verifier_transcription_et_garde_fou(token, langue_attendue=lg)
    assert decision.statut in ("VALIDE", "CONFIRME")
    assert decision.charabia is False
    assert decision.action == "CONTINUER"
    assert decision.recommencer_ecoute is False


# ─────────────────────────────────────────────────────────────────────────────
# 12. Audit & Hardening M2 : Exemption Phonotactique Anglaise (5 Consonnes)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "What are the strengths of this solar meter ?",
    "Please measure the lengths of the cable",
    "It represents two twelfths of my bill",
    "strengths and lengths",
])
def test_exemption_phonotactique_mots_anglais(phrase):
    """Vérifie que strengths, lengths, twelfths ne déclenchent aucun faux rollback en anglais."""
    est_ch, raison = detecter_charabia(phrase)
    assert est_ch is False, f"Faux positif charabia sur '{phrase}': {raison}"

    decision = verifier_transcription_et_garde_fou(phrase, langue_attendue="en")
    assert decision.statut in ("VALIDE", "CONFIRME")
    assert decision.charabia is False
    assert decision.action == "CONTINUER"
    assert decision.recommencer_ecoute is False


def test_charabia_consonantique_reel_toujours_intercepte():
    """Vérifie qu'un véritable amas de consonnes incohérent reste intercepté."""
    est_ch, raison = detecter_charabia("kuran zrktpmwfsx banna")
    assert est_ch is True
    assert "Amas consonantique" in raison


# ─────────────────────────────────────────────────────────────────────────────
# 13. Audit & Hardening M2 : Interception des Scripts Non Autorisés Élargis
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texte_exotique,script_nom", [
    ("Ελληνικά ρεύμα διακοπή", "Grec"),
    ("ไฟฟ้าดับช่วยด้วย", "Thaï"),
    ("הפסקת חשמל בבית", "Hébreu"),
    ("बिजली का बिल कैसे भरें", "Devanagari"),
])
def test_interception_scripts_exotiques(texte_exotique, script_nom):
    """Vérifie l'interception systématique des écritures non autorisées (grec, thaï, hébreu, devanagari)."""
    est_ch, raison = detecter_charabia(texte_exotique)
    assert est_ch is True
    assert "non autorisés" in raison

    for lg in ["fr", "en", "wo", "dyu", "bci"]:
        decision = verifier_transcription_et_garde_fou(texte_exotique, langue_attendue=lg)
        assert decision.statut == "ROLLBACK"
        assert decision.charabia is True
        assert decision.action == "ANNULER"
        assert decision.recommencer_ecoute is True


# ─────────────────────────────────────────────────────────────────────────────
# 14. Audit & Hardening M2 : Sécurisation des Ordres d'Urgence face à la Négation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase_negative", [
    # Français
    "coupe pas le courant",
    "ne coupe pas",
    "ne coupe pas le compteur",
    "coupe surtout pas",
    "éteins pas l'appareil",
    "ne pas couper",
    # Anglais
    "don't cut",
    "dont cut",
    "do not cut",
    "never turn off",
    "don't turn off the power",
    # Wolof
    "bul fay",
    # Dioula
    "kana tige",
])
def test_securisation_ordres_urgence_negation(phrase_negative):
    """Vérifie formellement qu'un ordre d'action avec négation n'est JAMAIS interprété comme COUPER."""
    clf = ClassificateurLegoNgrammes()
    cmd = clf.detecter_commande_critique(phrase_negative)
    assert cmd is None or cmd[0] not in ("COUPER", "ALLUMER"), f"Faux ordre critique sur '{phrase_negative}': {cmd}"

    # Vérification que le garde-fou ne génère pas de commande critique COUPER
    lg = "fr" if any(w in phrase_negative for w in ["coupe", "éteins"]) else "en" if any(w in phrase_negative for w in ["cut", "turn"]) else "wo" if "fay" in phrase_negative else "dyu"
    decision = verifier_transcription_et_garde_fou(phrase_negative, langue_attendue=lg)
    assert decision.commande_critique is None or decision.commande_critique not in ("COUPER", "ALLUMER")
    assert decision.statut != "COMMANDE_CRITIQUE"


@pytest.mark.parametrize("phrase_positive,cmd_attendu", [
    ("coupe le courant", "COUPER"),
    ("coupe", "COUPER"),
    ("turn off", "COUPER"),
    ("fay ko", "COUPER"),
    ("a tige", "COUPER"),
    ("taal ko", "ALLUMER"),
    ("allumer le compteur", "ALLUMER"),
])
def test_ordres_urgence_positifs_toujours_reconnus(phrase_positive, cmd_attendu):
    """Vérifie que les ordres légitimes sans négation restent reconnus à 100%."""
    clf = ClassificateurLegoNgrammes()
    cmd = clf.detecter_commande_critique(phrase_positive)
    assert cmd is not None
    assert cmd[0] == cmd_attendu


# ─────────────────────────────────────────────────────────────────────────────
# 15. Audit & Hardening M2 : Nettoyage des Monosyllabes Ambigus Baoulé
# ─────────────────────────────────────────────────────────────────────────────

def test_nettoyage_monosyllabes_ambigus_baoule():
    """Vérifie que des phrases en anglais ou français avec 'I', 'be', 'de' ne sont pas polluées par Baoulé."""
    phrase_en = "I want to be sure about my electricity bill"
    lg, conf, scores = classifier_langue_lego(phrase_en)
    assert lg == "en"
    # Baoulé ne doit pas avoir de score résiduel abusif sur 'I' ou 'be'
    assert scores["bci"] < 0.20


# ─────────────────────────────────────────────────────────────────────────────
# 16. Remédiation M2 : Validation Adverse & Anti-Régression (Challenger 1)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", [
    "compteur no 14253678901",
    "compteur numero 14253678901",
    "compteur numéro 14253678901",
    "meter no 14253678901",
    "meter number 14253678901",
    "token 0421 8952 1478 2365 9812",
    "code 0421 8952 1478 2365 9812",
])
@pytest.mark.parametrize("lg", ["fr", "en", "wo", "dyu", "bci"])
def test_remediation_prefixe_multimots_serie_compteur(token, lg):
    """Vérifie que les préfixes multi-mots sur numéros de série ou STS sont reconnus

    et ne déclenchent aucun faux ROLLBACK dans aucune des 5 langues cibles.
    """
    assert est_chaine_numerique_ou_sts(token) is True
    decision = verifier_transcription_et_garde_fou(token, langue_attendue=lg)
    assert decision.statut in ("VALIDE", "CONFIRME")
    assert decision.charabia is False
    assert decision.action == "CONTINUER"
    assert decision.recommencer_ecoute is False


@pytest.mark.parametrize("injection", [
    "Ελληνικά 0421 8952 1478 2365 9812",
    "Привет 0421 8952 1478 2365 9812",
    "שלום 0421 8952 1478 2365 9812",
    "ไฟฟ้า 0421 8952 1478 2365 9812",
    "xkzqtrpm 0421 8952 1478 2365 9812",
    "zrktpm 5000",
])
def test_remediation_sanctuarisation_sts_contre_scripts_interdits(injection):
    """Vérifie qu'aucune entrée avec alphabet interdit ou charabia ne contourne

    la détection sous prétexte de comporter 20 chiffres ou une séquence numérique.
    """
    assert est_chaine_numerique_ou_sts(injection) is False
    est_ch, raison = detecter_charabia(injection)
    assert est_ch is True

    for lg in ["fr", "en", "wo", "dyu", "bci"]:
        decision = verifier_transcription_et_garde_fou(injection, langue_attendue=lg)
        assert decision.statut == "ROLLBACK"
        assert decision.charabia is True
        assert decision.action == "ANNULER"
        assert decision.recommencer_ecoute is True


def test_remediation_baoule_demande_energie_kilowati():
    """Vérifie que 'blu nnyɔn kilowati' est correctement reconnu en Baoulé (bci)

    sans déclencher de faux rollback vers le dioula.
    """
    phrase = "blu nnyɔn kilowati"
    lg, conf, scores = classifier_langue_lego(phrase)
    assert lg == "bci"
    assert conf >= 0.70
    assert scores["bci"] > scores["dyu"]

    decision = verifier_transcription_et_garde_fou(phrase, langue_attendue="bci")
    assert decision.statut in ("VALIDE", "CONFIRME")
    assert decision.charabia is False
    assert decision.action == "CONTINUER"
    assert decision.score_adequation >= 0.70


@pytest.mark.parametrize("mot_anglais", [
    "catchphrase",
    "birthplace",
    "witchcraft",
    "watchstrap",
])
def test_remediation_mots_composes_anglais_exemptes(mot_anglais):
    """Vérifie que les mots composés anglais comportant 5 consonnes consécutives

    sont proprement exemptés de la violation phonotactique.
    """
    est_ch, raison = detecter_charabia(mot_anglais)
    assert est_ch is False, f"Faux positif sur '{mot_anglais}': {raison}"

    decision = verifier_transcription_et_garde_fou(mot_anglais, langue_attendue="en")
    assert decision.charabia is False
    assert decision.action == "CONTINUER"


def test_remediation_charabia_sans_voyelles_avec_y():
    """Vérifie que les séquences consonantiques de type keyboard mash contenant 'y'

    comme 'qwrtyp' sont interceptées comme charabia et déclenchent un ROLLBACK.
    """
    est_ch, raison = detecter_charabia("qwrtyp")
    assert est_ch is True

    decision = verifier_transcription_et_garde_fou("qwrtyp", langue_attendue="en")
    assert decision.statut == "ROLLBACK"
    assert decision.charabia is True
    assert decision.action == "ANNULER"



