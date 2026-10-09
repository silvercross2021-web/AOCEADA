"""Agent d'actions (05/10/2026) : un plan entier par demande, contrôlé, exécuté d'un coup par la page, corrigé si la page
s'arrête, appris (raccourcis). Sans Internet : le modèle et la page sont simulés."""
import asyncio
import json

import pytest

from apps.ai_assistant.chatbot import agent_actions, config, live_agent

CARTE = {"version": "v1", "ecrans": [
    {"ecran": "Page principale", "cle": "#vue_chat", "ouvert_par": [], "elements": [
        {"cle": "#btn_options", "role": "bouton", "nom": "Options", "ouvre": "Options"},
        {"cle": "#btn_historique", "role": "bouton", "nom": "Historique", "ouvre": "Historique"},
        {"cle": "#texte", "role": "champ", "nom": "Votre message", "valeur": ""},
        {"cle": "#micro", "role": "bouton", "nom": "Message vocal", "reserve_a_la_personne": "le micro du chat"}]},
    {"ecran": "Options", "cle": "#feuille_options", "ouvert_par": ["#btn_options"], "elements": [
        {"cle": "#genre", "role": "liste", "nom": "Voix", "valeur": "Femme", "options": ["Femme", "Homme"]},
        {"cle": '#theme [data-theme-choix="clair"]', "role": "bouton", "nom": "Clair"}]},
    {"ecran": "Historique", "cle": "#feuille_historique", "ouvert_par": ["#btn_historique"], "elements": [
        {"cle": "#effacer_historique", "role": "bouton", "nom": "Effacer l'historique", "reserve_a_la_personne": "définitif"}]}]}
ETAT = {"ecran_ouvert": None, "reglages": {"voix": "Femme", "theme": "auto"}}
BON = {"etapes": [{"action": "choisir", "cible": "#genre", "valeur": "Homme"},
                  {"action": "cliquer", "cible": '#theme [data-theme-choix="clair"]'}], "dit": "Voix d'homme et thème clair.", "impossible": None}


def test_controle_du_plan_rien_hors_de_la_carte():
    C = agent_actions.controler
    assert C(BON, CARTE) == []
    assert C({"etapes": [{"action": "fermer"}, {"action": "defiler", "cible": "#feuille_options", "sens": "bas"}]}, CARTE) == []
    assert "n'est pas une clé de la carte" in C({"etapes": [{"action": "cliquer", "cible": "#inventee"}]}, CARTE)[0]
    assert "réservé à la personne" in C({"etapes": [{"action": "cliquer", "cible": "#effacer_historique"}]}, CARTE)[0]
    assert "n'est pas une option" in C({"etapes": [{"action": "choisir", "cible": "#genre", "valeur": "Robot"}]}, CARTE)[0]
    assert "n'est pas une liste" in C({"etapes": [{"action": "choisir", "cible": "#btn_options", "valeur": "x"}]}, CARTE)[0]
    assert "n'est pas un champ" in C({"etapes": [{"action": "ecrire", "cible": "#btn_options", "texte": "x"}]}, CARTE)[0]
    assert "action inconnue" in C({"etapes": [{"action": "supprimer", "cible": "#genre"}]}, CARTE)[0]
    assert "trop long" in C({"etapes": [{"action": "fermer"}] * 16}, CARTE)[0]
    assert C("pas un dict", CARTE) and C({"etapes": "x"}, CARTE)


def test_json_du_modele_lu_meme_entoure():
    assert agent_actions._lire_json('```json\n{"etapes": [], "dit": "ok"}\n```') == {"etapes": [], "dit": "ok"}
    assert agent_actions._lire_json('Voici : {"etapes": []} merci') == {"etapes": []}


class FaussePage:
    """La page : sa carte, et l'exécution d'un plan (réussite, ou arrêt à une étape)."""
    def __init__(self, echecs=0):
        self.echecs, self.plans, self.demandes = echecs, [], []

    async def __call__(self, d):
        self.demandes.append(d["nom"])
        if d["nom"] == "carte":
            return {"carte": CARTE, "etat": ETAT}
        self.plans.append(d["args"]["etapes"])
        if self.echecs:
            self.echecs -= 1
            return {"ok": False, "etape": 1, "action": "choisir", "cible": "#genre", "raison": "la valeur n'a pas été prise",
                    "faites": [], "ecran": {**ETAT, "ecran_ouvert": "Options"}}
        return {"ok": True, "faites": [f"{e['action']} {e.get('cible')}" for e in d["args"]["etapes"]], "duree_ms": 900}


def planificateur(*plans):
    appels = []
    def p(objectif, carte, etat, retour):
        appels.append({"objectif": objectif, "retour": retour, "etat": etat})
        return plans[min(len(appels), len(plans)) - 1], {"modele": "faux", "duree_s": 0.1, "cout_dollars": 0.0001}
    p.appels = appels
    return p


@pytest.fixture
def raccourcis(tmp_path):
    return agent_actions.Raccourcis(tmp_path / "raccourcis.json")


