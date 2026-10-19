# 03 · Architecture cible (PROPOSITION : rien n'est déplacé tant que l'humain n'a pas dit « validé »)

Date : 2026-10-19. Les chemins marqués 🔒 sont des zones protégées ou des contrats figés : ils ne bougent pas.

## 1. Principe directeur

Le dépôt est déjà assez bien rangé *à l'intérieur* des apps ; les vrais problèmes sont (1) le **bruit autour** : archives,
scripts d'essai, maquettes, captures, doublons de mémoire ; (2) l'**absence de documentation** structurée ; (3) les
**cycles d'import** et les **vues géantes** de `analytics` et `sensors`. La cible corrige d'abord (1) et (2), qui sont
sans risque, puis (3) avec réexport pour garder les anciens chemins d'import valides. On ne renomme aucune app
Django (`app_label` figés) et on ne déplace aucun dossier d'app.

## 2. Arborescence cible

```
/                         racine : l'essentiel seulement
├── README.md             présentation, démarrage en 5 min, carte du dépôt
├── AGENTS.md  CLAUDE.md  GEMINI.md  .github/   consignes agents (mêmes règles, nouveaux chemins)
├── firmware/ ?           (voir §7, décision humaine) sinon : src/ include/ lib/ test/ platformio.ini restent à la racine
├── docs/                 TOUTE la documentation
│   ├── architecture/     vue d'ensemble, couches, flux, décisions (une page par décision)
│   ├── developpement/    installation, conventions, ajouter une page/app/réglage/test, tests
│   ├── api/              endpoints
│   ├── exploitation/     déploiement, sauvegardes, .env, dépannage
│   ├── firmware/         methode_detection_onoff_zmct103c.md (déplacé de la racine)
│   ├── memoire/          mémoire IIT (une seule version suivie + images)
│   ├── maquettes/        les 13 maquettes HTML (déplacées d'AOCEDA/maquette, doublons « (1) » archivés)
│   ├── refonte/          inventaire, diagnostic, cible, journal, CHANGELOG
│   └── archives/         anciens documents périmés (avec avertissement)
├── AOCEDA/               serveur Django (nom conservé : contrat installateur, .bat, AGENTS.md)
│   ├── manage.py  installer.py  installer.bat  lancer_aoceda.bat  requirements.txt  pytest.ini  Procfile  .env.example   🔒 inchangés
│   ├── aoceda/           projet Django (settings 🔒 partiellement, urls, asgi, celery)
│   ├── apps/             accounts  sensors  analytics  alerts  dashboard  ai_assistant 🔒  (noms inchangés)
│   ├── static/           par page : js/, css/, img/, video/ (voir §5)
│   ├── templates/        pages/, partials/, admin/ (voir §5)
│   ├── outils/           scripts d'outillage maintenus (ex. serial_bridge.py si confirmé vivant)
│   ├── deploiement/      cerebrium_voix 🔒
│   └── mobile_app/       Capacitor (inchangé)
└── _a_supprimer/         quarantaine (phase 5), avec LISEZ-MOI.md ; hors du chemin d'import
```

Le firmware reste, par défaut, **à la racine** (`src/`, `include/`, `lib/`, `test/`, `platformio.ini`) : PlatformIO les
attend là, le VS Code de l'humain aussi. On le *documente* dans `docs/firmware/`.

## 3. Règles de nommage

- **Langue** : le code suit le fichier modifié (le projet mélange déjà français métier et anglais Django) ; on n'invente
  pas de renommage de masse. Dossiers et documents **en français, minuscules, sans accent, sans espace** (`maquettes`,
  `exploitation`). Interdits : `utils`, `helpers`, `misc`, `new`, `old`, `v2`, `essai`, `tmp`, `(1)`.
- **Tests** : `apps/<app>/tests/test_<sujet>.py`, un sujet par fichier, même vocabulaire que le code testé.
- **Front** : `static/js/<page>.js`, `static/css/<page>.css` ; le socle commun en `static/js/commun/` et
  `static/css/commun/` (voir §5, étape optionnelle).
- **Commits** : `type(portée): résumé`, en français.

## 4. Règles de dépendance entre applications (cible)

