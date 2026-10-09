"""Une question en DIOULA, de bout en bout (langue relais : on passe par le français).

  1. dossier : ce qui a été entendu (brut + réparé, mots douteux, nombres relus) ou tapé, formules dioula reconnues,
     glossaire et lexique AOCEDA des mots présents ;
  2. DeepSeek reçoit ce dossier, déduit l'INTENTION (+ sa certitude) et répond en français simple ;
     il fait confirmer les nombres et les ordres, et dit quand il n'a pas compris ;
  3. PAS COMPRIS (certitude basse) : les traductions Google/Djelia, lancées en arrière-plan dès le début (elles ne
     retardent rien), sont ajoutées au dossier et DeepSeek réessaie UNE fois (utile hors du vocabulaire de
     l'électricité : mesuré sur un long message d'actualité) ; toujours pas compris -> c'est la réponse de DeepSeek
     qui part : elle cite ce qui a été entendu et propose des sujets. Plus de phrase fixe « pouvez-vous répéter ? » :
     retour client du 30/09/2026, c'était toujours la même phrase, même quand une intention avait été devinée ;
  4. chaque phrase de la réponse est traduite en dioula DÈS qu'elle est écrite (pendant que DeepSeek écrit la suite),
     et la voix de la 1re phrase se prépare aussitôt : le client lit et entend la réponse le plus tôt possible.

Événements envoyés à la page (en plus de ceux de fournisseurs.py) :
  {"type": "intention", "texte", "certitude"}  ce que le chatbot a compris (affiché sous le message du client)
  {"type": "morceau", "texte"}                 une phrase de la réponse, en dioula
  {"type": "francais", "texte"}                la même phrase en français (bouton « Voir en français »)
  {"type": "fin", "texte" (dioula), "francais", "intention", "certitude", ...temps}
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse

from . import consignes, conversation, dioula_relais, dioula_texte, fournisseurs, salutations, voix

# Traductions à l'aller (dioula -> français) : mesuré le 29/09/2026 sur 100 phrases AOCEDA, elles n'améliorent PAS la
# compréhension du 1er coup (46 % avec comme sans ; les traducteurs se trompent justement sur le vocabulaire de
# l'électricité, que le lexique couvre mieux) et coûtent ~0,7 s. Elles ne servent donc qu'à la RELANCE (point 3).
TRADUIRE_ALLER = False
RELANCE_AVEC_TRADUCTIONS = True
ATTENTE_TRADUCTIONS_RELANCE_S = 2.5
VOCAL_DUREE_VIE_S = 600
ATTENTE_TRADUCTION_S = 8.0
MAX_ESSAIS = 3             # 1er essai + relance + marge : jamais de boucle sans fin
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dioula")
_vocaux, _verrou = {}, threading.Lock()


# ── Détails d'un vocal (transcription -> message) ──────────────────────────────
def memoriser_vocal(session, details):
    """La transcription garde ici ce qu'elle a entendu (brut, réparé, mots douteux...) pour le message qui suit."""
    with _verrou:
        maintenant = time.time()
        for s in [s for s, d in _vocaux.items() if maintenant - d["t"] > VOCAL_DUREE_VIE_S]:
            _vocaux.pop(s, None)
        _vocaux[session] = {**details, "t": maintenant}


def _vocal_de(session, texte):
    with _verrou:
        d = _vocaux.get(session)
    if d and d.get("texte", "").strip() == (texte or "").strip():
        return d
    return None                                          # texte corrigé à la main par le client : c'est un écrit


# ── Dossier envoyé à DeepSeek ──────────────────────────────────────────────────
def dossier_langue_directe(texte, origine, langue_question, nom_locale):
    """Question posée dans une langue que DeepSeek comprend (français, anglais...) alors que la réponse est voulue en
    dioula/baoulé (menu) : pas de traduction de la question, rien de la langue locale à relire."""
    from . import langues
    nom = langues.nom(langue_question).lower()
    lignes = [f"[Message {'VOCAL' if origine == 'vocal' else 'ÉCRIT'} en {nom.upper()}, pas en {nom_locale}]",
              f"Message de l'utilisateur : « {texte} »",
              f"L'utilisateur a choisi de recevoir les réponses en {nom_locale} : réponds EN FRANÇAIS simple, comme "
              f"d'habitude (en-tête INTENTION / CERTITUDE compris) ; ta réponse sera traduite en {nom_locale}."]
    return {"texte": "\n".join(lignes), "brut": texte, "repare": texte, "vocal": origine == "vocal",
            "traductions": {"google": None, "djelia": None, "duree_s": 0, "erreurs": []}, "nombres": [], "lexique": {},
            "langue_question": langue_question}


