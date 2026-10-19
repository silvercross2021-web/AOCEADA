"""Prévision de la consommation : les habitudes du foyer et la température (note technique, 4.1 et 4.2 ; 19/10/2026).

Pour CHAQUE capteur :
  - deux niveaux habituels (kWh par jour) : un pour la semaine, un pour les jours de repos (samedi, dimanche, fériés) ;
  - l'effet de la chaleur, c (kWh en plus par degré-jour), appris en comparant ses journées chaudes et fraîches ;
  - prévision d'un jour = niveau habituel + c × (degrés-jours du jour − degrés-jours habituels).
Degrés-jours (de climatisation) = max(0, température moyenne − 24 °C) : en dessous de 24 °C, la chaleur ne fait rien
consommer de plus ; au-dessus, chaque degré compte (un climatiseur réagit beaucoup, une lampe pas du tout).

Chaque soir, une petite correction : nouveau niveau = ancien niveau + 0,3 × (mesure du jour − prévision du jour). Le
niveau ne se corrige que de l'écart que la chaleur n'explique pas. Au tout début, le niveau est la moyenne des
premières journées (pas 0,3 tant qu'il y en a moins de 3), puis le lissage prend le relais : une seule journée
inhabituelle ne change pas tout. C'est un lissage exponentiel (famille de Holt-Winters) avec un terme de température.

L'effet de la chaleur c : pente médiane (Theil-Sen, robuste à un jour étrange) entre paires de journées du MÊME type,
à moins de 3 semaines d'écart (la saison bouge peu), qui diffèrent d'au moins 0,5 degré-jour ; puis rapproché d'une
valeur a priori selon l'appareil (climatiseur 0,6 ; ventilateur 0,04 ; réfrigérateur 0,03 ; sinon 0), avec le poids
de 10 journées : les premiers jours, c'est l'a priori qui parle ; ensuite, les mesures. Jamais négatif (pas de chauffage
en Côte d'Ivoire). Recalculé chaque semaine pendant la relecture de l'historique : aucune journée n'est prévue avec
une information venue de son propre futur.

La fourchette vient des ERREURS déjà constatées (prévision de chaque jour faite la veille, puis comparée à la mesure) :
large au début, elle se resserre. Le profil horaire (part de la journée consommée à chaque heure) sert à couper un jour
en heures : reste d'aujourd'hui, heure à laquelle le crédit finira.

Une journée ne sert que si elle est COMPLÈTE (capteur présent au moins 80 % de la journée, voir PresenceCapteur) :
une journée sans mesure n'est jamais prise pour une consommation nulle.
"""
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from apps.sensors.models import Capteur, MesureEnergie, PresenceCapteur

from . import meteo
from .jours_feries import type_jour

ALPHA = 0.3                  # correction du soir (note technique 4.1)
ALPHA_HABITUEL = 0.05        # degrés-jours « habituels » : moyenne lissée, lente (environ trois semaines)
T_BASE = 24.0                # °C : seuil des degrés-jours de climatisation
JOURS_HISTOIRE = 90          # historique relu (la météo passée couvre 92 jours)
COUVERTURE_COMPLETE = 0.8    # journée complète : capteur présent au moins 80 % du temps
POIDS_A_PRIORI = 10          # poids (en journées) de la valeur a priori de c
FENETRE_PAIRES_J = 21
ECART_MIN_DJ = 0.5
RECALCUL_C = 7               # c recalculé toutes les 7 journées complètes pendant la relecture
FENETRE_PENTE_J = 60
JOURS_PROFIL_FIABLE = 7      # heure annoncée seulement avec au moins 7 journées complètes de profil
RESIDUS_MIN = 5              # en dessous, fourchette tirée de la dispersion des journées (prudente)
Z80 = 1.2816                 # intervalle à 80 %
C_A_PRIORI = (("climatis", 0.6), ("clim", 0.6), ("split", 0.6), ("ventil", 0.04), ("réfrigér", 0.03),
              ("refriger", 0.03), ("frigo", 0.03), ("congél", 0.03), ("congel", 0.03))


def degres_jour(t):
    return None if t is None else max(0.0, float(t) - T_BASE)


def c_a_priori(nom):
    n = (nom or "").lower()
    return next((c for mot, c in C_A_PRIORI if mot in n), 0.0)


