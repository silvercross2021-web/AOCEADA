import os
import re
from django.shortcuts import render  # pyrefly: ignore [untyped-import]
from django.http import JsonResponse, FileResponse, HttpResponse, Http404  # pyrefly: ignore [untyped-import]
from django.contrib.admin.views.decorators import staff_member_required  # pyrefly: ignore [untyped-import]
from django.contrib.staticfiles import finders  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Count  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate, TruncMonth  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.views.decorators.cache import cache_control  # pyrefly: ignore [untyped-import]
from datetime import timedelta
from decimal import Decimal

def index(request):
    return render(request, 'index.html')


# Fichiers vidéo servis en lecture par plage d'octets (HTTP Range).
# Le scrubbing du film logo au défilement exige que le navigateur puisse
# « seeker » dans la vidéo : cela nécessite des réponses 206 Partial Content.
# FileResponse gère nativement les requêtes Range ; le handler statique du
# runserver, non — d'où cette vue dédiée (fonctionne en dev comme en prod).
_ALLOWED_VIDEOS = {
    'logo-scrub.mp4',
    'logo-reveal.mp4',
    'pillars-bg.mp4',
}

@cache_control(max_age=60 * 60 * 24 * 30, public=True)
def site_video(request, name):
    if name not in _ALLOWED_VIDEOS:
        raise Http404('Vidéo introuvable.')
    path = finders.find(f'video/{name}')
    if isinstance(path, (list, tuple)):
        path = path[0] if path else None
    if not path or not os.path.exists(path):
        raise Http404('Vidéo introuvable.')

    file_size = os.path.getsize(path)
    range_header = request.META.get('HTTP_RANGE', '').strip()

    # Requête Range (« bytes=start-end ») → 206 Partial Content.
    # Indispensable pour que le navigateur puisse « seeker » dans la vidéo
    # pendant le scrubbing au défilement.
    m = re.match(r'bytes=(\d*)-(\d*)$', range_header)
    if m:
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            resp = HttpResponse(status=416)
            resp['Content-Range'] = f'bytes */{file_size}'
            return resp
        length = end - start + 1
        fh = open(path, 'rb')
        fh.seek(start)
        resp = FileResponse(fh, status=206, content_type='video/mp4')
        resp['Content-Length'] = str(length)
        resp['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        resp['Accept-Ranges'] = 'bytes'
        # FileResponse streamerait tout le fichier : on borne à la plage demandée.
        resp.streaming_content = _iter_range(fh, length)
        return resp

    resp = FileResponse(open(path, 'rb'), content_type='video/mp4')
    resp['Accept-Ranges'] = 'bytes'
    resp['Content-Length'] = str(file_size)
    return resp


def _iter_range(fh, length, chunk=64 * 1024):
    remaining = length
    try:
        while remaining > 0:
            data = fh.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        fh.close()

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

def interventions_view(request):
    return render(request, 'aoceda-interventions.html')



@staff_member_required
def admin_stats_data(request):
    """Données agrégées pour le tableau de bord ADMINISTRATEUR.

    Vision « pilotage plateforme » (revenus, croissance, parc IoT, infrastructure,
    tarifaire CIE, opérations terrain) — PAS des métriques client/technique.
    Tous les montants sont RÉELS (grille CIE sur les kWh réellement consommés),
    jamais de projection ni de donnée fabriquée.
    """
    from apps.accounts.models import Client, Technicien, Administrateur
    from apps.sensors.models import Dispositif, Capteur, MesureEnergie, Intervention
    from apps.alerts.models import Alerte
    from apps.alerts.utils import (
        cout_mois_courant_fcfa, credit_prepaye_info,
        SEUIL_CREDIT_BAS_FCFA, JOURS_AUTONOMIE_BAS,
    )
    from apps.analytics.tarifs_cie import calculer_facture_pour_client

    now            = timezone.now()
    il_y_a_10min   = now - timedelta(minutes=10)
    il_y_a_24h     = now - timedelta(hours=24)
    il_y_a_7j      = now - timedelta(days=7)
    il_y_a_30j     = now - timedelta(days=30)
    il_y_a_6m      = now - timedelta(days=186)
    il_y_a_6mois_complets = now - timedelta(days=183)   # pour le basculement CIE
    seuil_en_ligne = il_y_a_10min                       # fraîcheur = « en ligne »

    # ── 👥 Utilisateurs ──────────────────────────────────────────────────────
    clients_qs       = Client.objects.all()
    clients_total    = clients_qs.count()
    clients_actifs   = clients_qs.filter(is_active=True, estActif=True).count()
    techniciens      = Technicien.objects.count()
    admins           = Administrateur.objects.count()
    nouveaux_7j      = clients_qs.filter(date_joined__gte=il_y_a_7j).count()
    nouveaux_30j     = clients_qs.filter(date_joined__gte=il_y_a_30j).count()
    compteurs_pre    = clients_qs.filter(typeCompteur='prepaye').count()
    compteurs_post   = clients_qs.filter(typeCompteur='postpaye').count()
    # Activation = comptes ayant déjà effectué au moins une connexion
    jamais_connectes = clients_qs.filter(last_login__isnull=True).count()
    taux_activation  = round(100 * (clients_total - jamais_connectes) / clients_total) if clients_total else 0

    # ── 💰 Revenus (CA RÉEL du mois, grille CIE) ────────────────────────────
    ca_mois          = Decimal('0')
    clients_a_risque = 0
    clients_map      = {}
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

    # ── 📋 Parc tarifaire CIE (répartition ampérage / type de tarif) ─────────
    amp_5a  = clients_qs.filter(amperage=5).count()
    amp_10a = clients_qs.filter(amperage=10).count()
    amp_15a = clients_qs.filter(amperage=15).count()
    tarif_social  = clients_qs.filter(typeTarif='social').count()
    tarif_general = clients_qs.filter(typeTarif='general').count()

    # Clients éligibles au basculement Social→Général.
    # Règle CIE (EXPLICATION_TARIFAIRE.md §3) : >100 kWh/mois en moyenne sur
    # 6 mois consécutifs → basculement tarifaire réglementaire obligatoire.
    # Seuil pratique : somme sur 6 mois glissants > 600 kWh.
    clients_basculement = 0
    for c in clients_qs.filter(typeTarif='social'):
        try:
            kwh_6m = MesureEnergie.objects.filter(
                capteur__client=c, timestamp__gte=il_y_a_6mois_complets
            ).aggregate(t=Sum('energie'))['t'] or Decimal('0')
            if kwh_6m > Decimal('600'):
                clients_basculement += 1
        except Exception:
            pass

    # ── ⚡ Parc IoT (connectivité RÉELLE par fraîcheur) ──────────────────────
    capteurs_qs          = Capteur.objects.all()
    capteurs_actifs      = capteurs_qs.filter(actif=True).count()
    dispositifs_total    = Dispositif.objects.count()
    # « En ligne » = a posté via au moins un capteur dans les 10 dernières min.
    dispositifs_en_ligne = (Dispositif.objects
                            .filter(capteurs__derniereLecture__gte=seuil_en_ligne)
                            .distinct().count())
    # Capteurs actifs hors ligne > 10 min (ont déjà transmis mais plus depuis)
    capteurs_hors_ligne_10min = (capteurs_qs
                                 .filter(actif=True, derniereLecture__isnull=False)
                                 .exclude(derniereLecture__gte=seuil_en_ligne).count())
    # Capteurs hors ligne > 24 h (situation plus grave)
    capteurs_hors_ligne_24h   = (capteurs_qs
                                 .filter(actif=True, derniereLecture__isnull=False)
                                 .exclude(derniereLecture__gte=il_y_a_24h).count())
    # Capteurs enregistrés mais n'ayant JAMAIS transmis (non installés / défectueux)
    capteurs_jamais_transmis  = capteurs_qs.filter(actif=True, derniereLecture__isnull=True).count()
    # Capteurs en état ON (appareil allumé et consommant à l'instant)
    capteurs_etat_on          = capteurs_qs.filter(actif=True, etatCourant='ON').count()
    mesures_24h               = MesureEnergie.objects.filter(timestamp__gte=il_y_a_24h).count()

    # ── 🔔 Alertes & interventions ────────────────────────────────────────────
    alertes_non_lues  = Alerte.objects.filter(lue=False).count()
    alertes_critiques = Alerte.objects.filter(lue=False, **{"s\u00e9v\u00e9rit\u00e9": 'Critique'}).count()
    alertes_24h       = Alerte.objects.filter(createdAt__gte=il_y_a_24h).count()
    # Interventions détaillées par statut (plus d'un seul chiffre global)
    interventions_en_attente  = Intervention.objects.filter(statut='EN_ATTENTE').count()
    interventions_en_cours    = Intervention.objects.filter(statut='EN_COURS').count()
    interventions_terminees_7j = Intervention.objects.filter(
        statut='TERMINEE', dateIntervention__gte=il_y_a_7j).count()

    kpi = {
        # Revenus plateforme
        'ca_mois_fcfa': ca_mois,
        'compteurs_prepaye': compteurs_pre,
        'compteurs_postpaye': compteurs_post,
        # Utilisateurs
        'clients_total': clients_total,
        'clients_actifs': clients_actifs,
        'clients_jamais_connectes': jamais_connectes,
        'techniciens': techniciens,
        'admins': admins,
        'nouveaux_clients_7j': nouveaux_7j,
        'nouveaux_clients_30j': nouveaux_30j,
        'taux_activation': taux_activation,
        # Parc tarifaire CIE
        'amp_5a': amp_5a,
        'amp_10a': amp_10a,
        'amp_15a': amp_15a,
        'tarif_social': tarif_social,
        'tarif_general': tarif_general,
        'clients_basculement_cie': clients_basculement,
        # Parc IoT
        'dispositifs_total': dispositifs_total,
        'dispositifs_en_ligne': dispositifs_en_ligne,
        'capteurs_actifs': capteurs_actifs,
        'capteurs_hors_ligne_10min': capteurs_hors_ligne_10min,
        'capteurs_hors_ligne_24h': capteurs_hors_ligne_24h,
        'capteurs_jamais_transmis': capteurs_jamais_transmis,
        'capteurs_etat_on': capteurs_etat_on,
        'mesures_24h': mesures_24h,
        # Alertes & interventions
        'alertes_non_lues': alertes_non_lues,
        'alertes_critiques': alertes_critiques,
        'alertes_24h': alertes_24h,
        'clients_a_risque': clients_a_risque,
        'interventions_en_attente': interventions_en_attente,
        'interventions_en_cours': interventions_en_cours,
        'interventions_terminees_7j': interventions_terminees_7j,
    }

    # ── Graphique 1 : CA mensuel de la plateforme (FCFA), 6 mois ─────────────
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

    # ── Graphique 2 : alertes CLIENTS par type, 30 j ─────────────────────────
    types_alerte = dict(Alerte.TYPE_CHOICES)
    couleur_type = {
        'DEPASSEMENT_SEUIL':     'rgba(239,68,68,.75)',   # rouge
        'CONSOMMATION_NOCTURNE': 'rgba(245,158,11,.75)',  # ambre
        'CREDIT_BAS':            'rgba(59,130,246,.75)',  # bleu
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

    # ── Graphique 3 : volume distribué (kWh) / jour, 7 jours ─────────────────
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

    # ── Graphique 4 : nouveaux clients / mois, 12 mois (tendance long terme) ──
    inscrits_bruts = (
        Client.objects
        .filter(date_joined__gte=now - timedelta(days=365))
        .annotate(mois=TruncMonth('date_joined'))
        .values('mois').annotate(n=Count('id')).order_by('mois')
    )
    inscrits_map = {(e['mois'].year, e['mois'].month): e['n'] for e in inscrits_bruts if e['mois']}
    cur_m = timezone.localdate().replace(day=1)
    inscrits_labels, inscrits_valeurs = [], []
    for _ in range(12):
        inscrits_labels.append(f"{mois_fr[cur_m.month - 1]} {str(cur_m.year)[2:]}")
        inscrits_valeurs.append(inscrits_map.get((cur_m.year, cur_m.month), 0))
        cur_m = (cur_m - timedelta(days=1)).replace(day=1)
    inscrits_labels.reverse()
    inscrits_valeurs.reverse()

    return JsonResponse({
        'kpi': kpi,
        'ca_6m':        {'labels': ca_labels,       'valeurs': ca_valeurs},
        'alertes_30j':  {'labels': al_labels,       'valeurs': al_valeurs, 'couleurs': al_couleurs},
        'volume_7j':    {'labels': conso_labels,    'valeurs': conso_valeurs},
        'inscrits_12m': {'labels': inscrits_labels, 'valeurs': inscrits_valeurs},
    })
