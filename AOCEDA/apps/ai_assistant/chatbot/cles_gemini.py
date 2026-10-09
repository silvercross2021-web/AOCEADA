"""RÉSERVES de l'agent Live : chaque couple (modèle Gemini, compte Gemini) a son propre quota chez Google (mesuré le
01/10/2026 : « GenerateRequestsPerDayPerProjectPerModel » -> limite PAR COMPTE ET PAR MODÈLE). On les utilise dans
l'ordre « meilleur modèle d'abord » (choix du client) :

    modèle 1 sur les comptes 1, 2, 3, 4  ->  modèle 2 sur les comptes 1, 2, 3, 4  ->  ...

  - limite atteinte (quota) : ce couple se repose (jusqu'à minuit heure du Pacifique pour une limite du jour, heure de
    remise à zéro chez Google ; sinon PAUSE_LIMITE_S) ; l'appel continue sur le couple suivant ;
  - clé refusée (« API key not valid », 401) : le compte est écarté pour TOUS les modèles ;
  - accès refusé (403 sans que la clé soit en cause : modèle réservé à certains comptes) ou réglage refusé à la
    connexion (option refusée, modèle retiré) : CE COUPLE seulement est écarté pendant PAUSE_REFUS_S (un modèle peut
    être ouvert sur un compte et pas sur un autre) ; un réglage refusé EN PLEINE session (image trop lourde...) ne
    l'écarte pas : l'appel change seulement de réserve ;
  - autre erreur (coupure réseau, erreur interne 1011) : passagère, le couple reste utilisable.

Google ne donne JAMAIS le quota restant (aucun en-tête) : on ne sait qu'une limite est atteinte qu'en la touchant (le
message dit alors laquelle). On tient donc notre propre compte de l'usage du jour (appels, minutes), par couple, gardé
sur le disque (cache/live_reserves.json) avec les repos en cours : un redémarrage du serveur ne les oublie pas.
Les clés ne sont jamais écrites : seulement une empreinte (12 caractères d'un hachage) pour reconnaître le compte.
"""
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

PAUSE_LIMITE_S = 120            # limite courte (par minute) : le couple revient 2 min plus tard
PAUSE_REFUS_S = 6 * 3600        # accès ou réglage refusé : réessayé 6 h plus tard (un modèle peut être ouvert entre-temps)
# Classement sur le CODE de l'erreur (attribut « code » de google.genai, ou nombre en tête du message des fermetures
# WebSocket : « 1007 None. API key not valid ») et sur des expressions précises ; jamais sur un nombre trouvé n'importe où
# (« request 7f4013ab » n'est pas une erreur 401) ni sur « exceeded » seul (« Deadline exceeded »).
_QUOTA = ("resource_exhausted", "quota", "rate limit", "ratelimit", "too many requests")
_CLE_REFUSEE = ("api key not valid", "api_key_invalid", "invalid api key", "api key expired")
_INVALIDE = _CLE_REFUSEE + ("permission_denied", "unauthenticated")
# erreur de RÉGLAGE : propre au modèle (option refusée, modèle retiré) -> ce modèle est écarté, on passe au suivant
_REGLAGE = ("invalid argument", "invalid_argument", "is not found", "not found for api version", "is not supported",
            "must be specified")
_CODE_EN_TETE = re.compile(r"^\s*(\d{3,4})\b")
_VALEUR_QUOTA = re.compile(r"""quotaValue['"]?\s*[:=]\s*['"]?(\d+)""")


def _code(erreur):
    c = getattr(erreur, "code", None)
    if isinstance(c, int):
        return c
    m = _CODE_EN_TETE.match(str(erreur))
    return int(m.group(1)) if m else None


def classer(erreur):
    """« quota », « invalide », « reglage » ou « passagere »."""
    t, code = str(erreur).lower(), _code(erreur)
    if code == 429 or any(m in t for m in _QUOTA):
        return "quota"
    if code in (401, 403) or any(m in t for m in _INVALIDE):
        return "invalide"
    if code in (400, 404, 1007, 1008) or any(m in t for m in _REGLAGE):
        return "reglage"
    return "passagere"


def _decalage_pacifique(m):
    """Décalage de Los Angeles (heure d'été : 2e dimanche de mars -> 1er dimanche de novembre), calculé à la main :
    Windows n'a pas toujours la base des fuseaux horaires (tzdata)."""
    def dimanche(annee, mois, rang):
        d = datetime(annee, mois, 1, tzinfo=timezone.utc)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (rang - 1))
    ete = dimanche(m.year, 3, 2) + timedelta(hours=10) <= m < dimanche(m.year, 11, 1) + timedelta(hours=9)
    return timedelta(hours=-7 if ete else -8)


