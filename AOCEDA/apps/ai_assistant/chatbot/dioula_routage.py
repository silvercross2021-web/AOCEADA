"""Un vocal arrive en mode « Automatique » : dioula (Omnilingual) ou autre langue (Whisper) ?

Mesuré le 29/09/2026 sur 354 extraits (tests\\bancs\\dioula_logique) :
  - face au dioula, Whisper est perdu : il répond japonais, indonésien, espagnol, français... avec une certitude
    médiane de 0,34 ; face à du français ou de l'anglais clair, il est sûr (0,96 à 0,99) ;
  - il n'est JAMAIS sûr à tort pour le français ou l'anglais (≥ 0,90) sur nos 292 extraits dioula/bambara ; ses rares
    erreurs sûres sont en portugais, arabe, coréen, et disparaissent au-dessus de 0,99 ;
  - les mots courts (« oui », « merci », « d'accord ») et l'anglais à l'accent africain le font hésiter autant que le
    dioula : l'empreinte de Whisper seule confondrait ;
  - Omnilingual écrit correctement le français, l'anglais, l'espagnol... : lire SON TEXTE tranche ;
  - sur une réponse très courte en dioula (« Ɔn ɔn, a to yen »), Omnilingual écrit parfois en coréen ou en arabe :
    un alphabet que Whisper n'a pas entendu est une erreur d'écoute, pas une langue.

Décision (du plus rapide au plus sûr) :
  1. Whisper « tiny » sûr d'une langue du chatbot (français/anglais ≥ 0,90 ; autres ≥ 0,99) -> chemin Whisper habituel,
     0 seconde ajoutée. Dans une conversation en dioula ou en baoulé, il faut ≥ 0,92 pour changer de langue ;
  1 bis. BAOULÉ (étape 3) : si l'écoute baoulé est installée, ses mots et ceux de l'écoute dioula décident baoulé / dioula
     (baoule_texte.baoule_ou_dioula) avant le point 2.b ; mesuré sur 169 vrais vocaux ;
  2. sinon Omnilingual écoute et on lit son texte :
       a. expression courte connue (« merci », « d'accord », « yes ») -> cette langue ; mais dans une conversation en
          dioula, un « merci » ou un « d'accord » français reste du dioula (c'est ainsi qu'on parle le dioula ici) ;
       b. le texte porte le dioula (mots dioula, lettres ɛ ɔ ɲ ŋ) -> dioula ;
       c. le texte est clairement d'une autre langue du chatbot -> cette langue, avec des garde-fous : pour une autre
          langue que le français ou l'anglais, Whisper doit l'avoir un peu entendue ; un autre alphabet doit avoir été
          entendu par Whisper ; dans une conversation en dioula, il faut au moins 3 mots ;
       d. Whisper et le texte d'accord sur une langue du chatbot -> cette langue ;
  3. encore douteux -> la langue de la conversation (dioula ; ou autre langue si le message est très court) ;
     Whisper très sûr d'une langue non gérée -> « non prise en charge » ; trace de dioula ou rien de reconnu -> dioula
     (c'est la langue locale attendue quand rien d'autre n'est reconnu).
"""
import re

from . import baoule_texte, detection, dioula_texte, langues, wolof_texte

SEUIL_SUR_FR_EN = 0.90
SEUIL_SUR_AUTRES = 0.99
# Conversation en langue locale : Whisper doit être sûr à 0,92 pour changer de langue (0,97 avant le 30/09/2026 :
# mesuré sur 120 vrais vocaux baoulé et dioula, Whisper n'est JAMAIS sûr à tort du français ou de l'anglais au-dessus de
# 0,90 ; avec 0,97, 7 vocaux français sur 16 restaient bloqués en dioula)
SEUIL_CHANGER_DEPUIS_DIOULA = 0.92
SEUIL_AUTRE_TEXTE = 0.90
SEUIL_TEXTE_SEUL = 0.95          # texte seul (Whisper pas d'accord) : il doit être TRÈS net
SEUIL_ACCORD_WHISPER = 0.20      # autre langue que fr/en lue dans le texte : Whisper doit l'avoir un peu entendue
SEUIL_ACCORD_AUTRE_NET = 0.50    # ... et NETTEMENT entendue pour écarter le baoulé avant même de l'essayer
SEUIL_ALPHABET = 0.50            # texte dans un autre alphabet : Whisper doit l'avoir nettement entendu
SEUIL_NON_PRISE = 0.80           # Whisper très sûr d'une langue que le chatbot ne gère pas (mesuré : 0,62 et 0,73 = erreurs)
ECRITURES_NON_LATINES = {"ar", "he", "th", "bn", "hi", "ja", "ko", "zh", "el", "ru", "uk"}

