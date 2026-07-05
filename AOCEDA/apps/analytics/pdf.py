"""Socle PDF partagé des exports AOCEDA (identité visuelle, en-tête/pied de page).

Tous les documents PDF émis par la plateforme (historique, rapport mensuel…)
passent par ce module pour garantir une présentation homogène de niveau
professionnel :
  • bandeau de marque + titre + référence du document sur CHAQUE page ;
  • pied de page avec mention légale et pagination « Page X sur Y » ;
  • mêmes styles typographiques, mêmes conventions françaises pour les
    nombres (espace insécable des milliers, virgule décimale) ;
  • tableaux zébrés avec en-tête répété à chaque saut de page.

NB police : Helvetica (encodage WinAnsi). Éviter les caractères hors
Latin-1 (→, ≈, espaces fines U+202F…) qui seraient remplacés par un carré.
"""
import io

from django.utils import timezone  # pyrefly: ignore [untyped-import]
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _rl_canvas
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# ── Identité visuelle (charte ocre de l'application) ──
OCRE = colors.HexColor('#9C5A07')
INK = colors.HexColor('#231B10')
SUB = colors.HexColor('#6B5A45')
LINE = colors.HexColor('#CDBCA3')
HEAD_BG = colors.HexColor('#F2EBDD')
ZEBRA_BG = colors.HexColor('#FAF6EE')
RED = colors.HexColor('#B4231A')

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

BASELINE = "Analyse et optimisation de la consommation d'énergie domestique"
LEGAL = "Document indicatif, non contractuel, généré automatiquement par la plateforme AOCEDA."
JOURS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
NBSP = ' '


# ── Formats (conventions françaises) ─────────────────────────────────────────

def fmt_num(x, dec=2):
    """1234.5 → « 1 234,50 » (milliers en espace insécable, virgule décimale)."""
    return f"{float(x):,.{dec}f}".replace(',', NBSP).replace('.', ',')


def fmt_fcfa(x):
    """Montant FCFA : entier arrondi, milliers séparés (« 12 345 »)."""
    return format(int(round(float(x))), ',').replace(',', NBSP)


def _car_winansi(ch):
    """Un caractère sûr pour Helvetica, ou sa translittération la plus proche.

    Les polices Type 1 standard de reportlab (Helvetica) utilisent l'encodage
    WinAnsi = cp1252, qui couvre le Latin-1 PLUS les signes typographiques
    Windows (tiret cadratin « — », guillemets courbes « " " ' ' », points de
    suspension « … », € …). On teste donc contre cp1252 (et non le Latin-1 strict,
    qui rejetait ces signes et les transformait en « ? »). Ce qui reste hors
    cp1252 (cyrillique, CJK, emoji…) est déplié en ASCII, ou « ? » en dernier recours."""
    try:
        ch.encode('cp1252')
        return ch
    except UnicodeEncodeError:
        pass
    import unicodedata
    base = ''.join(c for c in unicodedata.normalize('NFKD', ch)
                   if not unicodedata.combining(c))
    try:
        base.encode('cp1252')
        return base
    except UnicodeEncodeError:
        return '?'


def texte_libre(s):
    """Texte SAISI PAR L'UTILISATEUR (nom, email, contenu de rapport…) rendu sûr
    pour un Paragraph reportlab : échappement XML (un « & » ou « < » brut ferait
    planter le mini-parseur) + repli WinAnsi (un glyphe hors charte Helvetica
    serait dessiné en carré). Les textes maison n'en ont pas besoin."""
    from xml.sax.saxutils import escape
    return escape(''.join(_car_winansi(c) for c in str(s)))


def fmt_date_fr(d):
    return d.strftime('%d/%m/%Y')


def fmt_jour_fr(d):
    """date → « jeu. 03/07/2026 » (jour de semaine abrégé, utile pour repérer les week-ends)."""
    return f"{JOURS_FR[d.weekday()]} {d.strftime('%d/%m/%Y')}"


def reference_document(code, client):
    """Référence unique et traçable du document : AOC-<CODE>-<AAAAMMJJ>-<id client court>.
    L'identifiant client est un UUID : on en garde 8 hexas, suffisant pour tracer."""
    now = timezone.localtime()
    pk_court = str(client.pk).replace('-', '').upper()[:8]
    return f"AOC-{code}-{now.strftime('%Y%m%d')}-{pk_court}"


# ── Styles ───────────────────────────────────────────────────────────────────

