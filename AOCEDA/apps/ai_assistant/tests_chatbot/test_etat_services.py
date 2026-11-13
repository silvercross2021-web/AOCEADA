"""Options > Crédits des services (13/11/2026) : TOUS les services, leur rôle (principal / relais de quoi) et leur état.
Aucun appel réseau : tout est simulé."""
import json
import time

import pytest

from apps.ai_assistant.chatbot import credits, etat_services, voix, voix_kooma

DS_OK = {"ok": True, "disponible": True, "solde": 2.45}
OR_OK = {"ok": True, "restant": 2.43, "achete": 5.0, "utilise": 2.57, "agent": {"plafond": 0.2, "restant": 0.19, "utilise": 0.01}}
GPU_OK = {"configure": True, "ok": True, "restant_usd": 14.0, "offert_usd": 25.0, "eveille": False, "plafond_atteint": False}
MODELES = ("deepseek/deepseek-v4-flash", "google/gemini-3.5-flash-lite", "qwen/qwen3.7-flash", "anthropic/claude-haiku-4.5")


def relais(**changes):
    liste = [{"modele": m, "configure": True, "ok": True, "restant": 0.5, "plafond": 1.0, "hors_service": False} for m in MODELES]
    for i, c in changes.items():
        liste[int(i)].update(c)
    return liste


def live(modeles=("gemini-3.8-live", "gemini-3.1-flash-live-preview"), **etat_compte):
    comptes = [{"compte": n, "etat": "ok", "disponible": True, "raison": None, "retour_dans_s": 0, "appels_jour": 0, "minutes_jour": 0, "limites_jour": 0} for n in (1, 2)]
    return {"remise_a_zero_dans_s": 7200, "reserves": [{"modele": m, "comptes": [dict(c, **(etat_compte if k == 0 else {})) for c in comptes]}
                                                       for k, m in enumerate(modeles)]}


def construire(**kw):
    base = dict(ds=DS_OK, orr=OR_OK, gpu=GPU_OK, relais=relais(), live=live(), traducteurs={}, essais={}, kooma={}, locaux={})
    base.update(kw)
    return etat_services.construire(**base)


def tous(sv):
    return {s["id"]: s for g in sv["groupes"] for s in g["services"]}


@pytest.fixture(autouse=True)
def _cles(settings):
    settings.DEEPSEEK_API_KEY = "sk-secret-deepseek"
    settings.KOOMA_API_KEY = "sk-secret-kooma"
    settings.OPENROUTER_KEY_AGENT = "sk-secret-agent"


# ── la structure : principal, relais « de quoi », ordre ───────────────────────────────────────────
def test_les_relais_du_chat_disent_de_quoi_ils_relevent_et_leur_ordre():
    s = tous(construire())
    assert s["deepseek"]["role"] == "principal" and s["deepseek"]["relais_de"] is None
    for rang in (1, 2, 3, 4):
        r = s[f"relais{rang}"]
        assert (r["role"], r["relais_de"], r["rang"]) == ("relais", "DeepSeek", rang)
    assert [s[f"relais{i}"]["nom"].split(" (")[0] for i in (1, 2, 3, 4)] == ["DeepSeek V4 Flash", "Gemini 3.5 Flash Lite", "Qwen 3.7 Flash", "Claude Haiku 4.5"]


def test_les_modeles_live_suivants_relaient_le_meilleur():
    s = tous(construire(live=live(("gemini-3.8-live", "gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-latest"))))
    assert (s["live0"]["role"], s["live0"]["relais_de"]) == ("principal", None)
    assert (s["live1"]["role"], s["live1"]["relais_de"], s["live1"]["rang"]) == ("relais", "Gemini 3.8 Live", 1)
    assert s["live2"]["rang"] == 2


def test_chaque_service_a_un_groupe_un_role_et_un_etat_connus():
    sv = construire()
    for g in sv["groupes"]:
        for s in g["services"]:
            assert s["role"] in ("principal", "relais", "local", "compte") and s["etat"] in ("ok", "attention", "ko", "inactif", "inconnu"), s["nom"]
            assert s["role"] != "relais" or s["relais_de"], s["nom"]
    titres = [g["titre"] for g in sv["groupes"]]
    assert titres[0].startswith("Réponses du chat") and "Voix" in titres[2] and "Traduction" in titres[3]


def test_les_services_sans_relais_sont_signales_mais_pas_les_modeles_locaux():
    s = tous(construire(locaux={"whisper/tiny": ("micro : reconnaît la langue parlée", True)}))
    assert s["voix_wolof"]["sans_relais"] and s["trad_google"]["sans_relais"]            # vrais trous : un seul fournisseur
    assert not s["stt_whisper_tiny"]["sans_relais"] and s["stt_whisper_tiny"]["role"] == "local"
    assert not s["voix_djelia"]["sans_relais"] and s["voix_kooma"]["relais_de"].startswith("Djelia")


