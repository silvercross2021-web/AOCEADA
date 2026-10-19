import logging
from decimal import Decimal
from django.db.models import Sum, Min  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from datetime import timedelta
from django.conf import settings  # pyrefly: ignore [untyped-import]
from apps.accounts.utils import send_mail_async
from .models import RegleDetection, Alerte
from apps.sensors.models import MesureEnergie, Capteur

logger = logging.getLogger(__name__)

# Seuil sous lequel un compteur prépayé déclenche une alerte « Crédit bas ».
SEUIL_CREDIT_BAS_FCFA = Decimal("10000")
JOURS_AUTONOMIE_BAS = 4
# Valeur enregistrée par la page quand l'alerte de puissance est désactivée
PUISSANCE_DESACTIVEE_W = Decimal("100000")
COMPTE_VERIF_SECONDES = 60


# Réglages SIMPLES : part de la puissance de l'abonnement à partir de laquelle un appareil déclenche l'alerte
NIVEAUX_DEPASSEMENT = {'prudent': Decimal("0.5"), 'normal': Decimal("0.8"), 'limite': Decimal("1.0")}


def capacite_w(client):
    """Puissance que supporte l'abonnement du client (5 A ≈ 1 100 W, 10 A ≈ 2 200 W, 15 A ≈ 3 300 W)."""
    from apps.analytics.tarifs_cie import PUISSANCE_KW
    amperage = int(getattr(client, 'amperage', 10) or 10)
    return int(PUISSANCE_KW.get(amperage, Decimal("2.2")) * 1000)


def seuil_simple_w(client):
    """Seuil de puissance du réglage simple : niveau choisi × puissance de l'abonnement."""
    facteur = NIVEAUX_DEPASSEMENT.get(getattr(client, 'niveauDepassement', 'normal'), Decimal("0.8"))
    return (Decimal(capacite_w(client)) * facteur).quantize(Decimal("1"))


class ReglePrefs:
    """Règle « virtuelle » déduite des réglages simples du compte, pour un capteur SANS règle personnalisée. Même
    interface qu'une RegleDetection ; elle n'est jamais enregistrée (pk None → les alertes qu'elle crée n'ont pas de
    règle : le cooldown retombe sur (capteur, type) et la page propose « Régler »)."""
    pk = None

    def __init__(self, client, capteur):
        self.capteur = capteur
        self.puissanceMax_W = seuil_simple_w(client)
        self.surveilleNuit = bool(getattr(client, 'alerteNuit', True))
        self.heureDébutNuit = client.nuitDebut
        self.heureFinNuit = client.nuitFin
        # nuit : 10 % du seuil, 50 W au moins (même formule que les règles personnalisées)
        self.seuilNuit_W = max(self.puissanceMax_W * Decimal("0.1"), Decimal("50"))


def evaluate_measurements(client, sensor_ids, mesures=None):
    """Évalue les règles de détection du client contre des mesures.

    - `mesures` fourni (chemin synchrone d'ingestion) : on évalue CHAQUE mesure
      nouvellement reçue, afin de ne manquer aucun pic à l'intérieur d'un lot.
    - `mesures` absent (chemin Celery périodique) : on évalue la dernière mesure
      connue de chaque capteur surveillé.

    Un capteur qui a une ou plusieurs règles PERSONNALISÉES est évalué avec elles ; un capteur sans règle est évalué avec
    les RÉGLAGES SIMPLES du compte (19/10/2026), tant qu'un des deux types (puissance, nuit) est activé.
    """
    rules_par_capteur = {}
    for r in (RegleDetection.objects
              .filter(client=client, capteur_id__in=sensor_ids)
              .select_related('capteur')):
        rules_par_capteur.setdefault(r.capteur_id, []).append(r)

    if getattr(client, 'alerteDepassement', True) or getattr(client, 'alerteNuit', True):
        for cap in Capteur.objects.filter(client=client, id__in=sensor_ids, actif=True):
            if cap.id not in rules_par_capteur:
                rules_par_capteur[cap.id] = [ReglePrefs(client, cap)]

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
    # tranche de la facture postpayée. Le boîtier poste toutes les ~2 s : au plus UNE vérification par minute et par
    # client (avant le 19/10/2026 le crédit était recalculé à chaque envoi : 0,6 s par envoi sur 40 000 mesures, et
    # l'ingestion attendait). La recharge, le relevé et la tâche planifiée appellent check_credit_prepaye directement.
    from django.core.cache import cache
    cle = f"aoceda:verif-compte:{client.pk}"
    if not cache.get(cle):
        cache.set(cle, True, COMPTE_VERIF_SECONDES)
        check_credit_prepaye(client)
        check_tranche_postpaye(client)


