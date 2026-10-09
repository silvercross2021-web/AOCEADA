"""Les VRAIES données AOCEDA du client connecté, pour l'assistant : les 9 outils d'AOCEDA (apps/ai_assistant/outils.py :
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
            r["facture_fcfa"] = int(float(facture_mois_a_ce_jour(c)["detail"]["total_fcfa"]))
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

    def executer(self, nom, args):
        """(résultat de l'outil (dict), libellé) ; {"erreur": ...} si quelque chose ne va pas (jamais d'exception)."""
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
