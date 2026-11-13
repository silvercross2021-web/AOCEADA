"""Voix dioula de RELAIS : Kooma (API officielle, voix bambara), utilisée seulement si Djelia ne répond pas (13/11/2026).

Pourquoi : la voix dioula n'avait qu'un seul fournisseur (Djelia, par sa démo publique sans clé). Kooma est un second
fournisseur indépendant, avec une clé (KOOMA_API_KEY dans .env) : 59 voix bambara, WAV 24 kHz. Mesuré le 13/11/2026 : de 3 à 43 s
par phrase selon la charge (Djelia : environ 4 s), débit limité à 20 requêtes par minute et par clé, facturé au caractère.
Sans clé, ce module ne fait rien : la liste des voix du dioula reste celle d'avant (Djelia seul).
"""
import re

ADRESSE = "https://api.kooma.ai/v1/audio/speech"
VOIX = {"femme": "kani", "homme": "modibo"}         # deux voix bambara de la liste de Kooma (GET /v1/voices)
DELAI_S = 60                                        # une phrase a mis jusqu'à 43 s en pleine charge
LIMITE_CARACTERES = 5000                            # plafond de l'API par requête


class ErreurKooma(Exception):
    pass


# Kooma ne donne pas le solde par sa clé (visible seulement dans leur console) : on compte ce qu'on lui envoie depuis le démarrage.
USAGE = {"appels": 0, "caracteres": 0}


def _cle():
    from django.conf import settings
    return getattr(settings, "KOOMA_API_KEY", "") or ""


def disponible():
    """Vrai si une clé Kooma est dans .env (sinon le relais n'est pas ajouté à la liste des voix)."""
    return bool(_cle())


def fabriquer(texte, genre="femme"):
    """Lit un texte BAMBARA / DIOULA avec Kooma. Renvoie les octets du fichier WAV. Lève ErreurKooma si ça échoue."""
    from .dioula_relais import _http
    cle = _cle()
    if not cle:
        raise ErreurKooma("pas de clé Kooma (KOOMA_API_KEY)")
    texte = re.sub(r"\s+", " ", texte or "").strip()[:LIMITE_CARACTERES]
    if not texte:
        raise ErreurKooma("rien à lire")
    r = _http.post(ADRESSE, headers={"Authorization": f"Bearer {cle}"},
                   json={"input": texte, "voice": VOIX.get(genre, VOIX["femme"])}, timeout=DELAI_S)
    if r.status_code == 429:
        raise ErreurKooma("trop de demandes (limite de 20 par minute)")
    if r.status_code in (401, 403):
        raise ErreurKooma(f"clé refusée ({r.status_code})")
    if r.status_code == 402:
        raise ErreurKooma("solde Kooma épuisé")
    r.raise_for_status()
    if "audio" not in r.headers.get("content-type", "") or len(r.content) < 1000:
        raise ErreurKooma("pas d'audio dans la réponse")
    USAGE["appels"] += 1
    USAGE["caracteres"] += len(texte)
    return r.content