def pente_chaleur(obs, c0):
    """(c, pente brute ou None). obs = [(date, type, degrés-jours, kWh)] des journées complètes avec température."""
    obs = [o for o in obs if o[0] >= obs[-1][0] - timedelta(days=FENETRE_PENTE_J)] if obs else []
    pentes, jours = [], set()
    for i, (di, ti, xi, yi) in enumerate(obs):
        for dj, tj, xj, yj in obs[i + 1:]:
            if ti != tj or abs((dj - di).days) > FENETRE_PAIRES_J or abs(xj - xi) < ECART_MIN_DJ:
                continue
            pentes.append((yj - yi) / (xj - xi))
            jours.update((di, dj))
    if not pentes:
        return c0, None
    brute = statistics.median(pentes)
    n = len(jours)
    return max(0.0, (n * brute + POIDS_A_PRIORI * c0) / (n + POIDS_A_PRIORI)), brute


@dataclass
class ModeleCapteur:
    id: object
    nom: str
    c0: float
    niveaux: dict = field(default_factory=dict)      # type de jour -> kWh/jour
    vus: dict = field(default_factory=dict)          # type de jour -> journées observées
    c: float = 0.0
    c_brute: float = None
    habituel: float = None                           # degrés-jours habituels
    n_habituel: int = 0
    jours: int = 0
    residus: dict = field(default_factory=dict)      # date -> mesure − prévision faite la veille

    def niveau(self, typ):
        if typ in self.niveaux:
            return self.niveaux[typ]
        autres = list(self.niveaux.values())
        return autres[0] if autres else None

    def predire(self, d, dj):
        base = self.niveau(type_jour(d))
        if base is None:
            return None
        effet = self.c * (dj - self.habituel) if (dj is not None and self.habituel is not None) else 0.0
        return max(0.0, base + effet)

    def apprendre(self, d, dj, y):
        """Une journée complète de plus : erreur de la prévision faite avant de la voir, puis correction du niveau."""
        typ = type_jour(d)
        pred = self.predire(d, dj)
        base = self.niveau(typ)
        if pred is None:
            self.niveaux[typ] = y
        else:
            r = y - pred
            self.residus[d] = r
            n = self.vus.get(typ, 0)
            a = max(ALPHA, 1.0 / (n + 1)) if typ in self.niveaux else 1.0   # moyenne des 1res journées, puis 0,3
            self.niveaux[typ] = max(0.0, base + a * r)
        self.vus[typ] = self.vus.get(typ, 0) + 1
        if dj is not None:
            a = max(ALPHA_HABITUEL, 1.0 / (self.n_habituel + 1))
            self.habituel = dj if self.habituel is None else self.habituel + a * (dj - self.habituel)
            self.n_habituel += 1
        self.jours += 1


@dataclass
class ModeleFoyer:
    capteurs: list
    temperatures: dict
    jours_complets: int                 # journées où TOUS les capteurs en service ont été présents
    sigma: float                        # écart-type d'une journée du foyer (kWh)
    n_residus: int
    profil: list                        # 24 parts de la journée (somme = 1)
    jours_profil: int
    couverture: dict                    # (capteur id, date) -> part de la journée couverte
    activation: dict                    # capteur id -> 1re date vue
    meteo_disponible: bool

    def degres(self, d):
        return degres_jour(self.temperatures.get(d))

    def jour_capteur(self, cap, d):
        return cap.predire(d, self.degres(d)) or 0.0

    def jour(self, d):
        return sum(self.jour_capteur(c, d) for c in self.capteurs if self._en_service(c, d))

    def _en_service(self, cap, d):
        a = self.activation.get(cap.id)
        return a is not None and d >= a

    def effet_chaleur(self, d):
        """kWh en plus (ou en moins) prévus ce jour-là à cause de la chaleur, par rapport à d'habitude."""
        x = self.degres(d)
        return sum(c.c * (x - c.habituel) for c in self.capteurs
                   if x is not None and c.habituel is not None and self._en_service(c, d))

    def temperature_habituelle(self):
        h = [c.habituel for c in self.capteurs if c.habituel is not None]
        return T_BASE + statistics.median(h) if h else None

    @property
    def profil_fiable(self):
        return self.jours_profil >= JOURS_PROFIL_FIABLE

    def part_restante(self, t):
        """Part de la journée de t encore à consommer, après l'instant t (heure locale)."""
        h = t.hour
        frac = (t.minute * 60 + t.second) / 3600.0
        return sum(self.profil[h + 1:]) + self.profil[h] * (1.0 - frac)

    def heure_de_part(self, s):
        """Heure locale (h, min) à laquelle la part cumulée s (0..1) de la journée est consommée."""
        cumul = 0.0
        for h, p in enumerate(self.profil):
            if p > 0 and cumul + p >= s:
                minutes = int(round((s - cumul) / p * 60))
                return (h, minutes) if minutes < 60 else (min(h + 1, 23), 0)
            cumul += p
        return 23, 59


