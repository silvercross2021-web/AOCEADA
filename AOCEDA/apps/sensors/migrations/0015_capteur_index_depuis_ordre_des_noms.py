"""Numéro fixe de chaque capteur sur son boîtier (Capteur.indexDispositif).

Jusqu'ici, le serveur retrouvait le capteur d'une mesure ESP32 par l'ordre alphabétique
des noms des capteurs du boîtier (capteur_index 1 = premier nom). On fige cet ordre tel
qu'il est aujourd'hui : les boîtiers déjà installés gardent exactement la même
correspondance, et un renommage ne peut plus la changer.
"""
from django.db import migrations


def figer_ordre_actuel(apps, schema_editor):
    Capteur = apps.get_model('sensors', 'Capteur')
    Dispositif = apps.get_model('sensors', 'Dispositif')
    for dispositif in Dispositif.objects.all():
        # Même tri que l'ancienne ingestion (ZMCTIngestionView) : par nom
        capteurs = Capteur.objects.filter(dispositif=dispositif).order_by('nom')
        for position, capteur in enumerate(capteurs, start=1):
            capteur.indexDispositif = position
            capteur.save(update_fields=['indexDispositif'])


class Migration(migrations.Migration):

    dependencies = [
        ('sensors', '0014_capteur_index_et_coupure'),
    ]

    operations = [
        migrations.RunPython(figer_ordre_actuel, migrations.RunPython.noop),
    ]
