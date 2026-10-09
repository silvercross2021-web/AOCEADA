"""Tests automatiques du DIOULA (étape 2), sans Internet : DeepSeek, traducteurs, voix et Omnilingual sont simulés
(sauf le test marqué « modele », qui charge le vrai modèle d'écoute s'il est présent).

    env\\Scripts\\python.exe -m pytest tests -q
"""
import io
from datetime import datetime
import json
import time
import wave

import numpy as np
import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import (consignes, conversation, dioula_ecoute, dioula_relais, dioula_routage, dioula_texte, garde_langue, langues, salutations, securite, service_chat, service_dioula, voix)
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur


@pytest.fixture(autouse=True)
def base_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])        # aucune voix fabriquée pendant les tests
    monkeypatch.setattr(salutations, "maintenant", lambda: datetime(2026, 10, 9, 20, 0))   # 20 h : 1re réponse « I ni su. »
    securite.remettre_a_zero()
    yield
    securite.remettre_a_zero()


@pytest.fixture
def traducteurs(monkeypatch):
    """Traducteurs simulés : aller = traductions fausses typiques ; retour = une phrase dioula par phrase française
    (une « traduction » qui garderait le français serait refusée par le contrôle, voir plus bas)."""
    vu = {"aller": [], "retour": []}

    def traduire(service, sens, texte):
        vu["aller" if sens == "vers_fr" else "retour"].append((service, texte))
        if sens == "vers_fr":
            return {"google": "mon cordon est débranché", "djelia": "ma carte de crédit est finie"}[service]
        return dyu(texte)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    return vu


def dyu(texte_francais):
    return f"A ka di {len(texte_francais)} ɲɛ."


def deepseek(*morceaux):
    return [("DeepSeek", "ds", lambda systeme, historique: iter(morceaux))]


# ── Texte : reconnaître le dioula ──────────────────────────────────────────────
@pytest.mark.parametrize("texte", ["n ka kuran juru banna", "I ni ce kosɔbɛ", "ɔnhɔn", "N ka crédit banna",
                                   "Courant tigɛra n ka so kɔnɔ", "kilowati lere bi nani ni flatora efe"])
def test_textes_dioula_reconnus(texte):
    assert dioula_texte.est_dioula(texte)[0]


@pytest.mark.parametrize("texte", ["mon courant a coupé depuis ce matin", "non merci", "d'accord",
                                   "the power went off this morning", "Je veux recharger mon compteur",
                                   "cuanto crédito me queda", "asante sana"])
def test_autres_langues_pas_prises_pour_du_dioula(texte):
    assert not dioula_texte.est_dioula(texte)[0]


# ── Texte : chiffres dioula ────────────────────────────────────────────────────
@pytest.mark.parametrize("texte,valeur", [("Kilowati lɛrɛ bi naani ni fila tora n fɛ", 42), ("N ye juru waa duuru san", 5000),
                                          ("tan ni saba", 13), ("kɛmɛ fila", 200), ("bin nani ni fila tora", 42),
                                          ("n ye juru wa duu san", 5000)])
def test_nombres_dioula(texte, valeur):
    assert dioula_texte.lire_nombres(texte)[0]["valeur"] == valeur


def test_dorome_vaut_cinq_francs():
    n = dioula_texte.lire_nombres("a ye dɔrɔmɛ kɛmɛ duuru di")[0]
    assert n["valeur"] == 500 and n["valeur_fcfa"] == 2500


def test_pas_de_faux_nombre_dans_une_phrase_ordinaire():
    assert dioula_texte.lire_nombres("Kɔsa in na, mɔgɔ caman ye bana in sɔrɔ") == []


# ── Texte : réparations prudentes ──────────────────────────────────────────────
class FausseEcoute:
    """Écoute simulée : mots entendus + score sonore choisi par le test."""
    def __init__(self, mots, score=lambda chaine: -10.0):
        self.mots = [{"mot": m, "certitude": 0.9, "t0": 10 * i, "t1": 10 * i + 8} for i, m in enumerate(mots)]
        self._score = score

    def score_sonore(self, chaine, t0, t1):
        return self._score(chaine)


def test_mot_colle_redecoupe():
    texte, faits = dioula_texte.reparer(FausseEcoute(["kilowati", "filatora"]))
    assert texte == "kilowati fila tora" and faits[0]["repare"] == "fila tora"


def test_mot_aoceda_deforme_corrige():
    texte, _ = dioula_texte.reparer(FausseEcoute(["n", "ka", "kumanfakitiri", "la"]))
    assert "kuran fakitiri" in texte


def test_correction_refusee_si_le_son_ne_colle_pas():
    # l'audio colle beaucoup moins bien au mot corrigé (écart > marge) : on garde ce qui a été entendu
    ecoute = FausseEcoute(["jugu"], score=lambda c: -10.0 if c == "jugu" else -30.0)
    assert dioula_texte.reparer(ecoute)[0] == "jugu"


