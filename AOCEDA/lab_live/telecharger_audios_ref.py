import os
import sys
from pathlib import Path
from decouple import Config, RepositoryEnv
from huggingface_hub import hf_hub_download
import requests
import json

# Setup environment and directories
base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
env_file = base_dir / ".env"
env_config = Config(RepositoryEnv(env_file))
hf_token = env_config('HF_TOKEN', default=None)

bench_dir = base_dir / "lab_live" / "wolof_bench"
audios_dir = bench_dir / "audios_references"
stt_dir = bench_dir / "modeles" / "stt" / "whisper_small_wolof_onnx"
tts_dir = bench_dir / "modeles" / "tts" / "speecht5_tts_wolof"

for d in [audios_dir, stt_dir, tts_dir]:
    d.mkdir(parents=True, exist_ok=True)

print(f"=== PRÉPARATION DU BANC WOLOF DANS {bench_dir} ===")

# 1. Téléchargement des 4 Audios Longs de Référence
print("\n--- 1. TÉLÉCHARGEMENT DES 4 AUDIOS LONGS DE RÉFÉRENCE ---")

audios_to_fetch = [
    {
        "id": "audio_01_conte_spontane",
        "nom": "Audio 1 - Conte & Récit spontané (35s)",
        "fichier": audios_dir / "audio_01_conte_spontane.wav",
        "url": "https://huggingface.co/soynade-research/Wolof-HuBERT-CTC/resolve/main/story.wav",
        "transcription_wolof": "Dama leen di nettali léegi benn taarix bu am solo ci sunu réew, ci wallu nite ak jëflante...",
        "sens_francais": "Je m'en vais vous raconter maintenant une histoire importante de notre pays, sur l'humanité et les relations humaines...",
        "locuteur": "Locuteur natif (Sénégal), parole spontanée continue",
        "source": "https://huggingface.co/soynade-research/Wolof-HuBERT-CTC/resolve/main/story.wav"
    },
    {
        "id": "audio_02_presse_alffa_homme",
        "nom": "Audio 2 - Presse & Vie quotidienne Homme (22s)",
        "fichier": audios_dir / "audio_02_presse_alffa_homme.wav",
        "url": "https://raw.githubusercontent.com/getalp/ALFFA_PUBLIC/master/ASR/WOLOF/data/test/wav/05/WOL_05_lect_0053.wav",
        "transcription_wolof": "ba mu demee ba wara takk jabar mu dem seeti doomu nijaayam",
        "sens_francais": "Quand le moment fut venu d'épouser une femme, il alla voir la fille de son oncle maternel.",
        "locuteur": "Homme (Locuteur 05 ALFFA, Dakar/Saint-Louis)",
        "source": "https://raw.githubusercontent.com/getalp/ALFFA_PUBLIC/master/ASR/WOLOF/data/test/wav/05/WOL_05_lect_0053.wav"
    },
    {
        "id": "audio_03_studio_pro_femme",
        "nom": "Audio 3 - Voix Studio Femme Pro (20s)",
        "fichier": audios_dir / "audio_03_studio_pro_femme.wav",
        "url": "https://huggingface.co/spaces/soynade-research/Oolel-Voices-Demo/resolve/main/8_1_c.wav",
        "transcription_wolof": "Su ko nit ñi laajee: Ñan ngay defal say filme? day tontu naan: Europe mooy sama marché, waaye ñimay seetaan, Afrique lañu nekk.",
        "sens_francais": "Si les gens lui demandent : Pour qui fais-tu tes films ? il répond : L'Europe est mon marché, mais ceux qui me regardent sont en Afrique.",
        "locuteur": "Femme (Enregistrement studio professionnel haute clarté)",
        "source": "https://huggingface.co/spaces/soynade-research/Oolel-Voices-Demo/resolve/main/8_1_c.wav"
    },
    {
        "id": "audio_04_conseil_famille",
        "nom": "Audio 4 - Conseil familial & sagesse (18s)",
        "fichier": audios_dir / "audio_04_conseil_famille.wav",
        "url": "https://raw.githubusercontent.com/getalp/ALFFA_PUBLIC/master/ASR/WOLOF/data/test/wav/05/WOL_05_lect_0030.wav",
        "transcription_wolof": "nanga diisoo ak sa jëkkër bala ngay def dara",
        "sens_francais": "Concerte-toi avec ton mari avant de faire quoi que ce soit.",
        "locuteur": "Homme (Locuteur 05 ALFFA, parole naturelle articulée)",
        "source": "https://raw.githubusercontent.com/getalp/ALFFA_PUBLIC/master/ASR/WOLOF/data/test/wav/05/WOL_05_lect_0030.wav"
    }
]

catalogue = []
headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}

for item in audios_to_fetch:
    dest = item["fichier"]
    if not dest.exists() or dest.stat().st_size == 0:
        print(f"Téléchargement de {item['nom']}...")
        r = requests.get(item["url"], headers=headers if "huggingface.co" in item["url"] else {}, timeout=20)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            taille_ko = len(r.content) / 1024
            print(f"  -> OK ({taille_ko:.1f} Ko)")
        else:
            print(f"  -> ERREUR {r.status_code}")
    else:
        print(f"Déjà présent : {item['nom']} ({dest.stat().st_size / 1024:.1f} Ko)")
    
    catalogue.append({
        "id": item["id"],
        "nom": item["nom"],
        "fichier": dest.name,
        "taille_octets": dest.stat().st_size if dest.exists() else 0,
        "transcription_wolof": item["transcription_wolof"],
        "sens_francais": item["sens_francais"],
        "locuteur": item["locuteur"],
        "source_url": item["source"]
    })

cat_file = bench_dir / "catalogue_references.json"
with open(cat_file, "w", encoding="utf-8") as f:
    json.dump(catalogue, f, indent=2, ensure_ascii=False)
print(f"Catalogue des références sauvegardé : {cat_file}")
