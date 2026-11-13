# Project: Audit Technique Approfondi et Benchmark Multilingue IA AOCEDA

## Architecture
- **Domaine d'évaluation :** Assistant IA vocal et multilingue d'AOCEDA (Django 6, Channels/Daphne, ONNX Runtime CPU, Faster-Whisper, Sherpa-ONNX, Cerebrium GPU).
- **Langues cibles :** Dioula (`dyu`), Baoulé (`bci`), Wolof (`wo`), Français véhiculaire (`fr`), Anglais (`en`).
- **Périmètre d'audit :**
  1. Reconnaissance vocale (STT) : Modèles CTC Omnilingual 1B, OmniASR 300M, Whisper Small Wolof ONNX, Whisper FR/EN.
  2. Synthèse vocale (TTS) : Edge-TTS / Kokoro FR, OmniVoice Baoulé GPU/local, Oolel-Voices Wolof GPU, Djelia Dioula.
  3. Détection de langue (LID) : Étage 1 Audio LID (ResAcousticNet INT8 ONNX) & Étage 2 Dictionnaire Lego (n-grammes) vs Pipeline Historique Multi-oreilles en streaming.
  4. Traduction automatique (MT) : Relais Djelia, Google Translate, NiuTrans, catalogues statiques et diagnostic formel de la dérive sémantique baoulé.
  5. Architecture, Wolof, Sécurité et Test Suites : Intégration wolof, quadruple barrière de coupure électrique, verrou RAM `VERROU_MODELE`, exécution pytest (837 tests) et Django test (467 tests), état de l'art Afrique de l'Ouest.
- **Répertoire des livrables finaux :** `docs/audits/` (`RAPPORT_STT.md`, `RAPPORT_TTS.md`, `RAPPORT_LID.md`, `RAPPORT_TRADUCTION.md`, `RAPPORT_ARCHITECTURE.md`, `SYNTHESE_GLOBALE.md`).

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | STT Transcription Chain Analysis | Analyse de la chaîne réelle (prétraitements, décodage glouton masqué latin, score sonore CTC forward, post-corrections) pour dyu, bci, wo, fr | M1 | ORIGINAL_REQUEST §R1 |
| F02 | STT Quantitative Benchmark | Mesure expérimentale du WER, CER et RTF par langue sur corpus réels ($n \ge 40$), avant et après post-corrections | M1 | ORIGINAL_REQUEST §R1 |
| F03 | STT Robustness Evaluation | Évaluation de la robustesse : bruit SNR 20/10/5 dB, téléphonie 8 kHz, silences, code-switching, montants et chiffres | M1 | ORIGINAL_REQUEST §R1 |
| F04 | STT Anti-Hallucination & Flaw Detection | Analyse des filtres anti-hallucination (`FANTOMES`, `_en_boucle`, `no_speech`), identification des failles fichier:ligne et propositions CPU (Silero VAD, Beam Search + LM) | M1 | ORIGINAL_REQUEST §R1 |
| F05 | TTS Synthesis Chain Analysis | Analyse des moteurs de synthèse vocale pour fr (Edge/Kokoro), bci (OmniVoice), wo (Oolel-Voices), dyu (Djelia) | M2 | ORIGINAL_REQUEST §R2 |
| F06 | TTS Text Normalization Benchmark | Évaluation de la normalisation sur banc de $\ge 50$ phrases pièges (nombres, montants FCFA, unités, dates, markdown, sigles) | M2 | ORIGINAL_REQUEST §R2 |
| F07 | TTS Intelligibility Loop (TTS->STT) | Mesure de l'intelligibilité par boucle audio TTS->STT (calcul du CER) sur les enregistrements existants | M2 | ORIGINAL_REQUEST §R2 |
| F08 | TTS Cerebrium Credit & Open Alternatives | Encadrement strict du solde Cerebrium $\ge 9\$$, identification de la faille de quota, et étude d'alternatives ouvertes CPU (MMS-TTS) | M2 | ORIGINAL_REQUEST §R2 |
| F09 | LID Pipeline Complete Audit | Audit du pipeline 2 étages (Étage 1 ResAcousticNet INT8 ONNX, Étage 2 Dictionnaire Lego sous-mots) vs Pipeline Historique Multi-oreilles | M3 | ORIGINAL_REQUEST §R3 |
| F10 | LID Confusion Matrix & Metrics | Matrice de confusion complète (fr, en, dyu, bci, wo, autre) sur corpus audio et texte réels avec précision, rappel, latence, abstention | M3 | ORIGINAL_REQUEST §R3 |
| F11 | LID Failure Analysis & CPU Proposals | Analyse des failles (langues proches bci/agni, code-switching, phrases courtes, bruit) et propositions CPU (MMS-LID, fusion CTC, vote hybride) | M3 | ORIGINAL_REQUEST §R3 |
| F12 | Machine Translation Chain Audit | Audit de la chaîne de traduction aller/retour pour dyu, bci, wo (relais Djelia, Google, NiuTrans, catalogues) | M4 | ORIGINAL_REQUEST §R4 |
| F13 | Baoulé Semantic Drift Diagnostic | Diagnostic approfondi et formalisation mathématique/linguistique de la dérive sémantique baoulé lors du cycle FR -> BCI -> FR | M4 | ORIGINAL_REQUEST §R4 |
| F14 | Translation Bench on 60+ Realistic Responses | Évaluation quantitative sur $\ge 60$ requêtes réalistes AOCEDA (mesures, facturation, coupures, négations, alertes) sans appel payant | M4 | ORIGINAL_REQUEST §R4 |
| F15 | Translation Solutions & Hardening | Conception de solutions pérennes : simplification contrôlée, réactivation des gabarits relus (`phrases_types_baoule.json`), masquage numérique `__NUM__` | M4 | ORIGINAL_REQUEST §R4 |
| F16 | Architecture & Wolof Code Review | Revue de code approfondie sur l'intégration du wolof (71 tests validés), portabilité, isolation et modularité | M5 | ORIGINAL_REQUEST §R5 |
| F17 | Power Cut Safeguards & RAM Lock Audit | Audit de la quadruple barrière de coupure (`AGENT.REFUS`, server-side `reponse_vocale_coupure`), et spécification du verrou atomique `VERROU_MODELE` | M5 | ORIGINAL_REQUEST §R5 |
| F18 | Test Suites Execution & Logging | Exécution et consignation intégrale des résultats de non-régression : `pytest` (837 tests) et `manage.py test` (467 tests) | M5 | ORIGINAL_REQUEST §R5 |
| F19 | SOTA West African Low-Resource AI | État de l'art documenté et sourcé (LID, ASR, MT, TTS pour dyu, bci, wo) et définition de la feuille de route cible priorisée | M5 | ORIGINAL_REQUEST §R5 |
| F20 | Global Synthesis & Executive Summaries | Rédaction du document maître de synthèse générale et des 5 résumés exécutifs $\le 60$ lignes consolidant les chiffres clés et les 10 failles majeures | M5 | ORIGINAL_REQUEST §R5 |
| F21 | Delivery & Integrity Verification | Contrôle d'intégrité strict : conformité des 6 rapports dans `docs/audits/`, respect de l'immutabilité du dépôt et de `D:`, zéro fuite d'API | E2E | ORIGINAL_REQUEST §R6 |

