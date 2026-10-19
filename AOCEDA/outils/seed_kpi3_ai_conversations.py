import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aoceda.settings')
django.setup()

from apps.accounts.models import Client
from apps.ai_assistant.models import Conversation, QuotaIA

# 1. Conversations longues (8 messages) pour Yann Ouattara (marasseediteur@gmail.com)
yann_convs = [
    {
        "titre": "Gestion du climatiseur et optimisation facture",
        "messages": [
            {
                "role": "user",
                "content": "Bonjour, mon climatiseur au salon tourne souvent toute la journée avec la chaleur à Cocody. Ça consomme combien environ par jour ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Ouattara ! D'après vos données, votre climatiseur du salon consomme en moyenne entre 1,2 et 1,5 kWh par heure de fonctionnement. Si vous le laissez allumé 8 heures par jour, cela représente environ 10 à 12 kWh par jour (soit environ 1 000 FCFA/jour au tarif général CIE 15A). Pour réduire cette consommation sans perdre en confort, régler la température à 24°C au lieu de 18°C économise près de 7% par degré !"
            },
            {
                "role": "user",
                "content": "Ah d'accord ! Mais si je mets un programmateur pour qu'il s'éteigne à 3h du matin quand on dort, ça va vraiment réduire la note ?"
            },
            {
                "role": "assistant",
                "content": "Absolument ! Éteindre le climatiseur à 3h du matin (quand la chambre est déjà bien fraîche) vous fera économiser 4 heures de fonctionnement par nuit, soit environ 5 à 6 kWh en moins chaque jour. Sur un mois complet, cela représente une baisse d'environ 15 000 FCFA sur votre facture CIE !"
            },
            {
                "role": "user",
                "content": "C'est super intéressant ça. Et mon réfrigérateur dans la cuisine, est-ce qu'il consomme beaucoup en comparaison ?"
            },
            {
                "role": "assistant",
                "content": "Votre réfrigérateur est bien plus économe : il consomme environ 1,5 à 2 kWh sur 24 heures (soit environ 160 FCFA/jour). Son compresseur s'arrête automatiquement dès que le froid intérieur est stabilisé. Veillez juste à ne pas laisser la porte ouverte trop longtemps et à dépoussiérer la grille arrière 1 fois par an."
            },
            {
                "role": "user",
                "content": "Merci pour ces explications très claires ! Du coup, je peux m'attendre à combien au total pour ma facture ce mois-ci ?"
            },
            {
                "role": "assistant",
                "content": "Avec vos habitudes actuelles et vos 280 kWh déjà mesurés ce mois-ci, votre facture estimée en fin de mois se situe entre 28 500 FCFA et 31 200 FCFA (prime fixe d'abonnement 15A comprise). En appliquant la coupure nocturne de la clim, vous pourriez descendre sous la barre des 20 000 FCFA le mois prochain !"
            }
        ]
    },
    {
        "titre": "Explication des tranches de facturation CIE 15A",
        "messages": [
            {
                "role": "user",
                "content": "Slt, je ne comprends pas trop ma facture CIE. C'est quoi la prime fixe et pourquoi il y a tranche 1 et tranche 2 ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Ouattara ! C'est très simple :\n- La Prime Fixe : C'est le prix de l'abonnement mensuel au réseau CIE (889 FCFA TTC/mois pour votre compteur 15A), dû quoi qu'il arrive.\n- La Tranche 1 : Les premiers kWh du mois (jusqu'à votre quota de 297 kWh en 15A) facturés au tarif normal de 95,62 FCFA / kWh.\n- La Tranche 2 : Les kWh au-delà de 297 kWh, facturés à 82,86 FCFA / kWh."
            },
            {
                "role": "user",
                "content": "Ah d'accord, donc si je dépasse 297 kWh, la suite est moins chère ?"
            },
            {
                "role": "assistant",
                "content": "Exactement ! Pour le tarif général (10A et 15A), la CIE applique un tarif dégressif en tranche 2. Mais attention : plus vous consommez de kWh au total, plus les taxes d'État (RTI, ordures ménagères, électrification rurale) augmentent, car elles ajoutent environ 5,56 FCFA sur chaque kWh consommé !"
            },
            {
                "role": "user",
                "content": "D'accord je vois. Et le facteur de puissance cosinus phi, c'est quoi exactement ?"
            },
            {
                "role": "assistant",
                "content": "Le cosinus phi mesure l'efficacité de l'utilisation de l'électricité. Dans le système domestique AOCEDA, il est fixé à 1.0 (hypothèse résistive standard), ce qui permet de calculer précisément la puissance active consommée par vos appareils en Watts."
            },
            {
                "role": "user",
                "content": "Ok d'accord. Et si mon disjoncteur saute souvent quand le frigo et la clim marchent ensemble ?"
            },
            {
                "role": "assistant",
                "content": "Votre disjoncteur 15A supporte jusqu'à 3,3 kW (3 300 Watts) simultanément. La clim (1 500 W) et le frigo (200 W) ne dépassent pas 1 700 W ensemble. Si ça disjoncte, cela peut être dû au courant d'appel au démarrage du compresseur ou à un autre appareil puissant branché en même temps (comme un fer à repasser de 2 000 W)."
            }
        ]
    }
]

