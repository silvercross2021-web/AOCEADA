from pathlib import Path

# Let's inspect Table 3.3 numbers:
# Thème 1 (15 cas):
# M_arith: 26.7% -> 4/15 = 26.67%
# M_neg: 100.0% -> 15/15 = 100% (or no negations failed)
# M_lex: 86.7% -> 13/15 = 86.67% (or sum=13.0)
# Score Global Actuel: 62.3%
# Formula: 0.35 * M_arith + 0.30 * M_neg + 0.20 * M_lex + 0.15 * M_sens
# 0.35 * 0.2667 + 0.30 * 1.0 + 0.20 * 0.8667 + 0.15 * M_sens = 62.3%
# Let's solve for M_sens:
# 0.35*0.26667 + 0.30*1.0 + 0.20*0.86667 = 0.09333 + 0.30 + 0.17333 = 0.56667
# Score - 0.56667 = 0.623 - 0.56667 = 0.05633
# 0.05633 / 0.15 = 0.3755 -> M_sens ≈ 0.375 or 5.6/15?

# Let's check Thème 2 (15 cas):
# M_arith: 40.0% -> 6/15 = 40.0%
# M_neg: 33.3% -> 5/15 = 33.3% or 1/3
# M_lex: 43.3% -> 6.5/15 = 43.33%
# Score Global Actuel: 44.8%
# Let's check formula:
# 0.35 * 0.40 + 0.30 * 0.3333 + 0.20 * 0.4333 + 0.15 * M_sens
# = 0.14 + 0.10 + 0.08667 = 0.32667
# 0.448 - 0.32667 = 0.12133 -> 0.12133 / 0.15 = 0.8088 -> M_sens ≈ 80.9% (12/15 = 0.8)

# Let's check Thème 3 (12 cas):
# M_arith: 100.0% -> 12/12 = 100%
# M_neg: 66.7% -> 8/12 = 66.67% (4 failed: CUT-06, CUT-10, CUT-12... wait, 12 - 4 = 8/12 = 66.7%!)
# M_lex: 87.5% -> 10.5/12 = 87.5% (CUT-01 has 0.5, 11 have 1.0 -> 10.5/12 = 87.5%!)
# Score Global Actuel: 82.5%
# 0.35 * 1.0 + 0.30 * (8/12) + 0.20 * (10.5/12) + 0.15 * M_sens
# = 0.35 + 0.20 + 0.175 = 0.725
# 0.825 - 0.725 = 0.100 -> 0.100 / 0.15 = 0.6667 (8/12 = 66.7%)!

# Let's check Thème 4 (12 cas):
# M_arith: 50.0% -> 6/12 = 50.0%
# M_neg: 41.7% -> 5/12 = 41.67% (7 failed negations out of 12! 12 - 7 = 5/12 = 41.67%!)
# M_lex: 91.7% -> 11/12 = 91.67% (NEG-06 has 0.5, 11 have 1 -> wait, 11.5/12 = 95.8%, 11/12 = 91.67%)
# Score Global Actuel: 60.8%
# 0.35 * 0.50 + 0.30 * (5/12) + 0.20 * (11/12) + 0.15 * M_sens
# = 0.175 + 0.125 + 0.18333 = 0.48333
# 0.608 - 0.48333 = 0.12467 -> 0.12467 / 0.15 = 0.8311 (10/12 = 0.8333)!

# Let's check Thème 5 (10 cas):
# M_arith: 0.0% -> 0/10 = 0%
# M_neg: 20.0% -> 2/10 = 20.0%
# M_lex: 85.0% -> 8.5/10 = 85.0%
# Score Global Actuel: 38.5%
# 0.35 * 0.0 + 0.30 * 0.20 + 0.20 * 0.85 + 0.15 * M_sens
# = 0.0 + 0.06 + 0.17 = 0.23
# 0.385 - 0.23 = 0.155 -> 0.155 / 0.15 = 1.0333 ≈ 1.0!

# Now let's check the Consolidated Average (64 cas):
# Is Moyenne Consolidée the unweighted average of the 5 themes, or weighted by number of cases?
# Let's compute both:
themes_weights = [15, 15, 12, 12, 10]
m_arith_vals = [26.6667, 40.0, 100.0, 50.0, 0.0]
m_neg_vals = [100.0, 33.3333, 66.6667, 41.6667, 20.0]
m_lex_vals = [86.6667, 43.3333, 87.5, 91.6667, 85.0]
score_vals = [62.3, 44.8, 82.5, 60.8, 38.5]

print("=== VÉRIFICATION DE LA MOYENNE CONSOLIDÉE (PONDÉRÉE PAR LE NOMBRE DE CAS) ===")
total_cases = sum(themes_weights)
weighted_arith = sum(w * v for w, v in zip(themes_weights, m_arith_vals)) / total_cases
weighted_neg = sum(w * v for w, v in zip(themes_weights, m_neg_vals)) / total_cases
weighted_lex = sum(w * v for w, v in zip(themes_weights, m_lex_vals)) / total_cases
weighted_score = sum(w * v for w, v in zip(themes_weights, score_vals)) / total_cases

print(f"M_arith calculé pondéré : {weighted_arith:.2f}% | Rapport annonce : 42,2%")
print(f"M_neg calculé pondéré   : {weighted_neg:.2f}% | Rapport annonce : 52,4%")
print(f"M_lex calculé pondéré   : {weighted_lex:.2f}% | Rapport annonce : 78,8%")
print(f"Score calculé pondéré   : {weighted_score:.2f}% | Rapport annonce : 57,8%")

# Unweighted average:
simple_arith = sum(m_arith_vals) / 5
simple_neg = sum(m_neg_vals) / 5
simple_lex = sum(m_lex_vals) / 5
simple_score = sum(score_vals) / 5
print("\n=== MOYENNE SIMPLE (NON PONDÉRÉE) ===")
print(f"M_arith simple : {simple_arith:.2f}%")
print(f"M_neg simple   : {simple_neg:.2f}%")
print(f"M_lex simple   : {simple_lex:.2f}%")
print(f"Score simple   : {simple_score:.2f}%")
