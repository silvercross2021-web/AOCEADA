'use strict';
/* ════════════════════════════════════════════════════════════
   AOCEDA, Historique de consommation (Chart.js, vanilla JS)
   (Les alertes et leur configuration vivent désormais sur /alertes/)
   ════════════════════════════════════════════════════════════ */

const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401.
   IMPORTANT : on rejette explicitement sur un statut HTTP non-OK. Sinon une erreur
   serveur qui renvoie un corps JSON (429 throttle, 403, 500 via DRF) serait traitée
   comme un succès « vide » → on effacerait les vraies données et le badge « En direct »
   mentirait. En rejetant, l'appel part dans le .catch qui, lui, préserve l'affichage. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  });
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

/* Export CSV (Authorization requis → fetch → blob → lien temporaire) */
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
      a.href = objUrl; a.download = filename;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    });
}

/* Prix effectif CIE du client (FCFA/kWh, taxes/TVA incl.), fourni par l'API. Repli 92,5. */
let prixMoyenKwh = 92.5;
function fcfaOf(kwh) { return Math.round(kwh * prixMoyenKwh); }

/* ── Puissance souscrite (disjoncteur), miroir EXACT de PUISSANCE_KW (tarifs_cie.py) ──
   5A→1,1kW · 10A→2,2kW · 15A→3,3kW. Limite calculée UNIQUEMENT si l'ampérage RÉEL du
   client (fourni par l'API) est connu, jamais de seuil inventé (règle « aucune donnée
   fictive »). */
const CAP_KW = { 5: 1.1, 10: 2.2, 15: 3.3 };
function capaciteW() {
  const kw = CAP_KW[histState.amperage];
  return kw ? Math.round(kw * 1000) : null;   // null = ampérage inconnu → aucune alerte
}
/* '' sous la limite · 'near' ≥ 90 % · 'over' a dépassé la puissance souscrite (coupure possible) */
function niveauPic(peakW) {
  const cap = capaciteW();
  if (!cap || !peakW) return '';
  if (peakW > cap) return 'over';
  if (peakW >= cap * 0.9) return 'near';
  return '';
}
function peakClass(peakW) {
  const lvl = niveauPic(peakW);
  return lvl === 'over' ? 'peak-over' : lvl === 'near' ? 'peak-near' : '';
}
/* Médiane des jours réellement consommateurs (kWh > 0) : socle de la détection d'anomalie.
   Un jour est « inhabituel » si sa conso ≥ 2 × cette médiane (voir ANOMALY_FACTOR). */
const ANOMALY_FACTOR = 2;
function medianePositive(rows) {
  const xs = rows.map(r => r.kwhExact).filter(v => v > 0).sort((a, b) => a - b);
  if (!xs.length) return 0;
  const m = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[m] : (xs[m - 1] + xs[m]) / 2;
}

/* Construit les lignes d'affichage à partir des jours DÉJÀ AGRÉGÉS par le serveur
   (/api/analytics/historique/), plus aucune agrégation lourde côté client, donc
   plus de téléchargement de milliers de mesures brutes. On fusionne juste le nombre
   d'alertes par jour (petite liste). */
function buildRowsFromJours(jours, alertes) {
  const alertsByDay = {};
  (alertes || []).forEach(a => {
    if (!a.createdAt) return;
    const d = new Date(a.createdAt);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    alertsByDay[key] = (alertsByDay[key] || 0) + 1;
  });

  return (jours || []).map(j => {
    const d = new Date(j.date + 'T00:00:00');   // date ISO locale (AAAA-MM-JJ)
    const kwh = Number(j.kwh) || 0;
    return {
      date: d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' }),
      rawDate: d,
      isoDate: j.date,
      kwh: Math.round(kwh * 100) / 100,
      kwhExact: kwh,
      fcfa: fcfaOf(kwh),
      avgW: Math.round(Number(j.avg_w) || 0),
      peak: Math.round(Number(j.peak_w) || 0),
      nightKwh: Number(j.night_kwh) || 0,
      mesures: Number(j.n) || 0,
      alerts: alertsByDay[j.date] || 0,
    };
  }).sort((a, b) => a.rawDate - b.rawDate);
}

/* ════════════════ Thème ════════════════ */
const MOON_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const SUN_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
let theme = localStorage.getItem('aoceda-theme') || 'light';
const themeToggleBtn = document.getElementById('theme-toggle');
function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('aoceda-theme', theme);
  if (themeToggleBtn) themeToggleBtn.innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
}
if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => {
  theme = theme === 'light' ? 'dark' : 'light';
  applyTheme();
  renderHistorique();
});

/* ════════════════ État + rendu ════════════════ */
// '7j' → 7 jours glissants ; '30j' → 30 jours glissants ; 'mois' → mois CALENDAIRE
// en cours (traité via date_from/date_to, et non un simple « 30 jours »).
const PERIOD_MAP = { '7j': 'week', '30j': 'month' };
const histState = {
  period: '7j', sensor: 'all', sensorsList: [], jours: [], alertes: [],
  loaded: false, loadError: false, exporting: false, exportingPdf: false, sort: { f: 'date', d: 1 },
  customFrom: '', customTo: '',
  amperage: null,       // ampérage souscrit RÉEL (fourni par l'API), null tant qu'inconnu
  unit: 'fcfa',         // unité du graphique : 'fcfa' (coût, défaut) | 'kwh' (énergie)
  previous: null,       // période précédente de même durée (comparaison), null si aucune donnée
  winFrom: '', winTo: '', // fenêtre réelle renvoyée par le serveur (jours calendaires)
};

