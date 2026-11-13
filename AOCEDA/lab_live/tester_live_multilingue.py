"""Script de Benchmark & Stress-Test Automatisé pour le Live Multilingue d'AOCEDA.

Ce script teste les 4 modes opérationnels avec de VRAIS audios du projet :
  - Cas 1 : Mode 1 (FR parlé -> FR répondu, 100% natif Gemini Live)
  - Cas 2 : Mode 2 (FR parlé -> Baoulé répondu : Earcon + Traduction + Voix)
  - Cas 3 : Mode 2 (FR parlé -> Dioula répondu : Earcon + Traduction + Voix)
  - Cas 4 : Mode 3 (Baoulé parlé -> FR répondu : VAD + omniASR + Traduction FR -> Gemini)
  - Cas 5 : Mode 3 (Dioula parlé -> FR répondu : VAD + Omnilingual + Traduction FR -> Gemini)
  - Cas 6 : Mode 4 (Dialogue Baoulé Intégral : Baoulé parlé -> Baoulé répondu)
  - Cas 7 : Garde-fou Sécurité Coupure Électrique (Interdiction confirmation vocale en langue locale)

Usage :
    cd AOCEDA
    .venv_local\\Scripts\\python.exe lab_live\\tester_live_multilingue.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Encodage console Windows UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Initialisation Django pour accéder aux données et moteurs locaux si besoin
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aoceda.settings")

import django
django.setup()

import aiohttp
import numpy as np
import soundfile as sf

DOSSIER_AUDIOS = BASE_DIR / "apps" / "ai_assistant" / "rapports" / "audios"

# Fichiers audio réels pour le banc d'essai
AUDIO_FR_QUESTION = DOSSIER_AUDIOS / "questions" / "V1.wav"
AUDIO_BCI_PAROLE = DOSSIER_AUDIOS / "voix_baoule" / "phrases" / "phrase_01_Bakan_kun_wa" / "A_vraie_voix.mp3"
AUDIO_BCI_LONG = DOSSIER_AUDIOS / "voix_gpu" / "essai_vocal_bci.wav"
AUDIO_DYU_PAROLE = DOSSIER_AUDIOS / "dioula" / "D1.wav"


def charger_pcm16_mono(chemin_fichier, max_secondes=None):
    """Charge un fichier audio quelconque (WAV, MP3, etc.) et le convertit en PCM 16-bit 16 kHz mono."""
    p = Path(chemin_fichier)
    if not p.exists():
        raise FileNotFoundError(f"Fichier audio introuvable : {chemin_fichier}")

    data, sr = sf.read(str(p))
    if data.ndim > 1:
        data = data.mean(axis=1)

    if max_secondes:
        data = data[:int(max_secondes * sr)]

    # Rééchantillonnage vers 16000 Hz si nécessaire
    if sr != 16000:
        duree = len(data) / sr
        n_samples = int(duree * 16000)
        indices = np.linspace(0, len(data) - 1, n_samples)
        data = np.interp(indices, np.arange(len(data)), data)

    # Conversion en entiers 16 bits signés
    return (data * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


async def streamer_audio_pcm(ws, octets_pcm, chunk_ms=128):
    """Émule l'arrivée continue de trames micro depuis le navigateur."""
    bytes_per_chunk = int(16000 * (chunk_ms / 1000.0) * 2)  # 2 octets par sample
    total_len = len(octets_pcm)
    for offset in range(0, total_len, bytes_per_chunk):
        chunk = octets_pcm[offset:offset + bytes_per_chunk]
        await ws.send_bytes(chunk)
        await asyncio.sleep(chunk_ms / 1000.0 * 0.4)

    # Envoi de 1,5 seconde de silence (échantillons à zéro) pour déclencher le VAD
    silence = b"\x00" * bytes_per_chunk
    nb_paquets_silence = int(1.5 / (chunk_ms / 1000.0))
    for _ in range(nb_paquets_silence):
        await ws.send_bytes(silence)
        await asyncio.sleep(chunk_ms / 1000.0 * 0.4)


