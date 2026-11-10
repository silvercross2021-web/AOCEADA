"""Tests automatisés de l'interface utilisateur (/ia/ et /ia/assistant/).

Vérifie :
1. Le code HTTP 200 et les gabarits rendus sur /ia/ et /ia/assistant/.
2. La protection et redirection/refus pour utilisateur non authentifié.
3. La présence des 5 boutons d'en-tête canoniques dans aoceda-ia.html (nouvelle, historique, options, credits, plein_ecran).
4. La présence du cadre iframe #assistant-cadre et du script assistant-page.js.
5. La présence des éléments clés dans le HTML d'assistant.html (#btn_historique, #btn_options, #btn_credits, #perso_dock, saisie).
6. La conformité des styles dans assistant.css (.cd-oui, .cd-non, .assistant-plein-ecran, contraste WCAG AA, responsive).
"""
import re
from pathlib import Path
from django.test import TestCase, Client as TestClient
from django.conf import settings
from rest_framework import status

from apps.accounts.models import Client, Utilisateur


class AssistantUITests(TestCase):
    """Suite de vérifications automatisées de l'interface utilisateur de l'assistant IA."""

    @classmethod
    def setUpTestData(cls):
        cls.client_user = Client.objects.create_user(
            email='client_ui@test.ci',
            nom='Client Test UI',
            password='Password123!'
        )

    def setUp(self):
        self.http = TestClient()
        self.http.force_login(self.client_user)

    def test_rendu_ia_page_authentifie(self):
        """La route /ia/ renvoie HTTP 200 et le gabarit aoceda-ia.html avec tous ses composants."""
        reponse = self.http.get('/ia/')
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, 'aoceda-ia.html')
        html = reponse.content.decode('utf-8')

        # Iframe du cadre assistant
        self.assertIn('id="assistant-cadre"', html)
        self.assertIn('class="assistant-cadre"', html)
        self.assertIn('allow="microphone; camera; display-capture; autoplay; fullscreen; clipboard-write"', html)

        # Script assistant-page.js avec cache busting
        self.assertRegex(html, r'assistant-page\.js\?v=\d+')

        # Bouton quitter le plein écran
        self.assertIn('id="btn_quitter_plein_ecran"', html)
        self.assertIn('class="bouton-quitter-plein-ecran"', html)

    def test_presence_des_5_boutons_entete_canoniques(self):
        """L'en-tête de aoceda-ia.html doit présenter les 5 actions : nouvelle, historique, options, credits, plein_ecran."""
        reponse = self.http.get('/ia/')
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')

        boutons_attendus = ['nouvelle', 'historique', 'options', 'credits', 'plein_ecran']
        for action in boutons_attendus:
            self.assertIn(
                f'data-assistant="{action}"',
                html,
                f"Le bouton avec data-assistant='{action}' est manquant dans l'en-tête de aoceda-ia.html"
            )

        # Vérifier que le bouton plein écran a son identifiant et aria-pressed
        self.assertIn('id="btn_plein_ecran"', html)
        self.assertIn('aria-pressed="false"', html)

    def test_rendu_assistant_cadre_et_securite(self):
        """La page /ia/assistant/ renvoie HTTP 200, ses en-têtes CSP/SAMEORIGIN et ses éléments clés."""
        reponse = self.http.get('/ia/assistant/')
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, 'assistant.html')

        # En-têtes de sécurité
        self.assertEqual(reponse.get('X-Frame-Options'), 'SAMEORIGIN')
        csp = reponse.get('Content-Security-Policy', '')
        self.assertIn("frame-ancestors 'self'", csp)

        perm_policy = reponse.get('Permissions-Policy', '')
        self.assertIn('microphone=(self)', perm_policy)

        html = reponse.content.decode('utf-8')

        # Cibles des actions d'en-tête dans l'assistant
        self.assertIn('id="nouvelle"', html)
        self.assertIn('id="btn_historique"', html)
        self.assertIn('id="btn_options"', html)
        self.assertIn('id="btn_credits"', html)

        # Composants interactifs clés
        self.assertIn('id="perso_dock"', html)
        self.assertIn('id="vue_chat"', html)
        self.assertIn('id="fil"', html)
        self.assertIn('id="texte"', html)
        self.assertIn('id="micro"', html)
        self.assertIn('id="btn_live"', html)
        self.assertIn('id="envoyer"', html)

        # Feuilles modales
        self.assertIn('id="feuille_options"', html)
        self.assertIn('id="feuille_historique"', html)
        self.assertIn('id="feuille_credits"', html)

        # Scripts du personnage et du client assistant
        self.assertIn('static/js/personnage.js?v=', html)
        self.assertIn('static/js/assistant.js?v=', html)

    def test_protection_non_authentifie_api_et_redirection(self):
        """Les requêtes API de l'assistant sans jeton JWT renvoient 401 et la page intègre le garde-fou vers /auth/."""
        client_anonyme = TestClient()

        # L'API protégée refuse les utilisateurs non authentifiés
        rep_api = client_anonyme.get('/api/assistant/conversations/')
        self.assertEqual(rep_api.status_code, status.HTTP_401_UNAUTHORIZED)

        rep_credits = client_anonyme.get('/api/assistant/credits')
        self.assertEqual(rep_credits.status_code, status.HTTP_401_UNAUTHORIZED)

        # Le gabarit assistant.html contient la vérification JS de token avec redirection vers /auth/
        reponse_cadre = client_anonyme.get('/ia/assistant/')
        self.assertEqual(reponse_cadre.status_code, 200)
        html = reponse_cadre.content.decode('utf-8')
        self.assertIn('aoceda_access_token', html)
        self.assertIn('/auth/', html)

    def test_script_assistant_page_logique_et_mapping(self):
        """Le script assistant-page.js intègre la table d'alias ACTION_MAP, la file d'attente et le plein écran."""
        chemin_js = Path(settings.BASE_DIR) / 'static' / 'js' / 'assistant-page.js'
        self.assertTrue(chemin_js.exists(), "Le fichier static/js/assistant-page.js n'existe pas")
        code = chemin_js.read_text(encoding='utf-8')

        # Présence de la table de correspondance d'actions canoniques
        self.assertIn('ACTION_MAP', code)
        self.assertIn("'nouvelle': 'nouvelle'", code)
        self.assertIn("'historique': 'btn_historique'", code)
        self.assertIn("'options': 'btn_options'", code)
        self.assertIn("'credits': 'btn_credits'", code)
        self.assertIn("'plein_ecran': 'toggle_plein_ecran'", code)

        # Présence de la file d'attente pré-chargement
        self.assertIn('actionQueue', code)
        self.assertIn('viderFileAttente', code)

        # Logique de plein écran et gestion Escape
        self.assertIn('basculerPleinEcran', code)
        self.assertIn('assistant-plein-ecran', code)
        self.assertIn('aria-pressed', code)
        self.assertIn("'Escape'", code)

        # Synchronisation synchrone du thème
        self.assertIn('synchroniserThemeCadre', code)
        self.assertIn('data-theme', code)

    def test_css_regles_securite_coupure_et_plein_ecran(self):
        """assistant.css contient les règles critiques pour .cd-oui, .cd-non, .assistant-plein-ecran et le contraste."""
        chemin_css = Path(settings.BASE_DIR) / 'static' / 'css' / 'assistant.css'
        self.assertTrue(chemin_css.exists(), "Le fichier static/css/assistant.css n'existe pas")
        css = chemin_css.read_text(encoding='utf-8')

        # Style alerte / danger très net pour .cd-oui
        self.assertIn('.cd-oui', css)
        self.assertRegex(css, r'\.cd-oui[^{]*\{[^}]*background:[^;]*var\(--ko')

        # Style sécurisant / secondaire pour .cd-non
        self.assertIn('.cd-non', css)
        self.assertRegex(css, r'\.cd-non[^{]*\{[^}]*background:[^;]*var\(--surface')

        # Mode plein écran immersif
        self.assertIn('.assistant-plein-ecran', css)
        self.assertIn('position: fixed !important', css)
        self.assertIn('inset: 0 !important', css)
        self.assertIn('z-index: 99999 !important', css)

        # Contraste rehaussé de --tres-doux (WCAG AA >= 4.5:1)
        self.assertIn('--tres-doux: #68717d', css)

        # Optimisation responsive petits écrans (< 400px)
        self.assertIn('@media (max-width: 400px)', css)
        self.assertIn('textarea { font-size: 15px', css)

    def test_securisation_personnage_directeur(self):
        """personnage.js intègre une classe Directeur avec méthode duree() sécurisée contre tout crash TypeError."""
        chemin_personnage = Path(settings.BASE_DIR) / 'static' / 'js' / 'personnage.js'
        self.assertTrue(chemin_personnage.exists())
        js = chemin_personnage.read_text(encoding='utf-8')

        self.assertIn('class Directeur', js)
        self.assertIn('duree(nom, o)', js)
        self.assertIn('if (!a) return Infinity;', js)
        self.assertIn('Directeur', js)
        self.assertIn('window.AocedaPersonnage', js)
