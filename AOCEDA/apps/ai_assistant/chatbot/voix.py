"""Voix du chatbot : transcrire un message vocal, lire une réponse à voix haute. Tout est GRATUIT.

Transcription : WHISPER installé sur le serveur (faster-whisper, hors ligne, illimité, 99 langues), en 2 temps :
  1. le petit modèle « tiny » trouve la LANGUE (0,3 s) ; 2. « small » transcrit en connaissant la langue (2,3 s).
  Mesuré le 29/09/2026 sur nos 10 vocaux : 2,6 s au lieu de 4,4 s, 10/10 langues, 0 mot faux.
  (C'était la recherche de la langue par « small » qui coûtait 2 s.) Si « tiny » hésite, « small » cherche seul.
  Si une langue est imposée dans le menu, on saute l'étape 1.
  Le texte passe ensuite par le même chemin qu'un message écrit : une seule logique de réponse.
  DIOULA (étape 2) : Whisper ne le connaît pas. En mode Automatique, si « tiny » n'est pas sûr d'une langue du chatbot,
  Omnilingual (dioula_ecoute) écoute et son texte tranche (dioula_routage) ; le texte dioula est ensuite réparé
  (dioula_texte) et ses détails (brut, mots douteux...) sont gardés pour le message (service_dioula).

Lecture : voix neurales Microsoft (edge-tts, sans clé, 142 langues, très humaines), la voix est choisie
  selon la LANGUE DE LA RÉPONSE (voix « Multilingual », les plus naturelles, en priorité).
  Secours : Kokoro installé sur le serveur (français et anglais, hors ligne) ; puis la voix du navigateur
  (côté page). Réponse découpée en morceaux (le son démarre vite) et gardée en cache (2e écoute immédiate).
  DIOULA : voix Djelia (bambara, démonstration sans clé ; ~2,2 s par phrase, connexion gardée ouverte). Une seule voix :
  le choix Femme/Homme ne s'applique pas. Pas de secours navigateur (aucune voix dioula dans les navigateurs).
  BAOULÉ : OmniVoice (voix_baoule : GPU Cerebrium, secours sur le PC), qui imite un vrai locuteur baoulé ; deux voix
  depuis le 18/10/2026 (Femme : RK, WAXAL ; Homme : Common Voice 566016a2) ; fabriquée dans une file à part, la page
  affiche le texte tout de suite et la voix arrive ensuite.
"""
import asyncio
import hashlib
import io
import json
import re
import threading
import time
import wave

from . import detection, langues
from .config import CACHE, CONFIG, MODELES

AUDIO_MAX_S = 60                      # même limite que la page : un message vocal, pas un enregistrement d'une heure
AUDIO_MAX_OCTETS = 2_500_000          # 60 s en WAV 16 kHz mono ≈ 1,9 Mo
AUDIO_MIN_S = 0.4
TRANSCRIPTIONS_SIMULTANEES = 2        # plusieurs personnes : 2 transcriptions en même temps...
MAX_EN_ATTENTE = 6                    # ... et au plus 6 en attente ; au-delà : « serveur occupé » tout de suite
ATTENTE_MAX_S = 30
DOSSIER_VOIX = CACHE / "tts"
DOSSIER_KOKORO = MODELES / "kokoro"          # voix de secours (installée par manage.py installer_modeles_ia)
DOSSIER_WHISPER = MODELES / "whisper"        # Whisper tiny + small (téléchargés une fois ici)

# Phrases que Whisper « invente » parfois sur du silence ou du bruit (défaut connu de Whisper)
FANTOMES = re.compile(r"(sous-titr|amara\.org|merci d'avoir regard|abonnez-vous|thanks? for watching|subscribe|"
                      r"www\.|\.com\b|♪)", re.I)


class ErreurVoix(Exception):
    pass


class ServeurOccupe(ErreurVoix):
    pass


