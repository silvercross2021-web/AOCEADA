import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client

class Prevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="previsions")
    moisConcerné = models.CharField(max_length=50, verbose_name="Mois concerné (ex: Mai 2026)")
    # Clé de tri chronologique fiable (AAAA-MM) — le libellé français ne se trie pas
    annee_mois = models.CharField(max_length=7, default='', blank=True, db_index=True, verbose_name="Mois (AAAA-MM)")
    consomméeEstimée_kWh = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Consommation estimée (kWh)")
    montantEstimé_FCFA = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant estimé (FCFA)")
    écartSurMoisPrécédent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Écart sur mois précédent (%)")

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        verbose_name = "Prévision de Facturation"
        verbose_name_plural = "Prévisions de Facturation"
        ordering = ['-annee_mois', '-moisConcerné']

    def __str__(self):
        return f"Prévision {self.moisConcerné} - Client: {self.client.nom}"
