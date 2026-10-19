"""Salutation de l'heure au début d'une conversation (09/10/2026, demande du client) : la 1re réponse commence par la
salutation du moment, dans la langue de la réponse, et plus jamais ensuite (sauf si la personne salue : on lui répond).
Formules vérifiées le 09/10/2026 (voir chatbot/salutations.py) :
  dioula : « I ni sɔgɔma » (4-12 h), « I ni tile » (12-15 h), « I ni wula » (15-19 h), « I ni su » (19-4 h) ;
           en réponse « Nse, i ni ... » (voix de femme) ou « Nba, i ni ... » (voix d'homme) ;
  baoulé : en premier « Aɲiho » (4-11 h), « Manti » (11-17 h), « Anun o » (17-4 h) ;
           en réponse « Arɛ o », « Aanti o », « Awossi'n o ».
Sans Internet (DeepSeek, traducteurs, Gemini simulés).
"""
import json
from datetime import datetime

import pytest

from apps.ai_assistant.chatbot import (baoule_memoire, baoule_repondre, conversation, dioula_relais, live_agent, salutations, securite, service_baoule, service_chat, service_dioula, voix)

VINGT_HEURES = datetime(2026, 10, 9, 20, 0)


def heure(h, minute=30):
    return datetime(2026, 10, 9, h, minute)


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    monkeypatch.setattr(voix, "annoncer_baoule", lambda *a, **k: None)
    monkeypatch.setattr(voix, "reveiller_voix_baoule", lambda *a, **k: False)
    monkeypatch.setattr(baoule_memoire, "BANQUE", tmp_path / "exemples_baoule.json")
    monkeypatch.setattr(baoule_memoire, "ATTENTE", tmp_path / "attente.json")
    monkeypatch.setattr(baoule_repondre, "PHRASES_TYPES", tmp_path / "phrases_types.json")
    monkeypatch.setattr(salutations, "maintenant", lambda: VINGT_HEURES)          # il est 20 h
    monkeypatch.setenv("CHATBOT_BAOULE_CHAINE", "1")
    monkeypatch.delenv("NIUTRANS_API_KEY", raising=False)
    securite.remettre_a_zero()


def systemes():
    """Faux DeepSeek qui garde chaque consigne reçue."""
    vu = []

    def ouvrir(systeme, historique):
        vu.append(systeme)
        return iter(["Réglez le climatiseur sur vingt-six degrés."])
    return [("DeepSeek", "ds", ouvrir)], vu


# ── les moments de la journée, par langue ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("h,attendu", [(3, "nuit"), (4, "matin"), (11, "matin"), (12, "apres_midi"), (17, "apres_midi"),
                                       (18, "soir"), (21, "soir"), (22, "nuit"), (0, "nuit")])
def test_moments_francais(h, attendu):
    assert salutations.moment(heure(h)) == attendu


@pytest.mark.parametrize("h,dioula,baoule", [(3, "su", "soir"), (4, "sɔgɔma", "matin"), (10, "sɔgɔma", "matin"),
                                             (11, "sɔgɔma", "midi"), (12, "tile", "midi"), (14, "tile", "midi"),
                                             (15, "wula", "midi"), (16, "wula", "midi"), (17, "wula", "soir"),
                                             (18, "wula", "soir"), (19, "su", "soir"), (23, "su", "soir"), (0, "su", "soir")])
def test_moments_dioula_et_baoule(h, dioula, baoule):
    """Dioula : cours Ankataa (tile jusqu'à 15 h, wula jusqu'à la nuit) ; baoulé : N'Zi 2024 (3 moments, soir dès 17 h)."""
    assert salutations.moment_local("dyu", heure(h)) == dioula and salutations.moment_local("bci", heure(h)) == baoule


