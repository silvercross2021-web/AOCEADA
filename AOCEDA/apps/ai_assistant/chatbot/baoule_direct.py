"""Question posée en FRANÇAIS (ou en anglais, espagnol...), réponse voulue en BAOULÉ (19/10/2026, retour du client).

Avant : une question française passait par la liste fermée de la chaîne baoulé (faite pour COMPRENDRE le baoulé, très mal
reconnu et traduit). Vu en vrai le 19/10/2026 : « mets-moi les statistiques de ce qu'on a consommé » -> classée
« économiser » (certitude basse) -> deux conseils sur le réfrigérateur, sans un chiffre ni une carte. Or une question
française est déjà comprise : seule la RÉPONSE doit être en baoulé. Désormais :
  1. le cerveau IA lit les VRAIES données avec les outils d'AOCEDA, exactement comme en français (mêmes cartes sous la
     réponse, même carte Oui / Non pour éteindre ou rallumer), et rédige en français simple et structuré ;
  2. chaque ligne est traduite en baoulé DÈS qu'elle est écrite, puis contre-vérifiée (baoule_repondre : nombres, noms
     d'appareils) ; une ligne douteuse garde son français dessous (« traduction automatique ») ;
  3. la structure reste : la réponse directe, les puces, le conseil.
Une phrase BAOULÉ (tapée ou dite) suit toujours la chaîne robuste (baoule_chaine) : là, comprendre est le vrai problème.
"""
import re
import time

from . import baoule_repondre, consignes, conversation, fournisseurs, salutations, voix
from .baoule_demandes import Phrase
from .nombres_fr import nombres_dans

CONSIGNE = """

RÉPONSE TRADUITE EN BAOULÉ (prioritaire sur les règles de longueur et de mise en forme ci-dessus)
Écris ta réponse en FRANÇAIS : elle sera traduite automatiquement en baoulé, ligne par ligne, puis lue à voix haute.
- Pas de salutation (elle est déjà mise en baoulé), pas de présentation, pas de phrase d'attente.
- 1re ligne : UNE phrase courte, la réponse directe avec le chiffre clé et sa période.
- Puis, quand il y a plusieurs chiffres utiles, 2 à 4 puces « - » : une seule idée par puce, 12 mots au plus.
- Puis, si c'est utile, UNE ligne qui commence par « Conseil : », une phrase courte liée à SES appareils.
- Mots simples, phrases complètes avec un verbe (« La prise a consommé 1,35 kilowattheure. », pas « Prise : 1,35 »).
- Pas de gras, pas de parenthèses, pas de guillemets, pas de deux-points en milieu de phrase, pas de sigle sauf CIE,
  pas d'abréviation (« kilowattheures », jamais « kWh »).
- Nombres EN LETTRES (« un virgule six kilowattheure », « cent soixante-dix-sept francs »)."""

# noms d'appareils qui doivent survivre à la traduction (contre-vérification, comme baoule_demandes)
APPAREILS = ("prise", "lampe", "climatiseur", "ventilateur", "réfrigérateur", "frigo", "congélateur", "télévision",
             "fer à repasser", "pompe", "ampoule", "chargeur")
_PUCE = re.compile(r"^\s*[-*•]\s+")
_CONSEIL = re.compile(r"^\s*conseil\s*:\s*", re.I)


def _propre(t):
    """Texte à traduire : sans markdown ni guillemets."""
    t = re.sub(r"[*_`#>|]+", "", t)
    t = re.sub(r"\s+", " ", t.replace("«", "").replace("»", "").replace('"', "")).strip()
    return t[:1].upper() + t[1:]                     # « Conseil : réglez… » -> « Réglez… »


