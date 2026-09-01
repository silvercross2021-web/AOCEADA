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
        from apps.analytics.models import Prevision
        client = creer_client(email="cross-mois@test.ci")
        client.typeCompteur = 'prepaye'
        client.creditPrepaye_FCFA = Decimal('20000')  # recharge unique, jamais renouvelée
        client.save()
        # Mois précédent déjà clos : 18 000 FCFA consommés (snapshot figé, comme
        # le fait réellement PrevisionListView.generate_forecast_for_client).
        mois_precedent = (timezone.localdate().replace(day=1) - timedelta(days=1))
        Prevision.objects.create(
            client=client, moisConcerné="Mois précédent", annee_mois=mois_precedent.strftime("%Y-%m"),
            consomméeEstimée_kWh=Decimal('50'), montantEstimé_FCFA=Decimal('18000'))
        info = credit_prepaye_info(client)
        # Il ne reste RÉELLEMENT qu'environ 2000 FCFA (20000 - 18000), pas 20000.
        self.assertLessEqual(info['restant_fcfa'], Decimal('2000'))
