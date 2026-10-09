"""Tests de la CHAÎNE ROBUSTE du baoulé (06/10/2026), sans Internet : cerveau IA, interprètes (Google, NiuTrans),
données AOCEDA et voix simulés. Couvre les 4 blocs et ce qui les entoure :
  A. carnet de mots par le sens (« salut » -> « bonjour »), réparation contrôlée par le son, deux interprètes ;
  B. raccourci oui/non, classement dans la liste fermée (format, demande inconnue, réponse hors format -> secours) ;
  C. vérifications (montant non entendu, appareil absent), note de confiance, règle de réponse ;
  D. réponses avec les vraies données (capteurs muets, postpayé, erreur), contre-vérification (nombres perdus), boutons,
     mémoire (liste d'attente, validation), jamais deux fois la même tournure.
"""
import json

import pytest
from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import (baoule_chaine, baoule_comprendre, baoule_decider, baoule_demandes, baoule_lexique, baoule_memoire, baoule_relais, baoule_repondre, conversation, dioula_relais, securite, service_baoule, service_chat, voix)
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur
from apps.ai_assistant.chatbot.baoule_demandes import Phrase


# ── outils de test ─────────────────────────────────────────────────────────────
DONNEES = {
    "credit_et_recharges": {"type_compteur": "prepaye", "credit": {"restant_fcfa": 47673.08, "jours_restants": None},
                            "dernieres_recharges": [{"montant_fcfa": 30000.0, "date": "2026-09-24T03:46:25+00:00"}]},
    "etat_capteurs": {"capteurs": [{"nom": "Climatiseur salon", "etat": "ON", "secondes_depuis_derniere_lecture": 30},
                                   {"nom": "Réfrigérateur", "etat": "OFF", "secondes_depuis_derniere_lecture": 30}]},
    "repartition_appareils": {"periode": {"libelle": "les 30 derniers jours, du ..."}, "appareils": [
        {"nom": "Climatiseur salon", "kwh": 40.5, "pct": 64}, {"nom": "Réfrigérateur", "kwh": 12.0, "pct": 19}]},
    "conso_periode": {"periode": {"libelle": "aujourd'hui, le mardi 6 octobre 2026"}, "kwh_total": 3.4,
                      "cout_estime_fcfa": 312, "periode_precedente": {"kwh_total": 5.0}},
    "historique_mensuel": {"mois": [{"mois_libelle": "Août 2026", "total_fcfa": 54546, "en_cours": False},
                                    {"mois_libelle": "Septembre 2026", "total_fcfa": 52159, "en_cours": False}]},
    "prevision_fin_mois": {"mode": "trop_tot"},
    "alertes": {"nb_non_lues": 1, "alertes": [{"type": "Crédit bas", "message": "Crédit prépayé estimé bas."}]},
}


def lecteur(donnees=None, appels=None):
    d = {**DONNEES, **(donnees or {})}

    def lire(nom, args):
        if appels is not None:
            appels.append((nom, args))
        return d.get(nom, {"erreur": "inconnu"})
    return lire


def ia(*reponses):
    """Cerveau IA simulé : chaque appel renvoie la réponse suivante (dict -> JSON, ou texte brut)."""
    vu = {"n": 0, "dossiers": []}

    def ouvrir(systeme, historique):
        vu["n"] += 1
        vu["dossiers"].append(historique[-1]["texte"])
        r = reponses[min(vu["n"], len(reponses)) - 1]
        return iter([json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r])
    return [("DeepSeek", "ds", ouvrir)], vu


def classement(demande, p=90, certitude="haute", montant=None, appareil=None, periode=None, autres=()):
    return {"hypotheses": [{"demande": demande, "probabilite": p}] + [{"demande": a, "probabilite": 5} for a in autres],
            "details": {"montant": montant, "appareil": appareil, "periode": periode}, "certitude": certitude,
            "reformulation": f"La personne veut : {demande}", "indices": ["test"]}


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "FICHIER", tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(baoule_memoire, "BANQUE", tmp_path / "exemples_baoule.json")
    monkeypatch.setattr(baoule_memoire, "ATTENTE", tmp_path / "attente.json")
    monkeypatch.setattr(baoule_lexique, "MANQUANTS", tmp_path / "manquants.jsonl")
    monkeypatch.setattr(baoule_repondre, "PHRASES_TYPES", tmp_path / "phrases_types.json")
    monkeypatch.setattr(voix, "preparer", lambda *a, **k: [])
    monkeypatch.setattr(voix, "annoncer_baoule", lambda *a, **k: None)
    monkeypatch.setattr(voix, "reveiller_voix_baoule", lambda *a, **k: False)
    monkeypatch.setenv("CHATBOT_BAOULE_CHAINE", "1")
    monkeypatch.delenv("NIUTRANS_API_KEY", raising=False)
    baoule_decider._etats.clear()
    baoule_chaine._variantes.clear()
    securite.remettre_a_zero()
    yield


