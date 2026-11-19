"""Température du logement : le DHT11 du boîtier, calibré sur la météo de la ville (18/11/2026).

Garanties vérifiées : une journée n'est « mesurée » que si elle est vraiment couverte ; tant que le capteur n'est pas
calibré (7 jours communs avec la ville), la prévision garde la météo seule (aucun mélange de deux échelles) ; une fois
calibré, TOUS les jours (mesurés, sans relevé, aujourd'hui, à venir) sont sur la même échelle ; un capteur aberrant est
écarté en le disant ; jamais de valeur inventée ; aucun test n'appelle Internet (la météo est dans MeteoJour)."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from apps.sensors.models import Capteur, Dispositif, MesureEnergie, PresenceCapteur, ReleveAmbiant

from . import prevision_ia, temperature_locale
from .models import MeteoJour


def creer_client(email="temp@test.ci"):
    c = Client(email=email, nom="Client température", role="client")
    c.set_password("Password123!")
    c.save()
    return c


def debut_du_jour(d):
    return timezone.make_aware(datetime.combine(d, time(0, 0)))


class BaseTemperature(TestCase):
    """Un client avec un boîtier ; aide pour poser des relevés heure par heure."""

    def setUp(self):
        cache.clear()
        self.client_ = creer_client()
        self.boitier = Dispositif.objects.create(client=self.client_, apiKeyDevice="cle_temp_test")
        self.aujourd_hui = timezone.localdate()

    def releves(self, jour, temperature, heures=range(24), par_heure=6, boitier=None):
        """`par_heure` relevés à `temperature` pour chacune des `heures` de ce jour."""
        boitier = boitier or self.boitier
        base = debut_du_jour(jour)
        lignes = [ReleveAmbiant(dispositif=boitier, instant=base + timedelta(hours=h, minutes=i * (60 // par_heure)),
                                temperature_c=Decimal(str(temperature)), humidite_pct=Decimal("60"))
                  for h in heures for i in range(par_heure)]
        ReleveAmbiant.objects.bulk_create(lignes)

    def ville(self, jour, t, prevue=False):
        MeteoJour.objects.update_or_create(ville="Abidjan", date=jour, defaults={"t_moy": Decimal(str(t)), "prevue": prevue})

    def jours_passes(self, n):
        return [self.aujourd_hui - timedelta(days=i) for i in range(n, 0, -1)]


class MoyennesJournalieresTests(BaseTemperature):
    def test_journee_couverte_donne_sa_moyenne(self):
        hier = self.aujourd_hui - timedelta(days=1)
        self.releves(hier, 30.0)
        m = temperature_locale.moyennes_journalieres(self.client_, hier, hier)
        self.assertAlmostEqual(m[hier], 30.0, places=6)

    def test_journee_trouee_n_est_pas_utilisee(self):
        """19 heures sur 24 : une moyenne tirée des seules heures présentes pourrait être fausse (nuits manquantes)."""
        hier = self.aujourd_hui - timedelta(days=1)
        self.releves(hier, 30.0, heures=range(19))
        self.assertEqual(temperature_locale.moyennes_journalieres(self.client_, hier, hier), {})
        self.releves(hier, 30.0, heures=range(19, 20))                       # 20 heures : le seuil
        self.assertIn(hier, temperature_locale.moyennes_journalieres(self.client_, hier, hier))

    def test_une_heure_avec_un_seul_releve_ne_compte_pas(self):
        hier = self.aujourd_hui - timedelta(days=1)
        self.releves(hier, 30.0, heures=range(19))
        self.releves(hier, 30.0, heures=range(19, 24), par_heure=1)         # 5 heures à 1 relevé : isolés
        self.assertEqual(temperature_locale.moyennes_journalieres(self.client_, hier, hier), {})

    def test_chaque_heure_compte_autant_meme_avec_plus_de_releves(self):
        """12 h à 28 °C avec 60 relevés par heure, 12 h à 32 °C avec 6 : la journée vaut 30, pas 28,2."""
        hier = self.aujourd_hui - timedelta(days=1)
        self.releves(hier, 28.0, heures=range(12), par_heure=60)
        self.releves(hier, 32.0, heures=range(12, 24), par_heure=6)
        m = temperature_locale.moyennes_journalieres(self.client_, hier, hier)
        self.assertAlmostEqual(m[hier], 30.0, places=6)

    def test_les_releves_d_un_autre_client_ne_comptent_pas(self):
        hier = self.aujourd_hui - timedelta(days=1)
        autre = Dispositif.objects.create(client=creer_client("autre@test.ci"), apiKeyDevice="cle_autre_temp")
        self.releves(hier, 40.0, boitier=autre)
        self.assertEqual(temperature_locale.moyennes_journalieres(self.client_, hier, hier), {})

    def test_deux_boitiers_du_meme_client_se_moyennent(self):
        hier = self.aujourd_hui - timedelta(days=1)
        second = Dispositif.objects.create(client=self.client_, apiKeyDevice="cle_second")
        self.releves(hier, 28.0)
        self.releves(hier, 32.0, boitier=second)
        m = temperature_locale.moyennes_journalieres(self.client_, hier, hier)
        self.assertAlmostEqual(m[hier], 30.0, places=6)


class CalibrationTests(BaseTemperature):
    def _mesurer(self, n, ecart):
        for d in self.jours_passes(n):
            self.ville(d, 28.0)
            self.releves(d, 28.0 + ecart)
        for i in range(0, 5):
            self.ville(self.aujourd_hui + timedelta(days=i), 31.0, prevue=True)

    def test_sans_capteur_c_est_la_meteo_de_la_ville_sans_bruit(self):
        for d in self.jours_passes(5):
            self.ville(d, 28.0)
        temps, info = temperature_locale.temperatures(self.client_, self.aujourd_hui - timedelta(days=5),
                                                      self.aujourd_hui + timedelta(days=4))
        self.assertEqual(info["source"], "ville")
        self.assertEqual(info["jours_mesures"], 0)
        self.assertIsNone(info["raison"])
        self.assertEqual(temps[self.aujourd_hui - timedelta(days=1)], 28.0)

    def test_avant_7_jours_communs_la_prevision_garde_la_ville_telle_quelle(self):
        """Aucun mélange : le capteur lit 3 °C de plus ; 6 jours ne suffisent pas pour le savoir."""
        self._mesurer(6, ecart=3.0)
        debut = self.aujourd_hui - timedelta(days=6)
        temps, info = temperature_locale.temperatures(self.client_, debut, self.aujourd_hui + timedelta(days=4))
        self.assertEqual(info["source"], "ville")
        self.assertFalse(info["calibre"])
        self.assertEqual(info["raison"], "calibration")
        self.assertEqual(info["jours_mesures"], 6)
        self.assertEqual(info["jours_communs"], 6)
        for d, t in temps.items():                                           # chaque valeur est celle d'Open-Meteo
            self.assertEqual(t, float(MeteoJour.objects.get(ville="Abidjan", date=d).t_moy))

    def test_apres_7_jours_tout_est_sur_l_echelle_du_logement(self):
        self._mesurer(7, ecart=3.0)
        debut = self.aujourd_hui - timedelta(days=9)
        demain = self.aujourd_hui + timedelta(days=1)
        trou = self.aujourd_hui - timedelta(days=9)                          # un jour de ville sans relevé du capteur
        self.ville(trou, 26.0)
        temps, info = temperature_locale.temperatures(self.client_, debut, self.aujourd_hui + timedelta(days=4))
        self.assertEqual(info["source"], "capteur")
        self.assertTrue(info["calibre"])
        self.assertAlmostEqual(info["decalage_c"], 3.0, places=1)
        self.assertAlmostEqual(temps[self.aujourd_hui - timedelta(days=1)], 31.0, places=6)   # jour mesuré : le capteur
        self.assertAlmostEqual(temps[trou], 29.0, places=6)                  # sans relevé : ville 26 + écart 3
        self.assertAlmostEqual(temps[self.aujourd_hui], 34.0, places=6)      # aujourd'hui : ville 31 + écart 3
        self.assertAlmostEqual(temps[demain], 34.0, places=6)                # à venir : ville 31 + écart 3

    def test_l_ecart_est_la_mediane_pas_la_moyenne(self):
        """Une journée étrange (capteur au soleil : +9 °C) ne déplace pas l'écart habituel de +2 °C."""
        for i, d in enumerate(self.jours_passes(9)):
            self.ville(d, 28.0)
            self.releves(d, 28.0 + (9.0 if i == 4 else 2.0))
        _, info = temperature_locale.temperatures(self.client_, self.aujourd_hui - timedelta(days=9),
                                                  self.aujourd_hui + timedelta(days=2))
        self.assertAlmostEqual(info["decalage_c"], 2.0, places=1)

    def test_ecart_anormal_revient_a_la_ville_et_le_dit(self):
        self._mesurer(8, ecart=15.0)                                         # un capteur à 43 °C pour 28 °C dehors
        temps, info = temperature_locale.temperatures(self.client_, self.aujourd_hui - timedelta(days=8),
                                                      self.aujourd_hui + timedelta(days=4))
        self.assertEqual(info["source"], "ville")
        self.assertEqual(info["raison"], "ecart_anormal")
        self.assertAlmostEqual(info["decalage_c"], 15.0, places=1)
        self.assertEqual(temps[self.aujourd_hui - timedelta(days=1)], 28.0)

    def test_la_journee_en_cours_n_est_jamais_utilisee_comme_mesure(self):
        """Aujourd'hui n'est pas finie : sa moyenne (heures déjà passées) serait fausse."""
        self._mesurer(8, ecart=2.0)
        self.releves(self.aujourd_hui, 45.0)                                 # des relevés d'aujourd'hui, très chauds
        temps, info = temperature_locale.temperatures(self.client_, self.aujourd_hui - timedelta(days=8),
                                                      self.aujourd_hui + timedelta(days=2))
        self.assertAlmostEqual(temps[self.aujourd_hui], 33.0, places=6)      # ville 31 + écart 2, pas 45
        self.assertEqual(info["jours_mesures"], 8)

    def test_sans_meteo_de_la_ville_le_capteur_ne_peut_pas_se_calibrer(self):
        for d in self.jours_passes(8):
            self.releves(d, 30.0)
        temps, info = temperature_locale.temperatures(self.client_, self.aujourd_hui - timedelta(days=8),
                                                      self.aujourd_hui + timedelta(days=2))
        self.assertEqual(temps, {})
        self.assertEqual(info["source"], "ville")
        self.assertEqual(info["raison"], "calibration")


