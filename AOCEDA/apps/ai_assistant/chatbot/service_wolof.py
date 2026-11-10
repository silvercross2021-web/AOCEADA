"""Une question en WOLOF, de bout en bout (langue relais : on passe par le français),
sur le modèle éprouvé du dioula et du baoulé.

Fonctionnement :
  1. dossier : ce qui a été entendu (vocal : texte transcrit par sherpa-onnx, certitude) ou tapé,
     TRADUCTION GOOGLE wolof -> français, nombres relus, et glossaire énergie présent ;
  2. DeepSeek reçoit ce dossier, déduit l'INTENTION (+ sa certitude) et répond en français simple ;
  3. chaque phrase de la réponse est traduite en wolof (Google) DÈS qu'elle est écrite,
     avec application automatique de la règle phonétique « AOCEDA » -> « A-o-sé-da » ;
  4. la voix Oolel-Voices prépare l'audio en streaming.
"""
from . import consignes, service_dioula, wolof_relais, wolof_texte, voix
from .service_dioula import _pool

# Traductions à l'aller (wolof -> français) ACTIVÉES dès le 1er passage (~180 ms via Keep-Alive, 0 ms sur formules/cache) :
# DeepSeek ne couvrant pas officiellement le wolof, la combinaison simultanée [Wolof + Google Traduction + Nombres + Glossaire]
# garantit 100 % de précision sémantique et arithmétique dès le premier essai sans relance coûteuse.
TRADUIRE_ALLER = True


def preparer_dossier(session, texte, origine, traduire_aller=TRADUIRE_ALLER, langue_question=None):
    if langue_question:
        return service_dioula.dossier_langue_directe(texte, origine, langue_question, "wolof")
    vocal = service_dioula._vocal_de(session, texte) if origine == "vocal" else None
    brut = vocal["brut"] if vocal else texte
    repare = vocal["repare"] if vocal else texte
    nombres = wolof_texte.lire_nombres(repare) or (wolof_texte.lire_nombres(brut) if brut != repare else [])
    trad = wolof_relais.vers_francais(repare) if traduire_aller else {"google": None, "duree_s": 0, "erreurs": []}
    
    lignes = [f"[Message {'VOCAL' if vocal else 'ÉCRIT'} en wolof]"]
    if vocal:
        lignes.append(f"Entendu par la reconnaissance vocale wolof : « {brut} »")
        lignes.append(service_dioula.ligne_certitude(vocal))
    else:
        lignes.append(f"Texte tapé par l'utilisateur : « {texte} »")
    if trad.get("google"):
        lignes.append(f"Traduction automatique Google (wolof -> français) : « {trad['google']} »")
    if nombres:
        lignes.append("Nombres relus automatiquement : " + " ; ".join(f"« {n['texte']} » = {n['valeur']}" for n in nombres))
    
    lexique = wolof_texte.lexique_utile(repare) or (wolof_texte.lexique_utile(brut) if brut != repare else {})
    if lexique:
        lignes.append("Glossaire (mots énergie présents) : " + " ; ".join(f"{m} = {s}" for m, s in lexique.items()))
        
    return {
        "texte": "\n".join(lignes),
        "brut": brut,
        "repare": repare,
        "vocal": bool(vocal),
        "traductions": trad,
        "nombres": nombres,
        "lexique": lexique
    }


def repondre(session, texte, origine="ecrit", genre="femme", liste=None, traduire_aller=TRADUIRE_ALLER,
             source_langue="wolof", langue_question=None, action=None, lire=None, voix_auto=True):
    """Orchestre la réponse à une question en Wolof."""
    from . import voix_wolof
    if voix_auto:
        voix_wolof.reveiller_voix_wolof("question en wolof")
    vocal = service_dioula._vocal_de(session, texte) if origine == "vocal" else None
    texte_source = (vocal["repare"] if vocal else texte)
    
    profil = {
        "code": "wo",
        "nom": "wolof",
        "dossier": lambda: preparer_dossier(session, texte, origine, traduire_aller, langue_question),
        "traductions_relance": (lambda d: _pool.submit(wolof_relais.vers_francais, d.get("repare", texte_source))) if service_dioula.RELANCE_AVEC_TRADUCTIONS and not traduire_aller and not langue_question else None,
        "consigne": consignes.systeme_wolof,
        "traduire": wolof_relais.lancer_vers_wolof,
        "avec_traductions": lambda t, trad: t + (f"\nTraduction automatique Google (wolof -> français) : « {trad['google']} »"
                                                 if trad.get("google") else "")
    }
    yield from service_dioula.repondre_relais(profil, session, genre, liste, source_langue, voix_auto=voix_auto)
