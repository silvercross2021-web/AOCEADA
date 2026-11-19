#!/usr/bin/env python3
"""
Pont USB ESP32 -> AOCEDA (canal de secours quand le Wi-Fi ne passe pas).

Quand l'ESP32 n'arrive pas a joindre le Wi-Fi ou le serveur, il envoie chaque mesure
sur le cable USB, sur une ligne « @USB {json} ». Ce script la lit, la transmet a
Django (POST /api/sensors/zmct/, comme en Wi-Fi) et renvoie a l'ESP32 la reponse du
serveur dans un accuse « @ACK {json} ». Cette reponse porte les ordres de coupure des
relais (coupe_1, coupe_2) : le bouton « Couper » du site marche donc aussi par l'USB.

Tant que le Wi-Fi marche, l'ESP32 n'utilise pas l'USB : ce pont peut rester lance sans
risque de doublon. Il affiche aussi les messages utiles du firmware (Wi-Fi, relais...).

Usage (depuis AOCEDA/, avec le Python du projet) :
    .venv_local\\Scripts\\python.exe outils\\pont_usb_esp32.py
    .venv_local\\Scripts\\python.exe outils\\pont_usb_esp32.py --port COM4 --url http://127.0.0.1:8003/api/sensors/zmct/

Le port COM de l'ESP32 est detecte tout seul (puce CP210x). Un seul programme peut ouvrir
ce port a la fois : fermez le moniteur serie de PlatformIO avant de lancer le pont.
La cle du boitier est lue dans include/secrets.h (AOCEDA_CLE_DISPOSITIF ; l'ancien src/main.cpp
est aussi accepte), ou donnee par --cle ou par la variable d'environnement
AOCEDA_CLE_DISPOSITIF. Elle n'est jamais affichee.

Prerequis : pyserial et requests (requirements.txt).
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("[Pont USB] ERREUR : la bibliotheque « requests » manque (pip install requests).")
    sys.exit(1)

RACINE_DEPOT = Path(__file__).resolve().parents[2]
# Ou chercher la cle du boitier : include/secrets.h (non versionne), puis l'ancien src/main.cpp
FICHIERS_CLE = (
    (RACINE_DEPOT / "include" / "secrets.h", r'AOCEDA_CLE_DISPOSITIF\s+"([^"]+)"'),
    (RACINE_DEPOT / "src" / "main.cpp", r'apiKeyDevice\s*=\s*"([^"]+)"'),
)
URL_DEFAUT = "http://127.0.0.1:8003/api/sensors/zmct/"
BAUD_DEFAUT = 115200
PUCE_CP210X = (0x10C4, 0xEA60)  # VID / PID de l'ESP32 DevKit (Silicon Labs)

# Messages du firmware qui valent la peine d'etre montres (le reste est du bruit de mesure)
RE_UTILE = re.compile(
    r"rst:|\[RELAIS\]|\[WiFi\]|\[Serveur\]|\[TAMPON\]|ETAT :|Bruit de depart|Pret a mesurer|"
    r"Canal de secours|\[OTA\]|Connecte a|Synchronisation NTP|ZMCT103C - AOCEDA|\[DHT11\]"
)


def horloge():
    return time.strftime("%H:%M:%S")


def journal(message):
    print(f"{horloge()} [Pont USB] {message}", flush=True)


def lire_cle(args):
    """Cle du boitier : option, variable d'environnement, sinon include/secrets.h (ou ancien main.cpp)."""
    if args.cle:
        return args.cle
    if os.environ.get("AOCEDA_CLE_DISPOSITIF"):
        return os.environ["AOCEDA_CLE_DISPOSITIF"]
    for fichier, motif in FICHIERS_CLE:
        try:
            texte = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(motif, texte)
        if m:
            return m.group(1)
    return None


def trouver_port(demande):
    if demande:
        return demande
    from serial.tools import list_ports

    for p in list_ports.comports():
        if (p.vid, p.pid) == PUCE_CP210X:
            return p.device
    return None


def ouvrir_port(serial_module, nom, baud):
    ser = serial_module.Serial()
    ser.port = nom
    ser.baudrate = baud
    ser.timeout = 0.5
    ser.dtr = False  # ne pas redemarrer l'ESP32 a l'ouverture du port
    ser.rts = False
    ser.open()
    ser.reset_input_buffer()
    return ser


