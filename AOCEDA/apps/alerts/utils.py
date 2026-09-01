import logging
import statistics
from decimal import Decimal
from django.core.mail import send_mail  # pyrefly: ignore [untyped-import]
from django.db.models import Sum  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.conf import settings  # pyrefly: ignore [untyped-import]
from apps.accounts.utils import send_mail_async
from .models import RegleDetection, Alerte
from apps.sensors.models import MesureEnergie

logger = logging.getLogger(__name__)

# Seuil sous lequel un compteur prépayé déclenche une alerte « Crédit bas ».
SEUIL_CREDIT_BAS_FCFA = Decimal("10000")
JOURS_AUTONOMIE_BAS = 4


def evaluate_measurements(client, sensor_ids, mesures=None):
    """Évalue les règles de détection du client contre des mesures.

    - `mesures` fourni (chemin synchrone d'ingestion) : on évalue CHAQUE mesure
      nouvellement reçue, afin de ne manquer aucun pic à l'intérieur d'un lot.
    - `mesures` absent (chemin Celery périodique) : on évalue la dernière mesure
      connue de chaque capteur surveillé.
    """
    # Un capteur peut porter PLUSIEURS configurations : on les regroupe en LISTE
    # par capteur (et non plus un dict qui n'en gardait qu'une → les autres étaient
    # ignorées en silence). Chaque règle du capteur est évaluée indépendamment.
    rules_par_capteur = {}
    for r in (RegleDetection.objects
              .filter(client=client, capteur_id__in=sensor_ids)
              .select_related('capteur')):
        rules_par_capteur.setdefault(r.capteur_id, []).append(r)

    if rules_par_capteur:
        if mesures is None:
            mesures = []
            for capteur_id in rules_par_capteur:
                m = (MesureEnergie.objects.filter(capteur_id=capteur_id)
                     .order_by('-timestamp').first())
                if m:
                    mesures.append(m)

        for mesure in mesures:
            for rule in rules_par_capteur.get(mesure.capteur_id, []):
                _evaluer_mesure(client, rule, mesure)

    # Vérification du crédit prépayé (indépendante des règles par capteur)
    check_credit_prepaye(client)


def _alerte_recente(client, capteur_id, type_alerte, minutes):
    """True si une alerte du même type existe déjà pour ce capteur dans la fenêtre.

    Cooldown anti-spam : sans ça, un dépassement soutenu créerait une alerte
    (et un e-mail) à CHAQUE mesure, un ESP32 postant toutes les 2 s produirait
    ~1800 alertes/heure. On déduplique par (capteur, type) sur une fenêtre de temps.
    """
    from datetime import timedelta
    depuis = timezone.now() - timedelta(minutes=minutes)
    return Alerte.objects.filter(
        client=client, type=type_alerte,
        mesure__capteur_id=capteur_id, createdAt__gte=depuis,
    ).exists()


def _evaluer_mesure(client, rule, mesure):
    """Applique les règles de seuil et de surveillance nocturne à une mesure."""
    # Règle 1 : dépassement de seuil de puissance (cooldown 15 min par capteur)
    if mesure.puissance > rule.puissanceMax_W:
        if not _alerte_recente(client, mesure.capteur_id, 'DEPASSEMENT_SEUIL', 15):
            msg = (f"Dépassement de seuil détecté sur le capteur {rule.capteur.nom} : "
                   f"{mesure.puissance} W mesurés (Seuil configuré : {rule.puissanceMax_W} W).")
            alert = Alerte.objects.create(
                client=client, mesure=mesure, type='DEPASSEMENT_SEUIL',
                message=msg, sévérité='Critique')
            send_alert_email(alert)

    # Règle 2 : consommation nocturne « fantôme »
    # Suspendue en mode absence : le bruit de fond nocturne change légitimement quand
    # le foyer est vide (frigo, éclairage de sécurité laissés allumés) — inutile de
    # spammer le client pour un comportement qu'il a lui-même anticipé. Le dépassement
    # de seuil (règle 1, ci-dessus) et le crédit bas restent actifs : une absence est,
    # au contraire, un moment où ces deux-là sont PLUS utiles, pas moins.
    absence_active = (
        getattr(client, 'modeAbsenceActif', False)
        and (client.absenceJusquau is None or timezone.localdate() <= client.absenceJusquau)
    )
    if rule.surveilleNuit and not absence_active:
        local_time = timezone.localtime(mesure.timestamp)
        meas_time = local_time.time()

        if rule.heureDébutNuit <= rule.heureFinNuit:
            is_night = rule.heureDébutNuit <= meas_time <= rule.heureFinNuit
        else:  # Fenêtre à cheval sur minuit, ex. 22:00 → 05:00
            is_night = meas_time >= rule.heureDébutNuit or meas_time <= rule.heureFinNuit

        # Seuil de veille = 10 % du seuil max, avec un plancher à 50 W
        standby_threshold = rule.puissanceMax_W * Decimal("0.1")
        if standby_threshold < 50:
            standby_threshold = Decimal("50")

        if is_night and mesure.puissance > standby_threshold:
            # Cooldown 60 min : une alerte nocturne par capteur et par heure suffit.
            if not _alerte_recente(client, mesure.capteur_id, 'CONSOMMATION_NOCTURNE', 60):
                msg = (f"Consommation nocturne suspecte détectée sur le capteur "
                       f"{rule.capteur.nom} : {mesure.puissance} W à "
                       f"{local_time.strftime('%H:%M:%S')} "
                       f"(Seuil veille estimé : {standby_threshold} W).")
                alert = Alerte.objects.create(
                    client=client, mesure=mesure, type='CONSOMMATION_NOCTURNE',
                    message=msg, sévérité='Avertissement')
                send_alert_email(alert)


