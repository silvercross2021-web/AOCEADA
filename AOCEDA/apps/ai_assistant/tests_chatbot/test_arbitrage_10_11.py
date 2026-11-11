"""Tests PROPOSÉS par l'arbitrage du 10/11/2026 (à placer dans apps/ai_assistant/tests_chatbot/). Chacun échoue sur le dépôt actuel et
réussit avec le correctif correspondant (voir correctifs_proposes.md)."""
import json
import time

import pytest
import requests
from google.genai import types

from apps.ai_assistant.chatbot import fournisseurs, live_agent, voix_wolof

from .test_confirmation_vocale import COUPER, ApresOutil, confirmations, vous_dit
from .test_live import FaussePage, FauxGemini, PontCoupure, lancer, msg, reserves, tour_parle


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    monkeypatch.setattr(live_agent, "CONFIRMATION_VOCALE_S", 0.0)


# ── F1 (B1) : un « oui » entendu PENDANT que l'agent parle est peut-être son écho ───────────────────
def sortie(texte):
    return msg(server_content=types.LiveServerContent(
        output_transcription=types.Transcription(text=texte),
        model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=b"\x00\x01" * 50, mime_type="audio/pcm"))])))


def entree(texte):
    return msg(server_content=types.LiveServerContent(input_transcription=types.Transcription(text=texte)))


FIN = msg(server_content=types.LiveServerContent(turn_complete=True))
DEBUT = "J'ai bien compris : vous voulez que j'éteigne la prise. Vous pouvez appuyer sur Oui ou Non, "
SUITE = "ou simplement dire oui ou non, je vous écoute."


def jouer(*tours):
    page = FaussePage()
    lancer(page, FauxGemini([ApresOutil(COUPER, list(tours))]), reserves(), pont=PontCoupure())
    return confirmations(page)


def test_B1_un_oui_transcrit_au_milieu_de_la_phrase_de_l_agent_n_est_pas_une_reponse():
    assert jouer([sortie(DEBUT), entree("oui"), sortie(SUITE), FIN], tour_parle("Fin.")) == []


def test_B1_un_oui_transcrit_quand_l_agent_commence_par_oui_n_est_pas_une_reponse():
    assert jouer([sortie("Oui, j'ai bien compris : vous voulez que j'éteigne la prise. "), entree("oui"), sortie(SUITE), FIN],
                 tour_parle("Fin.")) == []


def test_B1_le_vrai_oui_apres_la_fin_du_tour_de_l_agent_reste_accepte():
    assert jouer([sortie(DEBUT + SUITE), FIN], vous_dit("oui"), tour_parle("Fin.")) == ["oui"]


def test_B1_un_non_pendant_que_l_agent_parle_annule_toujours():
    assert jouer([sortie("J'ai bien compris : vous voulez que j'éteigne la prise. Donnez votre réponse, "), entree("non"), sortie(SUITE), FIN],
                 tour_parle("Fin.")) == ["non"]


def test_B1_echo_pendant_la_parole_puis_vrai_oui_apres():
    assert jouer([sortie(DEBUT), entree("oui"), sortie(SUITE), FIN], vous_dit("oui"), tour_parle("Fin.")) == ["oui"]


# ── F4 (1e) : jamais de balisage d'appel d'outil dans la réponse ────────────────────────────────────
class Rep:
    status_code, text = 200, ""

    def __init__(self, lignes):
        self.lignes = lignes

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self, decode_unicode=True):
        return iter(self.lignes)


def sse(contenu=None, appel=None):
    delta = {"content": contenu} if contenu is not None else {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "x", "arguments": "{}"}}]}
    return "data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False)


class Donnees:
    specs = [{"type": "function", "function": {"name": "x", "description": "", "parameters": {"type": "object", "properties": {}}}}]

    def executer(self, nom, args):
        return {"ok": True}, "x"


DSML = "<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name=\"x\">\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>"