def faire(objectif, page, plan, raccourcis):
    return asyncio.run(agent_actions.faire(objectif, page, plan, raccourcis))


def test_un_seul_plan_puis_le_raccourci_appris_sans_modele(raccourcis):
    page, plan = FaussePage(), planificateur(BON)
    r = faire("Mets une voix d'homme et le thème clair.", page, plan, raccourcis)
    assert r["ok"] and r["source"] == "plan" and r["etapes"] == 2 and r["fait"] == "Voix d'homme et thème clair."
    assert len(plan.appels) == 1 and page.demandes == ["carte", "executer_plan"]
    r = faire("mets une voix d’homme, et le thème clair", page, plan, raccourcis)      # même demande, autrement écrite
    assert r["ok"] and r["source"] == "raccourci" and len(plan.appels) == 1          # le modèle n'est pas rappelé


def test_arret_de_la_page_le_plan_est_corrige_avec_la_raison(raccourcis):
    page = FaussePage(echecs=1)
    plan = planificateur(BON, {**BON, "etapes": BON["etapes"][1:]})
    r = faire("Mets une voix d'homme et le thème clair.", page, plan, raccourcis)
    assert r["ok"] and len(plan.appels) == 2 and len(page.plans) == 2
    assert "la valeur n'a pas été prise" in plan.appels[1]["retour"] and plan.appels[1]["etat"]["ecran_ouvert"] == "Options"


def test_plan_hors_carte_refuse_avant_execution_puis_corrige(raccourcis):
    page = FaussePage()
    plan = planificateur({"etapes": [{"action": "cliquer", "cible": "#effacer_historique"}], "dit": "x"}, BON)
    r = faire("Mets une voix d'homme et le thème clair.", page, plan, raccourcis)
    assert r["ok"] and page.plans == [BON["etapes"]]                                 # le plan dangereux n'est jamais joué
    assert "réservé à la personne" in plan.appels[1]["retour"]


def test_impossible_dit_honnetement_et_rien_n_est_fait(raccourcis):
    page = FaussePage()
    plan = planificateur({"etapes": [], "dit": "Effacer l'historique est réservé à la personne.", "impossible": "réservé à la personne"})
    r = faire("Efface tout l'historique.", page, plan, raccourcis)
    assert not r["ok"] and r["impossible"] == "réservé à la personne" and page.plans == []


def test_deja_fait_rien_a_executer(raccourcis):
    page = FaussePage()
    r = faire("Mets le thème clair.", page, planificateur({"etapes": [], "dit": "C'est déjà le thème clair.", "impossible": None}), raccourcis)
    assert r["ok"] and r["etapes"] == 0 and page.plans == []


def test_raccourci_qui_ne_marche_plus_est_oublie_et_refait(raccourcis):
    raccourcis.noter("ouvre les options", "v1", {"etapes": [{"action": "cliquer", "cible": "#btn_options"}], "dit": "x"})
    page, plan = FaussePage(echecs=1), planificateur({"etapes": [{"action": "cliquer", "cible": "#btn_options"}], "dit": "Options ouvertes."})
    r = faire("Ouvre les options", page, plan, raccourcis)
    assert r["ok"] and r["source"] == "plan" and len(plan.appels) == 1
    assert raccourcis.trouver("ouvre les options", "v1")["dit"] == "Options ouvertes."   # remplacé par le plan qui marche


def test_trois_echecs_on_s_arrete_et_on_le_dit(raccourcis):
    page = FaussePage(echecs=10)
    r = faire("Mets une voix d'homme.", page, planificateur(BON), raccourcis)
    assert not r["ok"] and "pas réussi après 2 corrections" in r["erreur"] and len(page.plans) == 3
    assert raccourcis.trouver("Mets une voix d'homme.", "v1") is None


def test_objectif_vide_ou_page_sans_carte(raccourcis):
    assert not faire("  ", FaussePage(), planificateur(BON), raccourcis)["ok"]
    async def sans_carte(d):
        return {"erreur": "La page n'a pas répondu."}
    assert "carte" in faire("x", sans_carte, planificateur(BON), raccourcis)["erreur"]


def test_carte_change_les_raccourcis_ne_s_appliquent_plus(raccourcis):
    raccourcis.noter("ouvre les options", "ancienne", {"etapes": [{"action": "cliquer", "cible": "#vieux"}], "dit": "x"})
    assert raccourcis.trouver("ouvre les options", "v1") is None


class Reponse:
    def __init__(self, code, d):
        self.status_code, self._d, self.text = code, d, json.dumps(d)

    def json(self):
        return self._d


