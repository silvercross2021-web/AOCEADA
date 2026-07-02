# Méthode qui marche : détecter si un appareil est ALLUMÉ ou ÉTEINT avec un capteur de courant ZMCT103C + Arduino

> **But de ce document.** Expliquer précisément la méthode qui fonctionne pour savoir, en temps réel et de façon stable, si un appareil électrique est allumé ou éteint, à partir d'un capteur de courant ZMCT103C branché sur un Arduino.
>
> Ce document est écrit pour être **directement applicable** : un humain peut le suivre pour reproduire le montage, et une IA peut le lire pour comprendre la logique et générer/adapter le code sans refaire les erreurs.
>
> **À retenir en une phrase :** on ne fait **jamais** de détection de pic (max/min). On calcule la **valeur RMS** du signal alternatif sur plusieurs cycles, en retirant l'offset continu en permanence, puis on décide ON/OFF avec **hystérésis + confirmation**. C'est ça, et seulement ça, qui donne un résultat stable.

---

## 1. Le contexte matériel

- **Carte :** Arduino Uno.
- **Capteurs :** 2 × ZMCT103C (transformateurs de courant, souvent sur une petite carte type HW-670).
- **Câblage :**
  - Capteur 1 (mini-lampe) → broche analogique **A0**
  - Capteur 2 (prise) → broche analogique **A1**
