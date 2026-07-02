"""Tests de l'assistant IA : quota journalier (429), réinitialisation au lendemain,
refus pour non-clients, et protection contre les messages trop longs."""
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import Client, Technicien
from .models import ConversationIA


def creer_client(email='client@test.ci', password='Password123!'):
    c = Client(email=email, nom='Client IA', role='client', typeCompteur='postpaye')
    c.set_password(password)
    c.save()
    return c


def creer_technicien(email='tech@test.ci', password='Password123!'):
    t = Technicien(email=email, nom='Tech IA', role='technicien', matricule='T-IA01')
    t.set_password(password)
    t.save()
    return t


class QuotaIATests(APITestCase):
    """Le quota journalier de 10 requêtes est appliqué ; dépassement → 429."""

    def setUp(self):
        self.user = creer_client()

    def _post_chat(self, message='Bonjour'):
        return self.client.post('/api/assistant/chat/', {'message': message},
                                format='json')

    @patch('apps.ai_assistant.views.requests.post')
    def test_quota_epuise_renvoie_429(self, mock_post):
        """Après 10 requêtes, la 11ème est rejetée avec 429."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'choices': [{'message': {'content': 'Réponse test.'}}]
        }
        mock_post.return_value = mock_resp

        self.client.force_authenticate(user=self.user)
        # Consomme les 10 requêtes autorisées
        for _ in range(10):
            r = self._post_chat()
            self.assertEqual(r.status_code, status.HTTP_200_OK)

        # La 11ème doit être refusée
        r = self._post_chat()
        self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Limite quotidienne', r.data.get('detail', ''))

    def test_quota_reinitialise_le_lendemain(self):
        """Si la dernière requête date d'hier, le compteur est remis à zéro."""
        self.client.force_authenticate(user=self.user)
        # Crée la conversation avec get_or_create puis force la date via .update()
        # (auto_now=True rend save() inutile pour remonter la date).
        conv, _ = ConversationIA.objects.get_or_create(client=self.user.client)
        ConversationIA.objects.filter(pk=conv.pk).update(
            nb_requetes_aujourd_hui=10,
            timestamp=timezone.now() - timedelta(days=1),
        )

        # Le GET (historique) doit réinitialiser le compteur
        r = self.client.get('/api/assistant/chat/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        conv.refresh_from_db()
        self.assertEqual(conv.nb_requetes_aujourd_hui, 0)

    def test_technicien_ne_peut_pas_utiliser_le_chat(self):
        """L'assistant IA est réservé aux clients (403 pour les autres rôles)."""
        tech = creer_technicien()
        self.client.force_authenticate(user=tech)
        r = self._post_chat()
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_message_trop_long_refuse(self):
        """Un message dépassant 2000 caractères est refusé avec 400."""
        self.client.force_authenticate(user=self.user)
        r = self._post_chat(message='A' * 2001)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_message_vide_refuse(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post('/api/assistant/chat/', {'message': '   '}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.ai_assistant.views.requests.post')
    def test_quota_incremente_apres_reponse_ok(self, mock_post):
        """Chaque requête réussie incrémente le compteur."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'choices': [{'message': {'content': 'OK'}}]
        }
        mock_post.return_value = mock_resp

        self.client.force_authenticate(user=self.user)
        self._post_chat()
        conv = ConversationIA.objects.get(client=self.user.client)
        self.assertEqual(conv.nb_requetes_aujourd_hui, 1)
