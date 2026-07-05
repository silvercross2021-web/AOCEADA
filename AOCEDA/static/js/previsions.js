/* AOCEDA, Prévisions & Facturation (JavaScript vanilla, sans React)
   N.B. : le shell commun (client-shell.js, chargé avant) gère le bloc
   utilisateur, la déconnexion, la cloche de notifications et la nav
   mobile. Ici : thème (#theme-toggle, recréation des graphiques),
   données API (/api/analytics/facture/, moteur tarifaire officiel CIE,
   /api/previsions/, /api/analytics/summary/), export CSV,
   simulateur, heatmap et rendu de la page. */

// --- Authentication helper ---
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
    // Rejette sur tout statut non-OK (429/500/403) : sinon un corps JSON d'erreur
    // serait pris pour une donnée réelle. L'appel part alors dans le .catch du loader.
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json().catch(() => null);
  });
}

// --- Échappement HTML ---
function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// --- Export CSV (Authorization requis → fetch → blob → lien temporaire) ---
function downloadCSV(url, fallbackName) {
  return window.AOCEDA.authFetch(url)
    .then(res => {
      if (!res.ok) throw new Error('Export impossible');
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : (fallbackName || 'aoceda_export.csv');
      return res.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => {
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    });
}

/* Pas de repli maquette, on affiche "—" quand l'API ne retourne rien */

/* ── État de la page ── */
let theme = localStorage.getItem('aoceda-theme') || 'light';
let budget = 25000;
let chartPeriod = 'mois';
let summary = null;
let previsions = [];
let facture = null;        // décomposition officielle CIE (/api/analytics/facture/)
let prevision = null;      // prévision fin de mois (/api/analytics/prevision/), fourchette honnête
let prixMoyen = 92.5;      // prix moyen effectif FCFA/kWh (repli grille 10A T1 + taxes)
let exporting = false;
let projChart = null;
// Agrégation JOURNALIÈRE du mois courant (/api/analytics/historique/), rapide (une
// ligne par jour) au lieu des milliers de mesures brutes qui bloquaient le graphe.
let joursMonth = [];       // [{date:'AAAA-MM-JJ', kwh:…}]
let joursLoaded = false;   // true une fois le fetch terminé (succès OU échec)
let joursError = false;    // true si le fetch a ÉCHOUÉ (≠ « pas de mesure »)
// Carte thermique agrégée côté serveur (/api/analytics/heatmap/)
let heatCells = null;      // [{dow:0-6, hour:0-23, avg_w:…}]
let heatLoaded = false;
let heatError = false;     // true si le fetch a ÉCHOUÉ (≠ « pas de mesure »)
// Historique FCFA mensuel RÉEL (répartition fixe/consommation), /api/analytics/historique-mensuel/.
// Recalculé depuis la vraie conso → cohérent avec le héros (plus d'estimation périmée).
let moisHisto = [];        // [{annee_mois, mois_libelle, kwh, fixe_fcfa, variable_fcfa, total_fcfa, en_cours}]

// Simulateur
let heures = 2;
let watts = 1500;
let simulating = false;

const $ = id => document.getElementById(id);

/* Lecture d'un token CSS du shell (couleurs data-viz, surfaces…) au moment du
   rendu, pour que les graphiques suivent le thème clair/sombre sans valeurs en dur. */
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

const ICON_MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';

/* ── Thème clair / sombre ── */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('aoceda-theme', theme);
  $('theme-toggle').innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
}

/* ── Données dérivées de l'API (champs aux noms accentués → notation crochets) ── */
/* Tri chronologique sur annee_mois ("AAAA-MM"), le tri alphabétique sur
   moisConcerné était un bug. */
function previsionsTriees() {
  return [...previsions].sort((a, b) =>
    String(b.annee_mois || '').localeCompare(String(a.annee_mois || '')));
}

/* Item du mois courant de /api/previsions/ (écart réel vs mois précédent) */
function getCurrent() {
  if (previsions.length === 0) return null;
  const sorted = previsionsTriees();
  if (facture && facture.annee_mois) {
    const cur = sorted.find(p => p.annee_mois === facture.annee_mois);
    if (cur) return cur;
  }
  return sorted[0];
}

/* Décomposition affichable (lignes arrondies → leur somme EST le total affiché) */
function decompose(f) {
  const t2kwh = f.tranche2 ? Number(f.tranche2.kwh) : 0;
  const t1 = Math.round(Number(f.tranche1.fcfa));
  const t2 = t2kwh > 0 ? Math.round(Number(f.tranche2.fcfa)) : 0;
  const prime = Math.round(Number(f.prime_fixe_fcfa));
  const taxes = Math.round(Number(f.taxes_fcfa));
  return { t1, t2, prime, taxes, hasT2: t2kwh > 0, total: t1 + t2 + prime + taxes };
}

/* (Ancien repli « facture locale 10A » supprimé : il fabriquait une décomposition
   inexacte pour un client 15A/5A. On préfère un état honnête « — » sans facture.) */

function getFacture() {
  if (facture) return decompose(facture).total;
  const current = getCurrent();
  if (summary && summary.facture_estimee_fcfa) return Math.round(Number(summary.facture_estimee_fcfa));
  if (current) return Math.round(Number(current['montantEstimé_FCFA'])) || null;
  return null;
}

function getHisto() {
  // Historique mensuel RÉEL (facture recalculée depuis la vraie conso par le moteur CIE),
  // cohérent au franc près avec le héros. Plus d'estimation périmée ni d'écart 990/1007.
  if (!moisHisto.length) return [];
  return moisHisto.map(mo => ({
    m: mo.en_cours ? `${mo.mois_libelle} (en cours)` : mo.mois_libelle,
    v: Math.round(Number(mo.total_fcfa)) || 0,
    kwh: Number(mo.kwh) || 0,
    cur: !!mo.en_cours,
  }));
}

/* ── Rendu principal (hero, décomposition, historique) ── */
const EMPTY_PREVISIONS_HTML = `<div class="empty-state" style="padding:2rem;text-align:center;color:var(--txt-secondary)">
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:.5rem"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/></svg>
  <div style="font-weight:600;margin-bottom:.25rem">Aucune donnée disponible</div>
  <div style="font-size:.85rem">Les prévisions apparaîtront une fois vos capteurs actifs.</div>
</div>`;

