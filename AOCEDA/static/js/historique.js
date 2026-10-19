'use strict';
const t = window.AOCEDA_T || (x => x);
/* ════════════════════════════════════════════════════════════
   AOCEDA, Historique de consommation (Chart.js, vanilla JS)
   Réécrit le 19/10/2026 après audit : chargement rapide, jours « éteint » (vrai 0) distingués des jours sans mesure,
   état réel du boîtier, détail d'un jour heure par heure, comparaison tracée, habitudes, conseil calculé.
   La traduction anglaise est faite par la page entière (i18n.js) : les textes sont écrits en français ici.
   ════════════════════════════════════════════════════════════ */

const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}
const LOCALE = window.AOCEDA_LANG === 'en' ? 'en-GB' : 'fr-FR';

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. On REJETTE sur tout statut non-OK
   (sinon une erreur serveur à corps JSON serait lue comme un succès « vide » et effacerait les vraies données). */
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
const $ = id => document.getElementById(id);

/* Export (Authorization requis → fetch → blob → lien temporaire) */
function downloadFile(url, fallbackName) {
  return window.AOCEDA.authFetch(url)
    .then(res => {
      if (!res.ok) throw new Error('Export impossible');
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : fallbackName;
      return res.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => window.AOCEDA.downloadBlob(blob, filename));
}

/* ── Formats : tout en français, 2 décimales pour les kWh partout ── */
function kwh2(v) {
  return Number(v || 0).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function nb(v, dec) { return Number(v || 0).toLocaleString(LOCALE, { maximumFractionDigits: dec == null ? 0 : dec }); }
const pad2 = n => String(n).padStart(2, '0');
const fmtDate = dt => `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
const parseISO = iso => new Date(iso + 'T00:00:00');
const dayShort = d => d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' });
const dayMid = d => d.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short' });
const dayLong = d => d.toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

/* Prix du kWh tout compris (fourni par l'API) : null tant qu'il n'est pas connu. Aucun tarif supposé :
   avant le 19/10/2026, 87 F codés en dur s'affichaient en attendant. */
const histState = {
  period: '7j', sensor: 'all', sensorsList: [],
  jours: [], manquants: [], previous: null, repartition: [],
  loaded: false, loadError: false, exporting: false, exportingDay: false, exportingPdf: false,
  sort: { f: 'date', d: 1 },
  customFrom: '', customTo: '',
  amperage: null,
  prix: null,
  unit: 'fcfa',
  winFrom: '', winTo: '',
  enLigne: false, dernierContact: null, derniereMesure: null,
  factDebut: '', factType: '',
  detailIso: null,           // jour ouvert dans « Détail du jour »
  _sig: '',
};
function fcfaOf(kwh) { return histState.prix ? Math.round(kwh * histState.prix) : null; }

/* Répartit un total ENTIER entre des parts réelles, la somme des entiers rendus == total (plus grand reste). Sert
   aux lignes du tableau : « Σ des lignes == total affiché » (avant : 106 662 au total, 106 666 en additionnant). */
function repartirEntier(parts, total) {
  const somme = parts.reduce((s, v) => s + (v || 0), 0);
  if (somme <= 0) return parts.map(() => 0);
  const bruts = parts.map(v => (v || 0) / somme * total);
  const bas = bruts.map(Math.floor);
  let reste = total - bas.reduce((s, v) => s + v, 0);
  const ordre = bruts.map((v, i) => ({ i, frac: v - Math.floor(v) })).sort((a, b) => b.frac - a.frac);
  for (let k = 0; k < ordre.length && reste > 0; k++, reste--) bas[ordre[k].i] += 1;
  return bas;
}

/* ── Puissance souscrite (disjoncteur) : miroir de PUISSANCE_KW (tarifs_cie.py) ── */
const CAP_KW = { 5: 1.1, 10: 2.2, 15: 3.3 };
function capaciteW() {
  const kw = CAP_KW[histState.amperage];
  return kw ? Math.round(kw * 1000) : null;
}
function niveauPic(peakW) {
  const cap = capaciteW();
  if (!cap || !peakW) return '';
  if (peakW > cap) return 'over';
  if (peakW >= cap * 0.9) return 'near';
  return '';
}
const peakClass = w => ({ over: 'peak-over', near: 'peak-near' }[niveauPic(w)] || '');

/* Jour inhabituel : consommation ≥ 2 × la médiane des jours consommateurs */
const ANOMALY_FACTOR = 2;
function medianePositive(rows) {
  const xs = rows.map(r => r.kwhExact).filter(v => v > 0).sort((a, b) => a - b);
  if (!xs.length) return 0;
  const m = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[m] : (xs[m - 1] + xs[m]) / 2;
}

/* Lignes d'affichage : un jour = une ligne, qu'il soit mesuré, « éteint » (boîtier en ligne, 0 kWh) ou « manquant »
   (aucune trace du boîtier : inconnu, jamais un 0 inventé). Les valeurs affichées sont réparties pour que les sommes
   tombent juste (kWh au centième, FCFA à l'entier). */
function buildRows() {
  const map = new Map();
  (histState.jours || []).forEach(j => map.set(j.date, {
    iso: j.date, etat: j.etat, kwhExact: Number(j.kwh) || 0, avgW: Math.round(Number(j.avg_w) || 0),
    peak: Math.round(Number(j.peak_w) || 0), nightKwh: Number(j.night_kwh) || 0, mesures: Number(j.n) || 0,
    alerts: Number(j.alertes) || 0,
  }));
  (histState.manquants || []).forEach(d => map.set(d, {
    iso: d, etat: 'manquant', kwhExact: 0, avgW: 0, peak: 0, nightKwh: 0, mesures: 0, alerts: 0,
  }));
  const rows = [...map.values()].sort((a, b) => a.iso < b.iso ? -1 : 1);
  rows.forEach(r => { r.rawDate = parseISO(r.iso); r.date = dayMid(r.rawDate); });
  const vus = rows.filter(r => r.etat !== 'manquant');
  const exact = vus.reduce((s, r) => s + r.kwhExact, 0);
  const centi = repartirEntier(vus.map(r => r.kwhExact * 100), Math.round(exact * 100));
  vus.forEach((r, i) => { r.kwh = centi[i] / 100; });
  const totalF = fcfaOf(exact);
  const parts = totalF === null ? vus.map(() => null)
    : repartirEntier(vus.map(r => r.kwhExact * histState.prix), totalF);
  vus.forEach((r, i) => { r.fcfa = parts[i]; });
  rows.filter(r => r.etat === 'manquant').forEach(r => { r.kwh = null; r.fcfa = null; });
  const mes = vus.reduce((s, r) => s + r.mesures, 0);
  const total = {
    kwhExact: exact, kwh: Math.round(exact * 100) / 100, fcfa: totalF,
    alerts: vus.reduce((s, r) => s + r.alerts, 0),
    peak: vus.reduce((m, r) => Math.max(m, r.peak), 0),
    // moyenne PONDÉRÉE par le nombre de mesures (et non moyenne des moyennes)
    avgW: mes ? Math.round(vus.reduce((s, r) => s + r.avgW * r.mesures, 0) / mes) : 0,
    nightKwh: vus.reduce((s, r) => s + r.nightKwh, 0), mesures: mes,
    nMesure: rows.filter(r => r.etat === 'mesure').length,
    nEteint: rows.filter(r => r.etat === 'eteint').length,
    nManquant: rows.filter(r => r.etat === 'manquant').length,
  };
  return { rows, total };
}

/* ════════════════ Thème ════════════════ */
const MOON_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const SUN_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
let theme = document.documentElement.getAttribute('data-theme') || 'light';
const themeToggleBtn = $('theme-toggle');
function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  if (themeToggleBtn) themeToggleBtn.innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
}
if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => {
  theme = window.AOCEDA.toggleTheme();
  applyTheme();
  renderHistorique();
  renderDay();
});

/* ════════════════ Éléments ════════════════ */
const sensorSelect = $('sensor-select');
const dateRangeEl = $('date-range');
const exportBtn = $('export-btn'), exportLabel = $('export-label');
const exportDayBtn = $('export-day-btn'), exportDayLabel = $('export-day-label');
const pdfBtn = $('pdf-btn'), pdfLabel = $('pdf-label');
const statsGrid = $('stats-grid');
const insightStrip = $('insight-strip'), insightCard = $('insight-card');
const unitBtns = Array.from(document.querySelectorAll('.ut'));
const chartTitleEl = $('chart-title');
const dataDepthNote = $('data-depth-note');
const tableMeta = $('table-meta');
const histTbody = $('hist-tbody');
const periodBtns = Array.from(document.querySelectorAll('.pt'));
const sortHeaders = Array.from(document.querySelectorAll('th[data-field]'));
const customRangeEl = $('custom-range');
const dateFromInput = $('date-from'), dateToInput = $('date-to'), crApplyBtn = $('cr-apply');
const liveBadge = $('live-badge'), liveStatus = $('live-status');
const chartCard = $('chart-card'), dayCard = $('day-card'), histGrid = $('hist-grid');

function syncCustomRangeUI() {
  if (customRangeEl) customRangeEl.style.display = histState.period === 'perso' ? '' : 'none';
}
const isToday = () => histState.period === 'auj';

/* ════════════════ Temps réel ════════════════
   Le jour en cours grandit au fil des mesures : on ne rafraîchit (toutes les 30 s) que si la plage affichée inclut
   aujourd'hui, et jamais pendant un export ou un chargement. */
const REFRESH_MS = 30000;
let refreshTimer = null;
function rangeIncludesToday() {
  if (histState.period === 'perso') return !histState.customTo || histState.customTo >= fmtDate(new Date());
  return true;
}
function quand(iso) { return iso ? new Date(iso) : null; }
function agoText(d) {
  if (!d) return '';
  const s = Math.max(1, Math.round((Date.now() - d.getTime()) / 1000));
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `le ${dayShort(d)} à ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
/* Badge d'état du boîtier : « En direct » SEULEMENT si le boîtier répond (avant le 19/10/2026 il s'affichait
   toujours, même sans capteur ou boîtier muet depuis des jours). */
function updateStateBadge() {
  if (!liveBadge) return;
  const b = liveBadge;
  const aCapteur = (histState.repartition || []).length > 0 || histState.derniereMesure;
  if (!histState.loaded || histState.loadError) { b.hidden = true; return; }
  if (!aCapteur) {
    b.hidden = false; b.className = 'live-badge is-off'; b.textContent = t('Aucun capteur installé'); b.title = '';
    return;
  }
  if (!rangeIncludesToday()) { b.hidden = true; return; }
  b.hidden = false;
  if (histState.enLigne) {
    b.className = 'live-badge is-live';
    b.innerHTML = '<span class="live-dot" aria-hidden="true"></span>' + esc(t('En direct')) + ' · ' + esc(new Date().toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }));
    b.title = t('Le jour en cours se met à jour automatiquement');
  } else {
    b.className = 'live-badge is-off';
    b.textContent = `${t('Hors ligne')} · ${t('dernière mesure')} ${agoText(quand(histState.dernierContact))}`;
    b.title = t('Le boîtier ne répond plus : le jour en cours n’est pas mis à jour.');
  }
}
function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (document.hidden || histState.exporting || histState.exportingDay || !histState.loaded) return;
    if (!rangeIncludesToday()) return;
    loadMesures({ silent: true });
  }, REFRESH_MS);
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && histState.loaded && !histState.exporting && rangeIncludesToday()) loadMesures({ silent: true });
});

