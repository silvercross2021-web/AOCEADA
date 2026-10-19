from django.db import migrations
from django.utils import timezone


def dater_les_credits_existants(apps, schema_editor):
    """Un compteur prépayé dont le crédit a été saisi sans recharge datée (administration, anciennes versions) reçoit
    UNE recharge datée d'aujourd'hui du montant du crédit : le calcul du crédit déduit désormais l'énergie mesurée
    depuis la première recharge, pas depuis toujours (20/10/2026)."""
    Client = apps.get_model('accounts', 'Client')
    RechargeCredit = apps.get_model('analytics', 'RechargeCredit')
    maintenant = timezone.now()
    for c in Client.objects.filter(typeCompteur='prepaye', creditPrepaye_FCFA__gt=0):
        if not RechargeCredit.objects.filter(client=c).exists():
            r = RechargeCredit.objects.create(client=c, montant_FCFA=c.creditPrepaye_FCFA)
            RechargeCredit.objects.filter(pk=r.pk).update(dateRecharge=maintenant)


class Migration(migrations.Migration):
    dependencies = [
        ('analytics', '0004_meteojour'),
        ('accounts', '0019_alertes_simples'),
    ]
    operations = [migrations.RunPython(dater_les_credits_existants, migrations.RunPython.noop)]