function render() {
  const hasData = !!(facture || previsions.length > 0 || (summary && summary.facture_estimee_fcfa));

  if (!hasData) {
    $('est-mois').textContent = 'En attente de données';
    $('est-amount').textContent = '—';
    if ($('est-unit')) $('est-unit').textContent = '';
    const badge = $('cmp-badge');
    if (badge) { badge.className = 'cmp-badge'; badge.textContent = ''; }
    if ($('cmp-label')) $('cmp-label').textContent = '';
    if ($('decomp')) $('decomp').innerHTML = EMPTY_PREVISIONS_HTML;
    if ($('histo-sub')) $('histo-sub').textContent = 'Aucune donnée';
    if ($('histo-list')) $('histo-list').innerHTML = '';
    return;
  }

  const current = getCurrent();
  const factureTotal = getFacture();
  const kwhEst = facture
    ? Math.round(Number(facture.kwh_projetes))
    : (current && current['consomméeEstimée_kWh']
      ? Math.round(Number(current['consomméeEstimée_kWh']))
      : (summary && factureTotal ? Math.round(factureTotal / prixMoyen) : 0));
  const moisLabel = facture && facture.mois
    ? `${facture.mois} · à ce jour`
    : (current && current['moisConcerné'] ? `${current['moisConcerné']} · à ce jour` : '— · à ce jour');

  $('est-mois').textContent = moisLabel;
  $('est-amount').textContent = factureTotal ? factureTotal.toLocaleString('fr-FR') : '—';

  // Cadrage selon le type de compteur : coût RÉEL consommé à ce jour (pas de projection).
  const prepaid = (facture && facture.type_compteur === 'prepaye')
    || (summary && summary.type_compteur === 'prepaye') || !!getCredit();
  const unitEl = $('est-unit');
  if (unitEl) unitEl.textContent = prepaid
    ? 'FCFA · coût du mois à ce jour (déduit de votre crédit prépayé)'
    : 'FCFA · facture du mois à ce jour (compteur postpayé)';

  // Historique mensuel : le mois en cours est aligné sur l'estimation « live »
  // (héros). Garantit la cohérence montant / décomposition / comparatif.
  const histo = getHisto();
  const curFound = histo.find(x => x.cur);
  const curEntry = curFound || histo[histo.length - 1];
  // On n'aligne la valeur du mois sur le total LIVE (partiel « à ce jour ») QUE pour le
  // VRAI mois en cours (celui tagué « (en cours) »). Sinon (cas limite : aucun Prevision
  // pour le mois de la facture) on laisserait un mois COMPLET afficher des chiffres
  // partiels sans marqueur → trompeur. Et jamais null (sinon r.v.toLocaleString plante).
  if (curFound) { if (factureTotal != null) curFound.v = factureTotal; curFound.kwh = kwhEst; }
  const maxFcfaHisto = Math.max(...histo.map(x => x.v), 1);
  const curIdx = histo.indexOf(curEntry);
  const prev = curIdx > 0 ? histo[curIdx - 1] : (histo.length > 1 ? histo[histo.length - 2] : null);

  // PAS de pourcentage d'écart : le mois affiché est TOUJOURS le mois EN COURS (partiel,
  // « à ce jour »). Le comparer à un mois précédent COMPLET donnerait un faux « −83 % »
  // en début de mois (même piège que le −845 % retiré du simulateur). On montre juste le
  // mois précédent complet comme repère neutre, sans %.
  const badge = $('cmp-badge');
  badge.style.display = 'none';
  badge.textContent = '';
  if (prev && prev.v > 0) {
    $('cmp-label').textContent = `Mois précédent : ${prev.m}, ${prev.v.toLocaleString('fr-FR')} FCFA (mois complet)`;
  } else {
    $('cmp-label').textContent = '';
  }

  // ── Décomposition SIMPLE en 2 parts (identique au tableau de bord) : abonnement
  // fixe (dû chaque mois) + votre consommation. Les 2 somment EXACTEMENT au total.
  // Le détail officiel CIE (tranches, prime, taxes) reste accessible d'un clic. ──
  const fmtKwh = v => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  const fmtPrix = v => Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const decompTitle = prepaid ? 'De quoi se compose votre coût' : 'De quoi se compose votre facture';

  if (!facture || !facture.tranche1) {
    // Pas de décomposition CIE disponible : honnête, aucune fabrication.
    $('decomp').innerHTML = `<div class="decomp-title">${decompTitle}</div>` +
      `<div class="decomp-empty">Le détail apparaîtra dès que vos mesures seront disponibles.</div>`;
  } else {
    const f = facture;
    const d = decompose(f);
    const total = (f.total_fcfa_arrondi != null) ? Number(f.total_fcfa_arrondi) : d.total;
    const abo = (f.abonnement_fixe_fcfa != null) ? Number(f.abonnement_fixe_fcfa)
      : Math.round(Number(f.prime_fixe_fcfa)) + Math.round(Number(f.taxe_fixe_fcfa || 0));
    const conso = (f.consommation_fcfa != null) ? Number(f.consommation_fcfa) : (total - abo);
    const kwhConso = fmtKwh(Number(f.kwh_projetes) || 0);

    const HOME = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></svg>';
    const BOLT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';
    const bucket = (ico, cls, lbl, sub, val, tip) =>
      `<div class="decomp-bucket ${cls}"><span class="db-ico">${ico}</span>` +
      `<span class="db-txt"><span class="db-lbl">${esc(lbl)}${tip ? ' ' + infoTip(tip) : ''}</span><span class="db-sub">${esc(sub)}</span></span>` +
      `<span class="db-val">${esc(val)}</span></div>`;

    const drow = (l, v) => `<div class="dd-row"><span class="dd-lbl">${esc(l)}</span><span class="dd-val">${esc(v)}</span></div>`;
    const detail = [
      drow(`Tranche 1 : ${fmtKwh(f.tranche1.kwh)} kWh × ${fmtPrix(f.tranche1.prix)} F`, `${d.t1.toLocaleString('fr-FR')} FCFA`)
    ];
    if (d.hasT2) detail.push(drow(`Tranche 2 : ${fmtKwh(f.tranche2.kwh)} kWh × ${fmtPrix(f.tranche2.prix)} F`, `${d.t2.toLocaleString('fr-FR')} FCFA`));
    detail.push(drow(`Prime fixe (abonnement ${esc(String(f.amperage))} A)`, `${d.prime.toLocaleString('fr-FR')} FCFA`));
    // Taxes HONNÊTES : part par kWh + part FIXE (sinon « 5,56 F/kWh = 52 F » est trompeur).
    detail.push(drow(`Taxes & redevances (${fmtPrix(f.taxes_par_kwh)} F/kWh + ${Math.round(Number(f.taxe_fixe_fcfa || 0)).toLocaleString('fr-FR')} F fixe)`, `${d.taxes.toLocaleString('fr-FR')} FCFA`));

    $('decomp').innerHTML =
      `<div class="decomp-title">${decompTitle}</div>` +
      bucket(HOME, 'db-fixed', 'Abonnement fixe',
        `Payé chaque mois, même sans rien consommer · ${esc(String(f.amperage))} A`, `${abo.toLocaleString('fr-FR')} F`,
        TIP.fixe) +
      bucket(BOLT, 'db-conso', prepaid ? 'Ce que vous avez consommé' : 'Votre consommation',
        `${kwhConso} kWh ${prepaid ? 'consommés' : 'utilisés'} ce mois-ci`, `${conso.toLocaleString('fr-FR')} F`,
        "Le coût de vos kWh réellement mesurés ce mois-ci, chiffré avec la grille officielle CIE (tranches et taxes incluses). C'est la seule part qui augmente quand vous consommez.") +
      `<div class="decomp-total"><span class="dt-lbl">Total à ce jour<em>TVA 18 % incluse</em></span><span class="dt-val">${total.toLocaleString('fr-FR')} F</span></div>` +
      ((abo > conso) ? `<p class="decomp-note">L’abonnement fixe est la plus grosse part tant que vous consommez peu. Seule «&nbsp;votre consommation&nbsp;» augmente avec vos kWh.</p>` : '') +
      `<details class="decomp-details"><summary>Voir le détail officiel CIE</summary><div class="dd-rows">${detail.join('')}</div></details>`;
  }

  // Historique mensuel (barres proportionnelles, sans rouge : --err est réservé aux anomalies)
  if (histo.length === 0) {
    // Facture chargée mais pas encore d'historique multi-mois (0 ou 1 prévision)
    $('histo-sub').textContent = 'Aucun historique disponible';
    $('histo-list').innerHTML = '';
    return;
  }
  $('histo-sub').textContent = histo.length > 1
    ? `Comparatif des ${histo.length} derniers mois`
    : 'Votre premier mois de facturation';
  $('histo-list').innerHTML = histo.map((r, i) => {
    // Barre toujours visible (min 4 %) même pour un tout petit mois.
    const pct = Math.min(100, Math.max(4, r.v / (maxFcfaHisto || 1) * 100));
    const cur = r.cur ? ' cur' : '';
    // Évolution RÉELLE vs mois précédent (rien d'inventé ; absente sur le 1er mois affiché).
    let delta = '';
    if (i > 0 && histo[i - 1].v > 0) {
      const p = Math.round((r.v - histo[i - 1].v) / histo[i - 1].v * 100);
      delta = p === 0
        ? `<span class="histo-delta hd-flat">stable</span>`
        : `<span class="histo-delta ${p > 0 ? 'hd-up' : 'hd-dn'}">${p > 0 ? '▲' : '▼'} ${Math.abs(p)} %</span>`;
    }
    return `<div class="histo-item">
      <div class="histo-head">
        <span class="histo-month${cur}">${esc(r.m)}</span>
        <span class="histo-right"><span class="histo-val${cur}">${r.v.toLocaleString('fr-FR')} FCFA</span>${delta}</span>
      </div>
      <div class="histo-track"><div class="histo-bar${cur}" style="width:${pct}%"></div></div>
    </div>`;
  }).join('') + (histo.some(r => r.cur)
    ? `<p class="histo-foot">Le mois en cours grandit jusqu'au dernier jour, sa barre n'est pas encore comparable à un mois complet.</p>`
    : '');
}

