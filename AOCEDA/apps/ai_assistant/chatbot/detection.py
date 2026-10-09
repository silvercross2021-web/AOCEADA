"""Détection de la langue d'un message (mode « Automatique »).

Pourquoi : mesuré le 28/09/2026, avec la seule consigne « réponds dans la langue de l'utilisateur »,
Gemini ET DeepSeek ont répondu en français à des questions en anglais ou en espagnol (3 cas sur 23),
parce que la consigne système est écrite en français. Le serveur détecte donc lui-même la langue
et donne au modèle un ordre explicite (« ce message est en anglais : réponds en anglais »).

Méthode (légère, sans Internet, ~1 ms) :
  1. écriture non latine -> langue sûre (arabe, chinois, russe...) ;
  2. sinon py3langid, limité aux langues du chatbot ;
  3. message trop court ou ambigu (« ok », « merci ») -> on garde la langue de la conversation.
"""
import re

from . import langues

SEUIL_CONFIANCE = 0.80
MOTS_MIN = 3

ECRITURES = [  # (motif, code) : l'écriture suffit à trancher
    (r"[؀-ۿ]", "ar"), (r"[֐-׿]", "he"), (r"[฀-๿]", "th"), (r"[ঀ-৿]", "bn"),
    (r"[ऀ-ॿ]", "hi"), (r"[぀-ヿ]", "ja"), (r"[가-힯]", "ko"), (r"[一-鿿]", "zh"),
    (r"[Ͱ-Ͽ]", "el"),
]
_ident = {"objet": None}


def _identifiant():
    if _ident["objet"] is None:
        from py3langid.langid import MODEL_FILE, LanguageIdentifier
        idf = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
        idf.set_languages(list(langues.LANGUES))
        _ident["objet"] = idf
    return _ident["objet"]


def detecter(texte):
    """Renvoie (code, confiance) ; code = None si on ne peut pas trancher."""
    t = (texte or "").strip()
    lettres = re.findall(r"\w", t)
    if not lettres:
        return None, 0.0
    for motif, code in ECRITURES:
        if len(re.findall(motif, t)) >= max(2, len(lettres) * 0.3):
            return code, 1.0
    if re.search(r"[Ѐ-ӿ]", t):                   # cyrillique : russe ou ukrainien
        return ("uk" if re.search(r"[іїєґ]", t, re.I) else "ru"), 0.95
    code, confiance = _identifiant().classify(t)
    return code, float(confiance)


def langue_du_message(texte, precedente=None, indice=None):
    """Langue à imposer pour la réponse. Message court/ambigu -> indice (langue entendue par la
    transcription d'un vocal) ou, à défaut, langue précédente de la conversation."""
    code, confiance = detecter(texte)
    court = len(re.findall(r"\w+", texte or "")) < MOTS_MIN
    if code and confiance >= (0.99 if court else SEUIL_CONFIANCE) and code in langues.LANGUES:
        return code, confiance, "détectée"
    if indice in langues.LANGUES:
        return indice, confiance, "entendue (vocal)"
    if precedente:
        return precedente, confiance, "conversation"
    if code in langues.LANGUES and confiance >= 0.5:
        return code, confiance, "détectée (faible)"
    return None, confiance, "inconnue"
