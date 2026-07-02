"""Tests de l'application sensors : authentification API Key ESP32,
réception/validation/stockage des mesures, endpoints technicien."""
from decimal import Decimal
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import Client, Technicien
from .models import Dispositif, Capteur, MesureEnergie, Intervention


def creer_client(email="client@test.ci"):
    client = Client(email=email, nom="Client Test", role='client')
    client.set_password("Password123!")
    client.save()
    return client


def creer_technicien(email="tech@test.ci"):
    tech = Technicien(email=email, nom="Tech Test", role='technicien', matricule=f"T-{email[:4]}")
    tech.set_password("Password123!")
    tech.save()
    return tech


class MesureESP32Tests(APITestCase):
    """Flux ESP32 -> API Django (mémoire §6.2.1 : POST /api/mesures/ par API Key)."""

    def setUp(self):
        self.proprietaire = creer_client()
        self.dispositif = Dispositif.objects.create(
            client=self.proprietaire, apiKeyDevice="test_api_key_esp32_001")
        self.capteur = Capteur.objects.create(
            client=self.proprietaire, dispositif=self.dispositif,
            nom="Capteur Lampe", valeurMax=Decimal("2000.00"))
        self.payload = {
            "capteur": str(self.capteur.id),
            "puissance": "95.20", "courant": "0.433", "energie": "0.0952",
            "timestamp": timezone.now().isoformat(),
        }

    def test_post_mesure_avec_api_key_valide(self):
        self.client.credentials(HTTP_AUTHORIZATION="Device test_api_key_esp32_001")
        response = self.client.post('/api/mesures/', self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MesureEnergie.objects.count(), 1)

    def test_post_mesure_api_key_invalide_refusee(self):
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_inconnue")
        response = self.client.post('/api/mesures/', self.payload)
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        self.assertEqual(MesureEnergie.objects.count(), 0)

    def test_post_mesure_sans_authentification_refusee(self):
        response = self.client.post('/api/mesures/', self.payload)
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_post_mesure_lot_synchronisation_differee(self):
        """Bulk upload après reconnexion Wi-Fi (tampon SPIFFS, mémoire §5.2.3)."""
        self.client.credentials(HTTP_AUTHORIZATION="Device test_api_key_esp32_001")
        lot = [dict(self.payload), dict(self.payload), dict(self.payload)]
        response = self.client.post('/api/mesures/', lot, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MesureEnergie.objects.count(), 3)

    def test_post_mesure_capteur_d_un_autre_client_refusee(self):
        autre = creer_client(email="autre@test.ci")
        capteur_autre = Capteur.objects.create(client=autre, nom="Capteur intrus")
        self.client.credentials(HTTP_AUTHORIZATION="Device test_api_key_esp32_001")
        payload = dict(self.payload, capteur=str(capteur_autre.id))
        response = self.client.post('/api/mesures/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_mesure_met_a_jour_derniere_lecture(self):
        self.client.credentials(HTTP_AUTHORIZATION="Device test_api_key_esp32_001")
        self.client.post('/api/mesures/', self.payload)
        self.capteur.refresh_from_db()
        self.assertIsNotNone(self.capteur.derniereLecture)

    def test_get_mesures_filtre_par_periode(self):
        vieille = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=100, courant=Decimal("0.45"),
            energie=Decimal("0.1"), timestamp=timezone.now() - timezone.timedelta(days=10))
        recente = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=200, courant=Decimal("0.9"),
            energie=Decimal("0.2"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.proprietaire)
        response = self.client.get('/api/mesures/?period=week')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m['id'] for m in response.data]
        self.assertIn(str(recente.id), ids)
        self.assertNotIn(str(vieille.id), ids)

    def test_get_mesures_filtre_par_dates(self):
        m1 = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=100, courant=Decimal("0.45"),
            energie=Decimal("0.1"), timestamp=timezone.now() - timezone.timedelta(days=5))
        m2 = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=200, courant=Decimal("0.9"),
            energie=Decimal("0.2"), timestamp=timezone.now() - timezone.timedelta(days=2))
        self.client.force_authenticate(user=self.proprietaire)
        date_from = (timezone.now() - timezone.timedelta(days=6)).date().isoformat()
        date_to = (timezone.now() - timezone.timedelta(days=4)).date().isoformat()
        response = self.client.get(f'/api/mesures/?date_from={date_from}&date_to={date_to}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m['id'] for m in response.data]
        self.assertIn(str(m1.id), ids)
        self.assertNotIn(str(m2.id), ids)

    def test_get_mesures_dates_prioritaires_sur_periode(self):
        """date_from/date_to l'emportent sur period : la plage seule décide."""
        vieille = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=90, courant=Decimal("0.41"),
            energie=Decimal("0.09"), timestamp=timezone.now() - timezone.timedelta(days=20))
        recente = MesureEnergie.objects.create(
            capteur=self.capteur, puissance=210, courant=Decimal("0.95"),
            energie=Decimal("0.21"), timestamp=timezone.now())
        date_from = (timezone.now() - timezone.timedelta(days=25)).date().isoformat()
        date_to = (timezone.now() - timezone.timedelta(days=15)).date().isoformat()
        self.client.force_authenticate(user=self.proprietaire)
        # period=week renverrait la mesure récente, mais la plage doit primer
        response = self.client.get(
            f'/api/mesures/?period=week&date_from={date_from}&date_to={date_to}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m['id'] for m in response.data]
        self.assertIn(str(vieille.id), ids)
        self.assertNotIn(str(recente.id), ids)

    def test_get_mesures_date_invalide_rejetee(self):
        """Un format de date erroné renvoie 400 (pas de 500)."""
        self.client.force_authenticate(user=self.proprietaire)
        response = self.client.get('/api/mesures/?date_from=2026-99-99&date_to=2026-01-01')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_mesures_plage_inversee_rejetee(self):
        """date_from > date_to renvoie 400."""
        self.client.force_authenticate(user=self.proprietaire)
        response = self.client.get('/api/mesures/?date_from=2026-06-10&date_to=2026-06-01')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_capteurs_du_client(self):
        self.client.force_authenticate(user=self.proprietaire)
        response = self.client.get('/api/sensors/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(data), 1)


class EspaceTechnicienTests(APITestCase):
    """Cas d'utilisation technicien : enregistrer ESP32, calibrer, intervenir."""

    def setUp(self):
        self.technicien = creer_technicien()
        self.un_client = creer_client(email="menage@test.ci")

    def test_client_ne_peut_pas_enregistrer_dispositif(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.post('/api/sensors/dispositifs/',
                                    {"client": str(self.un_client.id)})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_technicien_enregistre_esp32_avec_cle_generee(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/sensors/dispositifs/', {
            "client": str(self.un_client.id), "firmwareVersion": "v2.1.3",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['apiKeyDevice'].startswith('aoceda_esp32_'))

    def test_technicien_regenere_cle_api(self):
        dispositif = Dispositif.objects.create(
            client=self.un_client, apiKeyDevice="ancienne_cle")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(f'/api/sensors/dispositifs/{dispositif.id}/regenerer-cle/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['apiKeyDevice'], "ancienne_cle")

    def test_technicien_calibre_capteur(self):
        capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Prise")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(f'/api/sensors/capteurs/{capteur.id}/',
                                     {"coeffCalibration": "0.9180"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        capteur.refresh_from_db()
        self.assertEqual(capteur.coeffCalibration, Decimal("0.9180"))

    def test_technicien_declare_panne_et_genere_rapport(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/sensors/interventions/', {
            "client": str(self.un_client.id),
            "typeIntervention": "PANNE",
            "description": "Capteur muet depuis 24h.",
            "dateIntervention": timezone.now().isoformat(),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        intervention_id = response.data['id']
        # L'intervention est assignée automatiquement au technicien connecté
        self.assertEqual(Intervention.objects.get(id=intervention_id).technicien_id,
                         self.technicien.id)
        # Génération du rapport
        response = self.client.post(f'/api/sensors/interventions/{intervention_id}/rapport/', {
            "contenu": "Remplacement du capteur ZMCT103C.",
            "conclusion": "Panne résolue.",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