```
niveau 0  accounts                       (identité, droits, villes)          ne dépend de personne
niveau 1  sensors                        (appareils, mesures, interventions) -> accounts
niveau 2  analytics                      (tarifs, prévisions, historique)    -> accounts, sensors
niveau 3  alerts                         (moteur d'alertes)                  -> accounts, sensors, analytics
niveau 4  dashboard, ai_assistant        (pages / assistant)                 -> tout ce qui est plus bas
```

Aujourd'hui `accounts` importe `sensors`/`alerts`/`analytics`, `sensors` importe `alerts`/`analytics`, `analytics`
importe `alerts` (15 imports) et `ai_assistant`. Chaque dépendance « montante » est à remplacer par : (a) un
**signal** Django déjà existant, ou (b) une **fonction de service** déplacée vers le niveau bas, ou (c) un import
différé *documenté* en dernier recours. Cette partie (lot 6) se fait **fonction par fonction** avec le Gardien.

## 5. Découpage des gros modules (lot 6, réexport pour garder les imports)

| Aujourd'hui | Cible | Compatibilité |
|---|---|---|
| `analytics/views.py` (1 612 l.) | paquet `analytics/vues/` : `tableau_bord.py`, `historique.py`, `previsions.py`, `facturation.py`, `export.py` ; calculs → `analytics/services/` | `analytics/views.py` devient un module qui réexporte les mêmes noms ; `urls.py` inchangé |
| `sensors/views.py` (1 430 l.) | `sensors/vues/` : `mesures.py` (ESP32), `appareils.py`, `interventions.py`, `technicien.py` | idem ; URL et format JSON inchangés |
| `alerts/utils.py` (508 l.) | `alerts/moteur.py` | `utils.py` réexporte |
| `accounts/utils.py`, `accounts/views.py` (746 l.) | `accounts/services.py`, vues par thème | idem |
| `static/js/*.js` et `css` | inchangés au lot 5 sauf rangement validé page par page (chaque déplacement impose `?v=`+1) | — |

Les fichiers `chatbot/*` (live_agent 1 268 l., voix 1 259 l.) ne sont **pas** découpés.

## 6. Tableau « ancien chemin → nouveau chemin » (lots sûrs uniquement, à valider)

| Ancien | Nouveau | Lot | Remarque |
|---|---|---|---|
| `methode_detection_onoff_zmct103c.md` | `docs/firmware/detection-onoff-zmct103c.md` | 2 | |
| `AOCEDA/EXPLICATION_TARIFAIRE.md` | `docs/architecture/tarification-cie.md` | 2 | vérifier d'abord contre `tarifs_cie.py` |
| `AOCEDA/INSTALLATION.md` | **reste** (AGENTS.md et le .bat le citent) ; copie liée depuis `docs/developpement/` | 2 | contrat de lecture |
| `AOCEDA/Memoire_MD/` | `docs/memoire/` (version la plus récente) | 2 | choix de version : humain |
| `AOCEDA/diagrame+memoire/` | `docs/archives/memoire-v30/` ou `_a_supprimer/` | 2 / 5 | humain |
| `AOCEDA/maquette/*.html` | `docs/maquettes/` ; doublons `(1)` → `_a_supprimer/` | 2 | |
| `AOCEDA/rapport/*.html` | `docs/archives/rapports-2026-07/` | 2 | |
| `AOCEDA/_backup_presync/` | `_a_supprimer/_backup_presync/` | 5 | 0 référence |
| `AOCEDA/brain/` | `_a_supprimer/brain/` | 5 | 0 référence |
| `AOCEDA/scripts/` (essais dioula, kpi3, colab, lamia) | `_a_supprimer/scripts_essais/` ou `AOCEDA/outils/` si utile | 3 / 5 | humain, élément par élément |
| `AOCEDA/detect_dashes.py` | `AOCEDA/outils/detect_dashes.py` ou quarantaine | 3 / 5 | |
| `AOCEDA/image pour coxio.png` | `_a_supprimer/` | 5 | 0 référence |
| `AOCEDA/skills-lock.json`, `pyrefly.toml`, `pyrightconfig.json` | `.gitignore` ou conserver | 1 | réglages d'outils : humain |
| `AOCEDA/media/avatars/…` | sorti du suivi (`git rm --cached`) | 1 | fichier gardé sur disque |
| `ESSAI_VOIX_BAOULE/` (non suivi) | `.gitignore` ou archive hors dépôt | 1 | humain |
| captures `UserssilveDocuments…png` (non suivies) | supprimées du disque ou `.gitignore` | 1 | humain |
| `AOCEDA/apps/*/tests*.py` | `AOCEDA/apps/<app>/tests/test_<sujet>.py` | 4 | nombre de tests identique |
| gros modules | voir §5 | 6 | réexport |

