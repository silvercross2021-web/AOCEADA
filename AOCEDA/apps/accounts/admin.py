# pyrefly: ignore [untyped-import]
from django.contrib import admin
from django.utils.html import format_html
from .models import Utilisateur, Client, Technicien, Administrateur, AuditLog, NoteClient

def get_photo_preview(obj):
    if obj.photo:
        return format_html('<img src="{}" style="width:40px; height:40px; border-radius:50%; object-fit:cover;" />', obj.photo.url)
    return format_html('<div style="width:40px; height:40px; border-radius:50%; background-color:#ccc; display:flex; align-items:center; justify-content:center; color:#fff; font-weight:bold;">{}</div>', (obj.nom[:1].upper() if obj.nom else '?'))
get_photo_preview.short_description = 'Photo'

@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ('photo_preview', 'email', 'nom', 'role', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nom')
    def photo_preview(self, obj): return get_photo_preview(obj)
    photo_preview.short_description = 'Photo'

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('photo_preview', 'email', 'nom', 'typeLogement', 'numeroCIE')
    search_fields = ('email', 'nom', 'numeroCIE')
    def photo_preview(self, obj): return get_photo_preview(obj)
    photo_preview.short_description = 'Photo'

@admin.register(Technicien)
class TechnicienAdmin(admin.ModelAdmin):
    list_display = ('photo_preview', 'email', 'nom', 'matricule', 'specialite')
    search_fields = ('email', 'nom', 'matricule')
    def photo_preview(self, obj): return get_photo_preview(obj)
    photo_preview.short_description = 'Photo'

@admin.register(Administrateur)
class AdministrateurAdmin(admin.ModelAdmin):
    list_display = ('photo_preview', 'email', 'nom', 'niveauAcces')
    search_fields = ('email', 'nom')
    def photo_preview(self, obj): return get_photo_preview(obj)
    photo_preview.short_description = 'Photo'

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'utilisateur_str', 'role', 'action', 'client', 'description', 'cible_id')
    list_filter = ('role', 'action', 'timestamp')
    search_fields = ('utilisateur__nom', 'utilisateur__email', 'client__nom', 'action', 'description', 'cible_id')
    readonly_fields = ('timestamp', 'utilisateur', 'role', 'action', 'description', 'client', 'cible_id')

    def utilisateur_str(self, obj):
        return f"{obj.utilisateur.nom} ({obj.utilisateur.email})" if obj.utilisateur else "Système"
    utilisateur_str.short_description = 'Utilisateur'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(NoteClient)
class NoteClientAdmin(admin.ModelAdmin):
    list_display = ('dateCreation', 'client', 'technicien', 'contenu')
    list_filter = ('dateCreation',)
    search_fields = ('client__nom', 'technicien__nom', 'contenu')
    date_hierarchy = 'dateCreation'