def unites(texte, fini=False):
    """Découpe le français écrit jusqu'ici en unités à traduire : [(genre, phrase)] avec genre = « texte » (1re ligne),
    « puce » ou « conseil » ; renvoie (unités finies, reste pas encore fini)."""
    lignes = texte.split("\n")
    reste = "" if fini else lignes.pop()
    out = []
    for l in lignes:
        if not l.strip():
            continue
        genre = "puce" if _PUCE.match(l) else "conseil" if _CONSEIL.match(l) else "texte"
        corps = _propre(_CONSEIL.sub("", _PUCE.sub("", l)))
        if genre == "puce":                              # une puce = une unité (même avec deux phrases courtes)
            out.append((genre, corps))
            continue
        for i, p in enumerate(x for x in re.split(r"(?<=[.!?])\s+", corps) if x.strip()):
            out.append((genre if i == 0 else "texte", p))
    if not fini and reste.strip() and not _PUCE.match(reste):
        # 1re ligne longue : ses phrases finies partent tout de suite (la 1re phrase se lit pendant que la suite s'écrit)
        morceaux = re.split(r"(?<=[.!?])\s+", reste)
        if len(morceaux) > 1:
            genre = "conseil" if _CONSEIL.match(reste) else "texte"
            for i, p in enumerate(morceaux[:-1]):
                p = _propre(_CONSEIL.sub("", p) if i == 0 else p)
                if p:
                    out.append((genre if i == 0 else "texte", p))
            reste = ("Conseil : " if genre == "conseil" else "") + morceaux[-1]
    return out, reste


def phrase(fr):
    """La phrase et ce qui doit survivre à la traduction (nombres, appareils nommés)."""
    bas = fr.lower()
    return Phrase(fr, tuple(sorted(nombres_dans(fr))), tuple(a for a in APPAREILS if a in bas))


def _prefixe(genre, apres):
    """Mise en page de l'unité dans la bulle (markdown lu par la page) : puces à la ligne, conseil en paragraphe."""
    if genre == "puce":
        return "\n- "
    if genre == "conseil":
        return "\n\n"
    return " " if apres else ""


