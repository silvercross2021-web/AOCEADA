# templates/ : gabarits HTML

| Fichier | Page |
|---|---|
| `index.html` | vitrine publique `/` |
| `aoceda-auth.html` | connexion `/auth/` |
| `aoceda-dashboard.html`, `aoceda-historique.html`, `aoceda-alertes.html`, `aoceda-interventions.html`, `aoceda-previsions.html` (facturation), `aoceda-parametres.html` | espace client |
| `aoceda-technicien.html` | espace technicien |
| `aoceda-ia.html` + `assistant.html` | assistant IA : `/ia/` (gabarit AOCEDA) contient le cadre `/ia/assistant/` |
| `partials/` | barre latérale et barre du bas du client (partagées) |
| `admin/` | personnalisation de l'administration Django (Jazzmin) |

Les gabarits sont à plat : les vues y font référence par leur nom (`render(request, 'aoceda-xxx.html')`). Ne pas les
déplacer sans corriger toutes les vues.
