import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from django.core.validators import MinValueValidator, MaxValueValidator  # pyrefly: ignore [untyped-import]
from ckeditor.fields import RichTextField
from apps.accounts.models import Client, Technicien

class Dispositif(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="dispositifs", null=True, blank=True)
    nom = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nom de l'installation")
    adresse = models.TextField(blank=True, null=True, verbose_name="Adresse d'installation")
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
    # Horodatage de la DERNIÈRE calibration réelle (auto ou manuelle) — absent avant
    # cette date, jamais déduit de derniereLecture (un contact capteur n'est pas une
    # calibration). Permet d'afficher « calibré il y a N jours » côté technicien,
    # sans imposer de seuil d'alerte arbitraire (aucune périodicité n'est spécifiée
    # dans le cahier des charges — seule la visibilité de l'ancienneté est objective).
    derniereCalibration = models.DateTimeField(null=True, blank=True)
    # derniereLecture = dernier CONTACT du capteur (mis à jour à chaque lecture, même
    # éteint) → sert à décider en ligne / hors ligne. À NE PAS confondre avec l'horodatage
    # de la dernière mesure de puissance (qui n'existe que quand l'appareil consomme).
    derniereLecture = models.DateTimeField(null=True, blank=True)
    # État instantané réel de l'appareil, tel que rapporté par le pont/firmware à la
    # dernière lecture : 'ON' (consomme) ou 'OFF' (branché mais éteint). Persisté pour
    # que le dashboard n'ait pas à le déduire d'une mesure périmée.
    etatCourant = models.CharField(max_length=3, choices=[('ON', 'Allumé'), ('OFF', 'Éteint')], default='OFF')
    # Compteur d'échantillons OFF consécutifs reçus depuis le pont. Anti-rebond côté
    # serveur : on ne bascule etatCourant de ON→OFF qu'après CONFIRM_OFF échantillons
    # OFF d'affilée, pour ne pas afficher « éteint » à tort lors d'un OFF isolé (bruit,
    # zéro-crossing, phase de stabilisation firmware au démarrage). Miroir de la
    # confirmation (CONFIRMATIONS=3) déjà faite côté firmware.
    cptOffConsecutifs = models.PositiveSmallIntegerField(default=0)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    def __str__(self):
        nom_client = self.client.nom if self.client else "disponible"
        return f"{self.nom}, {nom_client}"

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
        ('DIAGNOSTIC', 'Diagnostic & Audits'),
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

    # Planification (rendez-vous à venir) : distincte de dateIntervention, qui reste
    # la date d'enregistrement/réalisation. Fixée par le technicien, visible par le
    # client sous forme « Intervention prévue le X » tant que le statut n'est pas final.
    dateProgrammee = models.DateTimeField(blank=True, null=True, verbose_name="Date programmée")

    # Retour client après une intervention TERMINEE : note de satisfaction facultative,
    # jamais générée/fabriquée — uniquement saisie volontairement par le client.
    satisfactionClient = models.PositiveSmallIntegerField(
        blank=True, null=True, verbose_name="Satisfaction client (1 à 5)",
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaireClient = models.TextField(blank=True, null=True, verbose_name="Commentaire client")
    dateRetourClient = models.DateTimeField(blank=True, null=True)

    # Réouverture : si le problème persiste, le client déclare une NOUVELLE
    # intervention liée à l'originale plutôt que de réécrire l'historique du
    # technicien (cohérent avec le verrou anti-antidatage existant).
    interventionOrigine = models.ForeignKey(
        'self', on_delete=models.SET_NULL, blank=True, null=True,
        related_name='suivis', verbose_name="Intervention d'origine (si signalement de persistance)")

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
    contenu = RichTextField()
    conclusion = RichTextField(blank=True, null=True)
    dateGénération = models.DateTimeField(auto_now_add=True)
    estValidé = models.BooleanField(default=False)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        ordering = ['-dateGénération']
        verbose_name = "Rapport d'intervention"
        verbose_name_plural = "Rapports d'intervention"

    def __str__(self):
        return f"Rapport {self.id} - Intervention {self.intervention_id}"
