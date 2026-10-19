"""
Moteur tarifaire officiel, grille domestique basse tension de Côte d'Ivoire.

Source de vérité : arrêté interministériel n° 1355/MMPE/MFB du 27 décembre 2023
fixant les tarifs de vente de l'électricité (en vigueur au 1er janvier 2024),
publié par la CIE (cie.ci, rubrique « Tarifs d'électricité »). Méthode de calcul
d'une facture : ANARE-CI, « Prix de l'électricité » (exemple 10A, 348 kWh,
reproduit au franc près). Détail et exemples : docs/architecture/tarification-cie.md.

Ce qu'impose l'arrêté (vérifié sur le texte le 14/10/2026) :
- POSTPAIEMENT (articles 2 à 5) : facture par BIMESTRE, deux tranches.
  Seuil : 80 kWh/bimestre au tarif social, 180 h × puissance souscrite (kVA) au
  tarif général. Social progressif (tranche 2 plus chère), général dégressif.
  Prime fixe : 614,90 F/bimestre au social, 1 618,04 F (5A, 10A) ou 1 779,84 F
  (15A et plus) PAR kVA et par bimestre au général.
- PRÉPAIEMENT (articles 10 à 13) : AUCUNE tranche, un prix par kWh (prime fixe
  « linéarisée » comprise dans chaque kWh), décompté par le compteur.
- Redevances et taxes : électrification rurale (100 F/bimestre + par kWh en
  postpaiement, par kWh seulement en prépaiement) ; RTI (2 F/kWh plafonnée à
  2 000 F/bimestre au social et en 5A, forfait de 2 000 F/bimestre en 10A et plus
  postpayé, 3 F/kWh en prépayé 10A+) ; ordures ménagères 2,50 F/kWh à Abidjan,
  1,00 F ailleurs.
- Tous les prix sont TTC : la TVA de 18 % est déjà incluse, on ne l'ajoute jamais.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


# Puissance souscrite par ampérage (monophasé 220 V) : P = U × I
PUISSANCE_KW = {5: Decimal("1.1"), 10: Decimal("2.2"), 15: Decimal("3.3")}
AMPERAGES_VALIDES = (5, 10, 15)

# Taxe d'enlèvement des ordures ménagères, par kWh (tous régimes)
TEOM_ABIDJAN = Decimal("2.50")
TEOM_AUTRES_COMMUNES = Decimal("1.00")

# ── Postpaiement : grille par BIMESTRE (articles 2 à 5), montants TTC ──────────
GRILLE_POSTPAYE = {
    # Art. 2 : domestique social monophasé 5A
    "social": {
        "prime_fixe_bimestre": Decimal("614.90"),   # forfait (pas par kVA)
        "prime_par_kva": False,
        "seuil_t1_bimestre": Decimal("80"),
        "prix_t1": Decimal("31.72"),
        "prix_t2": Decimal("65.11"),
        "rural_kwh": Decimal("1.00"),
        "rti_kwh": Decimal("2.00"),                 # plafonnée à 2 000 F/bimestre
        "rti_forfait": None,
    },
    # Art. 3 : domestique général monophasé 5A (abonné social basculé, ou choix)
    ("general", 5): {
        "prime_fixe_bimestre": Decimal("1618.04"),  # par kVA
        "prime_par_kva": True,
        "seuil_t1_heures": Decimal("180"),
        "prix_t1": Decimal("86.92"),
        "prix_t2": Decimal("75.34"),
        "rural_kwh": Decimal("1.06"),
        "rti_kwh": Decimal("2.00"),                 # plafonnée à 2 000 F/bimestre
        "rti_forfait": None,
    },
    # Art. 4 : domestique général monophasé 10A
    ("general", 10): {
        "prime_fixe_bimestre": Decimal("1618.04"),
        "prime_par_kva": True,
        "seuil_t1_heures": Decimal("180"),
        "prix_t1": Decimal("86.92"),
        "prix_t2": Decimal("75.34"),
        "rural_kwh": Decimal("1.06"),
        "rti_kwh": None,
        "rti_forfait": Decimal("2000"),             # par bimestre
    },
    # Art. 5 : domestique général monophasé 15A et plus
    ("general", 15): {
        "prime_fixe_bimestre": Decimal("1779.84"),
        "prime_par_kva": True,
        "seuil_t1_heures": Decimal("180"),
        "prix_t1": Decimal("95.62"),
        "prix_t2": Decimal("82.86"),
        "rural_kwh": Decimal("1.06"),
        "rti_kwh": None,
        "rti_forfait": Decimal("2000"),
    },
}
RURAL_FIXE_BIMESTRE = Decimal("100")
RTI_PLAFOND_BIMESTRE = Decimal("2000")

# ── Prépaiement : prix PAR kWh (articles 10 à 13), montants TTC ────────────────
# « energie » regroupe les parts d'énergie, « prime » la prime fixe linéarisée.
GRILLE_PREPAYE = {
    # Art. 10 : social 5A. Le tableau liste une part « exonérée » (21,38) et une
    # part « taxable » (21,32 TTC) : comme toutes les lignes du tableau (FCFA/kWh),
    # elles s'ADDITIONNENT pour chaque kWh (lecture retenue, à confirmer sur un ticket).
    "social": {"energie": Decimal("42.70"), "prime": Decimal("6.50"),
               "rural": Decimal("1.01"), "rti": Decimal("2.00")},
    # Art. 11 : général 5A
    ("general", 5): {"energie": Decimal("84.50"), "prime": Decimal("8.95"),
                     "rural": Decimal("1.30"), "rti": Decimal("2.00")},
    # Art. 12 : général 10A
    ("general", 10): {"energie": Decimal("84.50"), "prime": Decimal("9.22"),
                      "rural": Decimal("1.30"), "rti": Decimal("3.00")},
    # Art. 13 : général 15A et plus. Prime HT = 8,35 + 0,24 × (kVA − 1,1) / 1,1,
    # + TVA 18 % (même rapport TTC/HT que les articles 11 et 12).
    ("general", 15): {"energie": Decimal("92.95"), "prime": None,
                      "rural": Decimal("1.30"), "rti": Decimal("3.00")},
}

# Repères d'éligibilité au tarif social (articles 2 et 10)
SOCIAL_MAX_KWH_BIMESTRE_POSTPAYE = Decimal("200")   # moyenne sur 3 bimestres
SOCIAL_MAX_KWH_MOIS_PREPAYE = Decimal("100")        # moyenne sur 6 mois

MOIS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
           "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _round(montant):
    return Decimal(montant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _categorie(amperage, type_tarif):
    """(type_tarif effectif, ampérage) : le social n'existe qu'en 5A (articles 2 et 10) ;
    un social demandé en 10A ou 15A relève du général de cet ampérage."""
    amperage = int(amperage) if amperage in AMPERAGES_VALIDES else 10
    if type_tarif == "social" and amperage == 5:
        return "social", amperage
    return "general", amperage


def _teom(abidjan):
    return TEOM_ABIDJAN if abidjan else TEOM_AUTRES_COMMUNES


def calculer_facture_bimestre(kwh, amperage=10, type_tarif="general", abidjan=True):
    """Facture POSTPAYÉE officielle d'un bimestre pour `kwh` consommés (articles 2 à 5).

    Renvoie la décomposition complète (Decimal, FCFA TTC) : tranches, prime fixe,
    taxes (part par kWh et part fixe), total."""
    kwh = max(Decimal(str(kwh)), Decimal("0"))
    tarif, amperage = _categorie(amperage, type_tarif)
    kva = PUISSANCE_KW[amperage]
    g = GRILLE_POSTPAYE["social"] if tarif == "social" else GRILLE_POSTPAYE[("general", amperage)]

    seuil = g["seuil_t1_bimestre"] if tarif == "social" else g["seuil_t1_heures"] * kva
    prime = g["prime_fixe_bimestre"] * kva if g["prime_par_kva"] else g["prime_fixe_bimestre"]
    kwh_t1 = min(kwh, seuil)
    kwh_t2 = max(Decimal("0"), kwh - seuil)
    montant_t1 = _round(kwh_t1 * g["prix_t1"])
    montant_t2 = _round(kwh_t2 * g["prix_t2"])

    teom = _teom(abidjan)
    if g["rti_kwh"] is not None:
        rti_variable = min(kwh * g["rti_kwh"], RTI_PLAFOND_BIMESTRE)
        rti_fixe = Decimal("0")
    else:
        rti_variable = Decimal("0")
        rti_fixe = g["rti_forfait"]
    taxes_variable = _round(kwh * (g["rural_kwh"] + teom) + rti_variable)
    taxe_fixe = _round(RURAL_FIXE_BIMESTRE + rti_fixe)
    taxes = _round(taxes_variable + taxe_fixe)
    prime = _round(prime)
    total = _round(montant_t1 + montant_t2 + prime + taxes)
    taxes_par_kwh = g["rural_kwh"] + teom + (g["rti_kwh"] or Decimal("0"))

    return {
        "regime": "postpaye",
        "periode": "bimestre",
        "kwh": _round(kwh),
        "type_tarif": tarif,
        "amperage": amperage,
        "seuil_t1_kwh": _round(seuil),
        "tranche1_kwh": _round(kwh_t1),
        "tranche1_prix": g["prix_t1"],
        "tranche1_fcfa": montant_t1,
        "tranche2_kwh": _round(kwh_t2),
        "tranche2_prix": g["prix_t2"],
        "tranche2_fcfa": montant_t2,
        "prime_fixe_fcfa": prime,
        "taxes_fcfa": taxes,
        "taxes_variable_fcfa": taxes_variable,
        "taxe_fixe_fcfa": taxe_fixe,
        "taxes_par_kwh": taxes_par_kwh,
        "total_fcfa": total,
        "prix_moyen_kwh": _round(total / kwh) if kwh > 0 else _round(g["prix_t1"] + taxes_par_kwh),
        "tva_incluse": True,
    }


def prix_kwh_prepaye(amperage=10, type_tarif="general", abidjan=True):
    """Prix TTC d'UN kWh prépayé (articles 10 à 13) : énergie + prime linéarisée
    + électrification rurale + RTI + ordures ménagères. Renvoie (prix, détail)."""
    tarif, amperage = _categorie(amperage, type_tarif)
    g = GRILLE_PREPAYE["social"] if tarif == "social" else GRILLE_PREPAYE[("general", amperage)]
    prime = g["prime"]
    if prime is None:
        kva = PUISSANCE_KW[amperage]
        prime_ht = Decimal("8.35") + Decimal("0.24") * (kva - Decimal("1.1")) / Decimal("1.1")
        prime = _round(prime_ht * Decimal("1.18"))
    taxes = g["rural"] + g["rti"] + _teom(abidjan)
    return g["energie"] + prime + taxes, {
        "type_tarif": tarif, "amperage": amperage,
        "energie": g["energie"], "prime": prime, "taxes": taxes,
    }


def calculer_cout_prepaye(kwh, amperage=10, type_tarif="general", abidjan=True):
    """Coût PRÉPAYÉ de `kwh` : un seul prix par kWh, sans tranche ni prime fixe à part.

    Même forme de réponse que calculer_facture_bimestre (tranche 2, prime et taxe fixe
    à zéro) pour que les écrans et l'assistant lisent les deux régimes de la même façon.
    La RTI prépayée est plafonnée à 2 000 F/bimestre : le plafond n'est atteint qu'au-delà
    de 666 kWh par bimestre (3 F/kWh), il n'est pas appliqué ici."""
    kwh = max(Decimal(str(kwh)), Decimal("0"))
    prix, d = prix_kwh_prepaye(amperage, type_tarif, abidjan)
    prix_energie = d["energie"] + d["prime"]
    montant = _round(kwh * prix_energie)
    taxes = _round(kwh * d["taxes"])
    total = _round(montant + taxes)
    return {
        "regime": "prepaye",
        "periode": "mois",
        "kwh": _round(kwh),
        "type_tarif": d["type_tarif"],
        "amperage": d["amperage"],
        "seuil_t1_kwh": None,
        "tranche1_kwh": _round(kwh),
        "tranche1_prix": prix_energie,
        "tranche1_fcfa": montant,
        "tranche2_kwh": Decimal("0.00"),
        "tranche2_prix": Decimal("0"),
        "tranche2_fcfa": Decimal("0.00"),
        "prime_fixe_fcfa": Decimal("0.00"),
        "taxes_fcfa": taxes,
        "taxes_variable_fcfa": taxes,
        "taxe_fixe_fcfa": Decimal("0.00"),
        "taxes_par_kwh": d["taxes"],
        "total_fcfa": total,
        "prix_moyen_kwh": _round(prix),
        "tva_incluse": True,
    }


