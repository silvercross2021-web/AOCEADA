import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from apps.accounts.models import Client

class ConversationIA(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="conversations_ia")
    historique_messages = models.JSONField(default=list, verbose_name="Historique des messages")
    nb_requetes_aujourd_hui = models.IntegerField(default=0, verbose_name="Nombre de requêtes aujourd'hui")
    timestamp = models.DateTimeField(auto_now=True)

    objects = models.Manager()  # manager par défaut (explicite pour le typage)

    class Meta:
        verbose_name = "Conversation IA"
        verbose_name_plural = "Conversations IA"
        ordering = ['-timestamp']

    def __str__(self):
        return f"Chat IA {self.id} - Client: {self.client.nom}"
