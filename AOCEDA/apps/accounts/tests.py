"""Tests de l'application accounts : inscription, connexion JWT, profil, admin."""
from unittest.mock import patch, MagicMock
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


class RevocationJWTTests(APITestCase):
    """Un changement de mot de passe doit couper court à toute session ouverte
    avec l'ancien mot de passe (jeton volé, autre appareil connecté) — vérifie
    à la fois la révocation immédiate de l'access token (password_changed_at +
    apps.accounts.authentication.TokenAuthentication) et le blacklist du
    refresh token (rest_framework_simplejwt.token_blacklist)."""

    def setUp(self):
        self.user = creer_client()

    def _login(self, password="Password123!"):
        r = self.client.post('/api/auth/login/', {"email": "client@test.ci", "password": password})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        return r.data['access'], r.data['refresh']

    def test_ancien_access_token_rejete_apres_changement_mdp(self):
        old_access, _ = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.assertEqual(self.client.get('/api/users/me/').status_code, status.HTTP_200_OK)

        # Le claim `iat` du JWT est à la précision de la seconde : sans un vrai
        # écart d'au moins 1 s avec password_changed_at, un test exécuté en
        # quelques millisecondes tomberait dans la même seconde et ne prouverait
        # rien (cf. apps/accounts/authentication.py pour le choix de comparer
        # aux secondes entières, qui protège au contraire le cas légitime
        # « nouvelle connexion juste après le changement »).
        import time
        time.sleep(1.1)

        r = self.client.put('/api/users/me/password/', {
            "old_password": "Password123!", "new_password": "NouveauMdp2026!",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

        # Même jeton, même en-tête : doit maintenant être refusé (401), pas expiré
        # mais émis avant password_changed_at.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ancien_refresh_token_blackliste_apres_changement_mdp(self):
        old_access, old_refresh = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.client.put('/api/users/me/password/', {
            "old_password": "Password123!", "new_password": "NouveauMdp2026!",
        })
        self.client.credentials()  # pas besoin d'auth pour /refresh/
        response = self.client.post('/api/auth/refresh/', {"refresh": old_refresh})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_connexion_avec_nouveau_mot_de_passe_fonctionne(self):
        old_access, _ = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.client.put('/api/users/me/password/', {
            "old_password": "Password123!", "new_password": "NouveauMdp2026!",
        })
        self.client.credentials()
        new_access, _ = self._login(password="NouveauMdp2026!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        self.assertEqual(self.client.get('/api/users/me/').status_code, status.HTTP_200_OK)

    def test_reinitialisation_mot_de_passe_revoque_aussi_les_jetons(self):
        """Même garantie côté « mot de passe oublié » (PasswordResetConfirmView)."""
        old_access, _ = self._login()
        import time
        time.sleep(1.1)  # cf. commentaire dans test_ancien_access_token_rejete_apres_changement_mdp
        self.user.token_reset = "11111111-1111-1111-1111-111111111111"
        from django.utils import timezone
        from datetime import timedelta
        self.user.date_expiration_token = timezone.now() + timedelta(hours=1)
        self.user.save(update_fields=['token_reset', 'date_expiration_token'])

        r = self.client.post('/api/auth/password/reset/confirm/', {
            "email": "client@test.ci",
            "token": "11111111-1111-1111-1111-111111111111",
            "new_password": "ApresReset2026!",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


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

    def test_edition_abonnement_est_journalisee(self):
        from apps.accounts.models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/users/clients/{self.un_client.id}/abonnement/',
            {"typeCompteur": "prepaye"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entree = AuditLog.objects.get(action='EDITION_ABONNEMENT')
        self.assertEqual(entree.utilisateur_id, self.technicien.id)
        self.assertEqual(entree.client_id, self.un_client.id)
        self.assertIn('postpaye', entree.description)
        self.assertIn('prepaye', entree.description)

    def test_abonnement_sans_changement_ne_journalise_rien(self):
        from apps.accounts.models import AuditLog
        AuditLog.objects.all().delete()
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(
            f'/api/users/clients/{self.un_client.id}/abonnement/',
            {"typeCompteur": "postpaye"})  # valeur déjà en place, aucun changement réel
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.filter(action='EDITION_ABONNEMENT').count(), 0)


class JournalEquipeCreationEditionClientTests(APITestCase):
    """Traçabilité de la création/édition de compte client par un technicien
    (mémoire §6.2.2 : « le compte client est créé par le technicien lors de
    l'installation » — cette responsabilité doit être journalisée)."""

    def setUp(self):
        self.technicien = creer_technicien()

    def test_creation_client_par_technicien_est_journalisee(self):
        from apps.accounts.models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/users/clients/creer/', {
            "email": "nouveau.client@test.ci", "nom": "Nouveau Client",
            "password": "Password123!",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        nouveau_client = Client.objects.get(email="nouveau.client@test.ci")
        entree = AuditLog.objects.get(action='CREATION_CLIENT')
        self.assertEqual(entree.utilisateur_id, self.technicien.id)
        self.assertEqual(entree.client_id, nouveau_client.id)

    def test_edition_client_par_technicien_est_journalisee(self):
        from apps.accounts.models import AuditLog
        un_client = creer_client(email="edit@test.ci", nom="Ancien Nom")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.patch(f'/api/users/clients/{un_client.id}/', {"nom": "Nouveau Nom"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entree = AuditLog.objects.get(action='EDITION_CLIENT')
        self.assertIn('Ancien Nom', entree.description)
        self.assertIn('Nouveau Nom', entree.description)


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


def _reponse_llm_ok(mock_post):
    """Mock minimal d'une réponse HTTP compatible OpenAI (200, contenu 'OK') —
    suffisant pour satisfaire verifier_cle_fonctionnelle."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'choices': [{'message': {'content': 'OK'}}]}
    mock_post.return_value = mock_resp


class CleApiIAPersonnelleTests(APITestCase):
    """/api/users/me/ : la clé API IA perso est validée à l'ENREGISTREMENT — format
    reconnu (voir apps.ai_assistant.fournisseurs_llm.detecter_fournisseur) ET un
    VRAI appel de test réussi (voir verifier_cle_fonctionnelle) — plutôt que
    d'échouer silencieusement au premier message envoyé à l'assistant. Le réseau
    est mocké : ces tests valident notre logique, pas la disponibilité d'un vrai
    fournisseur."""

    def setUp(self):
        self.user = creer_client(email="ia-cle@test.ci")
        self.client.force_authenticate(user=self.user)

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_cle_openai_qui_fonctionne_acceptee(self, mock_post):
        _reponse_llm_ok(mock_post)
        r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": "sk-proj-abcdefghijklmnop"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cle_api_ia_personnelle, "sk-proj-abcdefghijklmnop")
        mock_post.assert_called_once()

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_cle_gemini_qui_fonctionne_acceptee(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'OK'}]}}]}
        mock_post.return_value = mock_resp
        r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": "AIzaSyAbc123def456ghi789jkl012mno345pqr"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_cle_anthropic_qui_fonctionne_acceptee(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'content': [{'type': 'text', 'text': 'OK'}]}
        mock_post.return_value = mock_resp
        r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": "sk-ant-api03-abcdefgh"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_cle_format_non_reconnu_refusee_sans_appel_reseau(self):
        """Une clé au format inconnu (ni OpenAI/Gemini/Anthropic/DeepSeek/xAI) est
        refusée avec un message clair, SANS même tenter d'appel réseau — jamais
        acceptée pour échouer en silence ensuite au premier message IA."""
        with patch('apps.ai_assistant.fournisseurs_llm.requests.post') as mock_post:
            r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": "un-jeton-quelconque"})
            mock_post.assert_not_called()
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cle_api_ia_personnelle', r.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.cle_api_ia_personnelle)

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_cle_au_bon_format_mais_qui_ne_marche_pas_refusee(self, mock_post):
        """Une clé au format reconnu MAIS refusée par le vrai fournisseur (401 —
        révoquée/invalide) n'est PAS enregistrée : la garantie n'est pas juste 'le
        format ressemble à une clé', mais 'cette clé fonctionne vraiment'."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error": "invalid api key"}'
        mock_post.return_value = mock_resp

        r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": "sk-proj-abcdefghijklmnop"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cle_api_ia_personnelle', r.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.cle_api_ia_personnelle)

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_cle_inchangee_pas_revérifiée_sur_maj_sans_rapport(self, mock_post):
        """Mettre à jour un autre champ (téléphone) sans toucher à la clé perso ne
        doit PAS redéclencher un appel réseau à chaque sauvegarde de profil."""
        self.user.cle_api_ia_personnelle = 'sk-proj-abcdefghijklmnop'
        self.user.save()
        r = self.client.put('/api/users/me/', {
            "cle_api_ia_personnelle": "sk-proj-abcdefghijklmnop",
            "telephone": "+225 07 00 00 00",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        mock_post.assert_not_called()

    def test_url_perso_sans_modele_refusee(self):
        r = self.client.put('/api/users/me/', {"url_api_ia_personnelle": "https://exemple.ci/v1/chat/completions"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('modele_api_ia_personnelle', r.data)

    @patch('apps.ai_assistant.fournisseurs_llm.requests.post')
    def test_url_et_modele_perso_acceptes_ensemble(self, mock_post):
        _reponse_llm_ok(mock_post)
        r = self.client.put('/api/users/me/', {
            "cle_api_ia_personnelle": "un-jeton-quelconque",
            "url_api_ia_personnelle": "https://exemple.ci/v1/chat/completions",
            "modele_api_ia_personnelle": "mon-modele",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_cle_vide_toujours_acceptee_sans_appel_reseau(self):
        """Vider la clé (retour au fournisseur partagé du projet) ne doit jamais
        être bloqué par la validation, ni déclencher d'appel réseau."""
        self.user.cle_api_ia_personnelle = 'sk-proj-abcdefghijklmnop'
        self.user.save()
        with patch('apps.ai_assistant.fournisseurs_llm.requests.post') as mock_post:
            r = self.client.put('/api/users/me/', {"cle_api_ia_personnelle": ""})
            mock_post.assert_not_called()
        self.assertEqual(r.status_code, status.HTTP_200_OK)


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


class AuditLogTests(APITestCase):
    def test_audit_log_connexion_signal(self):
        from .models import AuditLog
        AuditLog.objects.all().delete()

        # Connecter un utilisateur
        creer_client(email="test.audit@test.local")
        self.client.post('/api/auth/login/', {
            "email": "test.audit@test.local", "password": "Password123!"
        })

        # Vérifier que le log d'audit de connexion a été créé
        logs = AuditLog.objects.filter(action='CONNEXION')
        self.assertTrue(logs.exists())
        self.assertIn("connecté", logs.first().description)

    def test_audit_log_deconnexion_explicite(self):
        """L'authentification JWT ne déclenche jamais le signal user_logged_out :
        la déconnexion doit être journalisée explicitement par un endpoint dédié."""
        from .models import AuditLog
        user = creer_client(email="logout.audit@test.local")
        AuditLog.objects.all().delete()
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        logs = AuditLog.objects.filter(action='DÉCONNEXION')
        self.assertTrue(logs.exists())
        self.assertEqual(logs.first().utilisateur_id, user.id)

    def test_deconnexion_refusee_sans_authentification(self):
        response = self.client.post('/api/auth/logout/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class DemandeDesactivationTests(APITestCase):
    """Le bouton « Demander la désactivation » du profil technicien n'exécutait
    auparavant qu'un alert() JS sans aucun effet réel."""

    def setUp(self):
        self.technicien = creer_technicien(email="desact@test.ci")
        self.admin = creer_admin(email="admin.desact@test.ci")

    def test_technicien_demande_desactivation(self):
        from django.core import mail
        from .models import AuditLog
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/users/me/demander-desactivation/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditLog.objects.filter(action='DEMANDE_DESACTIVATION', utilisateur=self.technicien).exists())
        self.assertTrue(any(self.admin.email in m.to for m in mail.outbox))

    def test_client_ne_peut_pas_demander_desactivation(self):
        client_user = creer_client(email="clientdesact@test.ci")
        self.client.force_authenticate(user=client_user)
        response = self.client.post('/api/users/me/demander-desactivation/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_demande_desactivation_refusee_sans_authentification(self):
        response = self.client.post('/api/users/me/demander-desactivation/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class NoteClientTests(APITestCase):
    """Notes internes technicien sur un client — jamais visibles du client,
    plusieurs notes cumulées (jamais un champ unique écrasé)."""

    def setUp(self):
        self.technicien = creer_technicien(email="notea@test.ci")
        self.autre_tech = creer_technicien(email="noteb@test.ci")
        self.un_client = creer_client(email="note.client@test.ci")

    def test_technicien_ajoute_une_note(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/users/clients/notes/', {
            "client": str(self.un_client.id), "contenu": "Accès facile, RAS.",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['technicien_nom'], self.technicien.nom)

    def test_note_vide_refusee(self):
        self.client.force_authenticate(user=self.technicien)
        response = self.client.post('/api/users/clients/notes/', {
            "client": str(self.un_client.id), "contenu": "   ",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_notes_cumulees_visibles_par_toute_l_equipe(self):
        """Plusieurs techniciens peuvent voir/ajouter des notes sur le même client
        (cohérent avec le pool partagé, pas de note écrasée)."""
        from .models import NoteClient
        NoteClient.objects.create(client=self.un_client, technicien=self.technicien, contenu="Note A")
        NoteClient.objects.create(client=self.un_client, technicien=self.autre_tech, contenu="Note B")
        self.client.force_authenticate(user=self.technicien)
        response = self.client.get(f'/api/users/clients/notes/?client={self.un_client.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contenus = {n['contenu'] for n in response.data['results']}
        self.assertEqual(contenus, {"Note A", "Note B"})

    def test_client_ne_peut_pas_acceder_aux_notes(self):
        self.client.force_authenticate(user=self.un_client)
        response = self.client.get(f'/api/users/clients/notes/?client={self.un_client.id}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

