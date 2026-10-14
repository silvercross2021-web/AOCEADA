import logging
import statistics
from decimal import Decimal
from django.core.mail import send_mail  # pyrefly: ignore [untyped-import]
from django.db.models import Sum  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from datetime import timedelta
from django.conf import settings  # pyrefly: ignore [untyped-import]
from apps.accounts.utils import send_mail_async
from .models import RegleDetection, Alerte
from apps.sensors.models import MesureEnergie

logger = logging.getLogger(__name__)

# Seuil sous lequel un compteur prépayé déclenche une alerte « Crédit bas ».
SEUIL_CREDIT_BAS_FCFA = Decimal("10000")
JOURS_AUTONOMIE_BAS = 4
# Valeur enregistrée par la page quand l'alerte de puissance est désactivée
PUISSANCE_DESACTIVEE_W = Decimal("100000")


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

    # Vérifications du compte (indépendantes des règles par capteur) : crédit prépayé,
    # tranche de la facture postpayée.
    check_credit_prepaye(client)
    check_tranche_postpaye(client)


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


def seuil_nuit(rule):
    """Seuil de la surveillance nocturne : celui choisi par le client, sinon le seuil
    automatique de la note technique (10 % du seuil de puissance, 50 W au moins)."""
    if rule.seuilNuit_W is not None:
        return Decimal(rule.seuilNuit_W)
    # Alerte de puissance désactivée (100 000 W, valeur de la page) : le seuil de nuit
    # retombe sur son minimum, sinon il vaudrait 10 000 W et ne se déclencherait jamais.
    if Decimal(rule.puissanceMax_W) >= PUISSANCE_DESACTIVEE_W:
        return Decimal("50")
    return max(Decimal(rule.puissanceMax_W) * Decimal("0.1"), Decimal("50"))


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

        standby_threshold = seuil_nuit(rule)

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
    """Coût (FCFA TTC) de ce qui a été consommé depuis le 1er du mois. En postpayé,
    c'est la part du mois dans la facture du bimestre (voir analytics.views.cout_entre)."""
    from apps.analytics.views import cout_entre
    now = timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return cout_entre(client, start, now)


