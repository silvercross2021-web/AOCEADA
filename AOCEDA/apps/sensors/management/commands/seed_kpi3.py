"""
Commande KPI3 : crée 4 comptes clients de démonstration (Yann Ouattara,
Kouassi Nissi, Traoré Kader, Kotchi Josué), chacun avec un dispositif ESP32 et
des capteurs posés sur des appareils DIFFÉRENTS d'un client à l'autre, un mois
de mesures réelles injectées en base (1er du mois -> aujourd'hui), et une
intervention d'installation confiée au MÊME technicien pour les 4 comptes.

Usage :
    python manage.py seed_kpi3            # crée les comptes + mesures (idempotent)
    python manage.py seed_kpi3 --reset     # regénère les mesures si déjà présentes
"""
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Client, Technicien
from apps.sensors.models import Dispositif, Capteur, MesureEnergie, Intervention, RapportIntervention

PASSWORD = 'TETA2004D'
TECH_EMAIL = 'chrisyapobrou@gmail.com'

# ─── 4 comptes clients, chacun avec 2 appareils DIFFÉRENTS (8 types distincts au total) ───
CLIENTS = [
    {
        'email': 'marasseediteur@gmail.com',
        'nom': 'Yann Ouattara',
        'typeLogement': 'Villa',
        'adresse': 'Abidjan, Cocody Angré 8e Tranche, Villa 12',
        'numeroCIE': 'CI-CO-4471820',
        'telephone': '+225 07 41 22 63 05',
        'amperage': 15,
        'typeTarif': 'general',
        'typeCompteur': 'postpaye',
        'creditPrepaye_FCFA': Decimal('0.00'),
        'device_serial': 'ESP32-KPI3-001',
        'capteurs': [
            {'nom': 'Climatiseur Salon', 'device': 'climatiseur', 'valeurMax': 1800, 'coeff': Decimal('0.9930')},
            {'nom': 'Réfrigérateur Cuisine', 'device': 'refrigerateur', 'valeurMax': 300, 'coeff': Decimal('0.9885')},
        ],
    },
    {
        'email': 'nissikouassi83@gmail.com',
        'nom': 'Kouassi Nissi',
        'typeLogement': 'Appartement',
        'adresse': 'Abidjan, Marcory Résidentiel, Lot 26',
        'numeroCIE': 'CI-MA-2290147',
        'telephone': '+225 05 62 18 40 77',
        'amperage': 10,
        'typeTarif': 'general',
        'typeCompteur': 'prepaye',
        'creditPrepaye_FCFA': Decimal('15000.00'),
        'seuilCreditBas_FCFA': Decimal('4000.00'),
        'device_serial': 'ESP32-KPI3-002',
        'capteurs': [
            {'nom': 'Congélateur', 'device': 'congelateur', 'valeurMax': 300, 'coeff': Decimal('1.0050')},
            {'nom': 'Éclairage Salon', 'device': 'eclairage', 'valeurMax': 150, 'coeff': Decimal('0.9975')},
        ],
    },
    {
        'email': 'anget373@gmail.com',
        'nom': 'Traoré Kader',
        'typeLogement': 'Maison',
        'adresse': 'Abidjan, Yopougon Niangon, Rue 14 Lot 63',
        'numeroCIE': 'CI-YO-3358291',
        'telephone': '+225 01 27 55 90 14',
        'amperage': 10,
        'typeTarif': 'general',
        'typeCompteur': 'postpaye',
        'creditPrepaye_FCFA': Decimal('0.00'),
        'device_serial': 'ESP32-KPI3-003',
        'capteurs': [
            {'nom': 'Chauffe-eau', 'device': 'chauffe_eau', 'valeurMax': 2500, 'coeff': Decimal('0.9910')},
            {'nom': 'Prise Chambre', 'device': 'prise', 'valeurMax': 2000, 'coeff': Decimal('1.0020')},
        ],
    },
    {
        'email': 'triiiumph12@gmail.com',
        'nom': 'Kotchi Josué',
        'typeLogement': 'Appartement',
        'adresse': 'Abidjan, Adjamé Bracodi, Immeuble D Porte 4',
        'numeroCIE': 'CI-AD-1187563',
        'telephone': '+225 09 74 36 21 88',
        'amperage': 5,
        'typeTarif': 'social',
        'typeCompteur': 'prepaye',
        'creditPrepaye_FCFA': Decimal('8000.00'),
        'seuilCreditBas_FCFA': Decimal('2000.00'),
        'device_serial': 'ESP32-KPI3-004',
        'capteurs': [
            {'nom': 'Machine à laver', 'device': 'machine_laver', 'valeurMax': 1000, 'coeff': Decimal('0.9960')},
            {'nom': 'Téléviseur & Box', 'device': 'tv_box', 'valeurMax': 300, 'coeff': Decimal('1.0010')},
        ],
    },
]


