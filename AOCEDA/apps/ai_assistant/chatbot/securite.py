"""Sécurité du serveur : limites de débit par personne, noms d'hôte acceptés, origine des demandes, en-têtes de protection.

Limites (par conversation ET par adresse IP, fenêtre glissante d'une minute) : empêchent qu'une seule
personne (ou un robot) monopolise DeepSeek, Whisper ou la voix au détriment des autres.

Audit du 09/10/2026 (corrigé) :
  - NOM D'HÔTE : seules les adresses IP, « localhost » et le nom du partage public EN COURS sont acceptés. Un site piégé
    dont le nom pointe vers 127.0.0.1 (« DNS rebinding ») ne peut plus utiliser l'API (DeepSeek, GPU, banque d'exemples).
  - ORIGINE : une demande qui modifie quelque chose (POST) venant d'un AUTRE site que la page du chatbot est refusée
    (une page web malveillante ouverte sur ce PC ne peut plus réveiller le GPU payant ni poser des questions).
  - PARTAGE PUBLIC : le nom du tunnel n'est accepté que si le tunnel tourne VRAIMENT (programme cloudflared vivant) ;
    avant, le fichier cache/partage_public.json restait après une fermeture brutale de la fenêtre du partage.
  - ADRESSE DU VISITEUR : l'en-tête Cf-Connecting-Ip n'est cru que pour une demande arrivée PAR le tunnel en cours
    (nom d'hôte du tunnel) ; avant, n'importe quelle demande locale pouvait l'inventer et contourner les limites.
"""
import ctypes
import ipaddress
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from .config import CACHE

# action -> (nombre maximum, par fenêtre de secondes)
LIMITES = {
    "message": (20, 60),        # questions au chatbot
    "transcription": (12, 60),  # messages vocaux
    "voix": (300, 60),          # morceaux de voix (une réponse = quelques morceaux x 2 genres)
    "nouvelle": (30, 60),
    "morceau": (60, 60),        # dioula : morceaux de vocal envoyés PENDANT l'enregistrement (≤ 12 par vocal)
    "live": (6, 60),            # appels Live ouverts par minute (chaque appel ouvre une session Gemini)
    "reveil": (6, 60),          # réveils du GPU de la voix baoulé (menu passé au baoulé) ; voix_gpu n'en lance qu'un / 45 s
    "credit": (20, 60),         # lecture du crédit Cerebrium (gardée 60 s côté serveur)
    "decoupage": (120, 60),     # découpage d'une réponse en morceaux de voix (bouton Écouter)
    "lecture": (60, 60),        # lectures sans calcul (tests et rapports, état des réserves Live, liste d'exemples)
}

_historique = defaultdict(deque)
_verrou = threading.Lock()


class TropDeDemandes(Exception):
    def __init__(self, attente_s):
        super().__init__(f"Trop de demandes : réessayez dans {attente_s} s.")
        self.attente_s = attente_s


# ── Noms d'hôte et partage public ──────────────────────────────────────────────
PARTAGE_PUBLIC = CACHE / "partage_public.json"      # écrit par partage_public.py pendant un partage, effacé à l'arrêt
# noms d'hôte acceptés en plus (essais automatiques : « testserver » du client de test FastAPI ; voir tests/conftest.py)
HOTES_SUPPLEMENTAIRES = {h.strip().lower() for h in os.environ.get("CHATBOT_HOTES_SUPPLEMENTAIRES", "").split(",")
                         if h.strip()}
ENTETES_TUNNEL = ("cf-connecting-ip", "cf-ray", "x-real-ip", "x-forwarded-for")
_partage = {"cle": None, "t": 0.0, "hotes": frozenset(), "verrou": threading.Lock()}
VERIFICATION_PARTAGE_S = 5          # le tunnel est revérifié (programme vivant) au plus toutes les 5 s


def nom_hote(hote):
    """« 127.0.0.1:8770 » -> « 127.0.0.1 » ; « [::1]:8770 » -> « ::1 » ; « Abc.Example:80 » -> « abc.example »."""
    try:
        return (urlparse("//" + (hote or "")).hostname or "").lower()
    except ValueError:
        return ""


def hote_sur(hote):
    """Adresse IP ou « localhost » : un nom de domaine pourrait pointer vers ce PC (« DNS rebinding »)."""
    nom = nom_hote(hote)
    if nom == "localhost":
        return True
    try:
        ipaddress.ip_address(nom)
        return True
    except ValueError:
        return False


