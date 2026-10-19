"""Page Historique (19/10/2026) : calcul journalier par plages indexées, nuit 22 h → 6 h, jours « éteint » (vrai 0)
distingués des jours sans trace, alertes comptées côté serveur, comparaison gardée, état du boîtier, exports."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework import status
from rest_framework.test import APITestCase

from apps.alerts.models import Alerte
from apps.sensors.models import Capteur, MesureEnergie, PresenceCapteur

from .tests import creer_client
from .views import HEURE_NUIT_DEBUT, HEURE_NUIT_FIN, _aggregate_jours, _evolution_pct


def _a(d, h, m=0):
    """Instant LOCAL du jour d à h:m."""
    return timezone.make_aware(datetime.combine(d, time(h, m)), timezone.get_current_timezone())


def _mes(cap, quand, energie="0.50", puissance="500.00"):
    return MesureEnergie.objects.create(capteur=cap, puissance=Decimal(puissance), courant=Decimal("2.2"),
                                        energie=Decimal(energie), timestamp=quand)


class HistoriqueBase(APITestCase):
    def setUp(self):
        self.cl = creer_client()
        self.cap = Capteur.objects.create(client=self.cl, nom="Salon")
        self.auj = timezone.localdate()
        self.client.force_authenticate(user=self.cl)

    def get(self, qs):
        r = self.client.get('/api/analytics/historique/?' + qs)
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        return r.data


class AggregationJourTests(HistoriqueBase):
    def test_constantes_de_nuit(self):
        self.assertEqual((HEURE_NUIT_DEBUT, HEURE_NUIT_FIN), (22, 6))

    def test_energie_pic_moyenne_et_nuit(self):
        j = self.auj - timedelta(days=1)
        _mes(self.cap, _a(j, 2), "0.10", "100.00")     # nuit (avant 6 h)
        _mes(self.cap, _a(j, 12), "0.40", "400.00")    # jour
        _mes(self.cap, _a(j, 23), "0.20", "700.00")    # nuit (après 22 h)
        _mes(self.cap, _a(j, 6), "0.30", "300.00")     # 6 h pile : déjà le jour
        d = self.get(f'date_from={j}&date_to={j}')
        self.assertEqual(len(d['jours']), 1)
        ligne = d['jours'][0]
        self.assertEqual(ligne['date'], j.isoformat())
        self.assertAlmostEqual(ligne['kwh'], 1.0)
        self.assertAlmostEqual(ligne['night_kwh'], 0.30)
        self.assertEqual(ligne['peak_w'], 700)
        self.assertEqual(ligne['avg_w'], 375)   # (100 + 400 + 700 + 300) / 4
        self.assertEqual(ligne['n'], 4)
        self.assertEqual(ligne['etat'], 'mesure')
        self.assertEqual(d['nuit'], {'debut': 22, 'fin': 6})

    def test_minuit_va_au_jour_suivant(self):
        j = self.auj - timedelta(days=2)
        _mes(self.cap, _a(j, 23, 59), "0.20")
        _mes(self.cap, _a(j + timedelta(days=1), 0, 0), "0.30")
        d = self.get(f'date_from={j}&date_to={j + timedelta(days=1)}')
        self.assertEqual([round(x['kwh'], 2) for x in d['jours']], [0.20, 0.30])

    def test_jours_manquants_et_futurs(self):
        j = self.auj - timedelta(days=2)
        _mes(self.cap, _a(j, 10))
        d = self.get(f'date_from={j}&date_to={self.auj + timedelta(days=5)}')
        self.assertEqual([x['date'] for x in d['jours']], [j.isoformat()])
        # hier et aujourd'hui : aucune trace, donc « manquants » ; les jours futurs n'existent pas
        self.assertEqual(d['manquants'], [(j + timedelta(days=1)).isoformat(), self.auj.isoformat()])

    def test_presence_sans_mesure_est_un_vrai_zero(self):
        j = self.auj - timedelta(days=1)
        PresenceCapteur.objects.create(capteur=self.cap, heure=_a(j, 14))
        d = self.get(f'date_from={j}&date_to={j}')
        self.assertEqual(d['jours'][0]['etat'], 'eteint')
        self.assertEqual(d['jours'][0]['kwh'], 0.0)
        self.assertEqual(d['manquants'], [])

    def test_nombre_de_requetes_proportionnel_aux_jours_pas_aux_mesures(self):
        """Plus de fonction par ligne : 3 000 mesures sur un jour ne changent pas le nombre de requêtes."""
        j = self.auj - timedelta(days=1)
        MesureEnergie.objects.bulk_create([
            MesureEnergie(capteur=self.cap, puissance=Decimal("300"), courant=Decimal("1.4"), energie=Decimal("0.001"),
                          timestamp=_a(j, 8) + timedelta(seconds=2 * i)) for i in range(3000)])
        with CaptureQueriesContext(connection) as ctx:
            jours, _ = _aggregate_jours([self.cap.id], j, j)
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual(jours[0]['n'], 3000)


class AlertesEtComparaisonTests(HistoriqueBase):
    def test_alertes_comptees_par_jour_et_seulement_de_consommation(self):
        j = self.auj - timedelta(days=1)
        _mes(self.cap, _a(j, 10))
        a1 = Alerte.objects.create(client=self.cl, type='DEPASSEMENT_SEUIL', message="x")
        a2 = Alerte.objects.create(client=self.cl, type='CREDIT_BAS', message="crédit")
        a3 = Alerte.objects.create(client=self.cl, type='TRANCHE_APPROCHE', message="tranche")
        Alerte.objects.filter(pk__in=[a1.pk, a2.pk, a3.pk]).update(createdAt=_a(j, 15))
        d = self.get(f'date_from={j}&date_to={j}')
        self.assertEqual(d['jours'][0]['alertes'], 1)

    def test_comparaison_avec_ecart(self):
        for k in (1, 2):
            _mes(self.cap, _a(self.auj - timedelta(days=k), 10), "1.00")             # fenêtre : 2 kWh
            _mes(self.cap, _a(self.auj - timedelta(days=k + 2), 10), "1.00")         # avant : 2 kWh
        _mes(self.cap, _a(self.auj - timedelta(days=1), 11), "1.00")                 # fenêtre : 3 kWh
        d = self.get(f'date_from={self.auj - timedelta(days=2)}&date_to={self.auj - timedelta(days=1)}')
        self.assertEqual(d['previous']['kwh'], 2.0)
        self.assertEqual(d['previous']['evolution_pct'], 50)
        self.assertEqual(d['previous']['date_to'], (self.auj - timedelta(days=3)).isoformat())

    def test_ecart_absurde_ou_base_trop_faible_donne_none(self):
        self.assertIsNone(_evolution_pct(1.49, 0.12))        # +1 142 %
        self.assertIsNone(_evolution_pct(5.0, 0.05))         # moins de 0,1 kWh avant
        self.assertIsNone(_evolution_pct(5.0, None))
        self.assertEqual(_evolution_pct(3.0, 2.0), 50)
        self.assertEqual(_evolution_pct(1.0, 2.0), -50)

    def test_pas_de_periode_precedente_sans_mesure(self):
        _mes(self.cap, _a(self.auj - timedelta(days=1), 10))
        d = self.get(f'date_from={self.auj - timedelta(days=1)}&date_to={self.auj - timedelta(days=1)}')
        self.assertIsNone(d['previous'])


class EtatEtRepartitionTests(HistoriqueBase):
    def test_boitier_muet(self):
        _mes(self.cap, timezone.now() - timedelta(days=3))
        d = self.get('period=week')
        self.assertFalse(d['en_ligne'])
        self.assertIsNotNone(d['dernier_contact'])
        self.assertEqual(d['derniere_mesure'], timezone.localtime(timezone.now() - timedelta(days=3)).date().isoformat())

    def test_boitier_en_ligne(self):
        _mes(self.cap, timezone.now() - timedelta(seconds=5))
        self.assertTrue(self.get('period=week')['en_ligne'])

    def test_aucun_capteur(self):
        autre = creer_client("vide@test.ci")
        self.client.force_authenticate(user=autre)
        d = self.get('period=week')
        self.assertEqual((d['jours'], d['manquants'], d['repartition'], d['previous'], d['en_ligne']), ([], [], [], None, False))
        self.assertIsNone(d['derniere_mesure'])

    def test_repartition_liste_tous_les_capteurs_meme_a_zero(self):
        autre_cap = Capteur.objects.create(client=self.cl, nom="Cuisine")
        _mes(self.cap, _a(self.auj - timedelta(days=1), 10), "2.00")
        d = self.get(f'sensor_id={autre_cap.id}&date_from={self.auj - timedelta(days=1)}&date_to={self.auj - timedelta(days=1)}')
        self.assertEqual({r['nom']: r['kwh'] for r in d['repartition']}, {'Salon': 2.0, 'Cuisine': 0.0})
        self.assertEqual(d['jours'], [])      # le filtre par capteur s'applique au détail, pas à la répartition


class ValidationEtIsolationTests(HistoriqueBase):
    def test_capteur_d_un_autre_client_ne_donne_rien(self):
        autre = creer_client("autre@test.ci")
        cap2 = Capteur.objects.create(client=autre, nom="Autre")
        _mes(cap2, _a(self.auj - timedelta(days=1), 10), "9.00")
        d = self.get(f'sensor_id={cap2.id}&period=week')
        self.assertEqual(d['jours'], [])

    def test_aucune_fuite_entre_clients(self):
        autre = creer_client("autre2@test.ci")
        cap2 = Capteur.objects.create(client=autre, nom="Autre")
        _mes(cap2, _a(self.auj - timedelta(days=1), 10), "9.00")
        self.assertEqual(self.get('period=week')['jours'], [])

    def test_requetes_invalides(self):
        for qs in ('sensor_id=pas-un-uuid', 'date_from=2026-13-45', 'date_from=2026-06-10&date_to=2026-06-01',
                   'date_from=2025-01-01&date_to=2026-06-01'):
            r = self.client.get('/api/analytics/historique/?' + qs)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, qs)

    def test_plage_de_366_jours_acceptee(self):
        r = self.client.get(f'/api/analytics/historique/?date_from={self.auj - timedelta(days=365)}&date_to={self.auj}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_non_connecte(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/analytics/historique/?period=week').status_code, (401, 403))


class ExportsHistoriqueTests(HistoriqueBase):
    def test_export_journalier_lignes_et_jours_manquants(self):
        j = self.auj - timedelta(days=3)
        _mes(self.cap, _a(j, 10), "1.00", "800.00")
        PresenceCapteur.objects.create(capteur=self.cap, heure=_a(j + timedelta(days=1), 9))
        r = self.client.get(f'/api/analytics/export/journalier/?date_from={j}&date_to={j + timedelta(days=2)}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        texte = r.content.decode('utf-8')
        self.assertTrue(texte.startswith('﻿'))
        lignes = texte.lstrip('﻿').strip().split('\r\n')
        self.assertEqual(len(lignes), 4)       # en-tête + 3 jours
        self.assertIn('Mesuré', lignes[1])
        self.assertIn('Éteint', lignes[2])
        self.assertIn('Aucune mesure', lignes[3])
        self.assertIn('1,00', lignes[1])
        self.assertIn('aoceda_journalier_', r['Content-Disposition'])

    def test_export_journalier_validation(self):
        for qs in ('date_from=nope', 'sensor_id=x', 'date_from=2026-06-10&date_to=2026-06-01'):
            self.assertEqual(self.client.get('/api/analytics/export/journalier/?' + qs).status_code, 400, qs)

    def test_export_brut_inchange(self):
        j = self.auj - timedelta(days=1)
        _mes(self.cap, _a(j, 10), "0.25", "650.00")
        r = self.client.get(f'/api/analytics/export/?date_from={j}&date_to={j}')
        texte = b''.join(r.streaming_content).decode('utf-8')
        self.assertIn('Salon', texte)
        self.assertIn('650,00', texte)
        self.assertIn('0,250000', texte)

    def test_pdf_historique_avec_jour_eteint(self):
        j = self.auj - timedelta(days=1)
        PresenceCapteur.objects.create(capteur=self.cap, heure=_a(j, 9))
        r = self.client.get(f'/api/analytics/export/pdf/?date_from={j}&date_to={j}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))


class OutilAssistantTests(HistoriqueBase):
    def test_outil_conso_periode_utilise_le_meme_calcul_journalier(self):
        """L'assistant IA lit les jours comme la page Historique (régression : il appelait l'ancienne signature)."""
        from apps.ai_assistant.outils import _outil_conso_periode
        j = self.auj - timedelta(days=2)
        _mes(self.cap, _a(j, 10), "1.50", "900.00")
        r = _outil_conso_periode(self.cl, {"date_debut": j.isoformat(), "date_fin": self.auj.isoformat()})
        self.assertEqual([x['date'] for x in r['jours']], [j.isoformat()])
        self.assertAlmostEqual(r['jours'][0]['kwh'], 1.5)
        self.assertEqual(r['jours'][0]['etat'], 'mesure')