/* ════════════════ Graphique : un jour par barre ════════════════ */
let chartInstance = null, dayChartInstance = null;
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
const FONT_MONO = "'Spline Sans Mono', ui-monospace, monospace";
const FONT_DISP = "'Hanken Grotesk', system-ui, sans-serif";
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
const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const WHITE = [255, 255, 255];

function palette() {
  const d = theme === 'dark';
  return {
    d,
    grid: d ? 'rgba(255,255,255,.06)' : 'rgba(35,27,16,.07)',
    label: cssVar('--tx-s', d ? '#C2B19A' : '#6B5A45'),
    text: cssVar('--tx-p', d ? '#F0E9DC' : '#231B10'),
    normal: toRGB(cssVar('--chart-normal', cssVar('--dv-2', '#1B7A6E'))),
    high: toRGB(cssVar('--chart-high', cssVar('--ac-text', '#9C5A07'))),
    surface: cssVar('--bg-s', d ? '#1E1A13' : '#FFFFFF'),
    border: cssVar('--bd-d', d ? 'rgba(255,255,255,.14)' : '#CDBCA3'),
  };
}
function tooltipBase(p) {
  return {
    backgroundColor: p.surface, borderColor: p.border, borderWidth: 1, titleColor: p.text, bodyColor: p.label,
    titleFont: { family: FONT_DISP, weight: '600' }, bodyFont: { family: FONT_MONO },
    padding: 12, cornerRadius: 10, displayColors: false,
  };
}

