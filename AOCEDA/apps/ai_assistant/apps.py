import os
import sys

from django.apps import AppConfig  # pyrefly: ignore [untyped-import]


class AiAssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'  # pyrefly: ignore
    name = 'apps.ai_assistant'

    def ready(self):
        # Précharge l'assistant (Whisper, écoute dioula et baoulé, voix : ~10 s en arrière-plan) dès le démarrage du
        # SERVEUR, comme au laboratoire : la 1re question n'attend pas. Pas pour migrate / test / createsuperuser... (rien
        # à charger), ni dans le processus qui surveille les fichiers (runserver sans --noreload : seul le processus
        # serveur, RUN_MAIN=true, charge). Sinon, chargement à la 1re ouverture de la page (/api/assistant/config).
        serveur = 'runserver' in sys.argv and ('--noreload' in sys.argv or os.environ.get('RUN_MAIN') == 'true')
        serveur = serveur or any(n in os.path.basename(sys.argv[0]).lower() for n in ('daphne', 'uvicorn', 'gunicorn'))
        if serveur:
            from .chatbot.demarrage import prechauffer
            prechauffer()