def _mediane_kwh_jour_complet(client, start, now):
    """Médiane des kWh mesurés sur les jours COMPLETS entre `start` et aujourd'hui
    (aujourd'hui exclu, toujours partiel). None si aucun jour complet n'est mesuré.

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
    """Estimation du crédit restant d'un compteur prépayé, None pour un postpayé.

    En prépaiement, l'arrêté n° 1355 (articles 10 à 13) fixe UN prix par kWh, sans
    tranche, prime fixe linéarisée comprise : le compteur décompte chaque kWh au même
    prix. Donc : crédit restant = TOTAL des recharges − TOUTE l'énergie mesurée depuis
    toujours × prix du kWh. Jamais la seule consommation du mois en cours (le crédit
    « remonterait » chaque 1er du mois, alors qu'un compteur prépayé ne se recharge
    jamais tout seul).

    Autonomie : rythme d'un jour typique = médiane des jours COMPLETS des 30 derniers
    jours (robuste à un pic ou à une absence), au même prix du kWh.
    """
    if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
        return None

    recharge = Decimal(str(getattr(client, 'creditPrepaye_FCFA', 0) or 0))
    # Jamais rechargé → aucun crédit à afficher (état vide honnête, pas de solde fabriqué).
    if recharge <= 0:
        return None

    from apps.analytics.tarifs_cie import calculer_facture_pour_client, prix_kwh_tout_compris
    kwh = MesureEnergie.objects.filter(capteur__client=client).aggregate(e=Sum('energie'))['e'] or Decimal('0')
    cout = calculer_facture_pour_client(kwh, client)['total_fcfa']
    restant = max(Decimal('0'), recharge - cout)

    now = timezone.localtime()
    depuis = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)
    mediane_kwh = _mediane_kwh_jour_complet(client, depuis, now)
    if mediane_kwh and mediane_kwh > 0:
        cout_jour = (Decimal(str(mediane_kwh)) * prix_kwh_tout_compris(client)).quantize(Decimal('0.01'))
        jours_restants = int(restant / cout_jour) if cout_jour > 0 else None
    else:
        # Aucun jour complet mesuré : pas de rythme fiable, honnête (aucun chiffre inventé).
        cout_jour = None
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


# Tranche postpayée : prévenir quand le seuil de la tranche 1 approche (90 % atteints,
# ou atteint dans 7 jours au rythme actuel), puis quand il est franchi.
TRANCHE_PART_APPROCHE = Decimal("0.9")
TRANCHE_JOURS_APPROCHE = 7
TRANCHE_VERIF_SECONDES = 60   # l'ESP32 poste toutes les ~2 s : un calcul par minute suffit


def _fmt_prix(x):
    return f"{Decimal(x):.2f}".replace(".", ",")


def _fmt_kwh(x):
    return f"{Decimal(x):.1f}".replace(".", ",")


def etat_tranche(client):
    """Où en est la facture postpayée du bimestre par rapport au seuil de sa tranche 1.

    None pour un prépayé (aucune tranche en prépaiement, arrêté n° 1355 art. 10 à 13).
    Sinon : kWh du bimestre, seuil, prix des deux tranches, rythme (médiane des jours
    complets du bimestre, au moins 3) et jours avant le seuil à ce rythme."""
    if getattr(client, 'typeCompteur', 'postpaye') == 'prepaye':
        return None
    from apps.analytics.tarifs_cie import calculer_facture_bimestre, libelle_periode
    from apps.analytics.views import periode_courante, _debut_jour
    now = timezone.localtime()
    per = periode_courante(client, now)
    debut = _debut_jour(per["debut"])
    kwh = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=debut, timestamp__lte=now
    ).aggregate(e=Sum('energie'))['e'] or Decimal('0')
    g = calculer_facture_bimestre(
        0, getattr(client, 'amperage', 10) or 10, getattr(client, 'typeTarif', 'general') or 'general')
    seuil = g["seuil_t1_kwh"]

    rows = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=debut,
                                         timestamp__lt=now.replace(hour=0, minute=0, second=0, microsecond=0))
            .annotate(jour=TruncDate('timestamp', tzinfo=timezone.get_current_timezone()))
            .values('jour').annotate(kwh=Sum('energie')))
    valeurs = [float(r['kwh'] or 0) for r in rows]
    rythme = statistics.median(valeurs) if len(valeurs) >= 3 else None
    jours_avant = None
    if rythme and rythme > 0 and kwh < seuil:
        jours_avant = float(seuil - kwh) / rythme
    return {
        "periode": per, "libelle": libelle_periode(per["debut"], per["fin"]),
        "kwh": Decimal(kwh), "seuil": seuil, "type_tarif": g["type_tarif"],
        "prix_t1": g["tranche1_prix"], "prix_t2": g["tranche2_prix"],
        "rythme_kwh_jour": rythme, "jours_avant_seuil": jours_avant,
        "jours_restants_periode": (per["fin"] - now.date()).days,
    }


def check_tranche_postpaye(client, forcer=False):
    """Crée l'alerte « tranche » d'un compteur postpayé, au plus une fois par bimestre
    et par type (approche, puis franchie). Ne fait rien pour un prépayé."""
    if getattr(client, 'typeCompteur', 'postpaye') == 'prepaye':
        return
    from django.core.cache import cache
    cle = f"aoceda:tranche:{client.pk}"
    if not forcer and cache.get(cle):
        return
    cache.set(cle, True, TRANCHE_VERIF_SECONDES)

    e = etat_tranche(client)
    if not e or e["seuil"] <= 0:
        return
    depuis = _debut_jour_aware(e["periode"]["debut"])
    social = e["type_tarif"] == "social"
    # Au social, la tranche 2 coûte DEUX fois plus (31,72 → 65,11 F) : vrai risque, avertissement.
    # Au général, elle coûte MOINS cher (86,92 → 75,34 F) : simple information.
    severite = 'Avertissement' if social else 'Info'
    if social:
        effet = (f"Au-delà, chaque kWh coûte {_fmt_prix(e['prix_t2'])} F au lieu de "
                 f"{_fmt_prix(e['prix_t1'])} F (tarif social : environ deux fois plus cher).")
    else:
        effet = (f"Au-delà, chaque kWh coûte {_fmt_prix(e['prix_t2'])} F au lieu de "
                 f"{_fmt_prix(e['prix_t1'])} F (au tarif général, la tranche 2 est moins chère).")
    seuil_txt = f"{_fmt_kwh(e['seuil']).replace(',0', '')} kWh"

    if e["kwh"] >= e["seuil"]:
        if Alerte.objects.filter(client=client, type='TRANCHE_FRANCHIE', createdAt__gte=depuis).exists():
            return
        msg = (f"Tranche 2 atteinte pour le bimestre {e['libelle']} : {_fmt_kwh(e['kwh'])} kWh "
               f"consommés, au-delà des {seuil_txt} de la tranche 1. {effet}")
        alert = Alerte.objects.create(client=client, type='TRANCHE_FRANCHIE', message=msg, sévérité=severite)
        send_alert_email(alert)
        return

    proche = e["kwh"] >= e["seuil"] * TRANCHE_PART_APPROCHE
    bientot = (e["jours_avant_seuil"] is not None
               and e["jours_avant_seuil"] <= TRANCHE_JOURS_APPROCHE
               and e["jours_avant_seuil"] <= e["jours_restants_periode"] + 1)
    if not (proche or bientot):
        return
    if Alerte.objects.filter(client=client, type='TRANCHE_APPROCHE', createdAt__gte=depuis).exists():
        return
    quand = ""
    if e["jours_avant_seuil"] is not None:
        j = max(1, round(e["jours_avant_seuil"]))
        quand = f" Au rythme actuel ({_fmt_kwh(e['rythme_kwh_jour'])} kWh par jour), il sera atteint dans environ {j} jour(s)."
    msg = (f"La tranche 1 approche pour le bimestre {e['libelle']} : {_fmt_kwh(e['kwh'])} kWh "
           f"consommés sur {seuil_txt}.{quand} {effet}")
    alert = Alerte.objects.create(client=client, type='TRANCHE_APPROCHE', message=msg, sévérité=severite)
    send_alert_email(alert)


def _debut_jour_aware(d):
    from apps.analytics.views import _debut_jour
    return _debut_jour(d)


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