def test_deepseek_flash_sans_reflexion_en_json_puis_secours_qwen(monkeypatch):
    monkeypatch.setitem(config.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    monkeypatch.setenv("OPENROUTER_KEY_AGENT", "cle-or")
    envois = []
    def poster(url, headers, json, timeout):
        envois.append((url, json))
        if "deepseek" in url:
            return Reponse(503, {"error": "occupé"})
        return Reponse(200, {"choices": [{"message": {"content": '{"etapes": [], "dit": "ok"}'}}], "usage": {"cost": 0.0002}})
    plan, infos = agent_actions.planifier("Mets le thème clair.", CARTE, ETAT, poster=poster)
    assert plan == {"etapes": [], "dit": "ok"} and infos["modele"] == "OpenRouter qwen/qwen3.7-flash" and infos["cout_dollars"] == 0.0002
    ds = envois[0][1]
    assert ds["model"] == "deepseek-flash" and ds["thinking"] == {"type": "disabled"} and ds["response_format"] == {"type": "json_object"}
    systeme = ds["messages"][0]["content"]
    assert "#genre" in systeme and "reserve_a_la_personne" in systeme and "OBJECTIF : Mets le thème clair." in ds["messages"][1]["content"]


def test_aucun_modele_qui_repond(monkeypatch):
    monkeypatch.setitem(config.CONFIG, "DEEPSEEK_API_KEY", "cle-ds")
    monkeypatch.delenv("OPENROUTER_KEY_AGENT", raising=False)
    with pytest.raises(RuntimeError):
        agent_actions.demander_modele([], poster=lambda *a, **k: Reponse(500, {}))


# ── Dans l'appel Live : Gemini n'a plus qu'un outil pour agir, « faire » ───────
def test_gemini_agit_par_faire_et_plus_par_des_clics_un_a_un():
    noms = {d.name for d in live_agent.declarations([])}
    assert "faire" in noms and {"lire_ecran", "montrer", "defiler", "afficher_appel", "ecran_entier"} <= noms
    assert not noms & {"cliquer", "ecrire", "choisir", "ouvrir_options", "changer_theme", "changer_langue_reponses"}
    c = live_agent.consigne("auto")
    assert "appelle UNE fois" in c and "faire" in c and "objectif COMPLET" in c


def test_faire_pendant_l_appel(monkeypatch, tmp_path):
    from apps.ai_assistant.tests_chatbot.test_live import FaussePage as PageLive, FausseSession, FauxGemini, appel_outil, lancer, reserves, tour_parle
    monkeypatch.setattr(agent_actions, "RACCOURCIS", agent_actions.Raccourcis(tmp_path / "r.json"))
    monkeypatch.setattr(agent_actions, "planifier", lambda o, c, e, r: (BON, {"modele": "faux", "duree_s": 0.1, "cout_dollars": 0}))

    class Page(PageLive):
        async def send_text(self, t):
            d = json.loads(t)
            if d["type"] == "page" and d["nom"] in ("carte", "executer_plan"):
                self.recu.append(d)
                r = {"carte": CARTE, "etat": ETAT} if d["nom"] == "carte" else {"ok": True, "faites": ["choisir #genre", "cliquer theme"]}
                self.dire({"type": "resultat_page", "id": d["id"], "resultat": r})
                return
            await super().send_text(t)
    page = Page()
    s = FausseSession([appel_outil("faire", {"objectif": "Mets une voix d'homme et le thème clair."})],
                      apres_outil=tour_parle("C'est fait : voix d'homme et thème clair."))
    a, journal = lancer(page, FauxGemini([s]), reserves())
    r = s.reponses_outils[0].response["resultat"]
    assert r["ok"] and r["etapes"] == 2 and r["fait"] == "Voix d'homme et thème clair." and "modeles" not in r
    assert [d["nom"] for d in page.recu if d["type"] == "page"] == ["carte", "executer_plan"]
    assert any(d["type"] == "etat" and d["etat"] == "agit" for d in page.recu)
    assert journal[-1]["actions"][0]["ok"] and journal[-1]["actions"][0]["source"] == "plan"


def test_page_d_avant_la_mise_a_jour_message_clair(raccourcis):
    """Vu le 05/10 (soir) : onglet ouvert avant la mise à jour -> « action inconnue » -> « n'a pas pu aboutir »."""
    async def vieille_page(d):
        return {"erreur": "action inconnue"}
    r = faire("Change le thème.", vieille_page, planificateur(BON), raccourcis)
    assert not r["ok"] and "recharger la page" in r["erreur"]


def test_appel_refuse_si_la_page_n_est_pas_a_jour():
    from apps.ai_assistant.tests_chatbot.test_live import FaussePage as PageLive, FauxGemini, reserves
    page = PageLive()
    page.dire({"type": "debut", "genre": "femme", "langue": "auto", "version": "ancienne"})
    a = live_agent.Appel(page, lambda e: None, connecter=FauxGemini([]), reserves=reserves(), version="nouvelle")
    asyncio.run(asyncio.wait_for(a.servir(), 5))
    err = [d for d in page.recu if d["type"] == "erreur"]
    assert err and err[0]["recharger"] and "rechargez la page" in err[0]["texte"]
    assert live_agent.version_page() and len(live_agent.version_page()) == 12
