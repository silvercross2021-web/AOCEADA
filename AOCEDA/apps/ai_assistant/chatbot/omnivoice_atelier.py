"""Atelier de VOIX BAOULÉ : OmniVoice (k2-fsa, validé le 29/09/2026 contre de vraies voix baoulé) qui imite la voix
d'un vrai locuteur baoulé (RK, enregistrement WAXAL), sur ce PC, sans Internet.

FACULTATIF (secours du GPU Cerebrium) : il tourne dans un programme À PART, avec un Python qui a torch et OmniVoice
(réglage CHATBOT_PYTHON_OMNIVOICE du .env ; le serveur AOCEDA n'a pas besoin de ces 3 Go de bibliothèques). Le chatbot le démarre quand il faut (voix_baoule.py) et il
s'arrête tout seul après ARRET_INACTIF_S sans travail (il occupe ~3,5 Go de mémoire). Il tourne en priorité la plus
basse du système et sur la moitié des cœurs : il ne doit JAMAIS ralentir le reste du chatbot.

Petit serveur local (127.0.0.1 seulement) :
  GET  /etat            -> {"pret", "en_cours", "moyenne_s"}
  POST /voix  {"texte"} -> audio WAV (24 kHz) ; une seule fabrication à la fois (le processeur est déjà plein)

Vitesse sur ce PC (pas de carte graphique) : ~15 à 45 s par phrase avec le réglage rapide (30/09/2026) ; plus si la
mémoire du PC est pleine (le modèle occupe ~3,8 Go : sans mémoire libre, Windows échange avec le disque).

    <python avec OmniVoice> omnivoice_atelier.py 8771     (lancé par voix_baoule.py, qui lui passe les dossiers)
"""
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Dossiers passés par voix_baoule.py (réglages AOCEDA) : poids d'OmniVoice (cache Hugging Face, ~3,1 Go) et voix modèle.
# OBLIGATOIRE (pas « setdefault ») : le serveur qui lance l'atelier a son propre HF_HOME (Whisper), hérité par ce
# programme. Bug vu le 30/09/2026 : modèle introuvable.
os.environ["HF_HOME"] = os.environ["OMNIVOICE_HF_HOME"]
if (Path(os.environ["HF_HOME"]) / "hub" / "models--k2-fsa--OmniVoice").exists():
    os.environ["HF_HUB_OFFLINE"] = "1"                     # le modèle est déjà sur le disque : jamais de téléchargement
VOIX = Path(os.environ["CHATBOT_VOIX_BAOULE_DIR"])
# 8 étapes + voix modèle COURTE (2,4 s) : mesuré le 30/09/2026 sur 3 vraies phrases (tests/qualite_reglage_rapide.py
# du labo) : 30 s par phrase au lieu de 306 s (16 étapes + modèle de 8 s), qualité égale (sons 0,77 contre 0,79,
# 3/3 reconnues, mélodie 0,62 contre 0,52). La voix modèle est recalculée à CHAQUE étape : c'est elle qui coûtait.
ETAPES = 8
ARRET_INACTIF_S = 300           # ~4 Go de mémoire rendus 5 min après la dernière voix
FILS = max(2, (os.cpu_count() or 4) // 2)   # la moitié des cœurs : l'autre moitié reste au chatbot (écoute, Whisper)
TEXTE_MAX = 400

_etat = {"modele": None, "invite": None, "verrou": threading.Lock(), "en_cours": 0, "durees": [], "dernier": time.time()}


def charger():
    import torch
    from omnivoice import OmniVoice
    torch.set_num_threads(FILS)
    ref = json.loads((VOIX / "reference.json").read_text(encoding="utf-8"))
    m = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu", dtype=torch.float32)
    _etat["invite"] = m.create_voice_clone_prompt(ref_audio=str(VOIX / ref["fichier"]), ref_text=ref["texte"])
    _etat["modele"] = m


def fabriquer(texte):
    import soundfile as sf
    with _etat["verrou"]:                                   # une seule phrase à la fois
        t = time.time()
        audio = _etat["modele"].generate(text=texte, language="Baoulé", voice_clone_prompt=_etat["invite"], num_step=ETAPES)[0]
        _etat["durees"] = (_etat["durees"] + [time.time() - t])[-10:]
    tampon = io.BytesIO()
    sf.write(tampon, audio, 24000, format="WAV")
    return tampon.getvalue()


class Guichet(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, d):
        corps = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(corps)))
        self.end_headers(); self.wfile.write(corps)

    def do_GET(self):
        if self.path == "/etat":
            d = _etat["durees"]
            return self._json(200, {"pret": _etat["modele"] is not None, "en_cours": _etat["en_cours"],
                                    "moyenne_s": round(sum(d) / len(d), 1) if d else None})
        self._json(404, {"erreur": "inconnu"})

    def do_POST(self):
        if self.path != "/voix" or _etat["modele"] is None:
            return self._json(503 if self.path == "/voix" else 404, {"erreur": "atelier pas prêt"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            texte = (json.loads(self.rfile.read(min(n, 20000)).decode("utf-8")).get("texte") or "").strip()
        except Exception:
            return self._json(400, {"erreur": "demande illisible"})
        if not texte or len(texte) > TEXTE_MAX:
            return self._json(400, {"erreur": "texte vide ou trop long"})
        _etat["en_cours"] += 1
        try:
            audio = fabriquer(texte)
        except Exception as e:
            return self._json(500, {"erreur": f"OmniVoice : {e}"[:200]})
        finally:
            _etat["en_cours"] -= 1
            _etat["dernier"] = time.time()
        self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(audio)))
        self.end_headers(); self.wfile.write(audio)


def surveiller(serveur):
    """Arrêt automatique après ARRET_INACTIF_S sans travail : la mémoire (~3,5 Go) est rendue au PC."""
    while True:
        time.sleep(30)
        if _etat["en_cours"] == 0 and time.time() - _etat["dernier"] > ARRET_INACTIF_S:
            serveur.shutdown()
            return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
    serveur = ThreadingHTTPServer(("127.0.0.1", port), Guichet)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    charger()
    _etat["dernier"] = time.time()
    print("PRET", flush=True)
    surveiller(serveur)