def get_styles():
    base = getSampleStyleSheet()
    return {
        # Titres de section (ocre, majuscules gérées par l'appelant)
        'h2': ParagraphStyle('h2', parent=base['Heading2'], fontName='Helvetica-Bold',
                             fontSize=10.5, textColor=OCRE, spaceBefore=0, spaceAfter=2,
                             leading=13),
        'body': ParagraphStyle('body', parent=base['Normal'], fontSize=9,
                               textColor=INK, leading=13),
        'meta': ParagraphStyle('meta', parent=base['Normal'], fontSize=9,
                               textColor=SUB, leading=13),
        'note': ParagraphStyle('note', parent=base['Normal'], fontSize=8,
                               textColor=SUB, leading=11.5),
        # Cartes d'identification (Titulaire / Document)
        'card_title': ParagraphStyle('card_title', parent=base['Normal'], fontName='Helvetica-Bold',
                                     fontSize=7.5, textColor=OCRE, leading=10),
        'card_lbl': ParagraphStyle('card_lbl', parent=base['Normal'], fontSize=8,
                                   textColor=SUB, leading=11),
        'card_val': ParagraphStyle('card_val', parent=base['Normal'], fontSize=8.5,
                                   textColor=INK, leading=11),
        # Bande de KPI
        'kpi_lbl': ParagraphStyle('kpi_lbl', parent=base['Normal'], fontSize=6.8,
                                  textColor=SUB, leading=9, alignment=1),
        'kpi_val': ParagraphStyle('kpi_val', parent=base['Normal'], fontName='Helvetica-Bold',
                                  fontSize=13, textColor=INK, leading=16, alignment=1),
        'kpi_sub': ParagraphStyle('kpi_sub', parent=base['Normal'], fontSize=7,
                                  textColor=SUB, leading=9, alignment=1),
    }


def section(titre, styles):
    """Titre de section normalisé : libellé ocre en capitales + filet."""
    return [Spacer(1, 5 * mm),
            Paragraph(titre.upper(), styles['h2']),
            HRFlowable(width='100%', thickness=0.6, color=LINE, spaceBefore=0, spaceAfter=4)]


# ── Habillage de page (en-tête / pied de page, pagination X sur Y) ───────────

class _NumberedCanvas(_rl_canvas.Canvas):
    """Canvas qui mémorise chaque page puis dessine l'habillage une fois le
    nombre TOTAL de pages connu (indispensable pour « Page X sur Y »)."""
    chrome = {}  # rempli par la sous-classe créée dans build_pdf()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self._draw_chrome(i, total)
            _rl_canvas.Canvas.showPage(self)
        _rl_canvas.Canvas.save(self)

    def _draw_chrome(self, page_num, total):
        top = PAGE_H - 13 * mm
        # Marque (gauche)
        self.setFillColor(OCRE)
        self.setFont('Helvetica-Bold', 15)
        self.drawString(MARGIN, top, 'AOCEDA')
        self.setFillColor(SUB)
        self.setFont('Helvetica', 6.8)
        self.drawString(MARGIN, top - 3.6 * mm, BASELINE)
        # Titre + référence + date d'édition (droite)
        self.setFillColor(INK)
        self.setFont('Helvetica-Bold', 10)
        self.drawRightString(PAGE_W - MARGIN, top, self.chrome.get('title', ''))
        self.setFillColor(SUB)
        self.setFont('Helvetica', 7.5)
        self.drawRightString(PAGE_W - MARGIN, top - 3.6 * mm, self.chrome.get('subtitle', ''))
        # Filet de séparation
        self.setStrokeColor(OCRE)
        self.setLineWidth(0.9)
        self.line(MARGIN, top - 6.8 * mm, PAGE_W - MARGIN, top - 6.8 * mm)
        # Pied de page
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        self.setFillColor(SUB)
        self.setFont('Helvetica', 7)
        self.drawString(MARGIN, 10 * mm, self.chrome.get('legal', LEGAL))
        self.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {page_num} sur {total}")


def build_pdf(title, reference, elements):
    """Assemble le document A4 final (bytes) avec l'habillage sur chaque page."""
    edited = timezone.localtime().strftime('%d/%m/%Y à %H:%M')
    chrome = {
        'title': title,
        'subtitle': f"Réf. {reference}  ·  Édité le {edited}",
        'legal': LEGAL,
    }
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title,
                            topMargin=27 * mm, bottomMargin=21 * mm,
                            leftMargin=MARGIN, rightMargin=MARGIN)
    canvas_cls = type('_ChromeCanvas', (_NumberedCanvas,), {'chrome': chrome})
    doc.build(elements, canvasmaker=canvas_cls)
    return buf.getvalue()


# ── Blocs de contenu réutilisables ───────────────────────────────────────────

