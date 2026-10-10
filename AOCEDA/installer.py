"""INSTALLATION COMPLÈTE D'AOCEDA (après un « git clone »), en une commande, sans rien à corriger à la main :

    python installer.py              (Windows : double-clic sur installer.bat)

Étapes (chacune est sautée si elle est déjà faite : on peut relancer sans risque) :
  1. Python du projet : dossier .venv_local (Python 3.12 ou 3.13 : Django 6 n'existe pas pour 3.11) ;
  2. bibliothèques : requirements.txt ;
  3. réglages : .env créé depuis .env.example (clé secrète Django générée, base SQLite) ; s'il existe déjà (ancienne
     version, .env d'un autre PC), seuls les réglages qui lui manquent sont ajoutés, vides ;
  4. base de données : migrations ;
  5. modèles de l'assistant IA (~2,1 Go, vérifiés) : python manage.py installer_modeles_ia ;
  6. bilan : ce qui marche, et les clés d'API à mettre dans .env pour le reste.

Options : --sans-modeles (sauter l'étape 5, par exemple sur une connexion lente : la relancer plus tard)
          --dossier-ia <dossier> (modèles et données de l'assistant ailleurs que dans le projet, par exemple sur un
                                  autre disque quand celui du projet manque de place)

Clés d'API reçues d'un membre de l'équipe (un fichier de lignes NOM=valeur) :

    python installer.py --cles <fichier>            (--effacer : supprimer ce fichier une fois les clés posées)

Cette commande ne fait QUE cela : elle met ces clés dans le .env sans jamais les afficher (seuls leurs noms sont
écrits à l'écran). Un agent IA peut donc la lancer sans voir les clés.
"""
import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path, PureWindowsPath

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


def disque_absent(chemin):
    """Disque du chemin s'il n'existe pas sur ce PC (ex. « D: »), sinon None. Un chemin Windows (« D:\\... ») sur Linux
    ou Mac compte comme absent."""
    lecteur = PureWindowsPath(chemin).drive
    if lecteur and os.name != "nt":
        return lecteur
    ancre = Path(chemin).anchor
    return ancre if ancre and not Path(ancre).exists() else None