const sensorSelect = document.getElementById('sensor-select');
const dateRangeEl = document.getElementById('date-range');
const exportBtn = document.getElementById('export-btn');
const exportLabel = document.getElementById('export-label');
const pdfBtn = document.getElementById('pdf-btn');
const pdfLabel = document.getElementById('pdf-label');
const statsGrid = document.getElementById('stats-grid');
const insightStrip = document.getElementById('insight-strip');
const unitBtns = Array.from(document.querySelectorAll('.ut'));
const chartTitleEl = document.getElementById('chart-title');
const dataDepthNote = document.getElementById('data-depth-note');
const tableMeta = document.getElementById('table-meta');
const histTbody = document.getElementById('hist-tbody');
const periodBtns = Array.from(document.querySelectorAll('.pt'));
const sortHeaders = Array.from(document.querySelectorAll('th[data-field]'));
const customRangeEl = document.getElementById('custom-range');
const dateFromInput = document.getElementById('date-from');
const dateToInput = document.getElementById('date-to');
const crApplyBtn = document.getElementById('cr-apply');

const liveBadge = document.getElementById('live-badge');
const liveTime = document.getElementById('live-time');
const liveStatus = document.getElementById('live-status');

const pad2 = n => String(n).padStart(2, '0');
const fmtDate = dt => `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
function syncCustomRangeUI() {
  if (customRangeEl) customRangeEl.style.display = histState.period === 'perso' ? '' : 'none';
}

/* ════════════════ Temps réel ════════════════
   L'Historique montre surtout du passé (jours FIGÉS). Mais le jour EN COURS grandit
   au fil des mesures. On ne rafraîchit donc automatiquement QUE si la plage affichée
   inclut aujourd'hui, sinon les données ne bougent pas et un poll serait un mensonge
   « en direct » pour rien. Cadence 20 s : le kWh journalier s'accumule lentement. */
const REFRESH_MS = 20000;
let refreshTimer = null;
function rangeIncludesToday() {
  if (histState.period === 'perso') {
    // Plage libre : « live » seulement si la date de fin atteint (ou dépasse) aujourd'hui.
    return !histState.customTo || histState.customTo >= fmtDate(new Date());
  }
  return true; // 7j / 30j / mois se terminent toujours à maintenant
}
function updateLiveBadge() {
  if (!liveBadge) return;
  const live = rangeIncludesToday() && histState.loaded;
  liveBadge.hidden = !live;
  if (live && liveTime) liveTime.textContent = new Date().toLocaleTimeString('fr-FR');
}
function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    // Onglet caché, export en cours, 1er chargement pas fini, ou plage 100 % passée → on s'abstient.
    if (document.hidden || histState.exporting || !histState.loaded) return;
    if (!rangeIncludesToday()) return;
    loadMesures({ silent: true });
  }, REFRESH_MS);
}
document.addEventListener('visibilitychange', () => {
  // Au retour sur l'onglet, on rattrape immédiatement (sans attendre le prochain tick).
  if (!document.hidden && histState.loaded && !histState.exporting && rangeIncludesToday()) {
    loadMesures({ silent: true });
  }
});

let chartInstance = null;

/* Lit un token CSS du shell (couleurs data-viz, surfaces…) pour rester
   fidèle à la palette et au thème sans valeurs en dur. */
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function renderChart(rows, silent) {
  const d = theme === 'dark';
  const unit = histState.unit;   // 'fcfa' (coût, défaut) | 'kwh' (énergie mesurée)
  // Pas d'animation lors d'un rafraîchissement temps réel (sinon le graphe « rejoue »
  // toutes les 20 s) ni si l'utilisateur a demandé un mouvement réduit.
  const reduceMotion = silent || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const gc = d ? 'rgba(255,255,255,.06)' : 'rgba(35,27,16,.07)';
  const lc = cssVar('--tx-s', d ? '#C2B19A' : '#6B5A45');
  const tp = cssVar('--tx-p', d ? '#F0E9DC' : '#231B10');
  const normal = cssVar('--dv-2', '#1B7A6E');   // série « normale » (teal)
  const high = cssVar('--ac-text', '#9C5A07');  // série « élevée » (ocre accent)
  const FONT_MONO = "'Spline Sans Mono', ui-monospace, monospace";
  const FONT_DISP = "'Hanken Grotesk', system-ui, sans-serif";

  /*, aides couleur : conversion en [r,g,b], mélange et rgba(), */
  const toRGB = c => {
    c = String(c).trim();
    if (c[0] === '#') {
      let h = c.slice(1);
      if (h.length === 3) h = h.replace(/./g, x => x + x);
      const n = parseInt(h, 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    const m = c.match(/[\d.]+/g) || [0, 0, 0];
    return [+m[0], +m[1], +m[2]];
  };
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const WHITE = [255, 255, 255];
  const normalRGB = toRGB(normal);
  const highRGB = toRGB(high);

  const labels = rows.map(r => r.date);
  // Hauteur des barres selon l'unité active : coût estimé (FCFA) OU énergie mesurée (kWh).
  const data = rows.map(r => unit === 'fcfa' ? r.fcfa : r.kwh);
  const baseRGB = rows.map(r => r.alerts === 0 ? normalRGB : highRGB);

  // Info-bulle riche (réutilisée à l'identique en rebuild ET en maj temps réel en place).
  const tooltipTitle = items => { const r = rows[items[0].dataIndex]; return r ? r.date : ''; };
  const tooltipLabel = c => {
    const r = rows[c.dataIndex];
    if (!r) return '';
    const lines = [
      `${r.kwh.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kWh consommés`,
      `≈ ${r.fcfa.toLocaleString('fr-FR')} FCFA (tarif CIE)`,
      `Puissance moy. ${r.avgW.toLocaleString('fr-FR')} W · pic ${r.peak.toLocaleString('fr-FR')} W`,
    ];
    if (r.nightKwh > 0) lines.push(`Dont nuit (0h–6h) : ${r.nightKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh`);
    if (r.alerts > 0) lines.push(`⚠ ${r.alerts} alerte${r.alerts > 1 ? 's' : ''} ce jour`);
    lines.push(`${r.mesures.toLocaleString('fr-FR')} mesure${r.mesures > 1 ? 's' : ''} relevée${r.mesures > 1 ? 's' : ''}`);
    return lines;
  };

  /* Dégradé vertical par barre : base saturée en bas → teinte plus claire en haut. */
  const barFill = lighten => ctx => {
    const area = ctx.chart.chartArea;
    const base = baseRGB[ctx.dataIndex] || normalRGB;
    if (!area) return rgba(base, 1);
    const g = ctx.chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
    g.addColorStop(0, rgba(base, 1));
    g.addColorStop(1, rgba(mix(base, WHITE, lighten), 1));
    return g;
  };

  /* Plugin : ombre douce portée sous les barres (profondeur). */
  const barShadow = {
    id: 'barShadow',
    beforeDatasetDraw(chart) {
      const c = chart.ctx;
      c.save();
      c.shadowColor = d ? 'rgba(0,0,0,.45)' : 'rgba(35,27,16,.16)';
      c.shadowBlur = 14;
      c.shadowOffsetY = 5;
    },
    afterDatasetDraw(chart) { chart.ctx.restore(); }
  };

  /* Plugin : ligne de moyenne en pointillé, tracée DERRIÈRE les barres. */
  const avgLine = {
    id: 'avgLine',
    beforeDatasetsDraw(chart) {
      const ds = chart.data.datasets[0].data;
      const y = chart.scales.y, area = chart.chartArea;
      if (!ds.length || !y || !area) return;
      const avg = ds.reduce((s, v) => s + (v || 0), 0) / ds.length;
      const yp = y.getPixelForValue(avg);
      const c = chart.ctx;
      c.save();
      c.strokeStyle = rgba(toRGB(lc), 0.55);
      c.lineWidth = 1.5;
      c.setLineDash([5, 4]);
      c.beginPath();
      c.moveTo(area.left, yp);
      c.lineTo(area.right, yp);
      c.stroke();
      c.restore();
    }
  };

  /* Plugin : valeur en kWh affichée au-dessus de chaque barre. */
  const valueLabels = {
    id: 'valueLabels',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      const c = chart.ctx;
      c.save();
      c.shadowColor = 'transparent';
      c.font = `600 11px ${FONT_MONO}`;
      c.fillStyle = tp;
      c.textAlign = 'center';
      c.textBaseline = 'bottom';
      meta.data.forEach((bar, i) => {
        const v = chart.data.datasets[0].data[i];
        if (v == null) return;
        const txt = unit === 'fcfa'
          ? Math.round(v).toLocaleString('fr-FR')
          : v.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
        c.fillText(txt, bar.x, bar.y - 7);
      });
      c.restore();
    }
  };

  // Rafraîchissement temps réel : on met à jour l'instance EN PLACE (pas de destroy/
  // recreate) → pas de clignotement du canevas, pas de churn mémoire toutes les 20 s.
  // Les barres qui apparaissent/disparaissent (nouveau jour) sont gérées par update().
  if (chartInstance && silent) {
    const ds = chartInstance.data.datasets[0];
    chartInstance.data.labels = labels;
    ds.data = data;
    ds.backgroundColor = barFill(0.22);       // recalcule la couleur (alerte → ocre)
    ds.hoverBackgroundColor = barFill(0.40);
    const cb = chartInstance.options.plugins.tooltip.callbacks;
    cb.title = tooltipTitle;                  // referme sur les nouvelles `rows`
    cb.label = tooltipLabel;
    chartInstance.update('none');             // sans animation, sans teardown, sans flash
    return;
  }
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  chartInstance = new Chart(document.getElementById('hist-chart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: barFill(0.22),
        hoverBackgroundColor: barFill(0.40),
        borderRadius: { topLeft: 8, topRight: 8, bottomLeft: 2, bottomRight: 2 },
        borderSkipped: false, maxBarThickness: 52, categoryPercentage: 0.7, barPercentage: 0.82
      }]
    },
    plugins: [barShadow, avgLine, valueLabels],
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: reduceMotion ? 0 : 600, easing: 'easeOutQuart' },
      layout: { padding: { top: 10 } },
      plugins: {
        legend: { display: false }, tooltip: {
          backgroundColor: cssVar('--bg-s', d ? '#1E1A13' : '#FFFFFF'),
          borderColor: cssVar('--bd-d', d ? 'rgba(255,255,255,.14)' : '#CDBCA3'),
          borderWidth: 1, titleColor: tp, bodyColor: lc,
          titleFont: { family: FONT_DISP, weight: '600' }, bodyFont: { family: FONT_MONO },
          padding: 12, cornerRadius: 10, displayColors: false,
          // Info-bulle riche et lisible : une ligne = une info, dans un ordre logique
          // (énergie → coût → puissance → nuit → alertes → fiabilité de la mesure).
          callbacks: { title: tooltipTitle, label: tooltipLabel }
        }
      },
      scales: {
        y: { beginAtZero: true, grace: '12%', grid: { color: gc, drawTicks: false }, border: { display: false }, ticks: { font: { family: FONT_MONO, size: 11 }, color: lc, callback: v => unit === 'fcfa' ? v.toLocaleString('fr-FR') : `${v} kWh`, maxTicksLimit: 6, padding: 8 } },
        x: { grid: { display: false }, border: { display: false }, ticks: { font: { family: FONT_MONO, size: 11 }, color: lc, maxTicksLimit: 12, padding: 6 } }
      }
    }
  });
}

function renderSensorSelect() {
  if (histState.sensorsList.length === 0) {
    sensorSelect.style.display = 'none';
    sensorSelect.innerHTML = '<option value="all">Tous les capteurs</option>';
    return;
  }
  sensorSelect.style.display = '';
  sensorSelect.innerHTML = '<option value="all">Tous les capteurs</option>' +
    histState.sensorsList.map(s => `<option value="${esc(String(s.id))}">${esc(s.nom)}</option>`).join('');
  sensorSelect.value = histState.sensor;
}

function updateExportBtn() {
  exportBtn.disabled = histState.exporting;
  exportLabel.textContent = histState.exporting ? 'Export en cours…' : 'Exporter CSV';
  if (pdfBtn) {
    pdfBtn.disabled = histState.exportingPdf;
    if (pdfLabel) pdfLabel.textContent = histState.exportingPdf ? 'Export…' : 'PDF';
  }
}

/* % d'évolution vs période précédente (null si base ≤ 0 → jamais de division absurde). */
function pctEvolution(cur, prev) {
  if (!prev || prev <= 0) return null;
  return Math.round((cur - prev) / prev * 100);
}

/* Bandeau de synthèse en langage simple (orienté coût) : total, comparaison période
   précédente, constat « pic vs disjoncteur » et anomalies. Chiffres 100 % réels ; masqué
   si aucune donnée ; textContent (pas innerHTML) → aucune injection possible. */
const PERIOD_LABELS = { '7j': 'Sur 7 jours', '30j': 'Sur 30 jours', 'mois': 'Ce mois', 'perso': 'Sur la période choisie' };
function renderInsight(rows, total) {
  if (!insightStrip) return;
  if (!rows.length) { insightStrip.hidden = true; insightStrip.textContent = ''; insightStrip.className = 'insight-strip'; return; }
  const parts = [];
  const nJours = rows.length;
  const moyJour = nJours ? total.kwh / nJours : 0;
  const periodeLbl = PERIOD_LABELS[histState.period] || 'Sur la période';
  parts.push(`${periodeLbl} : ≈ ${total.fcfa.toLocaleString('fr-FR')} FCFA d’énergie (estimation tarif CIE, hors abonnement fixe) pour ${total.kwh.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh, soit ${moyJour.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh/jour en moyenne.`);

  // Comparaison vs période précédente, seulement si de VRAIES données existent avant.
  const prev = histState.previous;
  if (prev && prev.kwh > 0) {
    const p = pctEvolution(total.kwh, prev.kwh);
    if (p !== null) {
      parts.push(p === 0
        ? 'Consommation stable par rapport à la période précédente.'
        : `Soit ${Math.abs(p)} % ${p > 0 ? 'de plus' : 'de moins'} que la période précédente (${prev.kwh.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh).`);
    }
  }

  // Constat pic vs disjoncteur (ampérage RÉEL du client).
  let variant = '';
  const cap = capaciteW();
  if (cap) {
    const peakRow = rows.reduce((m, r) => r.peak > m.peak ? r : m, rows[0]);
    const ampTxt = `${histState.amperage} A ≈ ${cap.toLocaleString('fr-FR')} W`;
    const picTxt = peakRow.peak.toLocaleString('fr-FR');
    if (peakRow.peak > cap) {
      variant = 'warn';
      parts.push(`⚠ Le ${peakRow.date}, votre pic de ${picTxt} W a dépassé votre puissance souscrite (${ampTxt}) : le disjoncteur peut couper. Délestez ou augmentez votre abonnement.`);
    } else if (peakRow.peak >= cap * 0.9) {
      variant = 'watch';
      parts.push(`Votre pic de ${picTxt} W approche votre puissance souscrite (${ampTxt}).`);
    }
  }

  // Anomalies de consommation : jour ≥ 2× la médiane des jours consommateurs.
  const med = medianePositive(rows);
  const anomJours = med > 0 ? rows.filter(r => r.kwhExact >= ANOMALY_FACTOR * med).length : 0;
  if (anomJours > 0) {
    if (!variant) variant = 'watch';
    parts.push(`${anomJours} jour${anomJours > 1 ? 's' : ''} de consommation inhabituelle (≥ ${ANOMALY_FACTOR}× votre habitude).`);
  }

  insightStrip.className = 'insight-strip' + (variant ? ' is-' + variant : '');
  insightStrip.textContent = parts.join(' ');
  insightStrip.hidden = false;
}

const NCOLS = 7; // Période, kWh, FCFA, Puissance moy, Nuit, Alertes, Pic
/* Répartition par capteur : tous les capteurs liés, part de chacun sur la période
   (kWh réels + coût estimé au tarif CIE + %). Masquée si moins de 2 capteurs. */
const REP_DV = ['var(--dv-1)', 'var(--dv-2)', 'var(--dv-3)', 'var(--dv-4)', 'var(--dv-5)', 'var(--dv-6)'];
function renderRepartition() {
  const el = document.getElementById('repartition-card');
  if (!el) return;
  const rep = histState.repartition || [];
  if (rep.length < 2) { el.style.display = 'none'; el.innerHTML = ''; return; }
  const totalKwh = rep.reduce((s, r) => s + (r.kwh || 0), 0);
  el.style.display = '';
  const nf2 = v => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  const rows = rep.map((r, i) => {
    const pct = totalKwh > 0 ? Math.round(r.kwh / totalKwh * 100) : 0;
    const barPct = totalKwh > 0 ? Math.max(2, r.kwh / totalKwh * 100) : 0;
    const fcfa = Math.round((r.kwh || 0) * prixMoyenKwh);
    const c = REP_DV[i % REP_DV.length];
    return `<div class="rep-row">
      <div class="rep-name"><span class="rep-dot" style="background:${c}"></span>${esc(r.nom)}</div>
      <div class="rep-track"><span class="rep-bar" style="width:${barPct}%;background:${c}"></span></div>
      <div class="rep-kwh">${nf2(r.kwh)} kWh</div>
      <div class="rep-fcfa">${fcfa.toLocaleString('fr-FR')} F</div>
      <div class="rep-pct">${pct} %</div>
    </div>`;
  }).join('');
  el.innerHTML =
    `<div class="rep-head"><h2 class="rep-title">Répartition par capteur</h2>` +
    `<span class="rep-sub">Part de chaque capteur sur la période · énergie réelle mesurée</span></div>` +
    `<div class="rep-rows">${rows}</div>` +
    `<div class="rep-total"><span>Total</span><strong>${nf2(totalKwh)} kWh · ${Math.round(totalKwh * prixMoyenKwh).toLocaleString('fr-FR')} F</strong></div>`;
}

function renderHistorique(silent) {
  const sort = histState.sort;
  const rows = buildRowsFromJours(histState.jours, histState.alertes);
  const usingApi = rows.length > 0;
  const loading = !histState.loaded;
  const error = histState.loadError;

  const sortKey = sort.f === 'date' ? 'rawDate' : sort.f;
  const sortedData = [...rows].sort((a, b) => {
    const v = a[sortKey] < b[sortKey] ? -1 : a[sortKey] > b[sortKey] ? 1 : 0;
    return v * sort.d;
  });
  const kwhExactTotal = rows.reduce((s, r) => s + r.kwhExact, 0);
  const nightExactTotal = rows.reduce((s, r) => s + (r.nightKwh || 0), 0);
  const total = {
    kwh: Math.round(kwhExactTotal * 100) / 100,
    fcfa: fcfaOf(kwhExactTotal),
    alerts: rows.reduce((s, r) => s + r.alerts, 0),
    peak: rows.reduce((m, r) => Math.max(m, r.peak), 0),
    avgW: rows.length ? Math.round(rows.reduce((s, r) => s + r.avgW, 0) / rows.length) : 0,
    nightKwh: nightExactTotal,
    mesures: rows.reduce((s, r) => s + r.mesures, 0),
  };

  periodBtns.forEach(b => {
    const on = b.dataset.period === histState.period;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });

  const LBLS = ['Consommation totale', 'Coût de l’énergie', 'Pic maximum', 'Jour / Nuit'];
  let stats;
  if (loading) {
    stats = LBLS.map(l => ({ l, v: '…', u: '', s: 'Chargement…' }));
  } else if (error) {
    // Cartes 2-4 : « — » DISCRET (classe stat-empty) et sous-titre VIDE (plus de « — » brut).
    stats = LBLS.map((l, i) => ({ l, v: i === 0 ? 'Indispo.' : '—', u: '', cls: i === 0 ? '' : 'stat-empty',
      s: i === 0 ? 'Erreur de chargement, réessayez dans un instant' : '' }));
  } else if (!usingApi) {
    stats = LBLS.map((l, i) => ({ l, v: i === 0 ? 'Aucune donnée' : '—', u: '', cls: i === 0 ? '' : 'stat-empty',
      s: i === 0 ? 'Aucune mesure reçue pour cette période' : '' }));
  } else {
    const peakRow = rows.reduce((m, r) => r.peak > m.peak ? r : m, rows[0]);
    const capW = capaciteW();
    const nightPct = total.kwh > 0 ? Math.round(total.nightKwh / total.kwh * 100) : 0;
    const dayPct = total.kwh > 0 ? 100 - nightPct : 0;
    const dayKwh = Math.max(0, total.kwh - total.nightKwh);
    const nJours = rows.length;
    const moyJour = nJours ? total.kwh / nJours : 0;
    const prev = histState.previous;
    const pEvo = (prev && prev.kwh > 0) ? pctEvolution(total.kwh, prev.kwh) : null;
    const evoTxt = pEvo === null ? '' : (pEvo === 0 ? ' · stable vs préc.' : ` · ${pEvo > 0 ? '▲' : '▼'} ${Math.abs(pEvo)} % vs préc.`);
    const picOver = !!(capW && total.peak > capW);
    stats = [
      { l: 'Consommation totale', v: total.kwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 }), u: 'kWh',
        s: `${nJours} jour${nJours > 1 ? 's' : ''} · ≈ ${moyJour.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh/jour${evoTxt}` },
      { l: 'Coût de l’énergie', v: total.fcfa.toLocaleString('fr-FR'), u: 'FCFA',
        s: `${total.kwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh × ${prixMoyenKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} F · hors abonnement fixe` },
      { l: 'Pic maximum', v: total.peak.toLocaleString('fr-FR'), u: 'W', cls: picOver ? 'card-alert' : '',
        s: capW ? `le ${peakRow.date} · limite ≈ ${capW.toLocaleString('fr-FR')} W (${histState.amperage} A)` : `le ${peakRow.date} · puiss. moy. ${total.avgW.toLocaleString('fr-FR')} W` },
      { l: 'Jour / Nuit', v: `${dayPct} / ${nightPct}`, u: '%',
        s: `${dayKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh jour · ${total.nightKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh nuit (0h–6h)` },
    ];
  }
  statsGrid.innerHTML = stats.map(s => `<div class="stat-card${s.cls ? ' ' + s.cls : ''}">
    <div class="stat-card-lbl">${esc(s.l)}</div>
    <div class="stat-card-val">${esc(s.v)}${s.u ? `<span class="stat-unit">${esc(s.u)}</span>` : ''}</div>
    <div class="stat-card-sub">${esc(s.s)}</div>
  </div>`).join('');

  renderRepartition();

  dateRangeEl.textContent = loading ? 'Chargement…'
    : error ? 'Erreur de chargement, données indisponibles'
    : (usingApi ? `${rows[0].date} – ${rows[rows.length - 1].date} ${rows[rows.length - 1].rawDate.getFullYear()}`
                : 'Aucune donnée pour cette période');

  if (chartTitleEl) chartTitleEl.textContent = histState.unit === 'fcfa'
    ? 'Coût journalier estimé (FCFA)'
    : 'Consommation journalière (kWh)';
  renderChart(rows, silent);
  renderInsight((loading || error || !usingApi) ? [] : rows, total);

  // Profondeur des données : la fenêtre demandée peut couvrir plus de jours que ceux
  // réellement mesurés (ex. « 30 jours » mais 3 jours reçus) → on le dit honnêtement.
  if (dataDepthNote) {
    let winDays = rows.length;
    if (histState.winFrom && histState.winTo) {
      winDays = Math.round((new Date(histState.winTo + 'T00:00:00') - new Date(histState.winFrom + 'T00:00:00')) / 86400000) + 1;
    }
    if (!loading && !error && usingApi && winDays > rows.length) {
      dataDepthNote.hidden = false;
      dataDepthNote.textContent = `${rows.length} jour${rows.length > 1 ? 's' : ''} avec des mesures sur les ${winDays} jours de la période.`;
    } else {
      dataDepthNote.hidden = true;
      dataDepthNote.textContent = '';
    }
  }

  const SORT_LABELS = { date: 'Période', kwh: 'kWh', fcfa: 'FCFA', avgW: 'Puiss. moy.', nightKwh: 'Nuit', alerts: 'Alertes', peak: 'Pic' };
  const sortWord = sort.d === 1 ? 'croissant' : 'décroissant';
  tableMeta.textContent = `${rows.length} entrées · Tri ${SORT_LABELS[sort.f] || sort.f} ${sortWord}`;
  sortHeaders.forEach(th => {
    const f = th.dataset.field;
    const isActive = sort.f === f;
    const ico = th.querySelector('.sort-ico');
    if (ico) ico.textContent = isActive ? (sort.d === 1 ? '↑' : '↓') : '↕';
    th.setAttribute('aria-sort', isActive ? (sort.d === 1 ? 'ascending' : 'descending') : 'none');
  });

  const cell = (v, cls) => `<td class="cell-num${cls ? ' ' + cls : ''}">${v}</td>`;
  const med = medianePositive(rows);
  const emptyMsg = loading ? 'Chargement…' : error ? 'Erreur de chargement, données indisponibles' : 'Aucune donnée pour cette période';
  histTbody.innerHTML = (loading || error || rows.length === 0)
    ? `<tr><td colspan="${NCOLS}" style="text-align:center;color:var(--tx-m);padding:22px">${emptyMsg}</td></tr>`
    : sortedData.map(r => {
      const anom = med > 0 && r.kwhExact >= ANOMALY_FACTOR * med;
      // Jour mesuré mais arrondi à 0,00 → « ≈ 0,00 » (évite le « 0 kWh mais 154 W » trompeur).
      const kwhStr = (r.kwhExact > 0 && r.kwh === 0 ? '≈ ' : '') + r.kwh.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const dateCell = `${esc(r.date)}${anom ? ' <span class="anom-dot" title="Consommation inhabituelle (≥ 2× votre habitude)" aria-label="jour inhabituel">●</span>' : ''}`;
      return `<tr${anom ? ' class="row-anom"' : ''}>
      <td>${dateCell}</td>
      ${cell(kwhStr)}
      ${cell(r.fcfa.toLocaleString('fr-FR') + ' FCFA')}
      ${cell(r.avgW.toLocaleString('fr-FR') + ' W')}
      ${cell(r.nightKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' kWh')}
      <td><span class="badge-alert ${r.alerts === 0 ? 'ba-0' : 'ba-n'}">${r.alerts}</span></td>
      ${cell(r.peak.toLocaleString('fr-FR') + ' W', peakClass(r.peak))}
    </tr>`;
    }).join('') + `<tr class="tbl-total">
      <td>Total ${rows.length} jours</td>
      ${cell(total.kwh.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' kWh')}
      ${cell(total.fcfa.toLocaleString('fr-FR') + ' FCFA')}
      ${cell(total.avgW.toLocaleString('fr-FR') + ' W')}
      ${cell(total.nightKwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' kWh')}
      ${cell(total.alerts)}
      ${cell(total.peak.toLocaleString('fr-FR') + ' W', peakClass(total.peak))}
    </tr>`;

  // Annonce lecteur d'écran concise, UNIQUEMENT sur action utilisateur (pas les ticks
  // temps réel) : sinon la région serait relue toutes les 20 s.
  if (liveStatus && !silent) {
    liveStatus.textContent = loading ? 'Chargement de l’historique…'
      : error ? 'Erreur de chargement des données.'
      : !usingApi ? 'Aucune donnée pour cette période.'
      : `${rows.length} jour${rows.length > 1 ? 's' : ''}, ${total.kwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh, ${total.fcfa.toLocaleString('fr-FR')} FCFA.`;
  }

  updateExportBtn();
}

/* Charge l'historique DÉJÀ AGRÉGÉ par jour (rapide) depuis /api/analytics/historique/.
   opts.silent = rafraîchissement temps réel : pas d'état « Chargement… », re-rendu
   UNIQUEMENT si les données ont changé, et graphe sans animation (pas de clignotement). */
let histReqSeq = 0;
let histInFlight = false;
function loadMesures(opts) {
  const silent = !!(opts && opts.silent);
  // Évite d'empiler des requêtes silencieuses qui se chevauchent (retour d'onglet +
  // tick d'intervalle). Une action utilisateur, elle, passe toujours.
  if (silent && histInFlight) return;

  let url = '/api/analytics/historique/?';
  if (histState.period === 'mois') {
    // date_to OMIS volontairement : le serveur borne à SON « maintenant » (fuseau
    // Africa/Abidjan). Sinon, près de minuit et avec un navigateur dans un autre
    // fuseau, on exclurait le jour serveur en cours → données du jour manquantes
    // alors que le badge annonce « En direct ».
    const now = new Date();
    url += `date_from=${fmtDate(new Date(now.getFullYear(), now.getMonth(), 1))}`;
  } else if (histState.period === 'perso' && histState.customFrom && histState.customTo) {
    url += `date_from=${histState.customFrom}&date_to=${histState.customTo}`;
  } else {
    url += `period=${PERIOD_MAP[histState.period] || 'week'}`;
  }
  if (histState.sensor !== 'all') url += `&sensor_id=${histState.sensor}`;

  // Anti-course : si l'utilisateur change de filtre pendant qu'une requête est en vol,
  // seule la DERNIÈRE réponse est prise en compte (les périmées sont ignorées).
  const seq = ++histReqSeq;
  histInFlight = true;
  if (!silent) { histState.loaded = false; histState.loadError = false; renderHistorique(); } // état « chargement »
  // On rafraîchit AUSSI les alertes (colonne « Alertes » + couleur des barres). MAIS
  // les alertes sont SECONDAIRES : leur échec ne doit pas effacer la consommation qui,
  // elle, a bien chargé. → l'appel alertes a son propre .catch(()=>null) ; seul l'échec
  // de l'historique (donnée primaire) fait rejeter le Promise.all et part en erreur.
  Promise.all([fetchWithAuth(url), fetchWithAuth('/api/alertes/').catch(() => null)])
    .then(([data, al]) => {
      if (seq !== histReqSeq) return;
      // État AVANT maj : sert à forcer un redessin quand on SORT d'une erreur / d'un
      // chargement (sinon un tick silencieux « rien de neuf » laisserait l'écran figé
      // sur « Erreur de chargement » alors que l'état est de nouveau bon).
      const wasErrorOrLoading = histState.loadError || !histState.loaded;
      const jours = (data && Array.isArray(data.jours)) ? data.jours : [];
      // Alertes indisponibles → on garde les précédentes (pas de perte, pas de faux 0).
      const alertes = (al === null) ? (histState.alertes || []) : window.AOCEDA.asList(al);
      if (data && data.prix_kwh) prixMoyenKwh = Number(data.prix_kwh);
      // Ampérage souscrit RÉEL (déjà renvoyé par l'API) → capacité « pic vs disjoncteur ».
      if (data && (data.amperage || data.amperage === 0)) histState.amperage = Number(data.amperage);
      // Période précédente (comparaison honnête, null si aucune donnée) + fenêtre calendaire réelle.
      histState.previous = (data && data.previous) || null;
      histState.winFrom = (data && data.date_from) || '';
      histState.winTo = (data && data.date_to) || '';
      // Signature = jours + prix + ampérage + précédent + alertes → tout changement redessine.
      const repartition = (data && Array.isArray(data.repartition)) ? data.repartition : [];
      const sig = JSON.stringify(jours) + '|' + prixMoyenKwh + '|' + histState.amperage + '|' + JSON.stringify(histState.previous) + '|' + JSON.stringify(alertes) + '|' + JSON.stringify(repartition);
      const changed = sig !== histState._sig;
      histState.jours = jours;
      histState.repartition = repartition;
      histState.alertes = alertes;
      histState._sig = sig;
      histState.loaded = true;
      histState.loadError = false;
      updateLiveBadge();
      // Silencieux + rien de neuf + pas de sortie d'erreur → on ne redessine pas.
      if (!silent || changed || wasErrorOrLoading) renderHistorique(silent);
    })
    .catch(err => {
      if (seq !== histReqSeq) return;
      console.error(err);
      // Un échec n'est JAMAIS « En direct » : on masque le badge (plus de faux direct).
      if (liveBadge) liveBadge.hidden = true;
      // On ne touche pas aux données déjà affichées (rafraîchissement silencieux) ; sur
      // une action utilisateur, on montre une vraie erreur, surtout PAS « 0 kWh ».
      if (!silent) { histState.loadError = true; histState.loaded = true; renderHistorique(); }
    })
    // Reset gardé par seq : une requête périmée ne libère PAS le verrou d'une requête
    // plus récente encore en vol (sinon un tick silencieux pourrait s'y glisser et
    // laisser un « Chargement… » figé).
    .then(() => { if (seq === histReqSeq) histInFlight = false; });
}

function initHistorique() {
  // Pré-remplit la plage personnalisée (7 derniers jours) et interdit le futur.
  if (dateFromInput && dateToInput) {
    const now = new Date();
    const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 6);
    dateToInput.value = fmtDate(now);
    dateFromInput.value = fmtDate(weekAgo);
    dateToInput.max = fmtDate(now);
    dateFromInput.max = fmtDate(now);
    histState.customFrom = dateFromInput.value;
    histState.customTo = dateToInput.value;
  }
  syncCustomRangeUI();
  renderSensorSelect();
  renderHistorique();
  fetchWithAuth('/api/sensors/')
    .then(data => { histState.sensorsList = window.AOCEDA.asList(data); renderSensorSelect(); })
    .catch(err => console.error(err));
  // Les alertes sont désormais récupérées PAR loadMesures (à chaque tick), donc pas de
  // fetch séparé ici : ça garde la colonne « Alertes » et la couleur des barres à jour.
  loadMesures();
  scheduleRefresh(); // le jour en cours se met à jour tout seul (toutes les 20 s)
}

/* ════════════════ Écouteurs ════════════════ */
periodBtns.forEach(b => b.addEventListener('click', () => {
  const k = b.dataset.period;
  if (histState.period === k) return;
  histState.period = k;
  syncCustomRangeUI();
  renderHistorique();
  // « Personnalisé » : on ne recharge qu'au clic « Appliquer » (2 dates valides).
  if (k === 'perso') {
    if (histState.customFrom && histState.customTo) loadMesures();
    return;
  }
  loadMesures();
}));

if (crApplyBtn) crApplyBtn.addEventListener('click', () => {
  const from = dateFromInput && dateFromInput.value;
  const to = dateToInput && dateToInput.value;
  if (!from || !to) { dateRangeEl.textContent = 'Choisissez une date de début et de fin'; return; }
  if (from > to) { dateRangeEl.textContent = 'La date de début doit précéder la date de fin'; return; }
  histState.period = 'perso';
  histState.customFrom = from;
  histState.customTo = to;
  syncCustomRangeUI();
  renderHistorique();
  loadMesures();
});

sensorSelect.addEventListener('change', e => {
  histState.sensor = e.target.value;
  loadMesures();
});

/* Bascule FCFA ⇄ kWh du graphique : pas de requête réseau, on redessine juste (le graphe
   est détruit/recréé avec la nouvelle unité). Les données restent réelles. */
unitBtns.forEach(b => b.addEventListener('click', () => {
  const u = b.dataset.unit;
  if (histState.unit === u) return;
  histState.unit = u;
  unitBtns.forEach(x => {
    const on = x.dataset.unit === u;
    x.classList.toggle('active', on);
    x.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  renderHistorique();
}));

function applySort(f) {
  histState.sort = histState.sort.f === f ? { f, d: -histState.sort.d } : { f, d: 1 };
  renderHistorique();
}
sortHeaders.forEach(th => {
  th.addEventListener('click', () => applySort(th.dataset.field));
  th.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      applySort(th.dataset.field);
    }
  });
});

/* Construit la query d'export (CSV/PDF) : EXACTEMENT la même plage que le tableau affiché. */
function exportQuery() {
  let q;
  if (histState.period === 'mois') {
    // « Ce mois » = du 1er à maintenant. date_to omis → le serveur borne à SON « maintenant »
    // (fuseau Abidjan), comme loadMesures, pour éviter l'écart de fuseau navigateur.
    const now = new Date();
    q = `date_from=${fmtDate(new Date(now.getFullYear(), now.getMonth(), 1))}`;
  } else if (histState.period === 'perso' && histState.customFrom && histState.customTo) {
    q = `date_from=${histState.customFrom}&date_to=${histState.customTo}`;
  } else {
    q = `period=${PERIOD_MAP[histState.period] || 'week'}`;
  }
  if (histState.sensor !== 'all') q += `&sensor_id=${histState.sensor}`;
  return q;
}

exportBtn.addEventListener('click', () => {
  if (histState.exporting) return;
  histState.exporting = true;
  updateExportBtn();
  downloadCSV(`/api/analytics/export/?${exportQuery()}`, 'aoceda_historique.csv')
    .catch(err => console.error(err))
    .then(() => { histState.exporting = false; updateExportBtn(); });
});

if (pdfBtn) pdfBtn.addEventListener('click', () => {
  if (histState.exportingPdf) return;
  histState.exportingPdf = true;
  updateExportBtn();
  // downloadCSV = téléchargeur blob générique (nom via Content-Disposition) → sert aussi au PDF.
  downloadCSV(`/api/analytics/export/pdf/?${exportQuery()}`, 'aoceda_historique.pdf')
    .catch(err => console.error(err))
    .then(() => { histState.exportingPdf = false; updateExportBtn(); });
});

/* ════════════════ Démarrage ════════════════ */
applyTheme();
initHistorique();

fetchWithAuth('/api/analytics/facture/')
  .then(data => {
    // Prix STABLE (marginal T1 + taxes, ~92,5 F). PAS prix_moyen_kwh, qui explose
    // en début de mois (prime fixe ÷ kWh minuscules) → colonne FCFA ×40 fausse.
    const p = data && (data.prix_kwh_tout_compris || data.prix_moyen_kwh);
    if (p) {
      prixMoyenKwh = Number(p);
      renderHistorique();
    }
  })
  .catch(err => console.error(err));