def test_mot_conjugue_jamais_coupe():
    assert dioula_texte.flechi("sɔrɔra") and dioula_texte.reparer(FausseEcoute(["sɔrɔra"]))[0] == "sɔrɔra"


def test_mot_ordinaire_pas_corrige_en_mot_aoceda():
    assert dioula_texte._candidat_domaine("caama") is None           # « caama » (beaucoup) n'est pas « tama »


def test_pronom_colle_separe():
    assert dioula_texte.reparer(FausseEcoute(["mbafe", "ka", "taa"]))[0].startswith("n ba")


@pytest.mark.parametrize("texte,formules", [("ini ke kuso be", ["i ni ce", "kosɛbɛ"]), ("aw ni iche kusebe", ["aw ni ce", "kosɛbɛ"]),
                                            ("ini soma herecirawa", ["i ni sɔgɔma", "hɛrɛ sira wa"]),
                                            ("mbafe kanga conté recharger", ["n b'a fɛ"]), ("Ɔnhɔn, a tigɛ.", ["ɔnhɔn", "a tigɛ"])])
def test_formules_reconnues_meme_mal_entendues(texte, formules):
    assert [f for f, _ in dioula_texte.formules_reconnues(texte)] == formules


def test_non_jamais_pris_pour_oui():
    trouvees = [f for f, _ in dioula_texte.formules_reconnues("Ɔn ɔn, a to yen.")]
    assert "ɔn ɔn" in trouvees and "ɔnhɔn" not in trouvees


@pytest.mark.parametrize("texte", ["kilowati lerɛ bi naani ni fila tora e fɛ", "Kɔsa in na, mɔgɔ caman ye bana in sɔrɔ Burukina jamana na"])
def test_pas_de_formule_inventee(texte):
    assert dioula_texte.formules_reconnues(texte) == []


def test_glossaire_question_et_reste():
    lex = dioula_texte.lexique_utile("juru hakɛ jumɛn tora n fɛ wa")
    assert "tora" in lex and "wa" in lex and "question" in lex["wa"]


def test_lexique_pour_deepseek():
    lex = dioula_texte.lexique_utile("n ka kuran juru banna")
    assert "kuran" in lex and "juru" in lex and "crédit" in lex["juru"]


# ── Détection de langue d'un vocal ─────────────────────────────────────────────
def lecteur(latin, libre=None, compteur=None):
    def lire():
        if compteur is not None:
            compteur.append(1)
        return latin, libre if libre is not None else latin
    return lire


def test_francais_sur_ne_fait_pas_ecouter_omnilingual():
    appels = []
    d = dioula_routage.decider({"fr": 0.98, "en": 0.01}, lecteur("x", compteur=appels))
    assert d["langue"] == "fr" and d["chemin"] == "whisper" and appels == []      # 0 seconde ajoutée


def test_dioula_lu_dans_le_texte():
    d = dioula_routage.decider({"ja": 0.3, "id": 0.2}, lecteur("n ka kuran juru banna"))
    assert d["langue"] == "dyu" and d["chemin"] == "omni"


def test_whisper_sur_a_tort_en_portugais_ne_suffit_pas():
    d = dioula_routage.decider({"pt": 0.95}, lecteur("dooridenw ye ne ka fɛnw bɛɛ jɛni"))
    assert d["langue"] == "dyu"


def test_mot_court_francais_sans_contexte():
    assert dioula_routage.decider({"fr": 0.35, "pt": 0.3}, lecteur("merci beaucoup"))["langue"] == "fr"


def test_merci_glisse_dans_une_conversation_dioula():
    d = dioula_routage.decider({"fr": 0.35, "pt": 0.3}, lecteur("merci beaucoup"), langue_conversation="dyu")
    assert d["langue"] == "dyu"


def test_alphabet_inattendu_ne_change_pas_la_langue():
    # Omnilingual a écrit en arabe alors que Whisper n'entendait pas d'arabe : erreur d'écoute, pas de l'arabe
    d = dioula_routage.decider({"sw": 0.4, "ar": 0.05}, lecteur("mi ma saliyata", "مي مسالياتا"))
    assert d["langue"] == "dyu"


def test_phrase_francaise_claire_dans_conversation_dioula_change_de_langue():
    d = dioula_routage.decider({"fr": 0.99}, lecteur("x"), langue_conversation="dyu")
    assert d["langue"] == "fr"


def test_langue_non_prise_en_charge():
    d = dioula_routage.decider({"yo": 0.85}, lecteur("eleyi dara pupo"))
    assert d["chemin"] == "non-prise" and d["langue"] is None