def test_F4_le_balisage_dsml_du_dernier_tour_n_est_jamais_affiche(monkeypatch):
    from apps.ai_assistant.chatbot import donnees_client
    monkeypatch.setattr(donnees_client, "courantes", lambda: Donnees())
    corps_vus = []

    def faux_post(url, **kw):
        corps_vus.append(kw["json"])
        if "tools" in kw["json"]:
            return Rep([sse(appel=True), "data: [DONE]"])
        return Rep([sse("Bonsoir ! "), sse(DSML), "data: [DONE]"])
    monkeypatch.setattr(fournisseurs.requests, "post", faux_post)
    texte = "".join(x for x in fournisseurs.flux_deepseek("systeme", [{"role": "user", "texte": "question"}]) if isinstance(x, str))
    assert "DSML" not in texte and "<｜" not in texte
    assert "Bonsoir" in texte
    assert "tools" not in corps_vus[-1] and "sans appeler d'outil" in corps_vus[-1]["messages"][-1]["content"]


def test_F4_balisage_seul_donne_une_phrase_honnete(monkeypatch):
    from apps.ai_assistant.chatbot import donnees_client
    monkeypatch.setattr(donnees_client, "courantes", lambda: Donnees())
    monkeypatch.setattr(fournisseurs.requests, "post",
                        lambda url, **kw: Rep([sse(appel=True), "data: [DONE]"]) if "tools" in kw["json"] else Rep([sse(DSML), "data: [DONE]"]))
    texte = "".join(x for x in fournisseurs.flux_deepseek("s", [{"role": "user", "texte": "q"}]) if isinstance(x, str))
    assert "DSML" not in texte and "reformuler" in texte


# ── F5 (1g, 1d) : voix wolof ────────────────────────────────────────────────────────────────────────
def _wav(octet):
    import io
    import wave
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes([octet, 1]) * 2205)
    return b.getvalue()


class ReponseGpu:
    status_code, text = 200, ""

    def __init__(self, octets):
        self.octets = octets

    def json(self):
        import base64
        return {"result": {"wav_b64": base64.b64encode(self.octets).decode()}}


def test_1g_la_voix_homme_n_est_pas_servie_par_le_cache_de_la_voix_femme(monkeypatch):
    appels = []
    monkeypatch.setattr(voix_wolof, "configure", lambda: True)
    monkeypatch.setattr(voix_wolof, "_post_cerebrium", lambda url, **kw: (appels.append(kw["json"]["voix"]),
                                                                           ReponseGpu(_wav(10 if kw["json"]["voix"] == "femme" else 200)))[1])
    t = "Texte de controle genre wolof " + str(time.time())
    femme, homme = voix_wolof.fabriquer(t, "femme"), voix_wolof.fabriquer(t, "homme")
    assert appels == ["femme", "homme"] and femme != homme
    assert voix_wolof.fabriquer(t, "homme") == homme and appels == ["femme", "homme"]          # le cache sert chaque voix à sa place


def test_1d_apres_un_delai_de_demarrage_du_gpu_on_peut_reessayer_vite(monkeypatch):
    monkeypatch.setattr(voix_wolof, "configure", lambda: True)
    monkeypatch.setattr(voix_wolof, "ATTENTE_APRES_DELAI_S", 0.0)
    essais = []

    def post(url, **kw):
        essais.append(1)
        if len(essais) == 1:
            raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=240)")
        return ReponseGpu(_wav(7))
    monkeypatch.setattr(voix_wolof, "_post_cerebrium", post)
    t = "Phrase de demarrage a froid " + str(time.time())
    etat, tache = voix_wolof.demander_reponse(t)
    with pytest.raises(Exception):
        tache.result(timeout=5)                         # 1re demande : le GPU démarre, délai dépassé
    time.sleep(0.05)
    etat2, tache2 = voix_wolof.demander_reponse(t)       # le GPU est prêt : la 2e demande part tout de suite (avant : « échec récent » 120 s)
    assert etat2 != "echec"
    assert tache2.result(timeout=5)[0]


def test_1d_le_delai_de_lecture_couvre_un_demarrage_a_froid():
    assert voix_wolof.DELAI_S >= 210


