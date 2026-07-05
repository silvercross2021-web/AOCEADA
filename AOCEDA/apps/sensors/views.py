import secrets
import logging
import json
import time
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Avg  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncHour, TruncDay  # pyrefly: ignore [untyped-import]
from django.http import StreamingHttpResponse, HttpResponse  # pyrefly: ignore [untyped-import]
from django.views import View  # pyrefly: ignore [untyped-import]
from datetime import timedelta, datetime
from .models import Capteur, MesureEnergie, Dispositif, Intervention
from .serializers import (
    CapteurSerializer, MesureEnergieSerializer, DispositifSerializer,
    CapteurTechnicienSerializer, InterventionSerializer, RapportInterventionSerializer,
    ZMCTMesureSerializer,
)
from .authentication import DeviceAPIKeyAuthentication
from apps.accounts.permissions import IsTechnicienOrAdministrateur

logger = logging.getLogger(__name__)


def _sensor_uuid(qp):
    """?sensor_id= validé en UUID (Capteur.id est un UUIDField), ou (None, err 400).
    Filtrer directement avec une valeur non-UUID lèverait une ValidationError que
    DRF ne convertit pas → 500 au lieu d'un 400. Même garde que côté analytics."""
    raw = qp.get('sensor_id')
    if not raw:
        return None, None
    import uuid as _uuid
    try:
        return _uuid.UUID(str(raw)), None
    except (ValueError, AttributeError, TypeError):
        return None, Response({"detail": "Identifiant de capteur invalide."},
                              status=status.HTTP_400_BAD_REQUEST)


def _energie_kwh(capteur, puissance, now, defaut_s, cap_s=60.0):
    """Énergie (kWh) d'un échantillon = puissance × durée RÉELLE depuis la mesure
    précédente, PAS une fenêtre fixe. Le pont/ESP32 peut poster toutes les 0,2 s
    comme toutes les 4 s : une fenêtre codée en dur sous-comptait alors ~20×.
    L'intervalle est borné (cap_s) pour ne pas compter un long trou (appareil
    éteint/déconnecté) comme de la consommation continue."""
    last = MesureEnergie.objects.filter(capteur=capteur).order_by('-timestamp').first()
    dt_s = (now - last.timestamp).total_seconds() if last else defaut_s
    if dt_s <= 0:
        dt_s = defaut_s
    dt_s = min(dt_s, cap_s)
    return puissance / 1000.0 * (dt_s / 3600.0)


class CapteurListView(generics.ListAPIView):
    serializer_class = CapteurSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            return Capteur.objects.filter(client=user.client).order_by('nom')
        return Capteur.objects.none()