def alertes_du_client(client):
    """Les alertes que le client doit voir, avec UNE seule règle partout (tableau de bord, liste, cloche, assistant) :
    un compteur postpayé n'a pas de crédit, une ancienne alerte « Crédit bas » ne compte plus (19/10/2026 : le
    tableau de bord disait « 1 alerte active » pendant que la liste et la cloche n'en montraient aucune)."""
    qs = Alerte.objects.filter(client=client)
    if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
        qs = qs.exclude(type='CREDIT_BAS')
    return qs


def nombre_fr(x, decimales=1):
    """« 45,1 » (virgule française) pour les messages d'alerte."""
    return f"{float(x):.{decimales}f}".replace(".", ",")


def _alerte_recente(client, capteur_id, type_alerte, minutes, regle=None):
    """True si une alerte du même type existe déjà dans la fenêtre.

    Cooldown anti-spam : sans ça, un dépassement soutenu créerait une alerte
    (et un e-mail) à CHAQUE mesure, un ESP32 postant toutes les 2 s produirait
    ~1800 alertes/heure. On déduplique par (RÈGLE, type) sur une fenêtre de temps : deux règles d'un même capteur
    (ex. un seuil bas pour une lampe et un seuil haut) ne se masquent plus l'une l'autre (19/10/2026) ; une ancienne
    alerte sans règle retombe sur la clé (capteur, type).
    """
    from datetime import timedelta
    depuis = timezone.now() - timedelta(minutes=minutes)
    qs = Alerte.objects.filter(client=client, type=type_alerte, createdAt__gte=depuis)
    if regle is not None:
        return qs.filter(regle=regle).exists() or qs.filter(regle__isnull=True, mesure__capteur_id=capteur_id).exists()
    return qs.filter(mesure__capteur_id=capteur_id).exists()


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
    """Applique les règles de seuil et de surveillance nocturne à une mesure. Les interrupteurs du compte
    (alerteDepassement, alerteNuit) coupent TOUT ce type d'alerte, règles personnalisées comprises."""
    regle_fk = rule if isinstance(rule, RegleDetection) else None
    auto = regle_fk is None
    # Règle 1 : dépassement de seuil de puissance (cooldown 15 min)
    if getattr(client, 'alerteDepassement', True) and mesure.puissance > rule.puissanceMax_W:
        if not _alerte_recente(client, mesure.capteur_id, 'DEPASSEMENT_SEUIL', 15, regle=regle_fk):
            msg = (f"Dépassement de seuil détecté sur le capteur {rule.capteur.nom} : "
                   f"{nombre_fr(mesure.puissance)} W mesurés (seuil {'automatique' if auto else 'configuré'} : "
                   f"{nombre_fr(rule.puissanceMax_W, 0)} W).")
            alert = Alerte.objects.create(
                client=client, mesure=mesure, regle=regle_fk, type='DEPASSEMENT_SEUIL',
                message=msg, sévérité='Critique')
            send_alert_email(alert)

    # Règle 2 : consommation nocturne « fantôme ». Suspendue en mode absence (le bruit de fond change légitimement
    # quand le foyer est vide) ; le dépassement de seuil et le crédit bas restent actifs.
    if getattr(client, 'alerteNuit', True) and rule.surveilleNuit and not absence_active(client):
        local_time = timezone.localtime(mesure.timestamp)
        meas_time = local_time.time()

        if rule.heureDébutNuit <= rule.heureFinNuit:
            is_night = rule.heureDébutNuit <= meas_time <= rule.heureFinNuit
        else:  # Fenêtre à cheval sur minuit, ex. 22:00 → 05:00
            is_night = meas_time >= rule.heureDébutNuit or meas_time <= rule.heureFinNuit

        standby_threshold = seuil_nuit(rule)

        if is_night and mesure.puissance > standby_threshold:
            # Cooldown 60 min : une alerte nocturne par capteur et par heure suffit.
            if not _alerte_recente(client, mesure.capteur_id, 'CONSOMMATION_NOCTURNE', 60, regle=regle_fk):
                msg = (f"Consommation nocturne suspecte détectée sur le capteur "
                       f"{rule.capteur.nom} : {nombre_fr(mesure.puissance)} W à "
                       f"{local_time.strftime('%H:%M')} "
                       f"(seuil de veille : {nombre_fr(standby_threshold, 0)} W).")
                alert = Alerte.objects.create(
                    client=client, mesure=mesure, regle=regle_fk, type='CONSOMMATION_NOCTURNE',
                    message=msg, sévérité='Avertissement')
                send_alert_email(alert)


def cout_mois_courant_fcfa(client):
    """Coût (FCFA TTC) de ce qui a été consommé depuis le 1er du mois. En postpayé,
    c'est la part du mois dans la facture du bimestre (voir analytics.views.cout_entre)."""
    from apps.analytics.views import cout_entre
    now = timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return cout_entre(client, start, now)