# 2. Conversations longues (8 messages) pour Kouassi Nissi (nissikouassi83@gmail.com)
nissi_convs = [
    {
        "titre": "Gestion de la recharge prépayée et du congélateur",
        "messages": [
            {
                "role": "user",
                "content": "Bjr, j'ai rechargé 15 000 FCFA sur mon compteur prépayé la semaine dernière à Marcory. Ça va me tenir combien de jours environ ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Kouassi ! D'après votre rythme habituel de consommation (environ 4,5 kWh par jour), votre recharge de 15 000 FCFA devrait vous durer environ 22 à 25 jours de fonctionnement normal."
            },
            {
                "role": "user",
                "content": "Ok et quel appareil consomme le plus chez moi entre le congélateur et les lampes du salon ?"
            },
            {
                "role": "assistant",
                "content": "C'est votre congélateur qui représente plus de 85% de votre consommation ! Il consomme environ 3,8 à 4,0 kWh par jour pour maintenir les aliments congelés, alors que l'ensemble de vos ampoules du salon ne consomme que 0,3 à 0,5 kWh par soirée."
            },
            {
                "role": "user",
                "content": "Ah oui quand même ! Y a des astuces pour que mon congélateur consomme moins de courant ?"
            },
            {
                "role": "assistant",
                "content": "Oui, voici 3 conseils pratiques très efficaces :\n1. N'ouvrez pas la porte du congélateur trop souvent et ne la laissez pas ouverte longtemps.\n2. Ne placez pas de plats encore chauds à l'intérieur.\n3. Dégivrez-le dès que la couche de glace dépasse 0,5 cm : 0,5 cm de givre augmente la consommation d'électricité de 30% !"
            },
            {
                "role": "user",
                "content": "Merci du conseil, je vais le dégivrer ce week-end ! Et les ampoules du salon, vaut mieux mettre des LED ?"
            },
            {
                "role": "assistant",
                "content": "Absolument ! Remplacer d'anciennes ampoules à incandescence de 60W par des ampoules LED de 7W divise votre consommation d'éclairage par 8, tout en offrant le même confort visuel !"
            }
        ]
    },
    {
        "titre": "Prévention des coupures et alerte de solde bas",
        "messages": [
            {
                "role": "user",
                "content": "Comment je peux éviter que mon courant prépayé se coupe brusquement sans prévenir ?"
            },
            {
                "role": "assistant",
                "content": "L'application AOCEDA possède un système d'alerte automatique de solde bas. Dès que votre crédit restant passe sous le seuil de 3 jours de consommation (environ 2 000 FCFA), une alerte apparaît sur votre dashboard et par notification !"
            },
            {
                "role": "user",
                "content": "C'est génial ça. Et si je pars en voyage 1 semaine, est-ce que mon solde va continuer de baisser ?"
            },
            {
                "role": "assistant",
                "content": "Si vous partez en voyage et laissez votre congélateur branché, il continuera de consommer ses 4 kWh par jour pour préserver vos aliments (soit environ 350 FCFA/jour). Si vous videz et débranchez le congélateur, la consommation tombera à 0 kWh !"
            },
            {
                "role": "user",
                "content": "D'accord. Et sur mon reçu de recharge de 15 000 FCFA, pourquoi le nombre de kWh n'est pas le même quand je recharge au début du mois et à la fin ?"
            },
            {
                "role": "assistant",
                "content": "C'est à cause de la déduction de la prime fixe d'abonnement mensuel (809 FCFA). La CIE la prélève lors de votre toute première recharge du mois. Les recharges suivantes du même mois sont dédiées à 100% à l'achat de kWh d'énergie !"
            },
            {
                "role": "user",
                "content": "Ah d'accord je ne savais pas du tout ! Et si le boîtier ESP32 se déconnecte du Wi-Fi ?"
            },
            {
                "role": "assistant",
                "content": "Aucune donnée n'est perdue ! L'ESP32 enregistre les mesures dans son tampon mémoire interne (LittleFS). Dès que le Wi-Fi revient, il transmet tout au serveur de manière totalement transparente."
            }
        ]
    }
]

