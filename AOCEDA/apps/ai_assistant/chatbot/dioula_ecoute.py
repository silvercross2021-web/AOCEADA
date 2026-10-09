"""Écoute du DIOULA : Meta Omnilingual ASR, modèle CTC 1B v2 compressé int8 (Apache 2.0), sur le serveur, hors ligne.

Choisi le 29/09/2026 après le banc de test du laboratoire (bancs/stt_dioula) : même précision que MMS-1B
(13,9 % de sons faux sur 59 extraits), plus rapide, 4 fois moins de mémoire, seul utilisable commercialement.

Le modèle est appelé directement avec onnxruntime (déjà installé pour Kokoro) : même précision que sherpa-onnx
(13,92 % contre 13,87 %, écart de calcul), aucune installation, et on garde ses PROBABILITÉS lettre par lettre :
  - certitude de chaque mot (pour décider s'il faut faire confirmer) ;
  - « preuve sonore » d'une correction : on peut mesurer si l'audio colle mieux au mot corrigé qu'au mot entendu.

Préparation de l'audio : silences du début et de la fin retirés (moins de calcul), normalisation officielle de Meta
(moyenne 0, variance 1). Les audios de plus de 30 s sont coupés aux silences (mémoire et vitesse maîtrisées).

Alphabet : le modèle connaît 1 600 langues ; sur du dioula difficile (bruit, débit rapide), il lui arrive d'écrire en
arabe, thaï ou japonais (mesuré : « مي مسالياتا », « うhあちで »). La lecture principale est donc LIMITÉE À L'ALPHABET
LATIN (lettres dioula ɛ ɔ ɲ ŋ et accents compris). La lecture libre est gardée : elle sert à reconnaître une autre
langue (un vrai message en arabe reste en arabe dans la lecture libre). Même calcul du modèle : 0 seconde de plus.

Le moteur (classe Moteur) sert aussi à l'écoute du BAOULÉ (baoule_ecoute.py) : même famille de modèle (Omnilingual CTC),
même format de fichier, seul le modèle change. Les fonctions du module (charger, transcrire_audio...) restent celles du
dioula.
"""
import unicodedata
import math
import os
import threading
import time

import numpy as np

from .config import MODELES

DOSSIER = MODELES / "omnilingual-1b-ctc-v2-int8"
TAUX = 16000
TRAME_S = 0.02                 # une probabilité toutes les 20 ms
BLANC = 0                      # jeton « rien » du CTC
MORCEAU_MAX_S = 15.0           # vocal plus long : coupé aux pauses en morceaux de 15 s au plus (mesuré : 21 % -> 11 % d'erreurs)
MORCEAU_MIN_S = 5.0            # ... pas de coupure avant 5 s (couper les courts les dégrade : 7,0 % -> 7,9 %)
PAUSE_MIN_S = 0.25             # silence minimum pour être une vraie pause
FILS = None                    # fils de calcul (None = tous les cœurs)
ATTENTE_ACTIVE = "0"           # « 0 » : pas de fils qui tournent à vide (mesuré : jamais plus lent, et ne vole pas le processeur)
MARGE_SILENCE_S = 0.15
# Réserve de mémoire d'onnxruntime (« arena ») : gardée telle quelle, elle retient le pic atteint par le plus long vocal
# (audit du 09/10/2026 : serveur passé de 1,8 à 5,8 Go, PC qui échangeait avec le disque). Mesuré le 09/10/2026 (vocal
# de 45 s) : sans réserve, la mémoire est rendue mais la 1re écoute longue prend 22,5 s au lieu de 16,5 s. Choix : la
# réserve sert PENDANT l'écoute et elle est RÉTRÉCIE à la fin de chaque écoute (« retrecir », par défaut).
# CHATBOT_ONNX_RESERVE = retrecir | garder (ancien comportement) | sans.
RESERVE_MEMOIRE = os.environ.get("CHATBOT_ONNX_RESERVE", "retrecir")


class Annulee(Exception):
    """Écoute abandonnée en cours de route : son résultat ne servait plus (une autre langue a été reconnue)."""


