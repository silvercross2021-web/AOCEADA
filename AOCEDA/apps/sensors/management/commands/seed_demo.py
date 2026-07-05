"""
Commande d'initialisation AOCEDA.
Usage :
    python manage.py seed_demo               # comptes + installations (pas de mesures)
    python manage.py seed_demo --avec-mesures  # idem + mesures historiques pour Toure Thierry
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

# Définition des 3 installations réelles
INSTALLATIONS = [
    {
        'client_email': 'tt@client.aoceda.ci',
        'device_serial': 'ESP32-ABJ-001',
        'device_key':    'a4f8c2d91b3e705687a01c9d84f6b35a',
        'capteurs': [('Lampe Salon', 500), ('Prise Cuisine', 2000)],
        'jours': 8,
    },
    {
        'client_email': 'adjoua.coulibaly@client.aoceda.ci',
        'device_serial': 'ESP32-ABJ-002',
        'device_key':    'b7e3a1c245f9d086312e4b7c9a820f41',
        'capteurs': [('Eclairage Principal', 500), ('Prise Salon', 2000)],
        'jours': 5,
    },
    {
        'client_email': 'paul.nguessan@client.aoceda.ci',
        'device_serial': 'ESP32-ABJ-003',
        'device_key':    'c9f1d4e372a0b518642c3e8d1f059b27',
        'capteurs': [('Eclairage Sejour', 800), ('Prise Chambre', 2000)],
        'jours': 3,
    },
]


class Command(BaseCommand):
    help = "Initialise les comptes et installations AOCEDA"

    def add_arguments(self, parser):
        parser.add_argument(
            '--avec-mesures',
            action='store_true',
            default=False,
            help="Genere aussi des mesures historiques simulees pour le compte principal.",
        )

    def handle(self, *args, **options):
        self.stdout.write("\n=== Initialisation AOCEDA ===\n")

        self._create_admin()
        tech = self._create_technicien()
        self._create_clients()
        self._migrate_legacy_serials()
        self._create_capteurs_pool()

        from apps.accounts.models import Client
        for cfg in INSTALLATIONS:
            try:
                client = Client.objects.get(email=cfg['client_email'])
            except Client.DoesNotExist:
                self.stdout.write(f"  [!] Client {cfg['client_email']} introuvable, installation ignoree")
                continue
            disp = self._configurer_dispositif(client, cfg['device_serial'], cfg['device_key'])
            self._configurer_capteurs(client, disp, cfg['capteurs'])
            self._configurer_intervention(client, tech, disp, cfg['capteurs'], cfg['jours'])

        if options['avec_mesures']:
            client_tt = Client.objects.filter(email='tt@client.aoceda.ci').first()
            if client_tt:
                self._create_mesures(client_tt)
        else:
            self.stdout.write("  ~ Mesures ignorees (passer --avec-mesures pour en generer)")

        self.stdout.write("\n[OK] Initialisation terminee.\n")
        self._afficher_recap()

    # ------------------------------------------------------------------
    # Comptes
    # ------------------------------------------------------------------
    def _create_admin(self):
        from apps.accounts.models import Administrateur
        if Administrateur.objects.filter(email='admin@aoceda.ci').exists():
            self.stdout.write("  ~ Admin deja existant")
            return
        admin = Administrateur(
            email='admin@aoceda.ci', nom='Admin AOCEDA',
            role='admin', is_staff=True, is_superuser=True, niveauAcces='super',
        )
        admin.set_password('Admin1234!')
        admin.save()
        self.stdout.write("  [OK] Admin cree : admin@aoceda.ci / Admin1234!")

    def _create_technicien(self):
        from apps.accounts.models import Technicien
        tech, created = Technicien.objects.get_or_create(
            email='tech@aoceda.ci',
            defaults={
                'nom': 'Jean Kouame', 'role': 'technicien',
                'matricule': 'TECH-0001', 'specialite': 'Electricite domestique',
            },
        )
        if created:
            tech.set_password('Tech1234!')
            tech.save(update_fields=['password'])
            self.stdout.write("  [OK] Technicien cree : tech@aoceda.ci / Tech1234!")
        else:
            self.stdout.write("  ~ Technicien deja existant")
        return tech

    def _create_clients(self):
        definitions = [
            {
                'email': 'tt@client.aoceda.ci',
                'password': '2004',
                'nom': 'Toure Thierry',
                'typeLogement': 'Appartement',
                'amperage': 10,
                'typeTarif': 'general',
                'typeCompteur': 'prepaye',
                'creditPrepaye_FCFA': 25000.00,
                'seuilCreditBas_FCFA': 5000.00,
                'adresse': 'Abidjan, Cocody Riviera 2, Lot 47',
                'numeroCIE': 'CI-CO-2748963',
                'telephone': '+225 07 58 24 13 90',
                'tarifkWh_FCFA': 87.00,
            },
            {
                'email': 'adjoua.coulibaly@client.aoceda.ci',
                'password': 'Adjoua2004!',
                'nom': 'Coulibaly Adjoua',
                'typeLogement': 'Maison',
                'amperage': 10,
                'typeTarif': 'general',
                'typeCompteur': 'prepaye',
                'creditPrepaye_FCFA': 18000.00,
                'seuilCreditBas_FCFA': 3000.00,
                'adresse': 'Abidjan, Yopougon Selmer, Rue 12 Lot 89',
                'numeroCIE': 'CI-YO-1193482',
                'telephone': '+225 05 34 17 62 40',
                'tarifkWh_FCFA': 87.00,
            },
            {
                'email': 'paul.nguessan@client.aoceda.ci',
                'password': 'Paul2004!',
                'nom': "N'Guessan Paul",
                'typeLogement': 'Villa',
                'amperage': 15,
                'typeTarif': 'general',
                'typeCompteur': 'postpaye',
                'creditPrepaye_FCFA': 0.00,
                'seuilCreditBas_FCFA': 0.00,
                'adresse': "Abidjan, Cocody II-Plateaux, Villa 34 Rue des Jardins",
                'numeroCIE': 'CI-CO-3371045',
                'telephone': '+225 07 09 88 21 55',
                'tarifkWh_FCFA': 87.00,
            },
        ]
        from apps.accounts.models import Client
        for d in definitions:
            pwd = d.pop('password')
            email = d['email']
            client, created = Client.objects.get_or_create(email=email, defaults={**d, 'role': 'client'})
            if created:
                client.set_password(pwd)
                client.save(update_fields=['password'])
                self.stdout.write(f"  [OK] Client cree : {email}")
            else:
                # Mise a jour du numero CIE si ancienne valeur
                updated = []
                if client.numeroCIE != d.get('numeroCIE'):
                    client.numeroCIE = d['numeroCIE']
                    updated.append('numeroCIE')
                if updated:
                    client.save(update_fields=updated)
                self.stdout.write(f"  ~ Client deja existant : {email}")

    # ------------------------------------------------------------------
    # Capteurs stock (non assignes)
    # ------------------------------------------------------------------
    def _create_capteurs_pool(self):
        from apps.sensors.models import Capteur
        for nom in ['ZMCT103C-003', 'ZMCT103C-004']:
            _, created = Capteur.objects.get_or_create(
                nom=nom, client=None,
                defaults={'type': 'Courant', 'valeurMax': 2000, 'actif': True},
            )
            if created:
                self.stdout.write(f"  [OK] Capteur stock cree : {nom}")
            else:
                self.stdout.write(f"  ~ Capteur stock deja existant : {nom}")

    def _migrate_legacy_serials(self):
        """Corrige les anciens serials de demonstration."""
        from apps.sensors.models import Dispositif
        Dispositif.objects.filter(numeroSerie='ESP32-DEMO-001').update(
            numeroSerie='ESP32-ABJ-001',
            apiKeyDevice='a4f8c2d91b3e705687a01c9d84f6b35a',
        )

    # ------------------------------------------------------------------
    # Installation d'un client (1 dispositif + N capteurs + 1 intervention)
    # ------------------------------------------------------------------
    def _configurer_dispositif(self, client, serial, apikey):
        from apps.sensors.models import Dispositif
        disp, created = Dispositif.objects.get_or_create(
            numeroSerie=serial,
            defaults={
                'client': client, 'apiKeyDevice': apikey,
                'firmwareVersion': '1.0.0', 'estConnecté': False,
            },
        )
        if not created and disp.client is None:
            disp.client = client
            disp.save(update_fields=['client'])
        label = "[OK] Dispositif cree" if created else "  ~ Dispositif deja existant"
        self.stdout.write(f"  {label} : {serial}  (client={client.nom})")
        return disp

    def _configurer_capteurs(self, client, disp, capteurs_def):
        from apps.sensors.models import Capteur
        for nom, valeur_max in capteurs_def:
            cap, created = Capteur.objects.get_or_create(
                nom=nom, client=client,
                defaults={
                    'dispositif': disp, 'type': 'Courant',
                    'valeurMax': valeur_max, 'actif': True, 'coeffCalibration': 1.0,
                },
            )
            if not created and cap.dispositif is None:
                cap.dispositif = disp
                cap.save(update_fields=['dispositif'])
            label = "[OK] Capteur cree" if created else "  ~ Capteur deja existant"
            self.stdout.write(f"  {label} : '{nom}'  -> {client.nom}")

    def _configurer_intervention(self, client, tech, disp, capteurs_def, jours_depuis):
        from apps.sensors.models import Intervention, RapportIntervention

        if Intervention.objects.filter(client=client, typeIntervention='INSTALLATION').exists():
            self.stdout.write(f"  ~ Intervention INSTALLATION deja existante pour {client.nom}")
            return

        now = timezone.now()
        date_inst = now - timedelta(days=jours_depuis)
        serial = disp.numeroSerie if disp else 'N/A'

        lignes_capteurs = ''.join(
            f"  * Capteur {i+1} : {nom} , seuil max {vmax} W\n"
            for i, (nom, vmax) in enumerate(capteurs_def)
        )

        intervention = Intervention.objects.create(
            technicien=tech,
            client=client,
            dispositif=disp,
            typeIntervention='INSTALLATION',
            description=(
                f"Installation du systeme de monitoring AOCEDA chez {client.nom}, "
                f"{client.adresse}.\n\n"
                "Operations effectuees :\n"
                f"- Pose et branchement de {len(capteurs_def)} capteur(s) ZMCT103C\n"
                "- Appairage du module ESP32 au reseau Wi-Fi du client\n"
                "- Enregistrement sur la plateforme AOCEDA\n"
                "- Verification de la transmission en temps reel\n"
                f"- Reference abonnement CIE : {client.amperage}A, "
                f"compteur {client.typeCompteur}, tarif {client.typeTarif}\n"
                f"- Numero abonne CIE : {client.numeroCIE}"
            ),
            dateIntervention=date_inst,
            statut='TERMINEE',
            résultat=(
                "Installation realisee avec succes. "
                f"Les {len(capteurs_def)} capteur(s) transmettent correctement "
                "vers la plateforme AOCEDA."
            ),
        )

        RapportIntervention.objects.create(
            intervention=intervention,
            contenu=(
                f"RAPPORT D'INSTALLATION AOCEDA\n"
                f"==============================\n\n"
                f"Date        : {date_inst.strftime('%d/%m/%Y')}\n"
                f"Technicien  : {tech.nom}  (matricule {tech.matricule})\n"
                f"Client      : {client.nom}  ({client.email})\n"
                f"Adresse     : {client.adresse}\n\n"
                "MATERIEL INSTALLE\n"
                "-----------------\n"
                f"- {len(capteurs_def)}x capteur ZMCT103C (rapport 1000:1, R_burden 100 Ohm)\n"
                f"{lignes_capteurs}"
                f"- 1x module ESP32 (firmware v1.0.0, S/N {serial})\n\n"
                "ABONNEMENT CIE REFERENCE\n"
                "------------------------\n"
                f"- Amperage souscrit : {client.amperage}A\n"
                f"- Type de tarif     : Domestique {client.typeTarif}\n"
                f"- Type de compteur  : {client.typeCompteur}\n"
                f"- Numero abonne CIE : {client.numeroCIE}\n\n"
                "TESTS REALISES SUR SITE\n"
                "-----------------------\n"
                "- Connexion Wi-Fi          : OK\n"
                "- Lecture capteurs         : OK\n"
                "- Transmission plateforme  : OK\n"
                "- Regles d'alerte          : actives\n"
            ),
            conclusion=(
                f"Installation validee. Le client {client.nom} est desormais "
                "operationnel sur la plateforme AOCEDA."
            ),
            estValidé=True,
        )
        self.stdout.write(
            f"  [OK] Intervention INSTALLATION ({date_inst.strftime('%d/%m/%Y')}) "
            f"— tech={tech.nom}, client={client.nom}"
        )

    # ------------------------------------------------------------------
    # Mesures simulees (optionnel, uniquement pour les tests UI)
    # ------------------------------------------------------------------
    def _puissance_lampe(self, rng, h, dow):
        on_matin   = 5.5 <= h < 7.0
        on_soir    = 17.5 <= h < 23.0
        on_dimanche = (dow == 6) and (9.0 <= h < 12.5)
        if on_matin or on_soir or on_dimanche:
            return round(rng.uniform(40.0, 50.0), 2)
        return 0.00

    def _puissance_prise(self, rng, h, dow):
        frigo = round(rng.uniform(100.0, 148.0), 2)
        if 5.5 <= h < 6.0:
            extra = round(rng.uniform(1400.0, 1800.0), 2)
        elif 6.0 <= h < 8.0:
            extra = round(rng.uniform(300.0, 900.0), 2)
        elif 12.0 <= h < 14.0:
            extra = round(rng.uniform(600.0 if dow == 6 else 200.0, 1800.0 if dow == 6 else 1000.0), 2)
        elif 18.0 <= h < 21.5:
            extra = round(rng.uniform(400.0, 1400.0), 2)
        else:
            extra = 0.0
        return round(min(frigo + extra, 2200.0), 2)

    def _create_mesures(self, client):
        from apps.sensors.models import Capteur, MesureEnergie

        capteurs = list(Capteur.objects.filter(client=client).order_by('nom'))
        if not capteurs:
            return

        deleted, _ = MesureEnergie.objects.filter(capteur__client=client).delete()
        if deleted:
            self.stdout.write(f"  ~ {deleted} anciennes mesures supprimees")

        rng = random.Random(42)
        now = timezone.now()
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

        mesures = []
        ts = start
        while ts <= now - timedelta(minutes=10):
            h = ts.hour + ts.minute / 60
            dow = ts.weekday()
            for capteur in capteurs[:2]:
                if capteur.nom in ('Lampe Salon', 'Eclairage Principal', 'Eclairage Sejour'):
                    puissance = self._puissance_lampe(rng, h, dow)
                else:
                    puissance = self._puissance_prise(rng, h, dow)
                courant = round(puissance / 220.0, 3)
                energie = round(puissance * 0.5 / 1000.0, 6)
                mesures.append(MesureEnergie(
                    capteur=capteur, courant=courant, puissance=puissance,
                    energie=energie, tension_V=220.0, timestamp=ts,
                ))
            ts += timedelta(minutes=30)

        MesureEnergie.objects.bulk_create(mesures, batch_size=500)
        Capteur.objects.filter(client=client).update(
            derniereLecture=ts - timedelta(minutes=30)
        )
        self.stdout.write(f"  [OK] {len(mesures)} mesures generees (7 jours)")

    # ------------------------------------------------------------------
    # Recapitulatif
    # ------------------------------------------------------------------
    def _afficher_recap(self):
        from apps.accounts.models import Client, Technicien, Administrateur
        from apps.sensors.models import Capteur, Dispositif, MesureEnergie, Intervention

        self.stdout.write("--- Recapitulatif ---")

        self.stdout.write("  COMPTES")
        admin = Administrateur.objects.filter(email='admin@aoceda.ci').first()
        tech  = Technicien.objects.filter(email='tech@aoceda.ci').first()
        if admin:
            self.stdout.write(f"    Admin      : {admin.email}  /  Admin1234!")
        if tech:
            self.stdout.write(f"    Technicien : {tech.email}   /  Tech1234!  ({tech.matricule})")

        self.stdout.write("  INSTALLATIONS")
        for cfg in INSTALLATIONS:
            try:
                c = Client.objects.get(email=cfg['client_email'])
            except Client.DoesNotExist:
                continue
            disp = Dispositif.objects.filter(client=c).first()
            nb_cap = Capteur.objects.filter(client=c).count()
            nb_mes = MesureEnergie.objects.filter(capteur__client=c).count()
            nb_int = Intervention.objects.filter(client=c, typeIntervention='INSTALLATION').count()
            self.stdout.write(
                f"    [{c.amperage}A / {c.typeCompteur:8}] {c.nom:20} "
                f"| capteurs={nb_cap} | mesures={nb_mes} | intervention={'oui' if nb_int else 'NON'}"
            )
            if disp:
                self.stdout.write(f"      -> Dispositif : {disp.numeroSerie}  |  Key : {disp.apiKeyDevice}")

        nb_pool = Capteur.objects.filter(client__isnull=True).count()
        self.stdout.write(f"  STOCK CAPTEURS NON ASSIGNES : {nb_pool}")
        self.stdout.write("---------------------\n")
