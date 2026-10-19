"""Tâche Celery planifiée : température des villes des clients, relue toutes les 6 heures (19/10/2026). La prévision
lit aussi la météo à la demande ; cette tâche évite qu'une page attende Internet après une longue pause."""
try:
    from celery import shared_task  # pyrefly: ignore [missing-import]  # dépendance optionnelle (prod)
except ImportError:  # Celery non installé : la météo est lue à la demande, au plus toutes les 6 heures
    def shared_task(func):
        return func


@shared_task
def rafraichir_meteo():
    from apps.accounts.models import Client
    from . import meteo
    villes = set(Client.objects.values_list("ville", flat=True)) or {meteo.VILLE_PAR_DEFAUT}
    return {v: meteo.rafraichir(v, forcer=True) for v in villes if v in meteo.VILLES}


@shared_task
def enregistrer_previsions():
    """Instantané de la période en cours de chaque client équipé (une fois par heure) : les GET du tableau de bord
    n'écrivent plus rien (19/10/2026)."""
    from apps.accounts.models import Client
    from .views import enregistrer_prevision
    n = 0
    for client in Client.objects.filter(capteurs__isnull=False).distinct():
        enregistrer_prevision(client)
        n += 1
    return n
