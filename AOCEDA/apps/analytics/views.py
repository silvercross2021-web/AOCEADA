import calendar
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Avg, Count, Min, Max, Q  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate  # pyrefly: ignore [untyped-import]
from datetime import timedelta, datetime as _datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import Prevision
from .serializers import PrevisionSerializer
from .tarifs_cie import calculer_facture_pour_client, prix_kwh_tout_compris
from apps.sensors.models import Capteur, MesureEnergie

MOIS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
           "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _fcfa_affiche(detail):
    """Total ENTIER affiché = somme des lignes arrondies (HALF_UP, comme JS Math.round).
    Garantit deux invariants : (1) somme des lignes affichées == Total ; (2) KPI (backend)
    == Total de la carte (front). On arrondit chaque composante puis on somme (jamais
    round de la somme exacte, qui pouvait diverger d'1 FCFA sur les valeurs en ,50)."""
    q = lambda v: Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    total = (q(detail['tranche1_fcfa']) + q(detail['tranche2_fcfa'])
             + q(detail['prime_fixe_fcfa']) + q(detail['taxes_fcfa']))
    return int(total)


def _credit_payload(info):
    """Rend le crédit prépayé compatible JSON (floats), ou None si postpayé."""
    if not info:
        return None
    return {
        "recharge_fcfa": float(info["recharge_fcfa"]),
        "consomme_fcfa": float(info["consomme_fcfa"]),
        "restant_fcfa": float(info["restant_fcfa"]),
        "cout_jour_fcfa": float(info["cout_jour_fcfa"]),
        "jours_restants": info["jours_restants"],
    }


def _kwh_consommes(client, depuis, jusqua):
    """Énergie consommée (kWh) sur la période.

    1) Source fiable : somme du champ `energie` (kWh) des mesures.
    2) Repli si `energie` absent : estimation par la puissance moyenne mesurée
       multipliée par la DURÉE RÉELLE couverte (tmax − tmin), sans supposer une
       fréquence d'échantillonnage fixe — bien plus robuste qu'un /60000.
    """
    agg = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=depuis, timestamp__lte=jusqua
    ).aggregate(e=Sum('energie'), pm=Avg('puissance'), n=Count('id'),
                tmin=Min('timestamp'), tmax=Max('timestamp'))

    total_energie = agg['e'] or Decimal('0')
    if total_energie > 0:
        return Decimal(total_energie)

    n = agg['n'] or 0
    if n == 0:
        return Decimal('0')
    avg_w = Decimal(str(agg['pm'] or 0))
    if n >= 2 and agg['tmin'] and agg['tmax']:
        span_h = Decimal(str((agg['tmax'] - agg['tmin']).total_seconds() / 3600.0))
        if span_h > 0:
            return avg_w / Decimal('1000') * span_h
    # Mesure unique : durée non fiable → estimation horaire prudente (1 h)
    return avg_w / Decimal('1000')


def facture_mois_a_ce_jour(client):
    """Facture RÉELLE du mois à ce jour : coût CIE des kWh RÉELLEMENT consommés
    depuis le 1er du mois, valorisés avec la grille complète selon l'ampérage
    (tranches/lots, prime fixe, taxes, TVA 18 % incluse).

    AUCUNE projection du futur : le montant ne monte que quand le client consomme,
    reste figé s'il n'allume rien, et devient sa facture réelle en fin de mois.
    Le passage d'une tranche à l'autre (ex. > 198 kWh en 10A) est géré par le
    moteur tarifaire : les kWh au-delà du seuil basculent au tarif de la tranche 2.
    """
    now = timezone.localtime()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    jours_du_mois = calendar.monthrange(now.year, now.month)[1]

    consommes = _kwh_consommes(client, start_of_month, now)
    detail = calculer_facture_pour_client(consommes, client)
    return {
        "annee_mois": now.strftime("%Y-%m"),
        "mois_libelle": f"{MOIS_FR[now.month - 1]} {now.year}",
        "jours_du_mois": jours_du_mois,
        "jours_ecoules": now.day,
        "kwh_consommes": consommes.quantize(Decimal('0.01')),
        "detail": detail,
    }


