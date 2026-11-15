"""Tests du moteur de détection d'anomalies par règles configurables
(mémoire §6.4.1 : dépassement de seuil, consommation nocturne)."""
from decimal import Decimal
from datetime import time, timedelta
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import Client
from apps.sensors.models import Capteur, MesureEnergie
from .models import RegleDetection, Alerte
from .utils import evaluate_measurements


def creer_client(email="client@test.ci"):
    client = Client(email=email, nom="Client Test", role='client')
    client.set_password("Password123!")
    client.save()
    return client


class MoteurDetectionTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(
            client=self.un_client, nom="Capteur Salon", valeurMax=Decimal("2000.00"))
        self.regle = RegleDetection.objects.create(
            client=self.un_client, capteur=self.capteur,
            puissanceMax_W=Decimal("2000.00"),
            surveilleNuit=True, heureDébutNuit=time(0, 0), heureFinNuit=time(5, 0))

    def _mesure(self, puissance, timestamp=None):
        return MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal(str(puissance)),
            courant=Decimal(str(round(puissance / 220.0, 3))),
            energie=Decimal(str(round(puissance / 1000.0, 4))),
            timestamp=timestamp or timezone.now())

    def test_depassement_seuil_genere_alerte_critique(self):
        self._mesure(2340)  # > 2000 W
        evaluate_measurements(self.un_client, {self.capteur.id})
        alerte = Alerte.objects.filter(client=self.un_client, type='DEPASSEMENT_SEUIL').first()
        self.assertIsNotNone(alerte)
        self.assertEqual(alerte.sévérité, 'Critique')

    def test_puissance_normale_aucune_alerte(self):
        # Heure fixée à 14h pour rester hors de la fenêtre nocturne (00h-05h)
        apres_midi = timezone.now().replace(hour=14, minute=0)
        self._mesure(450, timestamp=apres_midi)
        evaluate_measurements(self.un_client, {self.capteur.id})
        self.assertEqual(Alerte.objects.filter(client=self.un_client).count(), 0)

    def test_pas_de_doublon_d_alerte_pour_la_meme_mesure(self):
        self._mesure(2340)
        evaluate_measurements(self.un_client, {self.capteur.id})
        evaluate_measurements(self.un_client, {self.capteur.id})
        self.assertEqual(
            Alerte.objects.filter(client=self.un_client, type='DEPASSEMENT_SEUIL').count(), 1)

    def test_consommation_nocturne_detectee(self):
        nuit = timezone.now().replace(hour=2, minute=30)
        self._mesure(250, timestamp=nuit)  # > seuil veille (10 % de 2000 W = 200 W) pendant 00h-05h
        evaluate_measurements(self.un_client, {self.capteur.id})
        self.assertTrue(
            Alerte.objects.filter(client=self.un_client, type='CONSOMMATION_NOCTURNE').exists())


