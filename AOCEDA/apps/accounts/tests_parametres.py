"""Menu Paramètres du client (20/10/2026) : profil et logement validés, photo réellement contrôlée, changement de mot de
passe qui garde la session, double authentification en deux temps, connexions récentes, déconnexion de tous les appareils,
export des données personnelles, suppression réservée aux clients."""
import io
import json
import os
import time
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AuditLog, Client, Technicien, Utilisateur

from .tests import creer_client, creer_technicien

ME = '/api/users/me/'


def png(taille=(8, 8)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', taille, (245, 166, 35)).save(buf, format='PNG')
    return buf.getvalue()


class ProfilValidationTests(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="profil.param@test.ci")
        self.client.force_authenticate(user=self.cl)

    def put(self, **corps):
        return self.client.put(ME, corps, format='json')

    def test_nom_trop_court_ou_vide_refuse_et_espaces_normalises(self):
        self.assertEqual(self.put(nom="A").status_code, 400)
        self.assertEqual(self.put(nom="   ").status_code, 400)
        r = self.put(nom="  Konaté   Adjoua  Marie ")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['nom'], "Konaté Adjoua Marie")

    def test_telephone(self):
        for faux in ("abc", "12", "+225 01 02 03 04 05 06 07 08 09 10"):
            self.assertEqual(self.put(telephone=faux).status_code, 400, faux)
        self.assertEqual(self.put(telephone="+225 01 02 03 04 05").status_code, 200)
        r = self.put(telephone="")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data['telephone'])

    def test_foyer_bornes(self):
        self.assertEqual(self.put(nbPersonnesFoyer=0).status_code, 400)
        self.assertEqual(self.put(nbPersonnesFoyer=31).status_code, 400)
        self.assertEqual(self.put(superficie_m2=0).status_code, 400)
        self.assertEqual(self.put(superficie_m2=20000).status_code, 400)
        self.assertEqual(self.put(adresse="x" * 301).status_code, 400)
        r = self.put(nbPersonnesFoyer=4, superficie_m2=90, adresse="  Cocody, Abidjan ")
        self.assertEqual((r.status_code, r.data['adresse']), (200, "Cocody, Abidjan"))

    def test_la_ville_regle_la_taxe_sur_les_ordures(self):
        r = self.put(ville="Bouaké")
        self.assertEqual((r.status_code, r.data['ville'], r.data['horsAbidjan']), (200, 'Bouaké', True))
        r = self.put(ville="Abidjan")
        self.assertEqual((r.data['ville'], r.data['horsAbidjan']), ('Abidjan', False))
        self.assertEqual(self.put(ville="Atlantide").status_code, 400)

    def test_la_double_authentification_ne_s_active_pas_par_le_profil(self):
        self.put(is_2fa_enabled=True)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)

    def test_technicien_meme_validation(self):
        tech = creer_technicien(email="tech.param@test.ci")
        self.client.force_authenticate(user=tech)
        self.assertEqual(self.put(nom="A").status_code, 400)
        self.assertEqual(self.put(telephone="abc").status_code, 400)


class PhotoTests(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="photo.param@test.ci")
        self.client.force_authenticate(user=self.cl)

    def envoyer(self, contenu, nom='a.png', type_='image/png'):
        return self.client.post('/api/users/me/photo/', {"photo": SimpleUploadedFile(nom, contenu, content_type=type_)}, format='multipart')

    def test_un_faux_png_est_refuse(self):
        for nom, contenu in (("x.png", b"<html><script>alert(1)</script></html>"), ("x.png", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
                             ("x.png", b"")):
            r = self.envoyer(contenu, nom)
            self.assertEqual(r.status_code, 400, nom)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.photo)

    def test_une_vraie_image_est_recompressee_sous_un_nom_aleatoire(self):
        r = self.envoyer(png((2000, 1000)), nom="../../evil.html")
        self.assertEqual(r.status_code, 200, r.data)
        self.cl.refresh_from_db()
        nom = os.path.basename(self.cl.photo.name)
        self.assertTrue(nom.endswith('.jpg'))
        self.assertNotIn('evil', self.cl.photo.name)
        from PIL import Image
        with Image.open(self.cl.photo.path) as img:
            self.assertEqual(img.format, 'JPEG')
            self.assertLessEqual(max(img.size), 800)
        self.client.delete('/api/users/me/photo/')

    def test_remplacer_efface_l_ancien_fichier(self):
        self.envoyer(png())
        self.cl.refresh_from_db()
        ancien = self.cl.photo.path
        self.assertTrue(os.path.exists(ancien))
        self.envoyer(png((20, 20)))
        self.assertFalse(os.path.exists(ancien))
        self.cl.refresh_from_db()
        chemin = self.cl.photo.path
        self.client.delete('/api/users/me/photo/')
        self.assertFalse(os.path.exists(chemin))