def cout_mois_courant_fcfa(client):
    """Coût (FCFA TTC) de la consommation du mois en cours, grille CIE."""
    from apps.analytics.tarifs_cie import calculer_facture_pour_client
    now = timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    agg = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=start, timestamp__lte=now
    ).aggregate(e=Sum('energie'))
    kwh = agg['e'] or Decimal('0')
    return calculer_facture_pour_client(kwh, client)['total_fcfa']


def _mediane_kwh_jour_complet(client, start, now):
    """Médiane des kWh mesurés sur les jours COMPLETS du mois en cours (aujourd'hui
    exclu, toujours partiel). Renvoie None si aucun jour complet n'est encore mesuré.

    Conforme au mémoire §6.3.3 (« consommation journalière médiane observée ») : robuste
    à un jour atypique (pic ponctuel ou absence), contrairement à une moyenne simple qui
    se laisse fausser par une seule journée extrême. Même principe que la médiane+MAD
    utilisée pour l'estimation « fin de mois » (apps.analytics.views._prevision_fin_de_mois),
    volontairement simplifiée ici (pas de MAD/plafond) car le mémoire ne décrit, pour ce
    module précis, qu'une médiane simple.
    """
    minuit = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=start, timestamp__lt=minuit)
            .annotate(jour=TruncDate('timestamp', tzinfo=timezone.get_current_timezone()))
            .values('jour').annotate(kwh=Sum('energie')))
    valeurs = [float(r['kwh'] or 0) for r in rows]
    if not valeurs:
        return None
    return statistics.median(valeurs)