function renderChart(rows, silent) {
  const canvas = $('hist-chart');
  if (!canvas) return;
  const p = palette();
  const unit = histState.unit;
  const reduceMotion = silent || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const prix = histState.prix;
  const val = r => r.etat === 'manquant' ? null : (unit === 'fcfa' ? r.fcfa : r.kwh);
  const labels = rows.map(r => rows.length <= 8 ? dayMid(r.rawDate) : dayShort(r.rawDate));
  const data = rows.map(val);
  const baseRGB = rows.map(r => r.alerts === 0 ? p.normal : p.high);

  // Période précédente tracée en pointillé : le jour n d'avant face au jour n de la période (par DATE, pas par rang)
  const prev = histState.previous;
  let prevData = null;
  if (prev && prev.jours && prev.jours.length && histState.winFrom) {
    const map = new Map(prev.jours.map(j => [j.date, j.kwh]));
    const debutPrev = parseISO(prev.date_from);
    prevData = rows.map((_, i) => {
      const d = new Date(debutPrev); d.setDate(d.getDate() + i);
      const k = map.get(fmtDate(d));
      if (k === undefined) return null;
      return unit === 'fcfa' ? (prix ? Math.round(k * prix) : null) : Math.round(k * 100) / 100;
    });
    if (!prevData.some(v => v !== null)) prevData = null;
  }
  const legendPrev = $('legend-prev');
  if (legendPrev) legendPrev.hidden = !prevData;

  const tooltipTitle = items => { const r = rows[items[0].dataIndex]; return r ? dayLong(r.rawDate) : ''; };
  const tooltipLabel = c => {
    const r = rows[c.dataIndex];
    if (!r) return '';
    if (c.dataset.isPrev) {
      const k = c.raw;
      return k === null ? '' : `${t('Période précédente')} : ${unit === 'fcfa' ? nb(k) + ' F' : kwh2(k) + ' kWh'}`;
    }
    if (r.etat === 'manquant') return [t('Aucune mesure reçue'), t('(boîtier hors ligne : valeur inconnue)')];
    if (r.etat === 'eteint') return [`0,00 ${t('kWh')}`, t('Éteint (boîtier en ligne, rien consommé)')];
    const lines = [
      `${kwh2(r.kwh)} ${t('kWh consommés')}`,
      r.fcfa === null ? '' : `≈ ${nb(r.fcfa)} ${t('FCFA (tarif CIE)')}`,
      `${t('Puissance en marche')} ${nb(r.avgW)} W · ${t('pic')} ${nb(r.peak)} W`,
    ].filter(Boolean);
    if (r.nightKwh > 0) lines.push(`${t('Dont nuit (22h–6h) :')} ${nb(r.nightKwh, 2)} kWh`);
    if (r.alerts > 0) lines.push(`⚠ ${r.alerts} ${r.alerts > 1 ? t('alertes') : t('alerte')} ${t('ce jour')}`);
    lines.push(t('Cliquez pour voir ce jour heure par heure'));
    return lines;
  };
  const barFill = lighten => ctx => {
    const area = ctx.chart.chartArea;
    const base = baseRGB[ctx.dataIndex] || p.normal;
    if (!area) return rgba(base, 1);
    const g = ctx.chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
    g.addColorStop(0, rgba(base, 1));
    g.addColorStop(1, rgba(mix(base, WHITE, lighten), 1));
    return g;
  };
  const avgLine = {
    id: 'avgLine',
    beforeDatasetsDraw(chart) {
      const ds = chart.data.datasets[0].data.filter(v => v !== null && v !== undefined);
      const y = chart.scales.y, area = chart.chartArea;
      if (!ds.length || !y || !area) return;
      const yp = y.getPixelForValue(ds.reduce((s, v) => s + v, 0) / ds.length);
      const c = chart.ctx;
      c.save(); c.strokeStyle = rgba(toRGB(p.label), 0.6); c.lineWidth = 1.5; c.setLineDash([5, 4]);
      c.beginPath(); c.moveTo(area.left, yp); c.lineTo(area.right, yp); c.stroke(); c.restore();
    }
  };
  // Valeurs au-dessus des barres : toutes si la période est courte, sinon seulement le jour le plus fort (au-delà,
  // 25 étiquettes se superposaient et devenaient illisibles)
  const valueLabels = {
    id: 'valueLabels',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      const ds = chart.data.datasets[0].data;
      const max = Math.max(...ds.filter(v => v !== null), 0);
      const c = chart.ctx;
      c.save(); c.shadowColor = 'transparent'; c.font = `600 11px ${FONT_MONO}`; c.fillStyle = p.text;
      c.textAlign = 'center'; c.textBaseline = 'bottom';
      meta.data.forEach((bar, i) => {
        const v = ds[i];
        if (v === null || v === undefined || v <= 0) return;
        if (ds.length > 10 && v !== max) return;
        c.fillText(unit === 'fcfa' ? nb(v) : nb(v, 1), bar.x, bar.y - 6);
      });
      c.restore();
    }
  };
  const datasets = [{
    type: 'bar', data, order: 2,
    backgroundColor: barFill(0.22), hoverBackgroundColor: barFill(0.40),
    borderRadius: { topLeft: 8, topRight: 8, bottomLeft: 2, bottomRight: 2 },
    borderSkipped: false, maxBarThickness: 56, categoryPercentage: 0.75, barPercentage: 0.85,
  }];
  if (prevData) {
    datasets.push({
      type: 'line', data: prevData, isPrev: true, order: 1, borderColor: rgba(toRGB(p.label), 0.9), borderWidth: 2,
      borderDash: [6, 4], pointRadius: 3, pointBackgroundColor: p.surface, pointBorderColor: rgba(toRGB(p.label), 0.9),
      pointBorderWidth: 1.5, tension: 0.25, spanGaps: false, fill: false,
    });
  }

  const sig = `${labels.length}|${datasets.length}|${unit}`;
  if (chartInstance && chartInstance.__sig === sig && silent) {
    chartInstance.data.labels = labels;
    datasets.forEach((ds, i) => { chartInstance.data.datasets[i].data = ds.data; });
    chartInstance.data.datasets[0].backgroundColor = barFill(0.22);
    chartInstance.data.datasets[0].hoverBackgroundColor = barFill(0.40);
    chartInstance.__rows = rows;
    const cb = chartInstance.options.plugins.tooltip.callbacks;
    cb.title = tooltipTitle; cb.label = tooltipLabel;
    chartInstance.update('none');
    return;
  }
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  chartInstance = new Chart(canvas, {
    type: 'bar',
    data: { labels, datasets },
    plugins: [avgLine, valueLabels],
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: reduceMotion ? 0 : 600, easing: 'easeOutQuart' },
      layout: { padding: { top: 16 } },
      interaction: { mode: 'index', intersect: false },
      onClick: (e, els, chart) => {
        const el = chart.getElementsAtEventForMode(e, 'index', { intersect: false }, true)[0];
        const r = el && chartInstance.__rows[el.index];
        if (r && r.etat !== 'manquant') openDay(r.iso);
      },
      onHover: (e, els, chart) => {
        const el = chart.getElementsAtEventForMode(e, 'index', { intersect: false }, true)[0];
        const r = el && chartInstance.__rows[el.index];
        e.native.target.style.cursor = r && r.etat !== 'manquant' ? 'pointer' : 'default';
      },
      plugins: {
        legend: { display: false },
        tooltip: Object.assign(tooltipBase(p), { callbacks: { title: tooltipTitle, label: tooltipLabel } }),
      },
      scales: {
        y: { beginAtZero: true, grace: '14%', grid: { color: p.grid, drawTicks: false }, border: { display: false },
          ticks: { font: { family: FONT_MONO, size: 11 }, color: p.label, maxTicksLimit: 6, padding: 8,
            callback: v => unit === 'fcfa' ? nb(v) : `${nb(v, 1)} kWh` } },
        x: { grid: { display: false }, border: { display: false },
          ticks: { font: { family: FONT_MONO, size: 11 }, color: p.label, maxTicksLimit: 10, maxRotation: 0, autoSkip: true, padding: 6 } }
      }
    }
  });
  chartInstance.__sig = sig;
  chartInstance.__rows = rows;
  canvas.setAttribute('aria-label', `${t('Consommation par jour')} : ${rows.length} ${t('jours')}`);
}

/* ════════════════ Détail d'un jour, heure par heure ════════════════ */
let dayData = null;      // {iso, slots:[{h, kwh|null}], loading, error}
let daySeq = 0;
function sensorQuery() { return histState.sensor !== 'all' ? `&sensor_id=${encodeURIComponent(histState.sensor)}` : ''; }