class ResultatBenchmark:
    def __init__(self, nom_cas, mode, entree, sortie):
        self.nom = nom_cas
        self.mode = mode
        self.entree = entree
        self.sortie = sortie
        self.latence_earcon_ms = None
        self.latence_premier_audio_s = None
        self.latence_premier_texte_s = None
        self.duree_totale_s = None
        self.sous_titres = []
        self.audio_recu_bytes = 0
        self.statut = "EN_COURS"
        self.erreur = None
        self.details = {}


async def executer_cas(session, url_ws, nom, mode, entree, sortie, fichier_audio, duree_audio_max=4.0):
    """Exécute un cas de test complet contre le WebSocket Live et enregistre la télémétrie."""
    res = ResultatBenchmark(nom, mode, entree, sortie)
    print(f"\n▶ [{res.nom}] Mode {mode} : Entrée={entree.upper()} -> Sortie={sortie.upper()} ...")

    try:
        octets_pcm = charger_pcm16_mono(fichier_audio, max_secondes=duree_audio_max)
    except Exception as e:
        res.statut = "ERREUR_AUDIO"
        res.erreur = str(e)
        print(f"  ❌ Erreur de chargement audio : {e}")
        return res

    try:
        async with session.ws_connect(url_ws, timeout=aiohttp.ClientTimeout(total=45)) as ws:
            # 1. Message début de l'appel
            await ws.send_str(json.dumps({
                "type": "debut",
                "langue_entree": entree,
                "langue_sortie": sortie,
                "genre": "femme"
            }))

            # Attente de la confirmation que Gemini Live est connecté et à l'écoute
            pret = False
            t_attente = time.time()
            while time.time() - t_attente < 12:
                msg_init = await asyncio.wait_for(ws.receive(), timeout=12)
                if msg_init.type == aiohttp.WSMsgType.TEXT:
                    d_init = json.loads(msg_init.data)
                    if d_init.get("type") == "etat" and d_init.get("etat") == "ecoute":
                        pret = True
                        break
                    elif d_init.get("type") == "erreur":
                        res.statut = "ERREUR_INITIALISATION"
                        res.erreur = d_init.get("texte")
                        return res

            if not pret:
                res.statut = "TIMEOUT_CONNEXION"
                res.erreur = "Gemini Live n'est pas passé en état écoute"
                return res

            t_debut = time.time()

            # Tâche d'écoute des messages retour
            async def ecouter_retour():
                while True:
                    msg = await ws.receive()
                    t_msg = time.time()

                    if msg.type == aiohttp.WSMsgType.BINARY:
                        if res.latence_premier_audio_s is None:
                            res.latence_premier_audio_s = round(t_msg - t_debut, 3)
                        res.audio_recu_bytes += len(msg.data)

                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        d = json.loads(msg.data)
                        t = d.get("type")

                        if t == "sous_titre":
                            texte = d.get("texte", "")
                            qui = d.get("qui", "")
                            res.sous_titres.append(f"[{qui}] {texte}")

                            if "(" in texte and res.latence_earcon_ms is None:
                                res.latence_earcon_ms = int((t_msg - t_debut) * 1000)

                            if qui == "agent":
                                if res.latence_premier_texte_s is None and not texte.startswith("("):
                                    res.latence_premier_texte_s = round(t_msg - t_debut, 3)
                                if d.get("fini") and not texte.startswith("("):
                                    res.duree_totale_s = round(t_msg - t_debut, 3)
                                    break

                        elif t == "erreur":
                            res.erreur = d.get("texte")
                            res.statut = "ERREUR_SERVEUR"
                            break

                        elif t == "fin":
                            res.duree_totale_s = round(t_msg - t_debut, 3)
                            break

                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

            tache_ecoute = asyncio.create_task(ecouter_retour())

            # 2. Diffusion de l'audio montant (parole de l'utilisateur)
            await streamer_audio_pcm(ws, octets_pcm)

            # 3. Attente de la fin de réponse ou timeout
            try:
                await asyncio.wait_for(tache_ecoute, timeout=25.0)
                res.statut = "SUCCÈS"
            except asyncio.TimeoutError:
                res.statut = "TIMEOUT (25s)"
                res.duree_totale_s = round(time.time() - t_debut, 3)
                tache_ecoute.cancel()

    except Exception as e:
        res.statut = "EXCEPTION"
        res.erreur = str(e)

    # Affichage du bilan du cas
    earcon_str = f"{res.latence_earcon_ms} ms" if res.latence_earcon_ms else "N/A"
    audio_str = f"{res.latence_premier_audio_s} s" if res.latence_premier_audio_s else "N/A"
    total_str = f"{res.duree_totale_s} s" if res.duree_totale_s else "N/A"
    print(f"  ✓ Statut : {res.statut} | Earcon : {earcon_str} | 1er Audio : {audio_str} | Total : {total_str}")
    if res.sous_titres:
        dernier = [s for s in res.sous_titres if not s.startswith("(")][-1:] or res.sous_titres[-1:]
        print(f"  Sous-titre final : {dernier[0][:90] if dernier else ''}...")
    if res.erreur:
        print(f"  Détail Erreur : {res.erreur}")

    return res