def preparer_dossier(session, texte, origine, traduire_aller=TRADUIRE_ALLER, langue_question=None):
    if langue_question:                                  # question en français/anglais..., réponse voulue en dioula
        return dossier_langue_directe(texte, origine, langue_question, "dioula")
    vocal = _vocal_de(session, texte) if origine == "vocal" else None
    repare = vocal["repare"] if vocal else texte
    brut = vocal["brut"] if vocal else texte
    nombres = dioula_texte.lire_nombres(repare) or dioula_texte.lire_nombres(brut)
    lexique = dioula_texte.lexique_utile(brut, repare)
    trad = dioula_relais.vers_francais(repare) if traduire_aller else {"google": None, "djelia": None, "duree_s": 0,
                                                                        "erreurs": []}
    lignes = [f"[Message {'VOCAL' if vocal else 'ÉCRIT'} en dioula]"]
    if vocal:
        lignes.append(f"Entendu par la reconnaissance vocale : « {brut} »")
        if repare != brut:
            lignes.append(f"Après réparation automatique : « {repare} » (" +
                          " ; ".join(f"{r['entendu']} -> {r['repare']}" for r in vocal.get("reparations", [])) + ")")
        if vocal.get("douteux"):
            lignes.append("Mots entendus avec peu de certitude : " + ", ".join(vocal["douteux"]))
        lignes.append(f"Certitude globale de l'écoute : {vocal.get('certitude', 0):.2f} (sur 1)")
    else:
        lignes.append(f"Texte tapé par l'utilisateur : « {texte} »")
    if nombres:
        lignes.append("Nombres relus automatiquement : " + " ; ".join(
            f"« {n['texte']} » = {n['valeur']}" + (f" dɔrɔmɛ, soit {n['valeur_fcfa']} F CFA" if 'valeur_fcfa' in n else "")
            for n in nombres))
    if trad.get("google"):
        lignes.append(f"Traduction automatique Google (dioula -> français) : « {trad['google']} »")
    if trad.get("djelia"):
        lignes.append(f"Traduction automatique Djelia (bambara -> français) : « {trad['djelia']} »")
    dernier = dioula_texte.cle((repare.split() or [""])[-1])
    if dernier.endswith("wa") and len(repare.split()) >= 3:
        lignes.append("Indice : la phrase se termine par « wa » : c'est très probablement une QUESTION (oui/non).")
    formules = dioula_texte.formules_reconnues(repare) or dioula_texte.formules_reconnues(brut)
    if formules:
        lignes.append("Formules dioula reconnues (même mal entendues) : " + " ; ".join(f"« {f} » = {s}" for f, s in formules))
    if lexique:
        lignes.append("Lexique (mots présents) : " + " ; ".join(f"{m} = {s}" for m, s in lexique.items()))
    return {"texte": "\n".join(lignes), "brut": brut, "repare": repare, "vocal": bool(vocal), "traductions": trad,
            "nombres": nombres, "lexique": lexique}


# ── Lecture de l'en-tête « INTENTION / CERTITUDE » ─────────────────────────────
_INTENTION = re.compile(r"^\s*\**\s*INTENTION\s*\**\s*:\s*(.+?)\s*$", re.I | re.M)
_CERTITUDE = re.compile(r"^\s*\**\s*CERTI\w*\s*\**\s*:\s*\**\s*(haute|moyenne|basse|high|medium|low)\b.*$", re.I | re.M)
_LIGNE_TECHNIQUE = re.compile(r"^\s*\**\s*(INTENTION|CERTI\w*)\s*\**\s*:.*$\n?", re.I | re.M)
_NIVEAUX = {"high": "haute", "medium": "moyenne", "low": "basse"}
ENTETE_MAX = 400          # si le modèle oublie l'en-tête, tout est considéré comme la réponse