def credit_prepaye_info(client):
    """Estimation du crédit restant d'un compteur prépayé.

    Renvoie None pour les compteurs postpayés. Le crédit restant est estimé
    comme : TOTAL de toutes les recharges depuis toujours − TOUTE la consommation
    depuis toujours (mois précédents clos + mois en cours à ce jour).

    Point important (bug corrigé) : on ne doit JAMAIS ne déduire que la
    consommation du mois EN COURS, sous peine de voir le crédit « remonter tout
    seul » à chaque 1er du mois comme s'il s'était rechargé — un vrai compteur
    prépayé ne se réinitialise jamais spontanément, seule une recharge fait
    remonter le solde. Les mois clos utilisent leur snapshot figé (Prevision),
    déjà généré/maintenu par PrevisionListView pour la carte « Historique
    mensuel » ; le mois en cours est recalculé en direct (jamais de projection).
    """
    if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
        return None

    recharge = Decimal(str(getattr(client, 'creditPrepaye_FCFA', 0) or 0))
    # Jamais rechargé → aucun crédit à afficher (état vide honnête, pas de solde fabriqué).
    if recharge <= 0:
        return None

    # Coût RÉEL du mois à ce jour (grille CIE, TTC), jamais de projection.
    import calendar
    from apps.analytics.tarifs_cie import calculer_facture_pour_client
    from apps.analytics.models import Prevision
    now = timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    kwh = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=start, timestamp__lte=now
    ).aggregate(e=Sum('energie'))['e'] or Decimal('0')
    d = calculer_facture_pour_client(kwh, client)
    cout_mois_courant = d['total_fcfa']

    # Coût CUMULÉ des mois précédents déjà clos (jamais oublié, contrairement à
    # l'ancien calcul qui ne regardait que le mois en cours).
    cout_mois_precedents = Prevision.objects.filter(client=client).exclude(
        annee_mois=now.strftime("%Y-%m")
    ).aggregate(s=Sum('montantEstimé_FCFA'))['s'] or Decimal('0')

    cout = cout_mois_precedents + cout_mois_courant
    restant = max(Decimal('0'), recharge - cout)

    # Rythme journalier honnête : part VARIABLE tarifée au tarif MARGINAL réel (palier
    # CIE atteint, jamais un prix moyen) pour UN JOUR TYPIQUE (médiane des jours complets
    # du mois, robuste à un pic ponctuel/une absence — cf. _mediane_kwh_jour_complet) ;
    # part FIXE (prime fixe + taxe fixe) amortie sur le mois entier, constante quel que
    # soit le rythme de consommation.
    jours_du_mois = calendar.monthrange(now.year, now.month)[1]
    fixe_jour = (d['prime_fixe_fcfa'] + d['taxe_fixe_fcfa']) / Decimal(jours_du_mois)
    mediane_kwh = _mediane_kwh_jour_complet(client, start, now)
    if mediane_kwh and mediane_kwh > 0:
        # Coût marginal d'UN jour médian de plus, au tarif du palier actuellement atteint :
        # la part fixe s'annule dans la soustraction, il ne reste que le variable marginal.
        d_marge = calculer_facture_pour_client(kwh + Decimal(str(mediane_kwh)), client)
        variable_jour = d_marge['total_fcfa'] - d['total_fcfa']
        cout_jour = variable_jour + fixe_jour
        jours_restants = int(restant / cout_jour) if cout_jour > 0 else None
    else:
        # Aucun jour complet mesuré ce mois-ci : pas de rythme fiable, honnête (pas de
        # nombre de jours inventé sur la seule base de la part fixe).
        cout_jour = fixe_jour
        jours_restants = None

    return {
        "recharge_fcfa": recharge,
        "consomme_fcfa": cout,
        "restant_fcfa": restant,
        "cout_jour_fcfa": cout_jour,
        "jours_restants": jours_restants,
    }


def check_credit_prepaye(client):
    """Crée une alerte « Crédit bas » si le crédit prépayé estimé est faible.

    Déduplication : au plus une alerte CREDIT_BAS par jour et par client.
    """
    info = credit_prepaye_info(client)
    if not info:
        return

    # Seuil personnalisé par client, ou valeur globale par défaut
    seuil = getattr(client, 'seuilCreditBas_FCFA', None) or SEUIL_CREDIT_BAS_FCFA
    est_bas = (
        info["restant_fcfa"] < seuil
        or (info["jours_restants"] is not None and info["jours_restants"] <= JOURS_AUTONOMIE_BAS)
    )
    if not est_bas:
        return

    today = timezone.localdate()
    if Alerte.objects.filter(client=client, type='CREDIT_BAS', createdAt__date=today).exists():
        return

    autonomie = (f" (≈ {info['jours_restants']} jour(s) d'autonomie)"
                 if info["jours_restants"] is not None else "")
    msg = (f"Crédit prépayé estimé bas : environ {int(info['restant_fcfa'])} FCFA "
           f"restants{autonomie}. Pensez à recharger pour éviter une coupure.")
    alert = Alerte.objects.create(
        client=client, type='CREDIT_BAS', message=msg, sévérité='Avertissement')
    send_alert_email(alert)


def send_alert_email(alert):
    """Envoie l'e-mail d'alerte si le client a activé les notifications e-mail."""
    if not getattr(alert.client, 'notifEmail', True):
        return

    subject = f"[{alert.sévérité.upper()}] Alerte Énergétique AOCEDA - {alert.get_type_display()}"
    body = (
        f"Bonjour {alert.client.nom},\n\n"
        f"Une alerte a été déclenchée sur votre système AOCEDA :\n"
        f"- Type : {alert.get_type_display()}\n"
        f"- Sévérité : {alert.sévérité}\n"
        f"- Détails : {alert.message}\n"
        f"- Date/Heure : {timezone.localtime(alert.createdAt).strftime('%d/%m/%Y à %H:%M:%S')}\n\n"
        f"Veuillez consulter votre tableau de bord AOCEDA pour plus de détails.\n\n"
        f"Cordialement,\n"
        f"L'équipe AOCEDA"
    )

    def mark_sent():
        alert.emailEnvoyé = True
        alert.save(update_fields=['emailEnvoyé'])

    send_mail_async(
        subject,
        body,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
        [alert.client.email],
        fail_silently=False,
        callback=mark_sent
    )
