"""Réglages SIMPLES des alertes (19/10/2026) : un interrupteur par type d'alerte, un niveau en trois mots, des heures de
nuit, appliqués à tous les capteurs sans règle personnalisée ; couper un type le coupe aussi pour les règles
personnalisées ; profil client : valeurs par défaut, validations."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Client
from apps.sensors.models import Capteur, MesureEnergie

from .models import Alerte, RegleDetection
from .tests import creer_client
from .utils import (ReglePrefs, capacite_w, check_credit_prepaye, check_tranche_postpaye, etat_surveillance,
                    evaluate_measurements, seuil_simple_w)


def _a(h, m=0, jours=0):
    d = timezone.localdate() - timedelta(days=jours)
    return timezone.make_aware(datetime.combine(d, time(h, m)), timezone.get_current_timezone())


def _mesure(cap, puissance, quand):
    return MesureEnergie.objects.create(capteur=cap, puissance=Decimal(str(puissance)), courant=Decimal("2.0"),
                                        energie=Decimal("0.01"), timestamp=quand)


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.cl = creer_client()                      # 10 A : l'abonnement supporte 2 200 W
        self.cap = Capteur.objects.create(client=self.cl, nom="Salon")

    def evaluer(self, puissance, quand):
        _mesure(self.cap, puissance, quand)
        evaluate_measurements(self.cl, {self.cap.id})

    def types(self):
        return sorted(Alerte.objects.filter(client=self.cl).values_list('type', flat=True))

    def refresh(self):
        self.cl = Client.objects.get(pk=self.cl.pk)


class ValeursParDefautTests(Base):
    def test_defauts_du_compte(self):
        c = self.cl
        self.assertEqual((c.alerteDepassement, c.niveauDepassement, c.alerteNuit, c.alerteTranche, c.alerteCredit),
                         (True, 'normal', True, True, True))
        self.assertEqual((c.nuitDebut, c.nuitFin), (time(22, 0), time(6, 0)))

    def test_seuils_selon_l_abonnement_et_le_niveau(self):
        self.assertEqual(capacite_w(self.cl), 2200)
        for niveau, attendu in (('prudent', 1100), ('normal', 1760), ('limite', 2200)):
            self.cl.niveauDepassement = niveau
            self.assertEqual(seuil_simple_w(self.cl), attendu)
        self.cl.amperage = 5
        self.cl.niveauDepassement = 'normal'
        self.assertEqual(seuil_simple_w(self.cl), 880)         # 5 A : 1 100 W × 0,8

    def test_regle_virtuelle(self):
        r = ReglePrefs(self.cl, self.cap)
        self.assertIsNone(r.pk)
        self.assertEqual((r.puissanceMax_W, r.seuilNuit_W), (Decimal(1760), Decimal("176.0")))


class DepassementSimpleTests(Base):
    def test_un_capteur_sans_regle_est_surveille_par_le_reglage_simple(self):
        self.evaluer(1700, _a(14))
        self.assertEqual(self.types(), [])
        self.evaluer(1800, _a(14, 1))
        self.assertEqual(self.types(), ['DEPASSEMENT_SEUIL'])
        a = Alerte.objects.get()
        self.assertIsNone(a.regle_id)
        self.assertEqual(a.sévérité, 'Critique')
        self.assertIn('automatique', a.message)
        self.assertIn('1 760 W'.replace(' ', ''), a.message.replace(' ', '').replace(' ', ''))

    def test_niveau_prudent_alerte_plus_tot(self):
        self.cl.niveauDepassement = 'prudent'
        self.cl.save()
        self.evaluer(1200, _a(14))
        self.assertEqual(self.types(), ['DEPASSEMENT_SEUIL'])

    def test_niveau_limite_alerte_plus_tard(self):
        self.cl.niveauDepassement = 'limite'
        self.cl.save()
        self.evaluer(2000, _a(14))
        self.assertEqual(self.types(), [])
        self.evaluer(2300, _a(14, 1))
        self.assertEqual(self.types(), ['DEPASSEMENT_SEUIL'])

    def test_interrupteur_coupe_l_alerte(self):
        self.cl.alerteDepassement = False
        self.cl.save()
        self.evaluer(2000, _a(14))
        self.assertEqual(self.types(), [])

    def test_une_regle_personnalisee_prime_sur_le_reglage_simple(self):
        RegleDetection.objects.create(client=self.cl, capteur=self.cap, puissanceMax_W=Decimal("5000"), surveilleNuit=False)
        self.evaluer(2000, _a(14))                    # le réglage simple aurait alerté dès 1 760 W
        self.assertEqual(self.types(), [])

    def test_l_interrupteur_coupe_aussi_les_regles_personnalisees(self):
        RegleDetection.objects.create(client=self.cl, capteur=self.cap, puissanceMax_W=Decimal("100"), surveilleNuit=False)
        self.cl.alerteDepassement = False
        self.cl.save()
        self.evaluer(500, _a(14))
        self.assertEqual(self.types(), [])

    def test_cooldown_du_reglage_simple(self):
        self.evaluer(2000, _a(14))
        self.evaluer(2100, _a(14, 1))
        self.assertEqual(Alerte.objects.filter(type='DEPASSEMENT_SEUIL').count(), 1)

    def test_capteur_inactif_ignore(self):
        self.cap.actif = False
        self.cap.save()
        self.evaluer(2000, _a(14))
        self.assertEqual(self.types(), [])


class NuitSimpleTests(Base):
    def test_nuit_par_defaut_22h_6h(self):
        self.evaluer(300, _a(23))                    # > 176 W, en pleine nuit
        self.assertEqual(self.types(), ['CONSOMMATION_NOCTURNE'])

    def test_le_jour_aucune_alerte_de_nuit(self):
        self.evaluer(300, _a(14))
        self.assertEqual(self.types(), [])

    def test_sous_le_seuil_de_nuit(self):
        self.evaluer(150, _a(23))
        self.assertEqual(self.types(), [])

    def test_heures_de_nuit_personnalisees(self):
        self.cl.nuitDebut, self.cl.nuitFin = time(0, 0), time(5, 0)
        self.cl.save()
        self.evaluer(300, _a(23, jours=1))           # hier à 23 h : hors de 0 h-5 h
        self.assertEqual(self.types(), [])
        self.evaluer(300, _a(3))                      # aujourd'hui à 3 h : dans la nuit choisie
        self.assertEqual(self.types(), ['CONSOMMATION_NOCTURNE'])

    def test_interrupteur_nuit_coupe(self):
        self.cl.alerteNuit = False
        self.cl.save()
        self.evaluer(300, _a(23))
        self.assertEqual(self.types(), [])

    def test_mode_absence_suspend_la_nuit_mais_pas_la_puissance(self):
        self.cl.modeAbsenceActif = True
        self.cl.save()
        self.evaluer(300, _a(23))
        self.assertEqual(self.types(), [])
        self.evaluer(2000, _a(23, 5))
        self.assertEqual(self.types(), ['DEPASSEMENT_SEUIL'])

    def test_tout_coupe_aucune_surveillance_simple(self):
        self.cl.alerteDepassement = self.cl.alerteNuit = False
        self.cl.save()
        self.evaluer(5000, _a(23))
        self.assertEqual(self.types(), [])


class TrancheEtCreditTests(Base):
    def test_interrupteur_tranche(self):
        self.cl.amperage, self.cl.typeTarif = 5, 'social'
        self.cl.alerteTranche = False
        self.cl.save()
        MesureEnergie.objects.create(capteur=self.cap, puissance=Decimal('100'), courant=Decimal('0.5'),
                                     energie=Decimal('73'), timestamp=timezone.now())
        check_tranche_postpaye(self.cl, forcer=True)
        self.assertEqual(self.types(), [])
        self.cl.alerteTranche = True
        self.cl.save()
        check_tranche_postpaye(self.cl, forcer=True)
        self.assertEqual(self.types(), ['TRANCHE_APPROCHE'])

    def test_interrupteur_credit(self):
        self.cl.typeCompteur = 'prepaye'
        self.cl.creditPrepaye_FCFA = Decimal('5000')
        self.cl.alerteCredit = False
        self.cl.save()
        check_credit_prepaye(self.cl)
        self.assertEqual(self.types(), [])
        self.cl.alerteCredit = True
        self.cl.save()
        check_credit_prepaye(self.cl)
        self.assertEqual(self.types(), ['CREDIT_BAS'])


class ProfilEtSurveillanceTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.cl)

    def test_le_profil_expose_les_reglages_simples(self):
        d = self.client.get('/api/users/me/').data
        for cle in ('alerteDepassement', 'niveauDepassement', 'alerteNuit', 'nuitDebut', 'nuitFin', 'alerteTranche', 'alerteCredit'):
            self.assertIn(cle, d)
        self.assertEqual((d['niveauDepassement'], d['nuitDebut'], d['nuitFin']), ('normal', '22:00:00', '06:00:00'))

    def test_modifier_un_reglage_partiellement(self):
        r = self.client.put('/api/users/me/', {'alerteTranche': False, 'niveauDepassement': 'prudent'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.refresh()
        self.assertEqual((self.cl.alerteTranche, self.cl.niveauDepassement, self.cl.alerteNuit), (False, 'prudent', True))

    def test_validations(self):
        for corps in ({'niveauDepassement': 'enorme'}, {'nuitDebut': '23:00:00', 'nuitFin': '23:00:00'},
                      {'seuilCreditBas_FCFA': 100}, {'seuilCreditBas_FCFA': 999999}, {'nuitDebut': 'abc'}):
            r = self.client.put('/api/users/me/', corps, format='json')
            self.assertEqual(r.status_code, 400, corps)

    def test_nuit_deux_heures_identiques_refusee_aussi_avec_la_valeur_existante(self):
        r = self.client.put('/api/users/me/', {'nuitFin': '22:00:00'}, format='json')    # début déjà à 22 h
        self.assertEqual(r.status_code, 400)

    def test_les_champs_en_lecture_seule_restent_proteges(self):
        self.client.put('/api/users/me/', {'amperage': 15, 'typeCompteur': 'prepaye'}, format='json')
        self.refresh()
        self.assertEqual((self.cl.amperage, self.cl.typeCompteur), (10, 'postpaye'))

    def test_surveillance_couverte_par_le_reglage_simple(self):
        s = etat_surveillance(self.cl)
        self.assertEqual((s['capteurs'], s['regles'], s['capteurs_surveilles'], s['reglage_simple']), (1, 0, 1, True))

    def test_surveillance_sans_aucun_reglage_ni_regle(self):
        self.cl.alerteDepassement = self.cl.alerteNuit = False
        self.cl.save()
        s = etat_surveillance(self.cl)
        self.assertEqual((s['capteurs_surveilles'], s['reglage_simple']), (0, False))
        RegleDetection.objects.create(client=self.cl, capteur=self.cap)
        self.assertEqual(etat_surveillance(self.cl)['capteurs_surveilles'], 1)