def processus_vivant(pid, nom=None):
    """Le programme `pid` tourne-t-il encore (et s'appelle-t-il bien `nom`, pour ne pas se tromper sur un numéro réutilisé) ?"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)                       # signal 0 : test d'existence seulement (hors Windows)
            return True
        except OSError:
            return False
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:     # 259 = STILL_ACTIVE
            return False
        if nom:
            tampon, taille = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if not k.QueryFullProcessImageNameW(h, 0, tampon, ctypes.byref(taille)):
                return False
            return nom.lower() in os.path.basename(tampon.value).lower()
        return True
    finally:
        k.CloseHandle(h)


def hotes_partage(fichier=None):
    """Noms publics du partage EN COURS (tunnel vivant), sinon un ensemble vide. Fichier sans numéro de programme (ancienne
    version de partage_public.py) ou programme arrêté : aucun nom accepté."""
    f = fichier or PARTAGE_PUBLIC
    try:
        st = f.stat()
        cle = (str(f), st.st_mtime_ns, st.st_size)
    except OSError:
        return frozenset()
    with _partage["verrou"]:
        if _partage["cle"] == cle and time.time() - _partage["t"] < VERIFICATION_PARTAGE_S:
            return _partage["hotes"]
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            vivant = processus_vivant(d.get("pid"), "cloudflared")
            hotes = frozenset(nom_hote(h) for h in d.get("hotes", []) if isinstance(h, str) and nom_hote(h)) if vivant else frozenset()
        except (OSError, ValueError, AttributeError, TypeError):
            hotes = frozenset()
        _partage.update(cle=cle, t=time.time(), hotes=hotes)
        return hotes


def hote_partage(hote, fichier=None):
    nom = nom_hote(hote)
    return bool(nom) and nom in hotes_partage(fichier)


def hote_accepte(hote):
    """Nom d'hôte d'une demande accepté : adresse IP, « localhost », partage public en cours (ou essais automatiques)."""
    return hote_sur(hote) or nom_hote(hote) in HOTES_SUPPLEMENTAIRES or hote_partage(hote)


def origine_acceptee(origine, hote):
    """Demande venant de la page du chatbot elle-même. Sans en-tête Origin (outils, essais, anciens navigateurs pour un
    GET) : acceptée ; un navigateur envoie toujours Origin pour un POST venu d'un autre site."""
    if not origine:
        return True
    if origine.strip().lower() == "null":
        return False
    try:
        return urlparse(origine).netloc.lower() == (hote or "").lower() and hote_accepte(hote)
    except ValueError:
        return False


def _est_local(hote_client):
    try:
        return hote_client is not None and ipaddress.ip_address(hote_client).is_loopback
    except ValueError:
        return False


def adresse_client(hote_client, entetes):
    """Adresse de la personne, pour les limites. Le serveur n'écoute que sur ce PC (127.0.0.1) : une connexion venant de
    127.0.0.1 est soit ce PC, soit le tunnel du partage public, par lequel TOUS les visiteurs arrivent avec la même
    adresse. Le tunnel (Cloudflare) écrit la vraie adresse du visiteur dans Cf-Connecting-Ip, en écrasant ce que le
    visiteur enverrait. Cet en-tête n'est cru QUE pour une demande arrivée par le tunnel en cours (nom d'hôte du
    tunnel) : sinon, n'importe quel programme local pourrait l'inventer et contourner les limites."""
    if _est_local(hote_client) and hote_partage(entetes.get("host")):
        for nom in ("cf-connecting-ip", "x-real-ip"):
            reelle = (entetes.get(nom) or "").strip()
            try:
                return str(ipaddress.ip_address(reelle))
            except ValueError:
                continue
    return hote_client


def acces_local(hote_client, entetes):
    """Ce PC lui-même, pas un visiteur du partage public : réservé aux réglages (validation des exemples baoulé, crédit
    du GPU relu de force)."""
    return (_est_local(hote_client) and hote_sur(entetes.get("host"))
            and not any(entetes.get(n) for n in ENTETES_TUNNEL))


# ── Limites de débit ───────────────────────────────────────────────────────────
def verifier(action, *cles):
    """Lève TropDeDemandes si l'une des clés (session, IP...) a dépassé la limite de cette action."""
    maximum, fenetre = LIMITES[action]
    maintenant = time.time()
    with _verrou:
        for cle in cles:
            if not cle:
                continue
            q = _historique[(action, cle)]
            while q and q[0] <= maintenant - fenetre:
                q.popleft()
            if len(q) >= maximum:
                raise TropDeDemandes(int(q[0] + fenetre - maintenant) + 1)
        for cle in cles:
            if cle:
                _historique[(action, cle)].append(maintenant)
        if len(_historique) > 50_000:            # mémoire bornée : on oublie les clés inactives
            for k in [k for k, q in _historique.items() if not q or q[-1] < maintenant - 3600]:
                del _historique[k]


def remettre_a_zero():
    with _verrou:
        _historique.clear()


# ── En-têtes de protection ─────────────────────────────────────────────────────
ENTETES = {
    "X-Content-Type-Options": "nosniff",          # le navigateur ne devine pas le type des fichiers
    "X-Frame-Options": "DENY",                    # la page ne peut pas être intégrée par un autre site
    "Referrer-Policy": "no-referrer",
    # caméra et partage d'écran : seulement pour la page elle-même (appel Live : « montrez-moi votre compteur »)
    "Permissions-Policy": "microphone=(self), camera=(self), display-capture=(self), geolocation=()",
}
_HOTE_PROPRE = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,255}$")


def politique_contenu(hote):
    """Content-Security-Policy : la page ne charge que ses propres fichiers (et la police Google), ne parle qu'à ce
    serveur (WebSocket de l'appel Live compris) et ne peut pas être intégrée ailleurs. « unsafe-inline » : tout le code
    de la page est dans index.html ; « blob: » : capteur du micro (AudioWorklet) et sons des réponses."""
    ws = f" ws://{hote} wss://{hote}" if hote and _HOTE_PROPRE.match(hote) else ""
    return ("default-src 'self'; script-src 'self' 'unsafe-inline' blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; media-src 'self' data: blob:; "
            f"connect-src 'self'{ws}; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'")


def entetes(hote=None):
    """En-têtes de protection d'une réponse (la politique de contenu dépend du nom d'hôte : WebSocket du Live)."""
    return {**ENTETES, "Content-Security-Policy": politique_contenu(hote)}


def entetes_page_aoceda(hote=None):
    """Les mêmes protections pour la page de l'assistant DANS AOCEDA : elle s'affiche dans le cadre de la page « Assistant
    IA » d'AOCEDA, et nulle part ailleurs (frame-ancestors 'self', pas 'none')."""
    return {**ENTETES, "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": politique_contenu(hote).replace("frame-ancestors 'none'", "frame-ancestors 'self'")}