# ── Audio ──────────────────────────────────────────────────────────────────────
def duree_wav(octets):
    """Durée d'un WAV (entier 16 bits, 8 bits... ; et aussi « flottant », que le module wave ne lit pas), ou None."""
    try:
        with wave.open(io.BytesIO(octets)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        pass
    try:
        import soundfile as sf
        info = sf.info(io.BytesIO(octets))
        return info.frames / float(info.samplerate) if info.format == "WAV" and info.samplerate else None
    except Exception:
        return None


def verifier_audio(octets):
    """Seul un vrai WAV d'au plus AUDIO_MAX_S secondes est accepté (c'est ce qu'envoie la page). Messages exacts (audit du
    09/10/2026 : un fichier trop LOURD était annoncé « trop long », un WAV flottant « pas un WAV »)."""
    if not octets:
        raise ErreurVoix("Audio vide.")
    if len(octets) > AUDIO_MAX_OCTETS:
        raise ErreurVoix(f"Fichier audio trop lourd (au plus {AUDIO_MAX_OCTETS / 1e6:.1f} Mo, soit {AUDIO_MAX_S} secondes en "
                         "WAV 16 kHz mono).".replace(".", ",", 1))
    d = duree_wav(octets)
    if d is None:
        raise ErreurVoix("Format audio refusé : la page doit envoyer un fichier WAV.")
    if d < AUDIO_MIN_S:
        raise ErreurVoix("Message vocal trop court : parlez un peu plus longtemps.")
    if d > AUDIO_MAX_S + 1:
        raise ErreurVoix(f"Message vocal trop long (maximum {AUDIO_MAX_S} secondes).")
    return d


# ── Transcription : Whisper sur le serveur ────────────────────────────────────
_whisper = {"modele": None, "detecteur": None, "verrou": threading.Lock(),
            "places": threading.BoundedSemaphore(TRANSCRIPTIONS_SIMULTANEES), "en_attente": 0, "compteur": threading.Lock()}
SEUIL_DETECTION = 0.7        # en dessous, « tiny » hésite : « small » cherche la langue lui-même
SEUIL_LANGUE_ETRANGERE = 0.6  # « tiny » sûr d'une langue que le chatbot ne gère pas -> on le dit au lieu d'écrire n'importe quoi


def modele_whisper(nom):
    """Dossier du modèle Whisper `nom` (tiny, small...) installé par manage.py installer_modeles_ia (modeles/whisper/<nom>) ;
    sinon le nom seul : faster-whisper le télécharge alors une fois (modeles/whisper/hf)."""
    d = DOSSIER_WHISPER / nom
    return str(d) if (d / "model.bin").exists() else nom


def whisper():
    """Charge les 2 modèles Whisper une seule fois (quelques secondes ; appelé au démarrage du serveur)."""
    with _whisper["verrou"]:
        if _whisper["modele"] is None:
            import os
            from faster_whisper import WhisperModel
            # 2 transcriptions en parallèle : chacune a la moitié des cœurs du processeur
            fils = max(2, (os.cpu_count() or 4) // TRANSCRIPTIONS_SIMULTANEES)
            _whisper["detecteur"] = WhisperModel(modele_whisper("tiny"), device="cpu", compute_type="int8", cpu_threads=fils,
                                                 num_workers=TRANSCRIPTIONS_SIMULTANEES, download_root=str(DOSSIER_WHISPER / "hf"))
            _whisper["modele"] = WhisperModel(modele_whisper(CONFIG["MODELE_WHISPER"]), device="cpu", compute_type="int8",
                                              cpu_threads=fils, num_workers=TRANSCRIPTIONS_SIMULTANEES,
                                              download_root=str(DOSSIER_WHISPER / "hf"))
        return _whisper["modele"]


SEUIL_DOUTE = 0.75           # mot dioula entendu avec moins de certitude : signalé à DeepSeek et à la page


def _whisper_texte(audio, langue, annulation=None, vad=True):
    """Transcription par Whisper « small » (langue connue ou None). Renvoie (texte, langue, certitude). `annulation`
    (dioula_ecoute.Annulation) : arrêtée entre deux passages si elle ne sert plus. `vad=False` : sans le filtre de
    silence de Whisper (il efface parfois un « Oui » dit seul)."""
    from .dioula_ecoute import Annulee
    segments, info = _whisper["modele"].transcribe(audio, language=langue, beam_size=1, vad_filter=vad,
                                                   without_timestamps=True, condition_on_previous_text=False)
    morceaux = []
    for s in segments:                                # les passages sont calculés un à un, pendant cette boucle
        if annulation is not None and annulation.annulee:
            raise Annulee()
        if s.no_speech_prob < 0.6 and not FANTOMES.search(s.text):
            morceaux.append(s)
    texte = " ".join(s.text.strip() for s in morceaux).strip()
    if langue is None:
        return texte, info.language, float(info.language_probability)
    return texte, langue, 1.0


def _whisper_transcrire(octets, langue):
    """Chemin de l'étape 1 (sans dioula), gardé pour comparaison. Renvoie (texte, langue, certitude, prise_en_charge)."""
    from faster_whisper.audio import decode_audio
    whisper()
    audio = decode_audio(io.BytesIO(octets))
    certitude = 1.0
    if not langue:
        langue, certitude, _ = _whisper["detecteur"].detect_language(audio)
        if langue not in langues.LANGUES and certitude >= SEUIL_LANGUE_ETRANGERE:
            return "", langue, float(certitude), False
        if langue not in langues.LANGUES or certitude < SEUIL_DETECTION:
            langue = None
    cherche_par_small = langue is None
    texte, langue, c2 = _whisper_texte(audio, langue)
    if langue not in langues.LANGUES:
        return "", langue, float(c2), False
    return texte, langue, float(c2 if cherche_par_small else certitude), True


def _pas_de_parole(details):
    """Bruit pris pour de la parole : moins de 3 lettres ET certitude < 0,5 (mesuré : bruit blanc -> « e » à 0,29 ;
    vraies réponses courtes « at », « ayi... » : 0,47 à 0,98)."""
    lettres = re.sub(r"[\W\d_]", "", details.get("texte") or "")
    return len(lettres) < 3 and details.get("certitude", 0) < 0.5


def _oreille(langue):
    """Modèle d'écoute d'une langue locale : dioula (Omnilingual 1B) ou baoulé (Omnilingual 300M baoulé)."""
    from . import baoule_ecoute, dioula_ecoute
    return baoule_ecoute if langue == "bci" else dioula_ecoute


def _details_dioula(ecoute, session, langue="dyu"):
    """Répare le texte entendu et garde les détails pour le message qui suit (dioula ou baoulé)."""
    from . import baoule_texte, dioula_texte, service_dioula
    t = time.time()
    repare, faits = (baoule_texte if langue == "bci" else dioula_texte).reparer(ecoute)
    d = {"texte": repare, "brut": ecoute.texte, "repare": repare, "reparations": faits,
         "douteux": [m["mot"] for m in ecoute.mots if m["certitude"] < SEUIL_DOUTE], "certitude": ecoute.certitude,
         "ecoute_s": ecoute.duree_calcul_s, "reparation_s": round(time.time() - t, 3)}
    if session:
        service_dioula.memoriser_vocal(session, d)
    return d


_ecoute = {"pool": None}


def _pool_ecoute():
    if _ecoute["pool"] is None:
        from concurrent.futures import ThreadPoolExecutor
        _ecoute["pool"] = ThreadPoolExecutor(max_workers=TRANSCRIPTIONS_SIMULTANEES, thread_name_prefix="ecoute")
    return _ecoute["pool"]


# ── Dioula : écouter PENDANT que la personne parle ─────────────────────────────
# Mesuré le 29/09/2026 sur des vocaux de 25-35 s : écoutés d'un bloc à la fin, 10 à 16 s d'attente ; écoutés phrase par
# phrase pendant qu'on parle (l'écoute va 2 fois plus vite que la parole), il ne reste à la fin que le dernier morceau
# (1 à 2 s). La page envoie chaque morceau à une pause ; à la fin, elle envoie TOUT le vocal et le nombre de morceaux
# déjà envoyés : on réutilise ceux qui sont prêts et on n'écoute que la suite. Au moindre doute, on réécoute tout.
MORCEAU_VOCAL_MAX_S = 15
MORCEAUX_MAX = 12
MORCEAUX_DUREE_VIE_S = 180
ATTENTE_MORCEAUX_S = 20
MORCEAUX_EN_ATTENTE_MAX = 6          # morceaux pas encore écoutés, tous clients confondus
SESSIONS_MORCEAUX_MAX = 100          # conversations dont on garde des morceaux en réserve
_morceaux = {"sessions": {}, "verrou": threading.Lock()}


def ecouter_morceau(octets, session, rang, langue="dyu", langue_conversation=None, parle=None):
    """Reçoit un morceau de vocal pendant l'enregistrement et lance son écoute en arrière-plan : dioula ou baoulé (langue
    connue), ou « auto » (19/10/2026 : langue pas encore connue, voir _taches_auto)."""
    from faster_whisper.audio import decode_audio
    langue = langue if langue in ("bci", "auto") else "dyu"
    d = verifier_audio(octets)
    if d > MORCEAU_VOCAL_MAX_S + 1:
        raise ErreurVoix(f"Morceau trop long (maximum {MORCEAU_VOCAL_MAX_S} s).")
    if not 0 <= rang < MORCEAUX_MAX:
        raise ErreurVoix("Trop de morceaux pour un seul vocal.")
    audio = decode_audio(io.BytesIO(octets))
    if langue == "bci":
        # GPU payant réveillé seulement pour un VRAI morceau de vocal (audit du 09/10/2026 : un faux fichier le réveillait),
        # et le plus tôt possible : la personne parle encore
        reveiller_voix_baoule("vocal baoulé en cours")
    with _morceaux["verrou"]:
        maintenant = time.time()
        for s in [s for s, v in _morceaux["sessions"].items() if maintenant - v["t"] > MORCEAUX_DUREE_VIE_S]:
            _morceaux["sessions"].pop(s, None)
        # bornes (vu le 29/09/2026 : 30 morceaux envoyés d'un coup étaient tous acceptés -> minutes de calcul en file) :
        # au-delà, « occupé » ; la page enverra alors simplement le vocal entier à la fin (file d'attente normale, bornée)
        en_attente = sum(1 for v in _morceaux["sessions"].values() for _, f in v["liste"].values() if not f.done())
        if en_attente >= MORCEAUX_EN_ATTENTE_MAX:
            raise ServeurOccupe("Beaucoup de vocaux en cours : ce morceau sera écouté avec la fin du vocal.")
        if session not in _morceaux["sessions"] and len(_morceaux["sessions"]) >= SESSIONS_MORCEAUX_MAX:
            plus_vieille = min(_morceaux["sessions"], key=lambda s: _morceaux["sessions"][s]["t"])
            _morceaux["sessions"].pop(plus_vieille, None)
        v = _morceaux["sessions"].setdefault(session, {"t": maintenant, "liste": {}, "langue": langue})
        if rang == 0 or v.get("langue") != langue:        # nouveau vocal : on oublie les morceaux d'un vocal précédent
            v["liste"].clear()
            v["langue"] = langue
            v.pop("verrou", None); v.pop("audios", None); v.pop("whisper_debut", None)
        v["t"] = maintenant
        if langue == "auto":
            v["conv"] = langue_conversation
            if parle and rang == 0:                       # langue directe déclarée : Whisper dans cette langue, sans chercher
                v["verrou"] = f"w:{parle}"
            v.setdefault("audios", {})[rang] = audio
            v["liste"][rang] = (len(audio), _taches_auto(v, audio, rang))
            verrou = _verrou_auto(v)
        else:
            v["liste"][rang] = (len(audio), _pool_ecoute().submit(_oreille(langue).transcrire_audio, audio))
            verrou = langue
    if langue == "auto" and verrou == "bci":
        reveiller_voix_baoule("vocal baoulé reconnu pendant la parole")
    return {"rang": rang, "duree_s": round(d, 2), **({"langue": verrou} if langue == "auto" and verrou else {})}


# ── Mode Automatique : écouter PENDANT la parole, avant de connaître la langue (19/10/2026) ─────────────────────────
# Avant : en Automatique, rien n'était écouté avant la fin du vocal, puis Whisper tiny, l'oreille dioula et l'oreille
# baoulé passaient L'UNE APRÈS L'AUTRE (mesuré : 7,1 s de calcul pour 7,5 s de baoulé). Maintenant, chaque morceau
# envoyé à une pause est écouté tout de suite, pendant que la personne parle encore (le processeur est libre) :
#   1. Whisper tiny d'abord (0,3 s) : s'il est SÛR d'une langue directe (mêmes seuils que dioula_routage), Whisper small
#      transcrit le morceau tout de suite et la langue est verrouillée pour la suite du vocal ;
#   2. sinon les deux oreilles (dioula, baoulé) écoutent le morceau EN MÊME TEMPS ;
#   3. dioula ou baoulé ne sont verrouillés qu'après DEUX morceaux qui donnent une décision nette (banc réel du
#      19/10/2026 : sur un seul morceau de 2,5 à 4 s, 3 vocaux sur 12 étaient verrouillés dans la mauvaise langue) ; sinon
#      la décision habituelle se prend à la fin, sur TOUT le texte déjà écouté.
# À la fin, il ne reste que le dernier bout de vocal à écouter ; au moindre doute (morceau manquant, incohérent), on
# réécoute tout comme avant.
_pool_auto = {"pool": None, "oreilles": None}
MORCEAUX_POUR_VERROU_LOCAL = 2


def _pool_morceaux_auto():
    if _pool_auto["pool"] is None:
        from concurrent.futures import ThreadPoolExecutor
        _pool_auto["pool"] = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ecoute-auto")
        _pool_auto["oreilles"] = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oreilles-auto")
    return _pool_auto["pool"]


def _probs_tiny(audio):
    whisper()
    _, _, toutes = _whisper["detecteur"].detect_language(audio)
    return {k: float(v) for k, v in toutes if v >= 1e-4}


def _moyenne_probs(liste):
    """Probabilités de langue de plusieurs morceaux, pondérées par leur durée : [(nb d'échantillons, probs)]."""
    total = sum(n for n, _ in liste) or 1
    out = {}
    for n, p in liste:
        for k, x in p.items():
            out[k] = out.get(k, 0.0) + x * n / total
    return out


def _whisper_sur(probs, langue_conversation):
    """Langue directe dont Whisper tiny est SÛR (mêmes seuils que dioula_routage.decider), sinon None."""
    from . import dioula_routage
    top = max(probs, key=probs.get) if probs else None
    if top not in langues.LANGUES:
        return None
    seuil = dioula_routage.SEUIL_SUR_FR_EN if top in ("fr", "en") else dioula_routage.SEUIL_SUR_AUTRES
    if langue_conversation in ("dyu", "bci"):
        seuil = max(seuil, dioula_routage.SEUIL_CHANGER_DEPUIS_DIOULA)
    return top if probs[top] >= seuil else None


SEUIL_ESSAI_WHISPER = 0.05     # tiny pas sûr, mais une langue directe garde au moins cette probabilité : essai Whisper


def _candidat_whisper(probs, langue_conversation):
    """Langue directe à transcrire « au cas où » par Whisper small quand tiny n'est pas sûr (19/10/2026 : vocal français
    à l'accent ivoirien, tiny à 0,11 -> les deux oreilles locales écoutaient, puis Whisper transcrivait TOUT le vocal
    après la fin : 7,3 s d'attente). La langue entendue au vocal d'avant si elle est directe, sinon le français ou
    l'anglais s'il n'est pas négligeable : quand tiny hésite sur un accent ivoirien, sa 1re langue est souvent sans
    rapport (japonais, gallois...), alors que les clients parlent français, anglais, dioula ou baoulé."""
    if langue_conversation in langues.LANGUES:
        return langue_conversation
    probs = probs or {}
    lg = max(("fr", "en"), key=lambda k: probs.get(k, 0.0))
    return lg if probs.get(lg, 0.0) >= SEUIL_ESSAI_WHISPER else None


def _ecouter_morceau_auto(audio, verrou, langue_conversation):
    """Un morceau en mode Automatique. Renvoie {"tiny", "dyu", "bci", "whisper", "whisper_langue", "whisper_essai"} (ce
    qui a été fait ; « whisper_essai » = (transcription, langue) faite au cas où, quand tiny n'était pas sûr)."""
    from . import baoule_ecoute
    if verrou in ("dyu", "bci"):
        return {verrou: _oreille(verrou).transcrire_audio(audio)}
    if verrou:
        return {"whisper": _whisper_texte(audio, verrou[2:])}
    probs = _probs_tiny(audio)
    sur = _whisper_sur(probs, langue_conversation)
    if sur:                                               # français, anglais... net : Whisper transcrit tout de suite
        return {"tiny": probs, "whisper": _whisper_texte(audio, sur), "whisper_langue": sur}
    oreilles = _pool_auto["oreilles"]
    fd = oreilles.submit(_oreille("dyu").transcrire_audio, audio)
    fb = oreilles.submit(_oreille("bci").transcrire_audio, audio) if baoule_ecoute.disponible() else None
    candidat = _candidat_whisper(probs, langue_conversation)
    fw = oreilles.submit(_whisper_texte, audio, candidat) if candidat else None
    out = {"tiny": probs, "dyu": fd.result()}
    if fb is not None:
        out["bci"] = fb.result()
    if fw is not None:
        try:
            out["whisper_essai"] = (fw.result(), candidat)
        except Exception:                                 # l'essai ne sert qu'à gagner du temps : sans lui, comme avant
            pass
    return out


def _verrou_de(dec):
    """Une décision NETTE pour le dioula ou le baoulé : « dyu » / « bci » ; sinon None."""
    raison = dec.get("raison", "")
    if dec["chemin"] == "omni" and raison.startswith("texte dioula"):
        return "dyu"
    if dec["chemin"] == "baoule" and (raison.startswith("mots baoulé") or raison.startswith("conversation en baoulé, lecture")):
        return "bci"
    return None


def _verrou_auto(v):
    """Langue verrouillée du vocal, d'après les morceaux déjà écoutés (dans l'ordre), ou None :
    « w:<code> » dès qu'un morceau a été reconnu par Whisper ; « dyu » / « bci » après 2 morceaux d'accord."""
    from . import dioula_ecoute, dioula_routage
    if v.get("verrou"):
        return v["verrou"]
    faits = []
    for r in sorted(v["liste"]):
        n, f = v["liste"][r]
        if not f.done() or f.exception() is not None:
            break
        res = f.result()
        if res.get("whisper_langue"):
            v["verrou"] = f"w:{res['whisper_langue']}"
            return v["verrou"]
        if "dyu" not in res:
            break
        faits.append((n, res))
    if len(faits) < MORCEAUX_POUR_VERROU_LOCAL:
        return None
    probs = _moyenne_probs([(n, res["tiny"]) for n, res in faits])
    e = dioula_ecoute.fusionner([res["dyu"] for _, res in faits])
    b = dioula_ecoute.fusionner([res["bci"] for _, res in faits]) if all("bci" in res for _, res in faits) else None
    dec = dioula_routage.decider(probs, lambda: (e.texte, e.texte_libre), v.get("conv"),
                                 lire_baoule=(lambda: b.texte) if b is not None else None)
    v["verrou"] = _verrou_de(dec)
    return v["verrou"]


def _taches_auto(v, audio, rang):
    """Lance l'écoute d'un morceau (selon la langue déjà verrouillée) ; si Whisper vient d'être verrouillé, le début du
    vocal écouté par les oreilles locales passe aussi à Whisper. Renvoie le Future du morceau."""
    pool = _pool_morceaux_auto()
    verrou = _verrou_auto(v)
    if verrou and verrou.startswith("w:") and "whisper_debut" not in v:
        sans = [r for r in sorted(v["liste"]) if r < rang and v["liste"][r][1].done()
                and "whisper" not in (v["liste"][r][1].result() or {})]
        if sans and sans == list(range(len(sans))):       # un début contigu écouté par les oreilles locales
            import numpy as np
            debut = np.concatenate([v["audios"][r] for r in sans])
            v["whisper_debut"] = (sans, pool.submit(_whisper_texte, debut, verrou[2:]))
    return pool.submit(_ecouter_morceau_auto, audio, verrou, v.get("conv"))


def _resultat_local(lg, ecoutes, session, probs, routage, temps):
    """Résultat d'un vocal dioula ou baoulé écouté par morceaux."""
    from . import dioula_ecoute
    d = _details_dioula(dioula_ecoute.fusionner(ecoutes), session, lg)
    top = max(probs, key=probs.get) if probs else None
    if _pas_de_parole(d):
        return {"texte": "", "langue": "", "certitude": 0.0, "prise": True, "moteur": MOTEURS_ECOUTE[lg],
                "routage": {**routage, "chemin": "silence", "raison": "bruit : texte trop court et incertain"}, "temps": temps}
    return {"texte": d["texte"], "langue": lg, "certitude": probs.get(top, 0.0) if top else 1.0, "prise": True,
            "moteur": MOTEURS_ECOUTE[lg], ("baoule" if lg == "bci" else "dioula"): d, "routage": routage, "temps": temps}


def _transcrire_auto_morceaux(audio, session, deja, langue_conversation, temps):
    """Fin d'un vocal en mode Automatique dont les morceaux ont été écoutés pendant la parole. Renvoie le résultat, ou
    None (morceaux manquants ou incohérents) : le vocal est alors réécouté en entier, comme avant."""
    import numpy as np
    from . import baoule_ecoute, dioula_ecoute
    with _morceaux["verrou"]:
        v = _morceaux["sessions"].get(session)
        if not v or v.get("langue") != "auto":
            return None
        _morceaux["sessions"].pop(session, None)
    if sorted(v["liste"]) != list(range(deja)):
        return None
    t = time.time()
    try:
        res = [v["liste"][r][1].result(timeout=ATTENTE_MORCEAUX_S) for r in range(deja)]
    except Exception:
        return None
    pos = sum(v["liste"][r][0] for r in range(deja))
    if pos > len(audio) + 1600:
        return None
    temps["morceaux_reutilises"] = deja
    v["conv"] = langue_conversation
    reste = audio[pos:] if len(audio) - pos > int(0.3 * 16000) else None
    if reste is not None:                                 # le dernier bout, écouté comme un morceau de plus
        v["audios"][deja] = reste
        v["liste"][deja] = (len(reste), _taches_auto(v, reste, deja))
        try:
            res.append(v["liste"][deja][1].result(timeout=ATTENTE_MORCEAUX_S))
        except Exception:
            return None
    verrou = _verrou_auto(v)
    temps["fin_s"] = round(time.time() - t, 2)
    temps["langue_verrouillee"] = verrou
    probs = _moyenne_probs([(v["liste"][r][0], x["tiny"]) for r, x in enumerate(res) if "tiny" in x])
    routage = {"chemin": None, "raison": "langue reconnue pendant la parole"}
    if verrou in ("dyu", "bci"):
        if not all(verrou in x for x in res):
            return None
        routage["chemin"] = "baoule" if verrou == "bci" else "omni"
        if verrou == "bci":
            reveiller_voix_baoule("vocal entendu en baoulé")
        return _resultat_local(verrou, [x[verrou] for x in res], session, probs, routage, temps)
    if verrou:
        lg = verrou[2:]
        sans = [r for r, x in enumerate(res) if "whisper" not in x]
        textes = {r: x["whisper"][0] for r, x in enumerate(res) if "whisper" in x}
        if sans:
            if "whisper_debut" in v and v["whisper_debut"][0] == sans:
                textes[sans[0]] = v["whisper_debut"][1].result(timeout=ATTENTE_MORCEAUX_S)[0]
            elif sans == list(range(len(sans))):
                textes[0] = _whisper_texte(np.concatenate([v["audios"][r] for r in sans]), lg)[0]
            else:                                         # trous au milieu : on retranscrit tout le vocal
                textes = {0: _whisper_texte(audio, lg)[0]}
        temps["fin_s"] = round(time.time() - t, 2)
        routage["chemin"] = "whisper"
        return {"texte": " ".join(textes[r] for r in sorted(textes) if textes[r]).strip(), "langue": lg,
                "certitude": probs.get(lg, 0.0), "prise": True, "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}",
                "routage": routage, "temps": temps}
    # pas de verrou : la décision habituelle, sur des écoutes DÉJÀ faites de tout le vocal (rien n'est réécouté)
    pretes = _Anticipees()
    for lg in ("dyu", "bci"):
        if all(lg in x for x in res):
            pretes.deja_pret(lg, dioula_ecoute.fusionner([x[lg] for x in res]))
    essais = [x.get("whisper_essai") for x in res]
    if essais and all(essais) and len({lg for _, lg in essais}) == 1:
        # Whisper a déjà transcrit tout le vocal pendant la parole, dans la langue qu'il croyait la plus probable :
        # si la décision donne cette langue, ce texte sert tel quel (19/10/2026)
        lg = essais[0][1]
        pretes.deja_pret("whisper", (" ".join(t[0] for t, _ in essais if t[0]).strip(), lg, 1.0))
        pretes.langue_whisper = lg
        temps["whisper_pendant_parole"] = lg
    return _transcrire_auto(audio, langue_conversation, session, 0, temps, t, baoule_ecoute.disponible(), pretes,
                            probs=probs)


def _langue_des_morceaux(session):
    """Langue (dioula / baoulé) des morceaux déjà écoutés pendant la parole, ou None."""
    with _morceaux["verrou"]:
        v = _morceaux["sessions"].get(session)
        return v.get("langue", "dyu") if v else None


def _reprendre_morceaux(session, deja, audio, langue="dyu"):
    """Écoute du vocal complet à partir des morceaux déjà écoutés (ou None : on réécoutera tout)."""
    from . import dioula_ecoute
    if not session or not deja:
        return None
    with _morceaux["verrou"]:
        v = _morceaux["sessions"].pop(session, None)
    if not v or sorted(v["liste"]) != list(range(deja)) or v.get("langue", "dyu") != langue:
        return None                                       # morceau manquant, en trop ou d'une autre langue : on réécoute
    ecoutes, pos = [], 0
    try:
        for r in range(deja):
            n, tache = v["liste"][r]
            ecoutes.append(tache.result(timeout=ATTENTE_MORCEAUX_S))
            pos += n
    except Exception:
        return None
    if pos > len(audio) + 1600:                            # les morceaux dépassent le vocal complet : incohérent
        return None
    reste = audio[pos:]
    if len(reste) > int(0.3 * 16000):
        ecoutes.append(_oreille(langue).transcrire_audio(reste))
    return dioula_ecoute.fusionner(ecoutes)


MOTEURS_ECOUTE = {"dyu": "omnilingual-1b (serveur)", "bci": "omniasr-300m-baoule (serveur)"}
SEUIL_ANTICIPER_WHISPER = 0.35        # vrais vocaux dioula : fr/en max p90 = 0,10 ; baoulé : médiane 0,08
SEUIL_SUR_FR_EN_ROUTAGE = 0.90        # au-dessus, Whisper est sûr : chemin direct, rien à anticiper


def transcrire_serveur(octets, langue=None, langue_conversation=None, session=None, deja=0, forcer=False):
    """Moteur complet : dioula imposé -> Omnilingual ; autre langue imposée -> Whisper ; « auto » -> Whisper tiny,
    puis si besoin Omnilingual + lecture de son texte (dioula_routage). Renvoie un dictionnaire (voir transcrire)."""
    from faster_whisper.audio import decode_audio
    from . import baoule_ecoute, dioula_ecoute, dioula_routage
    if "bci" in (langue, langue_conversation):
        reveiller_voix_baoule("vocal probablement en baoulé")
    audio = decode_audio(io.BytesIO(octets))
    temps = {}
    if langue in ("dyu", "bci") and not deja and not forcer:
        # le menu fixe la langue des RÉPONSES, pas celle qu'on parle : Whisper « tiny » vérifie d'abord (0,3 s) si la
        # personne parle nettement français, anglais... Bug vu le 30/09/2026 : menu Baoulé + phrase dite en français ->
        # l'oreille baoulé écoutait le français (lent, texte déformé).
        whisper()
        t = time.time()
        _, _, toutes = _whisper["detecteur"].detect_language(audio)
        temps["detection_s"] = round(time.time() - t, 2)
        probs = {k: float(v) for k, v in toutes if v >= 1e-4}
        top = max(probs, key=probs.get) if probs else None
        from . import dioula_routage
        seuil = dioula_routage.SEUIL_SUR_FR_EN if top in ("fr", "en") else dioula_routage.SEUIL_SUR_AUTRES
        if top in langues.LANGUES and probs[top] >= max(seuil, dioula_routage.SEUIL_CHANGER_DEPUIS_DIOULA):
            t = time.time()
            texte, lg, _ = _whisper_texte(audio, top)
            temps["whisper_s"] = round(time.time() - t, 2)
            return {"texte": texte, "langue": lg, "certitude": probs[top], "prise": True,
                    "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}", "temps": temps,
                    "routage": {"chemin": "menu-whisper", "raison": f"menu {langue}, mais Whisper sûr : {top} à {probs[top]:.2f} "
                                                                    "(la réponse reste dans la langue du menu)"}}
    if langue in ("dyu", "bci"):                          # langue locale choisie dans le menu : son oreille, directement
        t = time.time()
        e = _reprendre_morceaux(session, deja, audio, langue)
        if e is not None:
            temps["morceaux_reutilises"] = deja
        else:
            e = _oreille(langue).transcrire_audio(audio)
        temps["ecoute_baoule_s" if langue == "bci" else "ecoute_dioula_s"] = round(time.time() - t, 2)
        d = _details_dioula(e, session, langue)
        if _pas_de_parole(d):
            d["texte"] = ""
        nom = "baoulé" if langue == "bci" else "dioula"
        return {"texte": d["texte"], "langue": langue, "certitude": 1.0, "prise": True, "moteur": MOTEURS_ECOUTE[langue],
                ("baoule" if langue == "bci" else "dioula"): d, "routage": {"chemin": "menu", "raison": f"{nom} choisi dans le menu"},
                "temps": temps}
    whisper()
    if langue and deja and session:                       # langue directe déclarée, écoutée pendant la parole (19/10/2026)
        r = _transcrire_auto_morceaux(audio, session, deja, langue_conversation, temps)
        if r is not None:
            return r
    if langue:                                            # autre langue imposée par le menu : étape 1 inchangée
        t = time.time()
        texte, lg, c = _whisper_texte(audio, langue)
        temps["whisper_s"] = round(time.time() - t, 2)
        return {"texte": texte, "langue": lg, "certitude": c, "prise": True, "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}",
                "routage": {"chemin": "menu"}, "temps": temps}
    t = time.time()
    if deja and session:                                  # vocal écouté pendant la parole (Automatique, 19/10/2026)
        r = _transcrire_auto_morceaux(audio, session, deja, langue_conversation, temps)
        if r is not None:
            return r
        temps.pop("morceaux_reutilises", None)
        t = time.time()
    # conversation déjà en langue locale : le vocal suivant l'est très probablement -> son oreille écoute PENDANT que
    # Whisper cherche la langue (0,35 s de gagnés) ; si Whisper entend nettement une autre langue, elle est ARRÊTÉE
    avec_baoule = baoule_ecoute.disponible()
    anticipe = _Anticipees()
    try:
        if langue_conversation in ("dyu", "bci") and not deja and (langue_conversation == "dyu" or avec_baoule):
            anticipe.lancer(langue_conversation, _oreille(langue_conversation).transcrire_audio, audio, True)
        return _transcrire_auto(audio, langue_conversation, session, deja, temps, t, avec_baoule, anticipe)
    finally:
        anticipe.arreter()                                 # ce qui tourne encore ne sert plus : arrêté


class _Anticipees:
    """Écoutes lancées « au cas où » (nom -> (tâche, annulation)), ARRÊTÉES dès qu'elles ne servent plus, même en plein
    calcul (audit du 09/10/2026 : elles allaient jusqu'au bout, +60 % de calcul pour un vocal français dans une
    conversation en dioula, et tout le serveur ralentissait)."""

    def __init__(self):
        self.taches = {}
        self.langue_whisper = None          # langue de la transcription Whisper déjà faite pendant la parole

    def lancer(self, nom, fonction, *args):
        from .dioula_ecoute import Annulation
        a = Annulation()
        self.taches[nom] = (_pool_ecoute().submit(fonction, *args, annulation=a), a)

    def deja_pret(self, nom, resultat):
        """Une écoute déjà faite (vocal écouté pendant la parole) : servie comme une écoute anticipée terminée."""
        from concurrent.futures import Future
        from .dioula_ecoute import Annulation
        f = Future()
        f.set_result(resultat)
        self.taches[nom] = (f, Annulation())

    def __contains__(self, nom):
        return nom in self.taches

    def resultat(self, nom):
        return self.taches[nom][0].result()

    def arreter(self, *noms):
        """Arrête les écoutes nommées (toutes si aucun nom) : pas encore commencée -> ne démarre pas ; en cours -> stoppée."""
        for nom in (noms or list(self.taches)):
            if nom in self.taches:
                tache, annulation = self.taches.pop(nom)
                tache.cancel()
                annulation.annuler()


def _transcrire_auto(audio, langue_conversation, session, deja, temps, t, avec_baoule, anticipe, probs=None):
    """Mode Automatique : Whisper tiny cherche la langue, puis la décision (dioula_routage) et la transcription.
    `probs` : probabilités déjà calculées pendant la parole (vocal écouté par morceaux)."""
    from . import dioula_routage
    if probs is None:
        _, _, toutes = _whisper["detecteur"].detect_language(audio)
        probs = {k: float(v) for k, v in toutes if v >= 1e-4}
        temps["detection_s"] = round(time.time() - t, 2)
    memo = {}
    langue_morceaux = _langue_des_morceaux(session) if deja else None
    # Whisper sûr d'une langue directe (même seuil que dioula_routage.decider, étape 1) : l'oreille locale lancée au cas
    # où ne servira pas, on l'arrête TOUT DE SUITE (sinon elle prend le processeur pendant que Whisper transcrit)
    top0 = max(probs, key=probs.get) if probs else None
    seuil_sur = max(dioula_routage.SEUIL_SUR_FR_EN if top0 in ("fr", "en") else dioula_routage.SEUIL_SUR_AUTRES,
                    dioula_routage.SEUIL_CHANGER_DEPUIS_DIOULA if langue_conversation in ("dyu", "bci") else 0)
    if top0 in langues.LANGUES and probs[top0] >= seuil_sur:
        anticipe.arreter("dyu", "bci")
    # anglais ou français À L'ACCENT AFRICAIN : Whisper « tiny » hésite (0,4 à 0,7), l'oreille locale vérifie d'abord
    # que ce n'est pas du dioula/baoulé (~1 s), PUIS Whisper transcrivait (~3 s). Mesuré le 30/09/2026 : anglais nigérian
    # 4,4 à 5,5 s contre 3,6 s pour le français. On lance donc la transcription Whisper EN MÊME TEMPS ; si la
    # décision confirme la langue, le texte est déjà prêt, sinon elle est arrêtée.
    seuil0 = SEUIL_SUR_FR_EN_ROUTAGE if top0 in ("fr", "en") else 1.0
    if top0 in ("fr", "en") and SEUIL_ANTICIPER_WHISPER <= probs[top0] < seuil0 and not deja:
        anticipe.lancer("whisper", _whisper_texte, audio, top0)

    def ecouter(lg):
        t1 = time.time()
        e = _reprendre_morceaux(session, deja, audio, lg) if deja and langue_morceaux == lg else None   # pendant la parole
        if e is not None:
            temps["morceaux_reutilises"] = deja
        e = e or (anticipe.resultat(lg) if lg in anticipe else _oreille(lg).transcrire_audio(audio))
        temps["ecoute_baoule_s" if lg == "bci" else "ecoute_dioula_s"] = round(time.time() - t1, 2)
        if lg in anticipe:
            temps["ecoute_anticipee"] = lg
        return e

    def lire_omni():
        memo["e"] = ecouter("dyu")
        return memo["e"].texte, memo["e"].texte_libre

    def lire_baoule():
        try:
            memo["b"] = ecouter("bci")
        except Exception as e:                            # écoute baoulé en panne : le dioula et Whisper continuent
            temps["erreur_baoule"] = str(e)[:120]
            return ""
        return memo["b"].texte

    top = max(probs, key=probs.get) if probs else None
    try:
        dec = dioula_routage.decider(probs, lire_omni, langue_conversation, lire_baoule=lire_baoule if avec_baoule else None)
    except Exception as e:                                # écoute dioula en panne : on retombe sur l'étape 1 (Whisper
        t = time.time()                                   # seul), plutôt que de refuser le vocal à tout le monde
        texte, lg, c = _whisper_texte(audio, top if top in langues.LANGUES and probs[top] >= SEUIL_DETECTION else None)
        temps["whisper_s"] = round(time.time() - t, 2)
        prise = lg in langues.LANGUES
        return {"texte": texte if prise else "", "langue": lg, "certitude": c, "prise": prise,
                "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}", "temps": temps,
                "routage": {"chemin": "secours-whisper", "raison": f"écoute dioula indisponible : {e}"[:160]}}
    routage = {k: v for k, v in dec.items() if k not in ("texte_omni", "texte_baoule")}
    court = _mot_court(audio, dec, langue_conversation, temps)
    if court is not None:
        return {**court, "routage": {**routage, **court["routage"]}, "temps": temps}
    if dec["chemin"] == "baoule" and "b" not in memo:
        # décision « baoulé » sans lecture baoulé (oreille baoulé absente, en panne, ou pas encore lancée) : audit du
        # 09/10/2026, KeyError -> vocal refusé (503). On écoute en baoulé si possible, sinon on passe au dioula.
        if avec_baoule:
            lire_baoule()
        if "b" not in memo:
            if "e" not in memo:
                lire_omni()
            routage = {**routage, "chemin": "omni", "raison": "écoute baoulé indisponible : dioula"}
            dec = {**dec, "chemin": "omni", "langue": "dyu"}
    if dec["chemin"] == "baoule":
        reveiller_voix_baoule("vocal entendu en baoulé")
        d = _details_dioula(memo["b"], session, "bci")
        if _pas_de_parole(d):
            return {"texte": "", "langue": "", "certitude": 0.0, "prise": True, "moteur": MOTEURS_ECOUTE["bci"],
                    "routage": {**routage, "chemin": "silence", "raison": "bruit : texte trop court et incertain"}, "temps": temps}
        return {"texte": d["texte"], "langue": "bci", "certitude": probs.get(top, 0.0), "prise": True,
                "moteur": MOTEURS_ECOUTE["bci"], "baoule": d, "routage": routage, "temps": temps}
    if dec["chemin"] == "omni":
        if "e" not in memo:                               # décision prise sans lecture dioula (ne devrait pas arriver)
            lire_omni()
        d = _details_dioula(memo["e"], session)
        if _pas_de_parole(d):
            return {"texte": "", "langue": "", "certitude": 0.0, "prise": True, "moteur": "omnilingual-1b (serveur)",
                    "routage": {**routage, "chemin": "silence", "raison": "bruit : texte trop court et incertain"}, "temps": temps}
        return {"texte": d["texte"], "langue": "dyu", "certitude": probs.get(top, 0.0), "prise": True,
                "moteur": "omnilingual-1b (serveur)", "dioula": d, "routage": routage, "temps": temps}
    if dec["chemin"] == "silence":
        return {"texte": "", "langue": "", "certitude": 0.0, "prise": True, "moteur": "omnilingual-1b (serveur)",
                "routage": routage, "temps": temps}
    if dec["chemin"] == "non-prise":
        return {"texte": "", "langue": dec.get("langue_entendue") or top, "certitude": probs.get(top, 0.0), "prise": False,
                "moteur": "whisper-tiny", "routage": routage, "temps": temps}
    anticipe.arreter("dyu", "bci")                        # chemin Whisper : les oreilles locales ne servent plus
    t = time.time()
    if "whisper" in anticipe and dec["langue"] == (anticipe.langue_whisper or top0):
        texte, lg, _ = anticipe.resultat("whisper")       # déjà transcrit pendant la vérification
        temps["whisper_anticipe"] = True
    else:
        anticipe.arreter("whisper")                       # transcription anticipée dans une autre langue : arrêtée
        texte, lg, _ = _whisper_texte(audio, dec["langue"])
    temps["whisper_s"] = round(time.time() - t, 2)
    # formule très courte (« non merci », « yes ») reconnue par l'oreille locale, mais effacée par le filtre de silence
    # de Whisper (vu le 30/09/2026 : le vocal finissait en « rien entendu ») : on garde ce que l'oreille a lu
    if not texte and dec["chemin"] == "whisper-force" and dec.get("texte_omni") and "expression courte" in dec.get("raison", ""):
        texte = dec["texte_omni"]
        routage["texte_repris"] = "oreille locale (Whisper n'a rien gardé)"
    return {"texte": texte, "langue": lg, "certitude": probs.get(dec["langue"], 0.0), "prise": True,
            "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}", "routage": routage, "temps": temps}


COURT_S = 1.6                         # vocal plus court : peut-être un simple « oui », « merci », « d'accord »


def _mot_court(audio, dec, langue_conversation, temps):
    """Vocal très court que les oreilles locales n'ont pas su lire (« Oui » -> « w », ou rien) : Whisper, sans son filtre
    de silence, et la liste des formules courtes (19/10/2026 : vu sur de vrais vocaux, « Oui » partait en dioula ou en
    « rien entendu »). Renvoie un résultat, ou None si ce n'est pas le cas."""
    from . import dioula_routage
    if len(audio) / 16000 > COURT_S or dec["chemin"] not in ("omni", "silence", "baoule"):
        return None
    lu = dec.get("texte_omni") or ""
    if len(re.sub(r"[\W\d_]", "", lu)) >= 3 and dec["chemin"] != "silence":
        return None
    t = time.time()
    texte, lg, _ = _whisper_texte(audio, None, vad=False)
    temps["whisper_court_s"] = round(time.time() - t, 2)
    expr = dioula_routage._expression(texte)
    if expr not in langues.LANGUES:
        return None
    locale = langue_conversation if langue_conversation in ("dyu", "bci") else None
    langue = locale if locale and expr in dioula_routage.COURTOISIE_FR_EN else expr
    return {"texte": texte, "langue": langue, "certitude": 1.0, "prise": True, "moteur": f"whisper-{CONFIG['MODELE_WHISPER']}",
            "routage": {"chemin": "court", "raison": f"formule courte « {texte} » ({expr})"
                                                     + (" dans une conversation en langue locale" if langue != expr else "")}}


def _prendre_une_place():
    """File d'attente bornée pour Whisper : au-delà de MAX_EN_ATTENTE, on répond « occupé » tout de suite."""
    with _whisper["compteur"]:
        if _whisper["en_attente"] >= MAX_EN_ATTENTE:
            raise ServeurOccupe("Le serveur transcrit déjà beaucoup de messages : réessayez dans quelques secondes.")
        _whisper["en_attente"] += 1
    try:
        if not _whisper["places"].acquire(timeout=ATTENTE_MAX_S):
            raise ServeurOccupe("Le serveur est très occupé : réessayez dans quelques secondes.")
    finally:
        with _whisper["compteur"]:
            _whisper["en_attente"] -= 1


def transcrire(octets, langue=None, moteur=None, langue_conversation=None, session=None, deja=0, forcer=False):
    """Renvoie {"texte", "langue", "certitude_langue", "parole", "prise_en_charge", "modele", "duree_audio_s", "duree_s",
    "routage", "temps", "dioula"?}. `langue` : code imposé par le menu (ou None = automatique), « dyu » compris.
    `moteur(octets, langue) -> (texte, langue, certitude[, prise_en_charge])` remplace le moteur du serveur (tests)."""
    duree_audio = verifier_audio(octets)
    t0 = time.time()
    _prendre_une_place()
    try:
        if moteur:
            r = moteur(octets, langue)
            r = {"texte": r[0], "langue": r[1], "certitude": r[2], "prise": r[3] if len(r) > 3 else True,
                 "moteur": f"whisper-{CONFIG['MODELE_WHISPER']} (serveur)", "routage": {}, "temps": {}}
        else:
            r = transcrire_serveur(octets, langue, langue_conversation, session, deja, forcer)
    except ErreurVoix:
        raise
    except Exception as e:                    # le détail technique va dans journaux/erreurs.log, jamais à la page
        from . import erreurs
        erreurs.noter("transcription", e)
        raise ErreurVoix("Transcription impossible pour le moment : réessayez dans un instant.")
    finally:
        _whisper["places"].release()
    texte, prise = r["texte"], r["prise"]
    sortie = {"texte": texte if prise else "", "langue": (r["langue"] or "").lower() if (texte or not prise) else "",
              "certitude_langue": round(r["certitude"], 2), "parole": bool(texte) and prise, "prise_en_charge": prise,
              "modele": r["moteur"], "duree_audio_s": round(duree_audio, 2) if duree_audio else None,
              "duree_s": round(time.time() - t0, 2), "routage": r.get("routage", {}), "temps": r.get("temps", {})}
    for cle in ("dioula", "baoule"):                      # ce que l'oreille locale a entendu (affiché sous le vocal)
        if r.get(cle):
            d = r[cle]
            sortie[cle] = {k: d[k] for k in ("brut", "repare", "douteux", "reparations", "certitude")}
    return sortie


# ── Lecture à voix haute ──────────────────────────────────────────────────────
def texte_pour_voix(texte):
    """Retire ce qui ne se lit pas (markdown, émojis) sans toucher au sens."""
    t = re.sub(r"```.*?```", " ", texte or "", flags=re.S)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)          # puces
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)             # titres
    t = re.sub(r"[*_`#>|~]+", "", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", t)
    lignes = [l.strip() for l in t.splitlines() if l.strip()]
    # « , » accepté en fin : un 1er morceau coupé à la virgule doit rester identique quand la page le renvoie
    # (sinon « ...AOCEDA,. » ne correspond plus au morceau autorisé et la voix est refusée : bug vu le 29/09/2026)
    t = " ".join(l if l[-1] in ".!?:;,…。！？" else l + "." for l in lignes)
    return re.sub(r"\s+", " ", t).strip()


PREMIER_MORCEAU_MAX = 60     # 1re phrase plus longue : sa voix est fabriquée en 2 morceaux (coupée à la 1re virgule)


def _couper_a_la_virgule(phrase):
    """« Pour réduire la facture, éteignez le climatiseur » -> 2 morceaux. Le temps d'une voix grandit avec la longueur
    du texte (Djelia : ~2 s pour 5 mots, ~4 s pour 12) : le 1er morceau court se lit pendant que le 2e se fabrique.
    Même résultat sur un début de phrase et sur la phrase finie (la voix préparée tôt reste la bonne)."""
    if len(phrase) <= PREMIER_MORCEAU_MAX:
        return [phrase]
    for m in re.finditer(r"[,;:]\s", phrase):
        if 20 <= m.start() <= len(phrase) - 12:
            return [phrase[:m.start() + 1].strip(), phrase[m.end():].strip()]
    return [phrase]


SALUT_COURT = 25        # 1re phrase de cette longueur au plus (« Bonsoir ! ») : la 2e phrase est lue seule ensuite


def decouper(texte, max_car=320):
    """Découpe en morceaux de phrases entières. Le 1er morceau = la 1re phrase seule (ou son début jusqu'à la 1re
    virgule si elle est longue) : il est connu dès qu'il est écrit, donc sa voix se prépare pendant que la suite de la
    réponse s'écrit. Les suivants : ≤ max_car."""
    phrases = [p.strip() for p in re.split(r"(?<=[.!?…。！？])\s+", texte_pour_voix(texte)) if p.strip()]
    if not phrases:
        return []
    phrases = _couper_a_la_virgule(phrases[0]) + phrases[1:]
    morceaux, courant, reste = [phrases[0]], "", phrases[1:]
    # 19/10/2026 (vu en vrai) : après une 1re phrase très courte (« Bonsoir ! »), tout le reste formait UN long morceau,
    # et la voix se taisait plusieurs secondes après la salutation. La 2e phrase part donc seule, elle aussi.
    if len(phrases[0]) <= SALUT_COURT and reste:
        morceaux += _couper_a_la_virgule(reste[0])
        reste = reste[1:]
    for p in reste:
        if courant and len(courant) + 1 + len(p) > max_car:
            morceaux.append(courant); courant = p
        else:
            courant = f"{courant} {p}".strip()
    if courant:
        morceaux.append(courant)
    return morceaux


def premier_morceau_si_complet(texte_partiel):
    """Pendant l'écriture de la réponse : la 1re phrase, dès qu'elle est sûrement terminée (une 2e a commencé)."""
    m = decouper(texte_partiel)
    return m[0] if len(m) >= 2 else None


# Région préférée par langue (voix la plus comprise) ; le reste est choisi automatiquement
REGION = {"fr": "fr-FR", "en": "en-US", "es": "es-ES", "pt": "pt-BR", "de": "de-DE", "it": "it-IT", "nl": "nl-NL",
          "ar": "ar-SA", "sw": "sw-KE", "zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR", "hi": "hi-IN", "bn": "bn-IN",
          "ru": "ru-RU", "uk": "uk-UA", "pl": "pl-PL", "tr": "tr-TR", "vi": "vi-VN", "th": "th-TH", "id": "id-ID",
          "ro": "ro-RO", "el": "el-GR", "he": "he-IL", "sv": "sv-SE", "cs": "cs-CZ", "hu": "hu-HU"}
_catalogue = {"voix": None}


def catalogue_voix():
    """Liste des voix Microsoft (mise en cache sur disque : la page n'attend pas Internet)."""
    if _catalogue["voix"] is None:
        f = CACHE / "voix_edge.json"
        if f.exists():
            _catalogue["voix"] = json.loads(f.read_text(encoding="utf-8"))
        else:
            import edge_tts
            v = asyncio.run(edge_tts.list_voices())
            _catalogue["voix"] = [{"nom": x["ShortName"], "region": x["Locale"], "genre": x["Gender"]} for x in v]
            f.write_text(json.dumps(_catalogue["voix"], ensure_ascii=False), encoding="utf-8")
    return _catalogue["voix"]


def choisir_voix(langue, genre="femme"):
    """Voix Microsoft pour cette langue et ce genre : la voix NATIVE d'abord. 19/10/2026 (mesuré par retranscription) :
    la voix « Multilingual » changeait de langue au milieu d'une réponse française (« Bonsoir » lu « Bonne soir », mots
    sautés, chiffres à l'anglaise) et mettait 7 à 13 s au lieu de 3 ; elle ne sert plus que s'il n'y a pas de native."""
    g = "Male" if genre == "homme" else "Female"
    region = REGION.get(langue, "")
    voix = catalogue_voix()
    for filtre in (lambda x: x["region"] == region, lambda x: x["region"].split("-")[0] == langue):
        candidats = [x for x in voix if filtre(x)]
        if candidats:
            candidats.sort(key=lambda x: (x["genre"] != g, "Multilingual" in x["nom"]))
            return candidats[0]["nom"]
    return "fr-FR-DeniseNeural" if g == "Female" else "fr-FR-HenriNeural"


# Ce que la voix française doit DIRE (19/10/2026, retour du client : « kWh », « % », « 14 h », les chiffres étaient mal
# dits, parfois en anglais). Appliqué seulement au texte envoyé à la voix : l'affichage ne change pas.
_PRONONCER_FR = [
    (r"(?<=\d)[\s  ](?=\d{3}\b)", ""),                     # 119 662 -> 119662 (lu « cent dix-neuf mille… »)
    (r"(?<=\d)\s*kWh\b", " kilowattheures"), (r"\bkWh\b", "kilowattheures"),
    (r"(?<=\d)\s*kW\b", " kilowatts"), (r"(?<=\d)\s*W\b", " watts"), (r"(?<=\d)\s*V\b", " volts"),
    (r"(?<=\d)\s*A\b", " ampères"), (r"\bF\s?CFA\b", "francs CFA"), (r"(?<=\d)\s*F\b", " francs"),
    (r"\s*%", " pour cent"),
    (r"\b(\d{1,2})\s*h\s*(\d{2})\b", r"\1 heures \2"), (r"\b(\d{1,2})\s*h\b", r"\1 heures"), (r"\b1 heures\b", "1 heure"),
    (r"\b1er\b", "premier"), (r"\bvs\.?(?=\s)", "contre"), (r"\s[–—]\s", ", "), (r"(?<=\d)\s?[–—-]\s?(?=\d)", " à "),
]


def prononcer(texte, langue):
    """Texte tel que la voix doit le lire (français : unités, heures et grands nombres en toutes lettres)."""
    if langue != "fr":
        return texte
    for motif, remplacement in _PRONONCER_FR:
        texte = re.sub(motif, remplacement, texte)
    return re.sub(r"\s{2,}", " ", texte).strip()


def _edge(texte, voix):
    import edge_tts

    async def lire():
        audio = bytearray()
        async for m in edge_tts.Communicate(texte, voix).stream():
            if m["type"] == "audio":
                audio += m["data"]
        return bytes(audio)
    audio = asyncio.run(asyncio.wait_for(lire(), timeout=20))
    if len(audio) < 1000:
        raise ErreurVoix("voix Microsoft : audio vide")
    return audio


def _djelia_voix(texte):
    """Voix dioula : Djelia (bambara), avec la connexion gardée ouverte du relais."""
    from .dioula_relais import _http
    r = _http.post("https://www.djelia.cloud/api/text-to-speech", json={"text": texte}, timeout=30)
    r.raise_for_status()
    if "audio" not in r.headers.get("content-type", "") or len(r.content) < 1000:
        raise ErreurVoix("voix Djelia : pas d'audio dans la réponse")
    return r.content


_kokoro = {"objet": None, "verrou": threading.Lock()}
KOKORO_VOIX = {("fr", "femme"): ("ff_siwis", "fr-fr"), ("fr", "homme"): ("ff_siwis", "fr-fr"),
               ("en", "femme"): ("af_heart", "en-us"), ("en", "homme"): ("am_michael", "en-us")}


def _kokoro_lire(texte, langue, genre):
    if (langue, genre) not in KOKORO_VOIX or not (DOSSIER_KOKORO / "kokoro-v1.0.onnx").exists():
        raise ErreurVoix("Kokoro : langue non prise en charge")
    import soundfile as sf
    from kokoro_onnx import Kokoro
    with _kokoro["verrou"]:
        if _kokoro["objet"] is None:
            _kokoro["objet"] = Kokoro(str(DOSSIER_KOKORO / "kokoro-v1.0.onnx"), str(DOSSIER_KOKORO / "voices-v1.0.bin"))
        voix, lang = KOKORO_VOIX[(langue, genre)]
        son, taux = _kokoro["objet"].create(texte, voice=voix, speed=1.0, lang=lang)
    tampon = io.BytesIO()
    sf.write(tampon, son, taux, format="WAV")
    return tampon.getvalue()


GENRES = ("femme", "homme")
_atelier = {"pool": None, "en_cours": {}, "verrou": threading.Lock()}


def _pool():
    if _atelier["pool"] is None:
        from concurrent.futures import ThreadPoolExecutor
        _atelier["pool"] = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voix")
    return _atelier["pool"]


VOIX_UNIQUE = ("dyu",)                # une seule voix (le choix Femme/Homme ne s'applique pas) ; baoulé : deux depuis le 18/10/2026
_baoule = {"attente": {}, "echecs": {}, "vu": {}, "verrou": threading.Lock()}   # voix baoulé demandées : clé -> Future
ATTENTE_APRES_ECHEC_S = 120           # une voix baoulé en échec n'est pas relancée avant 2 min
ABANDON_S = 45                        # voix baoulé plus redemandée depuis 45 s (la page redemande toutes les 10 s) : abandonnée


class VoixAbandonnee(Exception):
    """Plus personne n'attend cette voix : on ne la fabrique pas (plusieurs minutes de processeur économisées)."""


def preparer(morceaux, langue=None, genre_prioritaire="femme"):
    """Lance en arrière-plan la fabrication des voix : d'abord TOUS les morceaux dans le genre choisi
    (celui qui sera écouté), ensuite dans l'autre genre (pour un changement Femme/Homme instantané).
    Baoulé : RIEN d'automatique. Une voix baoulé coûte plusieurs minutes de processeur ; elle n'est fabriquée que si
    quelqu'un la demande (bouton Écouter, lecture automatique) : voir demander_baoule. Renvoie les tâches (tests)."""
    if langue == "bci":
        return []
    autre = "homme" if genre_prioritaire == "femme" else "femme"
    genres = (genre_prioritaire,) if langue in VOIX_UNIQUE else (genre_prioritaire, autre)
    return [_pool().submit(obtenir, m, langue, g) for g in genres for m in morceaux]


def voix_baoule_prete(texte, genre="femme"):
    """Voix baoulé déjà fabriquée (sur le disque) dans cette voix : (audio, infos), sinon None."""
    moteur, voix, mime = moteur_baoule(genre)
    f = _fichier_voix(voix, texte_pour_voix(texte), mime)
    if f.exists():
        return f.read_bytes(), {"moteur": moteur, "voix": voix, "mime": mime, "cache": True, "duree_s": 0.0}
    return None


PHRASE_BAOULE_MIN = 15               # phrase plus courte : collée à la suivante (une fabrication de moins)
PHRASE_BAOULE_MAX = 200              # plus longue : coupée à une virgule (OmniVoice se dégrade sur les longs textes)
PAUSE_ENTRE_PHRASES_S = 0.35


def phrases_baoule(texte):
    """Phrases d'une réponse baoulé, fabriquées une par une (qualité), puis assemblées en UN audio continu.
    Audit du 09/10/2026 : une phrase de plus de 200 caractères sans virgule était coupée EN PLEIN MOT (« ni|an ») ; et une
    phrase courte suivie d'une longue n'était pas collée. Maintenant : collage d'abord, puis coupure à une virgule, sinon
    au dernier espace."""
    brutes = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texte_pour_voix(texte)) if p.strip()]
    sortie = []
    for p in brutes:
        if sortie and len(sortie[-1]) < PHRASE_BAOULE_MIN:      # phrase trop courte : collée à la suivante
            p = f"{sortie.pop()} {p}"
        while len(p) > PHRASE_BAOULE_MAX:
            coupes = [m.end() for m in re.finditer(r"[,;:]\s", p) if 30 <= m.end() <= PHRASE_BAOULE_MAX]
            espace = p.rfind(" ", 30, PHRASE_BAOULE_MAX + 1)
            c = coupes[-1] if coupes else espace if espace > 0 else PHRASE_BAOULE_MAX
            sortie.append(p[:c].strip()); p = p[c:].strip()
        if p:
            sortie.append(p)
    return sortie


