"""
Commande Django : python manage.py setup_nguessan

Configure le compte N'Guessan dans AOCEDA :
  1. Trouve ou crée le client (email + mot de passe fournis en argument)
  2. Supprime TOUTES les fausses mesures existantes pour ce client
  3. Crée (ou confirme) les capteurs Capteur_1 et Capteur_2

Usage :
    python manage.py setup_nguessan --email nguessan@example.com --password monmotdepasse
"""
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import Client
from apps.sensors.models import Capteur, MesureEnergie


CAPTEURS_DEFAUT = [
    {'nom': 'Capteur_1', 'label': 'Lampe'},
    {'nom': 'Capteur_2', 'label': 'Prise'},
]


class Command(BaseCommand):
    help = "Configure le compte N'Guessan et nettoie les fausses données."

    def add_arguments(self, parser):
        parser.add_argument('--email',    required=True,  help="Email du compte N'Guessan")
        parser.add_argument('--password', required=False, help="Mot de passe (si création)")
        parser.add_argument('--nom',      default="N'Guessan", help="Nom affiché")

    def handle(self, *args, **options):
        email    = options['email'].strip()
        password = options.get('password', '').strip()
        nom      = options['nom'].strip()

        # ── 1. Trouver ou créer le client ─────────────────────────────────────
        try:
            client = Client.objects.get(email=email)
            self.stdout.write(f"[OK] Client trouvé : {client.nom} ({client.email})")
        except Client.DoesNotExist:
            if not password:
                raise CommandError(
                    "Le compte n'existe pas. Fournissez --password pour le créer."
                )
            client = Client(email=email, nom=nom, role='client')
            client.set_password(password)
            client.save()
            self.stdout.write(self.style.SUCCESS(
                f"[CRÉÉ] Client : {client.nom} ({client.email})"
            ))

        # ── 2. Vider les fausses mesures ──────────────────────────────────────
        nb = MesureEnergie.objects.filter(capteur__client=client).count()
        MesureEnergie.objects.filter(capteur__client=client).delete()
        if nb:
            self.stdout.write(self.style.WARNING(
                f"[NETTOYÉ] {nb} fausse(s) mesure(s) supprimée(s)."
            ))
        else:
            self.stdout.write("[INFO] Aucune mesure préexistante à supprimer.")

        # ── 3. Créer / confirmer les capteurs ─────────────────────────────────
        for c in CAPTEURS_DEFAUT:
            capteur, created = Capteur.objects.get_or_create(
                nom=c['nom'],
                client=client,
                defaults={
                    'type': 'Courant',
                    'valeurMax': 2000,
                    'actif': True,
                    'coeffCalibration': 1.0,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"[CRÉÉ] Capteur '{capteur.nom}' ({c['label']}) → id={capteur.id}"
                ))
            else:
                self.stdout.write(
                    f"[OK]   Capteur '{capteur.nom}' existe déjà → id={capteur.id}"
                )

        self.stdout.write(self.style.SUCCESS(
            "\n✓ Setup terminé. Lancez maintenant :\n"
            "    python serial_bridge.py COM3\n"
            "  puis ouvrez http://localhost:8000/dashboard/ et connectez-vous."
        ))
