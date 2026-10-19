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
            from .utils import alertes_du_client
            # Ordre stable (récentes d'abord) + jointure capteur pour capteur_nom sans N+1
            return alertes_du_client(user.client).select_related('mesure__capteur', 'regle').order_by('-createdAt')
        return Alerte.objects.none()

    def list(self, request, *args, **kwargs):
        """?limit=N : les N plus récentes, sans pagination (le tableau de bord n'en montre que 3 ; avant le
        19/10/2026 il en recevait jusqu'à 1000 toutes les 10 s)."""
        limite = request.query_params.get('limit')
        if limite and limite.isdigit():
            qs = self.get_queryset()[:max(1, min(int(limite), 50))]
            return Response(self.get_serializer(qs, many=True).data)
        return super().list(request, *args, **kwargs)

class AlerteMarkReadView(APIView):
    """Marque UNE alerte comme lue (défaut) ou, avec {"lue": false}, comme non lue (19/10/2026 : un clic de trop ne se
    rattrapait pas)."""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent modifier leurs alertes."}, status=status.HTTP_403_FORBIDDEN)

        try:
            alert = Alerte.objects.select_related('mesure__capteur', 'regle').get(id=pk, client=user.client)
        except (Alerte.DoesNotExist, ValueError):
            return Response({"detail": "Alerte non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        alert.lue = request.data.get('lue', True) not in (False, 'false', 'False', 0, '0')
        alert.save(update_fields=['lue'])
        return Response(AlerteSerializer(alert).data)


class AlerteMarkAllReadView(APIView):
    """Marque comme lues les alertes non lues du client QUE LA PAGE MONTRE (même règle que la liste : pas les anciennes
    alertes « crédit bas » d'un compteur postpayé, qu'il ne voit nulle part et qui gonflaient le compte)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, 'client'):
            return Response({"detail": "Seuls les clients peuvent modifier leurs alertes."}, status=status.HTTP_403_FORBIDDEN)
        from .utils import alertes_du_client
        updated = alertes_du_client(request.user.client).filter(lue=False).update(lue=True)
        return Response({"detail": f"{updated} alerte(s) marquée(s) comme lue(s).", "count": updated})


class CompteurAlertesView(APIView):
    """État léger des alertes, pour la cloche et l'alarme de TOUTES les pages (relu toutes les 15 s) : avant le
    19/10/2026 chaque page téléchargeait la liste complète (jusqu'à 1000 alertes) pour en compter les non lues.
    `critiques_non_lues` : identifiants des alertes critiques non lues (20 au plus), pour ne sonner que sur une
    NOUVELLE alerte critique, jamais sur une simple variation du nombre. `surveillance` : ce que la surveillance fait."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"non_lues": 0, "critiques_non_lues": [], "surveillance": None})
        from .utils import alertes_du_client, etat_surveillance
        non_lues = alertes_du_client(user.client).filter(lue=False)
        critiques = list(non_lues.filter(sévérité='Critique').order_by('-createdAt').values('id', 'message', 'createdAt')[:20])
        return Response({
            "non_lues": non_lues.count(),
            "critiques_non_lues": [{"id": str(c['id']), "message": c['message'], "createdAt": c['createdAt'].isoformat()}
                                   for c in critiques],
            "surveillance": etat_surveillance(user.client),
        })


class EmailTestView(APIView):
    """Envoie un e-mail de TEST à l'adresse du compte, pour vérifier que les alertes arriveront (une fois par minute au
    plus). N'enregistre aucune fausse alerte."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Réservé aux clients."}, status=status.HTTP_403_FORBIDDEN)
        from django.core.cache import cache
        from django.conf import settings
        from apps.accounts.utils import send_mail_async
        cle = f"aoceda:email-test:{user.client.pk}"
        if cache.get(cle):
            return Response({"detail": "Un e-mail de test vient d'être envoyé : patientez une minute."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        cache.set(cle, True, 60)
        send_mail_async(
            "[TEST] Alertes AOCEDA",
            f"Bonjour {user.client.nom},\n\nCeci est un e-mail de test : vos alertes AOCEDA arriveront à cette adresse "
            "lorsqu'une de vos règles se déclenchera.\n\nL'équipe AOCEDA",
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'), [user.client.email], fail_silently=True)
        return Response({"detail": f"E-mail de test envoyé à {user.client.email}.", "email": user.client.email},
                        status=status.HTTP_202_ACCEPTED)


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
