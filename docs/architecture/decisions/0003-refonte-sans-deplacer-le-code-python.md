# 0003 · Refonte du dépôt sans déplacer le code Python

**Contexte.** La refonte d'octobre 2026 visait un dépôt lisible. Le diagnostic ([02](../../refonte/02-diagnostic.md))
montre des cycles d'import entre apps, des vues de plus de 1 400 lignes et une tarification répartie sur trois fichiers.
Les tests protégés (`apps/*/tests.py`, `tests_*.py`) contiennent des `mock.patch('apps.alerts.utils.check_credit_prepaye')`,
`mock.patch('apps.alerts.utils.send_mail_async')`, `mock.patch('apps.accounts.views.send_mail_async')`, etc. Un
`mock.patch` remplace un nom **dans le module où il est utilisé** : déplacer une fonction vers un autre module, même avec un
réexport, fait que le test patche l'ancien nom et que le code appelle le nouveau. Le test passerait sans rien vérifier, ou
échouerait. Comme ces tests ne doivent pas être modifiés, le code qu'ils visent ne peut pas être déplacé en sécurité.

**Choix.** La refonte a rangé tout ce qui entoure le code (documentation, outillage, archives, fichiers générés) et a laissé
le code Python et les tests à leur place. Le découpage de `analytics/views.py` et `sensors/views.py`, la réduction des cycles
et le rangement des tests en dossiers `tests/` sont **reportés**.

**Pour les reprendre plus tard.** Il faudra d'abord obtenir l'accord écrit de modifier les tests concernés (mettre à
jour les chemins des `mock.patch`), puis traiter une fonction à la fois avec les deux suites complètes (688 + 458 tests,
environ 25 minutes en tout) après chaque pas. Ordre conseillé : tarification (argent) en dernier.

**Alternatives écartées.** Découper quand même avec réexport : trompeur pour les `mock.patch`, voir ci-dessus.
