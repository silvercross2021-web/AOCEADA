"""Page Facturation (20/10/2026) : crédit prépayé compté depuis la première recharge, recharge robuste (NaN, plafond,
annulation d'une erreur), descriptif du tarif tout compris, ce que couvre le montant à ce jour, cycle de facturation."""
import importlib
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from apps.sensors.models import Capteur, MesureEnergie

from .models import RechargeCredit
from .tarifs_cie import descriptif_tarif, periode_contenant


def _client(email, **kw):
    c = Client(email=email, nom="Test", role='client', **kw)
    c.set_password("Password123!")
    c.save()
    return c


def _mesure(cap, kwh, quand):
    return MesureEnergie.objects.create(capteur=cap, puissance=Decimal('500'), courant=Decimal('2.5'),
                                        energie=Decimal(str(kwh)), timestamp=quand)


class CreditDepuisLeReleveTests(APITestCase):
    """Le crédit prépayé ne se recharge PAS dans AOCEDA (c'est la CIE) : il repart de la dernière lecture du compteur."""

    def setUp(self):
        self.cl = _client("prepaye.fact@test.ci", typeCompteur='prepaye')
        self.cap = Capteur.objects.create(client=self.cl, nom="Cap", actif=True)
        self.client.force_authenticate(user=self.cl)

    def credit(self):
        return self.client.get('/api/analytics/summary/').data['credit_prepaye']

    def releve(self, kwh):
        return self.client.post('/api/analytics/credit/releve/', {"kwh": kwh}, format='json')

    def test_sans_lecture_ni_credit_aucun_solde_n_est_invente(self):
        _mesure(self.cap, 300, timezone.now() - timedelta(days=40))
        self.assertIsNone(self.credit())

    def test_la_lecture_donne_le_credit_et_ignore_les_mesures_d_avant(self):
        _mesure(self.cap, 300, timezone.now() - timedelta(days=40))        # consommation d'avant la lecture : ignorée
        r = self.releve("50,5")
        self.assertEqual(r.status_code, 200, r.data)
        c = self.credit()
        self.assertEqual(c['source'], 'releve')
        self.assertAlmostEqual(c['restant_kwh'], 50.5, places=2)
        self.assertAlmostEqual(c['restant_fcfa'], 50.5 * 100.52, places=1)

    def test_la_consommation_apres_la_lecture_est_deduite(self):
        self.releve(50)
        _mesure(self.cap, 10, timezone.now() + timedelta(seconds=5))
        self.assertAlmostEqual(self.credit()['restant_kwh'], 40.0, places=2)

    def test_une_nouvelle_lecture_remplace_la_precedente(self):
        self.releve(50)
        _mesure(self.cap, 10, timezone.now())                               # entre les deux lectures
        self.releve(200)                                                    # achat d'énergie à la CIE, nouvelle lecture
        self.assertAlmostEqual(self.credit()['restant_kwh'], 200.0, places=2)

    def test_annuler_la_lecture_sans_credit_initial_efface_le_credit(self):
        self.releve(50)
        self.client.post('/api/analytics/credit/releve/', {"annuler": True}, format='json')
        self.assertIsNone(self.credit())

    def test_valeurs_refusees(self):
        for v in ('NaN', 'Infinity', -1, 200000, 'abc', None, ''):
            self.assertEqual(self.releve(v).status_code, 400, f"{v!r}")

    def test_plus_aucune_route_de_recharge(self):
        for url in ('/api/analytics/recharge/', '/api/analytics/recharge/historique/'):
            self.assertEqual(self.client.post(url, {"montant": 5000}, format='json').status_code, 404, url)

    def test_credit_initial_saisi_par_le_technicien_reste_pris_en_compte(self):
        ancien = _client("ancien.fact@test.ci", typeCompteur='prepaye', creditPrepaye_FCFA=Decimal('30000'))
        cap = Capteur.objects.create(client=ancien, nom="Cap", actif=True)
        _mesure(cap, 5, timezone.now())
        self.client.force_authenticate(user=ancien)
        self.assertAlmostEqual(self.credit()['restant_fcfa'], 30000 - 5 * 100.52, places=1)

    def test_credit_initial_date_ignore_la_consommation_d_avant(self):
        ancien = _client("date.fact@test.ci", typeCompteur='prepaye', creditPrepaye_FCFA=Decimal('20000'))
        cap = Capteur.objects.create(client=ancien, nom="Cap", actif=True)
        _mesure(cap, 300, timezone.now() - timedelta(days=40))
        RechargeCredit.objects.create(client=ancien, montant_FCFA=Decimal('20000'))
        self.client.force_authenticate(user=ancien)
        self.assertEqual(self.credit()['restant_fcfa'], 20000.0)            # avant le 20/10/2026 : 0 (tout était déduit)

    def test_la_migration_date_un_credit_existant(self):
        ancien = _client("migre.fact@test.ci", typeCompteur='prepaye', creditPrepaye_FCFA=Decimal('12000'))
        postpaye = _client("pp.migre@test.ci", creditPrepaye_FCFA=Decimal('999'))
        deja = _client("deja.fact@test.ci", typeCompteur='prepaye', creditPrepaye_FCFA=Decimal('500'))
        RechargeCredit.objects.create(client=deja, montant_FCFA=Decimal('500'))
        mod = importlib.import_module('apps.analytics.migrations.0005_recharges_sans_date')
        from django.apps import apps as registre
        mod.dater_les_credits_existants(registre, None)
        mod.dater_les_credits_existants(registre, None)                    # rejouable sans doublon
        self.assertEqual(RechargeCredit.objects.filter(client=ancien).count(), 1)
        self.assertEqual(RechargeCredit.objects.get(client=ancien).montant_FCFA, Decimal('12000'))
        self.assertEqual(RechargeCredit.objects.filter(client=postpaye).count(), 0)
        self.assertEqual(RechargeCredit.objects.filter(client=deja).count(), 1)