class PrevisionListView(generics.ListAPIView):
    serializer_class = PrevisionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            # Automatically calculate/update the current month's forecast before returning
            self.generate_forecast_for_client(user.client)
            return Prevision.objects.filter(client=user.client)
        return Prevision.objects.none()

    def generate_forecast_for_client(self, client):
        # Snapshot RÉEL du mois à ce jour (pas de projection). Pour les mois passés,
        # ce snapshot = la facture finale réelle ; pour le mois courant il s'affine
        # à chaque consultation.
        fac = facture_mois_a_ce_jour(client)
        kwh = fac["kwh_consommes"]
        fcfa = _fcfa_affiche(fac["detail"])  # entier (somme des lignes) = KPI = carte

        # Écart réel par rapport au mois précédent (si connu)
        now = timezone.localtime()
        prev_annee_mois = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        precedente = Prevision.objects.filter(client=client, annee_mois=prev_annee_mois).first()
        if precedente and precedente.montantEstimé_FCFA:
            ecart = (fcfa - precedente.montantEstimé_FCFA) / precedente.montantEstimé_FCFA * 100
            ecart = max(min(ecart, Decimal('999')), Decimal('-999'))
        else:
            ecart = Decimal('0')

        # Supprimer les doublons éventuels avant update_or_create
        qs = Prevision.objects.filter(client=client, annee_mois=fac["annee_mois"])
        if qs.count() > 1:
            ids = list(qs.values_list('id', flat=True))
            Prevision.objects.filter(id__in=ids[:-1]).delete()

        Prevision.objects.update_or_create(
            client=client,
            annee_mois=fac["annee_mois"],
            defaults={
                'moisConcerné': fac["mois_libelle"],
                'consomméeEstimée_kWh': round(kwh, 2),
                'montantEstimé_FCFA': round(fcfa, 0),
                'écartSurMoisPrécédent': round(ecart, 2),
            }
        )


