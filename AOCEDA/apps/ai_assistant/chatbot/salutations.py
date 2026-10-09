"""Salutation de l'heure au DÉBUT d'une conversation (09/10/2026, demande du client) : la toute première réponse d'une
conversation commence par la salutation du moment de la journée, dans la langue de la réponse ; ensuite, plus de
salutation, sauf si la personne salue elle-même (on lui répond alors avec la formule de RÉPONSE de sa langue).

Français (et langues que le cerveau IA parle lui-même) : « Bonjour » de 4 h à 18 h, « Bonsoir » de 18 h à 4 h.

Dioula et baoulé (langues relais : la réponse est écrite en français puis traduite) : la salutation est mise
DIRECTEMENT dans la langue par le code, jamais traduite (vérifié le 09/10/2026 : Google et Djelia traduisent mal une
salutation dans une phrase, ex. « Bonjour, comment allez-vous ? » -> Djelia « Nba, i ni tile, i ni tile ? » ; et Google
ne connaît pas les salutations baoulé de la mi-journée et du soir : « Manti » -> « Manteau », « Anun o » -> « Oiseau o »).

DIOULA (cours de bambara/dioula Ankataa ; Google et Djelia d'accord dans les deux sens pour les quatre formules) :
  4 h - 12 h « I ni sɔgɔma », 12 h - 15 h « I ni tile », 15 h - 19 h « I ni wula », 19 h - 4 h « I ni su ».
  Celui qui RÉPOND à une salutation dit « Nba » (homme) ou « Nse » (femme) puis la répète : « Nse, i ni wula ».

BAOULÉ : trois moments, et deux formules par moment, l'une pour celui qui salue EN PREMIER, l'autre pour celui qui
RÉPOND (Y. J. D. N'Zi, « Aspects linguistiques et discursifs de la salutation en baoulé », ERI n°02, juin 2024 ;
A. A. K. N'Guessan, « Les salutations chez les Baoulés en Côte d'Ivoire », Djiboul n°005, juillet 2023 ; cours de baoulé
Coast Systems) :
                      salue en premier            répond
  4 h - 11 h          [āɲı̰́ ó]  « Aɲiho »          [ārɛ́ ó]   « Arɛ o »
  11 h - 17 h         [mà̰tí]   « Manti »          [aǎ̰tı̰́ ó]  « Aanti o »
  17 h - 4 h          [ānṵ́ ó]  « Anun o »         [āōsı̰̄ ó]  « Awossi'n o »
  « Aɲiho » et « Awossi'n o » sont les graphies de Google et de GATITOS (mots baoulé écrits par des locuteurs pour
  Google) ; « Aɲiho » se trouve aussi dans de vrais enregistrements (« Aɲiho, Kouassi, a su kɔ nin? »). Attention :
  Google traduit « Bonsoir » par « Awossi'n o », qui est en réalité la RÉPONSE du soir.

Quand la personne salue, la réponse va avec SA salutation (à « Anun o » : « Awossi'n o » ; à « I ni su » : « Nse, i ni
su »), si son moment est à moins de 2 h de l'heure ; sinon (« Aɲiho » à 20 h, simple « bonjour »), avec l'heure.
À faire confirmer par un locuteur, comme le reste du dioula et du baoulé.
"""
import re
from datetime import datetime

HEURE_MATIN, HEURE_MIDI, HEURE_SOIR, HEURE_NUIT = 4, 12, 18, 22      # français

FRANCAIS = {"matin": "Bonjour", "apres_midi": "Bonjour", "soir": "Bonsoir", "nuit": "Bonsoir"}
# équivalents donnés en exemple au cerveau IA pour les autres langues (il les adapte à la langue de sa réponse)
EXEMPLES = {"matin": "anglais « Good morning », espagnol « Buenos días », arabe « صباح الخير »",
            "apres_midi": "anglais « Good afternoon », espagnol « Buenas tardes », arabe « مساء الخير »",
            "soir": "anglais « Good evening », espagnol « Buenas noches », arabe « مساء الخير »",
            "nuit": "anglais « Good evening », espagnol « Buenas noches », arabe « مساء الخير »"}

# (heure de début, moment) dans l'ordre de la journée ; avant la 1re heure, c'est le dernier moment (la nuit)
DIOULA = [(4, "sɔgɔma"), (12, "tile"), (15, "wula"), (19, "su")]
BAOULE = [(4, "matin"), (11, "midi"), (17, "soir")]           # « vers 3 h » selon N'Zi : 4 h comme les autres langues
BAOULE_FORMULES = {"matin": ("Aɲiho", "Arɛ o"), "midi": ("Manti", "Aanti o"), "soir": ("Anun o", "Awossi'n o")}
REPONSE_DIOULA = {"femme": "Nse", "homme": "Nba"}


