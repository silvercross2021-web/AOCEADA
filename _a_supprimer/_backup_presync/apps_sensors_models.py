import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client, Technicien

class Dispositif(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="dispositifs", null=True, blank=True)
    numeroSerie = models.CharField(max_length=100, blank=True, null=True, verbose_name="Numéro de série")
    apiKeyDevice = models.CharField(max_length=255, unique=True)
    firmwareVersion = models.CharField(max_length=50, blank=True, null=True)
    estConnecté = models.BooleanField(default=False)
    adresseIP = models.GenericIPAddressField(blank=True, null=True)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    def __str__(self):
        nom_client = self.client.nom if self.client else "non assigné"
        return f"Dispositif {self.numeroSerie or self.id} ({nom_client})"

class Capteur(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="capteurs", null=True, blank=True)
    dispositif = models.ForeignKey(Dispositif, on_delete=models.CASCADE, related_name="capteurs", null=True, blank=True)
    nom = models.CharField(max_length=150)
    type = models.CharField(max_length=100, default="Courant")
    valeurMax = models.DecimalField(max_digits=10, decimal_places=2, default=2000.00) # Seuil maximal par défaut
    actif = models.BooleanField(default=True)
    coeffCalibration = models.DecimalField(max_digits=6, decimal_places=4, default=1.0000)
    derniereLecture = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    def __str__(self):
        nom_client = self.client.nom if self.client else "disponible"
        return f"{self.nom} — {nom_client}"

class MesureEnergie(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    capteur = models.ForeignKey(Capteur, on_delete=models.CASCADE, related_name="mesures")
    puissance = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Puissance (W)")
    courant = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Courant (A)")
    energie = models.DecimalField(max_digits=15, decimal_places=6, verbose_name="Énergie (kWh)")
    tension_V = models.DecimalField(max_digits=5, decimal_places=1, default=220.0, verbose_name="Tension (V)")
    facteur_puissance = models.DecimalField(max_digits=4, decimal_places=3, default=0.900, verbose_name="Facteur de puissance")
    timestamp = models.DateTimeField(db_index=True)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['capteur', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.capteur.nom} - {self.puissance}W at {self.timestamp}"

class Intervention(models.Model):
    TYPE_CHOICES = [
        ('INSTALLATION', 'Installation'),
        ('CALIBRATION', 'Calibration'),
        ('PANNE', 'Déclaration de panne'),
        ('MAINTENANCE', 'Maintenance'),
    ]
    STATUT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('EN_COURS', 'En cours'),
        ('TERMINEE', 'Terminée'),
        ('ANNULEE', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    technicien = models.ForeignKey(Technicien, on_delete=models.CASCADE, related_name="interventions")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="interventions", null=True, blank=True)
    dispositif = models.ForeignKey(Dispositif, on_delete=models.SET_NULL, null=True, blank=True, related_name="interventions")
    capteur = models.ForeignKey(Capteur, on_delete=models.SET_NULL, null=True, blank=True, related_name="interventions")
    typeIntervention = models.CharField(max_length=50, choices=TYPE_CHOICES, default='MAINTENANCE')
    description = models.TextField()
    dateIntervention = models.DateTimeField()
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default='EN_ATTENTE')
    résultat = models.TextField(blank=True, null=True)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        ordering = ['-dateIntervention']
        verbose_name = "Intervention"
        verbose_name_plural = "Interventions"

    def __str__(self):
        return f"{self.typeIntervention} - {self.statut} ({self.technicien.nom})"

class RapportIntervention(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intervention = models.OneToOneField(Intervention, on_delete=models.CASCADE, related_name="rapport")
    contenu = models.TextField()
    conclusion = models.TextField(blank=True, null=True)
    dateGénération = models.DateTimeField(auto_now_add=True)
    estValidé = models.BooleanField(default=False)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        ordering = ['-dateGénération']
        verbose_name = "Rapport d'intervention"
        verbose_name_plural = "Rapports d'intervention"

    def __str__(self):
        return f"Rapport {self.id} - Intervention {self.intervention_id}"