def _niveau(m):
    return _NIVEAUX.get(m.group(1).lower(), m.group(1).lower()) if m else None


def separer_entete(texte, fini=False):
    """Renvoie (intention, certitude, reste) si l'en-tête est complet (ou si fini), sinon None.
    Le reste ne contient JAMAIS de ligne technique (elle serait traduite et lue au client)."""
    mi, mc = _INTENTION.search(texte), _CERTITUDE.search(texte)
    if mi and mc:
        reste = _LIGNE_TECHNIQUE.sub("", texte[max(mi.end(), mc.end()):]).lstrip("\n ")
        if reste or fini:
            return mi.group(1).strip(), _niveau(mc), reste
        return None
    if fini or len(texte) > ENTETE_MAX:
        return (mi.group(1).strip() if mi else None), _niveau(mc), _LIGNE_TECHNIQUE.sub("", texte).strip()
    return None


_FIN_PHRASE = re.compile(r"(?<=[.!?…])\s+|\s*\n+\s*")    # un retour à la ligne termine aussi une phrase


def phrases_finies(texte):
    """(phrases terminées, reste en cours d'écriture)."""
    parts = _FIN_PHRASE.split(texte)
    return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]


def _avec_traductions(texte_dossier, trad):
    lignes = [texte_dossier]
    if trad.get("google"):
        lignes.append(f"Traduction automatique Google (dioula -> français) : « {trad['google']} »")
    if trad.get("djelia"):
        lignes.append(f"Traduction automatique Djelia (bambara -> français) : « {trad['djelia']} »")
    lignes.append("(2e essai : au 1er essai tu n'avais pas compris ; ces traductions peuvent aider, surtout si le sujet "
                  "n'est pas l'électricité. Même si tu ne comprends toujours pas, réponds au sujet le plus probable "
                  "(règle : jamais de « pas compris »).)")
    return "\n".join(lignes)


# ── Réponse ────────────────────────────────────────────────────────────────────
def repondre(session, texte, origine="ecrit", genre="femme", liste=None, traduire_aller=TRADUIRE_ALLER, source_langue="dioula",
             langue_question=None):
    profil = {"code": "dyu", "nom": "dioula",
              "dossier": lambda: preparer_dossier(session, texte, origine, traduire_aller, langue_question),
              "traductions_relance": (lambda d: _pool.submit(dioula_relais.vers_francais, d["repare"]))
              if RELANCE_AVEC_TRADUCTIONS and not traduire_aller and not langue_question else None,
              "consigne": consignes.systeme_dioula, "traduire": dioula_relais.lancer_vers_dioula,
              "avec_traductions": _avec_traductions}
    yield from repondre_relais(profil, session, genre, liste, source_langue)


