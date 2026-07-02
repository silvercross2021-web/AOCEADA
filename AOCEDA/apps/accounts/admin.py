# pyrefly: ignore [untyped-import]
from django.contrib import admin
from .models import Utilisateur, Client, Technicien, Administrateur

@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'role', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nom')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'typeLogement', 'numeroCIE')
    search_fields = ('email', 'nom', 'numeroCIE')

@admin.register(Technicien)
class TechnicienAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'matricule', 'specialite')
    search_fields = ('email', 'nom', 'matricule')

@admin.register(Administrateur)
class AdministrateurAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'niveauAcces')
    search_fields = ('email', 'nom')