def _puissance(device, h, dow, rng):
    """Puissance (W) réaliste pour un type d'appareil, à l'heure h (0-23), jour dow (0=lundi)."""
    if device == 'climatiseur':
        base = {0: 1100, 1: 1080, 2: 1060, 3: 1060, 4: 1080, 5: 1120, 6: 700, 7: 450,
                 8: 280, 9: 220, 10: 200, 11: 240, 12: 380, 13: 450, 14: 400, 15: 320,
                 16: 280, 17: 340, 18: 700, 19: 980, 20: 1150, 21: 1300, 22: 1380, 23: 1350}
        return max(5.0, round(base[h] * rng.uniform(0.88, 1.12), 1))

    if device in ('refrigerateur', 'congelateur'):
        on_baseline = (130.0, 190.0) if device == 'congelateur' else (95.0, 150.0)
        off_baseline = (15.0, 28.0)
        compresseur_on = rng.random() < 0.55
        lo, hi = on_baseline if compresseur_on else off_baseline
        return round(rng.uniform(lo, hi), 1)

    if device == 'eclairage':
        on_matin = 5.5 <= h < 7.0
        on_soir = 18.0 <= h < 23.0
        if on_matin or on_soir:
            return round(rng.uniform(35.0, 55.0), 1)
        return 0.0

    if device == 'chauffe_eau':
        on_matin = 5.5 <= h < 6.5
        on_soir = 18.5 <= h < 19.5
        if on_matin or on_soir:
            return round(rng.uniform(1500.0, 2200.0), 1)
        return round(rng.uniform(0.0, 4.0), 1)

    if device == 'prise':
        base = {0: 20, 1: 18, 2: 18, 3: 18, 4: 20, 5: 60, 6: 320, 7: 560, 8: 300,
                 9: 180, 10: 140, 11: 180, 12: 520, 13: 420, 14: 220, 15: 160,
                 16: 180, 17: 260, 18: 620, 19: 900, 20: 780, 21: 520, 22: 240, 23: 60}
        return max(5.0, round(base[h] * rng.uniform(0.85, 1.15), 1))

    if device == 'machine_laver':
        # utilisée 3 jours non-consécutifs par semaine (lun/mer/sam), un cycle de 2h le matin
        jours_util = {0, 2, 5}
        if dow in jours_util and 9.0 <= h < 11.0:
            return round(rng.uniform(420.0, 780.0), 1)
        return 0.0

    if device == 'tv_box':
        veille = rng.uniform(6.0, 10.0)
        if 12.0 <= h < 14.0:
            return round(rng.uniform(90.0, 140.0), 1)
        if 18.0 <= h < 23.5:
            return round(rng.uniform(100.0, 180.0), 1)
        return round(veille, 1)

    return 0.0


