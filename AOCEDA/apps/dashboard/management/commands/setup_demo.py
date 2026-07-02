"""Commande de démonstration AOCEDA — données extrêmement complètes.

Comptes créés (mot de passe : Password123!) :
  adjoua.konate@gmail.com     — Client prépayé 10A  (villa Cocody)
  fatou.traore@gmail.com      — Client postpayé 15A (villa Marcory, tarif général)
  kouame.bamba@gmail.com      — Client postpayé 5A  (studio Yopougon, tarif social)
  moussa.diarrassouba@aoceda.ci — Technicien
  admin@aoceda.ci              — Administrateur (superuser)

Données générées pour adjoua.konate (compte principal) :
  - 2 ESP32 (1 actif + 1 hors-ligne)
  - 3 capteurs (Salon/Cuisine, Chambre, Climatiseur)
  - 60 jours × 24 h de mesures horaires réalistes (4 320 mesures / capteur)
  - 10 alertes horodatées distinctement (auto_now_add → .update() requis)
  - 6 mois de prévisions avec annee_mois correct
  - 5 interventions couvrant tout le cycle de vie
"""
import random
from django.core.management.base import BaseCommand  # pyrefly: ignore
from django.utils import timezone  # pyrefly: ignore
from datetime import timedelta
from decimal import Decimal
from apps.accounts.models import Client, Technicien, Administrateur
from apps.sensors.models import Dispositif, Capteur, MesureEnergie, Intervention, RapportIntervention
from apps.alerts.models import RegleDetection, Alerte
from apps.analytics.models import Prevision


# ─── profil de puissance horaire (Watts, par circuit) ─────────────────────────
def _profil_heure(heure: int, circuit: str, variabilite: float = 1.0) -> float:
    """Profil de consommation réaliste par heure (0–23) et circuit.
    Intègre les habitudes ivoiriennes : repas 12 h–14 h, soirée 19 h–22 h,
    climatiseur pic nocturne 23 h–05 h.
    """
    random.seed()  # chaque appel doit être pseudo-aléatoire non reproductible

    if circuit == "salon":
        # Veille : TV, Box, réfrigérateur (~90 W fond de roulement)
        base = {
            0: 60, 1: 55, 2: 55, 3: 55, 4: 60, 5: 70,
            6: 280, 7: 520, 8: 380, 9: 280, 10: 210, 11: 250,
            12: 680, 13: 590, 14: 350, 15: 240, 16: 220, 17: 310,
            18: 780, 19: 1450, 20: 1680, 21: 1420, 22: 890, 23: 180,
        }
    elif circuit == "chambre":
        # Chambre : chargeurs, lampes, ventilateur
        base = {
            0: 35, 1: 30, 2: 30, 3: 30, 4: 35, 5: 40,
            6: 90, 7: 150, 8: 110, 9: 80, 10: 60, 11: 65,
            12: 120, 13: 110, 14: 90, 15: 75, 16: 70, 17: 85,
            18: 200, 19: 380, 20: 420, 21: 350, 22: 280, 23: 90,
        }
    else:  # climatiseur
        # Clim : quasi-inactif le jour si occupants absents, pic nuit et soirée
        base = {
            0: 1200, 1: 1150, 2: 1100, 3: 1100, 4: 1150, 5: 1200,
            6: 600, 7: 400, 8: 280, 9: 200, 10: 180, 11: 220,
            12: 350, 13: 420, 14: 380, 15: 300, 16: 250, 17: 320,
            18: 680, 19: 950, 20: 1100, 21: 1250, 22: 1380, 23: 1350,
        }

    val = base[heure] * variabilite
    bruit = random.uniform(0.88, 1.12)
    return max(5.0, round(val * bruit, 1))


