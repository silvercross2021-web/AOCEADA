"""Fin rapide d'un vocal écouté par morceaux (11/11/2026) : l'avis de Whisper tiny sur le vocal ENTIER évite d'attendre les oreilles
lourdes (dioula, baoulé, wolof) quand le vocal entier est nettement français ou anglais, et ne change RIEN sinon.

Cas réel : un vocal de 11 s, français à 93 % en entier, mais un morceau de 2,6 s tombait à 20 % : moyenne 73 %, donc « pas sûr », les trois
oreilles locales lancées, et 18,8 s d'attente après le dernier mot. Sans modèle : oreilles, Whisper et ses probabilités sont simulés."""
import threading
import time

from apps.ai_assistant.chatbot import voix

from .test_passerelle_ecoute import ecoute, moteurs, wav_bytes  # noqa: F401  (fixture `moteurs`)


class OreilleBloquee:
    """Une oreille lourde qui ne rend la main que quand le test la libère."""

    def __init__(self, texte="x"):
        self.libre, self.texte, self.appels = threading.Event(), texte, 0

    def transcrire_audio(self, audio, garder_probas=True, annulation=None):
        self.appels += 1
        self.libre.wait(timeout=30)
        return ecoute(self.texte)


def _probs_selon_la_duree(entier, morceau):
    """Whisper tiny simulé : sûr du français sur le vocal entier (> 5 s), hésitant sur un morceau court."""
    return lambda audio: dict(entier) if len(audio) > 5 * 16000 else dict(morceau)


def test_vocal_entier_francais_sur_ne_attend_pas_les_oreilles_lourdes(moteurs, monkeypatch):
    lourde = OreilleBloquee()
    moteurs.dyu = moteurs.bci = moteurs.wo = lourde
    monkeypatch.setattr(voix, "_probs_tiny", _probs_selon_la_duree({"fr": 0.93, "pt": 0.02}, {"tr": 0.4, "fr": 0.2}))
    assert "langue" not in voix.ecouter_morceau(wav_bytes(2.5), "sess-fr-1", 0, "auto", None)      # tiny hésite : oreilles locales lancées
    t = time.time()
    r = voix.transcrire_serveur(wav_bytes(8.0), None, None, "sess-fr-1", 1)
    assert time.time() - t < 5, "il a attendu les oreilles lourdes"
    assert r["langue"] == "fr" and r["routage"]["chemin"] == "whisper" and "vocal entier" in r["routage"]["raison"]
    assert r["temps"]["avis_vocal_entier_s"] < 5 and "morceaux_abandonnes" in r["temps"]
    assert moteurs.whisper and moteurs.whisper[-1][0] == 8.0                  # Whisper a transcrit le vocal ENTIER
    lourde.libre.set()


def test_vocal_entier_pas_sur_la_decision_habituelle_est_gardee(moteurs, monkeypatch):
    """Un vocal dioula : tiny n'est sûr de rien en entier ; les oreilles locales décident, exactement comme avant."""
    monkeypatch.setattr(voix, "_probs_tiny", _probs_selon_la_duree({"it": 0.31, "fr": 0.12}, {"it": 0.3, "fr": 0.1}))
    moteurs.dyu.textes = ["n ka kuran juru banna", "a tora joli", "a bɛ dɔgɔya", "kosɛbɛ"]
    moteurs.bci.textes = ["n ka kuran", "a tora"]
    for rang, duree in ((0, 2.5), (1, 2.0), (2, 2.0)):
        voix.ecouter_morceau(wav_bytes(duree), "sess-dy-1", rang, "auto", None)
        voix._morceaux["sessions"]["sess-dy-1"]["liste"][rang][1].result(timeout=10)
    r = voix.transcrire_serveur(wav_bytes(7.5), None, None, "sess-dy-1", 3)
    assert r["langue"] == "dyu" and r["routage"]["chemin"] == "omni"
    assert "avis_vocal_entier_s" not in r["temps"]                          # l'avis n'a rien changé


def test_vocal_entier_pas_sur_attend_les_oreilles_meme_quand_elles_sont_lentes(moteurs, monkeypatch):
    lourde = OreilleBloquee("n ka kuran juru banna")
    moteurs.dyu = moteurs.bci = moteurs.wo = lourde
    monkeypatch.setattr(voix, "_probs_tiny", _probs_selon_la_duree({"it": 0.31, "fr": 0.12}, {"it": 0.3, "fr": 0.1}))
    voix.ecouter_morceau(wav_bytes(2.5), "sess-dy-2", 0, "auto", None)
    threading.Timer(1.0, lourde.libre.set).start()                           # les oreilles finissent après 1 s
    t = time.time()
    r = voix.transcrire_serveur(wav_bytes(5.0), None, None, "sess-dy-2", 1)
    assert time.time() - t >= 0.9                                           # il les a bien attendues
    assert "avis_vocal_entier_s" not in r["temps"] and r.get("langue") != "fr"


def test_oreilles_deja_finies_aucun_avis_sur_le_vocal_entier(moteurs, monkeypatch):
    """Tout est déjà écouté à la fin : rien à attendre, donc aucun appel supplémentaire à tiny."""
    appels = []
    monkeypatch.setattr(voix, "_probs_tiny", lambda audio: appels.append(len(audio)) or {"fr": 0.97})
    voix.ecouter_morceau(wav_bytes(2.5), "sess-fr-3", 0, "auto", None)
    voix._morceaux["sessions"]["sess-fr-3"]["liste"][0][1].result(timeout=10)
    voix.transcrire_serveur(wav_bytes(5.0), None, None, "sess-fr-3", 1)
    assert 5 * 16000 not in appels                                           # jamais d'avis sur les 5 s entières : rien à gagner
