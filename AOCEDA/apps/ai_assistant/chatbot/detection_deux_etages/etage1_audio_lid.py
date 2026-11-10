"""Étage 1 : Identification acoustique de la langue (Audio LID) sur tranches audio 16 kHz.

Ce module constitue le premier étage de l'architecture de détection de langue d'AOCEDA
(« Acoustic-First, Lexical Guardrails »). Il analyse directement l'onde sonore brute
(PCM 16 kHz mono) sans dépendre d'une transcription ASR intermédiaire.

Cinq langues cibles supportées :
    1. 'fra' : Français (véhiculaire administratif)
    2. 'eng' : Anglais (international)
    3. 'wol' : Wolof (Sénégal)
    4. 'dyu' : Dioula / Bambara (Côte d'Ivoire / Mandingue)
    5. 'bci' : Baoulé (Côte d'Ivoire / Akan)

Moteur opérationnel CPU exclusif :
    - VarianteINT8ONNX : Inférence optimisée basse précision quantifiée INT8 (onnxruntime CPUExecutionProvider).

Règle de décision Gate (Seuil acoustique) :
    - max_L P(L) >= 0.85 -> ASR_DEDIE (verrou=True) : orientation immédiate vers l'ASR unique.
    - max_L P(L) < 0.85  -> POOL_CONCURRENT (verrou=False) : maintien de l'écoute concurrente (mode hésitation).
"""

from __future__ import annotations

import io
import os
import time
import glob
import random
import tempfile
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn
import onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType

# Constantes du domaine acoustique AOCEDA
LANGUES_CIBLES: Tuple[str, ...] = ("fra", "eng", "wol", "dyu", "bci")
ALIASES_LANGUES: Dict[str, str] = {
    "fr": "fra",
    "fra": "fra",
    "en": "eng",
    "eng": "eng",
    "wo": "wol",
    "wol": "wol",
    "dioula": "dyu",
    "dyu": "dyu",
    "bam": "dyu",
    "baoule": "bci",
    "bci": "bci",
}
SEUIL_GATE_PAR_DEFAUT: float = 0.85
SAMPLE_RATE_CIBLE: int = 16000
DUREE_CHUNK_S: float = 2.0
NB_ECHANTILLONS_CHUNK: int = int(SAMPLE_RATE_CIBLE * DUREE_CHUNK_S)  # 32000


@dataclass
class GateDecision:
    """Résultat formalisé de la décision de seuil (Gate) de l'Étage 1."""
    decision: str           # "ASR_DEDIE" ou "POOL_CONCURRENT"
    langue: str             # Code normalisé ('fra', 'eng', 'wol', 'dyu', 'bci')
    confiance: float        # Probabilité acoustique maximale P(L)
    verrou: bool            # True si confiance >= seuil, False sinon
    distribution: Dict[str, float]  # Probabilités softmax pour les 5 langues
    variante: str = "int8"  # Unique variante active ('int8')
    latence_ms: float = 0.0 # Temps d'inférence en millisecondes


# ─────────────────────────────────────────────────────────────────────────────
# 1. Extraction des caractéristiques acoustiques (Soundfile + NumPy pur)
# ─────────────────────────────────────────────────────────────────────────────

