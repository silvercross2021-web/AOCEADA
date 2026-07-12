"""Tests du tableau de bord de l'administration AOCEDA."""
from decimal import Decimal

from django.test import TestCase, Client as TestClient
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import Utilisateur, Client
from apps.sensors.models import Dispositif, Capteur, MesureEnergie
from apps.alerts.models import Alerte


class AdminDashboardTests(TestCase):
    """Vérifie la page d'accueil de l'admin et l'endpoint /admin-stats-data/."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_superuser(
            email='admin@aoceda.ci', nom='Admin AOCEDA', password='Password123!'
        )
        cls.client_aoceda = Client.objects.create_user(
            email='client@test.ci', nom='Client Test', password='Password123!'
        )
        dispositif = Dispositif.objects.create(
            client=cls.client_aoceda, apiKeyDevice='clef-test-001', estConnecté=True
        )
        capteur = Capteur.objects.create(
            client=cls.client_aoceda, dispositif=dispositif, nom='Capteur salon'
        )
        now = timezone.now()
        for h in range(1, 4):
            MesureEnergie.objects.create(
                capteur=capteur,
                puissance=Decimal('500.00'),
                courant=Decimal('2.500'),
                energie=Decimal('0.500000'),
                timestamp=now - timedelta(hours=h),
            )
        # Capteur ayant émis récemment → considéré « en ligne » (seuil 10 min).
        # « Hors ligne » = capteur actif sans relevé récent (définition alignée
        # sur analytics.AdminStatsView).
        capteur.derniereLecture = now
        capteur.save(update_fields=['derniereLecture'])
        Alerte.objects.create(
            client=cls.client_aoceda,
            type='DEPASSEMENT_SEUIL',
            message='Seuil dépassé sur Capteur salon',
        )

    def setUp(self):
        self.http = TestClient()
        self.http.force_login(self.admin)

    def test_admin_index_contient_le_dashboard(self):
        reponse = self.http.get('/admin/')
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        # Branding
        self.assertIn('AOCEDA', html)
        self.assertIn('Supervision de la plateforme', html)
        # Dashboard injecté avant la liste des applications
        self.assertIn('adm-dash', html)
        self.assertIn('chart.umd.min.js', html)
        self.assertIn('chart-ca', html)
        self.assertIn('chart-alertes', html)
        self.assertIn('chart-conso', html)
        self.assertIn('chart-inscrits', html)

    def test_admin_stats_data_retourne_les_agregats(self):
        reponse = self.http.get('/admin-stats-data/')
        self.assertEqual(reponse.status_code, 200)
        data = reponse.json()

        kpi = data['kpi']
        self.assertEqual(kpi['clients_actifs'], 1)
        self.assertEqual(kpi['dispositifs_en_ligne'], 1)
        self.assertEqual(kpi['dispositifs_total'], 1)
        self.assertEqual(kpi['capteurs_actifs'], 1)
        self.assertEqual(kpi['capteurs_sans_donnees'], 0)
        self.assertEqual(kpi['mesures_24h'], 3)
        self.assertEqual(kpi['alertes_non_lues'], 1)

        # Consommation 7 jours : 7 points, somme = 3 x 0,5 kWh
        self.assertEqual(len(data['conso_7j']['labels']), 7)
        self.assertAlmostEqual(sum(data['conso_7j']['valeurs']), 1.5, places=3)

        # Alertes 30 jours : libellé français du type
        self.assertIn('Dépassement de seuil', data['alertes_30j']['labels'])
        self.assertEqual(sum(data['alertes_30j']['valeurs']), 1)

        # CA 6 mois : 6 derniers mois
        self.assertEqual(len(data['ca_6m']['labels']), 6)

    def test_admin_stats_data_refuse_les_anonymes(self):
        anonyme = TestClient()
        reponse = anonyme.get('/admin-stats-data/')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/admin/login/', reponse.url)

