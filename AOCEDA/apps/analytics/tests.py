"""Tests de l'application analytics : moteur tarifaire CIE officiel,
prévision de facturation FCFA, indicateurs, export CSV, statistiques admin."""
from decimal import Decimal
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import Client, Administrateur
from apps.sensors.models import Capteur, MesureEnergie
from .models import Prevision
from .tarifs_cie import (calculer_facture_bimestre, calculer_cout_prepaye, prix_kwh_prepaye,
                         periode_contenant)


class MoteurTarifaireCIETests(APITestCase):
    """Valide le moteur contre l'arrêté interministériel n° 1355/MMPE/MFB du 27/12/2023
    (texte publié par la CIE). Chaque montant attendu est recalculé à la main depuis les
    articles cités : prime fixe, tranches par BIMESTRE, redevances et taxes TTC."""

    def test_art2_social_5a_70kwh_sous_le_seuil(self):
        d = calculer_facture_bimestre(70, amperage=5, type_tarif='social')
        self.assertEqual(d['seuil_t1_kwh'], Decimal('80.00'))      # 80 kWh / bimestre
        self.assertEqual(d['tranche2_kwh'], Decimal('0.00'))
        # 70 × 31,72 + prime 614,90 + rural (100 + 70 × 1) + RTI 70 × 2 + ordures 70 × 2,5
        self.assertEqual(d['total_fcfa'], Decimal('3320.30'))

    def test_art2_social_5a_120kwh_progressif(self):
        d = calculer_facture_bimestre(120, amperage=5, type_tarif='social')
        self.assertEqual(d['tranche1_kwh'], Decimal('80.00'))
        self.assertEqual(d['tranche2_kwh'], Decimal('40.00'))
        self.assertGreater(d['tranche2_prix'], d['tranche1_prix'])  # social : progressif
        # 80 × 31,72 + 40 × 65,11 + 614,90 + (100 + 120) + 240 + 300
        self.assertEqual(d['total_fcfa'], Decimal('6516.90'))

    def test_art3_general_5a_existe(self):
        """Le tarif domestique GÉNÉRAL 5A existe (article 3) : prime 1 618,04 F par kVA."""
        d = calculer_facture_bimestre(250, amperage=5, type_tarif='general')
        self.assertEqual(d['type_tarif'], 'general')
        self.assertEqual(d['seuil_t1_kwh'], Decimal('198.00'))     # 180 h × 1,1 kVA
        self.assertEqual(d['prime_fixe_fcfa'], Decimal('1779.84'))  # 1 618,04 × 1,1
        # 198 × 86,92 + 52 × 75,34 + 1 779,84 + (100 + 250 × 1,06) + 500 + 625
        self.assertEqual(d['total_fcfa'], Decimal('24397.68'))

    def test_art4_general_10a_300kwh(self):
        d = calculer_facture_bimestre(300, amperage=10, type_tarif='general')
        self.assertEqual(d['seuil_t1_kwh'], Decimal('396.00'))     # 180 h × 2,2 kVA
        self.assertEqual(d['prime_fixe_fcfa'], Decimal('3559.69'))  # 1 618,04 × 2,2
        self.assertEqual(d['taxe_fixe_fcfa'], Decimal('2100.00'))   # rural 100 + RTI 2 000
        # 300 × 86,92 + 3 559,69 + (100 + 318) + 2 000 + 750
        self.assertEqual(d['total_fcfa'], Decimal('32803.69'))

    def test_art4_general_10a_540kwh_degressif(self):
        d = calculer_facture_bimestre(540, amperage=10, type_tarif='general')
        self.assertEqual(d['tranche1_kwh'], Decimal('396.00'))
        self.assertEqual(d['tranche2_kwh'], Decimal('144.00'))
        self.assertLess(d['tranche2_prix'], d['tranche1_prix'])     # général : dégressif
        self.assertEqual(d['total_fcfa'], Decimal('52851.37'))

    def test_art5_general_15a_700kwh(self):
        d = calculer_facture_bimestre(700, amperage=15, type_tarif='general')
        self.assertEqual(d['seuil_t1_kwh'], Decimal('594.00'))     # 180 h × 3,3 kVA
        self.assertEqual(d['prime_fixe_fcfa'], Decimal('5873.47'))  # 1 779,84 × 3,3
        self.assertEqual(d['total_fcfa'], Decimal('76046.91'))

    def test_methode_anare_10a_348kwh(self):
        """Exemple de l'ANARE-CI (10A, 348 kWh) refait aux prix de 2024 : énergie
        348 × 86,92 ; prime 3 559,69 ; rural 100 + 368,88 ; RTI 2 000 ; ordures 870."""
        d = calculer_facture_bimestre(348, amperage=10, type_tarif='general')
        self.assertEqual(d['total_fcfa'], Decimal('37146.73'))

    def test_rti_plafonnee_a_2000_au_social(self):
        d = calculer_facture_bimestre(1200, amperage=5, type_tarif='social')
        # rural 1 200 × 1 + ordures 1 200 × 2,5 + RTI min(2 400, 2 000)
        self.assertEqual(d['taxes_variable_fcfa'], Decimal('6200.00'))

    def test_ordures_menageres_hors_abidjan(self):
        d = calculer_facture_bimestre(300, amperage=10, type_tarif='general', abidjan=False)
        self.assertEqual(d['total_fcfa'], Decimal('32353.69'))     # 1,00 F/kWh au lieu de 2,50

    def test_pas_de_double_tva(self):
        """Les prix de l'arrêté sont TTC : jamais +18 % en plus."""
        d = calculer_facture_bimestre(100, amperage=10, type_tarif='general')
        attendu = (Decimal('100') * Decimal('86.92') + Decimal('3559.69')
                   + Decimal('100') + Decimal('106') + Decimal('2000') + Decimal('250'))
        self.assertEqual(d['total_fcfa'], attendu)

    def test_social_impossible_hors_5a_retombe_en_general(self):
        d = calculer_facture_bimestre(100, amperage=10, type_tarif='social')
        self.assertEqual(d['type_tarif'], 'general')

    def test_zero_kwh_paie_quand_meme_la_part_fixe(self):
        d = calculer_facture_bimestre(0, amperage=10, type_tarif='general')
        self.assertEqual(d['total_fcfa'], Decimal('5659.69'))       # prime + rural 100 + RTI 2 000

    def test_prepaye_prix_unique_sans_tranche(self):
        """Articles 10 à 13 : un prix par kWh, sans tranche ni prime fixe séparée."""
        self.assertEqual(prix_kwh_prepaye(10, 'general')[0], Decimal('100.52'))
        self.assertEqual(prix_kwh_prepaye(5, 'general')[0], Decimal('99.25'))
        self.assertEqual(prix_kwh_prepaye(5, 'social')[0], Decimal('54.71'))
        self.assertEqual(prix_kwh_prepaye(15, 'general')[0], Decimal('110.17'))
        d = calculer_cout_prepaye(1000, amperage=10, type_tarif='general')
        self.assertEqual(d['tranche2_kwh'], Decimal('0.00'))
        self.assertEqual(d['prime_fixe_fcfa'], Decimal('0.00'))
        self.assertEqual(d['total_fcfa'], Decimal('100520.00'))      # linéaire, même au-delà de 396 kWh

    def test_bimestres_des_deux_groupes_de_facturation(self):
        from datetime import date
        from types import SimpleNamespace
        gf1 = SimpleNamespace(typeCompteur='postpaye', groupeFacturation='GF1')
        gf2 = SimpleNamespace(typeCompteur='postpaye', groupeFacturation='GF2')
        pre = SimpleNamespace(typeCompteur='prepaye')
        self.assertEqual(periode_contenant(gf1, date(2026, 10, 14)), (date(2026, 9, 1), date(2026, 10, 31)))
        self.assertEqual(periode_contenant(gf2, date(2026, 10, 14)), (date(2026, 10, 1), date(2026, 11, 30)))
        self.assertEqual(periode_contenant(gf2, date(2027, 1, 10)), (date(2026, 12, 1), date(2027, 1, 31)))
        self.assertEqual(periode_contenant(pre, date(2026, 10, 14)), (date(2026, 10, 1), date(2026, 10, 31)))


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
        # Clé = mois de DÉBUT de la période en cours (bimestre pour un postpayé)
        annee_mois = periode_contenant(self.un_client, timezone.localdate())[0].strftime("%Y-%m")
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
        # 10A général, bimestre : au minimum la prime fixe (3 559,69) + rural 100 + RTI 2 000
        self.assertGreater(montant, Decimal("5659"))

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
        # Appareil allumé, comme l'ingestion le marque quand elle crée une mesure
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Capteur Salon",
                                              etatCourant='ON')

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

    def test_puissance_instantanee_nulle_des_que_l_appareil_est_eteint(self):
        """Régression 12/10/2026 : la dernière mesure d'un appareil qu'on vient
        d'éteindre restait comptée jusqu'à 60 s (« ça continue de compter »)."""
        MesureEnergie.objects.create(
            capteur=self.capteur, puissance=Decimal("450.00"),
            courant=Decimal("2.0"), energie=Decimal("0.45"), timestamp=timezone.now())
        self.capteur.etatCourant = 'OFF'
        self.capteur.save(update_fields=['etatCourant'])
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/analytics/summary/')
        self.assertEqual(response.data['puissance_instantanee'], 0)


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
