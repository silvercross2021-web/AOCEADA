"""TOUS les services dont l'assistant dépend, en une liste structurée (Options > Crédits des services, 13/11/2026).

Pour chaque service : ce qu'il fait, son RÔLE (principal, relais « de quoi » et dans quel ordre, ou local), son ÉTAT (ok / attention /
ko / inactif / inconnu), le crédit quand le service permet de le lire, et sinon la nature de sa limite (gratuit, quota du jour, solde
visible seulement chez le fournisseur). Jamais une clé. Rien n'est inventé : un service qu'on ne peut pas sonder sans le payer
(voix, traduction) est « inconnu » tant qu'il n'a pas été utilisé depuis le démarrage du serveur, puis son dernier essai est montré.

`construire()` ne fait AUCUN appel réseau : les soldes lui sont donnés (lus en parallèle par credits.py), ce qui le rend testable.
"""
import time

from django.conf import settings

SEUIL_BAS_USD = 0.05          # un relais OpenRouter sous ce reste est « presque épuisé »
SEUIL_BAS_DEEPSEEK_USD = 1.0
SEUIL_BAS_GPU_USD = 3.0

GROUPES = ("Réponses du chat (écrit et vocal)", "Appel vocal en direct", "Voix (lecture à voix haute)",
           "Traduction vers le dioula, le baoulé et le wolof", "Écoute du micro (sur le serveur)", "Autres services")


def _hhmm(t):
    return time.strftime("%H:%M", time.localtime(t))


def _svc(groupe, id, nom, fonction, role, etat, detail, relais_de=None, rang=None, credit=None, mesure=None, sans_relais=False):
    return {"groupe": groupe, "id": id, "nom": nom, "fonction": fonction, "role": role, "relais_de": relais_de, "rang": rang,
            "etat": etat, "detail": detail, "credit": credit, "mesure": mesure, "sans_relais": sans_relais}


def _credit(restant, sur=None, nature="solde"):
    return {"restant": None if restant is None else round(float(restant), 3), "devise": "USD",
            "sur": None if sur is None else round(float(sur), 2), "nature": nature}


def _dernier_essai(noms, essais):
    """Le plus récent essai d'une voix parmi ses noms de moteur : (état, détail)."""
    vus = [essais[n] for n in noms if n in essais]
    if not vus:
        return "inconnu", "pas encore utilisée depuis le démarrage du serveur"
    e = max(vus, key=lambda x: x["t"])
    if e["ok"]:
        return "ok", f"dernier essai réussi à {_hhmm(e['t'])}"
    return "attention", f"dernier essai en échec à {_hhmm(e['t'])}" + (f" ({e['raison']})" if e.get("raison") else "")


def _traducteur(e):
    """(état, détail) d'un traducteur à partir de dioula_relais.etat()."""
    if not e:
        return "inconnu", "état inconnu"
    if not e.get("disponible", True):
        return "attention", "coupé quelques minutes après plusieurs pannes de suite : l'autre traducteur prend la suite"
    if e.get("pannes"):
        return "attention", f"{e['pannes']} panne(s) de suite, encore essayé"
    if e.get("dernier_ok"):
        return "ok", f"dernière traduction réussie à {_hhmm(e['dernier_ok'])}"
    return "inconnu", "pas encore utilisé depuis le démarrage du serveur"


def _modeles_locaux(dossier_modeles=None):
    """{nom du modèle: (description, présent)} d'après le catalogue de installer_modeles_ia (tailles seulement, rien n'est lu en entier)."""
    from pathlib import Path
    from .config import MODELES
    from ..management.commands.installer_modeles_ia import CATALOGUE
    racine = Path(dossier_modeles) if dossier_modeles else MODELES
    sortie = {}
    for nom, (description, _source, fichiers) in CATALOGUE.items():
        dossier = racine / nom
        sortie[nom] = (description, all((dossier / f).is_file() and (dossier / f).stat().st_size == t for f, (t, _s) in fichiers.items()))
    return sortie


