"""Smoke test visuel des pages AOCEDA (Playwright, Python global).

Usage : python smoke_pages.py <url_base> <dossier_sortie>
Le serveur doit tourner sur une COPIE de la base avec les comptes de démonstration (setup_demo).
Pour chaque page et chaque largeur (390 et 1280 px) : erreurs console, débordement horizontal, titre, capture.
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
SORTIE = Path(sys.argv[2])
SORTIE.mkdir(parents=True, exist_ok=True)
MDP = "Password123!"
PAGES = {
    "client": ("adjoua.konate@gmail.com", ["/dashboard/", "/historique/", "/alertes/", "/interventions/",
                                           "/ia/", "/ia/assistant/", "/previsions/", "/parametres/"]),
    "technicien": ("moussa.diarrassouba@aoceda.ci", ["/technicien/"]),
}
LARGEURS = {"390": (390, 844), "1280": (1280, 800)}


def jeton(page, email):
    r = page.request.post(BASE + "/api/auth/login/", data={"email": email, "password": MDP})
    return r.json() if r.ok else None


def main():
    bilan = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        # pages publiques
        for nom, (email, urls) in [("public", (None, ["/", "/auth/"]))] + list(PAGES.items()):
            for lbl, (w, h) in LARGEURS.items():
                ctx = nav.new_context(viewport={"width": w, "height": h})
                page = ctx.new_page()
                erreurs = []
                page.on("console", lambda m, e=erreurs: e.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda x, e=erreurs: e.append("PAGEERROR " + str(x)))
                if email:
                    page.goto(BASE + "/auth/")
                    t = jeton(page, email)
                    if not t:
                        bilan.append({"page": nom, "largeur": lbl, "erreur": "connexion impossible"})
                        ctx.close()
                        continue
                    page.evaluate("t => { localStorage.setItem('aoceda_access_token', t.access);"
                                  " localStorage.setItem('aoceda_refresh_token', t.refresh); }", t)
                for u in urls:
                    erreurs.clear()
                    rep = page.goto(BASE + u, wait_until="load", timeout=60000)
                    page.wait_for_timeout(3500)
                    deb = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    titre = page.title()
                    h1 = page.locator("h1").count()
                    fich = SORTIE / (u.strip("/").replace("/", "_") or "accueil")
                    page.screenshot(path=str(fich) + f"_{lbl}.png")
                    bilan.append({"url": u, "largeur": lbl, "statut": rep.status if rep else None,
                                  "titre": titre, "nb_h1": h1, "debordement_px": deb,
                                  "erreurs_console": sorted(set(erreurs))[:5]})
                ctx.close()
        nav.close()
    (SORTIE / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    for b in bilan:
        print(json.dumps(b, ensure_ascii=False))


main()
