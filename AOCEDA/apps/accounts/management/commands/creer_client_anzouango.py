"""
Commande de management Django pour creer et verifier le compte client
anzouangomisthony@gmail.com (Mot de passe: TETA200D) ainsi que le dispositif ESP32
et ses capteurs pour la reception des donnees en temps reel.

Usage :
    python manage.py creer_client_anzouango
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Cree le compte client anzouangomisthony@gmail.com et configure l'ESP32 et ses capteurs."

    def handle(self, *args, **options):
        from apps.accounts.models import Client
        from apps.sensors.models import Capteur, Dispositif, MesureEnergie

        EMAIL      = "anzouangomisthony@gmail.com"
        PASSWORD   = "TETA200D"
        NOM        = "Anzouango Misthony"
        DEVICE_KEY = "c9f1d4e372a0b518642c3e8d1f059b27"  # Cle de main.cpp

        self.stdout.write("\n" + "=" * 65)
        self.stdout.write("  CREATION ET VERIFICATION DU COMPTE CLIENT ET CONFIGURATION ESP32")
        self.stdout.write("=" * 65)

        with transaction.atomic():
            # -- 1. Creer ou recuperer le Client ----------------------------
            client, created = Client.objects.get_or_create(
                email=EMAIL,
                defaults={
                    "nom":          NOM,
                    "role":         "client",
                    "estActif":     True,
                    "typeLogement": "Appartement",
                    "amperage":     10,
                    "typeTarif":    "general",
                    "typeCompteur": "postpaye",
                    "notifEmail":   True,
                },
            )

            if created:
                client.set_password(PASSWORD)
                client.save()
                self.stdout.write(self.style.SUCCESS(
                    "\n[OK] Compte client cree avec succes !"
                ))
            else:
                if not client.check_password(PASSWORD):
                    client.set_password(PASSWORD)
                    client.save()
                    self.stdout.write(self.style.WARNING(
                        "\n[WARN] Compte client existant -- Mot de passe reinitialise a TETA200D."
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        "\n[OK] Compte client existant -- Mot de passe deja correct."
                    ))

            # -- 2. Associer / Configurer le Dispositif ESP32 ---------------
            dispositif, d_created = Dispositif.objects.get_or_create(
                apiKeyDevice=DEVICE_KEY,
                defaults={
                    "client":      client,
                    "nom":         "Logger IoT ZMCT103C (ESP32)",
                    "numeroSerie": "ESP32-ANZ-2026",
                    "estConnecté": True,
                },
            )
            if dispositif.client != client:
                dispositif.client = client
                dispositif.save()

            if d_created:
                self.stdout.write(self.style.SUCCESS(
                    "[OK] Dispositif ESP32 cree et associe au client."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "[OK] Dispositif ESP32 (apiKey: %s) deja associe au client." % DEVICE_KEY
                ))

            # -- 3. Configurer les Capteurs (Salon & Chambre) ---------------
            capteur_1, c1_created = Capteur.objects.get_or_create(
                dispositif=dispositif,
                nom="Capteur 1 - Salon / Cuisine",
                defaults={
                    "client":    client,
                    "type":      "Courant",
                    "valeurMax": 2000.00,
                    "actif":     True,
                },
            )
            if capteur_1.client != client:
                capteur_1.client = client
                capteur_1.save()

            capteur_2, c2_created = Capteur.objects.get_or_create(
                dispositif=dispositif,
                nom="Capteur 2 - Chambre",
                defaults={
                    "client":    client,
                    "type":      "Courant",
                    "valeurMax": 2000.00,
                    "actif":     True,
                },
            )
            if capteur_2.client != client:
                capteur_2.client = client
                capteur_2.save()

            self.stdout.write(self.style.SUCCESS(
                "[OK] Capteurs 1 (Salon/Cuisine) et 2 (Chambre) configures et fonctionnels."
            ))

            # -- 4. Affichage detaille des informations -------------------
            self.stdout.write("\n[INFO] FICHE DU COMPTE CLIENT")
            self.stdout.write("    ID           : %s" % client.id)
            self.stdout.write("    Email        : %s" % client.email)
            self.stdout.write("    Nom          : %s" % client.nom)
            self.stdout.write("    Role         : %s" % client.role)
            self.stdout.write("    Actif        : %s" % client.estActif)
            self.stdout.write("    Tarif CIE    : %s / %sA" % (client.typeTarif, client.amperage))
            self.stdout.write("    Compteur     : %s" % client.typeCompteur)

            self.stdout.write("\n[INFO] CONFIGURATION ESP32 LIER")
            self.stdout.write("    Nom Device   : %s" % dispositif.nom)
            self.stdout.write("    N Serie      : %s" % dispositif.numeroSerie)
            self.stdout.write("    API Key      : %s" % dispositif.apiKeyDevice)
            self.stdout.write("    Capteur 1    : %s (ID: %s)" % (capteur_1.nom, capteur_1.id))
            self.stdout.write("    Capteur 2    : %s (ID: %s)" % (capteur_2.nom, capteur_2.id))

            # -- 5. Bilan des mesures enregistrees --------------------------
            nb_mesures = MesureEnergie.objects.filter(capteur__client=client).count()
            self.stdout.write("\n" + "-" * 65)
            self.stdout.write("  RECAPITULATIF & VERIFICATION DE RECEPTION")
            self.stdout.write("    Compte client      : %s" % client.email)
            self.stdout.write("    Mot de passe       : TETA200D")
            self.stdout.write("    Dispositifs relies : 1")
            self.stdout.write("    Capteurs relies    : 2")
            self.stdout.write("    Mesures enregistrees: %d" % nb_mesures)
            self.stdout.write("-" * 65)
            self.stdout.write(self.style.SUCCESS(
                "\n[SUCCESS] Tout est pret et fonctionnel ! Toutes les donnees envoyees\n"
                "          par l'ESP32 seront directement attribuees a ce compte.\n"
            ))
