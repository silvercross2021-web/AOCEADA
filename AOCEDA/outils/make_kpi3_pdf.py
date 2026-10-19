import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aoceda.settings')
django.setup()

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from apps.analytics import pdf as pdfdoc

def build_kpi3_pdf():
    pdf_filename = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'Memoire_IIT_BROU_KABLAN',
        'Rapport_Evaluation_KPI3_Pertinence_IA_Final.pdf'
    )

    st = pdfdoc.get_styles()
    el = []

    # Cartes d'identification du document
    carte_eval = [
        ("Projet", "AOCEDA (Système IoT & IA d'énergie)"),
        ("Établissement", "Institut International de Technologie (IIT)"),
        ("Indicateur", "KPI 3 — Pertinence de l'Assistant IA"),
        ("Statut KPI 3", "ATTEINT (84 % mesuré vs >= 80 % requis)"),
    ]
    carte_doc = [
        ("Référence", "AOC-KPI3-20260725-IIT-84PCT"),
        ("Date d'édition", "25/07/2026"),
        ("Échantillon", "Panel restreint (5 utilisateurs réels)"),
        ("Méthodologie", "Évaluation 5 critères x 4 points"),
    ]

    el.append(pdfdoc.panneau_identification(
        [("Évaluation & Contexte", carte_eval), ("Document & Référence", carte_doc)], st
    ))

    # Section 1: Contexte et Objectifs
    el.extend(pdfdoc.section("1. Contexte et Objectifs de l'Évaluation", st))
    text_s1 = (
        "Dans le cadre du cahier des charges du projet <b>AOCEDA</b>, l'indicateur clé de performance "
        "<b>KPI 3</b> fixe une exigence de pertinence et d'accessibilité pour l'Assistant IA conversationnel :<br/>"
        "• <b>Objectif fixé :</b> au moins 80 % de réponses jugées pertinentes et utiles.<br/>"
        "• <b>Résultat mesuré en laboratoire :</b> <b>84 % de satisfaction globale</b>.<br/>"
        "Cette évaluation valide l'hypothèse <b>H3</b> du mémoire : l'information énergétique restituée par l'IA "
        "doit être compréhensible, personnalisée et immédiatement utile pour un ménage ivoirien non spécialiste, sans formation."
    )
    el.append(Paragraph(text_s1, st['body']))

    # Section 2: Justification du Panel
    el.extend(pdfdoc.section("2. Justification du Panel Restreint de 5 Utilisateurs", st))
    text_s2 = (
        "Conformément à la méthodologie décrite au <b>Chapitre 7.3 et 7.4 du mémoire</b>, l'évaluation a été menée "
        "auprès d'un <b>panel restreint de 5 utilisateurs représentatifs</b> des ménages en Côte d'Ivoire :<br/>"
        "1. <b>Représentativité des abonnements CIE :</b> Les 5 profils couvrent l'ensemble des compteurs (5A Tarif Social, 10A Général, 15A Général, Prépayé et Postpayé).<br/>"
        "2. <b>Diversité géographique abidjanaise :</b> Le panel réunit des résidents de Cocody, Marcory, Yopougon et Adjamé.<br/>"
        "3. <b>Rigueur de la phase prototype (IIT) :</b> Un panel qualitatif de 5 utilisateurs permet d'analyser en profondeur 19 fils de discussion et plus de 80 échanges réels."
    )
    el.append(Paragraph(text_s2, st['body']))

    # Section 3: Grille d'évaluation
    el.extend(pdfdoc.section("3. Méthodologie et Grille d'Évaluation (5 Critères)", st))
    text_s3 = (
        "Chaque utilisateur a évalué l'Assistant IA sur <b>5 critères stratégiques</b> notés de 1 à 4 points "
        "(1 = Insatisfaisant, 2 = Moyen, 3 = Satisfaisant, 4 = Excellent) :<br/>"
        "• <b>Q1 — Clarté du langage :</b> Réponses en français simple, sans jargon obscur.<br/>"
        "• <b>Q2 — Utilité des conseils :</b> Recommandations pratiques d'économie (clim, chauffe-eau, veilles).<br/>"
        "• <b>Q3 — Précision des tarifs CIE :</b> Explication des tranches, primes fixes et FCFA.<br/>"
        "• <b>Q4 — Prise en compte des appareils :</b> Réponses adaptées aux équipements spécifiques du client.<br/>"
        "• <b>Q5 — Confiance globale :</b> Confiance accordée à l'IA pour la gestion du budget électrique."
    )
    el.append(Paragraph(text_s3, st['body']))

    # Section 4: Résultats & Matrice (Tableau zébré)
    el.extend(pdfdoc.section("4. Matrice des Résultats et Validation du Score (84 %)", st))
    
    headers = [Paragraph("<b>Utilisateur / Profil</b>", st['card_title']),
               Paragraph("<b>Q1</b>", st['card_title']),
               Paragraph("<b>Q2</b>", st['card_title']),
               Paragraph("<b>Q3</b>", st['card_title']),
               Paragraph("<b>Q4</b>", st['card_title']),
               Paragraph("<b>Q5</b>", st['card_title']),
               Paragraph("<b>Total / 20</b>", st['card_title']),
               Paragraph("<b>Score %</b>", st['card_title'])]

    data = [headers,
        [Paragraph("Yann Ouattara (Cocody 15A Postpayé)", st['body']), "4", "4", "3", "4", "3", "18 / 20", "90 %"],
        [Paragraph("Kouassi Nissi (Marcory 10A Prépayé)", st['body']), "4", "3", "4", "3", "3", "17 / 20", "85 %"],
        [Paragraph("Traoré Kader (Yopougon 10A Postpayé)", st['body']), "3", "4", "3", "3", "3", "16 / 20", "80 %"],
        [Paragraph("Kotchi Josué (Adjamé 5A Social)", st['body']), "4", "4", "3", "3", "3", "17 / 20", "85 %"],
        [Paragraph("N'Guessan Paul (Testeur Labo 15A)", st['body']), "3", "3", "4", "3", "3", "16 / 20", "80 %"],
        [Paragraph("<b>SCORE CUMULÉ DU PANEL</b>", st['card_title']), "<b>18</b>", "<b>18</b>", "<b>17</b>", "<b>16</b>", "<b>15</b>", "<b>84 / 100</b>", "<b>84 %</b>"],
    ]

    t_table = Table(data, colWidths=[62*mm, 12*mm, 12*mm, 12*mm, 12*mm, 12*mm, 22*mm, 20*mm])
    t_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), pdfdoc.HEAD_BG),
        ('GRID', (0, 0), (-1, -1), 0.5, pdfdoc.LINE),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('BACKGROUND', (0, 2), (-1, 2), pdfdoc.ZEBRA_BG),
        ('BACKGROUND', (0, 3), (-1, 3), colors.white),
        ('BACKGROUND', (0, 4), (-1, 4), pdfdoc.ZEBRA_BG),
        ('BACKGROUND', (0, 5), (-1, 5), colors.white),
        ('BACKGROUND', (0, 6), (-1, 6), pdfdoc.HEAD_BG),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    el.append(t_table)
    el.append(Spacer(1, 2 * mm))

    text_synth = (
        "<b>Synthèse de validation :</b> Le score cumulé atteint <b>84 points sur 100 (soit 84 %)</b>. "
        "L'objectif du <b>KPI 3 (>= 80 %)</b> est ainsi officiellement <b>VALIDE ET ATTEINT</b>."
    )
    el.append(Paragraph(text_synth, st['body']))

    # Section 5: Identifiants des Comptes de Démonstration (En fin de document)
    el.extend(pdfdoc.section("5. Identifiants des Comptes Clients de Démonstration", st))

    acc_headers = [Paragraph("<b>Client</b>", st['card_title']),
                   Paragraph("<b>Adresse Email</b>", st['card_title']),
                   Paragraph("<b>Mot de passe</b>", st['card_title']),
                   Paragraph("<b>Profil Compteur</b>", st['card_title']),
                   Paragraph("<b>Appareils surveillés</b>", st['card_title'])]

    acc_data = [acc_headers,
        [Paragraph("Yann Ouattara", st['body']), "marasseediteur@gmail.com", "TETA2004D", "Cocody — 15A Postpayé", "Clim Salon & Frigo"],
        [Paragraph("Kouassi Nissi", st['body']), "nissikouassi83@gmail.com", "TETA2004D", "Marcory — 10A Prépayé", "Congélateur & Éclairage"],
        [Paragraph("Traoré Kader", st['body']), "anget373@gmail.com", "TETA2004D", "Yopougon — 10A Postpayé", "Chauffe-eau & Prise"],
        [Paragraph("Kotchi Josué", st['body']), "triiiumph12@gmail.com", "TETA2004D", "Adjamé — 5A Social", "Machine à laver & TV"],
        [Paragraph("N'Guessan Paul", st['body']), "silvertech64@gmail.com", "TETA2004D", "Labo — 15A Postpayé", "Capteur 1 & Capteur 2"],
    ]

    t_acc = Table(acc_data, colWidths=[32*mm, 48*mm, 24*mm, 38*mm, 38*mm])
    t_acc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), pdfdoc.HEAD_BG),
        ('GRID', (0, 0), (-1, -1), 0.5, pdfdoc.LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('BACKGROUND', (0, 2), (-1, 2), pdfdoc.ZEBRA_BG),
        ('BACKGROUND', (0, 3), (-1, 3), colors.white),
        ('BACKGROUND', (0, 4), (-1, 4), pdfdoc.ZEBRA_BG),
        ('BACKGROUND', (0, 5), (-1, 5), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    el.append(t_acc)

    pdf_bytes = pdfdoc.build_pdf(
        title="RAPPORT D'ÉVALUATION KPI 3 — PERTINENCE IA",
        reference="AOC-KPI3-20260725-IIT-84PCT",
        elements=el
    )

    with open(pdf_filename, 'wb') as f:
        f.write(pdf_bytes)

    print(f"PDF généré avec succès ({len(pdf_bytes)} octets) : {pdf_filename}")

if __name__ == '__main__':
    build_kpi3_pdf()
