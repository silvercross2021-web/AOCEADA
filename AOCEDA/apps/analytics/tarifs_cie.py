"""
Moteur tarifaire officiel CIE, grille domestique basse tension.

Source de vérité : EXPLICATION_TARIFAIRE.md (racine du projet), vérifié sur
cie.ci, ANARE-CI et PEPT en juin 2026. Grille en vigueur depuis la hausse de
+10 % du 1er janvier 2024 (grille ANARE 2019 × 1,10).

Principes appliqués :
- Calcul MENSUEL (grille bimestrielle ÷ 2), conforme aux compteurs nouvelle
  génération et au rythme de paiement réel des ménages.
- Prix TTC : la TVA de 18 % est DÉJÀ incluse, on ne l'ajoute jamais.
- Deux tranches dont le seuil dépend de l'ampérage (180 h × P souscrite par
  bimestre, soit 90 h × P par mois). Social progressif, général dégressif.
- Taxes d'État par kWh (électrification rurale + RTI + ordures ménagères)
  et petite part fixe mensuelle.
"""
from decimal import Decimal, ROUND_HALF_UP


# Puissance souscrite par ampérage (monophasé 220 V) : P = U × I
PUISSANCE_KW = {5: Decimal("1.1"), 10: Decimal("2.2"), 15: Decimal("3.3")}

# Grille MENSUELLE (= grille bimestrielle officielle ÷ 2), montants TTC en FCFA
GRILLE_MENSUELLE = {
    "social": {
        # Tarif Domestique Social monophasé 5A, TVA 0 sur la tranche 1
        "prime_fixe": Decimal("307.45"),
        "seuil_t1": Decimal("40"),       # 80 kWh / bimestre
        "prix_t1": Decimal("31.72"),
        "prix_t2": Decimal("65.11"),
        "taxes_par_kwh": Decimal("5.50"),
        "taxe_fixe": Decimal("0.50"),
    },
    "general": {
        # NB : pas de « 5A général » à la CIE, le 5A domestique relève du Tarif
        # Social (voir parametres_tarif, qui bascule tout 5A vers le social).
        10: {
            "prime_fixe": Decimal("809.02"),
            "seuil_t1": Decimal("198"),   # 90 h × 2,2 kW (396 kWh/bim, conf. ANARE)
            "prix_t1": Decimal("86.92"),
            "prix_t2": Decimal("75.34"),
        },
        15: {
            "prime_fixe": Decimal("889.92"),
            "seuil_t1": Decimal("297"),   # 90 h × 3,3 kW (594 kWh/bim, conf. ANARE)
            "prix_t1": Decimal("95.62"),
            "prix_t2": Decimal("82.86"),
        },
    },
}

# Taxes et redevances d'État (tarif général) : élec. rurale 1,06 + RTI 2,00
# + ordures ménagères Abidjan 2,50 = 5,56 F/kWh, + 100 F/bimestre fixe.
TAXES_PAR_KWH_GENERAL = Decimal("5.56")
TAXE_FIXE_MENSUELLE_GENERAL = Decimal("50")

AMPERAGES_VALIDES = (5, 10, 15)


def _round(montant):
    return Decimal(montant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parametres_tarif(amperage=10, type_tarif="general"):
    """Renvoie les paramètres de grille applicables.

    Règles CIE appliquées de façon cohérente :
    - Le 5A domestique relève TOUJOURS du Tarif Social (le 5A « général »
      n'existe pas) → tout 5A est facturé au social.
    - Le tarif social n'existe qu'en 5A → un social demandé en 10/15A retombe
      sur le général de l'ampérage correspondant.
    """
    amperage = int(amperage) if amperage in AMPERAGES_VALIDES else 10
    if amperage == 5:
        p = dict(GRILLE_MENSUELLE["social"])
        p["type_tarif"] = "social"
    else:
        base = GRILLE_MENSUELLE["general"][amperage]
        p = dict(base)
        p["taxes_par_kwh"] = TAXES_PAR_KWH_GENERAL
        p["taxe_fixe"] = TAXE_FIXE_MENSUELLE_GENERAL
        p["type_tarif"] = "general"
    p["amperage"] = amperage
    p["puissance_kw"] = PUISSANCE_KW[amperage]
    return p


def calculer_facture_mensuelle(kwh, amperage=10, type_tarif="general"):
    """
    Calcule la facture mensuelle officielle CIE pour `kwh` consommés.

    Renvoie la décomposition complète (tout en Decimal, FCFA TTC) :
    tranche 1, tranche 2, prime fixe, taxes, total, prix moyen effectif.
    """
    kwh = Decimal(str(kwh))
    if kwh < 0:
        kwh = Decimal("0")
    p = parametres_tarif(amperage, type_tarif)

    kwh_t1 = min(kwh, p["seuil_t1"])
    kwh_t2 = max(Decimal("0"), kwh - p["seuil_t1"])
    montant_t1 = _round(kwh_t1 * p["prix_t1"])
    montant_t2 = _round(kwh_t2 * p["prix_t2"])
    # Les taxes ont DEUX parts : une variable (par kWh) et une petite part FIXE
    # mensuelle. On les expose séparément pour un affichage clair côté client
    # (« abonnement fixe » vs « votre consommation »).
    taxes_variable = _round(kwh * p["taxes_par_kwh"])
    taxe_fixe = _round(p["taxe_fixe"])
    taxes = _round(kwh * p["taxes_par_kwh"] + p["taxe_fixe"])
    total = _round(montant_t1 + montant_t2 + p["prime_fixe"] + taxes)

    return {
        "kwh": _round(kwh),
        "type_tarif": p["type_tarif"],
        "amperage": p["amperage"],
        "seuil_t1_kwh": p["seuil_t1"],
        "tranche1_kwh": _round(kwh_t1),
        "tranche1_prix": p["prix_t1"],
        "tranche1_fcfa": montant_t1,
        "tranche2_kwh": _round(kwh_t2),
        "tranche2_prix": p["prix_t2"],
        "tranche2_fcfa": montant_t2,
        "prime_fixe_fcfa": p["prime_fixe"],
        "taxes_fcfa": taxes,
        "taxes_variable_fcfa": taxes_variable,
        "taxe_fixe_fcfa": taxe_fixe,
        "taxes_par_kwh": p["taxes_par_kwh"],
        "total_fcfa": total,
        # Prix moyen effectif (utile pour les tooltips et le prépayé)
        "prix_moyen_kwh": _round(total / kwh) if kwh > 0 else _round(p["prix_t1"] + p["taxes_par_kwh"]),
        "tva_incluse": True,
    }


def calculer_facture_pour_client(kwh, client):
    """Variante pratique : lit l'ampérage et le type de tarif sur le Client."""
    return calculer_facture_mensuelle(
        kwh,
        amperage=getattr(client, "amperage", 10) or 10,
        type_tarif=getattr(client, "typeTarif", "general") or "general",
    )


def prix_kwh_tout_compris(client):
    """Prix marginal tranche 1 + taxes, sert à estimer le crédit prépayé."""
    p = parametres_tarif(
        getattr(client, "amperage", 10) or 10,
        getattr(client, "typeTarif", "general") or "general",
    )
    return _round(p["prix_t1"] + p["taxes_par_kwh"])