def completer_env(env):
    """.env d'une ancienne version d'AOCEDA (copie locale passée sur cette branche) : il lui manque les réglages
    ajoutés depuis (clés de l'assistant...). Ajoutés VIDES, comme dans une installation neuve ; les réglages qui ont
    une valeur dans .env.example (DB_ENGINE, DEBUG...) ne sont jamais ajoutés : absents, ils gardent le choix de
    cette machine (DB_ENGINE absent = PostgreSQL, par exemple)."""
    presents = lire_env(env)
    manquants = []
    for ligne in (ICI / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            nom, valeur = (x.strip() for x in ligne.split("=", 1))
            if nom not in presents and not valeur:
                manquants.append(nom)
    if manquants:
        texte = env.read_text(encoding="utf-8")
        texte += ("" if texte.endswith("\n") else "\n") + "\n# Réglages ajoutés par installer.py (rôle de chacun : .env.example)\n"
        env.write_text(texte + "".join(f"{nom}=\n" for nom in manquants), encoding="utf-8")
        print(f"      {len(manquants)} réglage(s) ajouté(s), vides : {', '.join(manquants)}")


def verifier_dossier_ia(env):
    """.env recopié d'un autre PC (par exemple pour avoir ses clés d'API) : son CHATBOT_DOSSIER_IA peut viser un disque
    qui n'existe pas ici ; il est alors remis par défaut (AOCEDA/donnees_ia), sinon AOCEDA ne démarrerait pas."""
    dossier = lire_env(env).get("CHATBOT_DOSSIER_IA", "")
    disque = disque_absent(dossier) if dossier else None
    if disque:
        regler_env(env, "CHATBOT_DOSSIER_IA", "")
        print(f"      CHATBOT_DOSSIER_IA={dossier} : le disque {disque} n'existe pas sur ce PC (.env venu d'un autre PC ?) ;"
              " remis par défaut : AOCEDA/donnees_ia")


# Réglages propres à chaque PC : un fichier de clés venu d'un autre PC ne les change jamais (un CHATBOT_DOSSIER_IA
# sur un disque absent ici empêcherait AOCEDA de démarrer, un autre DB_ENGINE changerait de base de données...)
PROPRES_AU_PC = ("SECRET_KEY", "DEBUG", "DB_ENGINE", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT",
                 "FRONTEND_URL", "ALLOWED_HOSTS", "CHATBOT_DOSSIER_IA", "CHATBOT_PYTHON_OMNIVOICE")


def importer_cles(env, fichier, effacer=False):
    """Met dans le .env les clés d'API d'un fichier reçu d'un membre de l'équipe (lignes NOM=valeur), SANS JAMAIS les
    afficher : seuls leurs noms sont écrits. Seuls les réglages connus de .env.example sont pris ; ceux qui sont
    propres à chaque PC sont laissés, même s'ils sont dans le fichier. Une ligne déjà présente est remplacée (pas de
    doublon) ; une valeur vide ne remplace rien. effacer : le fichier de clés est supprimé une fois les clés posées
    (fichier temporaire écrit par un agent IA à partir de clés reçues dans un message)."""
    source = Path(fichier).expanduser()
    if not source.is_file():
        sys.exit(f"Fichier de clés introuvable : {source}")
    if not env.exists():
        sys.exit("Pas encore de fichier .env : lancez d'abord l'installation (installer.bat ou python installer.py).")
    octets = source.read_bytes()
    try:
        texte = octets.decode("utf-8-sig")              # Bloc-notes : UTF-8, avec ou sans marque de début
    except UnicodeDecodeError:
        texte = octets.decode("latin-1")
    connus = set(lire_env(ICI / ".env.example"))
    mises, laissees, inconnues = [], [], []
    for ligne in texte.splitlines():
        ligne = ligne.strip().lstrip("-*•> ").strip("`").strip()     # recopié d'un message : puce, accents graves
        if "=" not in ligne or ligne.startswith("#"):
            continue
        nom, valeur = (x.strip() for x in ligne.split("=", 1))
        valeur = valeur.strip("`\"'").strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", nom) or not valeur:
            continue
        if nom in PROPRES_AU_PC:
            laissees.append(nom)
        elif nom in connus or re.fullmatch(r"GEMINI_API_KEY_[2-9]", nom):
            regler_env(env, nom, valeur)
            mises.append(nom)
        else:
            inconnues.append(nom)
    print("=== Clés d'API d'AOCEDA (aucune valeur n'est affichée) ===")
    print(f"Mises dans .env ({len(mises)}) : {', '.join(mises) or 'aucune'}")
    if laissees:
        print(f"Laissées telles quelles (propres à chaque PC) : {', '.join(laissees)}")
    if inconnues:
        print(f"Ignorées (noms inconnus d'AOCEDA) : {', '.join(inconnues)}")
    if not mises:
        sys.exit("Aucune clé trouvée dans ce fichier : il doit contenir des lignes NOM=valeur (ex. DEEPSEEK_API_KEY=...).")
    manquantes = [k for k, _, _ in CLES_ASSISTANT[:2] if not lire_env(env).get(k)]
    if manquantes:
        print(f"Encore vide dans .env : {', '.join(manquantes)}")
    if effacer:
        source.unlink()
        print(f"Fichier de clés effacé : {source.name}")
        print("Redémarrez AOCEDA pour qu'il lise ces clés.")
    else:
        print("Redémarrez AOCEDA pour qu'il lise ces clés, puis supprimez le fichier de clés : elles sont dans le .env.")


def main():
    a = argparse.ArgumentParser(description="Installation complète d'AOCEDA")
    a.add_argument("--sans-modeles", action="store_true", help="ne pas installer les modèles de l'assistant maintenant")
    a.add_argument("--dossier-ia", help="dossier des modèles et données de l'assistant (par défaut : AOCEDA/donnees_ia)")
    a.add_argument("--cles", metavar="FICHIER", help="seulement : mettre dans .env les clés d'API de ce fichier (lignes "
                   "NOM=valeur), sans les afficher")
    a.add_argument("--effacer", action="store_true", help="avec --cles : effacer le fichier de clés une fois posées")
    o = a.parse_args()
    if o.cles:
        importer_cles(ICI / ".env", o.cles, effacer=o.effacer)
        return
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
        print("      .env déjà là (gardé ; seuls les réglages qui lui manquent sont ajoutés, vides)")
        completer_env(env)
    else:
        shutil.copyfile(ICI / ".env.example", env)
        regler_env(env, "SECRET_KEY", "aoceda-" + secrets.token_urlsafe(48))
        print("      .env créé depuis .env.example (clé secrète générée, base SQLite)")
    if o.dossier_ia:
        regler_env(env, "CHATBOT_DOSSIER_IA", o.dossier_ia)
        print(f"      dossier de l'assistant : {o.dossier_ia}")
    else:
        verifier_dossier_ia(env)

    titre(4, "Base de données (migrations)")
    lancer(PYTHON, "manage.py", "migrate", "--noinput")

    titre(5, "Modèles de l'assistant IA (~2,1 Go, téléchargés puis vérifiés fichier par fichier)")
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
