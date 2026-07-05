#!/usr/bin/env python3
"""
Pont série Arduino → AOCEDA
Lit les mesures du Arduino (ZMCT103C) sur le port série et les envoie
à l'API AOCEDA en temps réel.

Usage:
    python serial_bridge.py [port] [baudrate]
    python serial_bridge.py COM3 9600

Prérequis:
    pip install pyserial requests
"""
import sys
import re
import time
import queue
import threading
import requests

SERIAL_PORT  = sys.argv[1] if len(sys.argv) > 1 else 'COM7'
BAUD_RATE    = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
AOCEDA_URL   = 'http://localhost:8000/api/sensors/arduino/'
BRIDGE_TOKEN = 'arduino-bridge-local-aoceda'

# Format Arduino : [Capteur_1] Centre=512 Ampl=120 [ON ] Courant=0.586A Tension=220V Puissance=128.9W
RE_STATUS    = re.compile(r'\[(\w+)\]\s+Centre=\d+\s+Ampl=\d+\s+\[(ON |OFF)\](.*)')
RE_COURANT   = re.compile(r'Courant=([\d.]+)A')
RE_PUISSANCE = re.compile(r'Puissance=([\d.]+)W')

# ---- File d'envoi HTTP -------------------------------------------------------
# La boucle série ne bloque JAMAIS sur le réseau. L'envoi HTTP se fait
# dans un thread séparé pour que le bridge reste synchrone avec l'Arduino.
_send_queue = queue.Queue(maxsize=100)


def _sender_worker():
    """Thread d'arrière-plan : envoie les mesures à l'API Django."""
    while True:
        data = _send_queue.get()
        if data is None:   # sentinelle d'arrêt
            break
        envoyer(data)
        _send_queue.task_done()


def parse_ligne(ligne: str):
    ligne = ligne.strip()
    m = RE_STATUS.search(ligne)   # search() car la ligne commence par t=123s [Capteur_1] ...
    if not m:
        return None
    capteur = m.group(1)
    etat    = m.group(2).strip()
    reste   = m.group(3)          # tout après [ON ]/[OFF] (Courant=... Puissance=...)
    mc = RE_COURANT.search(reste)
    mp = RE_PUISSANCE.search(reste)
    return {
        'capteur':   capteur,
        'etat':      etat,
        'courant':   float(mc.group(1)) if mc else None,
        'puissance': float(mp.group(1)) if mp else None,
    }


def envoyer(data: dict):
    try:
        r = requests.post(
            AOCEDA_URL,
            json=data,
            headers={'X-Bridge-Token': BRIDGE_TOKEN},
            timeout=2,   # 2s max (réduit de 5s pour ne pas congestionner la file)
        )
        if r.status_code not in (200, 201):
            print(f"[Bridge] Erreur API {r.status_code}: {r.text[:120]}")
    except requests.RequestException as e:
        print(f"[Bridge] Réseau : {e}")


def connecter():
    try:
        import serial
    except ImportError:
        print("[Bridge] ERREUR : pyserial non installé.")
        print("         Lancez : pip install pyserial")
        sys.exit(1)

    while True:
        try:
            port = serial.Serial()
            port.dtr      = False        # ne pas resetter l'Arduino à la connexion
            port.port     = SERIAL_PORT
            port.baudrate = BAUD_RATE
            port.timeout  = 1
            port.open()
            port.reset_input_buffer()    # vide les octets en attente
            print(f"[Bridge] Connecté sur {SERIAL_PORT} @ {BAUD_RATE} baud")
            print(f"[Bridge] Envoi vers {AOCEDA_URL}")
            return port
        except serial.SerialException as e:
            print(f"[Bridge] Impossible d'ouvrir {SERIAL_PORT} : {e}")
            print("[Bridge] Nouvelle tentative dans 5 s…")
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                print("\n[Bridge] Arrêt.")
                sys.exit(0)


def main():
    print("=== Pont Série Arduino → AOCEDA ===")
    print(f"    Port    : {SERIAL_PORT}")
    print(f"    API     : {AOCEDA_URL}")
    print("    Ctrl+C pour arrêter")
    print()

    # Démarrer le thread d'envoi HTTP en arrière-plan
    t = threading.Thread(target=_sender_worker, daemon=True)
    t.start()

    port = connecter()
    while True:
        try:
            ligne = port.readline().decode('utf-8', errors='replace')
            if not ligne.strip():
                continue
            data = parse_ligne(ligne)
            if data:
                courant_str   = f"{data['courant']}A"   if data['courant']   is not None else "—"
                puissance_str = f"{data['puissance']}W" if data['puissance'] is not None else "—"
                # Affichage immédiat, jamais bloqué par l'HTTP
                print(f"[Bridge] {data['capteur']:12s} [{data['etat']:3s}]  {courant_str:8s}  {puissance_str}")
                # Envoi asynchrone : si la file est pleine (API trop lente), on abandonne la mesure
                try:
                    _send_queue.put_nowait(data)
                except queue.Full:
                    pass

        except KeyboardInterrupt:
            print("\n[Bridge] Arrêt.")
            try:
                port.close()
            except Exception:
                pass
            _send_queue.put(None)   # signal d'arrêt au thread HTTP
            sys.exit(0)

        except Exception as e:
            if 'serial' in type(e).__module__:
                print(f"[Bridge] Perte de connexion : {e}")
                try:
                    port.close()
                except Exception:
                    pass
                try:
                    time.sleep(5)
                except KeyboardInterrupt:
                    print("\n[Bridge] Arrêt.")
                    sys.exit(0)
                port = connecter()
            else:
                print(f"[Bridge] Erreur inattendue : {e}")


if __name__ == '__main__':
    main()
