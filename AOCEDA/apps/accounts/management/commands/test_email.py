"""Diagnostic e-mail (SMTP) d'AOCEDA.

Usage :  python manage.py test_email destinataire@exemple.com
Envoie un e-mail de test avec la config EMAIL_* de settings/.env et affiche un
message clair selon le resultat (backend, SMTP, echec d'authentification, etc.).
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Envoie un e-mail de test avec la config SMTP actuelle (EMAIL_*)."

    def add_arguments(self, parser):
        parser.add_argument('destinataire', help="Adresse e-mail qui recevra le test")

    def handle(self, *args, **options):
        to = options['destinataire']
        backend = settings.EMAIL_BACKEND
        is_smtp = backend.endswith('smtp.EmailBackend')

        self.stdout.write(f"Backend : {backend}")
        self.stdout.write(f"From    : {settings.DEFAULT_FROM_EMAIL}")
        if is_smtp:
            self.stdout.write(
                f"SMTP    : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
                f"(TLS={settings.EMAIL_USE_TLS}, SSL={settings.EMAIL_USE_SSL}, "
                f"user={settings.EMAIL_HOST_USER or '(vide)'})")
        else:
            self.stdout.write(self.style.WARNING(
                "\n[!] Backend CONSOLE : l'e-mail va s'AFFICHER ci-dessous, il ne sera PAS envoye.\n"
                "    Renseigne EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD dans .env "
                "pour un envoi reel."))

        try:
            n = send_mail(
                "Test SMTP AOCEDA",
                ("Ceci est un e-mail de test envoye par « manage.py test_email ».\n"
                 "Si tu le recois, la configuration SMTP d'AOCEDA fonctionne.\n\n"
                 "-- L'equipe AOCEDA"),
                settings.DEFAULT_FROM_EMAIL,
                [to],
                fail_silently=False,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n[X] Echec d'envoi : {e}"))
            self.stdout.write(
                "    Verifie : EMAIL_HOST/PORT/USER/PASSWORD, le « mot de passe d'application » "
                "(Gmail), le port (587=TLS / 465=SSL) et que le pare-feu laisse sortir.")
            return

        if is_smtp:
            self.stdout.write(self.style.SUCCESS(
                f"\n[OK] {n} e-mail envoye a {to}. Verifie la boite de reception (et les spams)."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n[OK] {n} e-mail rendu en console (mode dev) ci-dessus."))