# ── F3 (1b, B3, B4, B2) : contrôle des nombres ─────────────────────────────────────────────────────
def test_B3_milliers_puis_decimale_et_ordinaux():
    from apps.ai_assistant.chatbot import dioula_relais as D
    assert D.nombres_ecrits("1 250,5 kWh") == D.nombres_ecrits("1250.5 kWh") == ["1250.5"]
    assert D.nombres_ecrits("0,50 FCFA") == D.nombres_ecrits("0.5 FCFA") == ["0.5"]
    assert D.nombres_ecrits("12 500 F") == D.nombres_ecrits("12,500 F") == D.nombres_ecrits("12.500 F") == ["12500"]
    assert D.nombres_ecrits("3,5 kW") == ["3.5"] and D.nombres_ecrits("le 03/11/2026") == ["03", "11", "2026"]
    assert D.nombres_ecrits("Le 1er novembre à 18 h 30") == ["18", "30"]                      # « 1er » n'est pas un « 1 » à retrouver
    assert D.nombres_perdus("Vous avez 1 250,5 kWh.", "I ye kWh 1250.5 ye.") == []
    assert D.nombres_perdus("Vous avez 1 250,5 kWh.", "I ye kWh 1250 ye.") != []             # un vrai nombre perdu reste détecté


def test_1b_decimale_ecrite_en_lettres_doit_survivre_en_chiffres():
    from apps.ai_assistant.chatbot import dioula_relais as D
    assert D.chiffres_en_lettres_perdus("La puissance est de deux virgule huit kilowatts.", "A fanga ye kilowati 8 ye.")           # le 2 est perdu
    assert D.chiffres_en_lettres_perdus("Vous avez consommé trois virgule quatre kilowattheures.", "I ye kilowati-lɛrɛ naani saba dun.")   # 4 3, sans virgule
    assert D.chiffres_en_lettres_perdus("Vous avez consommé trois virgule quatre kilowattheures.", "I ye kilowati 3,4 ye.") == []
    assert D.chiffres_en_lettres_perdus("Il vous reste cinq mille francs.", "I ka wari ye kelen ye.") == []                         # entier en lettres : invérifiable, accepté
    assert D.chiffres_en_lettres_perdus("Vous avez trois virgule quatre kilowattheures.", "Ñetti poñ ñeenti kilowatt.", [3, 4], ("poñ",)) == []
    assert D.chiffres_en_lettres_perdus("Vous avez 3,4 kilowattheures.", "x") == []                                                # des chiffres : nombres_perdus s'en charge
    assert D.chiffres_en_lettres_perdus("Le climatiseur représente soixante-dix pour cent.", "Klimatiseer bi mooy juróom ñatti fukki pursaa.", [70]) == []
    assert D.chiffres_en_lettres_perdus("Le pic est à vingt-trois heures.", "Konsommasioŋ bi mooy 11 waxtu ci bëccëg.", []) == ["23"]   # 11 pour 23 : refusé


def test_B4_un_et_une_articles_ne_sont_pas_le_nombre_un():
    from apps.ai_assistant.chatbot import baoule_direct, nombres_fr
    assert nombres_fr.nombres_sans_article("C'est une bonne nouvelle : votre consommation baisse.") == set()
    assert nombres_fr.nombres_sans_article("Vous avez un capteur en ligne.") == set()
    assert nombres_fr.nombres_sans_article("Votre consommation est stable depuis un mois.") == {1}
    assert nombres_fr.nombres_sans_article("Il reste vingt et un jours.") == {21}
    assert nombres_fr.nombres_sans_article("Un virgule six kilowattheure.") == {1, 6}
    assert nombres_fr.nombres_sans_article("Le climatiseur représente soixante-dix pour cent de la consommation.") == {70}      # « pour cent » n'est pas 100
    assert baoule_direct.phrase("C'est une bonne nouvelle : votre consommation baisse.").nombres == ()
    assert baoule_direct.phrase("Il vous reste 47 700 francs.").nombres == (47700,)


def test_B2_une_valeur_infinie_n_est_pas_un_nombre_de_facture():
    from apps.ai_assistant.chatbot import facture
    for v in ("inf", "Infinity", "1e999", "9" * 400, "nan", -5, None, "abc"):
        assert facture._nombre(v) is None, v
    assert facture._nombre("1 250,5") == 1250.5 and facture._nombre(15140) == 15140.0
    assert json.dumps(facture.nettoyer({"est_une_facture_electricite": True, "kwh_factures": "1e999", "montant_total_fcfa": 15140}))