def maintenant():
    """L'heure du serveur (celle de la Côte d'Ivoire). Les tests la remplacent pour fixer l'heure."""
    return datetime.now()


def moment(quand=None):
    """Français : « matin », « apres_midi », « soir » ou « nuit »."""
    h = (quand or maintenant()).hour
    if HEURE_MATIN <= h < HEURE_MIDI:
        return "matin"
    if HEURE_MIDI <= h < HEURE_SOIR:
        return "apres_midi"
    if HEURE_SOIR <= h < HEURE_NUIT:
        return "soir"
    return "nuit"


def francais(quand=None):
    """« Bonjour » ou « Bonsoir »."""
    return FRANCAIS[moment(quand)]


def _tranche(table, quand):
    h = (quand or maintenant()).hour
    choisi = table[-1][1]
    for debut, nom in table:
        if h >= debut:
            choisi = nom
    return choisi


TOLERANCE_H = 2                    # écart toléré entre l'heure et le moment de la salutation reçue


def _ecart_h(table, nom, quand):
    """Heures entre `quand` et la tranche `nom` de la table (0 si dedans), sur une journée qui boucle à minuit."""
    debuts, noms = [d for d, _ in table], [n for _, n in table]
    if nom not in noms:
        return 24
    i = noms.index(nom)
    debut, fin = debuts[i], debuts[(i + 1) % len(debuts)]
    h = quand.hour + quand.minute / 60
    if (debut <= h < fin) if debut < fin else (h >= debut or h < fin):
        return 0
    return min((debut - h) % 24, (h - fin) % 24)


def moment_local(code, quand=None):
    """Dioula : « sɔgɔma », « tile », « wula » ou « su » ; baoulé : « matin », « midi » ou « soir » ; sinon None."""
    return _tranche(DIOULA, quand) if code == "dyu" else _tranche(BAOULE, quand) if code == "bci" else None


def locale(code, quand=None, reponse=False, genre="femme", moment_recu=None):
    """(salutation dans la langue relais, la même en français), avec le point final ; None si langue inconnue.
    reponse=True : la personne vient de saluer -> formule de RÉPONSE (baoulé « Awossi'n o », dioula « Nse, i ni su »),
    du MOMENT DE SA SALUTATION s'il est connu (`moment_recu`) : à « Anun o » on répond « Awossi'n o », à « I ni su »
    « Nse, i ni su », même si l'heure du serveur tombe juste de l'autre côté d'une limite."""
    quand = quand or maintenant()
    m = moment_local(code, quand)
    if m is None:
        return None
    # le moment de la personne seulement s'il est PROCHE de l'heure (« Anun o » à 4 h 27) : « Aɲiho » à 20 h est un
    # simple « bonjour » (Google traduit « Bonjour » par « Aɲiho ») -> réponse de l'heure, « Awossi'n o »
    if reponse and moment_recu and _ecart_h(DIOULA if code == "dyu" else BAOULE, moment_recu, quand) <= TOLERANCE_H:
        m = moment_recu
    if code == "dyu":
        local = f"{REPONSE_DIOULA.get(genre, 'Nse')}, i ni {m}" if reponse else f"I ni {m}"
        fr = "Bonsoir" if m in ("wula", "su") else "Bonjour"     # comme Google et Djelia traduisent « I ni wula »
    else:
        local = BAOULE_FORMULES[m][1 if reponse else 0]
        fr = "Bonsoir" if m == "soir" else "Bonjour"          # le soir baoulé commence à 17 h
    return f"{local}.", f"{fr}."


# formule reconnue (dioula_texte / baoule_texte.FORMULES) -> moment de la journée qu'elle salue
_MOMENT_DES_FORMULES = {"dyu": {"sɔgɔma": "sɔgɔma", "tile": "tile", "wula": "wula", "su": "su"},
                        "bci": {"aɲiho": "matin", "arɛ o": "matin", "manti": "midi", "aanti o": "midi", "mo wonti": "midi",
                                "anun o": "soir", "awossi o": "soir"}}


