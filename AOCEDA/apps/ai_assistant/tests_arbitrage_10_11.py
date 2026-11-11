"""Tests PROPOSÉS par l'arbitrage du 10/11/2026 (à placer dans apps/ai_assistant/, lancés par `manage.py test`). Chacun échoue sur le dépôt
actuel et réussit avec le correctif correspondant (voir correctifs_proposes.md)."""
import uuid
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase, APITransactionTestCase

from apps.sensors.models import Capteur, Dispositif

from . import views
from .models import QuotaIA
from .outils import executer_outil
from .tests import connecter, creer_client, flux_deepseek_simule


class CorrectifsArbitrage(APITestCase):
    def setUp(self):
        self.user = creer_client(email='arbitre@test.ci')

    # F7 (1h) : un seul mot commun ne désigne pas un appareil
    def test_1h_un_appareil_n_est_pas_devine_sur_un_seul_mot_commun(self):
        boitier = Dispositif.objects.create(client=self.user, apiKeyDevice='cle_arbitre_1')
        for nom in ('Climatiseur (circuit dédié)', 'Salon / Cuisine', 'Chambre principale'):
            Capteur.objects.create(client=self.user, dispositif=boitier, nom=nom, coupureEffective=False)
        for demande in ('Circuit général', 'chambre des enfants', 'cuisine du voisin'):
            res = executer_outil(self.user, 'preparer_coupure', {'appareil': demande, 'action': 'couper'})
            self.assertNotIn('demande_confirmation', res, demande)
            self.assertIn('erreur', res, demande)
        for demande, attendu in (('climatiseur', 'Climatiseur (circuit dédié)'), ('Chambre principale', 'Chambre principale'),
                                 ('salon cuisine', 'Salon / Cuisine'), ('la clim', 'Climatiseur (circuit dédié)')):
            res = executer_outil(self.user, 'preparer_coupure', {'appareil': demande, 'action': 'couper'})
            self.assertEqual(res['demande_confirmation']['appareil'], attendu, demande)

    # D15 : deux boîtiers ayant chacun un capteur « Salon » : la liste « lequel ? » les distingue et une carte devient possible
    def test_d15_deux_capteurs_de_meme_nom_se_distinguent_par_leur_boitier(self):
        nord = Dispositif.objects.create(client=self.user, nom='Foyer Nord', apiKeyDevice='cle_d15_nord')
        sud = Dispositif.objects.create(client=self.user, nom='Foyer Sud', apiKeyDevice='cle_d15_sud')
        c_nord = Capteur.objects.create(client=self.user, dispositif=nord, nom='Salon', coupureEffective=False)
        c_sud = Capteur.objects.create(client=self.user, dispositif=sud, nom='Salon', coupureEffective=False)
        res = executer_outil(self.user, 'preparer_coupure', {'appareil': 'salon', 'action': 'couper'})
        self.assertNotIn('demande_confirmation', res)
        self.assertEqual(sorted(res['appareils']), ['Salon (Foyer Nord)', 'Salon (Foyer Sud)'])      # avant : ['Salon', 'Salon']
        res = executer_outil(self.user, 'preparer_coupure', {'appareil': 'salon foyer sud', 'action': 'couper'})
        self.assertEqual(res['demande_confirmation']['appareil'], 'Salon (Foyer Sud)')
        self.assertEqual(res['demande_confirmation']['capteur_id'], str(c_sud.id))
        self.assertIn('Foyer Sud', res['carte_page']['appareil'])
        noms = [c['nom'] for c in executer_outil(self.user, 'etat_capteurs', {})['capteurs']]
        self.assertEqual(sorted(noms), ['Salon (Foyer Nord)', 'Salon (Foyer Sud)'])
        self.assertNotEqual(c_nord.id, c_sud.id)

    def test_d15_boitiers_sans_nom_et_capteur_unique_garde_son_nom(self):
        a = Dispositif.objects.create(client=self.user, apiKeyDevice='cle_d15_a')
        b = Dispositif.objects.create(client=self.user, apiKeyDevice='cle_d15_b')
        for boitier in (a, b):
            Capteur.objects.create(client=self.user, dispositif=boitier, nom='Salon', coupureEffective=False)
        Capteur.objects.create(client=self.user, dispositif=a, nom='Lampe', coupureEffective=False)
        noms = sorted(c['nom'] for c in executer_outil(self.user, 'etat_capteurs', {})['capteurs'])
        self.assertEqual(noms[0], 'Lampe')                                                         # un nom unique reste tel quel
        self.assertTrue(all(n.startswith('Salon (boîtier ') for n in noms[1:]) and noms[1] != noms[2], noms)

    # D17 : modèles d'écoute absents -> 503 qui le dit, sans « Retry-After » (réessayer ne sert à rien)
    def test_d17_sans_modele_whisper_la_page_recoit_un_503_sans_reessayez(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .chatbot import voix
        connecter(self.client, self.user)

        def absent(*a, **k):
            raise voix.ModeleAbsent("La transcription vocale n'est pas installée sur ce serveur (modèle Whisper manquant).")
        with patch.object(voix, 'transcrire', absent):
            r = self.client.post('/api/assistant/transcrire', {'session': str(uuid.uuid4()), 'audio': SimpleUploadedFile('v.wav', b'RIFF')},
                                 format='multipart')
        self.assertEqual(r.status_code, 503)
        self.assertFalse(r.has_header('Retry-After'))
        self.assertIn('pas installée', r.json()['erreur'])

    # Réflexion : période vide -> aussi les chiffres de la dernière période mesurée (1 aller-retour DeepSeek de moins)
    def _mesures(self, capteur, jours_avant_aujourdhui, kwh='0.4'):
        from datetime import datetime, timedelta
        from decimal import Decimal

        from django.utils import timezone

        from apps.sensors.models import MesureEnergie
        for n in jours_avant_aujourdhui:
            jour = timezone.localdate() - timedelta(days=n)
            MesureEnergie.objects.create(capteur=capteur, puissance=Decimal('500'), courant=Decimal('2'), energie=Decimal(kwh),
                                         timestamp=timezone.make_aware(datetime.combine(jour, datetime.min.time())) + timedelta(hours=10))

    def test_reflexion_periode_vide_rend_aussi_la_derniere_periode_mesuree(self):
        from datetime import timedelta

        from django.utils import timezone

        from .chatbot.live_agent import carte_outil
        cap = Capteur.objects.create(client=self.user, nom='Capteur 1 - Lampe')
        self._mesures(cap, [45, 44, 40, 38])                                      # capteurs muets depuis 38 jours
        fin = timezone.localdate() - timedelta(days=38)
        r = executer_outil(self.user, 'conso_periode', {'periode': 'hier'})
        self.assertTrue(r['aucune_mesure_sur_la_periode'])
        self.assertEqual(r['kwh_total'], 0)                                              # la période demandée est bien annoncée vide
        ancienne = r['derniere_periode_mesuree']
        direct = executer_outil(self.user, 'conso_periode', {'date_debut': (fin - timedelta(days=29)).isoformat(), 'date_fin': fin.isoformat()})
        self.assertEqual(ancienne['kwh_total'], direct['kwh_total'])                     # les chiffres de l'outil lui-même, rien d'inventé
        self.assertEqual(ancienne['kwh_total'], 1.6)
        self.assertNotIn('derniere_periode_mesuree', ancienne)                           # jamais d'enrichissement dans l'enrichissement
        self.assertIn('ANCIENS', r['a_savoir'])
        self.assertIn('AUCUNE mesure sur la période demandée', r['a_savoir'])
        carte = carte_outil('conso_periode', r)                                          # la carte de la page reste honnête : période vide
        self.assertTrue(carte['aucune_mesure'])
        self.assertEqual(carte['kwh'], 0.0)
        rep = executer_outil(self.user, 'repartition_appareils', {'periode': 'hier'})
        self.assertTrue(rep['aucune_mesure_sur_la_periode'])
        self.assertEqual(rep['appareils'], [])
        self.assertEqual(rep['derniere_periode_mesuree']['appareils'][0]['nom'], 'Capteur 1 - Lampe')

    def test_reflexion_pas_d_enrichissement_sans_mesure_ou_avec_mesures(self):
        r = executer_outil(self.user, 'conso_periode', {'periode': 'hier'})              # compte sans aucune mesure
        self.assertNotIn('derniere_periode_mesuree', r)
        self.assertIn('AUCUNE mesure', r['a_savoir'])
        cap = Capteur.objects.create(client=self.user, nom='Capteur 1 - Lampe')
        self._mesures(cap, [1])
        r = executer_outil(self.user, 'conso_periode', {'periode': '7_derniers_jours'})  # période avec mesures : rien de plus qu'avant
        self.assertNotIn('derniere_periode_mesuree', r)
        self.assertNotIn('aucune_mesure_sur_la_periode', r)

    def test_reflexion_mesures_ailleurs_identique_a_l_ancienne_requete(self):
        """Les 3 recherches indexées rendent exactement ce que rendait la requête qui datait tout l'historique."""
        from datetime import datetime, timedelta

        from django.db.models.functions import TruncDate
        from django.utils import timezone

        from apps.sensors.models import MesureEnergie

        from . import outils
        cap = Capteur.objects.create(client=self.user, nom='Capteur 1 - Lampe')
        self._mesures(cap, [60, 59, 58, 57, 30, 29, 29, 28, 12, 11, 10, 4])         # plusieurs jours avant ET après, certains en double

        def ancienne(client, start, end):
            tz = timezone.get_current_timezone()
            qs = MesureEnergie.objects.filter(capteur__client=client)
            avant = sorted({j for j in qs.filter(timestamp__lt=start).annotate(j=TruncDate('timestamp', tzinfo=tz))
                            .values_list('j', flat=True).distinct().order_by('-j')[:20]}, reverse=True)[:3]
            apres = sorted({j for j in qs.filter(timestamp__gt=end).annotate(j=TruncDate('timestamp', tzinfo=tz))
                            .values_list('j', flat=True).distinct().order_by('j')[:20]})[:3]
            return [outils._date_txt(j) for j in sorted(avant)], [outils._date_txt(j) for j in apres]
        aujourdhui = timezone.localdate()
        for (a, b) in ((50, 40), (35, 31), (27, 14), (9, 5), (3, 1), (70, 65), (0, 0)):
            debut = timezone.make_aware(datetime.combine(aujourdhui - timedelta(days=a), datetime.min.time()))
            fin = timezone.make_aware(datetime.combine(aujourdhui - timedelta(days=b), datetime.max.time()))
            nouveau = outils._mesures_ailleurs(self.user, debut, fin)
            self.assertEqual((nouveau['derniers_jours_mesures_avant'], nouveau['premiers_jours_mesures_apres']), ancienne(self.user, debut, fin), (a, b))

    # F11 (A7) : le quota ne se lit plus puis s'écrit (course entre fils) : une seule requête d'incrément
    @override_settings(AI_DAILY_LIMIT=2)
    def test_A7_quota_atomique(self):
        QuotaIA.objects.get_or_create(client=self.user)                       # la ligne existe déjà : seul l'incrément est observé
        with patch.object(QuotaIA, 'save', side_effect=AssertionError('lecture puis écriture : course possible')):
            views.quota_du_jour(self.user)
            views.quota_du_jour(self.user)
            with self.assertRaises(views.Refus):
                views.quota_du_jour(self.user)
        self.assertEqual(QuotaIA.objects.get(client=self.user).nb_requetes_aujourd_hui, 2)

    @override_settings(AI_DAILY_LIMIT=0)
    def test_A7_quota_illimite_compte_quand_meme(self):
        for _ in range(3):
            views.quota_du_jour(self.user)
        self.assertEqual(QuotaIA.objects.get(client=self.user).nb_requetes_aujourd_hui, 3)


class CorrectifsArbitrageFlux(APITransactionTestCase):
    """/message est une vue asynchrone qui calcule dans des fils : base de test transactionnelle (comme FactureJointeTests)."""

    # D16 : une panne du service de réponse ne consomme pas la question du quota et dit la vraie cause
    @override_settings(AI_DAILY_LIMIT=3)
    def test_d16_une_panne_du_service_ne_consomme_pas_le_quota(self):
        from asgiref.sync import async_to_sync

        from .chatbot import fournisseurs
        user = creer_client(email='arbitre.panne@test.ci')
        connecter(self.client, user)

        def ouvrir(systeme, historique):
            raise fournisseurs.Echec('DeepSeek 402 : Insufficient Balance')
        with patch.object(fournisseurs, 'candidats', lambda *a, **k: [('DeepSeek', 'simulé', ouvrir)]):
            r = self.client.post('/api/assistant/message', {'session': str(uuid.uuid4()), 'texte': 'Bonjour', 'langue': 'fr'}, format='json')
            if hasattr(r.streaming_content, '__aiter__'):
                async def tout():
                    return [m async for m in r.streaming_content]
                corps = ''.join(m if isinstance(m, str) else m.decode() for m in async_to_sync(tout)())
            else:
                corps = b''.join(r.streaming_content).decode()
        self.assertIn('administrateur', corps)
        self.assertNotIn('saturé', corps)
        self.assertEqual(QuotaIA.objects.get(client=user).nb_requetes_aujourd_hui, 0)          # avant : 1 question perdue par panne

    # F8 (N1) : langue / indice_langue de mauvais type = saisie ignorée, pas HTTP 500
    @override_settings(AI_DAILY_LIMIT=0)
    def test_N1_langue_de_mauvais_type_ne_donne_pas_500(self):
        from asgiref.sync import async_to_sync

        from .chatbot import fournisseurs
        user = creer_client(email='arbitre.flux@test.ci')
        connecter(self.client, user)
        for champ in ('langue', 'indice_langue'):
            for valeur in ([], ['fr'], {}, {'a': 1}):
                post, _ = flux_deepseek_simule('Bonjour.')
                with patch.object(fournisseurs.requests, 'post', post), patch.dict(fournisseurs.CONFIG, {'DEEPSEEK_API_KEY': 'cle-de-test'}):
                    r = self.client.post('/api/assistant/message', {'session': str(uuid.uuid4()), 'texte': 'Bonjour', 'langue': 'fr', champ: valeur}, format='json')
                    if hasattr(r, 'streaming_content'):
                        async def tout():
                            return [m async for m in r.streaming_content]
                        async_to_sync(tout)() if hasattr(r.streaming_content, '__aiter__') else list(r.streaming_content)
                self.assertLess(r.status_code, 500, (champ, valeur, getattr(r, 'content', b'')[:200]))