def test_formules_selon_l_heure_et_selon_qui_salue_en_premier():
    s = salutations
    assert s.francais(heure(9)) == "Bonjour" and s.francais(heure(15)) == "Bonjour"
    assert s.francais(heure(19)) == "Bonsoir" and s.francais(heure(2)) == "Bonsoir"
    # dioula : l'assistant salue en premier ; s'il répond à une salutation : « Nse » (voix de femme) / « Nba » (homme)
    assert s.locale("dyu", heure(8)) == ("I ni sɔgɔma.", "Bonjour.")
    assert s.locale("dyu", heure(13)) == ("I ni tile.", "Bonjour.")
    assert s.locale("dyu", heure(16)) == ("I ni wula.", "Bonsoir.")      # « I ni wula » = bonsoir (Google, Djelia)
    assert s.locale("dyu", heure(23)) == ("I ni su.", "Bonsoir.")
    assert s.locale("dyu", heure(23), reponse=True) == ("Nse, i ni su.", "Bonsoir.")
    assert s.locale("dyu", heure(8), reponse=True, genre="homme") == ("Nba, i ni sɔgɔma.", "Bonjour.")
    # baoulé : « Aɲiho » est le salut du MATIN seulement (plus jamais l'après-midi) ; le soir commence à 17 h
    assert s.locale("bci", heure(8)) == ("Aɲiho.", "Bonjour.") and s.locale("bci", heure(8), reponse=True) == ("Arɛ o.", "Bonjour.")
    assert s.locale("bci", heure(14)) == ("Manti.", "Bonjour.") and s.locale("bci", heure(14), reponse=True) == ("Aanti o.", "Bonjour.")
    assert s.locale("bci", heure(17)) == ("Anun o.", "Bonsoir.")
    # « Awossi'n o » (le « Bonsoir » de Google) est la RÉPONSE du soir, jamais la salutation dite en premier
    assert s.locale("bci", heure(20)) == ("Anun o.", "Bonsoir.") and s.locale("bci", heure(20), reponse=True) == ("Awossi'n o.", "Bonsoir.")
    assert s.locale("fr") is None