class FactureDetailView(APIView):
    """Décomposition officielle CIE de la facture du mois en cours
    (grille EXPLICATION_TARIFAIRE.md : tranches, prime fixe, taxes — TVA incluse)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à la facture."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        from apps.alerts.utils import credit_prepaye_info
        # Compte sans capteur : état VIDE honnête, cohérent avec AnalyticsSummaryView —
        # surtout PAS le plancher « abonnement fixe » présenté comme une facture réelle.
        # Sans champ tranche1, le front (loadFacture) garde state.facture nul et la carte
        # retombe sur le 0 du résumé → aucune contradiction KPI (#kpi-bill) / carte.
        if not Capteur.objects.filter(client=client).exists():
            return Response({
                "mode": "vide",
                "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
                "credit_prepaye": _credit_payload(credit_prepaye_info(client)),
            })
        fac = facture_mois_a_ce_jour(client)
        d = fac["detail"]
        # Regroupement LISIBLE pour le client, en 2 seaux qui somment EXACTEMENT au KPI :
        #  • abonnement fixe = prime fixe + taxe fixe (dû chaque mois, quoi qu'on consomme)
        #  • consommation    = le reste (tranches + taxes par kWh) = total - abonnement
        # « consommation » dérivé par soustraction → garantit seau1 + seau2 == total affiché.
        def _r1(x):
            return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        total_affiche = _fcfa_affiche(d)
        abonnement_fixe = _r1(d["prime_fixe_fcfa"]) + _r1(d["taxe_fixe_fcfa"])
        consommation_fcfa = total_affiche - abonnement_fixe
        return Response({
            "credit_prepaye": _credit_payload(credit_prepaye_info(client)),
            "mois": fac["mois_libelle"],
            "annee_mois": fac["annee_mois"],
            "jours_du_mois": fac["jours_du_mois"],
            "jours_ecoules": fac["jours_ecoules"],
            "kwh_consommes": float(fac["kwh_consommes"]),
            # kwh_projetes conservé pour compat front, mais = consommé réel (plus de projection)
            "kwh_projetes": float(fac["kwh_consommes"]),
            "type_tarif": d["type_tarif"],
            "amperage": d["amperage"],
            "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
            "seuil_t1_kwh": float(d["seuil_t1_kwh"]),
            "tranche1": {"kwh": float(d["tranche1_kwh"]), "prix": float(d["tranche1_prix"]), "fcfa": float(d["tranche1_fcfa"])},
            "tranche2": {"kwh": float(d["tranche2_kwh"]), "prix": float(d["tranche2_prix"]), "fcfa": float(d["tranche2_fcfa"])},
            "prime_fixe_fcfa": float(d["prime_fixe_fcfa"]),
            "taxes_fcfa": float(d["taxes_fcfa"]),
            "taxes_variable_fcfa": float(d["taxes_variable_fcfa"]),
            "taxe_fixe_fcfa": float(d["taxe_fixe_fcfa"]),
            "taxes_par_kwh": float(d["taxes_par_kwh"]),
            "total_fcfa": float(d["total_fcfa"]),
            # Total ENTIER canonique (somme des lignes arrondies) = KPI du dashboard
            "total_fcfa_arrondi": total_affiche,
            # Vue SIMPLE en 2 parts (abonnement + consommation == total_fcfa_arrondi)
            "abonnement_fixe_fcfa": abonnement_fixe,
            "consommation_fcfa": consommation_fcfa,
            "prix_moyen_kwh": float(d["prix_moyen_kwh"]),
            "prix_kwh_tout_compris": float(prix_kwh_tout_compris(client)),
            "tva_incluse": True,
        })


class RechargePrepayeeView(APIView):
    """Recharge le crédit prépayé du client (compteurs prépayés uniquement)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent recharger leur crédit."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
            return Response({"detail": "La recharge ne concerne que les compteurs prépayés."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            montant = Decimal(str(request.data.get('montant')))
        except (TypeError, ValueError, InvalidOperation):
            return Response({"detail": "Montant de recharge invalide."},
                            status=status.HTTP_400_BAD_REQUEST)
        if montant <= 0:
            return Response({"detail": "Le montant de recharge doit être positif."},
                            status=status.HTTP_400_BAD_REQUEST)

        client.creditPrepaye_FCFA = (client.creditPrepaye_FCFA or Decimal('0')) + montant
        client.save(update_fields=['creditPrepaye_FCFA'])

        from apps.alerts.utils import credit_prepaye_info
        return Response({
            "detail": f"Recharge de {int(montant)} FCFA effectuée.",
            "credit_prepaye": _credit_payload(credit_prepaye_info(client)),
        }, status=status.HTTP_201_CREATED)


class AnalyticsSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à l'analyse."}, status=status.HTTP_403_FORBIDDEN)
            
        client = user.client
        now = timezone.now()
        from apps.alerts.models import Alerte
        from apps.alerts.utils import credit_prepaye_info, check_credit_prepaye

        # Compte sans aucun capteur : on renvoie un état VIDE honnête (zéros),
        # jamais de fausses valeurs présentées comme réelles.
        if not Capteur.objects.filter(client=client).exists():
            credit = credit_prepaye_info(client)
            return Response({
                "puissance_instantanee": 0,
                "consommation_jour_kwh": 0,
                "facture_estimee_fcfa": 0,
                "alertes_actives": Alerte.objects.filter(client=client, lue=False).count(),
                "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
                "credit_prepaye": _credit_payload(credit),
                "last_update": now.isoformat(),
                "mode": "vide",
            })

        # 1. Instantaneous power (sum of last measurement of active sensors)
        active_sensors = Capteur.objects.filter(client=client, actif=True)
        instantaneous_w = Decimal('0')
        # Fenêtre de fraîcheur : une mesure de plus de 60 s n'est PLUS « instantanée »
        # (un capteur muet depuis des heures ne doit pas gonfler la puissance affichée).
        # Aligne puissance_instantanee sur ce que le flux SSE agrège côté client.
        frais = now - timedelta(seconds=60)
        for sensor in active_sensors:
            last_m = MesureEnergie.objects.filter(
                capteur=sensor, timestamp__gte=frais
            ).order_by('-timestamp').first()
            if last_m:
                instantaneous_w += last_m.puissance

        # 2. Daily consumption in kWh (somme du champ energie, repli puissance/min)
        debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        today_kwh = _kwh_consommes(client, debut_jour, now)

        # 3. Facture RÉELLE du mois à ce jour (coût CIE des kWh réellement consommés)
        fac = facture_mois_a_ce_jour(client)
        montant_estime = _fcfa_affiche(fac["detail"])  # entier = somme des lignes (== carte)
        # Mémorise le snapshot du mois (pour l'historique et l'écart)
        PrevisionListView().generate_forecast_for_client(client)

        # 4. Crédit prépayé + déclenchement éventuel de l'alerte « Crédit bas »
        check_credit_prepaye(client)
        credit = credit_prepaye_info(client)

        # 5. Count of active alerts (après l'éventuelle alerte crédit bas)
        active_alerts_count = Alerte.objects.filter(client=client, lue=False).count()

        return Response({
            # HALF_UP comme JS Math.round (l'ancien int() tronquait → 1 W/1 F d'écart)
            "puissance_instantanee": int(instantaneous_w.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            "consommation_jour_kwh": round(float(today_kwh), 2),
            "facture_estimee_fcfa": montant_estime,  # déjà entier (somme des lignes, == carte)
            "alertes_actives": active_alerts_count,
            "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
            "credit_prepaye": _credit_payload(credit),
            "last_update": now.isoformat(),
            "mode": "production"
        })


class HistoriqueJournalierView(APIView):
    """Agrégation JOURNALIÈRE côté serveur pour la page Historique.

    Au lieu de renvoyer des milliers de mesures brutes (lent : ~0,9 Mo pour 4000
    mesures, et ça explose avec un ESP32 qui poste toutes les 2 s), on renvoie UNE
    ligne par jour, agrégée en base : énergie, pic, puissance moyenne, part nocturne,
    nb de mesures. Payload minuscule → page instantanée.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à l'historique."},
                            status=status.HTTP_403_FORBIDDEN)
        qs = MesureEnergie.objects.filter(capteur__client=user.client)

        sensor_id = request.query_params.get('sensor_id')
        if sensor_id:
            qs = qs.filter(capteur_id=sensor_id)

        now = timezone.now()
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        def _pd(v):
            try:
                return _datetime.strptime(v, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None

        if date_from or date_to:
            a, b = _pd(date_from), _pd(date_to)
            if (date_from and a is None) or (date_to and b is None):
                return Response({"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                                status=status.HTTP_400_BAD_REQUEST)
            if a and b and a > b:
                return Response({"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                                status=status.HTTP_400_BAD_REQUEST)
            if a:
                qs = qs.filter(timestamp__date__gte=a)
            if b:
                qs = qs.filter(timestamp__date__lte=b)
        else:
            period = request.query_params.get('period', 'week')
            days = {'day': 1, 'week': 7, 'month': 30}.get(period, 7)
            qs = qs.filter(timestamp__gte=now - timedelta(days=days))

        tz = timezone.get_current_timezone()
        # __hour et TruncDate respectent le fuseau actif (USE_TZ) → jour/nuit LOCAUX.
        rows = (qs.annotate(jour=TruncDate('timestamp', tzinfo=tz))
                  .values('jour')
                  .annotate(
                      kwh=Sum('energie'),
                      peak=Max('puissance'),
                      avg_w=Avg('puissance'),
                      n=Count('id'),
                      night_kwh=Sum('energie', filter=Q(timestamp__hour__lt=6)),
                  ).order_by('jour'))

        jours = [{
            "date": r['jour'].isoformat(),
            "kwh": float(r['kwh'] or 0),
            "peak_w": round(float(r['peak'] or 0)),
            "avg_w": round(float(r['avg_w'] or 0)),
            "night_kwh": float(r['night_kwh'] or 0),
            "n": r['n'],
        } for r in rows]

        return Response({
            "prix_kwh": float(prix_kwh_tout_compris(user.client)),
            "amperage": getattr(user.client, 'amperage', 10),
            "jours": jours,
        })


class HeatmapView(APIView):
    """Puissance moyenne par (jour de semaine × heure) sur les 7 derniers jours.

    Agrégation SQL (GROUP BY) → payload minuscule (168 cellules max) au lieu de
    renvoyer toutes les mesures brutes. Jamais de valeur fabriquée : une case sans
    mesure est simplement absente de la réponse.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à ces données."},
                            status=status.HTTP_403_FORBIDDEN)
        tz = timezone.get_current_timezone()
        since = timezone.now() - timedelta(days=7)
        qs = MesureEnergie.objects.filter(capteur__client=user.client, timestamp__gte=since)
        rows = (qs.annotate(dow=ExtractIsoWeekDay('timestamp', tzinfo=tz),
                            hr=ExtractHour('timestamp', tzinfo=tz))
                  .values('dow', 'hr')
                  .annotate(avg_w=Avg('puissance'))
                  .order_by('dow', 'hr'))
        # dow : ExtractIsoWeekDay = 1(lundi)…7(dimanche) → on renvoie 0(lundi)…6(dimanche).
        cells = [{"dow": (r['dow'] - 1), "hour": r['hr'], "avg_w": float(r['avg_w'] or 0)}
                 for r in rows if r['dow'] is not None and r['hr'] is not None]
        return Response({"cells": cells})


class ExportCSVView(APIView):
    """Export de l'historique des mesures du client au format CSV (spéc. SHOULD HAVE)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        import csv
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leurs mesures."},
                            status=status.HTTP_403_FORBIDDEN)

        queryset = MesureEnergie.objects.filter(capteur__client=user.client).select_related('capteur')

        sensor_id = request.query_params.get('sensor_id')
        if sensor_id:
            queryset = queryset.filter(capteur_id=sensor_id)

        now = timezone.now()
        # Plage de dates explicite (prioritaire) : le CSV couvre alors exactement la
        # même fenêtre que le tableau à l'écran (ex. « Ce mois » = mois calendaire).
        from datetime import datetime as _dt

        def _parse_date(value):
            try:
                return _dt.strptime(value, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None

        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        if date_from or date_to:
            if date_from:
                queryset = queryset.filter(timestamp__date__gte=date_from)
            if date_to:
                queryset = queryset.filter(timestamp__date__lte=date_to)
        else:
            period = request.query_params.get('period')
            if period == 'day':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=1))
            elif period == 'week':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=7))
            elif period == 'month':
                queryset = queryset.filter(timestamp__gte=now - timedelta(days=30))

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"aoceda_mesures_{now.strftime('%Y%m%d_%H%M')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Horodatage', 'Capteur', 'Puissance (W)', 'Courant (A)',
                         'Energie (kWh)', 'Tension (V)', 'Facteur de puissance'])
        for m in queryset.order_by('timestamp'):
            writer.writerow([
                m.timestamp.isoformat(), m.capteur.nom, m.puissance,
                m.courant, m.energie, m.tension_V, m.facteur_puissance,
            ])
        return response


class AdminStatsView(APIView):
    """Statistiques globales de la plateforme + santé des capteurs (espace admin)."""

    def get_permissions(self):
        from apps.accounts.permissions import IsAdministrateur
        return [permissions.IsAuthenticated(), IsAdministrateur()]

    def get(self, request):
        from apps.accounts.models import Utilisateur
        from apps.sensors.models import Dispositif
        from apps.alerts.models import Alerte

        now = timezone.now()
        offline_threshold = now - timedelta(minutes=10)

        total_clients = Utilisateur.objects.filter(role='client').count()
        total_techniciens = Utilisateur.objects.filter(role='technicien').count()
        capteurs = Capteur.objects.all()
        capteurs_actifs = capteurs.filter(actif=True).count()
        capteurs_hors_ligne = capteurs.filter(
            actif=True).exclude(derniereLecture__gte=offline_threshold).count()

        mesures_24h = MesureEnergie.objects.filter(timestamp__gte=now - timedelta(hours=24)).count()
        alertes_non_lues = Alerte.objects.filter(lue=False).count()
        alertes_24h = Alerte.objects.filter(createdAt__gte=now - timedelta(hours=24)).count()

        return Response({
            "clients_total": total_clients,
            "clients_actifs": Utilisateur.objects.filter(role='client', is_active=True).count(),
            "techniciens_total": total_techniciens,
            "dispositifs_total": Dispositif.objects.count(),
            "dispositifs_connectes": Dispositif.objects.filter(estConnecté=True).count(),
            "capteurs_total": capteurs.count(),
            "capteurs_actifs": capteurs_actifs,
            "capteurs_hors_ligne": capteurs_hors_ligne,
            "mesures_24h": mesures_24h,
            "alertes_non_lues": alertes_non_lues,
            "alertes_24h": alertes_24h,
            "last_update": now.isoformat(),
        })
