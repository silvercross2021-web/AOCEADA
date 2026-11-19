"""Température et humidité du DHT11 : réception, validation, enregistrement (18/11/2026).

Le firmware joint, une fois par relevé, temperature_c / humidite_pct / releve_unix à une trame de mesure du courant
(POST /api/sensors/zmct/). Ces tests vérifient surtout trois garanties : un relevé garde SA vraie date, rien n'est
jamais inventé ni compté deux fois, et une donnée d'air aberrante ne fait JAMAIS perdre les mesures de courant."""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from .ambiance import releve_valide
from .models import Capteur, Dispositif, MesureEnergie, ReleveAmbiant


def creer_client(email="ambiance@test.ci"):
    c = Client(email=email, nom="Client ambiance", role="client")
    c.set_password("Password123!")
    c.save()
    return c


class ValidationDesRelevesTests(APITestCase):
    def test_valeurs_plausibles_arrondies_au_dixieme(self):
        self.assertEqual(releve_valide(29.04, 61.96), (29.0, 62.0))
        self.assertEqual(releve_valide(30, 72), (30.0, 72.0))

    def test_temperature_aberrante_ecartee(self):
        for t in (None, 0, 0.0, 4.9, 60.1, 85, -10, float("nan"), float("inf"), "abc", True):
            self.assertIsNone(releve_valide(t, 50), f"{t!r} aurait dû être écartée")

    def test_humidite_aberrante_garde_la_temperature_sans_humidite(self):
        self.assertEqual(releve_valide(29.0, 0), (29.0, None))            # « 0 % » = capteur muet, pas un air sec
        self.assertEqual(releve_valide(29.0, 130), (29.0, None))
        self.assertEqual(releve_valide(29.0, None), (29.0, None))