# ── crédits et états ──────────────────────────────────────────────────────────────────────────────
def test_credit_de_chaque_relais_et_du_compte():
    s = tous(construire(relais=relais(**{"0": {"restant": 0.36, "plafond": 0.5}})))
    assert s["relais1"]["credit"]["restant"] == 0.36 and s["relais1"]["credit"]["sur"] == 0.5 and s["relais1"]["mesure"] == "credit"
    assert s["deepseek"]["credit"]["restant"] == 2.45
    assert s["openrouter"]["credit"]["restant"] == 2.43 and s["agent"]["credit"]["restant"] == 0.19


@pytest.mark.parametrize("changement,etat", [({"restant": 0.0}, "ko"), ({"restant": 0.03}, "attention"), ({"hors_service": True}, "ko"),
                                              ({"configure": False}, "inactif"), ({"ok": False, "raison": "x"}, "inconnu"), ({"restant": 0.5}, "ok")])
def test_etat_d_un_relais(changement, etat):
    assert tous(construire(relais=relais(**{"1": changement})))["relais2"]["etat"] == etat


def test_deepseek_epuise_ou_sans_cle_ou_illisible(settings):
    assert tous(construire(ds={"ok": True, "disponible": False, "solde": 0.0}))["deepseek"]["etat"] == "ko"
    assert tous(construire(ds={"ok": True, "disponible": True, "solde": 0.5}))["deepseek"]["etat"] == "attention"
    assert tous(construire(ds={"ok": False, "raison": "Solde illisible"}))["deepseek"]["etat"] == "inconnu"      # jamais un « ok » inventé
    settings.DEEPSEEK_API_KEY = ""
    assert tous(construire())["deepseek"]["etat"] == "inactif"


def test_gemini_live_limite_atteinte_et_acces_refuse():
    s = tous(construire(live=live(etat="repos", disponible=False, retour_dans_s=2520, raison="limite")))
    assert s["live0"]["etat"] == "attention" and s["live1"]["etat"] == "ok"           # 1 compte sur 2 a atteint sa limite
    tout_limite = live()
    for m in tout_limite["reserves"][:1]:
        for c in m["comptes"]:
            c.update(etat="repos", disponible=False, retour_dans_s=2520)
    d = tous(construire(live=tout_limite))["live0"]
    assert d["etat"] == "attention" and "42 min" in d["detail"]
    refuse = live()
    for c in refuse["reserves"][0]["comptes"]:
        c.update(etat="ko", disponible=False, retour_dans_s=0)
    assert tous(construire(live=refuse))["live0"]["etat"] == "ko"


def test_gpu_non_configure_plafond_atteint_et_credit_bas():
    assert tous(construire(gpu={"configure": False}))["voix_baoule"]["etat"] == "inactif"
    assert tous(construire(gpu=dict(GPU_OK, plafond_atteint=True)))["voix_baoule"]["etat"] == "attention"
    assert tous(construire(gpu=dict(GPU_OK, restant_usd=1.0)))["voix_baoule"]["etat"] == "attention"
    assert tous(construire(gpu={"configure": True, "ok": False, "raison": "illisible"}))["voix_baoule"]["etat"] == "inconnu"


# ── voix et traducteurs : rien n'est inventé ───────────────────────────────────────────────────────
def test_une_voix_jamais_essayee_est_inconnue_puis_son_dernier_essai_est_montre():
    assert tous(construire())["voix_djelia"]["etat"] == "inconnu"
    t = time.time()
    s = tous(construire(essais={"Djelia (voix bambara)": {"ok": True, "t": t, "raison": ""}}))["voix_djelia"]
    assert s["etat"] == "ok" and "réussi" in s["detail"]
    s = tous(construire(essais={"Djelia (voix bambara)": {"ok": False, "t": t, "raison": "403"}}))["voix_djelia"]
    assert s["etat"] == "attention" and "403" in s["detail"]


def test_kooma_sans_cle_en_reserve_et_compte_des_caracteres(settings):
    settings.KOOMA_API_KEY = ""
    assert tous(construire())["voix_kooma"]["etat"] == "inactif"
    settings.KOOMA_API_KEY = "sk-secret-kooma"
    assert tous(construire())["voix_kooma"]["etat"] == "ok"
    s = tous(construire(kooma={"appels": 3, "caracteres": 480}, essais={"Kooma (voix bambara, relais)": {"ok": True, "t": time.time(), "raison": ""}}))["voix_kooma"]
    assert "480 caractères" in s["detail"] and s["mesure"] == "non_lisible"


