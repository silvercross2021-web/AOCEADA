"""Prévision : habitudes du foyer et température (note technique 4.1 et 4.2 ; 19/10/2026).

Rejoue les exemples chiffrés de la note (ventilateur ; crédit qui finit dimanche vers 13 h), puis vérifie sur la base :
apprentissage des niveaux semaine / repos et de l'effet de la chaleur, journées incomplètes jamais prises pour une
consommation nulle, jours fériés, météo (simulée : aucun test ne va sur Internet), recalage sur l'écran du compteur,
présence des capteurs enregistrée même quand l'appareil est éteint."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from apps.sensors.models import Capteur, Dispositif, MesureEnergie, PresenceCapteur

from . import meteo, prevision_ia
from .jours_feries import feries, paques, type_jour
from .models import MeteoJour, RechargeCredit
from .prevision_ia import ModeleCapteur, ModeleFoyer


def creer_client(email="prev@test.ci", **champs):
    c = Client(email=email, nom="Client prévision", role="client", **champs)
    c.set_password("Password123!")
    c.save()
    return c


class JoursFeriesTests(TestCase):
    def test_paques_et_fetes_qui_en_dependent(self):
        self.assertEqual(paques(2026), date(2026, 4, 5))
        self.assertEqual(paques(2027), date(2027, 3, 28))
        f = feries(2026)
        for d in (date(2026, 4, 6), date(2026, 5, 14), date(2026, 5, 25),      # lundi de Pâques, Ascension, Pentecôte
                  date(2026, 8, 7), date(2026, 11, 15), date(2026, 5, 27)):    # Indépendance, Paix, Tabaski
            self.assertIn(d, f)

    def test_type_de_jour(self):
        self.assertEqual(type_jour(date(2026, 10, 20)), "semaine")            # mardi
        self.assertEqual(type_jour(date(2026, 10, 24)), "repos")              # samedi
        self.assertEqual(type_jour(date(2026, 8, 7)), "repos")                # vendredi, fête de l'Indépendance


class FormulesDeLaNoteTests(TestCase):
    def test_degres_jour_et_valeurs_a_priori(self):
        self.assertEqual(prevision_ia.degres_jour(29), 5.0)
        self.assertEqual(prevision_ia.degres_jour(22), 0.0)                   # sous 24 °C : pas de besoin de froid
        self.assertIsNone(prevision_ia.degres_jour(None))
        self.assertEqual(prevision_ia.c_a_priori("Climatiseur du salon"), 0.6)
        self.assertEqual(prevision_ia.c_a_priori("Capteur 1 - Lampe"), 0.0)

    def test_exemple_du_ventilateur_page_6(self):
        """Niveau 0,40 kWh en semaine à 29 °C (5 degrés-jours), 0,04 kWh de plus par degré. Mardi 32 °C : prévu 0,52,
        mesuré 0,60 → niveau 0,40 + 0,3 × 0,08 = 0,424. La note garde la température habituelle fixe ; ici elle
        bouge lentement (5 % par jour) : mercredi et jeudi restent au centième près de la note."""
        m = ModeleCapteur(1, "Ventilateur", 0.04, niveaux={"semaine": 0.40}, vus={"semaine": 30}, c=0.04,
                          habituel=5.0, n_habituel=100)
        mardi, mercredi, jeudi = date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)
        self.assertAlmostEqual(m.predire(mardi, 8.0), 0.52, places=6)
        m.apprendre(mardi, 8.0, 0.60)
        self.assertAlmostEqual(m.niveaux["semaine"], 0.424, places=6)
        self.assertAlmostEqual(m.predire(mercredi, 6.0), 0.46, delta=0.01)
        m.apprendre(mercredi, 6.0, 0.50)
        self.assertAlmostEqual(m.niveaux["semaine"], 0.43, delta=0.01)
        self.assertAlmostEqual(m.predire(jeudi, 7.0), 0.51, delta=0.01)

    def test_le_niveau_ne_se_corrige_que_de_l_ecart_que_la_chaleur_n_explique_pas(self):
        m = ModeleCapteur(1, "Climatiseur", 0.6, niveaux={"semaine": 5.0}, vus={"semaine": 30}, c=0.6,
                          habituel=3.0, n_habituel=100)
        jour = date(2026, 10, 20)
        m.apprendre(jour, 6.0, 5.0 + 0.6 * 3)        # journée plus chaude, exactement expliquée par la chaleur
        self.assertAlmostEqual(m.niveaux["semaine"], 5.0, places=6)

    def test_premieres_journees_moyenne_puis_lissage(self):
        m = ModeleCapteur(1, "Prise", 0.0)
        for i, y in enumerate((1.0, 3.0, 2.0)):
            m.apprendre(date(2026, 10, 19) + timedelta(days=i), None, y)
        self.assertAlmostEqual(m.niveaux["semaine"], 2.0, places=6)          # moyenne des trois 1res journées
        m.apprendre(date(2026, 10, 22), None, 12.0)                         # puis 0,3 : un jour étrange pèse peu
        self.assertAlmostEqual(m.niveaux["semaine"], 2.0 + 0.3 * 10.0, places=6)

    def test_effet_de_la_chaleur_appris_par_paires_et_jamais_negatif(self):
        jours = [date(2026, 9, 1) + timedelta(days=i) for i in range(28)]
        semaine = [d for d in jours if type_jour(d) == "semaine"]
        obs = [(d, "semaine", 2.0 + (i % 5), 3.0 + 0.5 * (2.0 + (i % 5))) for i, d in enumerate(semaine)]
        c, brute = prevision_ia.pente_chaleur(obs, 0.6)
        self.assertAlmostEqual(brute, 0.5, places=6)
        self.assertTrue(0.5 < c < 0.6)                                       # rapprochée de l'a priori du climatiseur
        inverse = [(d, t, x, 10 - y) for d, t, x, y in obs]
        self.assertEqual(prevision_ia.pente_chaleur(inverse, 0.0)[0], 0.0)

    def test_exemple_du_credit_page_6_dimanche_vers_13_h(self):
        """Il reste 20 kWh vendredi soir. Week-end : 12 kWh par jour, 2 degrés de plus que d'habitude, 0,5 kWh par
        degré → 13 kWh par jour. Samedi soir : 7 kWh ; dimanche, 7 / 13 de la journée : vers 13 h."""
        cap = ModeleCapteur(1, "Foyer", 0.5, niveaux={"repos": 12.0, "semaine": 10.0}, c=0.5, habituel=4.0)
        samedi = date(2026, 10, 24)
        temps = {samedi: 30.0, samedi + timedelta(days=1): 30.0, samedi + timedelta(days=2): 28.0}
        m = ModeleFoyer(capteurs=[cap], temperatures=temps, jours_complets=30, sigma=0.5, n_residus=20,
                        profil=[1 / 24] * 24, jours_profil=30, couverture={}, activation={1: date(2026, 9, 1)},
                        meteo_disponible=True)
        self.assertAlmostEqual(m.jour(samedi), 13.0, places=6)
        vendredi_soir = timezone.make_aware(datetime.combine(samedi, time(0, 0)))
        fin = prevision_ia.epuisement(m, 20.0, vendredi_soir)
        self.assertEqual(fin.date(), samedi + timedelta(days=1))
        self.assertEqual(round(fin.hour + fin.minute / 60), 13)
        sans_chaleur = ModeleFoyer(**{**m.__dict__, "temperatures": {}})
        fin_sans = prevision_ia.epuisement(sans_chaleur, 20.0, vendredi_soir)
        self.assertEqual(fin_sans.hour, 16)                                  # « sans la température : 16 h »
        self.assertLess(prevision_ia.epuisement(m, 20.0, vendredi_soir, ecarts=1.28), fin)   # fourchette


class ModeleSurLaBaseTests(TestCase):
    """Trois semaines d'un climatiseur : 6 kWh en semaine, 9 kWh au repos, + 0,5 kWh par degré-jour."""

    def setUp(self):
        cache.clear()
        self.client_ = creer_client()
        self.clim = Capteur.objects.create(client=self.client_, nom="Climatiseur")
        self.aujourd_hui = timezone.localdate()
        self.jours = [self.aujourd_hui - timedelta(days=i) for i in range(21, 0, -1)]
        for i, d in enumerate(self.jours):
            t = 26.0 + (i % 4)                                                # 2 à 5 degrés-jours
            MeteoJour.objects.create(ville="Abidjan", date=d, t_moy=Decimal(str(t)))
            y = (9.0 if type_jour(d) == "repos" else 6.0) + 0.5 * (t - 24.0 - 3.5)
            self._journee(d, y)
        for i in range(0, 17):
            MeteoJour.objects.create(ville="Abidjan", date=self.aujourd_hui + timedelta(days=i), t_moy=Decimal("31.0"),
                                     prevue=True)

    def _journee(self, d, kwh, heures=24):
        midi = timezone.make_aware(datetime.combine(d, time(12, 0)))
        MesureEnergie.objects.create(capteur=self.clim, puissance=Decimal("1000"), courant=Decimal("4.5"),
                                     energie=Decimal(str(round(kwh, 6))), timestamp=midi)
        debut = timezone.make_aware(datetime.combine(d, time(0, 0)))
        PresenceCapteur.objects.bulk_create([PresenceCapteur(capteur=self.clim, heure=debut + timedelta(hours=h))
                                             for h in range(heures)])

    def test_niveaux_semaine_et_repos_et_chaleur_apprise(self):
        m = prevision_ia.construire(self.client_)
        cap = m.capteurs[0]
        self.assertEqual(m.jours_complets, 21)
        self.assertAlmostEqual(cap.niveaux["semaine"], 6.0, delta=0.15)
        self.assertAlmostEqual(cap.niveaux["repos"], 9.0, delta=0.15)
        self.assertIsNotNone(cap.c_brute)
        self.assertAlmostEqual(cap.c_brute, 0.5, places=3)
        self.assertGreater(cap.c, 0.5)                                       # rapprochée de 0,6 (a priori du climatiseur)
        self.assertGreater(m.jour(self.aujourd_hui + timedelta(days=1)),     # 31 °C annoncés : plus que d'habitude
                           cap.niveaux[type_jour(self.aujourd_hui + timedelta(days=1))])
        # erreurs de la veille presque nulles : l'écart-type est le plancher, 10 % d'une journée moyenne
        self.assertGreaterEqual(m.n_residus, 15)
        self.assertAlmostEqual(m.sigma, 0.1 * 7.0, delta=0.1)

    def test_une_journee_incomplete_n_est_jamais_une_consommation_nulle(self):
        trou = self.aujourd_hui - timedelta(days=22)
        MeteoJour.objects.create(ville="Abidjan", date=trou, t_moy=Decimal("27"))
        self._journee(trou, 0.2, heures=2)                                   # deux heures de mesure seulement
        m = prevision_ia.construire(self.client_)
        self.assertEqual(m.jours_complets, 21)                               # la journée de 2 h ne compte pas
        self.assertAlmostEqual(m.capteurs[0].niveaux["semaine"], 6.0, delta=0.15)

    def test_prevision_de_facture_prend_la_chaleur_annoncee(self):
        from .views import _prevision_fin_de_mois
        p = _prevision_fin_de_mois(self.client_)
        self.assertIn(p["mode"], ("band", "band_large"))
        self.assertEqual(p["k"], 21)
        self.assertLessEqual(p["bill_low"], p["bill_central"])
        self.assertLessEqual(p["bill_central"], p["bill_high"])
        self.assertGreaterEqual(p["bill_low"], p["cost_to_date"])
        self.assertTrue(p["meteo"]["disponible"])
        self.assertEqual(p["meteo"]["t_prevue"], 31.0)
        self.assertGreater(p["meteo"]["effet_chaleur_kwh"], 0)
        self.assertEqual(p["par_capteur"][0]["nom"], "Climatiseur")
        self.assertEqual(len(p["prochains_jours"]), 7)

    def test_sans_meteo_la_prevision_le_dit(self):
        MeteoJour.objects.all().delete()
        from .views import _prevision_fin_de_mois
        p = _prevision_fin_de_mois(self.client_)
        self.assertFalse(p["meteo"]["disponible"])
        self.assertEqual(p["methode"], "habitudes (météo indisponible)")

    def test_credit_prepaye_date_de_fin(self):
        from apps.alerts.utils import credit_prepaye_info
        self.client_.typeCompteur = "prepaye"
        self.client_.creditPrepaye_FCFA = Decimal("3000")                  # une trentaine de kWh : quelques jours
        self.client_.save()
        info = credit_prepaye_info(self.client_)
        self.assertLess(info["jours_restants"], 8)
        self.assertIsNotNone(info["fin_estimee"])
        self.assertLessEqual(info["fin_tot"], info["fin_estimee"])
        self.assertGreaterEqual(info["fin_tard"], info["fin_estimee"])
        self.assertTrue(info["heure_fiable"])                                # 21 journées de profil
        jours = (info["fin_estimee"] - timezone.localtime()).total_seconds() / 86400
        self.assertAlmostEqual(info["jours_restants"], int(jours), delta=1)
        self.client_.creditPrepaye_FCFA = Decimal("200000")                # plus de deux mois : pas de date, des jours
        self.client_.save()
        loin = credit_prepaye_info(self.client_)
        self.assertIsNone(loin["fin_estimee"])
        self.assertGreater(loin["jours_restants"], 60)


