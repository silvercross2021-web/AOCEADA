"""BLOCS A et B : savoir CE QUI A ÉTÉ DIT, puis CE QUE LA PERSONNE VEUT (06/10/2026).

A. Le dossier d'indices (rassemblés par du code, sans IA) :
   - ce que l'oreille a entendu, ce qui a été réparé (contrôlé par le son), ses mots douteux et sa certitude ;
   - la traduction de DEUX interprètes (Google et NiuTrans, en même temps) et leur accord ;
   - le sens des mots trouvés dans le carnet de mots (sources libres), les nombres relus, les formules connues ;
   - les exemples VÉRIFIÉS les plus proches (banque d'exemples), et la conversation récente.
B. Le cerveau IA reçoit ce dossier et la LISTE FERMÉE des demandes (baoule_demandes) ; il doit répondre dans un format
   FIXE (JSON) : ses 3 meilleures hypothèses (demande + probabilité), les détails (montant, appareil, période), sa
   certitude, une reformulation et les indices qui l'ont convaincu. Il ne rédige PAS la réponse et ne peut pas inventer
   une demande : une réponse hors format est redemandée une fois, puis le système bascule sur l'ancien chemin.
"""
import json
import re
import time
from dataclasses import dataclass, field

from . import baoule_demandes, baoule_lexique, baoule_memoire, baoule_relais, baoule_texte, fournisseurs

ESSAIS = 2


class ComprehensionImpossible(Exception):
    pass


@dataclass
class Dossier:
    texte: str                      # ce que l'IA lit
    brut: str = ""                  # entendu par l'oreille
    repare: str = ""                # après réparation contrôlée par le son
    reparations: list = field(default_factory=list)
    certitude_ecoute: float = None
    traductions: dict = field(default_factory=dict)
    nombres: list = field(default_factory=list)
    exemples: list = field(default_factory=list)     # [(exemple, ressemblance)]
    vocal: bool = False
    langue_question: str = None
    mots: int = 0
    duree_s: float = 0.0


@dataclass
class Classement:
    hypotheses: list                # [{"demande", "probabilite"}], triées, toutes dans la liste
    details: dict                   # {"montant", "appareil", "periode"}
    certitude: str                  # haute | moyenne | basse (avis de l'IA)
    reformulation: str
    indices: list
    brut: str = ""                  # réponse brute de l'IA (journal)
    essais: int = 1
    duree_s: float = 0.0

    @property
    def demande(self):
        return self.hypotheses[0]["demande"]


