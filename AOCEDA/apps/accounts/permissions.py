from rest_framework import permissions


class IsTechnicien(permissions.BasePermission):
    """Accès réservé aux techniciens (installation, calibration, interventions)."""
    message = "Accès réservé aux techniciens."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (
            getattr(user, 'role', None) == 'technicien' or hasattr(user, 'technicien')
        ))


class IsAdministrateur(permissions.BasePermission):
    """Accès réservé aux administrateurs de la plateforme."""
    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (
            getattr(user, 'role', None) == 'admin' or user.is_staff or user.is_superuser
        ))


class IsTechnicienOrAdministrateur(permissions.BasePermission):
    """Accès réservé aux techniciens et administrateurs."""
    message = "Accès réservé aux techniciens et administrateurs."

    def has_permission(self, request, view):
        return (
            IsTechnicien().has_permission(request, view)
            or IsAdministrateur().has_permission(request, view)
        )