def salutation_recue(code, texte):
    """La personne salue-t-elle ? None : non ; sinon le moment de sa salutation (« su », « soir »...), ou « » si elle
    salue sans moment précis (« Bonjour » en français)."""
    if code == "dyu":
        from . import dioula_texte
        for f, s in dioula_texte.formules_reconnues(texte):
            if s.startswith(("bonjour", "bonsoir")):
                return _MOMENT_DES_FORMULES["dyu"].get(f.split()[-1], "")
    elif code == "bci":
        from . import baoule_texte
        for f, s in baoule_texte.formules_reconnues(texte):
            if s.startswith(("bonjour", "bonsoir", "bon après-midi")):
                return _MOMENT_DES_FORMULES["bci"].get(f, "")
    return "" if commence_par_salutation(texte) else None


def est_salutation(code, texte):
    """La personne salue-t-elle (dans sa langue, ou en français) ? Alors on lui RÉPOND (formule de réponse)."""
    return salutation_recue(code, texte) is not None


def francais_reponse(texte="", quand=None):
    """« Bonjour » ou « Bonsoir » selon l'heure ; si la personne a salué en français, le sien quand il est proche de l'heure
    (« Bonsoir » à 4 h 35 -> « Bonsoir », vu le 09/10 : le cerveau IA répondait « Bonjour ! »)."""
    quand = quand or maintenant()
    mot = francais(quand)
    recu = re.match(r"\s*(bonjour|bonsoir)\b", texte or "", re.I)
    if recu and recu.group(1).capitalize() != mot:
        tranches = [(HEURE_MATIN, "Bonjour"), (HEURE_SOIR, "Bonsoir")]
        if _ecart_h(tranches, recu.group(1).capitalize(), quand) <= TOLERANCE_H:
            mot = recu.group(1).capitalize()
    return mot


def consigne_debut(quand=None, texte=""):
    """Ajoutée à la consigne du cerveau IA pour la 1re réponse d'une conversation (langues qu'il parle lui-même)."""
    d = quand or maintenant()
    mot = francais_reponse(texte, d)
    m = moment(d) if mot == francais(d) else ("soir" if mot == "Bonsoir" else "apres_midi")
    return (f"\n\nDÉBUT DE CONVERSATION : c'est le tout premier message de cette conversation, et il est {d:%H} h {d:%M}. "
            f"Commence OBLIGATOIREMENT ta réponse par la salutation de ce moment de la journée : en français « {mot} » ; dans "
            f"une autre langue, son équivalent exact ({EXEMPLES[m]}). Mets-la tout au début (« {mot} ! » ou « {mot}, »), "
            "puis réponds tout de suite à la question, sans phrase d'introduction. Ne te présente pas, sauf si le message "
            "n'est qu'une salutation.")


CONSIGNE_SUITE = ("\n\nLA CONVERSATION EST DÉJÀ COMMENCÉE : ne commence PAS ta réponse par une salutation (« Bonjour », "
                  "« Bonsoir »...), sauf si la personne vient elle-même de te saluer.")


def consigne_suite(texte="", quand=None):
    """Conversation déjà commencée : pas de salutation ; si la personne salue, la bonne salutation à lui rendre."""
    if not commence_par_salutation(texte):
        return CONSIGNE_SUITE
    mot = francais_reponse(texte, quand)
    return (f"\n\nLA CONVERSATION EST DÉJÀ COMMENCÉE, mais la personne vient de te saluer : rends-lui sa salutation au début "
            f"de ta réponse (en français « {mot} », ou son équivalent dans la langue de ta réponse), sans te présenter.")


def note_relais(fr):
    """Pour le cerveau IA en dioula / baoulé : la salutation (`fr`, ex. « Bonsoir. ») est déjà mise par le code."""
    return (f"\n(La salutation « {fr.rstrip('.')} » est ajoutée automatiquement au début de ta réponse, dans la langue de la "
            "personne. Ne salue PAS toi-même : commence directement par la réponse.)")


# « Bonsoir ! », « Bonjour à vous. », « Bonsoir madame, »... : la formule entière (sinon il resterait « À vous. »)
_SALUT = re.compile(r"^\s*(?:bonjour|bonsoir|salut|bonne (?:journée|soirée|nuit|après-midi)|bon après-midi)"
                    r"(?:\s+(?:à\s+(?:vous|toi|tous)(?:\s+deux)?|madame|monsieur|mademoiselle))?\b\s*[,.!;:…]*\s*", re.I)


def commence_par_salutation(texte):
    return bool(_SALUT.match(texte or ""))


def retirer_salutation(texte):
    """« Bonsoir ! Votre crédit... » -> « Votre crédit... » (salutation déjà mise par le code) ; « Bonsoir. » -> « »."""
    reste = _SALUT.sub("", texte or "", count=1)
    if reste == (texte or ""):
        return texte
    return reste[:1].upper() + reste[1:]