class Annulation:
    """Permet d'arrêter une écoute EN PLEIN CALCUL (onnxruntime : RunOptions.terminate). Audit du 09/10/2026 : les écoutes
    lancées « au cas où » (conversation en dioula, vocal finalement français) continuaient jusqu'au bout, +60 % de calcul
    pour tout le serveur."""

    def __init__(self):
        self._verrou, self._en_cours, self.annulee = threading.Lock(), [], False

    def annuler(self):
        with self._verrou:
            self.annulee = True
            for options in self._en_cours:
                options.terminate = True

    def _debut(self, options):
        with self._verrou:
            if self.annulee:
                raise Annulee()
            self._en_cours.append(options)

    def _fin(self, options):
        with self._verrou:
            if options in self._en_cours:
                self._en_cours.remove(options)


def _latin(t):
    """Jeton permis en lecture latine : lettre latine (dont ɛ ɔ ɲ ŋ), accent, chiffre, apostrophe, trait d'union, espace."""
    if len(t) != 1:
        return False
    if t in " '’-" or t.isdigit():
        return True
    if unicodedata.category(t) == "Mn":
        return True
    return "LATIN" in unicodedata.name(t, "")


class Moteur:
    """Un modèle d'écoute Omnilingual CTC compressé (model.int8.onnx + tokens.txt), chargé une seule fois."""

    def __init__(self, dossier, nom):
        self.dossier, self.nom = dossier, nom
        self.etat = {"session": None, "jetons": None, "index": None, "espace": None, "interdits": None,
                     "verrou": threading.Lock()}

    def charger(self, fils=None):
        """Charge le modèle une seule fois (dioula 1B : ≈ 3 s, ≈ 1 Go ; baoulé 300M : ≈ 1 s, ≈ 0,4 Go)."""
        e = self.etat
        with e["verrou"]:
            if e["session"] is None:
                import onnxruntime as ort
                o = ort.SessionOptions()
                # tous les cœurs : mesuré plus rapide SEUL (4,4 s contre 4,9 s pour 10 s de parole) ET à deux en même temps
                # (7,6 s contre 8,3 s) qu'avec la moitié des cœurs
                o.intra_op_num_threads = fils or FILS or max(2, os.cpu_count() or 4)
                o.inter_op_num_threads = 1
                o.enable_cpu_mem_arena = RESERVE_MEMOIRE != "sans"
                o.add_session_config_entry("session.intra_op.allow_spinning", ATTENTE_ACTIVE)
                session = ort.InferenceSession(str(self.dossier / "model.int8.onnx"), o, providers=["CPUExecutionProvider"])
                jetons = []
                for ligne in (self.dossier / "tokens.txt").read_text(encoding="utf-8").splitlines():
                    texte, _, num = ligne.rpartition(" ")
                    jetons.append((texte, int(num)))
                e["jetons"] = [t for t, _ in sorted(jetons, key=lambda x: x[1])]
                e["index"] = {t: i for i, t in enumerate(e["jetons"]) if len(t) == 1}
                e["espace"] = e["index"][" "]
                permis = np.array([i == BLANC or _latin(t) for i, t in enumerate(e["jetons"])])
                e["interdits"] = ~permis
                e["permis_idx"] = np.where(permis)[0]
                e["colonne"] = {int(i): c for c, i in enumerate(e["permis_idx"])}
                e["session"] = session                    # en dernier : pret() n'est vrai que si tout est prêt
            return e["session"]

    def pret(self):
        return self.etat["session"] is not None

    def disponible(self):
        return (self.dossier / "model.int8.onnx").exists()

    def transcrire_audio(self, audio, garder_probas=True, annulation=None):
        return _transcrire(self, audio, garder_probas, annulation)


_dioula = Moteur(DOSSIER, "omnilingual-1b")
_etat = _dioula.etat


def charger(fils=None):
    """Charge le modèle dioula une seule fois (≈ 3 s, ≈ 1 Go de mémoire). Appelé au démarrage du serveur."""
    return _dioula.charger(fils)


def pret():
    return _dioula.pret()


def disponible():
    """Le modèle est-il sur le disque ? (installé par manage.py installer_modeles_ia ; sinon pas d'écoute dioula)"""
    return _dioula.disponible()


