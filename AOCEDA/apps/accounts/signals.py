from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .audit import log_action

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    log_action(user, 'CONNEXION', f"Utilisateur {user.email} connecté avec succès.")

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        log_action(user, 'DÉCONNEXION', f"Utilisateur {user.email} déconnecté.")