# ── Heures du soir (arbitrage du 10/11/2026, D7) ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texte,attendu", [
    ("Ne rallumez pas le climatiseur avant 18 h.", "Ne rallumez pas le climatiseur avant 6 heures du soir."),
    ("Le pic est à 23 heures, avec 22 kWh.", "Le pic est à 11 heures de la nuit, avec 22 kWh."),
    ("Vers 19 h 30, la consommation monte.", "Vers 7 heures 30 du soir, la consommation monte."),
    ("Entre 17 h et 19 h, évitez le fer.", "Entre 5 heures de l'après-midi et 7 heures du soir, évitez le fer."),
    ("De 10 h à 14 h, tout est calme.", "De 10 h à 2 heures de l'après-midi, tout est calme."),
    ("Il est 13 h.", "Il est 1 heure de l'après-midi."),
    ("Le pic est à vingt-trois heures.", "Le pic est à onze heures de la nuit."),
    ("Évitez le climatiseur après vingt heures trente.", "Évitez le climatiseur après huit heures trente du soir."),
    ("Depuis vingt et une heures il est éteint.", "Depuis neuf heures du soir il est éteint."),
])
def test_heures_du_soir_sont_ecrites_sur_12_h_avec_le_moment_de_la_journee(texte, attendu):
    from apps.ai_assistant.chatbot.heures_fr import heures_sur_12h
    assert heures_sur_12h(texte) == attendu


@pytest.mark.parametrize("texte", ["Le climatiseur a tourné pendant 20 h.", "Sur 24 h, vous avez consommé 12 kWh.", "Toutes les 18 h le cycle repart.",
                                   "La climatisation a 20 h de fonctionnement.", "À 9 h et à 11 h c'est bas.", "Vous avez consommé 18 kWh.",
                                   "Un cycle de 24 h."])
def test_une_duree_ou_une_heure_du_matin_n_est_jamais_reecrite(texte):
    from apps.ai_assistant.chatbot.heures_fr import heures_sur_12h
    assert heures_sur_12h(texte) == texte


def _faux_traducteur(monkeypatch, aller, retour, appels):
    """Remplace la traduction : `aller` (texte -> traduction), `retour` (traduction -> français) ; `appels` garde ce qui a été envoyé."""
    from apps.ai_assistant.chatbot import dioula_relais

    def traduire(service, sens, texte):
        appels.append((service, sens, texte))
        return aller(texte) if sens in ("vers_dyu", "vers_wo", "vers_bci") else retour(texte)
    monkeypatch.setattr(dioula_relais, "traduire", traduire)


def test_dioula_une_heure_du_soir_est_traduite_au_lieu_de_rester_en_francais(monkeypatch):
    """Avant : « avant 18 h » -> traduction « avant 6 h » -> « 18 » perdu -> la phrase restait en français (9 phrases sur 9)."""
    from apps.ai_assistant.chatbot import dioula_relais
    envoyes = []
    _faux_traducteur(monkeypatch, lambda t: "I kana fiɲɛdilan wuli tugun wulada fɛ 6h waati ɲɛ.", lambda t: "Ne rallumez pas le climatiseur avant 18 heures.", envoyes)
    texte, service = dioula_relais.vers_dioula("Ne rallumez pas le climatiseur avant 18 h.", ordre=("djelia",))
    assert "6h" in texte
    assert envoyes[0][2] == "Ne rallumez pas le climatiseur avant 6 heures du soir."       # le traducteur a reçu l'heure sur 12 h + le soir


def test_wolof_une_heure_du_soir_est_traduite_au_lieu_de_rester_en_francais(monkeypatch):
    from apps.ai_assistant.chatbot import wolof_relais
    envoyes = []
    _faux_traducteur(monkeypatch, lambda t: "Bul taalaat klimaa bi balaa 6 waxtu ci ngoon.", lambda t: "Ne rallumez pas le climatiseur avant 18 heures.", envoyes)
    assert "6 waxtu" in wolof_relais.vers_wolof("Ne rallumez pas le climatiseur avant 18 h.")
    assert envoyes[0][2] == "Ne rallumez pas le climatiseur avant 6 heures du soir."


