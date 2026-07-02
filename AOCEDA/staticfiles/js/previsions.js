/* AOCEDA — Prévisions & Facturation (JavaScript vanilla, sans React)
   N.B. : le shell commun (client-shell.js, chargé avant) gère le bloc
   utilisateur, la déconnexion, la cloche de notifications et la nav
   mobile. Ici : thème (#theme-toggle, recréation des graphiques),
   données API (/api/analytics/facture/ — moteur tarifaire officiel CIE,
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

/* Pas de repli maquette — on affiche "—" quand l'API ne retourne rien */

/* ── État de la page ── */
let theme = localStorage.getItem('aoceda-theme') || 'light';
let budget = 25000;
let chartPeriod = 'mois';
let summary = null;
let previsions = [];
let facture = null;        // décomposition officielle CIE (/api/analytics/facture/)
let prixMoyen = 92.5;      // prix moyen effectif FCFA/kWh (repli grille 10A T1 + taxes)
let exporting = false;
let projChart = null;
// Agrégation JOURNALIÈRE du mois courant (/api/analytics/historique/) — rapide (une
// ligne par jour) au lieu des milliers de mesures brutes qui bloquaient le graphe.
let joursMonth = [];       // [{date:'AAAA-MM-JJ', kwh:…}]
let joursLoaded = false;   // true une fois le fetch terminé (succès OU échec)
// Carte thermique agrégée côté serveur (/api/analytics/heatmap/)
let heatCells = null;      // [{dow:0-6, hour:0-23, avg_w:…}]
let heatLoaded = false;

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
/* Tri chronologique sur annee_mois ("AAAA-MM") — le tri alphabétique sur
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
  // Historique mensuel (5 derniers mois, ordre chronologique) — vide si API vide
  if (previsions.length <= 1) return [];
  const curYm = facture && facture.annee_mois ? facture.annee_mois : null;
  return previsionsTriees().slice(0, 5).reverse().map((p, i, a) => {
    const cur = curYm ? p.annee_mois === curYm : i === a.length - 1;
    return {
      m: cur ? `${p['moisConcerné']} (en cours)` : p['moisConcerné'],
      v: Math.round(Number(p['montantEstimé_FCFA'])) || 0,
      kwh: Math.round(Number(p['consomméeEstimée_kWh'])) || 0,
      cur
    };
  });
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
    ? 'FCFA — coût du mois à ce jour (déduit de votre crédit prépayé)'
    : 'FCFA — facture du mois à ce jour (compteur postpayé)';

  // Historique mensuel : le mois en cours est aligné sur l'estimation « live »
  // (héros). Garantit la cohérence montant / décomposition / comparatif.
  const histo = getHisto();
  const curEntry = histo.find(x => x.cur) || histo[histo.length - 1];
  if (curEntry) { curEntry.v = factureTotal; curEntry.kwh = kwhEst; }
  const maxKwhHisto = Math.max(...histo.map(x => x.kwh), 1);
  const curIdx = histo.indexOf(curEntry);
  const prev = curIdx > 0 ? histo[curIdx - 1] : (histo.length > 1 ? histo[histo.length - 2] : null);
  const cmpLabel = prev ? `comparé à ${prev.m} (${prev.v.toLocaleString('fr-FR')} FCFA)` : 'comparé au mois précédent';

  // Écart calculé sur les montants RÉELLEMENT affichés (jamais d'incohérence
  // entre le % et le montant comparé). Repli sur le champ API si pas de mois précédent.
  let ecart;
  if (prev && prev.v > 0) {
    ecart = Math.round((factureTotal - prev.v) / prev.v * 1000) / 10;
  } else {
    const ecartRaw = current ? parseFloat(current['écartSurMoisPrécédent']) : null;
    ecart = (ecartRaw === null || isNaN(ecartRaw)) ? 0 : Math.round(ecartRaw * 10) / 10;
  }

  // Badge d'écart : ↑ rouge (hausse), ↓ vert (baisse) — classes cmp-up / cmp-dn
  const badge = $('cmp-badge');
  badge.className = `cmp-badge ${ecart >= 0 ? 'cmp-up' : 'cmp-dn'}`;
  badge.textContent = `${ecart >= 0 ? '↑ +' : '↓ '}${ecart}%`;
  $('cmp-label').textContent = cmpLabel;

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
    const bucket = (ico, cls, lbl, sub, val) =>
      `<div class="decomp-bucket ${cls}"><span class="db-ico">${ico}</span>` +
      `<span class="db-txt"><span class="db-lbl">${esc(lbl)}</span><span class="db-sub">${esc(sub)}</span></span>` +
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
        `Payé chaque mois, même sans rien consommer · ${esc(String(f.amperage))} A`, `${abo.toLocaleString('fr-FR')} F`) +
      bucket(BOLT, 'db-conso', prepaid ? 'Ce que vous avez consommé' : 'Votre consommation',
        `${kwhConso} kWh ${prepaid ? 'consommés' : 'utilisés'} ce mois-ci`, `${conso.toLocaleString('fr-FR')} F`) +
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
  $('histo-sub').textContent = `Comparatif des ${histo.length} derniers mois`;
  $('histo-list').innerHTML = histo.map(r => {
    const pct = Math.min(100, r.kwh / maxKwhHisto * 100);
    const cur = r.cur ? ' cur' : '';
    return `<div class="histo-item">
      <div class="histo-head">
        <span class="histo-month${cur}">${esc(r.m)}</span>
        <span class="histo-val${cur}">${r.v.toLocaleString('fr-FR')} FCFA</span>
      </div>
      <div class="histo-track"><div class="histo-bar${cur}" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');
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
   serveur. Jours passés + aujourd'hui = mesuré (0 si aucune mesure) ; jours futurs =
   null (AUCUNE projection). Uniquement du réel. */