def test_vrai_dioula_l_emporte_sur_whisper_sur_d_une_langue_non_geree():
    assert dioula_routage.decider({"yo": 0.85}, lecteur("n ka kuran juru banna"))["langue"] == "dyu"


def test_ne_ne_dioula_repondu_en_coreen_reste_du_dioula():
    # « Ɔn ɔn, a to yen » (non, laisse-le) : Omnilingual a écrit en coréen, Whisper hésitait -> réponse dioula
    d = dioula_routage.decider({"ko": 0.35, "ja": 0.2}, lecteur("at", "어 아"), langue_conversation="dyu")
    assert d["langue"] == "dyu"


def test_oui_court_dans_une_conversation_en_francais():
    assert dioula_routage.decider({"en": 0.4, "zh": 0.15}, lecteur("w", "و"), langue_conversation="fr")["langue"] == "fr"


def test_silence():
    assert dioula_routage.decider({"nn": 0.3}, lecteur("", ""))["chemin"] == "silence"


# ── Langue : menu, demande explicite ───────────────────────────────────────────
@pytest.mark.parametrize("texte", ["Éteins le ventilateur du salon.", "Allume la télé du salon", "Ma clim fait du bruit"])
def test_francais_avec_mots_du_lexique_reste_du_francais(texte):
    assert service_chat.choisir_langue("sess-fr-" + str(abs(hash(texte)))[:10], texte, "auto", None)[0] == "fr"


@pytest.mark.parametrize("texte", ["Kalata sira kura bora Burukina jamana kan.", "Femi ka gundo jirala polisiw la.",
                                   "Dori lamini mogow bee kumana ni dusukasi ye."])
def test_dioula_tape_sans_lettres_speciales_pas_pris_pour_du_swahili(texte):
    assert service_chat.choisir_langue("sess-dy-" + str(abs(hash(texte)))[:10], texte, "auto", None)[0] == "dyu"


def test_dioula_dans_le_menu_mais_pas_dans_les_langues_directes():
    assert langues.valide("dyu") and langues.est_relais("dyu") and "dyu" not in langues.LANGUES
    assert any(l["code"] == "dyu" for l in langues.liste_pour_page())


@pytest.mark.parametrize("texte", ["réponds-moi en dioula", "parle dioula", "fɔ jula la", "answer in jula"])
def test_demande_explicite_de_dioula(texte):
    assert garde_langue.demande_explicite(texte) == "dyu"


# ── Service dioula (DeepSeek, traducteurs simulés) ─────────────────────────────
def test_entete_intention_lu():
    r = service_dioula.separer_entete("INTENTION : crédit fini\nCERTITUDE : haute\n\nAchetez du crédit. Merci.")
    assert r == ("crédit fini", "haute", "Achetez du crédit. Merci.")


@pytest.mark.parametrize("texte", ["INTENTION : facture\nCERTITÉ : haute\n\nRéglez à vingt-six degrés.",
                                   "**INTENTION** : facture\n**CERTITUDE** : haute\n\nRéglez à vingt-six degrés."])
def test_entete_mal_ecrit_par_le_modele_jamais_lu_au_client(texte):
    intention, certitude, reste = service_dioula.separer_entete(texte)
    assert intention == "facture" and certitude == "haute" and reste == "Réglez à vingt-six degrés."


def appels_successifs(*reponses):
    """DeepSeek simulé qui répond différemment à chaque appel (1er essai, relance...)."""
    compteur = {"n": 0}

    def ouvrir(systeme, historique):
        compteur["n"] += 1
        compteur.setdefault("dossiers", []).append(historique[-1]["texte"])
        return iter(reponses[min(compteur["n"], len(reponses)) - 1])
    return [("DeepSeek", "ds", ouvrir)], compteur