/* ── Progression du mois en cours (jours_ecoules / jours_du_mois de l'API) ── */
function renderProgress() {
  const now = new Date();
  const daysInMonth = facture && facture.jours_du_mois
    ? Number(facture.jours_du_mois)
    : new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const dayOfMonth = facture && facture.jours_ecoules
    ? Number(facture.jours_ecoules)
    : now.getDate();
  const pctMonth = Math.round(dayOfMonth / daysInMonth * 100);
  const moisNom = facture && facture.mois
    ? String(facture.mois).split(' ')[0]
    : now.toLocaleDateString('fr-FR', { month: 'long' });
  $('prog-pct').textContent = `${pctMonth}% écoulé`;
  // Largeur posée après le premier rendu pour que la transition CSS (0 → x%) soit visible
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $('prog-fill').style.width = `${pctMonth}%`;
  }));
  $('prog-start').textContent = `1 ${moisNom}`;
  $('prog-mid').textContent = `Jour ${dayOfMonth} / ${daysInMonth}`;
  $('prog-end').textContent = `${daysInMonth} ${moisNom}`;
}

/* ── Courbe de projection (Chart.js) ── */

/* État vide honnête du graphique : jamais de courbe fabriquée. Affiche un message
   à la place du canvas quand aucune mesure réelle n'est disponible. */
function showChartEmpty(msg) {
  if (projChart) { projChart.destroy(); projChart = null; }
  const canvas = $('proj-chart');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  let ph = wrap.querySelector('.chart-empty');
  if (!ph) {
    ph = document.createElement('div');
    ph.className = 'chart-empty';
    ph.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;min-height:220px;color:var(--tx-m);font-size:.9rem;text-align:center;padding:1rem';
    wrap.appendChild(ph);
  }
  ph.textContent = msg;
  ph.style.display = '';
  canvas.style.display = 'none';
}
function hideChartEmpty() {
  const canvas = $('proj-chart');
  if (!canvas) return;
  const ph = canvas.parentElement.querySelector('.chart-empty');
  if (ph) ph.style.display = 'none';
  canvas.style.display = '';
}

/* Consommation journalière RÉELLE du mois courant (kWh par jour), depuis l'agrégation
   serveur. Jours passés mesurés = valeur réelle ; jours passés SANS mesure = null (trou
   honnête, capteur hors ligne ≠ conso nulle) ; jours futurs = null (AUCUNE projection).
   Mois/jour ancrés sur le SERVEUR (facture, fuseau Abidjan), pas l'horloge navigateur. */
function buildMonthlyArrays() {
  const now = new Date();
  let year, month, today, daysInMonth;
  if (facture && facture.annee_mois) {
    const [y, m] = String(facture.annee_mois).split('-').map(Number);
    year = y; month = m - 1; // 0-indexed
    today = facture.jours_ecoules ? Number(facture.jours_ecoules) : now.getDate();
    daysInMonth = facture.jours_du_mois ? Number(facture.jours_du_mois) : new Date(year, month + 1, 0).getDate();
  } else {
    year = now.getFullYear(); month = now.getMonth(); today = now.getDate();
    daysInMonth = new Date(year, month + 1, 0).getDate();
  }

  // Map jour-du-mois → kWh réel. On parse la clé 'AAAA-MM-JJ' par découpage de chaîne
  // (pas de new Date()) → aucun décalage de fuseau possible.
  const dailyMap = new Map();
  joursMonth.forEach(j => {
    const p = String(j.date).split('-');
    if (Number(p[0]) !== year || (Number(p[1]) - 1) !== month) return;
    dailyMap.set(Number(p[2]), Number(j.kwh) || 0);
  });

  const actual = [];
  for (let day = 1; day <= daysInMonth; day++) {
    if (day <= today) {
      const v = dailyMap.get(day);
      // Jour passé SANS mesure → null (trou, comme la carte thermique), pas un 0 fabriqué.
      // Un jour PRÉSENT à ~0 reste un vrai 0 (il est dans dailyMap).
      actual.push(v != null ? Math.round(v * 100) / 100 : null);
    } else {
      actual.push(null); // futur : rien affiché (pas de projection)
    }
  }
  return { actual, daysInMonth, hasRealData: dailyMap.size > 0 };
}