function openDay(iso, opts) {
  histState.detailIso = iso;
  dayData = { iso, slots: [], loading: true, error: false };
  dayCard.hidden = false;
  renderDay();
  highlightRow();
  if (!(opts && opts.noScroll) && !isToday()) {
    try { dayCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) { /* ancien navigateur */ }
  }
  loadDay(iso);
}
function closeDay() {
  histState.detailIso = null;
  dayData = null;
  dayCard.hidden = true;
  highlightRow();
}
function loadDay(iso) {
  const seq = ++daySeq;
  fetchWithAuth(`/api/mesures/serie/?date_from=${iso}&date_to=${iso}${sensorQuery()}`)
    .then(data => {
      if (seq !== daySeq || !dayData || dayData.iso !== iso) return;
      const list = window.AOCEDA.asList(data);
      const byHour = new Map();
      list.forEach(m => {
        const h = parseInt(String(m.timestamp).slice(11, 13), 10);   // heure LOCALE du serveur (ISO avec décalage)
        if (isNaN(h)) return;
        byHour.set(h, (byHour.get(h) || 0) + (parseFloat(m.energie) || 0));
      });
      const now = new Date();
      const dernier = iso === fmtDate(now) ? now.getHours() : 23;
      dayData.slots = Array.from({ length: dernier + 1 }, (_, h) => ({ h, kwh: byHour.has(h) ? Math.round(byHour.get(h) * 1000) / 1000 : null }));
      dayData.loading = false; dayData.error = false;
      renderDay();
    })
    .catch(err => {
      if (seq !== daySeq) return;
      console.error(err);
      if (dayData) { dayData.loading = false; dayData.error = true; }
      renderDay();
    });
}
function renderDay() {
  if (!dayData) return;
  const titleEl = $('day-title'), totalEl = $('day-total'), noteEl = $('day-note'), canvas = $('day-chart');
  const closeBtn = $('day-close');
  const d = parseISO(dayData.iso);
  titleEl.textContent = isToday() ? `${t('Aujourd’hui, heure par heure')} · ${dayLong(d)}` : `${t('Détail du')} ${dayLong(d)}`;
  if (closeBtn) closeBtn.hidden = isToday();
  const wrap = canvas.parentElement;
  if (dayData.loading || dayData.error || !dayData.slots.some(s => s.kwh !== null)) {
    if (dayChartInstance) { dayChartInstance.destroy(); dayChartInstance = null; }
    wrap.hidden = true;
    totalEl.textContent = '';
    noteEl.textContent = dayData.loading ? t('Chargement…')
      : dayData.error ? t('Impossible de charger ce jour. Réessayez dans un instant.')
      : t('Aucune mesure reçue ce jour-là (boîtier hors ligne).');
    return;
  }
  wrap.hidden = false;
  const p = palette();
  const total = dayData.slots.reduce((s, x) => s + (x.kwh || 0), 0);
  const cout = fcfaOf(total);
  totalEl.textContent = `${kwh2(total)} kWh${cout === null ? '' : ' · ≈ ' + nb(cout) + ' F'}`;
  noteEl.textContent = t('Une barre vide = aucune mesure reçue cette heure-là ; une barre à 0 = boîtier en ligne mais appareil éteint.');
  const labels = dayData.slots.map(s => `${s.h}h`);
  const data = dayData.slots.map(s => s.kwh);
  const color = rgba(p.normal, 1);
  if (dayChartInstance) { dayChartInstance.destroy(); dayChartInstance = null; }
  dayChartInstance = new Chart(canvas, {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: color, hoverBackgroundColor: rgba(mix(p.normal, WHITE, 0.3), 1),
      borderRadius: { topLeft: 6, topRight: 6 }, borderSkipped: false, maxBarThickness: 34, categoryPercentage: 0.85, barPercentage: 0.9 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(p), { callbacks: {
        title: items => `${items[0].label} – ${parseInt(items[0].label, 10) + 1}h`,
        label: c => {
          if (c.raw === null) return t('Aucune mesure');
          const f = fcfaOf(c.raw);
          return [`${nb(c.raw, 3)} kWh`, f === null ? '' : `≈ ${nb(f)} F`].filter(Boolean);
        } } }) },
      scales: {
        y: { beginAtZero: true, grace: '12%', grid: { color: p.grid, drawTicks: false }, border: { display: false },
          ticks: { font: { family: FONT_MONO, size: 11 }, color: p.label, maxTicksLimit: 5, padding: 8, callback: v => `${nb(v, 2)} kWh` } },
        x: { grid: { display: false }, border: { display: false },
          ticks: { font: { family: FONT_MONO, size: 11 }, color: p.label, maxTicksLimit: 12, maxRotation: 0, autoSkip: true } }
      }
    }
  });
}
function highlightRow() {
  histTbody.querySelectorAll('tr[data-iso]').forEach(tr => tr.classList.toggle('row-sel', tr.dataset.iso === histState.detailIso));
}

/* ════════════════ Répartition, habitudes, conseil ════════════════ */
const REP_DV = ['var(--dv-1)', 'var(--dv-2)', 'var(--dv-3)', 'var(--dv-4)', 'var(--dv-5)', 'var(--dv-6)'];
function renderRepartition() {
  const el = $('repartition-card');
  if (!el) return;
  const rep = histState.repartition || [];
  histGrid.classList.toggle('no-rep', rep.length < 2);
  if (rep.length < 2) { el.style.display = 'none'; el.innerHTML = ''; return; }
  const totalKwh = rep.reduce((s, r) => s + (r.kwh || 0), 0);
  el.style.display = '';
  const totalFcfa = fcfaOf(totalKwh);
  const fcfaPar = totalFcfa === null ? rep.map(() => null) : repartirEntier(rep.map(r => (r.kwh || 0) * histState.prix), totalFcfa);
  const pcts = repartirEntier(rep.map(r => r.kwh || 0), 100);
  const rows = rep.map((r, i) => {
    const barPct = totalKwh > 0 ? Math.max(2, r.kwh / totalKwh * 100) : 0;
    const c = REP_DV[i % REP_DV.length];
    return `<div class="rep-row">
      <div class="rep-name" title="${esc(r.nom)}"><span class="rep-dot" style="background:${c}"></span><span class="rep-nom">${esc(r.nom)}</span></div>
      <div class="rep-track"><span class="rep-bar" style="width:${barPct}%;background:${c}"></span></div>
      <div class="rep-kwh">${kwh2(r.kwh)} kWh</div>
      <div class="rep-fcfa">${fcfaPar[i] === null ? '…' : nb(fcfaPar[i]) + ' F'}</div>
      <div class="rep-pct">${totalKwh > 0 ? pcts[i] : 0} %</div>
    </div>`;
  }).join('');
  const filtre = histState.sensor !== 'all' ? ` · ${t('tous les appareils, même avec un appareil choisi')}` : '';
  const tip = t('Affiche la part de consommation de chaque appareil mesuré sur la période.');
  el.innerHTML =
    `<div class="rep-head"><h2 class="rep-title">${t('Répartition par appareil')} <button type="button" class="itip" aria-label="${esc(tip)}" data-tip="${esc(tip)}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="10.5" x2="12" y2="16.5"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg></button></h2>` +
    `<span class="rep-sub">${t('Part de chaque appareil sur la période · énergie réelle mesurée')}${esc(filtre)}</span></div>` +
    `<div class="rep-rows">${rows}</div>` +
    `<div class="rep-total"><span>${t('Total')}</span><strong>${kwh2(totalKwh)} kWh${totalFcfa === null ? '' : ' · ' + nb(totalFcfa) + ' F'}</strong></div>`;
}