def test_pas_compris_relance_avec_les_traductions(traducteurs):
    liste, compteur = appels_successifs(["INTENTION : ?\nCERTITUDE : basse\n\nRépétez."],
                                        ["INTENTION : crédit fini\nCERTITUDE : haute\n\nAchetez du crédit."])
    ev = list(service_chat.repondre("sess-dyu-020", "N ka kuran juru banna", "dyu", None, "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    assert compteur["n"] == 2 and fin["relance"] and fin["intention"] == "crédit fini"
    assert "carte de crédit" not in compteur["dossiers"][0] and "carte de crédit" in compteur["dossiers"][1]
    assert [e["texte"] for e in ev if e["type"] == "intention"] == ["crédit fini"]    # le « ? » du 1er essai n'est pas montré


def test_toujours_pas_compris_la_reponse_de_deepseek_part_pas_une_phrase_fixe(traducteurs):
    # retour client 30/09/2026 : plus de « je n'ai pas compris, répétez » identique à chaque fois
    reponse = "Vous parlez peut-être de votre courant. S'agit-il d'une coupure, du crédit ou d'un appareil ?"
    liste, compteur = appels_successifs([f"INTENTION : ?\nCERTITUDE : basse\n\n{reponse}"])
    ev = list(service_chat.repondre("sess-dyu-021", "h cge", "dyu", None, "femme", liste=liste))
    fin = next(e for e in ev if e["type"] == "fin")
    assert compteur["n"] == 2 and fin["relance"] and fin["francais"] == "Bonsoir. " + reponse and "fixe" not in fin
    assert fin["texte"] == "I ni su. " + dyu("Vous parlez peut-être de votre courant.") + " " + dyu(
        "S'agit-il d'une coupure, du crédit ou d'un appareil ?")     # traduite en dioula comme toute réponse
    assert conversation.historique("sess-dyu-021")[0]["texte"].endswith("-> pas compris")


def test_consigne_relais_sans_phrase_toute_faite():
    for systeme in (consignes.systeme_dioula(), consignes.systeme_baoule()):
        assert "JAMAIS de phrase du type" in systeme and "{pas_compris}" not in systeme   # 05/10 : toujours une réponse utile
        assert "demande poliment de répéter" not in systeme


def test_retour_a_la_ligne_termine_une_phrase():
    finies, reste = service_dioula.phrases_finies("Éteignez le climatiseur\nFermez les portes\nMerci")
    assert finies == ["Éteignez le climatiseur", "Fermez les portes"] and reste == "Merci"


def test_jamais_de_boucle_sans_fin_si_le_flux_se_termine_sans_reponse(traducteurs, monkeypatch):
    compteur = {"n": 0}

    def flux_vide(systeme, historique, liste=None):      # générateur, comme le vrai flux, mais ni « fin » ni « erreur »
        compteur["n"] += 1
        yield from ()
    monkeypatch.setattr(service_dioula.fournisseurs, "repondre_flux", flux_vide)
    ev = list(service_chat.repondre("sess-dyu-030", "N ka kuran juru banna", "dyu", None, "femme"))
    assert compteur["n"] == service_dioula.MAX_ESSAIS and any(e["type"] == "erreur" for e in ev)
    assert conversation.historique("sess-dyu-030") == []


def test_entete_incomplet_on_attend():
    assert service_dioula.separer_entete("INTENTION : crédit") is None


def test_entete_oublie_par_le_modele():
    i, c, reste = service_dioula.separer_entete("Achetez du crédit.", fini=True)
    assert i is None and reste == "Achetez du crédit."


def test_message_dioula_de_bout_en_bout(traducteurs):
    ev = list(service_chat.repondre("sess-dyu-001", "N ka kuran juru banna", "auto", None, "femme",
                                    liste=deepseek("INTENTION : crédit d'électricité fini\n", "CERTITUDE : haute\n\n",
                                                   "Achetez du crédit. ", "Allez chez un vendeur agréé.")))
    types = [e["type"] for e in ev]
    assert ev[0] == {"type": "langue", "code": "dyu", "source": "détectée", "confiance": 1.0}
    # 1re réponse : la salutation part tout de suite, puis « Compris : ... », puis la réponse traduite
    assert ev[1] == {"type": "morceau", "texte": "I ni su.", "traduit": True}
    assert types.index("intention") < types.index("morceau", 2) < types.index("fin")
    fin = next(e for e in ev if e["type"] == "fin")
    assert fin["texte"] == f"I ni su. {dyu('Achetez du crédit.')} {dyu('Allez chez un vendeur agréé.')}"
    assert {s for s, _ in traducteurs["retour"]} == {"djelia"}              # Djelia d'abord, Google seulement en secours
    assert fin["francais"] == "Bonsoir. Achetez du crédit. Allez chez un vendeur agréé."
    assert fin["intention"] == "crédit d'électricité fini" and fin["traducteurs"] == ["formule", "djelia", "djelia"]
    dossier = next(e for e in ev if e["type"] == "bilan")["dossier"]
    assert "juru = crédit" in dossier                     # lexique envoyé à DeepSeek
    assert "carte de crédit" not in dossier    # traductions lancées en arrière-plan, mais PAS attendues ni envoyées (1er essai)
    h = conversation.historique("sess-dyu-001")
    assert h[0]["texte"].startswith("[dioula] « N ka kuran juru banna »") and h[1]["texte"] == fin["francais"]
    assert conversation.langue("sess-dyu-001") == "dyu"


def test_traductions_aller_si_on_les_rallume(traducteurs):
    d = service_dioula.preparer_dossier("sess-dyu-010", "N ka kuran juru banna", "ecrit", traduire_aller=True)
    assert "carte de crédit" in d["texte"] and "cordon" in d["texte"]


def test_indice_question_en_wa(traducteurs):
    d = service_dioula.preparer_dossier("sess-dyu-011", "climatiseur be kuran cama duwa", "ecrit")
    assert "QUESTION" in d["texte"]


def test_vocal_dioula_envoie_ce_qui_a_ete_entendu(traducteurs):
    service_dioula.memoriser_vocal("sess-dyu-002", {"texte": "n ka kuran juru banna", "brut": "n ka kuman juru bana",
                                                    "repare": "n ka kuran juru banna", "douteux": ["bana"], "certitude": 0.8,
                                                    "reparations": [{"entendu": "kuman", "repare": "kuran"}]})
    ev = list(service_chat.repondre("sess-dyu-002", "n ka kuran juru banna", "auto", "dyu", "femme", origine="vocal",
                                    liste=deepseek("INTENTION : x\nCERTITUDE : moyenne\n\nOui.")))
    dossier = next(e for e in ev if e["type"] == "bilan")["dossier"]
    assert "VOCAL" in dossier and "kuman juru bana" in dossier and "peu de certitude : bana" in dossier


def test_texte_corrige_a_la_main_traite_comme_ecrit(traducteurs):
    service_dioula.memoriser_vocal("sess-dyu-003", {"texte": "n ka kuman", "brut": "n ka kuman", "repare": "n ka kuman",
                                                    "douteux": [], "certitude": 0.5, "reparations": []})
    ev = list(service_chat.repondre("sess-dyu-003", "n ka kuran juru banna", "dyu", None, "femme", origine="vocal",
                                    liste=deepseek("INTENTION : x\nCERTITUDE : haute\n\nOui.")))
    assert "ÉCRIT" in next(e for e in ev if e["type"] == "bilan")["dossier"]


def test_traduction_en_panne_la_phrase_reste_en_francais(monkeypatch):
    def traduire(service, sens, texte):
        if sens == "vers_fr":
            return "traduction"
        raise dioula_relais.RelaisIndisponible("panne")
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    ev = list(service_chat.repondre("sess-dyu-004", "N ka kuran juru banna", "dyu", None, "femme",
                                    liste=deepseek("INTENTION : x\nCERTITUDE : haute\n\nAchetez du crédit.")))
    fin = next(e for e in ev if e["type"] == "fin")
    # rien de traduit : réponse en français, salutation en français aussi (lue avec la voix française)
    assert fin["texte"] == "Bonsoir. Achetez du crédit." and fin["non_traduit"] == 1 and fin["langue_voix"] == "fr"


def test_reponse_arretee_pas_gardee(traducteurs):
    flux = service_chat.repondre("sess-dyu-005", "N ka kuran juru banna", "dyu", None, "femme",
                                 liste=deepseek("INTENTION : x\nCERTITUDE : haute\n\n", "Achetez. ", "Encore. ", "Fin."))
    for ev in flux:
        if ev["type"] == "morceau":
            break
    flux.close()                                         # bouton Stop
    assert conversation.historique("sess-dyu-005") == []


def test_francais_reste_sur_le_chemin_habituel(traducteurs):
    ev = list(service_chat.repondre("sess-dyu-006", "Comment réduire ma facture d'électricité ?", "auto", None, "femme",
                                    liste=deepseek("Éteignez le climatiseur.")))
    assert ev[0]["code"] == "fr" and not any(e["type"] == "intention" for e in ev) and traducteurs["retour"] == []


# ── Relais : secours et vérifications ──────────────────────────────────────────
def test_traducteurs_en_panne_reponse_lue_avec_la_voix_francaise(monkeypatch):
    def traduire(service, sens, texte):
        raise dioula_relais.RelaisIndisponible("panne")
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    ev = list(service_chat.repondre("sess-dyu-040", "N ka kuran juru banna", "dyu", None, "femme",
                                    liste=deepseek("INTENTION : x\nCERTITUDE : haute\n\nAchetez du crédit. Merci.")))
    fin = next(e for e in ev if e["type"] == "fin")
    assert fin["langue_voix"] == "fr" and fin["non_traduit"] == 2           # la salutation ne compte pas comme traduite
    assert fin["texte"] == "Bonsoir. Achetez du crédit. Merci."            # jamais « I ni su » lu par la voix française
    morceaux = [e for e in ev if e["type"] == "morceau"]
    # la salutation est du vrai dioula (lue en voix dioula si la page l'anticipe) ; le reste, resté en français, jamais
    assert morceaux[0] == {"type": "morceau", "texte": "I ni su.", "traduit": True}
    assert all(e["traduit"] is False for e in morceaux[1:])


class FauxWhisper:
    def __init__(self, probs):
        self.probs = probs

    def detect_language(self, audio):
        top = max(self.probs, key=self.probs.get)
        return top, self.probs[top], list(self.probs.items())

    def transcribe(self, audio, language=None, **k):
        class Seg:
            text, no_speech_prob = "Bonjour, ma facture est trop chère.", 0.0

        class Info:
            language, language_probability = "fr", 0.95
        return iter([Seg()]), Info()


def test_ecoute_dioula_en_panne_on_retombe_sur_whisper(monkeypatch):
    monkeypatch.setitem(voix._whisper, "modele", FauxWhisper({"fr": 0.6}))
    monkeypatch.setitem(voix._whisper, "detecteur", FauxWhisper({"fr": 0.6, "pt": 0.3}))

    def panne(audio):
        raise RuntimeError("modèle illisible")
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", panne)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x01" * 16000)
    r = voix.transcrire(buf.getvalue())
    assert r["texte"].startswith("Bonjour") and r["langue"] == "fr" and r["routage"]["chemin"] == "secours-whisper"


# ── Vocal écouté PENDANT qu'on parle (morceaux envoyés aux pauses) ─────────────
def fausse_ecoute(texte, trames=10):
    mots = [{"mot": m, "certitude": 0.9, "t0": 2 * i, "t1": 2 * i + 1} for i, m in enumerate(texte.split())]
    return dioula_ecoute.Ecoute(mots, np.zeros((trames, 3), dtype="float32"), 1.0, 0.1, texte)


def wav_bytes(secondes, valeur=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.full(int(16000 * secondes), valeur, dtype="<i2").tobytes())
    return buf.getvalue()


def test_fusion_des_morceaux_recale_les_positions():
    e = dioula_ecoute.fusionner([fausse_ecoute("n ka", 10), fausse_ecoute("kuran juru", 7)])
    assert e.texte == "n ka kuran juru" and e._lp.shape[0] == 17
    assert [m["t0"] for m in e.mots] == [0, 2, 10, 12]              # 2e morceau décalé de 10 trames


def test_morceaux_ecoutes_pendant_l_enregistrement_sont_reutilises(monkeypatch):
    ecoutes = iter(["n ka kuran", "juru banna", "kosɛbɛ"])
    appels = []

    def transcrire_audio(audio, garder_probas=True):
        appels.append(len(audio))
        return fausse_ecoute(next(ecoutes))
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", transcrire_audio)
    voix.ecouter_morceau(wav_bytes(2), "sess-morceaux-1", 0)
    voix.ecouter_morceau(wav_bytes(2), "sess-morceaux-1", 1)
    audio = np.zeros(16000 * 5, dtype="float32")                   # vocal complet : 2 + 2 s déjà écoutées + 1 s
    e = voix._reprendre_morceaux("sess-morceaux-1", 2, audio)
    assert e.texte == "n ka kuran juru banna kosɛbɛ"
    assert appels == [32000, 32000, 16000]                          # seule la dernière seconde est écoutée à la fin


def test_morceau_manquant_on_reecoute_tout(monkeypatch):
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("x"))
    voix.ecouter_morceau(wav_bytes(2), "sess-morceaux-2", 0)
    voix.ecouter_morceau(wav_bytes(2), "sess-morceaux-2", 2)         # le n° 1 n'est jamais arrivé
    assert voix._reprendre_morceaux("sess-morceaux-2", 3, np.zeros(16000 * 7, dtype="float32")) is None


