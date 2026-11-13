# Rapport de Benchmark Live Multilingue - AOCEDA
*Généré le : 2026-10-28 04:43:20*

| Cas de Test | Mode | Ingress -> Egress | Earcon (< 300ms) | Premier Audio | Durée Totale | Statut |
|---|---|---|---|---|---|---|
| **Cas 1 : Mode 1 (FR direct natif)** | Mode 1 | `fr` -> `fr` | — | 2.801 s | 8.389 s | **SUCCÈS** |
| **Cas 2 : Mode 2 (FR -> Baoulé)** | Mode 2 | `fr` -> `bci` | — | 2.683 s | 8.144 s | **SUCCÈS** |
| **Cas 3 : Mode 2 (FR -> Dioula)** | Mode 2 | `fr` -> `dyu` | — | 2.702 s | 8.796 s | **SUCCÈS** |
| **Cas 4 : Mode 3 (Baoulé -> FR)** | Mode 3 | `bci` -> `fr` | — | 2.435 s | 6.836 s | **SUCCÈS** |
| **Cas 5 : Mode 3 (Dioula -> FR)** | Mode 3 | `dyu` -> `fr` | — | 3.323 s | 7.114 s | **SUCCÈS** |
| **Cas 6 : Mode 4 (Baoulé -> Baoulé)** | Mode 4 | `bci` -> `bci` | — | 2.223 s | 6.115 s | **SUCCÈS** |
| **Sécurité Coupure (Garde-fou)** | Mode 4 | `bci` -> `bci` | — | — | 0.005 s | **SUCCÈS (Garde-fou Actif)** |