const JOURS_SEM = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
function renderHabits(cells) {
  const body = $('habits-body');
  if (!body) return;
  if (!cells) { body.innerHTML = `<p class="habits-empty">${t('Impossible de charger vos habitudes. Réessayez dans un instant.')}</p>`; return; }
  if (!cells.length) { body.innerHTML = `<p class="habits-empty">${t('Aucune mesure sur les 7 derniers jours : vos habitudes apparaîtront dès les premières mesures.')}</p>`; return; }
  const grid = new Map(cells.map(c => [`${c.dow}-${c.hour}`, c.avg_w]));
  const max = Math.max(...cells.map(c => c.avg_w), 1);
  const pic = cells.reduce((m, c) => c.avg_w > m.avg_w ? c : m, cells[0]);
  let html = '<div class="habits-grid" role="img" aria-label="' + esc(t('Puissance moyenne par jour de la semaine et par heure')) + '">';
  html += '<span class="hg-corner"></span>';
  for (let h = 0; h < 24; h++) html += `<span class="hg-h">${h % 6 === 0 ? h + 'h' : ''}</span>`;
  JOURS_SEM.forEach((nom, dow) => {
    html += `<span class="hg-d">${nom.slice(0, 3)}.</span>`;
    for (let h = 0; h < 24; h++) {
      const w = grid.get(`${dow}-${h}`);
      html += w === undefined
        ? `<span class="hc hc-empty" title="${nom} ${h}h : ${t('aucune mesure')}"></span>`
        : `<span class="hc" style="background:rgba(245,166,35,${(0.14 + 0.86 * (w / max)).toFixed(2)})" title="${nom} ${h}h : ${nb(w)} W ${t('en moyenne')}"></span>`;
    }
  });
  html += '</div>';
  html += `<p class="habits-peak">${t('Votre moment le plus chargé')} : <strong>${JOURS_SEM[pic.dow].toLowerCase()} ${t('vers')} ${pic.hour} h</strong> (${nb(pic.avg_w)} W ${t('en moyenne')}).</p>`;
  body.innerHTML = html;
}
function loadHabits() {
  fetchWithAuth('/api/analytics/heatmap/')
    .then(d => renderHabits(d && Array.isArray(d.cells) ? d.cells : []))
    .catch(err => { console.error(err); renderHabits(null); });
}
function loadConseil() {
  fetchWithAuth('/api/analytics/conseils/')
    .then(d => {
      const c = d && d.conseils && d.conseils[0];
      if (!c) return;
      $('tip-title').textContent = c.titre;
      $('tip-text').textContent = c.texte;
      $('tip-badge').textContent = c.mesure ? t('Selon vos mesures') : t('Conseil général');
      const l = $('tip-link'); if (l && c.lien) l.setAttribute('href', c.lien);
    })
    .catch(err => console.error(err));
}

/* ════════════════ Synthèse en mots ════════════════ */
function renderInsight(rows, total) {
  if (!insightStrip) return;
  const vus = rows.filter(r => r.etat !== 'manquant');
  if (!vus.length) { insightCard.hidden = true; insightStrip.hidden = true; insightStrip.textContent = ''; return; }
  const parts = [];
  const nJours = vus.length;
  const moy = total.kwhExact / nJours;
  const lbl = { auj: "Aujourd'hui", '7j': 'Sur 7 jours', '30j': 'Sur 30 jours', mois: 'Ce mois', fact: 'Sur ce bimestre', perso: 'Sur la période choisie' }[histState.period];
  const cout = total.fcfa === null ? '' : `≈ ${nb(total.fcfa)} FCFA d’énergie (estimation tarif CIE, hors abonnement fixe) pour `;
  parts.push(`${t(lbl)} : ${cout}${kwh2(total.kwh)} kWh sur ${nJours} ${nJours > 1 ? 'jours' : 'jour'} avec mesures, soit ${kwh2(moy)} kWh/jour en moyenne.`);
  const prev = histState.previous;
  if (prev && prev.evolution_pct !== null && prev.evolution_pct !== undefined) {
    const e = prev.evolution_pct;
    parts.push(e === 0 ? 'Consommation stable par rapport à la période précédente.'
      : `Soit ${Math.abs(e)} % ${e > 0 ? 'de plus' : 'de moins'} que la période précédente (${kwh2(prev.kwh)} kWh).`);
  }
  let variant = '';
  const cap = capaciteW();
  if (cap) {
    const peakRow = vus.reduce((m, r) => r.peak > m.peak ? r : m, vus[0]);
    const amp = `${histState.amperage} A ≈ ${nb(cap)} W`;
    if (peakRow.peak > cap) {
      variant = 'warn';
      parts.push(`⚠ Le ${dayMid(peakRow.rawDate)}, votre pic de ${nb(peakRow.peak)} W a dépassé votre puissance souscrite (${amp}) : le disjoncteur peut couper. Délestez ou augmentez votre abonnement.`);
    } else if (peakRow.peak >= cap * 0.9) {
      variant = 'watch';
      parts.push(`Votre pic de ${nb(peakRow.peak)} W approche votre puissance souscrite (${amp}).`);
    }
  }
  const med = medianePositive(rows);
  const anom = med > 0 ? vus.filter(r => r.kwhExact >= ANOMALY_FACTOR * med).length : 0;
  if (anom > 0) {
    if (!variant) variant = 'watch';
    parts.push(`${anom} jour${anom > 1 ? 's' : ''} de consommation inhabituelle (≥ ${ANOMALY_FACTOR}× votre habitude).`);
  }
  insightStrip.className = 'insight-strip' + (variant ? ' is-' + variant : '');
  insightStrip.textContent = parts.join(' ');
  insightStrip.hidden = false;
  insightCard.hidden = false;
  const rp = $('rail-period');
  if (rp && histState.winFrom) { rp.hidden = false; rp.textContent = windowLabel(); }
}
function windowLabel() {
  if (!histState.winFrom || !histState.winTo) return '';
  const a = parseISO(histState.winFrom), b = parseISO(histState.winTo);
  const aujourdhui = new Date(); aujourdhui.setHours(0, 0, 0, 0);
  const fin = b > aujourdhui ? aujourdhui : b;
  if (fmtDate(a) === fmtDate(fin)) return dayLong(a);
  return `${dayShort(a)} → ${dayShort(fin)} ${fin.getFullYear()}`;
}

/* ════════════════ Rendu principal ════════════════ */
const LBLS = ['Consommation totale', 'Coût de l’énergie', 'Pic maximum', 'Jour / Nuit'];
const TIPS = [
  'La quantité totale d’énergie que vos appareils ont consommée sur la période, en kWh. C’est cette énergie que la CIE facture.',
  'Le coût de l’énergie consommée = kWh × tarif CIE (taxes incluses). Il n’inclut PAS l’abonnement fixe (par bimestre en postpayé) ; votre facture complète est dans « Facturation ».',
  'La plus forte puissance (en watts) atteinte d’un coup sur la période. Si elle dépasse la limite de votre disjoncteur (indiquée entre parenthèses, en ampères), le courant peut se couper.',
  'La part de votre énergie consommée en journée (6h–22h) et la nuit (22h–6h). Utile pour savoir quand vous consommez le plus.',
];
const I_INFO = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="10.5" x2="12" y2="16.5"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg>';

