"""
Configuration Celery du projet AOCEDA (mémoire §6.4.1).

Le moteur de détection d'anomalies est planifié toutes les 5 minutes via
Celery Beat, avec Redis comme broker. En développement sans Redis, la
détection reste déclenchée de manière synchrone à la réception des mesures
(apps/sensors/views.py), donc le système fonctionne sans Celery.

Lancement :
    celery -A aoceda worker -l info
    celery -A aoceda beat -l info
"""
import os

from celery import Celery  # pyrefly: ignore [missing-import]  # dépendance optionnelle (prod)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aoceda.settings')

app = Celery('aoceda')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Planification : détection d'anomalies toutes les 5 minutes (compromis
# réactivité / charge serveur retenu dans le mémoire).
app.conf.beat_schedule = {
    'detection-anomalies-5-min': {
        'task': 'apps.alerts.tasks.detecter_anomalies',
        'schedule': 300.0,
    },
}