function renderChart() {
  if (projChart) projChart.destroy();
  const d = theme === 'dark';
  const gc = d ? 'rgba(255,255,255,.06)' : 'rgba(35,27,16,.06)';
  const lc = cssVar('--tx-s', d ? '#C2B19A' : '#6B5A45');
  const surf = cssVar('--bg-s', d ? '#1E1A13' : '#FFFFFF');
  const dv2 = cssVar('--dv-2', '#1B7A6E');
  const ref = cssVar('--tx-m', '#8A7660');
  const ink = cssVar('--tx-p', '#231B10');

  const chartSub = $('chart-sub');
  const legRow = document.querySelector('.legend-row');
  const projNote = $('proj-note');

  // ── Mode « 3 mois » : FACTURE mensuelle RÉELLE empilée (abonnement fixe + votre
  // consommation), recalculée depuis la vraie conso → cohérente avec le héros. Fini le
  // double-axe trompeur kWh/FCFA : ici, on montre POURQUOI la facture est ce qu'elle est. ──
  if (chartPeriod === '3mois') {
    if (chartSub) chartSub.textContent = 'Facture réelle par mois : abonnement fixe + votre consommation (FCFA)';
    if (legRow) legRow.style.display = 'none';   // Chart.js affiche sa propre légende ici
    if (!moisHisto.length) { showChartEmpty('Aucun historique mensuel disponible pour le moment.'); if (projNote) projNote.hidden = true; return; }
    hideChartEmpty();
    const labels3 = moisHisto.map(mo => mo.en_cours ? `${mo.mois_libelle} (en cours)` : mo.mois_libelle);
    const fixe = moisHisto.map(mo => mo.fixe_fcfa);
    const conso = moisHisto.map(mo => mo.variable_fcfa);
    const kwhArr = moisHisto.map(mo => mo.kwh);
    const infoCol = cssVar('--info', '#3E6E8E');
    if (projNote) {
      projNote.hidden = false;
      projNote.textContent = 'Chaque barre = votre facture du mois. La grande part (bleu) est l’abonnement fixe, dû chaque mois même sans rien consommer ; la petite part (vert) est votre consommation réelle.';
    }
    projChart = new Chart($('proj-chart'), {
      type: 'bar',
      data: { labels: labels3, datasets: [
        { label: 'Abonnement fixe', data: fixe, backgroundColor: d ? 'rgba(62,110,142,.55)' : 'rgba(62,110,142,.35)', borderColor: infoCol, borderWidth: 1, stack: 'f', borderRadius: 3, maxBarThickness: 90 },
        { label: 'Votre consommation', data: conso, backgroundColor: d ? 'rgba(27,122,110,.85)' : 'rgba(27,122,110,.7)', borderColor: dv2, borderWidth: 1, stack: 'f', borderRadius: { topLeft: 6, topRight: 6, bottomLeft: 0, bottomRight: 0 }, maxBarThickness: 90 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
        plugins: {
          legend: { display: true, position: 'top', align: 'end', labels: { color: lc, font: { family: 'Hanken Grotesk', size: 12 }, boxWidth: 12, boxHeight: 12, usePointStyle: true, pointStyle: 'rectRounded' } },
          tooltip: { backgroundColor: surf, borderColor: cssVar('--bd-s', d ? 'rgba(255,255,255,.08)' : '#E4D9C8'), borderWidth: 1, titleColor: ink, bodyColor: lc,
            titleFont: { family: 'Hanken Grotesk', weight: '700', size: 12 }, bodyFont: { family: 'Spline Sans Mono', size: 12 }, padding: 10, cornerRadius: 8,
            callbacks: {
              label: c => `${c.dataset.label} : ${Number(c.raw).toLocaleString('fr-FR')} FCFA`,
              footer: items => { const i = items[0].dataIndex; return `Total : ${(fixe[i] + conso[i]).toLocaleString('fr-FR')} FCFA  ·  ${kwhArr[i].toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh`; },
            } } },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: lc, font: { family: 'Hanken Grotesk', size: 12 } } },
          y: { stacked: true, beginAtZero: true, grid: { color: gc }, border: { display: false }, ticks: { color: lc, font: { family: 'Spline Sans Mono', size: 11 }, callback: v => `${v.toLocaleString('fr-FR')} F` } }
        } }
    });
    return;
  }

  // ── Mode « Ce mois » (défaut) : consommation journalière RÉELLE, en BARRES (pas de courbe
  // lissée qui inventerait des valeurs entre les jours). Aucune projection du futur. ──
  if (chartSub) chartSub.textContent = 'Consommation réelle, jour par jour (kWh)';
  if (legRow) legRow.style.display = '';
  if (!joursLoaded) { showChartEmpty('Chargement…'); return; }
  // Échec serveur ≠ « 0 conso » : on affiche une erreur honnête, pas un faux zéro.
  if (joursError) { showChartEmpty('Consommation du mois indisponible (erreur serveur). Réessayez.'); return; }
  const built = buildMonthlyArrays();
  if (!built.hasRealData) { showChartEmpty('Aucune consommation enregistrée ce mois-ci.'); return; }
  hideChartEmpty();
  const historicalData = built.actual;
  const daysCount      = built.daysInMonth;
  const labels = Array.from({ length: daysCount }, (_, i) => `${i + 1}`);
  // Budget OBJECTIF ramené au JOUR (le budget est mensuel) : cible quotidienne en kWh.
  const budgetDailyKwh = daysCount > 0 ? (budget / daysCount / prixMoyen) : 0;
  const budgetDailyR = Math.round(budgetDailyKwh * 100) / 100;
  const budgetLine = Array(daysCount).fill(budgetDailyR);

  // ÉCHELLE calée sur la VRAIE conso. Si l'objectif/jour est très au-dessus (client largement
  // sous son budget), on NE trace PAS la ligne plate qui écraserait les vraies barres → note.
  const realVals = historicalData.filter(v => v != null && v > 0);
  const realMax = realVals.length ? Math.max(...realVals) : 0;
  const objFits = budgetDailyKwh > 0 && budgetDailyKwh <= Math.max(realMax * 1.6, 0.3);
  const yMax = objFits ? undefined : (realMax > 0 ? Math.round(realMax * 1.4 * 100) / 100 : undefined);

  const datasets = [
    { type: 'bar', label: 'Consommation', data: historicalData, backgroundColor: d ? 'rgba(27,122,110,.6)' : 'rgba(27,122,110,.5)', borderColor: dv2, borderWidth: 1, borderRadius: 4, maxBarThickness: 16 },
  ];
  if (objFits) datasets.push({ type: 'line', label: 'Objectif / jour', data: budgetLine, borderColor: ref, borderDash: [4, 4], borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0 });

  // Légende « Objectif » + note : visibles seulement quand l'objectif tient dans l'échelle.
  const legObj = $('leg-objectif');
  if (legObj) legObj.style.display = objFits ? '' : 'none';
  if (projNote) {
    projNote.hidden = objFits;
    projNote.textContent = objFits ? '' :
      `Objectif : ${budgetDailyR.toLocaleString('fr-FR')} kWh/jour, au-dessus de votre consommation mesurée (échelle ajustée pour la rendre lisible).`;
  }

  const tooltipLabel = c => {
    if (c.raw === null || c.raw === undefined) return null;
    if (c.dataset.type === 'line') return `Objectif du jour : ${Math.round(c.raw * prixMoyen).toLocaleString('fr-FR')} FCFA (${c.raw} kWh)`;
    return `Consommation : ${c.raw} kWh ≈ ${Math.round(c.raw * prixMoyen).toLocaleString('fr-FR')} FCFA`;
  };

  projChart = new Chart($('proj-chart'), {
    type: 'bar',
    data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: {
        backgroundColor: surf, borderColor: cssVar('--bd-s', d ? 'rgba(255,255,255,.08)' : '#E4D9C8'), borderWidth: 1,
        titleColor: ink, bodyColor: lc,
        titleFont: { family: 'Hanken Grotesk', weight: '700', size: 12 }, bodyFont: { family: 'Spline Sans Mono', size: 12 }, padding: 10, cornerRadius: 8,
        callbacks: { title: items => items.length ? `Jour ${items[0].label}` : '', label: tooltipLabel }
      } },
      scales: { y: { beginAtZero: true, suggestedMax: yMax, grid: { color: gc }, border: { display: false }, ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lc, callback: v => `${v} kWh`, maxTicksLimit: 6 } },
        x: { grid: { display: false }, border: { display: false }, ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lc, maxTicksLimit: 10, callback: (v, i) => i % 3 === 0 ? `J${i + 1}` : '' } }
      } }
  });
}

