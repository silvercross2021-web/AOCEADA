# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import RegleDetection, Alerte

@admin.register(RegleDetection)
class RegleDetectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'capteur', 'puissanceMax_W', 'surveilleNuit')
    search_fields = ('client__nom', 'capteur__nom')

@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'type', 'sévérité', 'lue', 'createdAt')
    list_filter = ('type', 'sévérité', 'lue')
    search_fields = ('client__nom', 'message')
    date_hierarchy = 'createdAt'
    list_per_page = 50
    readonly_fields = ('id', 'createdAt')