class ReleveActuelTests(BaseTemperature):
    def test_releve_recent(self):
        maintenant = timezone.now()
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=maintenant - timedelta(seconds=40),
                                     temperature_c=Decimal("30.0"), humidite_pct=Decimal("72.0"))
        r = temperature_locale.releve_actuel(self.client_, maintenant)
        self.assertEqual(r["temperature_c"], 30.0)
        self.assertEqual(r["humidite_pct"], 72.0)
        self.assertEqual(r["il_y_a_s"], 40)

    def test_releve_de_plus_de_15_minutes_n_est_pas_presente_comme_actuel(self):
        maintenant = timezone.now()
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=maintenant - timedelta(minutes=20),
                                     temperature_c=Decimal("30.0"))
        self.assertIsNone(temperature_locale.releve_actuel(self.client_, maintenant))

    def test_sans_releve_rien(self):
        self.assertIsNone(temperature_locale.releve_actuel(self.client_))

    def test_humidite_absente_reste_absente(self):
        maintenant = timezone.now()
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=maintenant, temperature_c=Decimal("30.0"))
        self.assertIsNone(temperature_locale.releve_actuel(self.client_, maintenant)["humidite_pct"])


class PrevisionAvecCapteurTests(BaseTemperature):
    """Trois semaines d'un climatiseur (6 kWh en semaine, 9 au repos, + 0,5 kWh par degré-jour) : la prévision se sert
    du capteur une fois calibré, et le dit dans l'API."""

    def setUp(self):
        super().setUp()
        self.clim = Capteur.objects.create(client=self.client_, dispositif=self.boitier, nom="Climatiseur")
        for i, d in enumerate(self.jours_passes(21)):
            t = 26.0 + (i % 4)
            self.ville(d, t)
            self.releves(d, t + 2.0)                                         # le capteur lit 2 °C de plus que la ville
            kwh = (9.0 if d.weekday() >= 5 else 6.0) + 0.5 * (t - 24.0 - 3.5)
            midi = timezone.make_aware(datetime.combine(d, time(12, 0)))
            MesureEnergie.objects.create(capteur=self.clim, puissance=Decimal("1000"), courant=Decimal("4.5"),
                                         energie=Decimal(str(round(kwh, 6))), timestamp=midi)
            PresenceCapteur.objects.bulk_create([PresenceCapteur(capteur=self.clim, heure=debut_du_jour(d) + timedelta(hours=h))
                                                 for h in range(24)])
        for i in range(0, 17):
            self.ville(self.aujourd_hui + timedelta(days=i), 31.0, prevue=True)

    def test_le_modele_utilise_le_capteur_une_fois_calibre(self):
        m = prevision_ia.construire(self.client_)
        self.assertEqual(m.source_temperature["source"], "capteur")
        self.assertAlmostEqual(m.source_temperature["decalage_c"], 2.0, places=1)
        demain = self.aujourd_hui + timedelta(days=1)
        self.assertAlmostEqual(m.temperatures[demain], 33.0, places=6)       # ville 31 + écart 2
        self.assertTrue(m.meteo_disponible)

    def test_l_effet_de_la_chaleur_reste_appris_avec_le_capteur(self):
        """Écart constant de 2 °C entre capteur et ville : la pente apprise (kWh par degré) est inchangée."""
        m = prevision_ia.construire(self.client_)
        self.assertAlmostEqual(m.capteurs[0].c_brute, 0.5, places=3)

    def test_l_api_dit_d_ou_vient_la_temperature(self):
        from .views import _prevision_fin_de_mois
        p = _prevision_fin_de_mois(self.client_)
        meteo = p["meteo"]
        self.assertEqual(meteo["source"], "capteur")
        self.assertAlmostEqual(meteo["decalage_c"], 2.0, places=1)
        self.assertEqual(meteo["jours_mesures"], 21)
        self.assertEqual(meteo["jours_pour_calibrer"], temperature_locale.JOURS_CALIBRATION_MIN)
        self.assertIsNone(meteo["raison_ville"])
        self.assertIsNone(meteo["ambiance"])                                 # aucun relevé des 15 dernières minutes
        self.assertEqual(p["methode"], "habitudes et température")

    def test_l_api_donne_l_air_de_maintenant_quand_le_capteur_envoie(self):
        from .views import _prevision_fin_de_mois
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=timezone.now() - timedelta(seconds=20),
                                     temperature_c=Decimal("31.0"), humidite_pct=Decimal("65.0"))
        p = _prevision_fin_de_mois(self.client_)
        self.assertEqual(p["meteo"]["ambiance"]["temperature_c"], 31.0)
        self.assertEqual(p["meteo"]["ambiance"]["humidite_pct"], 65.0)

    def test_des_releves_en_retard_relancent_le_calcul_du_cache(self):
        """Coupure Wi-Fi : le boîtier rejoue plus tard ses relevés d'avant-hier, alors que des relevés d'hier sont déjà
        arrivés. Le « plus récent » n'a pas changé, mais le modèle gardé en cache (une heure) doit se recalculer."""
        avant_hier = self.aujourd_hui - timedelta(days=2)
        trous = ReleveAmbiant.objects.filter(dispositif=self.boitier, instant__gte=debut_du_jour(avant_hier) + timedelta(hours=10),
                                             instant__lt=debut_du_jour(avant_hier + timedelta(days=1)))
        manquants = list(trous.values("instant", "temperature_c", "humidite_pct"))
        trous.delete()
        m1 = prevision_ia.modele_du_client(self.client_)
        self.assertEqual(m1.source_temperature["jours_mesures"], 20)         # avant-hier n'a que 10 heures
        ReleveAmbiant.objects.bulk_create([ReleveAmbiant(dispositif=self.boitier, **x) for x in manquants])
        m2 = prevision_ia.modele_du_client(self.client_)
        self.assertEqual(m2.source_temperature["jours_mesures"], 21)


