# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import QuotaIA, Conversation


@admin.register(QuotaIA)
class QuotaIAAdmin(admin.ModelAdmin):
    list_display = ('client', 'nb_requetes_aujourd_hui', 'tokens_entree_total', 'tokens_sortie_total', 'derniere_maj')
    search_fields = ('client__nom', 'client__email')
    list_per_page = 50


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    # Pas le contenu des messages en liste (RÈGLE D'ISOLATION/vie privée) — juste de quoi
    # superviser le volume, pas de quoi lire les échanges d'un client depuis la liste.
    list_display = ('titre', 'client', 'created_at', 'updated_at')
    search_fields = ('client__nom', 'client__email', 'titre')
    list_per_page = 50
