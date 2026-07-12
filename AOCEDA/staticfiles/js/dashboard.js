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

/* ── Icônes thème (swap moon/sun) ── */
const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';

/* ── État global ── */
const state = {
  theme: localStorage.getItem('aoceda-theme') || 'light',
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
  prixMoyen: 87, // Tarif indicatif CIE (cf. Mémoire)
  ecart: null,
  dailyAvgForecast: null, // moyenne journalière projetée (kWh/j) depuis /api/previsions/
  /* Comparaison = un CAPTEUR (obligatoire) + une PÉRIODE (même période ou plage libre) */
  compareSensor: null,    // null | 'all' | '{id}', capteur comparé (null = pas de comparaison)
  comparePeriod: 'same',  // 'same' (suit les pills) | 'custom' (plage libre)
  prevTelemetry: [],
  telemetryLoaded: false,
  compareBarOpen: false,  // état de la barre de comparaison (tracé en state)
  compareLoaded: false,   // true quand le fetch de comparaison a abouti (succès ou échec)
  compareDates: null,     // {from, to} de la plage libre chargée
};
let chart = null;

/* ════════════════════════ THÈME ════════════════════════ */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  localStorage.setItem('aoceda-theme', state.theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = state.theme === 'light' ? ICON_MOON : ICON_SUN;
}

function toggleTheme() {
  state.theme = state.theme === 'light' ? 'dark' : 'light';
  applyTheme();
  renderChart();        // couleurs du graphique dépendantes du thème
  renderRepartition();  // idem pour le donut de répartition (palette data-viz + surface)
}

/* ════════════════════════ AGRÉGATION ════════════════════════ */
function aggregateTelemetry(sorted, filter) {
  if (!sorted || sorted.length === 0) return { labels: [], actual: [] };

  // Group by (capteur, créneau) pour sommer correctement quand plusieurs capteurs
  const bySensor = new Map(); // sensorId → Map(timeKey → vals[])
  const labelMap = new Map(); // timeKey → label

  sorted.forEach(m => {
    const sid = String(m.sensor_id || m.capteur_id || m.capteur || 'main');
    const d = new Date(m.timestamp);
    let key, label;
    if (filter === 'auj') {
      // Clé CHRONOLOGIQUE (date + heure) : sans la date, la fenêtre 24 h glissante
      // qui traverse minuit trierait « 23h » (veille) après « 02h » (tri lexical).
      const h = d.getHours();
      key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0') + 'T' + String(h).padStart(2, '0');
      label = h + 'h';
    } else {
      key = d.toISOString().slice(0, 10);
      label = d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'short' });
    }
    labelMap.set(key, label);
    if (!bySensor.has(sid)) bySensor.set(sid, new Map());
    const sg = bySensor.get(sid);
    if (!sg.has(key)) sg.set(key, []);
    const val = filter === 'auj'
      ? parseFloat(m.puissance) / 1000.0
      : parseFloat(m.energie || 0);
    if (!isNaN(val)) sg.get(key).push(val);
  });

  // Collect all time keys
  const allKeys = new Set();
  bySensor.forEach(sg => sg.forEach((_, k) => allKeys.add(k)));
  const sortedKeys = [...allKeys].sort();

  // 'auj' = puissance (kW) → MOYENNE du créneau ; '7j'/'30j' = énergie (kWh) → SOMME.
  // (Sommer les kWh est cohérent avec le backend Sum('energie') ; faire une moyenne
  //  effondrait chaque barre vers ~0, c'était le bug « 00 ».)
  const isEnergy = filter !== 'auj';
  const labels = sortedKeys.map(k => labelMap.get(k) || k);
  const actual = sortedKeys.map(k => {
    let total = 0;
    bySensor.forEach(sg => {
      const vals = sg.get(k);
      if (vals && vals.length) {
        const s = vals.reduce((a, b) => a + b, 0);
        // Énergie : somme des kWh du créneau (par capteur, puis somme inter-capteurs).
        // Puissance : moyenne intra-capteur, puis somme inter-capteurs.
        total += isEnergy ? s : s / vals.length;
      }
    });
    return Math.round(total * 100) / 100;
  });

  return { labels, actual };
}

/* Ré-échantillonne une série sur n points pour l'aligner sur la vue affichée :
   - plus longue → moyenne par segment (sous-échantillonnage) ;
   - plus courte → étirement par interpolation linéaire (sur-échantillonnage), pour
     que la courbe de comparaison couvre TOUT l'axe et ne soit pas collée à gauche. */
function resampleSeries(arr, n) {
  if (!arr || arr.length === 0 || n < 1 || arr.length === n) return arr;
  const out = [];
  if (arr.length > n) {
    for (let i = 0; i < n; i++) {
      const start = Math.floor(i * arr.length / n);
      const end = Math.max(start + 1, Math.floor((i + 1) * arr.length / n));
      const seg = arr.slice(start, end).filter(v => v !== null && v !== undefined && !isNaN(v));
      out.push(seg.length ? Math.round(seg.reduce((a, b) => a + b, 0) / seg.length * 100) / 100 : null);
    }
  } else {
    if (arr.length === 1) return Array(n).fill(arr[0]);
    for (let i = 0; i < n; i++) {
      const pos = i * (arr.length - 1) / (n - 1);
      const lo = Math.floor(pos), hi = Math.min(arr.length - 1, lo + 1);
      const a = arr[lo], b = arr[hi];
      if (a == null && b == null) out.push(null);
      else if (a == null) out.push(b);
      else if (b == null) out.push(a);
      else out.push(Math.round((a + (b - a) * (pos - lo)) * 100) / 100);
    }
  }
  return out;
}

/* ════════════════════════ GRAPHIQUE ════════════════════════ */
/* Lit un token CSS du :root (couleurs data-viz pilotées par le thème).
   Repli codé en dur si la variable n'est pas résolue (sécurité). */
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function getChartUnit() {
  return state.filter === 'auj' ? 'kW' : 'kWh';
}

