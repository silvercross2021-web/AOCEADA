import logging
from .models import AuditLog

logger = logging.getLogger(__name__)

def log_action(utilisateur, action, description, cible_id=None, client=None):
    """
    Enregistre une action d'audit en base de données.
    `client` (optionnel) structure le lien vers le client concerné, en plus de
    `cible_id` (texte libre, peut référencer un dispositif/capteur/autre id).
    """
    try:
        role = getattr(utilisateur, 'role', 'système') if utilisateur else 'système'
        AuditLog.objects.create(
            utilisateur=utilisateur,
            role=role,
            action=action,
            description=description,
            cible_id=str(cible_id) if cible_id else None,
            client=client,
        )
    except Exception as e:
        logger.exception("Échec de l'enregistrement du log d'audit : %s", e)