def preparer_dossier(texte, vocal=None, langue_question=None, historique=None):
    """Rassemble les indices. `vocal` : détails de l'écoute (service_dioula._vocal_de) ou None (message écrit)."""
    t0 = time.time()
    historique = historique or []
    if langue_question:                                   # question posée en français/anglais : rien à traduire
        lignes = [f"[Message en {'FRANÇAIS' if langue_question == 'fr' else langue_question.upper()} : réponse voulue en baoulé]",
                  f"Message : « {texte} »"]
        d = Dossier("", brut=texte, repare=texte, langue_question=langue_question, mots=len(texte.split()))
    else:
        brut = vocal["brut"] if vocal else texte
        repare = vocal["repare"] if vocal else texte
        d = Dossier("", brut=brut, repare=repare, reparations=(vocal or {}).get("reparations", []),
                    certitude_ecoute=(vocal or {}).get("certitude"), vocal=bool(vocal),
                    mots=len(baoule_texte.mots_de(repare)))
        d.traductions = baoule_relais.deux_interpretes(repare)
        d.nombres = baoule_texte.lire_nombres(repare)
        d.exemples = baoule_memoire.proches(repare)
        lignes = [f"[Message {'VOCAL' if vocal else 'ÉCRIT'} en baoulé]"]
        if vocal:
            lignes.append(f"Entendu par l'oreille baoulé : « {brut} »")
            if d.reparations:
                lignes.append("Réparé (contrôlé par le son) : « " + repare + " » ("
                              + " ; ".join(f"{r['entendu']} -> {r['repare']}" for r in d.reparations) + ")")
            if vocal.get("douteux"):
                lignes.append("Mots entendus avec peu de certitude : " + ", ".join(vocal["douteux"]))
            if d.certitude_ecoute is not None:
                lignes.append(f"Certitude de l'oreille : {d.certitude_ecoute:.2f} (souvent trop optimiste)")
        else:
            lignes.append(f"Texte tapé : « {texte} »")
        tr = d.traductions
        if tr.get("google"):
            lignes.append(f"Interprète 1 (Google) : « {tr['google']} »")
        if tr.get("niutrans"):
            lignes.append(f"Interprète 2 (NiuTrans) : « {tr['niutrans']} »")
        if tr.get("accord") is not None:
            lignes.append(f"Accord entre les deux interprètes : {tr['accord']:.2f} (1 = identiques)")
        if not tr.get("google") and not tr.get("niutrans"):
            lignes.append("Aucun interprète n'a répondu : fie-toi au carnet de mots et aux exemples.")
        if d.nombres:
            lignes.append("Nombres relus : " + " ; ".join(f"« {n['texte']} » = {n['valeur']}" for n in d.nombres))
        formules = baoule_texte.formules_reconnues(repare)
        if formules:
            lignes.append("Formules connues : " + " ; ".join(f"« {f} » = {s}" for f, s in formules))
        sens = baoule_lexique.sens_du_texte(repare)
        if sens:
            lignes.append("Carnet de mots (sens) : " + " ; ".join(f"{m} = {s}" for m, s in sens.items()))
        for ex, score in d.exemples:
            lignes.append(f"Exemple vérifié proche ({score:.0%}) : « {ex['bci']} » = demande {ex['demande']}"
                          + (f" ({ex['sens']})" if ex.get("sens") else ""))
    recents = [m for m in historique if m.get("role") in ("user", "model")][-4:]
    if recents:
        lignes.append("Conversation récente : " + " | ".join(
            f"{'personne' if m['role'] == 'user' else 'assistant'} : {m['texte'][:160]}" for m in recents))
    d.texte = "\n".join(lignes)
    d.duree_s = round(time.time() - t0, 2)
    return d


SYSTEME = """Tu es le module de COMPRÉHENSION de l'assistant AOCEDA (électricité de la maison, Côte d'Ivoire, francs CFA).
La personne parle BAOULÉ (ou pose sa question en français/anglais pour une réponse en baoulé). Tu ne lui réponds PAS :
tu CLASSES son message dans la LISTE FERMÉE ci-dessous. La réponse sera construite ensuite avec ses vraies données.

Tu reçois un DOSSIER d'indices. Ils contiennent des erreurs : l'oreille colle ou déforme des mots, les interprètes
automatiques se trompent souvent. CROISE-LES. Pièges connus : « sika » = argent en FRANCS CFA (jamais des dollars) ;
« ɛɛ » = oui et « cɛcɛ » = non, même si un interprète dit l'inverse ; un sens imagé d'un mot de l'électricité est faux ;
« di aliɛ » / « dili aliɛ » (mot à mot « manger ») veut dire CONSOMMER : un interprète qui écrit « combien ai-je
mangé » ou « mon déjeuner » SANS nommer d'aliment parle en fait de la CONSOMMATION d'électricité (mesuré le
06/10/2026). Mais si un aliment, un légume, un plat ou un repas précis est nommé (laitue, riz, poisson...), c'est
vraiment de la nourriture : « hors_sujet ».
Un exemple vérifié très proche (80 % et plus) est un indice fort. Si les interprètes ne parlent ni d'électricité ni
d'AOCEDA, c'est probablement « hors_sujet » : ne ramène pas tout à l'électricité.

LISTE FERMÉE (identifiant : description) :
{liste}

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{{"hypotheses": [{{"demande": "<identifiant>", "probabilite": <0 à 100>}}, ... (1 à 3, la plus probable d'abord)],
 "details": {{"montant": <montant en francs CFA, ou null>, "appareil": "<appareil en français, ou null>",
             "periode": "<une de : {periodes}, ou null>"}},
 "certitude": "haute" | "moyenne" | "basse",
 "reformulation": "<ce que veut la personne, en une phrase courte en français>",
 "indices": ["<1 à 3 indices qui t'ont convaincu>"]}}

Règles : « demande » est TOUJOURS un identifiant de la liste. N'invente aucun montant : mets un montant seulement s'il
est dans les nombres relus ou clairement dit. « haute » seulement si plusieurs indices concordent."""


