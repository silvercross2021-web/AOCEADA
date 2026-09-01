"""Assistant IA en dioula — compréhension vocale (STT) + traduction/voix (TTS).

Architecture validée empiriquement (voir recherche du mémoire) :
  audio dioula -> STT (Meta MMS, quantifié ONNX, auto-hébergé)
               -> transcription dioula (imparfaite, surtout sur noms propres/sigles)
               -> LLM = LA MÊME boucle outils/function-calling que le chat FR/EN
                  (AIChatView._boucle_llm), avec un system prompt augmenté qui explique
                  les erreurs typiques de la transcription — le LLM répond en FRANÇAIS,
                  jamais directement en dioula (testé : un LLM généraliste ne comprend/
                  écrit PAS le dioula de façon fiable, voir la classification qui partait
                  sur "prix de la nourriture" sans ce garde-fou)
               -> traduction français -> dioula + voix (LAMIA, LAfricaMobile)

Aucune étape n'invente une donnée : les chiffres viennent toujours du même pipeline
outils que le chat français (voir outils.py), seule la langue de surface change.
"""
import base64
import concurrent.futures
import html
import io
import logging
import re
import threading

import requests  # pyrefly: ignore [untyped-import]
from django.conf import settings  # pyrefly: ignore [untyped-import]

logger = logging.getLogger(__name__)

# ── STT : Meta MMS quantifié (ONNX), chargé UNE SEULE FOIS par processus ──────
_stt_processor = None
_stt_model = None
_stt_lock = threading.Lock()


def stt_disponible():
    return settings.AI_DIOULA_STT_MODEL_DIR.exists()


def _charger_stt():
    global _stt_processor, _stt_model
    if _stt_model is not None:
        return _stt_processor, _stt_model
    with _stt_lock:
        if _stt_model is not None:  # un autre thread a pu charger pendant l'attente du verrou
            return _stt_processor, _stt_model
        if not stt_disponible():
            logger.warning("Modèle STT dioula introuvable : %s", settings.AI_DIOULA_STT_MODEL_DIR)
            return None, None
        try:
            from transformers import AutoProcessor
            from optimum.onnxruntime import ORTModelForCTC

            chemin = str(settings.AI_DIOULA_STT_MODEL_DIR)
            _stt_processor = AutoProcessor.from_pretrained(chemin)
            _stt_model = ORTModelForCTC.from_pretrained(chemin, subfolder='onnx', file_name='model_q4.onnx')
            logger.info("Modèle STT dioula chargé (%s)", chemin)
        except Exception:
            # Dépendance manquante (ex. paquet `optimum` absent d'un environnement) ou
            # modèle corrompu : ne doit JAMAIS faire planter la requête (500) — le
            # contrat de transcrire() promet explicitement de renvoyer None dans ce
            # cas, pas de laisser une exception s'échapper (constaté en test réel).
            logger.exception("Échec du chargement du modèle STT dioula")
            _stt_processor = None
            _stt_model = None
            return None, None
        return _stt_processor, _stt_model


def transcrire(audio_bytes):
    """Transcrit un audio (n'importe quel conteneur — webm/ogg/wav selon le
    navigateur/l'appareil) en texte dioula brut. Renvoie None si le modèle est
    indisponible ou en cas d'échec — jamais d'exception qui casse la requête."""
    processor, model = _charger_stt()
    if model is None:
        return None
    try:
        import subprocess
        import numpy as np
        import librosa
        import imageio_ffmpeg

        # ffmpeg (binaire portable embarqué via imageio-ffmpeg, pas de dépendance
        # système) appelé DIRECTEMENT en sous-processus plutôt que via pydub : pydub
        # sonde d'abord le fichier avec un binaire "ffprobe" séparé, qu'imageio-ffmpeg
        # n'embarque PAS (seulement ffmpeg), ce qui fait toujours échouer le sondage.
        # ffmpeg seul suffit : il détecte le conteneur d'entrée depuis le flux
        # (webm/opus du navigateur, m4a d'Android, wav...) sans sondage préalable, et
        # convertit directement vers un WAV 16kHz mono que librosa peut lire.
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [ffmpeg_bin, '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1', '-f', 'wav', 'pipe:1'],
            input=audio_bytes, capture_output=True,
        )
        if proc.returncode != 0:
            logger.warning("ffmpeg a échoué sur l'audio dioula : %s", proc.stderr[-500:])
            return None
        tampon_wav = io.BytesIO(proc.stdout)

        speech, _ = librosa.load(tampon_wav, sr=16000)
        # pyrefly infère à tort AutoProcessor.from_pretrained() comme un processeur
        # D'IMAGE (BaseImageProcessorFast) — au runtime c'est le bon processeur AUDIO
        # (Wav2Vec2Processor), voir le test réel de bout en bout qui transcrit
        # correctement. Limitation connue de l'inférence statique sur les classes
        # dynamiques `Auto*` de transformers, pas une vraie erreur.
        inputs = processor(speech, sampling_rate=16000, return_tensors='pt')  # pyrefly: ignore
        logits = model(**inputs).logits
        logits_np = logits.detach().numpy() if hasattr(logits, 'detach') else logits
        ids = np.argmax(logits_np, axis=-1)[0]
        return processor.decode(ids).strip()
    except Exception:
        logger.exception("Échec de la transcription dioula")
        return None


