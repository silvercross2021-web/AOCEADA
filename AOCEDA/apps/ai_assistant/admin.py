# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import ConversationIA

@admin.register(ConversationIA)
class ConversationIAAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'nb_requetes_aujourd_hui', 'timestamp')
    search_fields = ('client__nom', 'client__email')
    list_per_page = 50