function renderChart() {
  const canvas = document.getElementById('consumption-chart');
  const placeholder = document.getElementById('chart-placeholder');
  if (!canvas) return;

  if (!state.telemetryLoaded) {
    canvas.style.display = 'none';
    if (placeholder) placeholder.style.display = '';
    return;
  }
  if (placeholder) placeholder.style.display = 'none';
  canvas.style.display = '';

  // (Ne PAS détruire ici : on tente une mise à jour EN PLACE plus bas, rafraîchissement
  // fluide « temps réel » sans recréation ni clignotement. Destruction seulement si la
  // structure du graphe change réellement, cf. bloc de rendu.)
  const isDark = state.theme === 'dark';
  const unit = getChartUnit();

  let labels = [];
  let actual = [];
  let forecast = null; // rempli ci-dessous si prévision disponible

  const telemetry = state.telemetry;
  if (telemetry && telemetry.length > 0) {
    const sorted = [...telemetry].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    const agg = aggregateTelemetry(sorted, state.filter);
    labels = agg.labels;
    actual = agg.actual;
  } else {
    // Aucune mesure sur la période : état vide HONNÊTE (jamais de courbe fabriquée)
    if (chart) { chart.destroy(); chart = null; }
    canvas.style.display = 'none';
    if (placeholder) {
      placeholder.style.display = '';
      const span = placeholder.querySelector('span');
      if (span) span.textContent = t('Aucune donnée pour cette période.');
    }
    // Aucune courbe tracée → on masque TOUTES les légendes (sinon un chip
    // « Prévision »/« Comparaison » d'une période précédente resterait affiché).
    ['legend-main', 'legend-forecast', 'legend-prev'].forEach(id => {
      const l = document.getElementById(id);
      if (l) l.style.display = 'none';
    });
    // Vider le pied de page : sans ce reset, la valeur « 0.06 kW / X FCFA » d'un
    // capteur/période précédent resterait affichée sous un graphe vide (trompeur).
    const cfKwh = document.getElementById('cf-kwh');
    if (cfKwh) cfKwh.textContent = (getChartUnit() === 'kW' ? '0.00 kW' : '0.0 kWh');
    const cfFcfa = document.getElementById('cf-fcfa');
    if (cfFcfa) cfFcfa.textContent = '0 FCFA';
    const cfTrend = document.getElementById('cf-trend');
    if (cfTrend) { cfTrend.textContent = 'aucune donnée'; cfTrend.className = 'cf-trend neu'; }
    return;
  }

  /* Couleurs issues des tokens data-viz (--dv-*) : suivent le thème clair/sombre */
  const dvMain = cssVar('--dv-2', isDark ? '#3FB3A4' : '#1B7A6E');     // série principale (teal)
  const dvCompare = cssVar('--dv-4', isDark ? '#C79B66' : '#8A5E2B');  // comparaison (sable)
  const dvForecast = cssVar('--dv-dash', '#CDA46A');                   // prévision (pointillé)
  const surface = cssVar('--bg-s', isDark ? '#1E1A13' : '#FFFFFF');
  const fillTop = isDark ? 'rgba(63,179,164,0.22)' : 'rgba(27,122,110,0.13)';
  const fillBot = isDark ? 'rgba(63,179,164,0)' : 'rgba(27,122,110,0)';

  const gColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(35,27,16,0.05)';
  const lColor = cssVar('--tx-s', isDark ? '#C2B19A' : '#6B5A45');
  const mainLabel = `${t('Consommation')} (${unit})`;

  // Début d'heure/de période : un seul créneau existe encore. Un point isolé avec
  // pointRadius=2 est quasi invisible ; on l'agrandit pour qu'une consommation réelle
  // se voie tout de suite (sinon le graphe paraît vide alors qu'il y a bien 1 mesure).
  const validVals = actual.filter(v => v !== null && v !== undefined && !isNaN(v));
  const nbPoints = validVals.length;
  const ptRadius = nbPoints <= 2 ? 5 : 2;

  // Marge en haut de l'axe Y : avec beginAtZero, Chart.js calait y-max EXACTEMENT sur
  // la valeur max → une courbe plate basse (ex. 0,06 kW) collait à la bordure du haut
  // et devenait invisible. On suggère 20 % de marge (min plancher pour ne pas écraser
  // une valeur minuscule) afin que la ligne « respire » et se lise toujours.
  const maxVal = nbPoints ? Math.max(...validVals) : 0;
  const suggestedMax = maxVal > 0 ? maxVal * 1.2 : (unit === 'kW' ? 0.1 : 1);

  const datasets = [{
    label: mainLabel, data: actual,
    borderColor: dvMain, borderWidth: 2.5, order: 1,
    backgroundColor: function(context) {
      const ch = context.chart;
      const area = ch.chartArea;
      if (!area) return fillTop;
      const g = ch.ctx.createLinearGradient(0, area.top, 0, area.bottom);
      g.addColorStop(0, fillTop);
      g.addColorStop(1, fillBot);
      return g;
    },
    fill: true, tension: .42, pointRadius: ptRadius, pointHoverRadius: 6,
    pointBackgroundColor: dvMain, pointBorderColor: surface, pointBorderWidth: 2,
    spanGaps: true
  }];

  let compareDrawn = false;
  if (state.compareSensor !== null) {
    let prevActual = null;

    if (state.prevTelemetry.length > 0) {
      const ps = [...state.prevTelemetry].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      prevActual = aggregateTelemetry(ps, state.filter).actual;
    } else if (state.compareLoaded) {
      // Le fetch a abouti mais le capteur/période comparé n'a aucune donnée :
      // on n'affiche JAMAIS une courbe de comparaison fabriquée.
      setCbarHint('Aucune donnée pour le capteur/la période de comparaison choisi.', true);
    }
    // Sinon (plage libre sans dates chargées, ou fetch en cours) : aucune courbe

    if (prevActual && prevActual.length) {
      // Ré-échantillonnage : une plage plus longue que la vue est moyennée
      // sur le même nombre de points (jamais de troncature silencieuse)
      prevActual = resampleSeries(prevActual, labels.length);
      datasets.push({
        label: getCompareName(), data: prevActual,
        borderColor: dvCompare,
        borderWidth: 2, borderDash: [5, 3],
        backgroundColor: 'transparent',
        fill: false, tension: .42, pointRadius: 0, pointHoverRadius: 5,
        pointBackgroundColor: dvCompare,
        spanGaps: true, order: 2
      });
      compareDrawn = true;
    }
  }

  // Ligne de prévision : moyenne journalière projetée (kWh/j), uniquement
  // pour les vues kWh (pas kW) et si la donnée est disponible.
  if (state.dailyAvgForecast && unit === 'kWh' && labels.length > 0) {
    forecast = Array(labels.length).fill(
      Math.round(state.dailyAvgForecast * 100) / 100
    );
  }
  if (forecast) {
    datasets.push({
      label: `${t('Prévision')} (${unit})`, data: forecast,
      borderColor: dvForecast, borderDash: [5, 4], backgroundColor: 'transparent',
      fill: false, tension: 0, pointRadius: 0, pointHoverRadius: 4,
      pointBackgroundColor: dvForecast, order: 0
    });
  }

  // Légendes + pied : identiques quel que soit le mode (création ou maj en place).
  const applyLegends = () => {
    const legendMain = document.getElementById('legend-main');
    if (legendMain) legendMain.style.display = compareDrawn ? '' : 'none';
    const legendForecast = document.getElementById('legend-forecast');
    if (legendForecast) legendForecast.style.display = forecast ? '' : 'none';
    const legendPrev = document.getElementById('legend-prev');
    if (legendPrev) {
      legendPrev.style.display = compareDrawn ? '' : 'none';
      const lpLbl = legendPrev.querySelector('span');
      if (lpLbl && compareDrawn) lpLbl.textContent = getCompareName();
    }
    updateChartFooter();
  };

  // Signature de STRUCTURE : mêmes séries + mêmes points + même unité → on peut mettre
  // à jour les données du graphe existant (transition animée fluide) au lieu de le
  // recréer (qui le fait clignoter/re-animer depuis zéro à chaque rafraîchissement).
  const sig = `line|${datasets.length}|${labels.length}|${unit}`;
  if (chart && chart.__aocedaSig === sig) {
    chart.data.labels = labels;
    datasets.forEach((ds, i) => { if (chart.data.datasets[i]) Object.assign(chart.data.datasets[i], ds); });
    // Réappliquer la marge Y en place (sinon un rafraîchissement temps réel garderait
    // l'ancien plafond et pourrait recoller la courbe au bord du haut).
    if (chart.options && chart.options.scales && chart.options.scales.y) {
      chart.options.scales.y.suggestedMax = suggestedMax;
    }
    chart.update();          // Chart.js anime la transition des valeurs → « temps réel » visible
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
            title: items => items.length ? items[0].label : '',
            label: ctx => {
              if (ctx.raw === null || ctx.raw === undefined) return null;
              const lbl = ctx.dataset.label || '';
              if (!ctx.dataset.borderDash) {
                // Dataset principal : montrer kWh/kW + FCFA (seulement pour l'énergie)
                if (unit === 'kWh') {
                  const fcfa = Math.round(ctx.raw * state.prixMoyen);
                  return [`${lbl} : ${ctx.raw} ${unit}`, '≈ ' + fcfa.toLocaleString(_LOCALE) + ' FCFA'];
                }
                return `${lbl} : ${ctx.raw} ${unit}`;
              }
              return `${lbl} : ${ctx.raw} ${unit}`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true, suggestedMax, grid: { color: gColor }, border: { display: false },
          ticks: {
            font: { family: 'Spline Sans Mono', size: 11 }, color: lColor,
            callback: v => `${v} ${unit}`,
            maxTicksLimit: 6
          }
        },
        x: {
          grid: { display: false }, border: { display: false },
          ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lColor, maxTicksLimit: 12 }
        }
      }
    }
  });
  chart.__aocedaSig = sig;
  applyLegends();
}