def systeme():
    return SYSTEME.format(liste=baoule_demandes.liste_pour_ia(), periodes=", ".join(baoule_demandes.PERIODES))


def _json(texte):
    t = (texte or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    debut, fin = t.find("{"), t.rfind("}")
    if debut < 0 or fin <= debut:
        raise ValueError("pas d'objet JSON")
    return json.loads(t[debut:fin + 1])


def valider(d):
    """Contrôle du format (le règlement vérifie ensuite le fond). Renvoie Classement ; lève ValueError."""
    hyps = []
    for h in d.get("hypotheses") or []:
        dem = str(h.get("demande", "")).strip()
        if dem not in baoule_demandes.CATALOGUE:
            raise ValueError(f"demande « {dem} » absente de la liste")
        try:
            p = max(0, min(100, int(float(h.get("probabilite", 0)))))
        except (TypeError, ValueError):
            p = 0
        if dem not in {x["demande"] for x in hyps}:
            hyps.append({"demande": dem, "probabilite": p})
    if not hyps:
        raise ValueError("aucune hypothèse")
    hyps = sorted(hyps, key=lambda x: -x["probabilite"])[:3]
    det = d.get("details") or {}
    montant = det.get("montant")
    try:
        montant = int(float(str(montant).replace(" ", ""))) if montant not in (None, "", "null") else None
    except ValueError:
        montant = None
    periode = det.get("periode") if det.get("periode") in baoule_demandes.PERIODES else None
    appareil = (str(det["appareil"]).strip() or None) if det.get("appareil") not in (None, "", "null") else None
    cert = d.get("certitude") if d.get("certitude") in ("haute", "moyenne", "basse") else "basse"
    return Classement(hyps, {"montant": montant, "appareil": appareil, "periode": periode}, cert,
                      str(d.get("reformulation") or "").strip()[:240], [str(x)[:160] for x in (d.get("indices") or [])][:3])


def classer(dossier, liste=None):
    """Demande au cerveau IA de classer le message. Lève ComprehensionImpossible après ESSAIS réponses invalides."""
    t0, sys_, erreur, brut = time.time(), systeme(), None, ""
    for essai in range(1, ESSAIS + 1):
        texte = dossier.texte if not erreur else (dossier.texte + f"\n\n(Ta réponse précédente était invalide : {erreur}. "
                                                                  "Réponds UNIQUEMENT par l'objet JSON demandé.)")
        fin = None
        for ev in fournisseurs.repondre_flux(sys_, [{"role": "user", "texte": texte}], liste=liste):
            if ev["type"] in ("fin", "erreur"):
                fin = ev
        if not fin or fin["type"] == "erreur":
            raise ComprehensionImpossible((fin or {}).get("texte") or "aucun cerveau IA ne répond")
        brut = fin["texte"]
        try:
            c = valider(_json(brut))
            c.brut, c.essais, c.duree_s = brut[:1500], essai, round(time.time() - t0, 2)
            return c
        except (ValueError, json.JSONDecodeError) as e:
            erreur = str(e)[:160]
    raise ComprehensionImpossible(f"réponse hors format après {ESSAIS} essais : {erreur} ; « {brut[:200]} »")
