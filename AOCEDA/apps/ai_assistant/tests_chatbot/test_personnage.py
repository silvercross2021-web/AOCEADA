"""Personnage animé (étape 5) : signal envoyé par l'agent Live, fichier servi, version à jour dans la page,
licence du moteur, résultats dans « Tests et rapports ». L'essai dans le navigateur : tests/essais_reels/essai_personnage.py."""
import hashlib
import re
from pathlib import Path

from apps.ai_assistant.tests_chatbot.client_test import TestClient

from apps.ai_assistant.chatbot import live_agent
from apps.ai_assistant.tests_chatbot import serveur_labo as serveur
from django.conf import settings

from apps.ai_assistant.chatbot.config import CAPTURES

# AOCEDA : le personnage est un fichier statique de Django (au laboratoire : front/personnage/personnage.js)
PERSONNAGE = Path(settings.BASE_DIR) / "static" / "js" / "personnage.js"
client = TestClient(serveur.app)


def conso(actuel, precedent):
    return {"kwh_total": actuel, "periode_precedente": None if precedent is None else {"kwh_total": precedent}}


def test_signal_consommation_en_baisse_ou_en_hausse():
    assert live_agent.signal_outil("conso_periode", conso(80, 100)) == "baisse"      # -20 %
    assert live_agent.signal_outil("conso_periode", conso(130, 100)) == "hausse"     # +30 %
    assert live_agent.signal_outil("conso_periode", conso(90, 100)) == "baisse"      # pile -10 % : en baisse
    assert live_agent.signal_outil("conso_periode", conso(110, 100)) == "hausse"     # pile +10 % : en hausse


def test_signal_aucun_quand_c_est_stable_ou_inconnu():
    assert live_agent.signal_outil("conso_periode", conso(103, 100)) is None          # stable
    assert live_agent.signal_outil("conso_periode", conso(50, None)) is None          # pas de période précédente
    assert live_agent.signal_outil("conso_periode", conso(50, 0)) is None             # jamais de division par zéro
    assert live_agent.signal_outil("conso_periode", {"erreur": "lecture impossible"}) is None
    assert live_agent.signal_outil("conso_periode", "pas un dictionnaire") is None
    assert live_agent.signal_outil("prevision_fin_mois", {"fourchette": [1, 2]}) is None
    # 05/10/2026 : 0 kWh sans aucun jour mesuré = aucune mesure reçue, PAS une économie de 100 % (jamais de « bravo »)
    assert live_agent.signal_outil("conso_periode", {**conso(0.0, 8.73), "jours": []}) is None
    assert live_agent.signal_outil("conso_periode", {**conso(0.0, 8.73), "jours": [{"date": "2026-10-05", "kwh": 0.0}]}) == "baisse"


def test_signal_alertes_non_lues():
    assert live_agent.signal_outil("alertes", {"nb_non_lues": 2, "alertes": []}) == "alerte"
    assert live_agent.signal_outil("alertes", {"nb_non_lues": 0, "alertes": []}) is None


def test_le_signal_ne_contient_jamais_de_chiffre():
    for r in (conso(80, 100), conso(130, 100), {"nb_non_lues": 3}):
        s = live_agent.signal_outil("alertes" if "nb_non_lues" in r else "conso_periode", r)
        assert s in ("baisse", "hausse", "alerte") and not re.search(r"\d", s)


def test_le_fichier_du_personnage_est_servi_en_javascript():
    """AOCEDA : fichier statique (static/js/personnage.js), trouvé par Django et chargé par la page de l'assistant."""
    from django.contrib.staticfiles import finders
    assert finders.find("js/personnage.js")
    js = PERSONNAGE.read_text(encoding="utf-8")
    assert "window.AocedaPersonnage" in js and "class PersonnageAoceda" in js and "class ScenePersonnage" in js
    assert "/static/js/personnage.js?v=" in client.get("/").text


def test_licence_mit_du_moteur_reproduite_et_sons_de_mochi_jamais_joues():
    js = PERSONNAGE.read_text(encoding="utf-8")
    assert "MIT License" in js and "Copyright (c) 2026 Louis Raillé" in js and "Permission is hereby granted" in js
    assert "const Sound = { play() {} };" in js                                # sons de Mochi : jamais joués


def test_la_page_charge_la_version_actuelle_du_personnage():
    """La page demande personnage.js?v=<empreinte du fichier> : jamais une vieille copie gardée par le navigateur."""
    page = client.get("/").text
    empreinte = hashlib.sha256(PERSONNAGE.read_bytes()).hexdigest()[:10]
    assert f'<script src="/static/js/personnage.js?v={empreinte}"></script>' in page


def test_le_personnage_remplace_le_rond_de_l_appel_live():
    page = client.get("/").text
    assert 'id="live_perso"' in page and "live_orbe" not in page and "live-orbe" not in page
    assert 'id="perso_dock"' in page                                            # sa place à côté de la saisie


def test_resultats_du_personnage_dans_tests_et_rapports():
    assert "personnage" in client.get("/api/tests").json()


def test_captures_des_essais_servies():
    capture = next(CAPTURES.glob("perso_*.png"), None)
    if capture:                                                                 # créées au laboratoire (essai_personnage.py)
        r = client.get(f"/api/rapports/captures/{capture.name}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