def test_morceaux_plus_longs_que_le_vocal_refuses(monkeypatch):
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("x"))
    voix.ecouter_morceau(wav_bytes(3), "sess-morceaux-3", 0)
    assert voix._reprendre_morceaux("sess-morceaux-3", 1, np.zeros(16000, dtype="float32")) is None


def test_trop_de_morceaux_en_attente_serveur_occupe(monkeypatch):
    # bug réel du 29/09 : 30 morceaux envoyés d'un coup étaient tous acceptés (minutes de calcul en file)
    from concurrent.futures import Future
    monkeypatch.setattr(voix, "_pool_ecoute", lambda: type("P", (), {"submit": lambda self, *a: Future()})())
    monkeypatch.setitem(voix._morceaux, "sessions", {})
    acceptes = 0
    for r in range(10):
        try:
            voix.ecouter_morceau(wav_bytes(1), "sess-surcharge", r); acceptes += 1
        except voix.ServeurOccupe:
            pass
    assert acceptes == voix.MORCEAUX_EN_ATTENTE_MAX


def test_api_morceau_refuse_trop_long_et_rang_absurde(monkeypatch):
    monkeypatch.setattr(dioula_ecoute, "transcrire_audio", lambda a, garder_probas=True, annulation=None: fausse_ecoute("x"))
    c = TestClient(serveur.app)
    ok = c.post("/api/transcrire/morceau", files={"audio": ("m.wav", wav_bytes(2), "audio/wav")},
                data={"session": "session-morceau-api", "rang": "0"})
    long = c.post("/api/transcrire/morceau", files={"audio": ("m.wav", wav_bytes(20), "audio/wav")},
                  data={"session": "session-morceau-api", "rang": "1"})
    absurde = c.post("/api/transcrire/morceau", files={"audio": ("m.wav", wav_bytes(2), "audio/wav")},
                     data={"session": "session-morceau-api", "rang": "99"})
    assert ok.status_code == 200 and long.status_code == 400 and absurde.status_code == 400


