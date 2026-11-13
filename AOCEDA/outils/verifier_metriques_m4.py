import re
from pathlib import Path

rapport_path = Path(__file__).resolve().parent.parent.parent / "docs/audits/RAPPORT_TRADUCTION.md"
content = rapport_path.read_text(encoding="utf-8")

pattern_row = re.compile(r"\|\s*\*\*(TC-[A-Z]+-\d+)\*\*\s*\|\s*`?([a-zA-Z0-9_]+)`?\s*\|\s*«\s*([^»]+?)\s*»\s*\|\s*([^|]+?)\s*\|\s*`([^`]+?)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
matches = pattern_row.findall(content)

print(f"Total test cases: {len(matches)}")

def parse_eval(eval_str):
    """
    Exemples:
    $M_{\text{arith}}=0$ (« 3 ou 4 »)
    $M_{\text{lex}}=0$ (« dollars »)
    $M_{\text{arith}}=1$ (entier OK)
    $M_{\text{lex}}=1, M_{\text{sens}}=1$
    $M_{\text{sens}}=0.5$ (« 8 a.m. »)
    $M_{\text{arith}}=1, M_{\text{lex}}=0$
    $M_{\text{neg}}=0$ (« oui ou oui »)
    """
    res = {}
    # default values: if not mentioned, is it 1 or what?
    # Let's inspect all explicit mentions
    matches_m = re.findall(r"M_{\\text{([a-z]+)}}=([0-9.]+)", eval_str)
    for k, v in matches_m:
        res[k] = float(v)
    return res

cases_by_theme = {}

for m in matches:
    tc_id, intention, phrase_fr, entites, bci_cible, eval_sans, eval_avec = m
    theme = tc_id.split("-")[1]
    if theme not in cases_by_theme:
        cases_by_theme[theme] = []
    cases_by_theme[theme].append({
        "id": tc_id,
        "eval_sans_str": eval_sans.strip(),
        "parsed_sans": parse_eval(eval_sans),
        "eval_avec_str": eval_avec.strip(),
        "parsed_avec": parse_eval(eval_avec)
    })

print("\n--- DÉTAIL DES ÉVALUATIONS PAR THÈME ---")
for theme, cases in cases_by_theme.items():
    print(f"\nThème {theme} ({len(cases)} cas):")
    for c in cases:
        print(f"  {c['id']}: sans='{c['eval_sans_str']}' -> {c['parsed_sans']}")
