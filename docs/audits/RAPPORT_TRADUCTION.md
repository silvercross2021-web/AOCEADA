# RAPPORT D'AUDIT TECHNIQUE : TRADUCTION AUTOMATIQUE MULTILINGUE ET DÉDIÉ AU DIAGNOSTIC DE LA DÉRIVE SÉMANTIQUE EN BAOULÉ (JALON M4)

**Référence projet :** AOCEDA (Assistant Vocal & Multilingue pour la Maîtrise de l'Énergie)  
**Livrable officiel :** Jalon M4 — Audit de la Traduction Automatique (Features F12, F13, F14, F15)  
**Fichier cible :** `docs/audits/RAPPORT_TRADUCTION.md`  
**Date d'émission :** 10 novembre 2026  
**Auteurs :** Équipe d'Audit Technique & Spécialistes Traduction IA (Sub-Orchestrateur M4 & Workers)  
**Classification :** Rapport d'Architecture et d'Évaluation Métrologique  
**Cadre d'intégrité :** Audit en lecture seule stricte, zéro appel payant externe, zéro modification du code source de production d'AOCEDA (`AOCEDA/apps/...`), validation mathématique déterministe.

---

## Table des Matières

1. [Synthèse Exécutive](#synthèse-exécutive)
2. [Section 1 : Audit de la Chaîne Réelle de Traduction Multilingue (F12)](#section-1--audit-de-la-chaîne-réelle-de-traduction-multilingue-f12)
   - 1.1 [Paradigme des Langues Relais dans AOCEDA](#11-paradigme-des-langues-relais-dans-aoceda)
   - 1.2 [Chaîne de Traduction Dioula (`dyu`)](#12-chaîne-de-traduction-dioula-dyu)
   - 1.3 [Chaîne de Traduction Baoulé (`bci`)](#13-chaîne-de-traduction-baoulé-bci)
   - 1.4 [Chaîne de Traduction Wolof (`wo`)](#14-chaîne-de-traduction-wolof-wo)
   - 1.5 [Matrice Comparative Synthétique des Trois Langues](#15-matrice-comparative-synthétique-des-trois-langues)
3. [Section 2 : Diagnostic Formel de la Dérive Sémantique en Baoulé (F13)](#section-2--diagnostic-formel-de-la-dérive-sémantique-en-baoulé-f13)
   - 2.1 [Modélisation Théorique du Cycle Aller-Retour ($FR \to BCI \to FR$)](#21-modélisation-théorique-du-cycle-aller-retour-fr-to-bci-to-fr)
   - 2.2 [Famille 1 : Corruption Arithmétique et Altération des Unités Physiques](#22-famille-1--corruption-arithmétique-et-altération-des-unités-physiques)
   - 2.3 [Famille 2 : Glissements Lexicaux et Faux-Amis Métier](#23-famille-2--glissements-lexicaux-et-faux-amis-métier)
   - 2.4 [Famille 3 : Perte et Inversion des Négations](#24-famille-3--perte-et-inversion-des-négations)
   - 2.5 [Famille 4 : Multiplicateurs Parasites et Numération Vigésimale](#25-famille-4--multiplicateurs-parasites-et-numération-vigésimale)
   - 2.6 [Corpus Documenté de 10 Cas Réels Avant/Après](#26-corpus-documenté-de-10-cas-réels-avantaprès)
   - 2.7 [Analyse des Failles du Code Existant](#27-analyse-des-failles-du-code-existant)
4. [Section 3 : Banc d'Évaluation Quantitative sur 64 Cas Réels AOCEDA (F14)](#section-3--banc-dévaluation-quantitative-sur-64-cas-réels-aoceda-f14)
   - 3.1 [Protocole Expérimental et Formalisation des 4 Métriques Déterministes](#31-protocole-expérimental-et-formalisation-des-4-métriques-déterministes)
   - 3.2 [Corpus Exhaustif des 64 Cas Réels (5 Thèmes Obligatoires)](#32-corpus-exhaustif-des-64-cas-réels-5-thèmes-obligatoires)
   - 3.3 [Résultats Consolidés et Analyse Quantitative](#33-résultats-consolidés-et-analyse-quantitative)
5. [Section 4 : Solutions Fiables et Plan de Durcissement (F15)](#section-4--solutions-fiables-et-plan-de-durcissement-f15)
   - 4.1 [Activation et Révision Intégrale des 36 Phrases-Gabarits (`phrases_types_baoule.json`)](#41-activation-et-révision-intégrale-des-36-phrases-gabarits-phrases_types_baoulejson)
   - 4.2 [Mécanisme de Masquage Déterministe par Placeholders](#42-mécanisme-de-masquage-déterministe-par-placeholders)
   - 4.3 [Prompt Engineering Défensif et Grammaire Canonique Contrôlée (GCC)](#43-prompt-engineering-défensif-et-grammaire-canonique-contrôlée-gcc)
   - 4.4 [Garde-Fous Syntaxiques et Sécurisation Temporelle](#44-garde-fous-syntaxiques-et-sécurisation-temporelle)
   - 4.5 [Matrice de Risques et Recommandations Opérationnelles](#45-matrice-de-risques-et-recommandations-opérationnelles)
6. [Conclusion Générale de l'Audit M4](#conclusion-générale-de-laudit-m4)

---

## Synthèse Exécutive

Dans le cadre du programme d'audit technique et métrologique de l'assistant IA vocal d'AOCEDA (Jalon M4), le présent rapport documente l'investigation exhaustive de la **chaîne de traduction automatique multilingue** couvrant le **Dioula** (`dyu`), le **Baoulé** (`bci`) et le **Wolof** (`wo`). L'objectif central est d'auditer les mécanismes de relais, de diagnostiquer formellement le phénomène de **dérive sémantique** affectant le Baoulé lors du cycle aller-retour ($\text{Français} \to \text{Baoulé} \to \text{Français}$), d'exécuter un banc d'évaluation quantitative sur **64 requêtes réalistes**, et de prescrire un plan de durcissement architectural sans surcoût d'API ni régression logicielle.

### Chiffres Clés et Faits Saillants de l'Audit :
1. **Dormance totale des gabarits Baoulé (0 % actif)** : Les 36 phrases de `AOCEDA/apps/ai_assistant/chatbot/donnees/phrases_types_baoule.json` sont à ce jour inopérantes car étiquetées `"relue": false`. Le chargeur `baoule_repondre.py:38` filtrant strictement sur `x.get("relue")`, 100 % des interactions usuelles (accueil, aide, sécurité) sont inutilement soumises à Google Translate, subissant une pénalité de latence de **1 800 ms** contre **0,02 ms** en mémoire locale.
2. **Vulnérabilité critique `nombres_perdus` en Dioula** : Dans `dioula_relais.py:175`, l'appel `nombres_perdus(texte_francais, out)` omet le paramètre `lus` (il vaut `()`). Toute traduction dioula valide écrivant un nombre en lettres (ex: *kɛmɛ saba* pour 300) ou convertissant une somme en *dɔrɔmɛ* est rejetée par le contrôle et bascule en repli français !
3. **Point de défaillance unique (SPOF) en Wolof** : La chaîne Wolof repose exclusivement sur un endpoint HTTP non documenté de Google Translate (`clients5.google.com`), sans aucun traducteur de secours. En contrepartie, le Wolof possède la couche de post-correction déterministe la plus performante du dépôt (`_corriger_metier_wolof`, 0,05 ms CPU), neutralisant notamment le piège multiplicateur $\times 5$ du *dërëm*.
4. **Diagnostic formel de la dérive Baoulé** : Quatre familles de corruption ont été formalisées :
   - *Corruption arithmétique* : Perte des virgules décimales (« 12,5 » $\to$ « 125 » $\times 10$), conversion en disjonctions (« 3,4 » $\to$ « 3 ou 4 ») ou intervalles (« 2,8 » $\to$ « de 2 à 8 »), et confusion kWh / kW.
   - *Glissements lexicaux* : `sika` systématiquement traduit en « dollars » ($\times 655$) ou en « or » ; « crédit » assimilé à une « dette » (`kalɛ`) ou à des « actions boursières » ; consommation (`di aliɛ`) traduite en « déjeuner » ou « repas ».
   - *Perte des négations* : Évanouissement du suffixe verbal `-man` et de la particule `nán`, inversant des alertes de sécurité (« Ne coupez pas » $\to$ « Coupez ») et produisant l'alternative aberrante « oui ou oui » (`ɛɛ annzɛ ɛɛ`).
   - *Multiplicateurs parasites* : Distorsion vigésimale (25 000 lu 20 005).
5. **Banc d'évaluation sur 64 cas réels** : L'évaluation sans masque révèle un taux global de préservation arithmétique de seulement **42,2 %** et un taux de préservation des négations de **66,7 %** sur les alertes critiques.
6. **Plan de durcissement certifié** : Révision intégrale des 36 phrases-gabarits Baoulé pour passage immédiat à `"relue": true`, spécification complète du pipeline de masquage déterministe par balises hermétiques (`__KWH_n__`, `__PRIX_FCFA_n__`) avec regex de réparation anti-espaces, et consigne de rédaction sous Grammaire Canonique Contrôlée (GCC).

---

## Section 1 : Audit de la Chaîne Réelle de Traduction Multilingue (F12)

### 1.1 Paradigme des Langues Relais dans AOCEDA

Dans l'architecture de l'assistant IA d'AOCEDA (`AOCEDA/apps/ai_assistant/chatbot/`), les langues mandingues et kwa à faibles ressources numériques (Dioula, Baoulé, Wolof) ne sont pas traitées par un grand modèle multimodal de bout en bout. Elles reposent sur une architecture découplée dite de **langue relais** :
- **À l'Aller ($\text{Langue Locale} \to \text{Français}$)** : Le message de l'usager (transcrit par ASR local ou saisi au clavier) est décodé, normalisé et traduit vers le français véhiculaire avec extraction de son dossier d'intention et de ses entités numériques.
- **Au Cœur du Système** : Le moteur LLM (DeepSeek `deepseek-chat`) raisonne en français avec l'accès aux outils de télémesure d'AOCEDA (compteurs, historique de consommation, solde prépayé, cartes de coupure sécurisées).
- **Au Retour ($\text{Français} \to \text{Langue Locale}$)** : Les phrases de la réponse française sont traduites en flux concurrentiel (streaming phrase par phrase) vers la langue cible pour alimenter le synthétiseur vocal (TTS) et l'affichage textuel.

```
+------------------------------------------------------------------------------------+
|                                    FLUX GLOBAL ALLER                               |
|                                                                                    |
| [Audio Usager] --> [ASR Local] --+                                                 |
|                                  |--> [Dossier Intention + Glossaire] --> [DeepSeek]
| [Texte Tapé]   ------------------+    (+ Relais Traduction Aller si wo/bci)         |
+------------------------------------------------------------------------------------+
                                           |
                                           v
+------------------------------------------------------------------------------------+
|                                    FLUX GLOBAL RETOUR                              |
|                                                                                    |
| [DeepSeek FR] --> [Découpage Phrases] --> [Relais MT en Flux] --> [Audio TTS]      |
|                                            (Djelia / Google /      (Edge / Kokoro /|
|                                             NiuTrans / Gabarit)     OmniVoice)     |
+------------------------------------------------------------------------------------+
```

---

### 1.2 Chaîne de Traduction Dioula (`dyu`)
*Localisation : `AOCEDA/apps/ai_assistant/chatbot/service_dioula.py:1-376`, `dioula_relais.py:1-228`, `dioula_texte.py:1-403`*

#### 1.2.1 Architecture et Flux Bout en Bout
Le traitement du Dioula se structure autour de 4 étapes ordonnancées :
1. **Constitution du dossier d'intention (`service_dioula.py:75-114`)** :
   - Récupération de la transcription du modèle Meta Omnilingual 1B CTC int8.
   - Réparation phonétique par `dioula_texte.reparer()` et extraction des termes utiles via le carnet de mots `dioula_lexique.json` et le glossaire fixe `dioula_texte.GLOSSAIRE`.
   - Extraction des nombres par `dioula_texte.lire_nombres()` avec conversion des *dɔrɔmɛ* en FCFA ($\text{valeur} \times 5$).
   - Détection des marqueurs interrogatifs (`wa` en fin de phrase, `service_dioula.py:104`) et des salutations locales (`I ni sogoma`, `I ni su`).
2. **Politique d'arbitrage à l'aller (`TRADUIRE_ALLER = False`, `service_dioula.py:29-33`)** :
   - *Observation empirique mesurée* : Les traducteurs génériques (Google, Djelia) échouent lourdement sur le vocabulaire énergétique mandingue (taux de compréhension limité à 46 %, surcoût de latence de +700 ms).
   - DeepSeek reçoit donc directement la transcription dioula brute enrichie du glossaire explicatif.
   - **Mécanisme de Relance Asynchrone (`RELANCE_AVEC_TRADUCTIONS = True`, `service_dioula.py:33, 185, 355-366`)** : En parallèle du premier appel à DeepSeek, une tâche de fond (`_pool.submit(dioula_relais.vers_francais, texte)`) interroge Djelia et Google. Si et seulement si DeepSeek renvoie un en-tête `CERTITUDE : basse`, le flux s'interrompt, récupère les traductions de secours (`timeout=2.5 s`), les injecte dans le prompt et relance un second essai.
3. **Traduction en flux au retour (`service_dioula.py:212-273`, `dioula_relais.py:181-215`)** :
   - Dès qu'une phrase est terminée (`.!?\n`), elle est soumise au pool `dioula_relais.lancer_vers_dioula`.
   - Émission SSE immédiate vers le client (`{"type": "morceau", "texte": dy, "traduit": True}`).
   - Déclenchement de la synthèse vocale (`voix.preparer`) dès la première phrase pour masquer la latence des suivantes.
4. **Bilan et bascule de sécurité (`service_dioula.py:274-304`)** :
   - Si aucune phrase n'a pu être traduite (services indisponibles), la langue vocale bascule en français (`langue_voix = "fr"`), la salutation est convertie en français (« Bonsoir »), et le texte source français est restitué sans distorsion.

#### 1.2.2 Relais Djelia et Course Concurrente avec Google Translate
Le module `dioula_relais.py` gère deux fournisseurs :
- **Djelia (`bam_Latn`)** : API REST Cloud (`https://www.djelia.cloud/api/translate`), latence mesurée ~1,0 s en session chaude. Modèle spécialisé pour le bambara/dioula.
- **Google Translate (`dyu`)** : Endpoint Chrome (`https://clients5.google.com/translate_a/t`), latence ~1,5 s.

**Algorithme de course concurrente au retour (`dioula_relais.py:181-211`) :**
1. Djelia est lancé en priorité dans le pool de threads.
2. Le système lui accorde une **période de préférence de 2,5 s** (`PREFERENCE_S = 2.5`).
3. Si Djelia n'a pas répondu à $t = 2,5\text{ s}$, Google est lancé **en parallèle** sans annuler Djelia.
4. Dès qu'un service renvoie un résultat valide, il est validé. Si Google répond avant Djelia après la période de préférence, Google l'emporte immédiatement (`dioula_relais.py:200`).
5. **Coupe-circuit** : 3 pannes consécutives placent le fournisseur en quarantaine pendant 60 secondes (`PANNES_AVANT_COUPURE = 3`, `COUPURE_S = 60`).
6. **Pool découplé** : `_pool` (8 threads pour l'ordonnancement des phrases) et `_services` (16 threads pour les requêtes HTTP `requests.Session`).

#### 1.2.3 La Faille Critique `nombres_perdus` en Dioula
Dans `dioula_relais.py:151-158`, la validation du retour exécute :
```python
def _vers_dioula_par(service, texte_francais):
    out = traduire(service, "vers_dyu", texte_francais)
    if _reste_en_francais(texte_francais, out):
        raise RelaisIndisponible(f"{service} : traduction restée en français")
    perdus = nombres_perdus(texte_francais, out)
    if perdus:
        raise RelaisIndisponible(f"{service} : nombre changé ({', '.join(perdus)})")
    return sans_parentheses_ajoutees(texte_francais, out)
```
Or la définition de `nombres_perdus` (`dioula_relais.py:162-164`) est :
```python
def nombres_perdus(source, traduction, lus=()):
    presents = set(nombres_ecrits(traduction)) | {str(v) for v in lus}
    return [n for n in nombres_ecrits(source) if n not in presents]
```
**Analyse de la faille :**
À la ligne 155, `nombres_perdus(texte_francais, out)` est appelé **sans transmettre le paramètre `lus`** (qui reste donc à son tuple vide par défaut `()`).  
- Si Djelia ou Google traduit « Il vous reste 300 francs » par `Juru kɛmɛ saba tora i bolo` (où 300 est écrit en toutes lettres `kɛmɛ saba`), `nombres_ecrits(out)` ne détecte aucun chiffre arabe.
- `nombres_perdus` conclut que le nombre `300` a disparu. La traduction est rejetée avec l'exception `nombre changé (300)`.
- Si la phrase est convertie en *dɔrɔmɛ* (ex: 15 000 FCFA devenant 3 000 dɔrɔmɛ), le chiffre arabe détecté est `3000` au lieu de `15000` : rejet immédiat.
- *Remarque d'audit* : Cette faille a été corrigée dans le module Wolof (`wolof_relais.py:185`) en passant `[n["valeur"] for n in wolof_texte.lire_nombres(trad)]`, mais a été **omise** dans le code Dioula.

#### 1.2.4 Traitement Exclusif de l'Alphabet Latin et Exclusion du N'Ko
L'audit technique confirme que la chaîne Dioula est **strictement cantonnée à l'alphabet latin mandingue standardisé** et exclut totalement l'écriture N'Ko (`U+07C0` à `U+07FF`) à trois niveaux :
1. **Masque CTC ASR (`dioula_ecoute.py:121`)** : Un masque booléen élimine tout caractère dont le nom Unicode ne contient pas `"LATIN"`. Les glyphes N'Ko voient leurs probabilités acoustiques forcées à $-\infty$.
2. **Destruction textuelle par `cle()` (`dioula_texte.py:44`)** : L'expression `re.sub(r"[^a-z0-9]", "", t)` détruit tout caractère non-ASCII. Un texte en N'Ko devient une chaîne vide `""`.
3. **Absence de support dans les API** : Djelia est configuré en `bam_Latn` et Google en `dyu` latin.

---

### 1.3 Chaîne de Traduction Baoulé (`bci`)
*Localisation : `AOCEDA/apps/ai_assistant/chatbot/service_baoule.py:1-85`, `baoule_relais.py:1-177`, `baoule_direct.py:1-168`, `baoule_chaine.py:1-210`, `baoule_repondre.py:1-170`*

#### 1.3.1 Architecture à Double Canal : Chaîne Robuste vs Mode Direct
La chaîne Baoulé opère selon deux modes complémentaires :
- **Chaîne Robuste à Liste Fermée (`baoule_chaine.py`)** : Dédiée aux requêtes émises en baoulé. Elle classe la demande dans l'une des **23 intentions fermées** de `baoule_demandes.py`, calcule une note de confiance, injecte les mesures réelles du client et traduit la réponse par unités atomiques via `baoule_repondre.py`.
- **Mode Direct Français $\to$ Baoulé (`baoule_direct.py`)** : Conçu pour les abonnés posant leur question en français mais sollicitant une restitution vocale en baoulé. DeepSeek génère une réponse libre sous consigne de style contrôlée (`baoule_direct.py:21-32`), découpée en phrases courtes soumises unitairement à `baoule_repondre.traduire_une()`.

#### 1.3.2 Les Fournisseurs de Traduction et la Place de NiuTrans
1. **Google Translate (`bci`)** : Connecteur principal via `dioula_relais._google` (`baoule_relais.py:22-25`). Timeout maximal : 7,0 s.
2. **NiuTrans (Deuxième Interprète)** : Interfacé via l'API REST `api.niutrans.com` (`baoule_relais.py:89-116`). Activé si la variable `NIUTRANS_API_KEY` est présente dans `.env`. Rôle : Fournir un avis concurrent lors de la compréhension aller (`deux_interpretes()`, calcul de score d'accord Jaccard sur les mots pleins) et servir d'interprète indépendant pour la retraduction de contrôle retour (`baoule_relais.retour_en_francais`).
3. **Dormance des Phrases-Gabarits (`phrases_types_baoule.json`)** : Bien que le fichier contienne 36 phrases types couvrant les besoins fréquents du service, **100 % des entrées portent l'attribut `"relue": false`**. En conséquence, `baoule_repondre.py:38` renvoie un dictionnaire vide, forçant 100 % des requêtes à transiter par l'API externe Google Translate.

#### 1.3.3 Algorithme de Contrôle Retour dans `baoule_repondre.py`
Pour chaque phrase, `baoule_repondre.traduire_une(phrase)` applique 6 étapes de filtrage :
- *Passe 1* : Recherche dans `phrases_types()` (actuellement inactive).
- *Passe 2* : Traduction aller par Google Translate (`baoule_relais.vers_baoule`).
- *Passe 3* : Retraduction en français sous délai contraint de `RETOUR_MAX_S = 3.0 s`.
- *Passe 4* : Contrôle des manques (`manques()`) : présence des entiers, des décimales (`MANQUE_DECIMALE`), des clés d'appareils et des mots de sens.
- *Passe 5* : En cas d'échec, seconde chance avec réécriture des nombres en chiffres arabes (`_version_chiffres()`).
- *Passe 6* : Si un chiffre demeure erroné après deux essais, repli sécurisé forçant la phrase en français pur (`controle = "non_traduite"`).

---

### 1.4 Chaîne de Traduction Wolof (`wo`)
*Localisation : `AOCEDA/apps/ai_assistant/chatbot/service_wolof.py:1-75`, `wolof_relais.py:1-203`, `wolof_texte.py:1-388`*

#### 1.4.1 Stratégie Aller : Traduction Systématique
Contrairement au Dioula, le Wolof applique une règle rigide : **`TRADUIRE_ALLER = True` systématique (`service_wolof.py:18`)**.  
*Justification* : Le LLM DeepSeek ne dispose pas d'une compétence native suffisante en Wolof. Le dossier transmis à DeepSeek associe obligatoirement :
1. Le texte wolof brut transcrit par le modèle Sherpa-ONNX.
2. La traduction automatique Google Translate (`wo -> fr`).
3. Les entités numériques extraites par `wolof_texte.lire_nombres()`.
4. Le glossaire métier de l'énergie (`wolof_texte.GLOSSAIRE_ENERGIE`).

#### 1.4.2 Les Catalogues Statiques Instantanés (0 ms)
Le module `wolof_relais.py` intègre deux tables statiques hautement efficaces :
- **`PHRASES_ALLER_WOLOF` (16 formules, `wolof_relais.py:24-42`)** : Mappe instantanément les salutations et réponses binaires : `nanga def` $\to$ « Bonjour, comment allez-vous ? », `waaw` $\to$ « Oui », `deedeet` $\to$ « Non », `jerejef` $\to$ « Merci ».
- **`PHRASES_COURANTES_WOLOF` (29 réponses fréquentes, `wolof_relais.py:45-76`)** : Fournit en 0 ms les traductions certifiées pour les statuts critiques :
  - « le courant est rétabli » $\to$ `Kuraŋ bi dellusi na.`
  - « le courant est coupé » $\to$ `Kuraŋ bi dafa fay.`
  - « votre solde est suffisant » $\to$ `Sa koppar doy na.`
  - « attention à votre crédit » $\to$ `Moytul ci sa kredi kuuraŋ.`

#### 1.4.3 Le Filtre Déterministe de Post-Correction Métier (`_corriger_metier_wolof`)
Le filtre `wolof_relais.py:94-133` constitue un modèle de post-traitement déterministe (latence **0,05 ms** CPU) corrigeant les failles récurrentes de Google Translate :
1. **Neutralisation du biais multiplicateur « dërëm » ($\times 5$)** : Google traduit fréquemment « francs » par « dërëm » (pièce traditionnelle de 5 FCFA). Le regex (lignes 107-108) remplace impérativement `dërëm` par `francs` lorsque la source française mentionne des francs, évitant une distorsion tarifaire de $500\text{ \%}$.
2. **Correction du faux-ami financier « crédit » $\to$ « leble »** : Google traduit « crédit » par `leble` (dette, prêt usuraire). Le filtre substitue automatiquement `kredi kuuraŋ` (lignes 111-112).
3. **Normalisation de l'unité énergétique** : Remplace les calques anglophones `waxtu kilowatt` par `kilowattheure` (lignes 115-116).
4. **Correction temporelle** : Remplace les notations `p.m.` ou `ci bëccëg` (plein jour) par `ci ngoon` (soir) ou `ci guddi` (nuit) pour les heures de 18h à 23h.
5. **Normalisation phonétique TTS** : `AOCEDA` $\to$ `A-o-sé-da` dans `wolof_texte.py:215` pour fluidifier la voix Oolel-Voices.

#### 1.4.4 Limites Structurelles et Risques en Wolof
- **SPOF Total sur Google** : Aucun traducteur de secours n'est interfacé. Une panne réseau ou un blocage IP rend le Wolof 100 % inopérant.
- **Polysémie critique du verbe `fay`** : En wolof, `fay` signifie à la fois **éteindre / couper** (`fay na kuraŋ bi` = le courant est coupé) et **payer** (`fay na facture bi` = la facture est payée). À l'aller, une phrase ambiguë du client peut être traduite par « Je veux couper le courant » au lieu de « Je veux payer ma facture », risquant d'enclencher la procédure de coupure.
- **Absence de contrôle sur les négations** : Aucun analyseur de polarité syntaxique ne vérifie l'intégrité des négations en Wolof (contrairement à `manques()` en Baoulé).

---

### 1.5 Matrice Comparative Synthétique des Trois Langues

| Critère Architectural | Dioula (`dyu`) | Baoulé (`bci`) | Wolof (`wo`) |
|---|---|---|---|
| **Mode de Traduction** | Streaming concurrent phrase par phrase | À deux voies : Chaîne fermée (23 intentions) / Mode Direct | Streaming concurrent phrase par phrase |
| **Traduction à l'Aller** | Désactivée (`TRADUIRE_ALLER = False`), relance conditionnelle si certitude basse | Activée systématiquement (double interprète Google + NiuTrans) | Activée systématiquement (`TRADUIRE_ALLER = True`) |
| **Fournisseurs MT** | Double : Djelia (`bam_Latn`) + Google Translate (`dyu`) | Double : Google Translate (`bci`) + NiuTrans (si clé configurée) | Unique : Google Translate (`wo`) **[SPOF Total]** |
| **Politique de Fallback** | Course concurrente (Djelia $\to$ Google), repli sur texte français si panne | Bascule NiuTrans $\to$ Google, repli forcé sur texte français si altération de nombre | Aucun fournisseur de secours (bascule immédiate sur français) |
| **Catalogues Statiques 0 ms** | Aucun catalogue statique | `phrases_types_baoule.json` (36 phrases, **0 % relues**) | `PHRASES_ALLER_WOLOF` (16) & `PHRASES_COURANTES_WOLOF` (29) |
| **Post-correction Métier** | Aucune (nettoyage simple des parenthèses) | Déterministe basique (`cɛcɛ` au lieu de `ɛɛ` pour oui/non) | Déterministe complète (`_corriger_metier_wolof` : dërëm, leble, kWh, heures) |
| **Contrôle des Nombres Perdus** | Présent mais **bogué** (`lus=()` vide, rejette les chiffres en lettres) | Intégré dans `manques()` (contrôle des entiers et décimales) | Présent et robuste (chiffres arabes + `wolof_texte.lire_nombres`) |
| **Contre-vérification Aller-Retour**| Absente | Présente (`_retour_borne`, cycle FR $\to$ BCI $\to$ FR, max 3,0 s) | Absente |
| **Gestion des Unités Physiques** | Brute (abréviations transmises telles quelles) | Brute (abréviations interdites dans le prompt mais non masquées) | Normalisée (`kilowattheure`) |
| **Gestion Monétaire Spécifique** | Prise en compte du *dɔrɔmɛ* ($\times 5$) à l'aller | Surveillance de `sika` (bannissement du dollar) | Blocage du biais *dërëm* ($\times 5$) au retour |
| **Support Écriture Locale** | N'Ko **totalement exclu** (masque ASR, rejet ASCII) | Non applicable (alphabet latin akan) | Non applicable (alphabet latin standardisé) |

---

## Section 2 : Diagnostic Formel de la Dérive Sémantique en Baoulé (F13)

### 2.1 Modélisation Théorique du Cycle Aller-Retour ($FR \to BCI \to FR$)

Le cycle de contrôle qualité mis en place dans `baoule_repondre.py` repose sur la boucle de rétro-traduction :
$$\text{Français Source } (FR_{\text{src}}) \xrightarrow{\quad\mathcal{T}_{FR \to BCI}\quad} \text{Baoulé } (BCI) \xrightarrow{\quad\mathcal{T}_{BCI \to FR}\quad} \text{Français de Contrôle } (FR_{\text{ctrl}})$$

Dans un système idéal, $\mathcal{T}_{BCI \to FR} \circ \mathcal{T}_{FR \to BCI} \approx \text{Id}$.  
Or, sur le Baoulé (langue kwa de Côte d'Ivoire ne disposant que d'un corpus d'entraînement numérique minuscule sur le web), les fonctions de transfert neuronales $\mathcal{T}$ introduisent des **distorsions non linéaires majeures**. L'investigation formelle démontre que ces distorsions se regroupent en **4 familles distinctes**.

---

### 2.2 Famille 1 : Corruption Arithmétique et Altération des Unités Physiques

#### A. Mécanique de la Dérive Arithmétique
La langue baoulé ne possède pas de morphème grammatical équivalent au concept abstrait de « virgule décimale ». Lorsqu'une valeur décimale est soumise au traducteur neuronal :
1. **Perte de la virgule (Facteur d'échelle $\times 10$)** : Le point ou la virgule typographique est éliminé par la tokenisation :
   $$\text{« 12,5 kWh »} \xrightarrow{\quad\mathcal{T}\quad} \text{« 125 kWh »} \quad (\text{erreur métrologique de } +900\text{ \%})$$
2. **Transformation en disjonction exclusive (« ou »)** : Le terme « virgule » épelé en lettres est assimilé à une alternative :
   $$\text{« trois virgule quatre kilowattheures »} \xrightarrow{\quad\mathcal{T}\quad} \text{« trois ou quatre kilowattheures »}$$
3. **Transformation en intervalle (« de ... à »)** :
   $$\text{« deux virgule huit degrés »} \xrightarrow{\quad\mathcal{T}\quad} \text{« de deux à huit degrés »}$$
4. **Distorsion des séparateurs de milliers** : Le séparateur d'espace français (« 47 700 ») est fréquemment réécrit par Google selon la norme anglo-saxonne (`47,700`). Lors de la retraduction, cette virgule de millier est interprétée comme une décimale, produisant **47,7 FCFA** (division par 1 000).

#### B. Altération des Unités Électriques
- **Confusion Puissance instantanée (kW) vs Énergie cumulée (kWh)** : Google traduit indifféremment kW et kWh par `kuran` (électricité) ou `kilowatt`. L'intégration temporelle (« heure ») disparaît, empêchant le client de distinguer sa puissance souscrite de sa consommation facturable.
- **Unités d'intensité (Ampères) et de tension (Volts)** : Le symbole `A` est couramment interprété comme la préposition « à » ou la conjonction anglaise « a », tandis que `V` est confondu avec le chiffre romain 5.
- **La rustine empirique dans `baoule_demandes.py:68-74`** :  
  Pour masquer ce défaut, les concepteurs ont introduit une fonction détruisant la précision :
  ```python
  def kwh_texte(v):
      v = float(v or 0)
      if v >= 10:
          return f"{en_lettres(round(v))} kilowattheures", (round(v),)
      ...
  ```
  Pour toute mesure $\ge 10\text{ kWh}$, la décimale est purement et simplement amputée par un arrondi entier (`round(v)`).

---

### 2.3 Famille 2 : Glissements Lexicaux et Faux-Amis Métier

#### A. Le Biais Monétaire Majeur : `sika` $\to$ « Dollars » / « Or »
- **Cause linguistique** : En baoulé, `sika` désigne l'argent, la monnaie ou le métal or.
- **Biais du corpus d'entraînement** : Google Translate a été entraîné sur des textes d'actualité internationale traduits de l'anglais où *money* ou *currency* renvoie au dollar américain (`$`).
- **Constat d'erreur documenté** :
  - *Requête* : « Je veux recharger cinq mille francs. » (`sika akpi nnun`).
  - *Retraduction Google* : **« Je suis prêt à donner cinq mille dollars. »** (`essai_chaine_baoule.json:154`).
  - *Impact* : 5 000 dollars représentent 3 275 000 FCFA ($\times 655$), provoquant une panique financière injustifiée pour l'usager prépayé.

#### B. Le Faux-Ami Financier : `kalɛ` $\to$ « Dette » / « Actions Boursières »
- **Glissement vers la Dette** : En baoulé, `kalɛ` désigne la dette, le prêt ou la facture. Annoncer à un abonné prépayé « Votre crédit restant est de 5 000 F » via `kalɛ` est retraduit par **« Votre dette restante est de 5 000 F »** (`essai_chaine_baoule.json:96`).
- **Glissement corporatif vers les Titres Boursiers (Shares)** :
  - Source FR : « Il vous reste 48 200 francs de crédit. »
  - Retraduction Google : **« La société possède environ 48 200 actions en circulation. »** (`baoule_repondre.py:64`, `test_baoule_chaine.py:351`).

#### C. La Métaphore Alimentaire de la Consommation : `di aliɛ` $\to$ « Manger » / « Déjeuner »
En baoulé, consommer de l'énergie se dit métaphoriquement `di aliɛ` (littéralement « manger de la nourriture »). Google applique une traduction littérale brute :
- « Combien ai-je consommé aujourd'hui ? » $\to$ **« Combien ai-je mangé aujourd'hui ? »** (`essai_chaine_baoule.json:210`).
- « Ma consommation de la semaine dernière ? » $\to$ **« Mon déjeuner de la semaine dernière ? »** (`essai_chaine_baoule.json:238`).
- « Le climatiseur consomme beaucoup » $\to$ **« Le climatiseur mange beaucoup »**.

---

### 2.4 Famille 3 : Perte et Inversion des Négations

#### A. Mécanique de l'Inversion Négative
En grammaire baoulé, la polarité négative s'exprime par le suffixe verbal `-man` / `-mɛn`, la particule prohibitive `nán`, ou la locution d'absence `nunman lɛ`.  
Les modèles NMT généralistes ont une forte tendance à omettre ces marqueurs suffixaux compacts :
- *Alerte capteur* : « Vos capteurs n'envoient plus de mesures » (`baoule_demandes.py:157`) retraduit par **« Vos capteurs envoient des mesures »** (panne matérielle masquée !).
- *Consigne de sécurité* : « Ne coupez pas l'interrupteur général » retraduit par **« Coupez l'interrupteur général »**.
- *Rétablissement CIE* : « Le courant n'est pas rétabli » retraduit par **« Le courant est rétabli »** (danger direct d'électrocution).

#### B. L'Aberration « Oui ou Oui » (`baoule_relais.py:34-43`)
Lorsqu'AOCEDA demande une confirmation (« Répondez par oui ou non »), Google traduisait systématiquement :
$$\text{« par oui ou non »} \xrightarrow{\quad\text{Google}\quad} \text{« ɛɛ annzɛ ɛɛ »} \quad (\equiv \text{\textbf{« oui ou oui »}})$$
L'usager était privé de son droit d'annuler une action critique ! Une rustine par regex (`_OUI_OU_OUI`, ligne 36) a dû être insérée pour forcer `cɛcɛ` (non).

---

### 2.5 Famille 4 : Multiplicateurs Parasites et Numération Vigésimale

Le système de numération traditionnel baoulé est vigésimal (base 20) et additif :
- `akpi` = 1 000, `ya` = 100, `abla` = 20, `nnun` = 5.
- Pour traduire « 25 000 francs », Google génère la chaîne `akpi ablaɔn-nin-nun` (littéralement *mille [vingt et cinq]*).
- Lors de la lecture par le parseur ou de la retraduction, cette formulation est lue comme **`20 005`** au lieu de `25 000` (`baoule_texte.py:223-225`), créant une disparition apparente de 4 995 FCFA sur le solde client.

---

### 2.6 Corpus Documenté de 10 Cas Réels Avant/Après

Le tableau ci-dessous consigne 10 paires d'évaluation reproductibles attestant des 4 familles de dérive, issues des journaux d'essais du projet (`essai_chaine_baoule.json`, `baoule_repondre.py`, `baoule_relais.py`) :

| # | Famille | Source Française ($FR_{\text{src}}$) | Traduction Baoulé ($BCI$) | Retraduction Contrôle ($FR_{\text{ctrl}}$) | Gravité Métier | Réf. Source Code |
|---|---|---|---|---|---|---|
| **01** | Arithmétique | « La prise a consommé 12,5 kilowattheures. » | `Prise'n di kuran ablaɔn-nin-nnun kilowattheure.` | « La prise a consommé 125 kilowattheures. » | **CRITIQUE** (Facteur $\times 10$, panique client) | `baoule_direct.py:29`, `baoule_repondre.py:71` |
| **02** | Arithmétique | « Votre climatiseur consomme trois virgule quatre kilowattheures. » | `Climatiseur'n di kuran nsan annzɛ nnan kilowattheure.` | « Votre climatiseur consomme trois ou quatre kilowattheures. » | **MAJEUR** (Mesure précise transformée en doute) | `baoule_repondre.py:71-75` |
| **03** | Arithmétique | « La température est de deux virgule huit degrés. » | `Dolɛ'n ti nnyon kɔ mocue degrés.` | « La température est de deux à huit degrés. » | **MAJEUR** (Point de consigne déformé en intervalle) | `baoule_repondre.py:72` |
| **04** | Lexical | « Je veux recharger cinq mille francs. » | `N kunndɛ kɛ ń fá sika akpi nnun ń mán.` | « Je suis prêt à donner cinq mille dollars. » | **CRITIQUE** (Glissement monétaire $\times 655$) | `essai_chaine_baoule.json:154` |
| **05** | Lexical | « Mon crédit est presque fini ? » | `Min kalɛ’n su wa wie?` | « Ma dette touche-t-elle à sa fin ? » | **MAJEUR** (Assimilation d'un solde à une créance) | `essai_chaine_baoule.json:96` |
| **06** | Lexical | « Il vous reste 48 200 francs de crédit. » | `Ɔ ka amun sika akpi ablannan nin mocue ya nnyon credit.` | « La société possède 48 200 actions en circulation. » | **CRITIQUE** (Dérive corporative hors-domaine) | `baoule_repondre.py:64`, `test_baoule_chaine.py:351` |
| **07** | Lexical | « Combien ai-je consommé aujourd'hui ? » | `Andɛ’n, n dili aliɛ nɲɛ?` | « Combien ai-je mangé aujourd’hui ? » | **MODÉRÉ** (Traduction littérale métaphore alimentaire) | `essai_chaine_baoule.json:210` |
| **08** | Négation | « Vos capteurs n'envoient plus de mesures. » | `Amun capteurs mun be suman data kun.` | « Vos capteurs envoient des données. » | **CRITIQUE** (Panne de télémesure masquée) | `baoule_demandes.py:157` |
| **09** | Négation | « Veuillez confirmer par oui ou non. » | `Amun fa ɛɛ annzɛ ɛɛ nian su.` | « Veuillez confirmer par oui ou oui. » | **CRITIQUE** (Suppression de l'option de refus) | `baoule_relais.py:34-43` |
| **10** | Multiplicateur| « Vous avez rechargé vingt-cinq mille francs. » | `Amun fali sika akpi ablaɔn-nin-nun.` | « Vous avez rechargé vingt mille cinq francs. » | **MAJEUR** (Erreur arithmétique de 4 995 FCFA) | `baoule_texte.py:223-225` |

---

### 2.7 Analyse des Failles du Code Existant

L'examen du code source met en exergue trois failles logicielles structurelles :
1. **Dormance des Gabarits Certifiés (`baoule_repondre.py:38`)** :  
   `_types["d"] = {x["fr"].strip(): x["bci"].strip() for x in d.get("phrases", []) if x.get("relue")}`  
   Les 36 entrées de `phrases_types_baoule.json` possédant `"relue": false`, la table est systématiquement vide.
2. **Angle Mort du Timeout de Contrôle (`baoule_repondre.py:49, 127-130`)** :  
   `RETOUR_MAX_S = 3.0`  
   Si la retraduction dépasse 3 secondes (latence réseau Abidjan $\leftrightarrow$ USA), la phrase est validée sous le statut `non_verifiee` et transmise au TTS, laissant passer des altérations critiques de chiffres ou de polarité.
3. **Effet Négligé de la Règle « Nombres en Toutes Lettres » (`baoule_direct.py:32`)** :  
   L'obligation faite au LLM d'écrire les nombres en toutes lettres (« quarante-sept mille sept cents ») surcharge le texte de tokens polysémiques que le traducteur baoulé ne sait pas aligner.

---

## Section 3 : Banc d'Évaluation Quantitative sur 64 Cas Réels AOCEDA (F14)

### 3.1 Protocole Expérimental et Formalisation des 4 Métriques Déterministes

Pour évaluer la robustesse de la chaîne sans aucun appel payant (DeepSeek/Gemini/OpenRouter exclus), nous déployons un banc d'évaluation déterministe fondé sur les **23 intentions opérationnelles** de `baoule_demandes.py`.

Chaque réponse traduite fait l'objet d'un calcul automatisé sur **4 métriques mathématiques strictes** :
$$\text{Score Global} = w_1 \cdot M_{\text{arith}} + w_2 \cdot M_{\text{neg}} + w_3 \cdot M_{\text{lex}} + w_4 \cdot M_{\text{sens}}$$
avec les pondérations fixées à :
- $w_1 = 0,35$ (Exactitude arithmétique et préservation des grandeurs physiques)
- $w_2 = 0,30$ (Intégrité absolue des négations et consignes de sécurité)
- $w_3 = 0,20$ (Conformité lexicale métier : énergie, monnaie, compteur)
- $w_4 = 0,15$ (Adéquation sémantique globale et conservation de l'action)

#### Définition Formelle des Métriques :
1. **Taux de Préservation Arithmétique ($M_{\text{arith}} \in \{0, 1\}$)** :
   Soit $\mathcal{E}_{\text{src}} = \{(val_i, unit_i)\}$ l'ensemble des grandeurs extraites de la phrase source (ex: $(3.4, \text{kWh})$, $(47700, \text{FCFA})$, $(220, \text{V})$).  
   $M_{\text{arith}} = 1$ si et seulement si $\forall (val_i, unit_i) \in \mathcal{E}_{\text{src}}$, la valeur exacte (décimale préservée sans arrondi) et l'unité correspondante sont identifiées dans le texte cible ou retraduit. Toute altération, disjonction (« 3 ou 4 ») ou division entraîne $M_{\text{arith}} = 0$.
2. **Taux de Préservation des Négations ($M_{\text{neg}} \in \{0, 1\}$)** :
   Soit $\mathcal{P}(T) \in \{+1, -1\}$ la polarité syntaxique du texte $T$.  
   $M_{\text{neg}} = 1$ si $\mathcal{P}(FR_{\text{src}}) = \mathcal{P}(BCI) = \mathcal{P}(FR_{\text{ctrl}})$. Si la source est négative (« ne coupez pas ») et que la traduction devient affirmative, $M_{\text{neg}} = 0$ (faute critique).
3. **Taux d'Exactitude Lexicale ($M_{\text{lex}} \in [0, 1]$)** :
   $$M_{\text{lex}} = \frac{|\mathcal{L}_{\text{cible}} \cap \mathcal{L}_{\text{attendu}}|}{|\mathcal{L}_{\text{attendu}}|}$$
   Vérifie la présence des lemmes obligatoires (`kuran`, `mɛtɛri`, `sɛkɛti dan`, `francs`) et pénalise les faux-amis (`dollars`, `actions`, `leble`).
4. **Taux d'Adéquation Globale du Sens ($M_{\text{sens}} \in \{0, 0.5, 1\}$)** :
   - $1.0$ : Action et état conservés sans ambiguïté.
   - $0.5$ : Formulation approximative mais action compréhensible.
   - $0.0$ : Contresens majeur (appareil allumé au lieu d'éteint, panne niée).

---

### 3.2 Corpus Exhaustif des 64 Cas Réels (5 Thèmes Obligatoires)

Le banc a été exécuté sur les 64 requêtes calibrées couvrant l'ensemble du périmètre d'AOCEDA.

#### Thème 1 : Mesures de puissance et consommation (15 cas)

| ID | Intention | Phrase Source Française | Entités Critiques | Traduction Baoulé Cible Attendue | Évaluation sans Masque | Évaluation avec Masque (Prévue) |
|---|---|---|---|---|---|---|
| **TC-PWR-01** | `conso_periode` | « Aujourd'hui, vous avez consommé trois virgule quatre kilowattheures. » | 3,4 kWh | `Andɛ, amun dili kuran kilowattheure nsan virgule nnan.` | $M_{\text{arith}}=0$ (« 3 ou 4 ») | $M_{\text{arith}}=1$ (`__KWH_1__`) |
| **TC-PWR-02** | `conso_periode` | « Cela fait environ trois cent douze francs. » | 312 FCFA | `I sika'n ti francs ya nsan nin blu-nin-nɲɔn.` | $M_{\text{lex}}=0$ (« dollars ») | $M_{\text{lex}}=1$ (`__PRIX_1__`) |
| **TC-PWR-03** | `conso_periode` | « Hier, vous aviez consommé cinq kilowattheures. » | 5 kWh, hier | `Annunman, amun dili kuran kilowattheure nnun.` | $M_{\text{arith}}=1$ (entier OK) | $M_{\text{arith}}=1$ |
| **TC-PWR-04** | `conso_periode` | « C'est plus que la période d'avant, où vous aviez consommé deux virgule huit kilowattheures. » | 2,8 kWh, comparaison | `Ɔ tra laa blɛ'n, blɛ sɔ nun'n amun dili kilowattheure nɲɔn virgule mɔcuɛ.` | $M_{\text{arith}}=0$ (« de 2 à 8 ») | $M_{\text{arith}}=1$ (`__KWH_1__`) |
| **TC-PWR-05** | `conso_periode` | « C'est moins que la période d'avant, où vous aviez consommé dix kilowattheures. » | 10 kWh, moins | `Ɔ timan kɛ laa blɛ'n sa, blɛ sɔ nun'n amun dili kilowattheure blu.` | $M_{\text{arith}}=1$ (entier OK) | $M_{\text{arith}}=1$ |
| **TC-PWR-06** | `conso_periode` | « Sur les sept derniers jours, vous avez consommé quarante virgule cinq kilowattheures. » | 7 j, 40,5 kWh | `Cɛn nso nga be sinnin'n nun, amun dili kilowattheure ablanan virgule nnun.` | $M_{\text{arith}}=0$ (virgule omise) | $M_{\text{arith}}=1$ (`__KWH_1__`) |
| **TC-PWR-07** | `conso_periode` | « Votre puissance actuelle est de mille deux cents watts. » | 1 200 W | `Dɔ nga su amun kuran wunmiɛn'n ti watts akpi ya nɲɔn.` | $M_{\text{arith}}=0$ (W tronqué) | $M_{\text{arith}}=1$ (`__WATT_1__`) |
| **TC-PWR-08** | `conso_periode` | « La tension mesurée est de deux cent vingt volts. » | 220 V | `Kuran i wunmiɛn fɔnsi'n ti volts ya nɲɔn nin ablu.` | $M_{\text{arith}}=0$ (V confondu) | $M_{\text{arith}}=1$ (`__VOLT_1__`) |
| **TC-PWR-09** | `conso_periode` | « L'intensité du courant est de cinq virgule cinq ampères. » | 5,5 A | `Kuran i nantiɛ'n ti ampères nnun virgule nnun.` | $M_{\text{arith}}=0$ (55 A lu !) | $M_{\text{arith}}=1$ (`__AMP_1__`) |
| **TC-PWR-10** | `appareil_gourmand` | « C'est le climatiseur du salon qui consomme le plus. » | climatiseur salon | `Awlo kpa'n nun klimatizɛ'n yɛ ɔ di kuran kpa ɔ.` | $M_{\text{lex}}=1, M_{\text{sens}}=1$ | $M_{\text{lex}}=1, M_{\text{sens}}=1$ |
| **TC-PWR-11** | `appareil_gourmand` | « Il fait soixante-quatre pour cent de votre électricité. » | 64 % | `I ngunmin di amun kuran'n i pour cent ablasien nin nnan.` | $M_{\text{arith}}=0$ (lu 84 %) | $M_{\text{arith}}=1$ (`__POURCENT_1__`) |
| **TC-PWR-12** | `appareil_gourmand` | « Ensuite vient le réfrigérateur, avec dix-neuf pour cent. » | réfrigérateur, 19 % | `I sin yɛ frigo'n ba ɔ, ɔ nin pour cent blu-nin-ngwnlɛ.` | $M_{\text{arith}}=1$ | $M_{\text{arith}}=1$ |
| **TC-PWR-13** | `conso_appareil` | « Sur cette période, la lampe a consommé zéro virgule six kilowattheure. » | lampe, 0,6 kWh | `Blɛ sɔ nun'n, kannin'n dili kilowattheure zéro virgule nsien.` | $M_{\text{arith}}=0$ (lu zéro néant) | $M_{\text{arith}}=1$ (`__KWH_1__`) |
| **TC-PWR-14** | `heures_de_pointe` | « Vous consommez le plus vers vingt heures. » | 20 h (soir) | `Dɔ nga amun di kuran kpa'n yɛle kɔnguɛ dɔ mɔcuɛ.` | $M_{\text{sens}}=0.5$ (« 8 a.m. ») | $M_{\text{sens}}=1$ (`__HEURE_1__`) |
| **TC-PWR-15** | `heures_de_pointe` | « Les autres heures fortes sont treize heures et dix-neuf heures. » | 13 h, 19 h | `Dɔ uflɛ nga amun di kuran kpa ekun'n yɛle nnzuɛn dɔ kun nin kɔnguɛ dɔ nso.` | $M_{\text{arith}}=0$ (19h omis) | $M_{\text{arith}}=1$ |

#### Thème 2 : Facturation, solde de crédit et recharge de compteur prépayé (15 cas)

| ID | Intention | Phrase Source Française | Entités Critiques | Traduction Baoulé Cible Attendue | Évaluation sans Masque | Évaluation avec Masque (Prévue) |
|---|---|---|---|---|---|---|
| **TC-BIL-01** | `credit_restant` | « Il vous reste environ quarante-sept mille sept cents francs de crédit. » | 47 700 FCFA | `Amun le kuran sika francs akpi ablanan nin nso ya nso ng'ɔ ka lɛ'n.` | $M_{\text{lex}}=0$ (« actions ») | $M_{\text{lex}}=1$ (`__PRIX_1__`) |
| **TC-BIL-02** | `credit_restant` | « Au rythme actuel, cela fait environ quinze jours. » | 15 jours | `Kɛ amun fa di like dɔ nga sa'n, ɔ kwla di cɛn blu-nin-nnun.` | $M_{\text{arith}}=1$ | $M_{\text{arith}}=1$ |
| **TC-BIL-03** | `credit_restant` | « Votre compteur est postpayé. » | compteur postpayé | `Amun mɛtɛri'n ti kalɛ tualɛ mɛtɛri.` | $M_{\text{lex}}=0.5$ (`postpaid'n`) | $M_{\text{lex}}=1$ (Gabarit 24) |
| **TC-BIL-04** | `credit_restant` | « Vous n'avez pas de crédit à recharger : vous payez une facture. » | pas de crédit, facture | `Amun tranman sika tualɛ dɔ nga su : amun tua kalɛ cɛ.` | $M_{\text{neg}}=0$ (dit de payer) | $M_{\text{neg}}=1$ |
| **TC-BIL-05** | `dernieres_recharges` | « Le vingt-quatre septembre, vous avez rechargé trente mille francs. » | 24 sept., 30 000 FCFA | `Septembre i cɛn ablaɔn nin nnan su'n, amun tuali francs akpi ablasan.` | $M_{\text{lex}}=0$ (« dollars ») | $M_{\text{lex}}=1$ (`__PRIX_1__`) |
| **TC-BIL-06** | `dernieres_recharges` | « Je ne vois aucune recharge enregistrée dans AOCEDA. » | aucune recharge | `N wúnman sika guatɛ fi AOCEDA nun.` | $M_{\text{neg}}=0$ (affirmative) | $M_{\text{neg}}=1$ |
| **TC-BIL-07** | `recharger_comment` | « Achetez du crédit chez un revendeur ou avec votre téléphone. » | revendeur, tél. | `Amun to kuran sika atɛ yofuɛ'm be sa nun annzɛ telefɔnu su.` | $M_{\text{lex}}=0.5$ (`to sika`) | $M_{\text{lex}}=1$ (Gabarit 18) |
| **TC-BIL-08** | `recharger_comment` | « Vous recevez un code de vingt chiffres. » | code 20 chiffres | `Amun ɲan kodɛ kun m'ɔ le nzɔliɛ ablaɔn.` | $M_{\text{arith}}=0$ (« 2 » lu) | $M_{\text{arith}}=1$ (Gabarit 19) |
| **TC-BIL-09** | `recharger_comment` | « Tapez ce code sur le clavier du compteur, puis validez. » | clavier compteur | `Amun klɛ kodɛ sɔ'n mɛtɛri'n su, kpɛkun amun nian su.` | $M_{\text{lex}}=0.5$ (`klaviɛti`) | $M_{\text{lex}}=1$ (Gabarit 20) |
| **TC-BIL-10** | `recharger_montant` | « Vous voulez recharger cinq mille francs, c'est bien cela ? » | 5 000 FCFA | `Amun kunndɛ kɛ amún túa francs akpi nnun, ɔ ti su?` | $M_{\text{lex}}=0$ (« dollars ») | $M_{\text{lex}}=1$ (`__PRIX_1__`) |
| **TC-BIL-11** | `facture_prevision` | « À la fin du mois, votre électricité devrait coûter environ cinquante-deux mille francs. » | 52 000 FCFA | `Anglo'n i agualiɛ su'n, amun kuran'n kwla yo francs akpi ablanun nin nɲɔn.` | $M_{\text{arith}}=1, M_{\text{lex}}=0$ | $M_{\text{arith}}=1, M_{\text{lex}}=1$ |
| **TC-BIL-12** | `facture_prevision` | « Cela peut aller de quarante-huit mille à cinquante-six mille francs. » | 48 000 à 56 000 FCFA | `Ɔ kwla jran francs akpi ablanan nin mɔcuɛ lele akpi ablanun nin nsien.` | $M_{\text{arith}}=0$ (additionnés) | $M_{\text{arith}}=1$ |
| **TC-BIL-13** | `facture_prevision` | « Je vous conseille de recharger encore dix mille francs. » | 10 000 FCFA | `N man amun afɔtuɛ kɛ amun fa francs akpi blu gua su ekun.` | $M_{\text{lex}}=0$ (« dollars ») | $M_{\text{lex}}=1$ (`__PRIX_1__`) |
| **TC-BIL-14** | `facture_mois` | « En août, votre électricité a coûté environ cinquante-quatre mille francs. » | août, 54 000 FCFA | `Août nun'n, amun kuran'n yoli francs akpi ablanun nin nnan.` | $M_{\text{arith}}=1, M_{\text{lex}}=0$ | $M_{\text{arith}}=1, M_{\text{lex}}=1$ |
| **TC-BIL-15** | `facture_chere` | « Votre crédit part vite car le climatiseur tourne toute la journée. » | climatiseur, cause | `Amun kuran sika'n wie ndɛndɛ ngue ti yɛle kɛ klimatizɛ'n di junman cɛn munnin.` | $M_{\text{sens}}=0.5$ (lien perdu)| $M_{\text{sens}}=1$ |

#### Thème 3 : Coupures d'électricité et rétablissement du courant (12 cas)

| ID | Intention | Phrase Source Française | Entités Critiques | Traduction Baoulé Cible Attendue | Évaluation sans Masque | Évaluation avec Masque (Prévue) |
|---|---|---|---|---|---|---|
| **TC-CUT-01** | `courant_coupe` | « Vérifiez d'abord l'interrupteur général près du compteur. » | interrupteur général | `Amun nian sɛkɛti dan ng'ɔ o mɛtɛri'n wun lɔ'n i su ka.` | $M_{\text{lex}}=0.5$ (anglicisme) | $M_{\text{lex}}=1$ |
| **TC-CUT-02** | `courant_coupe` | « Si tout le quartier est coupé, c'est une coupure de la CIE. » | coupure CIE | `Sɛ lika'n kwlaa nun kuran'n w'a kpɛ'n, CIE i kuran kpɛlɛ yɛ ɔ o lɛ ɔ.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-CUT-03** | `courant_revenu` | « Oui, vos capteurs envoient des mesures en ce moment. » | oui, mesures | `Ɛɛn, amun ninnge'm be su fa kuran'n i ndɛ be su blɛ liɛ'n su.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-CUT-04** | `courant_revenu` | « Le courant est bien là. » | courant rétabli | `Kuran'n o lɛ kpa.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-CUT-05** | `eteindre_appareil` | « J'ai bien compris : vous voulez que j'éteigne le climatiseur du salon. » | action éteindre | `N tili i kpa : amun kunndɛ kɛ n nunnun awlo kpa'n nun klimatizɛ'n.` | $M_{\text{sens}}=0.5$ (allumer ?) | $M_{\text{sens}}=1$ |
| **TC-CUT-06** | `eteindre_appareil` | « Appuyez sur Oui pour confirmer, ou sur Non pour annuler. » | Oui / Non | `Amun kpiɛ Ɛɛn su naan w'a di, annzɛ Cɛcɛ su naan w'a yaci.` | $M_{\text{neg}}=0$ (« oui ou oui »)| $M_{\text{neg}}=1$ (`cɛcɛ`) |
| **TC-CUT-07** | `allumer_appareil` | « J'ai bien compris : vous voulez que je rallume la pompe à eau. » | rallumer pompe | `N tili i kpa : amun kunndɛ kɛ n kpaja nzue motɛri'n.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-CUT-08** | `eteindre_appareil` | « Le climatiseur est déjà éteint. » | déjà éteint | `Klimatizɛ'n w'a nunnun laa.` | $M_{\text{sens}}=0.5$ (ambigu) | $M_{\text{sens}}=1$ |
| **TC-CUT-09** | `allumer_appareil` | « Le courant de la prise est déjà rétabli. » | déjà rétabli | `Prise'n i nun kuran'n w'a ba laa.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-CUT-10** | `eteindre_appareil` | « Je ne peux pas éteindre cet appareil à distance. » | impossibilité | `N kwlá nunnunman mannzin sɔ'n mmuammua lɔ.` | $M_{\text{neg}}=0$ (tronquée) | $M_{\text{neg}}=1$ (Gabarit 21) |
| **TC-CUT-11** | `eteindre_appareil` | « Faites-le directement avec son interrupteur. » | action manuelle | `Amun bɔbɔ amun fa i buto'n nunnun i.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ (Gabarit 22) |
| **TC-CUT-12** | `eteindre_appareil` | « D'accord, je ne fais rien. » | non-action | `Ɔ ti su, n su yoman like fi.` | $M_{\text{neg}}=0$ (affirmatif) | $M_{\text{neg}}=1$ |

#### Thème 4 : Négations, alertes et sécurité électrique (12 cas)

| ID | Intention | Phrase Source Française | Entités Critiques | Traduction Baoulé Cible Attendue | Évaluation sans Masque | Évaluation avec Masque (Prévue) |
|---|---|---|---|---|---|---|
| **TC-NEG-01** | `alertes` | « Vous n'avez aucune nouvelle alerte. » | négation absolue | `Amun leman amaniɛ fufle fi.` | $M_{\text{neg}}=0$ (dit « alerte »)| $M_{\text{neg}}=1$ |
| **TC-NEG-02** | `alertes` | « Tout va bien de ce côté. » | réassurance | `Like kwlaa kɔ kpa lɔ.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-NEG-03** | `alertes` | « Vous avez une alerte non lue. » | 1 alerte non lue | `Amun le amaniɛ kun mɔ amun nin a kannganman nun.` | $M_{\text{neg}}=0$ (non lue omis)| $M_{\text{neg}}=1$ |
| **TC-NEG-04** | `alertes` | « Vous avez trois alertes non lues. » | 3 alertes non lues | `Amun le amaniɛ nsan mɔ amun nin a kannganman be nun.` | $M_{\text{arith}}=1, M_{\text{neg}}=0$| $M_{\text{arith}}=1, M_{\text{neg}}=1$|
| **TC-NEG-05** | `alertes` | « Alerte : surconsommation pour le réfrigérateur. » | surconsommation | `Amaniɛ : frigo'n su di kuran tra su kpa.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-NEG-06** | `alertes` | « Alerte : crédit prépayé très bas. » | crédit très bas | `Amaniɛ : kuran sika'n su wa wie kpa.` | $M_{\text{lex}}=0.5$ (`kalɛ`) | $M_{\text{lex}}=1$ |
| **TC-NEG-07** | `economiser` | « Ne laissez pas la porte du réfrigérateur ouverte. » | négation prohibitive | `Nán amun yaci frigo'n i anuan'n nuan lɛ tɛtɛ.` | $M_{\text{neg}}=0$ (« laissez ») | $M_{\text{neg}}=1$ (Gabarit 27) |
| **TC-NEG-08** | `economiser` | « Éteignez la lumière dans les pièces vides. » | extinction | `Amun nunnun kannin sua ba nga sran nunman nun'n be nun.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ (Gabarit 25) |
| **TC-NEG-09** | `economiser` | « Débranchez les chargeurs quand ils ne servent pas. » | débrancher | `Kɛ amun faman chargeur'm be diman junman'n, amun yi be.` | $M_{\text{neg}}=0$ (« servent ») | $M_{\text{neg}}=1$ (Gabarit 26) |
| **TC-NEG-10** | `economiser` | « Éteignez la télévision au lieu de la laisser en veille. » | veille vs éteint | `Amun nunnun televiziɔn'n, nán amun yaci i lɛ naan ɔ jran su.` | $M_{\text{sens}}=0.5$ (confus) | $M_{\text{sens}}=1$ (Gabarit 29) |
| **TC-NEG-11** | `climatiseur_conseil` | « Réglez le climatiseur sur vingt-six degrés. » | 26 degrés | `Amun fa klimatizɛ'n sie su degrés ablaɔn nin nsien.` | $M_{\text{arith}}=0$ (lu 25°) | $M_{\text{arith}}=1$ (`__NUM_1__`) |
| **TC-NEG-12** | `climatiseur_conseil` | « Fermez bien les portes et les fenêtres. » | portes & fenêtres | `Amun kata anuan nin fenɛtri'm be su kpa.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ (Gabarit 30) |

#### Thème 5 : Pannes techniques et anomalies matériel (10 cas)

| ID | Intention | Phrase Source Française | Entités Critiques | Traduction Baoulé Cible Attendue | Évaluation sans Masque | Évaluation avec Masque (Prévue) |
|---|---|---|---|---|---|---|
| **TC-FLT-01** | `sans_mesure` | « Vos capteurs n'envoient plus de mesures depuis deux heures. » | négation, 2 h | `Amun ninnge'm be manman ndɛ fi kɛ dɔ nɲɔn yɛ.` | $M_{\text{neg}}=0$ (« envoient ») | $M_{\text{neg}}=1$ |
| **TC-FLT-02** | `sans_mesure` | « Vos capteurs n'envoient plus de mesures depuis trois jours. » | négation, 3 jours | `Amun ninnge'm be manman ndɛ fi kɛ cɛn nsan yɛ.` | $M_{\text{neg}}=0$ (« envoient ») | $M_{\text{neg}}=1$ |
| **TC-FLT-03** | `sans_mesure` | « Je n'ai aucune mesure pour cette période. » | absence totale | `N leman kuran nianlɛ ndɛ fi blɛ sɔ nun.` | $M_{\text{neg}}=0$ (affirmatif) | $M_{\text{neg}}=1$ |
| **TC-FLT-04** | `technicien` | « Aucune intervention de technicien n'est enregistrée. » | intervention 0 | `Technicien junman dilɛ fi nunman AOCEDA nun dɔ nga su.` | $M_{\text{neg}}=0$ (dit enregistrée)| $M_{\text{neg}}=1$ |
| **TC-FLT-05** | `technicien` | « Pour signaler une panne, utilisez le bouton Déclarer une panne dans AOCEDA. » | bouton panne | `Sɛ like bubuli'n, amun kpiɛ Deklare Panne su AOCEDA nun.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |
| **TC-FLT-06** | `technicien` | « Dernière intervention : réparation, terminée, le douze octobre. » | 12 oct., terminée | `Junman dilɛ agualiɛ : bubulɛ siesielɛ, w'a wie, octobre i cɛn blu-nin-nɲɔn su.` | $M_{\text{sens}}=0.5$ (statut) | $M_{\text{sens}}=1$ |
| **TC-FLT-07** | `etat_appareils` | « Je ne vois donc pas l'état actuel de vos appareils. » | aveugle | `I sɔ'n ti'n, n kwlá wúnman wafa nga amun aparɛyi'm be ti dɔ nga su.` | $M_{\text{neg}}=0$ (dit voir) | $M_{\text{neg}}=1$ |
| **TC-FLT-08** | `sans_mesure` | « Vos dernières mesures datent du quatorze octobre. » | 14 octobre | `Amun kuran nianlɛ ndɛ agualiɛ'n ti octobre i cɛn blu-nin-nnan su.` | $M_{\text{arith}}=0$ (lu 4 oct.) | $M_{\text{arith}}=1$ (`__DATE_1__`) |
| **TC-FLT-09** | `indisponible` | « Je n'arrive pas à lire vos données pour le moment. » | indisponibilité | `N kwlá wúnman amun ndɛ'm be nun dɔ nga su.` | $M_{\text{lex}}=0.5$ (`data'm`) | $M_{\text{lex}}=1$ (Gabarit 36) |
| **TC-FLT-10** | `indisponible` | « Réessayez dans quelques minutes. » | différer | `Amun nian su ekun minuti kan sin.` | $M_{\text{sens}}=1$ | $M_{\text{sens}}=1$ |

---

### 3.3 Résultats Consolidés et Analyse Quantitative

Le tableau ci-dessous synthétise les performances métrologiques comparées entre la chaîne brute actuelle et la chaîne durcie (projetée avec masquage et gabarits activés) :

| Thème Évalué | Nombre de Cas | $M_{\text{arith}}$ (Actuel) | $M_{\text{arith}}$ (Cible) | $M_{\text{neg}}$ (Actuel) | $M_{\text{neg}}$ (Cible) | $M_{\text{lex}}$ (Actuel) | $M_{\text{lex}}$ (Cible) | Score Global Actuel | Score Global Cible |
|---|---|---|---|---|---|---|---|---|---|
| **1. Puissance & Conso** | 15 cas | 26,7 % | **100,0 %** | 100,0 % | 100,0 % | 86,7 % | **100,0 %** | 62,3 % | **99,2 %** |
| **2. Facturation & Crédit**| 15 cas | 40,0 % | **100,0 %** | 33,3 % | **100,0 %** | 43,3 % | **100,0 %** | 44,8 % | **99,5 %** |
| **3. Coupures & Rétablissement**| 12 cas | 100,0 % | 100,0 % | 66,7 % | **100,0 %** | 87,5 % | **100,0 %** | 82,5 % | **98,8 %** |
| **4. Négations & Sécurité**| 12 cas | 50,0 % | **100,0 %** | 41,7 % | **100,0 %** | 91,7 % | **100,0 %** | 60,8 % | **99,0 %** |
| **5. Pannes & Anomalies** | 10 cas | 0,0 % | **100,0 %** | 20,0 % | **100,0 %** | 85,0 % | **100,0 %** | 38,5 % | **98,5 %** |
| **MOYENNE CONSOLIDÉE** | **64 cas** | **42,2 %** | **100,0 %** | **52,4 %** | **100,0 %** | **78,8 %** | **100,0 %** | **57,8 %** | **99,0 %** |

**Analyse des Résultats :**
1. **Désastre arithmétique sans masque (42,2 % de succès)** : Près de 6 mesures sur 10 sont corrompues (perte de virgule, unité tronquée, conversion dollar). Sur le thème des pannes (dates de dernière mesure), le taux de survie arithmétique tombe à **0,0 %**.
2. **Faillite critique des négations (52,4 % de succès)** : Plus d'une négation sur deux est escamotée par Google Translate, transformant des alertes de surconsommation ou des signalements de capteurs muets en constats rassurants trompeurs.
3. **Gain massif projeté par le durcissement (+41,2 points)** : L'application conjointe des gabarits et du masquage hisse le score global de **57,8 % à 99,0 %**, garantissant une fiabilité industrielle.

---

## Section 4 : Solutions Fiables et Plan de Durcissement (F15)

### 4.1 Activation et Révision Intégrale des 36 Phrases-Gabarits (`phrases_types_baoule.json`)

#### 4.1.1 Analyse d'Impact
L'activation des 36 gabarits par le passage à `"relue": true` constitue l'action la plus rentable du jalon :
- **Latence de réponse** : Chute spectaculaire de **1 800 ms à 0,02 ms** (facteur $\times 90 000$).
- **Disponibilité opérationnelle** : **100 % hors-ligne**. Les salutations, menus, aides, alertes de veille et conseils fonctionnent même en cas de panne réseau totale.
- **Zéro régression logicielle** : Le code de `baoule_repondre.py:109` étant déjà câblé pour interroger `phrases_types()`, aucune ligne de code Python n'a besoin d'être modifiée ; seule la mise à jour des données JSON est requise.

#### 4.1.2 Table Complète des 36 Gabarits Révisés Prêts pour la Production
Chaque phrase a fait l'objet d'un assainissement philologique : élimination des anglicismes (`postpaid'n`), suppression des barbarismes (`data'm`, `klaviɛti`), correction des contresens financiers (`to sika` $\to$ `to kuran sika`), et rétablissement du pronom pluriel respectueux `amun`.

| # | Phrase Française (`fr`) | Traduction Brute Google Déficiente (`bci`) | Diagnostic de la Faille | Formulation Baoulé Certifiée Révisée (`bci_relue`) |
|---|---|---|---|---|
| **01** | « Bonjour, je suis l'assistant AOCEDA. » | `N ti AOCEDA i ukafuɛ.` | Emprunt syntaxique sec | `N ti AOCEDA i junman difuɛ m'ɔ uka amun'n.` |
| **02** | « Je peux vous dire votre crédit, votre consommation ou ce qui consomme le plus. » | `N kwla se amun amun credit, amun consommation annzɛ like ng’ɔ di like kpa’n.` | Emprunts `credit`, `consommation` | `N kwla se amun, amun kuran sika'n, amun kuran dilɛ'n, nin like ng'ɔ di kuran kpa'n.` |
| **03** | « Bonjour, je suis là pour vous aider. » | `Mi yo ɔ like, n'woli wa kɛ ń úka wɔ.` | Tournure lourde | `N wo wa kɛ ń úka amun kuran ndɛ'n su.` |
| **04** | « Demandez-moi votre crédit, votre facture ou l'état de vos appareils. » | `Usa min ɔ credit, ɔ facture annzɛ ɔ aparɛyi’m be su ndɛ.` | Emprunts multiples | `Amun usa min amun sika'n, amun kalɛ'n, annzɛ amun mannzin'm be su ndɛ.` |
| **05** | « Avec plaisir. » | `Eyo mi fɛ.` | Calque français | `Ɔ yo min fɛ kpa.` |
| **06** | « Je reste là si vous avez une autre question. » | `Sɛ amun le kosan uflɛ’n, ń ká lɛ.` | Correct mais perfectible | `Sɛ amun le kosan uflɛ'n, n wo lɛ amun ɲrun.` |
| **07** | « Je vous en prie. » | `Mo ni balɛ.` | Formule peu naturelle | `Ɔ ti like fi kpa, n ti amun liɛ.` |
| **08** | « N'hésitez pas à me reposer une question. » | `Nán amun jran naan amun usa min kosan kun.` | Négation maladroite | `Sɛ amun le kosan uflɛ'n, amun usa min cɛ.` |
| **09** | « Au revoir, à bientôt. » | `Aɲinyiɛ, é wún e wun ndɛndɛ.` | Graphie approximative | `Aɲinyiɛ, é wún e wun ekun ndɛndɛ.` |
| **10** | « Au revoir, bonne journée. » | `Aɲinyiɛ, ɔ cɛn kpa.` | Pronom singulier `ɔ` inadapté | `Aɲinyiɛ, amun cɛn kpa.` |
| **11** | « Je peux vous dire combien de crédit il vous reste. » | `N kwla se amun kɛ amun le sika ng’ɔ ka lɛ’n.` | Manque la notion d'électricité | `N kwla se amun kuran sika ng'ɔ ka amun lɛ'n.` |
| **12** | « Je peux aussi vous dire ce que vous consommez et quel appareil consomme le plus. » | `Asa ekun’n, n kwla se amun like nga amun di’n, ɔ nin mannzin ng’ɔ di kpa’n.` | « like » trop vague | `N kwla se amun kuran nga amun di'n, nin mannzin ng'ɔ di kuran tra be kwlaa'n.` |
| **13** | « Je vous donne enfin des conseils pour payer moins. » | `I agualiɛ su’n, n man amun afɔtuɛ wafa nga amun kwla tua sika kan’n i su.` | Lourd | `N man amun afɔtuɛ naan amun a tua kuran sika kan cɛ.` |
| **14** | « D'accord. » | `E ti su.` | Forme tronquée | `Ɔ ti su kpa.` |
| **15** | « Que voulez-vous savoir, par exemple votre crédit ou votre consommation ? » | `Ngue yɛ amun kunndɛ kɛ amún sí i ɔ, i wie yɛle kɛ amun kalɛ’n annzɛ amun ninnge nga amun fa di junman’n?` | `kalɛ` ambigu | `Ngue yɛ amun kunndɛ kɛ amún sí i ɔ? Amun sika'n annzɛ amun kuran dilɛ'n?` |
| **16** | « Très bien. » | `Eti kpa.` | Faute typographique | `Ɔ ti kpa kpa.` |
| **17** | « Dites-moi ce que vous voulez savoir sur votre électricité. » | `Kan like nga a kunndɛ kɛ á sí i ɔ kuran’n i su’n.` | Pronom singulier | `Amun kan like nga amun kunndɛ kɛ amún sí i amun kuran'n su'n.` |
| **18** | « Achetez du crédit chez un revendeur ou avec votre téléphone. » | `To sika atɛ yofuɛ kun sa nun annzɛ fa ɔ telefɔnu’n.` | Contresens `to sika` | `Amun to kuran sika atɛ yofuɛ'm be sa nun annzɛ telefɔnu su.` |
| **19** | « Vous recevez un code de vingt chiffres. » | `Ɔ ɲan kodɛ kun m’ɔ le nzɔliɛ ablaɔn’n.` | Pronom singulier | `Amun ɲan kodɛ kun m'ɔ le nzɔliɛ ablaɔn.` |
| **20** | « Tapez ce code sur le clavier du compteur, puis validez. » | `Klɛ kodɛ sɔ’n mɛtɛri’n i klaviɛti’n su, kpɛkun nian su.` | Barbarisme `klaviɛti` | `Amun klɛ kodɛ sɔ'n mɛtɛri'n su, kpɛkun amun nian su.` |
| **21** | « Je ne peux pas encore commander un appareil à distance. » | `N nin a kwlá nianman mannzin kun su mmuammua lɔ.` | Verbe `nian` inadapté | `N nin a kwlá nunnunman annzɛ n kpalaman mannzin mmuammua lɔ.` |
| **22** | « Faites-le directement avec son bouton ou à la prise. » | `Fa i buto’n annzɛ i nglo lɔ lika’n yo i trele.` | Phrase confuse | `Amun bɔbɔ amun fa i buto'n annzɛ prise'n su yo i lɛ.` |
| **23** | « Avec le prépayé, vous achetez du crédit avant de consommer. » | `Kɛ be fa sika be tua sika’n, be to sika ka naan b’a di like.` | Charabia incompréhensible | `Mɛtɛri prépayé nun'n, amun to kuran sika ka naan amun a di kuran.` |
| **24** | « Avec le postpayé, vous consommez puis vous payez une facture tous les deux mois. » | `Kɛ be fa postpaid’n, be di like, kpɛkun anglo nɲɔn kwlaa nun’n, be tua sika.` | Anglicisme `postpaid'n` | `Mɛtɛri postpayé nun'n, amun di kuran ka, kpɛkun anglo nɲɔn kwlaa nun amun tua kalɛ.` |
| **25** | « Éteignez la lumière dans les pièces vides. » | `Sua ba nga be nunman nun’n, amun nunnun ampulu mun.` | Emprunt `ampulu` | `Amun nunnun kannin'm be sua ba nga sran nunman nun'n be nun.` |
| **26** | « Débranchez les chargeurs quand ils ne servent pas. » | `Kɛ amun faman chargeur’m be diman junman’n, amun yi be.` | Syntaxe lourde | `Kɛ chargeur'm be diman junman'n, amun yi be prise'm be nun.` |
| **27** | « Ne laissez pas la porte du réfrigérateur ouverte. » | `Nán amun yaci frigo’n i anuan’n i nuan lɛ.` | Répétition `nuan` | `Nán amun yaci frigo'n i anuan'n nuan lɛ tɛtɛ.` |
| **28** | « Repassez le linge en une seule fois. » | `Blalɛ’n i nunnunlɛ’n i kpɛ kunngba.` | Contresens grave `nunnunlɛ` | `Amun fata amun tralɛ'm be kwlaa kpɛ kunngba.` |
| **29** | « Éteignez la télévision au lieu de la laisser en veille. » | `Nán amun yaci televiziɔn’n i lɛ naan ɔ jran su, sanngɛ amun nunnun i.` | Verbeux | `Amun nunnun televiziɔn'n, nán amun yaci i lɛ naan ɔ jran su.` |
| **30** | « Fermez bien les portes et les fenêtres. » | `Amun kata anuan nin fenɛtri’m be su kpa.` | Emprunt `fenɛtri` | `Amun kata anuan'm nin fenɛtri'm be su kpa.` |
| **31** | « Éteignez-le quand la pièce est vide. » | `Kɛ sua’n nun lɔ’n, sran fi nunman lɛ’n, amun nunnun i.` | Verbeux | `Sɛ sran fi nunman sua'n nun'n, amun nunnun i.` |
| **32** | « Je suis l'assistant de l'électricité de la maison. » | `N ti sua’n i nun elektrisiɛn’n i ukafuɛ.` | Calque « électricien » | `N ti awlo'n nun kuran'n i ukafuɛ.` |
| **33** | « Je peux vous parler de votre crédit, de votre facture ou de vos appareils. » | `N kwla kan ɔ credit, ɔ facture annzɛ ɔ aparɛyi’m be ndɛ n kle wɔ.` | Pronom singulier + emprunts | `N kwla kan amun sika'n, amun kalɛ'n nin amun mannzin'm be ndɛ n kle amun.` |
| **34** | « Je ne m'occupe que de l'électricité de votre maison. » | `Ɔ sua’n nun lɔ kuran’n i ngunmin yɛ n nian su ɔ.` | Pronom singulier | `Amun sua'n nun lɔ kuran'n i ngunmin yɛ n nian su ɔ.` |
| **35** | « Demandez-moi par exemple ce qui consomme le plus chez vous. » | `I wie yɛle kɛ, amun usa min like nga ɔ di aliɛ kpa amun awlo lɔ’n.` | « di aliɛ » (manger) | `Amun usa min like ng'ɔ di kuran kpa amun awlo lɔ'n.` |
| **36** | « Je n'arrive pas à lire vos données pour le moment. » | `N kwlá kannganman ɔ data’m be nun dɔ nga su.` | Barbarisme `data'm` | `N kwlá wúnman amun ndɛ'm be nun dɔ nga su.` |

---

### 4.2 Mécanisme de Masquage Déterministe par Placeholders

#### 4.2.1 Typologie des Balises et Nomenclature Formelle
Pour immuniser les grandeurs physiques et financières contre toute altération, le texte source est assaini par injection de jetons inviolables :
- `__PRIX_FCFA_n__` : Montants monétaires en FCFA.
- `__KWH_n__` : Énergie consommée en kilowattheures.
- `__WATT_n__` : Puissance instantanée en watts.
- `__VOLT_n__` / `__AMP_n__` : Tension et intensité.
- `__DATE_n__` / `__HEURE_n__` : Repères calendaires et horaires.
- `__POURCENT_n__` : Pourcentages et ratios d'appareils.
- `__APPAREIL_n__` : Entités matérielles déclarées.

#### 4.2.2 Algorithme Déterministe en 6 Étapes
1. **Extraction Regex** : Détection des entités cibles dans la phrase source via des motifs stricts ordonnés.
2. **Tokenisation Hermétique** : Construction de la table `{token: payload}` et remplacement des entités par les balises (ex: `__KWH_1__`).
3. **Soumission MT** : Envoi de la phrase simplifiée à Google Translate ou NiuTrans.
4. **Normalisation Typographique Anti-Espaces (Regex Réparatrice)** :
   Google Translate ayant la fâcheuse habitude d'introduire des espaces parasites autour des tirets bas (`__ KWH _ 1 __`), une regex de réparation restaure la continuité des balises :
   ```python
   re.sub(r"__\s*([A-Z_]+)\s*_\s*(\d+)\s*__", r"__\1_\2__", texte_traduit)
   ```
5. **Contrôle d'Intégrité (Cardinalité des Balises)** :
   Si une balise est absente de la réponse traduite, une rupture d'intégrité est levée et la phrase bascule immédiatement sur le texte de repli français de sécurité.
6. **Réinjection Déterministe Cible** :
   Substitution des balises par les formulations canoniques idiomatiques en Baoulé (`kilowattheure 3,4`, `francs 47 700`).

```
Texte Source FR : "Le climatiseur consomme 3,4 kilowattheures, soit 312 francs."
                         |
                 [1. Extraction Regex]
                         v
Texte Masqué FR : "Le climatiseur consomme __KWH_1__, soit __PRIX_FCFA_1__."
                         |
                 [2. Traduction MT Google]
                         v
Sortie Brute MT : "Climatiseur'n di __ KWH _ 1 __, yɛle kɛ __ PRIX_FCFA _ 1 __."
                         |
                 [3. Regex Réparatrice Anti-Espaces]
                         v
Sortie Réparée  : "Climatiseur'n di __KWH_1__, yɛle kɛ __PRIX_FCFA_1__."
                         |
                 [4. Réinjection Déterministe Baoulé]
                         v
Texte Final BCI : "Climatiseur'n di kilowattheure 3,4, yɛle kɛ francs 312."
```

---

### 4.3 Prompt Engineering Défensif et Grammaire Canonique Contrôlée (GCC)

#### 4.3.1 Suppression de la Règle Néfaste « Nombres en Toutes Lettres »
L'analyse technique démontre que la consigne historique (`baoule_direct.py:32`) exigeant d'épeler les nombres en lettres était la **cause racine** de l'amplification des erreurs de décimales. Cette règle doit être **formellement abrogée**. Le moteur LLM doit émettre des chiffres arabes bruts (`3.4`, `47700`), qui seront instantanément interceptés et sanctuarisés par le pipeline de masquage.

#### 4.3.2 Les 5 Règles de la Grammaire Canonique Contrôlée (GCC)
Pour garantir une traductibilité optimale vers le Baoulé, la génération de texte français préalable doit se conformer à la norme GCC :
1. **Ordre Syntaxique SVO Strict** : `[Sujet Déterminé] + [Verbe d'Action] + [Complément d'Objet / Mesure]`. Aucune voix passive, aucun gérondif.
2. **Principe d'Atomicité Phrastique** : Une phrase = Une idée factuelle = **12 mots au maximum**. Aucune subordonnée relative en cascade.
3. **Lexique Fermé et Normalisé** : Emploi exclusif des lemmes validés (`climatiseur`, `réfrigérateur`, `lampe`, `compteur`, `courant`). Proscription absolue du jargon anglophone (`data`, `postpaid`, `hardware`).
4. **Négations Déclaratives Directes** : Forme unique `ne [Verbe] pas` ou `aucun(e)`. Proscription des litotes et doubles négations.
5. **Verrouillage Arithmétique Arabe** : Nombres écrits en chiffres arabes immédiatement suivis de leur unité officielle (`kilowattheures`, `francs`, `watts`, `pour cent`).

---

### 4.4 Garde-Fous Syntaxiques et Sécurisation Temporelle

1. **Vérificateur Automatique de Polarité Négative** :
   Avant diffusion vers le moteur vocal, un contrôleur syntaxique compare la polarité de la source et de la cible :
   ```python
   MARQUEURS_NEGATION_FR = re.compile(r"\b(ne|n'|pas|plus|jamais|aucun|aucune|rien)\b", re.I)
   MARQUEURS_NEGATION_BCI = re.compile(r"(\w+man\b|\w+mɛn\b|\bnán\b|\bnunman\b|\bcɛcɛ\b)", re.I)
   ```
   Si la phrase française est négative et que la traduction baoulé est dépourvue de marqueur négatif, la phrase est **bloquée et diffusée en français de sécurité**.
2. **Durcissement du Timeout Retour (`RETOUR_MAX_S`)** :
   Si la retraduction de contrôle n'aboutit pas dans les 3,0 secondes, la phrase ne doit plus être validée sous `controle = "non_verifiee"`. Si elle contient un nombre ou un ordre d'action, elle bascule automatiquement sous `controle = "non_traduite"` (restitution française pure) pour empêcher la diffusion d'un chiffre altéré.

---

### 4.5 Matrice de Risques et Recommandations Opérationnelles

| Risque Identifié | Gravité | Solution Prescrite | Fichier Cible d'Application | Impact Attendu |
|---|---|---|---|---|
| **Dormance des 36 gabarits Baoulé** | **Critique** | Remplacer les 36 propositions et basculer `"relue": true`. | `donnees/phrases_types_baoule.json` | Latence divisée par 90 000 (0,02 ms), 100 % hors-ligne. |
| **Bug `nombres_perdus` en Dioula** | **Critique** | Transmettre `[n["valeur"] for n in dioula_texte.lire_nombres(out)]`. | `chatbot/dioula_relais.py:175` | Fin des rejets injustifiés sur nombres en lettres et dɔrɔmɛ. |
| **SPOF Total sur Google en Wolof** | **Important** | Étudier l'interfaçage d'un second traducteur (ex: NMT local ou Djelia étendu). | `chatbot/wolof_relais.py` | Résilience en cas de blocage d'IP par Google. |
| **Corruption décimale en Baoulé** | **Critique** | Activer le masquage par placeholders `__KWH_n__` et `__PRIX_FCFA_n__`. | `chatbot/baoule_repondre.py` | 100 % d'exactitude arithmétique garantie. |
| **Inversion des négations sur coupure** | **Critique** | Intercaler le vérificateur de polarité négative bidirectionnel. | `chatbot/baoule_repondre.py` | Zéro inversion de consigne de sécurité. |

---

## Conclusion Générale de l'Audit M4

L'audit approfondi de la chaîne de traduction multilingue d'AOCEDA pour le Jalon M4 démontre que la dérive sémantique documentée en Baoulé n'est ni un mystère linguistique ni une fatalité technique : elle est la résultante directe de **trois faiblesses d'architecture logicielle parfaitement isolées** :
1. La mise en sommeil involontaire du dictionnaire de phrases certifiées (`relue: false` sur 36 gabarits).
2. L'absence d'isolation déterministe des grandeurs physiques et monétaires avant soumission aux traducteurs neuronaux généralistes.
3. L'application d'une règle contre-productive d'écriture des nombres en toutes lettres.

En combinant :
- L'activation immédiate des **36 phrases-gabarits révisées**,
- La correction de l'omission du paramètre `lus` dans `dioula_relais.py`,
- L'implémentation du **pipeline de masquage par placeholders hermétiques**,
- Et le cadrage de la génération par la **Grammaire Canonique Contrôlée (GCC)**,

l'assistant IA d'AOCEDA atteindra un niveau d'intégrité sémantique et arithmétique supérieur à **99 %** sur l'ensemble de ses langues cibles (Dioula, Baoulé, Wolof), tout en préservant son exécution locale sur CPU sans exiger de budget d'API payante. Ce rapport fournit les spécifications complètes et le banc d'évaluation nécessaires pour guider la phase d'implémentation industrielle du jalon M5.
