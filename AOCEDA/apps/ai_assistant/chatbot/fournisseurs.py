"""Cerveau du chatbot : DeepSeek (API officielle), le moins cher, validé à l'étape 1.

Données du client (AOCEDA) : quand la question vient d'un client connecté (donnees_client.DONNEES), DeepSeek reçoit les
outils d'AOCEDA (appel d'outils, « function calling ») et lit les VRAIES données avant de répondre ; la lecture compte
comme un signe de vie dans la course (pas de relance inutile pendant qu'il lit).

Règles de fiabilité :
  - COURSE DE SECOURS : si DeepSeek n'a pas donné son 1er mot après RELAIS_S secondes, une 2e demande
    DeepSeek part EN PARALLÈLE ; la première qui parle gagne, l'autre est abandonnée (plus de jetons consommés) ;
  - une demande en erreur laisse aussitôt sa place ; une demande LENTE (pas de 1er mot en DELAI_PREMIER_MOT_S)
    libère aussi sa place mais reste en course jusqu'à DELAI_ABANDON_S ;
  - si la réponse s'interrompt EN PLEIN milieu : événement « recommencer » et on repart avec la suivante.

Le flux produit des événements (dict) :
  {"type": "fournisseur", "fournisseur", "modele"}   une demande démarre
  {"type": "outil", "nom", "label"[, "carte"]}        une donnée AOCEDA du client est lue (appel d'outil de DeepSeek) ;
                                                      "carte" : à montrer sur la page (confirmation de coupure)
  {"type": "morceau", "texte"}                        morceaux de la réponse (de la seule gagnante)
  {"type": "recommencer", "raison"}                   panne en pleine réponse : effacer et reprendre
  {"type": "fin", "texte", "fournisseur", "modele", "essais", "premier_mot_s", "total_s"}
  {"type": "erreur", "texte", "essais"}               toutes les demandes ont échoué
"""
import contextvars
import json
import queue
import re
import threading
import time

import requests

from .config import CONFIG

# Arrêt demandé par la page (bouton « Stop », onglet fermé) : threading.Event posé par le serveur pour la réponse en
# cours (serveur.FluxEvenements). Audit du 09/10/2026 : sans lui, DeepSeek continuait d'écrire (jetons payés) jusqu'au
# prochain morceau, et même jusqu'à 45 s quand la page coupait avant le 1er mot.
ARRET = contextvars.ContextVar("arret_reponse", default=None)


class Abandon(BaseException):
    """La page a coupé : la réponse est abandonnée. BaseException (comme GeneratorExit) : aucun « except Exception » ne la
    prend pour une panne (pas de secours lancé, pas d'erreur notée) ; les blocs « finally » font leur nettoyage."""


def verifier_arret():
    a = ARRET.get()
    if a is not None and a.is_set():
        raise Abandon()


RELAIS_S = 2.5              # sans 1er mot après 2,5 s (DeepSeek répond d'habitude en ~1 s), la relance part en parallèle
DELAI_PREMIER_MOT_S = 10     # au-delà, le candidat est « lent » : il libère sa place mais peut encore gagner
DELAI_ABANDON_S = 45         # au-delà, il est abandonné
DELAI_ENTRE_MORCEAUX_S = 25  # réponse figée plus longtemps = panne en pleine réponse
MAX_EN_COURSE = 2            # jamais plus de 2 candidats en même temps (coût borné)
MAX_MOTS_SORTIE = 900

class Echec(Exception):
    """Échec d'un fournisseur ; `avant_premier_mot` indique si la page n'a encore rien affiché."""
    def __init__(self, message, avant_premier_mot=True):
        super().__init__(message)
        self.avant_premier_mot = avant_premier_mot


# ── Producteurs bruts (bloquants) : ils renvoient des morceaux de texte ────────
MAX_TOURS_OUTILS = 4         # au plus 4 allers-retours de lecture de données par réponse


class Outil:
    """Signal (pas du texte) : le producteur lit une donnée du client. La course le prend pour un signe de vie.
    AOCEDA : `carte` = carte à montrer sur la page (ex. la confirmation Oui / Non d'une coupure)."""
    def __init__(self, nom, label, carte=None, cle=None):
        self.nom, self.label, self.carte, self.cle = nom, label, carte, cle      # cle : (outil, arguments), pour ne pas l'afficher deux fois

    def evenement(self):
        return {"type": "outil", "nom": self.nom, "label": self.label, **({"carte": self.carte} if self.carte else {})}


