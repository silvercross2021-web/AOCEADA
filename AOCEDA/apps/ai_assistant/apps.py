import sys
import threading

from django.apps import AppConfig  # pyrefly: ignore [untyped-import]

class AiAssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'  # pyrefly: ignore
    name = 'apps.ai_assistant'

    def ready(self):
        # Précharge le modèle STT dioula (Meta MMS, ~667 Mo) en arrière-plan au
        # démarrage — sinon la PREMIÈRE question vocale en dioula attend ce
        # chargement (~2s) en plus de la transcription elle-même. Seulement pour
        # `runserver` : `migrate`/`test`/etc. n'en ont pas besoin et ne doivent
        # pas être ralentis par le chargement d'un modèle ONNX de 667 Mo.
        if 'runserver' in sys.argv:
            def _preload():
                from .dioula import _charger_stt
                _charger_stt()
            threading.Thread(target=_preload, daemon=True).start()