# 3. Conversations longues (8 messages) pour Traoré Kader (anget373@gmail.com)
kader_convs = [
    {
        "titre": "Réduire la facture liée au chauffe-eau",
        "messages": [
            {
                "role": "user",
                "content": "Salut, j'ai l'impression que mon chauffe-eau me coûte trop cher à Yopougon. C'est vrai qu'il consomme beaucoup ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Traoré. Oui, tout à fait ! Le chauffe-eau est l'appareil le plus énergivore de votre logement. Il consomme environ 2 000 Watts (2 kW) lorsqu'il chauffe. D'après vos données, il représente à lui seul plus de 58% de votre consommation totale !"
            },
            {
                "role": "user",
                "content": "Purée 58% ! Que me conseilles-tu de faire concrètement pour diviser ça par deux ?"
            },
            {
                "role": "assistant",
                "content": "Voici les 2 actions les plus puissantes :\n1. L'allumer uniquement à la demande : Ne le laissez pas branché 24h/24. Allumez-le 1h avant vos douches puis éteignez-le.\n2. Baisser le thermostat : Réglez-le à 55°C au lieu de 70°C. L'eau reste chaude pour vos douches et vous économisez jusqu'à 25% d'énergie."
            },
            {
                "role": "user",
                "content": "Si je le branche seulement 1h par jour, combien j'économise par mois environ ?"
            },
            {
                "role": "assistant",
                "content": "En le branchant seulement 1h à 2h par jour au lieu de 24h/24, vous économisez environ 60 à 80 kWh par mois, soit une réduction directe de 6 000 à 8 000 FCFA sur votre facture mensuelle CIE !"
            },
            {
                "role": "user",
                "content": "Ah oui une belle économie ! Et la prise dans ma chambre, avec les téléphones et l'ordinateur, ça consomme combien ?"
            },
            {
                "role": "assistant",
                "content": "La prise de la chambre (chargeurs de téléphone, PC portable, petite veilleuse) consomme très peu : environ 0,2 à 0,4 kWh par jour (soit moins de 40 FCFA par jour). La vraie priorité d'économie reste votre chauffe-eau !"
            }
        ]
    },
    {
        "titre": "Compréhension de la facture CIE 10A et prévision",
        "messages": [
            {
                "role": "user",
                "content": "Tu peux m'expliquer comment la CIE calcule ma facture 10A en Côte d'Ivoire ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Traoré ! La facture CIE se décompose en 3 parties :\n1. La Prime Fixe : 809 FCFA TTC/mois (abonnement 10A).\n2. La Consommation : Tranche 1 (0 à 198 kWh) à 86,92 FCFA/kWh, puis Tranche 2 (> 198 kWh) à 75,34 FCFA/kWh.\n3. Les Taxes d'État : Redevances RTI, électrification rurale et ordures ménagères (environ 5,56 FCFA par kWh)."
            },
            {
                "role": "user",
                "content": "D'accord, et pour ce mois-ci, la prévision dans mon dashboard indique entre 18 000 et 21 000 FCFA. C'est fiable ?"
            },
            {
                "role": "assistant",
                "content": "Oui ! La prévision utilise un algorithme statistique basé sur la Médiane et l'Écart Absolu Médian (MAD) de vos journées complètes. Cela élimine les pics exceptionnels et donne une fourchette de confiance à 80% très proche de la réalité."
            },
            {
                "role": "user",
                "content": "C'est quoi la différence entre la médiane et une simple moyenne ?"
            },
            {
                "role": "assistant",
                "content": "Une moyenne peut être faussée si vous avez fait une grande fête un seul jour du mois. La médiane prend la valeur d'une journée 'typique' au milieu de vos habitudes, ce qui garantit une prévision robuste et honnête !"
            },
            {
                "role": "user",
                "content": "D'accord j'ai compris ! Et si mon capteur tombe en panne ou perd le courant ?"
            },
            {
                "role": "assistant",
                "content": "Si un capteur perd l'alimentation ou le Wi-Fi, l'application le repère et l'indique dans l'onglet 'Capteurs' ou 'Alertes'. Dès sa reconnexion, l'historique se met à jour automatiquement."
            }
        ]
    }
]