DELAI_CONNEXION_S = 20       # attente de la connexion à DeepSeek (avant le 13/11/2026 : 10 s, trop court sur un Internet lent)
ESSAIS_CONNEXION = 2         # une connexion qui échoue est retentée une fois (2e essai presque toujours instantané : connexion déjà chaude)


def _ouvrir_flux(corps, url=None, cle=None):
    """Ouvre la demande à DeepSeek. Si la CONNEXION échoue (délai dépassé, nom introuvable, coupure), on réessaie une fois :
    vu le 13/11/2026 sur le PC du propriétaire, un 1er essai à 15,5 s de connexion, puis 0,1 s aux suivants. Une erreur de
    lecture (réponse déjà commencée) n'est pas retentée ici : la relance de la course s'en charge.
    Pire cas : 2 x 20 s = 40 s, sous DELAI_ABANDON_S (45 s)."""
    def poster():
        return requests.post(url or CONFIG["DEEPSEEK_API_URL"], stream=True, timeout=(DELAI_CONNEXION_S, 40),
                             headers={"Authorization": f"Bearer {cle or CONFIG['DEEPSEEK_API_KEY']}"}, json=corps)
    for _ in range(ESSAIS_CONNEXION - 1):
        try:
            return poster()
        except requests.exceptions.ConnectionError:          # inclut ConnectTimeout
            verifier_arret()                                  # la page a coupé : on ne réessaie pas
            time.sleep(0.5)
    return poster()                                           # dernier essai : son erreur remonte à la course


def flux_deepseek(systeme, historique, outils=True, *, url=None, cle=None, modele=None, nom="DeepSeek"):
    """Morceaux de texte de la réponse ; `url`, `cle`, `modele`, `nom` : un autre fournisseur au même format OpenAI (relais, 13/11/2026) ; avec les données d'un client (donnees_client.courantes()), DeepSeek peut d'abord
    appeler les outils d'AOCEDA : on les exécute (lecture seule, pour CE client) et on lui renvoie les résultats, puis il
    écrit la réponse. Entre-temps, des Outil(nom, label) signalent la lecture."""
    from .donnees_client import courantes
    donnees = courantes() if outils else None
    messages = [{"role": "system", "content": systeme}] + [
        {"role": "user" if m["role"] == "user" else "assistant", "content": m["texte"]} for m in historique]
    for tour in range(MAX_TOURS_OUTILS + 1):
        if donnees is not None and tour == MAX_TOURS_OUTILS:    # dernier tour : plus d'outil, il doit répondre
            # sans cette consigne, DeepSeek veut encore un outil et écrit son appel EN TEXTE (balisage « <｜｜DSML｜｜ ... »), affiché brut
            # (arbitrage du 10/11/2026 : reproduit avec le vrai DeepSeek, 2 fois sur 3 au dernier tour)
            messages.append({"role": "user", "content": "(Message automatique) Tu as lu assez de données : réponds maintenant à la question "
                                                        "avec ce que tu as, sans appeler d'outil et sans écrire de balise."})
        corps = {"model": modele or CONFIG["DEEPSEEK_MODEL"], "messages": messages, "stream": True,
                 "temperature": 0.4, "max_tokens": MAX_MOTS_SORTIE * 2}
        if donnees is not None and tour < MAX_TOURS_OUTILS:     # dernier tour : plus d'outil, il doit répondre
            corps["tools"] = donnees.specs
        appels, balise, dit = {}, False, False
        with _ouvrir_flux(corps, url, cle) as r:
            if r.status_code != 200:
                if nom != "DeepSeek" and r.status_code in (401, 402, 403):
                    _mettre_hors_service(nom, modele)          # clé refusée ou solde épuisé : inutile de réessayer tout de suite
                raise RuntimeError(f"{nom} {r.status_code} : {r.text[:200]}")
            for ligne in r.iter_lines(decode_unicode=True):
                if not ligne or not ligne.startswith("data:"):
                    continue
                donnee = ligne[5:].strip()
                if donnee == "[DONE]":
                    break
                delta = json.loads(donnee)["choices"][0].get("delta", {})
                if delta.get("content") and not balise:
                    texte = delta["content"]
                    i = min((texte.find(m) for m in ("<｜", "DSML") if m in texte), default=-1)
                    if i >= 0:                              # filet : jamais de balisage d'appel d'outil dans la réponse affichée ou lue
                        texte, balise = texte[:i], True
                    if texte:
                        dit = True
                        yield texte
                for tc in delta.get("tool_calls") or []:     # l'appel arrive en morceaux : on le recolle
                    a = appels.setdefault(tc.get("index", 0), {"id": "", "nom": "", "arguments": ""})
                    f = tc.get("function") or {}
                    a["id"] = tc.get("id") or a["id"]
                    a["nom"] += f.get("name") or ""
                    a["arguments"] += f.get("arguments") or ""
        if not appels:
            if balise and not dit:
                yield "Je n'ai pas réussi à lire toutes vos données pour répondre. Pouvez-vous reformuler votre question ?"
            return
        appels = [appels[i] for i in sorted(appels)]
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": a["id"], "type": "function", "function": {"name": a["nom"], "arguments": a["arguments"] or "{}"}}
            for a in appels]})
        for a in appels:
            try:
                args = json.loads(a["arguments"] or "{}")
            except ValueError:
                args = {}
            resultat, label = donnees.executer(a["nom"], args if isinstance(args, dict) else {})
            # AOCEDA : la carte est pour la page seulement, pas pour DeepSeek ; sans carte de l'outil (coupure), la carte
            # des données lues, la même que dans l'appel Live (18/10/2026 : les chiffres se voient aussi dans le chat)
            carte = resultat.pop("carte_page", None) if isinstance(resultat, dict) else None
            if carte is None:
                from .live_agent import carte_outil
                carte = carte_outil(a["nom"], resultat)
            yield Outil(a["nom"], label, carte, cle=(a["nom"], a["arguments"] or "{}"))
            messages.append({"role": "tool", "tool_call_id": a["id"],
                             "content": json.dumps(resultat, ensure_ascii=False, default=str)})


