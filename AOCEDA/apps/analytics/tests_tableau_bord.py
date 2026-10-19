"""Tableau de bord client, corrections de l'audit du 19/10/2026 : règle unique des alertes, écart « à date », état réel
du boîtier (en ligne / dernier contact), série du graphe (journée depuis minuit, vrais 0 d'un appareil éteint) et GET
sans écriture en base."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework import status
from rest_framework.test import APITestCase

from apps.alerts.models import Alerte
from apps.alerts.utils import alertes_du_client
from apps.sensors.models import Capteur, MesureEnergie, PresenceCapteur

from .models import Prevision
from .tests import creer_client
from .views import ecart_a_date, etat_contact


def _mesure(capteur, quand, energie="0.50", puissance="500.00"):
    return MesureEnergie.objects.create(capteur=capteur, puissance=Decimal(puissance), courant=Decimal("2.2"),
                                        energie=Decimal(energie), timestamp=quand)


class AlertesRegleUniqueTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        Alerte.objects.create(client=self.un_client, type='CREDIT_BAS', message="Crédit bas")
        for i in range(5):
            Alerte.objects.create(client=self.un_client, type='DEPASSEMENT_SEUIL', message=f"Seuil {i}")

    def test_credit_bas_ignore_pour_un_postpaye(self):
        """Un compteur postpayé n'a pas de crédit : l'ancienne alerte ne compte nulle part."""
        self.assertEqual(alertes_du_client(self.un_client).count(), 5)
        self.client.force_authenticate(user=self.un_client)
        self.assertEqual(self.client.get('/api/analytics/summary/').data['alertes_actives'], 5)

    def test_credit_bas_garde_pour_un_prepaye(self):
        self.un_client.typeCompteur = 'prepaye'
        self.un_client.save(update_fields=['typeCompteur'])
        self.assertEqual(alertes_du_client(self.un_client).count(), 6)

    def test_limit_renvoie_les_n_plus_recentes_sans_pagination(self):
        self.client.force_authenticate(user=self.un_client)
        r = self.client.get('/api/alertes/?limit=3')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data, list)
        self.assertEqual(len(r.data), 3)
        self.assertNotIn('CREDIT_BAS', [a['type'] for a in r.data])
        self.assertTrue(all(a['type_display'] for a in r.data))   # libellé lisible fourni par le serveur


class EtatBoitierTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Salon", etatCourant='ON')
        self.client.force_authenticate(user=self.un_client)

    def test_boitier_muet_puissance_et_conso_inconnues(self):
        """Dernière mesure il y a 3 jours : ni « 0 W » ni « 0 kWh », mais inconnu, avec la date du dernier contact."""
        vieux = timezone.now() - timedelta(days=3)
        _mesure(self.capteur, vieux)
        d = self.client.get('/api/analytics/summary/').data
        self.assertFalse(d['en_ligne'])
        self.assertIsNone(d['puissance_instantanee'])
        self.assertIsNone(d['consommation_jour_kwh'])
        self.assertIsNotNone(d['dernier_contact'])
        f = self.client.get('/api/analytics/facture/').data
        self.assertFalse(f['en_ligne'])
        self.assertIsNotNone(f['dernier_contact'])

    def test_boitier_qui_repond_en_ligne(self):
        _mesure(self.capteur, timezone.now())
        d = self.client.get('/api/analytics/summary/').data
        self.assertTrue(d['en_ligne'])
        self.assertEqual(d['puissance_instantanee'], 500)

    def test_contact_par_la_derniere_lecture_meme_sans_consommation(self):
        """Appareil éteint mais boîtier qui répond : en ligne (la lecture compte, pas seulement la consommation)."""
        self.capteur.derniereLecture = timezone.now()
        self.capteur.save(update_fields=['derniereLecture'])
        self.assertTrue(etat_contact(self.un_client)['en_ligne'])

    def test_compte_jamais_mesure(self):
        c = etat_contact(self.un_client)
        self.assertFalse(c['en_ligne'])
        self.assertIsNone(c['dernier_contact'])


class EcartADateTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Salon")

    def test_sans_mesure_avant_aucun_pourcentage(self):
        _mesure(self.capteur, timezone.now())
        e = ecart_a_date(self.un_client)
        self.assertIsNone(e['pct'])
        self.assertTrue(e['libelle'].startswith('du '))

    def test_meme_duree_de_la_periode_precedente(self):
        """Seules les mesures de la période d'avant tombées dans la MÊME durée comptent : la fin de la période
        d'avant (plus tard que « à date ») n'entre pas dans la comparaison."""
        from .tarifs_cie import periode_contenant, periode_precedente
        debut, _ = periode_contenant(self.un_client, timezone.localdate())
        p_debut, p_fin = periode_precedente(self.un_client, debut)
        tz = timezone.get_current_timezone()
        maintenant = timezone.localtime()
        ecoule = maintenant - timezone.make_aware(timezone.datetime.combine(debut, timezone.datetime.min.time()), tz)
        t0 = timezone.make_aware(timezone.datetime.combine(p_debut, timezone.datetime.min.time()), tz)
        _mesure(self.capteur, t0 + timedelta(minutes=5), energie="20.00")          # dans la durée « à date »
        if ecoule < timedelta(days=50):
            fin_avant = timezone.make_aware(timezone.datetime.combine(p_fin, timezone.datetime.min.time()), tz)
            _mesure(self.capteur, fin_avant + timedelta(hours=12), energie="400.00")  # après : ignorée
        _mesure(self.capteur, maintenant - timedelta(minutes=1), energie="20.00")
        e = ecart_a_date(self.un_client)
        self.assertIsNotNone(e['precedent_fcfa'])
        self.assertIsNotNone(e['pct'])
        self.assertLess(abs(e['pct']), 50)    # 20 kWh contre 20 kWh : écart faible, pas « -95 % »


class SerieGrapheTests(APITestCase):
    def setUp(self):
        self.un_client = creer_client()
        self.capteur = Capteur.objects.create(client=self.un_client, nom="Salon")
        self.client.force_authenticate(user=self.un_client)

    def test_aujourd_hui_commence_a_minuit(self):
        minuit = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        _mesure(self.capteur, minuit - timedelta(hours=2))                 # hier soir : hors de « aujourd'hui »
        _mesure(self.capteur, timezone.now() - timedelta(minutes=1))
        data = self.client.get('/api/mesures/serie/?period=day').data
        self.assertTrue(data)
        self.assertTrue(all(timezone.datetime.fromisoformat(d['timestamp']) >= minuit for d in data))

    def test_heure_de_presence_sans_mesure_donne_un_vrai_zero(self):
        """Le boîtier a envoyé « éteint » pendant une heure : 0 kWh (vrai) ; une heure sans aucune trace reste absente."""
        heure = timezone.now().replace(minute=0, second=0, microsecond=0)
        PresenceCapteur.objects.create(capteur=self.capteur, heure=heure)
        data = self.client.get('/api/mesures/serie/?period=day').data
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['energie'], 0.0)


class GetSansEcritureTests(APITestCase):
    def test_tableau_de_bord_n_ecrit_rien(self):
        """Les GET appelés toutes les 30 s par le tableau de bord n'écrivent plus en base (« database is locked »)."""
        un_client = creer_client()
        capteur = Capteur.objects.create(client=un_client, nom="Salon", etatCourant='ON')
        _mesure(capteur, timezone.now())
        self.client.force_authenticate(user=un_client)
        avant = (Prevision.objects.count(), Alerte.objects.count())
        for url in ('/api/analytics/summary/', '/api/analytics/facture/', '/api/previsions/', '/api/alertes/?limit=3'):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK, url)
        self.assertEqual((Prevision.objects.count(), Alerte.objects.count()), avant)