# 4. Conversations longues (8 messages) pour Kotchi Josué (triiiumph12@gmail.com)
josue_convs = [
    {
        "titre": "Avantages du Tarif Social 5A et Machine à laver",
        "messages": [
            {
                "role": "user",
                "content": "Bonjour, je suis au tarif social 5A à Adjamé Bracodi. Si je fais mes lessives la journée avec la machine à laver, ça risque de me faire perdre le tarif social ?"
            },
            {
                "role": "assistant",
                "content": "Bonjour M. Kotchi ! Au tarif social 5A, vous bénéficiez du tarif le moins cher de Côte d'Ivoire : 31,72 FCFA / kWh tant que votre consommation reste inférieure à 40 kWh par mois ! Votre machine à laver consomme environ 0,8 kWh par lavage. En faisant 2 lessives par semaine (environ 7 kWh/mois), vous restez largement dans la limite du tarif social !"
            },
            {
                "role": "user",
                "content": "C'est une excellente nouvelle ! Et si un mois je consomme 45 kWh, que se passe-t-il ?"
            },
            {
                "role": "assistant",
                "content": "Au-delà de 40 kWh/mois, la tranche 2 du tarif social s'applique à 65,11 FCFA/kWh. Si vous dépassez régulièrement 100 kWh/mois sur 6 mois consécutifs, la CIE vous fait basculer automatiquement au tarif général 5A/10A. Mais avec vos habitudes actuelles, vous êtes très loin de ce seuil !"
            },
            {
                "role": "user",
                "content": "Super ! Et ma télévision avec le décodeur TV, ça consomme beaucoup de courant ?"
            },
            {
                "role": "assistant",
                "content": "Non, la télé et le décodeur sont très économiques : ensemble, ils consomment environ 90 Watts. Pour 4 heures de télé par soir, cela représente à peine 0,36 kWh par jour (soit moins de 12 FCFA par jour au tarif social) !"
            },
            {
                "role": "user",
                "content": "Et laisser le décodeur et la TV en veille toute la nuit, ça gâche du crédit ?"
            },
            {
                "role": "assistant",
                "content": "La veille consomme environ 3 à 5 Watts en continu, soit environ 30 à 40 FCFA par mois. Ce n'est pas énorme, mais couper la multiprise la nuit est une bonne habitude pour économiser et protéger vos appareils des surtensions !"
            }
        ]
    },
    {
        "titre": "Gestion de la recharge 8 000 FCFA et conseils d'économie",
        "messages": [
            {
                "role": "user",
                "content": "J'ai mis une recharge de 8 000 FCFA sur mon compteur prépayé. Elle va me faire combien de temps ?"
            },
            {
                "role": "assistant",
                "content": "Grâce à votre tarif social 5A (31,72 FCFA/kWh), vos 8 000 FCFA vous donnent un volume d'électricité très important (environ 240 kWh) ! Avec votre consommation quotidienne d'environ 1,2 kWh/jour, cette recharge peut vous durer jusqu'à 45 à 50 jours !"
            },
            {
                "role": "user",
                "content": "Wouah 50 jours c'est énorme ! Pourquoi mon voisin paye beaucoup plus cher pour la même somme ?"
            },
            {
                "role": "assistant",
                "content": "Votre voisin a probablement un abonnement 10A ou 15A au tarif général (où le kWh coûte 86,92 FCFA ou 95,62 FCFA, soit 3 fois plus cher que votre tarif social de 31,72 FCFA) !"
            },
            {
                "role": "user",
                "content": "D'accord je comprends mieux ! Est-ce que l'application AOCEDA m'avertira si mon solde commence à être bas ?"
            },
            {
                "role": "assistant",
                "content": "Oui ! L'application suit votre solde prépayé en direct. Dès qu'il ne vous reste plus que 3 jours de consommation, une alerte s'affiche pour vous conseiller d'effectuer une petite recharge avant d'être coupé."
            },
            {
                "role": "user",
                "content": "Merci beaucoup pour toutes ces réponses claires et précises !"
            },
            {
                "role": "assistant",
                "content": "C'est un plaisir M. Kotchi ! N'hésitez pas si vous avez d'autres questions sur votre consommation ou vos factures CIE. Passez une excellente journée !"
            }
        ]
    }
]

CLIENT_MAP = [
    ("marasseediteur@gmail.com", yann_convs),
    ("nissikouassi83@gmail.com", nissi_convs),
    ("anget373@gmail.com", kader_convs),
    ("triiiumph12@gmail.com", josue_convs),
]

def seed_conversations():
    total_created = 0
    for email, convs in CLIENT_MAP:
        try:
            client = Client.objects.get(email=email)
        except Client.DoesNotExist:
            print(f"Client non trouvé : {email}")
            continue

        QuotaIA.objects.get_or_create(client=client, defaults={
            'nb_requetes_aujourd_hui': 8,
            'tokens_entree_total': 3400,
            'tokens_sortie_total': 5800
        })

        for conv_data in convs:
            obj, created = Conversation.objects.get_or_create(
                client=client,
                titre=conv_data["titre"],
                defaults={"messages": conv_data["messages"]}
            )
            obj.messages = conv_data["messages"]
            obj.save()
            total_created += 1
            print(f"Enregistré conversation 8 msgs '{obj.titre}' pour {client.nom}")

    print(f"\nTerminé avec succès ! Total conversations enregistrées : {total_created}")

if __name__ == '__main__':
    seed_conversations()