def _client_abidjan(client):
    return not getattr(client, "horsAbidjan", False)


def est_prepaye(client):
    return getattr(client, "typeCompteur", "postpaye") == "prepaye"


def calculer_facture_pour_client(kwh, client):
    """Coût de `kwh` pour ce client, selon son régime : facture d'un bimestre
    (postpayé, kWh du bimestre) ou coût linéaire (prépayé)."""
    amperage = getattr(client, "amperage", 10) or 10
    type_tarif = getattr(client, "typeTarif", "general") or "general"
    if est_prepaye(client):
        return calculer_cout_prepaye(kwh, amperage, type_tarif, _client_abidjan(client))
    return calculer_facture_bimestre(kwh, amperage, type_tarif, _client_abidjan(client))


def prix_kwh_tout_compris(client):
    """Prix d'un kWh de plus, toutes taxes par kWh comprises : le prix unique en
    prépayé, le prix de la tranche 1 + taxes par kWh en postpayé."""
    amperage = getattr(client, "amperage", 10) or 10
    type_tarif = getattr(client, "typeTarif", "general") or "general"
    if est_prepaye(client):
        return _round(prix_kwh_prepaye(amperage, type_tarif, _client_abidjan(client))[0])
    d = calculer_facture_bimestre(0, amperage, type_tarif, _client_abidjan(client))
    return _round(d["tranche1_prix"] + d["taxes_par_kwh"])


