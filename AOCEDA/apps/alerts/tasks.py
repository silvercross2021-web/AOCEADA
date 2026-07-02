"""
Tâche Celery planifiée : moteur de détection d'anomalies par règles
configurables (mémoire §6.4.1 — exécution toutes les 5 minutes).
"""
from datetime import timedelta

try:
    from celery import shared_task  # pyrefly: ignore [missing-import]  # dépendance optionnelle (prod)
except ImportError:  # Celery non installé : la détection synchrone prend le relais
    def shared_task(func):
        return func


@shared_task
def detecter_anomalies():
    """Évalue les mesures récentes (5 dernières minutes) de tous les clients."""
    from django.utils import timezone  # pyrefly: ignore [untyped-import]
    from apps.accounts.models import Client
    from apps.sensors.models import MesureEnergie
    from .utils import evaluate_measurements

    cutoff = timezone.now() - timedelta(minutes=5)
    clients_concernes = (
        MesureEnergie.objects.filter(timestamp__gte=cutoff)
        .values_list('capteur__client_id', flat=True)
        .distinct()
    )

    total = 0
    for client_id in clients_concernes:
        try:
            client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            continue
        sensor_ids = set(
            MesureEnergie.objects.filter(
                timestamp__gte=cutoff, capteur__client=client
            ).values_list('capteur_id', flat=True)
        )
        evaluate_measurements(client, sensor_ids)
        total += 1

    return f"{total} client(s) évalué(s)"