class MesureEnergieView(APIView):
    # Support both JWT (for frontend graph queries) and Device API Key (for ESP32 posts)
    authentication_classes = [DeviceAPIKeyAuthentication] + list(APIView.authentication_classes)
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _parse_date(value):
        """Convertit 'AAAA-MM-JJ' en date ; renvoie None si vide ou invalide."""
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent voir leurs mesures."}, status=status.HTTP_403_FORBIDDEN)
        
        queryset = MesureEnergie.objects.filter(capteur__client=user.client)
        
        # Filter by sensor_id (validé : non-UUID → 400, jamais un 500)
        sensor_id, err = _sensor_uuid(request.query_params)
        if err:
            return err
        if sensor_id:
            queryset = queryset.filter(capteur_id=sensor_id)
            
        # Filter by specific date range (used by the "Plage libre" comparison).
        # Has priority over `period`; both bounds are inclusive on the calendar day.
        date_from_raw = request.query_params.get('date_from')
        date_to_raw = request.query_params.get('date_to')
        if date_from_raw or date_to_raw:
            date_from = self._parse_date(date_from_raw)
            date_to = self._parse_date(date_to_raw)
            if (date_from_raw and date_from is None) or (date_to_raw and date_to is None):
                return Response(
                    {"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if date_from and date_to and date_from > date_to:
                return Response(
                    {"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if date_from:
                queryset = queryset.filter(timestamp__date__gte=date_from)
            if date_to:
                queryset = queryset.filter(timestamp__date__lte=date_to)
        else:
            # Filter by period: 'day' (last 24h), 'week' (last 7 days), 'month' (last 30 days)
            period = request.query_params.get('period', 'week')
            now = timezone.now()
            if period == 'day':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=1))
            elif period == 'week':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=7))
            elif period == 'month':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=30))
            
        serializer = MesureEnergieSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        # Only clients (associated with the API key device) or the authenticated user can post measurements
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Authentification requise pour poster des mesures."}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        is_many = isinstance(data, list)

        # Helper validator to ensure the sensor belongs to the device's client
        def validate_sensor_ownership(sensor_id):
            try:
                capteur = Capteur.objects.get(id=sensor_id)
                return capteur.client == user.client
            except (Capteur.DoesNotExist, ValueError):
                return False

        if is_many:
            for item in data:
                if 'capteur' in item and not validate_sensor_ownership(item['capteur']):
                    return Response({"detail": "Le capteur spécifié n'appartient pas à votre compte."}, status=status.HTTP_400_BAD_REQUEST)
            serializer = MesureEnergieSerializer(data=data, many=True)
        else:
            if 'capteur' in data and not validate_sensor_ownership(data['capteur']):
                return Response({"detail": "Le capteur spécifié n'appartient pas à votre compte."}, status=status.HTTP_400_BAD_REQUEST)
            serializer = MesureEnergieSerializer(data=data)

        if serializer.is_valid():
            saved = serializer.save()
            # `save()` renvoie une instance (unitaire) ou une liste (lot).
            mesures = saved if isinstance(saved, list) else [saved]

            # Update the last read time for the sensors. Une mesure n'est postée que
            # lorsqu'il y a de la puissance → l'appareil consomme → etatCourant = 'ON'.
            sensor_ids = {m.capteur_id for m in mesures}
            Capteur.objects.filter(id__in=sensor_ids).update(
                derniereLecture=timezone.now(), etatCourant='ON')

            # Détection d'anomalies sur TOUTES les mesures du lot (pas seulement la
            # dernière), de manière synchrone pour un retour UI immédiat. En cas
            # d'échec, on journalise sans casser l'ingestion.
            try:
                from apps.alerts.utils import evaluate_measurements
                evaluate_measurements(user.client, sensor_ids, mesures=mesures)
            except Exception:
                logger.exception("Échec de l'évaluation des anomalies à l'ingestion")

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MesureSerieView(APIView):
    """Série AGRÉGÉE pour le graphe du dashboard.

    Le graphe tirait `/api/mesures/` = TOUTES les mesures brutes (postées toutes les
    ~0,2 s) → ~2,4 Mo et ~7 s pour 7 jours, rechargés en boucle. Ici on agrège côté
    serveur : un bucket par HEURE (vue jour) ou par JOUR (semaine/mois), une ligne
    par (bucket, capteur). Résultat : quelques Ko, ~0,3 s.

    Champs renvoyés compatibles avec les mesures brutes (`timestamp`, `capteur_id`,
    `puissance`, `energie`) pour que `aggregateTelemetry` côté front fonctionne sans
    changement : puissance = MOYENNE du créneau, energie = SOMME du créneau.
    """
    authentication_classes = [DeviceAPIKeyAuthentication] + list(APIView.authentication_classes)
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent voir leurs mesures."},
                            status=status.HTTP_403_FORBIDDEN)

        qs = MesureEnergie.objects.filter(capteur__client=user.client)
        sensor_id, err = _sensor_uuid(request.query_params)
        if err:
            return err
        if sensor_id:
            qs = qs.filter(capteur_id=sensor_id)

        now = timezone.now()
        # Plage libre (comparaison) prioritaire ; sinon période prédéfinie.
        date_from = MesureEnergieView._parse_date(request.query_params.get('date_from'))
        date_to = MesureEnergieView._parse_date(request.query_params.get('date_to'))
        if date_from or date_to:
            if date_from:
                qs = qs.filter(timestamp__date__gte=date_from)
            if date_to:
                qs = qs.filter(timestamp__date__lte=date_to)
            span = (date_to - date_from).days if (date_from and date_to) else 7
            par_heure = span <= 1  # une plage d'un seul jour → granularité horaire
        else:
            period = request.query_params.get('period', 'week')
            if period == 'day':
                qs = qs.filter(timestamp__gte=now - timedelta(days=1)); par_heure = True
            elif period == 'month':
                qs = qs.filter(timestamp__gte=now - timedelta(days=30)); par_heure = False
            else:
                qs = qs.filter(timestamp__gte=now - timedelta(days=7)); par_heure = False

        trunc = TruncHour('timestamp') if par_heure else TruncDay('timestamp')
        rows = (qs.annotate(bucket=trunc)
                  .values('bucket', 'capteur_id')
                  .annotate(p=Avg('puissance'), e=Sum('energie'))
                  .order_by('bucket'))

        data = [{
            'timestamp': r['bucket'].isoformat(),
            'capteur_id': str(r['capteur_id']),
            'puissance': float(r['p'] or 0),
            'energie': float(r['e'] or 0),
        } for r in rows]
        return Response(data)


