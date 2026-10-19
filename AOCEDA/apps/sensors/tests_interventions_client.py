"""Page « Interventions » du client (20/10/2026) : ce qu'un client peut demander, annuler, noter ; isolement entre
clients ; choix du technicien le moins chargé ; suivi d'une intervention terminée."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Capteur, Intervention
from .tests import creer_client, creer_technicien

URL = '/api/sensors/interventions/'


def _liste(r):
    return r.data['results'] if isinstance(r.data, dict) else r.data


class Base(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="demande@test.ci")
        self.autre = creer_client(email="autre.demande@test.ci")
        self.tech = creer_technicien(email="tech.demande@test.ci")
        self.tech.estActif = True
        self.tech.save()
        self.cap = Capteur.objects.create(client=self.cl, nom="Climatiseur salon")
        self.cap_autre = Capteur.objects.create(client=self.autre, nom="Frigo du voisin")
        self.client.force_authenticate(user=self.cl)

    def creer(self, **kw):
        corps = {"typeIntervention": "PANNE", "description": "Le boîtier ne répond plus depuis ce matin."}
        corps.update(kw)
        return self.client.post(URL, corps, format='json')

    def terminee(self, client=None, **kw):
        return Intervention.objects.create(
            technicien=self.tech, client=client or self.cl, typeIntervention=kw.pop('typeIntervention', 'PANNE'),
            description="Ancienne panne", dateIntervention=timezone.now() - timedelta(days=3), statut='TERMINEE', **kw)


class DemandeTests(Base):
    def test_demande_valide_avec_son_appareil(self):
        r = self.creer(capteur=str(self.cap.id))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual((r.data['statut'], r.data['capteur_nom'], r.data['client']), ('EN_ATTENTE', "Climatiseur salon", self.cl.id))
        self.assertEqual(r.data['suivis_ouverts'], 0)

    def test_l_appareil_d_un_autre_client_est_refuse(self):
        r = self.creer(capteur=str(self.cap_autre.id))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('capteur', r.data)
        self.assertEqual(Intervention.objects.count(), 0)

    def test_types_reserves_au_technicien_refuses(self):
        for t in ('INSTALLATION', 'DIAGNOSTIC', 'AUTRE'):
            self.assertEqual(self.creer(typeIntervention=t).status_code, 400, t)

    def test_description_trop_courte_ou_trop_longue(self):
        self.assertEqual(self.creer(description="Panne").status_code, 400)
        self.assertEqual(self.creer(description="   ").status_code, 400)
        self.assertEqual(self.creer(description="x" * 2001).status_code, 400)
        self.assertEqual(self.creer(description="x" * 2000).status_code, 201)

    def test_champs_du_technicien_ignores(self):
        r = self.creer(statut='TERMINEE', **{"résultat": "Réparé"}, dateProgrammee="2030-01-01T10:00:00Z",
                       dateIntervention="2020-01-01T00:00:00Z", technicien="inconnu")
        self.assertEqual(r.status_code, 201, r.data)
        iv = Intervention.objects.get()
        self.assertEqual(iv.statut, 'EN_ATTENTE')
        self.assertFalse(iv.résultat)
        self.assertIsNone(iv.dateProgrammee)
        self.assertGreater(iv.dateIntervention, timezone.now() - timedelta(minutes=1))
        self.assertEqual(iv.technicien_id, self.tech.id)

    def test_pas_plus_de_cinq_demandes_ouvertes(self):
        for i in range(5):
            self.assertEqual(self.creer(description=f"Problème numéro {i} sur l'installation").status_code, 201)
        r = self.creer(description="Une sixième demande de plus")
        self.assertEqual(r.status_code, 400)
        self.assertIn('detail', r.data)

    def test_sans_authentification_refuse(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.creer().status_code, 401)

    def test_technicien_le_moins_charge(self):
        autre_tech = creer_technicien(email="zeta.demande@test.ci")
        autre_tech.estActif = True
        autre_tech.save()
        Intervention.objects.create(technicien=self.tech, client=self.autre, typeIntervention='PANNE', description="en cours",
                                    dateIntervention=timezone.now(), statut='EN_COURS')
        r = self.creer()
        self.assertEqual(r.data['technicien'], autre_tech.id)


class SuiviTests(Base):
    def test_signaler_qu_un_probleme_persiste(self):
        o = self.terminee(capteur=self.cap)
        r = self.creer(typeIntervention='MAINTENANCE', interventionOrigine=str(o.id))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['typeIntervention'], r.data['capteur']), ('PANNE', self.cap.id))   # type forcé, appareil repris
        self.assertIsNotNone(r.data['origine_date'])
        liste = _liste(self.client.get(URL))
        origine = next(x for x in liste if x['id'] == str(o.id))
        self.assertEqual(origine['suivis_ouverts'], 1)

    def test_un_seul_signalement_ouvert_par_intervention(self):
        o = self.terminee()
        self.assertEqual(self.creer(interventionOrigine=str(o.id)).status_code, 201)
        r = self.creer(interventionOrigine=str(o.id), description="Toujours le même problème")
        self.assertEqual(r.status_code, 400)

    def test_signalement_possible_a_nouveau_une_fois_le_suivi_clos(self):
        o = self.terminee()
        self.creer(interventionOrigine=str(o.id))
        Intervention.objects.filter(interventionOrigine=o).update(statut='TERMINEE')
        self.assertEqual(self.creer(interventionOrigine=str(o.id), description="Revenu une seconde fois").status_code, 201)

    def test_origine_d_un_autre_client_ou_non_terminee_refusee(self):
        autre_o = self.terminee(client=self.autre)
        self.assertEqual(self.creer(interventionOrigine=str(autre_o.id)).status_code, 400)
        ouverte = Intervention.objects.create(technicien=self.tech, client=self.cl, typeIntervention='PANNE', description="x" * 12,
                                              dateIntervention=timezone.now(), statut='EN_COURS')
        self.assertEqual(self.creer(interventionOrigine=str(ouverte.id)).status_code, 400)


class AnnulationTests(Base):
    def test_annuler_une_demande_en_attente(self):
        iv = Intervention.objects.get(pk=self.creer().data['id'])
        r = self.client.post(f'{URL}{iv.id}/annuler/')
        self.assertEqual(r.status_code, 200, r.data)
        iv.refresh_from_db()
        self.assertEqual(iv.statut, 'ANNULEE')
        self.assertIn('annulée', iv.résultat)
        from apps.accounts.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(action='ANNULATION_INTERVENTION', client=self.cl).exists())

    def test_impossible_une_fois_prise_en_charge(self):
        iv = Intervention.objects.get(pk=self.creer().data['id'])
        Intervention.objects.filter(pk=iv.pk).update(statut='EN_COURS')
        r = self.client.post(f'{URL}{iv.id}/annuler/')
        self.assertEqual(r.status_code, 400)
        iv.refresh_from_db()
        self.assertEqual(iv.statut, 'EN_COURS')

    def test_impossible_pour_l_intervention_d_un_autre_client(self):
        iv = Intervention.objects.get(pk=self.creer().data['id'])
        self.client.force_authenticate(user=self.autre)
        self.assertEqual(self.client.post(f'{URL}{iv.id}/annuler/').status_code, 404)

    def test_un_technicien_ne_passe_pas_par_la(self):
        iv = Intervention.objects.get(pk=self.creer().data['id'])
        self.client.force_authenticate(user=self.tech)
        self.assertEqual(self.client.post(f'{URL}{iv.id}/annuler/').status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(f'{URL}{iv.id}/annuler/').status_code, 401)


class AvisTests(Base):
    def avis(self, iv, **corps):
        return self.client.patch(f'{URL}{iv.id}/retour/', corps, format='json')

    def test_un_avis_se_donne_une_seule_fois(self):
        iv = self.terminee()
        self.assertEqual(self.avis(iv, satisfactionClient=4, commentaireClient="Très bien").status_code, 200)
        r = self.avis(iv, satisfactionClient=1, commentaireClient="Finalement non")
        self.assertEqual(r.status_code, 400)
        iv.refresh_from_db()
        self.assertEqual((iv.satisfactionClient, iv.commentaireClient), (4, "Très bien"))

    def test_note_obligatoire_et_commentaire_limite(self):
        iv = self.terminee()
        self.assertEqual(self.avis(iv, commentaireClient="Sans note").status_code, 400)
        self.assertEqual(self.avis(iv, satisfactionClient=6).status_code, 400)
        self.assertEqual(self.avis(iv, satisfactionClient=5, commentaireClient="x" * 501).status_code, 400)
        self.assertEqual(self.avis(iv, satisfactionClient=5, commentaireClient="  bien  ").status_code, 200)
        iv.refresh_from_db()
        self.assertEqual(iv.commentaireClient, "bien")

    def test_avis_sur_l_intervention_d_un_autre_ou_non_terminee(self):
        autre = self.terminee(client=self.autre)
        self.assertEqual(self.avis(autre, satisfactionClient=3).status_code, 404)
        ouverte = Intervention.objects.create(technicien=self.tech, client=self.cl, typeIntervention='PANNE', description="x" * 12,
                                              dateIntervention=timezone.now(), statut='EN_COURS')
        self.assertEqual(self.avis(ouverte, satisfactionClient=3).status_code, 404)


class ListeTests(Base):
    def test_requetes_constantes_quel_que_soit_le_nombre(self):
        for i in range(8):
            o = self.terminee()
            Intervention.objects.create(technicien=self.tech, client=self.cl, typeIntervention='PANNE', description=f"suivi {i}",
                                        dateIntervention=timezone.now(), statut='EN_ATTENTE', interventionOrigine=o)
        with self.assertNumQueries(5):                     # session/jeton, pagination (count), liste, suivis, + marge
            r = self.client.get(URL)
        self.assertEqual(len(_liste(r)), 16)

    def test_chaque_client_ne_voit_que_les_siennes(self):
        self.terminee()
        self.terminee(client=self.autre)
        self.assertEqual(len(_liste(self.client.get(URL))), 1)


class NotificationsTests(Base):
    """Le client est prévenu (page Alertes + e-mail) quand le technicien agit ; le technicien l'est d'une nouvelle demande."""

    def alertes(self):
        from apps.alerts.models import Alerte
        return list(Alerte.objects.filter(client=self.cl, type='INTERVENTION').order_by('createdAt'))

    def ouverte(self):
        return Intervention.objects.get(pk=self.creer().data['id'])

    def test_la_creation_ne_previent_pas_le_client(self):
        self.ouverte()
        self.assertEqual(self.alertes(), [])

    def test_prise_en_charge_rendez_vous_et_fin(self):
        iv = self.ouverte()
        iv.statut = 'EN_COURS'
        iv.save()
        iv.dateProgrammee = timezone.now() + timedelta(days=2)
        iv.save()
        iv.statut = 'TERMINEE'
        iv.save()
        messages = [a.message for a in self.alertes()]
        self.assertEqual(len(messages), 3)
        self.assertIn('a pris en charge', messages[0])
        self.assertIn('Rendez-vous fixé', messages[1])
        self.assertIn('terminée', messages[2])
        a = self.alertes()[0]
        self.assertEqual((a.sévérité, a.intervention_id), ('Info', iv.id))

    def test_rien_si_rien_ne_change_ou_pour_un_avis(self):
        iv = self.ouverte()
        iv.save()
        iv.statut = 'TERMINEE'
        iv.save()
        n = len(self.alertes())
        self.client.patch(f'{URL}{iv.id}/retour/', {"satisfactionClient": 5}, format='json')
        iv.refresh_from_db()
        iv.save()
        self.assertEqual(len(self.alertes()), n)

    def test_annulation_par_le_client_ne_declenche_rien(self):
        iv = self.ouverte()
        self.client.post(f'{URL}{iv.id}/annuler/')
        self.assertEqual(self.alertes(), [])

    def test_annulation_par_le_technicien_avertit_le_client(self):
        iv = self.ouverte()
        iv.statut = 'ANNULEE'
        iv.save()
        a = self.alertes()
        self.assertEqual((len(a), a[0].sévérité), (1, 'Avertissement'))

    def test_l_alerte_est_lisible_par_le_client_avec_le_lien(self):
        iv = self.ouverte()
        iv.statut = 'EN_COURS'
        iv.save()
        r = self.client.get('/api/alertes/')
        items = r.data['results'] if isinstance(r.data, dict) else r.data
        a = next(x for x in items if x['type'] == 'INTERVENTION')
        self.assertEqual(a['intervention_id'], iv.id)
        self.assertEqual(a['type_display'], 'Suivi de votre intervention')

    def test_email_envoye_au_client_et_au_technicien(self):
        from unittest import mock
        with mock.patch('apps.accounts.utils.send_mail_async') as technicien:
            iv = self.ouverte()
        self.assertEqual(technicien.call_count, 1)
        self.assertEqual(technicien.call_args[0][3], [self.tech.email])
        self.assertIn(self.cl.nom, technicien.call_args[0][1])
        with mock.patch('apps.alerts.utils.send_mail_async') as client:
            iv.statut = 'EN_COURS'
            iv.save()
        self.assertEqual(client.call_count, 1)
        self.assertEqual(client.call_args[0][3], [self.cl.email])
        self.assertIn('Suivi de votre demande', client.call_args[0][0])

    def test_pas_d_email_si_le_client_les_a_coupes(self):
        from unittest import mock
        self.cl.notifEmail = False
        self.cl.save()
        iv = self.ouverte()
        with mock.patch('apps.alerts.utils.send_mail_async') as client:
            iv.statut = 'EN_COURS'
            iv.save()
        client.assert_not_called()
        self.assertEqual(len(self.alertes()), 1)