def _assembler(audios):
    """Colle les voix des phrases (WAV) en un seul WAV, avec une courte pause naturelle entre elles."""
    import numpy as np
    import soundfile as sf
    morceaux, taux = [], None
    for a in audios:
        x, sr = sf.read(io.BytesIO(a), dtype="float32")
        taux = taux or sr
        morceaux += [x, np.zeros(int(PAUSE_ENTRE_PHRASES_S * sr), dtype="float32")]
    tampon = io.BytesIO()
    sf.write(tampon, np.concatenate(morceaux[:-1]) if morceaux else np.zeros(1, dtype="float32"), taux or 24000, format="WAV")
    return tampon.getvalue()


def demander_baoule_reponse(texte, genre="femme"):
    """Voix d'une RÉPONSE baoulé entière, en UN audio continu (bug vu le 30/09/2026 : la page jouait la 1re phrase puis
    attendait la suivante plusieurs minutes, on croyait l'audio coupé). Chaque phrase est fabriquée à part (et gardée
    sur le disque), dans l'ordre ; quand toutes sont prêtes, elles sont assemblées.
    Renvoie (état, Future|None, rang, (phrases prêtes, total)) ; état = prete | preparation | echec."""
    from concurrent.futures import Future
    complet = texte_pour_voix(texte)
    deja = voix_baoule_prete(complet, genre)
    phrases = phrases_baoule(complet)
    if deja:
        f = Future(); f.set_result(deja)
        return "prete", f, 0, (len(phrases), len(phrases))
    annoncer_baoule(complet, genre)                # GPU : toutes les phrases manquantes en UN appel (déjà parti en général)
    etats = [demander_baoule(p, genre) for p in phrases]             # toutes en file, dans l'ordre
    faites = sum(1 for e in etats if e[0] == "prete")
    for e in etats:
        if e[0] == "echec":
            return "echec", e[1], 0, (faites, len(phrases))
    if faites == len(phrases):
        audio = _assembler([e[1].result()[0] for e in etats])
        moteur, voix, mime = moteur_baoule(genre)
        f = _fichier_voix(voix, complet, mime)
        DOSSIER_VOIX.mkdir(parents=True, exist_ok=True)
        f.write_bytes(audio)
        fut = Future(); fut.set_result((audio, {"moteur": moteur, "voix": voix, "mime": mime, "cache": False, "duree_s": 0.0}))
        return "prete", fut, 0, (faites, len(phrases))
    rang = max(e[2] for e in etats if e[0] == "preparation")
    return "preparation", None, rang, (faites, len(phrases))