# ── Préparation de l'audio ─────────────────────────────────────────────────────
def _energie_db(audio, trame=320):
    n = len(audio) // trame
    if n == 0:
        return np.array([-120.0])
    e = np.square(audio[: n * trame].reshape(n, trame)).mean(axis=1)
    return 10 * np.log10(e + 1e-10)


VOLUME_CIBLE = 0.5            # crête visée pour un enregistrement trop faible
VOLUME_FAIBLE = 0.05          # crête en dessous : on remonte le volume
VOLUME_MIN = 2e-4             # en dessous : du vrai silence (rien à remonter)


def remonter_volume(audio):
    """Enregistrement très faible (micro lointain, téléphone) : volume remonté AVANT de chercher la parole.
    Bug trouvé le 29/09/2026 sur de vraies voix baoulé (Common Voice) : 12 vocaux sur 30 avaient une crête de 0,001 à
    0,003 ; le seuil absolu de retirer_silences (-60 dB) les prenait pour du silence et rien n'était entendu.
    Le modèle normalise lui-même le son : remonter le volume ne change rien pour un vocal normal."""
    crete = float(np.abs(audio).max()) if len(audio) else 0.0
    if VOLUME_MIN < crete < VOLUME_FAIBLE:
        return (audio * (VOLUME_CIBLE / crete)).astype(np.float32)
    return audio


def retirer_silences(audio):
    """Retire le silence du début et de la fin (seuil : 35 dB sous le passage le plus fort)."""
    db = _energie_db(audio)
    parole = np.where(db > max(db.max() - 35, -60))[0]
    if len(parole) == 0:
        return audio[:0]
    marge = int(MARGE_SILENCE_S / TRAME_S)
    debut, fin = max(0, parole[0] - marge), min(len(db), parole[-1] + 1 + marge)
    return audio[debut * 320: fin * 320]


