"""Configuration du chatbot : clés et dossiers, lus dans les réglages Django (aoceda/settings.py, qui lit le .env).

Les clés ne sont écrites nulle part dans le code : elles viennent du .env d'AOCEDA (modèle sans valeurs : .env.example).
Dossiers :
  - MODELES : modèles d'écoute (dioula 1B, baoulé 300M), Whisper, voix de secours Kokoro, voix modèle baoulé ;
  - DONNEES_IA : ce que l'assistant écrit en marchant (mémoire des conversations, voix déjà faites, journaux...).
Par défaut ils sont DANS le projet (AOCEDA/donnees_ia, ignoré par git, rempli par `manage.py installer_modeles_ia`) ;
le .env peut les placer ailleurs (CHATBOT_DOSSIER_IA), par exemple sur un autre disque.
"""
import os
from pathlib import Path

from django.conf import settings

PAQUET = Path(__file__).resolve().parent                  # apps/ai_assistant/chatbot
DONNEES = PAQUET / "donnees"                              # lexiques, carnet de sens, phrases types (versionnés)
RAPPORTS = PAQUET.parent / "rapports"                     # résultats des essais du laboratoire (menu « Tests et rapports »)
DOCUMENTATION = RAPPORTS / "documentation"                # bilans des étapes, audit, plans
RESULTATS = RAPPORTS / "resultats"
CAPTURES = RESULTATS / "captures"                         # captures d'écran des essais dans le navigateur
AUDIOS_TESTS = RAPPORTS / "audios"                        # vocaux de test et voix enregistrées
# code de la page de l'assistant : son empreinte est la « version de la page » (une page restée ouverte pendant une
# mise à jour est priée de se recharger avant un appel Live)
PAGE = Path(settings.BASE_DIR) / "static" / "js" / "assistant.js"

DOSSIER_IA = Path(settings.CHATBOT_DOSSIER_IA)
MODELES = DOSSIER_IA / "modeles"
CACHE = DOSSIER_IA / "cache"                              # conversations, voix déjà faites, réserves Live, raccourcis
JOURNAUX = DOSSIER_IA / "journaux"                        # journal des échanges, erreurs
for _d in (CACHE / "tmp", JOURNAUX):
    _d.mkdir(parents=True, exist_ok=True)

# Clés et réglages lus par certains modules avec os.environ (comme au laboratoire) : recopiés depuis les réglages
# Django, qui lisent le .env (python-decouple ne remplit pas os.environ).
for _nom in ("NIUTRANS_API_KEY", "OPENROUTER_KEY_AGENT", "CEREBRIUM_PROJECT", "CEREBRIUM_API_KEY",
             "CEREBRIUM_SERVICE_ACCOUNT_TOKEN", "HF_TOKEN"):
    if getattr(settings, _nom, "") and not os.environ.get(_nom):
        os.environ[_nom] = getattr(settings, _nom)
for _nom, _valeur in (("CHATBOT_GPU_MINUTES_JOUR", settings.CHATBOT_GPU_MINUTES_JOUR),
                      ("CHATBOT_VOIX_BAOULE_GPU", "1" if settings.CHATBOT_VOIX_BAOULE_GPU else "0"),
                      ("CHATBOT_VOIX_BAOULE", "1" if settings.CHATBOT_VOIX_BAOULE else "0"),
                      ("CHATBOT_BAOULE_CHAINE", "1" if settings.CHATBOT_BAOULE_CHAINE else "0"),
                      ("CHATBOT_ONNX_RESERVE", settings.CHATBOT_ONNX_RESERVE),
                      ("CHATBOT_PORT_OMNIVOICE", settings.CHATBOT_PORT_OMNIVOICE)):
    os.environ.setdefault(_nom, str(_valeur))

CONFIG = {
    "GEMINI_API_KEY": settings.GEMINI_API_KEY,
    "DEEPSEEK_API_KEY": settings.DEEPSEEK_API_KEY,
    "DEEPSEEK_API_URL": settings.DEEPSEEK_API_URL,
    "DEEPSEEK_MODEL": settings.DEEPSEEK_MODEL,
    # DeepSeek (cerveau), Whisper sur le serveur (micro), voix Microsoft / Kokoro (Écouter)
    "MODELE_WHISPER": settings.CHATBOT_WHISPER,          # small = précis (~4 s) ; base = rapide (~1,5 s)
    # Agent Live : comptes Gemini DANS L'ORDRE (compte 1 = GEMINI_API_KEY, puis GEMINI_API_KEY_2, _3...), combinés aux
    # modèles (cles_gemini.Reserves : meilleur modèle sur tous les comptes, puis le suivant). Ordre des modèles Live
    # (meilleur d'abord) : liste par défaut dans live_agent.MODELES_LIVE ; CHATBOT_MODELES_LIVE pour en imposer une autre.
    "MODELES_LIVE": list(settings.CHATBOT_MODELES_LIVE),
    "GEMINI_CLES_LIVE": list(settings.GEMINI_CLES_LIVE),
}