---

## Milestones

| # | Name | Scope | Dependencies | Status | Sub-Orchestrator ID |
|---|------|-------|-------------|--------|---------------------|
| **M1** | Audit & Benchmark STT | Features F01, F02, F03, F04. Mesure WER/CER/RTF sur $\ge 40$ items/langue, robustesse bruit/8kHz/silence/chiffres, identification failles fichier:ligne, propositions CPU. Livrable : `docs/audits/RAPPORT_STT.md`. | none | **DONE** | Livrable certifié (717 lignes) |
| **M2** | Audit & Benchmark TTS | Features F05, F06, F07, F08. Analyse Edge/Kokoro/OmniVoice/Oolel, normalisation 50+ phrases pièges, CER boucle TTS->STT, encadrement Cerebrium $\ge 9\$$, alternatives MMS-TTS. Livrable : `docs/audits/RAPPORT_TTS.md`. | none | **IN_PROGRESS** | `cb114d0c-cb2b-4079-9a33-55c802f210a6` |
| **M3** | Audit & Benchmark LID | Features F09, F10, F11. Audit 2 Étages vs Historique, matrice de confusion 6x6 audio/texte, précision/rappel/latence/abstention, analyse bci/agni et code-switching, architecture cible CPU. Livrable : `docs/audits/RAPPORT_LID.md`. | M1 | **IN_PROGRESS** | `119bb636-2d51-4929-ad68-e1cc7cbec4d5` |
| **M4** | Audit Traduction & Dérive Baoulé | Features F12, F13, F14, F15. Diagnostic formel dérive baoulé, banc $\ge 60$ réponses réalistes FR->BCI->FR (sens, chiffres, négations, alertes), validation gabarits et masquage placeholders. Livrable : `docs/audits/RAPPORT_TRADUCTION.md`. | none | **IN_PROGRESS** | `5bdf9c20-e48f-4bf9-82c2-035d983dfba6` |
| **M5** | Architecture, Tests & Synthèse Globale | Features F16, F17, F18, F19, F20. Revue wolof, quadruple barrière coupure, verrou RAM `VERROU_MODELE`, exécution 837 pytest + 467 Django tests, SOTA, document maître et résumés $\le 60$ lignes. Livrables : `docs/audits/RAPPORT_ARCHITECTURE.md` et `docs/audits/SYNTHESE_GLOBALE.md`. | M1, M2, M3, M4 | **PLANNED** | — |
| **E2E** | E2E Verification & Test Suite Ready | Feature F21. Validation formelle des 6 rapports dans `docs/audits/`, conformité aux 15 critères d'acceptation, vérification de non-régression et d'intégrité. Publication de `TEST_READY.md`. | M5 | **PLANNED** | — |

