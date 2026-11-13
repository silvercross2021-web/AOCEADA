import re
from pathlib import Path

rapport_path = Path(__file__).resolve().parent.parent.parent / "docs/audits/RAPPORT_TRADUCTION.md"
content = rapport_path.read_text(encoding="utf-8")

pattern_row = re.compile(r"\|\s*\*\*(TC-[A-Z]+-\d+)\*\*\s*\|\s*`?([a-zA-Z0-9_]+)`?\s*\|\s*«\s*([^»]+?)\s*»\s*\|\s*([^|]+?)\s*\|\s*`([^`]+?)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
matches = pattern_row.findall(content)

print("Checking arithmetic values:")
# If 27 out of 64 had arith=1:
print(f"27 / 64 = {27/64:.4f} ({27/64*100:.2f}%)")

# Let's count how many test cases have negative markers in French
neg_pattern = re.compile(r"\b(ne|n'|pas|plus|jamais|aucun|aucune|rien)\b", re.I)
neg_cases = []
for m in matches:
    tc_id, intention, phrase_fr, entites, bci_cible, eval_sans, eval_avec = m
    if neg_pattern.search(phrase_fr) or "neg" in eval_sans or "Non" in phrase_fr:
        neg_cases.append((tc_id, phrase_fr, eval_sans))

print(f"\nNombre de cas avec négation ou test négatif dans le corpus : {len(neg_cases)}")
for tc_id, fr, ev in neg_cases:
    print(f"  {tc_id}: {fr} | eval: {ev}")

# Look at 11 / 21:
print(f"11 / 21 = {11/21:.4f} ({11/21*100:.2f}%)")
# Look at 33 / 63 or 33 / 64:
# If there are 21 negative cases in total, and 11 passed (or 10 failed and 11 passed):
# 11 / 21 = 52.38% = 52.4%!
