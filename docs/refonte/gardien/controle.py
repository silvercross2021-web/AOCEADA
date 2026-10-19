#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LE GARDIEN : controle de non-regression rapide (SANS suites de tests, SANS serveur) pour la refonte d'architecture.

Usage (depuis n'importe ou ; --depot = racine du depot Git, defaut : dossier courant) :

    AOCEDA/.venv_local/Scripts/python.exe controle.py                      # tout controler
    ... controle.py --enregistrer-reference                                # (re)ecrit les references
    ... controle.py --autoriser "AOCEDA/aoceda/settings.py" --autoriser "AOCEDA/apps/*/migrations/*"
    ... controle.py --seulement urls,celery,tests                          # quelques controles
    ... controle.py --liste                                                # liste des controles

Code de sortie : 0 si aucun ECHEC, 1 sinon. Statuts : OK / ECHEC / ATTENTION (non bloquant, a lire).
Ne modifie jamais le depot (la seule ecriture : dossier reference/ et tmp/ a cote de ce script).
Stdlib seulement ; le Python utilise doit etre celui du projet (AOCEDA/.venv_local) pour les controles Django.
"""
import argparse
import ast
import collections
import fnmatch
import json
import os
import re
import subprocess
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
REF_DIR_DEFAUT = os.path.join(QUI, "reference")
TMP_DIR = os.path.join(QUI, "tmp")
TAG_DEFAUT = "avant-refonte"
TRONC = 700

# Zones protegees (AGENTS.md section 4) : modifications / suppressions interdites (les ajouts sont tolérés).
PROTEGES = [
    "AOCEDA/apps/ai_assistant/chatbot",                      # moteur + donnees/*.json
    "AOCEDA/apps/ai_assistant/rapports",
    "AOCEDA/apps/ai_assistant/tests_chatbot",
    ":(glob)AOCEDA/apps/*/tests*.py",
    "AOCEDA/static/js/personnage.js",
    "AOCEDA/apps/ai_assistant/management/commands/installer_modeles_ia.py",
    ":(glob)AOCEDA/apps/*/migrations/**",
    "AOCEDA/aoceda/settings.py",
    "AOCEDA/.env.example",
    "AOCEDA/deploiement/cerebrium_voix",
    "AOCEDA/installer.py",
    "AOCEDA/installer.bat",
    "AOCEDA/lancer_aoceda.bat",
]

# Fichiers interdits dans l'index / le commit (AGENTS.md section 3)
INTERDITS = [
    r"(^|/)\.env$", r"(^|/)\.env\.(?!example$)[^/]+$", r"db\.sqlite3", r"\.sauvegarde$",
    r"^AOCEDA/donnees_ia/", r"(^|/)\.venv_local/", r"(^|/)venv/", r"(^|/)staticfiles/",
    r"\.(onnx|safetensors|gguf|pt|pth|ckpt)$", r"(^|/)[^/]*\.bin$", r"\.playwright-mcp", r"(^|/)\.claude/",
    r"(^|/)\.cursor/", r"aoceda_cles", r"cles.*api.*\.txt$",
]
AUTORISES_BASELINE = {"AOCEDA/db.sqlite3"}   # deja suivi avant la refonte (jamais committer ses modifications)

SECRETS = [
    r"sk-[A-Za-z0-9_\-]{20,}", r"AIza[0-9A-Za-z_\-]{30,}", r"ghp_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}",
    r"xox[bpas]-[A-Za-z0-9\-]{10,}", r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
    r"(?i)\b[A-Z_]*(API_KEY|SECRET_KEY|PASSWORD|TOKEN)[A-Z_0-9]*\s*=\s*['\"][A-Za-z0-9_\-/+=]{20,}['\"]",
    r"\bor_v1_[A-Za-z0-9]{20,}", r"\bcrbrm?_[A-Za-z0-9]{20,}",
]

# Dossiers exclus de la recherche de chemins absolus (historique, documentation, binaires)
ABS_EXCLUS = ("AOCEDA/apps/ai_assistant/rapports/", "AOCEDA/Memoire_MD/", "AOCEDA/mobile_app/android/",
              "AOCEDA/_backup_presync/", "AOCEDA/maquette/", "AOCEDA/diagrame+memoire/", "AOCEDA/rapport/",
              "AOCEDA/brain/", "_a_supprimer/", "AOCEDA/staticfiles/", "docs/", "AOCEDA/scripts/")
ABS_EXT = (".py", ".js", ".html", ".css", ".bat", ".json", ".ini", ".toml", ".txt", ".yml", ".yaml", "Procfile")
ABS_RE = re.compile(r"(?i)(\b[A-Z]:[\\/]{1,2}(Users|AOCEDA|Documents|Projects)|\b[CD]:\\\\?|(?<![\w.:])/home/[\w.-]+)")

# ---------------------------------------------------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------------------------------------------------

class Ctx:
    pass


def tronque(s, n=TRONC):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " ...[tronque, %d car.]" % len(s)


def run(cmd, cwd, timeout=600, env=None):
    e = dict(os.environ)
    e.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, env=e)
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT apres %ss : %s" % (timeout, " ".join(cmd)[:200])
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def git(ctx, *args, check=False):
    rc, out, err = run(["git"] + list(args), ctx.depot, timeout=120)
    return rc, out, err


def git_files(ctx):
    rc, out, _ = git(ctx, "ls-files", "-z")
    return [f for f in out.split("\0") if f]


def lire(ctx, rel):
    try:
        with open(os.path.join(ctx.depot, rel), "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def charger_ref(ctx, nom):
    p = os.path.join(ctx.refdir, nom + ".json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def ecrire_ref(ctx, nom, data):
    os.makedirs(ctx.refdir, exist_ok=True)
    with open(os.path.join(ctx.refdir, nom + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def delta(ref, new):
    """ref/new : listes de chaines. Retourne (disparus, apparus)."""
    r, n = set(ref), set(new)
    return sorted(r - n), sorted(n - r)


def fmt_liste(titre, items, n=12):
    if not items:
        return ""
    s = "%s (%d) : %s" % (titre, len(items), " ; ".join(map(str, items[:n])))
    return s + (" ; ..." if len(items) > n else "")


def comparer(ctx, nom, courant, mode, libelle="element"):
    """Compare une liste de chaines a la reference.
    mode 'egal' : tout ecart = ECHEC ; 'sans_perte' : un element disparu = ECHEC (apparitions = ATTENTION) ;
    'sans_nouveau' : un element apparu = ECHEC (disparitions tolerees)."""
    ref = charger_ref(ctx, nom)
    if ctx.enregistrer:
        ecrire_ref(ctx, nom, courant)
        return "OK", "reference enregistree : %d %s" % (len(courant), libelle)
    if ref is None:
        return "ATTENTION", "pas de reference (lancer --enregistrer-reference) ; courant : %d %s" % (len(courant), libelle)
    dis, app = delta(ref, courant)
    msg = ["%d %s (ref %d)" % (len(courant), libelle, len(ref))]
    if dis:
        msg.append(fmt_liste("DISPARUS", dis))
    if app:
        msg.append(fmt_liste("APPARUS", app))
    if not dis and not app:
        return "OK", msg[0] + ", identique a la reference"
    if mode == "egal":
        return "ECHEC", " | ".join(msg)
    if mode == "sans_perte":
        return ("ECHEC" if dis else "ATTENTION"), " | ".join(msg)
    return ("ECHEC" if app else "ATTENTION"), " | ".join(msg)


# ---------------------------------------------------------------------------------------------------------------------
# Collecte cote Django (un seul `manage.py shell -c`) : urls, celery, settings, modeles, commandes, gabarits, imports, asgi
# ---------------------------------------------------------------------------------------------------------------------

HELPER = r'''
import ast, importlib, io, json, os, re, sys, contextlib, traceback
from pathlib import Path
OUT = os.environ["GARDIEN_OUT"]
BASE = Path(os.environ["GARDIEN_BASE"])      # dossier AOCEDA/
res = {}

def securise(nom, f):
    try:
        res[nom] = f()
    except BaseException as e:
        res[nom] = {"__erreur__": "%s: %s" % (type(e).__name__, str(e)[:300]), "__tb__": traceback.format_exc()[-800:]}

def rel(p):
    return str(Path(p).resolve()).replace(str(BASE.resolve()), "<AOCEDA>").replace("\\", "/")

# ---- URL ----
def urls():
    from django.urls import get_resolver, URLResolver
    routes, cbs = [], []
    def marche(patterns, prefix, ns):
        for p in patterns:
            if isinstance(p, URLResolver):
                n = p.namespace
                marche(p.url_patterns, prefix + str(p.pattern), (ns + ":" if ns else "") + n if n else ns)
            else:
                cb = p.callback
                cls = getattr(cb, "view_class", None) or getattr(cb, "cls", None)
                cible = cls if cls is not None else cb
                nom = ((ns + ":") if ns else "") + (p.name or "")
                chemin = prefix + str(p.pattern)
                routes.append("%s  [name=%s]" % (chemin, nom or "-"))
                cbs.append("%s  ->  %s.%s" % (chemin, getattr(cible, "__module__", "?"), getattr(cible, "__qualname__", getattr(cible, "__name__", repr(cible)))))
    marche(get_resolver().url_patterns, "", "")
    return {"routes": sorted(routes), "callbacks": sorted(cbs)}

# ---- Celery ----
def celery():
    from aoceda.celery import app
    app.loader.import_default_modules()
    app.autodiscover_tasks(force=True)
    noms = sorted(k for k in app.tasks.keys() if not k.startswith("celery."))
    beat = sorted("%s => %s" % (k, v["task"]) for k, v in app.conf.beat_schedule.items())
    manquants = sorted(v["task"] for v in app.conf.beat_schedule.values() if v["task"] not in app.tasks)
    return {"taches": noms, "beat": beat, "beat_sans_tache": manquants}

# ---- reglages ----
def reglages():
    from django.conf import settings
    secret = re.compile(r"KEY|SECRET|PASSWORD|TOKEN|DSN|URL$", re.I)
    noms = sorted(n for n in dir(settings) if n.isupper())
    def nettoie(v):
        s = json.dumps(v, default=str, sort_keys=True)
        return s.replace(str(BASE).replace("\\", "\\\\"), "<AOCEDA>").replace(str(BASE), "<AOCEDA>").replace("\\\\", "/")
    garde = ["INSTALLED_APPS", "MIDDLEWARE", "ROOT_URLCONF", "ASGI_APPLICATION", "WSGI_APPLICATION", "AUTH_USER_MODEL",
             "TEMPLATES", "STATICFILES_DIRS", "STATIC_URL", "STATIC_ROOT", "MEDIA_URL", "MEDIA_ROOT", "LOGIN_URL", "REST_FRAMEWORK",
             "AUTHENTICATION_BACKENDS", "CELERY_TIMEZONE", "TIME_ZONE", "LANGUAGE_CODE", "ROOT_URLCONF", "DEFAULT_AUTO_FIELD"]
    valeurs = []
    for n in garde:
        if hasattr(settings, n) and not secret.search(n):
            valeurs.append("%s = %s" % (n, nettoie(getattr(settings, n))))
    cl = getattr(settings, "CHANNEL_LAYERS", None)
    if cl is not None:
        valeurs.append("CHANNEL_LAYERS.backends = %s" % sorted(v.get("BACKEND", "?") for v in cl.values()))
    return {"noms": noms, "valeurs": sorted(valeurs), "daphne_en_tete": settings.INSTALLED_APPS[0] == "daphne"}

# ---- modeles / commandes ----
def modeles():
    from django.apps import apps
    out = []
    for m in apps.get_models():
        champs = ",".join(sorted("%s:%s" % (f.name, type(f).__name__) for f in m._meta.get_fields()))
        out.append("%s | table=%s | %s" % (m._meta.label, m._meta.db_table, champs))
    return sorted(out)

def commandes():
    from django.core.management import get_commands
    return sorted("%s@%s" % (k, v) for k, v in get_commands().items())

# ---- gabarits ----
RE_EXT = re.compile(r"{%\s*extends\s+[\"']([^\"']+)[\"']")
RE_INC = re.compile(r"{%\s*include\s+[\"']([^\"']+)[\"']")
RE_STA = re.compile(r"{%\s*static\s+[\"']([^\"']+)[\"']")
RE_URL = re.compile(r"{%\s*url\s+[\"']([^\"']+)[\"']")
RE_SRC = re.compile(r"""<(?:script|img|source)\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.I)
RE_LNK = re.compile(r"""<link\b[^>]*?\bhref\s*=\s*["']([^"']+)["']""", re.I)

