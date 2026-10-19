"""Villes de Côte d'Ivoire et leurs coordonnées (19/10/2026) : la prévision lit la température du jour de la ville du
foyer (apps.analytics.meteo). Une ville absente de la liste : on prend la plus proche, à régler par le technicien."""

VILLES = {
    "Abidjan": (5.36, -4.01),
    "Abengourou": (6.73, -3.49),
    "Agboville": (5.93, -4.22),
    "Bondoukou": (8.04, -2.80),
    "Bouaflé": (6.99, -5.74),
    "Bouaké": (7.69, -5.03),
    "Daloa": (6.88, -6.45),
    "Divo": (5.84, -5.36),
    "Ferkessédougou": (9.59, -5.20),
    "Gagnoa": (6.13, -5.95),
    "Grand-Bassam": (5.21, -3.74),
    "Korhogo": (9.46, -5.63),
    "Man": (7.41, -7.55),
    "Odienné": (9.51, -7.56),
    "San-Pédro": (4.75, -6.64),
    "Séguéla": (7.96, -6.67),
    "Soubré": (5.79, -6.61),
    "Yamoussoukro": (6.82, -5.28),
}
VILLE_PAR_DEFAUT = "Abidjan"
CHOIX_VILLES = [(v, v) for v in VILLES]