def minuit_pacifique(maintenant=None):
    """Prochain minuit à Los Angeles (heure de remise à zéro des quotas Google), en secondes depuis 1970."""
    m = datetime.fromtimestamp(maintenant if maintenant is not None else time.time(), timezone.utc)
    d = _decalage_pacifique(m)
    minuit = (m + d + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (minuit - d).timestamp()


def jour_pacifique(maintenant=None):
    """Jour de quota Google en cours (AAAA-MM-JJ, heure du Pacifique) : les compteurs du jour repartent à zéro avec lui."""
    m = datetime.fromtimestamp(maintenant if maintenant is not None else time.time(), timezone.utc)
    return (m + _decalage_pacifique(m)).date().isoformat()


def empreinte(cle):
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()[:12]


class Reserves:
    def __init__(self, cles, modeles, fichier=None):
        vues = []
        self.cles = [k for k in cles if k and k not in vues and not vues.append(k)]
        self.modeles = list(dict.fromkeys(modeles))
        self.fichier = fichier
        self._verrou = threading.Lock()
        self._invalides = set()                              # comptes dont la CLÉ est refusée (tous modèles)
        # (m, c) -> {"jusqu_a", "raison", "genre"} ; genre : « quota » (limite), « refus » (accès), « reglage »
        self._repos, self._usage, self._jour = {}, {}, jour_pacifique()
        self._charger()

    def __len__(self):
        return len(self.modeles) * len(self.cles)

    # -- disque (sans les clés : empreintes seulement)
    def _id(self, m, c):
        return f"{self.modeles[m]}|{empreinte(self.cles[c])}"

    def _charger(self):
        if not self.fichier or not self.fichier.exists():
            return
        try:
            d = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        index = {self._id(m, c): (m, c) for m in range(len(self.modeles)) for c in range(len(self.cles))}
        maintenant = time.time()
        for k, v in (d.get("repos") or {}).items():
            if k in index and v.get("jusqu_a", 0) > maintenant:
                self._repos[index[k]] = {"jusqu_a": v["jusqu_a"], "raison": v.get("raison") or "limite atteinte",
                                         "genre": v.get("genre") or "quota"}
        if d.get("jour") == self._jour:
            for k, v in (d.get("usage") or {}).items():
                if k in index:
                    self._usage[index[k]] = {"appels": int(v.get("appels", 0)), "secondes": float(v.get("secondes", 0)),
                                             "limites": int(v.get("limites", 0))}

    def _sauver(self):
        if not self.fichier:
            return
        d = {"jour": self._jour, "repos": {self._id(*k): v for k, v in self._repos.items()},
             "usage": {self._id(*k): v for k, v in self._usage.items()}}
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.fichier.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.fichier)
        except OSError:
            pass                                          # l'affichage seul en pâtit, jamais l'appel

    def _nouveau_jour(self):
        j = jour_pacifique()
        if j != self._jour:                               # minuit heure du Pacifique : compteurs du jour remis à zéro
            self._jour, self._usage = j, {}

    def _usage_de(self, m, c):
        return self._usage.setdefault((m, c), {"appels": 0, "secondes": 0.0, "limites": 0})

    # -- choix et signalements
    def _repos_actif(self, m, c, maintenant):
        r = self._repos.get((m, c))
        return r if r and r["jusqu_a"] > maintenant else None

    def disponible(self, m, c, maintenant=None):
        maintenant = maintenant if maintenant is not None else time.time()
        return c not in self._invalides and not self._repos_actif(m, c, maintenant)

    def prendre(self, sauf=()):
        """Le 1er couple disponible dans l'ordre (meilleur modèle d'abord, puis compte) hors `sauf` :
        dict {m, c, modele, compte, cle} ; None si aucun."""
        with self._verrou:
            self._nouveau_jour()
            for m in range(len(self.modeles)):
                for c in range(len(self.cles)):
                    if (m, c) not in sauf and self.disponible(m, c):
                        return {"m": m, "c": c, "modele": self.modeles[m], "compte": c + 1, "cle": self.cles[c]}
        return None

    def motifs(self, sauf=()):
        """Pourquoi plus rien n'est disponible : ensemble de « quota », « cle », « refus », « reglage », « passagere »
        (couple écarté pour cet appel seulement, après des coupures)."""
        maintenant, out = time.time(), set()
        with self._verrou:
            for m in range(len(self.modeles)):
                for c in range(len(self.cles)):
                    r = self._repos_actif(m, c, maintenant)
                    if c in self._invalides:
                        out.add("cle")
                    elif r:
                        out.add(r["genre"])
                    elif (m, c) in sauf:
                        out.add("passagere")
        return out

    def signaler(self, m, c, erreur, maintenant=None, en_cours=False):
        """Note l'erreur reçue avec ce couple ; renvoie sa nature (« quota », « invalide », « reglage », « passagere »).
        en_cours : la session était ouverte (l'erreur vient de ce qu'on a envoyé, pas du modèle lui-même)."""
        nature = classer(erreur)
        maintenant = maintenant if maintenant is not None else time.time()
        texte = str(erreur)
        with self._verrou:
            if nature == "quota":
                jour = bool(re.search(r"per ?day|daily|par jour", texte, re.I))
                v = _VALEUR_QUOTA.search(texte)
                raison = ("limite du jour" if jour else "limite atteinte") + (f" ({v.group(1)}{' par jour' if jour else ''})" if v else "")
                self._repos[(m, c)] = {"jusqu_a": minuit_pacifique(maintenant) if jour else maintenant + PAUSE_LIMITE_S,
                                       "raison": raison, "genre": "quota"}
                self._usage_de(m, c)["limites"] += 1
            elif nature == "invalide":
                if _code(erreur) == 401 or any(k in texte.lower() for k in _CLE_REFUSEE):
                    self._invalides.add(c)        # la clé elle-même : tous les modèles de ce compte
                else:                             # 403 : ce modèle n'est pas ouvert à ce compte
                    self._repos[(m, c)] = {"jusqu_a": maintenant + PAUSE_REFUS_S, "raison": "accès refusé", "genre": "refus"}
            elif nature == "reglage" and not en_cours:
                self._repos[(m, c)] = {"jusqu_a": maintenant + PAUSE_REFUS_S, "raison": "réglage refusé", "genre": "reglage"}
            self._sauver()
        return nature

    def noter_appel(self, m, c):
        """Un appel a vraiment parlé avec ce couple (session ouverte) : compté une fois par appel."""
        with self._verrou:
            self._nouveau_jour()
            self._usage_de(m, c)["appels"] += 1
            self._sauver()

    def noter_duree(self, m, c, secondes):
        with self._verrou:
            self._nouveau_jour()
            self._usage_de(m, c)["secondes"] += max(0.0, secondes)
            self._sauver()

    def prochain_retour_s(self):
        """Secondes avant qu'une LIMITE se lève sur un couple (None si aucune) : pour « retour dans N min »."""
        maintenant = time.time()
        with self._verrou:
            r = [v["jusqu_a"] - maintenant for (m, c), v in self._repos.items()
                 if c not in self._invalides and v["genre"] == "quota" and v["jusqu_a"] > maintenant]
        return max(0, round(min(r))) if r else None

    def etat(self):
        """Pour l'affichage : par modèle et par compte, disponibilité, raison, retour, usage du jour (jamais les clés)."""
        maintenant = time.time()
        with self._verrou:
            self._nouveau_jour()
            out = []
            for m, nom in enumerate(self.modeles):
                comptes = []
                for c in range(len(self.cles)):
                    r, u = self._repos_actif(m, c, maintenant), self._usage.get((m, c), {})
                    if c in self._invalides:
                        etat, raison, retour = "ko", "clé refusée", 0
                    elif r:                       # orange : limite (revient) ; rouge : accès / réglage refusé
                        etat, raison, retour = "repos" if r["genre"] == "quota" else "ko", r["raison"], round(r["jusqu_a"] - maintenant)
                    else:
                        etat, raison, retour = "ok", None, 0
                    comptes.append({"compte": c + 1, "etat": etat, "disponible": etat == "ok", "raison": raison,
                                    "retour_dans_s": max(0, retour), "appels_jour": u.get("appels", 0),
                                    "minutes_jour": round(u.get("secondes", 0) / 60, 1), "limites_jour": u.get("limites", 0)})
                out.append({"modele": nom, "comptes": comptes})
            return {"jour_quota": self._jour, "remise_a_zero_dans_s": round(minuit_pacifique(maintenant) - maintenant),
                    "reserves": out}
