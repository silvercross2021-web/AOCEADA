# 0005 · Standards de l'interface IA (/ia/) et détection de langue à deux étages

**Contexte.** L'assistant vocal énergétique d'AOCEDA doit opérer de manière fiable, accessible et sécuritaire sur
machine locale à ressources limitées (CPU sans GPU dédié), tout en garantissant une expérience utilisateur fluide sur
la plateforme web `/ia/` (communication parent-iframe, responsive mobile, mode plein écran et sécurité des coupures).

**Choix.**
1. **Étage 1 (Audio LID acoustique) : Exclusivité INT8 ONNX**
   - Éradication complète de la variante FP32 (code et poids `.pt`) au profit exclusif du modèle quantifié INT8 ONNX sur CPU.
   - Poids divisé par ~4 (129 Ko contre 493 Ko), latence médiane réduite à 17,8 ms sur CPU local, et précision de détection maintenue à 95,0 % sur les 5 langues cibles (`fra`, `eng`, `wol`, `dyu`, `bci`).
   - Seuil de décision acoustique (Gate) fixé à 0,85 : aiguillage immédiat dès le Morceau 0 si $P \ge 0{,}85$ (87,5 % des cas réels), maintien du mode concurrent sécurisé sinon.

2. **Étage 2 (Dictionnaire Lego) : Garde-fou textuel sub-milliseconde**
   - Modélisation par sous-mots ($n$-grammes de caractères) avec temps d'inférence < 0,2 ms CPU.
   - Neutralité symétrique sur signal textuel vide ou non concluant (classement en langue inconnue, aucun biais français par défaut).
   - Reconnaissance native des codes compteurs STS à 20 chiffres (avec ou sans espaces) et des nombres cardinaux dans les 5 langues.
   - **Garde-fou critique sur les ordres de coupure** : neutralisation automatique de la commande en présence d'une particule négative (*« ne coupe pas »*, *« don't cut »*).

3. **Interface utilisateur `/ia/` (Frontend)**
   - **Communication Parent-Iframe** : tout clic depuis l'en-tête de `aoceda-ia.html` transite obligatoirement par `actionQueue` dans `assistant-page.js` tant que le cadre `assistant.html` n'est pas prêt, éliminant tout clic étouffé.
   - **Mode Plein Écran Immersif** : application de la classe `.assistant-plein-ecran` (`position: fixed; inset: 0; z-index: 99999;`), activation du bouton flottant `#btn_quitter_plein_ecran` et capture de la touche `Escape`.
   - **Cartes d'action critique (Coupure électrique)** : différenciation visuelle immédiate entre l'action critique (`.cd-oui` rouge vif `#dc2626`) et l'annulation (`.cd-non` neutre `#4b5563`), avec respect strict du ratio de contraste $\ge 4.5:1$ (WCAG AA).
   - **Pérennité des tests** : la suite `tests_ui.py` (7 tests) sanctuarise le respect de ce contrat d'interface.

**Alternatives écartées.**
- *Conserver FP32 comme solution de repli* : rejeté car le modèle pèse 4 fois plus lourd sans apporter le moindre gain de précision sur les 5 langues cibles.
- *Appels directs au DOM de l'iframe sans file d'attente* : rejeté car générateur de clics perdus (race condition) lors des connexions lentes ou charges CPU.
- *Boutons de coupure gris identiques* : rejeté car source d'extinction accidentelle du réseau électrique par l'utilisateur.

