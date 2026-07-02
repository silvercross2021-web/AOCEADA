# Charge l'application Celery au démarrage de Django si Celery est installé.
# Sans Celery/Redis (poste de développement), le projet fonctionne normalement :
# la détection d'anomalies est alors déclenchée à la réception des mesures.
try:
    from .celery import app as celery_app  # noqa: F401
    __all__ = ('celery_app',)
except ImportError:
    pass