function updateChartFooter() {
  const data = chart && chart.data && chart.data.datasets && chart.data.datasets[0]
    ? chart.data.datasets[0].data : null;
  const kwhEl = document.getElementById('cf-kwh');
  const lblEl = document.getElementById('cf-kwh-lbl');
  const trendEl = document.getElementById('cf-trend');
  const fcfaEl = document.getElementById('cf-fcfa');
  if (!kwhEl || !data) return;

  const nums = data.filter(v => v !== null && v !== undefined).map(Number).filter(n => !isNaN(n));

  if (state.filter === 'auj') {
    // Données en kW (puissance) → afficher la puissance moyenne, pas un total kWh
    const avg = nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
    kwhEl.textContent = avg.toFixed(2) + ' kW';
    if (lblEl) lblEl.textContent = _LOCALE === 'en-GB' ? "Avg. power, Today" : "Puissance moy., Aujourd'hui";
    if (fcfaEl) {
      const kwhReel = (state.telemetry || []).reduce((s, m) => s + (parseFloat(m.energie) || 0), 0);
      fcfaEl.textContent = Math.round(kwhReel * state.prixMoyen).toLocaleString(_LOCALE) + ' FCFA';
    }
  } else {
    const total = nums.reduce((a, b) => a + b, 0);
    kwhEl.textContent = total.toFixed(1) + ' kWh';
    if (fcfaEl) fcfaEl.textContent = Math.round(total * state.prixMoyen).toLocaleString(_LOCALE) + ' FCFA';
    const periodLabel = _LOCALE === 'en-GB'
      ? { '7j': 'Last 7 days', '30j': 'Last 30 days' }[state.filter] || 'Period'
      : { '7j': 'Ces 7 jours', '30j': 'Ces 30 jours' }[state.filter] || 'Période';
    if (lblEl) lblEl.textContent = periodLabel;
  }
  if (trendEl) { trendEl.textContent = _LOCALE === 'en-GB' ? 'selected period' : 'période sélectionnée'; trendEl.className = 'cf-trend neu'; }
}

function loadTelemetry() {
  const periodMap = { 'auj': 'day', '7j': 'week', '30j': 'month' };
  const apiPeriod = periodMap[state.filter] || 'week';
  // Série AGRÉGÉE côté serveur (buckets heure/jour) au lieu des mesures brutes :
  // ~0,3 s / quelques Ko au lieu de ~7 s / 2,4 Mo.
  let url = `/api/mesures/serie/?period=${apiPeriod}`;
  if (state.sensor !== 'all') url += `&sensor_id=${state.sensor}`;
  fetchWithAuth(url)
    .then(data => {
      state.telemetry = window.AOCEDA.asList(data);
      state.telemetryLoaded = true;
      // Re-charger les données de comparaison avec les nouveaux paramètres
      if (state.compareSensor !== null) {
        if (state.comparePeriod === 'same') {
          // La période des pills a pu changer → recharger le capteur comparé
          loadSensorCompare(state.compareSensor);
        } else if (state.compareDates) {
          // Plage déjà chargée : re-fetch (le ré-échantillonnage suivra la nouvelle vue)
          loadCompareByDates(state.compareDates.from, state.compareDates.to);
        } else {
          renderChart();
        }
      } else {
        renderChart();
      }
    })
    .catch(err => {
      state.telemetryLoaded = true;
      renderChart();
      console.error(err);
    });
}

function toDateStr(d) {
  return d.toISOString().slice(0, 10);
}

function fmtShortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return iso;
  return d.toLocaleDateString(_LOCALE, { day: '2-digit', month: '2-digit', year: '2-digit' });
}

/* Nom lisible de la comparaison active : « Capteur · plage » (bouton, légende, tooltip) */
function getCompareName() {
  if (state.compareSensor === null) return '';
  let name;
  if (state.compareSensor === 'all') {
    name = t('Tous les capteurs');
  } else {
    const s = state.sensorsList.find(x => String(x.id) === state.compareSensor);
    name = s ? s.nom : t('Capteur');
  }
  if (state.comparePeriod === 'custom') {
    name += state.compareDates
      ? ` · ${fmtShortDate(state.compareDates.from)} → ${fmtShortDate(state.compareDates.to)}`
      : ' · ' + t('plage à choisir');
  }
  return name;
}

function showDateRow(show) {
  const row = document.getElementById('cbar-dates');
  if (row) row.style.display = show ? '' : 'none';
}

function loadCompareByDates(from, to) {
  if (!from || !to) { state.prevTelemetry = []; renderChart(); return; }
  state.compareDates = { from, to };
  let url = `/api/mesures/serie/?date_from=${from}&date_to=${to}`;
  // La plage concerne le CAPTEUR COMPARÉ choisi dans la barre (pas la vue principale)
  if (state.compareSensor && state.compareSensor !== 'all') url += `&sensor_id=${state.compareSensor}`;
  fetchWithAuth(url)
    .then(data => { state.prevTelemetry = window.AOCEDA.asList(data); })
    .catch(() => { state.prevTelemetry = []; })
    .finally(() => { state.compareLoaded = true; updateCompareBtn(); renderChart(); });
}

function loadSensorCompare(sensorId) {
  const periodMap = { 'auj': 'day', '7j': 'week', '30j': 'month' };
  let url = `/api/mesures/serie/?period=${periodMap[state.filter] || 'week'}`;
  if (sensorId !== 'all') url += `&sensor_id=${sensorId}`;  // 'sensor-all' = pas de filtre → somme de tous
  fetchWithAuth(url)
    .then(data => { state.prevTelemetry = window.AOCEDA.asList(data); })
    .catch(() => { state.prevTelemetry = []; })
    .finally(() => { state.compareLoaded = true; renderChart(); });
}

function setCbarHint(msg, isErr) {
  const el = document.getElementById('cbar-hint');
  if (!el) return;
  el.textContent = msg || t('La plage est ajustée pour s’aligner sur la courbe affichée.');
  el.classList.toggle('err', !!isErr);
}

