"""Les VRAIES données AOCEDA du client connecté, pour l'assistant : les outils d'AOCEDA (apps/ai_assistant/outils.py :
consommation, appareils, factures, prévision, crédit, alertes, interventions...), appelés directement, en lecture seule.

Au laboratoire, ces outils tournaient dans un programme à part (le « pont »), sur un compte de démonstration. Dans AOCEDA,
ils lisent la base du serveur pour LE client qui pose la question (jamais un autre) :
  - DonneesClient(client) a la même forme que l'ancien pont (specs, executer, disponible...) : l'appel Live et la chaîne
    du baoulé l'utilisent sans changement ;
  - DONNEES (variable de contexte) porte celui de la question en cours : le chat écrit (fournisseurs.flux_deepseek :
    appel d'outils de DeepSeek), le dioula et le baoulé le trouvent là, sans le passer de fonction en fonction.
"""
import contextvars

from django.db import close_old_connections

# DonneesClient de la question en cours (posé par la vue à chaque morceau de réponse, comme fournisseurs.ARRET)
DONNEES = contextvars.ContextVar("donnees_client", default=None)


class DonneesClient:
    """Lecture seule des données d'UN client. Même interface que l'ancien pont du laboratoire."""

    compte_trouve = True

    def __init__(self, client):
        from apps.ai_assistant.outils import OUTILS_SPEC
        self.client = client
        self.specs = OUTILS_SPEC
        self.erreur = None
        import threading
        self._memo, self._verrous_cle, self._verrou_memo = {}, {}, threading.Lock()      # résultats d'outils récents (voir executer)

    def disponible(self):
        return self.client is not None

    def demarrer(self):
        """Rien à démarrer : les outils sont dans le serveur (au laboratoire, le pont chargeait Django à part)."""

    def arreter(self):
        """Rien à arrêter."""

    def resume(self):
        """Résumé LÉGER, RÉEL et sans donnée personnelle du client, pour la consigne : l'essentiel d'AUJOURD'HUI. Tout le
        reste (autres périodes, historique, prévision, crédit, alertes...) est lu à la demande par les outils. Mêmes
        fonctions que le tableau de bord (repris de l'ancien assistant d'AOCEDA). Jamais d'exception : {} si illisible."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.analytics.tarifs_cie import prix_kwh_tout_compris
        from apps.analytics.views import _kwh_consommes, facture_mois_a_ce_jour
        from apps.sensors.models import Capteur, MesureEnergie

        close_old_connections()
        c, r = self.client, {}
        try:
            now = timezone.now()
            debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
            r["kwh_jour"] = round(float(_kwh_consommes(c, debut_jour, now)), 2)
            frais = now - timedelta(seconds=60)
            r["puissance_w"] = int(sum(float(m.puissance) for m in (
                MesureEnergie.objects.filter(capteur=cap, timestamp__gte=frais).order_by("-timestamp").first()
                for cap in Capteur.objects.filter(client=c, actif=True)) if m))
            # AOCEDA : facture de la PÉRIODE en cours (bimestre en postpayé, mois en prépayé)
            fac = facture_mois_a_ce_jour(c)
            r["facture_fcfa"] = int(float(fac["detail"]["total_fcfa"]))
            r["facture_periode"] = f'{"bimestre" if fac["periode"]["type"] == "bimestre" else "mois"} {fac["mois_libelle"]}' 
            r["prix_kwh"] = round(float(prix_kwh_tout_compris(c)), 1)
        except Exception:
            pass
        try:
            # noms choisis par le client (« Clim salon »…) : pas de donnée personnelle, et indispensables pour nommer
            # correctement ses appareils
            r["appareils"] = list(Capteur.objects.filter(client=c).values_list("nom", flat=True))
            r.update(type_compteur=getattr(c, "typeCompteur", "postpaye"), type_tarif=getattr(c, "typeTarif", "general"),
                     amperage=getattr(c, "amperage", 10), mode_absence=bool(getattr(c, "modeAbsenceActif", False)))
        except Exception:
            pass
        finally:
            close_old_connections()
        return r

    MEMO_S = 20                                  # un résultat lu il y a moins de 20 s est réutilisé (la relance de DeepSeek refait les mêmes lectures)
    NON_MEMORISES = ("preparer_coupure",)         # fabrique une carte Oui / Non avec une heure d'expiration : jamais réutilisée

    def _cle_memo(self, nom, args):
        import json
        return (nom, json.dumps(args or {}, sort_keys=True, default=str))

    def executer(self, nom, args):
        """(résultat de l'outil (dict), libellé) ; {"erreur": ...} si quelque chose ne va pas (jamais d'exception).

        Deux candidats DeepSeek (la relance part après 2,5 s) appellent les MÊMES outils avec les MÊMES arguments : le 2e réutilise le
        résultat du 1er (11/11/2026 : lectures refaites, lignes « Je lis vos données » en double). Seuls les résultats sans erreur,
        pendant MEMO_S secondes ; une COPIE est rendue (l'appelant retire la carte du résultat)."""
        import copy
        import threading
        import time
        if nom in self.NON_MEMORISES:
            return self._executer(nom, args)
        cle = self._cle_memo(nom, args)
        with self._verrou_memo:
            verrou_cle = self._verrous_cle.setdefault(cle, threading.Lock())
        with verrou_cle:                         # le 2e candidat attend le 1er au lieu de refaire la lecture
            memo = self._memo
            entree = memo.get(cle)
            if entree and time.time() - entree[0] < self.MEMO_S:
                return copy.deepcopy(entree[1]), entree[2]
            resultat, label = self._executer(nom, args)
            if isinstance(resultat, dict) and not resultat.get("erreur"):
                memo[cle] = (time.time(), copy.deepcopy(resultat), label)
            return resultat, label

    def _executer(self, nom, args):
        from apps.ai_assistant.outils import executer_outil, label_outil
        close_old_connections()                 # appelé depuis des fils de calcul : connexion à la base fraîche
        try:
            return executer_outil(self.client, nom, args or {}), label_outil(nom)
        except Exception as e:                  # l'assistant reçoit l'erreur et la dit, il ne plante jamais
            return {"erreur": f"Lecture impossible : {e}"[:200]}, nom
        finally:
            close_old_connections()


def courantes():
    """Données du client de la question en cours, ou None (essais sans client)."""
    return DONNEES.get()