def _carte(titre, lignes, styles, width):
    """Carte encadrée « libellé : valeur » avec bandeau de titre."""
    rows = [[Paragraph(titre.upper(), styles['card_title']), '']]
    for lbl, val in lignes:
        # Les valeurs peuvent venir de saisies utilisateur (nom, email, capteur…) :
        # toujours passées par texte_libre (échappement XML + repli Latin-1).
        rows.append([Paragraph(lbl, styles['card_lbl']),
                     Paragraph(texte_libre(val), styles['card_val'])])
    t = Table(rows, colWidths=[width * 0.40, width * 0.60])
    t.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (1, 0), HEAD_BG),
        ('LINEBELOW', (0, 0), (-1, 0), 0.6, LINE),
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def panneau_identification(cartes, styles):
    """Cartes côte à côte (ex. « Titulaire » + « Document »), largeurs égales."""
    gap = 5 * mm
    n = len(cartes)
    w = (CONTENT_W - gap * (n - 1)) / n
    cells, widths = [], []
    for i, (titre, lignes) in enumerate(cartes):
        cells.append(_carte(titre, lignes, styles, w))
        widths.append(w)
        if i < n - 1:
            cells.append('')
            widths.append(gap)
    t = Table([cells], colWidths=widths)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def bande_kpi(kpis, styles):
    """Bande d'indicateurs clés : (libellé, valeur, précision) par cellule."""
    cells = []
    for lbl, val, sub in kpis:
        inner = [Paragraph(lbl.upper(), styles['kpi_lbl']),
                 Spacer(1, 1.2 * mm),
                 Paragraph(str(val), styles['kpi_val'])]
        if sub:
            inner += [Spacer(1, 0.8 * mm), Paragraph(str(sub), styles['kpi_sub'])]
        cells.append(inner)
    w = CONTENT_W / len(kpis)
    t = Table([cells], colWidths=[w] * len(kpis))
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), ZEBRA_BG),
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('INNERGRID', (0, 0), (-1, -1), 0.6, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def tableau_donnees(entetes, lignes, largeurs, total=None, lignes_rouges=None):
    """Tableau de données normalisé : en-tête ocre répété à chaque page, lignes
    zébrées, colonnes numériques alignées à droite, ligne TOTAL en gras.

    lignes_rouges : {index_ligne: [index_colonnes]} à mettre en évidence (rouge gras)."""
    data = [entetes] + [list(l) for l in lignes]
    if total:
        data.append(list(total))
    t = Table(data, colWidths=largeurs, repeatRows=1)
    last_data = len(data) - (2 if total else 1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), OCRE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), INK),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, OCRE),
        ('LINEBELOW', (0, 1), (-1, last_data), 0.3, LINE),
        ('ROWBACKGROUNDS', (0, 1), (-1, last_data), [colors.white, ZEBRA_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]
    if total:
        style += [
            ('LINEABOVE', (0, -1), (-1, -1), 0.8, SUB),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), HEAD_BG),
        ]
    for row, cols in (lignes_rouges or {}).items():
        for col in cols:
            style.append(('TEXTCOLOR', (col, row), (col, row), RED))
            style.append(('FONTNAME', (col, row), (col, row), 'Helvetica-Bold'))
    t.setStyle(TableStyle(style))
    return t


def tableau_journalier(jours, prix, cap_w, styles):
    """Tableau « détail journalier » commun (historique + rapport mensuel).

    Retourne (flowables, nb_jours_en_depassement). Un pic au-delà de la
    puissance souscrite est signalé en rouge avec un astérisque et une note."""
    from datetime import date as _date

    entetes = ["Jour", "Énergie (kWh)", "Coût énergie (FCFA)",
               "Puiss. moy. (W)", "Pic (W)", "Nuit 00h-06h (kWh)", "Relevés"]
    largeurs = [32 * mm, 24 * mm, 33 * mm, 26 * mm, 22 * mm, 28 * mm, 15 * mm]

    lignes, rouges = [], {}
    tot_kwh = tot_night = 0.0
    tot_n = 0
    pic_max = 0
    for idx, j in enumerate(jours, start=1):
        tot_kwh += j['kwh']
        tot_night += j['night_kwh']
        tot_n += j.get('n', 0)
        pic_max = max(pic_max, j['peak_w'])
        depasse = j['peak_w'] > cap_w
        if depasse:
            rouges[idx] = [4]
        d = _date.fromisoformat(j['date'])
        lignes.append([fmt_jour_fr(d), fmt_num(j['kwh']), fmt_fcfa(j['kwh'] * prix),
                       fmt_num(j['avg_w'], 0), fmt_num(j['peak_w'], 0) + (' *' if depasse else ''),
                       fmt_num(j['night_kwh']), str(j.get('n', ''))])
    total = ["TOTAL", fmt_num(tot_kwh), fmt_fcfa(tot_kwh * prix), "",
             fmt_num(pic_max, 0), fmt_num(tot_night), str(tot_n)]

    el = [tableau_donnees(entetes, lignes, largeurs, total=total, lignes_rouges=rouges)]
    n_over = len(rouges)
    if n_over:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(
            f"<b>*</b> {n_over} jour(s) avec un pic supérieur à la puissance souscrite "
            f"(env. {fmt_num(cap_w, 0)} W) : risque de déclenchement du disjoncteur.",
            styles['note']))
    return el, n_over