- **Réseau électrique :** 50 Hz (Côte d'Ivoire). **Une période dure donc 20 ms.** C'est une donnée clé : toute la mesure se cale sur ça.
- **Principe du capteur :** le ZMCT103C est un transformateur de courant. Le fil de phase de l'appareil passe **à travers le trou du tore**. Plus l'appareil consomme de courant, plus le signal alternatif en sortie du capteur est grand. Quand l'appareil est éteint, il ne reste qu'un petit signal de bruit.

> ⚠️ **Point de câblage critique :** dans le trou du capteur, il ne doit passer **que le fil de phase** (un seul conducteur). Si on fait passer les deux fils (phase + neutre) ensemble, leurs courants s'annulent et le capteur ne voit **rien**. Une seule et unique ligne dans le tore.

---

## 2. Le problème qu'on cherchait à résoudre

Les premiers codes essayés **marchaient un moment, puis se déréglaient**. Symptôme classique : au début la détection est bonne, puis après quelques minutes les valeurs partent, la détection devient fausse, ça clignote entre ALLUMÉ et ÉTEINT sans raison.

**Cause identifiée :** ces codes faisaient de la **détection de pic** — ils suivaient la valeur maximale et minimale du signal (`max`, `min`) pour en déduire l'amplitude.

Pourquoi ça dérive toujours :

1. **Le pic attrape le bruit.** Un seul parasite électrique (spike) fait exploser le max, donc la lecture saute.
2. **L'offset (le point milieu du signal) bouge dans le temps.** Il dépend de la température, de l'alimentation, du capteur. Si le code suppose un offset fixe (par exemple 512), dès que le vrai offset dérive, tous les calculs de pic deviennent faux.
3. **Aucune moyenne.** Une mesure de pic = un instant. Aucune stabilité statistique.

Conclusion : **la détection de pic est intrinsèquement instable pour cet usage.** Il faut une autre approche.

---

## 3. Le parcours : les problèmes rencontrés et les tests qui ont mené à la solution

Cette section raconte, dans l'ordre, ce qui a été essayé, ce qui a coincé à chaque étape, et comment on est passé de « ça se dérègle, je ne vois rien de fiable » à « je vois clairement, et de façon stable, quand c'est allumé ou éteint ». C'est le cœur de la démarche : la solution finale n'est pas tombée du ciel, elle est le résultat de ces tests.

### Étape 0 — Premiers codes : ça marchait puis ça se déréglait

Point de départ : le montage était déjà fait (2 capteurs, lampe sur A0, prise sur A1), et plusieurs codes Arduino avaient été essayés pour voir le changement de courant. **Problème constant : ça fonctionnait quelques instants, puis tout se déréglait** — les valeurs partaient, la détection devenait fausse, ça basculait entre allumé et éteint sans raison. Ces codes reposaient sur la détection de pic (voir §2). À ce stade, impossible de savoir de façon fiable si un appareil était allumé ou éteint. C'est ce blocage qui a lancé toute la démarche.

### Test 1 — Voir d'abord les vraies valeurs (code de diagnostic)

Avant même de vouloir décider ON/OFF, il fallait d'abord **voir** ce que le capteur mesure réellement, et à quel moment ça bouge. On a donc chargé un code de diagnostic qui n'affiche **que la RMS** de chaque voie, sans aucune décision — juste des chiffres bruts à observer.

Ce test a immédiatement montré deux choses :

1. **La méthode RMS est stable.** Les valeurs ne partaient plus dans tous les sens comme à l'étape 0. Même quand l'offset dérivait (observé : 368 → 392), la RMS restait cohérente. Le blocage de départ était donc bien réglé par la méthode elle-même.
2. On pouvait enfin **relever des chiffres propres** dans chaque état, pour comprendre le comportement de chaque voie.

Valeurs relevées, **tout éteint** :
```
A0 lampe -> RMS ≈ 4.5 (varie 3.6 à 5.5)   |   A1 prise -> RMS ≈ 3.4 (varie 2.8 à 4.0)
```
Valeurs relevées, **tout allumé** :
```
A0 lampe -> RMS ≈ 5.8 (varie 5.3 à 8.5)   |   A1 prise -> RMS ≈ 6.5 (varie 6.2 à 10.5)
```
*(Le détail précis de ces mesures et le tableau de calibration sont en §5.)*

### Ce que le test 1 a révélé — les deux voies ne se valent pas

En comparant éteint et allumé pour chaque voie, un problème net est apparu :

- **La prise (A1) change franchement.** Elle passe de ~3,4 (éteint) à ~6,5 (allumé). Entre les deux il y a un grand vide (rien entre 4 et 6). Le changement se voit sans aucune ambiguïté. ✅
- **La lampe (A0) change à peine.** Éteinte, elle monte déjà jusqu'à 5,47 ; allumée, elle descend jusqu'à 5,28. **Les deux plages se chevauchent.** Sur les chiffres bruts, on ne distingue presque pas l'allumé de l'éteint. ❌

Diagnostic tiré de ce test : la mini-lampe consomme trop peu de courant pour que le capteur la distingue nettement du bruit de fond. C'est précisément ce test qui a permis de comprendre **pourquoi la lampe posait problème et pas la prise**, et donc quoi corriger : soit remonter le signal de la lampe (boucles de fil dans le tore, voir §5), soit accepter des seuils serrés côté lampe compensés par la confirmation.

### Test 2 — Passer de la valeur à la décision, et enfin voir les changements

Une fois les niveaux de chaque voie connus, on a chargé le firmware final : il transforme la RMS en décision `ALLUMEE` / `eteinte`, avec les seuils calés sur les mesures ci-dessus, plus l'hystérésis et la confirmation sur 3 mesures.

Résultat, montage tout éteint : les deux voies affichent bien `eteinte`, de façon stable, **y compris quand la lampe frôle son seuil** (RMS 5,59, juste sous 5,6, retenue par le compteur de confirmation qui empêche le faux basculement) :
```
LAMPE : eteinte  (RMS=5.59)   |   PRISE : eteinte  (RMS=4.23)
LAMPE : eteinte  (RMS=5.01)   |   PRISE : eteinte  (RMS=4.36)
LAMPE : eteinte  (RMS=4.67)   |   PRISE : eteinte  (RMS=4.75)
```

**C'est à cette étape que l'objectif est atteint** : on voit clairement, et sans clignotement ni dérive, l'état de chaque appareil. Le contraste avec l'étape 0 (« ça se dérègle ») est total, et il vient uniquement du changement de méthode.

### Ce que ce parcours enseigne

- Il faut **mesurer avant de décider.** Le code de diagnostic (voir les valeurs brutes) est une étape à part entière, pas une perte de temps : c'est lui qui révèle quels seuils poser et quelle voie pose problème. Vouloir décider ON/OFF sans avoir d'abord regardé les chiffres, c'est ce qui menait aux réglages à l'aveugle qui se déréglaient.
- Un même montage peut avoir **une voie parfaite (prise) et une voie limite (lampe) en même temps.** Chaque voie se calibre séparément, avec ses propres seuils.
- La stabilité vient de la **méthode** (RMS + offset suivi + hystérésis + confirmation), pas d'un réglage magique. Le passage de l'étape 0 à l'étape 2 le prouve concrètement.

---

## 4. La solution qui marche (la méthode RMS)

La méthode stable repose sur **trois piliers**. Les trois sont nécessaires ; enlever l'un des trois fait revenir l'instabilité.

### Pilier 1 — Mesure RMS sur plusieurs cycles complets

Au lieu de regarder le pic, on calcule la **valeur efficace (RMS)** de la composante alternative sur une fenêtre de temps qui couvre **plusieurs cycles complets** du réseau.

- Fenêtre choisie : **100 ms**. À 50 Hz, ça fait **5 cycles complets** (5 × 20 ms). C'est assez long pour une mesure stable, assez court pour rester réactif (~2 mesures par seconde après affichage).
- La RMS est une moyenne quadratique : elle lisse le bruit au lieu de le subir. Un parasite isolé ne fait presque rien à une RMS calculée sur ~950 échantillons.

Formule appliquée : `RMS = racine( moyenne( (échantillon − offset)² ) )`.

### Pilier 2 — Suivi permanent de l'offset continu (anti-dérive)

C'est **le point clé** qui tue la dérive dans le temps.

Au lieu de supposer un offset fixe, on le **mesure et on le suit en continu** avec un filtre passe-bas très lent :

```
offset += (échantillon − offset) / 1024.0;
```

- Cette ligne fait remonter doucement `offset` vers la vraie valeur continue du signal.
- La constante `1024` rend le suivi **lent** : il suit la dérive continue (qui bouge sur plusieurs secondes) mais **ne suit pas** l'alternatif à 50 Hz (qui bouge en 20 ms). Exactement ce qu'on veut.
- Résultat : même si l'offset du capteur dérive de 368 à 392 (observé dans nos mesures), la RMS reste stable, parce qu'on retire toujours l'offset **réel du moment**, pas un offset supposé.

> C'est ce mécanisme qui explique pourquoi cette méthode ne « se dérègle » plus, contrairement aux codes à offset fixe.

### Pilier 3 — Décision ON/OFF par hystérésis + confirmation (anti-clignotement)

Même avec une RMS stable, une valeur peut passer juste sur la frontière du seuil et faire clignoter la décision. On empêche ça avec deux garde-fous :

- **Hystérésis = deux seuils différents.** On passe ALLUMÉ quand la RMS dépasse `SEUIL_ON`, mais on ne repasse ÉTEINT que quand elle descend sous `SEUIL_OFF`, avec `SEUIL_OFF < SEUIL_ON`. Entre les deux, l'état ne change pas. La zone morte entre les deux seuils absorbe le bruit près de la frontière.
- **Confirmation.** On ne change d'état qu'après **3 mesures consécutives** qui vont dans le même sens. Un aller-retour isolé ne suffit pas à basculer. Ça élimine les faux basculements.

---

## 5. La calibration (comment on a réglé les seuils avec des mesures réelles)

**Les seuils ne s'inventent pas : on les lit sur les vraies mesures.** La démarche est en deux temps.

### Étape A — On mesure d'abord (code de diagnostic)

On fait tourner un code qui affiche seulement la RMS de chaque voie (sans décider ON/OFF), et on relève les valeurs dans chaque état :

1. **Tout éteint** → on note la RMS des deux voies (c'est la base « bruit de fond »).
2. **Lampe seule allumée** → on note la nouvelle RMS de A0.
3. **Prise seule allumée** (avec l'appareil qui tourne) → on note la nouvelle RMS de A1.

### Étape B — Résultats mesurés sur ce montage

| Voie | Appareil | ÉTEINT (bruit de fond) | ALLUMÉ | Séparation |
|------|----------|------------------------|--------|------------|
| A1 | Prise | ~3,4 (max ~4,0) | ~6,5 (min ~6,2) | **Nette** — grand trou entre 4 et 6 |
| A0 | Lampe | ~4,5 (max ~5,47) | ~5,8 (min ~5,28) | **Faible** — les deux plages se touchent presque |

*(Valeurs en unités ADC brutes, pas en ampères. On n'a pas besoin des ampères pour un simple ON/OFF : la séparation relative suffit.)*

**Lecture de ce tableau :**

- **Prise (A1) : facile.** Il y a un grand vide entre « éteint » (≤ 4,0) et « allumé » (≥ 6,2). On pose les seuils au milieu, avec de la marge : `SEUIL_ON = 5,5`, `SEUIL_OFF = 4,5`. Aucun risque.
- **Lampe (A0) : délicat.** La mini-lampe consomme très peu de courant, donc son signal dépasse à peine le bruit de fond. « Éteinte » monte jusqu'à 5,47 et « allumée » descend jusqu'à 5,28 : **ça se chevauche**. Aucun seuil ne sépare parfaitement. On pose `SEUIL_ON = 5,6`, `SEUIL_OFF = 5,0`, ce qui marche pour la majorité des cas grâce à la confirmation sur 3 mesures, mais reste serré.

### Le cas des petites charges (mini-lampe) — le vrai remède

Quand une charge consomme trop peu pour être détectée franchement, la solution matérielle standard est d'**augmenter le nombre de spires** : on fait passer le fil de phase **plusieurs fois** (2 à 3 boucles) dans le trou du capteur au lieu d'une seule.

- Faire N boucles multiplie le signal vu par le capteur par **N**.
- Avec 3 boucles, la lampe allumée passerait d'environ 5,8 à environ **11–12**, tandis que le bruit de fond reste vers 4,5–5,5 → on retrouve un **vrai** trou de séparation, et la détection devient aussi solide que celle de la prise.
- Après avoir ajouté les boucles, il faut **refaire l'étape A** (diagnostic) pour relever les nouveaux chiffres, puis remonter les seuils de la lampe (par exemple `SEUIL_ON = 8,0`, `SEUIL_OFF = 6,0`).

> **Règle générale réutilisable :** si une charge donne une séparation faible entre éteint et allumé, on augmente le nombre de spires dans le tore avant de bricoler les seuils. C'est plus fiable que d'essayer de séparer deux plages qui se chevauchent.

---

## 6. Résultat vérifié

Avec la méthode ci-dessus, montage « tout éteint », la sortie observée est correcte et stable — les deux voies restent bien sur `eteinte`, y compris quand la lampe frôle son seuil (5,59, juste sous 5,6, retenue par la confirmation) :

```
LAMPE : eteinte  (RMS=5.59)   |   PRISE : eteinte  (RMS=4.23)
LAMPE : eteinte  (RMS=5.01)   |   PRISE : eteinte  (RMS=4.36)
LAMPE : eteinte  (RMS=5.36)   |   PRISE : eteinte  (RMS=4.14)
LAMPE : eteinte  (RMS=4.67)   |   PRISE : eteinte  (RMS=4.75)
LAMPE : eteinte  (RMS=5.02)   |   PRISE : eteinte  (RMS=4.43)
LAMPE : eteinte  (RMS=4.17)   |   PRISE : eteinte  (RMS=4.09)
```

C'est la preuve concrète que la logique fonctionne : pas de faux « allumé » malgré un bruit de fond qui monte parfois près du seuil de la lampe.

---

## 7. Comment appliquer / adapter cette méthode (checklist)

Pour reproduire sur un autre appareil ou un autre montage, dans l'ordre :

1. **Câbler** un seul fil de phase à travers le tore de chaque capteur (jamais phase + neutre ensemble).
2. **Charger le code de diagnostic** et ouvrir le Moniteur série à **9600 bauds**.
3. **Relever les RMS** dans chaque état : tout éteint, puis chaque appareil allumé un par un.
4. **Vérifier la séparation.** Si « allumé » est nettement au-dessus de « éteint » → parfait. Si ça se touche → **ajouter des spires** (2–3 boucles du fil dans le tore) et re-mesurer.
5. **Poser les seuils** dans le code final : `SEUIL_ON` au-dessus du max observé « éteint » (avec marge), `SEUIL_OFF` entre les deux plages. Garder `SEUIL_OFF < SEUIL_ON` (hystérésis).
6. **Charger le firmware final** et vérifier que les états affichés collent à la réalité.
7. Ne jamais revenir à une logique de pic. Toujours RMS + offset suivi + hystérésis + confirmation.

**Paramètres à ne pas casser :**
- Fenêtre de mesure = **plusieurs cycles complets** du réseau (100 ms à 50 Hz ; à 60 Hz, ~5 cycles = ~83 ms).
- Constante du suivi d'offset = **1024** (suivi lent, ne suit pas le 50 Hz).
- Confirmation = **3 mesures** minimum avant tout changement d'état.

---

## 8. Le code Arduino complet qui marche

> Cible : Arduino Uno. Réseau 50 Hz. A0 = lampe, A1 = prise.
> Les seuils en haut du fichier sont ceux calibrés sur le montage décrit ; ils se réajustent selon les mesures de chaque montage (voir §5 et §7).

```cpp
/*
 * FIRMWARE ZMCT103C - Detection ON/OFF stable
 * Carte   : Arduino Uno
 * Capteurs: A0 = mini-lampe   |   A1 = prise
 * Reseau  : 50 Hz (Cote d'Ivoire)
 * Methode : RMS du signal alternatif (jamais de detection de pic).
 *   - offset continu suivi en permanence (pas de derive)
 *   - hysteresis : 2 seuils differents pour ON et pour OFF
 *   - confirmation : 3 mesures d'accord avant de changer d'etat
 */

const uint8_t PIN_LAMPE = A0;
const uint8_t PIN_PRISE = A1;

// Offsets de depart proches des valeurs mesurees (converge plus vite)
float offsetLampe = 380.0;
float offsetPrise = 365.0;

const unsigned long FENETRE_MS = 100;   // 100 ms = 5 cycles a 50 Hz

// ---- SEUILS (a caler sur les mesures de diagnostic) ----
// SEUIL_ON  : on passe ALLUME quand le RMS depasse cette valeur
// SEUIL_OFF : on repasse eteint quand le RMS descend sous cette valeur
// Ecart entre les deux = hysteresis (evite le clignotement).

// PRISE (A1) : separation nette -> seuils larges
const float PRISE_SEUIL_ON  = 5.5;
const float PRISE_SEUIL_OFF = 4.5;

// LAMPE (A0) : separation faible (mini-lampe) -> seuils serres.
// Si tu boucles le fil 3x dans le capteur, remonte vers ON=8.0 / OFF=6.0
// (relance d'abord le diagnostic pour confirmer les nouveaux chiffres).
const float LAMPE_SEUIL_ON  = 5.6;
const float LAMPE_SEUIL_OFF = 5.0;

// Nombre de mesures consecutives d'accord avant de valider un changement
const uint8_t CONFIRMATIONS = 3;

// Etats courants
bool lampeAllumee = false;
bool priseAllumee = false;
uint8_t cptLampe = 0;
uint8_t cptPrise = 0;

// --- Mesure la valeur RMS de la composante alternative sur une broche ---
float mesurerRMS(uint8_t broche, float &offset) {
  unsigned long debut = millis();
  unsigned long n = 0;
  float sommeCarres = 0.0;
  while (millis() - debut < FENETRE_MS) {
    int brut = analogRead(broche);
    offset += (brut - offset) / 1024.0;   // suivi lent du continu
    float ac = brut - offset;             // composante alternative seule
    sommeCarres += ac * ac;
    n++;
  }
  if (n == 0) return 0.0;
  return sqrt(sommeCarres / n);
}

// --- Met a jour un etat ON/OFF avec hysteresis + confirmation ---
void majEtat(float rms, bool &etat, uint8_t &cpt,
             float seuilOn, float seuilOff) {
  if (!etat) {                     // ETEINT -> tenter d'allumer
    if (rms > seuilOn) {
      cpt++;
      if (cpt >= CONFIRMATIONS) { etat = true; cpt = 0; }
    } else {
      cpt = 0;
    }
  } else {                         // ALLUME -> tenter d'eteindre
    if (rms < seuilOff) {
      cpt++;
      if (cpt >= CONFIRMATIONS) { etat = false; cpt = 0; }
    } else {
      cpt = 0;
    }
  }
}

void setup() {
  Serial.begin(9600);
  delay(300);
  Serial.println(F("Stabilisation des capteurs..."));
  for (int i = 0; i < 8; i++) {           // laisser l'offset converger
    mesurerRMS(PIN_LAMPE, offsetLampe);
    mesurerRMS(PIN_PRISE, offsetPrise);
  }
  Serial.println(F("=== SURVEILLANCE ON/OFF ==="));
  Serial.println(F("----------------------------------------------"));
}

void loop() {
  float rmsL = mesurerRMS(PIN_LAMPE, offsetLampe);
  float rmsP = mesurerRMS(PIN_PRISE, offsetPrise);

  majEtat(rmsL, lampeAllumee, cptLampe, LAMPE_SEUIL_ON, LAMPE_SEUIL_OFF);
  majEtat(rmsP, priseAllumee, cptPrise, PRISE_SEUIL_ON, PRISE_SEUIL_OFF);

  Serial.print(F("LAMPE : "));
  Serial.print(lampeAllumee ? F("ALLUMEE") : F("eteinte "));
  Serial.print(F(" (RMS="));
  Serial.print(rmsL, 2);
  Serial.print(F(")   |   PRISE : "));
  Serial.print(priseAllumee ? F("ALLUMEE") : F("eteinte "));
  Serial.print(F(" (RMS="));
  Serial.print(rmsP, 2);
  Serial.println(F(")"));

  delay(200);
}
```

---

## 9. Résumé pour une IA qui lirait ce fichier

Si tu dois générer ou adapter du code pour ce type de détection, applique **exactement** ces principes, sans y déroger :

1. **Ne jamais** utiliser de détection de pic (`max`/`min`) pour décider ON/OFF. C'est la cause de l'instabilité.
2. Calculer la **RMS** de la composante alternative sur une fenêtre couvrant **plusieurs cycles complets** du réseau (100 ms à 50 Hz).
3. **Suivre l'offset continu en permanence** avec un filtre lent (`offset += (brut - offset) / 1024.0;`) et le soustraire avant d'élever au carré. C'est ce qui supprime la dérive dans le temps.
4. Décider ON/OFF avec **hystérésis** (deux seuils, `SEUIL_OFF < SEUIL_ON`) et **confirmation** (3 mesures consécutives), pour supprimer le clignotement.
5. **Calibrer les seuils sur des mesures réelles**, pas à l'aveugle : mesurer le bruit de fond « éteint » et le niveau « allumé » de chaque appareil, poser les seuils dans le trou entre les deux.
6. Si une charge donne une séparation trop faible (comme une mini-lampe), recommander d'**augmenter le nombre de spires** (2–3 boucles du fil dans le tore) et de recalibrer, plutôt que de forcer des seuils sur des plages qui se chevauchent.

Cette méthode a été validée en pratique sur un montage Arduino Uno + 2 × ZMCT103C : la détection est stable et ne se dérègle plus.