# ---------------------------------------------------------------------------
# Espace Technicien (cas d'utilisation : enregistrer ESP32, générer API Key,
# associer dispositif au client, calibrer capteur, pannes et interventions)
# ---------------------------------------------------------------------------

def _generate_api_key():
    return f"aoceda_esp32_{secrets.token_hex(16)}"


class DispositifListCreateView(generics.ListCreateAPIView):
    """Enregistrer un nouvel ESP32 (la clé API est générée côté serveur)."""
    serializer_class = DispositifSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        queryset = Dispositif.objects.select_related('client').all()
        client_id = self.request.query_params.get('client')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(apiKeyDevice=_generate_api_key())


class DispositifDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Consulter, ré-associer à un client ou retirer un dispositif."""
    serializer_class = DispositifSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]
    queryset = Dispositif.objects.select_related('client').all()


class DispositifRegenererCleView(APIView):
    """Générer une nouvelle API Key pour un dispositif existant."""
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def post(self, request, pk):
        try:
            dispositif = Dispositif.objects.get(pk=pk)
        except Dispositif.DoesNotExist:
            return Response({"detail": "Dispositif introuvable."}, status=status.HTTP_404_NOT_FOUND)
        dispositif.apiKeyDevice = _generate_api_key()
        dispositif.save(update_fields=['apiKeyDevice'])
        return Response(DispositifSerializer(dispositif).data)


class CapteurTechnicienListCreateView(generics.ListCreateAPIView):
    """Installer un capteur (ZMCT103C) sur un dispositif d'un client."""
    serializer_class = CapteurTechnicienSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        queryset = Capteur.objects.select_related('client', 'dispositif').order_by('nom')
        client_id = self.request.query_params.get('client')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        return queryset


class CapteurTechnicienDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Calibrer un capteur (coeffCalibration), l'activer/désactiver."""
    serializer_class = CapteurTechnicienSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]
    queryset = Capteur.objects.select_related('client', 'dispositif').order_by('nom')


class InterventionListCreateView(generics.ListCreateAPIView):
    """Créer une intervention (installation, calibration, panne, maintenance)."""
    serializer_class = InterventionSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        user = self.request.user
        queryset = Intervention.objects.select_related('technicien', 'client', 'capteur').all()
        # Un technicien ne voit que ses propres interventions, un admin voit tout
        if hasattr(user, 'technicien'):
            queryset = queryset.filter(technicien=user.technicien)
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if hasattr(user, 'technicien'):
            # Le technicien connecté est automatiquement assigné
            serializer.save(technicien=user.technicien)
        elif serializer.validated_data.get('technicien'):
            # Admin qui spécifie explicitement le technicien dans le body
            serializer.save()
        else:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"technicien": "Un administrateur doit spécifier le technicien assigné."})


class InterventionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Mettre à jour le statut / résultat d'une intervention."""
    serializer_class = InterventionSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        user = self.request.user
        queryset = Intervention.objects.all()
        if hasattr(user, 'technicien'):
            queryset = queryset.filter(technicien=user.technicien)
        return queryset