# ── Relais : d'autres modèles, par OpenRouter, quand DeepSeek ne répond plus (13/11/2026) ──────────────────────────────
# Ordre = du moins cher au plus cher, chacun avec SA clé plafonnée (OPENROUTER_KEY_* du .env). Un relais ne part que quand
# les DeepSeek directs ont ÉCHOUÉ ou n'ont rien dit depuis DELAI_PREMIER_MOT_S (jamais pour une simple lenteur de 2,5 s : ça coûterait
# à chaque question). Un relais dont la clé est refusée ou le solde épuisé est ignoré pendant 10 minutes.
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
RELAIS_LLM = (  # (réglage de la clé, modèle OpenRouter)
    ("OPENROUTER_KEY_DEEPSEEK", "deepseek/deepseek-v4-flash"),          # le même DeepSeek, par un autre chemin
    ("OPENROUTER_KEY_GEMINI", "google/gemini-3.5-flash-lite"),
    ("OPENROUTER_API_KEY", "qwen/qwen3.7-flash"),
    ("OPENROUTER_KEY_CLAUDE", "anthropic/claude-haiku-4.5"),            # le plus cher : en dernier
)
HORS_SERVICE_S = 600
_hors_service = {}


def _mettre_hors_service(nom, modele):
    _hors_service[(nom, modele)] = time.time() + HORS_SERVICE_S


def _cle_relais(reglage):
    from django.conf import settings
    return (getattr(settings, reglage, "") or "").strip().strip('"')


def candidats(outils=True):
    """DeepSeek (la 2e demande ne part que si la 1re traîne ou échoue), puis les relais OpenRouter pour lesquels une clé existe.
    Chaque candidat : (fournisseur, modèle, ouvrir(systeme, historique) -> itérable de morceaux) ; `ouvrir.secours` = relais payant."""
    if not CONFIG["DEEPSEEK_API_KEY"]:
        return []
    m = CONFIG["DEEPSEEK_MODEL"]

    def ouvrir(systeme, historique):
        return flux_deepseek(systeme, historique, outils=outils)
    liste = [("DeepSeek", m, ouvrir), ("DeepSeek", f"{m} (relance)", ouvrir)]
    for reglage, modele in RELAIS_LLM:
        cle = _cle_relais(reglage)
        if not cle or _hors_service.get(("OpenRouter", modele), 0) > time.time():
            continue

        def ouvrir_relais(systeme, historique, cle=cle, modele=modele):
            return flux_deepseek(systeme, historique, outils=outils, url=URL_OPENROUTER, cle=cle, modele=modele, nom="OpenRouter")
        ouvrir_relais.secours = True
        liste.append(("OpenRouter", modele, ouvrir_relais))
    return liste