EXPRESSIONS = {
    "fr": ["oui", "wi", "ouais", "non", "merci", "merci beaucoup", "non merci", "d'accord", "dac", "ok", "okay", "bonjour",
           "bonsoir", "salut", "au revoir", "pardon", "s'il vous plait", "s'il te plait", "c'est bon", "voila", "bien sur"],
    "en": ["yes", "jes", "yez", "no", "thanks", "thank you", "okay", "ok", "hello", "hi", "please", "sorry",
           "good morning", "bye", "no thanks", "yeah"],
    "es": ["si", "gracias", "hola", "vale", "de acuerdo", "buenos dias", "adios"],
    "pt": ["sim", "obrigado", "obrigada", "ola", "tchau", "bom dia"],
    "de": ["ja", "nein", "danke", "hallo", "tschuss"],
    "it": ["grazie", "ciao", "prego"],
    "sw": ["asante", "asante sana", "jambo", "habari"],
}
_EXPR = {dioula_texte.cle(e.replace(" ", "")): lg for lg, l in EXPRESSIONS.items() for e in l}
COURTOISIE_FR_EN = {"fr", "en"}          # glissés dans le dioula sans changer de langue


def _mots(texte):
    return re.findall(r"[\w'’]+", (texte or "").lower())


def _expression(texte):
    mots = _mots(texte)
    if not mots or len(mots) > 3:
        return None
    return _EXPR.get(dioula_texte.cle("".join(mots)))


CHEMIN_LOCAL = {"dyu": "omni", "bci": "baoule", "wo": "wolof"}


