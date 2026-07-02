from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sensors", "0003_dispositif_numeroserie"),
        ("accounts", "__first__"),
    ]

    operations = [
        migrations.AlterField(
            model_name="capteur",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="capteurs",
                to="accounts.client",
            ),
        ),
        migrations.AlterField(
            model_name="dispositif",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dispositifs",
                to="accounts.client",
            ),
        ),
    ]