def test_baoule_une_heure_du_soir_accepte_la_retraduction_en_12_h_ou_en_24_h():
    """La retraduction du baoulé redit souvent « 23h » pour « 11 heures de la nuit » : l'un OU l'autre suffit."""
    from apps.ai_assistant.chatbot import baoule_repondre
    from apps.ai_assistant.chatbot.baoule_demandes import Phrase
    p = baoule_repondre._heures_sur_12h(Phrase("Le pic est à 23 heures, avec 22 kWh.", (22, 23)))
    assert p.fr == "Le pic est à 11 heures de la nuit, avec 22 kWh." and p.nombres == (22, (11, 23))
    assert baoule_repondre.manques(p, "Le pic est à 23h avec 22 kWh") == []
    assert baoule_repondre.manques(p, "Le pic est à 11 heures avec 22 kWh") == []
    assert baoule_repondre.manques(p, "Le pic est à 9 heures avec 22 kWh") == ["11"]          # une autre heure reste une erreur


# ── Contrôle du SENS des états et des ordres de coupure traduits (arbitrage du 10/11/2026, D6) ──────────────────────
@pytest.mark.parametrize("texte,attendu", [
    ("Le courant de la lampe est rétabli.", "on"), ("La prise du salon est coupée.", "off"), ("Le climatiseur est allumé.", "on"),
    ("Le courant de la prise n'est pas coupé.", "on"), ("N'éteignez pas le réfrigérateur.", "on"), ("Le chargeur est débranché.", "off"),
    ("Le climatiseur ne fonctionne plus.", "off"), ("Le compteur est hors tension.", "off"), ("Votre consommation est stable.", None),
    ("Le courant est coupé puis rétabli.", None), ("Ne redémarrez pas la climatisation avant 18h00.", "off")])
def test_polarite_allume_ou_eteint(texte, attendu):
    from apps.ai_assistant.chatbot import controle_sens
    assert controle_sens.polarite(texte) == attendu


@pytest.mark.parametrize("source,retour,attendu", [
    ("Le courant de la lampe est rétabli.", "Le pouvoir de la lumière a disparu.", "sens inversé (allumé / éteint)"),
    ("Le courant de la lampe est rétabli.", "L'électricité est renvoyée à la lampe.", None),
    ("Le courant de la prise n'est pas coupé.", "L'alimentation électrique de la prise est ininterrompue.", None),
    ("Le courant du salon est coupé.", "Le courant de la chambre est coupé.", "lieu ou appareil différent"),
    ("Le fer à repasser est éteint.", "Le fer est sorti.", "sens de l'état non retrouvé"),
    ("Votre consommation est stable.", "Votre appétit est stable.", None)])             # pas un état : rien à contrôler
def test_controle_du_sens_par_retraduction(source, retour, attendu):
    from apps.ai_assistant.chatbot import controle_sens
    assert controle_sens.ecarts(source, retour) == ([attendu] if attendu else [])
    assert controle_sens.ecarts(source, None) == []                                          # aucune retraduction : rien à comparer


def test_un_autre_appareil_dans_la_retraduction_est_un_ecart_grave():
    """Cas réel (Djelia, 10/11/2026) : « Ne rallumez pas le climatiseur » traduit en dioula revenait « Ne redémarrez le ventilateur »."""
    from apps.ai_assistant.chatbot import controle_sens
    e = controle_sens.ecarts("Ne rallumez pas le climatiseur avant 6 heures du soir.", "Ne redémarrez le ventilateur qu'après 18 heures.")
    assert "lieu ou appareil différent" in e and controle_sens.inverse(e)


def test_dioula_un_etat_traduit_au_sens_inverse_reste_en_francais(monkeypatch):
    from apps.ai_assistant.chatbot import dioula_relais
    _faux_traducteur(monkeypatch, lambda t: "Kuran min bɛ lamp la, o sera a ma kokura.", lambda t: "Le pouvoir de la lumière a disparu.", [])
    with pytest.raises(dioula_relais.RelaisIndisponible, match="sens"):
        dioula_relais.vers_dioula("Le courant de la lampe est rétabli.")