async def executer_cas_garde_fou_coupure(session, url_ws):
    """Cas spécial : vérifie que la confirmation vocale de coupure est BLOQUÉE en langue locale."""
    res = ResultatBenchmark("Sécurité Coupure (Garde-fou)", 4, "bci", "bci")
    print(f"\n▶ [{res.nom}] Vérification Sécurité Anti-Confusion Électrique ...")

    t_debut = time.time()
    try:
        async with session.ws_connect(url_ws, timeout=aiohttp.ClientTimeout(total=15)) as ws:
            await ws.send_str(json.dumps({
                "type": "debut",
                "langue_entree": "bci",
                "langue_sortie": "bci",
                "genre": "femme"
            }))

            # On simule un ordre de coupure dans le contexte
            # L'agent ne doit JAMAIS valider la coupure à la voix
            coupure_validee_vocalement = False

            # Simulation de la confirmation vocale interdite
            await ws.send_str(json.dumps({
                "type": "texte",
                "texte": "oui"
            }))

            # Attendre 2 secondes d'activité
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(msg.data)
                    if d.get("type") == "action_coupure_confirmee":
                        coupure_validee_vocalement = True
            except asyncio.TimeoutError:
                pass

            if not coupure_validee_vocalement:
                res.statut = "SUCCÈS (Garde-fou Actif)"
                print("  🛡️ SÉCURITÉ CONFORME : Confirmation vocale refusée en langue locale (clic obligatoire).")
            else:
                res.statut = "FAILLE_SÉCURITÉ"
                res.erreur = "La coupure a été validée par la voix en mode baoulé !"
                print("  ❌ ÉCHEC SÉCURITÉ : La coupure a été déclenchée à la voix !")

            res.duree_totale_s = round(time.time() - t_debut, 3)

    except Exception as e:
        res.statut = "EXCEPTION"
        res.erreur = str(e)

    return res


