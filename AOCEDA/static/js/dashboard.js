'use strict';
const t = window.AOCEDA_T || (x => x);
/* ════════════════════════════════════════════════════════════
   AOCEDA, Tableau de bord client
   JavaScript vanilla (ES2020) + Chart.js, sans React/Babel
   ════════════════════════════════════════════════════════════ */

/* ── Garde d'authentification ── */
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* ── Helper fetch authentifié, délègue au shell (refresh JWT sur 401) ──
   On REJETTE sur tout statut HTTP non-OK. Sinon une erreur serveur à corps JSON
   (429 throttle, 500, 403) serait lue comme un succès et repeindrait les KPI en
   « 0 kWh / 0 FCFA » (faux zéros), en contradiction avec la carte facture. En
   rejetant, l'appel part dans le .catch de chaque loader, qui préserve l'état réel. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  });
}

/* ── Helper d'échappement HTML (pour innerHTML) ── */
function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

/* ── Temps relatif lisible (« il y a 3 min », « il y a 2 h ») ── */
/* ── Locale dynamique selon la langue choisie ── */
const _LOCALE = (localStorage.getItem('aoceda-lang') === 'en') ? 'en-GB' : 'fr-FR';

function timeAgo(d) {
  const s = Math.max(1, Math.round((new Date() - d) / 1000));
  if (_LOCALE === 'en-GB') {
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} d ago`;
  }
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
}

/* ── États vides (classe .empty-state fournie par client-shell.css) ── */
const EMPTY_SENSORS_HTML = `<div class="empty-state">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
  <div class="es-title">${window.AOCEDA_T ? window.AOCEDA_T('Aucun capteur appairé') : 'Aucun capteur appairé'}</div>
  <div class="es-sub">${window.AOCEDA_T ? window.AOCEDA_T('Vos capteurs apparaîtront ici dès leur première mesure.') : 'Vos capteurs apparaîtront ici dès leur première mesure.'}</div>
</div>`;
const EMPTY_ALERTS_HTML = `<div class="empty-state">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
  <div class="es-title">${window.AOCEDA_T ? window.AOCEDA_T('Aucune alerte récente') : 'Aucune alerte récente'}</div>
  <div class="es-sub">${window.AOCEDA_T ? window.AOCEDA_T('Tout est calme, votre consommation reste sous les seuils.') : 'Tout est calme, votre consommation reste sous les seuils.'}</div>
</div>`;
// Panneau « composition de la facture » quand aucune consommation n'a encore été
// mesurée (0 capteur, ou capteur jamais mesuré) : sans cet état, le panneau restait
// bloqué indéfiniment sur son squelette « Chargement du détail… » initial.
const EMPTY_FORECAST_HTML = `<div class="empty-state">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>
  <div class="es-title">${window.AOCEDA_T ? window.AOCEDA_T('Aucun capteur installé') : 'Aucun capteur installé'}</div>
  <div class="es-sub">${window.AOCEDA_T ? window.AOCEDA_T('Rien n’est mesuré, donc rien n’est calculé ici. Le détail de votre facture s’affichera dès la première mesure.') : 'Rien n’est mesuré, donc rien n’est calculé ici. Le détail de votre facture s’affichera dès la première mesure.'}</div>
</div>`;

/* ── Icônes thème (swap moon/sun) ── */
const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';

/* ── État global ── */
const state = {
  theme: document.documentElement.getAttribute('data-theme') || 'light',
  filter: '7j',
  sensor: 'all',
  sensorsList: [],
  telemetry: [],
  alerts: [],
  repartition: null,      // répartition de la conso par capteur (/api/analytics/repartition/)
  repMode: 'preset',      // 'preset' (nb de jours) | 'custom' (plage libre)
  repDays: 7,             // fenêtre en jours quand repMode = 'preset' (1 = aujourd'hui)
  repFrom: null,          // date début 'YYYY-MM-DD' quand repMode = 'custom'
  repTo: null,            // date fin  'YYYY-MM-DD' quand repMode = 'custom'
  kpis: null,
  facture: null,
  factureVide: null,      // réponse « vide » de /api/analytics/facture/ (compte sans capteur : période seule)
  // Prix d'un kWh tout compris (réponse de la facture) ; null tant qu'il n'est pas connu : aucun coût n'est
  // affiché avec un prix supposé (avant le 19/10/2026 : 87 F codés en dur)
  prixKwh: null,
  kpisLive: false,        // false tant que les indicateurs affichés viennent du cache (dernière visite)
  /* Comparaison = un CAPTEUR (obligatoire) + une PÉRIODE (même période, période d'avant ou plage libre) */
  compareSensor: null,    // null | 'all' | '{id}', capteur comparé (null = pas de comparaison)
  comparePeriod: 'same',  // 'same' (suit les pills) | 'prev' (période d'avant) | 'custom' (plage libre)
  prevTelemetry: [],
  telemetryLoaded: false,
  telemetryError: false,  // dernier chargement de la série en échec (réseau, serveur)
  compareBarOpen: false,  // état de la barre de comparaison (tracé en state)
  compareLoaded: false,   // true quand le fetch de comparaison a abouti (succès ou échec)
  compareDates: null,     // {from, to} de la plage libre chargée
};
let chart = null;

/* ════════════════════════ THÈME ════════════════════════ */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = state.theme === 'light' ? ICON_MOON : ICON_SUN;
}

function toggleTheme() {
  // Bascule + persiste via le helper partagé (client-shell.js) : fige le choix
  // explicite ('light'/'dark'), sort du mode « auto » et reste cohérent
  // entre toutes les pages (cf. écran Paramètres).
  state.theme = window.AOCEDA.toggleTheme();
  applyTheme();
  renderChart();        // couleurs du graphique dépendantes du thème
  renderRepartition();  // idem pour le donut de répartition (palette data-viz + surface)
}

/* ════════════════════════ AGRÉGATION ════════════════════════ */
/* 19/10/2026 : l'axe porte TOUS les créneaux de la fenêtre (chaque heure depuis minuit, ou chaque jour), et un
   créneau sans aucune trace du boîtier reste vide (trou dans la courbe), au lieu d'une courbe qui reliait deux
   mesures éloignées comme si l'on avait mesuré entre les deux. Un 0 n'apparaît que si le boîtier était là sans
   consommer (appareil éteint : lignes à 0 renvoyées par le serveur). Toutes les vues sont en kWh : par heure pour
   « Aujourd'hui » (le total = l'indicateur « Consommation du jour »), par jour sinon. */
function pad2(n) { return String(n).padStart(2, '0'); }
function repISO(dt) {                           // Date → 'YYYY-MM-DD' (date locale)
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}
function slotKey(d, hourly) { return hourly ? `${repISO(d)}T${pad2(d.getHours())}` : repISO(d); }

/* Créneaux d'une fenêtre : [{key, label, date}] */
function slotsForFilter(filter) {
  const now = new Date();
  const out = [];
  if (filter === 'auj') {
    for (let h = 0; h <= now.getHours(); h++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h);
      out.push({ key: slotKey(d, true), label: `${h}h`, date: d });
    }
    return out;
  }
  const n = filter === '30j' ? 30 : 7;
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    out.push({ key: slotKey(d, false), label: dayLabel(d, filter), date: d });
  }
  return out;
}
function slotsForRange(from, to, hourly) {
  const out = [];
  const d0 = new Date(from + 'T00:00:00'), d1 = new Date(to + 'T00:00:00');
  if (isNaN(d0) || isNaN(d1)) return out;
  if (hourly) {
    for (let h = 0; h < 24; h++) {
      const d = new Date(d0.getFullYear(), d0.getMonth(), d0.getDate(), h);
      out.push({ key: slotKey(d, true), label: `${h}h`, date: d });
    }
    return out;
  }
  for (let d = new Date(d0); d <= d1 && out.length < 400; d.setDate(d.getDate() + 1)) {
    const x = new Date(d);
    out.push({ key: slotKey(x, false), label: dayLabel(x, '30j'), date: x });
  }
  return out;
}
function dayLabel(d, filter) {
  return filter === '7j'
    ? d.toLocaleDateString(_LOCALE, { weekday: 'short', day: 'numeric' })
    : d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' });
}

/* kWh par créneau (somme de tous les capteurs reçus) ; null = aucune trace du boîtier dans ce créneau */
function seriesOnSlots(rows, slots, hourly) {
  const sums = new Map();
  (rows || []).forEach(m => {
    const k = slotKey(new Date(m.timestamp), hourly);
    const v = parseFloat(m.energie || 0);
    sums.set(k, (sums.get(k) || 0) + (isNaN(v) ? 0 : v));
  });
  return slots.map(s => sums.has(s.key) ? Math.round(sums.get(s.key) * 1000) / 1000 : null);
}

/* Nombres à la française : « 1,25 kWh », « 12 345 F » */
function fmtNum(v, dec) {
  return Number(v).toLocaleString(_LOCALE, { maximumFractionDigits: dec == null ? 2 : dec });
}
function fmtKwhAuto(v) {
  const a = Math.abs(Number(v));
  return fmtNum(v, a > 0 && a < 0.1 ? 3 : 2);
}
function fmtF(v) { return Math.round(Number(v)).toLocaleString(_LOCALE) + ' F'; }

/* ════════════════════════ GRAPHIQUE ════════════════════════ */
/* Lit un token CSS du :root (couleurs data-viz pilotées par le thème).
   Repli codé en dur si la variable n'est pas résolue (sécurité). */
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

const PERIOD_API = { 'auj': 'day', '7j': 'week', '30j': 'month' };

function periodWords(filter) {
  return { 'auj': t("aujourd'hui"), '7j': t('7 derniers jours'), '30j': t('30 derniers jours') }[filter] || '';
}
function sensorName(id) {
  if (id === 'all' || id == null) return t('Tous les capteurs');
  const s = state.sensorsList.find(x => String(x.id) === String(id));
  return s ? s.nom : t('Capteur');
}

/* Plage de la comparaison « période d'avant » / « plage libre » : {from, to, hourly} ou null */
function compareRange() {
  const today = new Date();
  const back = n => repISO(new Date(today.getFullYear(), today.getMonth(), today.getDate() - n));
  if (state.comparePeriod === 'prev') {
    if (state.filter === 'auj') return { from: back(1), to: back(1), hourly: true };
    const n = state.filter === '30j' ? 30 : 7;
    return { from: back(2 * n - 1), to: back(n), hourly: false };
  }
  if (state.comparePeriod === 'custom' && state.compareDates) {
    const { from, to } = state.compareDates;
    return state.filter === 'auj' ? { from, to: from, hourly: true } : { from, to, hourly: false };
  }
  return null;
}

/* Série de comparaison posée sur l'axe affiché : même créneau (même période) ou même rang (1er jour sur 1er jour) */
function compareOnAxis(mainSlots, hourly) {
  if (state.comparePeriod === 'same') {
    return { values: seriesOnSlots(state.prevTelemetry, mainSlots, hourly), labels: null, extra: 0, short: 0 };
  }
  const r = compareRange();
  if (!r) return null;
  const cs = slotsForRange(r.from, r.to, r.hourly);
  const vals = seriesOnSlots(state.prevTelemetry, cs, r.hourly);
  return {
    values: mainSlots.map((_, i) => i < vals.length ? vals[i] : null),
    labels: mainSlots.map((_, i) => cs[i]
      ? (r.hourly ? `${cs[i].date.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' })} ${cs[i].label}`
                  : cs[i].date.toLocaleDateString(_LOCALE, { weekday: 'short', day: 'numeric', month: 'short' }))
      : null),
    extra: Math.max(0, cs.length - mainSlots.length),
    short: Math.max(0, mainSlots.length - cs.length),
    horsVue: vals.slice(mainSlots.length).some(v => v !== null)   // des mesures existent, mais après la partie superposée
  };
}

/* Un point isolé entre deux trous serait invisible sans rayon : on le dessine toujours */
function pointRadiusFor(base) {
  return ctx => {
    const d = ctx.dataset.data, i = ctx.dataIndex;
    if (d[i] == null) return 0;
    return (d[i - 1] == null && d[i + 1] == null) ? 4 : base;
  };
}