def test_dioula_un_etat_bien_retraduit_est_traduit_par_l_autre_traducteur_d_abord(monkeypatch):
    from apps.ai_assistant.chatbot import dioula_relais
    appels = []
    _faux_traducteur(monkeypatch, lambda t: "Kuran min bɛ lamp la, o sera a ma kokura.", lambda t: "Le courant est revenu à la lampe.", appels)
    texte, service = dioula_relais.vers_dioula("Le courant de la lampe est rétabli.", ordre=("djelia",))
    assert service == "djelia" and appels[1][:2] == ("google", "vers_fr")                    # retraduit par l'AUTRE service


def test_wolof_un_etat_traduit_au_sens_inverse_reste_en_francais(monkeypatch):
    from apps.ai_assistant.chatbot import dioula_relais, wolof_relais
    _faux_traducteur(monkeypatch, lambda t: "Weñ wi dafa fay, mu sax ci kër gi.", lambda t: "Le fer est sorti.", [])
    with pytest.raises(dioula_relais.RelaisIndisponible, match="sens"):
        wolof_relais.vers_wolof("Le fer à repasser est éteint.")


def test_baoule_un_etat_au_sens_inverse_reste_en_francais_et_un_etat_juste_passe(monkeypatch):
    from apps.ai_assistant.chatbot import baoule_relais, baoule_repondre
    from apps.ai_assistant.chatbot.baoule_demandes import Phrase
    monkeypatch.setattr(baoule_relais, "vers_baoule", lambda fr, *a, **k: ("Kuran ni lamp ti nga a sa ye.", "google"))
    monkeypatch.setattr(baoule_relais, "retour_en_francais", lambda bci: ("Le pouvoir de la lumière a disparu.", "google"))
    r = baoule_repondre.traduire_une(Phrase("Le courant de la lampe est rétabli."))
    assert r["controle"] == "non_traduite" and r["bci"] == "Le courant de la lampe est rétabli."          # reste en français
    monkeypatch.setattr(baoule_relais, "retour_en_francais", lambda bci: ("Le courant est revenu à la lampe.", "google"))
    assert baoule_repondre.traduire_une(Phrase("Le courant de la lampe est rétabli."))["controle"] == "verifiee"


# ── Routage du wolof en mode Automatique (arbitrage du 10/11/2026, F2) ───────────────────────────────────────────
# Textes RÉELS écrits par l'oreille Omnilingual sur des vocaux wolof humains (corpus ALFFA) : avant le correctif, le moindre « trace »
# de dioula l'emportait et la réponse partait en dioula (29 vocaux wolof sur 40 mal routés). Rejeu mesuré : 0 faux wolof sur 40 extraits
# dioula et 30 extraits baoulé, 2 sur 30 en bambara.
@pytest.mark.parametrize("texte", ["balaw law tàppit malaana ngokk am yobbaale ko buur", "xeytipay téef yu bari lañu béy ci ñaay yi",
                                   "ndaw si sukkal bàay bi wax wax mu të", "ëllëgle ñibbisi bu soobe yàlla"])
def test_vocal_wolof_ecrit_en_wolof_par_l_oreille_dioula_va_au_wolof(texte):
    from apps.ai_assistant.chatbot import dioula_routage
    dec = dioula_routage.decider({}, lambda: (texte, texte), None, None, lambda: texte)
    assert dec["langue"] == "wo" and dec["chemin"] == "wolof"


@pytest.mark.parametrize("texte", ["i ni ce, a ka kɛnɛ baara la", "n ka sɔrɔ ɲɔgɔn fɛ", "mi kpanngɔ i jam be ti kukluku"])
def test_signature_wolof_jamais_sur_les_lettres_du_dioula_et_du_baoule(texte):
    """Les lettres ɛ ɔ ɲ n'existent pas en wolof : un texte qui en contient ne prend jamais la signature wolof."""
    from apps.ai_assistant.chatbot import dioula_routage
    assert not dioula_routage._signature_wolof(texte)


