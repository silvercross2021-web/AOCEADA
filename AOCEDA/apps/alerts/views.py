from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Alerte, RegleDetection
from .serializers import AlerteSerializer, RegleDetectionSerializer

class AlerteListView(generics.ListAPIView):
    serializer_class = AlerteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            # Ordre stable (récentes d'abord) + jointure capteur pour capteur_nom sans N+1
            qs = Alerte.objects.filter(client=user.client).select_related('mesure__capteur')
            if getattr(user.client, 'typeCompteur', 'postpaye') != 'prepaye':
                qs = qs.exclude(type='CREDIT_BAS')
            return qs.order_by('-createdAt')
        return Alerte.objects.none()

class AlerteMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent modifier leurs alertes."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            alert = Alerte.objects.get(id=pk, client=user.client)
        except (Alerte.DoesNotExist, ValueError):
            return Response({"detail": "Alerte non trouvée."}, status=status.HTTP_404_NOT_FOUND)
            
        alert.lue = True
        alert.save()
        return Response(AlerteSerializer(alert).data)

class AlerteMarkAllReadView(APIView):
    """Marque TOUTES les alertes non lues du client connecté comme lues."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, 'client'):
            return Response({"detail": "Seuls les clients peuvent modifier leurs alertes."}, status=status.HTTP_403_FORBIDDEN)
        updated = Alerte.objects.filter(client=request.user.client, lue=False).update(lue=True)
        return Response({"detail": f"{updated} alerte(s) marquée(s) comme lue(s).", "count": updated})


class RegleDetectionListCreateView(generics.ListCreateAPIView):
    serializer_class = RegleDetectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            return RegleDetection.objects.filter(client=user.client)
        return RegleDetection.objects.none()

    def create(self, request, *args, **kwargs):
        # Les règles de détection sont une notion propre au client.
        if not hasattr(request.user, 'client'):
            return Response(
                {"detail": "Seuls les clients peuvent définir des règles de détection."},
                status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(client=self.request.user.client)

class RegleDetectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RegleDetectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            return RegleDetection.objects.filter(client=user.client)
        return RegleDetection.objects.none()
