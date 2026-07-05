"""Tests de l'application accounts : inscription, connexion JWT, profil, admin."""
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Client, Technicien, Administrateur


def creer_client(email="client@test.ci", password="Password123!", **extra):
    client = Client(email=email, nom=extra.pop('nom', 'Client Test'), role='client', **extra)
    client.set_password(password)
    client.save()
    return client


def creer_admin(email="admin@test.ci", password="Password123!"):
    admin = Administrateur(email=email, nom="Admin Test", role='admin', is_staff=True)
    admin.set_password(password)
    admin.save()
    return admin


def creer_technicien(email="tech@test.ci", password="Password123!"):
    tech = Technicien(email=email, nom="Tech Test", role='technicien', matricule=f"T-{email[:5]}")
    tech.set_password(password)
    tech.save()
    return tech


class InscriptionPubliqueDesactiveeTests(APITestCase):
    """Conformément aux diagrammes de cas d'utilisation : PAS d'auto-inscription
    publique. Le Visiteur ne peut que se connecter / réinitialiser son mot de
    passe ; c'est le Technicien/Administrateur qui crée le compte du client."""

    def test_endpoint_inscription_publique_absent(self):
        # La route publique /api/auth/register/ a été retirée du projet.
        response = self.client.post('/api/auth/register/', {
            "email": "nouveau@test.ci", "nom": "Nouveau Client",
            "password": "Password123!", "typeLogement": "Villa",
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Client.objects.filter(email="nouveau@test.ci").exists())

    def test_creation_client_refusee_sans_technicien(self):
        # La création d'un compte client est réservée au technicien/admin.
        response = self.client.post('/api/users/clients/creer/', {
            "email": "x@test.ci", "nom": "X", "password": "Password123!",
        })
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class ConnexionJWTTests(APITestCase):
    def setUp(self):
        self.user = creer_client()

    def test_connexion_valide_renvoie_tokens(self):
        response = self.client.post('/api/auth/login/', {
            "email": "client@test.ci", "password": "Password123!",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_connexion_mot_de_passe_invalide(self):
        response = self.client.post('/api/auth/login/', {
            "email": "client@test.ci", "password": "mauvais",
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profil_me(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], "client@test.ci")
        self.assertEqual(response.data['role'], 'client')

    def test_modification_profil(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.put('/api/users/me/', {"typeLogement": "Villa"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.typeLogement, "Villa")


class AdminGestionComptesTests(APITestCase):
    def setUp(self):
        self.admin = creer_admin()
        self.un_client = creer_client()

    def test_client_ne_peut_pas_lister_les_comptes(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_liste_les_comptes(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        emails = [u['email'] for u in items]
        self.assertIn("client@test.ci", emails)

    def test_admin_cree_compte_technicien(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/users/', {
            "email": "tech@test.ci", "nom": "Tech Test",
            "password": "Password123!", "role": "technicien",
            "matricule": "TECH-0001",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Technicien.objects.filter(email="tech@test.ci").exists())

    def test_admin_desactive_un_compte(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f'/api/users/{self.un_client.id}/', {"estActif": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.un_client.refresh_from_db()
        self.assertFalse(self.un_client.is_active)

    def test_admin_ne_peut_pas_se_supprimer(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/users/{self.admin.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AbonnementTechnicienTests(APITestCase):
    """Le technicien référence l'abonnement et le type de compteur du client."""

    def setUp(self):
        self.technicien = creer_technicien()
        self.un_client = creer_client(email="menage@test.ci", amperage=10, typeCompteur='postpaye')

    def test_technicien_reference_compteur_prepaye(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/users/clients/{self.un_client.id}/abonnement/',
            {"typeCompteur": "prepaye", "amperage": 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.un_client.refresh_from_db()
        self.assertEqual(self.un_client.typeCompteur, 'prepaye')

    def test_5a_force_le_tarif_social(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/users/clients/{self.un_client.id}/abonnement/',
            {"amperage": 5, "typeTarif": "general"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.un_client.refresh_from_db()
        self.assertEqual(self.un_client.amperage, 5)
        self.assertEqual(self.un_client.typeTarif, 'social')

    def test_technicien_liste_les_clients(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get('/api/users/clients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        emails = [c['email'] for c in items]
        self.assertIn("menage@test.ci", emails)

    def test_client_ne_peut_pas_referencer_l_abonnement(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.patch(
            f'/api/users/clients/{self.un_client.id}/abonnement/',
            {"typeCompteur": "prepaye"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_ne_peut_pas_changer_son_compteur_via_profil(self):
        """typeCompteur/amperage/typeTarif sont en lecture seule sur /api/users/me/."""
        self.client.force_authenticate(user=self.un_client)
        response = self.client.put('/api/users/me/',
                                   {"typeCompteur": "prepaye", "amperage": 15})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.un_client.refresh_from_db()
        self.assertEqual(self.un_client.typeCompteur, 'postpaye')  # inchangé
        self.assertEqual(self.un_client.amperage, 10)              # inchangé


class MotDePasseTests(APITestCase):
    """Changement (connecté) et réinitialisation (oubli) du mot de passe."""

    def setUp(self):
        self.user = creer_client(email="pwd@test.ci")

    def test_changement_mdp_ancien_incorrect_refuse(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.put('/api/users/me/password/', {
            "old_password": "MAUVAIS", "new_password": "NouveauPass123!",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Password123!"))

    def test_changement_mdp_succes(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.put('/api/users/me/password/', {
            "old_password": "Password123!", "new_password": "NouveauPass123!",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NouveauPass123!"))

    def test_reset_mdp_flux_complet(self):
        # 1. Demande : un token de réinitialisation est généré et stocké
        req = self.client.post('/api/auth/password/reset/', {"email": "pwd@test.ci"})
        self.assertEqual(req.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        token = self.user.token_reset
        self.assertIsNotNone(token)
        # 2. Confirmation avec le token
        conf = self.client.post('/api/auth/password/reset/confirm/', {
            "email": "pwd@test.ci", "token": str(token), "new_password": "ResetPass123!",
        })
        self.assertEqual(conf.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ResetPass123!"))

    def test_reset_mdp_token_invalide_refuse(self):
        import uuid
        conf = self.client.post('/api/auth/password/reset/confirm/', {
            "email": "pwd@test.ci", "token": str(uuid.uuid4()), "new_password": "ResetPass123!",
        })
        self.assertEqual(conf.status_code, status.HTTP_400_BAD_REQUEST)


class ProfilEnrichiTests(APITestCase):
    """/api/users/me/ : champs téléphone/notifEmail (client) et matricule (technicien)."""

    def test_me_client_contient_telephone_et_notif(self):
        user = creer_client(email="me@test.ci")
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('telephone', response.data)
        self.assertIn('notifEmail', response.data)

    def test_me_technicien_contient_matricule(self):
        tech = creer_technicien(email="tech2@test.ci")
        self.client.force_authenticate(user=tech)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('matricule'), tech.matricule)
        self.assertEqual(response.data.get('role'), 'technicien')

    def test_me_client_met_a_jour_telephone(self):
        user = creer_client(email="tel@test.ci")
        self.client.force_authenticate(user=user)
        response = self.client.put('/api/users/me/', {"telephone": "+225 07 00 00 00"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.telephone, "+225 07 00 00 00")


class SuppressionCompteTests(APITestCase):
    """DELETE /api/users/me/ : suppression définitive avec confirmation par mot de passe."""

    def setUp(self):
        self.user = creer_client(email="todelete@test.ci")

    def test_suppression_avec_bon_mdp(self):
        self.client.force_authenticate(user=self.user)
        from apps.accounts.models import Utilisateur
        uid = self.user.id
        response = self.client.delete('/api/users/me/', {"password": "Password123!"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Utilisateur.objects.filter(id=uid).exists())

    def test_suppression_avec_mauvais_mdp_refuse(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete('/api/users/me/', {"password": "MAUVAIS"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('incorrect', response.data.get('detail', '').lower())
        # Le compte ne doit pas avoir été supprimé
        from apps.accounts.models import Utilisateur
        self.assertTrue(Utilisateur.objects.filter(id=self.user.id).exists())

    def test_suppression_sans_authentification_refuse(self):
        response = self.client.delete('/api/users/me/', {"password": "Password123!"}, format='json')
        self.assertIn(response.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class ProfilFoyerEtPhotoTests(APITestCase):
    """Nouveaux champs foyer (nb personnes, superficie) + photo de profil (upload/suppression)."""

    def setUp(self):
        self.un_client = creer_client(email="foyer@test.ci")
        self.client.force_authenticate(user=self.un_client)

    def test_maj_champs_foyer_reels(self):
        r = self.client.put('/api/users/me/', {
            "adresse": "Cocody, Abidjan", "nbPersonnesFoyer": 4, "superficie_m2": 90,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.un_client.refresh_from_db()
        self.assertEqual(self.un_client.nbPersonnesFoyer, 4)
        self.assertEqual(self.un_client.superficie_m2, 90)
        self.assertEqual(self.un_client.adresse, "Cocody, Abidjan")

    def test_champs_foyer_facultatifs_vidables(self):
        self.un_client.nbPersonnesFoyer = 3
        self.un_client.save()
        r = self.client.put('/api/users/me/', {"nbPersonnesFoyer": None}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.un_client.refresh_from_db()
        self.assertIsNone(self.un_client.nbPersonnesFoyer)

    def _png(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), (245, 166, 35)).save(buf, format='PNG')
        return SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')

    def test_upload_puis_suppression_photo(self):
        r = self.client.post('/api/users/me/photo/', {"photo": self._png()}, format='multipart')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertTrue(r.data.get('photo'))
        self.un_client.refresh_from_db()
        self.assertTrue(self.un_client.photo)
        # La photo revient dans le profil
        me = self.client.get('/api/users/me/')
        self.assertTrue(me.data.get('photo'))
        # Suppression
        d = self.client.delete('/api/users/me/photo/')
        self.assertEqual(d.status_code, status.HTTP_200_OK)
        self.un_client.refresh_from_db()
        self.assertFalse(self.un_client.photo)

    def test_upload_refuse_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('a.txt', b'pas une image', content_type='text/plain')
        r = self.client.post('/api/users/me/photo/', {"photo": bad}, format='multipart')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_photo_refuse_sans_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/users/me/photo/', {}, format='multipart')
        self.assertIn(r.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
