import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0003_seuil_nuit_et_alertes_tranche"),
    ]

    operations = [
        migrations.AddField(
            model_name="alerte",
            name="regle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alertes",
                to="alerts.regledetection",
            ),
        ),
    ]
