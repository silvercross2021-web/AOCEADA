"""Traduction + synthèse vocale français -> dioula pour de LONGS textes, via la
démo publique LAMIA de LAfricaMobile (https://translate.lafricamobile.com/).

CONTEXTE : la démo publique plafonne à 300 caractères par requête. D'après
LAfricaMobile (contact direct de l'auteur, pas d'API gratuite accordée aux
étudiants), la méthode admise pour un usage étudiant/prototype est de découper
le texte en tranches qui respectent cette limite et d'enchaîner les appels —
PAS de contourner la limite elle-même. Ce script automatise exactement ça,
avec une pause entre chaque appel pour rester à un rythme raisonnable (pas de
rafale). Réservé aux tests/démo du mémoire — pas un client officiel de l'API.

Usage :
    python scripts/lamia_dioula_test.py "Un long texte en français..."
    python scripts/lamia_dioula_test.py --file mon_texte.txt

Sortie : lamia_dioula_output.txt (texte dioula complet) et
         lamia_dioula_output.wav (audio dioula complet, tranches recollées).

Découverte de l'endpoint : lecture du JS public de la page (script.js), aucune
route privée/cachée — POST /translate (form-data: inLang, outLang, text),
réponse { translatedText, vocalizeText (URL .wav) }.
"""
import argparse
import re
import sys
import time
import wave
from pathlib import Path

import requests

ENDPOINT = "https://translate.lafricamobile.com/translate"
MAX_CHARS = 300  # limite imposée par LAfricaMobile sur la démo publique
DELAY_ENTRE_APPELS = 1.5  # secondes — rythme humain, pas une rafale de bot
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AOCEDA-memoire-test/1.0)"}


def decouper_en_tranches(texte, max_chars=MAX_CHARS):
    """Découpe `texte` en tranches <= max_chars, aux frontières de phrases
    quand c'est possible (jamais au milieu d'un mot)."""
    phrases = re.split(r'(?<=[.!?])\s+', texte.strip())
    tranches = []
    courante = ""
    for phrase in phrases:
        candidate = (courante + " " + phrase).strip() if courante else phrase
        if len(candidate) <= max_chars:
            courante = candidate
            continue
        if courante:
            tranches.append(courante)
        if len(phrase) <= max_chars:
            courante = phrase
        else:
            # Phrase seule trop longue : découpe brute mot par mot.
            mots = phrase.split(' ')
            bloc = ""
            for mot in mots:
                cand = (bloc + " " + mot).strip() if bloc else mot
                if len(cand) <= max_chars:
                    bloc = cand
                else:
                    if bloc:
                        tranches.append(bloc)
                    bloc = mot
            courante = bloc
    if courante:
        tranches.append(courante)
    return tranches


def traduire_tranche(texte):
    resp = requests.post(
        ENDPOINT,
        headers=HEADERS,
        files={},  # force multipart comme le fait le site (FormData)
        data={"inLang": "français", "outLang": "dioula", "text": texte},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("translatedText", ""), data.get("vocalizeText")


def telecharger_wav(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.content


def concatener_wav(chemins_octets, sortie):
    """Concatène plusieurs WAV (même format PCM attendu, tous issus du même
    moteur LAMIA) en un seul fichier, via le module standard `wave`."""
    import io
    params = None
    frames = []
    for octets in chemins_octets:
        with wave.open(io.BytesIO(octets), 'rb') as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
    with wave.open(str(sortie), 'wb') as out:
        out.setparams(params)
        for f in frames:
            out.writeframes(f)


def main():
    # Console Windows (cp1252) : les caractères dioula (ɛ, ɔ, ŋ...) plantent
    # l'affichage sans ça — force l'UTF-8 en sortie, indépendamment de l'OS.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("texte", nargs="?", help="Texte français à traduire/vocaliser en dioula")
    parser.add_argument("--file", help="Fichier texte à lire au lieu de l'argument direct")
    parser.add_argument("--out-prefix", default="lamia_dioula_output", help="Préfixe des fichiers de sortie")
    args = parser.parse_args()

    if args.file:
        texte = Path(args.file).read_text(encoding="utf-8")
    elif args.texte:
        texte = args.texte
    else:
        parser.error("Fournis un texte en argument ou --file <chemin>")
        return

    tranches = decouper_en_tranches(texte)
    print(f"Texte découpé en {len(tranches)} tranche(s) (limite {MAX_CHARS} caractères/appel).")

    textes_traduits = []
    audios = []
    for i, tranche in enumerate(tranches, 1):
        print(f"  [{i}/{len(tranches)}] ({len(tranche)} car.) -> traduction...")
        try:
            traduit, audio_url = traduire_tranche(tranche)
        except requests.RequestException as e:
            print(f"    Échec sur cette tranche : {e}", file=sys.stderr)
            continue
        print(f"    -> {traduit!r}")
        textes_traduits.append(traduit)
        if audio_url:
            audios.append(telecharger_wav(audio_url))
        if i < len(tranches):
            time.sleep(DELAY_ENTRE_APPELS)

    texte_final = " ".join(textes_traduits)
    out_txt = Path(f"{args.out_prefix}.txt")
    out_txt.write_text(texte_final, encoding="utf-8")
    print(f"\nTexte dioula complet -> {out_txt}")

    if audios:
        out_wav = Path(f"{args.out_prefix}.wav")
        concatener_wav(audios, out_wav)
        print(f"Audio dioula complet -> {out_wav}")
    else:
        print("Aucun audio récupéré.")


if __name__ == "__main__":
    main()
