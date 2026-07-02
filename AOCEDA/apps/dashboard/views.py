from django.shortcuts import render  # pyrefly: ignore [untyped-import]
from django.http import JsonResponse  # pyrefly: ignore [untyped-import]
from django.contrib.admin.views.decorators import staff_member_required  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Avg, Count  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate, TruncHour  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from datetime import timedelta

def index(request):
    return render(request, 'index.html')

def auth_view(request):
    return render(request, 'aoceda-auth.html')

def dashboard_view(request):
    return render(request, 'aoceda-dashboard.html')

def historique_view(request):
    return render(request, 'aoceda-historique.html')

def alertes_view(request):
    return render(request, 'aoceda-alertes.html')

def ia_view(request):
    return render(request, 'aoceda-ia.html')

def previsions_view(request):
    return render(request, 'aoceda-previsions.html')

def parametres_view(request):
    return render(request, 'aoceda-parametres.html')

def technicien_view(request):
    return render(request, 'aoceda-technicien.html')


@staff_member_required
def admin_stats_data(request):
    """Données agrégées pour le tableau de bord administrateur."""
    from apps.accounts.models import Client, Technicien, Administrateur
    from apps.sensors.models import Dispositif, Capteur, MesureEnergie, Intervention
    from apps.alerts.models import Alerte

    now = timezone.now()
    il_y_a_24h  = now - timedelta(hours=24)
    il_y_a_7j   = now - timedelta(days=7)
    il_y_a_30j  = now - timedelta(days=30)
    seuil_hors_ligne = now - timedelta(minutes=10)

    # ── Utilisateurs ────────────────────────────────────────────────────────
    clients_qs      = Client.objects.all()
    clients_total   = clients_qs.count()
    clients_actifs  = clients_qs.filter(is_active=True, estActif=True).count()
    techniciens     = Technicien.objects.count()
    admins          = Administrateur.objects.count()
    nouveaux_7j     = clients_qs.filter(date_joined__gte=il_y_a_7j).count()
    compteurs_pre   = clients_qs.filter(typeCompteur='prepaye').count()
    compteurs_post  = clients_qs.filter(typeCompteur='postpaye').count()

    # ── Infrastructure ───────────────────────────────────────────────────────
    capteurs_qs         = Capteur.objects.all()
    capteurs_actifs     = capteurs_qs.filter(actif=True).count()
    capteurs_hors_ligne = capteurs_qs.filter(actif=True).exclude(
                              derniereLecture__gte=seuil_hors_ligne).count()
    dispositifs_total      = Dispositif.objects.count()
    dispositifs_connectes  = Dispositif.objects.filter(estConnecté=True).count()
    mesures_24h            = MesureEnergie.objects.filter(timestamp__gte=il_y_a_24h).count()

    # ── Alertes & interventions ──────────────────────────────────────────────
    alertes_non_lues    = Alerte.objects.filter(lue=False).count()
    alertes_24h         = Alerte.objects.filter(createdAt__gte=il_y_a_24h).count()
    interventions_cours = Intervention.objects.exclude(statut='TERMINEE').count()

    kpi = {
        # Utilisateurs
        'clients_total': clients_total,
        'clients_actifs': clients_actifs,
        'techniciens': techniciens,
        'admins': admins,
        'nouveaux_clients_7j': nouveaux_7j,
        'compteurs_prepaye': compteurs_pre,
        'compteurs_postpaye': compteurs_post,
        # Infrastructure
        'dispositifs_total': dispositifs_total,
        'dispositifs_connectes': dispositifs_connectes,
        'capteurs_actifs': capteurs_actifs,
        'capteurs_hors_ligne': capteurs_hors_ligne,
        'mesures_24h': mesures_24h,
        # Alertes
        'alertes_non_lues': alertes_non_lues,
        'alertes_24h': alertes_24h,
        'interventions_en_cours': interventions_cours,
    }

    # ── Graphique 1 : consommation (kWh) / jour — 7 jours ───────────────────
    conso_brute = (
        MesureEnergie.objects
        .filter(timestamp__gte=il_y_a_7j)
        .annotate(jour=TruncDate('timestamp'))
        .values('jour')
        .annotate(total_kwh=Sum('energie'))
        .order_by('jour')
    )
    conso_map = {e['jour']: float(e['total_kwh'] or 0) for e in conso_brute}
    jours_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    conso_labels, conso_valeurs = [], []
    for delta in range(6, -1, -1):
        j = timezone.localdate() - timedelta(days=delta)
        conso_labels.append(f"{jours_fr[j.weekday()]} {j.strftime('%d/%m')}")
        conso_valeurs.append(round(conso_map.get(j, 0.0), 3))

    # ── Graphique 2 : alertes par type — 30 jours ───────────────────────────
    types_alerte = dict(Alerte.TYPE_CHOICES)
    alertes_brutes = (
        Alerte.objects
        .filter(createdAt__gte=il_y_a_30j)
        .values('type').annotate(total=Count('id')).order_by('-total')
    )
    alertes_labels  = [types_alerte.get(e['type'], e['type']) for e in alertes_brutes]
    alertes_valeurs = [e['total'] for e in alertes_brutes]

    # ── Graphique 3 : nouveaux clients / semaine — 8 semaines ───────────────
    inscrits_bruts = (
        Client.objects
        .filter(date_joined__gte=now - timedelta(weeks=8))
        .annotate(semaine=TruncDate('date_joined'))
        .values('semaine').annotate(n=Count('id')).order_by('semaine')
    )
    inscrits_map = {e['semaine']: e['n'] for e in inscrits_bruts}
    inscrits_labels, inscrits_valeurs = [], []
    for w in range(7, -1, -1):
        inscrits_labels.append(f"S-{w}" if w > 0 else "Cette sem.")
        semaine_date = timezone.localdate() - timedelta(weeks=w)
        total_semaine = sum(
            v for d, v in inscrits_map.items()
            if semaine_date <= d < semaine_date + timedelta(days=7)
        )
        inscrits_valeurs.append(total_semaine)

    # ── Graphique 4 : puissance moyenne (W) / heure — 24 h ──────────────────
    puissance_brute = (
        MesureEnergie.objects
        .filter(timestamp__gte=il_y_a_24h)
        .annotate(heure=TruncHour('timestamp'))
        .values('heure').annotate(puissance_moy=Avg('puissance')).order_by('heure')
    )
    puissance_labels, puissance_valeurs = [], []
    for e in puissance_brute:
        puissance_labels.append(timezone.localtime(e['heure']).strftime('%Hh'))
        puissance_valeurs.append(round(float(e['puissance_moy'] or 0), 1))

    return JsonResponse({
        'kpi': kpi,
        'conso_7j':      {'labels': conso_labels,     'valeurs': conso_valeurs},
        'alertes_30j':   {'labels': alertes_labels,   'valeurs': alertes_valeurs},
        'inscrits_8s':   {'labels': inscrits_labels,  'valeurs': inscrits_valeurs},
        'puissance_24h': {'labels': puissance_labels, 'valeurs': puissance_valeurs},
    })