def _traducteurs_simules(monkeypatch, comportement):
    def traduire(service, sens, texte):
        delai, resultat = comportement[service]
        time.sleep(delai)
        if resultat is None:
            raise dioula_relais.RelaisIndisponible(f"{service} en panne")
        return resultat
    monkeypatch.setattr(dioula_relais, "traduire", traduire)


def test_djelia_lent_a_echouer_google_prend_le_relais_a_temps(monkeypatch):
    # bug réel du 29/09 : Djelia met ~8 s à échouer -> la phrase restait en français alors que Google répondait en 1 s
    _traducteurs_simules(monkeypatch, {"djelia": (4.0, None), "google": (0.3, "Google a ka di.")})
    t = time.time()
    assert dioula_relais.vers_dioula("Achetez du crédit.", preference_s=0.5, delai_total_s=3.0) == ("Google a ka di.", "google")
    assert time.time() - t < 1.5


def test_djelia_reste_prefere_s_il_repond_a_temps(monkeypatch):
    _traducteurs_simules(monkeypatch, {"djelia": (0.8, "Djelia a ka di."), "google": (1.5, "Google.")})
    assert dioula_relais.vers_dioula("Achetez du crédit.", preference_s=0.5, delai_total_s=3.0) == ("Djelia a ka di.", "djelia")