function renderHistorique(silent) {
  const sort = histState.sort;
  const { rows, total } = buildRows();
  const vus = rows.filter(r => r.etat !== 'manquant');
  const hasData = vus.length > 0;
  const loading = !histState.loaded;
  const error = histState.loadError;
  const aCapteur = (histState.repartition || []).length > 0 || !!histState.derniereMesure;

  periodBtns.forEach(b => {
    const on = b.dataset.period === histState.period;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });

  let stats;
  if (loading) {
    stats = LBLS.map(l => ({ l, v: '…', u: '', s: t('Chargement…') }));
  } else if (error) {
    stats = LBLS.map((l, i) => ({ l, v: i === 0 ? t('Indisponible') : '-', u: '', cls: i === 0 ? '' : 'stat-empty',
      s: i === 0 ? t('Erreur de chargement, réessayez dans un instant') : '' }));
  } else if (!hasData) {
    stats = LBLS.map((l, i) => ({ l, v: i === 0 ? t('Aucune donnée') : '-', u: '', cls: i === 0 ? '' : 'stat-empty',
      s: i === 0 ? (aCapteur ? t('Aucune mesure reçue pour cette période') : t('Aucun capteur installé')) : '' }));
  } else {
    const peakRow = vus.reduce((m, r) => r.peak > m.peak ? r : m, vus[0]);
    const capW = capaciteW();
    const nightPct = total.kwhExact > 0 ? Math.round(total.nightKwh / total.kwhExact * 100) : 0;
    const dayKwh = Math.max(0, total.kwhExact - total.nightKwh);
    const nTrace = vus.length;
    const moy = total.kwhExact / nTrace;
    const prev = histState.previous;
    const pEvo = prev ? prev.evolution_pct : null;
    const evo = (pEvo === null || pEvo === undefined) ? '' : pEvo === 0 ? ' · stable vs préc.' : ` · ${pEvo > 0 ? '▲' : '▼'} ${Math.abs(pEvo)} % vs préc.`;
    stats = [
      { l: LBLS[0], v: kwh2(total.kwh), u: 'kWh', s: `${nTrace} ${nTrace > 1 ? 'jours' : 'jour'} avec mesures · ≈ ${kwh2(moy)} kWh/jour${evo}` },
      { l: LBLS[1], v: total.fcfa === null ? '…' : nb(total.fcfa), u: 'FCFA',
        s: `${kwh2(total.kwh)} kWh × ${histState.prix ? nb(histState.prix, 2) : '…'} F · hors abonnement fixe` },
      { l: LBLS[2], v: nb(total.peak), u: 'W', cls: (capW && total.peak > capW) ? 'card-alert' : '',
        s: capW ? `le ${dayMid(peakRow.rawDate)} · limite ≈ ${nb(capW)} W (${histState.amperage} A)` : `le ${dayMid(peakRow.rawDate)} · puiss. en marche ${nb(total.avgW)} W` },
      { l: LBLS[3], v: `${100 - nightPct} / ${nightPct}`, u: '%', s: `${kwh2(dayKwh)} kWh jour (6h–22h) · ${kwh2(total.nightKwh)} kWh nuit (22h–6h)` },
    ];
  }
  statsGrid.innerHTML = stats.map((s, i) => {
    const tip = t(TIPS[i] || '');
    const itip = tip ? `<button type="button" class="itip${i === stats.length - 1 ? ' itip-right' : ''}" aria-label="${esc(tip)}" data-tip="${esc(tip)}">${I_INFO}</button>` : '';
    return `<div class="stat-card${s.cls ? ' ' + s.cls : ''}">
    <div class="stat-card-lbl">${esc(t(s.l))}${itip}</div>
    <div class="stat-card-val">${esc(s.v)}${s.u ? `<span class="stat-unit">${esc(s.u)}</span>` : ''}</div>
    <div class="stat-card-sub">${esc(s.s)}</div>
  </div>`;
  }).join('');

  renderRepartition();
  if (sensorSelect) sensorSelect.style.display = histState.sensorsList.length >= 2 ? '' : 'none';

  const lib = windowLabel();
  dateRangeEl.textContent = loading ? t('Chargement…') : error ? t('Erreur de chargement, données indisponibles')
    : (lib ? `${lib}${rows.length > 1 ? ` · ${rows.length} jours` : ''}` : t('Aucune donnée pour cette période'));

  // « Aujourd'hui » : le détail heure par heure remplace le graphe journalier (une seule barre n'aurait aucun sens)
  chartCard.hidden = isToday();
  if (isToday() && histState.loaded && !error && (!dayData || dayData.iso !== fmtDate(new Date()))) {
    openDay(fmtDate(new Date()), { noScroll: true });
  }
  if (chartTitleEl) chartTitleEl.textContent = histState.unit === 'fcfa' ? t('Coût journalier estimé (FCFA)') : t('Consommation journalière (kWh)');
  if (!isToday()) {
    const wrap = chartCard.querySelector('.chart-wrap');
    if (loading || error || !hasData) {
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      wrap.classList.add('is-empty');
      wrap.setAttribute('data-msg', loading ? t('Chargement…') : error ? t('Erreur de chargement, données indisponibles')
        : aCapteur ? t('Aucune mesure reçue sur cette période.') : t('Aucun capteur installé : le graphique apparaîtra dès la première mesure.'));
    } else {
      wrap.classList.remove('is-empty');
      renderChart(rows, silent);
    }
  }
  renderInsight((loading || error) ? [] : rows, total);

  // Jours mesurés / éteints / sans mesure : dit honnêtement ce que la période contient vraiment
  if (dataDepthNote) {
    if (!loading && !error && hasData && (total.nEteint || total.nManquant)) {
      const bits = [`${total.nMesure} ${total.nMesure > 1 ? 'jours mesurés' : 'jour mesuré'}`];
      if (total.nEteint) bits.push(`${total.nEteint} ${total.nEteint > 1 ? 'jours éteints (0 kWh)' : 'jour éteint (0 kWh)'}`);
      if (total.nManquant) bits.push(`${total.nManquant} ${total.nManquant > 1 ? 'jours sans mesure (boîtier hors ligne)' : 'jour sans mesure (boîtier hors ligne)'}`);
      dataDepthNote.hidden = false;
      dataDepthNote.textContent = `${bits.join(' · ')} sur ${rows.length} jours.`;
    } else { dataDepthNote.hidden = true; dataDepthNote.textContent = ''; }
  }

  // « Aucune mesure ici, mais le boîtier en a envoyé avant » : proposer d'y aller
  const jb = $('jump-banner');
  if (jb) {
    const montrer = !loading && !error && !hasData && histState.derniereMesure;
    jb.hidden = !montrer;
    if (montrer) {
      $('jump-text').textContent = `${t('Aucune mesure sur cette période. Le boîtier a envoyé sa dernière mesure le')} ${dayLong(parseISO(histState.derniereMesure))}.`;
      $('jump-btn').textContent = t('Voir les 30 jours jusqu’à cette date');
    }
  }

  // Tableau : tous les jours. Hors tri par date, les jours sans mesure (valeur inconnue) ne se trient pas.
  const SORT_LABELS = { date: 'Jour', kwh: 'kWh', fcfa: 'Coût', avgW: 'Puiss. en marche', nightKwh: 'Nuit', alerts: 'Alertes', peak: 'Pic' };
  const triables = sort.f === 'date' ? rows : vus;
  const sortKey = sort.f === 'date' ? 'iso' : sort.f;
  const sorted = [...triables].sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    return (x < y ? -1 : x > y ? 1 : 0) * sort.d;
  });
  tableMeta.textContent = `${rows.length} ${rows.length > 1 ? 'jours' : 'jour'} · Tri ${t(SORT_LABELS[sort.f] || sort.f)} (${sort.d === 1 ? t('croissant') : t('décroissant')})`
    + (sort.f !== 'date' && total.nManquant ? ` · ${total.nManquant} ${t('jour(s) sans mesure masqué(s)')}` : '');
  sortHeaders.forEach(th => {
    const f = th.dataset.field, on = sort.f === f;
    const ico = th.querySelector('.sort-ico');
    if (ico) ico.textContent = on ? (sort.d === 1 ? '↑' : '↓') : '↕';
    th.setAttribute('aria-sort', on ? (sort.d === 1 ? 'ascending' : 'descending') : 'none');
  });
  const cell = (v, cls) => `<td class="cell-num${cls ? ' ' + cls : ''}">${v}</td>`;
  const med = medianePositive(rows);
  const emptyMsg = loading ? t('Chargement…') : error ? t('Erreur de chargement, données indisponibles') : t('Aucune donnée pour cette période');
  if (loading || error || !hasData) {
    histTbody.innerHTML = `<tr><td colspan="7" class="tbl-msg">${emptyMsg}</td></tr>`;
  } else {
    histTbody.innerHTML = sorted.map(r => {
      if (r.etat === 'manquant') {
        return `<tr class="row-miss"><td>${esc(r.date)} <span class="badge-state bs-miss">${t('Aucune mesure')}</span></td><td class="cell-num cell-miss" colspan="6">${t('boîtier hors ligne : valeur inconnue')}</td></tr>`;
      }
      const anom = med > 0 && r.kwhExact >= ANOMALY_FACTOR * med;
      const kwhStr = (r.kwhExact > 0 && r.kwh === 0 ? '≈ ' : '') + kwh2(r.kwh);
      const badge = r.etat === 'eteint' ? ` <span class="badge-state bs-off">${t('Éteint')}</span>` : '';
      const dot = anom ? ` <span class="anom-dot" title="${t('Consommation inhabituelle (≥ 2× votre habitude)')}" aria-label="${t('jour inhabituel')}">●</span>` : '';
      return `<tr class="row-day${anom ? ' row-anom' : ''}" data-iso="${r.iso}" tabindex="0" title="${t('Cliquez pour voir ce jour heure par heure')}">
      <td>${esc(r.date)}${badge}${dot}</td>
      ${cell(kwhStr)}
      ${cell(r.fcfa === null ? '…' : nb(r.fcfa) + ' FCFA')}
      ${cell(r.etat === 'eteint' ? '—' : nb(r.avgW) + ' W')}
      ${cell(kwh2(r.nightKwh) + ' kWh')}
      <td><span class="badge-alert ${r.alerts === 0 ? 'ba-0' : 'ba-n'}">${r.alerts}</span></td>
      ${cell(r.etat === 'eteint' ? '—' : nb(r.peak) + ' W', peakClass(r.peak))}
    </tr>`;
    }).join('') + `<tr class="tbl-total">
      <td>${t('Total')} ${vus.length} ${vus.length > 1 ? 'jours' : 'jour'}</td>
      ${cell(kwh2(total.kwh) + ' kWh')}
      ${cell(total.fcfa === null ? '…' : nb(total.fcfa) + ' FCFA')}
      ${cell(nb(total.avgW) + ' W')}
      ${cell(kwh2(total.nightKwh) + ' kWh')}
      ${cell(total.alerts)}
      ${cell(nb(total.peak) + ' W', peakClass(total.peak))}
    </tr>`;
    highlightRow();
  }

  if (liveStatus && !silent) {
    liveStatus.textContent = loading ? t('Chargement de l’historique…') : error ? t('Erreur de chargement des données.')
      : !hasData ? t('Aucune donnée pour cette période.')
      : `${vus.length} jour${vus.length > 1 ? 's' : ''}, ${nb(total.kwh, 2)} kWh${total.fcfa === null ? '' : ', ' + nb(total.fcfa) + ' FCFA'}.`;
  }
  updateExportBtn();
  updateStateBadge();
}