class AlerteAPITests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.alerte = Alerte.objects.create(
            client=self.un_client, type='DEPASSEMENT_SEUIL',
            message="2 340 W détectés.", sévérité='Critique')

    def test_liste_des_alertes_du_client(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/alertes/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(data), 1)

    def test_marquer_alerte_comme_lue(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.patch(f'/api/alertes/{self.alerte.id}/lire/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alerte.refresh_from_db()
        self.assertTrue(self.alerte.lue)

    def test_client_ne_voit_pas_les_alertes_des_autres(self):
        autre = creer_client(email="autre@test.ci")
        self.client.force_authenticate(user=autre)
        response = self.client.get('/api/alertes/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(data), 0)

    def test_creation_regle_de_detection(self):
        capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Chambre")
        self.client.force_authenticate(user=self.un_client)
        response = self.client.post('/api/regles/', {
            "capteur": str(capteur.id), "puissanceMax_W": "1500.00",
            "surveilleNuit": True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RegleDetection.objects.filter(client=self.un_client).count(), 1)


class RegleIDORTests(APITestCase):
    """Un client ne peut pas créer une règle sur le capteur d'un autre (IDOR)."""

    def test_creation_regle_capteur_autrui_refusee(self):
        client_a = creer_client(email="a@test.ci")
        client_b = creer_client(email="b@test.ci")
        capteur_b = Capteur.objects.create(client=client_b, nom="Capteur B")
        self.client.force_authenticate(user=client_a)
        response = self.client.post('/api/regles/', {
            "capteur": str(capteur_b.id), "puissanceMax_W": 1500, "surveilleNuit": False,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RegleDetection.objects.filter(capteur=capteur_b).exists())

    def test_creation_regle_par_non_client_refusee(self):
        from apps.accounts.models import Technicien
        tech = Technicien(email="t@test.ci", nom="Tech", role='technicien', matricule="T-1")
        tech.set_password("Password123!"); tech.save()
        client_x = creer_client(email="x@test.ci")
        capteur = Capteur.objects.create(client=client_x, nom="Cap")
        self.client.force_authenticate(user=tech)
        response = self.client.post('/api/regles/', {"capteur": str(capteur.id), "puissanceMax_W": 1500})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CreditPrepayeTests(APITestCase):
    """Alerte « Crédit bas » pour les compteurs prépayés uniquement."""

    def test_credit_bas_genere_alerte_pour_prepaye(self):
        from .utils import check_credit_prepaye
        client = creer_client(email="prepaye@test.ci")
        client.typeCompteur = 'prepaye'
        client.creditPrepaye_FCFA = Decimal('5000')  # < seuil 10 000
        client.save()
        check_credit_prepaye(client)
        self.assertEqual(Alerte.objects.filter(client=client, type='CREDIT_BAS').count(), 1)
        # Déduplication : pas de second déclenchement le même jour
        check_credit_prepaye(client)
        self.assertEqual(Alerte.objects.filter(client=client, type='CREDIT_BAS').count(), 1)

    def test_pas_d_alerte_credit_pour_postpaye(self):
        from .utils import check_credit_prepaye
        client = creer_client(email="postpaye@test.ci")  # postpayé par défaut
        check_credit_prepaye(client)
        self.assertEqual(Alerte.objects.filter(client=client, type='CREDIT_BAS').count(), 0)

    def test_credit_restant_ne_se_reinitialise_pas_au_nouveau_mois(self):
        """Un compteur prépayé ne se recharge JAMAIS tout seul : la consommation
        d'un mois clos doit rester déduite du crédit même après le passage au
        mois suivant (régression du bug où seule la conso du mois EN COURS
        était soustraite, faisant « remonter » le crédit chaque 1er du mois)."""
        from .utils import credit_prepaye_info
        client = creer_client(email="cross-mois@test.ci")
        client.typeCompteur = 'prepaye'
        client.creditPrepaye_FCFA = Decimal('20000')  # recharge unique, jamais renouvelée
        client.save()
        # Mois précédent déjà clos : 190 kWh mesurés (× 100,52 F en prépayé 10A ≈ 19 099 F).
        capteur = Capteur.objects.create(client=client, nom="Cap")
        mois_precedent = timezone.now().replace(day=1) - timedelta(days=3)
        MesureEnergie.objects.create(capteur=capteur, puissance=Decimal('500'), courant=Decimal('2.3'),
                                     energie=Decimal('190'), timestamp=mois_precedent)
        info = credit_prepaye_info(client)
        # Il ne reste RÉELLEMENT qu'environ 900 FCFA, pas 20 000.
        self.assertEqual(info['restant_fcfa'], Decimal('20000') - Decimal('19098.80'))


class SeuilsReglablesTests(APITestCase):
    """Seuils utilisables avec de petits appareils (lampe, chargeur) et seuil de nuit
    choisi par le client (14/10/2026)."""

    def setUp(self):
        self.un_client = creer_client(email="seuils@test.ci")
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Lampe")

    def _mesure(self, puissance, quand):
        return MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal(str(puissance)), courant=Decimal('0.2'),
            energie=Decimal('0.0001'), timestamp=quand)

    def test_seuil_de_puissance_de_5_w_accepte_et_4_w_refuse(self):
        self.client.force_authenticate(user=self.un_client)
        ok = self.client.post('/api/regles/', {"capteur": str(self.capteur.id), "puissanceMax_W": 5})
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED)
        refus = self.client.post('/api/regles/', {"capteur": str(self.capteur.id), "puissanceMax_W": 4})
        self.assertEqual(refus.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lampe_de_45_w_au_dessus_d_un_seuil_de_30_w(self):
        RegleDetection.objects.create(client=self.un_client, capteur=self.capteur,
                                      puissanceMax_W=Decimal('30'), surveilleNuit=False)
        m = self._mesure(45, timezone.now().replace(hour=14))
        evaluate_measurements(self.un_client, {self.capteur.id}, mesures=[m])
        self.assertTrue(Alerte.objects.filter(client=self.un_client, type='DEPASSEMENT_SEUIL').exists())

    def test_seuil_de_nuit_choisi_par_le_client(self):
        """Lampe de 45 W la nuit : rien avec le seuil automatique (50 W), une alerte avec 10 W."""
        regle = RegleDetection.objects.create(
            client=self.un_client, capteur=self.capteur, puissanceMax_W=Decimal('500'),
            surveilleNuit=True, heureDébutNuit=time(0, 0), heureFinNuit=time(5, 0))
        nuit = timezone.localtime().replace(hour=2, minute=0)
        m = self._mesure(45, nuit)
        evaluate_measurements(self.un_client, {self.capteur.id}, mesures=[m])
        self.assertFalse(Alerte.objects.filter(type='CONSOMMATION_NOCTURNE').exists())
        regle.seuilNuit_W = Decimal('10')
        regle.save()
        evaluate_measurements(self.un_client, {self.capteur.id}, mesures=[m])
        self.assertTrue(Alerte.objects.filter(type='CONSOMMATION_NOCTURNE').exists())

    def test_seuil_de_nuit_automatique_si_puissance_desactivee(self):
        """Alerte de puissance désactivée (100 000 W) : la nuit reste à 50 W, pas 10 000 W."""
        from .utils import seuil_nuit
        regle = RegleDetection.objects.create(client=self.un_client, capteur=self.capteur,
                                              puissanceMax_W=Decimal('100000'), surveilleNuit=True)
        self.assertEqual(seuil_nuit(regle), Decimal('50'))
        regle.puissanceMax_W = Decimal('2000')
        self.assertEqual(seuil_nuit(regle), Decimal('200'))

    def test_puissance_actuelle_exposee_pour_regler_une_alerte(self):
        self.capteur.etatCourant = 'ON'
        self.capteur.save()
        self._mesure(45.4, timezone.now())
        self.client.force_authenticate(user=self.un_client)
        data = self.client.get('/api/sensors/').data
        liste = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(liste[0]['puissanceActuelle'], 45)


class AlerteTrancheTests(APITestCase):
    """Alerte de tranche postpayée (arrêté n° 1355 : seuil par BIMESTRE)."""

    def setUp(self):
        self.un_client = creer_client(email="tranche@test.ci")
        self.un_client.amperage = 5
        self.un_client.typeTarif = 'social'       # seuil : 80 kWh par bimestre
        self.un_client.save()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Frigo")

    def _kwh(self, kwh, quand=None):
        MesureEnergie.objects.create(capteur=self.capteur, puissance=Decimal('100'), courant=Decimal('0.5'),
                                     energie=Decimal(str(kwh)), timestamp=quand or timezone.now())

    def test_rien_loin_du_seuil(self):
        from .utils import check_tranche_postpaye
        self._kwh(20)
        check_tranche_postpaye(self.un_client, forcer=True)
        self.assertFalse(Alerte.objects.filter(client=self.un_client, type__startswith='TRANCHE').exists())

    def test_approche_a_90_pour_cent_puis_franchie_une_fois_par_bimestre(self):
        from .utils import check_tranche_postpaye
        self._kwh(73)                                 # 91 % de 80 kWh
        check_tranche_postpaye(self.un_client, forcer=True)
        check_tranche_postpaye(self.un_client, forcer=True)
        approche = Alerte.objects.filter(client=self.un_client, type='TRANCHE_APPROCHE')
        self.assertEqual(approche.count(), 1)
        self.assertEqual(approche.first().sévérité, 'Avertissement')   # social : kWh deux fois plus cher
        self.assertIn('65,11', approche.first().message)
        self._kwh(10)                                 # 83 kWh : tranche 2
        check_tranche_postpaye(self.un_client, forcer=True)
        check_tranche_postpaye(self.un_client, forcer=True)
        self.assertEqual(Alerte.objects.filter(client=self.un_client, type='TRANCHE_FRANCHIE').count(), 1)

    def test_tarif_general_simple_information(self):
        from .utils import check_tranche_postpaye
        self.un_client.amperage = 10
        self.un_client.typeTarif = 'general'          # seuil : 396 kWh par bimestre
        self.un_client.save()
        self._kwh(400)
        check_tranche_postpaye(self.un_client, forcer=True)
        alerte = Alerte.objects.get(client=self.un_client, type='TRANCHE_FRANCHIE')
        self.assertEqual(alerte.sévérité, 'Info')     # au général, la tranche 2 est moins chère

    def test_aucune_tranche_en_prepaye(self):
        from .utils import check_tranche_postpaye
        self.un_client.typeCompteur = 'prepaye'
        self.un_client.save()
        self._kwh(500)
        check_tranche_postpaye(self.un_client, forcer=True)
        self.assertFalse(Alerte.objects.filter(client=self.un_client, type__startswith='TRANCHE').exists())
        self.client.force_authenticate(user=self.un_client)
        self.assertEqual(self.client.get('/api/alertes/tranche/').data, {"applicable": False})

    def test_etat_de_tranche_pour_la_page_alertes(self):
        self._kwh(40)
        self.client.force_authenticate(user=self.un_client)
        d = self.client.get('/api/alertes/tranche/').data
        self.assertTrue(d['applicable'])
        self.assertEqual(d['seuil_kwh'], 80.0)
        self.assertEqual(d['kwh'], 40.0)
        self.assertEqual(d['prix_t2'], 65.11)


class AlerteFcfaEtGlobaleTests(APITestCase):
    """Alertes en Francs CFA (simple) ou en Watts (expert), par appareil ou globales (tous les appareils combinés)."""

    def setUp(self):
        self.un_client = creer_client(email="fcfa_global@test.ci")
        self.cap1 = Capteur.objects.create(client=self.un_client, nom="Capteur 1 - ampoule", etatCourant='ON')
        self.cap2 = Capteur.objects.create(client=self.un_client, nom="Capteur 2 - climatiseur", etatCourant='ON')

    def test_creation_regle_en_fcfa_par_appareil_et_declenchement(self):
        self.client.force_authenticate(user=self.un_client)
        rep = self.client.post('/api/regles/', {
            "nom": "Budget Climatiseur",
            "capteur": str(self.cap2.id),
            "seuilMontant_FCFA": 10000,
            "puissanceMax_W": 100000,
            "surveilleNuit": False,
        }, format='json')
        self.assertEqual(rep.status_code, status.HTTP_201_CREATED)
        self.assertFalse(rep.data['est_globale'])
        self.assertEqual(Decimal(str(rep.data['seuilMontant_FCFA'])), Decimal('10000.00'))

        # Consommation dépassant 10 000 FCFA (ex. 120 kWh)
        m = MesureEnergie.objects.create(
            capteur=self.cap2, puissance=Decimal('1200'), courant=Decimal('5.4'),
            energie=Decimal('120'), timestamp=timezone.now())
        evaluate_measurements(self.un_client, {self.cap2.id}, mesures=[m])
        alerte = Alerte.objects.filter(client=self.un_client, type='DEPASSEMENT_SEUIL').first()
        self.assertIsNotNone(alerte)
        self.assertIn('FCFA', alerte.message)
        self.assertIn('10000', alerte.message)

    def test_alerte_globale_tous_appareils_combines_en_fcfa_et_detail_w_fcfa(self):
        self.client.force_authenticate(user=self.un_client)
        rep = self.client.post('/api/regles/', {
            "nom": "Alerte globale 10 000 FCFA",
            "capteur": None,
            "seuilMontant_FCFA": 10000,
            "puissanceMax_W": 100000,
            "surveilleNuit": False,
        }, format='json')
        self.assertEqual(rep.status_code, status.HTTP_201_CREATED)
        self.assertTrue(rep.data['est_globale'])
        self.assertEqual(rep.data['capteur_nom'], "Tous les appareils combinés")

        # Chaque appareil est sous 10 000 FCFA séparément (60 kWh chacun), mais combinés = 120 kWh (> 10 000 FCFA)
        now = timezone.now()
        m1 = MesureEnergie.objects.create(
            capteur=self.cap1, puissance=Decimal('60'), courant=Decimal('0.3'),
            energie=Decimal('60'), timestamp=now)
        m2 = MesureEnergie.objects.create(
            capteur=self.cap2, puissance=Decimal('1400'), courant=Decimal('6.3'),
            energie=Decimal('60'), timestamp=now)
        evaluate_measurements(self.un_client, {self.cap1.id, self.cap2.id}, mesures=[m1, m2])

        alerte = Alerte.objects.filter(client=self.un_client, regle_id=rep.data['id']).first()
        self.assertIsNotNone(alerte)
        self.assertIn('tous les appareils combinés', alerte.message)
        self.assertIn('Capteur 1 - ampoule : 60 W', alerte.message)
        self.assertIn('Capteur 2 - climatiseur : 1400 W', alerte.message)
        self.assertIn('FCFA', alerte.message)

        # L'API /api/sensors/ expose à la fois W et FCFA pour chaque appareil
        sensors_rep = self.client.get('/api/sensors/').data
        liste = sensors_rep.get('results', sensors_rep) if isinstance(sensors_rep, dict) else sensors_rep
        par_nom = {s['nom']: s for s in liste}
        self.assertEqual(par_nom['Capteur 1 - ampoule']['puissanceActuelle'], 60)
        self.assertGreater(par_nom['Capteur 1 - ampoule']['coutActuel_FCFA'], 4000)
        self.assertEqual(par_nom['Capteur 2 - climatiseur']['puissanceActuelle'], 1400)
        self.assertGreater(par_nom['Capteur 2 - climatiseur']['coutActuel_FCFA'], 4000)

    def test_alerte_globale_en_watts_mode_expert(self):
        regle = RegleDetection.objects.create(
            client=self.un_client, capteur=None, nom="Seuil global expert W",
            seuilMontant_FCFA=None, puissanceMax_W=Decimal('1500'), surveilleNuit=False)
        now = timezone.now()
        m1 = MesureEnergie.objects.create(
            capteur=self.cap1, puissance=Decimal('300'), courant=Decimal('1.3'),
            energie=Decimal('0.3'), timestamp=now)
        m2 = MesureEnergie.objects.create(
            capteur=self.cap2, puissance=Decimal('1300'), courant=Decimal('5.9'),
            energie=Decimal('1.3'), timestamp=now)
        # 300 W + 1300 W = 1600 W > 1500 W
        evaluate_measurements(self.un_client, {self.cap1.id, self.cap2.id}, mesures=[m1, m2])
        alerte = Alerte.objects.filter(client=self.un_client, regle=regle).first()
        self.assertIsNotNone(alerte)
        self.assertIn('1600 W', alerte.message)
        self.assertIn('Capteur 1 - ampoule : 300 W', alerte.message)
        self.assertIn('Capteur 2 - climatiseur : 1300 W', alerte.message)