/* ── Rampe d'intensité de la carte thermique (data-viz teal → ocre) ──
   Aucun rouge : --err est réservé aux anomalies, pas à une échelle d'intensité. */
const HEAT_RAMP = [
  'rgba(27,122,110,.22)',   // teal très clair
  'rgba(27,122,110,.50)',   // teal
  'rgba(181,103,11,.40)',   // ocre clair
  'rgba(181,103,11,.70)',   // ocre
  'rgba(160,88,8,.92)'      // ocre profond (intensité max)
];
function heatBand(v, maxV) {
  // Cellule sans mesure : neutre TRÈS clair → les cellules avec données ressortent nettement.
  if (v === null || v === undefined) return cssVar('--bg-h', '#F2EBDD');
  const r = maxV > 0 ? v / maxV : 0;   // intensité relative au maximum réel
  if (r < 0.2) return HEAT_RAMP[0];
  if (r < 0.4) return HEAT_RAMP[1];
  if (r < 0.6) return HEAT_RAMP[2];
  if (r < 0.8) return HEAT_RAMP[3];
  return HEAT_RAMP[4];
}

/* ── Carte thermique de consommation (7 derniers jours, DONNÉES RÉELLES) ──
   Intensité = puissance moyenne (W) par (jour de semaine × heure), agrégée depuis
   /api/mesures/. Robuste (indépendant de la fréquence d'échantillonnage) et jamais
   fabriquée : état vide honnête si aucune mesure. */
function renderHeatmap() {
  const container = $('heatmap');
  if (!container) return;
  container.innerHTML = '';

  const emptyMsg = txt => {
    const el = document.createElement('div');
    el.style.cssText = 'padding:1.5rem;text-align:center;color:var(--tx-m);font-size:.88rem';
    el.textContent = txt;
    container.appendChild(el);
  };
  if (!heatLoaded) { emptyMsg('Chargement…'); return; }
  // Échec serveur ≠ « aucune conso » : erreur honnête plutôt qu'un faux zéro.
  if (heatError) { emptyMsg('Carte thermique indisponible (erreur serveur). Réessayez.'); return; }

  // Cellules agrégées CÔTÉ SERVEUR : puissance moyenne par (jour 0=lundi…6=dimanche, heure).
  const map = {};
  (heatCells || []).forEach(c => { map[c.dow + '-' + c.hour] = Number(c.avg_w) || 0; });
  const avg = (di, hi) => { const k = di + '-' + hi; return (k in map) ? map[k] : null; };

  let maxV = 0;
  for (let di = 0; di < 7; di++) for (let hi = 0; hi < 24; hi++) { const v = avg(di, hi); if (v != null && v > maxV) maxV = v; }
  if (maxV <= 0) { emptyMsg('Aucune donnée de consommation sur les 7 derniers jours.'); return; }

  const days = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
  const dayNames = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];

  const wrap = document.createElement('div');
  wrap.className = 'heat-wrap';

  const dayCol = document.createElement('div');
  dayCol.className = 'heat-daycol';
  days.forEach(dLbl => {
    const el = document.createElement('div');
    el.className = 'heat-daylbl';
    el.textContent = dLbl;
    dayCol.appendChild(el);
  });

  const grid = document.createElement('div');
  grid.className = 'heat-grid';
  for (let ri = 0; ri < 7; ri++) {
    const rowEl = document.createElement('div');
    rowEl.className = 'heat-row';
    for (let ci = 0; ci < 24; ci++) {
      const v = avg(ri, ci);
      const cell = document.createElement('div');
      cell.className = 'heat-cell';
      cell.title = v == null
        ? `${dayNames[ri]} ${ci}h : aucune mesure`
        : `${dayNames[ri]} ${ci}h : ${Math.round(v).toLocaleString('fr-FR')} W (puissance moyenne)`;
      cell.style.background = heatBand(v, maxV);
      rowEl.appendChild(cell);
    }
    grid.appendChild(rowEl);
  }

  wrap.appendChild(dayCol);
  wrap.appendChild(grid);

  const hours = document.createElement('div');
  hours.className = 'heat-hours';
  ['0h', '6h', '12h', '18h', '23h'].forEach(h => {
    const s = document.createElement('span');
    s.textContent = h;
    hours.appendChild(s);
  });

  const legend = document.createElement('div');
  legend.className = 'heat-legend';
  const lo = document.createElement('span');
  lo.textContent = 'Faible';
  legend.appendChild(lo);
  HEAT_RAMP.forEach(c => {
    const sw = document.createElement('div');
    sw.className = 'heat-sw';
    sw.style.background = c;
    legend.appendChild(sw);
  });
  const hi = document.createElement('span');
  hi.textContent = 'Élevée';
  legend.appendChild(hi);

  container.appendChild(wrap);
  container.appendChild(hours);
  container.appendChild(legend);
}

