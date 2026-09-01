"""Diagnostic de l'assistant IA (DeepSeek).

Usage :  python manage.py test_deepseek
Vérifie la config DEEPSEEK_* de settings/.env et fait un appel réel minimal à
l'API, avec des messages clairs selon le résultat (clé, modèle, quota, réseau).
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Teste la connexion à l'API DeepSeek avec la config actuelle (DEEPSEEK_*)."

    def handle(self, *args, **options):
        key = (settings.DEEPSEEK_API_KEY or '').strip()
        model = settings.DEEPSEEK_MODEL
        url = settings.DEEPSEEK_API_URL

        self.stdout.write(f"Modèle   : {model}")
        self.stdout.write(f"Endpoint : {url}")
        self.stdout.write(f"Timeout  : {settings.DEEPSEEK_TIMEOUT}s | max_tokens : {settings.DEEPSEEK_MAX_TOKENS}")

        if not key or key.startswith('your-'):
            self.stdout.write(self.style.WARNING(
                "\n[!] Aucune cle DeepSeek valide dans DEEPSEEK_API_KEY -> l'assistant reste en mode LOCAL "
                "(conseils integres, sans planter).\n"
                "    Colle ta cle (sk-...) dans .env puis relance : python manage.py test_deepseek"))
            return

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Réponds en une phrase courte, en français."},
                {"role": "user", "content": "Dis bonjour et confirme en un mot que tu es bien DeepSeek."},
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
                timeout=settings.DEEPSEEK_TIMEOUT,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Échec réseau : {e}"))
            return

        if r.status_code == 200:
            try:
                data = r.json()
                txt = data['choices'][0]['message']['content'].strip()
                usage = data.get('usage') or {}
            except Exception:
                txt = r.text[:200]
                usage = {}
            self.stdout.write(self.style.SUCCESS(f"\n[OK] (200) - {model} a repondu :"))
            self.stdout.write("   " + txt)
            if usage:
                self.stdout.write(
                    f"   Tokens : {usage.get('prompt_tokens', '?')} entrée / "
                    f"{usage.get('completion_tokens', '?')} sortie"
                )
        elif r.status_code in (401, 403):
            self.stdout.write(self.style.ERROR(
                f"\n[X] {r.status_code} - cle DeepSeek invalide ou refusee. Verifie DEEPSEEK_API_KEY dans .env."))
            self.stdout.write("   " + r.text[:300])
        elif r.status_code == 404:
            self.stdout.write(self.style.ERROR(
                f"\n[X] 404 - modele « {model} » introuvable pour ta cle. "
                "Verifie l'ID exact sur https://platform.deepseek.com puis corrige DEEPSEEK_MODEL dans .env."))
            self.stdout.write("   " + r.text[:300])
        elif r.status_code == 429:
            self.stdout.write(self.style.WARNING(
                "\n[X] 429 - quota/debit depasse cote DeepSeek. Reessaie plus tard ou verifie ton solde."))
            self.stdout.write("   " + r.text[:300])
        else:
            self.stdout.write(self.style.ERROR(f"\n[X] {r.status_code} : {r.text[:300]}"))