def test_traduction_bornee_dans_le_temps_meme_si_tout_traine(monkeypatch):
    _traducteurs_simules(monkeypatch, {"djelia": (5.0, "x"), "google": (5.0, "y")})
    t = time.time()
    with pytest.raises(dioula_relais.RelaisIndisponible):
        dioula_relais.vers_dioula("Achetez du crédit.", preference_s=0.3, delai_total_s=1.0)
    assert time.time() - t < 1.5


def test_huit_phrases_en_meme_temps_sans_blocage(monkeypatch):
    # une réponse longue : 8 phrases traduites en parallèle ne doivent pas bloquer leurs propres traductions de secours
    _traducteurs_simules(monkeypatch, {"djelia": (1.0, None), "google": (0.2, "Google a ka di.")})
    taches = [dioula_relais.lancer_vers_dioula(f"Phrase numéro {i}.") for i in range(8)]
    t = time.time()
    assert all(f.result(timeout=10)[1] == "google" for f in taches) and time.time() - t < 6


@pytest.mark.parametrize("texte,certitude,bruit", [("e", 0.29, True), ("", 0.0, True), ("at", 0.76, False),
                                                   ("ayi", 0.3, False), ("h cge", 0.47, False)])
def test_bruit_pas_pris_pour_de_la_parole(texte, certitude, bruit):
    assert voix._pas_de_parole({"texte": texte, "certitude": certitude}) is bruit


def test_retour_djelia_puis_google_si_panne(monkeypatch):
    def traduire(service, sens, texte):
        if service == "djelia":
            raise dioula_relais.RelaisIndisponible("djelia en panne")
        return "I ni ce"
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    assert dioula_relais.vers_dioula("Merci") == ("I ni ce", "google")


def test_traduction_restee_en_francais_refusee(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda s, sens, t: t if s == "djelia" else "A ka di")
    assert dioula_relais.vers_dioula("Il faut acheter du crédit chez un vendeur.") == ("A ka di", "google")


def test_aller_n_attend_pas_un_traducteur_lent(monkeypatch):
    def traduire(service, sens, texte):
        if service == "google":
            time.sleep(2)
        return service
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    t = time.time()
    r = dioula_relais.vers_francais("n ka kuran", attente_second_s=0.2)
    assert r["djelia"] == "djelia" and r["google"] is None and time.time() - t < 1.0


def test_coupe_circuit_apres_pannes(monkeypatch):
    monkeypatch.setitem(dioula_relais._etat, "google", {"pannes": 0, "coupe_jusqu_a": 0.0})
    for _ in range(dioula_relais.PANNES_AVANT_COUPURE):
        dioula_relais._noter("google", False)
    assert not dioula_relais._disponible("google")
    dioula_relais._etat["google"]["coupe_jusqu_a"] = 0.0


# ── Voix dioula ────────────────────────────────────────────────────────────────
def test_premiere_phrase_longue_voix_en_deux_morceaux():
    t = "Pour réduire votre facture d'électricité, éteignez le climatiseur quand vous sortez. Merci."
    m = voix.decouper(t)
    assert m[0] == "Pour réduire votre facture d'électricité," and m[1].startswith("éteignez")
    assert voix.premier_morceau_si_complet(t[:60]) == m[0]       # voix préparée tôt = la même que celle lue à la fin
    assert voix.decouper("I ka kuran juru banna. Aw ka kan ka juru kura san.") == ["I ka kuran juru banna.",
                                                                                   "Aw ka kan ka juru kura san."]


