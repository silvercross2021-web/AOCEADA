"""INSTALLATION COMPLÈTE D'AOCEDA (après un « git clone »), en une commande, sans rien à corriger à la main :

    python installer.py              (Windows : double-clic sur installer.bat)

Étapes (chacune est sautée si elle est déjà faite : on peut relancer sans risque) :
  1. Python du projet : dossier .venv_local (Python 3.12 ou 3.13 : Django 6 n'existe pas pour 3.11) ;
  2. bibliothèques : requirements.txt ;
  3. réglages : .env créé depuis .env.example (clé secrète Django générée, base SQLite) ;
  4. base de données : migrations ;
  5. modèles de l'assistant IA (~2,1 Go, vérifiés) : python manage.py installer_modeles_ia ;
  6. bilan : ce qui marche, et les clés d'API à mettre dans .env pour le reste.

Options : --sans-modeles (sauter l'étape 5, par exemple sur une connexion lente : la relancer plus tard)
          --dossier-ia <dossier> (modèles et données de l'assistant ailleurs que dans le projet, par exemple sur un
                                  autre disque quand celui du projet manque de place)
"""
import argparse
import os
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ICI = Path(__file__).resolve().parent
VENV = ICI / ".venv_local"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(PYTHON.relative_to(ICI))           # le même, tel qu'il s'écrit depuis le dossier AOCEDA (messages)
CLES_ASSISTANT = (("DEEPSEEK_API_KEY", "chat écrit et vocal (indispensable)", "https://platform.deepseek.com/api_keys"),
                  ("GEMINI_API_KEY", "appel Live (voix en direct)", "https://aistudio.google.com/apikey"),
                  ("CEREBRIUM_API_KEY", "voix baoulé sur GPU (facultatif)", "https://dashboard.cerebrium.ai"),
                  ("OPENROUTER_KEY_AGENT", "secours de l'agent Live (facultatif)", "https://openrouter.ai/settings/keys"),
                  ("OPENROUTER_MANAGEMENT_KEY", "lire le crédit OpenRouter (facultatif)",
                   "https://openrouter.ai/settings/provisioning-keys"))


def titre(n, texte):
    print(f"\n[{n}/6] {texte}", flush=True)


def lancer(*commande, **kw):
    print("      >", " ".join(str(c) for c in commande), flush=True)
    r = subprocess.run([str(c) for c in commande], cwd=ICI, **kw)
    if r.returncode:
        sys.exit(f"\nÉCHEC de : {' '.join(str(c) for c in commande)}\nCorrigez le problème affiché ci-dessus puis relancez "
                 "« python installer.py » (les étapes déjà faites sont sautées).")


def lire_env(f):
    d = {}
    for ligne in f.read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            k, v = ligne.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def regler_env(f, nom, valeur):
    """Met NOM=valeur dans le .env (remplace la ligne existante, sinon l'ajoute)."""
    lignes, fait = f.read_text(encoding="utf-8").splitlines(), False
    for i, l in enumerate(lignes):
        if l.startswith(f"{nom}="):
            lignes[i], fait = f"{nom}={valeur}", True
    if not fait:
        lignes.append(f"{nom}={valeur}")
    f.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def main():
    a = argparse.ArgumentParser(description="Installation complète d'AOCEDA")
    a.add_argument("--sans-modeles", action="store_true", help="ne pas installer les modèles de l'assistant maintenant")
    a.add_argument("--dossier-ia", help="dossier des modèles et données de l'assistant (par défaut : AOCEDA/donnees_ia)")
    o = a.parse_args()
    print("=== Installation d'AOCEDA ===")

    titre(1, "Python du projet (.venv_local)")
    if sys.version_info < (3, 12) or sys.version_info >= (3, 14):
        sys.exit(f"Python {sys.version.split()[0]} : il faut Python 3.12 ou 3.13 (https://www.python.org/downloads/) ; "
                 "Django 6 n'existe pas pour Python 3.11, ni kokoro-onnx (voix de secours) pour 3.14.")
    if PYTHON.exists():
        print("      déjà là")
    else:
        venv.EnvBuilder(with_pip=True).create(VENV)
        print("      créé")

    titre(2, "Bibliothèques (requirements.txt) : quelques minutes la première fois")
    lancer(PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip")
    lancer(PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements.txt")

    titre(3, "Réglages (.env)")
    env = ICI / ".env"
    if env.exists():
        print("      .env déjà là (gardé tel quel)")
    else:
        shutil.copyfile(ICI / ".env.example", env)
        regler_env(env, "SECRET_KEY", "aoceda-" + secrets.token_urlsafe(48))
        print("      .env créé depuis .env.example (clé secrète générée, base SQLite)")
    if o.dossier_ia:
        regler_env(env, "CHATBOT_DOSSIER_IA", o.dossier_ia)
        print(f"      dossier de l'assistant : {o.dossier_ia}")

    titre(4, "Base de données (migrations)")
    lancer(PYTHON, "manage.py", "migrate", "--noinput")

    titre(5, "Modèles de l'assistant IA (~2,1 Go, téléchargés depuis leurs sources officielles et vérifiés)")
    if o.sans_modeles:
        print(f"      sauté (--sans-modeles) : plus tard, « {PY} manage.py installer_modeles_ia »")
    else:
        lancer(PYTHON, "manage.py", "installer_modeles_ia")

    titre(6, "Bilan")
    valeurs = lire_env(env)
    manquantes = [(k, role, lien) for k, role, lien in CLES_ASSISTANT if not valeurs.get(k)]
    if manquantes:
        print("      Clés d'API à mettre dans le fichier .env (lien pour obtenir chacune) :")
        for k, role, lien in manquantes:
            print(f"        - {k:22} {role} : {lien}")
        print("      Sans clé, l'assistant le dit honnêtement ; tout le reste d'AOCEDA marche.")
    else:
        print("      Clés de l'assistant : renseignées.")
    lanceur = "lancer_aoceda.bat (ou " if os.name == "nt" else "("
    print(f"\nInstallation terminée. Lancer AOCEDA : {lanceur}« {PY} manage.py runserver 0.0.0.0:8003 »), "
          "puis http://127.0.0.1:8003\n"
          f"Comptes : « {PY} manage.py createsuperuser » (administrateur), ou « {PY} manage.py setup_demo » "
          "(comptes de démonstration pour essayer) : voir INSTALLATION.md")


if __name__ == "__main__":
    main()
