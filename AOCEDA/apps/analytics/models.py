import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client

class Prevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="previsions")
    moisConcerné = models.CharField(max_length=50, verbose_name="Mois concerné (ex: Mai 2026)")
    # Clé de tri chronologique fiable (AAAA-MM), le libellé français ne se trie pas
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


class RechargeCredit(models.Model):
    """Une recharge DÉCLARÉE par le client (compteur prépayé) : AOCEDA ne recharge
    jamais le vrai compteur CIE (aucune affiliation/API CIE), il se contente
    d'enregistrer le montant que le client dit avoir rechargé ailleurs (agent CIE,
    mobile money…), pour calculer un crédit restant estimé et en garder la trace.
    Une ligne par recharge (jamais écrasée) : c'est ce qui permet un historique
    daté, contrairement au simple cumul stocké sur Client.creditPrepaye_FCFA."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="recharges_credit")
    montant_FCFA = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant rechargé (FCFA)")
    dateRecharge = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        verbose_name = "Recharge de crédit prépayé"
        verbose_name_plural = "Recharges de crédit prépayé"
        ordering = ['-dateRecharge']

    def __str__(self):
        return f"{self.client.nom} · {self.montant_FCFA} FCFA · {self.dateRecharge:%d/%m/%Y %H:%M}"
