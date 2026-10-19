"""Page Alertes (19/10/2026) : cooldown par règle, compteur léger, état de la surveillance, « non lue », marquage groupé
limité à ce que la page montre, validations des règles, e-mail de test, purge, vérification du compte limitée."""
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework import status
from rest_framework.test import APITestCase

from apps.sensors.models import Capteur, MesureEnergie

from .models import Alerte, RegleDetection
from .tasks import purger_alertes_lues
from .tests import creer_client
from .utils import evaluate_measurements


def _mesure(cap, puissance, quand=None):
    return MesureEnergie.objects.create(capteur=cap, puissance=Decimal(str(puissance)), courant=Decimal("2.0"),
                                        energie=Decimal("0.01"), timestamp=quand or timezone.now())


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.cl = creer_client()
        self.cap = Capteur.objects.create(client=self.cl, nom="Salon")
        self.client.force_authenticate(user=self.cl)


class CooldownParRegleTests(Base):
    def test_deux_regles_d_un_meme_capteur_ne_se_masquent_plus(self):
        bas = RegleDetection.objects.create(client=self.cl, capteur=self.cap, nom="Lampe", puissanceMax_W=Decimal("100"))
        haut = RegleDetection.objects.create(client=self.cl, capteur=self.cap, nom="Gros", puissanceMax_W=Decimal("500"))
        _mesure(self.cap, 600)
        evaluate_measurements(self.cl, {self.cap.id})
        evaluate_measurements(self.cl, {self.cap.id})          # le cooldown joue toujours PAR règle
        alertes = Alerte.objects.filter(client=self.cl, type='DEPASSEMENT_SEUIL')
        self.assertEqual(alertes.count(), 2)
        self.assertEqual({a.regle_id for a in alertes}, {bas.id, haut.id})

    def test_une_ancienne_alerte_sans_regle_garde_le_cooldown_par_capteur(self):
        RegleDetection.objects.create(client=self.cl, capteur=self.cap, puissanceMax_W=Decimal("100"))
        mesure = _mesure(self.cap, 600)
        Alerte.objects.create(client=self.cl, mesure=mesure, type='DEPASSEMENT_SEUIL', message="ancienne")
        evaluate_measurements(self.cl, {self.cap.id})
        self.assertEqual(Alerte.objects.filter(client=self.cl, type='DEPASSEMENT_SEUIL').count(), 1)

    def test_l_alerte_garde_la_regle_et_l_api_l_expose(self):
        regle = RegleDetection.objects.create(client=self.cl, capteur=self.cap, nom="Ma règle", puissanceMax_W=Decimal("100"))
        _mesure(self.cap, 600)
        evaluate_measurements(self.cl, {self.cap.id})
        d = self.client.get('/api/alertes/').data
        a = (d['results'] if isinstance(d, dict) else d)[0]
        self.assertEqual(a['regle_id'], regle.id)
        self.assertEqual(a['regle_nom'], "Ma règle")
        self.assertEqual(a['capteur_id'], str(self.cap.id))


class VerificationDuCompteLimiteeTests(Base):
    def test_le_credit_n_est_recalcule_qu_une_fois_par_minute(self):
        RegleDetection.objects.create(client=self.cl, capteur=self.cap, puissanceMax_W=Decimal("5000"))
        _mesure(self.cap, 50)
        with mock.patch('apps.alerts.utils.check_credit_prepaye') as credit, \
                mock.patch('apps.alerts.utils.check_tranche_postpaye') as tranche:
            for _ in range(5):
                evaluate_measurements(self.cl, {self.cap.id})
        self.assertEqual(credit.call_count, 1)
        self.assertEqual(tranche.call_count, 1)

    def test_deux_clients_ne_se_limitent_pas_entre_eux(self):
        autre = creer_client("b@test.ci")
        with mock.patch('apps.alerts.utils.check_credit_prepaye') as credit, \
                mock.patch('apps.alerts.utils.check_tranche_postpaye'):
            evaluate_measurements(self.cl, set())
            evaluate_measurements(autre, set())
        self.assertEqual(credit.call_count, 2)


