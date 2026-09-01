import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client

# Historique : depuis 2026-07-17, le CONTENU des conversations est stocké ici (voir
# Conversation ci-dessous) pour être synchronisé entre les appareils du même compte —
# avant cette date il ne vivait que dans le localStorage du navigateur (voir git log
# static/js/ia.js). Le quota, lui, a TOUJOURS dû rester côté serveur (un client ne peut
# pas être juge de son propre quota).


class Conversation(models.Model):
    """Fil de discussion avec l'assistant IA. Synchronisé entre tous les appareils du
    client (compte = source de vérité), contrairement à l'ancien stockage local seul.
    `messages` est la liste complète [{role, content}, ...] du fil, dans l'ordre —
    remplacée en bloc à chaque échange par le frontend (pas de modèle Message séparé :
    le volume par fil est faible et ça évite une jointure pour un gain nul ici)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="conversations_ia")
    titre = models.CharField(max_length=200, blank=True, default="")
    messages = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Conversation IA"
        verbose_name_plural = "Conversations IA"

    def __str__(self):
        return f"{self.titre or 'Sans titre'} — {self.client.nom}"


class QuotaIA(models.Model):
    """Quota quotidien + tokens cumulés PAR CLIENT (partagé par tous ses fils de discussion)."""
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="quota_ia")
    nb_requetes_aujourd_hui = models.IntegerField(default=0, verbose_name="Nombre de requêtes aujourd'hui")
    # Cumul des tokens réellement consommés (format OpenAI-compatible), pour repérer
    # un usage anormal/du gaspillage sans devoir éplucher les logs.
    tokens_entree_total = models.PositiveIntegerField(default=0, verbose_name="Tokens entrée (cumulé)")
    tokens_sortie_total = models.PositiveIntegerField(default=0, verbose_name="Tokens sortie (cumulé)")
    derniere_maj = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        verbose_name = "Quota IA"
        verbose_name_plural = "Quotas IA"

    def __str__(self):
        return f"Quota IA - Client: {self.client.nom}"
