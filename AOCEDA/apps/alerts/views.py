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


class TrancheEtatView(APIView):
    """Où en est la facture postpayée du bimestre par rapport au seuil de sa tranche 1
    (carte « Alerte de tranche » de la page Alertes). Prépayé : {"applicable": false},
    l'arrêté n° 1355 ne prévoit aucune tranche en prépaiement."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Réservé aux clients."}, status=status.HTTP_403_FORBIDDEN)
        from .utils import etat_tranche, TRANCHE_PART_APPROCHE, TRANCHE_JOURS_APPROCHE
        e = etat_tranche(user.client)
        if e is None:
            return Response({"applicable": False})
        return Response({
            "applicable": True,
            "periode": e["libelle"],
            "debut": e["periode"]["debut"].isoformat(),
            "fin": e["periode"]["fin"].isoformat(),
            "kwh": round(float(e["kwh"]), 2),
            "seuil_kwh": float(e["seuil"]),
            "type_tarif": e["type_tarif"],
            "prix_t1": float(e["prix_t1"]),
            "prix_t2": float(e["prix_t2"]),
            "rythme_kwh_jour": round(e["rythme_kwh_jour"], 2) if e["rythme_kwh_jour"] else None,
            "jours_avant_seuil": round(e["jours_avant_seuil"], 1) if e["jours_avant_seuil"] is not None else None,
            "alerte_pourcent": int(TRANCHE_PART_APPROCHE * 100),
            "alerte_jours": TRANCHE_JOURS_APPROCHE,
        })