function setChartPlaceholder(text, loading) {
  const placeholder = document.getElementById('chart-placeholder');
  if (!placeholder) return;
  placeholder.style.display = '';
  const span = placeholder.querySelector('span');
  if (span) span.textContent = text;
  const spin = placeholder.querySelector('.chart-spin');
  if (spin) spin.style.display = loading ? '' : 'none';
}

function setChartMeta() {
  const el = document.getElementById('chart-meta');
  if (!el) return;
  el.textContent = state.filter === 'auj' ? t('kWh par heure, depuis minuit')
    : state.filter === '30j' ? t('kWh par jour, 30 derniers jours') : t('kWh par jour, 7 derniers jours');
}

function renderChart() {
  const canvas = document.getElementById('consumption-chart');
  const placeholder = document.getElementById('chart-placeholder');
  if (!canvas) return;
  setChartMeta();

  if (!state.telemetryLoaded) {
    canvas.style.display = 'none';
    setChartPlaceholder(t('Chargement des données…'), true);
    return;
  }

  const hourly = state.filter === 'auj';
  const slots = slotsForFilter(state.filter);
  const labels = slots.map(s => s.label);
  const actual = seriesOnSlots(state.telemetry, slots, hourly);
  const hasMain = actual.some(v => v !== null);

  let cmp = null;
  if (state.compareSensor !== null && state.compareLoaded) {
    cmp = compareOnAxis(slots, hourly);
    if (cmp && !cmp.values.some(v => v !== null)) {
      setCbarHint(cmp.horsVue
        ? `${t('Les')} ${slots.length} ${hourly ? t('premières heures') : t('premiers jours')} ${t('de la plage, superposés à la vue, n’ont aucune mesure. Choisissez une plage de')} ${slots.length} ${hourly ? t('heures') : t('jours')} ${t('qui contient des mesures.')}`
        : t('Aucune mesure pour ce capteur sur la période de comparaison.'), true);
      cmp = null;
    } else if (cmp && state.comparePeriod === 'custom') {
      const unite = hourly ? t('heures') : t('jours');
      if (cmp.extra) setCbarHint(`${t('Seuls les')} ${slots.length} ${t('premiers')} ${unite} ${t('de la plage sont superposés (même durée que la vue).')}`);
      else if (cmp.short) setCbarHint(`${t('La plage est plus courte que la vue : sa courbe s’arrête après')} ${slots.length - cmp.short} ${unite}.`);
      else setCbarHint('');
    }
  }
  const compareDrawn = !!cmp;

  if (!hasMain && !compareDrawn) {
    // Aucune trace du boîtier sur la période : état vide HONNÊTE (jamais de courbe fabriquée)
    if (chart) { chart.destroy(); chart = null; }
    canvas.style.display = 'none';
    setChartPlaceholder(state.telemetryError
      ? t('Impossible de charger les mesures. Nouvel essai dans quelques secondes…')
      : state.kpis && state.kpis.mode === 'vide'
        ? t('Aucun capteur installé : la courbe s’affichera dès la première mesure.')
        : t('Aucune mesure reçue sur cette période.'), false);
    ['legend-main', 'legend-prev'].forEach(id => {
      const l = document.getElementById(id);
      if (l) l.style.display = 'none';
    });
    updateChartFooter(null, null);
    return;
  }
  if (placeholder) placeholder.style.display = 'none';
  canvas.style.display = '';

  const isDark = state.theme === 'dark';
  /* Couleurs issues des tokens data-viz (--dv-*) : suivent le thème clair/sombre */
  const dvMain = cssVar('--dv-2', isDark ? '#3FB3A4' : '#1B7A6E');
  const dvCompare = cssVar('--dv-4', isDark ? '#C79B66' : '#8A5E2B');
  const surface = cssVar('--bg-s', isDark ? '#1E1A13' : '#FFFFFF');
  const fillTop = cssVar('--dv-fill-top', isDark ? 'rgba(63,179,164,0.22)' : 'rgba(27,122,110,0.13)');
  const fillBot = cssVar('--dv-fill-bot', isDark ? 'rgba(63,179,164,0)' : 'rgba(27,122,110,0)');
  const gColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(35,27,16,0.05)';
  const lColor = cssVar('--tx-s', isDark ? '#C2B19A' : '#6B5A45');

  const all = actual.concat(cmp ? cmp.values : []).filter(v => v !== null);
  const maxVal = all.length ? Math.max(...all) : 0;
  // Marge en haut de l'axe : une courbe basse ne colle pas au bord
  const suggestedMax = maxVal > 0 ? maxVal * 1.2 : 0.1;
  const base = slots.length > 12 ? 2 : 3;

  const datasets = [{
    label: mainName(), data: actual,
    borderColor: dvMain, borderWidth: 2.5, order: 1,
    backgroundColor: function (context) {
      const area = context.chart.chartArea;
      if (!area) return fillTop;
      const g = context.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
      g.addColorStop(0, fillTop);
      g.addColorStop(1, fillBot);
      return g;
    },
    fill: true, tension: .3, cubicInterpolationMode: 'monotone',
    pointRadius: pointRadiusFor(base), pointHoverRadius: 6,
    pointBackgroundColor: dvMain, pointBorderColor: surface, pointBorderWidth: 2,
    spanGaps: false
  }];
  if (cmp) {
    datasets.push({
      label: getCompareName(), data: cmp.values, cmpLabels: cmp.labels,
      borderColor: dvCompare, borderWidth: 2, borderDash: [5, 3],
      backgroundColor: 'transparent', fill: false, tension: .3, cubicInterpolationMode: 'monotone',
      pointRadius: pointRadiusFor(base), pointHoverRadius: 5,
      pointBackgroundColor: dvCompare, pointBorderColor: surface, pointBorderWidth: 1.5,
      spanGaps: false, order: 2
    });
  }

  const applyLegends = () => {
    const legendMain = document.getElementById('legend-main');
    if (legendMain) {
      legendMain.style.display = compareDrawn ? '' : 'none';
      const s = legendMain.querySelector('span');
      if (s) s.textContent = mainName();
    }
    const legendPrev = document.getElementById('legend-prev');
    if (legendPrev) {
      legendPrev.style.display = compareDrawn ? '' : 'none';
      const s = legendPrev.querySelector('span');
      if (s && compareDrawn) s.textContent = getCompareName();
    }
    updateChartFooter(actual, cmp ? cmp.values : null);
  };

  // Même structure (séries, créneaux, période) : mise à jour EN PLACE, sans clignotement
  const sig = `line|${datasets.length}|${labels.length}|${state.filter}|${state.comparePeriod}`;
  if (chart && chart.__aocedaSig === sig) {
    chart.data.labels = labels;
    datasets.forEach((ds, i) => { if (chart.data.datasets[i]) Object.assign(chart.data.datasets[i], ds); });
    chart.options.scales.y.suggestedMax = suggestedMax;
    chart.update();
    applyLegends();
    return;
  }

  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 400, easing: 'easeInOutQuart' },
      // Survol ou appui n'importe où dans la colonne : les deux courbes du même créneau, côte à côte
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cssVar('--bg-s', isDark ? '#1E1A13' : '#FFFFFF'),
          borderColor: cssVar('--bd-d', isDark ? 'rgba(255,255,255,0.14)' : '#CDBCA3'),
          borderWidth: 1,
          titleColor: cssVar('--tx-p', isDark ? '#F0E9DC' : '#231B10'),
          bodyColor: cssVar('--tx-s', isDark ? '#C2B19A' : '#6B5A45'),
          titleFont: { family: 'Hanken Grotesk', weight: '600', size: 13 },
          bodyFont: { family: 'Spline Sans Mono', size: 12 },
          padding: 12, cornerRadius: 8,
          callbacks: {
            title: items => {
              if (!items.length) return '';
              const s = slots[items[0].dataIndex];
              if (!s) return items[0].label;
              return hourly ? `${s.label} – ${s.date.getHours() + 1}h`
                : s.date.toLocaleDateString(_LOCALE, { weekday: 'long', day: 'numeric', month: 'long' });
            },
            label: ctx => {
              if (ctx.raw === null || ctx.raw === undefined) return null;
              const ds = ctx.dataset;
              const quand = ds.cmpLabels && ds.cmpLabels[ctx.dataIndex] ? ` (${ds.cmpLabels[ctx.dataIndex]})` : '';
              const ligne = `${ds.label}${quand} : ${fmtKwhAuto(ctx.raw)} kWh`;
              return state.prixKwh ? [ligne, `  ≈ ${fmtF(ctx.raw * state.prixKwh)}`] : ligne;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true, suggestedMax, grid: { color: gColor }, border: { display: false },
          ticks: {
            font: { family: 'Spline Sans Mono', size: 11 }, color: lColor, maxTicksLimit: 6,
            callback: v => `${fmtKwhAuto(v)} kWh`
          }
        },
        x: {
          grid: { display: false }, border: { display: false },
          ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lColor, maxTicksLimit: 12, maxRotation: 0, autoSkip: true }
        }
      }
    }
  });
  chart.__aocedaSig = sig;
  applyLegends();
}

/* Nom de la courbe principale : capteur (+ période quand on la compare à une autre période) */
function mainName() {
  const nom = sensorName(state.sensor);
  return state.compareSensor !== null && state.comparePeriod !== 'same' ? `${nom} · ${periodWords(state.filter)}` : nom;
}

/* Pied du graphe : total de la courbe affichée, son coût approché, et la comparaison s'il y en a une */
function updateChartFooter(actual, cmpValues) {
  const kwhEl = document.getElementById('cf-kwh');
  const lblEl = document.getElementById('cf-kwh-lbl');
  const fcfaEl = document.getElementById('cf-fcfa');
  const fcfaLbl = document.getElementById('cf-fcfa-lbl');
  const cmpBox = document.getElementById('cf-cmp');
  if (!kwhEl) return;

  const periode = { 'auj': t("Aujourd'hui, depuis minuit"), '7j': t('Ces 7 jours'), '30j': t('Ces 30 jours') }[state.filter];
  if (lblEl) lblEl.textContent = state.sensor !== 'all' ? `${periode} · ${sensorName(state.sensor)}` : periode;
  if (fcfaLbl) fcfaLbl.textContent = meterType() === 'prepaye'
    ? t('≈ coût, prix unique CIE') : t('≈ coût des kWh, hors abonnement');

  const nums = (actual || []).filter(v => v !== null);
  if (!nums.length) {
    kwhEl.textContent = t('Aucune mesure');
    if (fcfaEl) fcfaEl.textContent = t('Rien à chiffrer');
  } else {
    const total = nums.reduce((a, b) => a + b, 0);
    kwhEl.textContent = `${fmtKwhAuto(total)} kWh`;
    if (fcfaEl) fcfaEl.textContent = state.prixKwh ? `≈ ${fmtF(total * state.prixKwh)}` : t('Tarif en attente');
  }

  if (!cmpBox) return;
  const cn = (cmpValues || []).filter(v => v !== null);
  if (!cmpValues || !cn.length) { cmpBox.hidden = true; return; }
  cmpBox.hidden = false;
  const cTot = cn.reduce((a, b) => a + b, 0);
  const mTot = nums.reduce((a, b) => a + b, 0);
  const valEl = document.getElementById('cf-cmp-val');
  const cLbl = document.getElementById('cf-cmp-lbl');
  const delta = document.getElementById('cf-cmp-delta');
  if (valEl) valEl.textContent = `${fmtKwhAuto(cTot)} kWh`;
  if (cLbl) cLbl.textContent = getCompareName();
  if (delta) {
    if (cTot >= 0.01 && nums.length) {
      const pct = Math.round((mTot - cTot) / cTot * 100);
      delta.hidden = false;
      // Au-delà de +300 %, « × 27,6 » se lit mieux que « +2 657 % »
      delta.textContent = pct > 300 ? `× ${fmtNum(mTot / cTot, 1)}` : `${pct > 0 ? '+' : ''}${pct.toLocaleString(_LOCALE)} %`;
      delta.className = 'cf-delta ' + (pct > 0 ? 'up' : pct < 0 ? 'dn' : 'eq');
      delta.title = pct === 0 ? t('La courbe affichée consomme autant que la comparaison.')
        : `${t('La courbe affichée consomme')} ${Math.abs(pct)} % ${pct > 0 ? t('de plus') : t('de moins')} ${t('que la comparaison.')}`;
    } else {
      delta.hidden = true;
    }
  }
}