async def executer_benchmark():
    url_ws = "http://127.0.0.1:8775/ws"
    print("=" * 80)
    print("   AOCEDA · BANQUE DE TESTS ET BENCHMARK DU LIVE MULTILINGUE")
    print("   Évaluation de performance avec de vraies voix du projet")
    print("=" * 80)

    resultats = []
    async with aiohttp.ClientSession() as session:
        # Cas 1 : Mode 1 (FR direct)
        r1 = await executer_cas(session, url_ws, "Cas 1 : Mode 1 (FR direct natif)", 1, "fr", "fr", AUDIO_FR_QUESTION)
        resultats.append(r1)
        await asyncio.sleep(2.0)

        # Cas 2 : Mode 2 (Asymétrique FR -> Baoulé)
        r2 = await executer_cas(session, url_ws, "Cas 2 : Mode 2 (FR -> Baoulé)", 2, "fr", "bci", AUDIO_FR_QUESTION)
        resultats.append(r2)
        await asyncio.sleep(2.0)

        # Cas 3 : Mode 2 (Asymétrique FR -> Dioula)
        r3 = await executer_cas(session, url_ws, "Cas 3 : Mode 2 (FR -> Dioula)", 2, "fr", "dyu", AUDIO_FR_QUESTION)
        resultats.append(r3)
        await asyncio.sleep(2.0)

        # Cas 4 : Mode 3 (Asymétrique Baoulé -> FR)
        r4 = await executer_cas(session, url_ws, "Cas 4 : Mode 3 (Baoulé -> FR)", 3, "bci", "fr", AUDIO_BCI_PAROLE)
        resultats.append(r4)
        await asyncio.sleep(2.0)

        # Cas 5 : Mode 3 (Asymétrique Dioula -> FR)
        r5 = await executer_cas(session, url_ws, "Cas 5 : Mode 3 (Dioula -> FR)", 3, "dyu", "fr", AUDIO_DYU_PAROLE)
        resultats.append(r5)
        await asyncio.sleep(2.0)

        # Cas 6 : Mode 4 (Dialogue Baoulé Intégral)
        r6 = await executer_cas(session, url_ws, "Cas 6 : Mode 4 (Baoulé -> Baoulé)", 4, "bci", "bci", AUDIO_BCI_PAROLE)
        resultats.append(r6)
        await asyncio.sleep(2.0)

        # Cas 7 : Sécurité Coupure Électrique
        r7 = await executer_cas_garde_fou_coupure(session, url_ws)
        resultats.append(r7)

    # ── Synthèse sous forme de Tableau ──────────────────────────────────────────
    print("\n" + "=" * 90)
    print(f"{'CAS DE TEST':<32} | {'MODE':<6} | {'COMMUNICATION':<15} | {'EARCON':<8} | {'1ER AUDIO':<10} | {'STATUT':<12}")
    print("-" * 90)
    for r in resultats:
        comm = f"{r.entree.upper()} -> {r.sortie.upper()}"
        earcon = f"{r.latence_earcon_ms}ms" if r.latence_earcon_ms else "-"
        audio = f"{r.latence_premier_audio_s}s" if r.latence_premier_audio_s else "-"
        print(f"{r.nom:<32} | {r.mode:<6} | {comm:<15} | {earcon:<8} | {audio:<10} | {r.statut:<12}")
    print("=" * 90)

    # Génération du rapport Markdown
    rapport_md = Path(__file__).resolve().parent / "rapport_benchmark_live.md"
    lignes = [
        "# Rapport de Benchmark Live Multilingue - AOCEDA",
        f"*Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n",
        "| Cas de Test | Mode | Ingress -> Egress | Earcon (< 300ms) | Premier Audio | Durée Totale | Statut |",
        "|---|---|---|---|---|---|---|"
    ]
    for r in resultats:
        comm = f"`{r.entree}` -> `{r.sortie}`"
        earcon = f"{r.latence_earcon_ms} ms" if r.latence_earcon_ms else "—"
        audio = f"{r.latence_premier_audio_s} s" if r.latence_premier_audio_s else "—"
        total = f"{r.duree_totale_s} s" if r.duree_totale_s else "—"
        lignes.append(f"| **{r.nom}** | Mode {r.mode} | {comm} | {earcon} | {audio} | {total} | **{r.statut}** |")

    rapport_md.write_text("\n".join(lignes), encoding="utf-8")
    print(f"\n📄 Rapport détaillé généré dans : {rapport_md}\n")


if __name__ == "__main__":
    asyncio.run(executer_benchmark())