def _rythme(modele, now, jours=7):
    """Consommation moyenne prévue (kWh par jour) sur les prochains jours, ou None si le foyer n'a pas encore de
    journée complète mesurée (aucun chiffre inventé)."""
    if modele.jours_complets < 1:
        return None
    d = now.date()
    r = sum(modele.jour(d + timedelta(days=i)) for i in range(jours)) / jours
    return r if r > 0 else None


def credit_prepaye_info(client):
    """Estimation du crédit restant d'un compteur prépayé, None pour un postpayé.

    En prépaiement, l'arrêté n° 1355 (articles 10 à 13) fixe UN prix par kWh, sans
    tranche, prime fixe linéarisée comprise : le compteur décompte chaque kWh au même
    prix. Donc : crédit restant = TOTAL des recharges − TOUTE l'énergie mesurée depuis
    toujours × prix du kWh. Jamais la seule consommation du mois en cours (le crédit
    « remonterait » chaque 1er du mois, alors qu'un compteur prépayé ne se recharge
    jamais tout seul).

    Recalage (19/10/2026, note technique 4.2) : si la personne a lu les kWh restants sur
    l'écran de son compteur, le crédit repart de cette lecture : kWh lus + kWh des
    recharges faites après − kWh mesurés après.

    Autonomie (note technique 4.2) : ce qui reste, moins ce que le foyer va consommer
    chaque jour selon le modèle de prévision (habitudes semaine / repos, température
    annoncée), jusqu'à zéro : DATE et heure de fin (l'heure seulement quand le profil
    horaire du foyer est connu), avec une fourchette (plus tôt si le foyer consomme plus
    que d'habitude, plus tard sinon). Seules les journées COMPLÈTES servent : avant le
    19/10/2026, une journée de deux heures de mesure faisait croire à un rythme très bas
    (des centaines de jours d'autonomie affichés).
    """
    if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
        return None
    from apps.analytics.models import RechargeCredit
    from apps.analytics.prevision_ia import Z80, epuisement, modele_du_client
    from apps.analytics.tarifs_cie import calculer_facture_pour_client, prix_kwh_tout_compris

    recharge = Decimal(str(getattr(client, 'creditPrepaye_FCFA', 0) or 0))
    prix_kwh = prix_kwh_tout_compris(client)
    releve, releve_le = getattr(client, 'creditReleve_kWh', None), getattr(client, 'creditReleveLe', None)
    if releve is not None and releve_le is not None:
        kwh_apres = MesureEnergie.objects.filter(capteur__client=client, timestamp__gt=releve_le).aggregate(
            e=Sum('energie'))['e'] or Decimal('0')
        recharges_apres = RechargeCredit.objects.filter(client=client, dateRecharge__gt=releve_le).aggregate(
            m=Sum('montant_FCFA'))['m'] or Decimal('0')
        restant_kwh = Decimal(str(releve)) + (recharges_apres / prix_kwh if prix_kwh > 0 else Decimal('0')) - kwh_apres
        cout = calculer_facture_pour_client(kwh_apres, client)['total_fcfa']
        restant = max(Decimal('0'), (restant_kwh * prix_kwh).quantize(Decimal('0.01')))
        source = "releve"
    else:
        # Recharges DATÉES (déclarées dans l'application) : le crédit = leur total − le coût de l'énergie mesurée
        # DEPUIS la première. Avant le 20/10/2026, toute l'énergie mesurée depuis toujours était déduite, y compris
        # celle d'avant la première recharge : un client qui déclarait sa première recharge après des semaines de
        # mesures voyait un crédit à 0.
        agg = RechargeCredit.objects.filter(client=client).aggregate(total=Sum('montant_FCFA'), premiere=Min('dateRecharge'))
        mesures = MesureEnergie.objects.filter(capteur__client=client)
        if agg['premiere'] is not None:
            recharge = Decimal(str(agg['total']))
            mesures = mesures.filter(timestamp__gte=agg['premiere'])
        elif recharge <= 0:
            # Jamais rechargé → aucun crédit à afficher (état vide honnête, pas de solde fabriqué).
            return None
        kwh = mesures.aggregate(e=Sum('energie'))['e'] or Decimal('0')
        cout = calculer_facture_pour_client(kwh, client)['total_fcfa']
        restant = max(Decimal('0'), recharge - cout)
        source = "recharges"
    restant_kwh = float(restant / prix_kwh) if prix_kwh > 0 else 0.0

    now = timezone.localtime()
    modele = modele_du_client(client, now)
    rythme = _rythme(modele, now)
    cout_jour = jours_restants = fin = fin_tot = fin_tard = None
    if rythme:
        cout_jour = (Decimal(str(rythme)) * prix_kwh).quantize(Decimal('0.01'))
        fin = epuisement(modele, restant_kwh, now)
        fin_tot = epuisement(modele, restant_kwh, now, ecarts=Z80)
        fin_tard = epuisement(modele, restant_kwh, now, ecarts=-Z80)
        jours_restants = (int((fin - now).total_seconds() // 86400) if fin is not None
                          else int(restant_kwh / rythme))                 # au-delà de 60 jours : au rythme moyen
    return {
        "recharge_fcfa": recharge,
        "consomme_fcfa": cout,
        "restant_fcfa": restant,
        "restant_kwh": round(restant_kwh, 2),
        "cout_jour_fcfa": cout_jour,
        "jours_restants": jours_restants,
        "fin_estimee": fin, "fin_tot": fin_tot, "fin_tard": fin_tard,
        "heure_fiable": modele.profil_fiable,
        "source": source,
        "releve": ({"kwh": float(releve), "le": releve_le} if source == "releve" else None),
    }


def check_credit_prepaye(client):
    """Crée une alerte « Crédit bas » si le crédit prépayé estimé est faible.

    Déduplication : au plus une alerte CREDIT_BAS par jour et par client.
    """
    if not getattr(client, 'alerteCredit', True):
        return
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
           f"restants{autonomie}. Pensez à acheter de l'énergie (agence CIE, mobile money) avant la coupure, puis mettez à jour votre crédit dans AOCEDA.")
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
    prévu par le modèle, après au moins 3 journées complètes) et jours avant le seuil."""
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

    # Rythme et date du changement de tranche : le modèle de prévision (journées complètes seulement, habitudes
    # semaine / repos, température annoncée), plus une médiane de journées parfois partielles (19/10/2026)
    from apps.analytics.prevision_ia import jours_avant as _jours_avant, modele_du_client
    modele = modele_du_client(client, now)
    rythme = _rythme(modele, now) if modele.jours_complets >= 3 else None
    jours_avant = None
    if rythme and kwh < seuil:
        jours_avant = _jours_avant(modele, float(seuil - kwh), now)
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
    if getattr(client, 'typeCompteur', 'postpaye') == 'prepaye' or not getattr(client, 'alerteTranche', True):
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

    if alert.type == 'INTERVENTION':
        # Suivi d'une demande d'intervention : un message simple, pas une « alerte énergétique »
        sujet = "AOCEDA - Suivi de votre demande d'intervention"
        corps = (f"Bonjour {alert.client.nom},\n\n{alert.message}\n\n"
                 "Retrouvez le détail de votre demande dans la rubrique « Interventions » de votre espace AOCEDA.\n\n"
                 "Cordialement,\nL'équipe AOCEDA")

        def envoye():
            alert.emailEnvoyé = True
            alert.save(update_fields=['emailEnvoyé'])
        send_mail_async(sujet, corps, getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
                        [alert.client.email], fail_silently=False, callback=envoye)
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


def absence_active(client):
    return bool(getattr(client, 'modeAbsenceActif', False)
                and (client.absenceJusquau is None or timezone.localdate() <= client.absenceJusquau))


def etat_surveillance(client):
    """Ce que la surveillance fait RÉELLEMENT pour ce client (page Alertes, 19/10/2026) : sans lui, la page disait
    « Tout va bien, aucune règle ne s'est déclenchée » même sans capteur, sans règle ou boîtier muet depuis des jours.
    capteurs_surveilles = capteurs couverts par une règle personnalisée OU par les réglages simples (puissance ou nuit
    activés) ; en_ligne / dernier_contact = le boîtier répond-il."""
    from apps.analytics.views import etat_contact
    capteurs = list(Capteur.objects.filter(client=client).values_list('id', flat=True))
    avec_regle = set(RegleDetection.objects.filter(client=client, capteur_id__in=capteurs).values_list('capteur_id', flat=True))
    simple = bool(getattr(client, 'alerteDepassement', True) or getattr(client, 'alerteNuit', True))
    surveilles = set(capteurs) if simple else avec_regle
    contact = etat_contact(client)
    return {
        "capteurs": len(capteurs),
        "regles": RegleDetection.objects.filter(client=client).count(),
        "capteurs_surveilles": len(surveilles),
        "reglage_simple": simple,
        "en_ligne": contact["en_ligne"],
        "dernier_contact": (timezone.localtime(contact["dernier_contact"]).isoformat(timespec="seconds")
                            if contact["dernier_contact"] else None),
        "absence_active": absence_active(client),
        "absence_jusquau": client.absenceJusquau.isoformat() if getattr(client, 'absenceJusquau', None) else None,
        "email_actif": bool(getattr(client, 'notifEmail', True)),
    }