def reveiller_voix_baoule(raison=""):
    """Réveil ANTICIPÉ du GPU de la voix baoulé (en arrière-plan, sans rien attendre) : une conversation part en baoulé,
    la machine démarre (~35 s) pendant que l'écoute, DeepSeek et Google travaillent. Sans GPU : rien."""
    from . import voix_gpu
    return voix_gpu.reveiller(raison)


def annoncer_baoule(texte, genre="femme"):
    """GPU Cerebrium (06/10/2026) : envoie d'un coup toutes les phrases d'une réponse baoulé qui n'ont pas encore de voix
    (un seul trajet réseau). Appelé dès que la réponse est écrite : quand la page demande la voix, elle est prête ou en
    route. Sans GPU : rien (l'atelier du PC, plusieurs minutes par phrase, ne fabrique que ce qu'on demande)."""
    from . import voix_gpu
    if not voix_gpu.disponible():
        return None
    # même clé que la demande de chaque phrase (demander_baoule -> texte_pour_voix) : sinon le lot ne servait pas et la
    # phrase était fabriquée (et payée) une 2e fois (audit du 09/10/2026)
    manquantes = [texte_pour_voix(p) for p in phrases_baoule(texte_pour_voix(texte)) if not voix_baoule_prete(p, genre)]
    return voix_gpu.annoncer(manquantes, genre) if manquantes else None