class TarifDuClientTests(APITestCase):
    def test_general_10a_abidjan(self):
        d = descriptif_tarif(_client("t1.fact@test.ci", amperage=10, typeTarif='general'))
        self.assertEqual((d['regime'], d['seuil_t1_kwh'], d['sens']), ('postpaye', 396.0, 'degressif'))
        self.assertAlmostEqual(d['prix_t1'], 86.92 + 1.06 + 2.50, places=2)       # tout compris
        self.assertAlmostEqual(d['prix_t2'], 75.34 + 1.06 + 2.50, places=2)
        self.assertAlmostEqual(d['abonnement_periode'], 3559.69 + 100 + 2000, places=2)
        self.assertEqual(d['cycle']['groupe'], 'GF1')

    def test_hors_abidjan_ordures_a_1_franc(self):
        d = descriptif_tarif(_client("t2.fact@test.ci", amperage=10, typeTarif='general', horsAbidjan=True))
        self.assertAlmostEqual(d['prix_t1'], 86.92 + 1.06 + 1.00, places=2)

    def test_social_5a_progressif(self):
        d = descriptif_tarif(_client("t3.fact@test.ci", amperage=5, typeTarif='social'))
        self.assertEqual((d['seuil_t1_kwh'], d['sens']), (80.0, 'progressif'))
        self.assertAlmostEqual(d['prix_t1'], 31.72 + 1.00 + 2.50 + 2.00, places=2)
        self.assertGreater(d['prix_t2'], d['prix_t1'])

    def test_prepaye_sans_tranche(self):
        d = descriptif_tarif(_client("t4.fact@test.ci", amperage=10, typeCompteur='prepaye'))
        self.assertEqual((d['regime'], d['prix_kwh'], d['seuil_t1_kwh'], d['cycle']), ('prepaye', 100.52, None, None))

    def test_cycle_gf2(self):
        d = descriptif_tarif(_client("t5.fact@test.ci", groupeFacturation='GF2'))
        self.assertTrue(d['cycle']['libelle'].startswith('février-mars'))

    def test_endpoint_reserve_aux_clients(self):
        cl = _client("t6.fact@test.ci")
        self.client.force_authenticate(user=cl)
        r = self.client.get('/api/analytics/tarif/')
        self.assertEqual((r.status_code, r.data['regime']), (200, 'postpaye'))
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/analytics/tarif/').status_code, 401)

    def test_le_client_choisit_son_cycle_et_sa_commune(self):
        cl = _client("t7.fact@test.ci")
        self.client.force_authenticate(user=cl)
        r = self.client.put('/api/users/me/', {"groupeFacturation": "GF2", "horsAbidjan": True}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        cl.refresh_from_db()
        self.assertEqual((cl.groupeFacturation, cl.horsAbidjan), ('GF2', True))
        self.assertEqual(self.client.put('/api/users/me/', {"groupeFacturation": "GF9"}, format='json').status_code, 400)
        debut, fin = periode_contenant(cl, timezone.localdate().replace(month=3, day=15))
        self.assertEqual((debut.month, fin.month), (2, 3))                 # GF2 : février-mars


class FactureCouvertureTests(APITestCase):
    def setUp(self):
        self.cl = _client("couv.fact@test.ci")
        self.cap = Capteur.objects.create(client=self.cl, nom="Cap", actif=True)
        self.client.force_authenticate(user=self.cl)

    def facture(self):
        return self.client.get('/api/analytics/facture/').data

    def test_aucune_mesure_dans_la_periode(self):
        f = self.facture()
        self.assertTrue(f['aucune_mesure'])
        self.assertIsNone(f['mesure_depuis'])
        self.assertEqual(f['capteurs_suivis'], 1)
        self.assertEqual(f['tarif']['regime'], 'postpaye')
        self.assertIn('fin_periode', f)

    def test_mesure_depuis_quand_le_boitier_est_arrive_en_cours_de_periode(self):
        _mesure(self.cap, 2, timezone.now())
        f = self.facture()
        self.assertFalse(f['aucune_mesure'])
        premiere = timezone.localdate().isoformat()
        debut = periode_contenant(self.cl, timezone.localdate())[0]
        self.assertEqual(f['mesure_depuis'], premiere if timezone.localdate() > debut else None)

    def test_periode_historique_incomplete_signalee(self):
        _mesure(self.cap, 2, timezone.now())
        mois = self.client.get('/api/analytics/historique-mensuel/').data['mois']
        self.assertTrue(len(mois) >= 1)
        self.assertIn('mesure_depuis', mois[-1])
