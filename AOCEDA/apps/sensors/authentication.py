from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Dispositif

class DeviceAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        # Expecting format: "Bearer <apiKey>" or "Device <apiKey>" or just "<apiKey>"
        parts = auth_header.split()
        
        if len(parts) == 2:
            prefix, key = parts[0].lower(), parts[1]
            if prefix not in ['bearer', 'device']:
                return None
        elif len(parts) == 1:
            key = parts[0]
        else:
            return None

        try:
            device = Dispositif.objects.select_related('client').get(apiKeyDevice=key)
        except Dispositif.DoesNotExist:
            # Préfixe "Device" explicite : la clé est forcément une API Key -> rejet clair.
            # Sinon ("Bearer ..." ou clé nue), on laisse la main aux autres
            # authentifications (JWT du frontend) en retournant None.
            if len(parts) == 2 and parts[0].lower() == 'device':
                raise AuthenticationFailed("Clé d'API dispositif invalide.")
            return None

        if device.client is None:
            raise AuthenticationFailed("Ce dispositif n'est pas encore assigné à un client.")

        # Authenticate the request by returning the associated client (which is a User subclass) and the device
        return (device.client, device)

    def authenticate_header(self, request):
        # Sans cet en-tête, DRF renverrait 403 au lieu de 401 sur un échec d'auth
        # (y compris pour /api/mesures/ où cet authenticator est en tête de liste).
        return 'Device'