function buildMonthlyArrays() {
  const now   = new Date();
  const year  = now.getFullYear();
  const month = now.getMonth(); // 0-indexed
  const today = now.getDate();  // 1-indexed, jour du mois
  const daysInMonth = facture && facture.jours_du_mois
    ? Number(facture.jours_du_mois)
    : new Date(year, month + 1, 0).getDate();

  // Map jour-du-mois → kWh réel (clé ISO 'AAAA-MM-JJ' de l'agrégation serveur)
  const dailyMap = new Map();
  joursMonth.forEach(j => {
    const d = new Date(j.date + 'T00:00:00');
    if (d.getFullYear() !== year || d.getMonth() !== month) return;
    dailyMap.set(d.getDate(), Number(j.kwh) || 0);
  });

  const actual = [];
  for (let day = 1; day <= daysInMonth; day++) {
    if (day <= today) {
      const v = dailyMap.get(day);
      actual.push(v != null ? Math.round(v * 100) / 100 : 0);
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
  const dvDash = cssVar('--dv-dash', '#CDA46A');
  const ref = cssVar('--tx-m', '#8A7660');
  const ink = cssVar('--tx-p', '#231B10');
  const fillC = d ? 'rgba(27,122,110,.10)' : 'rgba(27,122,110,.07)';

  // Mode "3 mois" : graphique mensuel basé sur les données réelles de prévisions
  if (chartPeriod === '3mois') {
    if (previsions.length === 0) {
      showChartEmpty('Aucune donnée de prévision mensuelle disponible.');
      return;
    }
    hideChartEmpty();
    const sorted = previsionsTriees().slice(0, 3).reverse();
    const labels3 = sorted.map(p => p['moisConcerné'] || p.annee_mois || '—');
    const kwh3 = sorted.map(p => Math.round(Number(p['consomméeEstimée_kWh'])) || 0);
    const fcfa3 = sorted.map(p => Math.round(Number(p['montantEstimé_FCFA'])) || 0);
    projChart = new Chart($('proj-chart'), {
      type: 'bar',
      data: { labels: labels3, datasets: [
        { label: 'Consommation (kWh)', data: kwh3, backgroundColor: d ? 'rgba(27,122,110,.55)' : 'rgba(27,122,110,.45)', borderColor: dv2, borderWidth: 1.5, borderRadius: 6, yAxisID: 'y' },
        { label: 'Facture (FCFA)', data: fcfa3, type: 'line', borderColor: dvDash, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 5, pointBackgroundColor: dvDash, tension: .3, yAxisID: 'y2' },
      ] },
      options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
        plugins: { legend: { display: true, labels: { color: lc, font: { family: 'Hanken Grotesk', size: 12 } } }, tooltip: {
          backgroundColor: surf, borderColor: cssVar('--bd-s', d ? 'rgba(255,255,255,.08)' : '#E4D9C8'), borderWidth: 1,
          titleColor: ink, bodyColor: lc,
          titleFont: { family: 'Hanken Grotesk', weight: '700', size: 12 }, bodyFont: { family: 'Spline Sans Mono', size: 12 }, padding: 10, cornerRadius: 8,
        } },
        scales: {
          y: { beginAtZero: true, grid: { color: gc }, border: { display: false }, ticks: { color: lc, font: { family: 'Spline Sans Mono', size: 11 }, callback: v => `${v} kWh` } },
          y2: { position: 'right', beginAtZero: true, grid: { display: false }, border: { display: false }, ticks: { color: lc, font: { family: 'Spline Sans Mono', size: 11 }, callback: v => `${v.toLocaleString('fr-FR')} F` } },
          x: { grid: { display: false }, border: { display: false }, ticks: { color: lc, font: { family: 'Hanken Grotesk', size: 12 } } }
        } }
    });
    return;
  }

  // Mode "Ce mois" (défaut) : consommation journalière RÉELLE. Aucune projection.
  if (!joursLoaded) { showChartEmpty('Chargement…'); return; }
  const built = buildMonthlyArrays();
  if (!built.hasRealData) { showChartEmpty('Aucune consommation enregistrée ce mois-ci.'); return; }
  hideChartEmpty();
  const historicalData = built.actual;
  const daysCount      = built.daysInMonth;
  const labels = Array.from({ length: daysCount }, (_, i) => `${i + 1}`);
  // Budget OBJECTIF ramené au JOUR (le budget est mensuel) : cible quotidienne en kWh.
  // Avant, on posait le budget mensuel entier → ligne ~30× trop haute, barres écrasées.
  const budgetDailyKwh = daysCount > 0 ? (budget / daysCount / prixMoyen) : 0;
  const budgetLine = Array(daysCount).fill(Math.round(budgetDailyKwh * 100) / 100);

  const tooltipLabel = c => {
    if (c.raw === null || c.raw === undefined) return null;
    if (c.datasetIndex === 1) return `Objectif du jour : ${Math.round(c.raw * prixMoyen).toLocaleString('fr-FR')} FCFA (${c.raw} kWh)`;
    return `Consommation : ${c.raw} kWh ≈ ${Math.round(c.raw * prixMoyen).toLocaleString('fr-FR')} FCFA`;
  };

  projChart = new Chart($('proj-chart'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Consommation', data: historicalData, borderColor: dv2, backgroundColor: fillC, fill: true, tension: .4, pointRadius: 2, pointHoverRadius: 5, pointBackgroundColor: dv2, pointBorderColor: surf, pointBorderWidth: 1.5, spanGaps: false },
      { label: 'Objectif / jour', data: budgetLine, borderColor: ref, borderDash: [4, 4], borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: {
        backgroundColor: surf, borderColor: cssVar('--bd-s', d ? 'rgba(255,255,255,.08)' : '#E4D9C8'), borderWidth: 1,
        titleColor: ink, bodyColor: lc,
        titleFont: { family: 'Hanken Grotesk', weight: '700', size: 12 }, bodyFont: { family: 'Spline Sans Mono', size: 12 }, padding: 10, cornerRadius: 8,
        callbacks: { title: items => items.length ? `Jour ${items[0].label}` : '', label: tooltipLabel }
      } },
      scales: { y: { beginAtZero: true, grid: { color: gc }, border: { display: false }, ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lc, callback: v => `${v} kWh`, maxTicksLimit: 6 } },
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
  if (v === null || v === undefined) return cssVar('--bd-s', '#E4D9C8');
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

  // Cellules agrégées CÔTÉ SERVEUR : puissance moyenne par (jour 0=lundi…6=dimanche, heure).
  const map = {};
  (heatCells || []).forEach(c => { map[c.dow + '-' + c.hour] = Number(c.avg_w) || 0; });
  const avg = (di, hi) => { const k = di + '-' + hi; return (k in map) ? map[k] : null; };

  let maxV = 0;
  for (let di = 0; di < 7; di++) for (let hi = 0; hi < 24; hi++) { const v = avg(di, hi); if (v != null && v > maxV) maxV = v; }
  if (maxV <= 0) { emptyMsg('Aucune donnée de consommation sur les 7 derniers jours.'); return; }

  const days = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
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
  fetchWithAuth('/api/analytics/recharge/', { method: 'POST', body: JSON.stringify({ montant }) })
    .then(data => {
      if (btn) btn.disabled = false;
      if (data && data.credit_prepaye) {
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

/* ── Initialisation ── */
function init() {
  applyTheme();
  renderProgress();
  render();
  renderChart();
  renderHeatmap();
  updateSliders();
  renderCredit();

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

  // Rapport PDF → impression navigateur (génère un PDF via « Enregistrer en PDF »)
  const printBtn = $('btn-print');
  if (printBtn) printBtn.addEventListener('click', () => window.print());

  // Recharge du crédit prépayé (action réelle)
  const rechargeBtn = $('recharge-btn');
  if (rechargeBtn) rechargeBtn.addEventListener('click', rechargeCredit);
  const creditInput = $('credit-input');
  if (creditInput) creditInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); rechargeCredit(); }
  });

  // Chargement API : facture officielle CIE + résumé analytique + prévisions + mesures du mois
  fetchWithAuth('/api/analytics/facture/')
    .then(data => {
      if (!data || !data.tranche1) return; // réponse inattendue → on garde l'état vide honnête (—)
      facture = data;
      // Prix STABLE (marginal T1 + taxes, ~92,5 F) pour le simulateur/budget/tooltips.
      // PAS prix_moyen_kwh, qui explose en début de mois → économies aberrantes (−318 788 F).
      if (data.prix_kwh_tout_compris) prixMoyen = Number(data.prix_kwh_tout_compris);
      else if (data.prix_moyen_kwh) prixMoyen = Number(data.prix_moyen_kwh);
      render();
      renderProgress();
      renderChart();
      renderCredit();
    })
    .catch(err => console.error(err));
  fetchWithAuth('/api/analytics/summary/')
    .then(data => { summary = data; render(); renderCredit(); })
    .catch(err => console.error(err));
  fetchWithAuth('/api/previsions/')
    .then(data => { previsions = window.AOCEDA.asList(data); render(); renderChart(); })
    .catch(err => console.error(err));
  // Consommation JOURNALIÈRE du mois (agrégée côté serveur → rapide) pour le graphe.
  const now0 = new Date();
  const firstOfMonth = `${now0.getFullYear()}-${String(now0.getMonth() + 1).padStart(2, '0')}-01`;
  fetchWithAuth(`/api/analytics/historique/?date_from=${firstOfMonth}`)
    .then(data => {
      joursMonth = (data && Array.isArray(data.jours)) ? data.jours : [];
      joursLoaded = true;
      renderChart();
    })
    .catch(() => { joursLoaded = true; renderChart(); });
  // Carte thermique agrégée (puissance moyenne par jour × heure, 7 derniers jours).
  fetchWithAuth('/api/analytics/heatmap/')
    .then(data => {
      heatCells = (data && Array.isArray(data.cells)) ? data.cells : [];
      heatLoaded = true;
      renderHeatmap();
    })
    .catch(() => { heatLoaded = true; renderHeatmap(); });
}

init();