# ── Course de secours ─────────────────────────────────────────────────────────
class _Coureur:
    """Un candidat qui tourne dans son fil et dépose ses morceaux dans la file commune."""
    def __init__(self, fournisseur, modele, ouvrir, systeme, historique, file):
        self.fournisseur, self.modele, self.depart, self.lent = fournisseur, modele, time.time(), False
        self.arret = threading.Event()

        def travail():
            try:
                for x in ouvrir(systeme, historique):
                    if self.arret.is_set():
                        return                      # abandonné : on ferme le flux (plus de jetons consommés)
                    file.put((self, "outil", x) if isinstance(x, Outil) else (self, "morceau", x))
                file.put((self, "fin", None))
            except Exception as e:
                file.put((self, "erreur", e))
        # le fil garde le contexte de la question (données du client connecté : donnees_client.DONNEES)
        threading.Thread(target=contextvars.copy_context().run, args=(travail,), daemon=True).start()


def message_de_panne(erreurs, reseau):
    """Le message le plus HONNÊTE selon la panne (arbitrage du 10/11/2026 : « saturé, réessayez » pour un solde épuisé ou une clé
    refusée, où réessayer ne sert à rien)."""
    if reseau:
        return "Impossible de joindre le service de réponse : vérifiez la connexion Internet, puis réessayez."
    tout = " ".join(erreurs)
    if re.search(r"(?:DeepSeek|OpenRouter)\s+(?:401|402|403)\b", tout):       # clé refusée ou solde épuisé : rien à voir avec la charge, ce n'est pas passager
        return ("Le service de réponse n'est pas disponible pour le moment, et ce n'est pas passager : réessayer tout de suite "
                "ne servira à rien. Prévenez l'administrateur d'AOCEDA.")
    if re.search(r"(?:DeepSeek|OpenRouter)\s+429\b", tout):
        return "Le service de réponse reçoit trop de demandes. Réessayez dans une minute."
    return "Le service de réponse est saturé pour le moment. Réessayez dans quelques instants."


def repondre_flux(systeme, historique, liste=None, outils=True):
    """Générateur d'événements (voir en-tête). `liste` remplace candidats() (tests). `outils=False` : sans lecture des
    données du client (réponse générale)."""
    t0 = time.time()
    restants = list(liste if liste is not None else (candidats() if outils else candidats(outils=False)))
    if not restants and not CONFIG["DEEPSEEK_API_KEY"]:
        # AOCEDA : serveur installé sans clé (nouveau PC) -> le dire tel quel, pas « service saturé ». Vérifié APRÈS
        # la liste des candidats (vide sans clé) : un DeepSeek simulé (tests) répond même sans clé dans le .env
        yield {"type": "erreur", "essais": [], "texte": "L'assistant n'est pas encore configuré sur ce serveur : la clé "
               "DeepSeek (DEEPSEEK_API_KEY) manque dans le fichier .env d'AOCEDA (voir INSTALLATION.md)."}
        return
    file, essais, tous = queue.Queue(), [], []
    try:
        yield from _course(systeme, historique, restants, file, essais, tous, t0, set())
    finally:                                 # réponse arrêtée ou connexion coupée : plus aucun jeton consommé
        for c in tous:
            c.arret.set()


def _a_afficher(outil, deja_affiches):
    """Faux si CE MÊME outil, avec les MÊMES arguments, a déjà été montré pour cette question (la relance refait les mêmes lectures :
    4 lignes « Je lis vos données » au lieu de 2, 11/11/2026)."""
    if outil.cle is None:
        return True
    if outil.cle in deja_affiches:
        return False
    deja_affiches.add(outil.cle)
    return True


