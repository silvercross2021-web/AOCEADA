from django.shortcuts import render  # pyrefly: ignore [untyped-import]
from django.http import JsonResponse  # pyrefly: ignore [untyped-import]
from django.contrib.admin.views.decorators import staff_member_required  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Count  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate, TruncMonth  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from datetime import timedelta
from decimal import Decimal

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
    """Données agrégées pour le tableau de bord ADMINISTRATEUR.

    Vision « pilotage plateforme » (argent, croissance, parc, opérations) — PAS des
    métriques client/technique. Tous les montants sont RÉELS (grille CIE sur les kWh
    réellement consommés), jamais de projection ni de donnée fabriquée.
    """
    from apps.accounts.models import Client, Technicien, Administrateur
    from apps.sensors.models import Dispositif, Capteur, MesureEnergie, Intervention
    from apps.alerts.models import Alerte
    from apps.alerts.utils import (
        cout_mois_courant_fcfa, credit_prepaye_info,
        SEUIL_CREDIT_BAS_FCFA, JOURS_AUTONOMIE_BAS,
    )
    from apps.analytics.tarifs_cie import calculer_facture_pour_client

    now = timezone.now()
    il_y_a_24h  = now - timedelta(hours=24)
    il_y_a_7j   = now - timedelta(days=7)
    il_y_a_30j  = now - timedelta(days=30)
    il_y_a_6m   = now - timedelta(days=186)
    seuil_en_ligne = now - timedelta(minutes=10)   # fraîcheur = « en ligne »

    # ── 👥 Utilisateurs ──────────────────────────────────────────────────────
    clients_qs      = Client.objects.all()
    clients_total   = clients_qs.count()
    clients_actifs  = clients_qs.filter(is_active=True, estActif=True).count()
    techniciens     = Technicien.objects.count()
    admins          = Administrateur.objects.count()
    nouveaux_7j     = clients_qs.filter(date_joined__gte=il_y_a_7j).count()
    compteurs_pre   = clients_qs.filter(typeCompteur='prepaye').count()
    compteurs_post  = clients_qs.filter(typeCompteur='postpaye').count()
    # Activation = comptes qui se sont déjà connectés au moins une fois
    jamais_connectes = clients_qs.filter(last_login__isnull=True).count()
    taux_activation  = round(100 * (clients_total - jamais_connectes) / clients_total) if clients_total else 0

    # ── 💰 Argent (CA RÉEL du mois, grille CIE ; clients prépayés à risque) ───
    ca_mois = Decimal('0')
    clients_a_risque = 0
    clients_map = {}
    for c in clients_qs:
        clients_map[c.id] = c
        try:
            ca_mois += (cout_mois_courant_fcfa(c) or Decimal('0'))
        except Exception:
            pass
        info = credit_prepaye_info(c)   # None si postpayé ou jamais rechargé
        if info:
            seuil = getattr(c, 'seuilCreditBas_FCFA', None) or SEUIL_CREDIT_BAS_FCFA
            if (info['restant_fcfa'] < seuil or
                    (info['jours_restants'] is not None and info['jours_restants'] <= JOURS_AUTONOMIE_BAS)):
                clients_a_risque += 1
    ca_mois = int(ca_mois)

    # ── ⚡ Parc (connectivité RÉELLE par fraîcheur, pas de booléen collant) ────
    capteurs_qs        = Capteur.objects.all()
    capteurs_actifs    = capteurs_qs.filter(actif=True).count()
    dispositifs_total  = Dispositif.objects.count()
    # « En ligne » = a posté au moins une mesure récemment (via un de ses capteurs).
    dispositifs_en_ligne = (Dispositif.objects
                            .filter(capteurs__derniereLecture__gte=seuil_en_ligne)
                            .distinct().count())
    # Capteurs actifs SANS donnée récente = info NEUTRE (un appareil éteint ne poste
    # pas → normal, ce n'est pas « hors ligne »). On ne le montre plus en alarme rouge.
    capteurs_sans_donnees = (capteurs_qs.filter(actif=True)
                             .exclude(derniereLecture__gte=seuil_en_ligne).count())
    mesures_24h = MesureEnergie.objects.filter(timestamp__gte=il_y_a_24h).count()

    # ── 🔔 Alertes & interventions ────────────────────────────────────────────
    alertes_non_lues  = Alerte.objects.filter(lue=False).count()
    alertes_critiques = Alerte.objects.filter(lue=False, sévérité='Critique').count()
    alertes_24h       = Alerte.objects.filter(createdAt__gte=il_y_a_24h).count()
    interventions_cours = Intervention.objects.exclude(statut='TERMINEE').count()

    kpi = {
        # Argent
        'ca_mois_fcfa': ca_mois,
        'clients_a_risque': clients_a_risque,
        'compteurs_prepaye': compteurs_pre,
        'compteurs_postpaye': compteurs_post,
        # Utilisateurs
        'clients_total': clients_total,
        'clients_actifs': clients_actifs,
        'techniciens': techniciens,
        'admins': admins,
        'nouveaux_clients_7j': nouveaux_7j,
        'taux_activation': taux_activation,
        # Parc
        'dispositifs_total': dispositifs_total,
        'dispositifs_en_ligne': dispositifs_en_ligne,
        'capteurs_actifs': capteurs_actifs,
        'capteurs_sans_donnees': capteurs_sans_donnees,
        'mesures_24h': mesures_24h,
        # Alertes & interventions
        'alertes_non_lues': alertes_non_lues,
        'alertes_critiques': alertes_critiques,
        'alertes_24h': alertes_24h,
        'interventions_en_cours': interventions_cours,
    }

    # ── Graphique 1 (REMPLACE la puissance) : CA estimé / mois, 6 mois ────────
    # CA réel par (client, mois) tarifé à la grille CIE du client, sommé par mois.
    conso_cm = (
        MesureEnergie.objects
        .filter(timestamp__gte=il_y_a_6m)
        .annotate(mois=TruncMonth('timestamp'))
        .values('capteur__client', 'mois')
        .annotate(kwh=Sum('energie'))
    )
    ca_par_mois = {}   # {(annee, mois): Decimal}
    for row in conso_cm:
        c = clients_map.get(row['capteur__client'])
        if not c or not row['mois']:
            continue
        kwh = row['kwh'] or Decimal('0')
        try:
            fcfa = calculer_facture_pour_client(kwh, c)['total_fcfa']
        except Exception:
            continue
        key = (row['mois'].year, row['mois'].month)
        ca_par_mois[key] = ca_par_mois.get(key, Decimal('0')) + fcfa
    mois_fr = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin', 'juil', 'août', 'sep', 'oct', 'nov', 'déc']
    cur = timezone.localdate().replace(day=1)
    derniers_mois = []
    for _ in range(6):
        derniers_mois.append(cur)
        cur = (cur - timedelta(days=1)).replace(day=1)
    derniers_mois.reverse()
    ca_labels  = [f"{mois_fr[m.month - 1]} {str(m.year)[2:]}" for m in derniers_mois]
    ca_valeurs = [int(ca_par_mois.get((m.year, m.month), Decimal('0'))) for m in derniers_mois]

    # ── Graphique 2 : alertes par type, 30 j (couleurs FIXÉES par type) ───────
    types_alerte = dict(Alerte.TYPE_CHOICES)
    couleur_type = {
        'DEPASSEMENT_SEUIL':     'rgba(239,68,68,.75)',   # rouge
        'CONSOMMATION_NOCTURNE': 'rgba(245,158,11,.75)',  # ambre
        'CREDIT_BAS':            'rgba(59,130,246,.75)',   # bleu
    }
    cnt = {r['type']: r['n'] for r in (
        Alerte.objects.filter(createdAt__gte=il_y_a_30j)
        .values('type').annotate(n=Count('id'))
    )}
    al_labels, al_valeurs, al_couleurs = [], [], []
    for t, _lbl in Alerte.TYPE_CHOICES:   # ordre FIXE → couleur = type, jamais le rang
        n = cnt.get(t, 0)
        if n > 0:
            al_labels.append(types_alerte.get(t, t))
            al_valeurs.append(n)
            al_couleurs.append(couleur_type.get(t, 'rgba(156,163,175,.75)'))

    # ── Graphique 3 : consommation plateforme (kWh) / jour, 7 jours ───────────
    conso_brute = (
        MesureEnergie.objects
        .filter(timestamp__gte=il_y_a_7j)
        .annotate(jour=TruncDate('timestamp'))
        .values('jour').annotate(total_kwh=Sum('energie')).order_by('jour')
    )
    conso_map = {e['jour']: float(e['total_kwh'] or 0) for e in conso_brute}
    jours_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    conso_labels, conso_valeurs = [], []
    for delta in range(6, -1, -1):
        j = timezone.localdate() - timedelta(days=delta)
        conso_labels.append(f"{jours_fr[j.weekday()]} {j.strftime('%d/%m')}")
        conso_valeurs.append(round(conso_map.get(j, 0.0), 3))

    # ── Graphique 4 : nouveaux clients / semaine, 8 semaines ──────────────────
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
        inscrits_valeurs.append(sum(
            v for d, v in inscrits_map.items()
            if semaine_date <= d < semaine_date + timedelta(days=7)
        ))

    return JsonResponse({
        'kpi': kpi,
        'ca_6m':       {'labels': ca_labels,       'valeurs': ca_valeurs},
        'alertes_30j': {'labels': al_labels,       'valeurs': al_valeurs, 'couleurs': al_couleurs},
        'conso_7j':    {'labels': conso_labels,    'valeurs': conso_valeurs},
        'inscrits_8s': {'labels': inscrits_labels, 'valeurs': inscrits_valeurs},
    })
