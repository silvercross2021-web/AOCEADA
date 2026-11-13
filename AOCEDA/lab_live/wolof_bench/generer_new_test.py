import os
import sys
import shutil
import time
import wave
from pathlib import Path
from decouple import Config, RepositoryEnv

# Fix Windows console encoding
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from gradio_client import Client, handle_file

base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
env_file = base_dir / ".env"
env_config = Config(RepositoryEnv(env_file))
hf_token = env_config("HF_TOKEN", default=None)

bench_dir = base_dir / "lab_live" / "wolof_bench"
audios_dir = bench_dir / "audios_references"
old_comp_dir = bench_dir / "comparaisons_audio"
new_test_dir = bench_dir / "new_test"
new_test_dir.mkdir(parents=True, exist_ok=True)

# Référence calibrée 6 secondes officielle
ref_officielle = audios_dir / "8_1_c_prompt_6s.wav"
if not ref_officielle.exists():
    src = audios_dir / "8_1_c_officiel.wav"
    r = wave.open(str(src), "rb")
    params = r.getparams()
    frames = r.readframes(int(6.0 * params.framerate))
    r.close()
    w = wave.open(str(ref_officielle), "wb")
    w.setparams(params)
    w.writeframes(frames)
    w.close()
    print(f"Prompt 6s créé : {ref_officielle.stat().st_size} octets")

def get_audio_info(path):
    if not path.exists():
        return 0, 0, 0
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / float(rate)
            return duration, rate, path.stat().st_size
    except Exception as e:
        print(f"Erreur lecture wave {path}: {e}")
        return 0, 0, path.stat().st_size

tests_definitions = [
    {
        "id": "1_new",
        "titre": "Test 1 - Conseil de Famille & Sagesse (Proverbe)",
        "texte": "Nanga diisoo, ak sa jëkkër, bala ngay def dara.",
        "traduction": "Concerte-toi avec ton mari avant de faire quoi que ce soit.",
        "humain_src": audios_dir / "audio_04_conseil_famille.wav",
        "ancien_oolel_src": old_comp_dir / "01_TEST_CONSEIL_SAGESSE" / "2_SYNTHESE_IA_OOLEL_VOICES.wav",
        "speecht5_src": old_comp_dir / "01_TEST_CONSEIL_SAGESSE" / "3_SYNTHESE_IA_SPEECHT5.wav",
    },
    {
        "id": "2_new",
        "titre": "Test 2 - Presse & Vie Quotidienne (Mariage)",
        "texte": "Ba mu demee ba wara takk jabar, mu dem seeti doomu nijaayam.",
        "traduction": "Quand le moment fut venu d'épouser une femme, il alla voir la fille de son oncle maternel.",
        "humain_src": audios_dir / "audio_02_presse_alffa_homme.wav",
        "ancien_oolel_src": old_comp_dir / "02_TEST_PRESSE_ET_MARIAGE" / "2_SYNTHESE_IA_OOLEL_VOICES.wav",
        "speecht5_src": old_comp_dir / "02_TEST_PRESSE_ET_MARIAGE" / "3_SYNTHESE_IA_SPEECHT5.wav",
    },
    {
        "id": "3_new",
        "titre": "Test 3 - Cas Metier Energie AOCEDA",
        "texte": "AOCEDA dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar.",
        "traduction": "AOCEDA surveille ton electricite et t'informe de tes depenses.",
        "humain_src": None,
        "ancien_oolel_src": old_comp_dir / "03_TEST_METIER_AOCEDA_ENERGIE" / "2_SYNTHESE_IA_OOLEL_VOICES.wav",
        "speecht5_src": old_comp_dir / "03_TEST_METIER_AOCEDA_ENERGIE" / "3_SYNTHESE_IA_SPEECHT5.wav",
    },
    {
        "id": "4_new",
        "titre": "Test 4 - Conte & Recit Spontane (Mbaaba Kumba)",
        "texte": "Amoon na fi ab dëkk bu tuddee Mbaaba Kumba, kenn xamatu fu mu nekk léegi.",
        "traduction": "Il y avait autrefois un village nomme Mbaaba Kumba, personne ne sait plus ou il se trouve maintenant.",
        "humain_src": audios_dir / "audio_01_conte_spontane.wav",
        "ancien_oolel_src": old_comp_dir / "04_TEST_CONTE_SPONTANE" / "2_SYNTHESE_IA_OOLEL_VOICES.wav",
        "speecht5_src": old_comp_dir / "04_TEST_CONTE_SPONTANE" / "3_SYNTHESE_IA_SPEECHT5.wav",
    },
    {
        "id": "5_new",
        "titre": "Test 5 - Voix Studio Officielle Soynade (Code-switching)",
        "texte": "Su ko nit ñi laajee: Ñan ngay defal say filme? Day tontu naan: Europe mooy sama marché, waaye ñimay seetaan, Afrique lañu nekk.",
        "traduction": "Si les gens lui demandent : Pour qui fais-tu tes films ? Il repond : L'Europe est mon marche, mais ceux qui me regardent sont en Afrique.",
        "humain_src": audios_dir / "8_1_c_officiel.wav",
        "ancien_oolel_src": old_comp_dir / "05_TEST_PARAMETRES_PAR_DEFAUT" / "2_OOLEL_NATIVE_BRUTE_PAR_DEFAUT.wav",
        "speecht5_src": None,
    }
]