def pauses(audio, pause_min_s=None):
    """Trames (20 ms) au milieu de chaque vraie pause (silence ≥ pause_min_s) : les bons endroits où couper."""
    pause_min_s = pause_min_s or PAUSE_MIN_S
    db = _energie_db(audio)
    calme = db < max(db.max() - 30, -55)
    coupes, i, n = [], 0, len(calme)
    while i < n:
        if calme[i]:
            j = i
            while j < n and calme[j]:
                j += 1
            if (j - i) * TRAME_S >= pause_min_s and i > 0 and j < n:
                coupes.append((i + j) // 2)
            i = j
        else:
            i += 1
    return coupes, db


def decouper_aux_silences(audio, maxi_s=None, mini_s=None, pause_min_s=None):
    """Morceaux coupés aux VRAIES PAUSES : chaque pause dès que le morceau dépasse mini_s, et au plus maxi_s
    (sans pause, on coupe au moment le plus calme). Mesuré le 29/09/2026 : sur des vocaux de 25-35 s, transcrire d'un
    seul bloc donne 21,3 % de sons faux, par phrases 9,9 % (le modèle se dégrade sur les longs passages)."""
    maxi_s, mini_s = maxi_s or MORCEAU_MAX_S, mini_s or MORCEAU_MIN_S
    if len(audio) <= maxi_s * TAUX:                     # vocal court : jamais coupé
        return [audio]
    coupes_possibles, db = pauses(audio, pause_min_s)
    fmax, fmin, n = int(maxi_s / TRAME_S), int(mini_s / TRAME_S), len(db)
    morceaux, debut = [], 0
    while n - debut > fmin:
        suivantes = [c for c in coupes_possibles if debut + fmin <= c <= debut + fmax]
        if suivantes:
            c = suivantes[0]
        elif n - debut > fmax:
            zone = db[debut + int(fmax * 0.6): debut + fmax]
            c = debut + int(fmax * 0.6) + int(np.argmin(zone))
        else:
            break
        morceaux.append(audio[debut * 320: c * 320]); debut = c
    morceaux.append(audio[debut * 320:])
    return [m for m in morceaux if len(m) > 0]


# ── Transcription ──────────────────────────────────────────────────────────────
class Ecoute:
    """Résultat d'une écoute : texte, mots avec certitude, et accès aux probabilités (preuve sonore)."""

    def __init__(self, mots, lp, duree_audio_s, duree_calcul_s, texte_libre="", moteur=None):
        self.mots = mots                      # [{"mot", "certitude", "t0", "t1"}] (t0/t1 en trames), lecture latine
        self.texte_libre = texte_libre        # lecture sans limite d'alphabet (pour reconnaître une autre langue)
        self._lp = lp                         # log-probabilités [trames, jetons] (None si audio vide)
        self.duree_audio_s = duree_audio_s
        self.duree_calcul_s = duree_calcul_s
        self.moteur = moteur or _dioula       # modèle qui a écouté (ses lettres servent à la preuve sonore)

    @property
    def texte(self):
        return " ".join(m["mot"] for m in self.mots)

    @property
    def certitude(self):
        """Certitude globale : moyenne des certitudes des mots, pondérée par leur longueur."""
        if not self.mots:
            return 0.0
        n = sum(len(m["mot"]) for m in self.mots)
        return round(sum(m["certitude"] * len(m["mot"]) for m in self.mots) / n, 3)

    def score_sonore(self, chaine, t0, t1):
        """Log-probabilité CTC que l'audio des trames [t0, t1) dise exactement `chaine` (None si lettre inconnue).
        Sert à comparer deux lectures possibles du MÊME passage : la plus haute colle le mieux au son."""
        if self._lp is None:
            return None
        etat = self.moteur.etat
        col = etat["colonne"]                                  # n° de lettre -> colonne gardée (lettres latines)
        ids = [col.get(etat["index"].get(c)) for c in chaine]
        if not ids or None in ids:
            return None
        lp = self._lp[max(0, t0): min(len(self._lp), t1)]
        if len(lp) == 0:
            return None
        blanc = col[BLANC]
        etats = [blanc]
        for i in ids:
            etats += [i, blanc]
        s = len(etats)
        e = lp[:, etats]                                       # [trames, états]
        saut = np.array([k >= 2 and etats[k] != blanc and etats[k] != etats[k - 2] for k in range(s)])
        alpha = np.full(s, -np.inf)
        alpha[0], alpha[1] = e[0, 0], e[0, 1]
        for t in range(1, len(e)):
            a1 = np.concatenate([[-np.inf], alpha[:-1]])
            a2 = np.where(saut, np.concatenate([[-np.inf, -np.inf], alpha[:-2]]), -np.inf)
            alpha = np.logaddexp(np.logaddexp(alpha, a1), a2) + e[t]
        return float(np.logaddexp(alpha[-1], alpha[-2]))

    def pour_api(self):
        return {"texte": self.texte, "texte_libre": self.texte_libre, "certitude": self.certitude,
                "duree_audio_s": self.duree_audio_s,
                "duree_calcul_s": self.duree_calcul_s,
                "mots": [{"mot": m["mot"], "certitude": round(m["certitude"], 3)} for m in self.mots]}


def _decoder(lp, decalage, etat=None):
    """Lecture la plus probable (CTC glouton) + certitude par lettre, regroupée en mots."""
    etat = etat or _etat
    jetons, espace = etat["jetons"], etat["espace"]
    ids = lp.argmax(axis=1)
    p = np.exp(lp[np.arange(len(ids)), ids])
    mots, courant, prec = [], None, -1
    for t, (i, pr) in enumerate(zip(ids, p)):
        if i != prec and i != BLANC:
            if i == espace:
                if courant:
                    mots.append(courant); courant = None
            elif len(jetons[i]) == 1:
                if courant is None:
                    courant = {"lettres": [], "probas": [], "t0": t + decalage}
                courant["lettres"].append(jetons[i]); courant["probas"].append(float(pr))
                courant["t1"] = t + 1 + decalage
        elif i == prec and i != BLANC and courant and i != espace:
            courant["probas"][-1] = max(courant["probas"][-1], float(pr))
            courant["t1"] = t + 1 + decalage
        prec = i
    if courant:
        mots.append(courant)
    sortie = []
    for m in mots:
        # certitude d'un mot = moyenne géométrique de ses lettres (une seule lettre douteuse fait baisser le mot)
        cert = math.exp(sum(math.log(max(x, 1e-6)) for x in m["probas"]) / len(m["probas"]))
        sortie.append({"mot": "".join(m["lettres"]), "certitude": cert, "t0": m["t0"], "t1": m["t1"],
                       "lettres": list(zip(m["lettres"], m["probas"]))})
    return sortie


def _options():
    """Réglages d'UN calcul : la réserve de mémoire est rétrécie à la fin (voir RESERVE_MEMOIRE) ; l'objet sert aussi à
    arrêter le calcul (Annulation)."""
    import onnxruntime as ort
    o = ort.RunOptions()
    if RESERVE_MEMOIRE == "retrecir":
        o.add_run_config_entry("memory.enable_memory_arena_shrinkage", "cpu:0")
    return o


def _transcrire(moteur, audio, garder_probas=True, annulation=None):
    """audio : numpy float32 16 kHz mono. Renvoie un objet Ecoute. `annulation` (Annulation) : l'écoute peut être arrêtée
    en plein calcul ; elle lève alors Annulee."""
    session = moteur.charger()
    etat = moteur.etat
    t0 = time.time()
    audio = remonter_volume(np.asarray(audio, dtype=np.float32).reshape(-1))
    duree = len(audio) / TAUX
    utile = retirer_silences(audio)
    if len(utile) < int(0.25 * TAUX):
        return Ecoute([], None, round(duree, 2), round(time.time() - t0, 3), moteur=moteur)
    mots, blocs, decalage, libre = [], [], 0, []
    for morceau in decouper_aux_silences(utile):
        x = (morceau - morceau.mean()) / np.sqrt(morceau.var() + 1e-5)
        options = _options()
        if annulation is not None:
            annulation._debut(options)                    # déjà annulée : Annulee, sans calculer
        try:
            logits = session.run(None, {"x": x[None].astype(np.float32)}, options)[0][0]
        except Exception:
            if annulation is not None and annulation.annulee:
                raise Annulee()
            raise
        finally:
            if annulation is not None:
                annulation._fin(options)
        libre += [m["mot"] for m in _decoder_rapide(logits, etat)]
        logits[:, etat["interdits"]] = -np.inf           # lecture latine
        lp = logits - logits.max(axis=1, keepdims=True)
        lp = lp - np.log(np.exp(lp).sum(axis=1, keepdims=True))
        mots += _decoder(lp, decalage, etat)
        if garder_probas:                                 # seulement les lettres latines : 12 fois moins de mémoire
            blocs.append(lp[:, etat["permis_idx"]].astype(np.float32))
        decalage += len(lp)
    lp = np.concatenate(blocs) if blocs else None
    return Ecoute(mots, lp, round(duree, 2), round(time.time() - t0, 3), " ".join(libre), moteur=moteur)


def transcrire_audio(audio, garder_probas=True, annulation=None):
    """Écoute DIOULA. audio : numpy float32 16 kHz mono. Renvoie un objet Ecoute."""
    return _transcrire(_dioula, audio, garder_probas, annulation)


def fusionner(ecoutes):
    """Une seule écoute à partir de morceaux écoutés séparément (vocal écouté PENDANT qu'on parle) : mots mis bout à
    bout, positions décalées, probabilités recollées (la preuve sonore reste valable sur le tout)."""
    mots, blocs, decalage = [], [], 0
    for e in ecoutes:
        for m in e.mots:
            mots.append({**m, "t0": m["t0"] + decalage, "t1": m["t1"] + decalage})
        if e._lp is not None:
            blocs.append(e._lp)
            decalage += len(e._lp)
    return Ecoute(mots, np.concatenate(blocs) if blocs else None, round(sum(e.duree_audio_s for e in ecoutes), 2),
                  round(sum(e.duree_calcul_s for e in ecoutes), 3), " ".join(e.texte_libre for e in ecoutes if e.texte_libre),
                  moteur=ecoutes[0].moteur if ecoutes else None)


def _decoder_rapide(logits, etat=None):
    """Lecture libre (tous alphabets), sans probabilités : seulement le texte."""
    etat = etat or _etat
    jetons, espace = etat["jetons"], etat["espace"]
    ids = logits.argmax(axis=1)
    lettres, prec = [], -1
    for i in ids:
        if i != prec and i != BLANC and len(jetons[i]) == 1:
            lettres.append(jetons[i])
        prec = i
    return [{"mot": m} for m in "".join(lettres).split()]
