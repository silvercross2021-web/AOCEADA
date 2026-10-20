"""Cohérence de la page « Tests et rapports » : essai de clonage de voix baoulé et catalogue.

Garde-fous : chaque audio cité existe, les moyennes se recalculent, chaque fichier de rapports/ est
référencé dans le catalogue. Aucun réseau, aucun modèle.
"""
import json
import re
from pathlib import Path

RAPPORTS = Path(__file__).resolve().parent.parent / "rapports"
RESULTATS = RAPPORTS / "resultats"
AUDIOS = RAPPORTS / "audios"


def _lire(nom):
    return json.loads((RESULTATS / nom).read_text(encoding="utf-8"))


def test_voix_baoule_audios_existent():
    d = _lire("voix_baoule.json")
    fichiers = [m["fichier"] for m in d["modeles"] if m.get("fichier")]
    for ph in d["phrases"]:
        fichiers += [v["fichier"] for v in ph["versions"]]
    for p in d["production"]:
        fichiers += [p[g]["fichier"] for g in ("femme", "homme") if p.get(g)]
    assert fichiers
    for f in fichiers:
        assert re.fullmatch(r"[A-Za-z0-9_./ -]+", f), f
        assert (AUDIOS / f).is_file(), f


def test_voix_baoule_phrases_completes():
    d = _lire("voix_baoule.json")
    assert len(d["phrases"]) == 8
    for ph in d["phrases"]:
        assert ph["texte"].strip() and ph["sens_fr"].strip()
        assert [v["id"] for v in ph["versions"]] == ["A", "B", "C", "D"]
        for v in ph["versions"]:
            assert v["retranscription"].strip()


def test_voix_baoule_moyennes_recalculees():
    d = _lire("voix_baoule.json")
    for k in "ABCD":
        valeurs = [v["lettres_fausses_pct"] for ph in d["phrases"] for v in ph["versions"] if v["id"] == k]
        assert abs(sum(valeurs) / len(valeurs) - d["moyennes"][k]["lettres_fausses_pct"]) < 0.15, k


def test_catalogue_reference_chaque_fichier():
    cat = _lire("catalogue.json")
    cites = {f for t in cat["themes"] for r in t["rapports"] for f in r["fichiers"]}
    assert cat["nombre_rapports"] == sum(len(t["rapports"]) for t in cat["themes"])
    for sous in ("resultats", "audios", "documentation"):
        for p in (RAPPORTS / sous).rglob("*"):
            if p.is_file():
                rel = p.relative_to(RAPPORTS).as_posix()
                if rel == "resultats/catalogue.json":
                    continue
                assert any(rel == c or rel.startswith(c.rstrip("/") + "/") for c in cites), rel
