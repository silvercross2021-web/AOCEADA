# Spécification Technique & Architecturale : Nouveau Mode Live Multilingue Universel

**Dépôt :** AOCEDA (Django 6, Daphne ASGI, Channels)  
**Composant :** `apps/ai_assistant/chatbot/live_agent.py`, `live.py`, `assistant-live.js`  
**Date :** 28 octobre 2026  
**Statut :** Spécification d'architecture cible – Prête pour implémentation  

---

## 1. Vision et Objectif

Le mode **Live** actuel offre une interaction vocale fluide et instantanée (0,6 à 1,1 s) en français et en anglais grâce au modèle Speech-to-Speech natif de Google (Gemini Live). Cependant, **Gemini Live ne sait ni comprendre ni synthétiser les langues ivoiriennes et africaines** (Baoulé `bci`, Dioula `dyu`, et ultérieurement Wolof `wol`, Yoruba `yor`). 

Lorsque l'on tentait de lui demander de parler baoulé, il hallucinait des phonèmes aléatoires, ce qui a contraint le projet à instaurer la règle de garde-fou `SANS_VOIX`.

L'objectif de cette nouvelle architecture est de **briser cette barrière sans perdre la réactivité du Live**, en permettant :
1. De **parler dans n'importe quelle langue supportée** (Français, Anglais, Baoulé, Dioula, etc.).
2. De **recevoir la réponse dans la langue de son choix**, que ce soit la même langue ou une langue différente (ex: l'utilisateur parle en français et l'agent répond en baoulé ; ou l'utilisateur parle en baoulé et l'agent répond en français).
3. De **basculer dynamiquement à la volée** en cours de conversation (par commande vocale ou via l'interface).
4. De **maintenir une latence ressentie quasi-nulle (< 0,5 s)** grâce à des micro-réponses d'attente natives et un réveil anticipé des moteurs de voix sur GPU.
5. De **garantir une extensibilité immédiate** pour l'ajout du Wolof et du Yoruba.

---

## 2. Le Paradigme Fondamental : Dissociation Oreille / Cerveau / Bouche

Le blocage historique venait de la tentative de traiter Gemini Live comme un bloc monolithique où l'entrée vocale et la sortie vocale étaient indissociables.

La nouvelle architecture découple explicitement les trois fonctions cognitives :

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 1. L'OREILLE (Ingress / Écoute)                                        │
│  Détecte et transcrit la langue parlée par l'utilisateur.                                              │
│  - Branche A (Rapide / Directe) : Flux audio routé vers Gemini Live (Français, Anglais).               │
│  - Branche B (Locale / Spécialisée) : Flux audio routé vers STT local (Baoulé omniASR, Dioula Omni).   │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ [Texte Normalisé / Pivot Français]
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 2. LE CERVEAU (Raisonnement & Outils)                                  │
│  Toujours assuré par GEMINI LIVE (avec les 10 outils AOCEDA, vision caméra, écran et page).            │
│  - Reçoit soit l'audio natif (fr/en), soit le texte pivot traduit (baoulé/dioula).                     │
│  - Analyse l'intention, consulte les capteurs ZMCT103C, lit la base de données.                        │
│  - Décide de la réponse et émet le flux textuel de raisonnement.                                       │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ [Texte de la réponse]
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 3. LA BOUCHE (Egress / Synthèse)                                       │
│  Génère la voix dans la langue de réponse désirée.                                                     │
│  - Branche A (Natif) : Voix intégrée Gemini Live (Français, Anglais).                                  │
│  - Branche B (Local / Cloud GPU) : Traducteur NMT + Voix neuronale dédiée                              │
│    (Cerebrium OmniVoice pour le Baoulé, Djelia pour le Dioula).                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Matrice Complète des 4 Modes Opérationnels

La combinaison des entrées et des sorties génère 4 modes opérationnels entièrement gérés par la passerelle WebSocket :

| Mode | Langue Parlée (Entrée) | Langue Réponse (Sortie) | Pipeline Oreille | Pipeline Bouche | Latence 1er Son Estimée | Silence Ressenti (avec Earcon) |
|---|---|---|---|---|---|---|
| **Mode 1** *(Full Natif)* | Français ou Anglais | Français ou Anglais | Gemini Live Direct | Voix Gemini Live Direct | **0,6 à 1,1 s** | **0,6 s** (Immédiat) |
| **Mode 2** *(Asymétrique FR $\rightarrow$ Local)* | Français ou Anglais | **Baoulé ou Dioula** | Gemini Live Direct | Traduction NMT + Voix GPU Cerebrium / Djelia | **3,2 à 4,5 s** | **< 0,5 s** (Micro-son d'attente local) |
| **Mode 3** *(Asymétrique Local $\rightarrow$ FR)* | **Baoulé ou Dioula** | Français ou Anglais | STT Local (omniASR / Omnilingual) + NMT | Cerveau Gemini $\rightarrow$ Voix Gemini Live Direct | **3,5 à 5,0 s** | **< 0,5 s** (Micro-son d'attente français) |
| **Mode 4** *(Full Local)* | **Baoulé ou Dioula** | **Baoulé ou Dioula** | STT Local + Traduction pivot FR | Traduction NMT + Voix GPU Cerebrium / Djelia | **5,5 à 7,0 s** | **< 0,5 s** (Micro-son d'attente local) |

### Chronogramme Détaillé du Mode 4 (Le cas le plus exigeant)

```
t = 0.0 s ── Fin de parole de l'utilisateur (Silence VAD 0,7 s détecté)
t = 0.1 s ── Le serveur joue l'Earcon d'attente préenregistré ("Un instant, je regarde..." en baoulé)
t = 0.1 s à 1.8 s ── Écoute locale omniASR-300M (déjà anticipée sur les derniers buffers) -> Texte baoulé
t = 1.8 s à 2.5 s ── Traduction pivot Baoulé -> Français (Google Translate API / Djelia)
t = 2.5 s à 3.8 s ── Inférence Cerveau Gemini (appel des outils AOCEDA compteur/conso si nécessaire) -> Réponse FR
t = 3.8 s à 4.6 s ── Traduction Phrase 1 Français -> Baoulé
t = 4.6 s à 6.2 s ── Synthèse Vocale Phrase 1 sur Cerebrium GPU (machine déjà préchauffée)
t = 6.2 s ── Fin de l'Earcon d'attente et début de lecture continue de la vraie réponse parlée
```

---

## 4. Machine à États et Système de Double Verrouillage

L'appel Live maintient en mémoire deux axes d'état indépendants :

### A. Les Variables d'État

1. **`langue_entree`** : `["fr", "en", "bci", "dyu", "auto"]` (Langue que le système s'attend à entendre).
2. **`langue_sortie`** : `["fr", "en", "bci", "dyu", "meme"]` (`meme` signifie "répondre dans la même langue que celle qui a été parlée").
3. **`verrou_sortie`** : `["aucun", "demande_vocale", "selection_ui", "menu_profil"]`.

### B. Matrice de Décision des Verrous

```
                         ┌───────────────────────────────────────────────────────────┐
                         │              Arrivée d'un événement utilisateur           │
                         └─────────────────────────────┬─────────────────────────────┘
                                                       │
                       ┌───────────────────────────────┴───────────────────────────────┐
                       ▼                                                               ▼
        [Interaction sur l'Interface UI]                              [Parole / Audio Détecté]
                       │                                                               │
        Clic sur le sélecteur "Je parle"                              Détection automatique par Whisper / ASR
        ──► Fixe `langue_entree` (verrouillée)                        ──► Si `langue_entree == 'auto'` :
                                                                          Mise à jour dynamique de `langue_entree`
        Clic sur le sélecteur "L'agent me répond"                                      │
        ──► Fixe `langue_sortie`                                      Analyse sémantique de la demande :
            et passe `verrou_sortie = 'selection_ui'`                  - "Parle en baoulé" ──► `langue_sortie = 'bci'`
                                                                       - "Réponds en français" ──► `langue_sortie = 'fr'`
                                                                       - "Switch to English" ──► `langue_sortie = 'en'`
                                                                       (Passe `verrou_sortie = 'demande_vocale'`)
```

### C. Règles de Priorité
* **Priorité 1 (Absolue)** : Clic explicite de l'utilisateur dans l'interface Live.
* **Priorité 2** : Commande vocale explicite formulée dans n'importe quelle langue.
* **Priorité 3** : Réglage issu du menu général de l'application.
* **Priorité 4 (Par défaut)** : Mode miroir (`langue_sortie = meme`) basé sur la détection automatique de l'entrée.

---

## 5. Algorithme d'Aiguillage Acoustique Temps Réel (Ingress Pipeline)

Le navigateur envoie en continu des trames audio PCM 16 kHz 16 bits mono via le WebSocket `/api/assistant/live`.

```
Flux Audio Montant (Chunks 100 ms)
      │
      ├───► [Tampon Circulaire Glissant - 1500 ms]
      │
      ▼
[Contrôleur de Routage Ingress]
      │
      ├── Cas 1 : `langue_entree` explicitement fixée sur Baoulé ou Dioula
      │     └──► Court-circuite Gemini Live.
      │     └──► Alimente directement le buffer STT local (`omniASR` ou `Omnilingual`).
      │
      └── Cas 2 : `langue_entree` en mode Auto ou Français
            │
            ├──► Le flux est transmis en temps réel à Gemini Live (0 latence).
            │
            └──► En parallèle (thread non-bloquant), Whisper Tiny analyse le premier paquet de parole (300 ms).
                  │
                  ├── Si probabilité FR ou EN >= 0.90 :
                  │     └──► La session Gemini Live continue sans interruption.
                  │
                  └── Si probabilité FR/EN < 0.60 ET présence de signatures locales :
                        └──► Signal d'interruption immédiat à Gemini Live.
                        └──► Injection du paquet "vider" vers l'audio sortant.
                        └──► Bascule automatique du contrôleur vers l'ASR local correspondant.
```

### Critères de Détection Acoustique Locale
Pour arbitrer entre Baoulé et Dioula à l'oral en mode automatique, le contrôleur réutilise la logique validée au banc d'essais :
1. `Omnilingual 1B` décode phonétiquement en alphabet latin.
2. Si des mots exclusifs dioula sont présents (`d_d >= 1 and d_d >= b_d`) $\rightarrow$ Validation **Dioula direct** (inutile de solliciter l'oreille baoulé).
3. Sinon, consultation de l'oreille spécialisée `omniASR-300M-baoule` avec calcul du score croisé pondéré :
   $$\text{Score} = \frac{b_b}{n_b} + \frac{b_d}{n_d}$$
   Si $\text{Score} \ge 0{,}50$ (ou $0{,}25$ en l'absence de mot dioula) $\rightarrow$ Validation **Baoulé**.

---

## 6. Pipeline de Synthèse et Streaming Sortant (Egress Pipeline)

Lorsque `langue_sortie` est définie sur **Baoulé** ou **Dioula**, Gemini Live ne doit **jamais** utiliser sa voix synthétique native.

### Processus d'Interception et de Transformation :
1. **Consigne Système Dynamique injectée à Gemini** :
   ```text
   Tu es l'agent AOCEDA en direct. La réponse doit être fournie pour une traduction vers le [Baoulé/Dioula].
   Règles impératives :
   - Formule ta réponse en français extrêmement simple, concis et direct (maximum 2 à 3 phrases).
   - Écris tous les nombres en chiffres cardinaux (ex: 45000 et non quarante-cinq mille).
   - Évite toute métaphore ou tournure idiomatique complexe intraduisible.
   ```
2. **Filtrage des Paquets WebSocket Gemini** :
   * Les paquets `model_turn.parts[].inline_data` (l'audio natif Gemini) sont **interceptés et supprimés côté serveur**. Aucun son anglais/américain n'est envoyé au navigateur.
   * Les paquets `output_transcription.text` (le texte émis par Gemini au fil de l'eau) sont capturés et assemblés dans un buffer textuel.
3. **Segmentation Phrase par Phrase (Streaming Chunking)** :
   * Dès qu'un délimiteur de phrase est détecté (`.`, `!`, `?`, `;\n`), le tronçon textuel est immédiatement expédié au traducteur NMT sans attendre la fin du tour de parole de Gemini.
4. **Génération Vocale Déportée Haute Performance** :
   * **Baoulé (`bci`)** : Transmission asynchrone du texte traduit au cluster **Cerebrium GPU** exécutant `OmniVoice` (voix de référence RK / WAXAL). Temps de synthèse : 1,7 s.
   * **Dioula (`dyu`)** : Transmission à l'API **Djelia TTS** (voix bambara/dioula). Temps de synthèse : 2,2 s.
5. **Diffusion vers le Client** :
   * Les blocs audio PCM 24 kHz générés par Cerebrium ou Djelia sont transmis au navigateur via les mêmes trames binaires WebSocket que celles attendues par le lecteur audio Live.

---

## 7. Les Accélérateurs de Latence Ressentie (Réduction du Silence)

Pour transformer une attente technique de 5 secondes en une expérience perçue comme immédiate, trois accélérateurs sont obligatoires :

### Accélérateur 1 : Les Earcons et Micro-Réponses Natives Préenregistrées
Dans la culture orale ouest-africaine, une conversation naturelle comporte des marques d'écoute immédiates (*phatiques*). Dès que la fin de parole est détectée ($t = 0{,}1\text{ s}$), le serveur envoie immédiatement l'un des fichiers audio préenregistrés (durée 0,8 à 1,5 s) choisis aléatoirement dans le catalogue validé :

* **En Baoulé (`bci`)** :
  * *"N kɔ nian nun..."* (Je regarde / Je vérifie...)
  * *"Sɛsɛ kpa, n ti..."* (Très bien, je comprends...)
  * *"Anun o, n kɔ fa..."* (D'accord, je prends les données...)
* **En Dioula (`dyu`)** :
  * *"A to n k'a lajɛ..."* (Laisse-moi regarder...)
  * *"Nba, ayiwa..."* (D'accord, très bien...)
  * *"I ni ce, n b'a fɛ..."* (Merci, je vérifie cela...)
* **En Français (`fr`)** :
  * *"Très bien, je regarde..."*
  * *"Un instant, je vérifie sur votre compteur..."*

> **Impact mesuré :** Le client entend une voix humaine fluide dès **300 millisecondes**. Le cerveau de l'utilisateur perçoit le système comme ultra-rapide pendant que le modèle de fond calcule.

### Accélérateur 2 : Préchauffage et Maintien du GPU Cerebrium (Warmup Actif)
Le démarrage à froid (*cold start*) d'une instance GPU sur Cerebrium prend **35 secondes**.
* **Déclencheur d'anticipation** : Dès que l'appel Live est lancé avec le Baoulé sélectionné, OU dès que le premier mot baoulé est identifié, la fonction `reveiller_voix_baoule()` est appelée en arrière-plan.
* **Maintien actif** : Tant que l'appel Live est ouvert, un ping keep-alive maintient l'instance allumée.
* **Sécurité budgétaire** : Le garde-fou `CHATBOT_GPU_MINUTES_JOUR` (120 min/jour, soit ~2 $) coupe automatiquement le GPU en cas d'oubli ou d'appel anormalement long, avec repli sur le synthétiseur local.

### Accélérateur 3 : Détection d'Interruption (Barge-In) Instantané
Si le client reprend la parole alors qu'un Earcon ou qu'une réponse longue en Baoulé/Dioula est en cours de lecture :
* Le détecteur VAD client détecte la voix en 50 ms.
* Envoi immédiat du message `{"type": "interrompu"}` au serveur.
* Le serveur annule immédiatement les requêtes HTTP/GPU en cours vers Cerebrium ou Djelia (`task.cancel()`).
* Le haut-parleur du navigateur est vidé instantanément (`audioContext.suspend()` puis reprise).

---

## 8. Interface Utilisateur (UI) du Nouveau Live

Dans la fenêtre d'appel Live (cadre supérieur avec l'onde et le personnage animé), deux sélecteurs discrets et ergonomiques sont ajoutés :

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  [● En direct]  Gemini 3.8 Live · GPU Baoulé Prêt                      [✕ Raccrocher]  │
│                                                                                        │
│                                   ( Onde Animée )                                      │
│                                                                                        │
│   🗣️ Je parle : [ Automatique ▾ ]       📢 L'agent répond : [ Comme moi (Miroir) ▾ ]  │
│                   ├── Automatique                            ├── Comme moi (Miroir)    │
│                   ├── Français                               ├── Français              │
│                   ├── Wawle (Baoulé)                         ├── Wawle (Baoulé)        │
│                   └── Jula (Dioula)                          └── Jula (Dioula)         │
│                                                                                        │
│   💬 Sous-titres bilingues dynamiques :                                               │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Vous : N klo kɛ n wun n kouran'n i statut                                     │   │
│   │ [Traduction auto : Je veux voir le statut de mon électricité]                  │   │
│   │                                                                                │   │
│   │ Agent : Kouran'n wo su kpa. Matin nian nun 12 kWh (1 200 FCFA).                │   │
│   │ [Traduction auto : Le courant fonctionne bien. Ce matin vous avez 12 kWh...]   │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
│   [🎙️ Micro]      [📹 Caméra]      [🖥️ Écran]      [⌨️ Clavier]       [⚙️ Options]     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.B. Boutons Rapides 1-Clic et Verrouillage de Tour (Half-Duplex Mic Gating)

Pour répondre à l'impératif de confort d'usage et éviter les bruits parasites ou interruptions intempestives pendant le traitement en langue locale :

1. **Boutons de Choix Rapide (Pills 1-Clic)** :
   * Une rangée de boutons pills est immédiatement accessible au-dessus de l'onde visuelle :
     `[ 🔄 Miroir ]` `[ 🇫🇷 Français ]` `[ 🇨🇮 Wawle (Baoulé) ]` `[ 🇨🇮 Jula (Dioula) ]` `[ 🇬🇧 English ]`
   * Un simple clic commute instantanément la langue de sortie sans ouvrir aucun menu.
   * La bascule peut également être commandée à la voix (*« réponds-moi en baoulé »*, *« parle en dioula »*, *« reviens en français »*), ce qui synchronise automatiquement l'illumination du bouton correspondant.

2. **Verrouillage de Tour Half-Duplex (Micro Gating)** :
   * **Principe** : Tant que l'agent prépare, traduit ou diffuse une réponse en Baoulé ou Dioula, le microphone est **strictement coupé** à la fois côté navigateur (`isGateBlocked = true`) et côté serveur (`_traiter_audio_montant` rejette les paquets).
   * **Bannière d'état visuelle claire** :
     * 🔒 **Micro coupé** : Bannière rouge/ambre pulsante avec message *« Microphone coupé · L'agent répond... »*.
     * 🎤 **Micro ouvert** : Bannière émeraude lumineuse *« Micro ouvert · Vous pouvez parler »*.
   * **Protocole de libération synchrone** :
     * Le navigateur empile les trames audio reçues de l'agent (`audioQueue`).
     * Dès que le dernier échantillon audio a été joué dans les haut-parleurs, le navigateur envoie `{"type": "audio_termine"}`.
     * Le serveur et le client rouvrent alors instantanément le microphone (`verrou_tour_agent = False`).
     * Un délai de secours de 6 secondes protège contre toute déconnexion ou oubli de signal.

---

## 9. Sécurité et Garde-fous Incompressibles

### A. Confirmation des Coupures d'Appareils (Carte Oui / Non)
* **En Français / Anglais** : La confirmation vocale ("Oui, coupe le courant") est acceptée sous réserve des 30 secondes d'expiration.
* **En Baoulé et Dioula** : **VALIDATION AU CLIC UNIQUEMENT**.
  * **Raison impérative** : En Dioula, « oui » se dit `ɔnhɔn` et « non » se dit `ɔn ɔn`. Même pour un modèle phonétique de pointe, la proximité acoustique entre l'affirmation nasalisée et la négation nasalisée présente un risque inacceptable de fausse manœuvre sur un disjoncteur réel.
  * L'agent explique oralement dans la langue : *"Veuillez appuyer sur le bouton Oui vert de l'écran pour confirmer la coupure."*

### B. Barrière Anti-Hallucination
La fonction `invention()` reste active : si pour une raison quelconque Gemini commence à émettre du pseudo-baoulé ou du pseudo-dioula directement avec sa voix native, le flux est coupé en moins de 150 ms et redirigé vers le pipeline de traduction certifié.

---

## 10. Extensibilité : Intégration du Wolof (`wol`) et Yoruba (`yor`)

L'architecture étant découplée, ajouter le **Wolof** et le **Yoruba** ne nécessite **aucune modification de la machine à états ni de la passerelle WebSocket**.

Il suffit d'enregistrer les connecteurs dans le registre des langues :

| Composant | Wolof (`wol`) | Yoruba (`yor`) |
|---|---|---|
| **STT (Oreille)** | Modèle Meta MMS-ASR Wolof ou WAXAL CTC | Modèle Meta MMS-ASR Yoruba ou Whisper fine-tuné |
| **Traduction Pivot** | Google Translate API (`wo` $\leftrightarrow$ `fr`) | Google Translate API (`yo` $\leftrightarrow$ `fr`) |
| **TTS (Bouche)** | VITS Wolof (hébergé sur Cerebrium GPU) | VITS Yoruba ou modèle neural dédié |
| **Earcons** | Phrases préenregistrées en studio wolof | Phrases préenregistrées en studio yoruba |

---

## 11. Plan d'Implémentation Technique Étape par Étape

Pour respecter scrupuleusement la règle d'or du projet (**garder les 751 tests pytest et 458 tests Django 100 % au vert**), le déploiement s'articule en 4 phases :

### Phase 1 : Infrastructure de l'Appel et Double Contrôle d'État
* Ajout des champs `langue_entree`, `langue_sortie` et `verrou_sortie` dans le protocole de démarrage `{"type": "debut"}`.
* Ajout des sélecteurs visuels dans `assistant.html` et `assistant-live.js`.
* Tests unitaires sur la machine à états et les transitions de verrous.

### Phase 2 : Implémentation du Mode 2 (FR Parlé $\rightarrow$ Langue Locale Répondue)
* Interception de la sortie audio native de Gemini quand `langue_sortie in ('bci', 'dyu')`.
* Branchement du buffer textuel sur le pipeline de découpage de phrases.
* Connexion au moteur Cerebrium OmniVoice et Djelia TTS.
* Validation sur banc d'essais avec mesure de latence.

### Phase 3 : Implémentation du Mode 3 & Mode 4 (Langue Locale Parlée)
* Dérivation du flux audio entrant vers l'ASR local (`omniASR` / `Omnilingual`).
* Injection du texte pivot dans le tour Gemini Live via `session.send_realtime_text()`.
* Intégration des micro-sons d'attente (Earcons) à déclenchement immédiat ($t < 300\text{ ms}$).

### Phase 4 : Tests de Robustesse, Barge-in et Validation
* Test d'endurance sur 50 tours de parole mixtes.
* Vérification des garde-fous de coupure de courant (clic forcé en langue locale).
* Contrôle strict des non-régressions : validation complète des suites de tests unitaires du projet.
