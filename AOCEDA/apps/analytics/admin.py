# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import Prevision

@admin.register(Prevision)
class PrevisionAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'moisConcerné', 'consomméeEstimée_kWh', 'montantEstimé_FCFA')
    search_fields = ('client__nom', 'moisConcerné')
    list_per_page = 50