def test_un_traducteur_coupe_est_a_surveiller():
    s = tous(construire(traducteurs={"djelia": {"disponible": False, "pannes": 0}, "google": {"disponible": True, "pannes": 0, "dernier_ok": time.time()}}))
    assert s["trad_djelia"]["etat"] == "attention" and "autre traducteur" in s["trad_djelia"]["detail"]
    assert s["trad_google_dyu"]["etat"] == "ok"


def test_modele_local_absent_est_signale():
    s = tous(construire(locaux={"omnilingual-1b-ctc-v2-int8": ("micro : écoute du DIOULA", False), "whisper/tiny": ("micro : langue", True)}))
    assert s["stt_omnilingual-1b-ctc-v2-int8"]["etat"] == "ko" and s["stt_whisper_tiny"]["etat"] == "ok"


# ── résumé, alertes, secret ───────────────────────────────────────────────────────────────────────
def test_resume_et_alertes_sont_coherents():
    sv = construire(relais=relais(**{"0": {"hors_service": True}, "3": {"restant": 0.01}}))
    r = sv["resume"]
    assert r["total"] == sum(len(g["services"]) for g in sv["groupes"]) == r["ok"] + r["attention"] + r["ko"] + r["inactif"] + r["inconnu"]
    assert {a["etat"] for a in sv["alertes"]} == {"ko", "attention"} and len(sv["alertes"]) == r["ko"] + r["attention"]


def test_jamais_une_cle_dans_la_reponse():
    texte = json.dumps(construire(), ensure_ascii=False)
    for cle in ("sk-secret-deepseek", "sk-secret-kooma", "sk-secret-agent"):
        assert cle not in texte


# ── ce que le serveur note à chaque essai ──────────────────────────────────────────────────────────
def test_la_synthese_note_le_dernier_essai_de_chaque_voix(monkeypatch, tmp_path):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    monkeypatch.setattr(voix, "DERNIERS_ESSAIS", {})

    def panne(texte):
        raise ConnectionError("403")
    monkeypatch.setattr(voix, "_djelia_voix", panne)
    monkeypatch.setattr(voix_kooma, "fabriquer", lambda texte, genre="femme": b"RIFF" + b"k" * 2000)
    voix.synthetiser("I ni ce.", "dyu", "femme")                       # sans clé Kooma (conftest) : Djelia seul, en échec
    assert voix.DERNIERS_ESSAIS["Djelia (voix bambara)"]["ok"] is False and "403" in voix.DERNIERS_ESSAIS["Djelia (voix bambara)"]["raison"]


def test_kooma_compte_les_caracteres_envoyes(monkeypatch, settings):
    settings.KOOMA_API_KEY = "cle-de-test"
    monkeypatch.setattr(voix_kooma, "USAGE", {"appels": 0, "caracteres": 0})

    class Reponse:
        status_code, headers, content = 200, {"content-type": "audio/wav"}, b"RIFF" + b"x" * 2000

        def raise_for_status(self):
            pass
    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setattr(dioula_relais._http, "post", lambda *a, **k: Reponse())
    voix_kooma.fabriquer("I ni ce, n bɛ i dɛmɛ.", "femme")
    assert voix_kooma.USAGE == {"appels": 1, "caracteres": len("I ni ce, n bɛ i dɛmɛ.")}


def test_les_traducteurs_notent_leur_dernier_succes(monkeypatch):
    from apps.ai_assistant.chatbot import dioula_relais
    monkeypatch.setitem(dioula_relais._etat, "google", {"pannes": 2, "coupe_jusqu_a": 0.0})
    dioula_relais._noter("google", True)
    e = dioula_relais.etat()["google"]
    assert e["pannes"] == 0 and e["dernier_ok"] and e["disponible"]


# ── la route ──────────────────────────────────────────────────────────────────────────────────────
def test_credits_tous_donne_la_liste_des_services_sans_planter_si_elle_echoue(monkeypatch):
    monkeypatch.setattr(credits, "_deepseek", lambda: DS_OK)
    monkeypatch.setattr(credits, "_openrouter", lambda: OR_OK)
    monkeypatch.setattr(credits.voix_gpu, "credit", lambda forcer=False: GPU_OK)
    monkeypatch.setitem(credits._cache, "valeur", None)
    v = credits.tous(forcer=True)
    assert v["services"]["groupes"] and v["services"]["resume"]["total"] > 20 and v["deepseek"]["solde"] == 2.45     # l'ancien format est gardé
    monkeypatch.setattr(etat_services, "construire", lambda *a, **k: 1 / 0)
    v = credits.tous(forcer=True)
    assert v["services"]["groupes"] == [] and "indisponible" in v["services"]["erreur"] and v["deepseek"]["solde"] == 2.45