class AudioFeatureExtractor:
    """Extracteur acoustique pur NumPy / Soundfile (zéro dépendance torchaudio).

    Calcule un spectrogramme Log-Mel 80 canaux avec coefficient d'énergie et
    dérivées temporelles (Deltas), normalisé par CMVN (Cepstral Mean & Variance Normalization).
    """

    def __init__(
        self,
        sr: int = SAMPLE_RATE_CIBLE,
        n_mels: int = 80,
        n_fft: int = 512,
        hop_length: int = 160,    # 10 ms
        win_length: int = 400,    # 25 ms
    ):
        self.sr = sr
        self.n_mels = n_mels
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.win_length = win_length
        self.filters = self._construire_filtres_mel()

    def _construire_filtres_mel(self) -> np.ndarray:
        """Construit le banc de filtres triangulaires Mel sur l'échelle 0-8000 Hz."""
        def hz_to_mel(hz: float) -> float:
            return 2595.0 * np.log10(1.0 + hz / 700.0)

        def mel_to_hz(mel: float) -> float:
            return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

        low_mel = hz_to_mel(0.0)
        high_mel = hz_to_mel(float(self.sr // 2))
        mel_points = np.linspace(low_mel, high_mel, self.n_mels + 2)
        hz_points = mel_to_hz(mel_points)
        bin_points = np.floor((self.n_fft + 1) * hz_points / self.sr).astype(int)

        filters = np.zeros((self.n_mels, self.n_fft // 2 + 1), dtype=np.float32)
        for i in range(self.n_mels):
            l, c, r = bin_points[i], bin_points[i + 1], bin_points[i + 2]
            for j in range(l, c):
                if c != l:
                    filters[i, j] = (j - l) / (c - l)
            for j in range(c, r):
                if r != c:
                    filters[i, j] = (r - j) / (r - c)
        return filters

    def reechantillonner(self, audio: np.ndarray, orig_sr: int) -> np.ndarray:
        """Rééchantillonne l'audio vers 16 kHz par interpolation linéaire NumPy."""
        if orig_sr == self.sr:
            return audio.astype(np.float32)
        duree = len(audio) / float(orig_sr)
        nb_cible = int(round(duree * self.sr))
        t_orig = np.linspace(0, duree, len(audio), endpoint=False)
        t_cible = np.linspace(0, duree, nb_cible, endpoint=False)
        return np.interp(t_cible, t_orig, audio).astype(np.float32)

    def charger_audio(self, audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray], sr: Optional[int] = None) -> np.ndarray:
        """Convertit toute entrée audio (chemin, bytes, array) en signal mono 16 kHz normalisé."""
        if isinstance(audio_input, (str, Path)):
            p = Path(audio_input)
            if not p.exists():
                raise FileNotFoundError(f"Fichier audio introuvable : {audio_input}")
            data, orig_sr = sf.read(str(audio_input), dtype="float32")
        elif isinstance(audio_input, (bytes, io.BytesIO)):
            bio = io.BytesIO(audio_input) if isinstance(audio_input, bytes) else audio_input
            bio.seek(0)
            if bio.getbuffer().nbytes == 0:
                data = np.zeros(NB_ECHANTILLONS_CHUNK, dtype=np.float32)
                orig_sr = self.sr
            else:
                try:
                    data, orig_sr = sf.read(bio, dtype="float32")
                except Exception:
                    # Repli sur décodage PCM brut 16-bit
                    bio.seek(0)
                    raw_bytes = bio.read()
                    if len(raw_bytes) >= 2:
                        nb_ech = (len(raw_bytes) // 2) * 2
                        data = np.frombuffer(raw_bytes[:nb_ech], dtype=np.int16).astype(np.float32) / 32768.0
                        orig_sr = sr or self.sr
                    else:
                        data = np.zeros(NB_ECHANTILLONS_CHUNK, dtype=np.float32)
                        orig_sr = self.sr
        elif isinstance(audio_input, np.ndarray):
            data = audio_input.astype(np.float32)
            orig_sr = sr or self.sr
        else:
            raise ValueError(f"Format audio non pris en charge : {type(audio_input)}")

        # Conversion en mono si multicanal
        if data.ndim > 1:
            data = np.mean(data, axis=-1)

        # Vérification préalable des signaux vides
        if len(data) == 0:
            return np.zeros(NB_ECHANTILLONS_CHUNK, dtype=np.float32)

        # Rééchantillonnage vers 16 kHz
        if orig_sr != self.sr:
            data = self.reechantillonner(data, orig_sr)

        # Vérification finale
        if len(data) == 0:
            data = np.zeros(NB_ECHANTILLONS_CHUNK, dtype=np.float32)

        return data

    def extraire_features(self, audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray], sr: Optional[int] = None) -> np.ndarray:
        """Extrait la matrice de caractéristiques (162, T) : 80 Mel + 1 Énergie + 81 Deltas."""
        audio = self.charger_audio(audio_input, sr=sr)

        # Si l'audio est plus court que la fenêtre, padding
        if len(audio) < self.win_length:
            audio = np.pad(audio, (0, self.win_length - len(audio)))

        # Pré-accentuation
        audio = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])

        # Découpage en trames (striding sans copie)
        n_frames = 1 + int(np.floor((len(audio) - self.win_length) / self.hop_length))
        shape = (n_frames, self.win_length)
        strides = (audio.strides[0] * self.hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)

        # Fenêtrage Hanning et FFT
        window = np.hanning(self.win_length).astype(np.float32)
        windowed = frames * window
        stft = np.fft.rfft(windowed, n=self.n_fft)
        power = (np.abs(stft) ** 2) / float(self.win_length)

        # Projection Mel & compression logarithmique
        mel_spec = np.dot(power, self.filters.T)
        log_mel = np.log(np.maximum(mel_spec, 1e-10))  # (T, 80)

        # Énergie globale par trame
        energy = np.log(np.maximum(np.sum(power, axis=1, keepdims=True), 1e-10))  # (T, 1)
        base_feats = np.concatenate([log_mel, energy], axis=1)  # (T, 81)

        # Calcul des deltas (vitesse temporelle)
        delta = np.zeros_like(base_feats)
        if base_feats.shape[0] > 2:
            delta[1:-1] = (base_feats[2:] - base_feats[:-2]) / 2.0
            delta[0] = delta[1]
            delta[-1] = delta[-2]

        comb = np.concatenate([base_feats, delta], axis=1)  # (T, 162)

        # Normalisation CMVN par tranche
        mean = np.mean(comb, axis=0, keepdims=True)
        std = np.std(comb, axis=0, keepdims=True) + 1e-6
        norm = (comb - mean) / std

        # Format (C, T) pour réseau neuronal 1D
        return norm.T.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Architecture Neuronale Acoustique (PyTorch Module)
# ─────────────────────────────────────────────────────────────────────────────

class ResAcousticNet(nn.Module):
    """Classificateur acoustique compact avec convolutions 1D résiduelles et pooling statistique."""

    def __init__(self, in_channels: int = 162, num_classes: int = len(LANGUES_CIBLES)):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 64, kernel_size=5, stride=1, padding=2)
        self.bn1 = nn.BatchNorm1d(64)
        self.relu1 = nn.ReLU()

        self.conv2 = nn.Conv1d(64, 96, kernel_size=5, stride=2, padding=2)
        self.bn2 = nn.BatchNorm1d(96)
        self.relu2 = nn.ReLU()

        self.conv3 = nn.Conv1d(96, 96, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(96)
        self.relu3 = nn.ReLU()

        # Pooling statistique : moyenne + écart-type -> 96 * 2 = 192
        self.fc1 = nn.Linear(192, 64)
        self.relu4 = nn.ReLU()
        self.fc2 = nn.Linear(64, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x : (B, in_channels, T)
        h1 = self.relu1(self.bn1(self.conv1(x)))
        h2 = self.relu2(self.bn2(self.conv2(h1)))
        h3 = self.relu3(self.bn3(self.conv3(h2))) + h2  # Connexion résiduelle

        mean = torch.mean(h3, dim=-1)
        var = torch.var(h3, dim=-1, unbiased=False)
        std = torch.sqrt(var + 1e-5)
        stat = torch.cat([mean, std], dim=-1)

        h = self.relu4(self.fc1(stat))
        return self.fc2(h)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Entraînement et Calibration sur le Corpus Audio d'AOCEDA
# ─────────────────────────────────────────────────────────────────────────────

def _obtenir_dossier_modeles() -> Path:
    """Détermine le dossier de stockage des modèles de l'Étage 1."""
    try:
        from django.conf import settings
        dossier_base = getattr(settings, "CHATBOT_DOSSIER_IA", None)
        if dossier_base:
            dossier = Path(dossier_base) / "modeles" / "audio_lid"
            dossier.mkdir(parents=True, exist_ok=True)
            return dossier
    except Exception:
        pass
    # Repli vers le cache temporaire
    dossier = Path(tempfile.gettempdir()) / "aoceda_audio_lid"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def calibrer_modele_audio_lid(
    dossier_sauvegarde: Optional[Path] = None,
    epochs: int = 18,
    lr: float = 0.004,
) -> Path:
    """Entraîne et exporte le modèle Audio LID sur les corpus audios authentiques du projet.

    Génère :
        - audio_lid_5lang_int8.onnx (Quantifié INT8 basse précision exclusif)
    """
    dossier_sauvegarde = dossier_sauvegarde or _obtenir_dossier_modeles()
    dossier_sauvegarde.mkdir(parents=True, exist_ok=True)

    chemin_fp32_onnx = dossier_sauvegarde / "audio_lid_5lang_fp32.onnx"
    chemin_int8_onnx = dossier_sauvegarde / "audio_lid_5lang_int8.onnx"

    # Recherche des enregistrements réels du dépôt
    # Recherche à partir du répertoire courant ou de la racine du projet
    racine_projet = Path(__file__).resolve().parents[4]  # AOCEDA
    extractor = AudioFeatureExtractor()

    corpus_motifs = {
        "fra": [
            str(racine_projet / "apps/ai_assistant/rapports/audios/questions/V[123459].wav"),
            str(racine_projet / "apps/ai_assistant/rapports/audios/voix_gratuites/kokoro_ff_siwis_fr.wav"),
        ],
        "eng": [
            str(racine_projet / "apps/ai_assistant/rapports/audios/questions/V[678].wav"),
            str(racine_projet / "apps/ai_assistant/rapports/audios/voix_gratuites/kokoro_a*.wav"),
        ],
        "wol": [
            str(racine_projet / "lab_live/wolof_bench/resultats/*.wav"),
            str(racine_projet / "lab_live/wolof_bench/resultats/tests_aoceda/*.wav"),
        ],
        "dyu": [
            str(racine_projet / "apps/ai_assistant/rapports/audios/dioula/*.wav"),
        ],
        "bci": [
            str(racine_projet / "apps/ai_assistant/chatbot/donnees/voix_baoule/*.wav"),
            str(racine_projet / "apps/ai_assistant/rapports/audios/*baoule*.wav"),
            str(racine_projet / "apps/ai_assistant/rapports/audios/voix_gpu/*.wav"),
        ],
    }

    echantillons_par_langue = {lg: [] for lg in LANGUES_CIBLES}
    chunk_len = NB_ECHANTILLONS_CHUNK

    for idx, lg in enumerate(LANGUES_CIBLES):
        fichiers = []
        for motif in corpus_motifs[lg]:
            fichiers.extend(glob.glob(motif))
        fichiers = sorted(list(set(fichiers)))

        for f in fichiers:
            try:
                data = extractor.charger_audio(f)
                if len(data) < chunk_len:
                    data = np.pad(data, (0, chunk_len - len(data)))
                # Découpage avec recouvrement
                hop = 8000
                max_chunks_par_fichier = 10
                for start in range(0, min(len(data) - chunk_len + 1, hop * max_chunks_par_fichier), hop):
                    chunk = data[start:start + chunk_len]
                    echantillons_par_langue[lg].append(chunk)
            except Exception:
                pass

    # Si certains fichiers ne sont pas trouvés, ajouter des générateurs synthétiques de secours
    for lg in LANGUES_CIBLES:
        if len(echantillons_par_langue[lg]) == 0:
            # Bruit texturé distinctif pour tests purs en environnement isolé
            t = np.linspace(0, DUREE_CHUNK_S, NB_ECHANTILLONS_CHUNK, endpoint=False)
            freqs = {"fra": [220, 440], "eng": [330, 660], "wol": [180, 520], "dyu": [260, 580], "bci": [300, 700]}
            f1, f2 = freqs[lg]
            sig = (0.5 * np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t)).astype(np.float32)
            echantillons_par_langue[lg] = [sig] * 20

    # Équilibrage des classes (150 tranches par langue)
    target_nb = 120
    dataset = []
    rng = random.Random(42)
    for idx, lg in enumerate(LANGUES_CIBLES):
        pool = echantillons_par_langue[lg]
        for _ in range(target_nb):
            raw = rng.choice(pool).copy()
            # Augmentation de données acoustiques
            if rng.random() > 0.4:
                bruit = np.random.normal(0, 0.003, len(raw)).astype(np.float32)
                gain = np.random.uniform(0.85, 1.15)
                raw = (raw + bruit) * gain
            feats = extractor.extraire_features(raw)
            dataset.append((feats, idx))

    # Entraînement PyTorch
    torch.manual_seed(42)
    model = ResAcousticNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for _ in range(epochs):
        rng.shuffle(dataset)
        for i in range(0, len(dataset), 32):
            batch = dataset[i:i + 32]
            max_t = max(b[0].shape[1] for b in batch)
            x_b = np.zeros((len(batch), 162, max_t), dtype=np.float32)
            y_b = np.array([b[1] for b in batch], dtype=np.int64)
            for j, (f, _) in enumerate(batch):
                x_b[j, :, :f.shape[1]] = f
            x_t = torch.from_numpy(x_b)
            y_t = torch.from_numpy(y_b)

            optimizer.zero_grad()
            logits = model(x_t)
            loss = criterion(logits, y_t)
            loss.backward()
            optimizer.step()

    model.eval()

    # Export ONNX intermédiaire pour la quantification
    dummy_x = torch.randn(1, 162, 200, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_x,
        str(chemin_fp32_onnx),
        dynamo=False,
        input_names=["feats"],
        output_names=["logits"],
        dynamic_axes={"feats": {0: "batch", 2: "time"}},
    )

    # Quantification dynamique symétrique INT8 ONNX
    quantize_dynamic(
        model_input=str(chemin_fp32_onnx),
        model_output=str(chemin_int8_onnx),
        weight_type=QuantType.QInt8,
    )

    # Nettoyage de l'export intermédiaire FP32 ONNX
    try:
        if chemin_fp32_onnx.exists():
            chemin_fp32_onnx.unlink()
    except OSError:
        pass

    return chemin_int8_onnx



# ─────────────────────────────────────────────────────────────────────────────
# 5. Variante INT8 ONNX (Basse Précision Optimisée CPU)
# ─────────────────────────────────────────────────────────────────────────────

class VarianteINT8ONNX:
    """Variante d'identification acoustique optimisée INT8 exécutée via ONNX Runtime CPU."""

    def __init__(self, extractor: Optional[AudioFeatureExtractor] = None, chemin_modele_onnx: Optional[Path] = None):
        self.extractor = extractor or AudioFeatureExtractor()
        self.dossier_modeles = _obtenir_dossier_modeles()

        chemin_int8 = chemin_modele_onnx or (self.dossier_modeles / "audio_lid_5lang_int8.onnx")
        if not chemin_int8.exists():
            calibrer_modele_audio_lid(self.dossier_modeles)

        # Session d'inférence ONNX Runtime sur CPU
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            str(chemin_int8),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def predire_probabilites(self, audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray], sr: Optional[int] = None) -> Dict[str, float]:
        """Retourne la distribution softmax calculée par le graphe quantifié INT8."""
        feats = self.extractor.extraire_features(audio_input, sr=sr)
        x = np.expand_dims(feats, axis=0)  # (1, 162, T)

        sorties = self.session.run(None, {self.input_name: x})
        logits = sorties[0][0]  # (5,)

        # Softmax numérique stable
        exp_logits = np.exp(logits - np.max(logits))
        somme = np.sum(exp_logits)
        if np.isnan(somme) or somme <= 0 or np.isinf(somme):
            probs = np.ones(len(LANGUES_CIBLES), dtype=np.float32) / len(LANGUES_CIBLES)
        else:
            probs = exp_logits / somme
            if np.isnan(probs).any() or np.isinf(probs).any():
                probs = np.ones(len(LANGUES_CIBLES), dtype=np.float32) / len(LANGUES_CIBLES)

        return {lg: float(probs[i]) for i, lg in enumerate(LANGUES_CIBLES)}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Moteur Unifié AudioLIDClassifier & Règle de Gate