def _fabriquer_baoule(cle, genre="femme"):
    """Fabrique la voix, SAUF si plus personne ne l'attend (page fermée, autre question, nouvelle conversation)."""
    if time.time() - _baoule["vu"].get((genre, cle), 0) > ABANDON_S:
        raise VoixAbandonnee(cle)
    return obtenir(cle, "bci", genre)


def demander_baoule(texte, genre="femme"):
    """Voix baoulé d'un morceau : ("prete", Future terminé, 0) si déjà faite ; sinon elle est mise en file (une seule
    fois, même demandée plusieurs fois) et on renvoie ("preparation", Future, rang dans la file).
    Chaque demande prouve que quelqu'un attend encore."""
    from concurrent.futures import Future
    from . import voix_baoule
    genre = "homme" if genre == "homme" else "femme"
    cle = texte_pour_voix(texte)
    pret = voix_baoule_prete(cle, genre)
    if pret:
        f = Future(); f.set_result(pret)
        return "prete", f, 0
    vue = (genre, cle)                          # la même phrase dans les deux voix : deux fabrications distinctes
    with _baoule["verrou"]:
        maintenant = time.time()
        if len(_baoule["vu"]) > 2000 or len(_baoule["echecs"]) > 2000:     # mémoire bornée : on oublie le vieux (> 1 h)
            for d in (_baoule["vu"], _baoule["echecs"]):
                for k in [k for k, t in d.items() if maintenant - t > 3600]:
                    del d[k]
        _baoule["vu"][vue] = max(maintenant, _baoule["vu"].get(vue, 0))
        f = _baoule["attente"].get(vue)
        if f is not None and f.done() and isinstance(f.exception(), VoixAbandonnee):
            f = None                                                   # abandonnée faute d'attente : on reprend
        if f is not None and f.done() and f.exception() is not None:
            # échec récent : on le dit (la page affiche « voix indisponible ») au lieu de relancer à chaque demande
            # (vu le 30/09/2026 : chaque demande de la page relançait l'atelier en panne, 30 min de « préparation »)
            if time.time() - _baoule["echecs"].get(vue, 0) < ATTENTE_APRES_ECHEC_S:
                return "echec", f, 0
            f = None
        if f is None:                                                  # jamais demandée, ou échec ancien : on (re)lance
            f = voix_baoule.soumettre(_fabriquer_baoule, cle, genre)
            _baoule["attente"][vue] = f

            def apres(_f, c=vue):
                e = _f.exception()
                if e is not None and not isinstance(e, VoixAbandonnee):
                    _baoule["echecs"][c] = time.time()
                if e is None or isinstance(e, VoixAbandonnee):         # réussie (sur le disque) ou abandonnée
                    with _baoule["verrou"]:
                        if _baoule["attente"].get(c) is _f:
                            _baoule["attente"].pop(c, None)
            f.add_done_callback(apres)
        rang = sum(1 for x in _baoule["attente"].values() if not x.done())
    return "preparation", f, rang


