"""Erreurs IMPRÉVUES, gardées avec tout leur détail technique (06/10/2026).

Vu le 06/10/2026 : une réponse baoulé s'est coupée (« Réponse interrompue » dans la page) sans laisser AUCUNE trace,
impossible ensuite d'en retrouver la cause. Désormais, chaque erreur imprévue pendant une réponse est écrite ici
(journaux/erreurs.log : heure, contexte, message, pile d'appels) et la page reçoit un vrai message d'erreur.
"""
import threading
import traceback
from datetime import datetime

from .config import JOURNAUX

FICHIER = JOURNAUX / "erreurs.log"
TAILLE_MAX = 2_000_000
_verrou = threading.Lock()


def noter(contexte, erreur, detail=""):
    """Écrit l'erreur (avec sa pile d'appels) ; ne lève jamais d'exception elle-même."""
    try:
        pile = "".join(traceback.format_exception(type(erreur), erreur, erreur.__traceback__))
        with _verrou:
            FICHIER.parent.mkdir(parents=True, exist_ok=True)
            if FICHIER.exists() and FICHIER.stat().st_size > TAILLE_MAX:
                FICHIER.replace(FICHIER.with_name(f"erreurs_{datetime.now():%Y%m%d_%H%M%S}.log"))
            with open(FICHIER, "a", encoding="utf-8") as f:
                f.write(f"===== {datetime.now().isoformat(timespec='seconds')} · {contexte} · {str(detail)[:300]}\n{pile}\n")
    except Exception:
        pass