Ne bougent pas : tout ce qui est 🔒 (§2) et la liste des contrats figés du prompt.

## 7. Décisions qui vous appartiennent

1. **Mots de passe Wi-Fi dans `src/main.cpp`** : modification locale non commitée. Je ne la commiterai jamais. Voulez-vous la sortir du fichier (en-tête non suivi) ? Cela touche le firmware : seulement sur demande.
2. **`AOCEDA/db.sqlite3` suivi par Git** : à laisser (règle actuelle d'AGENTS.md) ou à sortir du suivi ? Mon avis : laisser tel quel pendant la refonte, en parler après.
3. **Suppression vs archivage** de `_backup_presync`, `brain`, `scripts/` d'essai, `maquette/(1)`, `image pour coxio.png`, `diagrame+memoire` (version V30 ou V41 à garder ?).
4. **Deux environnements** `venv` et `.venv_local` : supprimer `venv` du disque (local, non suivi) ?
5. **Dossier `firmware/`** : déplacer ou laisser à la racine (je recommande de laisser).
6. **Installer `ruff`, `vulture`, `coverage` dans un environnement jetable** (pas dans `requirements.txt`) pour diagnostiquer le code mort ?
7. **Zones protégées** : par défaut, aucune ne bouge. Souhaitez-vous un plan écrit pour `tests_chatbot/` ou `chatbot/` ? Mon avis : non, jamais dans cette refonte.
8. **Découpage des vues** (lot 6) : à faire, ou s'arrêter après le lot 5 (aucun risque métier) ? C'est la partie à risque d'argent (tarification).

## 8. Ordre des lots et risques

| Lot | Contenu | Risque | Preuve exigée |
|---|---|---|---|
| 1 | Hygiène : `.gitignore`, sortie du suivi de `media/`, rangement des fichiers égarés non suivis | très faible | `git status`, check-list |
| 2 | Documentation et `.md` déplacés vers `docs/` | très faible | liens valides |
| 3 | Scripts et outillage (`outils/`), chemins relatifs, exécution réelle | faible | chaque script lancé |
| 4 | Rangement des tests | faible à moyen | même nombre de tests |
| 5 | Statique et gabarits (optionnel, par page) | moyen | `{% static %}`/`include` résolus, `?v=`+1, Playwright |
| 6 | Python : services, vues en paquets, cycles | **élevé** | tests, URL identiques, relecture Gardien |
| 7 | Settings / URL / Celery / ASGI | **très élevé** | à ne faire que si nécessaire |
| 5′ | Quarantaine `_a_supprimer/` puis suppression validée | moyen | liste validée élément par élément |
| 6′ | Documentation finale + recette en clone neuf | — | recette phase 7 |

**Plan en 10 lignes** : (1) hygiène Git ; (2) `docs/` créé et `.md` rangés ; (3) scripts d'essai vers `outils/` ou quarantaine ;
(4) tests rangés par app, mêmes assertions ; (5) front inchangé, sauf rangement validé page par page ; (6) vues géantes découpées
en paquets avec réexport ; (7) cycles d'import réduits fonction par fonction ; (8) quarantaine puis suppression validée ;
(9) documentation complète vérifiée par script de liens ; (10) recette en clone neuf. Chaque étape : annonce, avis du Gardien,
exécution `git mv`, contrôle, commit local.

**Risques principaux** : la tarification (argent) en lot 6, la cascade CSS (`refonte-*`) en lot 5, les références invisibles
(chaînes, Celery, `.bat`, Capacitor), des suites de tests très lentes (jusqu'à 30+ min). Aucun workflow CI n'existe : le
Gardien manuel est le seul filet.