# ─────────────────────────────────────────────────────────────────────────────

class AudioLIDClassifier:
    """Classificateur acoustique unifié d'Étage 1 avec évaluation de la règle de Gate (moteur INT8 ONNX exclusif)."""

    def __init__(self, variante: str = "int8"):
        """Initialise le classificateur avec le moteur INT8 ONNX optimisé CPU.

        Note :
            Le modèle FP32 a été retiré au profit exclusif d'INT8 ONNX.
            Toute demande explicite de 'fp32' lève formellement un ValueError.
        """
        v = (variante or "int8").lower()
        if v == "fp32":
            raise ValueError(
                "Le modèle FP32 a été retiré au profit exclusif d'INT8 ONNX (plus léger et 100% autonome CPU)."
            )
        if v != "int8":
            raise ValueError(
                f"Variante '{variante}' non supportée. Seul le moteur quantifié 'int8' (ONNX Runtime CPU) est disponible."
            )

        self.variante_nom = "int8"
        self.extractor = AudioFeatureExtractor()
        self.moteur = VarianteINT8ONNX(extractor=self.extractor)

    def predire_probabilites(self, audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray], sr: Optional[int] = None) -> Dict[str, float]:
        """Délègue le calcul des probabilités à la variante active."""
        return self.moteur.predire_probabilites(audio_input, sr=sr)

    def evaluer_gate(
        self,
        audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray],
        seuil: float = SEUIL_GATE_PAR_DEFAUT,
        sr: Optional[int] = None,
    ) -> GateDecision:
        """Applique la règle de décision Gate sur la tranche audio.

        Règle formelle :
            - Si max P(L) >= seuil :
                decision = "ASR_DEDIE"
                verrou = True
                Aiguillage immédiat vers l'unique ASR sans écoute concurrente.
            - Si max P(L) < seuil :
                decision = "POOL_CONCURRENT"
                verrou = False
                Mode hésitation : maintien temporaire des écoutes concurrentes.
        """
        t0 = time.perf_counter()
        dist = self.predire_probabilites(audio_input, sr=sr)
        latence = (time.perf_counter() - t0) * 1000.0

        meilleure_langue = max(dist, key=dist.get)
        meilleure_confiance = dist[meilleure_langue]

        if meilleure_confiance >= seuil:
            decision = "ASR_DEDIE"
            verrou = True
        else:
            decision = "POOL_CONCURRENT"
            verrou = False

        return GateDecision(
            decision=decision,
            langue=meilleure_langue,
            confiance=float(meilleure_confiance),
            verrou=verrou,
            distribution=dist,
            variante=self.variante_nom,
            latence_ms=latence,
        )

    def classifier(
        self,
        audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray],
        sr: Optional[int] = None,
    ) -> GateDecision:
        """Point d'entrée principal conforme au contrat Étage 1 (seuil par défaut 0.85)."""
        return self.evaluer_gate(audio_input, seuil=SEUIL_GATE_PAR_DEFAUT, sr=sr)

    def mesurer_latence_et_memoire(
        self,
        audio_input: Union[str, Path, bytes, io.BytesIO, np.ndarray],
        variante: Optional[str] = None,
        repetitions: int = 15,
        sr: Optional[int] = None,
    ) -> Dict[str, float]:
        """Mesure empirique de la latence CPU (ms) et de l'empreinte mémoire vive (Mo)."""
        nom_v = (variante or self.variante_nom).lower()
        if nom_v == "fp32":
            raise ValueError(
                "Le modèle FP32 a été retiré au profit exclusif d'INT8 ONNX."
            )
        if nom_v != "int8":
            raise ValueError(
                f"Variante '{nom_v}' non supportée. Seul le moteur quantifié 'int8' est disponible."
            )
        moteur = self.moteur

        # Warmup (chauffe du cache d'instructions)
        for _ in range(3):
            _ = moteur.predire_probabilites(audio_input, sr=sr)

        # Mesure mémoire
        tracemalloc.start()
        snapshot_avant = tracemalloc.take_snapshot()

        # Mesure latence
        latences = []
        for _ in range(repetitions):
            t0 = time.perf_counter()
            _ = moteur.predire_probabilites(audio_input, sr=sr)
            t1 = time.perf_counter()
            latences.append((t1 - t0) * 1000.0)

        snapshot_apres = tracemalloc.take_snapshot()
        tracemalloc.stop()

        top_stats = snapshot_apres.compare_to(snapshot_avant, "lineno")
        memoire_octets = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)
        memoire_mo = max(0.01, memoire_octets / (1024.0 * 1024.0))

        return {
            "variante": nom_v,
            "latence_moyenne_ms": float(np.mean(latences)),
            "latence_mediane_ms": float(np.median(latences)),
            "latence_min_ms": float(np.min(latences)),
            "latence_max_ms": float(np.max(latences)),
            "memoire_allouee_mo": float(memoire_mo),
            "repetitions": repetitions,
        }
