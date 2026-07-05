"""Tests de l'application analytics : moteur tarifaire CIE officiel,
prévision de facturation FCFA, indicateurs, export CSV, statistiques admin."""
from decimal import Decimal
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import Client, Administrateur
from apps.sensors.models import Capteur, MesureEnergie
from .models import Prevision
from .tarifs_cie import calculer_facture_mensuelle


class MoteurTarifaireCIETests(APITestCase):
    """Valide le moteur contre les exemples chiffrés d'EXPLICATION_TARIFAIRE.md
    (grille officielle cie.ci, hausse janv. 2024, application mensuelle)."""

    def test_exemple_1_social_5a_35kwh(self):
        d = calculer_facture_mensuelle(35, amperage=5, type_tarif='social')
        self.assertEqual(d['tranche2_kwh'], Decimal('0.00'))  # sous le seuil de 40
        self.assertAlmostEqual(float(d['total_fcfa']), 1610, delta=10)

    def test_exemple_2_social_5a_60kwh_progressif(self):
        d = calculer_facture_mensuelle(60, amperage=5, type_tarif='social')
        self.assertEqual(d['tranche1_kwh'], Decimal('40.00'))
        self.assertEqual(d['tranche2_kwh'], Decimal('20.00'))
        # Social = progressif : la tranche 2 est PLUS chère
        self.assertGreater(d['tranche2_prix'], d['tranche1_prix'])
        self.assertAlmostEqual(float(d['total_fcfa']), 3210, delta=10)

    def test_exemple_3_general_10a_150kwh(self):
        d = calculer_facture_mensuelle(150, amperage=10, type_tarif='general')
        self.assertEqual(d['tranche2_kwh'], Decimal('0.00'))  # sous le seuil de 198
        self.assertAlmostEqual(float(d['total_fcfa']), 14730, delta=10)

    def test_exemple_4_general_10a_270kwh_degressif(self):
        d = calculer_facture_mensuelle(270, amperage=10, type_tarif='general')
        self.assertEqual(d['tranche1_kwh'], Decimal('198.00'))
        self.assertEqual(d['tranche2_kwh'], Decimal('72.00'))
        # Général = dégressif : la tranche 2 est MOINS chère
        self.assertLess(d['tranche2_prix'], d['tranche1_prix'])
        self.assertAlmostEqual(float(d['total_fcfa']), 25000, delta=15)

    def test_exemple_5_general_15a_350kwh(self):
        d = calculer_facture_mensuelle(350, amperage=15, type_tarif='general')
        self.assertEqual(d['seuil_t1_kwh'], Decimal('297'))
        self.assertAlmostEqual(float(d['total_fcfa']), 35680, delta=15)

    def test_pas_de_double_tva(self):
        """Les prix de la grille sont TTC : le total pour 100 kWh en 10A doit être
        T1×100 + prime + taxes, SANS +18 % supplémentaires."""
        d = calculer_facture_mensuelle(100, amperage=10, type_tarif='general')
        attendu = Decimal('100') * Decimal('86.92') + Decimal('809.02') + (Decimal('100') * Decimal('5.56') + 50)
        self.assertAlmostEqual(float(d['total_fcfa']), float(attendu), delta=1)

    def test_social_impossible_hors_5a_retombe_en_general(self):
        d = calculer_facture_mensuelle(100, amperage=10, type_tarif='social')
        self.assertEqual(d['type_tarif'], 'general')

    def test_5a_toujours_facture_au_social(self):
        # Le 5A « général » n'existe pas à la CIE → tout 5A relève du social.
        d = calculer_facture_mensuelle(35, amperage=5, type_tarif='general')
        self.assertEqual(d['type_tarif'], 'social')
        self.assertEqual(float(d['tranche1_prix']), 31.72)

    def test_zero_kwh_paie_quand_meme_la_prime(self):
        d = calculer_facture_mensuelle(0, amperage=10, type_tarif='general')
        self.assertAlmostEqual(float(d['total_fcfa']), float(Decimal('809.02') + 50), delta=1)


def creer_client(email="client@test.ci"):
    client = Client(email=email, nom="Client Test", role='client',
                    tarifkWh_FCFA=Decimal("87.00"))
    client.set_password("Password123!")
    client.save()
    return client


class PrevisionTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Salon")

    def test_prevision_generee_pour_le_mois_courant(self):
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("600.00"),
            courant=Decimal("2.7"), energie=Decimal("0.6"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/previsions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        annee_mois = timezone.localtime().strftime("%Y-%m")
        self.assertTrue(Prevision.objects.filter(
            client=self.un_client, annee_mois=annee_mois).exists())

    def test_montant_prevision_inclut_prime_fixe_et_taxes(self):
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("600.00"),
            courant=Decimal("2.7"), energie=Decimal("0.6"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/previsions/')
        items = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        montant = Decimal(str(items[0]['montantEstimé_FCFA']))
        # Grille CIE 10A général : au minimum la prime fixe mensuelle (809) + taxe fixe (50)
        self.assertGreater(montant, Decimal("858"))

    def test_facture_detail_decomposition_officielle(self):
        """L'endpoint /api/analytics/facture/ expose la décomposition CIE complète."""
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("600.00"),
            courant=Decimal("2.7"), energie=Decimal("9.0"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/facture/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = response.data
        for cle in ("tranche1", "tranche2", "prime_fixe_fcfa", "taxes_fcfa",
                    "total_fcfa", "prix_moyen_kwh", "seuil_t1_kwh", "amperage"):
            self.assertIn(cle, d)
        self.assertTrue(d["tva_incluse"])
        self.assertEqual(d["amperage"], 10)
        # Cohérence interne : total = T1 + T2 + prime + taxes
        somme = d["tranche1"]["fcfa"] + d["tranche2"]["fcfa"] + d["prime_fixe_fcfa"] + d["taxes_fcfa"]
        self.assertAlmostEqual(d["total_fcfa"], somme, delta=1)


class SummaryTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Salon")

    def test_summary_renvoie_les_quatre_indicateurs(self):
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("450.00"),
            courant=Decimal("2.0"), energie=Decimal("0.45"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for cle in ("puissance_instantanee", "consommation_jour_kwh",
                    "facture_estimee_fcfa", "alertes_actives"):
            self.assertIn(cle, response.data)
        self.assertEqual(response.data['puissance_instantanee'], 450)


def _texte_csv(response):
    """Corps d'une réponse CSV, streamée (StreamingHttpResponse) ou non."""
    if getattr(response, 'streaming', False):
        return b''.join(response.streaming_content).decode('utf-8')
    return response.content.decode('utf-8')


class ExportCSVTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Salon")
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("450.00"),
            courant=Decimal("2.0"), energie=Decimal("0.45"), timestamp=timezone.now())

    def test_export_csv_du_client(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/?period=month')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', response['Content-Type'])
        contenu = _texte_csv(response)
        self.assertIn('Horodatage', contenu)
        self.assertIn('Capteur Salon', contenu)

    def test_export_csv_refuse_sans_authentification(self):
        response = self.client.get('/api/analytics/export/')
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_export_csv_bom_et_conventions_francaises(self):
        """Le CSV doit s'ouvrir proprement dans Excel FR : BOM UTF-8, « ; »,
        horodatage local lisible et décimales à virgule (nombres, pas du texte)."""
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/?period=month')
        contenu = _texte_csv(response)
        self.assertTrue(contenu.startswith('﻿'))
        ligne_mesure = contenu.splitlines()[1]
        self.assertIn(';', ligne_mesure)
        self.assertIn('450,00', ligne_mesure)   # puissance, virgule décimale
        self.assertNotIn('T', ligne_mesure.split(';')[0])  # plus d'ISO 8601 brut

    def test_export_csv_filtre_par_capteur(self):
        autre = Capteur.objects.create(client=self.un_client, nom="Capteur Cuisine")
        MesureEnergie.objects.create(
            capteur=autre, puissance=Decimal("120.00"),
            courant=Decimal("0.6"), energie=Decimal("0.12"), timestamp=timezone.now())
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get(f'/api/analytics/export/?sensor_id={self.capteur.id}')
        contenu = _texte_csv(response)
        self.assertIn('Capteur Salon', contenu)
        self.assertNotIn('Capteur Cuisine', contenu)

    def test_export_csv_sensor_id_invalide_400_pas_500(self):
        """Un sensor_id non-UUID doit répondre 400 (pas une ValidationError → 500)."""
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/?sensor_id=INEXISTANT')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_csv_date_invalide_400(self):
        """Une date illisible n'est JAMAIS ignorée en silence (sinon on exporterait
        tout l'historique en croyant exporter une plage) : 400, comme le PDF."""
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/?date_from=garbage')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_csv_plage_inversee_400(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/?date_from=2026-07-03&date_to=2026-07-01')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ExportPDFTests(APITestCase):
    """Les deux documents PDF (historique + rapport mensuel) doivent se générer
    en un vrai PDF téléchargeable, y compris pour un compte sans mesures."""

    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Salon")
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("450.00"),
            courant=Decimal("2.0"), energie=Decimal("0.45"), timestamp=timezone.now())

    def _assert_pdf(self, response, prefixe_nom):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(prefixe_nom, response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_pdf_historique(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/pdf/?period=month')
        self._assert_pdf(response, 'aoceda_historique_')

    def test_pdf_historique_sensor_id_invalide_400_pas_500(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/pdf/?sensor_id=INEXISTANT')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pdf_rapport_mensuel(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/export/rapport-mensuel/')
        self._assert_pdf(response, 'aoceda_rapport_mensuel_')

    def test_pdf_rapport_mensuel_sans_capteur_reste_honnete(self):
        seul = creer_client(email="vide@test.ci")
        self.client.force_authenticate(user=seul)
        response = self.client.get('/api/analytics/export/rapport-mensuel/')
        self._assert_pdf(response, 'aoceda_rapport_mensuel_')

    def test_pdf_refuse_sans_authentification(self):
        for url in ('/api/analytics/export/pdf/', '/api/analytics/export/rapport-mensuel/'):
            response = self.client.get(url)
            self.assertIn(response.status_code,
                          [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class AdminStatsTests(APITestCase):
    def setUp(self):
        self.admin = Administrateur(email="admin@test.ci", nom="Admin",
                                    role='admin', is_staff=True)
        self.admin.set_password("Password123!")
        self.admin.save()
        self.un_client = creer_client()

    def test_stats_globales_pour_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/analytics/admin/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['clients_total'], 1)
        self.assertIn('capteurs_hors_ligne', response.data)

    def test_stats_refusees_pour_un_client(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/admin/stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CreditPrepayeAPITests(APITestCase):
    """Crédit prépayé exposé par le résumé/la facture + recharge réelle."""

    def setUp(self):
        self.client_prepaye = Client(email="cp@test.ci", nom="CP", role='client',
                                     typeCompteur='prepaye', creditPrepaye_FCFA=Decimal('30000'))
        self.client_prepaye.set_password("Password123!")
        self.client_prepaye.save()
        self.capteur = Capteur.objects.create(client=self.client_prepaye, nom="Cap", actif=True)
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal('500'), courant=Decimal('2.5'),
            energie=Decimal('1.0'), timestamp=timezone.now())

    def test_summary_contient_credit_prepaye(self):
        self.client.force_authenticate(user=self.client_prepaye)
        response = self.client.get('/api/analytics/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('credit_prepaye', response.data)
        self.assertIsNotNone(response.data['credit_prepaye'])
        self.assertIn('restant_fcfa', response.data['credit_prepaye'])

    def test_recharge_augmente_le_credit(self):
        self.client.force_authenticate(user=self.client_prepaye)
        response = self.client.post('/api/analytics/recharge/', {"montant": 5000})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client_prepaye.refresh_from_db()
        self.assertEqual(self.client_prepaye.creditPrepaye_FCFA, Decimal('35000.00'))

    def test_recharge_montant_invalide_refuse(self):
        self.client.force_authenticate(user=self.client_prepaye)
        response = self.client.post('/api/analytics/recharge/', {"montant": -10})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recharge_refusee_pour_postpaye(self):
        postpaye = Client(email="pp@test.ci", nom="PP", role='client', typeCompteur='postpaye')
        postpaye.set_password("Password123!"); postpaye.save()
        self.client.force_authenticate(user=postpaye)
        response = self.client.post('/api/analytics/recharge/', {"montant": 5000})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_summary_compte_sans_capteur_mode_vide(self):
        vide = Client(email="vide@test.ci", nom="Vide", role='client')
        vide.set_password("Password123!"); vide.save()
        self.client.force_authenticate(user=vide)
        response = self.client.get('/api/analytics/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['mode'], 'vide')
        self.assertEqual(response.data['puissance_instantanee'], 0)