def repondre(session, texte, genre="femme", liste=None, source_langue="menu", voix_auto=True):
    """Événements pour la page (comme la chaîne baoulé) : les cartes des outils, puis la réponse en baoulé, unité par
    unité (morceau baoulé + francais), puis fin et bilan."""
    t0 = time.time()
    deja = conversation.historique(session)
    dernier = conversation.dernier_message(session)
    historique, question_id = conversation.poser_question(session, texte)
    conversation.noter_langue(session, "bci")
    systeme = consignes.systeme("fr") + CONSIGNE
    recu = salutations.salutation_recue("bci", texte)     # « Bonjour » (français) ou « Anun o » : on lui répond
    salut = (salutations.locale("bci", reponse=recu is not None, genre=genre, moment_recu=recu)
             if (not deja or recu is not None or salutations.resaluer(dernier, "bci")) else None)

    resultats, file, ecrit = [], [], ""
    premiere, fin, annonce = None, None, False

    def saluer():
        if salut:
            bci, fr = salut
            resultats.append({"fr": fr, "bci": bci, "controle": "formule", "retour": None, "manques": [],
                              "service": "formule", "genre": "texte"})
            yield {"type": "morceau", "texte": bci, "traduit": True, "controle": "formule"}
            yield {"type": "francais", "texte": fr}

    def lancer(genre_u, fr):
        nonlocal annonce
        if salut and not resultats[1:] and not file:      # le cerveau IA a salué malgré la consigne : déjà fait
            fr = salutations.retirer_salutation(fr).strip()
        if not fr:
            return
        file.append((genre_u, baoule_repondre._pool.submit(baoule_repondre.traduire_une, phrase(fr))))
        if not annonce:
            annonce = True
            yield {"type": "etape", "texte": "Je traduis la réponse en baoulé", "redige": True}

    def sortir(bloquer):
        nonlocal premiere
        while file and (bloquer or file[0][1].done()):
            genre_u, tache = file.pop(0)
            try:
                r = tache.result(timeout=30)
            except Exception as e:                        # traduction en panne : la phrase reste en français
                r = {"fr": "", "bci": "", "controle": "non_traduite", "retour": None, "manques": [str(e)[:80]],
                     "service": "aucun"}
            if not r["fr"]:
                continue
            r["genre"] = genre_u
            resultats.append(r)
            if premiere is None:
                premiere = round(time.time() - t0, 2)
            pre = _prefixe(genre_u, len(resultats) > 1)
            yield {"type": "morceau", "texte": pre + r["bci"], "traduit": r["controle"] != "non_traduite",
                   "controle": r["controle"]}
            yield {"type": "francais", "texte": pre + ("Conseil : " if genre_u == "conseil" else "") + r["fr"]}

    flux = fournisseurs.repondre_flux(systeme, historique, liste=liste)
    try:
        yield from saluer()
        for ev in flux:
            if ev["type"] == "morceau":
                ecrit += ev["texte"]
                finies, ecrit = unites(ecrit)
                for g, p in finies:
                    yield from lancer(g, p)
                yield from sortir(False)
            elif ev["type"] == "recommencer":           # un autre fournisseur reprend tout : la page a tout effacé
                ecrit, annonce = "", False
                file.clear(); resultats.clear()
                yield ev
                yield from saluer()
            elif ev["type"] == "fin":
                finies, _ = unites(ecrit, fini=True)
                for g, p in finies:
                    yield from lancer(g, p)
                yield from sortir(True)
                fin = ev
            elif ev["type"] == "erreur":
                conversation.annuler_question(session, question_id)
                yield ev
                return
            else:                                         # outils (cartes de données, carte Oui / Non), fournisseur
                yield ev
    finally:
        flux.close()
        if fin is None:
            conversation.annuler_question(session, question_id)
    if fin is None:
        return

    reponse_bci = "".join(_morceau(r, i) for i, r in enumerate(resultats)).strip()
    reponse_fr = "".join(_morceau(r, i, "fr") for i, r in enumerate(resultats)).strip()
    reponse = [r for r in resultats if r["controle"] != "formule"]
    non_traduit = sum(1 for r in reponse if r["controle"] == "non_traduite")
    langue_voix = "fr" if reponse and non_traduit == len(reponse) else "bci"
    if langue_voix == "fr" and salut:                    # tout est resté en français : « Bonsoir. » en français aussi
        resultats[0] = {**resultats[0], "bci": resultats[0]["fr"]}
        reponse_bci = "".join(_morceau(r, i) for i, r in enumerate(resultats)).strip()
    conversation.ajouter_reponse(session, reponse_fr)
    morceaux = voix.decouper(reponse_bci)
    conversation.autoriser_voix(session, morceaux + [voix.texte_pour_voix(reponse_bci)])
    if langue_voix == "bci" and reponse_bci:
        if voix_auto:                                     # GPU : la voix part tout de suite, prête quand la page la lit
            voix.annoncer_baoule(reponse_bci, genre)
    else:
        voix.preparer(morceaux, langue_voix, genre)
    fin_ev = {"type": "fin", "texte": reponse_bci, "francais": reponse_fr, "premiere_phrase_s": premiere,
              "total_s": round(time.time() - t0, 2), "traducteurs": [r["service"] for r in resultats], "relance": False,
              "non_traduit": non_traduit, "douteuses": sum(1 for r in reponse if r["controle"] == "douteuse"),
              "non_verifiees": sum(1 for r in reponse if r["controle"] == "non_verifiee"), "langue_voix": langue_voix,
              "controles": [r["controle"] for r in resultats], "fournisseur": fin.get("fournisseur"),
              "modele": fin.get("modele"), "essais": fin.get("essais"), "mode": "langue_directe"}
    yield fin_ev
    yield {"type": "bilan", "langue_reponse": "bci", "source_langue": source_langue, "refaites": 0, "fin": fin_ev,
           "duree_s": round(time.time() - t0, 2),
           "chaine": {"mode": "langue_directe", "francais_ecrit": fin.get("texte", "")[:600],
                      "retours": [{"fr": r["fr"], "retour": r["retour"], "manques": r["manques"], "controle": r["controle"]}
                                  for r in resultats]}}


def _morceau(r, i, cle="bci"):
    """Texte complet (fin de réponse, conversation) avec la même mise en page que les morceaux envoyés à la page."""
    pre = _prefixe(r.get("genre", "texte"), i > 0)
    lib = "Conseil : " if cle == "fr" and r.get("genre") == "conseil" else ""
    return pre + lib + r[cle]