class Pont:
    def __init__(self, url, cle, tout_afficher):
        self.url = url
        self.cle = cle
        self.tout_afficher = tout_afficher
        self.session = requests.Session()
        self.stats = {"transmises": 0, "refusees": 0, "injoignable": 0, "illisibles": 0}
        self.dernier = {}  # capteur_index -> (etat, coupe, statut) affiches la derniere fois
        self.dernier_bilan = time.time()
        self.depuis_bilan = 0

    def transmettre(self, corps):
        """POST de la mesure a Django. Renvoie (code HTTP ou None, texte de reponse)."""
        try:
            r = self.session.post(
                self.url,
                data=corps.encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Device {self.cle}"},
                timeout=3,
            )
            return r.status_code, r.text
        except requests.RequestException as e:
            return None, str(e)[:120]

    def traiter_ligne(self, ser, ligne):
        if ligne.startswith("@USB "):
            self.traiter_trame(ser, ligne[5:].strip())
        elif self.tout_afficher or RE_UTILE.search(ligne):
            if "TRAME ENVOYEE PAR USB" not in ligne:
                print(f"{horloge()}   ESP32 | {ligne[:160]}", flush=True)

    def traiter_trame(self, ser, corps):
        try:
            mesure = json.loads(corps)
            index = mesure["capteur_index"]
        except (ValueError, KeyError, TypeError):
            self.stats["illisibles"] += 1
            journal(f"ligne illisible ignoree : {corps[:80]}")
            return

        code, texte = self.transmettre(corps)
        if code == 201:
            reponse = " ".join(texte.split())  # une seule ligne
            # L'heure du PC (UTC) part avec chaque accuse : sans Wi-Fi, la carte n'a pas de NTP et ne peut
            # pas dater son releve de temperature. Elle ne la prend que si elle n'a pas d'heure.
            ser.write(f"@HEURE {int(time.time())}\n@ACK {reponse}\n".encode("utf-8"))
            ser.flush()
            self.stats["transmises"] += 1
            self.depuis_bilan += 1
            cle = (mesure.get("etat"), mesure.get("coupe"), 201)
            if self.dernier.get(index) != cle:  # on n'affiche que les changements
                self.dernier[index] = cle
                journal(
                    f"capteur {index} : {mesure.get('etat')} {mesure.get('puissance')} W "
                    f"(relais {'COUPE' if mesure.get('coupe') else 'ferme'}) -> Django 201, reponse {reponse}"
                )
        elif code is None:
            self.stats["injoignable"] += 1
            if self.dernier.get(index) != ("hs", None, None):
                self.dernier[index] = ("hs", None, None)
                journal(f"Django injoignable ({texte}). Le serveur est-il lance sur {self.url} ?")
        else:
            self.stats["refusees"] += 1
            cle = ("refus", code, None)
            if self.dernier.get(index) != cle:
                self.dernier[index] = cle
                journal(f"Django a refuse la mesure du capteur {index} : HTTP {code} {texte[:100]}")

    def bilan_periodique(self):
        if time.time() - self.dernier_bilan >= 30:
            if self.depuis_bilan:
                journal(f"{self.depuis_bilan} mesure(s) transmise(s) ces 30 dernieres secondes (total {self.stats['transmises']})")
            self.dernier_bilan = time.time()
            self.depuis_bilan = 0


def main():
    parser = argparse.ArgumentParser(description="Pont USB ESP32 -> AOCEDA (canal de secours du Wi-Fi)")
    parser.add_argument("--port", help="port serie de l'ESP32 (detecte tout seul par defaut)")
    parser.add_argument("--baud", type=int, default=BAUD_DEFAUT)
    parser.add_argument("--url", default=URL_DEFAUT, help=f"point d'entree Django (defaut : {URL_DEFAUT})")
    parser.add_argument("--cle", help="cle du boitier (defaut : lue dans include/secrets.h)")
    parser.add_argument("--tout", action="store_true", help="affiche aussi tous les messages de mesure du firmware")
    parser.add_argument(
        "--silence",
        type=float,
        default=40.0,
        help="secondes sans aucun message de l'ESP32 avant de rouvrir le port (defaut 40) : Windows garde "
        "une connexion morte quand on debranche puis rebranche le cable, sans signaler d'erreur. Doit rester "
        "au-dessus du plus long silence normal de l'ESP32 (~26 s pendant la mesure du bruit de depart)",
    )
    args = parser.parse_args()

    # Un caractere que la console Windows (ou un fichier redirige) ne sait pas ecrire ne doit JAMAIS
    # arreter le pont : on le remplace par « ? » au lieu de lever UnicodeEncodeError
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    try:
        import serial
    except ImportError:
        print("[Pont USB] ERREUR : pyserial n'est pas installe dans ce Python.")
        print("           Lancez : .venv_local\\Scripts\\python.exe -m pip install pyserial")
        sys.exit(1)

    cle = lire_cle(args)
    if not cle:
        print("[Pont USB] ERREUR : cle du boitier introuvable (AOCEDA_CLE_DISPOSITIF dans include/secrets.h). Utilisez --cle.")
        sys.exit(1)

    print("=== Pont USB ESP32 -> AOCEDA ===")
    print(f"    Django : {args.url}")
    print("    Ctrl+C pour arreter\n")

    pont = Pont(args.url, cle, args.tout)
    ser = None
    derniere_reception = time.time()
    try:
        while True:
            if ser is None:
                nom = trouver_port(args.port)
                if nom is None:
                    journal("aucun ESP32 detecte sur USB (cable branche ?). Nouvel essai dans 3 s...")
                    time.sleep(3)
                    continue
                try:
                    ser = ouvrir_port(serial, nom, args.baud)
                    derniere_reception = time.time()
                    journal(f"connecte a l'ESP32 sur {nom} ({args.baud} bauds)")
                except serial.SerialException as e:
                    journal(f"impossible d'ouvrir {nom} : {e}")
                    journal("un autre programme utilise ce port (moniteur serie PlatformIO ouvert ?). Nouvel essai dans 3 s...")
                    time.sleep(3)
                    continue
            try:
                brut = ser.readline()
            except (serial.SerialException, OSError) as e:
                journal(f"connexion USB perdue ({e}). Reconnexion...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(2)
                continue
            if brut:
                derniere_reception = time.time()
                ligne = brut.decode("utf-8", errors="replace").strip()
                if ligne:
                    pont.traiter_ligne(ser, ligne)
            elif time.time() - derniere_reception > args.silence:
                # L'ESP32 ecrit en continu : un long silence = connexion devenue invalide (cable rebranche)
                journal(f"plus aucun message de l'ESP32 depuis {args.silence:.0f} s (cable rebranche ?). Reconnexion...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(1)
                continue
            pont.bilan_periodique()
    except KeyboardInterrupt:
        print()
        journal(
            "arret. Bilan : {transmises} transmise(s), {refusees} refusee(s), {injoignable} Django injoignable, "
            "{illisibles} illisible(s).".format(**pont.stats)
        )
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