class Command(BaseCommand):
    help = "Crée les 4 comptes clients KPI3 (appareils différents, même technicien, données du mois en cours)."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                             help="Supprime et régénère les mesures si déjà présentes.")

    def handle(self, *args, **options):
        reset = options.get('reset', False)
        now = timezone.now()
        debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            technicien = Technicien.objects.get(email=TECH_EMAIL)
        except Technicien.DoesNotExist:
            raise CommandError(f"Technicien introuvable : {TECH_EMAIL}")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Seed KPI3 : 4 comptes clients (technicien {technicien.nom}) ===\n"
        ))

        recap = []
        for cfg in CLIENTS:
            client = self._creer_client(cfg)
            disp = self._creer_dispositif(client, cfg)
            capteurs = self._creer_capteurs(client, disp, cfg)
            self._creer_intervention(client, technicien, disp, cfg, debut_mois)
            nb_mesures = self._generer_mesures(capteurs, cfg, debut_mois, now, reset)
            recap.append((cfg, client, disp, capteurs, nb_mesures))

        self.stdout.write(self.style.SUCCESS("\n[OK] Seed KPI3 terminé.\n"))
        self._afficher_recap(recap, technicien)

    # ------------------------------------------------------------------
    def _creer_client(self, cfg):
        defaults = {
            'nom': cfg['nom'], 'role': 'client',
            'typeLogement': cfg['typeLogement'], 'adresse': cfg['adresse'],
            'numeroCIE': cfg['numeroCIE'], 'telephone': cfg['telephone'],
            'amperage': cfg['amperage'], 'typeTarif': cfg['typeTarif'],
            'typeCompteur': cfg['typeCompteur'],
            'creditPrepaye_FCFA': cfg['creditPrepaye_FCFA'],
            'tarifkWh_FCFA': Decimal('87.00'),
        }
        if 'seuilCreditBas_FCFA' in cfg:
            defaults['seuilCreditBas_FCFA'] = cfg['seuilCreditBas_FCFA']

        client, created = Client.objects.get_or_create(email=cfg['email'], defaults=defaults)
        if created:
            client.set_password(PASSWORD)
            client.save(update_fields=['password'])
            self.stdout.write(self.style.SUCCESS(f"  [CRÉÉ] Client {cfg['nom']} ({cfg['email']})"))
        else:
            client.set_password(PASSWORD)
            client.save(update_fields=['password'])
            self.stdout.write(f"  ~ Client déjà existant, mot de passe réaligné : {cfg['email']}")
        return client

    def _creer_dispositif(self, client, cfg):
        disp, created = Dispositif.objects.get_or_create(
            numeroSerie=cfg['device_serial'],
            defaults={
                'client': client,
                'nom': f"Installation {cfg['nom']}",
                'adresse': cfg['adresse'],
                'apiKeyDevice': uuid.uuid4().hex,
                'firmwareVersion': '1.0.0',
                'estConnecté': True,
            },
        )
        if not created and disp.client_id != client.id:
            disp.client = client
            disp.save(update_fields=['client'])
        label = "[CRÉÉ] Dispositif" if created else "  ~ Dispositif existant"
        self.stdout.write(f"  {label} : {cfg['device_serial']} -> {client.nom}")
        return disp

    def _creer_capteurs(self, client, disp, cfg):
        capteurs = []
        for c in cfg['capteurs']:
            capteur, created = Capteur.objects.get_or_create(
                nom=c['nom'], client=client,
                defaults={
                    'dispositif': disp, 'type': 'Courant',
                    'valeurMax': c['valeurMax'], 'actif': True,
                    'coeffCalibration': c['coeff'],
                },
            )
            if not created and capteur.dispositif_id != disp.id:
                capteur.dispositif = disp
                capteur.save(update_fields=['dispositif'])
            label = "[CRÉÉ] Capteur" if created else "  ~ Capteur existant"
            self.stdout.write(f"    {label} : '{c['nom']}' ({c['device']})")
            capteurs.append((capteur, c['device']))
        return capteurs

    def _creer_intervention(self, client, technicien, disp, cfg, debut_mois):
        if Intervention.objects.filter(client=client, typeIntervention='INSTALLATION').exists():
            self.stdout.write(f"  ~ Intervention INSTALLATION déjà existante pour {client.nom}")
            return

        date_inst = debut_mois + timedelta(days=cfg['capteurs'][0]['valeurMax'] % 3, hours=9)
        noms_appareils = ', '.join(c['nom'] for c in cfg['capteurs'])

        intervention = Intervention.objects.create(
            technicien=technicien, client=client, dispositif=disp,
            typeIntervention='INSTALLATION',
            description=(
                f"Installation du système de monitoring AOCEDA chez {client.nom}, {client.adresse}.\n\n"
                f"Pose de {len(cfg['capteurs'])} capteur(s) ZMCT103C sur : {noms_appareils}.\n"
                "Appairage du module ESP32 au réseau Wi-Fi du client et enregistrement sur la plateforme."
            ),
            dateIntervention=date_inst,
            statut='TERMINEE',
            résultat=f"Installation réalisée avec succès par {technicien.nom}. Capteurs opérationnels : {noms_appareils}.",
        )
        RapportIntervention.objects.create(
            intervention=intervention,
            contenu=(
                f"Technicien : {technicien.nom} (matricule {technicien.matricule})\n"
                f"Client : {client.nom} ({client.email})\n"
                f"Appareils équipés : {noms_appareils}\n"
                f"Dispositif : {disp.numeroSerie}"
            ),
            conclusion=f"Installation validée, client {client.nom} opérationnel sur la plateforme AOCEDA.",
            estValidé=True,
        )
        self.stdout.write(f"  [CRÉÉ] Intervention INSTALLATION ({date_inst:%d/%m/%Y}) — tech={technicien.nom}")

    def _generer_mesures(self, capteurs, cfg, debut_mois, now, reset):
        capteur_ids = [c.id for c, _ in capteurs]
        existant = MesureEnergie.objects.filter(capteur_id__in=capteur_ids).count()
        if existant and not reset:
            self.stdout.write(f"    ~ {existant} mesures déjà présentes (utilisez --reset pour régénérer)")
            return existant
        if existant and reset:
            MesureEnergie.objects.filter(capteur_id__in=capteur_ids).delete()

        rng = random.Random(hash(cfg['email']) & 0xFFFFFFFF)
        mesures = []
        ts = debut_mois
        while ts <= now:
            h, dow = ts.hour, ts.weekday()
            for capteur, device in capteurs:
                p = _puissance(device, h, dow, rng)
                courant = round(p / 220.0, 3)
                energie = round(p / 1000.0, 6)
                mesures.append(MesureEnergie(
                    capteur=capteur, puissance=Decimal(str(p)), courant=Decimal(str(courant)),
                    energie=Decimal(str(energie)), tension_V=Decimal('220.0'),
                    facteur_puissance=Decimal('0.900'), timestamp=ts,
                ))
            ts += timedelta(hours=1)

        MesureEnergie.objects.bulk_create(mesures, batch_size=500)
        derniere_ts = ts - timedelta(hours=1)
        for capteur, device in capteurs:
            derniere_p = _puissance(device, derniere_ts.hour, derniere_ts.weekday(), rng)
            Capteur.objects.filter(pk=capteur.pk).update(
                derniereLecture=derniere_ts,
                etatCourant='ON' if derniere_p > 0 else 'OFF',
                cptOffConsecutifs=0,
            )
        self.stdout.write(self.style.SUCCESS(f"    [OK] {len(mesures)} mesures générées (depuis le {debut_mois:%d/%m/%Y})"))
        return len(mesures)

    def _afficher_recap(self, recap, technicien):
        self.stdout.write("--- Récapitulatif KPI3 ---")
        self.stdout.write(f"  Technicien en charge des 4 comptes : {technicien.nom} ({technicien.email})")
        for cfg, client, disp, capteurs, nb_mesures in recap:
            noms = ', '.join(c['nom'] for c in cfg['capteurs'])
            self.stdout.write(
                f"  {client.nom:16} | {cfg['email']:28} | mdp={PASSWORD} | "
                f"dispositif={disp.numeroSerie} | appareils=[{noms}] | mesures={nb_mesures}"
            )
        self.stdout.write("---------------------------\n")