def obtenir(texte, langue=None, genre="femme"):
    """Comme synthetiser(), mais si la même voix est déjà en fabrication, on attend celle-ci (pas de doublon)."""
    cle = (texte_pour_voix(texte), langue, "unique" if langue in VOIX_UNIQUE else genre)
    with _atelier["verrou"]:
        tache = _atelier["en_cours"].get(cle)
        proprietaire = tache is None
        if proprietaire:
            from concurrent.futures import Future
            tache = _atelier["en_cours"][cle] = Future()
    if not proprietaire:
        return tache.result()
    try:
        r = synthetiser(texte, langue, genre)
        tache.set_result(r)
        return r
    except Exception as e:
        tache.set_exception(e)
        raise
    finally:
        with _atelier["verrou"]:
            _atelier["en_cours"].pop(cle, None)


# « -v3 » (18/10/2026) : deux voix, voix modèles longues + 32 étapes ; les voix de l'ancien réglage (« -v2 » : 8 étapes,
# voix modèle de 2,4 s) ne sont plus resservies. Même réglage sur le GPU Cerebrium et sur le PC : même identifiant.
MOTEURS_BAOULE = {"femme": ("OmniVoice, voix de femme (RK, WAXAL) ; GPU Cerebrium, secours PC", "omnivoice-rk-v3", "audio/wav"),
                  "homme": ("OmniVoice, voix d'homme (Common Voice 566016a2) ; GPU Cerebrium, secours PC",
                            "omnivoice-cv566-v3", "audio/wav")}