/* Étape 1, choix du capteur à comparer (obligatoire pour toute comparaison) */
function setCompareSensor(id) {
  if (state.compareSensor === id) {
    // Re-clic sur le même capteur → désélection complète
    state.compareSensor = null;
    state.prevTelemetry = [];
    state.compareLoaded = false;
    updateCompareBtn();
    setCbarHint('');
    renderChart();
    return;
  }
  state.compareSensor = id;
  state.prevTelemetry = [];
  state.compareLoaded = false;

  // Anti-doublon : même capteur que la vue + même période = courbes identiques
  // → on bascule automatiquement en plage libre
  if (id === state.sensor && state.comparePeriod === 'same') {
    state.comparePeriod = 'custom';
    state.compareDates = null;
    updateCompareBtn();
    showDateRow(true);
    setCbarHint(t('Même capteur que la vue, choisissez une plage de dates différente.'));
    renderChart();
    return;
  }

  updateCompareBtn();
  if (state.comparePeriod === 'same') {
    setCbarHint('');
    if (state.telemetryLoaded) loadSensorCompare(id);
    else renderChart();
  } else {
    // Plage libre déjà sélectionnée : recharger si des dates valides sont saisies
    const from = document.getElementById('cbar-from')?.value || '';
    const to = document.getElementById('cbar-to')?.value || '';
    if (from && to && from <= to && state.telemetryLoaded) {
      loadCompareByDates(from, to);
    } else {
      setCbarHint(t('Saisissez la plage puis cliquez « Charger ».'));
      renderChart();
    }
  }
}

/* Étape 2, choix de la période de comparaison ('same' suit les pills, 'custom' = plage) */
function setComparePeriod(p) {
  if (state.comparePeriod === p) return; // pas un toggle : un des deux modes est toujours actif
  const sameSource = state.compareSensor !== null && state.compareSensor === state.sensor;
  if (p === 'same' && sameSource) {
    setCbarHint(t('Impossible : même capteur que la vue sur la même période (courbes identiques).'), true);
    return;
  }
  state.comparePeriod = p;
  state.prevTelemetry = [];
  state.compareLoaded = false;
  state.compareDates = null;
  updateCompareBtn();
  setCbarHint('');

  if (p === 'same') {
    showDateRow(false);
    if (state.compareSensor !== null && state.telemetryLoaded) loadSensorCompare(state.compareSensor);
    else renderChart();
  } else {
    showDateRow(true);
    const from = document.getElementById('cbar-from')?.value || '';
    const to = document.getElementById('cbar-to')?.value || '';
    if (state.compareSensor !== null && from && to && from <= to && state.telemetryLoaded) {
      loadCompareByDates(from, to);
    } else {
      if (state.compareSensor === null) setCbarHint(t('Choisissez d’abord le capteur à comparer.'));
      renderChart();
    }
  }
}

function clearCompare() {
  state.compareSensor = null;
  state.comparePeriod = 'same';
  state.prevTelemetry = [];
  state.compareLoaded = false;
  state.compareDates = null;
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
    b.classList.toggle('active', b.dataset.csensor === state.compareSensor);
  });
  document.querySelectorAll('.copt[data-cperiod]').forEach(b => {
    b.classList.toggle('active', b.dataset.cperiod === state.comparePeriod);
  });
  if (lbl) lbl.textContent = state.compareSensor !== null ? getCompareName() : 'Comparer';
}

function updateCompareSensors() {
  const container = document.getElementById('copt-sensors');
  const sep = document.getElementById('copt-sep');
  if (!container) return;

  if (!state.sensorsList.length) {
    container.innerHTML = '';
    if (sep) sep.style.display = 'none';
    return;
  }

  const icoSensor = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`;
  const icoAll = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>`;

  const btnParts = [];

  // « Tous les capteurs » seulement s'il y a ≥ 2 capteurs (sinon ≡ l'unique capteur)
  if (state.sensorsList.length >= 2) {
    const isActive = state.compareSensor === 'all';
    btnParts.push(`<button class="copt${isActive ? ' active' : ''}" data-csensor="all">${icoAll}${t('Tous les capteurs')}</button>`);
  }

  // Tous les capteurs individuels, y compris celui de la vue
  // (se comparer à soi-même est autorisé, mais uniquement sur une plage différente)
  state.sensorsList.forEach(s => {
    const isActive = state.compareSensor === String(s.id);
    btnParts.push(`<button class="copt${isActive ? ' active' : ''}" data-csensor="${esc(s.id)}">${icoSensor}${esc(s.nom)}</button>`);
  });

  if (sep) sep.style.display = '';
  container.innerHTML = btnParts.join('');
}