/* ── Simulateur d'économies (prix moyen effectif CIE, plus de 87 F forfaitaire) ── */
function computeEconomie() {
  const kwh = heures * (watts / 1000) * 30;
  return { kwh: kwh.toFixed(1), fcfa: Math.round(kwh * prixMoyen) };
}

function updateSliders() {
  const pctH = ((heures - 0.5) / (6 - 0.5)) * 100;
  const pctW = ((watts - 500) / (3000 - 500)) * 100;
  $('sim-heures-val').textContent = `${heures} h/jour`;
  $('sim-watts-val').textContent = `${watts.toLocaleString('fr-FR')} W`;
  $('sim-heures').style.background = `linear-gradient(to right,var(--ac) 0%,var(--ac) ${pctH}%,var(--bg-a) ${pctH}%,var(--bg-a) 100%)`;
  $('sim-watts').style.background = `linear-gradient(to right,var(--dv-2) 0%,var(--dv-2) ${pctW}%,var(--bg-a) ${pctW}%,var(--bg-a) 100%)`;
}

function renderSimResult(result) {
  const slot = $('sim-result-slot');
  if (!slot) return;
  if (!result) { slot.innerHTML = ''; return; }
  // Économie MENSUELLE hypothétique. On NE la divise plus par la facture du mois « à ce
  // jour » (partielle) : ça donnait un % absurde (ex. −845 %). On explique juste l'hypothèse.
  slot.innerHTML = `<div class="sim-result" id="sim-result">
    <div class="sim-saving">−${parseInt(result.fcfa).toLocaleString('fr-FR')} FCFA</div>
    <div class="sim-saving-label">d'économie estimée par mois</div>
    <div class="sim-detail">
      <strong>${esc(result.kwh)} kWh/mois</strong> en moins × ${esc(prixMoyen.toLocaleString('fr-FR', { maximumFractionDigits: 2 }))} FCFA/kWh (tarif CIE, taxes incl.).<br>
      Hypothèse : un appareil de ${watts.toLocaleString('fr-FR')} W utilisé ${heures} h de moins par jour, sur 30 jours.
    </div></div>`;
}

