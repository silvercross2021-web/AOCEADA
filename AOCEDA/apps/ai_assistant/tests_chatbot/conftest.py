"""Réglages communs des tests de l'assistant (repris du laboratoire, sans Internet).

Le dossier de l'assistant (CHATBOT_DOSSIER_IA) est, pendant les tests, un dossier TEMPORAIRE : les tests n'écrivent
jamais dans la vraie mémoire des conversations, les voix déjà faites, les journaux ou le compte du GPU. Ses modèles sont
un lien vers les vrais (lecture seule) : les quelques essais qui écoutent vraiment du dioula ou du baoulé les utilisent
s'ils sont installés, et se mettent de côté sinon.

GPU de la voix baoulé (Cerebrium) COUPÉ (06/10/2026) : sinon les tests baoulé réveilleraient la vraie machine (lent et
payant) ; les tests du GPU (test_voix_gpu.py) le rallument eux-mêmes avec un Cerebrium simulé.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

AOCEDA = Path(__file__).resolve().parents[3]


def _dossier_ia_temporaire():
    from decouple import AutoConfig
    reel = Path(AutoConfig(search_path=str(AOCEDA))("CHATBOT_DOSSIER_IA", default="") or AOCEDA / "donnees_ia")
    tmp = Path(tempfile.mkdtemp(prefix="aoceda_essais_ia_"))
    if (reel / "modeles").is_dir():
        try:
            if sys.platform == "win32":
                import _winapi
                _winapi.CreateJunction(str(reel / "modeles"), str(tmp / "modeles"))
            else:
                os.symlink(reel / "modeles", tmp / "modeles", target_is_directory=True)
        except OSError:
            pass
    return tmp


DOSSIER_ESSAIS = _dossier_ia_temporaire()
os.environ["CHATBOT_DOSSIER_IA"] = str(DOSSIER_ESSAIS)
os.environ["CHATBOT_VOIX_BAOULE_GPU"] = "0"

import pytest  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    lien = DOSSIER_ESSAIS / "modeles"
    try:
        if lien.is_symlink() or (sys.platform == "win32" and lien.exists()):
            os.rmdir(lien) if sys.platform == "win32" else lien.unlink()     # le lien seulement, jamais les modèles
    except OSError:
        return
    shutil.rmtree(DOSSIER_ESSAIS, ignore_errors=True)


@pytest.fixture(autouse=True)
def _base(transactional_db):
    """Base de test : les vues tournent dans des fils de calcul (réponse en flux) qui doivent voir le compte du test."""


@pytest.fixture(autouse=True)
def _fichiers_isoles(tmp_path, monkeypatch):
    """Chaque test a ses propres journal, erreurs et compte du GPU (audit du 09/10/2026)."""
    from apps.ai_assistant.chatbot import erreurs, journal, voix_gpu
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr(erreurs, "FICHIER", tmp_path / "erreurs.log")
    monkeypatch.setattr(voix_gpu, "FICHIER_BUDGET", tmp_path / "gpu_budget.json")
    monkeypatch.setattr(voix_gpu, "_budget", {"jour": None, "minutes": set(), "verrou": voix_gpu._budget["verrou"]})
    from apps.ai_assistant.chatbot import securite
    securite.remettre_a_zero()