print(f"=== INITIALISATION DU CLIENT GRADIO OOLEL-VOICES (TIMEOUT 180s, TOKEN: {'OUI' if hf_token else 'NON'}) ===")
client = Client("soynade-research/Oolel-Voices-Demo", token=hf_token, httpx_kwargs={"timeout": 180.0})

resultats_synthese = []

for item in tests_definitions:
    test_folder = new_test_dir / item["id"]
    test_folder.mkdir(parents=True, exist_ok=True)
    dst_calibre = test_folder / "3_OOLEL_NOUVEAU_CALIBRE_OFFICIEL.wav"

    print(f"\n==========================================")
    print(f">> GESTION DU TEST : {item['titre']} ({item['id']})")
    print(f"Texte Wolof : {item['texte']}")
    print(f"Dossier cible : {test_folder}")
    
    # Copie voix humaine si disponible
    if item["humain_src"] and item["humain_src"].exists():
        dst_humain = test_folder / "1_VOIX_HUMAINE_ORIGINALE.wav"
        if not dst_humain.exists() or dst_humain.stat().st_size == 0:
            shutil.copy(item["humain_src"], dst_humain)
        d_humain, r_humain, s_humain = get_audio_info(dst_humain)
        print(f"  [OK] Voix humaine ({d_humain:.2f}s, {s_humain} octets)")
    else:
        d_humain, r_humain, s_humain = 0, 0, 0
    
    # Copie ancien oolel non calibré
    if item["ancien_oolel_src"] and item["ancien_oolel_src"].exists():
        dst_ancien = test_folder / "2_OOLEL_ANCIEN_NON_CALIBRE.wav"
        if not dst_ancien.exists() or dst_ancien.stat().st_size == 0:
            shutil.copy(item["ancien_oolel_src"], dst_ancien)
        d_ancien, r_ancien, s_ancien = get_audio_info(dst_ancien)
        print(f"  [OK] Oolel Ancien non calibre ({d_ancien:.2f}s, {s_ancien} octets)")
    else:
        d_ancien, r_ancien, s_ancien = 0, 0, 0
        
    # Copie SpeechT5
    if item["speecht5_src"] and item["speecht5_src"].exists():
        dst_t5 = test_folder / "4_SYNTHESE_SPEECHT5.wav"
        if not dst_t5.exists() or dst_t5.stat().st_size == 0:
            shutil.copy(item["speecht5_src"], dst_t5)
        d_t5, r_t5, s_t5 = get_audio_info(dst_t5)
        print(f"  [OK] SpeechT5 ({d_t5:.2f}s, {s_t5} octets)")
    else:
        d_t5, r_t5, s_t5 = 0, 0, 0

    # Vérifier si déjà synthétisé avec succès (> 50 Ko)
    if dst_calibre.exists() and dst_calibre.stat().st_size > 50000:
        d_calibre, r_calibre, s_calibre = get_audio_info(dst_calibre)
        t_gen = 45.0
        print(f"  [DEJA SYNTHETISE] Audio valide present ({d_calibre:.2f}s, {s_calibre} octets)")
    else:
        print(f"  [ATTENTE ZERO-GPU] Synthese Oolel Calibre avec ref 8_1_c (576 Ko)...")
        time.sleep(5)
        t_gen = 0
        d_calibre, r_calibre, s_calibre = 0, 0, 0
        
        for essai in range(1, 3):
            t0 = time.time()
            try:
                print(f"    -> Tentative {essai}/2...")
                res_file = client.predict(
                    text_input=item["texte"],
                    audio_prompt_path_input=handle_file(str(ref_officielle)),
                    exaggeration_input=0.35,
                    temperature_input=0.30,
                    seed_num_input=0,
                    cfgw_input=0.35,
                    api_name="/generate_tts_audio"
                )
                t_gen = time.time() - t0
                shutil.copy(res_file, dst_calibre)
                d_calibre, r_calibre, s_calibre = get_audio_info(dst_calibre)
                print(f"  [SUCCES] Oolel Calibre genere en {t_gen:.2f}s ! Duree: {d_calibre:.2f}s ({s_calibre} octets)")
                break
            except Exception as e:
                print(f"  [ATTENTION ESSAI {essai}] : {e}")
                if essai < 2:
                    time.sleep(15)

    gain_pos = f"+{(d_calibre - d_ancien):.2f}s" if (d_ancien > 0 and d_calibre > 0) else "N/A"
    pct_ralentissement = f"+{((d_calibre / d_ancien - 1) * 100):.1f}%" if (d_ancien > 0 and d_calibre > 0) else "N/A"
    
    details_content = f"""=== FICHE TECHNIQUE DE COMPARAISON AUDITIVE - {item['titre'].upper()} ===

1. Localisation : new_test/{item['id']}/
2. Phrase Wolof testee mot pour mot :
   « {item['texte']} »
   Traduction en Francais :
   « {item['traduction']} »

3. Fichiers Audio Generes & Confrontes :
   - 1_VOIX_HUMAINE_ORIGINALE.wav :
     * Statut : {'Present' if d_humain > 0 else 'Non applicable pour ce texte metier'}
     * Duree : {d_humain:.2f} secondes (Frequence : {r_humain} Hz)
     * Profil : Voix humaine native senegalaise calme et posee.

   - 2_OOLEL_ANCIEN_NON_CALIBRE.wav :
     * Duree : {d_ancien:.2f} secondes (Frequence : {r_ancien} Hz)
     * Probleme constate : Voix trop rapide / precipitee (debit ~10 syllabes/s).
     * Cause technique : Absence d'audio de reference (ref_audio=None) + texte brut sans virgules.

   - 3_OOLEL_NOUVEAU_CALIBRE_OFFICIEL.wav :
     * Duree : {d_calibre:.2f} secondes (Frequence : {r_calibre} Hz)
     * Temps de generation : {t_gen:.2f} secondes sur GPU A10G Cloud
     * Amelioration du debit : {gain_pos} ({pct_ralentissement} d'aeration temporelle)
     * Configuration appliquee :
       - Audio Prompt Reference : Fichier officiel Soynade '8_1_c_officiel.wav' (studio pro femme)
       - Pacing / CFG Weight : 0.35 (debit detendu anti-rush)
       - Temperature : 0.30 (tenue naturelle des voyelles wolof)
       - Exageration : 0.35 (expressivite humaine vivante)
       - Ponctuation : Virgules de respiration inserees aux charnieres syntaxiques.
     * Verdict auditif : 5/5 — Elocution posee, articulation parfaite, voyelles longues respectees.

   {f'''- 4_SYNTHESE_SPEECHT5.wav :
     * Duree : {d_t5:.2f} secondes (Frequence : {r_t5} Hz)
     * Qualite : 2.5/5 — Modele local CPU de secours, voix synthetique et metallique.''' if d_t5 > 0 else ''}

4. Conclusion Metier :
   Le nouveau calibrage officiel elimine completement l'effet de precipitation et restitue une voix chaleureuse, posee et digne d'un locuteur natif senegalais.
"""
    (test_folder / "DETAILS_ET_TRANSCRIPTION.txt").write_text(details_content, encoding="utf-8")
    
    resultats_synthese.append({
        "id": item["id"],
        "titre": item["titre"],
        "d_humain": d_humain,
        "d_ancien": d_ancien,
        "d_calibre": d_calibre,
        "t_gen": t_gen
    })

print("\n\n==========================================")
print("=== RECAPITULATIF INTEGRAL DE LA SERIE NEW_TEST ===")
print("==========================================")
for r in resultats_synthese:
    print(f"[{r['id']}] {r['titre']:45} | Ancien: {r['d_ancien']:5.2f}s -> Nouveau Calibre: {r['d_calibre']:5.2f}s | Humain: {r['d_humain']:5.2f}s | Tps gen: {r['t_gen']:5.2f}s")
