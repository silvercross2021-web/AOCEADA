import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client
from apps.sensors.models import Capteur, MesureEnergie

class RegleDetection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="regles")
    capteur = models.ForeignKey(Capteur, on_delete=models.CASCADE, related_name="regles")
    puissanceMax_W = models.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    surveilleNuit = models.BooleanField(default=False)
    heureDébutNuit = models.TimeField(default="00:00:00")
    heureFinNuit = models.TimeField(default="05:00:00")

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    def __str__(self):
        return f"Règle pour {self.capteur.nom} (Client: {self.client.nom})"

class Alerte(models.Model):
    TYPE_CHOICES = [
        ('DEPASSEMENT_SEUIL', 'Dépassement de seuil'),
        ('CONSOMMATION_NOCTURNE', 'Consommation nocturne fantôme'),
        ('CREDIT_BAS', 'Crédit bas'),
    ]
    SEVERITY_CHOICES = [
        ('Critique', 'Critique'),
        ('Avertissement', 'Avertissement'),
        ('Info', 'Info'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="alertes")
    mesure = models.ForeignKey(MesureEnergie, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertes")
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    message = models.TextField()
    lue = models.BooleanField(default=False)
    createdAt = models.DateTimeField(db_index=True, auto_now_add=True)
    emailEnvoyé = models.BooleanField(default=False)
    sévérité = models.CharField(max_length=50, choices=SEVERITY_CHOICES, default='Avertissement')

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        ordering = ['-createdAt']

    def __str__(self):
        return f"{self.type} - {self.sévérité} - Client: {self.client.nom}"