def construire(ds, orr, gpu, relais, live=None, traducteurs=None, essais=None, kooma=None, locaux=None, maintenant=None):
    """Liste structurée de tous les services. Voir l'en-tête du module.
    ds : crédits.DeepSeek ; orr : crédits OpenRouter ({ok, restant, achete, utilise, agent}) ; gpu : voix_gpu.credit() ;
    relais : un dict par relais du chat {modele, configure, ok, restant, plafond, hors_service, raison} dans l'ordre de fournisseurs.RELAIS_LLM ;
    live : live_agent.etat() ; traducteurs : dioula_relais.etat() ; essais : voix.DERNIERS_ESSAIS ; kooma : voix_kooma.USAGE ;
    locaux : _modeles_locaux()."""
    ds, orr, gpu = ds or {}, orr or {}, gpu or {}
    traducteurs, essais, kooma, locaux = traducteurs or {}, essais or {}, kooma or {}, locaux or {}
    liste = []
    G = GROUPES

    # ── 1. Réponses du chat ────────────────────────────────────────────────────────────────────────────────
    if not settings.DEEPSEEK_API_KEY:
        etat, detail, cr = "inactif", "clé absente du fichier .env (DEEPSEEK_API_KEY) : l'assistant ne peut pas répondre", None
    elif not ds.get("ok"):
        etat, detail, cr = "inconnu", ds.get("raison") or "solde illisible", None
    else:
        cr = _credit(ds["solde"], nature="solde du compte")
        if not ds.get("disponible"):
            etat, detail = "ko", "solde épuisé : l'assistant ne peut plus répondre par DeepSeek (les relais prennent la suite)"
        elif ds["solde"] < SEUIL_BAS_DEEPSEEK_USD:
            etat, detail = "attention", "solde bas : pensez à recharger"
        else:
            etat, detail = "ok", "répond aux questions (la 1re demande, puis une relance si elle traîne)"
    liste.append(_svc(G[0], "deepseek", "DeepSeek", "Écrit toutes les réponses, appelle les outils de lecture des données", "principal",
                      etat, detail, credit=cr, mesure="credit" if cr else None))
    for rang, r in enumerate(relais or [], 1):
        modele = r.get("modele", "")
        nom = {"deepseek/deepseek-v4-flash": "DeepSeek V4 Flash (par OpenRouter)", "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite (par OpenRouter)",
               "qwen/qwen3.7-flash": "Qwen 3.7 Flash (par OpenRouter)", "anthropic/claude-haiku-4.5": "Claude Haiku 4.5 (par OpenRouter)"}.get(modele, modele)
        if not r.get("configure"):
            etat, detail, cr = "inactif", "pas de clé : ce relais n'est pas en place", None
        elif r.get("hors_service"):
            etat, detail, cr = "ko", "clé refusée ou solde épuisé : ignoré 10 minutes", None
        elif not r.get("ok"):
            etat, detail, cr = "inconnu", r.get("raison") or "crédit illisible", None
        else:
            cr = _credit(r["restant"], r.get("plafond"), "plafond de la clé")
            if r["restant"] <= 0:
                etat, detail = "ko", "crédit épuisé"
            elif r["restant"] < SEUIL_BAS_USD:
                etat, detail = "attention", "crédit presque épuisé"
            else:
                etat, detail = "ok", "en réserve : ne répond que si DeepSeek est en panne ou muet pendant 10 s"
        liste.append(_svc(G[0], f"relais{rang}", nom, "Répond à la place de DeepSeek, avec les mêmes outils", "relais", etat, detail,
                          relais_de="DeepSeek", rang=rang, credit=cr, mesure="credit" if cr else None))
    if orr.get("ok"):
        liste.append(_svc(G[0], "openrouter", "Compte OpenRouter", "Alimente les clés des relais (et celle de l'appel en direct)", "compte",
                          "ok" if orr["restant"] > SEUIL_BAS_USD else "attention",
                          f"{orr['utilise']:.2f} $ utilisés sur {orr['achete']:.2f} $ achetés", credit=_credit(orr["restant"], orr["achete"], "solde du compte"),
                          mesure="credit"))

    # ── 2. Appel vocal en direct ──────────────────────────────────────────────────────────────────────────
    reserves = (live or {}).get("reserves") or []
    reste_s = (live or {}).get("remise_a_zero_dans_s")
    for i, m in enumerate(reserves):
        comptes = m.get("comptes") or []
        dispo, total = sum(1 for c in comptes if c.get("disponible")), len(comptes)
        retours = [c.get("retour_dans_s") or 0 for c in comptes if c.get("etat") == "repos"]
        appels, minutes = sum(c.get("appels_jour", 0) for c in comptes), round(sum(c.get("minutes_jour", 0) for c in comptes), 1)
        if total == 0:
            etat, detail = "inactif", "aucune clé Gemini dans le fichier .env"
        elif dispo == total:
            etat = "ok"
            detail = f"{dispo} compte{'s' if dispo > 1 else ''} sur {total} disponible{'s' if dispo > 1 else ''}"
        elif dispo:
            etat, detail = "attention", f"{dispo} compte{'s' if dispo > 1 else ''} sur {total} disponible{'s' if dispo > 1 else ''} (les autres ont atteint leur limite du jour)"
        else:
            etat = "attention" if retours else "ko"
            detail = ("limite du jour atteinte sur tous les comptes" + (f", retour dans environ {max(1, round(min(retours) / 60))} min" if retours else "")
                      if retours else "accès refusé sur tous les comptes")
        if appels:
            detail += f" · {appels} appel{'s' if appels > 1 else ''}, {minutes} min aujourd'hui"
        from . import live_agent
        etiquette = live_agent.capacites(m.get("modele", ""))["etiquette"]
        if i == 0:
            premier = f"Gemini {etiquette}"
        principal = i == 0
        if not principal and etat == "ok":
            detail = "en réserve : " + detail
        liste.append(_svc(G[1], f"live{i}", f"Gemini {etiquette}", "Voix de l'appel en direct" if principal else "Voix de l'appel en direct, si le meilleur modèle est limité",
                          "principal" if principal else "relais", etat, detail, relais_de=None if principal else premier, rang=None if principal else i,
                          mesure="quota", credit=None))
    if orr.get("agent") and orr["agent"].get("plafond") is not None:
        a = orr["agent"]
        restant = a.get("restant")
        etat = "ko" if (restant is not None and restant <= 0) else "attention" if (restant is not None and restant < SEUIL_BAS_USD) else "ok"
        liste.append(_svc(G[1], "agent", "Qwen 3.7 Flash (clé de l'agent)", "Planifie les actions de l'appel (cliquer, écrire) si DeepSeek ne répond pas",
                          "relais", etat, "en réserve" if etat == "ok" else "crédit bas ou épuisé", relais_de="DeepSeek (actions de l'appel)", rang=1,
                          credit=_credit(restant, a.get("plafond"), "plafond de la clé"), mesure="credit"))
    elif getattr(settings, "OPENROUTER_KEY_AGENT", ""):
        liste.append(_svc(G[1], "agent", "Qwen 3.7 Flash (clé de l'agent)", "Planifie les actions de l'appel (cliquer, écrire) si DeepSeek ne répond pas",
                          "relais", "inconnu", "crédit illisible", relais_de="DeepSeek (actions de l'appel)", rang=1))

    # ── 3. Voix ────────────────────────────────────────────────────────────────────────────────────────────
    from . import voix as _voix
    etat, detail = _dernier_essai(["Microsoft (edge-tts)"], essais)
    liste.append(_svc(G[2], "voix_fr", "Microsoft (edge-tts) · français et anglais", "Lit les réponses en français et en anglais", "principal", etat, detail, mesure="gratuit"))
    kokoro = locaux.get("kokoro")
    if kokoro is None:
        etat, detail = "inconnu", "installation non vérifiée"
    elif not kokoro[1]:
        etat, detail = "inactif", "modèle non installé (manage.py installer_modeles_ia) : pas de secours local"
    else:
        etat, detail = _dernier_essai(["Kokoro (serveur)"], essais)
        detail = "installée sur le serveur, gratuite · " + detail if etat == "inconnu" else detail
        etat = "ok" if etat == "inconnu" else etat
    liste.append(_svc(G[2], "voix_kokoro", "Kokoro · français et anglais", "Lit à la place de Microsoft s'il ne répond pas", "relais", etat, detail,
                      relais_de="Microsoft (edge-tts)", rang=1, mesure="gratuit"))
    etat, detail = _dernier_essai(["Djelia (voix bambara)"], essais)
    liste.append(_svc(G[2], "voix_djelia", "Djelia · voix dioula", "Lit les réponses en dioula (voix bambara, très proche) · démo publique sans clé, sans garantie de service", "principal", etat, detail,
                      mesure="gratuit", credit=None))
    if not getattr(settings, "KOOMA_API_KEY", ""):
        etat, detail = "inactif", "pas de clé (KOOMA_API_KEY) : pas de relais pour la voix dioula"
    else:
        etat, detail = _dernier_essai(["Kooma (voix bambara, relais)"], essais)
        if kooma.get("appels"):
            detail += f" · {kooma['caracteres']} caractères lus depuis le démarrage (solde visible dans la console Kooma)"
        elif etat == "inconnu":
            detail = "en réserve, pas encore utilisée · solde visible seulement dans la console Kooma"
            etat = "ok"
    liste.append(_svc(G[2], "voix_kooma", "Kooma · voix dioula", "Lit à la place de Djelia s'il ne répond pas", "relais", etat, detail,
                      relais_de="Djelia (voix dioula)", rang=1, mesure="non_lisible"))
    noms_baoule = [m[0] for m in _voix.MOTEURS_BAOULE.values()]
    if not gpu.get("configure"):
        etat, detail, cr = "inactif", "GPU non configuré : la voix baoulé se fait sur le PC (très lente)", None
    elif gpu.get("plafond_atteint"):
        etat, detail, cr = "attention", "plafond de dépense du jour atteint : voix sur le PC jusqu'à demain", (_credit(gpu["restant_usd"], gpu.get("offert_usd"), "crédit offert") if gpu.get("ok") else None)
    elif gpu.get("ok"):
        cr = _credit(gpu["restant_usd"], gpu.get("offert_usd"), "crédit offert")
        etat = "attention" if gpu["restant_usd"] < SEUIL_BAS_GPU_USD else "ok"
        detail = ("crédit bas · " if etat == "attention" else "") + ("machine allumée" if gpu.get("eveille") else "machine en veille (la 1re voix prend ~35 s)")
    else:
        cr, etat, detail = None, "inconnu", gpu.get("raison") or "crédit illisible"
    if gpu.get("derniere_erreur"):
        detail += f" · dernier incident : {gpu['derniere_erreur']}"
    liste.append(_svc(G[2], "voix_baoule", "Cerebrium · voix baoulé (GPU)", "Lit les réponses en baoulé", "principal", etat, detail, credit=cr,
                      mesure="credit" if cr else None))
    from . import voix_baoule
    try:
        installe = voix_baoule.atelier_installe()
    except Exception:
        installe = False
    liste.append(_svc(G[2], "voix_baoule_pc", "OmniVoice sur le PC · voix baoulé", "Lit à la place du GPU s'il ne répond pas (3 à 4 min par phrase)", "relais",
                      "ok" if installe else "inactif", "installé sur ce PC, très lent" if installe else "non installé sur ce PC : sans GPU, pas de voix baoulé",
                      relais_de="Cerebrium (voix baoulé)", rang=1, mesure="gratuit"))
    if not gpu.get("configure"):
        etat, detail = "inactif", "GPU non configuré : pas de voix wolof"
    else:
        etat, detail = _dernier_essai(["Oolel-Voices (Wolof)"], essais)
        detail += " · même compte et même crédit que la voix baoulé"
    liste.append(_svc(G[2], "voix_wolof", "Cerebrium · voix wolof (GPU)", "Lit les réponses en wolof", "principal", etat, detail,
                      mesure="credit" if gpu.get("ok") else None, credit=_credit(gpu["restant_usd"], gpu.get("offert_usd"), "crédit offert") if gpu.get("ok") else None,
                      sans_relais=True))

    # ── 4. Traduction ──────────────────────────────────────────────────────────────────────────────────────
    etat, detail = _traducteur(traducteurs.get("djelia"))
    liste.append(_svc(G[3], "trad_djelia", "Djelia · traduction dioula", "Traduit les réponses du français vers le dioula (démo publique sans clé, sans garantie de service)", "principal", etat, detail, mesure="gratuit"))
    etat, detail = _traducteur(traducteurs.get("google"))
    liste.append(_svc(G[3], "trad_google_dyu", "Google Traduction · dioula", "Traduit à la place de Djelia s'il ne répond pas", "relais", etat, detail,
                      relais_de="Djelia (traduction dioula)", rang=1, mesure="gratuit"))
    liste.append(_svc(G[3], "trad_google", "Google Traduction · baoulé et wolof", "Traduit les réponses vers le baoulé et le wolof (et lit leur sens)", "principal",
                      etat, detail, mesure="gratuit", sans_relais=True))

    # ── 5. Écoute du micro ────────────────────────────────────────────────────────────────────────────────
    quoi = {"whisper/tiny": "Whisper tiny · langue parlée", "whisper/small": "Whisper small · français et anglais",
            "omnilingual-1b-ctc-v2-int8": "Omnilingual · écoute du dioula", "omniasr-300m-baoule-int8": "omniASR · écoute du baoulé",
            "whisper_small_wolof_onnx": "Whisper wolof · écoute du wolof"}
    for cle, nom in quoi.items():
        if cle not in locaux:
            continue
        present = locaux[cle][1]
        liste.append(_svc(G[4], "stt_" + cle.replace("/", "_"), nom, locaux[cle][0].replace("micro : ", "").capitalize(), "local",
                          "ok" if present else "ko", "installé sur le serveur, gratuit, sans Internet" if present else
                          "modèle absent (manage.py installer_modeles_ia) : cette langue n'est pas reconnue à la voix",
                          mesure="gratuit"))

    # ── 6. Autres ─────────────────────────────────────────────────────────────────────────────────────────
    cles_gemini = list(dict.fromkeys(c for c in [getattr(settings, "GEMINI_API_KEY", ""), *list(getattr(settings, "GEMINI_CLES_LIVE", []) or [])] if c))
    from . import facture
    versions = " → ".join(m.replace("gemini-", "") for m in facture.MODELES)
    liste.append(_svc(G[5], "facture", "Gemini · lecture des factures jointes", f"Extrait les chiffres d'une facture (versions essayées dans l'ordre : {versions})", "principal",
                      "ok" if cles_gemini else "inactif", f"{len(cles_gemini)} clé{'s' if len(cles_gemini) > 1 else ''} Gemini" if cles_gemini else "aucune clé Gemini",
                      mesure="quota"))
    meteo = getattr(settings, "METEO_EN_LIGNE", True)
    liste.append(_svc(G[5], "meteo", "Open-Meteo · température", "Température prévue pour la prévision de consommation", "principal",
                      "ok" if meteo else "inactif", "gratuit, sans clé" if meteo else "désactivé dans les réglages", mesure="gratuit"))

    groupes = []
    for titre in GROUPES:
        services = [s for s in liste if s["groupe"] == titre]
        if services:
            groupes.append({"titre": titre, "services": services})
    comptes = {e: sum(1 for s in liste if s["etat"] == e) for e in ("ok", "attention", "ko", "inactif", "inconnu")}
    alertes = [{"nom": s["nom"], "etat": s["etat"], "detail": s["detail"]} for s in liste if s["etat"] in ("ko", "attention")]
    return {"groupes": groupes, "resume": {"total": len(liste), **comptes}, "alertes": alertes,
            "remise_a_zero_live_s": reste_s}