class RapportInterventionView(APIView):
    """Générer le rapport d'une intervention terminée."""
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def post(self, request, pk):
        try:
            intervention = Intervention.objects.get(pk=pk)
        except Intervention.DoesNotExist:
            return Response({"detail": "Intervention introuvable."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if hasattr(user, 'technicien') and intervention.technicien_id != user.technicien.id:
            return Response({"detail": "Cette intervention ne vous est pas assignée."},
                            status=status.HTTP_403_FORBIDDEN)

        if hasattr(intervention, 'rapport'):
            return Response({"detail": "Un rapport existe déjà pour cette intervention."},
                            status=status.HTTP_400_BAD_REQUEST)

        # request.data peut être un QueryDict (formulaire) : on extrait champ par champ
        data = {
            'intervention': intervention.id,
            'contenu': request.data.get('contenu', ''),
            'conclusion': request.data.get('conclusion'),
        }
        if 'estValidé' in request.data:
            data['estValidé'] = request.data.get('estValidé')
        serializer = RapportInterventionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RapportInterventionPDFView(APIView):
    """Rapport d'intervention au format PDF — document d'archive téléchargeable.

    Même socle documentaire que les exports client (apps.analytics.pdf) : en-tête
    de marque, référence traçable, cartes d'identification, pagination X sur Y.
    Accessible au technicien ASSIGNÉ et aux administrateurs, comme la création."""
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    TYPE_LIBELLES = dict(Intervention.TYPE_CHOICES)
    STATUT_LIBELLES = dict(Intervention.STATUT_CHOICES)

    def get(self, request, pk):
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer
        from apps.analytics import pdf as pdfdoc

        try:
            intervention = (Intervention.objects
                            .select_related('technicien', 'client', 'capteur', 'dispositif')
                            .get(pk=pk))
        except Intervention.DoesNotExist:
            return Response({"detail": "Intervention introuvable."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if hasattr(user, 'technicien') and intervention.technicien_id != user.technicien.id:
            return Response({"detail": "Cette intervention ne vous est pas assignée."},
                            status=status.HTTP_403_FORBIDDEN)

        rapport = getattr(intervention, 'rapport', None)
        if rapport is None:
            return Response({"detail": "Aucun rapport n'a encore été rédigé pour cette intervention."},
                            status=status.HTTP_404_NOT_FOUND)

        st = pdfdoc.get_styles()
        ref = pdfdoc.reference_document('INT', intervention)
        date_iv = timezone.localtime(intervention.dateIntervention)

        carte_intervention = [
            ("Type", self.TYPE_LIBELLES.get(intervention.typeIntervention, intervention.typeIntervention)),
            ("Statut", self.STATUT_LIBELLES.get(intervention.statut, intervention.statut)),
            ("Date d'intervention", date_iv.strftime('%d/%m/%Y à %H:%M')),
            ("Technicien", intervention.technicien.nom),
        ]
        carte_contexte = [
            ("Référence", ref),
            ("Client", intervention.client.nom if intervention.client else "—"),
            ("Dispositif", intervention.dispositif.nom if intervention.dispositif else "—"),
            ("Capteur", intervention.capteur.nom if intervention.capteur else "—"),
            ("Édité le", timezone.localtime().strftime('%d/%m/%Y à %H:%M')),
        ]
        el = [pdfdoc.panneau_identification(
            [("Intervention", carte_intervention), ("Contexte", carte_contexte)], st)]

        # Corps du document : chaque texte saisi passe par texte_libre (échappement
        # XML + repli Latin-1) et les retours à la ligne deviennent des <br/>.
        def _bloc(titre, texte, vide):
            el.extend(pdfdoc.section(titre, st))
            if texte and str(texte).strip():
                el.append(Paragraph(
                    pdfdoc.texte_libre(texte).replace('\n', '<br/>'), st['body']))
            else:
                el.append(Paragraph(vide, st['meta']))
            el.append(Spacer(1, 1.5 * mm))

        _bloc("Description de la demande", intervention.description,
              "Aucune description enregistrée.")
        _bloc("Résultat des travaux", getattr(intervention, 'résultat', None),
              "Aucun résultat enregistré.")
        _bloc("Rapport du technicien", rapport.contenu,
              "Rapport vide.")
        # La conclusion n'est affichée que si elle apporte autre chose que le contenu
        # (l'ancien front la dupliquait à l'identique).
        if rapport.conclusion and rapport.conclusion.strip() and \
                rapport.conclusion.strip() != (rapport.contenu or '').strip():
            _bloc("Conclusion", rapport.conclusion, "")

        el.extend(pdfdoc.section("Traçabilité", st))
        el.append(Paragraph(
            f"Rapport rédigé le {timezone.localtime(rapport.dateGénération).strftime('%d/%m/%Y à %H:%M')}"
            f" par {pdfdoc.texte_libre(intervention.technicien.nom)} · "
            + ("Validé par le technicien." if rapport.estValidé else "Non validé."),
            st['note']))

        contenu_pdf = pdfdoc.build_pdf("Rapport d'intervention", ref, el)
        resp = HttpResponse(contenu_pdf, content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="aoceda_intervention_{date_iv.strftime("%Y%m%d")}_{str(intervention.pk)[:8]}.pdf"')
        return resp


# ---------------------------------------------------------------------------
# Pool de capteurs ZMCT disponibles + ingestion données temps réel
# ---------------------------------------------------------------------------

class CapteurDisponiblesView(generics.ListAPIView):
    """Liste tous les capteurs non encore assignés à un client (pool d'installation)."""
    serializer_class = CapteurTechnicienSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        return Capteur.objects.filter(client__isnull=True).order_by('nom')


class CapteurAssignerView(APIView):
    """Assigne un capteur disponible (client=None) à un client existant."""
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def post(self, request, pk):
        try:
            capteur = Capteur.objects.get(pk=pk, client__isnull=True)
        except Capteur.DoesNotExist:
            return Response(
                {"detail": "Capteur introuvable ou déjà assigné à un client."},
                status=status.HTTP_404_NOT_FOUND,
            )

        client_id = request.data.get('client')
        if not client_id:
            return Response({"detail": "Le champ 'client' (UUID) est requis."}, status=status.HTTP_400_BAD_REQUEST)

        from apps.accounts.models import Client
        try:
            client = Client.objects.get(pk=client_id)
        except (Client.DoesNotExist, ValueError):
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        capteur.client = client
        capteur.save(update_fields=['client'])
        return Response(CapteurTechnicienSerializer(capteur).data, status=status.HTTP_200_OK)


class ZMCTIngestionView(APIView):
    """Reçoit les mesures ZMCT103C envoyées par l'ESP32 via WiFi.

    Auth : Authorization: Device <apiKeyDevice>
    Body : liste ou objet JSON {capteur_index, courant, puissance, etat, ...}
    Le dispositif doit être assigné à un client (sinon 401).
    """
    authentication_classes = [DeviceAPIKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        device = request.auth      # Dispositif (avec client déjà chargé via select_related)
        client = device.client     # Client, garanti non-None par DeviceAPIKeyAuthentication

        data = request.data
        items = data if isinstance(data, list) else [data]

        serializer = ZMCTMesureSerializer(data=items, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Capteurs de ce dispositif, triés par nom (Lampe Salon < Prise Cuisine)
        capteurs = list(
            Capteur.objects.filter(dispositif=device, client=client).order_by('nom')
        )
        if not capteurs:
            return Response(
                {"detail": "Aucun capteur configuré pour ce dispositif."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        mesures_a_creer = []

        for item in serializer.validated_data:
            idx = item['capteur_index'] - 1  # capteur_index est 1-basé
            if idx >= len(capteurs):
                continue
            capteur = capteurs[idx]
            facteur = float(capteur.coeffCalibration or 1.0)
            puissance = float(item['puissance']) * facteur
            courant   = float(item['courant'])   * facteur
            # Énergie intégrée sur l'intervalle réel depuis la mesure précédente
            # (défaut 2 s pour la 1re mesure), plus de fenêtre fixe qui sous-comptait.
            energie = _energie_kwh(capteur, puissance, now, defaut_s=2.0)

            mesures_a_creer.append(MesureEnergie(
                capteur=capteur,
                courant=courant,
                puissance=puissance,
                energie=energie,
                tension_V=220.0,
                timestamp=now,
            ))

        if mesures_a_creer:
            MesureEnergie.objects.bulk_create(mesures_a_creer)
            sensor_ids = {m.capteur_id for m in mesures_a_creer}
            Capteur.objects.filter(id__in=sensor_ids).update(derniereLecture=now, etatCourant='ON')
            device.estConnecté = True
            device.save(update_fields=['estConnecté'])

            try:
                from apps.alerts.utils import evaluate_measurements
                evaluate_measurements(client, sensor_ids, mesures=mesures_a_creer)
            except Exception:
                logger.exception("Évaluation des anomalies ZMCT échouée")

        return Response({"created": len(mesures_a_creer)}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Ingestion Arduino via pont série (serial_bridge.py) + flux SSE temps réel
# ---------------------------------------------------------------------------

class ArduinoIngestionView(APIView):
    """Reçoit les mesures parsées depuis serial_bridge.py.

    Auth : header  X-Bridge-Token: <ARDUINO_BRIDGE_TOKEN>
    Body : { capteur, etat, courant, puissance }
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from django.conf import settings
        token = request.headers.get('X-Bridge-Token', '')
        expected = getattr(settings, 'ARDUINO_BRIDGE_TOKEN', '')
        if not expected or token != expected:
            return Response({"detail": "Token invalide."}, status=status.HTTP_403_FORBIDDEN)

        capteur_nom = request.data.get('capteur')
        courant_raw = request.data.get('courant')
        puissance_raw = request.data.get('puissance')
        etat = request.data.get('etat', 'OFF')

        if not capteur_nom:
            return Response({"detail": "Champ 'capteur' requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            capteur = Capteur.objects.get(nom=capteur_nom)
        except Capteur.DoesNotExist:
            return Response(
                {"detail": f"Capteur '{capteur_nom}' introuvable. Lancez d'abord 'python manage.py setup_nguessan'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Capteur.MultipleObjectsReturned:
            capteur = Capteur.objects.filter(nom=capteur_nom).first()

        facteur = float(capteur.coeffCalibration or 1.0)
        courant   = (float(courant_raw)   * facteur) if courant_raw   is not None else 0.0
        puissance = (float(puissance_raw) * facteur) if puissance_raw is not None else 0.0
        now = timezone.now()

        # N'enregistre une mesure que quand l'appareil est ON.
        # Fenêtre firmware = 100 ms × 2 capteurs → intervalle ≈ 0.2 s par capteur.
        # Évite aussi de polluer la DB avec des milliers d'enregistrements à 0 W.
        if etat == 'ON' and puissance > 0:
            # Énergie intégrée sur l'intervalle réel depuis la mesure précédente
            # (défaut 0,2 s à la 1re mesure), plus de fenêtre fixe qui sous-comptait ~20×.
            energie = _energie_kwh(capteur, puissance, now, defaut_s=0.2)
            MesureEnergie.objects.create(
                capteur=capteur,
                courant=courant,
                puissance=puissance,
                energie=energie,
                tension_V=220.0,
                timestamp=now,
            )

        # Toujours mettre à jour le CONTACT (capteur vivant même si OFF) ET l'état réel
        # instantané rapporté par le pont. On considère « ON » seulement si le firmware
        # dit ON ET qu'une puissance est effectivement mesurée (>0), sinon « OFF ».
        capteur.derniereLecture = now
        capteur.etatCourant = 'ON' if (etat == 'ON' and puissance > 0) else 'OFF'
        capteur.save(update_fields=['derniereLecture', 'etatCourant'])

        return Response({"ok": True, "capteur": capteur_nom, "etat": capteur.etatCourant})


class CapteurCalibrerView(APIView):
    """Calibration automatique : l'utilisateur saisit la puissance réelle de l'appareil
    allumé, le système calcule et enregistre le facteur de correction dans coeffCalibration."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not hasattr(user, 'technicien'):
            return Response({"detail": "Réservé aux techniciens."},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            capteur = Capteur.objects.get(pk=pk)
        except Capteur.DoesNotExist:
            return Response({"detail": "Capteur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            puissance_reelle = float(request.data.get('puissance_reelle', ''))
            if puissance_reelle <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({"detail": "Saisissez une puissance réelle positive (ex. 13.0)."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Dernière mesure non nulle AVANT calibration (valeur brute du capteur)
        derniere = MesureEnergie.objects.filter(capteur=capteur, puissance__gt=0) \
                                        .order_by('-timestamp').first()
        if not derniere:
            return Response(
                {"detail": "Aucune mesure disponible. Allumez l'appareil et attendez 5 secondes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # La valeur stockée a déjà été multipliée par l'ancien facteur → on ramène à la valeur brute
        ancien_facteur = float(capteur.coeffCalibration or 1.0)
        puissance_brute = float(derniere.puissance) / ancien_facteur
        nouveau_facteur = puissance_reelle / puissance_brute

        if not (0.01 <= nouveau_facteur <= 100.0):
            return Response(
                {"detail": (f"Facteur calculé ({nouveau_facteur:.3f}×) hors limites [0.01–100]. "
                            f"Valeur brute du capteur : {puissance_brute:.1f} W.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from decimal import Decimal
        capteur.coeffCalibration = Decimal(str(round(nouveau_facteur, 4)))
        capteur.save(update_fields=['coeffCalibration'])

        return Response({
            "capteur_id": str(capteur.id),
            "capteur_nom": capteur.nom,
            "puissance_reelle_W": puissance_reelle,
            "puissance_brute_W": round(puissance_brute, 2),
            "nouveau_facteur": float(capteur.coeffCalibration),
            "message": (f"Calibration OK : ×{float(capteur.coeffCalibration):.4f} "
                        f"({puissance_brute:.1f} W brut → {puissance_reelle:.1f} W réel)"),
        }, status=status.HTTP_200_OK)


class MesureStreamView(View):
    """Server-Sent Events : pousse les dernières mesures toutes les 3 s.

    Vue Django standard (pas DRF) pour éviter le 406 sur text/event-stream.
    Auth : ?token=<JWT access token>   (EventSource ne supporte pas les headers)
    """

    def get(self, request):
        token = request.GET.get('token', '')
        if not token:
            return HttpResponse('Token manquant.', status=401, content_type='text/plain')

        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from apps.accounts.models import Utilisateur
            access = AccessToken(token)
            user = Utilisateur.objects.get(id=access['user_id'])
        except Exception:
            return HttpResponse('Token invalide.', status=401, content_type='text/plain')

        if not hasattr(user, 'client'):
            return HttpResponse('Accès réservé aux clients.', status=403, content_type='text/plain')

        client = user.client

        def event_stream():
            while True:
                try:
                    capteurs = list(Capteur.objects.filter(client=client, actif=True))
                    mesures = []
                    for cap in capteurs:
                        latest = MesureEnergie.objects.filter(capteur=cap).order_by('-timestamp').first()
                        on = (cap.etatCourant == 'ON')
                        mesures.append({
                            'id': str(cap.id),
                            'nom': cap.nom,
                            # Puissance/courant INSTANTANÉS : 0 si l'appareil est éteint
                            # (ne pas ressortir une mesure périmée comme si elle était live).
                            'courant': (float(latest.courant) if latest else 0.0) if on else 0.0,
                            'puissance': (float(latest.puissance) if latest else 0.0) if on else 0.0,
                            # État réel persisté (pont/firmware), plus déduit d'une mesure périmée.
                            'etat': cap.etatCourant,
                            # Contact matériel réel (mis à jour à chaque lecture) → en ligne/hors ligne.
                            'derniereLecture': cap.derniereLecture.isoformat() if cap.derniereLecture else None,
                            # Horodatage de la dernière CONSOMMATION (info « dernière activité »).
                            'derniereMesure': latest.timestamp.isoformat() if latest else None,
                        })
                    payload = json.dumps({'mesures': mesures, 'ts': timezone.now().isoformat()})
                    yield f"data: {payload}\n\n"
                except Exception as exc:
                    yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                time.sleep(3)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
