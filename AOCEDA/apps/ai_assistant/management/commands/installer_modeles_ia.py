"""Installe les modèles de l'assistant IA (~2,1 Go) dans son dossier (réglage CHATBOT_DOSSIER_IA du .env ; par défaut
AOCEDA/donnees_ia, jamais envoyé sur GitHub) : chaque fichier est téléchargé depuis sa source OFFICIELLE, puis son
empreinte (SHA-256) est vérifiée : ce sont exactement les fichiers validés au laboratoire. Un modèle déjà présent n'est
pas retéléchargé.

    python manage.py installer_modeles_ia                 tout installer (ce qui manque)
    python manage.py installer_modeles_ia --verifier      état seulement (rien n'est téléchargé)
    python manage.py installer_modeles_ia --depuis <dossier>   copier depuis un dossier (clé USB, autre PC) au lieu de télécharger
    python manage.py installer_modeles_ia --seulement whisper/tiny whisper/small

Sans un modèle, l'assistant marche quand même : seule la fonction concernée se désactive (écoute du dioula, du baoulé,
voix de secours) ; Whisper, lui, est indispensable au micro.
"""
import hashlib
import shutil
import tarfile
import time
import zipfile
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

HF = "https://huggingface.co/{depot}/resolve/main/{fichier}"
SHERPA = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
          "sherpa-onnx-omnilingual-asr-1600-languages-1B-ctc-v2-int8-2026-02-05.tar.bz2")
KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/{fichier}"

