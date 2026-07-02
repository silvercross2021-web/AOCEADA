# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import Dispositif, Capteur, MesureEnergie, Intervention, RapportIntervention

@admin.register(Dispositif)
class DispositifAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'firmwareVersion', 'estConnecté', 'adresseIP')
    list_filter = ('estConnecté',)
    search_fields = ('client__nom', 'apiKeyDevice')

@admin.register(Capteur)
class CapteurAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'dispositif', 'nom', 'type', 'actif', 'derniereLecture')
    list_filter = ('type', 'actif')
    search_fields = ('client__nom', 'nom')

@admin.register(MesureEnergie)
class MesureEnergieAdmin(admin.ModelAdmin):
    list_display = ('id', 'capteur', 'puissance', 'courant', 'energie', 'tension_V', 'timestamp')
    list_filter = ('capteur',)
    search_fields = ('capteur__nom',)
    date_hierarchy = 'timestamp'
    list_per_page = 50
    readonly_fields = ('id', 'timestamp')

@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ('id', 'technicien', 'client', 'typeIntervention', 'statut', 'dateIntervention')
    list_filter = ('typeIntervention', 'statut')
    search_fields = ('technicien__nom', 'client__nom', 'description')
    date_hierarchy = 'dateIntervention'
    list_per_page = 50

@admin.register(RapportIntervention)
class RapportInterventionAdmin(admin.ModelAdmin):
    list_display = ('id', 'intervention', 'dateGénération', 'estValidé')
    list_filter = ('estValidé',)