function runSim() {
  if (simulating) return;
  simulating = true;
  renderSimResult(null);
  const btn = $('sim-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Calcul en cours…';
  const economie = computeEconomie();
  setTimeout(() => {
    simulating = false;
    btn.disabled = false;
    btn.textContent = 'Lancer la simulation';
    renderSimResult(economie);
  }, 1400);
}

/* ── Carte crédit prépayé : visible UNIQUEMENT pour les compteurs prépayés.
   Le solde restant et l'autonomie proviennent de l'API (jamais de maquette). ── */
function getCredit() {
  return (facture && facture.credit_prepaye)
    || (summary && summary.credit_prepaye) || null;
}

function renderCredit() {
  const card = $('credit-card');
  if (!card) return;
  const credit = getCredit();
  // La carte n'apparaît QUE pour un compteur prépayé CONFIRMÉ (type_compteur
  // ou présence d'un bloc credit_prepaye). Masquée par défaut → plus aucun
  // clignotement « prépayé » sur un compte postpayé, ni « facture » + « prépayé »
  // affichés en même temps.
  const isPrepaid = (facture && facture.type_compteur === 'prepaye')
    || (summary && summary.type_compteur === 'prepaye')
    || !!credit;
  if (!isPrepaid) { card.style.display = 'none'; return; }
  card.style.display = '';
  if (!credit) return; // prépayé confirmé, en attente des chiffres API

  const restant = Math.round(Number(credit.restant_fcfa));
  $('credit-big').textContent = restant.toLocaleString('fr-FR');
  $('credit-days').textContent = credit.jours_restants != null ? String(credit.jours_restants) : '—';
  $('credit-basis').textContent =
    `Recharge ${Math.round(Number(credit.recharge_fcfa)).toLocaleString('fr-FR')} FCFA − ` +
    `consommé ${Math.round(Number(credit.consomme_fcfa)).toLocaleString('fr-FR')} FCFA · ` +
    `≈ ${Math.round(Number(credit.cout_jour_fcfa)).toLocaleString('fr-FR')} FCFA/j`;
  $('credit-warning').style.display =
    (credit.jours_restants != null && credit.jours_restants <= 4) ? '' : 'none';
}

/* Recharge RÉELLE du crédit prépayé (POST /api/analytics/recharge/). */
function rechargeCredit() {
  const input = $('credit-input');
  const fb = $('recharge-feedback');
  const montant = parseInt(String(input ? input.value : '').replace(/[^\d]/g, ''), 10);
  if (isNaN(montant) || montant <= 0) {
    if (fb) { fb.style.color = 'var(--err)'; fb.textContent = 'Saisissez un montant de recharge valide.'; }
    return;
  }
  const btn = $('recharge-btn');
  if (btn) btn.disabled = true;
  if (fb) { fb.style.color = ''; fb.textContent = 'Recharge en cours…'; }
  // On appelle authFetch DIRECTEMENT (pas fetchWithAuth) pour lire le corps même sur une
  // erreur 4xx : ça préserve le message précis du serveur (ex. « réservé au prépayé »).
  window.AOCEDA.authFetch('/api/analytics/recharge/', { method: 'POST', body: JSON.stringify({ montant }) })
    .then(res => res.json().catch(() => null).then(data => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (btn) btn.disabled = false;
      if (ok && data && data.credit_prepaye) {
        if (facture) facture.credit_prepaye = data.credit_prepaye;
        if (summary) summary.credit_prepaye = data.credit_prepaye;
        renderCredit();
        if (input) input.value = '';
        if (fb) { fb.style.color = 'var(--ok)'; fb.textContent = data.detail || 'Recharge effectuée.'; }
      } else if (fb) {
        fb.style.color = 'var(--err)';
        fb.textContent = (data && data.detail) || 'Échec de la recharge.';
      }
    })
    .catch(() => { if (btn) btn.disabled = false; if (fb) { fb.style.color = 'var(--err)'; fb.textContent = 'Échec de la recharge.'; } });
}

/* ── Export CSV du mois calendaire (même fenêtre que le graphique « Ce mois ») ── */
function exportCSV() {
  if (exporting) return;
  exporting = true;
  const btn = $('btn-export-csv');
  btn.disabled = true;
  $('export-label').textContent = 'Export en cours…';
  // Mois calendaire (1er → aujourd'hui) pour coller au graphe, pas 30 jours glissants.
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const fmt = dt => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  downloadCSV(`/api/analytics/export/?date_from=${fmt(first)}&date_to=${fmt(now)}`, 'aoceda_rapport_mensuel.csv')
    .catch(err => console.error(err))
    .finally(() => {
      exporting = false;
      btn.disabled = false;
      $('export-label').textContent = 'Rapport mensuel CSV';
    });
}

/* ── Rapport mensuel PDF : document serveur structuré (synthèse, facture CIE
   détaillée, prévision, détail journalier), plus jamais un window.print(). ── */
let exportingPdf = false;
function exportPDF() {
  if (exportingPdf) return;
  exportingPdf = true;
  const btn = $('btn-export-pdf');
  const lbl = $('pdf-label');
  if (btn) btn.disabled = true;
  if (lbl) lbl.textContent = 'Export en cours…';
  // downloadCSV = téléchargeur blob générique (nom via Content-Disposition) → sert aussi au PDF.
  downloadCSV('/api/analytics/export/rapport-mensuel/', 'aoceda_rapport_mensuel.pdf')
    .catch(err => console.error(err))
    .finally(() => {
      exportingPdf = false;
      if (btn) btn.disabled = false;
      if (lbl) lbl.textContent = 'Rapport PDF';
    });
}

/* ── Icône « i » d'information : infobulle au survol ET au focus clavier (accessible).
   Le texte vit dans data-tip (affiché en ::after) + aria-label (lecteur d'écran). ── */
function infoTip(txt, pos) {
  return `<button type="button" class="itip${pos ? ' itip-' + pos : ''}" aria-label="${esc(txt)}" data-tip="${esc(txt)}">` +
    `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="10.5" x2="12" y2="16.5"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg></button>`;
}

/* ── Prévision fin de mois : fourchette honnête, part certaine séparée de l'estimée,
   chip de confiance, barre de fourchette visuelle, infobulles « i », divulgation des
   jours manquants. Le calcul est 100 % serveur ; ici on ne fait que FORMATER. ── */
const TIP = {
  titre: "Une estimation basée uniquement sur votre consommation réelle, jamais une promesse. Elle devient votre facture exacte le dernier jour du mois.",
  confiance: "Fiable = beaucoup de journées mesurées. Indicative = estimation raisonnable mais encore mouvante. Trop tôt = pas assez de données pour avancer un chiffre.",
  fourchette: "Le montant final a de fortes chances de se situer entre ces deux bornes. La fourchette se resserre à mesure que le mois avance.",
  fixe: "La prime fixe CIE + la taxe fixe : dues chaque mois, même sans rien consommer. Cette part est certaine à 100 %.",
  conso: "Vos kWh estimés d'ici la fin du mois, au rythme médian de vos journées réelles, chiffrés avec la vraie grille CIE (tranches et taxes incluses).",
  tropTot: "Une « journée complète » = un jour où votre capteur a mesuré presque tout le temps (≈ 19 h ou plus). Vos journées récentes n'ont que quelques heures de mesures : pas encore assez pour estimer un mois entier sans rien inventer. Laissez le capteur branché plus longtemps et le compte montera tout seul.",
  recharge: "Montant à recharger pour couvrir le coût estimé jusqu'à la fin du mois, d'après votre rythme actuel.",
};

function renderPrevision() {
  const el = $('prevision-card');
  if (!el) return;
  const p = prevision;
  if (!p || p.mode === 'vide') { el.style.display = 'none'; return; }
  el.style.display = '';
  const prepaid = p.type_compteur === 'prepaye';
  const fmt = v => Number(v || 0).toLocaleString('fr-FR');
  const titre = prepaid ? 'Coût estimé en fin de mois' : 'Estimation de votre facture en fin de mois';
  const head = (chipTxt, chipCls) =>
    `<div class="prev-head"><h2 class="card-title">${esc(titre)} ${infoTip(TIP.titre)}</h2>` +
    `<span class="prev-chip ${chipCls}">${esc(chipTxt)} ${infoTip(TIP.confiance, 'right')}</span></div>`;

  // TIER 0 : pas assez de jours complets → honnête, AUCUN chiffre de consommation inventé.
  if (p.mode === 'trop_tot') {
    const k = Math.max(0, Math.min(Number(p.k) || 0, p.n_min));
    const steps = Array.from({ length: p.n_min }, (_, i) =>
      `<span class="prev-step${i < k ? ' on' : ''}" aria-hidden="true"></span>`).join('');
    el.innerHTML = head('Trop tôt', 'pc-tot') +
      `<div class="prev-steps-row"><div class="prev-steps">${steps}</div>` +
      `<span class="prev-steps-lbl">${k}/${p.n_min} journées complètes mesurées ${infoTip(TIP.tropTot)}</span></div>` +
      `<p class="prev-tot-msg">Une <strong>journée complète</strong> = un jour où le capteur a mesuré quasiment toute la journée. Vos mesures récentes ne couvrent que quelques heures par jour, donc l'estimation attend d'avoir <strong>${p.n_min} journées complètes</strong>. En attendant, voici ce qui est déjà certain :</p>` +
      `<div class="prev-certain"><span>Abonnement fixe du mois ${infoTip(TIP.fixe)}</span><strong>${fmt(p.fixe_certain)} F</strong></div>`;
    return;
  }

  const confMap = { fiable: ['Fiable', 'pc-ok'], indicative: ['Indicative', 'pc-ind'], indicative_trous: ['Indicative', 'pc-ind'] };
  const conf = confMap[p.confiance] || ['Estimation', 'pc-ind'];
  const HOME = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></svg>';
  const BOLT = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';

  // Barre de fourchette : piste = la plage basse→haute ; marqueur = montant attendu.
  // Position du marqueur en % de la plage (bornée 6..94 pour rester visible).
  const lo = Number(p.bill_low) || 0, hi = Number(p.bill_high) || 0, mid = Number(p.bill_central) || 0;
  const pct = hi > lo ? Math.min(94, Math.max(6, (mid - lo) / (hi - lo) * 100)) : 50;
  const rangeBar =
    `<div class="prev-bar" role="img" aria-label="Fourchette d'estimation : basse ${fmt(lo)} FCFA, attendue ${fmt(mid)} FCFA, haute ${fmt(hi)} FCFA">` +
      `<div class="prev-bar-track"><span class="prev-bar-dot" style="left:${pct}%"></span></div>` +
      `<div class="prev-bar-lbls"><span>Basse<br><strong>${fmt(lo)} F</strong></span>` +
      `<span class="pbl-mid" style="left:${pct}%">Attendue<br><strong>≈ ${fmt(mid)} F</strong></span>` +
      `<span>Haute<br><strong>${fmt(hi)} F</strong></span></div>` +
    `</div>`;

  const trous = p.offline_days > 0
    ? `<p class="prev-warn">${p.offline_days} jour${p.offline_days > 1 ? 's' : ''} sans données, estimé${p.offline_days > 1 ? 's' : ''} à votre consommation habituelle, à confirmer. Votre facture réelle « à ce jour » n'est jamais gonflée.</p>` : '';
  const large = p.mode === 'band_large'
    ? `<p class="prev-note">Fourchette encore large : elle se resserrera après 1-2 journées complètes de plus.</p>` : '';

  el.innerHTML = head(conf[0], conf[1]) +
    `<div class="prev-range">entre <strong>${fmt(lo)}</strong> et <strong>${fmt(hi)}</strong> <span class="prev-unit">FCFA</span> ${infoTip(TIP.fourchette)}</div>` +
    rangeBar +
    `<div class="prev-split">` +
      `<div class="prev-part pp-fixed"><span class="pp-ico">${HOME}</span><span class="pp-txt"><span class="pp-lbl">Abonnement fixe ${infoTip(TIP.fixe)}</span><span class="pp-sub">certain, dû quoi qu'il arrive</span></span><span class="pp-val">${fmt(p.fixe_certain)} F</span></div>` +
      `<div class="prev-part pp-conso"><span class="pp-ico">${BOLT}</span><span class="pp-txt"><span class="pp-lbl">Consommation ${infoTip(TIP.conso)}</span><span class="pp-sub">estimée d'après votre rythme</span></span><span class="pp-val">~ ${fmt(p.variable_estime)} F</span></div>` +
    `</div>` +
    `<div class="prev-basis">Basé sur ${p.k} journée${p.k > 1 ? 's' : ''} réelle${p.k > 1 ? 's' : ''} de mesures · consommation projetée ≈ ${fmt(p.projected_kwh)} kWh</div>` +
    trous + large +
    (prepaid && p.recharge_conseillee != null
      ? `<div class="prev-recharge">Pour finir le mois sans coupure : recharge conseillée ≈ <strong>${fmt(p.recharge_conseillee)} FCFA</strong> ${infoTip(TIP.recharge)}</div>` : '');
}

/* ── Initialisation ── */
function init() {
  applyTheme();
  renderProgress();
  render();
  renderChart();
  renderHeatmap();
  updateSliders();
  renderCredit();
  renderPrevision();

  // Thème clair / sombre
  $('theme-toggle').addEventListener('click', () => {
    theme = theme === 'light' ? 'dark' : 'light';
    applyTheme();
    renderChart();
  });

  // Filtres de période du graphique
  document.querySelectorAll('.filter-row .pill').forEach(p => {
    p.addEventListener('click', () => {
      chartPeriod = p.dataset.period;
      document.querySelectorAll('.filter-row .pill').forEach(x => {
        const on = x.dataset.period === chartPeriod;
        x.classList.toggle('active', on);
        x.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      renderChart();
    });
  });

  // Budget mensuel objectif → ligne budget du graphique
  $('budget-input').addEventListener('input', e => {
    budget = +e.target.value;
    renderChart();
  });

  // Simulateur
  $('sim-heures').addEventListener('input', e => { heures = +e.target.value; updateSliders(); });
  $('sim-watts').addEventListener('input', e => { watts = +e.target.value; updateSliders(); });
  $('sim-btn').addEventListener('click', runSim);

  // Export CSV
  $('btn-export-csv').addEventListener('click', exportCSV);

  // Rapport mensuel PDF (document serveur, mise en page professionnelle)
  const pdfBtn = $('btn-export-pdf');
  if (pdfBtn) pdfBtn.addEventListener('click', exportPDF);

  // Recharge du crédit prépayé (action réelle)
  const rechargeBtn = $('recharge-btn');
  if (rechargeBtn) rechargeBtn.addEventListener('click', rechargeCredit);
  const creditInput = $('credit-input');
  if (creditInput) creditInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); rechargeCredit(); }
  });

  // Charge la consommation journalière du mois pour un 1er-du-mois 'AAAA-MM-01' donné.
  // (joursError distingue « échec serveur » de « aucune mesure » → pas de faux zéro.)
  function loadJoursForMonth(firstDay) {
    fetchWithAuth(`/api/analytics/historique/?date_from=${firstDay}`)
      .then(data => {
        joursMonth = (data && Array.isArray(data.jours)) ? data.jours : [];
        joursError = false; joursLoaded = true; renderChart();
      })
      .catch(() => { joursError = true; joursLoaded = true; renderChart(); });
  }
  const browserFirstOfMonth = () => {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-01`;
  };

  // Chargement API : facture officielle CIE + résumé + prévisions + conso du mois + heatmap
  fetchWithAuth('/api/analytics/facture/')
    .then(data => {
      if (!data || !data.tranche1) { loadJoursForMonth(browserFirstOfMonth()); return; } // état vide honnête
      facture = data;
      // Prix STABLE (marginal T1 + taxes, ~92,5 F) pour le simulateur/budget/tooltips.
      // PAS prix_moyen_kwh, qui explose en début de mois → économies aberrantes (−318 788 F).
      if (data.prix_kwh_tout_compris) prixMoyen = Number(data.prix_kwh_tout_compris);
      else if (data.prix_moyen_kwh) prixMoyen = Number(data.prix_moyen_kwh);
      render();
      renderProgress();
      renderChart();
      renderCredit();
      // Fenêtre du graphe ANCRÉE sur le mois SERVEUR (facture, fuseau Abidjan), jamais
      // sur l'horloge navigateur → plus de décalage près d'un changement de mois.
      loadJoursForMonth(facture.annee_mois ? `${facture.annee_mois}-01` : browserFirstOfMonth());
    })
    .catch(err => { console.error(err); loadJoursForMonth(browserFirstOfMonth()); });
  fetchWithAuth('/api/analytics/summary/')
    .then(data => { summary = data; render(); renderCredit(); })
    .catch(err => console.error(err));
  fetchWithAuth('/api/previsions/')
    .then(data => { previsions = window.AOCEDA.asList(data); render(); renderChart(); })
    .catch(err => console.error(err));
  // Historique FCFA mensuel RÉEL (répartition fixe / consommation) → alimente la carte
  // « Historique mensuel » ET le mode « 3 mois » du graphe, cohérent avec le héros.
  fetchWithAuth('/api/analytics/historique-mensuel/')
    .then(data => { moisHisto = (data && Array.isArray(data.mois)) ? data.mois : []; render(); renderChart(); })
    .catch(err => console.error(err));
  // Carte thermique agrégée (puissance moyenne par jour × heure, 7 derniers jours).
  fetchWithAuth('/api/analytics/heatmap/')
    .then(data => {
      heatCells = (data && Array.isArray(data.cells)) ? data.cells : [];
      heatError = false; heatLoaded = true; renderHeatmap();
    })
    .catch(() => { heatError = true; heatLoaded = true; renderHeatmap(); });
  // Prévision de fin de mois (fourchette honnête), calcul 100 % serveur.
  fetchWithAuth('/api/analytics/prevision/')
    .then(data => { prevision = data; renderPrevision(); })
    .catch(err => console.error(err));
}

init();
