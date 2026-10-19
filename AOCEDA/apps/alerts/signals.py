"""Suivi d'une demande d'intervention (20/10/2026) : le client est PRÉVENU quand le technicien agit, dans la page
Alertes et par e-mail (s'il l'a activé), au lieu de devoir revenir regarder la page. Branché sur le modèle
Intervention : couvre aussi bien l'écran du technicien que l'administration."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone  # pyrefly: ignore [untyped-import]

from apps.sensors.models import Intervention

from .models import Alerte
from .utils import send_alert_email

LIBELLES = {'PANNE': 'votre déclaration de panne', 'CALIBRATION': 'votre demande de vérification des valeurs',
            'MAINTENANCE': 'votre demande de contrôle', 'INSTALLATION': "l'installation de votre capteur",
            'DIAGNOSTIC': 'votre diagnostic'}


@receiver(pre_save, sender=Intervention)
def _retenir_etat_avant(sender, instance, **kwargs):
    instance._avant = (Intervention.objects.filter(pk=instance.pk).values('statut', 'dateProgrammee').first()
                       if instance.pk else None)


def _prevenir(iv, message, severite='Info'):
    alerte = Alerte.objects.create(client=iv.client, type='INTERVENTION', message=message, sévérité=severite, intervention=iv)
    send_alert_email(alerte)


@receiver(post_save, sender=Intervention)
def _prevenir_le_client(sender, instance, created, **kwargs):
    avant = getattr(instance, '_avant', None)
    if created or not avant or not instance.client_id or getattr(instance, '_silencieux', False):
        return
    quoi = LIBELLES.get(instance.typeIntervention, 'votre demande')
    tech = instance.technicien.nom if instance.technicien_id else 'Un technicien'
    if instance.statut != avant['statut']:
        if instance.statut == 'EN_COURS':
            _prevenir(instance, f"{tech} a pris en charge {quoi}.")
        elif instance.statut == 'TERMINEE':
            _prevenir(instance, f"L'intervention concernant {quoi} est terminée. Consultez le résultat des travaux et "
                                "donnez votre avis dans la rubrique « Interventions ».")
        elif instance.statut == 'ANNULEE':
            _prevenir(instance, f"La demande concernant {quoi} a été annulée par votre technicien.", 'Avertissement')
        return
    if instance.dateProgrammee and instance.dateProgrammee != avant['dateProgrammee'] and instance.statut in ('EN_ATTENTE', 'EN_COURS'):
        quand = timezone.localtime(instance.dateProgrammee).strftime('%d/%m/%Y à %H:%M')
        _prevenir(instance, f"Rendez-vous fixé : {tech} interviendra le {quand} ({quoi}).")