# ── Traduction + voix dioula : LAMIA (LAfricaMobile), démo publique ───────────
# Découverte en testant le site public https://translate.lafricamobile.com/ (lecture
# du JS public, aucune route privée) : endpoint POST /translate, form-data
# {inLang, outLang, text}, réponse {translatedText, vocalizeText (URL .wav)}.
# Le sens dioula -> français n'est PAS disponible (testé : HTTP 500), donc cette
# fonction ne couvre QUE français -> dioula, qui fonctionne.
LAMIA_ENDPOINT = "https://translate.lafricamobile.com/translate"
LAMIA_MAX_CHARS = 1500  # marge sûre sous le vrai plafond serveur mesuré (>1000 caractères OK)
LAMIA_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AOCEDA-memoire/1.0)"}


def _decouper_en_tranches(texte, max_chars=LAMIA_MAX_CHARS):
    phrases = re.split(r'(?<=[.!?])\s+', texte.strip())
    tranches, courante = [], ""
    for phrase in phrases:
        candidat = (courante + " " + phrase).strip() if courante else phrase
        if len(candidat) <= max_chars:
            courante = candidat
        else:
            if courante:
                tranches.append(courante)
            courante = phrase[:max_chars]
    if courante:
        tranches.append(courante)
    return tranches or [texte[:max_chars]]


def traduire_vers_dioula(texte_fr):
    """Traduit `texte_fr` en dioula (texte + audio, EN UN SEUL BLOC). Renvoie
    (texte_dioula, audio_wav_bytes) — audio_wav_bytes est None si la synthèse a
    échoué ; texte_dioula est '' en cas d'échec total (jamais d'exception).
    Conservée pour un usage "je veux juste le résultat final", sans le détail
    phrase par phrase — voir traduire_par_phrases() pour le lecteur bilingue
    synchronisé (dioula/français côte à côte), qui est le vrai usage côté UI."""
    segments = traduire_par_phrases(texte_fr)
    textes = [s["dioula"] for s in segments if s.get("dioula")]
    audios_wav = [base64.b64decode(s["audio_base64"]) for s in segments if s.get("audio_base64")]
    texte_final = " ".join(textes)
    audio_final = _concatener_wav(audios_wav) if audios_wav else None
    return texte_final, audio_final


