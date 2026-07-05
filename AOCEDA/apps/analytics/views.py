import calendar
import math
import statistics
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
from .tarifs_cie import calculer_facture_pour_client, prix_kwh_tout_compris, PUISSANCE_KW
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
       fréquence d'échantillonnage fixe, bien plus robuste qu'un /60000.
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
        # Valeur EXACTE (non arrondie), la prévision doit tarifer sur le MÊME kWh que
        # le détail (cost_to_date), sinon convergence à ±1 F le dernier jour du mois.
        "kwh_consommes_exact": consommes,
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
    (grille EXPLICATION_TARIFAIRE.md : tranches, prime fixe, taxes, TVA incluse)."""
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


def _parse_hist_window(qp, today):
    """(start_date, end_date) en dates LOCALES pour la page Historique, ou (None, err_response).

    Fenêtre ancrée sur des jours CALENDAIRES (le dernier = aujourd'hui pour les périodes) :
    corrige le 1er seau tronqué de l'ancien `now - Ndays` (instant en milieu de journée)."""
    date_from = qp.get('date_from')
    date_to = qp.get('date_to')

    def _pd(v):
        try:
            return _datetime.strptime(v, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    if date_from or date_to:
        a, b = _pd(date_from), _pd(date_to)
        if (date_from and a is None) or (date_to and b is None):
            return None, Response({"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                                  status=status.HTTP_400_BAD_REQUEST)
        if a and b and a > b:
            return None, Response({"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                                  status=status.HTTP_400_BAD_REQUEST)
        end_date = b or today
        start_date = a or (end_date - timedelta(days=6))
        return (start_date, end_date), None
    period = qp.get('period', 'week')
    days = {'day': 1, 'week': 7, 'month': 30}.get(period, 7)
    return (today - timedelta(days=days - 1), today), None


def _parse_sensor_id(qp):
    """UUID du capteur (?sensor_id=…) validé EN AMONT, ou (None, err_response).

    Capteur.id est un UUIDField : filtrer directement avec une valeur non-UUID
    lève une ValidationError que DRF ne convertit pas → 500 au lieu d'un 400.
    Toute vue qui accepte sensor_id doit passer par ici."""
    raw = qp.get('sensor_id')
    if not raw:
        return None, None
    import uuid as _uuid
    try:
        return _uuid.UUID(str(raw)), None
    except (ValueError, AttributeError, TypeError):
        return None, Response({"detail": "Identifiant de capteur invalide."},
                              status=status.HTTP_400_BAD_REQUEST)


def _aggregate_jours(qs, tz):
    """Une ligne par jour : énergie, pic, puissance moyenne, part nocturne, nb de mesures.
    __hour et TruncDate respectent le fuseau actif (USE_TZ) → jour/nuit LOCAUX."""
    rows = (qs.annotate(jour=TruncDate('timestamp', tzinfo=tz))
              .values('jour')
              .annotate(kwh=Sum('energie'), peak=Max('puissance'), avg_w=Avg('puissance'),
                        n=Count('id'), night_kwh=Sum('energie', filter=Q(timestamp__hour__lt=6)))
              .order_by('jour'))
    return [{
        "date": r['jour'].isoformat(),
        "kwh": float(r['kwh'] or 0),
        "peak_w": round(float(r['peak'] or 0)),
        "avg_w": round(float(r['avg_w'] or 0)),
        "night_kwh": float(r['night_kwh'] or 0),
        "n": r['n'],
    } for r in rows]


class RepartitionCapteursView(APIView):
    """Répartition de la consommation PAR CAPTEUR sur une fenêtre récente (défaut 7 jours).

    Montre « où va l'énergie » : la part de chaque appareil (kWh + %) et son pic de puissance.
    Angle absent du reste du dashboard (qui n'affiche que le total). 100 % données réelles :
    liste uniquement les capteurs ayant RÉELLEMENT mesuré sur la période (jamais de 0 fabriqué)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont une répartition par capteur."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        now = timezone.localtime()
        qp = request.query_params
        d_from = (qp.get('from') or '').strip()
        d_to = (qp.get('to') or '').strip()

        mode = 'preset'
        start = end = None
        jours = 7
        # Plage PERSONNALISÉE : deux dates YYYY-MM-DD, bornes incluses (comme le graphe principal).
        if d_from and d_to:
            try:
                f = _datetime.strptime(d_from, '%Y-%m-%d').date()
                t = _datetime.strptime(d_to, '%Y-%m-%d').date()
                if f > t:
                    f, t = t, f
                if (t - f).days > 366:            # borne de sécurité : 1 an max
                    f = t - timedelta(days=366)
                start = timezone.make_aware(_datetime.combine(f, _datetime.min.time()))
                end = timezone.make_aware(_datetime.combine(t, _datetime.max.time()))
                jours = (t - f).days + 1
                mode = 'custom'
            except (ValueError, TypeError):
                start = end = None

        # Sinon : PRESET en nombre de jours (Aujourd'hui = 1, 7 jours, 30 jours…).
        if start is None:
            try:
                jours = int(qp.get('days', 7))
            except (ValueError, TypeError):
                jours = 7
            jours = max(1, min(jours, 366))
            start = (now - timedelta(days=jours - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now

        rows = (MesureEnergie.objects
                .filter(capteur__client=client, timestamp__gte=start, timestamp__lte=end)
                .values('capteur_id', 'capteur__nom')
                .annotate(kwh=Sum('energie'), peak=Max('puissance'), n=Count('id'))
                .order_by('-kwh'))
        capteurs = [{"nom": r['capteur__nom'], "kwh": float(r['kwh'] or 0),
                     "peak_w": round(float(r['peak'] or 0)), "n": r['n']} for r in rows]
        total = sum(c["kwh"] for c in capteurs)
        for c in capteurs:
            c["pct"] = round(c["kwh"] / total * 100) if total > 0 else 0

        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        return Response({
            "mode": mode, "jours": jours,
            "debut": timezone.localtime(start).date().isoformat(),
            "fin": timezone.localtime(end).date().isoformat(),
            "total_kwh": total, "capacite_w": cap_w,
            "amperage": amperage, "capteurs": capteurs,
        })


class HistoriqueMensuelView(APIView):
    """Historique FCFA mensuel RÉEL, avec répartition « abonnement fixe » / « consommation ».

    Chaque mois est RECALCULÉ depuis la conso RÉELLE via le moteur CIE (jamais une estimation
    périmée) → cohérent au franc près avec le héros « facture à ce jour ». Le mois en cours est
    partiel (« à ce jour »). Ne renvoie que les mois RÉELLEMENT couverts (depuis la 1re mesure),
    jamais un mois fabriqué où le client n'avait pas le service."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont un historique mensuel."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client

        first = MesureEnergie.objects.filter(capteur__client=client).aggregate(m=Min('timestamp'))['m']
        if first is None:
            return Response({"mois": []})
        now = timezone.localtime()
        first_local = timezone.localtime(first)

        def _r1(x):
            return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        # Mois du 1er mois mesuré → mois courant (on garde les 6 plus récents).
        months = []
        y, m = first_local.year, first_local.month
        while (y, m) <= (now.year, now.month):
            months.append((y, m))
            m += 1
            if m > 12:
                m, y = 1, y + 1
        months = months[-6:]

        out = []
        for (yy, mm) in months:
            start = now.replace(year=yy, month=mm, day=1, hour=0, minute=0, second=0, microsecond=0)
            is_current = (yy == now.year and mm == now.month)
            if is_current:
                end = now
            else:
                last_day = calendar.monthrange(yy, mm)[1]
                end = start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
            kwh = _kwh_consommes(client, start, end)
            detail = calculer_facture_pour_client(kwh, client)
            fixe = _r1(detail['prime_fixe_fcfa']) + _r1(detail['taxe_fixe_fcfa'])
            total = _fcfa_affiche(detail)
            out.append({
                "annee_mois": f"{yy}-{mm:02d}",
                "mois_libelle": f"{MOIS_FR[mm - 1]} {yy}",
                "kwh": float(kwh),
                "fixe_fcfa": fixe,
                "variable_fcfa": max(0, total - fixe),
                "total_fcfa": total,
                "en_cours": is_current,
            })
        return Response({"mois": out})


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
        base = MesureEnergie.objects.filter(capteur__client=user.client)

        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        if sensor_id:
            base = base.filter(capteur_id=sensor_id)

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        win, err = _parse_hist_window(request.query_params, today)
        if err:
            return err
        start_date, end_date = win

        main_qs = base.filter(timestamp__date__gte=start_date, timestamp__date__lte=end_date)
        jours = _aggregate_jours(main_qs, tz)

        # Période PRÉCÉDENTE de même durée → comparaison honnête (null si aucune donnée avant :
        # jamais de faux « -100 % » ou de comparaison inventée).
        duration = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration - 1)
        prev_qs = base.filter(timestamp__date__gte=prev_start, timestamp__date__lte=prev_end)
        prev_agg = prev_qs.aggregate(kwh=Sum('energie'), peak=Max('puissance'))
        prev_days = prev_qs.annotate(j=TruncDate('timestamp', tzinfo=tz)).values('j').distinct().count()
        previous = None
        if prev_agg['kwh'] is not None or prev_days:
            previous = {
                "kwh": float(prev_agg['kwh'] or 0),
                "peak_w": round(float(prev_agg['peak'] or 0)),
                "days": prev_days,
                "date_from": prev_start.isoformat(),
                "date_to": prev_end.isoformat(),
            }

        # Répartition PAR CAPTEUR sur la fenêtre : rend compte de TOUS les capteurs liés
        # au client (même ceux à 0 sur la période), énergie RÉELLE mesurée. Indépendant
        # du filtre sensor_id (la carte montre toujours l'ensemble des capteurs).
        win_qs = MesureEnergie.objects.filter(
            capteur__client=user.client,
            timestamp__date__gte=start_date, timestamp__date__lte=end_date)
        sums = {r['capteur_id']: r for r in win_qs.values('capteur_id')
                .annotate(kwh=Sum('energie'), peak=Max('puissance'))}
        repartition = []
        for cap in Capteur.objects.filter(client=user.client).values('id', 'nom'):
            agg = sums.get(cap['id'])
            repartition.append({
                "id": str(cap['id']),
                "nom": cap['nom'],
                "kwh": float((agg or {}).get('kwh') or 0),
                "peak_w": round(float((agg or {}).get('peak') or 0)),
            })
        repartition.sort(key=lambda x: x['kwh'], reverse=True)

        return Response({
            "prix_kwh": float(prix_kwh_tout_compris(user.client)),
            "amperage": getattr(user.client, 'amperage', 10),
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "jours": jours,
            "previous": previous,
            "repartition": repartition,
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


def _prevision_fin_de_mois(client):
    """Prévision de la facture de FIN DE MOIS, fourchette honnête, additive, convergente.

    Principe : on part du coût RÉEL à ce jour (certain, = le KPI du héros) et on n'impute
    qu'au TEMPS non encore mesuré (reste d'aujourd'hui + jours capteur hors ligne + jours
    futurs) un débit journalier ROBUSTE (médiane des jours complets, dispersion via MAD).
    Chaque borne (basse/centrale/haute) est ensuite tarifée par le VRAI moteur CIE.

    Garanties dures : forecast >= coût à ce jour ; convergence exacte vers la facture réelle
    le dernier jour ; plafond physique (P souscrite × 24h × jours) → jamais de valeur absurde ;
    aucune division par un prix moyen. Part fixe (abonnement) 100 % certaine, séparée.
    Choix produit validés : fourchette (pas un point), seuil N_MIN=3 jours complets, jours
    hors ligne IMPUTÉS à la conso habituelle (divulgués), calcul 100 % côté serveur (Abidjan).
    """
    tz = timezone.get_current_timezone()
    now = timezone.localtime()
    today = now.day
    D = calendar.monthrange(now.year, now.month)[1]
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    f = min(max((now - midnight).total_seconds() / 86400.0, 0.0), 1.0)  # fraction d'aujourd'hui écoulée
    type_compteur = getattr(client, 'typeCompteur', 'postpaye')
    N_MIN = 3

    # Aucun capteur → état vide honnête
    if not Capteur.objects.filter(client=client).exists():
        return {"mode": "vide", "type_compteur": type_compteur, "jours_du_mois": D, "jours_ecoules": today}

    # Socle RÉEL = exactement le chiffre affiché par le héros (cohérence garantie, plancher du forecast)
    fac = facture_mois_a_ce_jour(client)
    d0 = fac["detail"]
    # kWh EXACT (non arrondi) → _bill(kwh_reel) == cost_to_date au franc près quand U→0.
    kwh_reel = float(fac.get("kwh_consommes_exact", fac["kwh_consommes"]))
    cost_to_date = _fcfa_affiche(d0)
    amperage = int(getattr(client, 'amperage', 10) or 10)
    p_kw = float(PUISSANCE_KW.get(amperage, Decimal("2.2")))

    def _r1(x):
        return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    fixe_certain = _r1(d0["prime_fixe_fcfa"]) + _r1(d0["taxe_fixe_fcfa"])
    base = {"type_compteur": type_compteur, "jours_du_mois": D, "jours_ecoules": today,
            "cost_to_date": cost_to_date, "fixe_certain": fixe_certain}

    # Données par jour du mois (jusqu'à maintenant) : kWh, 1re/dernière mesure, puissance moyenne
    start = midnight.replace(day=1)
    rows = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=start, timestamp__lte=now)
            .annotate(jour=TruncDate('timestamp', tzinfo=tz))
            .values('jour')
            .annotate(kwh=Sum('energie'), tmin=Min('timestamp'), tmax=Max('timestamp'), n=Count('id'))
            .order_by('jour'))
    byday = {r['jour'].day: r for r in rows}

    # Jour d'activation du service (1re mesure jamais reçue) → on n'impute JAMAIS avant.
    first_ever = MesureEnergie.objects.filter(capteur__client=client).aggregate(m=Min('timestamp'))['m']
    if first_ever is None:
        return dict(base, mode="trop_tot", k=0, n_min=N_MIN, offline_days=0)
    fe = timezone.localtime(first_ever)
    activation_day = fe.day if (fe.year == now.year and fe.month == now.month) else 1

    # Échantillon des jours PASSÉS complets + temps non mesuré U (en jours-équivalents)
    complete = []
    U = 0.0
    offline_days = 0
    for day in range(activation_day, today):   # jours passés, hors aujourd'hui
        r = byday.get(day)
        if r is None:
            offline_days += 1
            U += 1.0                            # capteur hors ligne → jour entier imputé
            continue
        span = (timezone.localtime(r['tmax']) - timezone.localtime(r['tmin'])).total_seconds() / 86400.0
        span = min(max(span, 0.0), 1.0)
        if span >= 0.8:
            # Énergie mesurée du jour (un vrai 0 idle reste 0). Dans ce projet, energie est
            # TOUJOURS calculée depuis la puissance à l'ingestion (energie=0 ⟺ puissance=0),
            # donc l'échantillon suit la même base que kwh_reel, pas de repli puissance à
            # ré-introduire (source des régressions de double comptage / gonflement).
            complete.append(float(r['kwh'] or 0.0))
        else:
            U += (1.0 - span)                   # jour partiel : part mesurée déjà dans kwh_reel, reste imputé
    # Aujourd'hui : on impute la partie NON mesurée (trou déjà écoulé + reste à venir),
    # exactement comme un jour passé partiel. La couverture = amplitude des mesures du jour.
    r_today = byday.get(today)
    if r_today is None:
        span_today = 0.0
        if today > activation_day:
            offline_days += 1                  # capteur hors ligne toute la journée
    else:
        span_today = (timezone.localtime(r_today['tmax']) - timezone.localtime(r_today['tmin'])).total_seconds() / 86400.0
        span_today = min(max(span_today, 0.0), 1.0)
    measured_today = min(span_today, f)         # ne peut pas dépasser la fraction déjà écoulée
    U += (f - measured_today)                   # trou déjà écoulé aujourd'hui (0 si tout mesuré)
    U += (1.0 - f)                              # reste à venir aujourd'hui
    U += max(0, D - today)                      # jours entièrement futurs
    k = len(complete)

    # TIER 0 : jour 1 ou pas assez de jours complets → aucun chiffre de conso (honnête)
    if today <= 1 or k < N_MIN:
        return dict(base, mode="trop_tot", k=k, n_min=N_MIN, offline_days=offline_days)

    med = statistics.median(complete)
    mad = statistics.median([abs(x - med) for x in complete])
    sigma = max(1.4826 * mad, 0.35 * med, 0.2)  # planchers → jamais de bande faussement nulle

    cap = max(p_kw * 24.0 * D, kwh_reel)         # plafond PHYSIQUE, jamais SOUS le réel déjà certain
    central = min(max(kwh_reel + med * U, kwh_reel), cap)
    se = sigma * math.sqrt((U * U) / k + U)      # erreur d'estimation + bruit jour-à-jour
    z = 1.28                                     # ~ intervalle 80 %
    low = min(max(kwh_reel, kwh_reel + med * U - z * se), central)
    high = max(min(cap, kwh_reel + med * U + z * se), central)

    def _bill(kwh):
        return _fcfa_affiche(calculer_facture_pour_client(max(0.0, kwh), client))
    bill_low = max(_bill(low), cost_to_date)     # INVARIANT : jamais < coût à ce jour
    bill_central = max(_bill(central), bill_low)
    bill_high = max(_bill(high), bill_central)
    variable_estime = max(0, bill_central - fixe_certain)

    # Palier de confiance (rétrogradé si beaucoup de jours manquants)
    # Dénominateur = jours observables DEPUIS l'activation, aujourd'hui INCLUS (offline_days
    # peut compter aujourd'hui via le correctif hors-ligne-du-jour) → ratio jamais > 1.
    coverage_ok = (offline_days / max(1, today - activation_day + 1)) <= 0.3
    if k >= 7 and coverage_ok and today >= (D - 2):
        tier, confiance = 2, "fiable"
    elif coverage_ok:
        tier, confiance = 1, "indicative"
    else:
        tier, confiance = 1, "indicative_trous"

    mode = "band_large" if (bill_low > 0 and (bill_high / bill_low) > 4) else "band"
    res = dict(base, mode=mode, bill_low=bill_low, bill_central=bill_central, bill_high=bill_high,
               variable_estime=variable_estime, projected_kwh=round(central, 1),
               k=k, offline_days=offline_days, tier=tier, confiance=confiance)

    if type_compteur == 'prepaye':
        try:
            from apps.alerts.utils import credit_prepaye_info
            info = credit_prepaye_info(client) or {}
            recharge_totale = float(info.get('recharge_fcfa') or 0)
            res["recharge_conseillee"] = max(0, int(round(bill_central - recharge_totale)))
        except Exception:
            pass
    return res


class PrevisionView(APIView):
    """Prévision honnête de la facture de fin de mois (fourchette, part certaine séparée)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à la prévision."},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(_prevision_fin_de_mois(user.client))


class ExportCSVView(APIView):
    """Export CSV des mesures du client (spéc. SHOULD HAVE).

    Fichier prêt pour un tableur en conventions françaises : BOM UTF-8 (sans lui,
    Excel Windows affiche « Ã© » à la place des accents), séparateur « ; »,
    horodatage LOCAL lisible, décimales à virgule (reconnues comme nombres).
    Données brutes uniquement : une ligne = une mesure, rien d'agrégé ni d'inventé.
    Réponse STREAMÉE (iterator) : un historique complet ne charge jamais toutes
    les mesures en mémoire. Validation stricte des paramètres, alignée sur le PDF :
    date malformée, plage inversée ou sensor_id non-UUID → 400, jamais un 500."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        import csv
        from django.http import StreamingHttpResponse  # pyrefly: ignore [untyped-import]

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leurs mesures."},
                            status=status.HTTP_403_FORBIDDEN)

        queryset = MesureEnergie.objects.filter(capteur__client=user.client).select_related('capteur')

        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
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

        date_from_raw = request.query_params.get('date_from')
        date_to_raw = request.query_params.get('date_to')
        date_from = date_to = None
        period = None
        if date_from_raw or date_to_raw:
            date_from, date_to = _parse_date(date_from_raw), _parse_date(date_to_raw)
            # Une date fournie mais illisible n'est JAMAIS ignorée en silence :
            # sinon on exporterait tout l'historique en croyant exporter une plage.
            if (date_from_raw and date_from is None) or (date_to_raw and date_to is None):
                return Response({"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                                status=status.HTTP_400_BAD_REQUEST)
            if date_from and date_to and date_from > date_to:
                return Response({"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                                status=status.HTTP_400_BAD_REQUEST)
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

        # Nom de fichier explicite : la période couverte, pas un horodatage opaque.
        if date_from or date_to:
            fin = date_to or timezone.localdate()
            debut = date_from.strftime('%Y%m%d') if date_from else 'debut'
            filename = f"aoceda_mesures_{debut}_{fin.strftime('%Y%m%d')}.csv"
        else:
            suffixe = {'day': '24h', 'week': '7j', 'month': '30j'}.get(period or '', 'tout')
            filename = f"aoceda_mesures_{suffixe}_{timezone.localtime().strftime('%Y%m%d')}.csv"

        def _virgule(x, dec):
            # Virgule décimale : Excel/LibreOffice FR reconnaît un NOMBRE, pas du texte.
            return (f"{float(x):.{dec}f}").replace('.', ',')

        class _Echo:
            """Pseudo-tampon : csv.writer.writerow() retourne la ligne au lieu de la stocker."""
            def write(self, value):
                return value

        writer = csv.writer(_Echo(), delimiter=';')

        def _lignes():
            yield '﻿'  # BOM UTF-8 : accents corrects dans Excel
            yield writer.writerow(['Horodatage (heure locale)', 'Capteur', 'Puissance (W)', 'Courant (A)',
                                   'Énergie (kWh)', 'Tension (V)', 'Facteur de puissance'])
            for m in queryset.order_by('timestamp').iterator(chunk_size=2000):
                yield writer.writerow([
                    timezone.localtime(m.timestamp).strftime('%d/%m/%Y %H:%M:%S'),
                    m.capteur.nom,
                    _virgule(m.puissance, 2), _virgule(m.courant, 3), _virgule(m.energie, 6),
                    _virgule(m.tension_V, 1), _virgule(m.facteur_puissance, 3),
                ])

        response = StreamingHttpResponse(_lignes(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class HistoriquePDFView(APIView):
    """Relevé PDF professionnel de l'historique journalier (MÊME fenêtre que le tableau).

    Document structuré via le socle apps.analytics.pdf : cartes d'identification
    (titulaire / document référencé), synthèse de la période en indicateurs,
    détail journalier zébré avec dépassements signalés, méthodologie explicite,
    en-tête de marque et pagination « Page X sur Y » sur chaque page.
    Coût = énergie × tarif CIE (taxes incl.), hors abonnement fixe. Indicatif."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer
        from . import pdf as pdfdoc

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leur historique."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        base = MesureEnergie.objects.filter(capteur__client=client)
        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        capteur_filtre = None
        if sensor_id:
            base = base.filter(capteur_id=sensor_id)
            capteur_filtre = Capteur.objects.filter(client=client, id=sensor_id).first()

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        win, err = _parse_hist_window(request.query_params, today)
        if err:
            return err
        start_date, end_date = win
        jours = _aggregate_jours(base.filter(timestamp__date__gte=start_date, timestamp__date__lte=end_date), tz)

        prix = float(prix_kwh_tout_compris(client))
        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        type_compteur = 'Prépayé' if getattr(client, 'typeCompteur', 'postpaye') == 'prepaye' else 'Postpayé'

        st = pdfdoc.get_styles()
        ref = pdfdoc.reference_document('HIST', client)
        nb_jours_periode = (end_date - start_date).days + 1

        # 1) Identification : qui, quoi, quelle période, quel tarif, traçable.
        titulaire = [("Nom", client.nom), ("Email", client.email)]
        if getattr(client, 'numeroCIE', None):
            titulaire.append(("N° compteur CIE", client.numeroCIE))
        titulaire += [("Abonnement", f"{amperage} A (env. {pdfdoc.fmt_num(cap_w, 0)} W)"),
                      ("Type de compteur", type_compteur)]
        doc_infos = [("Référence", ref),
                     ("Période", f"du {pdfdoc.fmt_date_fr(start_date)} au {pdfdoc.fmt_date_fr(end_date)}"),
                     ("Tarif appliqué", f"env. {pdfdoc.fmt_num(prix)} F/kWh (taxes incluses)"),
                     ("Édité le", timezone.localtime().strftime('%d/%m/%Y à %H:%M'))]
        if capteur_filtre:
            doc_infos.append(("Capteur", capteur_filtre.nom))
        el = [pdfdoc.panneau_identification([("Titulaire", titulaire), ("Document", doc_infos)], st)]

        if not jours:
            el += pdfdoc.section("Synthèse de la période", st)
            el.append(Paragraph(
                "Aucune mesure reçue sur cette période : le capteur était hors ligne ou non "
                "installé. Aucune donnée n'est estimée ni reconstituée dans ce document.", st['body']))
        else:
            tot_kwh = sum(j['kwh'] for j in jours)
            tot_night = sum(j['night_kwh'] for j in jours)
            pic = max(j['peak_w'] for j in jours)
            moyenne = tot_kwh / len(jours)
            part_nuit = (tot_night / tot_kwh * 100) if tot_kwh > 0 else 0.0

            # 2) Synthèse : les chiffres clés avant le détail.
            el += pdfdoc.section("Synthèse de la période", st)
            el.append(pdfdoc.bande_kpi([
                ("Énergie consommée", f"{pdfdoc.fmt_num(tot_kwh)} kWh",
                 f"{len(jours)} jour(s) mesurés sur {nb_jours_periode}"),
                ("Coût énergie estimé", f"{pdfdoc.fmt_fcfa(tot_kwh * prix)} F",
                 "hors abonnement fixe"),
                ("Moyenne journalière", f"{pdfdoc.fmt_num(moyenne)} kWh",
                 f"env. {pdfdoc.fmt_fcfa(moyenne * prix)} F/jour"),
                ("Pic de puissance", f"{pdfdoc.fmt_num(pic, 0)} W",
                 f"souscrit : env. {pdfdoc.fmt_num(cap_w, 0)} W"),
                ("Part nocturne", f"{pdfdoc.fmt_num(part_nuit, 1)} %",
                 f"{pdfdoc.fmt_num(tot_night)} kWh entre 00h et 06h"),
            ], st))

            # 3) Détail jour par jour (tableau zébré, en-tête répété à chaque page).
            el += pdfdoc.section("Détail journalier", st)
            table_el, _ = pdfdoc.tableau_journalier(jours, prix, cap_w, st)
            el += table_el

        # 4) Méthodologie : comment lire les chiffres, sans ambiguïté.
        el += pdfdoc.section("Méthodologie et mentions", st)
        for txt in (
            "Coût énergie = énergie mesurée × tarif CIE tout compris "
            f"(env. {pdfdoc.fmt_num(prix)} F/kWh, taxes et TVA incluses), hors prime fixe mensuelle. "
            "La facture complète du mois (abonnement inclus) figure dans l'application.",
            "Part nocturne = énergie mesurée entre 00h00 et 06h00, heure locale. "
            "Pic = puissance instantanée maximale relevée dans la journée.",
            "Un jour absent du tableau signifie qu'aucune mesure n'a été reçue ce jour-là "
            "(capteur hors ligne ou éteint) : aucune valeur n'est inventée ni extrapolée.",
        ):
            el.append(Paragraph(txt, st['note']))
            el.append(Spacer(1, 1.5 * mm))

        contenu = pdfdoc.build_pdf("Historique de consommation", ref, el)
        resp = HttpResponse(contenu, content_type='application/pdf')
        fname = f"aoceda_historique_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf"
        resp['Content-Disposition'] = f'attachment; filename="{fname}"'
        return resp


class RapportMensuelPDFView(APIView):
    """Rapport mensuel PDF complet du client, le document « propre » à archiver.

    Remplace l'ancienne impression navigateur (window.print) de la page Prévisions.
    Contenu : identification, synthèse du mois, détail de la facture (grille CIE,
    mêmes moteurs de calcul que l'application, invariant somme des lignes = total),
    prévision de fin de mois (fourchette honnête ou « trop tôt » assumé), crédit
    prépayé le cas échéant, détail journalier, méthodologie. Mois calendaire en cours."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer
        from . import pdf as pdfdoc

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leur rapport."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        start_month = today.replace(day=1)

        st = pdfdoc.get_styles()
        ref = pdfdoc.reference_document('RM', client)
        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        prix = float(prix_kwh_tout_compris(client))
        prepaye = getattr(client, 'typeCompteur', 'postpaye') == 'prepaye'

        def _q(v):
            return int(Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        # Identification (mêmes cartes que l'historique : identité visuelle commune).
        titulaire = [("Nom", client.nom), ("Email", client.email)]
        if getattr(client, 'numeroCIE', None):
            titulaire.append(("N° compteur CIE", client.numeroCIE))
        titulaire += [("Abonnement", f"{amperage} A (env. {pdfdoc.fmt_num(cap_w, 0)} W)"),
                      ("Type de compteur", 'Prépayé' if prepaye else 'Postpayé')]
        doc_infos = [("Référence", ref),
                     ("Période", f"du {pdfdoc.fmt_date_fr(start_month)} au {pdfdoc.fmt_date_fr(today)}"),
                     ("Tarif appliqué", f"env. {pdfdoc.fmt_num(prix)} F/kWh (taxes incluses)"),
                     ("Édité le", timezone.localtime().strftime('%d/%m/%Y à %H:%M'))]
        el = [pdfdoc.panneau_identification([("Titulaire", titulaire), ("Document", doc_infos)], st)]

        # Compte sans capteur : document VIDE honnête (cohérent avec le reste de l'app).
        if not Capteur.objects.filter(client=client).exists():
            el += pdfdoc.section("Synthèse du mois", st)
            el.append(Paragraph(
                "Aucun capteur n'est associé à ce compte : il n'y a encore rien à rapporter. "
                "Ce document ne contient volontairement aucune donnée estimée.", st['body']))
            contenu = pdfdoc.build_pdf("Rapport mensuel", ref, el)
            resp = HttpResponse(contenu, content_type='application/pdf')
            resp['Content-Disposition'] = (
                f'attachment; filename="aoceda_rapport_mensuel_{today.strftime("%Y-%m")}.pdf"')
            return resp

        fac = facture_mois_a_ce_jour(client)
        d = fac["detail"]
        total = _fcfa_affiche(d)
        abonnement_fixe = _q(d["prime_fixe_fcfa"]) + _q(d["taxe_fixe_fcfa"])

        # 1) Synthèse du mois : facture à ce jour, énergie, progression, mois précédent.
        prev_am = (start_month - timedelta(days=1)).strftime('%Y-%m')
        precedente = Prevision.objects.filter(client=client, annee_mois=prev_am).first()
        if precedente and precedente.montantEstimé_FCFA is not None:
            kpi_prec = (f"{pdfdoc.fmt_fcfa(precedente.montantEstimé_FCFA)} F",
                        precedente.moisConcerné or prev_am)
        else:
            kpi_prec = ("—", "aucune donnée")
        pct = round(fac["jours_ecoules"] / fac["jours_du_mois"] * 100)
        el += pdfdoc.section(f"Synthèse · {fac['mois_libelle']}", st)
        el.append(pdfdoc.bande_kpi([
            ("Coût du mois, à ce jour" if prepaye else "Facture du mois, à ce jour",
             f"{pdfdoc.fmt_fcfa(total)} F", "TVA 18 % incluse"),
            ("Énergie consommée", f"{pdfdoc.fmt_num(float(fac['kwh_consommes']))} kWh",
             "depuis le 1er du mois"),
            ("Progression du mois", f"{fac['jours_ecoules']}/{fac['jours_du_mois']} j", f"{pct} %"),
            ("Facture du mois précédent", kpi_prec[0], kpi_prec[1]),
        ], st))

        # 2) Détail de la facture : la décomposition officielle CIE, ligne à ligne.
        #    Composantes arrondies individuellement (HALF_UP) → leur somme = le total
        #    affiché, même invariant que _fcfa_affiche / la carte de l'application.
        el += pdfdoc.section("Détail de la facture (grille tarifaire CIE)", st)
        lignes = [[f"Consommation tranche 1 : {pdfdoc.fmt_num(float(d['tranche1_kwh']))} kWh "
                   f"× {pdfdoc.fmt_num(float(d['tranche1_prix']), 0)} F/kWh",
                   pdfdoc.fmt_fcfa(_q(d['tranche1_fcfa']))]]
        if float(d['tranche2_kwh']) > 0:
            lignes.append([f"Consommation tranche 2 : {pdfdoc.fmt_num(float(d['tranche2_kwh']))} kWh "
                           f"× {pdfdoc.fmt_num(float(d['tranche2_prix']), 0)} F/kWh",
                           pdfdoc.fmt_fcfa(_q(d['tranche2_fcfa']))])
        lignes.append(["Prime fixe mensuelle (abonnement)", pdfdoc.fmt_fcfa(_q(d['prime_fixe_fcfa']))])
        lignes.append([f"Taxes et redevances (dont part fixe {pdfdoc.fmt_fcfa(_q(d['taxe_fixe_fcfa']))} F)",
                       pdfdoc.fmt_fcfa(_q(d['taxes_fcfa']))])
        el.append(pdfdoc.tableau_donnees(
            ["Libellé", "Montant (FCFA)"], lignes, [135 * mm, 45 * mm],
            total=["TOTAL du mois à ce jour (TVA 18 % incluse)", pdfdoc.fmt_fcfa(total)]))
        el.append(Spacer(1, 2 * mm))
        tarif_libelle = {'social': 'tarif social', 'general': 'tarif général'}.get(
            str(d['type_tarif']), str(d['type_tarif']))
        el.append(Paragraph(
            f"Grille CIE « {tarif_libelle} » pour un abonnement {amperage} A ; tranche 1 jusqu'à "
            f"{pdfdoc.fmt_num(float(d['seuil_t1_kwh']), 0)} kWh/mois. Montant calculé sur la seule "
            "énergie réellement mesurée depuis le 1er du mois : aucune projection n'y est incluse.",
            st['note']))

        # 3) Prévision de fin de mois : fourchette honnête, ou « trop tôt » assumé.
        prev_fin = _prevision_fin_de_mois(client)
        el += pdfdoc.section("Prévision de fin de mois", st)
        if prev_fin.get('mode') in ('band', 'band_large'):
            el.append(pdfdoc.bande_kpi([
                ("Fourchette basse", f"{pdfdoc.fmt_fcfa(prev_fin['bill_low'])} F", ""),
                ("Montant attendu", f"{pdfdoc.fmt_fcfa(prev_fin['bill_central'])} F",
                 "estimation centrale"),
                ("Fourchette haute", f"{pdfdoc.fmt_fcfa(prev_fin['bill_high'])} F", ""),
            ], st))
            el.append(Spacer(1, 2.5 * mm))
            el.append(Paragraph(
                f"Part fixe certaine (abonnement) : <b>{pdfdoc.fmt_fcfa(prev_fin['fixe_certain'])} F</b> · "
                f"consommation estimée : env. {pdfdoc.fmt_fcfa(prev_fin['variable_estime'])} F. "
                f"Estimation basée sur {prev_fin['k']} journée(s) complète(s) de mesures réelles ; "
                f"consommation projetée env. {pdfdoc.fmt_num(prev_fin['projected_kwh'], 1)} kWh.",
                st['body']))
            if prev_fin.get('offline_days'):
                el.append(Spacer(1, 1.5 * mm))
                el.append(Paragraph(
                    f"{prev_fin['offline_days']} jour(s) sans données ont été imputés à la consommation "
                    "habituelle pour la prévision uniquement ; le montant « à ce jour » ci-dessus, lui, "
                    "n'est jamais gonflé.", st['note']))
            if prev_fin.get('mode') == 'band_large':
                el.append(Spacer(1, 1.5 * mm))
                el.append(Paragraph(
                    "Fourchette encore large : elle se resserrera après 1 à 2 journées complètes "
                    "de mesures supplémentaires.", st['note']))
        elif prev_fin.get('mode') == 'trop_tot':
            el.append(Paragraph(
                f"Pas encore assez de journées complètes de mesures ({prev_fin.get('k', 0)} sur "
                f"{prev_fin.get('n_min', 3)} requises) pour estimer la fin du mois sans rien inventer. "
                f"Seul l'abonnement fixe est déjà certain : "
                f"<b>{pdfdoc.fmt_fcfa(prev_fin.get('fixe_certain', abonnement_fixe))} F</b>.", st['body']))

        # 4) Crédit prépayé : uniquement pour les compteurs prépayés.
        if prepaye:
            from apps.alerts.utils import credit_prepaye_info
            try:
                info = credit_prepaye_info(client)
            except Exception:
                # Jamais un 500 en pleine génération de document pour une info annexe :
                # sans crédit calculable, la section est simplement omise.
                info = None
            if info:
                el += pdfdoc.section("Crédit prépayé", st)
                autonomie = (f"{info['jours_restants']} j" if info.get('jours_restants') is not None else "—")
                el.append(pdfdoc.bande_kpi([
                    ("Recharges du mois", f"{pdfdoc.fmt_fcfa(info['recharge_fcfa'])} F", ""),
                    ("Consommé", f"{pdfdoc.fmt_fcfa(info['consomme_fcfa'])} F", ""),
                    ("Crédit restant", f"{pdfdoc.fmt_fcfa(info['restant_fcfa'])} F", ""),
                    ("Coût moyen / jour", f"{pdfdoc.fmt_fcfa(info['cout_jour_fcfa'])} F", ""),
                    ("Autonomie estimée", autonomie, "au rythme actuel"),
                ], st))
                if prev_fin.get('recharge_conseillee') is not None:
                    el.append(Spacer(1, 2 * mm))
                    el.append(Paragraph(
                        "Pour finir le mois sans coupure, recharge conseillée : env. "
                        f"<b>{pdfdoc.fmt_fcfa(prev_fin['recharge_conseillee'])} F</b>.", st['body']))

        # 5) Détail journalier du mois (même tableau normalisé que l'historique).
        jours = _aggregate_jours(
            MesureEnergie.objects.filter(capteur__client=client,
                                         timestamp__date__gte=start_month,
                                         timestamp__date__lte=today), tz)
        el += pdfdoc.section("Consommation journalière du mois", st)
        if jours:
            table_el, _ = pdfdoc.tableau_journalier(jours, prix, cap_w, st)
            el += table_el
        else:
            el.append(Paragraph("Aucune mesure reçue depuis le début du mois.", st['body']))

        # 6) Méthodologie et mentions.
        el += pdfdoc.section("Méthodologie et mentions", st)
        for txt in (
            "Les montants sont calculés par le moteur tarifaire CIE de la plateforme (tranches, "
            "prime fixe, taxes, TVA 18 % incluse) sur la seule énergie réellement mesurée. "
            "La somme des lignes du détail est égale au total affiché, au franc près.",
            "La prévision de fin de mois est une estimation, jamais une promesse : elle devient "
            "la facture exacte le dernier jour du mois. Un jour absent du détail journalier = "
            "aucune mesure reçue ce jour-là ; aucune valeur n'est inventée.",
        ):
            el.append(Paragraph(txt, st['note']))
            el.append(Spacer(1, 1.5 * mm))

        contenu = pdfdoc.build_pdf("Rapport mensuel", ref, el)
        resp = HttpResponse(contenu, content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="aoceda_rapport_mensuel_{fac["annee_mois"]}.pdf"')
        return resp


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
