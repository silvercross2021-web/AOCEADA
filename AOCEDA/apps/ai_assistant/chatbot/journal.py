"""Journal de fonctionnement de l'assistant : une ligne JSON par échange (question, réponse, langue, temps, moteur...),
dans journaux/journal.jsonl du dossier de l'assistant ; archivé et recommencé au-delà de 5 Mo."""
import json
import threading
from datetime import datetime

from .config import JOURNAUX

JOURNAL = JOURNAUX / "journal.jsonl"
JOURNAL_MAX_OCTETS = 5_000_000
_verrou = threading.Lock()


def journaliser(entree):
    with _verrou:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        if JOURNAL.exists() and JOURNAL.stat().st_size > JOURNAL_MAX_OCTETS:
            JOURNAL.replace(JOURNAL.with_name(f"journal_{datetime.now():%Y%m%d_%H%M%S}.jsonl"))
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"heure": datetime.now().isoformat(timespec="seconds"), **entree}, ensure_ascii=False,
                               default=str) + "\n")