def _nettoyer_markdown(texte):
    """Retire tout ce qui n'est pas de la prose avant traduction/synthèse dioula —
    sans ça, LAMIA traduit les mots mais laisse (ou casse sur) tout le reste tel
    quel, ce qui pollue à la fois la colonne française du lecteur bilingue et la
    traduction/voix dioula. Constaté en test réel (retour utilisateur) :
    - un tableau Markdown envoyé ligne par ligne ("| Problème | Explication |",
      "|---|:--:|") fait partir des lignes de pipes bruts dans les deux colonnes ;
    - des emojis (⚠️, 🔎…) dans la réponse du LLM ressortaient mal ou pas du tout
      traduits par LAMIA ;
    - des guillemets ("« nom d'appareil »") revenaient de LAMIA encodés en entité
      HTML littérale ("&quot;nom d'appareil&quot;") au lieu du caractère lui-même —
      affiché tel quel dans le lecteur (double échappement avec l'esc() du front).
    Miroir (chemin serveur) du nettoyage déjà fait côté navigateur pour la voix
    système FR/EN, voir stripForSpeech() dans static/js/ia.js — même exigence."""
    # Entités HTML éventuelles (les nôtres ou déjà renvoyées par un appel LAMIA
    # précédent si ce texte a été retraduit) normalisées EN PREMIER, sinon un
    # "&quot;" traverserait intact les remplacements suivants.
    texte = html.unescape(texte)

    # Blocs de code : aucun intérêt à traduire/prononcer.
    texte = re.sub(r'```[\s\S]*?```', ' ', texte)

    # Liens Markdown [texte](url) -> garde le texte, jamais l'URL (LAMIA ne sait
    # pas « traduire » une URL, et une URL brute n'a rien à dire à l'oral).
    texte = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', texte)
    texte = re.sub(r'https?://\S+', '', texte)

    # Emojis/pictogrammes : LAMIA ne les traduit pas (constaté : silence ou
    # caractères parasites en sortie) — retirés par sécurité, comme côté FR/EN.
    texte = re.sub(r'[\U0001F300-\U0001FAFF☀-➿]', '', texte)

    # Tableaux Markdown : lignes séparatrices pures (|---|:--:|) supprimées ; les
    # lignes de données gardent leur contenu, pipes remplacés par des virgules
    # pour un semblant de rythme énuméré (même traitement que stripForSpeech()) —
    # les bordures de cellule (pipe en tête/fin de ligne) laisseraient sinon une
    # virgule isolée en tête/fin, envoyée comme un "phrase" à part entière à LAMIA.
    lignes = []
    for ligne in texte.split('\n'):
        if re.match(r'^[\s|:-]+$', ligne) and '|' in ligne:
            continue
        if '|' in ligne:
            ligne = ligne.replace('|', ',')
            ligne = re.sub(r'^\s*,\s*', '', ligne)
            ligne = re.sub(r'\s*,\s*$', '', ligne)
            ligne = re.sub(r',\s*,+', ', ', ligne)
        lignes.append(ligne)
    texte = '\n'.join(lignes)

    # Guillemets/apostrophes typographiques : source du bug de double échappement
    # ci-dessus — retirés avant l'envoi à LAMIA, la ponctuation ne se prononce pas.
    texte = re.sub(r'[«»""„]', '', texte)

    texte = re.sub(r'\*\*([^*]+)\*\*', r'\1', texte)
    texte = re.sub(r'^#{1,6}\s+', '', texte, flags=re.MULTILINE)
    texte = re.sub(r'^[-*_]{3,}$', '', texte, flags=re.MULTILINE)
    # Puces/numéros de liste : seul le contenu compte en prose/à l'oral.
    texte = re.sub(r'^[ \t]*(?:[-*•]|\d+[.)])[ \t]+', '', texte, flags=re.MULTILINE)
    # Code inline restant.
    texte = texte.replace('`', '')
    return texte


def _decouper_en_phrases(texte, max_chars=LAMIA_MAX_CHARS):
    """Découpe en phrases INDIVIDUELLES (pas en tranches groupées comme
    _decouper_en_tranches) — nécessaire pour le lecteur bilingue synchronisé
    phrase par phrase (voir traduire_par_phrases). Coupe aussi sur les retours
    à la ligne : sans ça, tout un bloc à puces Markdown se retrouvait regroupé
    en un seul segment (une puce = sa propre ligne = sa propre « phrase » ici).
    Une phrase seule qui dépasserait la limite LAMIA est quand même tronquée
    brutalement (garde-fou, cas très rare en pratique pour une réponse d'assistant)."""
    texte = _nettoyer_markdown(texte)
    brut = re.split(r'(?<=[.!?])\s+|\n+', texte.strip())
    phrases = [p.strip().lstrip('-*•').strip() for p in brut]
    phrases = [p for p in phrases if p]
    resultat = []
    for p in phrases:
        if len(p) <= max_chars:
            resultat.append(p)
        else:
            for i in range(0, len(p), max_chars):
                resultat.append(p[i:i + max_chars])
    return resultat or [texte[:max_chars]]