class Command(BaseCommand):
    help = "Configure le système avec des données de démonstration extrêmement complètes."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Supprime toutes les mesures/alertes/prévisions avant de recréer.')

    def handle(self, *args, **options):
        reset = options.get('reset', False)
        now = timezone.now()
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nAOCEDA -- Initialisation des donnees de demonstration\n"
        ))

        # ── 1. Comptes ────────────────────────────────────────────────────────
        self.stdout.write("1/9  Création des comptes utilisateurs...")
        client = self._creer_ou_mettre_a_jour_client(
            email="adjoua.konate@gmail.com",
            nom="Konaté Adjoua",
            typeLogement="Villa",
            adresse="Résidence Les Palmiers, Apt 3B, Cocody, Abidjan",
            numeroCIE="CI-ABJ-2024-87410",
            amperage=10, typeTarif="general", typeCompteur="prepaye",
            creditPrepaye_FCFA=Decimal("28500.00"),
            telephone="+225 07 12 34 56 78",
        )
        client2 = self._creer_ou_mettre_a_jour_client(
            email="fatou.traore@gmail.com",
            nom="Traoré Fatou",
            typeLogement="Villa",
            adresse="Rue des Bougainvilliers, Marcory, Abidjan",
            numeroCIE="CI-ABJ-2024-31250",
            amperage=15, typeTarif="general", typeCompteur="postpaye",
            creditPrepaye_FCFA=Decimal("0.00"),
            telephone="+225 05 77 88 99 10",
        )
        client3 = self._creer_ou_mettre_a_jour_client(
            email="kouame.bamba@gmail.com",
            nom="Bamba Kouamé",
            typeLogement="Studio",
            adresse="Cité Verte, Studio 12, Yopougon, Abidjan",
            numeroCIE="CI-ABJ-2024-60011",
            amperage=5, typeTarif="social", typeCompteur="postpaye",
            creditPrepaye_FCFA=Decimal("0.00"),
            telephone="+225 01 02 03 04 05",
        )

        technicien = self._creer_technicien()
        self._creer_admin()

        # ── 2. Dispositifs ────────────────────────────────────────────────────
        self.stdout.write("2/9  Création des dispositifs ESP32...")
        device, _ = Dispositif.objects.get_or_create(
            client=client, numeroSerie="ESP32-WR-2401",
            defaults={
                "apiKeyDevice": "AK-ADJK-3F9K2L7Q-A1B2",
                "firmwareVersion": "v2.3.1",
                "estConnecté": True,
                "adresseIP": "192.168.1.47",
            }
        )
        device_hors_ligne, _ = Dispositif.objects.get_or_create(
            client=client, numeroSerie="ESP32-WR-2402",
            defaults={
                "apiKeyDevice": "AK-ADJK-7Q2L9F3K-C3D4",
                "firmwareVersion": "v2.1.3",
                "estConnecté": False,
                "adresseIP": "192.168.1.48",
            }
        )
        device2, _ = Dispositif.objects.get_or_create(
            client=client2, numeroSerie="ESP32-WR-2403",
            defaults={
                "apiKeyDevice": "AK-FATT-8P1M4N6R-E5F6",
                "firmwareVersion": "v2.3.1",
                "estConnecté": True,
                "adresseIP": "192.168.2.12",
            }
        )
        device3, _ = Dispositif.objects.get_or_create(
            client=client3, numeroSerie="ESP32-WR-2404",
            defaults={
                "apiKeyDevice": "AK-KOUB-2K5R8M1P-G7H8",
                "firmwareVersion": "v2.2.0",
                "estConnecté": True,
                "adresseIP": "192.168.3.22",
            }
        )

        # ── 3. Capteurs ───────────────────────────────────────────────────────
        self.stdout.write("3/9  Création des capteurs ZMCT103C...")
        s_salon, _ = Capteur.objects.get_or_create(
            client=client, nom="Salon / Cuisine",
            defaults={"dispositif": device, "type": "Courant",
                      "valeurMax": Decimal("2000.00"), "actif": True,
                      "coeffCalibration": Decimal("0.9820")})
        s_chambre, _ = Capteur.objects.get_or_create(
            client=client, nom="Chambre principale",
            defaults={"dispositif": device, "type": "Courant",
                      "valeurMax": Decimal("1500.00"), "actif": True,
                      "coeffCalibration": Decimal("0.9910")})
        s_clim, _ = Capteur.objects.get_or_create(
            client=client, nom="Climatiseur (circuit dédié)",
            defaults={"dispositif": device, "type": "Courant",
                      "valeurMax": Decimal("1800.00"), "actif": True,
                      "coeffCalibration": Decimal("0.9975")})
        # Capteur client2 (Fatou)
        s_f_salon, _ = Capteur.objects.get_or_create(
            client=client2, nom="Salon principal",
            defaults={"dispositif": device2, "type": "Courant",
                      "valeurMax": Decimal("3000.00"), "actif": True,
                      "coeffCalibration": Decimal("1.0000")})
        # Capteur client3 (Kouamé)
        s_k_salon, _ = Capteur.objects.get_or_create(
            client=client3, nom="Circuit général",
            defaults={"dispositif": device3, "type": "Courant",
                      "valeurMax": Decimal("1000.00"), "actif": True,
                      "coeffCalibration": Decimal("0.9850")})

        # ── 4. Règles de détection ────────────────────────────────────────────
        self.stdout.write("4/9  Règles de détection...")
        for capteur, seuil in [
            (s_salon,  Decimal("2000.00")),
            (s_chambre, Decimal("1500.00")),
            (s_clim,   Decimal("1800.00")),
        ]:
            RegleDetection.objects.get_or_create(
                client=client, capteur=capteur,
                defaults={"puissanceMax_W": seuil, "surveilleNuit": True,
                          "heureDébutNuit": "00:00:00", "heureFinNuit": "05:00:00"})

        # ── 5. Mesures d'énergie ──────────────────────────────────────────────
        self.stdout.write("5/9  Génération des mesures (60 jours × 3 capteurs × 24 h)...")
        JOURS = 60
        capteurs_def = [
            (s_salon,   "salon",   1.00),
            (s_chambre, "chambre", 1.00),
            (s_clim,    "clim",    1.00),
        ]
        # Jours "froids" (pluie) : consommation clim réduite, salon légèrement plus
        JOURS_PLUIE = {5, 12, 19, 26, 33, 41, 48, 55}

        if reset or not MesureEnergie.objects.filter(capteur=s_salon).exists():
            MesureEnergie.objects.filter(capteur__in=[s_salon, s_chambre, s_clim]).delete()
            mesures = []
            for d_offset in range(JOURS):
                for h in range(24):
                    ts = now - timedelta(days=d_offset, hours=h)
                    for capteur, circuit, _ in capteurs_def:
                        variabilite = 0.60 if (d_offset in JOURS_PLUIE and circuit == "clim") else 1.00
                        # Anomalie de dépassement : il y a 5 jours à 20 h (salon)
                        if d_offset == 5 and h == 20 and circuit == "salon":
                            p = 2480.0
                        # Pic nocturne excessif il y a 12 jours (clim en panne)
                        elif d_offset == 12 and h == 3 and circuit == "clim":
                            p = 1950.0
                        else:
                            p = _profil_heure(h, circuit, variabilite)
                        v = 220.0
                        c = round(p / v, 4)
                        e = round(p / 1000.0, 5)
                        mesures.append(MesureEnergie(
                            capteur=capteur,
                            puissance=Decimal(str(p)),
                            courant=Decimal(str(c)),
                            energie=Decimal(str(e)),
                            tension_V=Decimal("220.00"),
                            facteur_puissance=Decimal("0.90"),
                            timestamp=ts,
                        ))
            MesureEnergie.objects.bulk_create(mesures, batch_size=500)
            self.stdout.write(self.style.SUCCESS(
                f"   {len(mesures)} mesures créées ({JOURS} j × 3 capteurs × 24 h)."))
        else:
            self.stdout.write("   Mesures déjà présentes — ignorées (utilisez --reset pour régénérer).")

        # Même chose pour les clients secondaires (1 capteur × 30 jours)
        for cli_capteur, cli_circuit in [(s_f_salon, "salon"), (s_k_salon, "chambre")]:
            if not MesureEnergie.objects.filter(capteur=cli_capteur).exists():
                mes2 = []
                for d_offset in range(30):
                    for h in range(24):
                        ts = now - timedelta(days=d_offset, hours=h)
                        p = _profil_heure(h, cli_circuit)
                        mes2.append(MesureEnergie(
                            capteur=cli_capteur,
                            puissance=Decimal(str(p)),
                            courant=Decimal(str(round(p / 220.0, 4))),
                            energie=Decimal(str(round(p / 1000.0, 5))),
                            tension_V=Decimal("220.00"),
                            facteur_puissance=Decimal("0.90"),
                            timestamp=ts,
                        ))
                MesureEnergie.objects.bulk_create(mes2, batch_size=500)

        # Mise à jour derniereLecture
        for cap in [s_salon, s_chambre, s_clim, s_f_salon, s_k_salon]:
            cap.derniereLecture = now
            cap.save(update_fields=["derniereLecture"])

        # ── 6. Alertes ────────────────────────────────────────────────────────
        self.stdout.write("6/9  Création des alertes...")
        Alerte.objects.filter(client=client).delete()
        # Note : auto_now_add=True empêche de passer createdAt au create().
        # On utilise .update() sur le pk juste après le create().
        alertes_def = [
            # (type,                    message,                                    lue,  sev,          j_ago, h_ago)
            ("DEPASSEMENT_SEUIL",
             "Pic de consommation détecté : 2 480 W sur Salon/Cuisine (seuil : 2 000 W). "
             "Vérifiez si un appareil est resté allumé.", False, "Critique", 5, 20),
            ("CONSOMMATION_NOCTURNE",
             "Consommation nocturne anormale détectée entre 02 h et 04 h sur le circuit Climatiseur "
             "(puissance mesurée : 1 950 W). Probable dysfonctionnement du thermostat.", False, "Avertissement", 12, 3),
            ("CREDIT_BAS",
             "Crédit prépayé estimé bas : environ 8 400 FCFA restants (~6 jours d'autonomie). "
             "Pensez à recharger pour éviter une coupure.", False, "Avertissement", 3, 10),
            ("DEPASSEMENT_SEUIL",
             "Dépassement du seuil nocturne sur Chambre principale : 620 W détectés à 02 h 15 "
             "(seuil nocturne : 400 W). Anomalie résolue automatiquement.", True, "Info", 18, 2),
            ("CREDIT_BAS",
             "Crédit prépayé épuisé à < 5 000 FCFA. Rechargez immédiatement pour éviter "
             "l'interruption du service.", True, "Critique", 22, 14),
            ("CONSOMMATION_NOCTURNE",
             "Consommation nocturne stabilisée — circuit Salon/Cuisine conforme au seuil (78 W).",
             True, "Info", 25, 22),
            ("DEPASSEMENT_SEUIL",
             "Pointe de consommation en soirée : 2 310 W à 20 h 45. Probable utilisation "
             "simultanée du four et de la climatisation.", True, "Avertissement", 31, 20),
            ("CREDIT_BAS",
             "Alerte crédit bas — 12 700 FCFA restants (~9 jours d'autonomie). Recharge recommandée "
             "avant fin de mois.", True, "Avertissement", 38, 9),
            ("CONSOMMATION_NOCTURNE",
             "Veille nocturne stabilisée. Consommation hors-heures conforme (55 W moy. entre 01 h–05 h).",
             True, "Info", 45, 1),
            ("DEPASSEMENT_SEUIL",
             "Pic isolé détecté : 1 890 W sur Climatiseur (seuil : 1 800 W). Épisode de chaleur "
             "extrême — pas d'anomalie matérielle.", True, "Info", 52, 15),
        ]
        for (type_, msg, lue, sev, j, h) in alertes_def:
            a = Alerte.objects.create(client=client, type=type_, message=msg,
                                      lue=lue, sévérité=sev)
            Alerte.objects.filter(pk=a.pk).update(
                createdAt=now - timedelta(days=j, hours=h))
        self.stdout.write(self.style.SUCCESS(f"   {len(alertes_def)} alertes créées."))

        # Alertes pour les clients secondaires
        Alerte.objects.filter(client=client2).delete()
        a2 = Alerte.objects.create(
            client=client2, type="DEPASSEMENT_SEUIL",
            message="Dépassement détecté : 3 200 W sur Salon principal (seuil : 3 000 W).",
            lue=False, sévérité="Critique")
        Alerte.objects.filter(pk=a2.pk).update(createdAt=now - timedelta(days=2, hours=18))

        Alerte.objects.filter(client=client3).delete()
        a3 = Alerte.objects.create(
            client=client3, type="CREDIT_BAS",
            message="Crédit restant estimé à 3 800 FCFA (~4 jours). Rechargez rapidement.",
            lue=False, sévérité="Avertissement")
        Alerte.objects.filter(pk=a3.pk).update(createdAt=now - timedelta(days=1, hours=6))

        # ── 7. Prévisions (6 mois) ────────────────────────────────────────────
        self.stdout.write("7/9  Création des prévisions de facturation (6 mois)...")
        Prevision.objects.filter(client=client).delete()
        # Données mensuelles réalistes (kWh, FCFA) pour un foyer ivoirien 10A
        previsions_data = [
            # (annee_mois, moisConcerné,    kWh,    FCFA,    écart%)
            ("2026-06", "Juin 2026",     Decimal("284.00"), Decimal("24820.00"), Decimal("4.40")),
            ("2026-05", "Mai 2026",      Decimal("272.00"), Decimal("23750.00"), Decimal("12.40")),
            ("2026-04", "Avril 2026",    Decimal("242.00"), Decimal("21180.00"), Decimal("-3.20")),
            ("2026-03", "Mars 2026",     Decimal("250.00"), Decimal("21890.00"), Decimal("2.10")),
            ("2026-02", "Février 2026",  Decimal("245.00"), Decimal("21440.00"), Decimal("-6.80")),
            ("2026-01", "Janvier 2026",  Decimal("263.00"), Decimal("22940.00"), Decimal("8.60")),
        ]
        for annee_mois, mois, kwh, fcfa, ecart in previsions_data:
            Prevision.objects.create(
                client=client,
                annee_mois=annee_mois,
                moisConcerné=mois,
                consomméeEstimée_kWh=kwh,
                montantEstimé_FCFA=fcfa,
                écartSurMoisPrécédent=ecart,
            )
        self.stdout.write(self.style.SUCCESS(f"   {len(previsions_data)} prévisions créées."))

        # ── 8. Technicien + Interventions ─────────────────────────────────────
        self.stdout.write("8/9  Création des interventions...")
        Intervention.objects.filter(technicien=technicien, client=client).delete()

        # Intervention 1 — INSTALLATION initiale (il y a 60 jours) → TERMINEE
        iv1 = Intervention.objects.create(
            technicien=technicien, client=client, dispositif=device,
            capteur=s_salon,
            typeIntervention="INSTALLATION",
            description=(
                "Installation initiale du système AOCEDA : pose du boîtier ESP32-WR-2401, "
                "raccordement de 3 capteurs ZMCT103C (Salon/Cuisine, Chambre, Climatiseur), "
                "configuration Wi-Fi et enregistrement dans la plateforme."
            ),
            dateIntervention=now - timedelta(days=60),
            statut="TERMINEE",
            résultat=(
                "Installation conforme. 3 capteurs actifs. Latence mesurée : 84 ms. "
                "Consommation de veille ≈ 58 W (réfrigérateur + box internet). "
                "KPI installation (< 15 min) : validé en 11 min."
            ),
        )
        RapportIntervention.objects.create(
            intervention=iv1,
            contenu=(
                "MATÉRIEL POSÉ\n"
                "— 1× ESP32 WROOM-32 (firmware v2.3.1)\n"
                "— 3× capteur de courant ZMCT103C (pinces tores)\n"
                "— Boîtier de protection IP44\n\n"
                "PROCÉDURE\n"
                "1. Identification des circuits dans le tableau électrique.\n"
                "2. Pose des pinces tores sur les phases Salon/Cuisine, Chambre et Climatiseur.\n"
                "3. Configuration Wi-Fi SSID « AOCEDA_Konate_2024 » (canal 6).\n"
                "4. Enregistrement dans la plateforme (clé API générée).\n"
                "5. Test de transmission : 5 mesures reçues en 8 s.\n\n"
                "CALIBRATION INITIALE\n"
                "Salon   : Kcal = 0,9820 (charge de référence : ampoule 100 W).\n"
                "Chambre : Kcal = 0,9910 (charge de référence : ampoule 100 W).\n"
                "Clim    : Kcal = 0,9975 (charge de référence : fer à repasser 1 000 W)."
            ),
            conclusion=(
                "Système opérationnel. Aucune anomalie. Client formé à l'interface web. "
                "Prochaine visite planifiée dans 30 jours (calibration de contrôle)."
            ),
            estValidé=True,
        )

        # Intervention 2 — CALIBRATION salon (il y a 30 jours) → TERMINEE
        iv2 = Intervention.objects.create(
            technicien=technicien, client=client, dispositif=device,
            capteur=s_salon,
            typeIntervention="CALIBRATION",
            description=(
                "Calibration de contrôle du capteur Salon/Cuisine suite à un écart de +1,4 % "
                "constaté lors de la comparaison avec la facture CIE du mois précédent."
            ),
            dateIntervention=now - timedelta(days=30),
            statut="TERMINEE",
            résultat="Coefficient ajusté : Kcal = 0,9803. Erreur résiduelle < 0,3 %. Conforme.",
        )
        RapportIntervention.objects.create(
            intervention=iv2,
            contenu=(
                "Méthode : charge de référence (ampoule 100 W + multimètre Fluke 117).\n"
                "Mesure avant correction : 101,4 W (écart +1,4 %).\n"
                "Nouveau coefficient appliqué : 0,9803.\n"
                "Mesure après correction : 100,1 W (écart +0,1 %)."
            ),
            conclusion="Capteur Salon/Cuisine recalibré avec succès. Kcal mis à jour dans la plateforme.",
            estValidé=True,
        )

        # Intervention 3 — CALIBRATION climatiseur (il y a 15 jours) → TERMINEE
        iv3 = Intervention.objects.create(
            technicien=technicien, client=client, dispositif=device,
            capteur=s_clim,
            typeIntervention="CALIBRATION",
            description=(
                "Recalibration préventive du capteur Climatiseur après alerte de consommation "
                "nocturne excessive (1 950 W détectés à 03 h)."
            ),
            dateIntervention=now - timedelta(days=15),
            statut="TERMINEE",
            résultat=(
                "Capteur conforme (Kcal = 0,9975 validé). La surconsommation était réelle : "
                "le thermostat du climatiseur était défaillant. Client informé pour remplacement."
            ),
        )
        RapportIntervention.objects.create(
            intervention=iv3,
            contenu=(
                "Diagnostic réalisé avec charge de référence (résistance chauffante 1 500 W).\n"
                "Mesure capteur : 1 500,8 W — écart < 0,1 %. Capteur intègre.\n"
                "Vérification du climatiseur : thermostat bloqué en mode refroidissement continu.\n"
                "Recommandation : remplacement du thermostat (pièce : DAIKIN FTX20KV)."
            ),
            conclusion=(
                "Capteur validé. Anomalie identifiée côté climatiseur (thermostat). "
                "Rapport transmis au client pour réparation."
            ),
            estValidé=True,
        )

        # Intervention 4 — PANNE Wi-Fi (il y a 7 jours) → TERMINEE
        iv4 = Intervention.objects.create(
            technicien=technicien, client=client, dispositif=device,
            typeIntervention="PANNE",
            description=(
                "Perte de connexion du dispositif ESP32-WR-2401 pendant 4 h (détectée par le "
                "système de monitoring heartbeat). Dernière mesure reçue : J-7 à 14 h 22."
            ),
            dateIntervention=now - timedelta(days=7),
            statut="TERMINEE",
            résultat=(
                "Redémarrage du routeur Wi-Fi client. Firmware mis à jour v2.1.3 → v2.3.1. "
                "Reconnexion stable, aucune mesure perdue grâce au tampon local ESP32."
            ),
        )
        RapportIntervention.objects.create(
            intervention=iv4,
            contenu=(
                "Intervention à distance (accès SSH sécurisé via AOCEDA VPN).\n"
                "Cause identifiée : canal Wi-Fi saturé (16 appareils sur canal 6).\n"
                "Actions : redémarrage du routeur, passage canal 6 → canal 11.\n"
                "Firmware mis à jour : v2.3.1 (correctif connexion Wi-Fi robuste).\n"
                "Test post-intervention : 10 cycles de 60 s sans interruption."
            ),
            conclusion="Dispositif opérationnel. Canal Wi-Fi optimisé. Firmware à jour.",
            estValidé=True,
        )

        # Intervention 5 — MAINTENANCE planifiée (demain) → EN_ATTENTE
        Intervention.objects.create(
            technicien=technicien, client=client, dispositif=device,
            typeIntervention="MAINTENANCE",
            description=(
                "Maintenance préventive semestrielle : vérification des connexions, nettoyage "
                "des boîtiers, mise à jour firmware, test de calibration des 3 capteurs et "
                "vérification conformité installation électrique (NFC 15-100)."
            ),
            dateIntervention=now + timedelta(days=1),
            statut="EN_ATTENTE",
        )
        self.stdout.write(self.style.SUCCESS("   5 interventions créées (4 terminées + 1 planifiée)."))

        # ── 9. Administrateur ─────────────────────────────────────────────────
        self.stdout.write("9/9  Vérification du compte administrateur...")
        self._creer_admin()

        self.stdout.write(self.style.SUCCESS(
            "\nInitialisation terminee avec succes !\n"
            "Comptes de demonstration (mot de passe : Password123!)\n"
            "  CLIENT  adjoua.konate@gmail.com  (prepaye 10A)\n"
            "  CLIENT  fatou.traore@gmail.com   (postpaye 15A)\n"
            "  CLIENT  kouame.bamba@gmail.com   (social 5A)\n"
            "  TECH    moussa.diarrassouba@aoceda.ci\n"
            "  ADMIN   admin@aoceda.ci\n"
        ))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _creer_ou_mettre_a_jour_client(self, email, nom, typeLogement, adresse,
                                        numeroCIE, amperage, typeTarif, typeCompteur,
                                        creditPrepaye_FCFA, telephone):
        client, created = Client.objects.get_or_create(
            email=email,
            defaults={
                "nom": nom, "role": "client",
                "typeLogement": typeLogement,
                "tarifkWh_FCFA": Decimal("87.00"),
                "adresse": adresse, "numeroCIE": numeroCIE,
                "amperage": amperage, "typeTarif": typeTarif,
                "typeCompteur": typeCompteur,
                "creditPrepaye_FCFA": creditPrepaye_FCFA,
                "telephone": telephone, "is_active": True,
            }
        )
        if created:
            client.set_password("Password123!")
            client.save()
            self.stdout.write(self.style.SUCCESS(f"   + Client {email} créé."))
        else:
            Client.objects.filter(pk=client.pk).update(
                amperage=amperage, typeTarif=typeTarif,
                typeCompteur=typeCompteur, creditPrepaye_FCFA=creditPrepaye_FCFA,
            )
            self.stdout.write(f"   ~ Client {email} mis à jour.")
        return client

    def _creer_technicien(self):
        email = "moussa.diarrassouba@aoceda.ci"
        tech, created = Technicien.objects.get_or_create(
            email=email,
            defaults={
                "nom": "Diarrassouba Moussa", "role": "technicien",
                "matricule": "TECH-ABJ-0047",
                "specialite": "Installation IoT / Calibration capteurs ZMCT103C",
                "is_active": True,
            }
        )
        if created:
            tech.set_password("Password123!")
            tech.save()
            self.stdout.write(self.style.SUCCESS(f"   + Technicien {email} créé."))
        return tech

    def _creer_admin(self):
        email = "admin@aoceda.ci"
        admin, created = Administrateur.objects.get_or_create(
            email=email,
            defaults={
                "nom": "Administrateur AOCEDA", "role": "admin",
                "niveauAcces": "super", "is_active": True,
                "is_staff": True, "is_superuser": True,
            }
        )
        if created:
            admin.set_password("Password123!")
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"   + Admin {email} créé."))
        elif not admin.is_superuser:
            admin.is_staff = True
            admin.is_superuser = True
            admin.save(update_fields=["is_staff", "is_superuser"])
        return admin