def _couvertures(capteurs, debut, fin, maintenant):
    """(couverture, activation). couverture[(capteur, date)] = part de la journée où le capteur a envoyé des mesures.
    Avant la 1re trace de présence d'un capteur (historique d'avant le 19/10/2026) : étendue des mesures du foyer ce
    jour-là (≥ 80 % = journée complète), l'ancienne règle."""
    tz = timezone.get_current_timezone()
    ids = [c.id for c in capteurs]
    debut_dt = timezone.make_aware(datetime.combine(debut, time.min), tz)
    couv, activation = {}, {}
    for r in (PresenceCapteur.objects.filter(capteur_id__in=ids, heure__gte=debut_dt)
              .annotate(j=TruncDate("heure", tzinfo=tz)).values("capteur_id", "j").annotate(n=Count("id"))):
        heures = 24.0
        if r["j"] == maintenant.date():
            heures = max(1.0, maintenant.hour + maintenant.minute / 60.0)
        couv[(r["capteur_id"], r["j"])] = min(1.0, r["n"] / heures)
    premiere_presence = dict(PresenceCapteur.objects.filter(capteur_id__in=ids).values("capteur_id")
                             .annotate(m=Min("heure")).values_list("capteur_id", "m"))
    for cid, m in MesureEnergie.objects.filter(capteur_id__in=ids).values("capteur_id").annotate(
            m=Min("timestamp")).values_list("capteur_id", "m"):
        activation[cid] = timezone.localtime(m).date()
    for cid, m in premiere_presence.items():
        d = timezone.localtime(m).date()
        activation[cid] = min(activation.get(cid, d), d)
    # ancienne règle, pour les jours d'avant la présence enregistrée
    etendue = {}
    for r in (MesureEnergie.objects.filter(capteur_id__in=ids, timestamp__gte=debut_dt)
              .annotate(j=TruncDate("timestamp", tzinfo=tz)).values("j")
              .annotate(tmin=Min("timestamp"), tmax=Max("timestamp"))):
        s = (r["tmax"] - r["tmin"]).total_seconds() / 86400.0
        etendue[r["j"]] = 1.0 if s >= COUVERTURE_COMPLETE else max(0.0, s)
    d = debut
    while d <= fin:
        for cid in ids:
            pp = premiere_presence.get(cid)
            if (cid, d) not in couv and (pp is None or d < timezone.localtime(pp).date()):
                couv[(cid, d)] = etendue.get(d, 0.0)
            couv.setdefault((cid, d), 0.0)
        d += timedelta(days=1)
    return couv, activation


def construire(client, maintenant=None):
    """Le modèle du foyer, appris sur les 90 derniers jours (jusqu'à hier). Toujours renvoyé ; voir jours_complets."""
    maintenant = timezone.localtime(maintenant) if maintenant else timezone.localtime()
    hier = maintenant.date() - timedelta(days=1)
    debut = maintenant.date() - timedelta(days=JOURS_HISTOIRE)
    tz = timezone.get_current_timezone()
    capteurs = list(Capteur.objects.filter(client=client).order_by("nom"))
    temps = meteo.temperatures(meteo.ville_du_client(client), debut, maintenant.date() + timedelta(days=meteo.JOURS_FUTURS))
    couv, activation = _couvertures(capteurs, debut, maintenant.date(), maintenant)
    debut_dt = timezone.make_aware(datetime.combine(debut, time.min), tz)
    kwh = {(r["capteur_id"], r["j"]): float(r["e"] or 0) for r in
           MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=debut_dt)
           .annotate(j=TruncDate("timestamp", tzinfo=tz)).values("capteur_id", "j").annotate(e=Sum("energie"))}

    modeles = []
    for cap in capteurs:
        m = ModeleCapteur(cap.id, cap.nom, c_a_priori(cap.nom))
        m.c = m.c0
        obs, complets = [], 0
        d = max(debut, activation.get(cap.id, hier + timedelta(days=1)))
        while d <= hier:
            if couv.get((cap.id, d), 0.0) >= COUVERTURE_COMPLETE:
                if complets and complets % RECALCUL_C == 0 and obs:
                    m.c, m.c_brute = pente_chaleur(obs, m.c0)
                x = degres_jour(temps.get(d))
                y = kwh.get((cap.id, d), 0.0)
                m.apprendre(d, x, y)
                if x is not None:
                    obs.append((d, type_jour(d), x, y))
                complets += 1
            d += timedelta(days=1)
        if obs:
            m.c, m.c_brute = pente_chaleur(obs, m.c0)
        modeles.append(m)

    # journées complètes du FOYER (tous les capteurs en service présents) : totaux et erreurs de la veille
    totaux, residus = [], []
    d = debut
    while d <= hier:
        en_service = [m for m in modeles if activation.get(m.id) is not None and d >= activation[m.id]]
        if en_service and all(couv.get((m.id, d), 0.0) >= COUVERTURE_COMPLETE for m in en_service):
            totaux.append((d, sum(kwh.get((m.id, d), 0.0) for m in en_service)))
            if all(d in m.residus for m in en_service):
                residus.append(sum(m.residus[d] for m in en_service))
        d += timedelta(days=1)
    sigma = _sigma(residus, [t for _, t in totaux])

    # profil horaire du foyer, sur ses journées complètes (lissé vers une journée régulière : le poids d'un jour)
    jours_ok = {d for d, _ in totaux}
    heures = [0.0] * 24
    for r in (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=debut_dt)
              .annotate(h=TruncHour("timestamp", tzinfo=tz)).values("h").annotate(e=Sum("energie"))):
        hl = timezone.localtime(r["h"])
        if hl.date() in jours_ok:
            heures[hl.hour] += float(r["e"] or 0)
    total = sum(heures)
    moyen = total / max(1, len(jours_ok))
    lisse = [x + moyen / 24.0 for x in heures]
    s = sum(lisse)
    profil = [x / s for x in lisse] if s > 0 else [1.0 / 24] * 24

    return ModeleFoyer(capteurs=modeles, temperatures=temps, jours_complets=len(totaux), sigma=sigma,
                       n_residus=len(residus), profil=profil, jours_profil=len(jours_ok), couverture=couv,
                       activation=activation, meteo_disponible=bool(temps))