# ── Périodes ──────────────────────────────────────────────────────────────────

def _ajouter_mois(annee, mois, n):
    m = mois - 1 + n
    return annee + m // 12, m % 12 + 1


def periode_contenant(client, jour):
    """Période de facturation contenant la date `jour` : (début, fin) inclus.

    Postpayé : le BIMESTRE de son groupe de facturation (GF1 : janvier-février,
    mars-avril… ; GF2 : février-mars, avril-mai…). Prépayé : le mois calendaire
    (aucune facture, le coût est linéaire : le mois sert seulement à l'affichage)."""
    if est_prepaye(client):
        debut = jour.replace(day=1)
        fin = jour.replace(day=calendar.monthrange(jour.year, jour.month)[1])
        return debut, fin
    premier = 2 if getattr(client, "groupeFacturation", "GF1") == "GF2" else 1
    ecart = (jour.month - premier) % 2
    a, m = _ajouter_mois(jour.year, jour.month, -ecart)
    debut = date(a, m, 1)
    a2, m2 = _ajouter_mois(a, m, 1)
    fin = date(a2, m2, calendar.monthrange(a2, m2)[1])
    return debut, fin


def libelle_periode(debut, fin):
    if (debut.year, debut.month) == (fin.year, fin.month):
        return f"{MOIS_FR[debut.month - 1]} {debut.year}"
    if debut.year == fin.year:
        return f"{MOIS_FR[debut.month - 1]}-{MOIS_FR[fin.month - 1]} {fin.year}"
    return f"{MOIS_FR[debut.month - 1]} {debut.year}-{MOIS_FR[fin.month - 1]} {fin.year}"