class FauxBaoule:
    """Traduction simulée : chaque phrase française reçoit un faux texte baoulé (« Ɔ kpa nun sran'n 3 ») ; la
    retraduction rend le français d'origine (ou ce que `retour` en fait)."""
    def __init__(self, retour=None):
        self.fr, self.retour = {}, retour or (lambda fr: fr)

    def vers_bci(self, fr):
        bci = f"Ɔ kpa nun sran'n {len(self.fr) + 1}"
        self.fr[bci] = fr
        return bci

    def vers_fr(self, bci):
        return self.retour(self.fr[bci]) if bci in self.fr else "Comment recharger mon compteur ?"


@pytest.fixture
def interpretes(monkeypatch):
    """Google simulé : baoulé inconnu -> « Comment recharger mon compteur ? » ; aller-retour fidèle."""
    vu = {"vers_bci": [], "bci_vers_fr": []}
    faux = FauxBaoule()

    def traduire(service, sens, texte):
        vu.setdefault(sens, []).append((service, texte))
        if sens == "bci_vers_fr":
            return faux.vers_fr(texte)
        if sens == "vers_bci":
            return faux.vers_bci(texte)
        if sens == "fr_vers_en":
            return {"coucou": "hello"}.get(texte, texte)
        raise AssertionError(sens)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    return vu


def evenements(session, texte, liste, lire=None, **k):
    return list(service_baoule.repondre(session, texte, liste=liste, lire=lire or lecteur(), **k))


def un(evs, type_):
    return next(e for e in evs if e["type"] == type_)


# ── A. carnet de mots par le SENS ──────────────────────────────────────────────
def test_salut_trouve_par_le_sens_comme_bonjour():
    r = baoule_lexique.traduire_mot("salut")
    assert "aɲiho" in r["bci"] and r["chemin"] in ("exact", "sens")
    r = baoule_lexique.traduire_mot("coucou")
    assert r["chemin"] == "sens" and r["via"] == "bonjour" and "aɲiho" in r["bci"]


def test_mot_par_l_anglais_puis_mot_manquant_note():
    r = baoule_lexique.traduire_mot("zxqvbn", vers_anglais=lambda m: "money")
    assert r["chemin"] == "anglais" and "sika" in r["bci"] and r["via"] == "money"
    r = baoule_lexique.traduire_mot("zzyzx", vers_anglais=lambda m: "zzyzx")
    assert r["chemin"] == "absent" and r["bci"] == [] and baoule_lexique.mots_manquants()[-1]["mot"] == "zzyzx"


@pytest.mark.parametrize("texte, attendu", [
    ("Comment dit-on salut en baoulé ?", ("fr", "salut")), ("comment on dit merci en baoulé", ("fr", "merci")),
    ("Que veut dire aɲiho ?", ("bci", "aɲiho")), ("How do you say hello in Baoulé?", ("en", "hello")),
    ("Bonjour, ça va ?", None), ("Combien de crédit il me reste ?", None)])
def test_questions_de_vocabulaire(texte, attendu):
    assert baoule_lexique.question_vocabulaire(texte) == attendu


def test_question_de_vocabulaire_en_francais_le_cerveau_ne_peut_rien_inventer(interpretes):
    vu = {}

    def ouvrir(systeme, historique):
        vu["systeme"] = systeme
        return iter(["En baoulé, on dit « aɲiho »."])
    list(service_chat.repondre("sess-voc-fr1", "Comment dit-on salut en baoulé ?", "fr", None, liste=[("DeepSeek", "ds", ouvrir)]))
    assert "CARNET DE MOTS BAOULÉ" in vu["systeme"] and "aɲiho" in vu["systeme"] and "n'en invente aucun" in vu["systeme"]


def test_sens_d_un_mot_baoule_avec_article():
    assert any("argent" in e["fr"] for e in baoule_lexique.sens("sika'n"))


# ── A. réparation contrôlée par le son ─────────────────────────────────────────
class EcouteSimulee:
    """Écoute dont le « son » préfère certaines écritures (score_sonore simulé)."""
    def __init__(self, mots, scores):
        self.mots = [{"mot": m, "certitude": 0.9, "t0": 2 * i, "t1": 2 * i + 1} for i, m in enumerate(mots)]
        self.scores = scores

    def score_sonore(self, chaine, t0, t1):
        return self.scores.get(chaine, -20.0)


def test_mot_colle_coupe_si_le_son_et_les_vrais_textes_l_acceptent():
    from apps.ai_assistant.chatbot import baoule_texte
    e = EcouteSimulee(["amunlɛman", "sika"], {"amunlɛman": -5.0, "amun lɛman": -5.5})
    texte, faits = baoule_texte.reparer(e)
    assert texte == "amun lɛman sika" and faits[0]["type"] == "coupure"