class ReceptionDesRelevesTests(APITestCase):
    def setUp(self):
        self.proprietaire = creer_client()
        self.dispositif = Dispositif.objects.create(client=self.proprietaire, apiKeyDevice="cle_ambiance_test")
        Capteur.objects.create(client=self.proprietaire, dispositif=self.dispositif, nom="Capteur_1",
                               valeurMax=Decimal("2000.00"))
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_ambiance_test")
        self.maintenant = int(timezone.now().timestamp())

    def _post(self, **champs):
        corps = {"capteur_index": 1, "etat": "ON", "courant": 0.33, "puissance": 72.0,
                 "timestamp_unix": self.maintenant}
        corps.update(champs)
        return self.client.post("/api/sensors/zmct/", corps, format="json")

    def test_un_releve_est_enregistre_avec_sa_vraie_date(self):
        quand = self.maintenant - 20                                       # le relevé a 20 s de plus que la trame
        r = self._post(temperature_c=30.0, humidite_pct=72.0, releve_unix=quand)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        rel = ReleveAmbiant.objects.get()
        self.assertEqual(rel.dispositif, self.dispositif)
        self.assertEqual(rel.temperature_c, Decimal("30.0"))
        self.assertEqual(rel.humidite_pct, Decimal("72.0"))
        self.assertEqual(rel.instant, datetime.fromtimestamp(quand, tz=dt_timezone.utc))
        self.assertEqual(MesureEnergie.objects.count(), 1)                 # la mesure de courant passe toujours

    def test_sans_champ_ambiant_aucune_ligne_et_rien_ne_change(self):
        """Ancien programme, ou DHT11 muet : jamais de relevé par défaut."""
        r = self._post()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ReleveAmbiant.objects.count(), 0)
        self.assertEqual(MesureEnergie.objects.count(), 1)

    def test_meme_releve_envoye_deux_fois_n_est_compte_qu_une_fois(self):
        """Accusé perdu puis renvoi, ou tampon rejoué : le même relevé (même boîtier, même instant) ne double rien."""
        for _ in range(2):
            self._post(temperature_c=30.0, humidite_pct=72.0, releve_unix=self.maintenant - 5)
        self.assertEqual(ReleveAmbiant.objects.count(), 1)

    def test_sans_instant_de_releve_celui_de_la_trame_sert(self):
        self._post(temperature_c=29.0, humidite_pct=60.0)
        self.assertEqual(ReleveAmbiant.objects.get().instant,
                         datetime.fromtimestamp(self.maintenant, tz=dt_timezone.utc))

    def test_instant_invalide_utilise_l_heure_de_reception_jamais_une_heure_inventee(self):
        avant = timezone.now()
        self._post(temperature_c=29.0, humidite_pct=60.0, releve_unix=12345, timestamp_unix=0)
        rel = ReleveAmbiant.objects.get()
        self.assertGreaterEqual(rel.instant, avant)
        self.assertLessEqual(rel.instant, timezone.now())

    def test_un_releve_ancien_du_tampon_garde_sa_date(self):
        il_y_a_trois_heures = self.maintenant - 3 * 3600
        self._post(temperature_c=33.0, humidite_pct=55.0, releve_unix=il_y_a_trois_heures,
                   timestamp_unix=il_y_a_trois_heures)
        self.assertEqual(ReleveAmbiant.objects.get().instant,
                         datetime.fromtimestamp(il_y_a_trois_heures, tz=dt_timezone.utc))

    def test_valeur_aberrante_ne_fait_pas_perdre_la_mesure_de_courant(self):
        """« 0 °C, 0 % » (capteur en défaut) : le relevé est écarté, mais la trame (201) et la mesure restent."""
        r = self._post(temperature_c=0.0, humidite_pct=0.0, releve_unix=self.maintenant)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ReleveAmbiant.objects.count(), 0)
        self.assertEqual(MesureEnergie.objects.count(), 1)

    def test_humidite_aberrante_garde_la_temperature(self):
        self._post(temperature_c=28.0, humidite_pct=0.0, releve_unix=self.maintenant)
        rel = ReleveAmbiant.objects.get()
        self.assertEqual(rel.temperature_c, Decimal("28.0"))
        self.assertIsNone(rel.humidite_pct)

    def test_une_panne_de_l_enregistrement_ambiant_ne_bloque_pas_les_mesures(self):
        with patch("apps.sensors.views.noter_releves", side_effect=RuntimeError("base indisponible")):
            r = self._post(temperature_c=30.0, humidite_pct=72.0, releve_unix=self.maintenant)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MesureEnergie.objects.count(), 1)

    def test_un_envoi_en_liste_enregistre_chaque_releve_distinct(self):
        """Le tampon rejoué ou un client qui groupe : plusieurs trames d'un coup."""
        corps = [
            {"capteur_index": 1, "etat": "ON", "courant": 0.3, "puissance": 70.0, "timestamp_unix": self.maintenant - 60,
             "temperature_c": 29.0, "humidite_pct": 60.0, "releve_unix": self.maintenant - 60},
            {"capteur_index": 1, "etat": "ON", "courant": 0.3, "puissance": 70.0, "timestamp_unix": self.maintenant - 30,
             "temperature_c": 29.5, "humidite_pct": 61.0, "releve_unix": self.maintenant - 30},
            {"capteur_index": 1, "etat": "ON", "courant": 0.3, "puissance": 70.0, "timestamp_unix": self.maintenant - 25},
        ]
        r = self.client.post("/api/sensors/zmct/", corps, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ReleveAmbiant.objects.count(), 2)

    def test_les_releves_de_deux_boitiers_ne_se_melangent_pas(self):
        autre = Dispositif.objects.create(client=creer_client("autre@test.ci"), apiKeyDevice="cle_autre")
        Capteur.objects.create(client=autre.client, dispositif=autre, nom="Capteur_1")
        self._post(temperature_c=30.0, humidite_pct=70.0, releve_unix=self.maintenant)
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_autre")
        self._post(temperature_c=25.0, humidite_pct=50.0, releve_unix=self.maintenant)
        self.assertEqual(ReleveAmbiant.objects.filter(dispositif=self.dispositif).count(), 1)
        self.assertEqual(ReleveAmbiant.objects.filter(dispositif=autre).get().temperature_c, Decimal("25.0"))

    def test_clef_invalide_aucun_releve(self):
        self.client.credentials(HTTP_AUTHORIZATION="Device mauvaise_cle")
        r = self._post(temperature_c=30.0, humidite_pct=72.0)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ReleveAmbiant.objects.count(), 0)
