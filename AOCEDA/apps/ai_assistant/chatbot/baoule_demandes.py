"""LISTE FERMÉE des demandes AOCEDA (06/10/2026) et leurs réponses construites à partir des VRAIES données.

Le cerveau IA ne peut que CHOISIR une demande de cette liste (il ne rédige pas la réponse) ; la réponse est ensuite
construite ici, par du code, avec les chiffres du compte (outils AOCEDA via le pont, lecture seule) : rien d'inventé.
Chaque réponse est une liste de Phrase(fr, nombres, cles) : « nombres » et « cles » (noms d'appareils) servent à
vérifier que la traduction en baoulé les a gardés (contrôle aller-retour, baoule_repondre).

Règles d'écriture (pour une bonne traduction automatique) : phrases courtes, une idée par phrase, nombres EN LETTRES,
montants arrondis à la centaine, vouvoiement, pas de sigle sauf CIE. Plusieurs tournures par réponse fréquente : on ne
répète jamais la même deux fois de suite dans une conversation (demande du client, 05/10/2026).
"""
from dataclasses import dataclass
from datetime import datetime

from .nombres_fr import en_lettres

PERIODES = ["aujourd_hui", "hier", "avant_hier", "cette_semaine", "semaine_derniere", "7_derniers_jours", "ce_week_end",
            "week_end_dernier", "ce_mois", "mois_dernier", "30_derniers_jours"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
HORS_LIGNE_S = 3600          # aucun capteur n'a envoyé de mesure depuis 1 h : on ne peut rien dire de « maintenant »


@dataclass
class Phrase:
    fr: str
    nombres: tuple = ()       # nombres qui doivent survivre à la traduction
    cles: tuple = ()          # noms d'appareils qui doivent survivre
    sens: tuple = ()          # mots de SENS : chaque groupe = synonymes (sans accents), au moins un doit survivre


# mots de sens des phrases chiffrées (contre-vérification de la traduction)
S_CREDIT = ("credit", "solde", "unite")
S_RECHARGE = ("recharg", "achat", "achet", "credit", "depot")
S_FRANCS = ("franc", "cfa", "cout", "prix", "argent", "fcfa")
S_CONSO = ("consomm", "utilis", "depens", "kilowatt", "energie", "electricite", "courant")
S_FACTURE = ("factur", "pay", "cout", "depens", "paie", "regle")


@dataclass
class Demande:
    id: str
    groupe: str
    type: str                 # conversation | info | conseil | argent | action | hors_sujet | libre
    libelle: str              # bouton de choix (« Mon crédit »)
    description: str          # pour le cerveau IA
    exemples: tuple = ()
    besoin: str = ""          # montant | appareil (détail utile)
    periode: str = ""         # période par défaut (consommation)
    contenu: object = None    # fonction(details, lire, variante) -> [Phrase]
    confirmer: object = None  # fonction(details) -> Phrase (question oui/non) ; demandes argent / action
    apres_oui: object = None  # fonction(details, lire) -> [Phrase]
    variantes: int = 1


# ── petits outils ──────────────────────────────────────────────────────────────
def arrondi(v, pas=100):
    return int(round(float(v or 0) / pas) * pas)


def francs(v):
    v = arrondi(v)
    return Phrase("", (v,)), f"{en_lettres(v)} francs"


def kwh_texte(v):
    v = float(v or 0)
    if v >= 10:
        return f"{en_lettres(round(v))} kilowattheures", (round(v),)
    entier, dec = int(v), int(round((v - int(v)) * 10))
    if dec == 10:
        entier, dec = entier + 1, 0
    return (f"{en_lettres(entier)} virgule {en_lettres(dec)} kilowattheure{'s' if v >= 2 else ''}" if dec
            else f"{en_lettres(entier)} kilowattheure{'s' if entier >= 2 else ''}"), (entier,)


def date_txt(iso):
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{'premier' if d.day == 1 else en_lettres(d.day)} {MOIS[d.month - 1]}"


def lettres_dans(texte):
    """Chiffres d'un libellé en lettres (« les 7 derniers jours » -> « les sept derniers jours »)."""
    import re
    return re.sub(r"\d+", lambda m: en_lettres(int(m.group())), texte or "")


def heure_txt(h):
    """Heure en lettres, au féminin (« vingt-et-une heures », « une heure »)."""
    h = int(h)
    if h == 1:
        return "une heure"
    return en_lettres(h).replace("et-un", "et-une") + " heures"


def jours_txt(secondes):
    j = int(secondes // 86400)
    if j >= 2:
        return f"{en_lettres(j)} jours"
    h = max(1, int(secondes // 3600))
    return "un jour" if j == 1 else f"{en_lettres(h)} heure{'s' if h > 1 else ''}"


def nom_simple(nom):
    """« Climatiseur salon » -> « le climatiseur du salon » (plus naturel, mieux traduit)."""
    n = (nom or "").strip()
    morceaux = n.split()
    if len(morceaux) == 2 and morceaux[1].lower() in ("salon", "chambre", "cuisine", "bureau"):
        return f"le {morceaux[0].lower()} du {morceaux[1].lower()}"
    return ("le " if n[:1].lower() not in "aeéiouh" else "l'") + n.lower()


def cle_appareil(nom):
    return (nom or "").split()[0].lower() if nom else ""


def _erreur(r):
    return not isinstance(r, dict) or "erreur" in r


def capteurs_muets(lire):
    """(muets ?, depuis combien de secondes) : aucun capteur n'a envoyé de mesure récente."""
    r = lire("etat_capteurs", {})
    if _erreur(r) or not r.get("capteurs"):
        return False, 0
    ages = [c.get("secondes_depuis_derniere_lecture") for c in r["capteurs"]]
    ages = [a for a in ages if a is not None]
    if not ages:
        return True, 0
    return min(ages) > HORS_LIGNE_S, min(ages)


def phrase_muets(age):
    return Phrase(f"Vos capteurs n'envoient plus de mesures depuis {jours_txt(age)}.", (), ())


def indisponible():
    return [Phrase("Je n'arrive pas à lire vos données pour le moment."), Phrase("Réessayez dans quelques minutes.")]


# ── contenus ───────────────────────────────────────────────────────────────────
def _saluer(d, lire, v):
    # la salutation de l'heure (« Aɲiho » le jour, « Awossi'n o » le soir) est mise en tête par baoule_chaine, directement
    # en baoulé (09/10/2026) : plus de « Bonjour » ici (il était dit même le soir, et Google l'enlevait de la traduction)
    return [[Phrase("Je suis l'assistant AOCEDA."),
             Phrase("Je peux vous dire votre crédit, votre consommation ou ce qui consomme le plus.")],
            [Phrase("Je suis là pour vous aider."),
             Phrase("Demandez-moi votre crédit, votre facture ou l'état de vos appareils.")]][v % 2]


def _remercier(d, lire, v):
    return [[Phrase("Avec plaisir."), Phrase("Je reste là si vous avez une autre question.")],
            [Phrase("Je vous en prie."), Phrase("N'hésitez pas à me reposer une question.")]][v % 2]


def _au_revoir(d, lire, v):
    return [[Phrase("Au revoir, à bientôt.")], [Phrase("Au revoir, bonne journée.")]][v % 2]


def _aide(d, lire, v):
    return [Phrase("Je peux vous dire combien de crédit il vous reste."),
            Phrase("Je peux aussi vous dire ce que vous consommez et quel appareil consomme le plus."),
            Phrase("Je vous donne enfin des conseils pour payer moins.")]


def _oui_non_seul(d, lire, v):
    return [[Phrase("D'accord."), Phrase("Que voulez-vous savoir, par exemple votre crédit ou votre consommation ?")],
            [Phrase("Très bien."), Phrase("Dites-moi ce que vous voulez savoir sur votre électricité.")]][v % 2]


def _credit(d, lire, v):
    r = lire("credit_et_recharges", {})
    if _erreur(r):
        return indisponible()
    if r.get("type_compteur") != "prepaye":
        return [Phrase("Votre compteur est postpayé."), Phrase("Vous n'avez pas de crédit à recharger : vous payez une facture.")]
    c = r.get("credit") or {}
    reste = arrondi(c.get("restant_fcfa"))
    out = [Phrase(f"Il vous reste environ {en_lettres(reste)} francs de crédit." if v % 2 == 0 else
                  f"Votre crédit restant est d'environ {en_lettres(reste)} francs.", (reste,), (), (S_CREDIT,))]
    if c.get("jours_restants"):
        j = int(c["jours_restants"])
        out.append(Phrase(f"Au rythme actuel, cela fait environ {en_lettres(j)} jours.", (j,)))
    rec = (r.get("dernieres_recharges") or [None])[0]
    if rec:
        m = arrondi(rec["montant_fcfa"])
        out.append(Phrase(f"Votre dernière recharge était de {en_lettres(m)} francs, le {date_txt(rec['date'])}.", (m,), (),
                          (S_RECHARGE,)))
    return out


def _recharger_comment(d, lire, v, montant=None):
    achat = f"Achetez {en_lettres(montant)} francs de crédit" if montant else "Achetez du crédit"
    return [Phrase(f"{achat} chez un revendeur ou avec votre téléphone.", (montant,) if montant else ()),
            Phrase("Vous recevez un code de vingt chiffres."),
            Phrase("Tapez ce code sur le clavier du compteur, puis validez.")]


def _recharges(d, lire, v):
    r = lire("credit_et_recharges", {})
    if _erreur(r):
        return indisponible()
    recs = r.get("dernieres_recharges") or []
    if not recs:
        return [Phrase("Je ne vois aucune recharge enregistrée dans AOCEDA.")]
    out = []
    for rec in recs[:2]:
        m = arrondi(rec["montant_fcfa"])
        out.append(Phrase(f"Le {date_txt(rec['date'])}, vous avez rechargé {en_lettres(m)} francs.", (m,), (), (S_RECHARGE,)))
    return out


def _conso(d, lire, v):
    periode = d.get("periode") if d.get("periode") in PERIODES else "aujourd_hui"
    r = lire("conso_periode", {"periode": periode})
    if _erreur(r):
        return indisponible()
    muets, age = capteurs_muets(lire)
    if muets and float(r.get("kwh_total") or 0) == 0:
        return [phrase_muets(age), Phrase("Je ne peux donc pas compter votre consommation sur cette période.")]
    texte, ns = kwh_texte(r.get("kwh_total"))
    cout = arrondi(r.get("cout_estime_fcfa"))
    libelle = lettres_dans((r.get("periode") or {}).get("libelle", "").split(",")[0]) or "sur cette période"
    out = [Phrase(f"{libelle.capitalize()}, vous avez consommé {texte}.", ns, (), (S_CONSO,)),
           Phrase(f"Cela fait environ {en_lettres(cout)} francs.", (cout,), (), (S_FRANCS,))]
    prec = r.get("periode_precedente")
    if prec and prec.get("kwh_total") is not None:
        p = float(prec["kwh_total"])
        k = float(r.get("kwh_total") or 0)
        if p > 0:
            out.append(Phrase("C'est plus qu'avant." if k > p * 1.05 else "C'est moins qu'avant." if k < p * 0.95
                              else "C'est à peu près comme avant."))
    if muets:
        out.append(phrase_muets(age))
    return out


def _repartition(lire, periode):
    r = lire("repartition_appareils", {"periode": periode})
    if _erreur(r):
        return None
    return r


def _gourmand(d, lire, v):
    periode = d.get("periode") if d.get("periode") in PERIODES else "30_derniers_jours"
    r = _repartition(lire, periode)
    if r is None:
        return indisponible()
    apps = r.get("appareils") or []
    if not apps:
        return [Phrase("Je n'ai aucune mesure d'appareil sur cette période.")]
    a = apps[0]
    out = [Phrase(f"C'est {nom_simple(a['nom'])} qui consomme le plus.", (), (cle_appareil(a["nom"]),)),
           Phrase(f"Il fait {en_lettres(a['pct'])} pour cent de votre électricité.", (a["pct"],), (), (S_CONSO,))]
    if len(apps) > 1:
        b = apps[1]
        out.append(Phrase(f"Ensuite vient {nom_simple(b['nom'])}, avec {en_lettres(b['pct'])} pour cent.", (b["pct"],),
                          (cle_appareil(b["nom"]),)))
    return out


def trouver_appareil(nom, noms):
    """Appareil du compte qui correspond au mot entendu (« clim » -> « Climatiseur salon »), ou None."""
    from . import baoule_lexique
    n = baoule_lexique.cle_fr(nom or "")
    if not n:
        return None
    synonymes = {"clim": "climatiseur", "frigo": "refrigerateur", "tele": "television", "tv": "television",
                 "ventilo": "ventilateur", "chauffe eau": "chauffe-eau"}
    n = synonymes.get(n, n)
    for x in noms:
        k = baoule_lexique.cle_fr(x)
        if n in k or k.split()[0] in n:
            return x
    return None


def _conso_appareil(d, lire, v):
    periode = d.get("periode") if d.get("periode") in PERIODES else "30_derniers_jours"
    r = _repartition(lire, periode)
    if r is None:
        return indisponible()
    apps = r.get("appareils") or []
    nom = trouver_appareil(d.get("appareil"), [a["nom"] for a in apps])
    if not nom:
        if not apps:
            return [Phrase("Je n'ai aucune mesure d'appareil sur cette période.")]
        liste = ", ".join(nom_simple(a["nom"]) for a in apps[:4])
        return [Phrase("Je ne trouve pas cet appareil dans vos mesures."), Phrase(f"Vos appareils mesurés sont {liste}.")]
    a = next(x for x in apps if x["nom"] == nom)
    texte, ns = kwh_texte(a["kwh"])
    libelle = lettres_dans((r.get("periode") or {}).get("libelle", "").split(",")[0]) or "sur cette période"
    return [Phrase(f"{libelle.capitalize()}, {nom_simple(nom)} a consommé {texte}.", ns, (cle_appareil(nom),), (S_CONSO,)),
            Phrase(f"C'est {en_lettres(a['pct'])} pour cent de votre électricité.", (a["pct"],), (), (S_CONSO,))]


def _heures(d, lire, v):
    r = lire("heures_de_pointe", {"nb_jours": 7})
    if _erreur(r) or not r.get("heures_de_pointe"):
        return indisponible() if _erreur(r) else [Phrase("Je n'ai pas assez de mesures pour trouver vos heures fortes.")]
    top = r["heures_de_pointe"]
    out = [Phrase(f"Vous consommez le plus vers {heure_txt(top[0]['heure'])}.", (top[0]["heure"],))]
    if len(top) >= 3:
        out.append(Phrase(f"Les autres heures fortes sont {heure_txt(top[1]['heure'])} et "
                          f"{heure_txt(top[2]['heure'])}.", (top[1]["heure"], top[2]["heure"])))
    return out


def _prevision(d, lire, v):
    r = lire("prevision_fin_mois", {})
    if _erreur(r):
        return indisponible()
    if r.get("mode") in ("trop_tot", "vide") or not r.get("bill_central"):
        return [Phrase("C'est encore trop tôt dans le mois pour prévoir votre facture."),
                Phrase("Il me faut au moins trois jours complets de mesures.")]
    bas, centre, haut = arrondi(r["bill_low"]), arrondi(r["bill_central"]), arrondi(r["bill_high"])
    out = [Phrase(f"À la fin du mois, votre électricité devrait coûter environ {en_lettres(centre)} francs.", (centre,), (),
                  (S_FACTURE,)),
           Phrase(f"Cela peut aller de {en_lettres(bas)} à {en_lettres(haut)} francs.", (bas, haut), (), (S_FRANCS,))]
    if r.get("recharge_conseillee"):
        rc = arrondi(r["recharge_conseillee"])
        out.append(Phrase(f"Je vous conseille de recharger encore {en_lettres(rc)} francs.", (rc,), (), (S_RECHARGE,)))
    return out


def _mois_complets(lire):
    r = lire("historique_mensuel", {})
    if _erreur(r):
        return None
    return [m for m in r.get("mois", []) if not m.get("en_cours")]


def _facture_mois(d, lire, v):
    mois = _mois_complets(lire)
    if mois is None:
        return indisponible()
    if not mois:
        return [Phrase("Je n'ai pas encore de mois complet mesuré.")]
    m = mois[-1]
    t = arrondi(m["total_fcfa"])
    out = [Phrase(f"En {m['mois_libelle'].split()[0].lower()}, votre électricité a coûté environ {en_lettres(t)} francs.", (t,),
                  (), (S_FACTURE,))]
    if len(mois) >= 2:
        p = arrondi(mois[-2]["total_fcfa"])
        out.append(Phrase(f"Le mois d'avant, c'était {en_lettres(p)} francs.", (p,), (), (S_FRANCS,)))
    return out


def _facture_chere(d, lire, v):
    out = _facture_mois(d, lire, v)
    r = _repartition(lire, "30_derniers_jours")
    if r and r.get("appareils"):
        a = r["appareils"][0]
        out += [Phrase(f"L'appareil qui consomme le plus est {nom_simple(a['nom'])}, avec {en_lettres(a['pct'])} pour cent.",
                       (a["pct"],), (cle_appareil(a["nom"]),)),
                Phrase("L'utiliser moins longtemps est le moyen le plus sûr de payer moins.")]
    return out


def _etat_appareils(d, lire, v):
    r = lire("etat_capteurs", {})
    if _erreur(r):
        return indisponible()
    muets, age = capteurs_muets(lire)
    if muets:
        return [phrase_muets(age), Phrase("Je ne vois donc pas l'état actuel de vos appareils.")]
    on = [c["nom"] for c in r.get("capteurs", []) if c.get("etat") == "ON"]
    off = [c["nom"] for c in r.get("capteurs", []) if c.get("etat") != "ON"]
    out = []
    if on:
        out.append(Phrase(f"En ce moment, {', '.join(nom_simple(x) for x in on)} {'est' if len(on) == 1 else 'sont'} allumé"
                          f"{'' if len(on) == 1 else 's'}.", (), tuple(cle_appareil(x) for x in on)))
    if off:
        out.append(Phrase(f"{', '.join(nom_simple(x) for x in off).capitalize()} {'est' if len(off) == 1 else 'sont'} éteint"
                          f"{'' if len(off) == 1 else 's'}.", (), tuple(cle_appareil(x) for x in off)))
    return out


def _confirmer_appareil(verbe):
    def q(d):
        app = d.get("appareil")
        return Phrase(f"Vous voulez {verbe} {nom_simple(app)}, c'est bien cela ?" if app else
                      f"Vous voulez {verbe} un appareil, c'est bien cela ?", (), (cle_appareil(app),) if app else ())
    return q


def _apres_commande(d, lire):
    return [Phrase("Je ne peux pas encore commander un appareil à distance."),
            Phrase("Faites-le directement avec son bouton ou à la prise.")]


def _courant_coupe(d, lire, v):
    # « l'interrupteur général » plutôt que « le disjoncteur » : traduit en vrai baoulé (« sɛkɛti dan ») et retraduit à
    # l'identique ; « disjoncteur » ressortait avec des mots anglais (« circuit breaker », audit du 09/10/2026)
    out = [Phrase("Vérifiez d'abord l'interrupteur général près du compteur."),
           Phrase("Si tout le quartier est coupé, c'est une coupure de la CIE.")]
    r = lire("credit_et_recharges", {})
    if not _erreur(r) and r.get("type_compteur") == "prepaye":
        reste = arrondi((r.get("credit") or {}).get("restant_fcfa"))
        out.insert(1, Phrase(f"D'après AOCEDA, il vous reste environ {en_lettres(reste)} francs de crédit.", (reste,)))
    return out


def _courant_revenu(d, lire, v):
    r = lire("etat_capteurs", {})
    if _erreur(r):
        return indisponible()
    muets, age = capteurs_muets(lire)
    if muets:
        return [phrase_muets(age), Phrase("Je ne peux donc pas savoir si le courant est revenu."),
                Phrase("Regardez si l'écran du compteur est allumé.")]
    return [Phrase("Oui, vos capteurs envoient des mesures en ce moment."), Phrase("Le courant est bien là.")]


def _alertes(d, lire, v):
    r = lire("alertes", {"seulement_non_lues": True, "limite": 2})
    if _erreur(r):
        return indisponible()
    n = int(r.get("nb_non_lues") or 0)
    if not n:
        return [Phrase("Vous n'avez aucune nouvelle alerte.")]
    out = [Phrase(f"Vous avez {en_lettres(n)} alerte{'s' if n > 1 else ''} non lue{'s' if n > 1 else ''}.", (n,))]
    for a in (r.get("alertes") or [])[:2]:                  # le type d'alerte et l'appareil, sans chiffres bruts
        msg = a.get("message", "")
        app = msg.split(":")[0].strip() if ":" in msg and len(msg.split(":")[0]) <= 30 else ""
        app = app if app and not any(c.isdigit() for c in app) else ""
        out.append(Phrase(f"Alerte : {a.get('type', 'alerte').lower()}{' pour ' + nom_simple(app) if app else ''}.", (),
                          (cle_appareil(app),) if app else ()))
    return out


def _technicien(d, lire, v):
    r = lire("interventions", {})
    if _erreur(r):
        return indisponible()
    its = r.get("interventions") or []
    if not its:
        return [Phrase("Aucune intervention de technicien n'est enregistrée.")]
    i = its[0]
    quand = date_txt(i.get("date_programmee") or i.get("date"))
    return [Phrase(f"Dernière intervention : {i.get('type', '').lower()}, {i.get('statut', '').lower()}, le {quand}.")]


def _prepaye_postpaye(d, lire, v):
    out = [Phrase("Avec le prépayé, vous achetez du crédit avant de consommer."),
           Phrase("Avec le postpayé, vous consommez puis vous payez une facture tous les deux mois.")]
    r = lire("credit_et_recharges", {})
    if not _erreur(r):
        out.append(Phrase("Votre compteur à vous est prépayé." if r.get("type_compteur") == "prepaye"
                          else "Votre compteur à vous est postpayé."))
    return out


def _economiser(d, lire, v):
    return [[Phrase("Réglez le climatiseur sur vingt-six degrés.", (26,)), Phrase("Éteignez la lumière dans les pièces vides."),
             Phrase("Débranchez les chargeurs quand ils ne servent pas.")],
            [Phrase("Ne laissez pas la porte du réfrigérateur ouverte."), Phrase("Repassez le linge en une seule fois."),
             Phrase("Éteignez la télévision au lieu de la laisser en veille.")]][v % 2]


def _climatiseur(d, lire, v):
    return [Phrase("Réglez le climatiseur sur vingt-six degrés.", (26,)),
            Phrase("Fermez bien les portes et les fenêtres."), Phrase("Éteignez-le quand la pièce est vide.")]


def _hors_sujet(d, lire, v):
    return [[Phrase("Je suis l'assistant de l'électricité de la maison."),
             Phrase("Je peux vous parler de votre crédit, de votre facture ou de vos appareils.")],
            [Phrase("Je ne m'occupe que de l'électricité de votre maison."),
             Phrase("Demandez-moi par exemple ce qui consomme le plus chez vous.")]][v % 2]


def _confirmer_recharge(d):
    m = arrondi(d["montant"]) if d.get("montant") else None
    return Phrase(f"Vous voulez recharger {en_lettres(m)} francs, c'est bien cela ?" if m
                  else "Vous voulez recharger votre compteur, c'est bien cela ?", (m,) if m else (), (), (S_RECHARGE,))


def _apres_recharge(d, lire):
    m = arrondi(d["montant"]) if d.get("montant") else None
    return [Phrase("D'accord. Je ne peux pas payer à votre place, mais voici comment faire.")] + _recharger_comment(d, lire, 0, m)


CATALOGUE = {x.id: x for x in [
    Demande("saluer", "conversation", "conversation", "Saluer", "Salutation (bonjour, bonsoir, salut).",
            ("Bonjour", "Bonsoir"), contenu=_saluer, variantes=2),
    Demande("remercier", "conversation", "conversation", "Merci", "Remerciement.", ("Merci beaucoup",),
            contenu=_remercier, variantes=2),
    Demande("au_revoir", "conversation", "conversation", "Au revoir", "Au revoir, fin de la conversation.",
            contenu=_au_revoir, variantes=2),
    Demande("aide", "conversation", "conversation", "Ce que je sais faire",
            "La personne demande ce que l'assistant sait faire, ou demande de l'aide sans préciser.",
            ("Qu'est-ce que tu peux faire ?", "Aide-moi"), contenu=_aide),
    Demande("oui_non_seul", "conversation", "conversation", "Oui / non", "Un simple oui, non ou d'accord, sans question en cours.",
            contenu=_oui_non_seul, variantes=2),
    Demande("credit_restant", "credit", "info", "Mon crédit", "Combien de crédit (d'unités, d'argent sur le compteur prépayé) il reste.",
            ("Combien il me reste de crédit ?", "Mon crédit est fini ?", "Il reste combien d'argent dans le compteur ?"),
            contenu=_credit, variantes=2),
    Demande("recharger_comment", "credit", "conseil", "Comment recharger", "Comment recharger, acheter du crédit, mettre le code.",
            ("Comment recharger mon compteur ?",), contenu=_recharger_comment),
    Demande("recharger_montant", "credit", "argent", "Recharger un montant",
            "La personne VEUT recharger ou payer un montant précis (« je veux recharger 5000 »).",
            ("Je veux recharger cinq mille francs",), besoin="montant", confirmer=_confirmer_recharge, apres_oui=_apres_recharge),
    Demande("dernieres_recharges", "credit", "info", "Mes recharges", "Les dernières recharges faites, leurs montants et dates.",
            ("Quand est-ce que j'ai rechargé ?",), contenu=_recharges),
    Demande("conso_periode", "consommation", "info", "Ma consommation",
            "Combien la personne a consommé (kWh, argent) sur une période : aujourd'hui, hier, cette semaine, ce mois...",
            ("J'ai consommé combien aujourd'hui ?", "Ma consommation de la semaine"), periode="aujourd_hui", contenu=_conso),
    Demande("appareil_gourmand", "consommation", "info", "Ce qui consomme le plus",
            "Quel appareil consomme le plus, ce qui mange le courant.", ("Qu'est-ce qui consomme le plus chez moi ?",),
            periode="30_derniers_jours", contenu=_gourmand),
    Demande("conso_appareil", "consommation", "info", "Un appareil précis",
            "Combien consomme UN appareil précis (climatiseur, réfrigérateur, télévision...).",
            ("Combien consomme le climatiseur ?",), besoin="appareil", periode="30_derniers_jours", contenu=_conso_appareil),
    Demande("heures_de_pointe", "consommation", "info", "Mes heures fortes", "À quelle heure la personne consomme le plus.",
            ("À quelle heure je consomme le plus ?",), contenu=_heures),
    Demande("facture_prevision", "facture", "info", "Ma facture à venir",
            "Combien la personne va payer à la fin du mois, prévision de la facture.", ("Je vais payer combien ce mois-ci ?",),
            contenu=_prevision),
    Demande("facture_mois", "facture", "info", "Ma dernière facture", "Combien la personne a payé le mois dernier ou un mois passé.",
            ("J'ai payé combien le mois dernier ?",), contenu=_facture_mois),
    Demande("facture_chere", "facture", "info", "Pourquoi c'est cher", "Pourquoi la facture ou le crédit part vite, pourquoi c'est cher.",
            ("Pourquoi ma facture est si chère ?", "Pourquoi mon crédit finit vite ?"), contenu=_facture_chere),
    Demande("etat_appareils", "appareils", "info", "Mes appareils allumés", "Quels appareils sont allumés ou éteints maintenant.",
            ("Qu'est-ce qui est allumé ?",), contenu=_etat_appareils),
    Demande("eteindre_appareil", "appareils", "action", "Éteindre un appareil", "La personne veut ÉTEINDRE ou couper un appareil.",
            ("Éteins le climatiseur",), besoin="appareil", confirmer=_confirmer_appareil("éteindre"), apres_oui=_apres_commande),
    Demande("allumer_appareil", "appareils", "action", "Allumer un appareil", "La personne veut ALLUMER un appareil ou la lumière.",
            ("Allume la lumière",), besoin="appareil", confirmer=_confirmer_appareil("allumer"), apres_oui=_apres_commande),
    Demande("courant_coupe", "courant", "info", "Le courant est coupé",
            "La personne dit que le courant est coupé, qu'il n'y a plus de courant chez elle.", ("Il n'y a plus de courant chez moi",),
            contenu=_courant_coupe),
    Demande("courant_revenu", "courant", "info", "Le courant est revenu ?",
            "La personne demande si le courant est revenu, est monté, est là.", ("Le courant est revenu ?",),
            contenu=_courant_revenu),
    Demande("alertes", "courant", "info", "Mes alertes", "Les alertes, notifications, problèmes signalés par AOCEDA.",
            ("J'ai des alertes ?",), contenu=_alertes),
    Demande("technicien", "technique", "info", "Le technicien", "Intervention d'un technicien, installation, maintenance.",
            ("Le technicien vient quand ?",), contenu=_technicien),
    Demande("prepaye_postpaye", "conseil", "conseil", "Prépayé ou postpayé", "Différence entre compteur prépayé et postpayé.",
            ("C'est quoi la différence entre prépayé et postpayé ?",), contenu=_prepaye_postpaye),
    Demande("economiser", "conseil", "conseil", "Payer moins", "Conseils pour économiser, réduire la facture, consommer moins.",
            ("Comment payer moins ?",), contenu=_economiser, variantes=2),
    Demande("climatiseur_conseil", "conseil", "conseil", "Bien régler le climatiseur",
            "Comment bien utiliser ou régler le climatiseur (température).", ("Je mets le climatiseur à combien ?",),
            contenu=_climatiseur),
    Demande("autre_question_energie", "libre", "libre", "Autre question sur l'électricité",
            "Question sur l'électricité ou AOCEDA qui n'entre dans AUCUNE autre demande (explication générale)."),
    Demande("hors_sujet", "hors_sujet", "hors_sujet", "Autre sujet",
            "Message qui ne parle pas d'électricité ni d'AOCEDA (famille, argent en général, santé, actualité...).",
            contenu=_hors_sujet, variantes=2),
]}

DEMANDES_CHOIX_PAR_DEFAUT = ("credit_restant", "conso_periode", "appareil_gourmand")


def liste_pour_ia():
    """La liste des demandes, telle que le cerveau IA la reçoit."""
    lignes = []
    for d in CATALOGUE.values():
        ex = f" Exemples : {' ; '.join(d.exemples)}." if d.exemples else ""
        besoin = f" Détail utile : {d.besoin}." if d.besoin else ""
        lignes.append(f"- {d.id} : {d.description}{besoin}{ex}")
    return "\n".join(lignes)