def local_statique(ref):
    """Retourne le chemin statique si la reference est un fichier local (sinon None)."""
    r = ref.strip()
    if not r or r.startswith(("http:", "https:", "//", "data:", "#", "mailto:", "blob:", "javascript:")) or "{{" in r or "{%" in r:
        if "{%" in r and "static" in r:
            pass
        return None
    r = r.split("?")[0].split("#")[0]
    if r.startswith("/static/"):
        return r[len("/static/"):]
    return None

def gabarits():
    from django.template import engines
    from django.template.loader import get_template
    from django.contrib.staticfiles import finders
    from django.urls import get_resolver
    eng = engines["django"]
    # noms d'URL valides
    noms_url = set()
    def marche(patterns, ns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                n = p.namespace
                marche(p.url_patterns, (ns + ":" if ns else "") + n if n else ns)
            elif p.name:
                noms_url.add(((ns + ":") if ns else "") + p.name)
    marche(get_resolver().url_patterns, "")
    racines = [BASE / "templates"] + [d / "templates" for d in sorted((BASE / "apps").iterdir()) if d.is_dir()]
    fichiers = []
    for r in racines:
        if r.is_dir():
            for f in sorted(r.rglob("*.html")):
                fichiers.append((r, f))
    pb, vus = [], []
    for racine, f in fichiers:
        nom = f.relative_to(racine).as_posix()
        vus.append(rel(f))
        txt = f.read_text(encoding="utf-8", errors="replace")
        try:
            get_template(nom)
        except Exception as e:
            pb.append("COMPILATION %s : %s: %s" % (nom, type(e).__name__, str(e)[:160]))
        for rx, lib in ((RE_EXT, "extends"), (RE_INC, "include")):
            for m in rx.findall(txt):
                try:
                    get_template(m)
                except Exception as e:
                    pb.append("%s introuvable dans %s : %s" % (lib, nom, m))
        for m in RE_STA.findall(txt):
            if "{" in m:
                continue
            if not finders.find(m.split("?")[0]):
                pb.append("static introuvable dans %s : %s" % (nom, m))
        for m in RE_URL.findall(txt):
            if m not in noms_url:
                pb.append("{%% url %%} nom inconnu dans %s : %s" % (nom, m))
        for rx in (RE_SRC, RE_LNK):
            for m in rx.findall(txt):
                chem = local_statique(m)
                if chem and not finders.find(chem):
                    pb.append("balise locale introuvable dans %s : %s" % (nom, m))
    # gabarits cites en dur dans le code Python (render(..., 'x.html'), template_name = ...)
    for d in ("apps", "aoceda"):
        for f in sorted((BASE / d).rglob("*.py")):
            if "tests" in f.name or "tests_chatbot" in f.parts or "migrations" in f.parts or "rapports" in f.parts:
                continue
            try:
                arbre = ast.parse(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for n in ast.walk(arbre):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[\w./\-]+\.html", n.value):
                    try:
                        get_template(n.value)
                    except Exception:
                        pb.append("gabarit cite par Python introuvable : %s (dans %s)" % (n.value, rel(f).replace("<AOCEDA>/", "")))
    # reverse('nom') litteral dans le code Python
    for d in ("apps", "aoceda"):
        for f in sorted((BASE / d).rglob("*.py")):
            if "tests_chatbot" in f.parts or "migrations" in f.parts:
                continue
            try:
                arbre = ast.parse(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for n in ast.walk(arbre):
                if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("reverse", "reverse_lazy") and n.args:
                    a = n.args[0]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value not in noms_url:
                        pb.append("reverse() nom inconnu : %s (dans %s)" % (a.value, rel(f).replace("<AOCEDA>/", "")))
    return {"gabarits": sorted(vus), "problemes": sorted(set(pb)), "noms_url": len(noms_url)}

def statiques():
    out = []
    st = BASE / "static"
    for f in sorted(st.rglob("*")):
        if f.is_file():
            out.append(f.relative_to(st).as_posix())
    return out

# ---- URL /api/... citees par le JS et les gabarits (resolution) ----
def api_js():
    from django.urls import resolve, Resolver404, get_resolver
    prefixes = set()
    def marche(patterns, prefix):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                marche(p.url_patterns, prefix + str(p.pattern))
            else:
                full = prefix + str(p.pattern)
                prefixes.add("/" + re.split(r"[<(\[^$]", full.lstrip("^"))[0])
    marche(get_resolver().url_patterns, "")
    rx = re.compile(r"""["'`](/api/[A-Za-z0-9_\-/.]*)""")
    inconnus = []
    cibles = list((BASE / "static" / "js").rglob("*.js")) + list((BASE / "templates").rglob("*.html"))
    for f in cibles:
        if f.name == "personnage.js" and False:
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        for m in set(rx.findall(txt)):
            ok = False
            for cand in (m, m + "1/", m + "1", m + "x/"):
                try:
                    resolve(cand); ok = True; break
                except Resolver404:
                    pass
            if not ok:
                ok = any(p.startswith(m) for p in prefixes)
            if not ok:
                inconnus.append("%s -> %s" % (f.relative_to(BASE).as_posix(), m))
    return sorted(inconnus)

# ---- import de chaque module ----
def importer():
    sys.path.insert(0, str(BASE))
    ech, ok = [], []
    excl_nom = re.compile(r"^(tests?(_.*)?|test_.*|conftest|client_test|serveur_labo)\.py$")
    for d in ("apps", "aoceda"):
        for f in sorted((BASE / d).rglob("*.py")):
            if excl_nom.match(f.name) or "tests_chatbot" in f.parts or "__pycache__" in f.parts or "rapports" in f.parts:
                continue
            parts = list(f.relative_to(BASE).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mod = ".".join(parts)
            tampon = io.StringIO()
            try:
                with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
                    importlib.import_module(mod)
                ok.append(mod)
            except BaseException as e:
                ech.append("%s : %s: %s" % (mod, type(e).__name__, str(e).splitlines()[0][:200] if str(e) else ""))
    return {"ok": ok, "echecs": sorted(ech)}

# ---- ASGI ----
def asgi():
    from django.conf import settings
    import aoceda.asgi as a
    from apps.ai_assistant.routing import websocket_urlpatterns
    app = a.application
    cles = sorted(getattr(app, "application_mapping", {}).keys())
    routes = sorted(str(p.pattern) for p in websocket_urlpatterns)
    return {"protocoles": cles, "routes_ws": routes, "ASGI_APPLICATION": getattr(settings, "ASGI_APPLICATION", None),
            "wsgi": getattr(settings, "WSGI_APPLICATION", None),
            "daphne_en_tete": settings.INSTALLED_APPS[0] == "daphne"}

for nom, f in (("urls", urls), ("celery", celery), ("reglages", reglages), ("modeles", modeles), ("commandes", commandes),
               ("gabarits", gabarits), ("statiques", statiques), ("api_js", api_js), ("importer", importer), ("asgi", asgi)):
    securise(nom, f)
with open(OUT, "w", encoding="utf-8") as fo:
    json.dump(res, fo, ensure_ascii=False)
'''


def collecte_django(ctx):
    if ctx.django is not None:
        return ctx.django
    os.makedirs(TMP_DIR, exist_ok=True)
    hp = os.path.join(TMP_DIR, "_collecte_helper.py")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(HELPER)
    out = os.path.join(TMP_DIR, "_collecte_out.json")
    if os.path.exists(out):
        os.remove(out)
    cmd = [sys.executable, "manage.py", "shell", "-c", "exec(open(r'%s', encoding='utf-8').read())" % hp]
    rc, so, se = run(cmd, ctx.aoceda, timeout=900, env={"GARDIEN_OUT": out, "GARDIEN_BASE": ctx.aoceda})
    if not os.path.isfile(out):
        ctx.django = {"__plantage__": "rc=%s stdout=%s stderr=%s" % (rc, tronque(so, 300), tronque(se, 500))}
    else:
        with open(out, encoding="utf-8") as f:
            ctx.django = json.load(f)
    return ctx.django


def bloc(ctx, nom):
    d = collecte_django(ctx)
    if "__plantage__" in d:
        return None, "collecte Django impossible : " + d["__plantage__"]
    b = d.get(nom)
    if isinstance(b, dict) and "__erreur__" in b:
        return None, "collecte '%s' en erreur : %s | %s" % (nom, b["__erreur__"], b.get("__tb__", "")[-300:])
    return b, None


# ---------------------------------------------------------------------------------------------------------------------
# Les controles (a) .. (m) + complements
# ---------------------------------------------------------------------------------------------------------------------

def c_check(ctx):
    rc, so, se = run([sys.executable, "manage.py", "check"], ctx.aoceda, timeout=300)
    sortie = (so + se).strip()
    lignes = sorted(l.strip() for l in sortie.splitlines() if l.strip())
    ref = charger_ref(ctx, "check")
    if ctx.enregistrer:
        ecrire_ref(ctx, "check", lignes)
    if rc != 0:
        return "ECHEC", "manage.py check code %s : %s" % (rc, tronque(sortie))
    if ref is not None and not ctx.enregistrer:
        dis, app = delta(ref, lignes)
        if app:
            return "ECHEC", "nouveaux messages de check : %s" % tronque(" ; ".join(app))
    return "OK", tronque(sortie or "(aucune sortie)", 300)


def c_migrations_a_jour(ctx):
    rc, so, se = run([sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], ctx.aoceda, timeout=300)
    sortie = (so + se).strip()
    if rc == 0 and "No changes detected" in sortie:
        return "OK", "No changes detected"
    return "ECHEC", "code %s : %s" % (rc, tronque(sortie))


def c_showmigrations(ctx):
    rc, so, se = run([sys.executable, "manage.py", "showmigrations", "--list"], ctx.aoceda, timeout=300)
    if rc != 0:
        return "ECHEC", "showmigrations code %s : %s" % (rc, tronque(se or so))
    noms, app = [], ""
    for l in so.splitlines():
        if not l.strip():
            continue
        m = re.match(r"^\s*\[(.| )\]\s+(\S+)", l)
        if m:
            noms.append("%s.%s" % (app, m.group(2)))
        elif not l.startswith(" "):
            app = l.strip()
    noms = sorted(noms)
    non_app = sum(1 for l in so.splitlines() if l.strip().startswith("[ ]"))
    st, msg = comparer(ctx, "showmigrations", noms, "egal", "migrations")
    if non_app:
        msg += " | %d migration(s) non appliquee(s) sur db.sqlite3 (info, base locale)" % non_app
    return st, msg


def c_urls(ctx):
    b, err = bloc(ctx, "urls")
    if err:
        return "ECHEC", err
    st, msg = comparer(ctx, "urls_routes", b["routes"], "egal", "routes (motif + nom)")
    # les vues peuvent legitimement changer de module : comparaison informative (ATTENTION)
    ref = charger_ref(ctx, "urls_vues")
    if ctx.enregistrer:
        ecrire_ref(ctx, "urls_vues", b["callbacks"])
    elif ref is not None:
        dis, app = delta(ref, b["callbacks"])
        if dis or app:
            msg += " || vues cibles modifiees (%d) : %s" % (len(dis), tronque(" ; ".join(app[:6]), 350))
            if st == "OK":
                st = "ATTENTION"
    return st, msg


def c_celery(ctx):
    b, err = bloc(ctx, "celery")
    if err:
        return "ECHEC", err
    if b["beat_sans_tache"]:
        return "ECHEC", "taches du beat non enregistrees : %s" % b["beat_sans_tache"]
    st, msg = comparer(ctx, "celery_taches", b["taches"] + ["beat:" + x for x in b["beat"]], "egal", "taches/planifications")
    return st, msg + " | taches : %s" % tronque(", ".join(b["taches"]), 300)


def c_gabarits(ctx):
    b, err = bloc(ctx, "gabarits")
    if err:
        return "ECHEC", err
    api, e2 = bloc(ctx, "api_js")
    probs = list(b["problemes"])
    if e2:
        return "ECHEC", e2
    st, msg = comparer(ctx, "gabarits_problemes", probs, "sans_nouveau", "probleme(s) de gabarits/static")
    st2, msg2 = comparer(ctx, "api_js_inconnus", api, "sans_nouveau", "URL /api/ du JS/gabarits sans route")
    st3, msg3 = comparer(ctx, "gabarits_liste", b["gabarits"], "sans_perte", "gabarits")
    pire = "ECHEC" if "ECHEC" in (st, st2, st3) else ("ATTENTION" if "ATTENTION" in (st, st2, st3) else "OK")
    base = "%d gabarits, %d noms d'URL" % (len(b["gabarits"]), b["noms_url"])
    return pire, "%s | problemes: %s | api: %s | liste: %s || actuels: %s" % (base, msg, msg2, msg3, tronque(" ; ".join(probs[:6]), 300))


def c_statiques(ctx):
    b, err = bloc(ctx, "statiques")
    if err:
        return "ECHEC", err
    return comparer(ctx, "statiques", b, "sans_perte", "fichiers static/")


def fichiers_py(ctx, sous=("AOCEDA/apps", "AOCEDA/aoceda")):
    return [f for f in git_files(ctx) if f.endswith(".py") and any(f.startswith(s + "/") for s in sous)]


def c_compilation(ctx):
    erreurs = []
    n = 0
    for rel in fichiers_py(ctx):
        txt = lire(ctx, rel)
        if txt is None:
            continue  # fichier supprime dans l'arbre de travail
        n += 1
        try:
            compile(txt, rel, "exec")
        except SyntaxError as e:
            erreurs.append("%s:%s %s" % (rel, e.lineno, e.msg))
    # compileall officiel, sans ecrire de .pyc (-B n'agit pas sur compileall : on utilise --invalidation sans sortie via -d)
    return ("ECHEC", "%d erreur(s) de syntaxe : %s" % (len(erreurs), tronque("; ".join(erreurs)))) if erreurs else ("OK", "%d fichiers .py compiles (compile() equivalent a compileall, sans ecrire de .pyc)" % n)


def c_imports(ctx):
    b, err = bloc(ctx, "importer")
    if err:
        return "ECHEC", err
    st, msg = comparer(ctx, "imports_echecs", b["echecs"], "sans_nouveau", "module(s) non importable(s)")
    ecr = charger_ref(ctx, "imports_modules")
    info = ""
    if ctx.enregistrer:
        ecrire_ref(ctx, "imports_modules", b["ok"])
    elif ecr is not None:
        dis, app = delta(ecr, b["ok"])
        if dis:
            info = " | modules importables disparus (deplaces ?) : %s" % fmt_liste("", dis, 8)
    return st, "%d modules importes OK, %d echecs | %s%s | echecs actuels: %s" % (len(b["ok"]), len(b["echecs"]), msg, info, tronque("; ".join(b["echecs"]), 300))


# --- resolution statique des imports internes et des chaines 'apps.x.y' (substitut de pyflakes) ---

def nom_module_depuis_fichier(rel):
    p = rel[len("AOCEDA/"):-3].split("/")
    est_pkg = p[-1] == "__init__"
    if est_pkg:
        p = p[:-1]
    return ".".join(p), est_pkg


class Index:
    def __init__(self, ctx, fichiers):
        self.ctx = ctx
        self.f = set(fichiers)
        self.noms_cache = {}

    def fichier_module(self, mod):
        base = "AOCEDA/" + mod.replace(".", "/")
        if base + ".py" in self.f:
            return base + ".py"
        if base + "/__init__.py" in self.f:
            return base + "/__init__.py"
        # paquet-namespace (dossier sans __init__ suivi)
        if any(x.startswith(base + "/") for x in self.f):
            return base + "/"
        return None

    def noms_definis(self, fichier):
        """Noms de premier niveau ; None = indetermine (import *)."""
        if fichier in self.noms_cache:
            return self.noms_cache[fichier]
        if fichier.endswith("/"):
            self.noms_cache[fichier] = set()
            return set()
        txt = lire(self.ctx, fichier)
        noms, etoile = set(), False
        try:
            arbre = ast.parse(txt or "")
        except SyntaxError:
            self.noms_cache[fichier] = None
            return None

        def visite(corps):
            nonlocal etoile
            for n in corps:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    noms.add(n.name)
                elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
                    for c in cibles:
                        for x in ast.walk(c):
                            if isinstance(x, ast.Name):
                                noms.add(x.id)
                elif isinstance(n, ast.Import):
                    for a in n.names:
                        noms.add((a.asname or a.name).split(".")[0])
                elif isinstance(n, ast.ImportFrom):
                    for a in n.names:
                        if a.name == "*":
                            etoile = True
                        else:
                            noms.add(a.asname or a.name)
                elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                    for attr in ("body", "orelse", "finalbody"):
                        visite(getattr(n, attr, []) or [])
                    for h in getattr(n, "handlers", []) or []:
                        visite(h.body)
        visite(arbre.body)
        # __getattr__ de module : tout est possible
        if "__getattr__" in noms:
            etoile = True
        self.noms_cache[fichier] = None if etoile else noms
        return self.noms_cache[fichier]

    def attribut_existe(self, mod, nom):
        """True si `mod.nom` existe (attribut ou sous-module). None si indetermine."""
        f = self.fichier_module(mod)
        if f is None:
            return False
        if self.fichier_module(mod + "." + nom):
            return True
        n = self.noms_definis(f)
        return None if n is None else (nom in n)


def c_imports_internes(ctx):
    """Chaque `from apps.x import y` / `import apps.x.y` / relatif / chaine 'apps.x.y' / mock.patch resolu statiquement."""
    tous = git_files(ctx)
    idx = Index(ctx, [f for f in tous if f.startswith("AOCEDA/")])
    py = [f for f in tous if f.startswith("AOCEDA/") and f.endswith(".py") and
          not f.startswith(("AOCEDA/venv/", "AOCEDA/scripts/", "AOCEDA/_backup_presync/", "AOCEDA/staticfiles/",
                            "AOCEDA/mobile_app/", "AOCEDA/maquette/", "AOCEDA/brain/", "AOCEDA/dioula_models/"))]
    pb = []
    racines = ("apps", "aoceda")
    re_chaine = re.compile(r"^(apps|aoceda)(\.[A-Za-z_]\w*)+$")
    for rel in py:
        txt = lire(ctx, rel)
        if txt is None:
            continue
        try:
            arbre = ast.parse(txt)
        except SyntaxError:
            pb.append("%s : syntaxe invalide" % rel)
            continue
        mod, est_pkg = nom_module_depuis_fichier(rel)
        paquet = mod if est_pkg else mod.rpartition(".")[0]
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom):
                if n.level:
                    parts = paquet.split(".") if paquet else []
                    remonte = n.level - 1
                    if remonte > len(parts):
                        pb.append("%s:%d import relatif hors paquet" % (rel, n.lineno)); continue
                    base = parts[:len(parts) - remonte]
                    cible = ".".join(base + ([n.module] if n.module else []))
                else:
                    cible = n.module or ""
                    if cible.split(".")[0] not in racines:
                        continue
                if idx.fichier_module(cible) is None:
                    pb.append("%s:%d module introuvable : %s" % (rel, n.lineno, cible)); continue
                for a in n.names:
                    if a.name == "*":
                        continue
                    if idx.attribut_existe(cible, a.name) is False:
                        pb.append("%s:%d nom introuvable : from %s import %s" % (rel, n.lineno, cible, a.name))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] in racines and idx.fichier_module(a.name) is None:
                        pb.append("%s:%d module introuvable : import %s" % (rel, n.lineno, a.name))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and re_chaine.match(n.value):
                s = n.value.split(".")
                trouve = False
                for i in range(len(s), 0, -1):
                    m = ".".join(s[:i])
                    if idx.fichier_module(m):
                        reste = s[i:]
                        trouve = True
                        if reste:
                            ex = idx.attribut_existe(m, reste[0])
                            if ex is False:
                                pb.append("%s:%d chaine '%s' : %s absent de %s" % (rel, n.lineno, n.value, reste[0], m))
                        break
                if not trouve:
                    pb.append("%s:%d chaine '%s' : module introuvable" % (rel, n.lineno, n.value))
    pb = sorted(set(pb))
    st, msg = comparer(ctx, "imports_internes", pb, "sans_nouveau", "reference(s) interne(s) cassee(s)")
    return st, "%d fichiers analyses | %s | actuels: %s" % (len(py), msg, tronque(" ; ".join(pb[:6]), 400))


def c_lint(ctx):
    for outil in ("ruff", "pyflakes", "flake8"):
        cmd = [sys.executable, "-m", outil]
        rc, so, se = run(cmd + ["--version"], ctx.aoceda, timeout=60)
        if rc == 0:
            if outil == "ruff":
                rc, so, se = run(cmd + ["check", "--select", "F", "--output-format", "concise", "apps", "aoceda"], ctx.aoceda, timeout=300)
            elif outil == "pyflakes":
                rc, so, se = run(cmd + ["apps", "aoceda"], ctx.aoceda, timeout=300)
            else:
                rc, so, se = run(cmd + ["--select", "F", "apps", "aoceda"], ctx.aoceda, timeout=300)
            lignes = sorted(re.sub(r":\d+:\d+:", ":", re.sub(r"(\.py):\d+:", r"\1:", l)).strip() for l in so.splitlines()
                            if ".py" in l)
            n_ref = charger_ref(ctx, "lint")
            if ctx.enregistrer:
                ecrire_ref(ctx, "lint", lignes)
                return "OK", "%s : %d erreur(s) F enregistree(s)" % (outil, len(lignes))
            if n_ref is None:
                return "ATTENTION", "%s : %d erreurs, pas de reference" % (outil, len(lignes))
            nv = sorted(set(lignes) - set(n_ref))
            return ("ECHEC", "%s : %d nouvelle(s) erreur(s) : %s" % (outil, len(nv), tronque("; ".join(nv)))) if len(lignes) > len(n_ref) or nv else ("OK", "%s : %d erreurs (ref %d)" % (outil, len(lignes), len(n_ref)))
    return "ATTENTION", ("ni ruff, ni pyflakes, ni flake8 dans le Python du projet : lint F non effectue "
                         "(le controle 'imports_internes' fait une resolution statique d'imports a la place ; "
                         "noms non definis / imports inutilises NON couverts)")


def c_chemins_absolus(ctx):
    trouves = collections.Counter()
    for rel in git_files(ctx):
        if rel == "compile_commands.json" or rel.startswith(ABS_EXCLUS) or not (rel.endswith(ABS_EXT[:-1]) or rel.endswith("Procfile")):
            continue
        if not rel.startswith("AOCEDA/") and not rel.startswith("src/") and not rel.startswith("include/"):
            pass
        txt = lire(ctx, rel)
        if txt is None:
            continue
        for m in ABS_RE.finditer(txt):
            trouves[rel] += 1
    lst = ["%s x%d" % (k, v) for k, v in sorted(trouves.items())]
    st, msg = comparer(ctx, "chemins_absolus", lst, "sans_nouveau", "fichier(s) avec chemin absolu (historique tolere, nouveaux interdits)")
    return st, msg + " | actuels : %s" % tronque(" ; ".join(lst[:8]), 300)


def pathspecs_protege(ctx):
    return PROTEGES


def autorise(ctx, chemin):
    return any(fnmatch.fnmatch(chemin, a) or chemin.startswith(a.rstrip("/") + "/") for a in ctx.autoriser)


def c_zones_protegees(ctx):
    base = ctx.tag
    rc, out, err = git(ctx, "rev-parse", "--verify", base + "^{commit}")
    if rc != 0:
        return "ECHEC", "tag/commit de base introuvable : %s" % base
    cmd = ["diff", "--no-renames", "--diff-filter=MDTUXB", "--name-status", base, "--"] + PROTEGES
    rc, out, err = git(ctx, *cmd)
    rc2, out2, _ = git(ctx, "diff", "--no-renames", "--diff-filter=MDTUXB", "--name-status", "--cached", "--", *PROTEGES)
    lignes = sorted(set(l for l in (out + out2).splitlines() if l.strip()))
    bad = [l for l in lignes if not autorise(ctx, l.split("\t", 1)[1])]
    ok_autor = [l for l in lignes if l not in bad]
    # fichiers protégés non suivis supprimes dans l'arbre de travail
    if rc != 0:
        return "ECHEC", "git diff code %s : %s" % (rc, tronque(err))
    if bad:
        rc3, stat, _ = git(ctx, "diff", "--no-renames", "--stat", base, "--", *PROTEGES)
        return "ECHEC", "%d modification(s) de zone protegee non autorisee(s) : %s || stat: %s" % (
            len(bad), tronque(" ; ".join(bad), 450), tronque(stat.strip().splitlines()[-1] if stat.strip() else "", 120))
    return "OK", "zones protegees inchangees vs %s%s" % (base, (" (%d modification(s) autorisee(s) : %s)" % (len(ok_autor), tronque("; ".join(ok_autor), 200))) if ok_autor else "")


def c_fichiers_interdits(ctx):
    rx = [re.compile(p) for p in INTERDITS]
    suivis = [f for f in git_files(ctx) if any(r.search(f) for r in rx)]
    suivis = [f for f in suivis if f not in AUTORISES_BASELINE and not f.endswith(".env.example")]
    rc, out, _ = git(ctx, "diff", "--cached", "--name-only")
    indexes = [f for f in out.splitlines() if any(r.search(f) for r in rx) and not f.endswith(".env.example")]
    rc, out, _ = git(ctx, "diff", "--no-renames", "--diff-filter=AM", "--name-only", ctx.tag)
    ajoutes = [f for f in out.splitlines() if any(r.search(f) for r in rx) and f not in AUTORISES_BASELINE and not f.endswith(".env.example")]
    # db.sqlite3 dans l'index
    pb = []
    if suivis:
        pb.append("suivis : " + ", ".join(suivis[:8]))
    if indexes:
        pb.append("dans l'index : " + ", ".join(indexes[:8]))
    if ajoutes:
        pb.append("ajoutes/modifies depuis %s : %s" % (ctx.tag, ", ".join(ajoutes[:8])))
    # secrets dans le diff
    secrets = []
    rcd, diff, _ = git(ctx, "diff", "-M", "-U0", "--text", ctx.tag, "--", ".", ":(exclude)AOCEDA/db.sqlite3", ":(exclude)*.png",
                       ":(exclude)*.jpg", ":(exclude)*.mp4", ":(exclude)*.webm")
    rcc, diffc, _ = git(ctx, "diff", "--cached", "-U0", "--text", "--", ".", ":(exclude)AOCEDA/db.sqlite3")
    rxs = [re.compile(p) for p in SECRETS]
    fichier = ""
    for l in (diff + "\n" + diffc).splitlines():
        if l.startswith("+++ "):
            fichier = l[6:]
        elif l.startswith("+") and not l.startswith("+++"):
            for r in rxs:
                if r.search(l):
                    secrets.append("%s : motif %s" % (fichier, r.pattern[:25]))
                    break
    if secrets:
        pb.append("motifs de cle d'API dans le diff : %s" % tronque("; ".join(sorted(set(secrets))[:6]), 300))
    # non suivis non ignores qui seraient dangereux
    rc, out, _ = git(ctx, "ls-files", "--others", "--exclude-standard")
    non_suivis = [f for f in out.splitlines() if any(r.search(f) for r in rx)]
    note = ("" if not non_suivis else " | ATTENTION non suivis a ne pas ajouter : %s" % ", ".join(non_suivis[:5]))
    if pb:
        return "ECHEC", " || ".join(pb) + note
    return "OK", "aucun fichier interdit suivi/indexe/ajoute, aucun motif de cle dans le diff (vs %s)%s" % (ctx.tag, note)


def comptage_tests(ctx):
    fichiers = [f for f in git_files(ctx) if f.endswith(".py") and f.startswith("AOCEDA/") and
                re.search(r"(^|/)(tests?(_[^/]*)?\.py|test_[^/]*\.py)$|/tests_chatbot/", f)]
    ids = collections.Counter()
    par_fichier = {}
    classes = 0
    for rel in fichiers:
        txt = lire(ctx, rel)
        if txt is None:
            continue
        try:
            arbre = ast.parse(txt)
        except SyntaxError:
            continue
        n_f = n_c = 0
        for noeud in arbre.body:
            if isinstance(noeud, ast.ClassDef):
                est_test = noeud.name.startswith("Test") or any(
                    (getattr(b, "attr", getattr(b, "id", "")) or "").endswith(("TestCase", "Test")) for b in noeud.bases)
                if est_test:
                    n_c += 1
                for m in noeud.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test"):
                        ids[noeud.name + "." + m.name] += 1
                        n_f += 1
            elif isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name.startswith("test_"):
                ids["<module>." + noeud.name] += 1
                n_f += 1
        par_fichier[rel] = [n_f, n_c]
        classes += n_c
    return ids, par_fichier, classes


def c_tests(ctx):
    ids, par_fichier, classes = comptage_tests(ctx)
    total = sum(ids.values())
    ref = charger_ref(ctx, "tests")
    courant = {"total": total, "classes": classes, "par_fichier": par_fichier, "ids": dict(ids)}
    if ctx.enregistrer:
        ecrire_ref(ctx, "tests", courant)
        return "OK", "reference : %d fonctions de test, %d classes, %d fichiers" % (total, classes, len(par_fichier))
    if ref is None:
        return "ATTENTION", "pas de reference ; %d tests" % total
    perdus = []
    for k, v in ref["ids"].items():
        if ids.get(k, 0) < v:
            perdus.append("%s (-%d)" % (k, v - ids.get(k, 0)))
    ajoutes = sum(max(0, v - ref["ids"].get(k, 0)) for k, v in ids.items())
    fich_disp = sorted(set(ref["par_fichier"]) - set(par_fichier))
    msg = "%d tests (ref %d), classes %d (ref %d), fichiers %d (ref %d)" % (total, ref["total"], classes, ref["classes"], len(par_fichier), len(ref["par_fichier"]))
    if perdus:
        return "ECHEC", "TESTS PERDUS : %s | %s" % (tronque("; ".join(sorted(perdus)), 400), msg)
    if fich_disp:
        return "ATTENTION", "%s | fichiers de test disparus/deplaces (aucun test perdu par nom) : %s" % (msg, fmt_liste("", fich_disp, 6))
    return "OK", msg + (" ; +%d test(s) ajoute(s)" % ajoutes if ajoutes else ", identique")


def c_asgi(ctx):
    pb = []
    a = lire(ctx, "AOCEDA/aoceda/asgi.py") or ""
    r = lire(ctx, "AOCEDA/apps/ai_assistant/routing.py") or ""
    for motif, txt, nom in (("ProtocolTypeRouter", a, "asgi.py"), ("URLRouter", a, "asgi.py"), ("websocket_urlpatterns", a, "asgi.py"),
                            ("AllowedHostsOriginValidator", a, "asgi.py"), ("api/assistant/live", r, "routing.py")):
        if motif not in txt:
            pb.append("%s absent de %s" % (motif, nom))
    b, err = bloc(ctx, "asgi")
    if err:
        return "ECHEC", err + (" | " + "; ".join(pb) if pb else "")
    if "websocket" not in b["protocoles"] or "http" not in b["protocoles"]:
        pb.append("protocoles ASGI = %s" % b["protocoles"])
    if not any("api/assistant/live" in x for x in b["routes_ws"]):
        pb.append("route WebSocket live absente : %s" % b["routes_ws"])
    if not b["daphne_en_tete"]:
        pb.append("daphne n'est plus en tete de INSTALLED_APPS")
    if b["ASGI_APPLICATION"] != "aoceda.asgi.application":
        pb.append("ASGI_APPLICATION = %s" % b["ASGI_APPLICATION"])
    # le consumer live doit etre importable
    if pb:
        return "ECHEC", "; ".join(pb)
    return "OK", "protocoles %s, routes WS %s, ASGI_APPLICATION=%s, daphne en tete" % (b["protocoles"], b["routes_ws"], b["ASGI_APPLICATION"])


def c_reglages(ctx):
    b, err = bloc(ctx, "reglages")
    if err:
        return "ECHEC", err
    s1, m1 = comparer(ctx, "reglages_noms", b["noms"], "sans_perte", "noms de reglages")
    s2, m2 = comparer(ctx, "reglages_valeurs", b["valeurs"], "egal", "valeurs structurantes")
    pire = "ECHEC" if "ECHEC" in (s1, s2) else ("ATTENTION" if "ATTENTION" in (s1, s2) else "OK")
    return pire, "noms: %s | valeurs: %s" % (m1, m2)


def c_modeles_commandes(ctx):
    m, e1 = bloc(ctx, "modeles")
    c, e2 = bloc(ctx, "commandes")
    if e1 or e2:
        return "ECHEC", e1 or e2
    s1, m1 = comparer(ctx, "modeles", m, "egal", "modeles")
    s2, m2 = comparer(ctx, "commandes", c, "egal", "commandes manage.py")
    pire = "ECHEC" if "ECHEC" in (s1, s2) else ("ATTENTION" if "ATTENTION" in (s1, s2) else "OK")
    return pire, "modeles: %s | commandes: %s" % (m1, m2)


REF_FICHIERS_LANCEUR = ["AOCEDA/Procfile", "AOCEDA/installer.py", "AOCEDA/installer.bat", "AOCEDA/lancer_aoceda.bat", "lancer_ngrok.bat",
                        "AOCEDA/pytest.ini", "AOCEDA/pyrightconfig.json", "AOCEDA/pyrefly.toml", "AOCEDA/mobile_app/capacitor.config.json",
                        "platformio.ini"]


def c_references_externes(ctx):
    """Chemins/modules cites dans Procfile, .bat, installer.py, pytest.ini, configs : doivent exister."""
    pb = []
    tous = set(git_files(ctx))
    rx_chemin = re.compile(r"""(?<![\w./\\-])((?:[A-Za-z0-9_\-]+[/\\])+[A-Za-z0-9_\-.]+(?:\.[A-Za-z0-9]+)?|[A-Za-z0-9_\-]+\.(?:py|bat|txt|ini|json|toml))(?![\w])""")
    for rel in REF_FICHIERS_LANCEUR:
        txt = lire(ctx, rel)
        if txt is None:
            pb.append("%s : fichier absent" % rel); continue
        dossier = os.path.dirname(rel)
        for m in set(rx_chemin.findall(txt)):
            c = m.replace("\\", "/")
            if c.startswith(("http", "www.", ".venv_local", "venv", "donnees_ia", "staticfiles", "media", "logs", "node_modules", ".env", "db.sqlite3",
                             "Scripts/", "bin/", "lib/", "Lib/", "dist/", "build/", "pio/")):
                continue
            if "*" in c or c.endswith("/"):
                continue
            cands = [os.path.normpath(os.path.join(dossier, c)).replace("\\", "/"), c]
            existe = any(x in tous or any(t.startswith(x + "/") for t in tous) or os.path.exists(os.path.join(ctx.depot, x)) for x in cands)
            if not existe and "/" in c:
                pb.append("%s cite '%s' introuvable" % (rel, c))
    # modules Python cites par Procfile : gunicorn aoceda.wsgi, celery -A aoceda
    pf = lire(ctx, "AOCEDA/Procfile") or ""
    for m in re.findall(r"gunicorn\s+([\w.]+)", pf):
        if not os.path.isfile(os.path.join(ctx.aoceda, m.replace(".", "/") + ".py")):
            pb.append("Procfile : module %s introuvable" % m)
    for m in re.findall(r"celery -A\s+(\w+)", pf):
        if not os.path.isfile(os.path.join(ctx.aoceda, m, "celery.py")):
            pb.append("Procfile : %s/celery.py introuvable" % m)
    # manage.py / DJANGO_SETTINGS_MODULE
    for rel in ("AOCEDA/manage.py", "AOCEDA/aoceda/wsgi.py", "AOCEDA/aoceda/asgi.py", "AOCEDA/aoceda/celery.py", "AOCEDA/pytest.ini"):
        txt = lire(ctx, rel) or ""
        for m in re.findall(r"DJANGO_SETTINGS_MODULE[\"']?\s*[,=]\s*[\"']?([\w.]+)", txt):
            if not os.path.isfile(os.path.join(ctx.aoceda, m.replace(".", "/") + ".py")):
                pb.append("%s : DJANGO_SETTINGS_MODULE=%s introuvable" % (rel, m))
    # pytest testpaths
    ini = lire(ctx, "AOCEDA/pytest.ini") or ""
    for m in re.findall(r"testpaths\s*=\s*(\S+)", ini):
        if not os.path.isdir(os.path.join(ctx.aoceda, m)):
            pb.append("pytest.ini : testpaths=%s introuvable" % m)
    pb = sorted(set(pb))
    st, msg = comparer(ctx, "references_externes", pb, "sans_nouveau", "reference(s) cassee(s) (bat/Procfile/ini)")
    return st, msg + " | actuels : %s" % tronque(" ; ".join(pb[:6]), 300)


def c_mobile(ctx):
    """Capacitor : l'app charge le site distant (webDir www) : toute modification d'URL / de chemin de session doit etre vue."""
    txt = lire(ctx, "AOCEDA/mobile_app/capacitor.config.json")
    if txt is None:
        return "ATTENTION", "capacitor.config.json absent"
    www = os.path.isdir(os.path.join(ctx.aoceda, "mobile_app", "www"))
    cfg = json.loads(txt)
    suivis = sorted(f for f in git_files(ctx) if f.startswith("AOCEDA/mobile_app/") and f.endswith((".js", ".html", ".json")) and "/android/" not in f
                    and "node_modules" not in f)
    st, msg = comparer(ctx, "mobile_fichiers", suivis + ["cfg:" + json.dumps(cfg, sort_keys=True)], "egal", "fichiers/config mobile")
    return st, msg + " | webDir=%s (www present: %s)" % (cfg.get("webDir"), www)


def c_db_intacte(ctx):
    p = os.path.join(ctx.aoceda, "db.sqlite3")
    return None


CONTROLES = [
    ("check", "(a) manage.py check", c_check),
    ("migrations_a_jour", "(b) makemigrations --check --dry-run = aucun changement", c_migrations_a_jour),
    ("showmigrations", "(c) showmigrations vs reference", c_showmigrations),
    ("urls", "(d) liste des URL (get_resolver) vs reference", c_urls),
    ("celery", "(e) taches Celery enregistrees + beat vs reference", c_celery),
    ("gabarits", "(f) gabarits : extends/include/static/url, <script>/<link> locaux, api JS", c_gabarits),
    ("statiques", "(f2) inventaire static/ sans perte", c_statiques),
    ("compilation", "(g) compilation de tous les .py suivis (apps, aoceda)", c_compilation),
    ("imports", "(g2) import reel de chaque module (hors tests/scripts)", c_imports),
    ("imports_internes", "(g3) imports internes, chaines 'apps.x.y' et patch() resolus statiquement", c_imports_internes),
    ("lint", "(h) ruff/pyflakes (si disponible) vs reference", c_lint),
    ("chemins_absolus", "(i) pas de chemin absolu C:\\Users, D:\\, /home/ (hors historique)", c_chemins_absolus),
    ("zones_protegees", "(j) zones protegees AGENTS.md section 4 inchangees vs tag", c_zones_protegees),
    ("fichiers_interdits", "(k) fichiers interdits / cles d'API dans index et diff", c_fichiers_interdits),
    ("tests", "(l) nombre de tests (par nom) sans perte vs reference", c_tests),
    ("asgi", "(m) ASGI/Daphne : route WebSocket live, protocoles, daphne en tete", c_asgi),
    ("reglages", "(n) reglages Django structurants vs reference", c_reglages),
    ("modeles_commandes", "(o) modeles et commandes manage.py vs reference", c_modeles_commandes),
    ("references_externes", "(p) chemins cites par Procfile/.bat/installer/ini existent", c_references_externes),
    ("mobile", "(q) Capacitor : config + sources mobiles vs reference", c_mobile),
]


def main():
    ap = argparse.ArgumentParser(description="Le Gardien : controle de non-regression rapide")
    ap.add_argument("--depot", default=os.getcwd())
    ap.add_argument("--tag", default=TAG_DEFAUT)
    ap.add_argument("--reference-dir", default=REF_DIR_DEFAUT)
    ap.add_argument("--enregistrer-reference", action="store_true")
    ap.add_argument("--autoriser", action="append", default=[], help="chemin/motif git autorise a changer en zone protegee")
    ap.add_argument("--seulement", default="")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--json", default="", help="ecrit le resultat en JSON")
    a = ap.parse_args()
    if a.liste:
        for n, l, _ in CONTROLES:
            print("%-20s %s" % (n, l))
        return 0
    ctx = Ctx()
    rc, out, err = run(["git", "rev-parse", "--show-toplevel"], os.path.abspath(a.depot), timeout=30)
    if rc != 0:
        print("ECHEC : %s n'est pas un depot Git" % a.depot)
        return 2
    ctx.depot = os.path.normpath(out.strip())
    ctx.aoceda = os.path.join(ctx.depot, "AOCEDA")
    ctx.tag = a.tag
    ctx.refdir = os.path.abspath(a.reference_dir)
    ctx.enregistrer = a.enregistrer_reference
    ctx.autoriser = a.autoriser
    ctx.django = None
    choisis = [x.strip() for x in a.seulement.split(",") if x.strip()]
    print("LE GARDIEN | depot=%s | python=%s | base=%s%s" % (ctx.depot, sys.executable, ctx.tag, " | ENREGISTREMENT DES REFERENCES" if ctx.enregistrer else ""))
    if ".venv_local" not in sys.executable.replace("\\", "/"):
        print("ATTENTION : ce Python n'est pas AOCEDA/.venv_local ; les controles Django peuvent echouer.")
    db = os.path.join(ctx.aoceda, "db.sqlite3")
    mt0 = os.path.getmtime(db) if os.path.exists(db) else None
    resultats = []
    echec = 0
    for nom, lib, fn in CONTROLES:
        if choisis and nom not in choisis:
            continue
        t0 = time.time()
        try:
            st, preuve = fn(ctx)
        except Exception as e:
            import traceback
            st, preuve = "ECHEC", "exception du controle : %s %s" % (e, traceback.format_exc()[-400:])
        dt = time.time() - t0
        if st == "ECHEC":
            echec += 1
        resultats.append({"controle": nom, "statut": st, "preuve": preuve})
        print("[%-9s] %s (%.1fs)\n            %s" % (st, lib, dt, tronque(preuve, TRONC).replace("\n", "\n            ")))
    mt1 = os.path.getmtime(db) if os.path.exists(db) else None
    if mt0 != mt1:
        print("[INFO     ] db.sqlite3 a ete modifiee pendant le controle (serveur/tests en cours ? ce script ne l'ecrit pas).")
    print("\nBILAN : %d controle(s), %d ECHEC, %d ATTENTION" % (len(resultats), echec, sum(1 for r in resultats if r["statut"] == "ATTENTION")))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(resultats, f, ensure_ascii=False, indent=1)
    return 1 if echec else 0


if __name__ == "__main__":
    sys.exit(main())