def periode_precedente(client, debut):
    return periode_contenant(client, debut - timedelta(days=1))


# ── Descriptif du tarif du client (page Facturation, page Paramètres) ─────────

CYCLES = {
    "GF1": "janvier-février, mars-avril, mai-juin, juillet-août, septembre-octobre, novembre-décembre",
    "GF2": "février-mars, avril-mai, juin-juillet, août-septembre, octobre-novembre, décembre-janvier",
}


def descriptif_tarif(client):
    """Le tarif de CE client, en chiffres tout compris (TVA, redevances et taxes par kWh incluses), pour l'afficher
    sans que l'écran ne recopie la grille. Source unique : avant le 20/10/2026, la page Paramètres avait sa propre
    copie de la grille, en kWh « par mois » et avec des seuils faux (40, 99, 198, 297 au lieu de 80, 198, 396, 594
    par bimestre), et montrait des tranches à un client prépayé qui n'en a pas."""
    amperage = getattr(client, "amperage", 10) or 10
    type_tarif = getattr(client, "typeTarif", "general") or "general"
    abidjan = _client_abidjan(client)
    tarif, amp = _categorie(amperage, type_tarif)
    kva = PUISSANCE_KW[amp]
    base = {"type_tarif": tarif, "amperage": amp, "puissance_kva": float(kva), "abidjan": abidjan,
            "tva_incluse": True}
    if est_prepaye(client):
        prix, d = prix_kwh_prepaye(amp, tarif, abidjan)
        return dict(base, regime="prepaye", prix_kwh=float(_round(prix)), seuil_t1_kwh=None,
                    prix_t1=None, prix_t2=None, sens=None, abonnement_periode=None, cycle=None)
    f = calculer_facture_bimestre(0, amp, tarif, abidjan)
    taxes = f["taxes_par_kwh"]
    groupe = getattr(client, "groupeFacturation", "GF1") or "GF1"
    return dict(base, regime="postpaye",
                prix_kwh=float(_round(f["tranche1_prix"] + taxes)),
                seuil_t1_kwh=float(f["seuil_t1_kwh"]),
                prix_t1=float(_round(f["tranche1_prix"] + taxes)),
                prix_t2=float(_round(f["tranche2_prix"] + taxes)),
                # social : la 2ᵉ tranche coûte plus cher (progressif) ; général : moins cher (dégressif)
                sens="progressif" if tarif == "social" else "degressif",
                abonnement_periode=float(f["prime_fixe_fcfa"] + f["taxe_fixe_fcfa"]),
                cycle={"groupe": groupe, "libelle": CYCLES.get(groupe, CYCLES["GF1"])})