@pytest.mark.parametrize("texte", ["Bonjour, je suis l'assistant AOCEDA, là pour vous aider à suivre votre consommation. Merci.",
                                   "A ka c'a la, mankan bɛ bɔ motɛri wulicogo la, wa a bɛ bɔ kosɛbɛ. Aw bɛ a lajɛ.",
                                   "- Réglez la climatisation\n- Éteignez (décodeur, chargeurs)\nVoilà : merci ;"])
def test_chaque_morceau_renvoye_par_la_page_est_accepte(texte):
    # la page renvoie chaque morceau tel quel ; le serveur le nettoie à nouveau : il doit rester identique
    for m in voix.decouper(texte):
        assert voix.texte_pour_voix(m) == m


def test_api_voix_accepte_le_premier_morceau_coupe_a_la_virgule(monkeypatch):
    monkeypatch.setattr(voix, "obtenir", lambda t, l, g: (b"0" * 2000, {"moteur": "m", "voix": "v", "mime": "audio/mp4",
                                                                        "cache": False, "duree_s": 0}))
    texte = "Bonjour, je suis l'assistant AOCEDA, là pour vous aider à suivre votre consommation. Merci."
    conversation.autoriser_voix("session-virgule", voix.decouper(texte))
    c = TestClient(serveur.app)
    for m in voix.decouper(texte):
        assert c.post("/api/voix", json={"session": "session-virgule", "texte": m, "langue": "fr"}).status_code == 200


def test_voix_dioula_djelia_une_seule_voix(monkeypatch, tmp_path):
    monkeypatch.setattr(voix, "DOSSIER_VOIX", tmp_path)
    monkeypatch.setattr(voix, "_djelia_voix", lambda t: b"\x00" * 2000)
    audio, infos = voix.synthetiser("I ni ce.", "dyu", "homme")
    assert infos["moteur"].startswith("Djelia") and infos["mime"] == "audio/mp4"
    assert voix.synthetiser("I ni ce.", "dyu", "femme")[1]["cache"]          # même son pour Femme et Homme


# ── API ────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    return TestClient(serveur.app)


def test_api_config_propose_le_dioula(client):
    assert any(l["code"] == "dyu" for l in client.get("/api/config").json()["langues"])


def test_api_message_dioula(client, traducteurs, monkeypatch):
    monkeypatch.setattr(service_chat.service_dioula.fournisseurs, "candidats",
                        lambda: deepseek("INTENTION : crédit fini\nCERTITUDE : haute\n\nAchetez du crédit."))
    r = client.post("/api/message", json={"session": "session-api-dyu", "texte": "N ka kuran juru banna", "langue": "dyu"})
    ev = [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert any(e["type"] == "intention" for e in ev) and ev[-1]["type"] == "fin"
    assert ev[-1]["francais"] == "Bonsoir. Achetez du crédit."


def test_api_transcription_dioula_du_menu(client, monkeypatch):
    vu = {}
    def faux(octets, langue, moteur=None, langue_conversation=None, session=None, deja=0):
        vu.update(langue=langue, session=session)
        return {"texte": "n ka kuran", "langue": "dyu", "certitude_langue": 1.0, "parole": True, "prise_en_charge": True,
                "modele": "omnilingual", "duree_audio_s": 1.0, "duree_s": 0.5,
                "dioula": {"brut": "n ka kuman", "repare": "n ka kuran", "douteux": [], "reparations": [], "certitude": 0.9}}
    monkeypatch.setattr(voix, "transcrire", faux)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 16000)
    r = client.post("/api/transcrire", files={"audio": ("v.wav", buf.getvalue(), "audio/wav")},
                    data={"langue": "dyu", "session": "session-tr-dyu"})
    assert r.json()["dioula"]["repare"] == "n ka kuran" and vu == {"langue": "dyu", "session": "session-tr-dyu"}


# ── Modèle d'écoute réel (si présent sur le disque) ────────────────────────────
@pytest.mark.skipif(not (dioula_ecoute.DOSSIER / "model.int8.onnx").exists(), reason="modèle Omnilingual absent")
def test_modele_ecoute_silence_et_preuve_sonore():
    e = dioula_ecoute.transcrire_audio(np.zeros(16000, dtype="float32"))
    assert e.texte == "" and e.mots == []
    t = np.arange(16000 * 2) / 16000
    e = dioula_ecoute.transcrire_audio((0.1 * np.sin(2 * np.pi * 220 * t)).astype("float32"))
    assert isinstance(e.texte, str) and 0.0 <= e.certitude <= 1.0