class CompteurEtSurveillanceTests(Base):
    def test_compteur_et_critiques_non_lues(self):
        a = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="crit", sévérité='Critique')
        Alerte.objects.create(client=self.cl, type='CONSOMMATION_NOCTURNE', message="warn", sévérité='Avertissement')
        Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="lue", sévérité='Critique', lue=True)
        d = self.client.get('/api/alertes/compteur/').data
        self.assertEqual(d['non_lues'], 2)
        self.assertEqual([c['id'] for c in d['critiques_non_lues']], [str(a.id)])

    def test_le_compteur_ignore_le_credit_bas_d_un_postpaye(self):
        Alerte.objects.create(client=self.cl, type='CREDIT_BAS', message="crédit")
        self.assertEqual(self.client.get('/api/alertes/compteur/').data['non_lues'], 0)

    def test_surveillance_sans_capteur(self):
        vide = creer_client("vide@test.ci")
        self.client.force_authenticate(user=vide)
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertEqual((s['capteurs'], s['regles'], s['capteurs_surveilles'], s['en_ligne']), (0, 0, 0, False))
        self.assertIsNone(s['dernier_contact'])

    def test_surveillance_capteur_sans_regle_puis_avec_regle(self):
        # réglages simples activés (défaut) : le capteur est surveillé même sans règle personnalisée
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertEqual((s['capteurs'], s['regles'], s['capteurs_surveilles']), (1, 0, 1))
        # tout coupé : plus rien n'est surveillé tant qu'aucune règle personnalisée n'existe
        from apps.accounts.models import Client
        Client.objects.filter(pk=self.cl.pk).update(alerteDepassement=False, alerteNuit=False)
        self.client.force_authenticate(user=Client.objects.get(pk=self.cl.pk))
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertEqual((s['regles'], s['capteurs_surveilles']), (0, 0))
        RegleDetection.objects.create(client=self.cl, capteur=self.cap)
        RegleDetection.objects.create(client=self.cl, capteur=self.cap, nom="2e")
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertEqual((s['regles'], s['capteurs_surveilles']), (2, 1))

    def test_surveillance_etat_du_boitier_et_absence(self):
        _mesure(self.cap, 50, timezone.now() - timedelta(days=2))
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertFalse(s['en_ligne'])
        self.assertIsNotNone(s['dernier_contact'])
        self.cl.modeAbsenceActif = True
        self.cl.absenceJusquau = timezone.localdate() + timedelta(days=3)
        self.cl.save()
        from apps.accounts.models import Client
        self.client.force_authenticate(user=Client.objects.get(pk=self.cl.pk))   # une vraie requête relit l'utilisateur
        s = self.client.get('/api/alertes/compteur/').data['surveillance']
        self.assertTrue(s['absence_active'])
        self.assertEqual(s['absence_jusquau'], (timezone.localdate() + timedelta(days=3)).isoformat())

    def test_non_connecte(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/alertes/compteur/').status_code, (401, 403))


class MarquageTests(Base):
    def test_marquer_non_lue_puis_lue(self):
        a = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="x", lue=True)
        r = self.client.patch(f'/api/alertes/{a.id}/lire/', {'lue': False}, format='json')
        self.assertEqual((r.status_code, r.data['lue']), (200, False))
        a.refresh_from_db()
        self.assertFalse(a.lue)
        r = self.client.patch(f'/api/alertes/{a.id}/lire/', {}, format='json')
        self.assertTrue(r.data['lue'])

    def test_alerte_d_un_autre_client_introuvable(self):
        autre = creer_client("autre@test.ci")
        a = Alerte.objects.create(client=autre, type='DEPASSEMENT_SEUIL', message="x")
        self.assertEqual(self.client.patch(f'/api/alertes/{a.id}/lire/', {}, format='json').status_code, 404)
        a.refresh_from_db()
        self.assertFalse(a.lue)

    def test_tout_lire_ne_touche_que_ce_que_la_page_montre(self):
        """Postpayé : l'ancienne alerte « crédit bas » n'est pas visible, elle ne doit pas être comptée ni touchée."""
        Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="visible")
        cache_ = Alerte.objects.create(client=self.cl, type='CREDIT_BAS', message="invisible")
        r = self.client.post('/api/alertes/tout-lire/')
        self.assertEqual(r.data['count'], 1)
        cache_.refresh_from_db()
        self.assertFalse(cache_.lue)

    def test_tout_lire_n_atteint_pas_les_alertes_des_autres(self):
        autre = creer_client("autre3@test.ci")
        a = Alerte.objects.create(client=autre, type='DEPASSEMENT_SEUIL', message="x")
        self.client.post('/api/alertes/tout-lire/')
        a.refresh_from_db()
        self.assertFalse(a.lue)


