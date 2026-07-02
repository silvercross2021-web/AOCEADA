# Generated manually on 2026-07-01 — nom + adresse d'installation sur le dispositif

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sensors", "0004_capteur_dispositif_client_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="dispositif",
            name="nom",
            field=models.CharField(
                blank=True, max_length=150, null=True, verbose_name="Nom de l'installation"
            ),
        ),
        migrations.AddField(
            model_name="dispositif",
            name="adresse",
            field=models.TextField(
                blank=True, null=True, verbose_name="Adresse d'installation"
            ),
        ),
    ]