def test_rien_ne_change_si_le_son_refuse():
    from apps.ai_assistant.chatbot import baoule_texte
    e = EcouteSimulee(["amunlɛman"], {"amunlɛman": -2.0, "amun lɛman": -15.0})
    assert baoule_texte.reparer(e) == ("amunlɛman", [])


def test_mot_connu_et_article_colle_jamais_touches():
    from apps.ai_assistant.chatbot import baoule_texte
    e = EcouteSimulee(["sika", "sran'mun"], {"sran mun": 10.0})
    assert baoule_texte.reparer(e)[0] == "sika sran'mun"


# ── A. deux interprètes ────────────────────────────────────────────────────────
def test_accord_des_interpretes():
    assert baoule_relais.accord("Il me reste combien de crédit ?", "Combien de crédit me reste-t-il ?") >= 0.5
    assert baoule_relais.accord("Le courant est coupé", "Mon frère est malade") < 0.2
    assert baoule_relais.accord("x", None) is None


def test_niutrans_absent_sans_cle_google_seul(interpretes):
    r = baoule_relais.deux_interpretes("Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?")
    assert r["google"] and r["niutrans"] is None and r["accord"] is None


def test_niutrans_avec_cle(interpretes, monkeypatch):
    monkeypatch.setenv("NIUTRANS_API_KEY", "cle-test")
    r = baoule_relais.deux_interpretes("Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?")
    assert r["niutrans"] and r["accord"] == 1.0 and ("niutrans", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?") in interpretes["bci_vers_fr"]


# ── B. raccourci oui / non ─────────────────────────────────────────────────────
@pytest.mark.parametrize("texte, attendu", [("Ɛɛ", "oui"), ("ɛɛn", "oui"), ("Oui", "oui"), ("ɛɛ kpa", "oui"), ("Cɛcɛ", "non"),
                                            ("Tchɛtchɛ", "non"), ("non merci", "non"), ("E ti su", "oui"),
                                            ("e", None), ("Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", None), ("", None)])
def test_oui_non(texte, attendu):
    assert baoule_decider.oui_non(texte) == attendu


# ── B. classement dans la liste fermée ─────────────────────────────────────────
def test_classement_valide_et_trie():
    c = baoule_comprendre.valider({"hypotheses": [{"demande": "economiser", "probabilite": 20},
                                                  {"demande": "credit_restant", "probabilite": "75"}],
                                   "details": {"montant": "5 000", "periode": "hier", "appareil": "null"}, "certitude": "moyenne"})
    assert c.demande == "credit_restant" and c.details == {"montant": 5000, "appareil": None, "periode": "hier"}


def test_demande_hors_liste_refusee_puis_redemandee(interpretes):
    liste, vu = ia({"hypotheses": [{"demande": "acheter_une_voiture", "probabilite": 90}]}, classement("credit_restant"))
    d = baoule_comprendre.preparer_dossier("Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?")
    c = baoule_comprendre.classer(d, liste)
    assert c.demande == "credit_restant" and c.essais == 2 and "invalide" in vu["dossiers"][1]


def test_reponse_hors_format_deux_fois_bascule_sur_l_ancien_chemin(interpretes):
    liste, _ = ia("Je pense que c'est le crédit.", "Toujours pas de JSON.",
                  "INTENTION : crédit restant\nCERTITUDE : moyenne\n\nIl vous reste du crédit.")
    evs = evenements("sess-secours-1", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    fin = un(evs, "fin")
    assert fin["texte"] and un(evs, "bilan")["chaine"]["secours"].startswith("réponse hors format")


def test_dossier_contient_les_indices(interpretes):
    baoule_memoire.banque()
    d = baoule_comprendre.preparer_dossier("Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ ?")
    assert "Interprète 1 (Google)" in d.texte and "Exemple vérifié proche" in d.texte and "credit_restant" in d.texte


# ── C. vérifications, note, règle ──────────────────────────────────────────────
def _dossier(**k):
    return baoule_comprendre.Dossier("", **{"repare": "x y z", "mots": 3, "traductions": {}, **k})


def test_montant_non_entendu_retire():
    c = baoule_comprendre.valider(classement("recharger_montant", montant=50000))
    controles = baoule_decider.verifier(c, _dossier(nombres=[{"texte": "akpi nnun", "valeur": 5000}]))
    assert c.details["montant"] is None and "non entendu" in controles[0]
    c = baoule_comprendre.valider(classement("recharger_montant", montant=5000))
    assert baoule_decider.verifier(c, _dossier(nombres=[{"texte": "akpi nnun", "valeur": 5000}])) == []


def test_appareil_reconnu_ou_absent_du_compte():
    c = baoule_comprendre.valider(classement("conso_appareil", appareil="clim"))
    assert baoule_decider.verifier(c, _dossier(), ["Climatiseur salon"]) == [] and c.details["appareil_compte"] == "Climatiseur salon"
    c = baoule_comprendre.valider(classement("conso_appareil", appareil="voiture"))
    assert "absent" in baoule_decider.verifier(c, _dossier(), ["Climatiseur salon"])[0]


def test_note_de_confiance_et_signaux():
    c = baoule_comprendre.valider(classement("credit_restant", certitude="moyenne"))
    deux = {"google": "a", "niutrans": "b"}
    n = baoule_decider.note_confiance(c, _dossier(traductions={**deux, "accord": 0.8}))
    assert n.niveau == "haute" and n.points == 3
    n = baoule_decider.note_confiance(c, _dossier(traductions={**deux, "accord": 0.1}, certitude_ecoute=0.5))
    assert n.niveau == "basse" and any("divergent" in s for s, _ in n.signaux)
    ex = ({"bci": "a", "demande": "economiser"}, 0.9)
    n = baoule_decider.note_confiance(c, _dossier(traductions={**deux, "accord": 0.8}, exemples=[ex]))
    assert n.points == 2 and any("AUTRE demande" in s for s, _ in n.signaux)
    n = baoule_decider.note_confiance(c, _dossier(traductions={}))
    assert any("aucun interprète" in s for s, _ in n.signaux) and n.niveau == "basse"


@pytest.mark.parametrize("demande, niveau, mode", [
    ("recharger_montant", "haute", "confirmer"), ("eteindre_appareil", "haute", "confirmer"),
    ("credit_restant", "haute", "direct"), ("credit_restant", "moyenne", "verifier"), ("credit_restant", "basse", "choix"),
    ("hors_sujet", "haute", "hors_sujet"), ("saluer", "basse", "direct"), ("autre_question_energie", "haute", "libre")])
def test_regle_de_reponse(demande, niveau, mode):
    c = baoule_comprendre.valider(classement(demande, autres=("economiser",)))
    assert baoule_decider.decider(c, baoule_decider.Note(0, niveau)).mode == mode


# ── D. réponses avec les vraies données ────────────────────────────────────────
def test_credit_arrondi_en_lettres_avec_nombres_a_controler():
    ph = baoule_demandes.CATALOGUE["credit_restant"].contenu({}, lecteur(), 0)
    assert ph[0].fr == "Il vous reste environ quarante-sept mille sept cents francs de crédit." and ph[0].nombres == (47700,)


def test_compteur_postpaye_et_donnees_indisponibles():
    ph = baoule_demandes.CATALOGUE["credit_restant"].contenu({}, lecteur({"credit_et_recharges": {"type_compteur": "postpaye"}}), 0)
    assert "postpayé" in ph[0].fr
    ph = baoule_demandes.CATALOGUE["credit_restant"].contenu({}, lecteur({"credit_et_recharges": {"erreur": "x"}}), 0)
    assert "Je n'arrive pas à lire vos données" in ph[0].fr


def test_capteurs_muets_on_le_dit_au_lieu_de_zero():
    muets = {"etat_capteurs": {"capteurs": [{"nom": "Climatiseur salon", "etat": "ON", "secondes_depuis_derniere_lecture": 6 * 86400}]},
             "conso_periode": {"periode": {"libelle": "aujourd'hui"}, "kwh_total": 0.0, "cout_estime_fcfa": 0}}
    ph = baoule_demandes.CATALOGUE["conso_periode"].contenu({}, lecteur(muets), 0)
    assert "n'envoient plus de mesures depuis six jours" in ph[0].fr
    ph = baoule_demandes.CATALOGUE["courant_revenu"].contenu({}, lecteur(muets), 0)
    assert "ne peux donc pas savoir" in ph[1].fr


def test_toutes_les_demandes_repondent_sans_planter():
    for d in baoule_demandes.CATALOGUE.values():
        if d.contenu:
            ph = d.contenu({"periode": "hier", "appareil": "frigo", "montant": 5000}, lecteur(), 0)
            assert ph and all(isinstance(p, Phrase) and p.fr.strip() for p in ph), d.id
        if d.confirmer:
            assert d.confirmer({"montant": 5000, "appareil": "Climatiseur salon"}).fr.endswith("?")
            assert d.apres_oui({"montant": 5000}, lecteur())


def test_jamais_deux_fois_la_meme_tournure():
    a = baoule_chaine._contenu("saluer", {}, lecteur(), "sess-var")
    b = baoule_chaine._contenu("saluer", {}, lecteur(), "sess-var")
    assert [p.fr for p in a] != [p.fr for p in b]


# ── D. contre-vérification de la traduction ────────────────────────────────────
def test_traduction_controlee_nombre_garde(interpretes):
    r = baoule_repondre.traduire([Phrase("Il vous reste environ quarante-sept mille sept cents francs.", (47700,))])[0]
    assert r["controle"] == "verifiee" and r["bci"].startswith("Ɔ kpa nun")


def test_nombre_perdu_puis_rattrape_en_chiffres(monkeypatch):
    faux = FauxBaoule(lambda fr: fr if any(c.isdigit() for c in fr) else "Il vous reste un peu de crédit.")  # lettres perdues
    monkeypatch.setattr(dioula_relais, "traduire",
                        lambda s, sens, t: faux.vers_bci(t) if sens == "vers_bci" else faux.vers_fr(t))
    r = baoule_repondre.traduire([Phrase("Il vous reste environ cinq mille francs.", (5000,))])[0]
    assert r["controle"] == "corrigee" and "5 000" in faux.fr[r["bci"]]


def test_nombre_perdu_deux_fois_phrase_douteuse(monkeypatch):
    faux = FauxBaoule(lambda fr: "Rien du tout.")
    monkeypatch.setattr(dioula_relais, "traduire",
                        lambda s, sens, t: faux.vers_bci(t) if sens == "vers_bci" else faux.vers_fr(t))
    r = baoule_repondre.traduire([Phrase("Il vous reste environ cinq mille francs.", (5000,))])[0]
    assert r["controle"] == "douteuse" and r["manques"] == ["5000"]


def test_nombre_garde_mais_sens_perdu_phrase_douteuse(monkeypatch):
    """Vu le 06/10/2026 : « il vous reste 48 200 francs de crédit » retraduit « la société possède 48 200 actions »."""
    faux = FauxBaoule(lambda fr: "La société possède environ 47 700 actions en circulation.")
    monkeypatch.setattr(dioula_relais, "traduire",
                        lambda s, sens, t: faux.vers_bci(t) if sens == "vers_bci" else faux.vers_fr(t))
    ph = baoule_demandes.CATALOGUE["credit_restant"].contenu({}, lecteur(), 0)[0]
    r = baoule_repondre.traduire([ph])[0]
    assert r["controle"] == "douteuse" and "credit" in r["manques"]


def test_retraduction_trop_lente_phrase_non_verifiee(monkeypatch):
    import time as _t
    faux = FauxBaoule()

    def traduire(s, sens, t):
        if sens == "vers_bci":
            return faux.vers_bci(t)
        _t.sleep(1.0)
        return faux.vers_fr(t)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    monkeypatch.setattr(baoule_repondre, "RETOUR_MAX_S", 0.2)
    t0 = _t.time()
    r = baoule_repondre.traduire([Phrase("Il vous reste environ cinq mille francs.", (5000,))])[0]
    assert r["controle"] == "non_verifiee" and _t.time() - t0 < 0.9


def test_phrases_rendues_dans_l_ordre_des_qu_elles_sont_pretes(monkeypatch):
    import time as _t
    faux = FauxBaoule()

    def traduire(s, sens, t):
        if sens == "vers_bci" and t.startswith("Lente"):
            _t.sleep(0.5)
        return faux.vers_bci(t) if sens == "vers_bci" else faux.vers_fr(t)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)
    t0, vus = _t.time(), []
    for r in baoule_repondre.traduire_flux([Phrase("Rapide une."), Phrase("Lente deux."), Phrase("Rapide trois.")]):
        vus.append((r["fr"], round(_t.time() - t0, 1)))
    assert [v[0] for v in vus] == ["Rapide une.", "Lente deux.", "Rapide trois."] and vus[0][1] < 0.3


def test_phrase_type_relue_utilisee_telle_quelle(interpretes):
    baoule_repondre.PHRASES_TYPES.write_text(json.dumps({"phrases": [
        {"fr": "Avec plaisir.", "bci": "Ɔ yo min fɛ.", "relue": True}]}, ensure_ascii=False), encoding="utf-8")
    r = baoule_repondre.traduire([Phrase("Avec plaisir.")])[0]
    assert r == {"fr": "Avec plaisir.", "bci": "Ɔ yo min fɛ.", "controle": "relue", "retour": None, "manques": [], "service": "relue"}
    assert interpretes["vers_bci"] == []


def test_traducteur_en_panne_phrase_non_traduite(monkeypatch):
    def panne(service, sens, texte):
        raise dioula_relais.RelaisIndisponible("google en panne")
    monkeypatch.setattr(dioula_relais, "traduire", panne)
    r = baoule_repondre.traduire([Phrase("Bonjour.")])[0]
    assert r["controle"] == "non_traduite" and r["bci"] == "Bonjour."


# ── La chaîne entière ──────────────────────────────────────────────────────────
def test_chaine_directe_credit(interpretes):
    liste, vu = ia(classement("credit_restant"))
    evs = evenements("sess-ch-1", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    types = [e["type"] for e in evs]
    assert types[0] == "langue" and "intention" in types and types[-2:] == ["fin", "bilan"] and "boutons" not in types
    fin = un(evs, "fin")
    assert "quarante-sept mille sept cents" in fin["francais"] and fin["mode"] == "direct" and fin["langue_voix"] == "bci"
    assert conversation.voix_autorisee("sess-ch-1", voix.texte_pour_voix(fin["texte"]))


def test_recharge_confirmee_par_oui_puis_liste_d_attente(interpretes):
    liste, _ = ia(classement("recharger_montant", montant=5000))
    evs = evenements("sess-ch-2", "N kunndɛ kɛ ń fá sika akpi nnun", liste)
    assert un(evs, "boutons")["oui_non"] and "cinq mille" in un(evs, "fin")["francais"]
    evs = evenements("sess-ch-2", "Ɛɛ", liste)                      # « oui » dit en baoulé : le code le reconnaît seul
    fin = un(evs, "fin")
    assert fin["mode"] == "execute" and "Achetez cinq mille francs" in fin["francais"]
    assert baoule_memoire.attente()[0]["demande"] == "recharger_montant"


def test_action_annulee_par_non_et_choix_proposes(interpretes):
    liste, _ = ia(classement("eteindre_appareil", appareil="climatiseur"))
    evenements("sess-ch-3", "Amun nunnun klimatizɛ'n", liste)
    evs = evenements("sess-ch-3", "Non", liste, action={"type": "non"})
    assert un(evs, "fin")["mode"] == "annule" and un(evs, "boutons")["choix"] and baoule_memoire.attente() == []


def test_note_basse_reponse_courte_et_boutons_puis_clic(interpretes):
    liste, _ = ia(classement("credit_restant", p=40, certitude="basse", autres=("facture_chere",)))
    evs = evenements("sess-ch-4", "ka", liste)
    b = un(evs, "boutons")
    assert un(evs, "fin")["mode"] == "choix" and b["choix"][0]["demande"] == "facture_chere"
    evs = evenements("sess-ch-4", "Pourquoi c'est cher", liste, action={"type": "choix", "demande": "facture_chere"})
    assert un(evs, "fin")["demande"] == "facture_chere" and baoule_memoire.attente()[0]["origine"] == "choix"


def test_les_boutons_menent_toujours_a_une_reponse_precise():
    c = baoule_comprendre.valider(classement("hors_sujet", autres=("autre_question_energie", "facture_mois")))
    alts = baoule_decider.alternatives(c)
    assert alts == ["facture_mois", "credit_restant"]                  # 2e choix complété par une demande courante
    c = baoule_comprendre.valider(classement("hors_sujet", autres=("saluer", "autre_question_energie")))
    assert not {"autre_question_energie", "saluer", "hors_sujet"} & set(baoule_decider.alternatives(c))


def test_verification_non_puis_choix(interpretes):
    liste, _ = ia(classement("economiser", certitude="moyenne"))
    evs = evenements("sess-ch-5", "Sran kun yo ninnge kpa", liste)          # phrase absente de la banque d'exemples
    assert un(evs, "fin")["mode"] == "verifier" and un(evs, "boutons")["oui_non"]
    evs = evenements("sess-ch-5", "Cɛcɛ", liste)
    assert un(evs, "fin")["mode"] == "corrige" and un(evs, "boutons")["choix"]


def test_question_en_francais_reponse_baoule_sans_traduction_aller(interpretes):
    liste, vu = ia(classement("appareil_gourmand"))
    evs = evenements("sess-ch-6", "Qu'est-ce qui consomme le plus chez moi ?", liste, langue_question="fr")
    assert "FRANÇAIS" in vu["dossiers"][0]
    assert all(t.startswith("Ɔ kpa nun") for _, t in interpretes["bci_vers_fr"])     # seulement les retraductions de contrôle
    assert "climatiseur du salon" in un(evs, "fin")["francais"]


def test_question_libre_repondue_par_le_cerveau(interpretes):
    liste, _ = ia(classement("autre_question_energie"), "Le disjoncteur protège la maison. Il coupe le courant en cas de danger.")
    fin = un(evenements("sess-ch-7", "Disjonctɛ'n ti n'zu ?", liste), "fin")
    assert fin["mode"] == "libre" and "disjoncteur" in fin["francais"]


def test_menu_baoule_passe_par_la_chaine_et_bouton_garde_le_baoule(interpretes):
    liste, _ = ia(classement("credit_restant", p=40, certitude="basse"))
    evs = list(service_chat.repondre("sess-ch-8", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", "bci", None, liste=liste))
    assert un(evs, "fin")["fournisseur"] == "chaîne robuste"
    evs = list(service_chat.repondre("sess-ch-8", "Mon crédit", "auto", None, liste=liste,
                                     action={"type": "choix", "demande": "credit_restant"}))
    assert un(evs, "langue")["code"] == "bci" and un(evs, "fin")["demande"] == "credit_restant"


# ── Erreurs imprévues (vu le 06/10/2026 : « Réponse interrompue » sans trace) ───
def test_erreur_imprevue_avant_la_reponse_l_ancien_chemin_prend_le_relais(interpretes, monkeypatch, tmp_path):
    from apps.ai_assistant.chatbot import erreurs
    monkeypatch.setattr(erreurs, "FICHIER", tmp_path / "erreurs.log")
    monkeypatch.setattr(baoule_chaine, "_comprendre", lambda *a, **k: 1 / 0)
    liste, _ = ia("INTENTION : crédit restant\nCERTITUDE : moyenne\n\nIl vous reste du crédit.")
    evs = evenements("sess-err-1", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    assert un(evs, "fin")["texte"] and "secours" in un(evs, "bilan")["chaine"]
    assert "ZeroDivisionError" in erreurs.FICHIER.read_text(encoding="utf-8")


def test_erreur_imprevue_apres_une_phrase_vrai_message_d_erreur(interpretes, monkeypatch, tmp_path):
    from apps.ai_assistant.chatbot import erreurs
    monkeypatch.setattr(erreurs, "FICHIER", tmp_path / "erreurs.log")

    def casse(phrases):
        yield baoule_repondre.traduire_une(phrases[0])
        raise RuntimeError("panne au milieu")
    monkeypatch.setattr(baoule_repondre, "traduire_flux", casse)
    liste, _ = ia(classement("credit_restant"))
    evs = evenements("sess-err-2", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste)
    assert [e["type"] for e in evs][-1] == "erreur" and "Réessayez" in evs[-1]["texte"]


def test_serveur_ne_coupe_jamais_un_flux_en_silence(monkeypatch, tmp_path):
    from apps.ai_assistant.chatbot import erreurs
    monkeypatch.setattr(erreurs, "FICHIER", tmp_path / "erreurs.log")

    def boum(*a, **k):
        yield {"type": "langue", "code": "fr", "source": "x", "confiance": 1}
        raise ValueError("imprévu")
    monkeypatch.setattr(service_chat, "repondre", boum)
    r = TestClient(serveur.app).post("/api/message", json={"session": "sess-err-3", "texte": "bonjour"})
    derniers = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    assert derniers[-1]["type"] == "erreur" and "ValueError" in erreurs.FICHIER.read_text(encoding="utf-8")


# ── Mémoire et serveur ─────────────────────────────────────────────────────────
def test_memoire_valider_rejeter():
    n = len(baoule_memoire.banque())
    a = baoule_memoire.ajouter_attente("Klɛ nɲɛ", "credit_restant", "oui")
    assert baoule_memoire.ajouter_attente("Klɛ nɲɛ", "credit_restant", "oui") == a          # pas de doublon
    b = baoule_memoire.ajouter_attente("Kpa kpa", "economiser", "choix")
    assert baoule_memoire.valider(a) and len(baoule_memoire.banque()) == n + 1
    assert baoule_memoire.rejeter(b) and baoule_memoire.attente() == []
    assert baoule_memoire.proches("Klɛ nɲɛ yɛ ɔ ka min lɛ")[0][0]["demande"] == "credit_restant"


def test_api_boutons_et_exemples(interpretes, monkeypatch):
    client = TestClient(serveur.app)
    r = client.post("/api/message", json={"session": "sess-api-ch1", "texte": "x", "action": {"type": "pirater"}})
    assert r.status_code == 200                                            # action inconnue : ignorée (message normal)
    a = baoule_memoire.ajouter_attente("Klɛ nɲɛ", "credit_restant", "oui")
    # la banque d'exemples est réservée à l'administrateur d'AOCEDA (au laboratoire : à ce PC, audit du 09/10/2026) : un
    # client ne la lit ni ne la modifie (ce sont des phrases dites par d'autres personnes)
    assert client.get("/api/baoule/exemples").status_code == 403
    assert client.post("/api/baoule/exemples/valider", json={"id": a}).status_code == 403
    assert client.post("/api/baoule/exemples/rejeter", json={"id": a}).status_code == 403
    tunnel = TestClient(serveur.app, headers={"cf-connecting-ip": "41.66.18.7"})   # même derrière un tunnel
    assert tunnel.get("/api/baoule/exemples").status_code == 403
    pc = TestClient(serveur.app, administrateur=True)
    assert pc.get("/api/baoule/exemples").json()["attente"][0]["id"] == a
    assert pc.post("/api/baoule/exemples/valider", json={"id": a, "demande": "inconnue"}).status_code == 400
    assert pc.post("/api/baoule/exemples/valider", json={"id": a}).json()["ok"]


# ── Audit du 09/10/2026 : corrections de la chaîne ─────────────────────────────────────────────────────────────────
def test_une_nouvelle_question_efface_la_confirmation_en_attente(interpretes):
    """I2 : « recharger 5 000 F » -> confirmation demandée ; autre question (réponse libre, sûre) ; plus tard « ɛɛ » ->
    avant, la RECHARGE était exécutée (et la phrase ajoutée aux exemples)."""
    liste, _ = ia(classement("recharger_montant", montant=5000), classement("autre_question_energie"),
                  "Le compteur mesure ce que vous consommez.", classement("oui_non_seul"))
    evenements("sess-au-1", "N kunndɛ kɛ ń fá sika akpi nnun", liste)
    assert baoule_decider.en_attente("sess-au-1")["type"] == "confirmation"
    fin = un(evenements("sess-au-1", "Mɛtɛri'n ti n'zu ?", liste), "fin")
    assert fin["mode"] == "libre" and baoule_decider.en_attente("sess-au-1") is None
    fin = un(evenements("sess-au-1", "Ɛɛ", liste), "fin")
    assert fin["mode"] != "execute" and "Achetez" not in fin["francais"] and baoule_memoire.attente() == []


def test_un_choix_non_propose_est_repondu_mais_n_entre_pas_dans_les_exemples(interpretes):
    """I3 : un bouton « choix » fabriqué (demande jamais proposée) ne doit pas remplir la liste d'attente."""
    liste, _ = ia(classement("credit_restant", p=40, certitude="basse", autres=("facture_chere",)))
    b = un(evenements("sess-au-2", "ka", liste), "boutons")
    assert "alertes" not in [c["demande"] for c in b["choix"]]
    evs = evenements("sess-au-2", "Mes alertes", liste, action={"type": "choix", "demande": "alertes"})
    assert un(evs, "fin")["demande"] == "alertes" and baoule_memoire.attente() == []


def test_question_posee_en_francais_jamais_enregistree_comme_phrase_baoule(interpretes):
    """I3 : « Je veux recharger cinq mille francs. » (menu Baoulé, question en français) + Oui -> avant, enregistrée
    comme phrase BAOULÉ dans la liste d'attente."""
    liste, _ = ia(classement("recharger_montant", montant=5000))
    evenements("sess-au-3", "Je veux recharger cinq mille francs.", liste, langue_question="fr")
    fin = un(evenements("sess-au-3", "Oui", liste, action={"type": "oui"}), "fin")
    assert fin["mode"] == "execute" and baoule_memoire.attente() == []


def test_refus_d_un_ordre_puis_choix_pas_un_exemple_mais_une_correction_oui(interpretes):
    liste, _ = ia(classement("eteindre_appareil", appareil="climatiseur"))
    evenements("sess-au-4", "Amun nunnun klimatizɛ'n", liste)
    choix = un(evenements("sess-au-4", "Non", liste, action={"type": "non"}), "boutons")["choix"][0]["demande"]
    evenements("sess-au-4", "x", liste, action={"type": "choix", "demande": choix})
    assert baoule_memoire.attente() == []                                 # refus d'un ordre : la personne a pu changer d'avis
    liste, _ = ia(classement("economiser", certitude="moyenne"))
    evenements("sess-au-5", "Sran kun yo ninnge kpa", liste)
    choix = un(evenements("sess-au-5", "Cɛcɛ", liste), "boutons")["choix"][0]["demande"]    # « Pardon, je me suis trompé »
    evenements("sess-au-5", "x", liste, action={"type": "choix", "demande": choix})
    assert [(e["bci"], e["demande"]) for e in baoule_memoire.attente()] == [("Sran kun yo ninnge kpa", choix)]


def test_voix_baoule_fabriquee_d_office_seulement_si_elle_sera_lue(interpretes, monkeypatch):
    """I4 : chaque réponse baoulé faisait fabriquer sa voix sur le GPU payant, même si personne ne l'écoutait."""
    annonces = []
    monkeypatch.setattr(voix, "annoncer_baoule", lambda t: annonces.append(t))
    liste, _ = ia(classement("credit_restant"), classement("credit_restant"))
    evenements("sess-au-6", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste, voix_auto=False)
    assert annonces == []
    fin = un(evenements("sess-au-6", "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?", liste, voix_auto=True), "fin")
    assert annonces == [fin["texte"]]
    from apps.ai_assistant.chatbot import fournisseurs                                    # la page envoie voix_auto : le serveur le transmet
    monkeypatch.setattr(fournisseurs, "candidats", lambda: ia(classement("credit_restant"))[0])
    for voix_auto, attendu in ((False, 1), (True, 2)):
        r = TestClient(serveur.app).post("/api/message", json={"session": "sess-au-7", "texte": "Klɛ nɲɛ yɛ ɔ ka min lɛ ɔ?",
                                                               "langue": "bci", "voix_auto": voix_auto})
        assert r.status_code == 200 and '"type": "fin"' in r.text and len(annonces) == attendu
