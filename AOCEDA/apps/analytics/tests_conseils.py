"""Conseils du tableau de bord : calculés sur les vraies mesures (19/10/2026), jamais inventés."""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework import status
from rest_framework.test import APITestCase

from apps.sensors.models import Capteur, MesureEnergie

from .conseils import conseils_du_client, regles
from .meteo import ville_du_client
from .models import MeteoJour
from .tests import creer_client


def _m(capteur, quand, energie="0.30", puissance="300.00"):
    return MesureEnergie.objects.create(capteur=capteur, puissance=Decimal(puissance), courant=Decimal("1.5"),
                                        energie=Decimal(energie), timestamp=quand)


def _kinds(client, maintenant=None):
    return [c['kind'] for c in regles(client, maintenant)]


class ConseilsReglesTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.cl = creer_client()
        self.salon = Capteur.objects.create(client=self.cl, nom="Salon", etatCourant='OFF')
        self.maintenant = timezone.now()

    def _jour(self, capteur, jours_avant, heure_locale, energie, puissance="300.00"):
        base = timezone.localtime(self.maintenant).replace(hour=heure_locale, minute=10, second=0, microsecond=0)
        return _m(capteur, base - timedelta(days=jours_avant), energie, puissance)

    def test_sans_mesure_aucune_regle(self):
        self.assertEqual(regles(self.cl, self.maintenant), [])

    def test_pic_au_dessus_de_la_capacite(self):
        """10 A = 2 200 W : un pic de 2 600 W conseille d'éviter la disjonction, avec les vrais chiffres."""
        self._jour(self.salon, 1, 12, "0.5", puissance="2600.00")
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'pic')
        self.assertEqual(c['chiffres'], {'nom': 'Salon', 'pic_w': 2600, 'capacite_w': 2200})
        self.assertIn('2 600 W', c['titre'])

    def test_pic_sous_la_capacite_pas_de_conseil(self):
        self._jour(self.salon, 1, 12, "0.5", puissance="1500.00")
        self.assertNotIn('pic', _kinds(self.cl, self.maintenant))

    def test_nuit_elevee(self):
        for j in range(1, 6):
            self._jour(self.salon, j, 23, "0.40")      # nuit
            self._jour(self.salon, j, 14, "0.20")      # jour
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'nuit')
        self.assertEqual(c['chiffres']['part'], 67)
        self.assertEqual(c['chiffres']['nom'], 'Salon')

    def test_nuit_faible_pas_de_conseil(self):
        for j in range(1, 6):
            self._jour(self.salon, j, 14, "0.50")
        self.assertNotIn('nuit', _kinds(self.cl, self.maintenant))

    def test_hausse_par_rapport_a_la_semaine_d_avant(self):
        for j in range(1, 6):
            self._jour(self.salon, j, 14, "0.60")      # cette semaine : 3,0 kWh
        for j in range(8, 13):
            self._jour(self.salon, j, 14, "0.30")      # semaine d'avant : 1,5 kWh
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'hausse')
        self.assertEqual(c['chiffres']['pct'], 100)
        self.assertEqual(c['chiffres']['kwh'], 3.0)

    def test_pas_de_hausse_sans_semaine_d_avant(self):
        """Aucune mesure la semaine d'avant : pas de pourcentage inventé."""
        for j in range(1, 6):
            self._jour(self.salon, j, 14, "0.60")
        self.assertNotIn('hausse', _kinds(self.cl, self.maintenant))

    def test_appareil_allume_depuis_longtemps(self):
        self.salon.etatCourant = 'ON'
        self.salon.etatDepuis = self.maintenant - timedelta(hours=10)
        self.salon.derniereLecture = self.maintenant
        self.salon.save()
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'allume')
        self.assertEqual(c['chiffres']['heures'], 10)

    def test_allume_mais_boitier_muet_pas_de_conseil(self):
        """Boîtier hors ligne : on ne sait pas si l'appareil tourne encore, donc aucun conseil."""
        self.salon.etatCourant = 'ON'
        self.salon.etatDepuis = self.maintenant - timedelta(hours=10)
        self.salon.derniereLecture = self.maintenant - timedelta(hours=2)
        self.salon.save()
        self.assertNotIn('allume', _kinds(self.cl, self.maintenant))

    def test_appareil_dominant(self):
        autre = Capteur.objects.create(client=self.cl, nom="Cuisine")
        for j in range(1, 4):
            self._jour(self.salon, j, 14, "0.80")
            self._jour(autre, j, 14, "0.20")
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'dominant')
        self.assertEqual(c['chiffres']['part'], 80)

    def test_chaleur_annoncee_avec_climatiseur(self):
        clim = Capteur.objects.create(client=self.cl, nom="Climatiseur chambre")
        self._jour(clim, 1, 14, "1.0")
        MeteoJour.objects.create(ville=ville_du_client(self.cl), date=timezone.localdate() + timedelta(days=1),
                                 t_moy=Decimal("30.0"), t_max=Decimal("35.0"), prevue=True)
        c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'chaleur')
        self.assertEqual(c['chiffres']['t_max'], 35)

    def test_chaleur_sans_climatiseur_pas_de_conseil(self):
        self._jour(self.salon, 1, 14, "1.0")
        MeteoJour.objects.create(ville=ville_du_client(self.cl), date=timezone.localdate() + timedelta(days=1),
                                 t_moy=Decimal("30.0"), t_max=Decimal("35.0"), prevue=True)
        self.assertNotIn('chaleur', _kinds(self.cl, self.maintenant))

    def test_credit_prepaye_bientot_epuise(self):
        self.cl.typeCompteur = 'prepaye'
        self.cl.creditPrepaye_FCFA = Decimal("300")
        self.cl.save()
        for j in range(1, 8):                                 # ~10 kWh/jour : 300 F ne durent pas 5 jours
            for h in range(0, 24, 2):
                self._jour(self.salon, j, h, "0.8")
        kinds = _kinds(self.cl, self.maintenant)
        self.assertIn('credit', kinds)

    def test_tranche_postpaye_proche_du_seuil(self):
        from unittest import mock
        faux = {"seuil": Decimal("396"), "kwh": Decimal("350"), "type_tarif": "general",
                "jours_avant_seuil": 4.0, "prix_t1": 1, "prix_t2": 1}
        with mock.patch('apps.alerts.utils.etat_tranche', return_value=faux):
            c = next(c for c in regles(self.cl, self.maintenant) if c['kind'] == 'tranche')
        self.assertEqual(c['chiffres']['reste_kwh'], 46.0)


class ConseilsDuClientTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.cl = creer_client()
        self.salon = Capteur.objects.create(client=self.cl, nom="Salon")

    def test_sans_mesure_deux_conseils_generaux_distincts_et_marques(self):
        d = conseils_du_client(self.cl)
        self.assertFalse(d['mesures_recentes'])
        self.assertEqual([c['kind'] for c in d['conseils']], ['general', 'general'])
        self.assertTrue(all(not c['mesure'] for c in d['conseils']))
        self.assertNotEqual(d['conseils'][0]['titre'], d['conseils'][1]['titre'])

    def test_les_conseils_mesures_passent_avant_le_general(self):
        _m(self.salon, timezone.now() - timedelta(hours=3), "0.5", "2600.00")
        d = conseils_du_client(self.cl)
        self.assertEqual(d['conseils'][0]['kind'], 'pic')
        self.assertTrue(d['conseils'][0]['mesure'])
        self.assertEqual(d['conseils'][-1]['kind'], 'general')    # complète jusqu'à 2 conseils
        self.assertEqual(len(d['conseils']), 2)

    def test_endpoint(self):
        _m(self.salon, timezone.now() - timedelta(hours=3), "0.5", "2600.00")
        self.client.force_authenticate(user=self.cl)
        r = self.client.get('/api/analytics/conseils/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['conseils'][0]['kind'], 'pic')
        self.assertTrue(r.data['mesures_recentes'])

    def test_endpoint_refuse_un_non_client(self):
        r = self.client.get('/api/analytics/conseils/')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_isolation_entre_clients(self):
        autre = creer_client("autre@test.ci")
        cap = Capteur.objects.create(client=autre, nom="Autre")
        _m(cap, timezone.now() - timedelta(hours=3), "0.5", "2600.00")
        self.assertEqual([c['kind'] for c in conseils_du_client(self.cl)['conseils']], ['general', 'general'])