def _traduire_une_phrase(phrase):
    """Traduit UNE phrase (texte + audio WAV en base64). Ne lève JAMAIS — en
    cas d'échec, `dioula`/`audio_base64` restent None plutôt que de faire
    disparaître toute la réponse (une phrase ratée n'empêche pas les autres
    de s'afficher dans le lecteur bilingue)."""
    try:
        r = requests.post(
            LAMIA_ENDPOINT, headers=LAMIA_HEADERS,
            data={"inLang": "français", "outLang": "dioula", "text": phrase},
            # 45s : une phrase à elle seule est courte, mais le serveur LAMIA a déjà
            # montré une latence variable (jusqu'à plus de 20s vu en test réel).
            timeout=45,
        )
        if r.status_code != 200:
            logger.warning("LAMIA traduction HTTP %s pour une phrase", r.status_code)
            return {"fr": phrase, "dioula": None, "audio_base64": None}
        data = r.json()
        audio_base64 = None
        if data.get("vocalizeText"):
            audio_r = requests.get(data["vocalizeText"], headers=LAMIA_HEADERS, timeout=20)
            if audio_r.status_code == 200:
                audio_base64 = base64.b64encode(audio_r.content).decode('ascii')
        # Défense en profondeur : LAMIA a déjà renvoyé du texte avec des entités HTML
        # littérales (ex. `&quot;`) dans `translatedText` (constaté en test réel) —
        # décodées ici, sinon elles ressortent doublement échappées côté navigateur
        # (l'esc() du lecteur bilingue échappe un `&` déjà présent en `&amp;`).
        traduction = data.get("translatedText") or None
        if traduction:
            traduction = html.unescape(traduction)
        return {"fr": phrase, "dioula": traduction, "audio_base64": audio_base64}
    except requests.RequestException:
        logger.exception("Échec réseau LAMIA (traduction d'une phrase)")
        return {"fr": phrase, "dioula": None, "audio_base64": None}


# Taille d'un groupe de phrases envoyé en UN SEUL appel LAMIA (voir _regrouper).
# Mesuré en test réel : découper phrase par phrase (1 appel/phrase) faisait
# monter le temps total de ~27-30s à 37-54s pour une réponse de 7-13 phrases —
# la parallélisation ne compense PAS (testé à 3 et 13 requêtes simultanées :
# temps quasi identique, ~37-43s), le vrai goulot est le NOMBRE d'appels réseau,
# pas leur simultanéité. Regrouper ~2-4 phrases courtes par appel a ramené le
# même cas de 37s à 16,5s. Compromis assumé : le surlignage avance par petits
# groupes de phrases plutôt que phrase par phrase exacte, contre un vrai gain
# de vitesse.
GROUPE_MAX_CHARS = 200


def _regrouper_phrases(phrases, max_chars=GROUPE_MAX_CHARS):
    groupes, courant = [], ""
    for p in phrases:
        candidat = (courant + " " + p).strip() if courant else p
        if len(candidat) <= max_chars:
            courant = candidat
        else:
            if courant:
                groupes.append(courant)
            courant = p
    if courant:
        groupes.append(courant)
    return groupes or phrases


def traduire_par_phrases(texte_fr):
    """Traduit `texte_fr` en dioula par PETITS GROUPES DE PHRASES (texte + audio
    par groupe) — pour le lecteur bilingue synchronisé du front (dioula à
    gauche / français à droite, surlignage qui avance pendant la lecture, voir
    static/js/ia.js). Les vrais locuteurs dioula consultés disent que la
    synthèse est un dioula authentique mais pas toujours facile à suivre : ce
    lecteur sert à compenser en montrant le français correspondant en même temps.

    Les appels LAMIA sont faits EN PARALLÈLE, sur des GROUPES de phrases plutôt
    que phrase par phrase — voir GROUPE_MAX_CHARS pour le compromis vitesse/
    granularité mesuré en test réel.

    Renvoie une liste de dicts {fr, dioula, audio_base64} DANS L'ORDRE d'origine
    — si un groupe échoue, il apparaît avec dioula=None plutôt que de faire
    disparaître tout le message."""
    phrases = _decouper_en_phrases(texte_fr)
    groupes = _regrouper_phrases(phrases)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(groupes))) as executor:
        resultats = list(executor.map(_traduire_une_phrase, groupes))
    return resultats


def _concatener_wav(fichiers_wav):
    """Concatène plusieurs WAV (même format, tous issus du moteur LAMIA) en un
    seul, via le module standard `wave` — pas de dépendance supplémentaire."""
    import wave
    if len(fichiers_wav) == 1:
        return fichiers_wav[0]
    params, frames = None, []
    for octets in fichiers_wav:
        with wave.open(io.BytesIO(octets), 'rb') as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
    tampon = io.BytesIO()
    with wave.open(tampon, 'wb') as out:
        out.setparams(params)
        for f in frames:
            out.writeframes(f)
    return tampon.getvalue()