def _course(systeme, historique, restants, file, essais, tous, t0, deja_affiches):

    def noter(c, **info):
        essais.append({"fournisseur": c.fournisseur, "modele": c.modele, "duree_s": round(time.time() - c.depart, 2), **info})

    while True:
        # ── Phase 1 : trouver un gagnant (le premier qui donne un 1er mot) ──
        en_course, dernier_depart, gagnant, premier = [], 0.0, None, None
        while gagnant is None:
            verifier_arret()                              # la page a coupé : plus aucune demande ne part ni n'attend
            maintenant = time.time()
            actifs = [c for c in en_course if not c.lent]       # un candidat lent ne bloque plus de place
            relais_payant = bool(restants) and getattr(restants[0][2], "secours", False)      # relais payant : seulement si plus rien n'est actif
            if restants and len(actifs) < MAX_EN_COURSE and (not actifs if relais_payant else (not actifs or maintenant - dernier_depart >= RELAIS_S)):
                f, m, ouvrir = restants.pop(0)
                en_course.append(_Coureur(f, m, ouvrir, systeme, historique, file))
                tous.append(en_course[-1])
                dernier_depart = maintenant
                yield {"type": "fournisseur", "fournisseur": f, "modele": m}
            if not en_course:
                # message HONNÊTE : sans connexion Internet, dire « saturé » induit en erreur (vu le 29/09/2026)
                erreurs = [e.get("erreur", "") for e in essais]
                reseau = bool(erreurs) and all(any(m in x for m in ("NameResolution", "ConnectTimeout", "ConnectionError",
                                                                    "Max retries", "getaddrinfo", "Connection refused"))
                                               for x in erreurs)
                yield {"type": "erreur", "essais": essais, "texte": message_de_panne(erreurs, reseau)}
                return
            try:
                c, genre, valeur = file.get(timeout=0.1)
            except queue.Empty:
                for c in en_course:
                    if not c.lent and time.time() - c.depart > DELAI_PREMIER_MOT_S:
                        c.lent, dernier_depart = True, 0.0           # le suivant part, celui-ci reste en course
                for c in [c for c in en_course if time.time() - c.depart > DELAI_ABANDON_S]:
                    c.arret.set(); en_course.remove(c)
                    noter(c, erreur=f"abandonné : pas de 1er mot en {DELAI_ABANDON_S} s")
                continue
            if c not in en_course:
                continue                              # message d'un candidat déjà abandonné
            if genre == "outil":                      # il lit les données du client : il est bien vivant
                c.depart = dernier_depart = time.time()
                if _a_afficher(valeur, deja_affiches):
                    yield valeur.evenement()
                continue
            if genre == "morceau" and valeur.strip():
                gagnant, premier = c, valeur
            elif genre == "morceau":
                continue                              # espaces seuls : on attend la suite
            else:                                     # erreur, ou fin sans aucun texte
                en_course.remove(c); dernier_depart = 0.0   # sa place se libère : le suivant part tout de suite
                noter(c, erreur=str(valeur)[:160] if genre == "erreur" else "réponse vide")
        for c in en_course:
            if c is not gagnant:
                c.arret.set()
                noter(c, abandonne=f"plus lent que {gagnant.fournisseur} {gagnant.modele}")

        # ── Phase 2 : diffuser la réponse du gagnant ──
        premier_mot_s = round(time.time() - t0, 2)
        texte = premier
        yield {"type": "morceau", "texte": premier}
        panne, limite = None, time.time() + DELAI_ENTRE_MORCEAUX_S
        while True:
            verifier_arret()
            try:
                c, genre, valeur = file.get(timeout=0.25)     # attente courte : un arrêt de la page est vu tout de suite
            except queue.Empty:
                if time.time() > limite:
                    panne = "réponse figée"; break
                continue
            if c is not gagnant:
                continue
            limite = time.time() + DELAI_ENTRE_MORCEAUX_S
            if genre == "outil":
                if _a_afficher(valeur, deja_affiches):
                    yield valeur.evenement()
            elif genre == "morceau":
                texte += valeur
                yield {"type": "morceau", "texte": valeur}
            elif genre == "fin":
                break
            else:
                panne = str(valeur)[:160]; break
        if panne is None:
            noter(gagnant, ok=True)
            yield {"type": "fin", "texte": texte.strip(), "fournisseur": gagnant.fournisseur, "modele": gagnant.modele,
                   "essais": essais, "premier_mot_s": premier_mot_s, "total_s": round(time.time() - t0, 2)}
            return
        gagnant.arret.set()
        noter(gagnant, erreur=f"interrompu en pleine réponse : {panne}")
        yield {"type": "recommencer", "raison": f"{gagnant.fournisseur} s'est interrompu en pleine réponse, reprise avec le suivant"}