def decider(probs_tiny, lire_omni, langue_conversation=None, lire_baoule=None, lire_wolof=None):
    """probs_tiny : {code: probabilité} de Whisper tiny.
    lire_omni : fonction -> (texte_latin, texte_libre) d'Omnilingual (dioula), appelée SEULEMENT si nécessaire.
    lire_baoule : fonction -> texte de l'écoute baoulé (None : pas d'écoute baoulé sur ce serveur).
    lire_wolof : fonction -> texte de l'écoute wolof (None : pas d'écoute wolof sur ce serveur).
    Renvoie {"langue", "chemin", "raison", "texte_omni"?, "texte_baoule"?, "texte_wolof"?} ;
    chemin = whisper | whisper-force | omni (dioula) | baoule | wolof | silence | non-prise."""
    top = max(probs_tiny, key=probs_tiny.get) if probs_tiny else None
    p = probs_tiny.get(top, 0.0) if top else 0.0
    seuil = SEUIL_SUR_FR_EN if top in ("fr", "en") else SEUIL_SUR_AUTRES
    locale = langue_conversation if langue_conversation in CHEMIN_LOCAL else None   # conversation en dioula, baoulé ou wolof
    en_dioula = locale is not None
    if en_dioula:
        seuil = max(seuil, SEUIL_CHANGER_DEPUIS_DIOULA)
    if top in langues.LANGUES and p >= seuil:
        return {"langue": top, "chemin": "whisper", "raison": f"Whisper sûr : {top} à {p:.2f}"}

    lu = {}

    def baoule():                                    # l'oreille baoulé n'écoute que si c'est utile (~3 s)
        if "b" not in lu:
            lu["b"] = (lire_baoule() or "").strip() if lire_baoule else ""
        return lu["b"]

    def wolof():                                     # l'oreille wolof n'écoute que si c'est utile (~3 s)
        if "w" not in lu:
            lu["w"] = (lire_wolof() or "").strip() if lire_wolof else ""
        return lu["w"]

    # conversation déjà en baoulé : si l'oreille baoulé entend nettement du baoulé, on n'attend pas l'oreille dioula
    if locale == "bci" and lire_baoule:
        sur, part = baoule_texte.baoule_net(baoule())
        if sur:
            return {"langue": "bci", "chemin": "baoule", "raison": f"conversation en baoulé, lecture baoulé nette ({part:.2f})",
                    "texte_omni": "", "texte_baoule": baoule()}

    # conversation déjà en wolof : si l'oreille wolof entend nettement du wolof, on n'attend pas l'oreille dioula
    if locale == "wo" and lire_wolof:
        sur_wo, part_wo, _ = wolof_texte.wolof_net(wolof())
        if sur_wo:
            return {"langue": "wo", "chemin": "wolof", "raison": f"conversation en wolof, lecture wolof nette ({part_wo:.2f})",
                    "texte_omni": "", "texte_wolof": wolof()}

    latin, libre = lire_omni()
    latin, libre = (latin or "").strip(), (libre or "").strip()
    if not latin and not libre and not (lire_baoule and baoule()) and not (lire_wolof and wolof()):
        return {"langue": None, "chemin": "silence", "raison": "aucune parole", "texte_omni": ""}
    base = {"texte_omni": latin}

    expr = _expression(latin)                                        # a. formule courte connue
    if expr:
        if en_dioula and expr in COURTOISIE_FR_EN:
            return {"langue": locale, "chemin": CHEMIN_LOCAL[locale],
                    "raison": f"« {latin} » glissé dans une conversation en langue locale", **base}
        if expr in langues.LANGUES:
            return {"langue": expr, "chemin": "whisper-force", "raison": f"expression courte {expr} : « {latin} »", **base}

    cle_latin = dioula_texte.cle(latin.replace(" ", ""))
    if cle_latin in {"waw", "waaw", "dedet", "deedeet", "jerejef", "jarama", "jaaraama", "baxna", "jammrekk"}:
        base["texte_wolof"] = wolof() if lire_wolof else latin
        return {"langue": "wo", "chemin": "wolof", "raison": f"expression courte wolof : « {latin} »", **base}

    # a''. Wolof ? Le modèle Omnilingual transcrit ce qu'il entend phonétiquement.
    # Si le texte porte la signature nette du Wolof (mots forts ou expressions wolof) :
    net_wo, score_wo, forts_wo = wolof_texte.wolof_net(latin)
    if net_wo:
        base["texte_wolof"] = wolof() if lire_wolof else latin
        return {"langue": "wo", "chemin": "wolof",
                "raison": f"texte wolof net ({score_wo:.2f}, marqueurs : {', '.join(forts_wo)})", **base}

    # a'. baoulé ou dioula ? Des mots propres au dioula dans la lecture dioula suffisent : pas besoin de l'oreille baoulé ;
    code_lu, conf_lu = detection.detecter(libre or latin)
    accord_lu = probs_tiny.get(code_lu, 0.0) if code_lu else 0.0
    score_dy = dioula_texte.score_dioula(latin)[0]
    lu_direct = (code_lu in langues.LANGUES and conf_lu >= SEUIL_AUTRE_TEXTE and len(_mots(latin)) >= 3
                 and not (code_lu in ECRITURES_NON_LATINES and accord_lu < SEUIL_ALPHABET)
                 and (score_dy == 0 if code_lu in ("fr", "en") else accord_lu >= SEUIL_ACCORD_AUTRE_NET and score_dy < 0.2))
    if lire_baoule and not lu_direct and not baoule_texte.dioula_net(latin):
        choix, raison = baoule_texte.baoule_ou_dioula(latin, baoule(), locale)
        base["texte_baoule"] = baoule()
        if choix == "bci":
            return {"langue": "bci", "chemin": "baoule", "raison": raison, **base}

    if lire_wolof and not lu_direct and not baoule_texte.dioula_net(latin):
        txt_wo = wolof()
        base["texte_wolof"] = txt_wo
        if txt_wo and wolof_texte.wolof_net(txt_wo)[0]:
            return {"langue": "wo", "chemin": "wolof", "raison": f"oreille wolof nette : « {txt_wo} »", **base}

    dioula, score = dioula_texte.est_dioula(latin)                   # b. le texte porte le dioula
    if dioula:
        return {"langue": "dyu", "chemin": "omni", "raison": f"texte dioula (score {score})", **base}

    code, conf = detection.detecter(libre or latin)                  # c. autre langue lue dans le texte
    accord = probs_tiny.get(code, 0.0) if code else 0.0
    alphabet_suspect = code in ECRITURES_NON_LATINES and accord < SEUIL_ALPHABET
    if (code in langues.LANGUES and conf >= SEUIL_AUTRE_TEXTE and score == 0 and not alphabet_suspect
            and (code in ("fr", "en") or accord >= SEUIL_ACCORD_WHISPER)
            and (not en_dioula or len(_mots(latin)) >= 3)):
        return {"langue": code, "chemin": "whisper-force", "raison": f"texte {code} ({conf:.2f})", **base}
    if top in langues.LANGUES and p >= 0.5 and code == top and not alphabet_suspect and not en_dioula:   # d. accord
        return {"langue": top, "chemin": "whisper-force", "raison": f"Whisper et texte d'accord : {top}", **base}
    if (code in langues.LANGUES and code not in ("fr", "en") and conf >= SEUIL_TEXTE_SEUL and score == 0
            and len(_mots(latin)) >= 3 and not alphabet_suspect and baoule_texte.signes(latin)[0] == 0
            and not (lire_baoule and baoule_texte.signes(baoule())[0])):
        return {"langue": code, "chemin": "whisper-force", "raison": f"texte {code} net ({conf:.2f}), aucun mot local", **base}

    if en_dioula:                                                    # 3. douteux
        if locale == "wo" and (score_wo > 0 or (lire_wolof and wolof_texte.wolof_net(wolof())[0])):
            base["texte_wolof"] = wolof() if lire_wolof else ""
            return {"langue": "wo", "chemin": "wolof", "raison": f"conversation en wolof, traces de wolof ({score_wo:.2f})", **base}
        if locale == "bci" and score > 0 and lire_baoule and not baoule_texte.baoule_net(baoule())[0]:
            return {"langue": "dyu", "chemin": "omni", "raison": f"traces de dioula ({score}), lecture baoulé pas nette",
                    **base}
        return {"langue": locale, "chemin": CHEMIN_LOCAL[locale], "raison": "douteux, conversation en langue locale", **base}
    if langue_conversation in langues.LANGUES and score == 0 and score_wo == 0 and len(_mots(latin)) <= 2:
        return {"langue": langue_conversation, "chemin": "whisper-force",
                "raison": f"message très court, conversation en {langue_conversation}", **base}
    if top and top not in langues.LANGUES and p >= SEUIL_NON_PRISE:     # (le texte n'est déjà pas du dioula ici)
        return {"langue": None, "chemin": "non-prise", "langue_entendue": top,
                "raison": f"Whisper sûr d'une langue non prise en charge ({top} à {p:.2f}), texte pas dioula", **base}
    if score_wo > 0 and score_wo > score:
        base["texte_wolof"] = wolof() if lire_wolof else ""
        return {"langue": "wo", "chemin": "wolof", "raison": f"douteux, traces de wolof ({score_wo:.2f})", **base}
    if score > 0:
        return {"langue": "dyu", "chemin": "omni", "raison": f"douteux, traces de dioula ({score})", **base}
    return {"langue": "dyu", "chemin": "omni", "raison": "aucune autre langue reconnue : dioula par défaut", **base}