def repondre_relais(profil, session, genre="femme", liste=None, source_langue="dioula", voix_auto=True):
    """Boucle de réponse d'une langue RELAIS (dioula, baoulé) : dossier -> DeepSeek (INTENTION/CERTITUDE, réponse en
    français) -> chaque phrase traduite dès qu'elle est écrite -> voix. `profil` décrit la langue (voir repondre).
    voix_auto : la page lira la réponse toute seule ; sinon la voix baoulé (GPU payant) n'est fabriquée que sur demande."""
    code, nom = profil["code"], profil["nom"]
    t0 = time.time()
    yield {"type": "langue", "code": code, "source": source_langue, "confiance": 1.0}
    dossier = profil["dossier"]()
    t_aller = round(time.time() - t0, 2)
    # traductions en arrière-plan : utilisées seulement si DeepSeek ne comprend pas du 1er coup
    trad_future = profil["traductions_relance"](dossier) if profil.get("traductions_relance") else None
    # 05/10/2026 : jamais deux fois la même réponse -> les dernières réponses sont rappelées, à ne pas répéter
    deja = conversation.historique(session)
    precedentes = [m["texte"] for m in deja if m["role"] == "model"][-3:]
    if precedentes:
        dossier["texte"] += ("\nTes dernières réponses dans cette conversation (n'en répète AUCUNE, ni la phrase ni l'idée : "
                             "apporte autre chose) : " + " | ".join(f"« {r[:220]} »" for r in precedentes))
    # 1re réponse de la conversation, ou la personne salue (09/10/2026) : la salutation de l'heure, mise par le code dans la
    # langue de la personne (jamais traduite) : « I ni su » / « Anun o »... ou, si elle a salué, la formule de RÉPONSE
    # (« Nse, i ni su » / « Awossi'n o ») ; le cerveau IA est prévenu de ne pas saluer lui-même
    recu = salutations.salutation_recue(code, dossier.get("repare", ""))
    salue = recu is not None
    salut = salutations.locale(code, reponse=salue, genre=genre, moment_recu=recu) if (not deja or salue) else None
    if salut:
        dossier["texte"] += salutations.note_relais(salut[1])
    historique, question_id = conversation.poser_question(session, dossier["texte"])
    systeme = profil["consigne"]()
    conversation.noter_langue(session, code)

    fin, intention, certitude, essais = None, None, None, 0
    dioula_phrases, fr_phrases, services, file = [], [], [], []
    premiere_phrase_s, premier_prepare, relance_faite = None, None, False
    debut_modele = True                                  # la 1re phrase du cerveau IA perd sa salutation (déjà mise)

    def lancer(phrase):
        nonlocal debut_modele
        if salut and debut_modele:
            debut_modele = False
            phrase = salutations.retirer_salutation(phrase).strip()
            if not phrase:                               # « Bonsoir. » tout seul : déjà dit
                return
        file.append((phrase, profil["traduire"](phrase)))

    def saluer():
        """La salutation de l'heure, en tête de la réponse (texte local + français), voix préparée tout de suite."""
        nonlocal premier_prepare
        if not salut:
            return
        local, fr = salut
        dioula_phrases.append(local); fr_phrases.append(fr); services.append("formule")
        if premier_prepare is None:
            premier_prepare = local
            conversation.autoriser_voix(session, [local])
            voix.preparer([local], code, genre)
        yield {"type": "morceau", "texte": local, "traduit": True}
        yield {"type": "francais", "texte": fr}

    def sortir(bloquer):
        """Envoie, dans l'ordre, les phrases déjà traduites (ou toutes si bloquer)."""
        nonlocal premiere_phrase_s, premier_prepare
        while file and (bloquer or file[0][1].done()):
            fr, tache = file.pop(0)
            try:
                dy, service = tache.result(timeout=ATTENTE_TRADUCTION_S)
            except (dioula_relais.RelaisIndisponible, DelaiDepasse, Exception) as e:
                dy, service = fr, f"non traduit ({str(e)[:60]})"
            dioula_phrases.append(dy); fr_phrases.append(fr); services.append(service)
            if premiere_phrase_s is None:
                premiere_phrase_s = round(time.time() - t0, 2)
            traduit = not service.startswith("non traduit")
            if premier_prepare is None and traduit:       # voix de la 1re phrase : tout de suite
                premier_prepare = voix.decouper(dy)[0] if voix.decouper(dy) else None
                if premier_prepare:
                    conversation.autoriser_voix(session, [premier_prepare])
                    voix.preparer([premier_prepare], code, genre)
            yield {"type": "morceau", "texte": (" " if len(dioula_phrases) > 1 else "") + dy, "traduit": traduit}
            yield {"type": "francais", "texte": (" " if len(fr_phrases) > 1 else "") + fr}

    def terminer(ev_fin):
        reponse = [x for x in services if x != "formule"]            # la salutation n'est pas une traduction
        non_traduit = sum(1 for x in reponse if x.startswith("non traduit"))
        # traducteurs en panne : la réponse est restée en français -> voix française (pas la voix locale sur du français),
        # et la salutation aussi en français (« Bonsoir. »), pour ne pas lire du dioula avec la voix française
        langue_voix = "fr" if reponse and non_traduit == len(reponse) else code
        if langue_voix == "fr" and "formule" in services:
            i = services.index("formule")
            dioula_phrases[i] = fr_phrases[i]
        reponse_fr = " ".join(fr_phrases).strip()
        reponse_dy = " ".join(dioula_phrases).strip()
        compact = f"[{nom}] « {dossier['repare']} »" + (f" -> compris : {intention}" if intention and certitude != "basse"
                                                         else " -> pas compris")
        conversation.remplacer_derniere_question(session, compact, question_id)
        conversation.ajouter_reponse(session, reponse_fr)
        morceaux = voix.decouper(reponse_dy)
        # baoulé : la page demande la voix de la réponse ENTIÈRE (un seul audio continu) : ce texte doit être autorisé
        conversation.autoriser_voix(session, morceaux + ([voix.texte_pour_voix(reponse_dy)] if code == "bci" else []))
        if langue_voix == "bci" and reponse_dy and voix_auto:
            voix.annoncer_baoule(reponse_dy)          # GPU : la voix part tout de suite, prête quand la page la lit seule
        voix.preparer([m for m in morceaux if m != premier_prepare], langue_voix, genre)
        return {**ev_fin, "type": "fin", "texte": reponse_dy, "francais": reponse_fr, "intention": intention,
                "certitude": certitude, "premiere_phrase_s": premiere_phrase_s, "traduction_aller_s": t_aller,
                "total_s": round(time.time() - t0, 2), "traducteurs": services, "relance": relance_faite,
                "non_traduit": non_traduit, "langue_voix": langue_voix}

    try:
        yield from saluer()                               # la salutation s'affiche tout de suite
        while fin is None and essais < MAX_ESSAIS:
            essais += 1
            ecrit, entete_lu, en_cours, decision = "", False, "", None
            flux = fournisseurs.repondre_flux(systeme, historique, liste=liste)
            try:
                for ev in flux:
                    if ev["type"] == "morceau":
                        ecrit += ev["texte"]
                        if not entete_lu:
                            r = separer_entete(ecrit)
                            if r is None:
                                continue
                            intention, certitude, en_cours = r
                            entete_lu = True
                            if certitude == "basse" and trad_future is not None and not relance_faite:
                                decision = "relancer"; break          # 2e essai avec les traductions
                            if intention:
                                yield {"type": "intention", "texte": intention, "certitude": certitude}
                        else:
                            en_cours += ev["texte"]
                        finies, en_cours = phrases_finies(en_cours)
                        for p in finies:
                            lancer(p)
                        yield from sortir(False)
                    elif ev["type"] == "recommencer":
                        entete_lu, ecrit, en_cours, file[:] = False, "", "", []
                        dioula_phrases.clear(); fr_phrases.clear(); services.clear()
                        debut_modele = True
                        yield ev
                        yield from saluer()                   # la page a tout effacé : la salutation revient en tête
                    elif ev["type"] == "fin":
                        if not entete_lu:
                            intention, certitude, en_cours = separer_entete(ecrit, fini=True)
                            if intention:
                                yield {"type": "intention", "texte": intention, "certitude": certitude}
                        if en_cours.strip():
                            lancer(_LIGNE_TECHNIQUE.sub("", en_cours).strip())
                        yield from sortir(True)
                        fin = terminer(ev)
                        yield fin
                    elif ev["type"] == "erreur":
                        conversation.annuler_question(session, question_id)
                        fin = ev
                        yield ev
                    else:
                        yield ev
            finally:
                flux.close()                              # arrête vraiment la demande DeepSeek en cours
            if decision == "relancer":
                relance_faite = True
                try:
                    trad = trad_future.result(timeout=ATTENTE_TRADUCTIONS_RELANCE_S)
                except Exception:
                    trad = {}
                if trad.get("google") or trad.get("djelia"):
                    texte_2 = profil["avec_traductions"](dossier["texte"], trad)
                    historique = historique[:-1] + [{**historique[-1], "texte": texte_2}]
                    conversation.remplacer_derniere_question(session, texte_2, question_id)
                    dossier["texte"] = texte_2
                continue                                  # 2e essai (sans traduction : même dossier) ; sa réponse part
        if fin is None:                                   # flux terminé sans réponse (ne devrait pas arriver)
            conversation.annuler_question(session, question_id)
            fin = {"type": "erreur", "texte": "Le chatbot n'a pas pu répondre. Réessayez dans un instant.", "essais": []}
            yield fin
    finally:
        if fin is None:                                   # réponse arrêtée par l'utilisateur ou connexion coupée
            conversation.annuler_question(session, question_id)
    yield {"type": "bilan", "langue_reponse": code, "source_langue": source_langue, "refaites": essais - 1, "fin": fin,
           "duree_s": round(time.time() - t0, 2), "dossier": dossier["texte"], "intention": intention,
           "certitude": certitude, "traduction_aller_s": t_aller}