function updateExportBtn() {
  exportBtn.disabled = histState.exporting;
  exportLabel.textContent = histState.exporting ? t('Export en cours…') : t('CSV mesures');
  if (exportDayBtn) {
    exportDayBtn.disabled = histState.exportingDay;
    exportDayLabel.textContent = histState.exportingDay ? t('Export…') : t('CSV par jour');
  }
  if (pdfBtn) {
    pdfBtn.disabled = histState.exportingPdf;
    if (pdfLabel) pdfLabel.textContent = histState.exportingPdf ? t('Export…') : t('PDF');
  }
}

/* ════════════════ Chargement ════════════════ */
function windowQuery() {
  const now = new Date();
  switch (histState.period) {
    case 'auj': return 'period=day';
    case '30j': return 'period=month';
    // « Ce mois » et « Ce bimestre » : date_to omis, le serveur borne à SON « maintenant » (fuseau Abidjan)
    case 'mois': return `date_from=${fmtDate(new Date(now.getFullYear(), now.getMonth(), 1))}`;
    case 'fact': return histState.factDebut ? `date_from=${histState.factDebut}` : 'period=month';
    case 'perso': if (histState.customFrom && histState.customTo) return `date_from=${histState.customFrom}&date_to=${histState.customTo}`;
    // eslint-disable-next-line no-fallthrough
    default: return 'period=week';
  }
}

let histReqSeq = 0;
let histInFlight = false;
function loadMesures(opts) {
  const silent = !!(opts && opts.silent);
  if (silent && histInFlight) return;
  const url = `/api/analytics/historique/?${windowQuery()}${sensorQuery()}`;
  // Anti-course : seule la DERNIÈRE réponse est prise en compte
  const seq = ++histReqSeq;
  histInFlight = true;
  if (!silent) { histState.loaded = false; histState.loadError = false; renderHistorique(); }
  fetchWithAuth(url)
    .then(data => {
      if (seq !== histReqSeq) return;
      const wasErrorOrLoading = histState.loadError || !histState.loaded;
      if (data && data.prix_kwh) histState.prix = Number(data.prix_kwh);
      if (data && (data.amperage || data.amperage === 0)) histState.amperage = Number(data.amperage);
      histState.jours = (data && Array.isArray(data.jours)) ? data.jours : [];
      histState.manquants = (data && Array.isArray(data.manquants)) ? data.manquants : [];
      histState.previous = (data && data.previous) || null;
      histState.repartition = (data && Array.isArray(data.repartition)) ? data.repartition : [];
      histState.winFrom = (data && data.date_from) || '';
      histState.winTo = (data && data.date_to) || '';
      histState.enLigne = !!(data && data.en_ligne);
      histState.dernierContact = (data && data.dernier_contact) || null;
      histState.derniereMesure = (data && data.derniere_mesure) || null;
      const sig = JSON.stringify([histState.jours, histState.manquants, histState.previous, histState.repartition,
        histState.prix, histState.amperage, histState.enLigne, histState.winFrom, histState.winTo, histState.unit]);
      const changed = sig !== histState._sig;
      histState._sig = sig;
      histState.loaded = true;
      histState.loadError = false;
      if (!silent || changed || wasErrorOrLoading) renderHistorique(silent);
      else updateStateBadge();
      if (silent && histState.detailIso) loadDay(histState.detailIso);
      if (histState.jourDemande) {            // lien venu d'une alerte : on ouvre le jour demandé, une seule fois
        const j = histState.jourDemande;
        histState.jourDemande = null;
        if (histState.jours.some(x => x.date === j)) openDay(j);
      }
    })
    .catch(err => {
      if (seq !== histReqSeq) return;
      console.error(err);
      if (liveBadge) liveBadge.hidden = true;
      if (!silent) { histState.loadError = true; histState.loaded = true; renderHistorique(); }
    })
    .then(() => { if (seq === histReqSeq) histInFlight = false; });
}