MOTEUR_BAOULE = MOTEURS_BAOULE["femme"]


def moteur_baoule(genre="femme"):
    return MOTEURS_BAOULE["homme" if genre == "homme" else "femme"]


def _fichier_voix(voix, texte, mime):
    ext = ".mp3" if "mpeg" in mime else ".m4a" if "mp4" in mime else ".wav"
    return DOSSIER_VOIX / (hashlib.sha1(f"{voix}|{texte}".encode("utf-8")).hexdigest() + ext)


def synthetiser(texte, langue=None, genre="femme", moteurs=None):
    """Renvoie (audio, infos) ; infos = {"moteur", "voix", "mime", "cache", "duree_s"}.
    Lève ErreurVoix si aucune voix du serveur ne marche (la page lit alors avec la voix du navigateur).
    `moteurs` remplace la liste des voix (tests)."""
    texte = texte_pour_voix(texte)
    if not texte:
        raise ErreurVoix("Rien à lire.")
    genre = "homme" if genre == "homme" else "femme"
    if not langue or langue == "auto":
        langue = detection.detecter(texte)[0] or "fr"
    if moteurs is None and langue == "dyu":
        moteurs = [("Djelia (voix bambara)", "djelia-bam", "audio/mp4", lambda: _djelia_voix(texte))]
    if moteurs is None and langue == "bci":
        from . import voix_baoule
        moteurs = [(*moteur_baoule(genre), lambda: voix_baoule.fabriquer(texte, genre))]
    if moteurs is None:
        v = choisir_voix(langue, genre)
        dit = prononcer(texte, langue)                    # « kWh » -> « kilowattheures »… (le texte affiché ne change pas)
        moteurs = [("Microsoft (edge-tts)", v, "audio/mpeg", lambda: _edge(dit, v)),
                   ("Kokoro (serveur)", "kokoro", "audio/wav", lambda: _kokoro_lire(dit, langue, genre))]
    t0, erreurs = time.time(), []
    for moteur, voix, mime, fabriquer in moteurs:
        f = _fichier_voix(voix, texte, mime)
        if f.exists():
            return f.read_bytes(), {"moteur": moteur, "voix": voix, "mime": mime, "cache": True, "duree_s": 0.0}
        try:
            audio = fabriquer()
        except Exception as e:
            erreurs.append(f"{moteur} : {e}"[:120])
            continue
        DOSSIER_VOIX.mkdir(parents=True, exist_ok=True)
        f.write_bytes(audio)
        return audio, {"moteur": moteur, "voix": voix, "mime": mime, "cache": False, "duree_s": round(time.time() - t0, 2),
                       "erreurs": erreurs}
    raise ErreurVoix("Voix du serveur indisponible : " + " ; ".join(erreurs))
