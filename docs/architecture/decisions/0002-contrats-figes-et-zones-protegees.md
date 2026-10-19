# 0002 · Contrats figés et zones protégées

**Contexte.** Plusieurs consommateurs invisibles dépendent du code : le firmware ESP32 (chemin et format de
`/api/sensors/zmct/`), l'application Android et le tunnel ngrok (URL publiques), l'installateur de tous les collaborateurs,
les noms de tâches Celery, les clés `localStorage`, les empreintes SHA-256 des modèles de l'assistant. Le moteur de
l'assistant contient des seuils mesurés sur de vrais enregistrements vocaux.

**Choix.** La liste des contrats figés et des zones protégées de [AGENTS.md](../../../AGENTS.md) §4 fait loi : on ne les
modifie que sur demande explicite et avec les suites de tests vertes. Un test peut être déplacé ou renommé, jamais
supprimé ni affaibli : le nombre de tests ne baisse pas.

**Alternatives écartées.** « Nettoyer » ces zones : aucun test ne détecte la rupture d'un contrat externe (ESP32, mobile).