/* Série principale ; la comparaison n'est relue que si elle suit la période en cours ou si la vue a changé */
function loadTelemetry(reloadCompare) {
  let url = `/api/mesures/serie/?period=${PERIOD_API[state.filter] || 'week'}`;
  if (state.sensor !== 'all') url += `&sensor_id=${encodeURIComponent(state.sensor)}`;
  const req = (loadTelemetry._n = (loadTelemetry._n || 0) + 1);
  const vue = `${state.filter}|${state.sensor}`;
  fetchWithAuth(url)
    .then(data => {
      if (req !== loadTelemetry._n || vue !== `${state.filter}|${state.sensor}`) return; // réponse périmée
      state.telemetry = window.AOCEDA.asList(data);
      state.telemetryLoaded = true;
      state.telemetryError = false;
      if (state.compareSensor !== null && (reloadCompare || state.comparePeriod === 'same')) loadCompare();
      else renderChart();
    })
    .catch(err => {
      if (req !== loadTelemetry._n) return;
      console.error(err);
      state.telemetryError = true;
      // Une courbe déjà tracée reste affichée (le prochain rafraîchissement réessaie) ; sinon, message clair
      if (!state.telemetryLoaded || !chart) { state.telemetryLoaded = true; state.telemetry = []; renderChart(); }
    });
}

function toDateStr(d) { return repISO(d); }

function fmtShortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return iso;
  return d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' });
}

/* Nom lisible de la comparaison active : « Capteur · période » (bouton, légende, infobulle, pied) */
function getCompareName() {
  if (state.compareSensor === null) return '';
  const nom = sensorName(state.compareSensor);
  if (state.comparePeriod === 'prev') {
    return `${nom} · ${state.filter === 'auj' ? t('hier') : state.filter === '30j' ? t('30 jours d’avant') : t('7 jours d’avant')}`;
  }
  if (state.comparePeriod === 'custom') {
    if (!state.compareDates) return `${nom} · ${t('plage à choisir')}`;
    const { from, to } = state.compareDates;
    return `${nom} · ${state.filter === 'auj' || from === to ? fmtShortDate(from) : `${fmtShortDate(from)} → ${fmtShortDate(to)}`}`;
  }
  return nom;
}

/* Ligne des dates (plage libre). Vue « Aujourd'hui » : un seul jour, comparé heure par heure. */
function showDateRow(show) {
  const row = document.getElementById('cbar-dates');
  if (!row) return;
  row.style.display = show ? '' : 'none';
  const unJour = state.filter === 'auj';
  const lblFrom = row.querySelector('label[for="cbar-from"]');
  const lblTo = row.querySelector('label[for="cbar-to"]');
  const to = document.getElementById('cbar-to');
  if (lblFrom) lblFrom.textContent = unJour ? t('Le') : t('Du');
  if (lblTo) lblTo.hidden = unJour;
  if (to) to.hidden = unJour;
  if (show) {
    // Pré-rempli avec la période d'avant (même durée que la vue) : « Charger » marche du premier coup
    const from = document.getElementById('cbar-from');
    const today = new Date();
    const n = unJour ? 1 : state.filter === '30j' ? 30 : 7;
    if (from && !from.value) from.value = repISO(new Date(today.getFullYear(), today.getMonth(), today.getDate() - (unJour ? 1 : 2 * n - 1)));
    if (to && !to.value) to.value = repISO(new Date(today.getFullYear(), today.getMonth(), today.getDate() - n));
  }
}

/* Charge la série du capteur comparé (même période, période d'avant ou plage libre) */
function loadCompare() {
  if (state.compareSensor === null) { renderChart(); return; }
  let url;
  if (state.comparePeriod === 'same') {
    url = `/api/mesures/serie/?period=${PERIOD_API[state.filter] || 'week'}`;
  } else {
    const r = compareRange();
    if (!r) { state.prevTelemetry = []; state.compareLoaded = false; renderChart(); return; }
    url = `/api/mesures/serie/?date_from=${r.from}&date_to=${r.to}`;
  }
  if (state.compareSensor !== 'all') url += `&sensor_id=${encodeURIComponent(state.compareSensor)}`;
  const req = (loadCompare._n = (loadCompare._n || 0) + 1);
  fetchWithAuth(url)
    .then(data => { if (req === loadCompare._n) state.prevTelemetry = window.AOCEDA.asList(data); })
    .catch(() => {
      if (req !== loadCompare._n) return;
      state.prevTelemetry = [];
      setCbarHint(t('La comparaison n’a pas pu être chargée. Réessayez.'), true);
    })
    .finally(() => {
      if (req !== loadCompare._n) return;
      state.compareLoaded = true;
      updateCompareBtn();
      renderChart();
    });
}

function setCbarHint(msg, isErr) {
  const el = document.getElementById('cbar-hint');
  if (!el) return;
  el.textContent = msg || '';
  el.hidden = !msg;
  el.classList.toggle('err', !!isErr);
}

function resetCompareData() {
  state.prevTelemetry = [];
  state.compareLoaded = false;
}

/* Étape 1 : le capteur à comparer (obligatoire). Re-clic sur le capteur choisi : comparaison retirée. */
function setCompareSensor(id) {
  if (state.compareSensor === id) {
    state.compareSensor = null;
    resetCompareData();
    updateCompareBtn();
    setCbarHint('');
    renderChart();
    return;
  }
  state.compareSensor = id;
  resetCompareData();
  setCbarHint('');
  // Même capteur que la vue sur la même période = deux courbes identiques : on compare avec la période d'avant
  if (id === state.sensor && state.comparePeriod === 'same') {
    state.comparePeriod = 'prev';
    showDateRow(false);
    setCbarHint(t('Même capteur que la vue : comparaison avec la période d’avant.'));
  }
  updateCompareBtn();
  if (state.comparePeriod === 'custom' && !state.compareDates) {
    setCbarHint(t('Choisissez les dates, puis « Charger ».'));
    renderChart();
    return;
  }
  if (state.telemetryLoaded) loadCompare(); else renderChart();
}

/* Étape 2 : la période de comparaison */
function setComparePeriod(p) {
  if (state.comparePeriod === p) return; // un des modes est toujours actif
  if (p === 'same' && state.compareSensor !== null && state.compareSensor === state.sensor) {
    setCbarHint(t('Même capteur et même période : les deux courbes seraient identiques. Choisissez un autre capteur.'), true);
    return;
  }
  state.comparePeriod = p;
  state.compareDates = null;
  resetCompareData();
  updateCompareBtn();
  setCbarHint('');
  showDateRow(p === 'custom');
  if (state.compareSensor === null) {
    setCbarHint(t('Choisissez maintenant le capteur à comparer.'));
    renderChart();
    return;
  }
  if (p === 'custom') {
    setCbarHint(t('Choisissez les dates, puis « Charger ».'));
    renderChart();
    return;
  }
  if (state.telemetryLoaded) loadCompare(); else renderChart();
}

function clearCompare() {
  state.compareSensor = null;
  state.comparePeriod = 'same';
  state.compareDates = null;
  resetCompareData();
  state.compareBarOpen = false;
  const bar = document.getElementById('compare-bar');
  if (bar) bar.style.display = 'none';
  const btn = document.getElementById('compare-btn');
  if (btn) { btn.classList.remove('open', 'active'); btn.setAttribute('aria-expanded', 'false'); }
  updateCompareBtn();
  showDateRow(false);
  setCbarHint('');
  renderChart();
}