CACHE_S = 3600


def modele_du_client(client, maintenant=None):
    """Le modèle du foyer, gardé une heure (il n'apprend que des journées finies ; relire 90 jours de mesures à
    chaque page serait lourd)."""
    t = timezone.localtime(maintenant) if maintenant else timezone.localtime()
    minuit = t.replace(hour=0, minute=0, second=0, microsecond=0)
    # version des données PASSÉES (les seules apprises) : une mesure d'aujourd'hui ne change pas le modèle
    passe = MesureEnergie.objects.filter(capteur__client=client, timestamp__lt=minuit).aggregate(m=Max("timestamp"))["m"]
    presence = PresenceCapteur.objects.filter(capteur__client=client, heure__lt=minuit).aggregate(m=Max("heure"))["m"]
    n_capteurs = Capteur.objects.filter(client=client).count()
    cle = (f"prevision_ia:{client.pk}:{getattr(client, 'date_joined', '')}:{getattr(client, 'ville', '')}:"
           f"{t.date().isoformat()}:{n_capteurs}:{passe}:{presence}").replace(" ", "_")
    m = cache.get(cle)
    if m is None:
        m = construire(client, t)
        cache.set(cle, m, CACHE_S)
    return m


def _sigma(residus, totaux):
    """Écart-type d'une journée du foyer : des erreurs déjà constatées quand il y en a assez, sinon de la dispersion
    des journées (prudent). Jamais nul."""
    if len(residus) >= RESIDUS_MIN:
        med = statistics.median(residus)
        mad = statistics.median([abs(r - med) for r in residus])
        moy = statistics.mean(totaux) if totaux else 0.0
        return max(math.hypot(1.4826 * mad, med), 0.1 * moy, 0.05)
    if totaux:
        med = statistics.median(totaux)
        mad = statistics.median([abs(t - med) for t in totaux])
        return max(1.4826 * mad, 0.35 * med, 0.2)
    return 0.2


def epuisement(modele, kwh_restant, maintenant, ecarts=0.0, horizon_jours=60):
    """Instant (heure locale) où kwh_restant sera consommé, ou None au-delà de l'horizon. `ecarts` : nombre
    d'écarts-types ajoutés chaque jour (> 0 : consommation plus forte, fin plus tôt ; < 0 : plus faible)."""
    t = timezone.localtime(maintenant)
    if kwh_restant <= 0:
        return t
    reste = float(kwh_restant)
    for i in range(horizon_jours + 1):
        d = t.date() + timedelta(days=i)
        prevu = modele.jour(d)
        conso = max(prevu + ecarts * modele.sigma, 0.25 * prevu)
        if conso <= 0:
            continue
        deja = (1.0 - modele.part_restante(t)) if i == 0 else 0.0
        dispo = conso * (1.0 - deja)
        if reste <= dispo:
            h, mn = modele.heure_de_part(deja + reste / conso)
            return timezone.make_aware(datetime.combine(d, time(h, mn)), timezone.get_current_timezone())
        reste -= dispo
    return None


def jours_avant(modele, kwh, maintenant, horizon_jours=120):
    """Nombre de jours (décimal) avant d'avoir consommé kwh de plus, ou None au-delà de l'horizon."""
    fin = epuisement(modele, kwh, maintenant, horizon_jours=horizon_jours)
    return None if fin is None else max(0.0, (fin - timezone.localtime(maintenant)).total_seconds() / 86400.0)