@pytest.mark.parametrize("code,texte,attendu", [
    ("dyu", "I ni wula", True), ("dyu", "i ni sɔgɔma, n ka kuran banna", True), ("dyu", "Aw ni su", True),
    ("dyu", "ini sogoma", True), ("dyu", "Bonsoir", True), ("dyu", "N ka kuran juru banna", False),
    ("dyu", "I ni ce", False), ("dyu", "A ka di", False), ("dyu", "n ka su kɔnɔ kuran tɛ", False),
    ("bci", "Aɲiho", True), ("bci", "Awossi'n o", True), ("bci", "Anun o", True), ("bci", "Manti", True),
    ("bci", "Aanti o", True), ("bci", "Arɛ o", True), ("bci", "Aɲiho, Kouassi, a su kɔ nin?", True),
    ("bci", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", False), ("bci", "E ti su", False), ("bci", "ɔti kpa ko wa nie na jua niu nan", False),
    ("bci", "Ahou'nti kpa? ?Kuran nɲɛ yɛ n fa di junman ɔn?", False)])
def test_la_personne_salue_t_elle(code, texte, attendu):
    assert salutations.est_salutation(code, texte) is attendu


@pytest.mark.parametrize("code,texte,moment", [
    ("dyu", "I ni su", "su"), ("dyu", "ini sogoma", "sɔgɔma"), ("dyu", "Aw ni wula", "wula"), ("dyu", "I ni tile", "tile"),
    ("dyu", "Bonsoir", ""), ("dyu", "A ka di", None),
    ("bci", "Aɲiho", "matin"), ("bci", "Arɛ o", "matin"), ("bci", "Manti", "midi"), ("bci", "Aanti o", "midi"),
    ("bci", "Anun o", "soir"), ("bci", "Awossi'n o", "soir"), ("bci", "Bonsoir", ""), ("bci", "E ti su", None)])
def test_moment_de_la_salutation_recue(code, texte, moment):
    assert salutations.salutation_recue(code, texte) == moment


def test_la_reponse_va_avec_la_salutation_recue_pas_avec_l_heure():
    """Vu en vrai le 09/10 à 4 h 27 : « Anun o » (bonsoir) recevait « Arɛ o » (réponse du MATIN). La réponse va avec la
    salutation reçue : « Anun o » -> « Awossi'n o » ; « I ni su » -> « Nse, i ni su »."""
    s = salutations
    assert s.locale("bci", heure(4, 27), reponse=True, moment_recu="soir") == ("Awossi'n o.", "Bonsoir.")
    assert s.locale("bci", heure(4, 27), reponse=True, moment_recu="") == ("Arɛ o.", "Bonjour.")      # « Bonjour » : l'heure
    assert s.locale("dyu", heure(4, 27), reponse=True, moment_recu="su") == ("Nse, i ni su.", "Bonsoir.")
    assert s.locale("bci", heure(4, 27), moment_recu="soir") == ("Aɲiho.", "Bonjour.")    # l'assistant salue en premier : l'heure
    # loin de l'heure (plus de 2 h) : « Aɲiho » à 20 h est un simple « bonjour » -> réponse du soir
    assert s.locale("bci", heure(20), reponse=True, moment_recu="matin") == ("Awossi'n o.", "Bonsoir.")
    assert s.locale("bci", heure(18), reponse=True, moment_recu="midi") == ("Aanti o.", "Bonjour.")    # 1 h après : on suit
    assert s.locale("dyu", heure(13), reponse=True, moment_recu="su") == ("Nse, i ni tile.", "Bonjour.")
    assert s.locale("dyu", heure(5), reponse=True, moment_recu="su") == ("Nse, i ni su.", "Bonsoir.")


@pytest.mark.parametrize("texte,attendu", [("Bonsoir ! Votre crédit est fini.", "Votre crédit est fini."), ("Bonsoir.", ""),
                                           ("Bonjour, je suis l'assistant AOCEDA.", "Je suis l'assistant AOCEDA."),
                                           ("Bonne soirée, à bientôt.", "À bientôt."),
                                           ("Bonjour à vous.", ""), ("Bonsoir à vous ! Le compteur est vide.", "Le compteur est vide."),
                                           ("Bonsoir madame, votre crédit tient.", "Votre crédit tient."),
                                           ("Bon après-midi ! Votre crédit tient.", "Votre crédit tient."),
                                           ("Bonnes nouvelles : votre crédit tient.", "Bonnes nouvelles : votre crédit tient."),
                                           ("Votre bonjour m'a fait plaisir.", "Votre bonjour m'a fait plaisir.")])
def test_retirer_une_salutation_deja_dite(texte, attendu):
    assert salutations.retirer_salutation(texte).strip() == attendu


# ── chat (langues que le cerveau IA parle) : il salue à la 1re réponse, plus ensuite ────────────────────────────────
def test_premiere_reponse_salue_selon_l_heure_puis_plus_jamais():
    liste, vu = systemes()
    list(service_chat.repondre("sess-salut-1", "Comment réduire ma facture ?", liste=liste))
    list(service_chat.repondre("sess-salut-1", "Et pour le réfrigérateur ?", liste=liste))
    assert "DÉBUT DE CONVERSATION" in vu[0] and "« Bonsoir »" in vu[0] and "Good evening" in vu[0] and "20 h 00" in vu[0]
    assert "DÉJÀ COMMENCÉE" not in vu[0]
    assert "DÉJÀ COMMENCÉE" in vu[1] and "DÉBUT DE CONVERSATION" not in vu[1]


def test_francais_on_rend_sa_salutation_a_la_personne_si_elle_est_proche_de_l_heure():
    s = salutations
    assert s.francais_reponse("Bonsoir, combien me reste-t-il de crédit ?", heure(4, 35)) == "Bonsoir"   # vu le 09/10
    assert s.francais_reponse("Combien me reste-t-il ?", heure(4, 35)) == "Bonjour"
    assert s.francais_reponse("Bonjour", heure(19)) == "Bonjour"                     # 1 h 30 après 18 h : on suit
    assert s.francais_reponse("Bonjour", heure(23)) == "Bonsoir"                     # trop loin : l'heure
    debut = s.consigne_debut(heure(4, 35), "Bonsoir, combien me reste-t-il de crédit ?")
    assert "« Bonsoir »" in debut and "Good evening" in debut
    assert s.consigne_suite("Et pour le réfrigérateur ?") == s.CONSIGNE_SUITE
    assert "rends-lui" in s.consigne_suite("Bonsoir !", heure(21)) and "« Bonsoir »" in s.consigne_suite("Bonsoir !", heure(21))


def test_en_pleine_conversation_la_personne_salue_on_lui_rend_sa_salutation():
    liste, vu = systemes()
    list(service_chat.repondre("sess-salut-4", "Comment réduire ma facture ?", liste=liste))
    list(service_chat.repondre("sess-salut-4", "Bonsoir ! Et le ventilateur ?", liste=liste))
    assert "rends-lui sa salutation" in vu[1] and "« Bonsoir »" in vu[1] and "DÉBUT DE CONVERSATION" not in vu[1]


def test_nouvelle_conversation_la_salutation_revient():
    liste, vu = systemes()
    list(service_chat.repondre("sess-salut-2", "Bonjour", liste=liste))
    conversation.effacer("sess-salut-2")                                # « Nouvelle conversation »
    list(service_chat.repondre("sess-salut-2", "Combien consomme un ventilateur ?", liste=liste))
    assert "DÉBUT DE CONVERSATION" in vu[0] and "DÉBUT DE CONVERSATION" in vu[1]


def test_reponse_ratee_la_question_suivante_est_toujours_la_premiere():
    """Une 1re question restée sans réponse (erreur, Stop) est retirée : la suivante reste la 1re de la conversation."""
    def panne(systeme, historique):
        raise RuntimeError("DeepSeek en panne")
    list(service_chat.repondre("sess-salut-3", "Bonjour ?", liste=[("DeepSeek", "ds", panne)]))
    liste, vu = systemes()
    list(service_chat.repondre("sess-salut-3", "Comment réduire ma facture ?", liste=liste))
    assert "DÉBUT DE CONVERSATION" in vu[0]


# ── dioula : salutation dans la langue, mise par le code, jamais deux fois ──────────────────────────────────────────
@pytest.fixture
def dioula(monkeypatch):
    """Traduction simulée : une vraie phrase dioula par phrase française (le contrôle refuse du français resté tel quel)."""
    monkeypatch.setattr(dioula_relais, "traduire", lambda service, sens, texte:
                        "mon crédit est fini" if sens == "vers_fr" else f"A ka di {len(texte)} ɲɛ.")


def reponse_dioula(session, texte, *morceaux, genre="femme"):
    vu = {}

    def ouvrir(systeme, historique):
        vu["dossier"] = historique[-1]["texte"]
        return iter(morceaux)
    evs = list(service_dioula.repondre(session, texte, genre=genre, liste=[("DeepSeek", "ds", ouvrir)]))
    return evs, vu


def morceaux_de(evs):
    return [e["texte"] for e in evs if e["type"] == "morceau"]


def test_dioula_premiere_reponse_commence_par_i_ni_su_et_le_modele_ne_salue_pas_deux_fois(dioula):
    evs, vu = reponse_dioula("sess-salut-dy1", "n ka kuran juru banna",
                             "INTENTION : crédit fini\nCERTITUDE : haute\n\nBonsoir ! Votre crédit est fini. Achetez du crédit.")
    fin = next(e for e in evs if e["type"] == "fin")
    assert morceaux_de(evs)[0] == "I ni su."                            # 20 h : avant même la réponse du cerveau IA
    assert fin["francais"] == "Bonsoir. Votre crédit est fini. Achetez du crédit."
    assert fin["texte"].startswith("I ni su. A ka di 22 ɲɛ.")           # « Votre crédit est fini. » traduit
    assert "Ne salue PAS toi-même" in vu["dossier"]
    assert voix.decouper(fin["texte"])[0] == "I ni su."                # la salutation est le 1er morceau lu à voix haute
    evs, vu = reponse_dioula("sess-salut-dy1", "a ka di", "INTENTION : merci\nCERTITUDE : haute\n\nAvec plaisir.")
    assert morceaux_de(evs)[0] == "A ka di 13 ɲɛ."                      # 2e réponse : pas de salutation
    assert "Ne salue PAS" not in vu["dossier"]


def test_dioula_la_personne_salue_on_lui_repond_nse_ou_nba(dioula):
    evs, _ = reponse_dioula("sess-salut-dy3", "I ni su", "INTENTION : salutation\nCERTITUDE : haute\n\nBonsoir ! Que voulez-vous savoir ?")
    assert morceaux_de(evs)[0] == "Nse, i ni su."                       # voix de femme
    assert next(e for e in evs if e["type"] == "fin")["francais"] == "Bonsoir. Que voulez-vous savoir ?"
    evs, _ = reponse_dioula("sess-salut-dy4", "I ni su, n ka kuran juru banna", "INTENTION : x\nCERTITUDE : haute\n\nAchetez du crédit.",
                            genre="homme")
    assert morceaux_de(evs)[0] == "Nba, i ni su."                       # voix d'homme
    # en pleine conversation, une nouvelle salutation de la personne reçoit sa réponse (une seule fois)
    evs, vu = reponse_dioula("sess-salut-dy4", "Aw ni su", "INTENTION : salutation\nCERTITUDE : haute\n\nBonsoir, je vous écoute.",
                             genre="homme")
    fin = next(e for e in evs if e["type"] == "fin")
    assert morceaux_de(evs)[0] == "Nba, i ni su." and fin["francais"] == "Bonsoir. Je vous écoute."


def test_dioula_reponse_reprise_apres_une_panne_garde_la_salutation_en_tete(dioula):
    from apps.ai_assistant.chatbot import fournisseurs

    def coupe(systeme, historique):
        yield "INTENTION : x\nCERTITUDE : haute\n\nVotre"
        raise fournisseurs.Echec("connexion perdue", avant_premier_mot=False)
    evs = list(service_dioula.repondre("sess-salut-dy2", "n ka kuran juru banna", liste=[
        ("DeepSeek", "ds1", coupe), ("DeepSeek", "ds2", lambda s, h: iter(["INTENTION : x\nCERTITUDE : haute\n\nAchetez du crédit."]))]))
    types = [(e["type"], e.get("texte")) for e in evs if e["type"] in ("morceau", "recommencer")]
    i = [t for t, _ in types].index("recommencer")
    assert types[i + 1] == ("morceau", "I ni su.")                      # après « recommencer », la salutation revient
    assert next(e for e in evs if e["type"] == "fin")["francais"] == "Bonsoir. Achetez du crédit."


# ── baoulé (chaîne robuste) : « Anun o » en premier, « Awossi'n o » en réponse ─────────────────────────────────────
def lecteur(nom, args):
    return {"credit_et_recharges": {"type_compteur": "prepaye", "credit": {"restant_fcfa": 47673}, "dernieres_recharges": []},
            "etat_capteurs": {"capteurs": []}}.get(nom, {"erreur": "inconnu"})


def ia(*reponses):
    n = {"i": 0}

    def ouvrir(systeme, historique):
        n["i"] += 1
        r = reponses[min(n["i"], len(reponses)) - 1]
        return iter([json.dumps(r) if isinstance(r, dict) else r])
    return [("DeepSeek", "ds", ouvrir)]


def classement(demande):
    return {"hypotheses": [{"demande": demande, "probabilite": 90}], "details": {}, "certitude": "haute",
            "reformulation": demande, "indices": ["test"]}


@pytest.fixture
def interpretes(monkeypatch):
    monkeypatch.setattr(dioula_relais, "traduire", lambda service, sens, texte:
                        f"Ɔ kpa {len(texte)}" if sens == "vers_bci" else "Combien de crédit me reste-t-il ?")


def baoule(session, texte, liste):
    return list(service_baoule.repondre(session, texte, liste=liste, lire=lecteur))


def test_baoule_premiere_reponse_anun_o_puis_plus_de_salutation(interpretes):
    liste = ia(classement("credit_restant"))
    evs = baoule("sess-salut-b1", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    fin = next(e for e in evs if e["type"] == "fin")
    assert morceaux_de(evs)[0] == "Anun o."                             # l'assistant salue en premier, le soir
    assert fin["francais"].startswith("Bonsoir. Il vous reste") and fin["texte"].startswith("Anun o. ")
    assert fin["controles"][0] == "formule"
    evs = baoule("sess-salut-b1", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    assert not next(e for e in evs if e["type"] == "fin")["francais"].startswith("Bonsoir")


@pytest.mark.parametrize("h,attendu", [(9, "Aɲiho."), (14, "Manti."), (20, "Anun o.")])
def test_baoule_salutation_du_moment(interpretes, monkeypatch, h, attendu):
    monkeypatch.setattr(salutations, "maintenant", lambda: heure(h))
    assert morceaux_de(baoule(f"sess-salut-bh{h}", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", ia(classement("credit_restant"))))[0] == attendu


def test_baoule_la_personne_salue_on_lui_repond_awossi_n_o_jamais_deux_fois(interpretes):
    liste = ia(classement("credit_restant"), classement("saluer"))
    baoule("sess-salut-b2", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    evs = baoule("sess-salut-b2", "Anun o", liste)
    fin = next(e for e in evs if e["type"] == "fin")
    assert morceaux_de(evs)[0] == "Awossi'n o."                         # réponse au « Anun o » de la personne
    assert fin["francais"].startswith("Bonsoir. Je suis") and fin["francais"].count("Bonsoir") == 1
    assert "Bonjour" not in fin["francais"]                             # plus de « Bonjour » le soir


def test_baoule_premier_message_qui_salue_reponse_directe(interpretes):
    evs = baoule("sess-salut-b5", "Awossi'n o", ia(classement("saluer")))
    assert morceaux_de(evs)[0] == "Awossi'n o."


def test_a_4_h_27_anun_o_recoit_awossi_n_o(interpretes, monkeypatch):
    monkeypatch.setattr(salutations, "maintenant", lambda: heure(4, 27))             # déjà le « matin » pour le serveur
    assert morceaux_de(baoule("sess-salut-b6", "Anun o", ia(classement("saluer"))))[0] == "Awossi'n o."
    assert morceaux_de(baoule("sess-salut-b7", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", ia(classement("credit_restant"))))[0] == "Aɲiho."


def test_a_4_h_27_i_ni_su_recoit_nse_i_ni_su(dioula, monkeypatch):
    monkeypatch.setattr(salutations, "maintenant", lambda: heure(4, 27))
    evs, _ = reponse_dioula("sess-salut-dy5", "I ni su", "INTENTION : salutation\nCERTITUDE : haute\n\nJe vous écoute.")
    assert morceaux_de(evs)[0] == "Nse, i ni su."
    evs, _ = reponse_dioula("sess-salut-dy6", "N ka kuran juru banna", "INTENTION : x\nCERTITUDE : haute\n\nAchetez du crédit.")
    assert morceaux_de(evs)[0] == "I ni sɔgɔma."                       # l'assistant salue en premier : l'heure


def test_baoule_reponse_libre_la_salutation_du_cerveau_ia_est_retiree(interpretes):
    liste = ia(classement("autre_question_energie"), "Bonsoir ! Le disjoncteur protège la maison.")
    fin = next(e for e in baoule("sess-salut-b3", "Disjonctɛ'n ti n'zu ?", liste) if e["type"] == "fin")
    assert fin["francais"].startswith("Bonsoir. Le disjoncteur protège la maison.")
    assert fin["francais"].count("Bonsoir") == 1


def test_baoule_traducteurs_en_panne_salutation_en_francais_voix_francaise(monkeypatch):
    def panne(service, sens, texte):
        raise dioula_relais.RelaisIndisponible("google : hors ligne")
    monkeypatch.setattr(dioula_relais, "traduire", panne)
    from apps.ai_assistant.chatbot import baoule_relais
    monkeypatch.setattr(baoule_relais, "DELAI_TOTAL_RETOUR_S", 1.0)
    evs = baoule("sess-salut-b4", "Combien de crédit me reste-t-il ?", ia(classement("credit_restant")))
    fin = next(e for e in evs if e["type"] == "fin")
    assert fin["langue_voix"] == "fr" and fin["controles"][0] == "formule"           # tout est resté en français
    assert fin["texte"] == fin["francais"] and fin["texte"].startswith("Bonsoir. Il vous reste")   # jamais « Anun o » en voix française


# ── appel Live : 1re réponse de l'appel seulement ───────────────────────────────────────────────────────────────────
def test_consigne_live_salue_au_debut_de_l_appel_seulement():
    debut = live_agent.consigne("auto", saluer=True, maintenant=VINGT_HEURES)
    suite = live_agent.consigne("auto", saluer=False, maintenant=VINGT_HEURES)
    assert "TOUTE PREMIÈRE réponse de cet appel" in debut and "« Bonsoir »" in debut
    assert "déjà commencé" in suite and "TOUTE PREMIÈRE" not in suite


def test_appel_live_salue_a_la_premiere_session_pas_apres_une_reconnexion():
    from apps.ai_assistant.tests_chatbot.test_live import FausseSession, FauxGemini, FaussePage, lancer, reserves, tour_parle
    page = FaussePage()
    s1 = FausseSession([tour_parle("Bonsoir ! Je vous écoute.", jetons=live_agent.SEUIL_MEMOIRE + 1)])        # mémoire pleine : nouvelle session
    s2 = FausseSession([tour_parle("Votre consommation...")])
    gemini = FauxGemini([s1, s2])
    lancer(page, gemini, reserves(), fin_apres=3)
    consignes = [c["system_instruction"] for _, _, c in gemini.appels]
    assert "TOUTE PREMIÈRE réponse de cet appel" in consignes[0]
    assert len(consignes) >= 2 and "déjà commencé" in consignes[1] and "TOUTE PREMIÈRE" not in consignes[1]


# ── même conversation reprise plus tard (18/10/2026, demande du client) ──────────────────────────────────────────────
def dernier_message_a(session, quand):
    """La conversation a eu son dernier message à `quand` (au lieu de maintenant)."""
    with conversation._base() as c:
        c.execute("UPDATE conversation SET dernier_message = ? WHERE session = ?", (quand.timestamp(), session))


@pytest.mark.parametrize("avant, maintenant, code, attendu", [
    (heure(9), heure(15), None, True),                  # matin puis après-midi, 6 h plus tard : on salue de nouveau
    (heure(11), heure(12, 40), None, False),            # autre moment, mais moins de 2 h : non
    (heure(13), heure(17, 30), None, False),            # 4 h 30 de pause, mais toujours l'après-midi : non
    (heure(9), datetime(2026, 10, 10, 9, 30), None, True),   # le lendemain matin : un autre jour
    (heure(12, 30), heure(15, 30), "dyu", True),        # dioula : « tile » puis « wula »
    (heure(12, 30), heure(15, 30), "bci", False),       # baoulé : toujours « midi » (11 h - 17 h)
    (None, heure(15), None, False),                     # conversation neuve : c'est la règle du 1er message
])
def test_regle_de_la_reprise(avant, maintenant, code, attendu):
    assert salutations.resaluer(avant and avant.timestamp(), code, maintenant) is attendu


def test_conversation_reprise_le_soir_resaluee_pas_20_minutes_apres():
    liste, vu = systemes()
    list(service_chat.repondre("sess-reprise-1", "Comment réduire ma facture ?", liste=liste))
    dernier_message_a("sess-reprise-1", heure(19, 40))                 # 20 min plus tôt : pas de nouvelle salutation
    list(service_chat.repondre("sess-reprise-1", "Et le ventilateur ?", liste=liste))
    assert "DÉJÀ COMMENCÉE" in vu[1] and "REPRISE" not in vu[1]
    dernier_message_a("sess-reprise-1", heure(10))                     # dernier message ce matin, il est 20 h
    list(service_chat.repondre("sess-reprise-1", "Et le réfrigérateur ?", liste=liste))
    assert "REPRISE DE CONVERSATION" in vu[2] and "« Bonsoir »" in vu[2]


def test_un_reglage_de_langue_ne_compte_pas_comme_un_message():
    liste, vu = systemes()
    list(service_chat.repondre("sess-reprise-2", "Comment réduire ma facture ?", liste=liste))
    dernier_message_a("sess-reprise-2", heure(10))
    conversation.noter_langue("sess-reprise-2", "fr")                  # « maj » bouge, pas le dernier message
    assert salutations.resaluer(conversation.dernier_message("sess-reprise-2"))


def test_dioula_conversation_reprise_resaluee_dans_la_langue(dioula):
    reponse_dioula("sess-reprise-dy", "n ka kuran juru banna", "INTENTION : crédit\nCERTITUDE : haute\n\nVotre crédit est fini.")
    dernier_message_a("sess-reprise-dy", heure(9))
    evs, _ = reponse_dioula("sess-reprise-dy", "a ka di", "INTENTION : merci\nCERTITUDE : haute\n\nAvec plaisir.")
    assert morceaux_de(evs)[0] == "I ni su."


def test_baoule_conversation_reprise_resaluee_dans_la_langue(interpretes):
    liste = ia(classement("credit_restant"), classement("credit_restant"))
    baoule("sess-reprise-b", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    dernier_message_a("sess-reprise-b", heure(9))
    assert morceaux_de(baoule("sess-reprise-b", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste))[0] == "Anun o."


# ── garde-fou du début de réponse (18/10/2026, vu en vrai avec DeepSeek) ─────────────────────────────────────────────
def flux(*evs):
    texte = "".join(e["texte"] for e in evs if e["type"] == "morceau")
    return iter(list(evs) + [{"type": "fin", "texte": texte.strip()}])


def m(t):
    return {"type": "morceau", "texte": t}


def page(evs):
    sortie = list(evs)
    return "".join(e["texte"] for e in sortie if e["type"] == "morceau"), sortie[-1]["texte"], sortie


def test_phrase_d_attente_avant_l_outil_retiree():
    vu, fin, evs = page(service_chat.debut_controle(flux(m("Let me check that for you."), {"type": "outil", "nom": "x", "label": "x"},
                                                         m("This week you used 1.6 kilowatt-hours."))))
    assert vu == fin == "This week you used 1.6 kilowatt-hours." and any(e["type"] == "outil" for e in evs)


def test_salutation_ajoutee_seulement_si_elle_manque():
    vu, fin, _ = page(service_chat.debut_controle(flux(m("Cette semaine, "), m("vous avez consommé 1,6 kWh.")), "Bonjour !"))
    assert vu == fin == "Bonjour ! Cette semaine, vous avez consommé 1,6 kWh."
    vu, fin, _ = page(service_chat.debut_controle(flux(m("Bonjour ! Cette semaine, vous avez consommé 1,6 kWh.")), "Bonjour !"))
    assert fin == "Bonjour ! Cette semaine, vous avez consommé 1,6 kWh."                 # jamais deux fois
    vu, fin, _ = page(service_chat.debut_controle(flux(m("Good afternoon! You used 1.6 kWh.")), "Good afternoon!"))
    assert fin == "Good afternoon! You used 1.6 kWh."
    vu, fin, _ = page(service_chat.debut_controle(flux(m("Une longue réponse " * 10)), None))   # rien à garantir : intacte
    assert fin == ("Une longue réponse " * 10).strip() and vu == "Une longue réponse " * 10


def test_formule_due_selon_la_langue_et_l_heure(monkeypatch):
    monkeypatch.setattr(salutations, "maintenant", lambda: heure(15))
    assert service_chat.formule_due("fr", "Combien ?") == "Bonjour !" and service_chat.formule_due("en", "x") == "Good afternoon!"
    assert service_chat.formule_due("es", "x") is None                                  # autres langues : la consigne


def test_reprise_francaise_la_salutation_est_garantie_meme_si_le_modele_l_oublie():
    liste, vu = systemes()                                              # le faux DeepSeek ne salue jamais
    list(service_chat.repondre("sess-reprise-3", "Comment réduire ma facture ?", "fr", liste=liste))
    dernier_message_a("sess-reprise-3", heure(10))
    evs = list(service_chat.repondre("sess-reprise-3", "Et le ventilateur ?", "fr", liste=liste))
    assert next(e for e in evs if e["type"] == "fin")["texte"].startswith("Bonsoir ! Réglez")


def test_apres_la_salutation_la_voix_enchaine_vite():
    """19/10/2026 (vu en vrai) : « Bonsoir ! » se lisait tout de suite, puis tout le reste de la réponse formait UN long
    morceau et la voix se taisait plusieurs secondes. La 2e phrase est maintenant lue seule, elle aussi."""
    texte = ("Bonsoir ! Sur les 30 derniers jours, vous avez consommé 1,61 kilowattheure. "
             "La prise pèse 84 % du total. La lampe pèse 16 %.")
    m = voix.decouper(texte)
    assert m[0] == "Bonsoir !"
    assert m[1:3] == ["Sur les 30 derniers jours,", "vous avez consommé 1,61 kilowattheure."]   # longue : coupée
    assert m[-1].endswith("La lampe pèse 16 %.")
    assert voix.decouper("Votre crédit est de 5 000 francs CFA aujourd'hui. Il durera dix jours. Rechargez avant.")[1] \
        == "Il durera dix jours. Rechargez avant."             # 1re phrase longue : comme avant