class ApiPrevisionHttpTests(APITestCase):
    def test_la_reponse_http_porte_les_nouveaux_champs_meme_sans_capteur(self):
        c = creer_client("http@test.ci")
        self.client.force_authenticate(c)
        r = self.client.get("/api/analytics/prevision/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        if "meteo" in r.data:                                                # sans mesure, la prévision peut être vide
            self.assertEqual(r.data["meteo"]["source"], "ville")
            self.assertEqual(r.data["meteo"]["jours_mesures"], 0)
            self.assertIsNone(r.data["meteo"]["ambiance"])


class EtatAmbianceTests(BaseTemperature):
    """Ce que le tableau de bord montre du capteur, indépendamment de la prévision."""

    def test_sans_aucun_releve_rien_a_afficher(self):
        e = temperature_locale.etat(self.client_)
        self.assertEqual(e, {"capteur": False, "ambiance": None, "calibration": None})

    def test_releve_recent_et_calibration_en_cours(self):
        maintenant = timezone.now()
        for d in self.jours_passes(3):                                       # 3 jours complets : sur 7 requis
            self.ville(d, 28.0)
            self.releves(d, 30.0)
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=maintenant - timedelta(seconds=12),
                                     temperature_c=Decimal("31.3"), humidite_pct=Decimal("67.0"))
        e = temperature_locale.etat(self.client_, maintenant)
        self.assertTrue(e["capteur"])
        self.assertEqual(e["ambiance"], {"temperature_c": 31.3, "humidite_pct": 67.0, "il_y_a_s": 12})
        self.assertEqual(e["calibration"]["source"], "ville")                # pas encore calibré : météo seule
        self.assertEqual(e["calibration"]["raison"], "calibration")
        self.assertEqual(e["calibration"]["jours_communs"], 3)
        self.assertEqual(e["calibration"]["jours_pour_calibrer"], 7)

    def test_capteur_deja_vu_mais_muet_depuis_plus_de_15_minutes(self):
        """Pas de valeur périmée présentée comme actuelle, mais le tableau de bord sait qu'un capteur existe."""
        maintenant = timezone.now()
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=maintenant - timedelta(hours=2),
                                     temperature_c=Decimal("30.0"))
        e = temperature_locale.etat(self.client_, maintenant)
        self.assertTrue(e["capteur"])
        self.assertIsNone(e["ambiance"])

    def test_calibre_apres_7_jours(self):
        for d in self.jours_passes(8):
            self.ville(d, 28.0)
            self.releves(d, 30.0)
        e = temperature_locale.etat(self.client_)
        self.assertEqual(e["calibration"]["source"], "capteur")
        self.assertAlmostEqual(e["calibration"]["decalage_c"], 2.0, places=1)


class ApiAmbianceTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.proprietaire = creer_client("api-ambiance@test.ci")
        self.boitier = Dispositif.objects.create(client=self.proprietaire, apiKeyDevice="cle_api_ambiance")

    def test_authentification_obligatoire(self):
        r = self.client.get("/api/analytics/ambiance/")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_un_client_sans_capteur_de_temperature(self):
        self.client.force_authenticate(self.proprietaire)
        r = self.client.get("/api/analytics/ambiance/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, {"capteur": False, "ambiance": None, "calibration": None})

    def test_un_client_avec_un_releve_recent(self):
        ReleveAmbiant.objects.create(dispositif=self.boitier, instant=timezone.now() - timedelta(seconds=5),
                                     temperature_c=Decimal("31.3"), humidite_pct=Decimal("67.0"))
        self.client.force_authenticate(self.proprietaire)
        r = self.client.get("/api/analytics/ambiance/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["capteur"])
        self.assertEqual(r.data["ambiance"]["temperature_c"], 31.3)
        self.assertEqual(r.data["calibration"]["source"], "ville")

    def test_un_client_ne_voit_jamais_les_releves_d_un_autre(self):
        autre = creer_client("autre-ambiance@test.ci")
        autre_boitier = Dispositif.objects.create(client=autre, apiKeyDevice="cle_autre_ambiance")
        ReleveAmbiant.objects.create(dispositif=autre_boitier, instant=timezone.now(),
                                     temperature_c=Decimal("40.0"), humidite_pct=Decimal("30.0"))
        self.client.force_authenticate(self.proprietaire)
        r = self.client.get("/api/analytics/ambiance/")
        self.assertEqual(r.data, {"capteur": False, "ambiance": None, "calibration": None})

    def test_reserve_aux_clients(self):
        from apps.accounts.models import Technicien
        tech = Technicien(email="tech-ambiance@test.ci", nom="Tech", role="technicien", matricule="T-AMB")
        tech.set_password("Password123!")
        tech.save()
        self.client.force_authenticate(tech)
        r = self.client.get("/api/analytics/ambiance/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
