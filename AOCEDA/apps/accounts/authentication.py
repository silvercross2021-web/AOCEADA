from rest_framework_simplejwt.authentication import JWTAuthentication  # pyrefly: ignore [missing-import]
from rest_framework_simplejwt.exceptions import AuthenticationFailed  # pyrefly: ignore [missing-import]


class TokenAuthentication(JWTAuthentication):
    """JWTAuthentication + révocation immédiate sur changement de mot de passe.

    Le blacklist SimpleJWT (rest_framework_simplejwt.token_blacklist) ne couvre
    que les REFRESH tokens : un access token déjà émis reste valable jusqu'à
    son expiration naturelle (30 min, mémoire §4.3.1) même après un changement
    de mot de passe. Ce contrôle ferme cette fenêtre : tout jeton dont le claim
    `iat` est antérieur à `user.password_changed_at` est rejeté immédiatement,
    qu'il soit expiré ou non.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        changed_at = getattr(user, 'password_changed_at', None)
        if changed_at is not None:
            iat = validated_token.get('iat')
            # `iat` est un entier (précision à la seconde) alors que
            # `password_changed_at` a une précision microseconde : comparer aux
            # secondes entières (floor) évite de rejeter à tort un jeton fraîchement
            # émis DANS LA MÊME SECONDE que le changement de mot de passe.
            if iat is not None and iat < int(changed_at.timestamp()):
                raise AuthenticationFailed(
                    "Ce jeton a été émis avant votre dernier changement de mot de passe. "
                    "Reconnectez-vous.",
                    code='token_before_password_change',
                )
        return user