/* ── Onglets de période ── */
function setFilter(f) {
  state.filter = f;
  state.telemetryLoaded = false;
  state.prevTelemetry = [];
  state.compareLoaded = false; // évite de dessiner un repli périmé pendant le rechargement
  document.querySelectorAll('#filter-pills .pill').forEach(b => {
    const on = b.dataset.filter === f;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  renderChart(); // affiche le chargement
  loadTelemetry();
}

/* ── Onglets capteurs ── */
function renderSensorTabs() {
  const wrap = document.getElementById('sensor-tabs');
  if (!wrap) return;
  let html = `<button class="stab${state.sensor === 'all' ? ' active' : ''}" data-sensor="all">${t('Tous les capteurs')}</button>`;
  state.sensorsList.forEach(s => {
    html += `<button class="stab${state.sensor === String(s.id) ? ' active' : ''}" data-sensor="${esc(s.id)}">${esc(s.nom)}</button>`;
  });
  wrap.innerHTML = html;
}

function setSensor(id) {
  state.sensor = id;
  state.telemetryLoaded = false;
  state.prevTelemetry = [];
  state.compareLoaded = false;
  // Conflit : la nouvelle vue principale EST le capteur comparé sur la même période
  // → bascule automatique en plage libre (la comparaison reste valable à dates différentes)
  if (state.compareSensor === id && state.comparePeriod === 'same') {
    state.comparePeriod = 'custom';
    state.compareDates = null;
    updateCompareBtn();
    showDateRow(true);
    if (state.compareBarOpen) setCbarHint('Même capteur que la vue, choisissez une plage de dates différente.');
  }
  renderSensorTabs();
  updateCompareSensors();
  renderChart();
  loadTelemetry();
}

/* ════════════════════════ STATUT IoT ════════════════════════ */
function renderIoT() {
  const wrap = document.getElementById('sensor-list');
  if (!wrap) return;
  const list = state.sensorsList;

  // Mini-stat « capteurs en ligne » : compte les capteurs RÉELLEMENT joignables
  // (dernier CONTACT < 120 s). derniereLecture = contact matériel (mis à jour à chaque
  // lecture, même éteint), un appareil éteint mais branché reste « en ligne ».
  const activeEl = document.getElementById('iot-active');
  if (activeEl) {
    const enLigne = list.filter(s => s.derniereLecture &&
      (Date.now() - new Date(s.derniereLecture).getTime()) <= 120000).length;
    // Pas de tiret : « 0 » honnête s'il n'y a aucun capteur, sinon « en ligne / total ».
    activeEl.textContent = list.length ? `${enLigne}/${list.length}` : '0';
  }

  if (list.length === 0) {
    wrap.innerHTML = EMPTY_SENSORS_HTML;
    return;
  }

  wrap.innerHTML = list.map(s => {
    // En ligne / hors ligne = dernier CONTACT (derniereLecture). Un capteur muet
    // depuis > 2 min est hors ligne ; sinon il est joignable (allumé OU éteint).
    const ageMs = s.derniereLecture ? (Date.now() - new Date(s.derniereLecture).getTime()) : Infinity;
    const stale = ageMs > 120000;
    // État instantané réel (persisté côté serveur) : 'ON' consomme, 'OFF' éteint.
    const etat = s.sseEtat || s.etatCourant;
    // Horodatage de la dernière CONSOMMATION (≠ contact) pour l'info « activité ».
    const mesure = s.derniereMesure ? new Date(s.derniereMesure) : null;
    let indicatorClass, statusText, statusColor, lastStr;
    if (stale) {
      // Depuis combien de temps le capteur ne répond plus.
      indicatorClass = 's-err'; statusText = t('Hors ligne'); statusColor = 'var(--err)';
      lastStr = s.derniereLecture ? (window.AOCEDA_LANG === 'en' ? `Seen ${timeAgo(new Date(s.derniereLecture))}` : `Vu ${timeAgo(new Date(s.derniereLecture))}`) : t('Jamais vu');
    } else if (etat === 'ON') {
      indicatorClass = 's-ok'; statusText = t('Actif · En ligne'); statusColor = 'var(--ok)';
      lastStr = mesure ? timeAgo(mesure) : t('à l’instant');
    } else if (etat === 'OFF') {
      // Joignable mais l'appareil ne consomme pas : on montre la dernière activité.
      indicatorClass = 's-idle'; statusText = t('En ligne · éteint'); statusColor = 'var(--tx-m)';
      lastStr = mesure ? (window.AOCEDA_LANG === 'en' ? `Last cons. ${timeAgo(mesure)}` : `Dernière conso. ${timeAgo(mesure)}`) : t('Aucune consommation');
    } else if (s.actif) {
      indicatorClass = 's-ok'; statusText = t('En ligne'); statusColor = 'var(--ok)';
      lastStr = mesure ? timeAgo(mesure) : t('En attente');
    } else {
      indicatorClass = 's-err'; statusText = t('Hors ligne'); statusColor = 'var(--err)';
      lastStr = t('Inactif');
    }
    return `<div class="sensor-row">
      <div class="sensor-indicator ${indicatorClass}"></div>
      <div class="sensor-name">${esc(s.nom)}</div>
      <div class="sensor-meta">
        <div style="color:${statusColor};font-weight:600">${statusText}</div>
        <div class="sm-time">${esc(lastStr)}</div>
      </div>
    </div>`;
  }).join('');
}

function loadSensors() {
  fetchWithAuth('/api/sensors/')
    .then(data => {
      const newList = window.AOCEDA.asList(data);
      newList.forEach(s => {
        const existing = state.sensorsList.find(x => String(x.id) === String(s.id));
        // Le SSE (temps réel) fait autorité s'il a déjà parlé ; sinon on amorce
        // l'état ON/OFF avec la valeur persistée renvoyée par le REST (etatCourant).
        if (existing && existing.sseEtat) s.sseEtat = existing.sseEtat;
        else if (s.etatCourant) s.sseEtat = s.etatCourant;
        // derniereMesure n'existe que via le SSE : on le préserve entre deux reloads.
        if (existing && existing.derniereMesure) s.derniereMesure = existing.derniereMesure;
      });
      state.sensorsList = newList;
      renderSensorTabs();
      renderIoT();
      updateCompareSensors();
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

/* Libellé lisible du type d'alerte (le code brut DÉPASSEMENT_SEUIL est technique). */
const ALERT_TYPE_LABELS = {
  'DEPASSEMENT_SEUIL': 'Dépassement de seuil',
  'CONSOMMATION_NOCTURNE': 'Consommation nocturne',
  'CREDIT_BAS': 'Crédit bas',
};
function alertTypeLabel(t) {
  const key = String(t || '').toUpperCase().replace(/ /g, '_');
  return ALERT_TYPE_LABELS[key] || String(t || '').replace(/_/g, ' ');
}

function renderAlerts() {
  const wrap = document.getElementById('alerts-list');
  if (!wrap) return;
  const list = state.alerts;

  // Nombre TOTAL d'alertes actives (non lues), depuis le résumé, PAS la sous-liste
  // limitée à 3 (sinon le compteur du panneau plafonnait à 3, ≠ KPI « Alertes actives »).
  const activeCount = (state.kpis && state.kpis.alertes_actives != null)
    ? state.kpis.alertes_actives
    : list.filter(a => !a.lue).length;
  const countEl = document.getElementById('alerts-count');
  if (countEl) {
    const activeWord = activeCount > 1 ? t('actives') : t('active');
    countEl.textContent = `${activeCount} ${activeWord}`;
  }

  if (list.length === 0) {
    wrap.innerHTML = EMPTY_ALERTS_HTML;
    return;
  }

  wrap.innerHTML = list.map(a => {
    const sev = a.sévérité || a.severity || 'Avertissement';
    const st = SEV_STYLE[sev] || SEV_STYLE['Avertissement'];
    const created = new Date(a.createdAt);
    const timeStr = created.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });

    return `<div class="alert-item" style="opacity:${a.lue ? .6 : 1}">
      <div class="alert-ico" style="background:${st.bg};color:${st.c}">${st.ico}</div>
      <div style="flex:1;min-width:0">
        <div class="alert-head">
          <span class="alert-type">${esc(t(alertTypeLabel(a.type)))}</span>
          <span class="alert-badge" style="background:${st.bg};color:${st.c}">${esc(t(sev))}</span>
        </div>
        <div class="alert-msg">${esc(a.message)}</div>
        <div class="alert-foot">
          <span class="alert-time">${esc(timeAgo(created))} · ${esc(timeStr)}</span>
          ${!a.lue
            ? `<button class="dismiss-btn" data-id="${esc(a.id)}">✓ ${t('Marquer lu')}</button>`
            : '<span class="alert-read">✓ ' + t('Lu') + '</span>'}
        </div>
      </div>
    </div>`;
  }).join('');
}

function dismissAlert(id) {
  fetchWithAuth(`/api/alertes/${id}/lire/`, { method: 'PATCH' })
    .then(() => {
      state.alerts = state.alerts.map(x => String(x.id) === String(id) ? { ...x, lue: true } : x);
      renderAlerts();
    })
    .catch(err => console.error(err));
}

function loadAlerts() {
  fetchWithAuth('/api/alertes/')
    .then(data => {
      state.alerts = window.AOCEDA.asList(data).slice(0, 3);
      renderAlerts();
    })
    .catch(err => console.error(err));
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
function repISO(dt) {                           // Date → 'YYYY-MM-DD' (local)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}
function repPeriodLabel() {
  if (state.repMode === 'custom' && state.repFrom && state.repTo) {
    const f = repFmtDate(state.repFrom), t = repFmtDate(state.repTo);
    return f === t ? f : `${f} → ${t}`;
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
  const surface = cssVar('--bg-s', isDark ? '#0A0A0A' : '#FFFFFF');
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
                  return ` ${Number(c.kwh).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh · ${c.pct} %`;
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
    const tot = Number(data.total_kwh || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
    center.innerHTML = `<span class="rc-val">${tot}</span><span class="rc-unit">kWh</span><span class="rc-lbl">total</span>`;
  }

  // ── Légende détaillée : nom + kWh + % + pic + alerte disjoncteur ──
  const legend = document.getElementById('rep-legend');
  if (legend) {
    legend.innerHTML = caps.map((c, i) => {
      const col = colors[i];
      const over = capW > 0 && Number(c.peak_w) > capW;
      const kwh = Number(c.kwh).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
      const peak = Number(c.peak_w).toLocaleString('fr-FR');
      return `<div class="rep-li">
        <div class="rep-li-head">
          <span class="rep-name"><span class="rep-dot" style="background:${col}"></span>${esc(c.nom)}</span>
          <span class="rep-val"><strong>${kwh} kWh</strong> · ${Number(c.pct) || 0} %</span>
        </div>
        <div class="rep-foot">pic ${peak} W${over ? ` <span class="rep-over">⚠ dépasse ${esc(String(data.amperage))} A</span>` : ''}</div>
      </div>`;
    }).join('');
  }
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
    .catch(err => console.error(err));
}

/* ════════════════════════ KPI + PRÉVISION ════════════════════════ */
/* Anti-flash « — » : on mémorise les DERNIÈRES valeurs RÉELLES des KPI et on les
   réaffiche instantanément au (re)chargement, le temps que les données live arrivent.
   → plus jamais de tiret « — » qui clignote quand on actualise. Valeurs 100 % réelles
   (dernier état connu), jamais fabriquées ; un squelette ne s'affiche qu'à la toute
   première visite (aucun cache encore). */
const KPI_CACHE_KEY = 'aoceda_kpi_cache_v1';
const KPI_CACHE_IDS = ['kpi-power', 'kpi-energy', 'kpi-bill', 'kpi-alerts', 'kpi-bill-label', 'kpi-bill-meta', 'forecast-bill', 'cf-kwh', 'cf-fcfa', 'iot-active'];
function cacheKpis() {
  try {
    const snap = {};
    KPI_CACHE_IDS.forEach(id => {
      const el = document.getElementById(id);
      // On ne mémorise ni un squelette, ni un ancien placeholder tiret.
      if (el && el.textContent && el.textContent.indexOf('—') === -1 && !el.querySelector('.skel')) snap[id] = el.textContent;
    });
    if (Object.keys(snap).length) localStorage.setItem(KPI_CACHE_KEY, JSON.stringify(snap));
  } catch (e) { /* localStorage indisponible : sans gravité */ }
}
function restoreKpis() {
  try {
    const snap = JSON.parse(localStorage.getItem(KPI_CACHE_KEY) || '{}');
    Object.keys(snap).forEach(id => {
      const el = document.getElementById(id);
      if (el && snap[id]) el.textContent = snap[id];
    });
  } catch (e) { /* ignore */ }
}

function renderKpis() {
  const kpis = state.kpis;
  if (!kpis) return;
  const power = document.getElementById('kpi-power');
  const energy = document.getElementById('kpi-energy');
  const bill = document.getElementById('kpi-bill');
  const alerts = document.getElementById('kpi-alerts');
  const num = v => Number(v || 0).toLocaleString('fr-FR');
  // La puissance live est pilotée par le SSE (3 s) dès qu'il a émis : on ne la
  // réécrit pas depuis le résumé (évite un clignotement « 0 W » ↔ «, W »).
  if (power && !state.sseHasPower) power.textContent = `${num(kpis.puissance_instantanee)} W`;
  // Format fr-FR (« 0,01 kWh ») cohérent avec les autres KPI, pas le brut JS « 0.01 ».
  if (energy) energy.textContent = `${Number(kpis.consommation_jour_kwh || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kWh`;
  // Source unique pour le KPI facture : le même total que la carte (state.facture.
  // total_fcfa_arrondi) dès qu'il est chargé, sinon le résumé. Évite un écart transitoire
  // d'~1 FCFA entre #kpi-bill et #forecast-bill (deux requêtes à des instants différents).
  if (bill) {
    const billVal = (state.facture && state.facture.total_fcfa_arrondi != null)
      ? Number(state.facture.total_fcfa_arrondi) : Number(kpis.facture_estimee_fcfa || 0);
    bill.textContent = `${num(billVal)} FCFA`;
  }
  if (alerts) alerts.textContent = `${kpis.alertes_actives != null ? kpis.alertes_actives : 0}`;
  updateConnectionBadge(kpis.mode);
  updateBillFraming();
  cacheKpis(); // mémorise les valeurs réelles pour l'affichage instantané au prochain chargement
}

/* Type de compteur effectif (référencé par le technicien) : prépayé / postpayé.
   Source : résumé ou facture ; à défaut, déduit de la présence d'un crédit. */
function meterType() {
  if (state.kpis && state.kpis.type_compteur) return state.kpis.type_compteur;
  if (state.facture && state.facture.type_compteur) return state.facture.type_compteur;
  if ((state.kpis && state.kpis.credit_prepaye) || (state.facture && state.facture.credit_prepaye)) return 'prepaye';
  return 'postpaye';
}

/* Cadrage du KPI « facture » selon le type de compteur :
   - postpayé : facture mensuelle (payée en fin de mois) ;
   - prépayé : coût du mois qui se déduit du crédit rechargé. */
function updateBillFraming() {
  const prepaid = meterType() === 'prepaye';
  const labelEl = document.getElementById('kpi-bill-label');
  const metaEl = document.getElementById('kpi-bill-meta');
  if (labelEl) labelEl.textContent = prepaid ? t('Coût du mois, à ce jour') : t('Facture du mois, à ce jour');
  if (metaEl) {
    const amp = (state.facture && state.facture.amperage) ? `${t('Grille CIE')} ${state.facture.amperage}A · ` : '';
    metaEl.textContent = amp + (prepaid
      ? t('Prépayé · coût réel consommé, TVA incl.')
      : t('Postpayé · coût réel consommé à ce jour, TVA incl.'));
  }
}

/* Badge d'en-tête : reflète l'origine réelle des données (production / vide). */
function updateConnectionBadge(mode) {
  const badge = document.getElementById('connection-badge');
  if (!badge) return;
  const span = badge.querySelector('span');
  if (mode === 'production') {
    if (span) span.textContent = t('Données en direct');
    badge.classList.remove('demo'); badge.classList.add('live');
  } else if (mode === 'vide') {
    if (span) span.textContent = t('Aucun capteur, en attente de données');
    badge.classList.remove('live'); badge.classList.add('demo');
  } else {
    // mode inconnu (avant la 1re réponse API) : libellé neutre, jamais « démonstration »
    if (span) span.textContent = t('Connexion…');
    badge.classList.remove('live', 'demo');
  }
}

function renderForecast() {
  const f = state.facture;
  const billEl = document.getElementById('forecast-bill');
  const kwhEl = document.getElementById('forecast-kwh');
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

    const simple =
      bucket(HOME, 'fc-fixed', t('Abonnement fixe'),
        `${t('Payé chaque mois, même sans rien consommer ·')} ${amperage} A`, `${esc(fmtF(abonnement))} F`) +
      bucket(BOLT, 'fc-conso', t('Votre consommation'),
        `${esc(fmtKwh(kwhTotal))} ${t('kWh utilisés ce mois-ci')}`, `${esc(fmtF(conso))} F`);

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

    const detailRows = [
      drow('Tranche 1 (Consommation HT)', `${esc(fmtKwh(f.tranche1.kwh))} kWh × ${esc(fmtPrix(f.tranche1.prix))} F`, `${esc(fmtF(f.tranche1.fcfa))} F`)
    ];
    if (f.tranche2 && Number(f.tranche2.kwh) > 0) {
      detailRows.push(drow('Tranche 2 (Consommation HT)', `${esc(fmtKwh(f.tranche2.kwh))} kWh × ${esc(fmtPrix(f.tranche2.prix))} F`, `${esc(fmtF(f.tranche2.fcfa))} F`));
    }
    detailRows.push(drow('Taxes variables (sur la consommation)', `${esc(fmtPrix(f.taxes_par_kwh))} F/kWh`, `${esc(fmtF(taxesVariables))} F`));
    detailRows.push(drow('Prime fixe HT (abonnement)', `${amperage} A`, `${esc(fmtF(f.prime_fixe_fcfa))} F`));
    detailRows.push(drow('Taxes fixes (sur l\'abonnement)', 'Redevance CIE fixe', `${esc(fmtF(taxesFixes))} F`));

    const detail =
      `<details class="fc-details"><summary>${t('Voir le détail officiel CIE')}</summary><div class="fc-drows">${detailRows.join('')}</div></details>`;

    if (formulaEl) formulaEl.innerHTML = simple + totalRow + note + detail;
    if (billEl) billEl.textContent = totalAffiche.toLocaleString(_LOCALE);
  } else if (state.kpis) {
    const billValue = Number(state.kpis.facture_estimee_fcfa || 0);
    if (billEl) billEl.textContent = billValue.toLocaleString(_LOCALE);
    if (kwhEl) kwhEl.innerHTML = '<span class="skel" style="width:3em"></span>';
  }

  // Progression réelle du mois : jours_ecoules / jours_du_mois
  const now = new Date();
  const joursDuMois = f && f.jours_du_mois ? Number(f.jours_du_mois)
    : new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const joursEcoules = f && f.jours_ecoules ? Number(f.jours_ecoules) : now.getDate();
  if (dayEl) dayEl.textContent = `Jour ${joursEcoules} / ${joursDuMois}`;
  if (progressEl) progressEl.style.width = `${Math.round(joursEcoules / joursDuMois * 100)}%`;

  renderCompare();
  renderCredit();
}

function renderCompare() {
  const el = document.getElementById('forecast-compare');
  if (!el || state.ecart === null) return; // repli : badge maquette inchangé
  const ecart = Math.round(state.ecart * 10) / 10;
  if (!ecart) {
    el.style.display = 'none';
    return;
  }
  el.style.display = '';
  el.className = `compare-badge ${ecart > 0 ? 'compare-up' : 'compare-dn'}`;
  // Chiffre en police mono (--fm) ; libellé en corps. Valeurs déjà numériques (pas d'injection).
  const sign = ecart > 0 ? '↑ ' : '↓ ';
  const num = `${ecart > 0 ? '+' : ''}${ecart.toLocaleString('fr-FR')} %`;
  el.innerHTML = `${sign}<span class="cb-num">${esc(num)}</span> vs mois précédent`;
}

/* Ligne crédit prépayé : visible UNIQUEMENT pour les compteurs prépayés.
   Affiche le solde RESTANT estimé et l'autonomie (données /api/analytics/). */
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
  if (labelEl) labelEl.textContent = 'Crédit restant estimé';
  if (valEl) valEl.textContent = `${Math.round(Number(credit.restant_fcfa)).toLocaleString('fr-FR')} FCFA`;
  if (subEl) {
    const jr = credit.jours_restants;
    subEl.textContent = (jr != null)
      ? `≈ ${jr} jour${jr > 1 ? 's' : ''} d'autonomie · ${Math.round(Number(credit.cout_jour_fcfa)).toLocaleString('fr-FR')} FCFA/j`
      : `Rechargé : ${Math.round(Number(credit.recharge_fcfa)).toLocaleString('fr-FR')} FCFA`;
  }
}

function loadSummary() {
  fetchWithAuth('/api/analytics/summary/')
    .then(data => {
      state.kpis = data;
      renderKpis();
      renderForecast();
    })
    .catch(err => console.error(err));
}

/* Facture officielle CIE (moteur tarifaire) → prévision, formule, KPI, tooltips */
function loadFacture() {
  fetchWithAuth('/api/analytics/facture/')
    .then(data => {
      if (!data || !data.tranche1) return; // réponse inattendue → on garde l'état honnête
      state.facture = data;
      renderKpis(); // #kpi-bill se recale sur le même total que la carte (source unique)
      // Prix STABLE (marginal T1 + taxes, ~92,5 F) et non prix_moyen_kwh qui
      // explose en début de mois (prime fixe ÷ kWh projetés minuscules).
      if (data.prix_kwh_tout_compris) state.prixMoyen = Number(data.prix_kwh_tout_compris);
      else if (data.prix_moyen_kwh) state.prixMoyen = Number(data.prix_moyen_kwh);
      renderForecast();
      renderChart(); // tooltips ≈ kWh × prix moyen réel
      updateBillFraming(); // libellé/meta selon le type de compteur + ampérage
    })
    .catch(err => console.error(err));
}

/* Écart réel du mois courant vs mois précédent (item de /api/previsions/).
   Sert au badge « ↑/↓ % vs mois précédent », comparaison de montants RÉELS,
   pas de projection du futur. */
function loadEcart() {
  fetchWithAuth('/api/previsions/')
    .then(data => {
      const list = window.AOCEDA.asList(data);
      if (list.length === 0) return;
      const sorted = [...list].sort((a, b) =>
        String(b.annee_mois || '').localeCompare(String(a.annee_mois || '')));
      const now = new Date();
      const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const cur = sorted.find(p => p.annee_mois === ym) || sorted[0];

      const e = parseFloat(cur['écartSurMoisPrécédent']);
      if (!isNaN(e)) { state.ecart = e; renderCompare(); }
    })
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

  // « Marquer comme lue » (délégation)
  const alertsList = document.getElementById('alerts-list');
  if (alertsList) alertsList.addEventListener('click', e => {
    const btn = e.target.closest('.dismiss-btn');
    if (btn) dismissAlert(btn.dataset.id);
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
    const f = repFromEl ? repFromEl.value : '', t = repToEl ? repToEl.value : '';
    if (!f || !t) { if (repHint) repHint.textContent = t('Choisissez une date de début et de fin.'); return; }
    if (f > t) { if (repHint) repHint.textContent = t('La date de début doit précéder la date de fin.'); return; }
    if (repHint) repHint.textContent = '';
    state.repMode = 'custom'; state.repFrom = f; state.repTo = t;
    loadRepartition();
  });

  // Bouton "Comparer" : ouvre/ferme la barre + désactive si déjà actif
  const compareBtn = document.getElementById('compare-btn');
  if (compareBtn) {
    compareBtn.addEventListener('click', () => {
      if (state.compareBarOpen && state.compareSensor !== null) {
        clearCompare();
      } else if (state.compareBarOpen) {
        state.compareBarOpen = false;
        const bar = document.getElementById('compare-bar');
        if (bar) bar.style.display = 'none';
        compareBtn.classList.remove('open');
        compareBtn.setAttribute('aria-expanded', 'false');
      } else {
        state.compareBarOpen = true;
        const bar = document.getElementById('compare-bar');
        if (bar) bar.style.display = '';
        compareBtn.classList.add('open');
        compareBtn.setAttribute('aria-expanded', 'true');
        updateCompareSensors();
        updateCompareBtn(); // états actifs (capteur + période) à jour
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
      el.addEventListener('input', () => { el.classList.remove('invalid'); setCbarHint(''); });
    }
  });

  // Bouton "Charger" du sélecteur de dates (capteur obligatoire + validation visible)
  const applyBtn = document.getElementById('cbar-apply');
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      // Règle métier : une plage ne se charge que pour un capteur choisi
      if (state.compareSensor === null) {
        setCbarHint('Choisissez d’abord le capteur à comparer.', true);
        return;
      }
      const fromEl = document.getElementById('cbar-from');
      const toEl = document.getElementById('cbar-to');
      const from = fromEl ? fromEl.value : '';
      const to = toEl ? toEl.value : '';
      if (!from || !to || from > to) {
        if (fromEl) fromEl.classList.toggle('invalid', !from || (!!to && from > to));
        if (toEl) toEl.classList.toggle('invalid', !to || (!!from && from > to));
        setCbarHint(t('Choisissez deux dates valides (début ≤ fin).'), true);
        return;
      }
      fromEl.classList.remove('invalid');
      toEl.classList.remove('invalid');
      setCbarHint('');
      state.prevTelemetry = [];
      state.compareLoaded = false;
      loadCompareByDates(from, to);
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
  loadEcart();
  loadSensors();
  loadTelemetry();
  loadAlerts();
  loadRepartition();

  // ── Rafraîchissement TEMPS RÉEL (sans recharger la page) ──
  // Tout toutes les 10 s. Le graphe se rafraîchit maintenant TOUTES LES 10 s (endpoint
  // agrégé ~0,3 s → coût négligeable) et se met à jour EN PLACE (transition animée),
  // donc on VOIT les données bouger sans clignotement ni rechargement manuel.
  // EN PAUSE quand l'onglet est masqué, nettoyé au déchargement (pas de fuite).
  function refreshKpisLive() { loadSummary(); loadFacture(); loadEcart(); }
  let liveTimers = [];
  function startLiveTimers() {
    stopLiveTimers();
    liveTimers.push(setInterval(loadAlerts, 10000));        // panneau alertes
    liveTimers.push(setInterval(refreshKpisLive, 10000));   // Consommation du jour + Facture
    liveTimers.push(setInterval(loadTelemetry, 10000));     // graphe de consommation (agrégé, léger)
    liveTimers.push(setInterval(loadRepartition, 30000));   // répartition par capteur (fenêtre 7 j, lente)
  }
  function stopLiveTimers() { liveTimers.forEach(clearInterval); liveTimers = []; }
  startLiveTimers();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopLiveTimers();
    } else {
      // Retour sur l'onglet : on rafraîchit immédiatement puis on relance les timers.
      loadAlerts(); refreshKpisLive(); loadTelemetry();
      startLiveTimers();
    }
  });
  window.addEventListener('pagehide', stopLiveTimers);

  // ── Flux SSE temps réel, puissance instantanée sans rechargement de page ──
  startSSE();
}

/* ════════════════════════ SSE TEMPS RÉEL ════════════════════════ */
let _sseSource = null;

function startSSE() {
  const token = localStorage.getItem('aoceda_access_token');
  if (!token) return;

  if (_sseSource) { _sseSource.close(); _sseSource = null; }

  _sseSource = new EventSource('/api/sensors/stream/?token=' + encodeURIComponent(token));

  _sseSource.onmessage = function (e) {
    try {
      const payload = JSON.parse(e.data);
      if (payload.error) return;
      applySSEUpdate(payload.mesures || []);
    } catch (_) {}
  };

  _sseSource.onerror = function () {
    _sseSource.close();
    _sseSource = null;
    // Tente un refresh du token avant de reconnecter (gère l'expiration JWT)
    setTimeout(function() {
      window.AOCEDA.refreshAccessToken()
        .then(function() { startSSE(); })
        .catch(function() {
          window.AOCEDA.logout();
          window.location.href = '/auth/';
        });
    }, 10000);
  };
}

function applySSEUpdate(mesures) {
  if (!mesures.length) return;

  // Mettre à jour l'état ON/OFF de chaque capteur dans state.sensorsList
  const now = Date.now();
  const STALE_MS = 60000; // données périmées si > 60 s (bridge arrêté)
  mesures.forEach(m => {
    const s = state.sensorsList.find(x => String(x.id) === String(m.id));
    if (s) {
      s.sseEtat = m.etat;
      s.etatCourant = m.etat;
      // derniereLecture = CONTACT matériel réel (en ligne/hors ligne).
      if (m.derniereLecture) s.derniereLecture = m.derniereLecture;
      // derniereMesure = dernière CONSOMMATION (info « activité »), distincte du contact.
      if (m.derniereMesure) s.derniereMesure = m.derniereMesure;
    }
  });
  renderIoT();

  // Données récentes : bridge en train de tourner (derniereLecture < 60 s)
  const avecMesure = mesures.filter(m =>
    m.puissance != null &&
    m.derniereLecture != null &&
    (now - new Date(m.derniereLecture).getTime()) < STALE_MS
  );

  // Badge d'en-tête : « Données en direct » UNIQUEMENT si des mesures fraîches
  // (< 60 s) arrivent. Sinon on n'affirme pas un flux live, cohérent avec la
  // puissance «, W » et le device-status « En attente » calculés juste après.
  const badge = document.getElementById('connection-badge');
  if (badge) {
    const span = badge.querySelector('span');
    if (avecMesure.length > 0) {
      if (span) span.textContent = t('Données en direct');
      badge.classList.remove('demo'); badge.classList.add('live');
    } else {
      if (span) span.textContent = t('Aucune donnée récente, en attente');
      badge.classList.remove('live', 'demo');
    }
  }

  // Panneau "Pont série" : visible si bridge actif
  const deviceRow = document.getElementById('device-row-main');
  if (deviceRow) deviceRow.style.display = avecMesure.length > 0 ? '' : 'none';
  const statusEl = document.getElementById('device-status');
  if (statusEl) statusEl.textContent = avecMesure.length > 0 ? t('En ligne') : t('En attente');

  // Puissance : total réel si le pont émet ; sinon on NE met PAS « — » (tiret qui
  // faisait « bug ») → on retombe sur la dernière puissance connue du résumé (valeur
  // réelle récente) ou on garde la valeur déjà affichée (cache). Jamais de tiret.
  const powerEl = document.getElementById('kpi-power');
  if (avecMesure.length === 0) {
    state.sseHasPower = false; // renderKpis pourra la réafficher depuis le résumé
    if (powerEl && state.kpis && state.kpis.puissance_instantanee != null) {
      powerEl.textContent = Number(state.kpis.puissance_instantanee || 0).toLocaleString('fr-FR') + ' W';
    }
  } else {
    state.sseHasPower = true; // le SSE pilote la puissance live
    if (powerEl) {
      const totalW = avecMesure.reduce((s, m) => s + (m.puissance || 0), 0);
      powerEl.textContent = Math.round(totalW).toLocaleString('fr-FR') + ' W';
    }
  }
  cacheKpis(); // mémorise la puissance réelle affichée pour l'anti-flash au rechargement

  // Rafraîchir la liste des capteurs toutes les 15 s
  if (!startSSE._lastSensorsRefresh ||
      Date.now() - startSSE._lastSensorsRefresh > 15000) {
    startSSE._lastSensorsRefresh = Date.now();
    loadSensors();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