class ValidationReglesTests(Base):
    def corps(self, **kw):
        base = {"nom": "R", "capteur": str(self.cap.id), "puissanceMax_W": 800, "surveilleNuit": True,
                "heureDébutNuit": "22:00:00", "heureFinNuit": "05:00:00"}
        base.update(kw)
        return base

    def post(self, **kw):
        return self.client.post('/api/regles/', self.corps(**kw), format='json')

    def test_regle_valide(self):
        self.assertEqual(self.post().status_code, 201)

    def test_seuil_hors_bornes_refuse_et_sentinelle_acceptee(self):
        self.assertEqual(self.post(puissanceMax_W=50000).status_code, 400)       # avant : accepté, ne surveillait rien
        self.assertEqual(self.post(puissanceMax_W=4).status_code, 400)
        self.assertEqual(self.post(puissanceMax_W=5001).status_code, 400)
        self.assertEqual(self.post(puissanceMax_W=100000).status_code, 201)      # désactivé, mais la nuit surveille

    def test_aucune_surveillance_refusee(self):
        r = self.post(puissanceMax_W=100000, surveilleNuit=False)
        self.assertEqual(r.status_code, 400)
        self.assertIn('surveillance', str(r.data).lower())

    def test_plage_nocturne_de_deux_heures_identiques_refusee(self):
        self.assertEqual(self.post(heureDébutNuit="03:00:00", heureFinNuit="03:00:00").status_code, 400)
        self.assertEqual(self.post(surveilleNuit=False, heureDébutNuit="03:00:00", heureFinNuit="03:00:00").status_code, 201)

    def test_plage_a_cheval_sur_minuit_acceptee(self):
        self.assertEqual(self.post(heureDébutNuit="22:00:00", heureFinNuit="05:00:00").status_code, 201)

    def test_modification_valide_aussi(self):
        regle = RegleDetection.objects.create(client=self.cl, capteur=self.cap)
        r = self.client.put(f'/api/regles/{regle.id}/', self.corps(puissanceMax_W=100000, surveilleNuit=False), format='json')
        self.assertEqual(r.status_code, 400)

    def test_limite_de_30_configurations(self):
        for i in range(30):
            RegleDetection.objects.create(client=self.cl, capteur=self.cap, nom=f"r{i}")
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertIn('30', str(r.data))


class EmailTestEtPurgeTests(Base):
    def test_email_de_test_une_fois_par_minute(self):
        with mock.patch('apps.accounts.utils.send_mail_async') as envoi:
            r1 = self.client.post('/api/alertes/test-email/')
            r2 = self.client.post('/api/alertes/test-email/')
        self.assertEqual(r1.status_code, 202)
        self.assertEqual(r2.status_code, 429)
        self.assertEqual(envoi.call_count, 1)
        self.assertEqual(envoi.call_args[0][3], [self.cl.email])
        self.assertEqual(Alerte.objects.count(), 0)                 # aucune fausse alerte enregistrée

    def test_purge_des_vieilles_alertes_lues_seulement(self):
        vieux = timezone.now() - timedelta(days=200)
        a = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="vieille lue", lue=True)
        b = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="vieille non lue")
        c = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="récente lue", lue=True)
        Alerte.objects.filter(pk__in=[a.pk, b.pk]).update(createdAt=vieux)
        purger_alertes_lues()
        self.assertEqual(set(Alerte.objects.values_list('pk', flat=True)), {b.pk, c.pk})