function updateCompareBtn() {
  const btn = document.getElementById('compare-btn');
  const lbl = document.getElementById('compare-label');
  if (btn) btn.classList.toggle('active', state.compareSensor !== null);
  document.querySelectorAll('.copt[data-csensor]').forEach(b => {
    const on = b.dataset.csensor === state.compareSensor;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  document.querySelectorAll('.copt[data-cperiod]').forEach(b => {
    const on = b.dataset.cperiod === state.comparePeriod;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  if (lbl) lbl.textContent = state.compareSensor !== null ? getCompareName() : t('Comparer');
  if (btn) btn.title = state.compareSensor !== null ? `${t('Comparaison')} : ${getCompareName()}` : '';
}

function updateCompareSensors() {
  const container = document.getElementById('copt-sensors');
  if (!container) return;
  if (!state.sensorsList.length) {
    container.innerHTML = `<span class="copt-empty">${t('Aucun capteur')}</span>`;
    return;
  }
  const icoSensor = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="2"/><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`;
  const icoAll = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>`;
  const parts = [];
  // « Tous les capteurs » seulement s'il y en a au moins 2 (sinon c'est l'unique capteur)
  if (state.sensorsList.length >= 2) {
    const on = state.compareSensor === 'all';
    parts.push(`<button type="button" class="copt${on ? ' active' : ''}" aria-pressed="${on}" data-csensor="all">${icoAll}${t('Tous les capteurs')}</button>`);
  }
  // Le capteur de la vue y est aussi : il se compare alors à une autre période
  state.sensorsList.forEach(s => {
    const on = state.compareSensor === String(s.id);
    parts.push(`<button type="button" class="copt${on ? ' active' : ''}" aria-pressed="${on}" data-csensor="${esc(s.id)}">${icoSensor}${esc(s.nom)}</button>`);
  });
  const html = parts.join('');
  if (container.__html !== html) { container.innerHTML = html; container.__html = html; }
}

/* ── Onglets de période ── */
function setFilter(f) {
  if (state.filter === f && state.telemetryLoaded) return;
  state.filter = f;
  state.telemetryLoaded = false;
  resetCompareData(); // évite de dessiner une comparaison périmée pendant le rechargement
  document.querySelectorAll('#filter-pills .pill').forEach(b => {
    const on = b.dataset.filter === f;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  // Plage libre : la vue « Aujourd'hui » se compare à un seul jour ; les dates sont reproposées pour la nouvelle durée
  if (state.comparePeriod === 'custom') {
    state.compareDates = null;
    ['cbar-from', 'cbar-to'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    showDateRow(true);
    if (state.compareSensor !== null) setCbarHint(t('Choisissez les dates, puis « Charger ».'));
  }
  updateCompareBtn();
  renderChart(); // affiche le chargement
  loadTelemetry(true);
}

/* ── Onglets capteurs ── */
function renderSensorTabs() {
  const wrap = document.getElementById('sensor-tabs');
  if (!wrap) return;
  const tab = (id, nom) => {
    const on = state.sensor === id;
    return `<button type="button" class="stab${on ? ' active' : ''}" aria-pressed="${on}" data-sensor="${esc(id)}">${esc(nom)}</button>`;
  };
  // Un seul capteur : « Tous les capteurs » et lui sont la même courbe, un seul onglet suffit
  const html = state.sensorsList.length === 1 && state.sensor === 'all'
    ? tab('all', state.sensorsList[0].nom)
    : tab('all', t('Tous les capteurs')) + state.sensorsList.map(s => tab(String(s.id), s.nom)).join('');
  // Réécrit seulement si la liste a changé : un onglet qui a le focus clavier le garde
  if (wrap.__html !== html) { wrap.innerHTML = html; wrap.__html = html; }
  wrap.hidden = state.sensorsList.length <= 1;
}

function setSensor(id) {
  if (state.sensor === id) return;
  state.sensor = id;
  state.telemetryLoaded = false;
  resetCompareData();
  // La vue devient le capteur comparé, sur la même période : on le compare avec la période d'avant
  if (state.compareSensor === id && state.comparePeriod === 'same') {
    state.comparePeriod = 'prev';
    showDateRow(false);
    if (state.compareBarOpen) setCbarHint(t('Même capteur que la vue : comparaison avec la période d’avant.'));
  }
  updateCompareBtn();
  renderSensorTabs();
  updateCompareSensors();
  renderChart();
  loadTelemetry(true);
}

/* ════════════════════════ STATUT IoT ════════════════════════ */
const HORS_LIGNE_MS = 30000; // sans nouvelle du boîtier depuis 30 s : capteur hors ligne

function vuLe(s) { return s.derniereLecture ? new Date(s.derniereLecture) : null; }
function enLigne(s) { const vu = vuLe(s); return !!vu && Date.now() - vu.getTime() <= HORS_LIGNE_MS; }

/* Dernier contact du boîtier, tous capteurs confondus (ou celui du serveur avant la 1re liste) */
function dernierContact() {
  let best = null;
  state.sensorsList.forEach(s => { const vu = vuLe(s); if (vu && (!best || vu > best)) best = vu; });
  if (!best && state.kpis && state.kpis.dernier_contact) best = new Date(state.kpis.dernier_contact);
  return best;
}

function sensorRowHtml(s) {
  // Deux informations distinctes par ligne (14/10/2026, demande du client) :
  //  1. le CAPTEUR fonctionne-t-il ? = le boîtier répond (dernier contact < 30 s) ;
  //  2. l'APPAREIL est-il allumé, éteint ou coupé à distance, et depuis quand ?
  const vu = vuLe(s);
  const stale = !enLigne(s);
  const etat = s.sseEtat || s.etatCourant;   // état réel persisté côté serveur : 'ON' consomme, 'OFF' éteint
  // Relais : bouton seulement si le boîtier a déjà rapporté l'état de son relais
  const aRelais = s.coupureEffective === true || s.coupureEffective === false;
  const ordreEnAttente = aRelais && s.coupureDemandee !== s.coupureEffective;

  const sante = !vu ? { cls: 'sa-err', txt: t('Capteur jamais connecté') }
    : stale ? { cls: 'sa-err', txt: `${t('Hors ligne')} · ${t('vu')} ${timeAgo(vu)}` }
    : { cls: 'sa-ok', txt: t('Capteur OK') };

  // Sans contact, l'état de l'appareil n'est pas connu : on ne le devine pas.
  let app;
  if (stale && ordreEnAttente) app = { cls: 'ea-attente', txt: s.coupureDemandee ? t('Coupure à la reconnexion') : t('Rétablissement à la reconnexion') };
  else if (stale) app = { cls: 'ea-inconnu', txt: t('État inconnu') };
  else if (ordreEnAttente) app = { cls: 'ea-attente', txt: s.coupureDemandee ? t('Coupure en cours…') : t('Rétablissement en cours…') };
  else if (aRelais && s.coupureEffective) app = { cls: 'ea-coupe', txt: t('Coupé à distance') };
  else if (etat === 'ON') app = { cls: 'ea-on', txt: t('Allumé') };
  else app = { cls: 'ea-off', txt: t('Éteint') };
  const depuis = !stale && !ordreEnAttente && s.etatDepuis ? `${t('depuis')} ${dureeDepuis(new Date(s.etatDepuis))}` : '';
  let bouton = '';
  if (aRelais) {
    const id = String(s.id);
    const envoi = relaisEnvoi.has(id);
    const confirmer = relaisConfirm.id === id && Date.now() < relaisConfirm.jusqua;
    const couper = !s.coupureDemandee; // action proposée : l'inverse de l'ordre en vigueur
    const libelle = envoi ? '…' : confirmer ? t('Confirmer ?') : couper ? t('Couper') : t('Rétablir');
    const aide = couper ? t('Couper le courant de cet appareil') : t('Rétablir le courant de cet appareil');
    bouton = `<button type="button" class="relais-btn ${couper ? 'rb-couper' : 'rb-retablir'}${confirmer ? ' rb-confirmer' : ''}"
      data-id="${esc(id)}" data-coupe="${couper}" ${envoi ? 'disabled' : ''}
      title="${esc(aide)}" aria-label="${esc(aide)} : ${esc(s.nom)}">${esc(libelle)}</button>`;
  }
  return `<div class="sensor-corps">
      <div class="sensor-name" title="${esc(s.nom)}">${esc(s.nom)}</div>
      <div class="sensor-sante ${sante.cls}"><i aria-hidden="true"></i><span>${esc(sante.txt)}</span></div>
    </div>
    <div class="sensor-etat ${app.cls}">
      <b><i aria-hidden="true"></i>${esc(app.txt)}</b>
      ${depuis ? `<small>${esc(depuis)}</small>` : ''}
    </div>
    ${bouton}`;
}

function renderIoT() {
  const wrap = document.getElementById('sensor-list');
  if (!wrap) return;
  const list = state.sensorsList;

  // Mini-statistiques, toutes mesurées : capteurs qui répondent, appareils allumés, dernier contact
  const nbEnLigne = list.filter(enLigne).length;
  const activeEl = document.getElementById('iot-active');
  if (activeEl) {
    activeEl.textContent = list.length ? `${nbEnLigne}/${list.length}` : '0';
    activeEl.className = 'iot-stat-val ' + (list.length && nbEnLigne === list.length ? 'ok' : nbEnLigne ? 'warn' : 'err');
  }
  const onEl = document.getElementById('iot-on');
  if (onEl) {
    const allumes = list.filter(s => enLigne(s) && (s.sseEtat || s.etatCourant) === 'ON' && s.coupureEffective !== true).length;
    onEl.textContent = list.length ? (nbEnLigne ? String(allumes) : t('inconnu')) : '0';
  }
  const vuEl = document.getElementById('iot-seen');
  if (vuEl) {
    const vu = dernierContact();
    vuEl.textContent = !vu ? t('jamais') : (Date.now() - vu.getTime() <= HORS_LIGNE_MS ? t('à l’instant') : timeAgo(vu));
  }

  if (list.length === 0) {
    if (wrap.__vide !== true) { wrap.innerHTML = EMPTY_SENSORS_HTML; wrap.__vide = true; }
    return;
  }
  if (wrap.__vide) { wrap.innerHTML = ''; wrap.__vide = false; }

  // Mise à jour LIGNE PAR LIGNE (le flux arrive chaque seconde) : une ligne inchangée n'est pas touchée,
  // et le bouton Couper / Rétablir qui a le focus clavier le retrouve après la mise à jour.
  const focusId = document.activeElement && document.activeElement.closest
    && document.activeElement.closest('#sensor-list .relais-btn') ? document.activeElement.dataset.id : null;
  const ids = new Set(list.map(s => String(s.id)));
  wrap.querySelectorAll('.sensor-row').forEach(r => { if (!ids.has(r.dataset.sid)) r.remove(); });
  list.forEach((s, i) => {
    const sid = String(s.id);
    let row = wrap.querySelector(`.sensor-row[data-sid="${CSS.escape(sid)}"]`);
    if (!row) {
      row = document.createElement('div');
      row.dataset.sid = sid;
    }
    if (wrap.children[i] !== row) wrap.insertBefore(row, wrap.children[i] || null);
    const aRelais = s.coupureEffective === true || s.coupureEffective === false;
    row.className = 'sensor-row' + (aRelais ? ' a-relais' : '');
    const html = sensorRowHtml(s);
    if (row.__html !== html) { row.innerHTML = html; row.__html = html; }
  });
  if (focusId) {
    const b = wrap.querySelector(`.relais-btn[data-id="${CSS.escape(focusId)}"]`);
    if (b && document.activeElement !== b) b.focus();
  }
}

/* « depuis 12 min » : durée lisible depuis un instant passé (12 s, 5 min, 2 h 10, 3 j) */
function dureeDepuis(d) {
  const s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`; }
  return `${Math.floor(s / 86400)} j`;
}

/* ── Coupure à distance (relais du boîtier) ──
   1er clic : le bouton demande confirmation pendant 4 s ; 2e clic : l'ordre part. Le
   boîtier l'applique à son prochain envoi de mesures (environ 1 s) : la liste est
   relue jusqu'à ce que l'état réel du relais (coupureEffective) suive l'ordre.
   État gardé ici, hors du DOM : renderIoT réécrit la liste à chaque mesure reçue. */
const relaisConfirm = { id: null, jusqua: 0 };
const relaisEnvoi = new Set();
const RELAIS_CONFIRM_MS = 4000;

function suivreOrdreRelais(id, essais) {
  if (essais <= 0) return;
  setTimeout(() => {
    loadSensors();
    const s = state.sensorsList.find(x => String(x.id) === id);
    if (s && s.coupureDemandee !== s.coupureEffective) suivreOrdreRelais(id, essais - 1);
  }, 1500);
}

function envoyerOrdreRelais(id, coupe) {
  relaisEnvoi.add(id);
  renderIoT();
  fetchWithAuth(`/api/sensors/mes-capteurs/${encodeURIComponent(id)}/coupure/`, {
    method: 'POST',
    body: JSON.stringify({ coupe })
  })
    .then(maj => {
      const s = state.sensorsList.find(x => String(x.id) === id);
      if (s) {
        s.coupureDemandee = maj.coupureDemandee;
        s.coupureEffective = maj.coupureEffective;
      }
      suivreOrdreRelais(id, 8);
    })
    .catch(err => {
      console.error(err);
      alerteRelais(t('L’ordre n’a pas pu être envoyé. Vérifiez la connexion et réessayez.'));
    })
    .finally(() => { relaisEnvoi.delete(id); renderIoT(); });
}

/* Message d'échec discret sous la liste (pas de fenêtre bloquante) */
function alerteRelais(texte) {
  const wrap = document.getElementById('sensor-list');
  if (!wrap) return;
  let el = document.getElementById('relais-erreur');
  if (!el) {
    el = document.createElement('div');
    el.id = 'relais-erreur';
    el.className = 'relais-erreur';
    el.setAttribute('role', 'alert');
    wrap.insertAdjacentElement('afterend', el);
  }
  el.textContent = texte;
  clearTimeout(alerteRelais._minuteur);
  alerteRelais._minuteur = setTimeout(() => { el.textContent = ''; }, 6000);
}

function brancherBoutonsRelais() {
  const wrap = document.getElementById('sensor-list');
  if (!wrap || wrap.dataset.relais) return;
  wrap.dataset.relais = '1';
  wrap.addEventListener('click', e => {
    const btn = e.target.closest('.relais-btn');
    if (!btn || btn.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    const id = btn.dataset.id;
    if (relaisConfirm.id === id && Date.now() < relaisConfirm.jusqua) {
      relaisConfirm.id = null;
      envoyerOrdreRelais(id, btn.dataset.coupe === 'true');
      return;
    }
    relaisConfirm.id = id;
    relaisConfirm.jusqua = Date.now() + RELAIS_CONFIRM_MS;
    renderIoT();
    setTimeout(() => { if (relaisConfirm.id === id && Date.now() >= relaisConfirm.jusqua) renderIoT(); },
      RELAIS_CONFIRM_MS + 50);
  });
}

function loadSensors() {
  fetchWithAuth('/api/sensors/')
    .then(data => {
      const newList = window.AOCEDA.asList(data);
      newList.forEach(s => {
        const existing = state.sensorsList.find(x => String(x.id) === String(s.id));
        // L'état provenant de l'API REST (persisté) fait autorité lors du rechargement.
        // Cela empêche un état SSE obsolète de bloquer indéfiniment la vue si un événement est manqué.
        if (s.etatCourant) s.sseEtat = s.etatCourant;
        else if (existing && existing.sseEtat) s.sseEtat = existing.sseEtat;
        
        // derniereMesure n'existe que via le SSE : on le préserve entre deux reloads.
        if (existing && existing.derniereMesure) s.derniereMesure = existing.derniereMesure;
      });
      state.sensorsList = newList;
      // Le capteur affiché a été supprimé ou dissocié : retour à « Tous les capteurs »
      if (state.sensor !== 'all' && !newList.some(s => String(s.id) === state.sensor)) setSensor('all');
      renderSensorTabs();
      renderIoT();
      updateCompareSensors();
      updateConnectionBadge();
      renderPowerKpi();
      renderFreshness();
    })
    .catch(err => console.error(err));
}

/* ════════════════════════ ALERTES ════════════════════════ */
/* Style par sévérité : tokens sémantiques (s'adaptent au thème clair/sombre).
   Badge = fond --X-surf + texte --X (règle du design system). Le rouge --err
   reste réservé aux anomalies, ici une alerte critique en est une. */
const SEV_STYLE = {
  'Critique': {
    c: 'var(--err)', bg: 'var(--err-surf)',
    ico: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
  },
  'Avertissement': {
    c: 'var(--warn)', bg: 'var(--warn-surf)',
    ico: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
  },
  'Info': {
    c: 'var(--info)', bg: 'var(--info-surf)',
    ico: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
  }
};

/* Libellé lisible du type d'alerte : celui du serveur (type_display, à jour de tous les types, dont les alertes de
   tranche) ; repli sur le code brut rendu lisible. */
function alertTypeLabel(a) {
  return a.type_display || String(a.type || '').replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase());
}

/* Heure de l'alerte : « il y a 5 min · 14:02 » aujourd'hui, sinon la date */
function alertWhen(created) {
  const auj = new Date();
  const memeJour = created.toDateString() === auj.toDateString();
  const quand = memeJour
    ? created.toLocaleTimeString(_LOCALE, { hour: '2-digit', minute: '2-digit' })
    : created.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' });
  return memeJour ? `${timeAgo(created)} · ${quand}` : quand;
}

function renderAlerts() {
  const wrap = document.getElementById('alerts-list');
  if (!wrap) return;
  const list = state.alerts;

  // Nombre TOTAL d'alertes non lues (résumé), pas la sous-liste limitée à 3
  const activeCount = (state.kpis && state.kpis.alertes_actives != null)
    ? state.kpis.alertes_actives
    : (state.alertsLoaded ? list.filter(a => !a.lue).length : null);
  const countEl = document.getElementById('alerts-count');
  if (countEl && activeCount != null) {
    countEl.textContent = activeCount === 0 ? t('aucune non lue')
      : `${activeCount} ${activeCount > 1 ? t('non lues') : t('non lue')}`;
  }

  let html;
  if (!state.alertsLoaded) html = state.alertsError
    ? `<div class="alerts-msg">${t('Impossible de charger les alertes. Nouvel essai dans quelques secondes…')}</div>`
    : `<div class="alerts-msg">${t('Chargement des alertes…')}</div>`;
  else if (list.length === 0) html = EMPTY_ALERTS_HTML;
  else html = list.map(a => {
    const sev = a.sévérité || a.severity || 'Avertissement';
    const st = SEV_STYLE[sev] || SEV_STYLE['Avertissement'];
    const created = new Date(a.createdAt);
    const type = alertTypeLabel(a);
    return `<a class="alert-item${a.lue ? ' lue' : ''}" href="/alertes/" title="${esc(type)} : ${esc(a.message)}">
      <div class="alert-ico" style="background:${st.bg};color:${st.c}">${st.ico}</div>
      <div style="flex:1;min-width:0">
        <div class="alert-head">
          <span class="alert-type">${esc(t(type))}</span>
          <span class="alert-badge" style="background:${st.bg};color:${st.c}">${esc(t(sev))}</span>
        </div>
        <div class="alert-msg">${esc(a.message)}</div>
        <div class="alert-foot">
          <span class="alert-time">${esc(alertWhen(created))}</span>
          ${a.lue ? `<span class="alert-read">${t('lue')}</span>` : ''}
        </div>
      </div>
    </a>`;
  }).join('');
  // Réécrit seulement si le contenu a changé (rafraîchi toutes les 30 s)
  if (wrap.__html !== html) { wrap.innerHTML = html; wrap.__html = html; }
}

function loadAlerts() {
  fetchWithAuth('/api/alertes/?limit=3')
    .then(data => {
      state.alerts = window.AOCEDA.asList(data).slice(0, 3);
      state.alertsLoaded = true;
      state.alertsError = false;
      renderAlerts();
    })
    .catch(err => {
      console.error(err);
      state.alertsError = true;
      renderAlerts();
    });
}

/* ════════════════════ RÉPARTITION PAR APPAREIL ════════════════════ */
/* Donut « où va l'énergie » : part de chaque capteur (kWh + %), pic de puissance,
   et alerte si le pic dépasse la capacité du disjoncteur. Période réglable comme le
   graphe principal (aujourd'hui / 7 j / 30 j / plage libre). 100 % données réelles
   (/api/analytics/repartition/), état vide honnête (jamais de segment fabriqué). */
let repChart = null;
const REP_MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                  'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

function repFmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' });
}
function repPeriodLabel() {
  if (state.repMode === 'custom' && state.repFrom && state.repTo) {
    const f = repFmtDate(state.repFrom), dTo = repFmtDate(state.repTo);
    return f === dTo ? f : `${f} → ${dTo}`;
  }
  return state.repDays <= 1 ? t("aujourd'hui") : `${state.repDays} ${t('derniers jours')}`;
}

function renderRepartition() {
  const empty = document.getElementById('rep-empty');
  const viz = document.getElementById('rep-viz');
  const sub = document.getElementById('rep-sub');
  if (sub) sub.textContent = repPeriodLabel();
  if (!empty || !viz) return;

  const data = state.repartition;
  const caps = data ? (data.capteurs || []).filter(c => Number(c.kwh) > 0) : [];
  const total = data ? Number(data.total_kwh || 0) : 0;
  const pcts = repartirEntier(caps.map(c => Number(c.kwh)));

  // États sans donut : chargement / rien de mesuré / conso négligeable.
  // (Honnête : jamais de donut de pourcentages sur une conso qui arrondit à 0,00 kWh.)
  if (!data) {
    empty.textContent = t('Chargement en cours…'); empty.hidden = false; viz.hidden = true;
    if (repChart) { repChart.destroy(); repChart = null; }
    return;
  }
  if (caps.length === 0 || total < 0.01) {
    empty.innerHTML = caps.length === 0
      ? t('Aucune consommation mesurée sur cette période.') + '<br>' +
        t('La répartition s’affichera dès que vos capteurs relèveront des données.')
      : t('Consommation négligeable sur cette période (moins de 0,01 kWh).');
    empty.hidden = false; viz.hidden = true;
    if (repChart) { repChart.destroy(); repChart = null; }
    return;
  }
  empty.hidden = true; viz.hidden = false;

  const isDark = state.theme === 'dark';
  const palette = ['--dv-2', '--dv-1', '--dv-3', '--dv-4', '--dv-5', '--dv-6']
    .map((v, i) => cssVar(v, ['#1B7A6E', '#E8930C', '#3F7CA0', '#8A5E2B', '#5E8C5A', '#9C7BB0'][i]));
  const colors = caps.map((_, i) => palette[i % palette.length]);
  const surface = cssVar('--rep-gap', cssVar('--bg-s', isDark ? '#0A0A0A' : '#FFFFFF'));
  const capW = Number(data.capacite_w) || 0;

  // ── Donut (Chart.js) : mis à jour EN PLACE si le nombre de segments est identique
  //    (transition animée, pas de clignotement au rafraîchissement 30 s). ──
  const canvas = document.getElementById('rep-chart');
  const values = caps.map(c => Number(c.kwh));
  const labels = caps.map(c => c.nom);
  if (canvas) {
    if (repChart && repChart.data.datasets[0].data.length === values.length) {
      repChart.data.labels = labels;
      Object.assign(repChart.data.datasets[0], { data: values, backgroundColor: colors, borderColor: surface });
      repChart.update();
    } else {
      if (repChart) { repChart.destroy(); repChart = null; }
      repChart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: surface, borderWidth: 3, hoverOffset: 6 }] },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: '66%',
          animation: { duration: 500, easing: 'easeInOutQuart' },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: cssVar('--bg-s', isDark ? '#1E1A13' : '#FFFFFF'),
              borderColor: cssVar('--bd-d', isDark ? 'rgba(255,255,255,0.16)' : '#D5D9DF'),
              borderWidth: 1,
              titleColor: cssVar('--tx-p', isDark ? '#ECEBE8' : '#111827'),
              bodyColor: cssVar('--tx-s', isDark ? '#B2B0AB' : '#4B5563'),
              titleFont: { family: 'Hanken Grotesk', weight: '600', size: 13 },
              bodyFont: { family: 'Spline Sans Mono', size: 12 },
              padding: 10, cornerRadius: 8,
              callbacks: {
                title: items => items.length ? items[0].label : '',
                label: ctx => {
                  const c = caps[ctx.dataIndex]; if (!c) return '';
                  return ` ${fmtKwhAuto(c.kwh)} kWh · ${pcts[ctx.dataIndex]} %`;
                }
              }
            }
          }
        }
      });
    }
  }

  // ── Centre du donut : total de la période ──
  const center = document.getElementById('rep-center');
  if (center) {
    const tot = fmtKwhAuto(Number(data.total_kwh || 0));
    center.innerHTML = `<span class="rc-val">${tot}</span><span class="rc-unit">kWh</span><span class="rc-lbl">${t('total')}</span>`;
  }

  // ── Légende détaillée : nom + kWh + % + pic + alerte disjoncteur ──
  const legend = document.getElementById('rep-legend');
  if (legend) {
    legend.innerHTML = caps.map((c, i) => {
      const col = colors[i];
      const over = capW > 0 && Number(c.peak_w) > capW;
      const kwh = fmtKwhAuto(c.kwh);
      const peak = Math.round(Number(c.peak_w) || 0).toLocaleString(_LOCALE);
      return `<div class="rep-li">
        <div class="rep-li-head">
          <span class="rep-name" title="${esc(c.nom)}"><span class="rep-dot" style="background:${col}"></span><span class="rep-nom">${esc(c.nom)}</span></span>
          <span class="rep-val" data-pct="${pcts[i]}"><strong>${kwh} kWh</strong> · ${pcts[i]} %</span>
        </div>
        ${Number(c.peak_w) > 0 ? `<div class="rep-foot">${t('pic')} ${peak} W${over ? ` <span class="rep-over">${t('dépasse votre abonnement de')} ${esc(String(data.amperage))} A</span>` : ''}</div>` : ''}
      </div>`;
    }).join('');
  }
}

/* Parts entières qui somment exactement à 100 (méthode du plus grand reste) : « 33 + 33 + 33 = 99 % » n'arrive plus */
function repartirEntier(vals) {
  const tot = vals.reduce((a, b) => a + b, 0);
  if (!(tot > 0)) return vals.map(() => 0);
  const brut = vals.map(v => v / tot * 100);
  const ent = brut.map(Math.floor);
  let reste = 100 - ent.reduce((a, b) => a + b, 0);
  brut.map((v, i) => [v - ent[i], i]).sort((x, y) => y[0] - x[0]).forEach(([, i]) => { if (reste > 0) { ent[i]++; reste--; } });
  return ent;
}

function loadRepartition() {
  let url = '/api/analytics/repartition/';
  if (state.repMode === 'custom' && state.repFrom && state.repTo) {
    url += `?from=${encodeURIComponent(state.repFrom)}&to=${encodeURIComponent(state.repTo)}`;
  } else {
    url += `?days=${state.repDays}`;
  }
  fetchWithAuth(url)
    .then(data => { state.repartition = data || { capteurs: [] }; renderRepartition(); })
    .catch(err => {
      console.error(err);
      if (!state.repartition) {
        const empty = document.getElementById('rep-empty');
        if (empty) empty.textContent = t('Impossible de charger la répartition. Nouvel essai dans quelques secondes…');
      }
    });
}

/* ════════════════════════ KPI + PRÉVISION ════════════════════════ */
/* Anti-flash : les DERNIÈRES valeurs réelles des indicateurs sont réaffichées au chargement, en grisé (« dernière
   valeur connue »), le temps que les données du moment arrivent. Le cache est PROPRE AU COMPTE (identifiant lu dans
   le jeton) et vidé à la déconnexion : avant le 19/10/2026, un second compte ouvert sur le même appareil voyait un
   instant les chiffres du premier. */
function compteId() {
  try {
    const tk = localStorage.getItem('aoceda_access_token') || '';
    const p = JSON.parse(atob(tk.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return p.user_id != null ? String(p.user_id) : null;
  } catch (e) { return null; }
}
const KPI_CACHE_KEY = (() => { const id = compteId(); return id ? `aoceda_kpi_cache_v2_${id}` : null; })();
const KPI_CACHE_IDS = ['kpi-power', 'kpi-energy', 'kpi-bill', 'kpi-alerts', 'kpi-bill-label', 'kpi-bill-meta', 'forecast-bill', 'iot-active'];
function cacheKpis() {
  if (!KPI_CACHE_KEY || !state.kpisLive) return;
  try {
    const snap = {};
    KPI_CACHE_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.textContent && !el.querySelector('.skel') && !el.classList.contains('kpi-unknown')) snap[id] = el.textContent;
    });
    if (Object.keys(snap).length) localStorage.setItem(KPI_CACHE_KEY, JSON.stringify(snap));
  } catch (e) { /* stockage indisponible : sans gravité */ }
}
function restoreKpis() {
  try {
    localStorage.removeItem('aoceda_kpi_cache_v1'); // ancien cache commun à tous les comptes
    if (!KPI_CACHE_KEY) return;
    const snap = JSON.parse(localStorage.getItem(KPI_CACHE_KEY) || '{}');
    Object.keys(snap).forEach(id => {
      const el = document.getElementById(id);
      if (el && snap[id]) { el.textContent = snap[id]; el.classList.add('kpi-stale'); el.title = t('Dernière valeur connue, mise à jour en cours…'); }
    });
  } catch (e) { /* ignore */ }
}
function setKpi(el, text, unknown) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove('kpi-stale');
  el.classList.toggle('kpi-unknown', !!unknown);
  el.removeAttribute('title');
}

/* « il y a 3 h », « le 12 oct. à 14:05 » pour un contact plus ancien qu'un jour */
function quandContact(d) {
  if (!d) return '';
  if (Date.now() - d.getTime() < 86400000) return timeAgo(d);
  return `${t('le')} ${d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' })} ${t('à')} ${d.toLocaleTimeString(_LOCALE, { hour: '2-digit', minute: '2-digit' })}`;
}

/* Le boîtier répond-il ? Flux temps réel d'abord (seconde par seconde), sinon le résumé du serveur */
function boitierEnLigne() {
  if (state.sensorsList.length && state.sseVu) return state.sensorsList.some(enLigne);
  return !!(state.kpis && state.kpis.en_ligne);
}

function renderPowerKpi() {
  const power = document.getElementById('kpi-power');
  const meta = document.getElementById('kpi-power-meta');
  const kpis = state.kpis;
  if (!power || !kpis) return;
  if (kpis.mode === 'vide') {
    setKpi(power, t('Aucun capteur'), true);
    if (meta) meta.textContent = t('Installez un capteur pour la mesurer');
    return;
  }
  if (!boitierEnLigne()) {
    // Boîtier muet : la puissance est INCONNUE, pas « 0 W »
    const vu = dernierContact();
    setKpi(power, t('Hors ligne'), true);
    if (meta) meta.textContent = vu ? `${t('Dernière mesure')} ${quandContact(vu)}` : t('Aucune mesure reçue');
    return;
  }
  const w = state.ssePower != null ? state.ssePower : kpis.puissance_instantanee;
  if (w == null) return;
  setKpi(power, `${Math.round(Number(w)).toLocaleString(_LOCALE)} W`);
  if (meta) meta.textContent = t('En direct, à la seconde');
}

function renderKpis() {
  const kpis = state.kpis;
  if (!kpis) return;
  state.kpisLive = true;
  const energy = document.getElementById('kpi-energy');
  const energyMeta = document.getElementById('kpi-energy-meta');
  const bill = document.getElementById('kpi-bill');
  const alerts = document.getElementById('kpi-alerts');
  renderPowerKpi();
  if (kpis.mode === 'vide') {
    setKpi(energy, t('Aucun capteur'), true);
    if (energyMeta) energyMeta.textContent = t('Installez un capteur pour la mesurer');
  } else if (kpis.consommation_jour_kwh == null) {
    setKpi(energy, t('Aucune mesure'), true);
    if (energyMeta) energyMeta.textContent = t('Rien reçu depuis minuit');
  } else {
    setKpi(energy, `${fmtKwhAuto(kpis.consommation_jour_kwh)} kWh`);
    if (energyMeta) energyMeta.textContent = t('Cumul depuis minuit');
  }
  // Une seule source pour la facture : le total de la carte dès qu'il est chargé, sinon le résumé
  if (bill) {
    const billVal = (state.facture && state.facture.total_fcfa_arrondi != null)
      ? Number(state.facture.total_fcfa_arrondi) : Number(kpis.facture_estimee_fcfa || 0);
    setKpi(bill, `${billVal.toLocaleString(_LOCALE)} FCFA`);
  }
  if (alerts) setKpi(alerts, `${kpis.alertes_actives != null ? kpis.alertes_actives : 0}`);
  const alertsMeta = document.getElementById('kpi-alerts-meta');
  if (alertsMeta) alertsMeta.textContent = kpis.alertes_actives ? t('Non lues, à consulter') : t('Rien à signaler');
  updateConnectionBadge();
  updateBillFraming();
  renderAlerts(); // compteur « non lues » du panneau = celui de l'indicateur
  cacheKpis();
}

/* Type de compteur effectif (référencé par le technicien) : prépayé / postpayé */
function meterType() {
  if (state.kpis && state.kpis.type_compteur) return state.kpis.type_compteur;
  if (state.facture && state.facture.type_compteur) return state.facture.type_compteur;
  if ((state.kpis && state.kpis.credit_prepaye) || (state.facture && state.facture.credit_prepaye)) return 'prepaye';
  return 'postpaye';
}

/* Période de facturation : postpayé = BIMESTRE (arrêté n° 1355) ; prépayé = le mois */
function periodeFacture() {
  const p = (state.facture && state.facture.periode) || (state.factureVide && state.factureVide.periode);
  return (p && p.type) ? p : { type: meterType() === 'prepaye' ? 'mois' : 'bimestre', libelle: '' };
}
function updateBillFraming() {
  const prepaid = meterType() === 'prepaye';
  const bimestre = periodeFacture().type === 'bimestre';
  const labelEl = document.getElementById('kpi-bill-label');
  const metaEl = document.getElementById('kpi-bill-meta');
  if (labelEl) setKpi(labelEl, prepaid ? t('Coût du mois, à ce jour')
    : (bimestre ? t('Facture du bimestre, à ce jour') : t('Facture du mois, à ce jour')));
  const per = periodeFacture();
  const titleEl = document.getElementById('forecast-title');
  const subEl = document.getElementById('forecast-sublabel');
  const detailTitleEl = document.getElementById('forecast-detail-title');
  if (titleEl) titleEl.textContent = prepaid ? t('Coût du mois') : (bimestre ? t('Facture du bimestre') : t('Facture du mois'));
  if (subEl) subEl.textContent = per.libelle ? `${t('FCFA à ce jour')} · ${per.libelle}` : t('FCFA à ce jour');
  if (detailTitleEl) detailTitleEl.textContent = prepaid ? t('Détail du mois') : (bimestre ? t('Détail du bimestre') : t('Détail du mois'));
  if (metaEl) {
    const amp = state.facture && state.facture.amperage ? ` ${state.facture.amperage} A` : '';
    setKpi(metaEl, `${prepaid ? t('Prépayé') : t('Postpayé')} · ${t('grille CIE')}${amp} · ${t('TVA incl.')}`);
  }
}

/* Badge d'en-tête : piloté par la FRAÎCHEUR réelle des mesures (avant le 19/10/2026 : « Données en direct » dès
   qu'un capteur existait, même muet depuis des jours) */
function updateConnectionBadge() {
  const badge = document.getElementById('connection-badge');
  if (!badge) return;
  const span = badge.querySelector('span');
  const set = (txt, cls) => {
    if (span && span.textContent !== txt) span.textContent = txt;
    badge.title = '';
    badge.classList.remove('live', 'demo', 'off');
    if (cls) badge.classList.add(cls);
  };
  if (!state.kpis && !state.sseVu) { set(t('Connexion…'), ''); return; }
  if (state.kpis && state.kpis.mode === 'vide') { set(t('Aucun capteur installé'), 'demo'); return; }
  if (boitierEnLigne()) { set(t('En direct'), 'live'); return; }
  const vu = dernierContact();
  // Court, pour tenir dans le badge : « Hors ligne depuis le 14 oct. » / « Hors ligne · vu il y a 3 h »
  const txt = !vu ? t('En attente du premier contact')
    : Date.now() - vu.getTime() < 86400000 ? `${t('Hors ligne')} · ${t('vu')} ${timeAgo(vu)}`
    : `${t('Hors ligne depuis le')} ${vu.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' })}`;
  set(txt, 'off');
  badge.title = vu ? `${t('Dernière mesure reçue')} ${quandContact(vu)}` : '';
}

function renderForecast() {
  const f = state.facture;
  const billEl = document.getElementById('forecast-bill');
  const dayEl = document.getElementById('forecast-day');
  const formulaEl = document.getElementById('forecast-formula');
  const progressEl = document.getElementById('forecast-progress');

  // 2 décimales : évite « 0 kWh × 86,92 = 2 F » (le kWh réel est 0,02), cohérence visuelle.
  const fmtKwh = v => Number(v).toLocaleString(_LOCALE, { maximumFractionDigits: 2 });
  const fmtPrix = v => Number(v).toLocaleString(_LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtF = v => Math.round(Number(v)).toLocaleString(_LOCALE);

  if (f && f.tranche1) {
    const amperage = esc(String(f.amperage != null ? f.amperage : ''));
    const kwhTotal = Number(f.tranche1.kwh) + (f.tranche2 ? Number(f.tranche2.kwh) : 0);
    // Total canonique = KPI (somme des lignes arrondies côté backend, champ total_fcfa_arrondi).
    const rT2 = (f.tranche2 && Number(f.tranche2.kwh) > 0) ? Math.round(Number(f.tranche2.fcfa)) : 0;
    const totalAffiche = (f.total_fcfa_arrondi != null) ? Number(f.total_fcfa_arrondi)
      : Math.round(Number(f.tranche1.fcfa)) + rT2 + Math.round(Number(f.prime_fixe_fcfa)) + Math.round(Number(f.taxes_fcfa));
    // ── Vue SIMPLE : 2 parts que tout le monde comprend, fournies par le backend et
    // qui somment EXACTEMENT au total (abonnement fixe + votre consommation). ──
    const abonnement = (f.abonnement_fixe_fcfa != null) ? Number(f.abonnement_fixe_fcfa)
      : Math.round(Number(f.prime_fixe_fcfa)) + Math.round(Number(f.taxe_fixe_fcfa || 0));
    const conso = (f.consommation_fcfa != null) ? Number(f.consommation_fcfa) : (totalAffiche - abonnement);

    const HOME = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></svg>';
    const BOLT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';
    const bucket = (ico, cls, lbl, sub, val) =>
      `<div class="fc-bucket ${cls}"><span class="fc-bucket-ico">${ico}</span>` +
      `<span class="fc-bucket-txt"><span class="fc-bucket-lbl">${lbl}</span><span class="fc-bucket-sub">${sub}</span></span>` +
      `<span class="fc-bucket-val">${val}</span></div>`;

    // Prépayé (arrêté n° 1355, art. 10 à 13) : un prix unique par kWh, prime fixe comprise,
    // aucune part fixe séparée. Postpayé : abonnement du bimestre + consommation.
    const prepaye = f.regime === 'prepaye';
    const bimestre = periodeFacture().type === 'bimestre';
    const simple = prepaye
      ? bucket(BOLT, 'fc-conso', t('Votre consommation'),
          `${esc(fmtKwh(kwhTotal))} kWh × ${esc(fmtPrix(f.prix_kwh_tout_compris || f.prix_moyen_kwh))} F · ${t('prix unique, tout compris')}`,
          `${esc(fmtF(totalAffiche))} F`)
      : bucket(HOME, 'fc-fixed', t('Abonnement fixe'),
          `${bimestre ? t('Dû chaque bimestre, même sans rien consommer ·') : t('Payé chaque mois, même sans rien consommer ·')} ${amperage} A`,
          `${esc(fmtF(abonnement))} F`) +
        bucket(BOLT, 'fc-conso', t('Votre consommation'),
          `${esc(fmtKwh(kwhTotal))} ${bimestre ? t('kWh utilisés ce bimestre') : t('kWh utilisés ce mois-ci')}`, `${esc(fmtF(conso))} F`);

    const totalRow =
      `<div class="fc-total-row"><span class="fc-total-lbl">${t('Total à ce jour')}<em>${t('TVA 18 % incluse')}</em></span>` +
      `<span class="fc-total-val">${esc(totalAffiche.toLocaleString(_LOCALE))} F</span></div>`;

    // Note pédagogique quand le fixe domine (début de mois / faible conso).
    const note = (abonnement > conso)
      ? `<p class="fc-note">${t('L’abonnement fixe est la plus grosse part tant que vous consommez peu. Il ne change pas&nbsp;: seule «&nbsp;votre consommation&nbsp;» augmente avec vos kWh.')}</p>`
      : '';

    const drow = (lbl, sub, val) =>
      `<div class="fc-drow"><span class="fc-drow-lbl">${t(lbl)}${sub ? `<em>${t(sub)}</em>` : ''}</span><span class="fc-drow-val">${val}</span></div>`;

    const taxesFixes = Math.round(Number(f.taxe_fixe_fcfa || 0));
    const taxesTotales = Math.round(Number(f.taxes_fcfa || 0));
    const taxesVariables = Math.max(0, taxesTotales - taxesFixes);

    // Libellés : les prix de l'arrêté sont TTC (TVA 18 % comprise), jamais « HT ».
    const detailRows = [];
    if (prepaye) {
      detailRows.push(drow('Énergie (prix unique, prime fixe comprise)', `${esc(fmtKwh(f.tranche1.kwh))} kWh × ${esc(fmtPrix(f.tranche1.prix))} F`, `${esc(fmtF(f.tranche1.fcfa))} F`));
      detailRows.push(drow('Taxes et redevances (sur la consommation)', `${esc(fmtPrix(f.taxes_par_kwh))} F/kWh`, `${esc(fmtF(taxesVariables))} F`));
    } else {
      const seuil = f.seuil_t1_kwh != null ? `${t('jusqu’à')} ${esc(fmtKwh(f.seuil_t1_kwh))} kWh · ` : '';
      detailRows.push(drow('Tranche 1', `${seuil}${esc(fmtKwh(f.tranche1.kwh))} kWh × ${esc(fmtPrix(f.tranche1.prix))} F`, `${esc(fmtF(f.tranche1.fcfa))} F`));
      if (f.tranche2 && Number(f.tranche2.kwh) > 0) {
        detailRows.push(drow('Tranche 2', `${esc(fmtKwh(f.tranche2.kwh))} kWh × ${esc(fmtPrix(f.tranche2.prix))} F`, `${esc(fmtF(f.tranche2.fcfa))} F`));
      }
      detailRows.push(drow('Taxes variables (sur la consommation)', `${esc(fmtPrix(f.taxes_par_kwh))} F/kWh`, `${esc(fmtF(taxesVariables))} F`));
      detailRows.push(drow('Prime fixe du bimestre (abonnement)', `${amperage} A`, `${esc(fmtF(f.prime_fixe_fcfa))} F`));
      detailRows.push(drow('Redevances fixes du bimestre', 'Électrification rurale, RTI', `${esc(fmtF(taxesFixes))} F`));
    }

    const detail =
      `<details class="fc-details"><summary>${t('Voir le détail officiel CIE')}</summary><div class="fc-drows">${detailRows.join('')}</div></details>`;

    // Réécrit seulement si le détail a changé : un « Voir le détail officiel » ouvert reste ouvert
    const html = simple + totalRow + note + detail;
    if (formulaEl && formulaEl.__html !== html) {
      const ouvert = !!formulaEl.querySelector('details[open]');
      formulaEl.innerHTML = html; formulaEl.__html = html; formulaEl.__vide = false;
      if (ouvert) { const d = formulaEl.querySelector('details'); if (d) d.open = true; }
    }
    if (billEl) billEl.textContent = totalAffiche.toLocaleString(_LOCALE);
  } else if (state.kpis && (state.kpis.mode === 'vide' || state.factureVide)) {
    const billValue = Number(state.kpis.facture_estimee_fcfa || 0);
    if (billEl) billEl.textContent = billValue.toLocaleString(_LOCALE);
    // Pas de détail par tranches (aucun capteur) : état vide honnête plutôt qu'un squelette qui pulse sans fin
    if (formulaEl && formulaEl.__vide !== true) { formulaEl.innerHTML = EMPTY_FORECAST_HTML; formulaEl.__vide = true; }
  }

  // Progression dans la période de facturation, donnée par le serveur (bimestre ou mois)
  const per = (f && f.periode) || (state.factureVide && state.factureVide.periode) || null;
  if (per && per.jours) {
    const fait = Math.min(Number(per.jours_ecoules), Number(per.jours));
    if (dayEl) dayEl.textContent = `${t('Jour')} ${fait} / ${per.jours}`;
    if (progressEl) progressEl.style.width = `${Math.round(fait / Number(per.jours) * 100)}%`;
    const bar = progressEl && progressEl.parentElement;
    if (bar) {
      bar.setAttribute('role', 'progressbar');
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', String(per.jours));
      bar.setAttribute('aria-valuenow', String(fait));
      bar.setAttribute('aria-label', `${t('Avancement de la période')} : ${t('jour')} ${fait} ${t('sur')} ${per.jours}`);
    }
  }

  renderCompare();
  renderCredit();
  renderFreshness();
}

/* Écart avec la MÊME DURÉE de la période d'avant (calculé par le serveur : le 19e jour du bimestre comparé aux 19
   premiers jours du bimestre d'avant). Rien n'est affiché quand la comparaison n'a pas de sens. */
function renderCompare() {
  const el = document.getElementById('forecast-compare');
  if (!el) return;
  const e = state.facture && state.facture.ecart;
  const pct = e && e.pct != null ? Math.round(Number(e.pct)) : null;
  if (pct === null) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.className = `compare-badge ${pct > 0 ? 'compare-up' : pct < 0 ? 'compare-dn' : 'compare-eq'}`;
  const bimestre = periodeFacture().type === 'bimestre';
  const sign = pct > 0 ? '↑ ' : pct < 0 ? '↓ ' : '';
  const num = `${pct > 0 ? '+' : ''}${pct.toLocaleString(_LOCALE)} %`;
  el.innerHTML = `${sign}<span class="cb-num">${esc(num)}</span> ${esc(bimestre ? t('vs même date du bimestre précédent') : t('vs même date du mois précédent'))}`;
  el.title = `${t('Comparé à la même durée de la période précédente')} (${e.libelle})` +
    (e.precedent_fcfa != null ? ` : ${Number(e.precedent_fcfa).toLocaleString(_LOCALE)} FCFA` : '');
}

/* Badge « À jour » de la carte facture : vrai seulement si le boîtier mesure ; sinon le montant est un minimum */
const FACTURE_INCOMPLETE_MS = 15 * 60 * 1000;
function renderFreshness() {
  const badge = document.getElementById('forecast-fresh');
  const note = document.getElementById('forecast-stale');
  const f = state.facture;
  if (!badge) return;
  if (!f) { badge.hidden = true; if (note) note.hidden = true; return; }
  const vu = dernierContact() || (f.dernier_contact ? new Date(f.dernier_contact) : null);
  const muet = !boitierEnLigne() && (!vu || Date.now() - vu.getTime() > FACTURE_INCOMPLETE_MS);
  badge.hidden = false;
  badge.textContent = muet ? t('Incomplet') : t('À jour');
  badge.className = muet ? 'rf-badge-ok rf-badge-warn' : 'rf-badge-ok';
  badge.title = muet ? t('Le boîtier ne mesure plus : la consommation depuis la dernière mesure n’est pas comptée.') : t('Calculé sur les mesures du moment.');
  if (note) {
    note.hidden = !muet;
    if (muet) note.textContent = vu
      ? `${t('Consommation non mesurée depuis')} ${quandContact(vu)} : ${t('ce montant est un minimum.')}`
      : t('Aucune mesure reçue : ce montant est l’abonnement seul.');
  }
}

/* Ligne crédit prépayé : visible UNIQUEMENT pour les compteurs prépayés (solde restant estimé et autonomie) */
function renderCredit() {
  const row = document.getElementById('forecast-credit');
  if (!row) return;
  const credit = (state.kpis && state.kpis.credit_prepaye)
    || (state.facture && state.facture.credit_prepaye) || null;
  if (!credit) { row.style.display = 'none'; return; } // postpayé ou inconnu

  const labelEl = document.getElementById('forecast-credit-label');
  const valEl = document.getElementById('forecast-credit-val');
  const subEl = document.getElementById('forecast-credit-sub');
  row.style.display = '';
  if (labelEl) labelEl.textContent = t('Crédit restant estimé');
  if (valEl) valEl.textContent = `${Math.round(Number(credit.restant_fcfa)).toLocaleString(_LOCALE)} FCFA`;
  if (subEl) {
    const jr = credit.jours_restants;
    const parJour = Number(credit.cout_jour_fcfa) > 0
      ? ` · ${Math.round(Number(credit.cout_jour_fcfa)).toLocaleString(_LOCALE)} FCFA/j` : '';
    // Date de fin prévue (habitudes + température) ; au-delà de 2 mois, une date précise n'aurait pas de sens
    const fin = credit.fin_estimee ? new Date(credit.fin_estimee) : null;
    let txt;
    if (jr == null) txt = `${t('Rechargé')} : ${Math.round(Number(credit.recharge_fcfa)).toLocaleString(_LOCALE)} FCFA`;
    else if (jr > 60) txt = `${t('plus de 2 mois d’autonomie')}${parJour}`;
    else if (fin) txt = `${t('fin prévue')} ${fin.toLocaleDateString(_LOCALE, { weekday: 'short', day: 'numeric', month: 'short' })}${parJour}`;
    else txt = `≈ ${jr} ${jr > 1 ? t('jours') : t('jour')} ${t('d’autonomie')}${parJour}`;
    subEl.textContent = txt;
  }
}

function loadSummary() {
  return fetchWithAuth('/api/analytics/summary/')
    .then(data => {
      state.kpis = data;
      renderKpis();
      renderForecast();
      renderIoT(); // « dernier contact » des mini-statistiques avant la 1re liste
      if (!chart && state.telemetryLoaded) renderChart(); // message d'état vide adapté (aucun capteur / aucune mesure)
    })
    .catch(err => console.error(err));
}

/* Facture officielle CIE (moteur tarifaire) : carte, indicateur, prix d'un kWh pour le graphe */
function loadFacture() {
  return fetchWithAuth('/api/analytics/facture/')
    .then(data => {
      if (!data || !data.tranche1) { // compte sans capteur : période seule, aucun montant inventé
        state.factureVide = data || null;
        renderForecast();
        return;
      }
      state.facture = data;
      // Prix STABLE d'un kWh tout compris (et non prix_moyen_kwh, qui explose en début de période)
      state.prixKwh = data.prix_kwh_tout_compris ? Number(data.prix_kwh_tout_compris)
        : (data.prix_moyen_kwh ? Number(data.prix_moyen_kwh) : null);
      renderKpis();
      renderForecast();
      renderChart(); // infobulles et pied : coût approché avec le vrai prix
    })
    .catch(err => console.error(err));
}

/* ════════════════════════ CONSEILS ════════════════════════ */
/* Les conseils viennent du serveur (/api/analytics/conseils/) : règles calculées sur vos vraies mesures (pic de
   puissance, crédit, tranche, nuit, hausse, chaleur annoncée…). Sans règle applicable, un conseil GÉNÉRAL du jour,
   alors marqué comme tel ; sans aucune mesure, la carte le dit au lieu d'inventer. */
function fillTip(c, ids) {
  const set = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
  set(ids.titre, c.titre);
  set(ids.texte, c.texte);
  const link = document.getElementById(ids.lien);
  if (link && c.lien) link.setAttribute('href', c.lien);
  if (ids.badge) set(ids.badge, c.mesure ? t('Selon vos mesures') : t('Conseil général'));
}
function renderConseils() {
  const d = state.conseils;
  if (!d) return;
  const [c1, c2] = d.conseils;
  if (c1) fillTip(c1, { titre: 'tip-head', texte: 'tip-note-txt', lien: 'tip-link', badge: 'tip-badge' });
  if (c2) fillTip(c2, { titre: 'tip-day-title', texte: 'tip-day-sub', lien: 'tip-day-link', badge: 'tip-day-badge' });
  const titre = document.getElementById('tip-day-title');
  if (titre && c2) titre.title = c2.titre;
}
function loadConseils() {
  return fetchWithAuth('/api/analytics/conseils/')
    .then(data => { state.conseils = data; renderConseils(); })
    .catch(err => console.error(err));
}

/* ════════════════════════ INITIALISATION ════════════════════════ */
/* N.B. : bloc utilisateur, déconnexion, cloche de notifications,
   badge d'alertes et navigation mobile sont gérés par client-shell.js. */
function init() {
  applyTheme();

  // Anti-flash : réaffiche instantanément les derniers KPI réels (cache local) au lieu
  // du squelette/tiret, en attendant les données live de cette session.
  restoreKpis();

  // Thème clair/sombre (géré par la page : le graphique doit être re-rendu)
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // Onglets de période
  document.querySelectorAll('#filter-pills .pill').forEach(btn => {
    btn.addEventListener('click', () => setFilter(btn.dataset.filter));
  });

  // Onglets capteurs (délégation : boutons re-rendus dynamiquement)
  const tabs = document.getElementById('sensor-tabs');
  if (tabs) tabs.addEventListener('click', e => {
    const btn = e.target.closest('.stab');
    if (btn) setSensor(btn.dataset.sensor);
  });

  // Répartition par appareil : période (Aujourd'hui / 7 j / 30 j / plage libre)
  const repPills = document.getElementById('rep-pills');
  const repRange = document.getElementById('rep-daterange');
  const repFromEl = document.getElementById('rep-from');
  const repToEl = document.getElementById('rep-to');
  const repHint = document.getElementById('rep-hint');
  if (repPills) repPills.addEventListener('click', e => {
    const btn = e.target.closest('.rep-pill');
    if (!btn) return;
    repPills.querySelectorAll('.rep-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (btn.dataset.rcustom) {
      // Ouvre la plage libre. Pré-remplit avec la fenêtre courante (jamais de futur).
      const today = new Date();
      const past = new Date(); past.setDate(today.getDate() - (state.repDays - 1));
      if (repFromEl) { if (!repFromEl.value) repFromEl.value = repISO(past); repFromEl.max = repISO(today); }
      if (repToEl) { if (!repToEl.value) repToEl.value = repISO(today); repToEl.max = repISO(today); }
      if (repRange) repRange.hidden = false;
    } else {
      if (repRange) repRange.hidden = true;
      if (repHint) repHint.textContent = '';
      state.repMode = 'preset';
      state.repDays = Number(btn.dataset.rday) || 7;
      loadRepartition();
    }
  });
  const repApply = document.getElementById('rep-apply');
  if (repApply) repApply.addEventListener('click', () => {
    // (dTo et non « t » : une variable « t » masquait la traduction t() et faisait planter ce bouton)
    const f = repFromEl ? repFromEl.value : '', dTo = repToEl ? repToEl.value : '';
    if (!f || !dTo) { if (repHint) repHint.textContent = t('Choisissez une date de début et de fin.'); return; }
    if (f > dTo) { if (repHint) repHint.textContent = t('La date de début doit précéder la date de fin.'); return; }
    if (repHint) repHint.textContent = '';
    state.repMode = 'custom'; state.repFrom = f; state.repTo = dTo;
    loadRepartition();
  });

  // Bouton "Comparer" : ouvre/ferme la barre + désactive si déjà actif
  const compareBtn = document.getElementById('compare-btn');
  if (compareBtn) {
    // Le bouton ouvre ou ferme la barre, sans jamais effacer la comparaison (c'est le rôle de « Désactiver ») :
    // avant le 19/10/2026, refermer la barre supprimait la courbe sans prévenir
    compareBtn.addEventListener('click', () => {
      state.compareBarOpen = !state.compareBarOpen;
      const bar = document.getElementById('compare-bar');
      if (bar) bar.style.display = state.compareBarOpen ? '' : 'none';
      compareBtn.classList.toggle('open', state.compareBarOpen);
      compareBtn.setAttribute('aria-expanded', String(state.compareBarOpen));
      if (state.compareBarOpen) {
        updateCompareSensors();
        updateCompareBtn();
        if (state.compareSensor === null) setCbarHint(t('Choisissez le capteur à comparer, puis la période.'));
      }
    });
  }

  // Barre de comparaison : choix du capteur, de la période, ou désactivation
  const compareBar = document.getElementById('compare-bar');
  if (compareBar) {
    compareBar.addEventListener('click', e => {
      const clr = e.target.closest('#compare-clear');
      const sOpt = e.target.closest('.copt[data-csensor]');
      const pOpt = e.target.closest('.copt[data-cperiod]');
      if (clr) clearCompare();
      else if (sOpt) setCompareSensor(sOpt.dataset.csensor);
      else if (pOpt) setComparePeriod(pOpt.dataset.cperiod);
    });
  }

  // Sélecteur de dates : bornes max = aujourd'hui + retrait de l'erreur à la saisie
  const todayStr = toDateStr(new Date());
  ['cbar-from', 'cbar-to'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.max = todayStr;
      el.addEventListener('input', () => {
        el.classList.remove('invalid');
        setCbarHint('');
        // Nouvelle date de début : la fin suit, pour une plage de la même durée que la vue (modifiable ensuite)
        if (id === 'cbar-from' && el.value && state.filter !== 'auj') {
          const n = state.filter === '30j' ? 30 : 7;
          const d = new Date(el.value + 'T00:00:00');
          d.setDate(d.getDate() + n - 1);
          const fin = repISO(d) > todayStr ? todayStr : repISO(d);
          const to = document.getElementById('cbar-to');
          if (to) { to.value = fin; to.classList.remove('invalid'); }
        }
      });
    }
  });

  // Bouton "Charger" du sélecteur de dates (capteur obligatoire + validation visible)
  const applyBtn = document.getElementById('cbar-apply');
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      // Règle métier : une plage ne se charge que pour un capteur choisi
      if (state.compareSensor === null) {
        setCbarHint(t('Choisissez d’abord le capteur à comparer.'), true);
        return;
      }
      const fromEl = document.getElementById('cbar-from');
      const toEl = document.getElementById('cbar-to');
      const from = fromEl ? fromEl.value : '';
      // Vue « Aujourd'hui » : un seul jour, comparé heure par heure
      const to = state.filter === 'auj' ? from : (toEl ? toEl.value : '');
      if (!from || !to || from > to) {
        if (fromEl) fromEl.classList.toggle('invalid', !from || (!!to && from > to));
        if (toEl) toEl.classList.toggle('invalid', !to || (!!from && from > to));
        setCbarHint(t('Choisissez deux dates valides (début ≤ fin).'), true);
        return;
      }
      fromEl.classList.remove('invalid');
      toEl.classList.remove('invalid');
      setCbarHint('');
      state.compareDates = { from, to };
      resetCompareData();
      updateCompareBtn();
      loadCompare();
    });
  }

  // Rendu initial : le graphique affiche l'état "chargement", le reste se peuple dès les données
  renderForecast();
  renderIoT();
  renderAlerts();
  renderRepartition();
  renderChart();

  loadSummary();
  loadFacture();
  brancherBoutonsRelais();
  loadSensors();
  loadTelemetry(false);
  loadAlerts();
  loadRepartition();
  loadConseils();

  // ── Rafraîchissement sans recharger la page ──
  // La puissance et l'état des appareils arrivent chaque seconde par le flux temps réel. Le reste (cumul du
  // jour, facture, graphe par heure ou par jour, alertes) change lentement : toutes les 30 s suffisent (avant le
  // 19/10/2026 : toutes les 10 s, plus un appel de l'historique des prévisions qui ne servait qu'à un badge).
  // EN PAUSE quand l'onglet est masqué, nettoyé au déchargement (pas de fuite).
  function refreshKpisLive() { loadSummary(); loadFacture(); }
  let liveTimers = [];
  function startLiveTimers() {
    stopLiveTimers();
    liveTimers.push(setInterval(loadAlerts, 30000));
    liveTimers.push(setInterval(refreshKpisLive, 30000));
    liveTimers.push(setInterval(() => loadTelemetry(false), 30000));
    liveTimers.push(setInterval(loadRepartition, 60000));
    liveTimers.push(setInterval(loadConseils, 300000));
    liveTimers.push(setInterval(() => { renderIoT(); updateConnectionBadge(); renderPowerKpi(); }, 5000)); // « vu il y a… »
  }
  function stopLiveTimers() { liveTimers.forEach(clearInterval); liveTimers = []; }
  startLiveTimers();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopLiveTimers();
    } else {
      // Retour sur l'onglet : on rafraîchit immédiatement puis on relance les timers.
      loadAlerts(); refreshKpisLive(); loadTelemetry(false);
      startLiveTimers();
      if (!_sseSource) startSSE();
    }
  });
  window.addEventListener('pagehide', stopLiveTimers);

  // ── Flux SSE temps réel, puissance instantanée sans rechargement de page ──
  startSSE();
}

/* ════════════════════════ SSE TEMPS RÉEL ════════════════════════ */
let _sseSource = null;
let _sseRetry = null;
let _sseDelai = 2000;

/* Coupure du flux (réseau, serveur redémarré, jeton expiré) : nouvel essai avec un délai croissant (2 s, 4 s… 60 s).
   On ne déconnecte la personne que sur un VRAI refus du jeton (authFetch : 401 puis échec du renouvellement) ;
   avant le 19/10/2026, une simple coupure réseau la renvoyait vers la page de connexion. */
function startSSE() {
  const token = localStorage.getItem('aoceda_access_token');
  if (!token || document.hidden) return;
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  clearTimeout(_sseRetry);

  _sseSource = new EventSource('/api/sensors/stream/?token=' + encodeURIComponent(token));
  _sseSource.onmessage = function (e) {
    _sseDelai = 2000;
    try {
      const payload = JSON.parse(e.data);
      if (payload.error) return;
      applySSEUpdate(payload.mesures || []);
    } catch (_) {}
  };
  _sseSource.onerror = function () {
    if (_sseSource) _sseSource.close();
    _sseSource = null;
    clearTimeout(_sseRetry);
    _sseRetry = setTimeout(function () {
      // Vérifie le jeton par une requête ordinaire : authFetch le renouvelle s'il a expiré
      window.AOCEDA.authFetch('/api/users/me/')
        .then(function (res) { if (res.ok) startSSE(); else throw new Error('HTTP ' + res.status); })
        .catch(function () { _sseDelai = Math.min(_sseDelai * 2, 60000); _sseSource = null; startSSE.planifier(); });
    }, _sseDelai);
  };
}
startSSE.planifier = function () {
  clearTimeout(_sseRetry);
  _sseRetry = setTimeout(startSSE, _sseDelai);
};
document.addEventListener('visibilitychange', () => {
  // Onglet caché : le flux est fermé (rien ne tourne pour rien côté serveur) ; rouvert au retour
  if (document.hidden && _sseSource) { _sseSource.close(); _sseSource = null; clearTimeout(_sseRetry); }
});

function applySSEUpdate(mesures) {
  state.sseVu = true;
  mesures.forEach(m => {
    const s = state.sensorsList.find(x => String(x.id) === String(m.id));
    if (s) {
      s.sseEtat = m.etat;
      s.etatCourant = m.etat;
      // derniereLecture = CONTACT matériel réel (en ligne/hors ligne).
      if (m.derniereLecture) s.derniereLecture = m.derniereLecture;
      // derniereMesure = dernière CONSOMMATION (info « activité »), distincte du contact.
      if (m.derniereMesure) s.derniereMesure = m.derniereMesure;
      if ('etatDepuis' in m) s.etatDepuis = m.etatDepuis;
      if ('coupureDemandee' in m) s.coupureDemandee = m.coupureDemandee;
      if ('coupureEffective' in m) s.coupureEffective = m.coupureEffective;
    }
  });
  // Un capteur inconnu de la liste (ajouté depuis) : relire la liste
  if (mesures.some(m => !state.sensorsList.find(x => String(x.id) === String(m.id)))) {
    if (!applySSEUpdate._relu || Date.now() - applySSEUpdate._relu > 10000) { applySSEUpdate._relu = Date.now(); loadSensors(); }
  }
  renderIoT();

  // Puissance du moment : somme des capteurs qui répondent (0 W pour un appareil éteint, envoyé tel quel par le
  // serveur) ; un capteur muet ne compte pas, et sans aucun capteur qui répond la puissance est « inconnue »
  const now = Date.now();
  const frais = mesures.filter(m => m.derniereLecture && now - new Date(m.derniereLecture).getTime() <= HORS_LIGNE_MS);
  state.ssePower = frais.length ? frais.reduce((s, m) => s + (Number(m.puissance) || 0), 0) : null;
  renderPowerKpi();
  updateConnectionBadge();
  renderFreshness();
  if (frais.length) cacheKpis();

  // Liste complète relue toutes les 60 s (noms modifiés ailleurs…) ; avant : toutes les 5 s, en plus du flux
  if (!applySSEUpdate._liste || now - applySSEUpdate._liste > 60000) {
    applySSEUpdate._liste = now;
    loadSensors();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