function loadFacture() {
  return fetchWithAuth('/api/analytics/facture/')
    .then(data => {
      // Prix STABLE d'un kWh tout compris (et non prix_moyen_kwh, qui explose en début de période)
      const p = data && (data.prix_kwh_tout_compris || data.prix_moyen_kwh);
      if (p) histState.prix = Number(p);
      const per = data && data.periode;
      if (per && per.debut) { histState.factDebut = per.debut; histState.factType = per.type; }
      const btn = $('pt-fact');
      if (btn) {
        // Le mois civil EST la période de facturation d'un prépayé : le bouton « Ce bimestre » n'existe que pour un postpayé
        btn.hidden = histState.factType !== 'bimestre';
        if (per && per.libelle) btn.title = `${per.libelle} : du début de la période de facturation à aujourd'hui`;
      }
      if (histState.loaded) renderHistorique();
    })
    .catch(err => console.error(err));
}

/* Lien depuis une alerte : /historique/?jour=AAAA-MM-JJ&capteur=<id> ouvre la semaine autour de ce jour, le capteur
   choisi, et le détail heure par heure de ce jour (19/10/2026). */
function lireLien() {
  const q = new URLSearchParams(window.location.search);
  const jour = q.get('jour');
  if (jour && /^\d{4}-\d{2}-\d{2}$/.test(jour) && !isNaN(parseISO(jour))) {
    const j = parseISO(jour);
    const a = new Date(j); a.setDate(a.getDate() - 3);
    const b = new Date(j); b.setDate(b.getDate() + 3);
    const auj = new Date(); auj.setHours(0, 0, 0, 0);
    histState.period = 'perso';
    histState.customFrom = fmtDate(a);
    histState.customTo = fmtDate(b > auj ? auj : b);
    histState.jourDemande = jour;
  }
  const cap = q.get('capteur');
  if (cap && /^[0-9a-fA-F-]{32,36}$/.test(cap)) histState.sensor = cap;
}

function initHistorique() {
  lireLien();
  if (histState.period === 'perso' && histState.customFrom) {
    if (dateFromInput) { dateFromInput.value = histState.customFrom; dateFromInput.max = fmtDate(new Date()); }
    if (dateToInput) { dateToInput.value = histState.customTo; dateToInput.max = fmtDate(new Date()); }
  }
  if (dateFromInput && dateToInput && histState.period !== 'perso') {
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
  renderHistorique();
  fetchWithAuth('/api/sensors/')
    .then(data => { histState.sensorsList = window.AOCEDA.asList(data); renderSensorSelect(); renderHistorique(); })
    .catch(err => console.error(err));
  loadMesures();
  loadFacture();
  loadHabits();
  loadConseil();
  scheduleRefresh();
}

function renderSensorSelect() {
  if (histState.sensorsList.length === 0) {
    sensorSelect.style.display = 'none';
    sensorSelect.innerHTML = `<option value="all">${t('Tous les appareils')}</option>`;
    return;
  }
  sensorSelect.innerHTML = `<option value="all">${t('Tous les appareils')}</option>` +
    histState.sensorsList.map(s => `<option value="${esc(String(s.id))}">${esc(s.nom)}</option>`).join('');
  sensorSelect.value = histState.sensor;
  sensorSelect.style.display = histState.sensorsList.length >= 2 ? '' : 'none';
}

/* ════════════════ Écouteurs ════════════════ */
periodBtns.forEach(b => b.addEventListener('click', () => {
  const k = b.dataset.period;
  if (histState.period === k) return;
  histState.period = k;
  closeDay();
  syncCustomRangeUI();
  if (k === 'perso' && !(histState.customFrom && histState.customTo)) { renderHistorique(); return; }
  loadMesures();
}));

if (crApplyBtn) crApplyBtn.addEventListener('click', () => {
  const from = dateFromInput && dateFromInput.value;
  const to = dateToInput && dateToInput.value;
  if (!from || !to) { dateRangeEl.textContent = t('Choisissez une date de début et de fin.'); return; }
  if (from > to) { dateRangeEl.textContent = t('La date de début doit précéder la date de fin.'); return; }
  if ((parseISO(to) - parseISO(from)) / 86400000 + 1 > 366) { dateRangeEl.textContent = t('La plage est limitée à 366 jours.'); return; }
  histState.period = 'perso';
  histState.customFrom = from;
  histState.customTo = to;
  closeDay();
  syncCustomRangeUI();
  loadMesures();
});

const jumpBtn = $('jump-btn');
if (jumpBtn) jumpBtn.addEventListener('click', () => {
  if (!histState.derniereMesure) return;
  const fin = parseISO(histState.derniereMesure);
  const debut = new Date(fin); debut.setDate(debut.getDate() - 29);
  histState.period = 'perso';
  histState.customFrom = fmtDate(debut);
  histState.customTo = fmtDate(fin);
  if (dateFromInput) dateFromInput.value = histState.customFrom;
  if (dateToInput) dateToInput.value = histState.customTo;
  closeDay();
  syncCustomRangeUI();
  loadMesures();
});

sensorSelect.addEventListener('change', e => {
  histState.sensor = e.target.value;
  loadMesures();
  if (histState.detailIso) loadDay(histState.detailIso);
});

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
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); applySort(th.dataset.field); }
  });
});

// Une ligne du tableau ouvre le détail du jour (souris, toucher ou clavier)
histTbody.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-iso]');
  if (tr) openDay(tr.dataset.iso);
});
histTbody.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const tr = e.target.closest('tr[data-iso]');
  if (tr) { e.preventDefault(); openDay(tr.dataset.iso); }
});
const dayClose = $('day-close');
if (dayClose) dayClose.addEventListener('click', closeDay);

/* Même plage que le tableau affiché, pour les trois exports */
function exportQuery() { return windowQuery() + sensorQuery(); }
function lancerExport(flag, url, nom) {
  if (histState[flag]) return;
  histState[flag] = true;
  updateExportBtn();
  downloadFile(url, nom)
    .catch(err => console.error(err))
    .then(() => { histState[flag] = false; updateExportBtn(); });
}
exportBtn.addEventListener('click', () => lancerExport('exporting', `/api/analytics/export/?${exportQuery()}`, 'aoceda_mesures.csv'));
if (exportDayBtn) exportDayBtn.addEventListener('click', () => lancerExport('exportingDay', `/api/analytics/export/journalier/?${exportQuery()}`, 'aoceda_journalier.csv'));
if (pdfBtn) pdfBtn.addEventListener('click', () => lancerExport('exportingPdf', `/api/analytics/export/pdf/?${exportQuery()}`, 'aoceda_historique.pdf'));

/* ════════════════ Démarrage ════════════════ */
applyTheme();
initHistorique();
