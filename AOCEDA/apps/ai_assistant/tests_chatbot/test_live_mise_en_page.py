"""Mise en page de l'appel Live : le titre d'état, le personnage et la carte ne passent jamais sur les sous-titres.

Vu par le client (zoom du navigateur, petite fenêtre) : « AOCEDA vous répond » se superposait aux sous-titres. La zone centrale
se règle maintenant sur la hauteur disponible (unités de conteneur). Les mesures réelles dans un navigateur (12 tailles, avec et
sans carte, champ « Écrire » ouvert) sont dans docs/refonte/00-journal.md ; ici on garde les règles qui l'assurent.
"""
from pathlib import Path

CSS = (Path(__file__).resolve().parents[3] / "static" / "css" / "assistant.css").read_text(encoding="utf-8")


def test_la_zone_centrale_est_un_conteneur_dont_la_hauteur_regle_le_personnage_et_la_carte():
    assert ".live:not(.compact) .live-centre { container-type: size; }" in CSS
    assert "--perso: clamp(72px, min(250px, 58vw, 100cqh - 60px), 250px)" in CSS            # perso borné par la hauteur
    assert ".live:not(.compact) .live-perso { width: var(--perso); }" in CSS
    assert ".live.avec-carte:not(.compact) .live-perso { width: var(--perso); }" in CSS      # la règle téléphone ne le force plus à 150 px
    assert "max-height: 100cqh; overflow: auto" in CSS and "calc(100cqh - var(--perso) - 52px)" in CSS   # la carte défile au lieu de déborder


def test_fenetre_tres_basse_sous_titres_plus_courts_et_blocs_equilibres():
    bloc = CSS[CSS.index("@media (max-height: 560px)"):]
    bloc = bloc[:bloc.index("}\n}") + 3] if "}\n}" in bloc else bloc[:bloc.index("}\r\n}") + 4]
    assert "-webkit-line-clamp: 1" in bloc and "-webkit-line-clamp: 2" in bloc
    assert CSS.count("{") == CSS.count("}")                                                  # aucune accolade perdue
    # ce bloc est au premier niveau (il vaut pour toutes les largeurs), pas dans la règle « max-width: 899px »
    avant = CSS[:CSS.index("@media (max-height: 560px)")]
    assert avant.count("{") == avant.count("}")