def test_signature_wolof_refuse_les_textes_trop_courts():
    from apps.ai_assistant.chatbot import dioula_routage
    assert not dioula_routage._signature_wolof("ëllëgle ñibbisi")


# ── Pannes : message honnête (D16) et modèles d'écoute absents (D17) ───────────────────────────────────────────────
@pytest.mark.parametrize("erreur,present,absent", [("DeepSeek 402 : Insufficient Balance", "administrateur", "saturé"),
                                                   ("DeepSeek 401 : Authentication Fails", "administrateur", "saturé"),
                                                   ("DeepSeek 429 : rate limit", "trop de demandes", "saturé"),
                                                   ("DeepSeek 503", "saturé", "administrateur")])
def test_d16_le_message_de_panne_dit_la_vraie_cause(erreur, present, absent):
    """Avant : « saturé, réessayez » pour un solde épuisé ou une clé refusée, où réessayer ne sert à rien."""
    def ouvrir(systeme, historique):
        raise fournisseurs.Echec(erreur)
    ev = list(fournisseurs.repondre_flux("système", [{"role": "user", "texte": "Bonjour"}], liste=[("DeepSeek", "ds", ouvrir)]))
    assert ev[-1]["type"] == "erreur" and present in ev[-1]["texte"] and absent not in ev[-1]["texte"]


def test_d17_sans_les_modeles_whisper_installes_et_hors_ligne_l_erreur_le_dit(monkeypatch, tmp_path):
    import faster_whisper
    from apps.ai_assistant.chatbot import voix

    def hors_ligne(*a, **k):
        raise OSError("Cannot find the requested files in the disk cache and outgoing traffic has been disabled")
    monkeypatch.setattr(faster_whisper, "WhisperModel", hors_ligne)
    monkeypatch.setattr(voix, "DOSSIER_WHISPER", tmp_path)                 # aucun modèle installé
    monkeypatch.setitem(voix._whisper, "modele", None)
    with pytest.raises(voix.ModeleAbsent, match="installer_modeles_ia"):
        voix.whisper()


# ── Option de diagnostic : garder les vocaux reçus (désactivée par défaut) ──────────────────────────────────────────
def test_les_vocaux_ne_sont_gardes_que_si_l_option_est_active(monkeypatch, tmp_path):
    import json as _json
    from apps.ai_assistant.chatbot import voix
    monkeypatch.setattr(voix, "DRAPEAU_VOCAUX", tmp_path / "garder_vocaux.flag")
    monkeypatch.setattr(voix, "DOSSIER_VOCAUX", tmp_path / "vocaux_diag")
    assert voix.garder_vocal_pour_diagnostic(b"RIFFxxxx", "abcdef123456", 0) is None           # option inactive : rien n'est écrit
    assert not (tmp_path / "vocaux_diag").exists()
    (tmp_path / "garder_vocaux.flag").write_text("", encoding="utf-8")
    base = voix.garder_vocal_pour_diagnostic(b"RIFFxxxx", "abcdef123456", 2, {"langue": "auto"})
    assert base and base.endswith("abcdef12_morceau2")
    assert (tmp_path / "vocaux_diag" / f"{base}.wav").read_bytes() == b"RIFFxxxx"
    meta = _json.loads((tmp_path / "vocaux_diag" / f"{base}.json").read_text(encoding="utf-8"))
    assert meta["rang"] == 2 and meta["langue"] == "auto" and meta["octets"] == 8 and meta["recu_a"] > 0
    assert voix.garder_vocal_pour_diagnostic(b"RIFFyyyy", "abcdef123456").endswith("_final")


def test_garder_un_vocal_ne_leve_jamais(monkeypatch, tmp_path):
    from apps.ai_assistant.chatbot import voix
    (tmp_path / "garder_vocaux.flag").write_text("", encoding="utf-8")
    monkeypatch.setattr(voix, "DRAPEAU_VOCAUX", tmp_path / "garder_vocaux.flag")
    monkeypatch.setattr(voix, "DOSSIER_VOCAUX", tmp_path / "garder_vocaux.flag" / "impossible")      # un fichier, pas un dossier
    assert voix.garder_vocal_pour_diagnostic(b"RIFF", "s", 0) is None
