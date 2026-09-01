import threading
import logging
from django.core.mail import send_mail  # pyrefly: ignore [untyped-import]
from django.db import close_old_connections  # pyrefly: ignore [untyped-import]

logger = logging.getLogger(__name__)


def revoke_all_tokens(user):
    """Révoque immédiatement tous les jetons JWT déjà émis pour `user`, sur
    changement/réinitialisation de mot de passe (une session volée ou un autre
    appareil connecté ne doit plus pouvoir continuer à utiliser l'ancien mot
    de passe une fois qu'il a été changé).

    Deux mécanismes complémentaires, car SimpleJWT ne blackliste que les
    REFRESH tokens par défaut, jamais les access tokens déjà émis (courte
    durée de vie, 30 min, mais pas nulle) :
      1. `password_changed_at` (horodatage) : apps.accounts.authentication.
         TokenAuthentication rejette tout access token dont le claim `iat`
         est antérieur — révocation immédiate, y compris pour un jeton
         déjà en circulation.
      2. Blacklist SimpleJWT (rest_framework_simplejwt.token_blacklist, déjà
         installée dans le projet mais jusqu'ici jamais utilisée) : empêche
         tout REFRESH token existant de servir à obtenir un nouvel access
         token après l'expiration naturelle de l'ancien.
    """
    from django.utils import timezone
    user.password_changed_at = timezone.now()
    user.save(update_fields=['password_changed_at'])

    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
    except ImportError:
        return  # app blacklist non installée (ne devrait pas arriver, cf. settings.py)

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

def send_mail_async(subject, message, from_email, recipient_list, fail_silently=False, html_message=None, callback=None, callback_args=None, callback_kwargs=None):
    """
    Envoie un email de manière asynchrone dans un thread séparé.
    Le callback peut être utilisé pour mettre à jour la base de données après un envoi réussi.
    """
    from django.conf import settings
    import sys
    is_testing = getattr(settings, 'TESTING', False) or ('test' in sys.argv)

    def _run():
        if not is_testing:
            close_old_connections()
        try:
            res = send_mail(
                subject,
                message,
                from_email,
                recipient_list,
                fail_silently=fail_silently,
                html_message=html_message
            )
            if res and callback:
                try:
                    callback(*(callback_args or []), **(callback_kwargs or {}))
                except Exception as cb_err:
                    logger.exception("Erreur dans le callback après envoi de mail : %s", cb_err)
        except Exception as e:
            logger.exception("Échec d'envoi de l'e-mail asynchrone : %s", e)
        finally:
            if not is_testing:
                close_old_connections()

    if is_testing:
        _run()
    else:
        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

