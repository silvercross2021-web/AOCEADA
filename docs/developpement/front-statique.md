# static/ : CSS, JS, images, vidéos

Une page = un JS + un CSS du même nom que la page.

| Dossier | Contenu |
|---|---|
| `js/` | `dashboard.js`, `historique.js`, `alertes.js`, `previsions.js`, `interventions.js`, `parametres.js`, `technicien.js`, `auth.js`, `index.js`, `assistant.js` ; socle : `client-shell.js`, `refonte-shell.js`, `i18n.js`, `assistant-page.js` |
| `css/` | un CSS par page, plus `client-shell.css` (socle) et `refonte-*.css` (surcouche posée sur les CSS de page : ne pas supprimer sans vérifier la cascade) |
| `img/`, `video/` | logos, images et films de la vitrine |

Règles :
- `js/personnage.js` est **généré** : modifier `apps/ai_assistant/personnage/` puis `node construire_personnage.js`.
- Après toute modification, augmenter à la main le `?v=` du gabarit qui charge le fichier (sauf la page de l'assistant, qui
  calcule ses empreintes seule dans `apps/dashboard/views.py`).
- Les clés `localStorage` (`aoceda_access_token`, `aoceda-theme-choice`…) et les identifiants HTML lus par le JS sont des contrats.
- `staticfiles/` est le résultat de `collectstatic` : jamais suivi par Git.
