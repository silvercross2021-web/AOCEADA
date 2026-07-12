"""Diagnostic de l'assistant IA (xAI Grok).

Usage :  python manage.py test_grok
Vérifie la config GROK_* de settings/.env et fait un appel réel minimal à l'API,
avec des messages clairs selon le résultat (clé, modèle, quota, réseau).
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Teste la connexion à l'API xAI Grok avec la config actuelle (GROK_*)."

    def handle(self, *args, **options):
        key = (settings.GROK_API_KEY or '').strip()
        model = settings.GROK_MODEL
        url = settings.GROK_API_URL

        self.stdout.write(f"Modèle   : {model}")
        self.stdout.write(f"Endpoint : {url}")
        self.stdout.write(f"Timeout  : {settings.GROK_TIMEOUT}s | max_tokens : {settings.GROK_MAX_TOKENS}")

        if not key or key.startswith('your-xai'):
            self.stdout.write(self.style.WARNING(
                "\n[!] Aucune cle xAI valide dans GROK_API_KEY -> l'assistant reste en mode LOCAL "
                "(conseils integres, sans planter).\n"
                "    Colle ta cle (xai-...) dans .env puis relance : python manage.py test_grok"))
            return

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Réponds en une phrase courte, en français."},
                {"role": "user", "content": "Dis bonjour et confirme en un mot que tu es bien Grok."},
            ],
            "max_tokens": 60,
            "temperature": 0.3,
            "stream": False,
        }
        try:
            r = requests.post(
                url,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                json=payload,
                timeout=settings.GROK_TIMEOUT,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Échec réseau : {e}"))
            return

        if r.status_code == 200:
            try:
                txt = r.json()['choices'][0]['message']['content'].strip()
            except Exception:
                txt = r.text[:200]
            self.stdout.write(self.style.SUCCESS(f"\n[OK] (200) - {model} a repondu :"))
            self.stdout.write("   " + txt)
        elif r.status_code in (401, 403):
            self.stdout.write(self.style.ERROR(
                f"\n[X] {r.status_code} - cle xAI invalide ou refusee. Verifie GROK_API_KEY dans .env."))
            self.stdout.write("   " + r.text[:300])
        elif r.status_code == 404:
            self.stdout.write(self.style.ERROR(
                f"\n[X] 404 - modele « {model} » introuvable pour ta cle. "
                "Verifie l'ID exact sur https://console.x.ai puis corrige GROK_MODEL dans .env."))
            self.stdout.write("   " + r.text[:300])
        elif r.status_code == 429:
            self.stdout.write(self.style.WARNING(
                "\n[X] 429 - quota/debit depasse cote xAI. Reessaie plus tard ou verifie ton credit."))
            self.stdout.write("   " + r.text[:300])
        else:
            self.stdout.write(self.style.ERROR(f"\n[X] {r.status_code} : {r.text[:300]}"))
