"""Fabrique les voix B (ancien réglage) et C (nouveau réglage) de chaque phrase sur le service d'essai Cerebrium.
La clé CEREBRIUM_API_KEY est lue dans AOCEDA/.env, jamais affichée.
Lancement (depuis AOCEDA/) : .venv_local\\Scripts\\python.exe ..\\ESSAI_VOIX_BAOULE\\5_OUTILS\\fabriquer_voix.py"""
import base64, json, sys, time
from pathlib import Path
import requests
from decouple import Config, RepositoryEnv

sys.stdout.reconfigure(encoding="utf-8")
E = Path(__file__).resolve().parents[1]
cfg = Config(RepositoryEnv(str(E.parent / "AOCEDA" / ".env")))
CLE, PROJET = cfg("CEREBRIUM_API_KEY"), cfg("CEREBRIUM_PROJECT", default="p-a50fe161")
URL = f"https://api.cerebrium.ai/v4/{PROJET}/voix-baoule-essai"
ENTETES = {"Authorization": f"Bearer {CLE}", "Content-Type": "application/json"}
TOUS = {"B_VOIX_GENEREE_ancien_reglage.wav": ("ancienne", 8), "C_VOIX_GENEREE_nouveau_reglage.wav": ("nouvelle", 32),
        "D_VOIX_GENEREE_voix_CommonVoice.wav": ("commonvoice", 32)}
# sans argument : toutes les versions ; sinon seulement les lettres demandées (ex. « D »)
REGLAGES = {k: v for k, v in TOUS.items() if len(sys.argv) < 2 or k[0] in sys.argv[1]}

t = time.time()
r = requests.post(f"{URL}/reveil", headers=ENTETES, json={}, timeout=300)
print(f"réveil de la machine : {time.time() - t:.0f} s ({r.status_code})")
infos = json.loads((E / "5_OUTILS" / "phrases.json").read_text(encoding="utf-8"))
mesures = []
for p in infos["phrases"]:
    d = E / "3_COMPARAISONS_A_ECOUTER" / p["dossier"]
    for nom, (voix, etapes) in REGLAGES.items():
        t = time.time()
        r = requests.post(f"{URL}/fabriquer", headers=ENTETES, json={"texte": p["texte"], "voix": voix, "etapes": etapes}, timeout=300)
        res = r.json().get("result", r.json())
        if "wav_b64" not in res:
            print(f"ÉCHEC {p['dossier']} {voix} : {str(res)[:200]}"); continue
        (d / nom).write_bytes(base64.b64decode(res["wav_b64"]))
        mesures.append({"dossier": p["dossier"], "fichier": nom, "voix": voix, "etapes": etapes, "calcul_gpu_s": res["calcul_s"],
                        "aller_retour_s": round(time.time() - t, 2), "duree_audio_s": res["audio_s"]})
        print(f"{p['dossier']:38s} {nom[:1]} ({voix}, {etapes} étapes) : calcul {res['calcul_s']:.2f} s, "
              f"aller-retour {time.time() - t:.1f} s, voix de {res['audio_s']} s")
f = E / "4_RESULTATS" / "mesures_fabrication.json"
anciennes = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
garder = [m for m in anciennes if m["fichier"] not in REGLAGES]
f.write_text(json.dumps(garder + mesures, ensure_ascii=False, indent=1), encoding="utf-8")
