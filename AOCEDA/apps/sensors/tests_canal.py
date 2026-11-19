"""Canal du boîtier (Wi-Fi ou câble USB) et état affiché des capteurs quand un canal tombe.

Le pont USB (outils/pont_usb_esp32.py) annonce ses trames par l'en-tête X-Canal: usb ; sans lui, une trame est du
Wi-Fi. Ces tests vérifient : le canal est retenu et journalisé, le boîtier n'est « connecté » que s'il répond vraiment,
et une trame REJOUÉE du tampon ne change jamais l'état « allumé / éteint » affiché."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from .models import Capteur, Dispositif, MesureEnergie
from .serializers import DispositifSerializer


def creer_client(email="canal@test.ci"):
    c = Client(email=email, nom="Client canal", role="client")
    c.set_password("Password123!")
    c.save()
    return c


class CanalDuBoitierTests(APITestCase):
    def setUp(self):
        self.proprietaire = creer_client()
        self.dispositif = Dispositif.objects.create(
            client=self.proprietaire, apiKeyDevice="cle_canal_test", numeroSerie="ESP32-CANAL")
        self.capteur = Capteur.objects.create(
            client=self.proprietaire, dispositif=self.dispositif, nom="Capteur_1", valeurMax=Decimal("2000.00"))
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_canal_test")

    def _post(self, extra=None, **kwargs):
        payload = {"capteur_index": 1, "etat": "ON", "courant": 0.33, "puissance": 72.0}
        payload.update(kwargs)
        return self.client.post('/api/sensors/zmct/', payload, format='json', **(extra or {}))

    def test_sans_en_tete_la_trame_est_du_wifi_et_l_ip_de_la_carte_est_retenue(self):
        r = self._post(extra={"REMOTE_ADDR": "192.168.1.143"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.dispositif.refresh_from_db()
        self.assertEqual(self.dispositif.canal, 'wifi')
        self.assertEqual(self.dispositif.adresseIP, "192.168.1.143")
        self.assertIsNotNone(self.dispositif.canalDepuis)

    def test_en_tete_usb_donne_le_canal_usb_sans_toucher_a_l_adresse_ip(self):
        r = self._post(extra={"HTTP_X_CANAL": "usb"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.dispositif.refresh_from_db()
        self.assertEqual(self.dispositif.canal, 'usb')
        self.assertIsNone(self.dispositif.adresseIP)   # le PC (127.0.0.1) n'est pas la carte

    def test_valeur_inconnue_de_l_en_tete_compte_comme_wifi(self):
        self._post(extra={"HTTP_X_CANAL": "bluetooth"})
        self.dispositif.refresh_from_db()
        self.assertEqual(self.dispositif.canal, 'wifi')

    def test_un_changement_de_canal_est_journalise_et_date(self):
        self._post()
        self.dispositif.refresh_from_db()
        premier = self.dispositif.canalDepuis
        self._post()                                    # même canal : rien ne change, pas de nouvelle date
        self.dispositif.refresh_from_db()
        self.assertEqual(self.dispositif.canalDepuis, premier)
        with self.assertLogs('aoceda.canal', level='WARNING') as journal:
            self._post(extra={"HTTP_X_CANAL": "usb"})   # le Wi-Fi est tombé, la carte passe par le câble
        self.assertIn("Wi-Fi -> USB", journal.output[0])
        self.dispositif.refresh_from_db()
        self.assertEqual(self.dispositif.canal, 'usb')
        self.assertGreater(self.dispositif.canalDepuis, premier)

    def test_le_canal_est_dans_la_liste_des_capteurs_du_client(self):
        self._post(extra={"HTTP_X_CANAL": "usb"})
        self.client.credentials()
        self.client.force_authenticate(user=self.proprietaire)
        r = self.client.get('/api/sensors/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        lignes = r.data['results'] if isinstance(r.data, dict) and 'results' in r.data else r.data
        self.assertEqual(lignes[0]['canal'], 'usb')


class EtatDuBoitierTests(APITestCase):
    def setUp(self):
        self.proprietaire = creer_client("etat@test.ci")
        self.dispositif = Dispositif.objects.create(
            client=self.proprietaire, apiKeyDevice="cle_etat_test", estConnecté=True)
        self.capteur = Capteur.objects.create(
            client=self.proprietaire, dispositif=self.dispositif, nom="Capteur_1", valeurMax=Decimal("2000.00"))
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_etat_test")

    def _post(self, **kwargs):
        payload = {"capteur_index": 1, "etat": "ON", "courant": 0.33, "puissance": 72.0}
        payload.update(kwargs)
        return self.client.post('/api/sensors/zmct/', payload, format='json')

    def test_boitier_muet_n_est_plus_dit_connecte(self):
        """estConnecté restait True pour toujours : il suit maintenant le dernier contact réel."""
        self.assertFalse(DispositifSerializer(self.dispositif).data['estConnecté'])        # jamais rien reçu
        self._post()
        self.assertTrue(DispositifSerializer(self.dispositif).data['estConnecté'])         # vient de parler
        Capteur.objects.filter(pk=self.capteur.pk).update(derniereLecture=timezone.now() - timedelta(minutes=5))
        self.assertFalse(DispositifSerializer(self.dispositif).data['estConnecté'])        # muet depuis 5 min

    def test_une_trame_rejouee_ne_change_pas_l_etat_affiche(self):
        """Le Wi-Fi revient et la carte vide son tampon : un vieux « allumé » ne doit pas rallumer l'écran alors que
        l'appareil est éteint maintenant. La consommation, elle, est bien comptée à sa vraie date."""
        self._post()                                                     # allumé, en direct
        self._post(etat="OFF", courant=0.0, puissance=0.0)               # éteint, en direct
        self.capteur.refresh_from_db()
        self.assertEqual(self.capteur.etatCourant, 'OFF')
        depuis = self.capteur.etatDepuis
        ancien = timezone.now() - timedelta(minutes=10)
        r = self._post(timestamp_unix=int(ancien.timestamp()))           # trame ON rejouée, vieille de 10 min
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.capteur.refresh_from_db()
        self.assertEqual(self.capteur.etatCourant, 'OFF')
        self.assertEqual(self.capteur.etatDepuis, depuis)
        self.assertTrue(MesureEnergie.objects.filter(capteur=self.capteur, timestamp__lte=ancien + timedelta(seconds=2)).exists())

    def test_une_trame_rejouee_donne_quand_meme_un_signe_de_vie(self):
        ancien = timezone.now() - timedelta(minutes=10)
        self._post(timestamp_unix=int(ancien.timestamp()))
        self.capteur.refresh_from_db()
        self.assertGreater(self.capteur.derniereLecture, timezone.now() - timedelta(seconds=10))