---

## Interface Contracts

### Contrat de Données et Corpus (M1 ↔ M3)
- **Corpus Dioula :** `D:/AOCEDA_CHATBOT/tests/bancs/stt_dioula/donnees/manifeste.json` (294 items avec transcriptions).
- **Corpus Non-Dioula :** `D:/AOCEDA_CHATBOT/tests/bancs/dioula_logique/donnees/non_dioula` (49 items bruit + langues étrangères).
- **Corpus Baoulé :** `D:/AOCEDA_CHATBOT/tests/bancs/baoule_logique/audio/manifeste.json` (295 items avec transcriptions).
- **Corpus Agni / Akan :** `D:/AOCEDA_IA_LAB/donnees/` (69 items pour test de confusion bci vs agni).
- **Corpus Wolof :** `lab_live/wolof_bench/catalogue_references.json` (55 items avec transcriptions et banc énergie).
- **Corpus Français :** `D:/AOCEDA_CHATBOT/tests/audios/questions` (V1-V9, X1, X2) et `tests/audios/live` (19 items).
- Format d'évaluation commun : échantillonnage 16 kHz mono, calcul CER/WER standardisé Levenshtein au niveau caractère et mot.

### Contrat de Normalisation & Placeholders (M2 ↔ M4)
- Normalisation numérique : Masquage des montants et chiffres par tokens neutres (`__NUM__`, `__PRIX_FCFA__`, `__DATE__`, `__COMPTEUR__`) avant soumission aux traducteurs, puis réinjection déterministe en post-traitement.
- Lexique métier garanti : Préservation des termes critiques (`kuran`, `fakitiri`, `kuraŋ bi`, `koppar`, `kura`, `alete`).

### Contrat de Sécurité & Encadrement Budgétaire (Transversal)
- **Interdiction absolue d'appels payants externes :** DeepSeek, Gemini, OpenRouter, NiuTrans interdits. Tout test doit être exécuté hors ligne ou sur les flux gratuits/simulés.
- **Règle Cerebrium :** Tout appel vers Cerebrium (voix baoulé ou wolof) doit obligatoirement vérifier au préalable que le solde `restant_usd >= 9.00 $`. En cas de solde indisponible ou $< 9.00 \$$, repli immédiat sur les audios pré-enregistrés dans `rapports/audios/` ou synthèse locale de secours.
- **Verrou mémoire atomique :** Utilisation systématique de `threading.Lock()` ou isolation de processus pour éviter le chargement simultané de plusieurs gros modèles (> 1 Go) en RAM.

---

## Code Layout

- **Code source de production (LECTURE SEULE STRICTE - Aucune modification autorisée) :**
  - Moteur Assistant IA : `AOCEDA/apps/ai_assistant/chatbot/`
  - Vues et URLs : `AOCEDA/apps/ai_assistant/views.py`, `urls.py`, `live.py`
  - Outils métier : `AOCEDA/apps/ai_assistant/outils.py`
  - Gabarits de données : `AOCEDA/apps/ai_assistant/chatbot/donnees/`
  - Pipeline 2 étages : `AOCEDA/apps/ai_assistant/chatbot/detection_deux_etages/`
  - Wolof bench : `AOCEDA/lab_live/wolof_bench/`
- **Documentation et Livrables d'Audit (ÉCRITURE AUTORISÉE EXCLUSIVEMENT ICI) :**
  - Dossier cible : `docs/audits/`
    - `RAPPORT_STT.md` (Livrable M1 - Terminé)
    - `RAPPORT_TTS.md` (Livrable M2 - Terminé, revue en cours)
    - `RAPPORT_LID.md` (Livrable M3 - En cours)
    - `RAPPORT_TRADUCTION.md` (Livrable M4 - Terminé, revue en cours)
    - `RAPPORT_ARCHITECTURE.md` (Livrable M5 - Prévu)
    - `SYNTHESE_GLOBALE.md` (Livrable Synthèse Consolidée M5 - Prévu)
- **Métadonnées de l'équipe (LECTURE/ÉCRITURE) :**
  - `.agents/teamwork/`