# dossier -> (à quoi il sert, source, {fichier: (taille en octets, SHA-256)})
#   source : ("fichiers", gabarit d'adresse avec {fichier})  ou  ("archive", adresse d'une archive .tar.bz2 / .zip)
#            ou ("reglage", nom du réglage qui donne l'adresse de l'archive)
CATALOGUE = {
    "whisper/tiny": ("micro : reconnaît la langue parlée (Whisper tiny, MIT)",
                     ("fichiers", HF.replace("{depot}", "Systran/faster-whisper-tiny")), {
        "model.bin": (75538270, "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"),
        "config.json": (2249, "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8"),
        "tokenizer.json": (2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
        "vocabulary.txt": (459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}),
    "whisper/small": ("micro : transcrit le français, l'anglais... (Whisper small, MIT)",
                      ("fichiers", HF.replace("{depot}", "Systran/faster-whisper-small")), {
        "model.bin": (483546902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
        "config.json": (2370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
        "tokenizer.json": (2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
        "vocabulary.txt": (459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}),
    "omnilingual-1b-ctc-v2-int8": ("micro : écoute du DIOULA (Meta Omnilingual 1B, sherpa-onnx, Apache 2.0)",
                                   ("archive", SHERPA), {
        "model.int8.onnx": (980149208, "558253f9772a8ff1c77705f4bd3a4118c81b7c9086819e2667d20420433b980d"),
        "tokens.txt": (100918, "14aab5cabf425ea1a5efdce2bcb74a24f836947baeab52cfb720eacd28492974"),
        "LICENSE": (581, "a70a523bafbb595c2844104feb313d204904dac91c3d186c05f22a10a71c7a94"),
        "README.md": (13928, "8462bbca4935ffab8745b047fe6baab9b0329805818e58a926f0f7306af410fd")}),
    "omniasr-300m-baoule-int8": ("micro : écoute du BAOULÉ (Omnilingual 300M baoulé de Tree-AI, Apache 2.0, compressé au "
                                 "laboratoire)", ("reglage", "CHATBOT_SOURCE_ECOUTE_BAOULE"), {
        "model.int8.onnx": (327365239, "0ea771bfe994376c494998f01b7793c96d1b5e5dc21a915946e906f79481883d"),
        "tokens.txt": (96235, "89f811af4846fe99949136f0d061b387b6d906cb2b231ea6755232b90d597861"),
        "config.json": (1968, "98ced82637c989cb8a7b76ee91efaad896c793c1eecbd62817888f3745ca1a97"),
        "preprocessor_config.json": (257, "617bd0950f8cc9ac4062e8c73a7be60305ca5790a243df55fa6f44fb671b55b1"),
        "README.md": (601, "1cc45da0a631cd9df0fd552fec56bfc6dd80d4a25782acfd9871eca1eebc940d")}),
    "kokoro": ("voix de SECOURS en français et anglais (Kokoro v1.0, Apache 2.0)", ("fichiers", KOKORO), {
        "kokoro-v1.0.onnx": (325532387, "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
        "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d")}),
}
INDISPENSABLES = ("whisper/tiny", "whisper/small")


class SansSource(CommandError):
    """Modèle sans adresse de téléchargement (réglage du .env vide) : relancer ne sert à rien tant qu'elle manque."""


def empreinte(f):
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for bloc in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def mo(octets):
    return f"{octets / 1e6:,.0f} Mo".replace(",", " ")


class Command(BaseCommand):
    help = "Installe (ou vérifie) les modèles de l'assistant IA dans son dossier, avec vérification des empreintes."

    def add_arguments(self, parser):
        parser.add_argument("--verifier", action="store_true", help="état des modèles seulement, rien n'est téléchargé")
        parser.add_argument("--depuis", help="copier les modèles depuis ce dossier (mêmes sous-dossiers) au lieu de télécharger")
        parser.add_argument("--seulement", nargs="+", choices=list(CATALOGUE), help="seulement ces modèles")

    # ── outils ──
    def ecrire(self, texte, style=None):
        self.stdout.write(style(texte) if style else texte)

    def complet(self, dossier, fichiers, vite=True):
        """Le modèle est-il là ? vite : tailles seulement (empreintes vérifiées à l'installation et avec --verifier)."""
        for nom, (taille, sha) in fichiers.items():
            f = dossier / nom
            if not f.is_file() or f.stat().st_size != taille or (not vite and empreinte(f) != sha):
                return False
        return True

    def telecharger(self, adresse, cible, taille=None):
        """Téléchargement en flux vers un fichier .part (renommé à la fin), avec l'avancement."""
        part = cible.with_name(cible.name + ".part")
        with requests.get(adresse, stream=True, timeout=(15, 120), allow_redirects=True) as r:
            if r.status_code != 200:
                raise CommandError(f"téléchargement refusé ({r.status_code}) : {adresse}")
            total = taille or int(r.headers.get("content-length") or 0)
            lu, t0, dernier = 0, time.time(), 0.0
            with open(part, "wb") as fh:
                for bloc in r.iter_content(4 * 1024 * 1024):
                    fh.write(bloc)
                    lu += len(bloc)
                    if total and time.time() - dernier > 3:
                        dernier = time.time()
                        vitesse = lu / max(0.1, time.time() - t0)
                        self.ecrire(f"      {cible.name} : {lu * 100 // total} % ({mo(lu)} / {mo(total)}, {mo(vitesse)}/s)")
        part.replace(cible)

    def verifier_fichier(self, f, taille, sha):
        if f.stat().st_size != taille or empreinte(f) != sha:
            f.unlink(missing_ok=True)
            raise CommandError(f"{f.name} : fichier différent de celui validé (taille ou empreinte) ; supprimé, relancez.")

    def extraire(self, archive, dossier, fichiers):
        """Les fichiers attendus, où qu'ils soient dans l'archive (.tar.bz2 ou .zip)."""
        voulus = set(fichiers)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    nom = Path(info.filename).name
                    if nom in voulus and not info.is_dir():
                        with z.open(info) as src, open(dossier / nom, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive, "r:bz2") as t:
                for membre in t:
                    nom = Path(membre.name).name
                    if membre.isfile() and nom in voulus:
                        with t.extractfile(membre) as src, open(dossier / nom, "wb") as dst:
                            shutil.copyfileobj(src, dst)

    # ── installation d'un modèle ──
    def installer(self, nom, source, fichiers, dossier, depuis, tmp):
        dossier.mkdir(parents=True, exist_ok=True)
        if depuis:
            src = Path(depuis) / nom
            for f in fichiers:
                if not (src / f).is_file():
                    raise CommandError(f"{src / f} introuvable")
                shutil.copyfile(src / f, dossier / f)
        elif source[0] == "fichiers":
            for f, (taille, sha) in fichiers.items():
                if (dossier / f).is_file() and (dossier / f).stat().st_size == taille:
                    continue
                self.telecharger(source[1].replace("{fichier}", f), dossier / f, taille)
        else:
            adresse = source[1] if source[0] == "archive" else getattr(settings, source[1], "")
            if not adresse:
                raise SansSource(f"pas d'adresse de téléchargement : le réglage {source[1]} du .env est vide")
            archive = tmp / Path(adresse.split("?")[0]).name
            try:
                self.telecharger(adresse, archive)
                self.ecrire("      extraction…")
                self.extraire(archive, dossier, fichiers)
            finally:
                archive.unlink(missing_ok=True)
        for f, (taille, sha) in fichiers.items():
            if not (dossier / f).is_file():
                raise CommandError(f"{f} absent de la source")
            self.verifier_fichier(dossier / f, taille, sha)

    def handle(self, *args, **o):
        racine = Path(settings.CHATBOT_DOSSIER_IA) / "modeles"
        tmp = Path(settings.CHATBOT_DOSSIER_IA) / "cache" / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        noms = o["seulement"] or list(CATALOGUE)
        total = sum(t for n in noms for t, _ in CATALOGUE[n][2].values())
        self.ecrire(f"Modèles de l'assistant IA -> {racine}  ({mo(total)} au total)")
        manquants, echecs, sans_source = [], [], []
        for nom in noms:
            role, source, fichiers = CATALOGUE[nom]
            dossier = racine / nom
            taille = sum(t for t, _ in fichiers.values())
            if o["verifier"]:
                ok = self.complet(dossier, fichiers, vite=False)
                self.ecrire(f"  {'OK      ' if ok else 'MANQUANT'}  {nom:28} {mo(taille):>8}  {role}",
                            self.style.SUCCESS if ok else self.style.WARNING)
                if not ok:
                    manquants.append(nom)
                continue
            if self.complet(dossier, fichiers):
                self.ecrire(f"  déjà là   {nom:28} {mo(taille):>8}  {role}", self.style.SUCCESS)
                continue
            self.ecrire(f"  installe  {nom:28} {mo(taille):>8}  {role}")
            try:
                self.installer(nom, source, fichiers, dossier, o["depuis"], tmp)
                self.ecrire(f"      vérifié (empreintes identiques au laboratoire)", self.style.SUCCESS)
            except SansSource as e:
                sans_source.append(nom)
                self.ecrire(f"      non installé : {e}", self.style.WARNING)
            except (CommandError, OSError, EOFError, requests.RequestException, tarfile.TarError,
                    zipfile.BadZipFile) as e:
                echecs.append(nom)
                self.ecrire(f"      ÉCHEC : {e}", self.style.ERROR)
        if o["verifier"]:
            if manquants:
                self.ecrire(f"\nÀ installer : {', '.join(manquants)}  ->  python manage.py installer_modeles_ia")
            return
        if sans_source:
            self.ecrire(f"\nPas encore téléchargeable : {', '.join(sans_source)}. L'assistant marche sans, mais un vocal "
                        "en baoulé n'est pas reconnu (il est écouté comme du dioula) ; le baoulé écrit et la voix baoulé "
                        "restent disponibles. "
                        "Quand l'adresse de l'archive est connue, la mettre dans .env (CHATBOT_SOURCE_ECOUTE_BAOULE) puis "
                        "relancer cette commande.", self.style.WARNING)
        if echecs:
            indispensable = [n for n in echecs if n in INDISPENSABLES]
            self.ecrire(f"\nNon installé : {', '.join(echecs)}. Relancez la commande (elle reprend où elle en était)."
                        + (" Sans Whisper, le micro ne marche pas." if indispensable else
                           " L'assistant marche quand même ; seule la fonction concernée est désactivée."),
                        self.style.WARNING)
        elif not sans_source:
            self.ecrire("\nTous les modèles sont installés et vérifiés.", self.style.SUCCESS)