class MotDePasseSessionTests(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="mdp.param@test.ci")

    def connexion(self, mdp="Password123!"):
        r = self.client.post('/api/auth/login/', {"email": "mdp.param@test.ci", "password": mdp})
        self.assertEqual(r.status_code, 200, r.data)
        return r.data['access'], r.data['refresh']

    def test_mot_de_passe_sans_majuscule_ou_sans_chiffre_refuse(self):
        self.client.force_authenticate(user=self.cl)
        for faible in ("motdepasse2026", "MotDePasseSeul", "Abcdefg"):
            r = self.client.put('/api/users/me/password/', {"old_password": "Password123!", "new_password": faible}, format='json')
            self.assertEqual(r.status_code, 400, faible)

    def test_la_session_en_cours_reste_ouverte_mais_les_autres_sont_fermees(self):
        ancien_acces, ancien_refresh = self.connexion()
        autre_acces, _ = self.connexion()                 # « un autre appareil »
        time.sleep(1.1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {ancien_acces}")
        r = self.client.put('/api/users/me/password/', {"old_password": "Password123!", "new_password": "NouveauMdp2026!"}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['access'] and r.data['refresh'])
        # les nouveaux jetons fonctionnent tout de suite
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.assertEqual(self.client.get(ME).status_code, 200)
        # l'ancien jeton et celui de l'autre appareil sont refusés
        for vieux in (ancien_acces, autre_acces):
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {vieux}")
            self.assertEqual(self.client.get(ME).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/refresh/', {"refresh": ancien_refresh}).status_code, 401)
        self.assertTrue(AuditLog.objects.filter(action='CHANGEMENT_MOT_DE_PASSE', utilisateur=self.cl).exists())

    def test_reinitialisation_exige_aussi_majuscule_et_chiffre(self):
        self.cl.token_reset = "22222222-2222-2222-2222-222222222222"
        self.cl.date_expiration_token = timezone.now() + timedelta(hours=1)
        self.cl.save(update_fields=['token_reset', 'date_expiration_token'])
        r = self.client.post('/api/auth/password/reset/confirm/', {"email": "mdp.param@test.ci", "token": "22222222-2222-2222-2222-222222222222",
                                                                    "new_password": "toutenminuscule"})
        self.assertEqual(r.status_code, 400)


class DoubleFacteurTests(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="a2f.param@test.ci")
        self.client.force_authenticate(user=self.cl)

    def activer_demande(self):
        with mock.patch('apps.accounts.views.send_mail_async') as envoi:
            r = self.client.post('/api/users/me/2fa/', {"enable": True}, format='json')
        return r, envoi

    def test_activation_en_deux_temps(self):
        r, envoi = self.activer_demande()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['pending'])
        self.assertIn('***', r.data['email'])
        self.assertEqual(envoi.call_count, 1)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)                      # pas encore active : le code n'a pas été confirmé
        code = self.cl.two_factor_code
        self.assertEqual(len(code), 6)
        self.assertIn(code, envoi.call_args[0][1])
        r = self.client.post('/api/users/me/2fa/', {"enable": True, "code": code}, format='json')
        self.assertEqual((r.status_code, r.data['is_2fa_enabled']), (200, True))
        self.cl.refresh_from_db()
        self.assertTrue(self.cl.is_2fa_enabled)
        self.assertIsNone(self.cl.two_factor_code)
        self.assertTrue(AuditLog.objects.filter(action='A2F_ACTIVEE', utilisateur=self.cl).exists())

    def test_mauvais_code_ou_code_expire_refuse(self):
        self.activer_demande()
        r = self.client.post('/api/users/me/2fa/', {"enable": True, "code": "000000"}, format='json')
        self.assertEqual(r.status_code, 400)
        self.cl.refresh_from_db()
        self.cl.two_factor_expiration = timezone.now() - timedelta(minutes=1)      # code expiré
        self.cl.save(update_fields=['two_factor_expiration'])
        r = self.client.post('/api/users/me/2fa/', {"enable": True, "code": self.cl.two_factor_code}, format='json')
        self.assertEqual(r.status_code, 400)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)

    def test_trop_d_essais(self):
        self.activer_demande()
        self.cl.refresh_from_db()
        vrai = self.cl.two_factor_code
        for _ in range(5):
            self.client.post('/api/users/me/2fa/', {"enable": True, "code": "999999" if vrai != "999999" else "111111"}, format='json')
        r = self.client.post('/api/users/me/2fa/', {"enable": True, "code": vrai}, format='json')
        self.assertEqual(r.status_code, 400)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)

    def test_pas_de_nouveau_code_avant_30_secondes(self):
        self.activer_demande()
        r, envoi = self.activer_demande()
        self.assertTrue(r.data['pending'])
        envoi.assert_not_called()

    def test_desactivation_demande_le_mot_de_passe(self):
        self.cl.is_2fa_enabled = True
        self.cl.save(update_fields=['is_2fa_enabled'])
        r = self.client.post('/api/users/me/2fa/', {"enable": False}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/users/me/2fa/', {"enable": False, "password": "faux"}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/users/me/2fa/', {"enable": False, "password": "Password123!"}, format='json')
        self.assertEqual((r.status_code, r.data['is_2fa_enabled']), (200, False))
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)

    def test_la_chaine_false_n_active_rien(self):
        r = self.client.post('/api/users/me/2fa/', {"enable": "false", "password": "Password123!"})
        self.assertEqual(r.status_code, 200)
        self.cl.refresh_from_db()
        self.assertFalse(self.cl.is_2fa_enabled)

    def test_technicien_comportement_historique(self):
        tech = creer_technicien(email="a2f.tech@test.ci")
        self.client.force_authenticate(user=tech)
        r = self.client.post('/api/users/me/2fa/', {"enable": True}, format='json')
        self.assertEqual(r.data, {"is_2fa_enabled": True})