class MeteoTests(TestCase):
    def test_tests_jamais_sur_internet(self):
        with patch.object(meteo, "_telecharger", side_effect=AssertionError("Internet appelé")):
            self.assertFalse(meteo.rafraichir("Abidjan", forcer=True))

    @override_settings(METEO_EN_LIGNE=True)
    def test_lecture_open_meteo_gardee_en_base(self):
        demain = timezone.localdate() + timedelta(days=1)
        lignes = [((demain - timedelta(days=2)).isoformat(), 27.4, 31.0), (demain.isoformat(), 29.1, 33.2),
                  ((demain + timedelta(days=1)).isoformat(), None, None)]
        with patch.object(meteo, "_telecharger", return_value=lignes):
            self.assertTrue(meteo.rafraichir("Bouaké", forcer=True))
        t = meteo.temperatures("Bouaké", demain - timedelta(days=5), demain + timedelta(days=5))
        self.assertEqual(t, {demain - timedelta(days=2): 27.4, demain: 29.1})
        self.assertTrue(MeteoJour.objects.get(ville="Bouaké", date=demain).prevue)
        with patch.object(meteo, "_telecharger", side_effect=OSError("panne")):
            self.assertFalse(meteo.rafraichir("Bouaké", forcer=True))       # panne : on garde ce qu'on a
        self.assertEqual(MeteoJour.objects.filter(ville="Bouaké").count(), 2)

    def test_ville_inconnue_abidjan(self):
        self.assertEqual(meteo.ville_du_client(Client(ville="Atlantis")), "Abidjan")


class ReleveCompteurTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.c = creer_client(email="releve@test.ci", typeCompteur="prepaye", amperage=10,
                              creditPrepaye_FCFA=Decimal("10000"))
        self.capteur = Capteur.objects.create(client=self.c, nom="Prise")
        self.client.force_authenticate(user=self.c)

    def test_recalage_puis_recharge_puis_annulation(self):
        from .tarifs_cie import prix_kwh_tout_compris
        prix = prix_kwh_tout_compris(self.c)
        r = self.client.post("/api/analytics/credit/releve/", {"kwh": "40,5"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cr = r.data["credit_prepaye"]
        self.assertEqual(cr["source"], "releve")
        self.assertAlmostEqual(cr["restant_kwh"], 40.5, places=2)
        self.assertAlmostEqual(cr["restant_fcfa"], float(Decimal("40.5") * prix), delta=0.02)
        MesureEnergie.objects.create(capteur=self.capteur, puissance=Decimal("500"), courant=Decimal("2.3"),
                                     energie=Decimal("0.5"), timestamp=timezone.now() + timedelta(seconds=1))
        RechargeCredit.objects.create(client=self.c, montant_FCFA=prix * 10)
        r = self.client.post("/api/analytics/credit/releve/", {"annuler": True}, format="json")
        self.assertEqual(r.data["credit_prepaye"]["source"], "recharges")
        self.c.refresh_from_db()
        self.assertIsNone(self.c.creditReleve_kWh)

    def test_recharges_et_mesures_apres_la_lecture(self):
        from apps.alerts.utils import credit_prepaye_info
        from .tarifs_cie import prix_kwh_tout_compris
        prix = prix_kwh_tout_compris(self.c)
        self.c.creditReleve_kWh, self.c.creditReleveLe = Decimal("20"), timezone.now() - timedelta(hours=3)
        self.c.save()
        MesureEnergie.objects.create(capteur=self.capteur, puissance=Decimal("500"), courant=Decimal("2.3"),
                                     energie=Decimal("2"), timestamp=timezone.now() - timedelta(hours=1))
        MesureEnergie.objects.create(capteur=self.capteur, puissance=Decimal("500"), courant=Decimal("2.3"),
                                     energie=Decimal("50"), timestamp=timezone.now() - timedelta(hours=5))  # avant
        RechargeCredit.objects.create(client=self.c, montant_FCFA=prix * 10)
        self.assertAlmostEqual(credit_prepaye_info(self.c)["restant_kwh"], 20 + 10 - 2, places=1)

    def test_valeurs_refusees(self):
        for v in ("abc", "-3", "999999"):
            r = self.client.post("/api/analytics/credit/releve/", {"kwh": v}, format="json")
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, v)
        postpaye = creer_client(email="post@test.ci")
        self.client.force_authenticate(user=postpaye)
        r = self.client.post("/api/analytics/credit/releve/", {"kwh": "10"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class PresenceDuBoitierTests(APITestCase):
    def test_presence_enregistree_meme_appareil_eteint(self):
        c = creer_client(email="presence@test.ci")
        d = Dispositif.objects.create(client=c, apiKeyDevice="cle_presence_test")
        cap = Capteur.objects.create(client=c, dispositif=d, nom="Lampe")
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_presence_test")
        for _ in range(3):                                                   # trois trames dans la même heure
            r = self.client.post("/api/sensors/zmct/", {"capteur_index": cap.indexDispositif or 1, "etat": "OFF",
                                                        "courant": 0, "puissance": 0}, format="json")
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertFalse(MesureEnergie.objects.filter(capteur=cap).exists())   # éteint : aucune consommation
        self.assertEqual(PresenceCapteur.objects.filter(capteur=cap).count(), 1)
