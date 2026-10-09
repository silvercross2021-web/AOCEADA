"""Une question en BAOULÉ, de bout en bout (langue relais : on passe par le français), sur le modèle du dioula.

  1. dossier : ce qui a été entendu (vocal : texte de l'écoute baoulé, mots douteux, certitude) ou tapé, TRADUCTION
     GOOGLE baoulé -> français, nombres relus, formules et mots du glossaire présents ;
  2. DeepSeek reçoit ce dossier, déduit l'INTENTION (+ sa certitude) et répond en français simple (mêmes règles de
     sûreté que le dioula : les ordres et les nombres sont toujours confirmés) ;
  3. PAS COMPRIS : jamais de « pas compris » (05/10) : réponse utile sur le sujet le plus probable, jamais répétée (voir
     service_dioula) ;
  4. chaque phrase de la réponse est traduite en baoulé (Google) DÈS qu'elle est écrite ; la voix (OmniVoice, sur ce PC,
     plusieurs minutes par phrase) est fabriquée ensuite, dans une file à part : le texte s'affiche tout de suite.

Différence avec le dioula (mesurée le 29/09/2026) : pour le dioula, le lexique AOCEDA comprenait mieux que les
traducteurs et la traduction à l'aller était inutile ; pour le baoulé, il n'existe pas de lexique aussi riche, donc la
traduction Google à l'ALLER est donnée à DeepSeek dès le 1er essai (TRADUIRE_ALLER, vérifié par le banc).
"""
import os

from . import baoule_relais, baoule_texte, consignes, service_dioula, voix
from .service_dioula import _pool

TRADUIRE_ALLER = True


def preparer_dossier(session, texte, origine, traduire_aller=TRADUIRE_ALLER, langue_question=None):
    if langue_question:                                  # question en français/anglais..., réponse voulue en baoulé
        return service_dioula.dossier_langue_directe(texte, origine, langue_question, "baoulé")
    vocal = service_dioula._vocal_de(session, texte) if origine == "vocal" else None
    repare = vocal["repare"] if vocal else texte
    brut = vocal["brut"] if vocal else texte
    nombres = baoule_texte.lire_nombres(repare)
    trad = baoule_relais.vers_francais(repare) if traduire_aller else {"google": None, "duree_s": 0, "erreurs": []}
    lignes = [f"[Message {'VOCAL' if vocal else 'ÉCRIT'} en baoulé]"]
    if vocal:
        lignes.append(f"Entendu par la reconnaissance vocale baoulé : « {brut} »")
        if vocal.get("douteux"):
            lignes.append("Mots entendus avec peu de certitude : " + ", ".join(vocal["douteux"]))
        lignes.append(f"Certitude globale de l'écoute : {vocal.get('certitude', 0):.2f} (sur 1)")
    else:
        lignes.append(f"Texte tapé par l'utilisateur : « {texte} »")
    if trad.get("google"):
        lignes.append(f"Traduction automatique Google (baoulé -> français) : « {trad['google']} »")
    if nombres:
        lignes.append("Nombres relus automatiquement : " + " ; ".join(f"« {n['texte']} » = {n['valeur']}" for n in nombres))
    proche = baoule_texte.phrase_proche(repare)
    if proche:
        lignes.append(f"Phrase de référence la plus proche (ressemblance {proche[1]:.0%}"
                      f"{', sens donné par un locuteur' if proche[0].get('verifiee') else ''}) : « {proche[0]['bci']} » = "
                      f"{proche[0]['sens']} (indice fort, pas une certitude)")
    formules = baoule_texte.formules_reconnues(repare)
    if formules:
        lignes.append("Formules baoulé reconnues : " + " ; ".join(f"« {f} » = {s}" for f, s in formules))
    lexique = baoule_texte.lexique_utile(brut, repare)
    if lexique:
        lignes.append("Glossaire (mots présents) : " + " ; ".join(f"{m} = {s}" for m, s in lexique.items()))
    return {"texte": "\n".join(lignes), "brut": brut, "repare": repare, "vocal": bool(vocal), "traductions": trad,
            "nombres": nombres, "lexique": lexique}


def _avec_traductions(texte_dossier, trad):
    return texte_dossier + ("\n(2e essai : au 1er essai tu n'avais pas compris. Même si tu ne comprends toujours pas, "
                            "réponds au sujet le plus probable (règle : jamais de « pas compris »).)")


def chaine_active():
    """La chaîne robuste (06/10/2026) est le chemin normal ; CHATBOT_BAOULE_CHAINE=0 revient à l'ancien chemin libre."""
    return os.environ.get("CHATBOT_BAOULE_CHAINE", "1") != "0"


def repondre(session, texte, origine="ecrit", genre="femme", liste=None, traduire_aller=TRADUIRE_ALLER, source_langue="baoulé",
             langue_question=None, action=None, lire=None, voix_auto=True):
    """Une question en baoulé (ou une réponse à des boutons). Chaîne robuste par défaut ; ancien chemin en secours.
    voix_auto : la page lira la réponse toute seule (sinon la voix GPU n'est fabriquée que sur demande, bouton Écouter)."""
    voix.reveiller_voix_baoule("question en baoulé")   # GPU de la voix : démarre pendant que les autres travaillent
    if chaine_active():
        from . import baoule_chaine
        yield from baoule_chaine.repondre(session, texte, origine, genre, liste, source_langue, langue_question, action, lire,
                                          voix_auto=voix_auto)
        return
    yield from repondre_libre(session, texte, origine, genre, liste, traduire_aller, source_langue, langue_question,
                              voix_auto=voix_auto)


def repondre_libre(session, texte, origine="ecrit", genre="femme", liste=None, traduire_aller=TRADUIRE_ALLER,
                   source_langue="baoulé", langue_question=None, voix_auto=True):
    """ANCIEN chemin (jusqu'au 05/10/2026) : DeepSeek déduit l'intention ET rédige librement la réponse. Gardé en
    SECOURS de la chaîne robuste (cerveau IA hors format deux fois de suite)."""
    profil = {"code": "bci", "nom": "baoulé",
              "dossier": lambda: preparer_dossier(session, texte, origine, traduire_aller, langue_question),
              # traduction déjà dans le dossier : pas de 2e traduction pour la relance ; sinon Google en relance
              "traductions_relance": None if traduire_aller else
              (lambda d: _pool.submit(lambda: {"google": baoule_relais.vers_francais(d["repare"])["google"]})),
              "consigne": consignes.systeme_baoule, "traduire": baoule_relais.lancer_vers_baoule,
              "avec_traductions": lambda t, trad: t + (f"\nTraduction automatique Google (baoulé -> français) : « {trad['google']} »"
                                                       if trad.get("google") else "") + _avec_traductions("", trad)}
    yield from service_dioula.repondre_relais(profil, session, genre, liste, source_langue, voix_auto=voix_auto)