class SessionsEtExportTests(APITestCase):
    def setUp(self):
        self.cl = creer_client(email="sess.param@test.ci")

    def test_connexions_recentes(self):
        r = self.client.post('/api/auth/login/', {"email": "sess.param@test.ci", "password": "Password123!"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        AuditLog.objects.create(utilisateur=self.cl, role='client', action='UNE_AUTRE_ACTION', description='x')
        data = self.client.get('/api/users/me/connexions/').data
        self.assertEqual(data['evenements'][0]['action'], 'CONNEXION')
        self.assertTrue(all(e['action'] != 'UNE_AUTRE_ACTION' for e in data['evenements']))

    def test_les_connexions_d_un_autre_ne_sont_pas_visibles(self):
        autre = creer_client(email="autre.param@test.ci")
        AuditLog.objects.create(utilisateur=autre, role='client', action='CONNEXION', description='autre')
        self.client.force_authenticate(user=self.cl)
        self.assertEqual(self.client.get('/api/users/me/connexions/').data['evenements'], [])

    def test_deconnexion_de_tous_les_appareils(self):
        r = self.client.post('/api/auth/login/', {"email": "sess.param@test.ci", "password": "Password123!"})
        access, refresh = r.data['access'], r.data['refresh']
        time.sleep(1.1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.post('/api/users/me/deconnexion-partout/').status_code, 200)
        self.assertEqual(self.client.get(ME).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/refresh/', {"refresh": refresh}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login/', {"email": "sess.param@test.ci", "password": "Password123!"}).status_code, 200)

    def test_export_des_donnees_personnelles(self):
        from apps.sensors.models import Capteur, Dispositif
        from decimal import Decimal
        d = Dispositif.objects.create(client=self.cl, apiKeyDevice="SECRET_CLE_BOITIER", numeroSerie="SN-1")
        Capteur.objects.create(client=self.cl, dispositif=d, nom="Climatiseur", valeurMax=Decimal("2000"))
        autre = creer_client(email="autre.export@test.ci")
        Capteur.objects.create(client=autre, nom="Frigo du voisin")
        self.client.force_authenticate(user=self.cl)
        r = self.client.get('/api/users/me/export/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r['Content-Disposition'])
        texte = r.content.decode('utf-8')
        data = json.loads(texte)
        self.assertEqual(data['compte']['email'], "sess.param@test.ci")
        self.assertEqual([c['nom'] for c in data['capteurs']], ["Climatiseur"])
        self.assertNotIn("SECRET_CLE_BOITIER", texte)
        self.assertNotIn("Frigo du voisin", texte)
        self.assertNotIn("password", texte.lower().replace('mot de passe', ''))

    def test_export_refuse_sans_authentification(self):
        self.assertEqual(self.client.get('/api/users/me/export/').status_code, 401)


class SuppressionReserveeAuxClientsTests(APITestCase):
    def test_un_technicien_ne_se_supprime_pas_d_ici(self):
        tech = creer_technicien(email="del.tech@test.ci")
        self.client.force_authenticate(user=tech)
        r = self.client.delete(ME, {"password": "Password123!"}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Utilisateur.objects.filter(pk=tech.pk).exists())

    def test_la_suppression_efface_le_fichier_de_la_photo(self):
        cl = creer_client(email="del.photo@test.ci")
        self.client.force_authenticate(user=cl)
        self.client.post('/api/users/me/photo/', {"photo": SimpleUploadedFile('a.png', png(), content_type='image/png')}, format='multipart')
        cl.refresh_from_db()
        chemin = cl.photo.path
        self.assertTrue(os.path.exists(chemin))
        r = self.client.delete(ME, {"password": "Password123!"}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(os.path.exists(chemin))
        self.assertTrue(AuditLog.objects.filter(action='SUPPRESSION_COMPTE').exists())
