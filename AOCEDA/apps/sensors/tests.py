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


class ZMCTIngestionTests(APITestCase):
    """POST /api/sensors/zmct/ : endpoint RÉELLEMENT utilisé par le firmware ESP32
    (Test_ZMCT/src/main.cpp) — capteur_index (1-basé) + auth "Device <clé>", distinct
    de /api/mesures/. Couvre notamment timestamp_unix : une mesure rejouée depuis le
    tampon hors-ligne du firmware doit garder SA vraie date d'acquisition (pas la
    date de rejeu), sans quoi toute une coupure WiFi serait tassée sur quelques
    secondes dans l'historique au lieu d'être répartie sur sa vraie durée."""

    def setUp(self):
        self.proprietaire = creer_client(email="zmct@test.ci")
        self.dispositif = Dispositif.objects.create(
            client=self.proprietaire, apiKeyDevice="cle_zmct_test")
        self.capteur = Capteur.objects.create(
            client=self.proprietaire, dispositif=self.dispositif,
            nom="Capteur_1", valeurMax=Decimal("2000.00"))
        self.client.credentials(HTTP_AUTHORIZATION="Device cle_zmct_test")

    def _post(self, **kwargs):
        payload = {"capteur_index": 1, "etat": "ON", "courant": 0.33, "puissance": 72.0}
        payload.update(kwargs)
        return self.client.post('/api/sensors/zmct/', payload, format='json')

    def test_sans_timestamp_unix_utilise_l_heure_de_reception(self):
        """Comportement historique (streaming live, déjà en prod) : inchangé."""
        avant = timezone.now()
        r = self._post()
        apres = timezone.now()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mesure = MesureEnergie.objects.get()
        self.assertGreaterEqual(mesure.timestamp, avant)
        self.assertLessEqual(mesure.timestamp, apres)

    def test_timestamp_unix_valide_reprend_la_vraie_date(self):
        """Mesure rejouée depuis le tampon hors-ligne : garde sa date réelle
        d'acquisition (il y a 2h), PAS l'heure de rejeu (maintenant)."""
        il_y_a_2h = timezone.now() - timezone.timedelta(hours=2)
        r = self._post(timestamp_unix=int(il_y_a_2h.timestamp()))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mesure = MesureEnergie.objects.get()
        self.assertAlmostEqual(mesure.timestamp.timestamp(), il_y_a_2h.timestamp(), delta=2)

    def test_timestamp_unix_zero_non_synchronise_utilise_l_heure_de_reception(self):
        """0 = l'ESP32 n'a jamais réussi de synchronisation NTP : pas une vraie date."""
        avant = timezone.now()
        r = self._post(timestamp_unix=0)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mesure = MesureEnergie.objects.get()
        self.assertGreaterEqual(mesure.timestamp, avant)

    def test_timestamp_unix_futur_aberrant_ignore(self):
        """Une date dans un futur lointain (horloge non fiable) est écartée, jamais
        insérée telle quelle dans l'historique du client."""
        futur = timezone.now() + timezone.timedelta(days=1)
        r = self._post(timestamp_unix=int(futur.timestamp()))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mesure = MesureEnergie.objects.get()
        self.assertLess(mesure.timestamp, futur)

    def test_derniere_lecture_reste_l_heure_de_reception_meme_si_rejoue(self):
        """Un rattrapage de tampon (vieilles mesures) ne doit JAMAIS faire paraître
        le capteur hors ligne : derniereLecture = quand on l'a VRAIMENT reçu."""
        avant = timezone.now()
        il_y_a_2h = timezone.now() - timezone.timedelta(hours=2)
        r = self._post(timestamp_unix=int(il_y_a_2h.timestamp()))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.capteur.refresh_from_db()
        self.assertGreaterEqual(self.capteur.derniereLecture, avant)

    def test_rejeu_sequentiel_preserve_les_intervalles_reels(self):
        """Le firmware rejoue le tampon UNE mesure par requête HTTP (jamais en lot) —
        ce test le simule : 3 mesures espacées de leur vrai intervalle (2 s) dans le
        PASSÉ, postées coup sur coup (comme un vrai rattrapage). Chaque energie doit
        refléter ~2 s réels, pas l'intervalle quasi nul entre les requêtes de test."""
        base = timezone.now() - timezone.timedelta(hours=1)
        for i in range(3):
            r = self._post(puissance=72.0, timestamp_unix=int(base.timestamp()) + i * 2)
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mesures = list(MesureEnergie.objects.order_by('timestamp'))
        self.assertEqual(len(mesures), 3)
        # 2e et 3e mesure : intervalle réel de 2s → énergie = 72W * 2s, pas défaut/capé.
        attendu_kwh = 72.0 / 1000.0 * (2.0 / 3600.0)
        for m in mesures[1:]:
            self.assertAlmostEqual(float(m.energie), attendu_kwh, places=6)

    def test_capteur_index_hors_limites_ignore_sans_erreur(self):
        r = self._post(capteur_index=5)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MesureEnergie.objects.count(), 0)

    def test_sans_authentification_refusee(self):
        self.client.credentials()
        r = self._post()
        self.assertIn(r.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


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

    def test_qr_config_genere_cote_serveur(self):
        """Le QR code de configuration doit être généré côté serveur (reportlab),
        jamais via un service tiers : la clé API ne doit fuiter vers aucune URL
        externe. On vérifie juste que l'endpoint répond un SVG contenant la clé,
        pas la présence/absence d'un appel réseau (hors de portée d'un test unitaire)."""
        dispositif = Dispositif.objects.create(
            client=self.un_client, apiKeyDevice="cle_qr_test_12345")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(f'/api/sensors/dispositifs/{dispositif.id}/qr-config/?ssid=MonWifi')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertTrue(response.content.startswith(b'<?xml'))

    def test_qr_config_dispositif_inexistant(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get('/api/sensors/dispositifs/00000000-0000-0000-0000-000000000000/qr-config/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_qr_config_refuse_au_client(self):
        dispositif = Dispositif.objects.create(client=self.un_client, apiKeyDevice="cle_qr_client")
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get(f'/api/sensors/dispositifs/{dispositif.id}/qr-config/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_technicien_regenere_cle_api(self):
        dispositif = Dispositif.objects.create(
            client=self.un_client, apiKeyDevice="ancienne_cle")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(f'/api/sensors/dispositifs/{dispositif.id}/regenerer-cle/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['apiKeyDevice'], "ancienne_cle")

    def test_technicien_calibre_capteur(self):
        capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Prise")
        self.assertIsNone(capteur.derniereCalibration)
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(f'/api/sensors/capteurs/{capteur.id}/',
                                     {"coeffCalibration": "0.9180"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        capteur.refresh_from_db()
        self.assertEqual(capteur.coeffCalibration, Decimal("0.9180"))
        # La calibration manuelle doit horodater derniereCalibration (visible côté
        # front, onglet Calibration : « Dernière calibration » n'affichait que "—"
        # faute de ce champ, jamais alimenté avant cette correction).
        self.assertIsNotNone(capteur.derniereCalibration)

    def test_edition_capteur_sans_changer_coeff_ne_touche_pas_derniere_calibration(self):
        """Modifier `actif` (ou tout autre champ) sans toucher au coefficient ne doit
        pas donner l'illusion d'une calibration qui n'a pas eu lieu."""
        capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Prise", actif=True)
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(f'/api/sensors/capteurs/{capteur.id}/', {"actif": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        capteur.refresh_from_db()
        self.assertIsNone(capteur.derniereCalibration)

    def test_calibration_auto_horodate_derniere_calibration(self):
        capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Auto")
        MesureEnergie.objects.create(
            capteur=capteur, puissance=Decimal("100.00"), courant=Decimal("0.45"),
            energie=Decimal("0.1"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(f'/api/sensors/capteurs/{capteur.id}/calibrer/', {"puissance_reelle": "60"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        capteur.refresh_from_db()
        self.assertIsNotNone(capteur.derniereCalibration)

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


class RapportInterventionPDFTests(APITestCase):
    """Le rapport d'intervention doit être téléchargeable en PDF par le
    technicien assigné (et lui seul, hors admin), jamais par un client."""

    def setUp(self):
        from .models import RapportIntervention
        self.technicien = creer_technicien()
        # email[:4] distinct → matricule distinct (le helper dérive T-<email[:4]>)
        self.autre_tech = creer_technicien(email="autre@test.ci")
        self.un_client = creer_client(email="menage2@test.ci")
        self.intervention = Intervention.objects.create(
            technicien=self.technicien, client=self.un_client,
            typeIntervention='MAINTENANCE', description="Contrôle du capteur salon.",
            dateIntervention=timezone.now(), statut='TERMINEE',
            résultat="Capteur recalibré, mesures conformes.")
        self.rapport = RapportIntervention.objects.create(
            intervention=self.intervention,
            contenu="Vérification complète du capteur.\nRemplacement du câble.",
            estValidé=True)
        self.url = f'/api/sensors/interventions/{self.intervention.id}/rapport/pdf/'

    def test_technicien_assigne_telecharge_le_pdf(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('aoceda_intervention_', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_autre_technicien_refuse(self):
        self.client.force_authenticate(user=self.autre_tech)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_proprietaire_telecharge_le_pdf(self):
        # Le client PROPRIÉTAIRE de l'intervention peut télécharger son propre
        # rapport (fonctionnalité réelle utilisée par la page Interventions côté
        # client, bouton « Télécharger le Rapport (PDF) ») — remplace l'ancien
        # test_client_refuse, qui attendait à tort un 403 pour ce cas précis alors
        # que self.un_client EST le propriétaire (setUp ci-dessus).
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_autre_client_refuse(self):
        # Un client qui n'est PAS le propriétaire de l'intervention, lui, doit
        # bien être refusé — c'est le cas que test_client_refuse voulait couvrir.
        autre_client = creer_client(email="pas-le-proprietaire@test.ci")
        self.client.force_authenticate(user=autre_client)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_intervention_sans_rapport_404(self):
        sans_rapport = Intervention.objects.create(
            technicien=self.technicien, client=self.un_client,
            typeIntervention='PANNE', description="Panne signalée.",
            dateIntervention=timezone.now(), statut='EN_COURS')
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(f'/api/sensors/interventions/{sans_rapport.id}/rapport/pdf/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_refuse_sans_authentification(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class JournalEquipeTests(APITestCase):
    """Traçabilité : les actions techniciens qui modifient directement une donnée
    (calibration, clé API, assignation) hors du cycle Intervention doivent être
    journalisées (AuditLog), consultables par TOUTE l'équipe via /api/sensors/journal/
    — pas seulement par leur auteur : la traçabilité n'a de sens que si elle est
    partagée entre collègues, pas cachée dans un journal personnel."""

    def setUp(self):
        from apps.accounts.models import AuditLog
        AuditLog.objects.all().delete()
        self.technicien = creer_technicien()
        self.autre_tech = creer_technicien(email="autre@test.ci")
        self.un_client = creer_client(email="menage3@test.ci")
        self.dispositif = Dispositif.objects.create(
            client=self.un_client, apiKeyDevice="cle_journal_test")
        self.capteur = Capteur.objects.create(
            client=self.un_client, dispositif=self.dispositif, nom="Capteur Journal")

    def test_calibration_auto_est_journalisee(self):
        from apps.accounts.models import AuditLog
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("100.00"), courant=Decimal("0.45"),
            energie=Decimal("0.1"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(
            f'/api/sensors/capteurs/{self.capteur.id}/calibrer/', {"puissance_reelle": "60"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entree = AuditLog.objects.get(action='CALIBRATION_AUTO')
        self.assertEqual(entree.utilisateur_id, self.technicien.id)
        self.assertEqual(entree.client_id, self.un_client.id)

    def test_calibration_directe_via_patch_est_journalisee(self):
        """Le PATCH direct de coeffCalibration (chemin réellement utilisé par le front
        pour la calibration manuelle) doit laisser une trace, pas seulement l'endpoint
        dédié /calibrer/."""
        from apps.accounts.models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/sensors/capteurs/{self.capteur.id}/', {"coeffCalibration": "0.9500"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entree = AuditLog.objects.get(action='CALIBRATION_MANUELLE')
        self.assertIn('0.9500', entree.description)

    def test_edition_capteur_sans_changement_ne_journalise_rien(self):
        """Un PATCH qui ne modifie ni coeffCalibration ni actif (ex. juste relire/
        renvoyer les mêmes valeurs) ne doit pas créer d'entrée de journal bruyante."""
        from apps.accounts.models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/sensors/capteurs/{self.capteur.id}/', {"type": "Courant"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_regeneration_cle_est_journalisee(self):
        from apps.accounts.models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(f'/api/sensors/dispositifs/{self.dispositif.id}/regenerer-cle/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entree = AuditLog.objects.get(action='REGENERATION_CLÉ')
        self.assertEqual(entree.cible_id, str(self.dispositif.id))

    def test_assignation_capteur_est_journalisee(self):
        from apps.accounts.models import AuditLog
        capteur_libre = Capteur.objects.create(client=None, nom="Capteur Pool")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post(
            f'/api/sensors/capteurs/{capteur_libre.id}/assigner/', {"client": str(self.un_client.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entree = AuditLog.objects.get(action='ASSIGNATION_CAPTEUR')
        self.assertEqual(entree.client_id, self.un_client.id)

    def test_journal_visible_par_toute_l_equipe(self):
        """Un technicien doit voir les actions de SES COLLÈGUES, pas seulement les
        siennes — c'est tout le sens d'un journal d'équipe partagé."""
        from apps.accounts.models import AuditLog
        from apps.accounts.audit import log_action
        log_action(self.technicien, 'REGENERATION_CLÉ', "Action A")
        log_action(self.autre_tech, 'REGENERATION_CLÉ', "Action B")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get('/api/sensors/journal/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resultats = response.data['results']
        descriptions = {r['description'] for r in resultats}
        self.assertEqual(descriptions, {"Action A", "Action B"})

    def test_journal_filtrable_par_client(self):
        from apps.accounts.audit import log_action
        autre_client = creer_client(email="menage4@test.ci")
        log_action(self.technicien, 'EDITION_CLIENT', "Sur le bon client", client=self.un_client)
        log_action(self.technicien, 'EDITION_CLIENT', "Sur un autre client", client=autre_client)
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(f'/api/sensors/journal/?client={self.un_client.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resultats = response.data['results']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['description'], "Sur le bon client")

    def test_journal_filtrable_par_utilisateur(self):
        from apps.accounts.audit import log_action
        log_action(self.technicien, 'REGENERATION_CLÉ', "Action du technicien A")
        log_action(self.autre_tech, 'REGENERATION_CLÉ', "Action du technicien B")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(f'/api/sensors/journal/?utilisateur={self.autre_tech.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resultats = response.data['results']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['description'], "Action du technicien B")

    def test_client_ne_peut_pas_acceder_au_journal(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/sensors/journal/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InterventionIntegriteTests(APITestCase):
    """Intégrité de la traçabilité : un technicien ne doit pouvoir ni réattribuer une
    intervention à un autre technicien, ni en antidater la date, après création."""

    def setUp(self):
        self.technicien = creer_technicien()
        self.autre_tech = creer_technicien(email="autre2@test.ci")
        self.un_client = creer_client(email="menage5@test.ci")
        self.date_originale = timezone.now()
        self.intervention = Intervention.objects.create(
            technicien=self.technicien, client=self.un_client,
            typeIntervention='MAINTENANCE', description="Contrôle standard.",
            dateIntervention=self.date_originale, statut='TERMINEE')
        self.url = f'/api/sensors/interventions/{self.intervention.id}/'

    def test_technicien_ne_peut_pas_reattribuer_l_intervention(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(self.url, {"technicien": str(self.autre_tech.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.technicien_id, self.technicien.id)

    def test_technicien_ne_peut_pas_antidater_l_intervention(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(self.url, {"dateIntervention": "2020-01-01T00:00:00Z"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.dateIntervention, self.date_originale)

    def test_technicien_peut_toujours_modifier_statut_et_resultat(self):
        """Le verrou ne doit porter que sur technicien/dateIntervention : le reste du
        cycle de vie (statut, résultat) doit rester pleinement fonctionnel."""
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(self.url, {
            "statut": "TERMINEE", "résultat": "Recalibrage effectué avec succès.",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.résultat, "Recalibrage effectué avec succès.")


class InterventionExportCSVTests(APITestCase):
    """Export CSV des interventions technicien (mémoire §6.1.1 : exports PDF/CSV
    déjà annoncés pour le rôle technicien, absents avant cette correction)."""

    def setUp(self):
        self.technicien = creer_technicien()
        self.autre_tech = creer_technicien(email="autre3@test.ci")
        self.un_client = creer_client(email="menage6@test.ci")
        self.url = '/api/sensors/interventions/export/csv/'
        Intervention.objects.create(
            technicien=self.technicien, client=self.un_client,
            typeIntervention='PANNE', description="Description ; avec point-virgule",
            dateIntervention=timezone.now(), statut='EN_ATTENTE')
        Intervention.objects.create(
            technicien=self.autre_tech, client=self.un_client,
            typeIntervention='MAINTENANCE', description="Intervention d'un autre technicien",
            dateIntervention=timezone.now(), statut='TERMINEE')

    def test_technicien_exporte_uniquement_ses_propres_interventions(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="aoceda_interventions_', response['Content-Disposition'])
        contenu = response.content.decode('utf-8-sig')
        self.assertIn('point-virgule', contenu)
        self.assertNotIn("d'un autre technicien", contenu)

    def test_client_ne_peut_pas_exporter(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_export_sans_authentification_refuse(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class InterventionClientTests(APITestCase):
    def setUp(self):
        self.client_user = creer_client(email="client.inter@test.ci")
        self.tech = creer_technicien(email="tech.inter@test.ci")
        self.tech.estActif = True
        self.tech.save()

    def test_client_cree_panne_et_auto_assigne_tech(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post('/api/sensors/interventions/', {
            "typeIntervention": "PANNE",
            "description": "Le capteur ne fonctionne plus"
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['statut'], 'EN_ATTENTE')
        self.assertEqual(response.data['client'], self.client_user.id)
        self.assertEqual(response.data['technicien'], self.tech.id)

    def test_client_ne_peut_pas_voir_interventions_des_autres(self):
        autre_client = creer_client(email="autre.inter@test.ci")
        Intervention.objects.create(
            technicien=self.tech, client=autre_client,
            typeIntervention='PANNE', description="Panne d'un autre client",
            dateIntervention=timezone.now(), statut='EN_ATTENTE'
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/sensors/interventions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Réponse paginée DRF ({count,next,previous,results}) : la liste vide est
        # dans 'results', pas response.data lui-même (qui a toujours 4 clés).
        self.assertEqual(response.data['results'], [])

