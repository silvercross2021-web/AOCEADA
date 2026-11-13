"""Relais de la voix dioula : Kooma prend la main quand Djelia ne répond pas (13/11/2026). Aucun appel réel : tout est simulé."""
import pytest
from django.test import override_settings

from apps.ai_assistant.chatbot import voix, voix_kooma


def _panne(texte):
    raise ConnectionError("403")


@pytest.fixture(autouse=True)
def _cache_isole(tmp_path, monkeypatch):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)


@override_settings(KOOMA_API_KEY="cle-de-test")
def test_kooma_prend_le_relais_si_djelia_tombe(monkeypatch):
    monkeypatch.setattr(voix, "_djelia_voix", _panne)
    monkeypatch.setattr(voix_kooma, "fabriquer", lambda texte, genre="femme": b"RIFF" + b"k" * 2000)
    audio, infos = voix.synthetiser("I ni ce.", "dyu", "femme")
    assert audio.startswith(b"RIFF") and infos["moteur"].startswith("Kooma") and infos["mime"] == "audio/wav"
    assert "Djelia" in infos["erreurs"][0]                      # la panne de Djelia est notée


@override_settings(KOOMA_API_KEY="cle-de-test")
def test_djelia_reste_le_premier_choix(monkeypatch):
    monkeypatch.setattr(voix, "_djelia_voix", lambda texte: b"d" * 2000)
    monkeypatch.setattr(voix_kooma, "fabriquer", lambda *a, **k: pytest.fail("Kooma ne doit pas être appelé si Djelia répond"))
    audio, infos = voix.synthetiser("I ni ce.", "dyu", "femme")
    assert infos["moteur"].startswith("Djelia")


@override_settings(KOOMA_API_KEY="")
def test_sans_cle_pas_de_relais(monkeypatch):
    monkeypatch.setattr(voix, "_djelia_voix", _panne)
    monkeypatch.setattr(voix_kooma, "fabriquer", lambda *a, **k: pytest.fail("pas de clé : Kooma ne doit pas être essayé"))
    with pytest.raises(voix.ErreurVoix):
        voix.synthetiser("I ni ce.", "dyu", "femme")


@override_settings(KOOMA_API_KEY="cle-de-test")
def test_si_les_deux_tombent_la_voix_est_indisponible(monkeypatch):
    monkeypatch.setattr(voix, "_djelia_voix", _panne)

    def kooma_en_panne(texte, genre="femme"):
        raise voix_kooma.ErreurKooma("trop de demandes (limite de 20 par minute)")
    monkeypatch.setattr(voix_kooma, "fabriquer", kooma_en_panne)
    with pytest.raises(voix.ErreurVoix) as e:
        voix.synthetiser("I ni ce.", "dyu", "homme")
    assert "Djelia" in str(e.value) and "Kooma" in str(e.value)


@override_settings(KOOMA_API_KEY="cle-de-test")
@pytest.mark.parametrize("statut,mot", [(429, "trop de demandes"), (401, "refusée"), (402, "épuisé")])
def test_kooma_dit_honnetement_pourquoi_il_echoue(monkeypatch, statut, mot):
    class Reponse:
        status_code = statut
        headers = {}
        content = b""

        def raise_for_status(self):
            raise AssertionError("non atteint")

    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setattr(dioula_relais._http, "post", lambda *a, **k: Reponse())
    with pytest.raises(voix_kooma.ErreurKooma, match=mot):
        voix_kooma.fabriquer("I ni ce.", "femme")


@override_settings(KOOMA_API_KEY="cle-de-test")
def test_kooma_choisit_la_voix_selon_le_genre(monkeypatch):
    envoyes = []

    class Reponse:
        status_code = 200
        headers = {"content-type": "audio/wav"}
        content = b"RIFF" + b"x" * 2000

        def raise_for_status(self):
            pass

    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setattr(dioula_relais._http, "post", lambda url, **k: envoyes.append(k["json"]["voice"]) or Reponse())
    voix_kooma.fabriquer("I ni ce.", "femme")
    voix_kooma.fabriquer("I ni ce.", "homme")
    assert envoyes == ["kani", "modibo"]
