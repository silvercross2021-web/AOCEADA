'use strict';
const t = window.AOCEDA_T || (x => x);
/* ── Locale dynamique ── */
const _LOCALE = (localStorage.getItem('aoceda-lang') === 'en') ? 'en-GB' : 'fr-FR';
/* ════════════════════════════════════════════════════════════
   AOCEDA, Alertes & Configuration (page dédiée)
   Deux onglets : « Mes alertes » et « Configuration ».
   ════════════════════════════════════════════════════════════ */

const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401.
   REJETTE sur tout statut non-OK : sinon un 400/500 à corps JSON serait pris pour un
   succès, c'était la cause du « Préférences enregistrées » menteur. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json().catch(() => null);
  });
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
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
});

/* ════════════════ Onglets (Mes alertes / Configuration) ════════════════ */
let currentTab = 'alertes';
const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
const tabPanels = {
  alertes: document.getElementById('tab-alertes'),
  config: document.getElementById('tab-config'),
};
const TAB_TO_HASH = { alertes: '', config: '#config' };
function hashToTab(hash) { return hash === '#config' ? 'config' : 'alertes'; }

function setTab(t, opts) {
  currentTab = t;
  tabButtons.forEach(b => {
    const isActive = b.dataset.tab === t;
    b.classList.toggle('active', isActive);
    b.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  Object.keys(tabPanels).forEach(k => { if (tabPanels[k]) tabPanels[k].style.display = k === t ? '' : 'none'; });
  if (!opts || !opts.fromHash) {
    history.replaceState(null, '', window.location.pathname + window.location.search + TAB_TO_HASH[t]);
  }
  if (t === 'alertes') initAlertes();
  else initConfig();
}
tabButtons.forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
window.addEventListener('hashchange', () => {
  const t = hashToTab(window.location.hash);
  if (t !== currentTab) setTab(t, { fromHash: true });
});

/* ════════════════ Onglet « Mes alertes » ════════════════ */
const alertState = { filter: 'toutes', alerts: [] };

const filterBar = document.getElementById('filter-bar');
const alertList = document.getElementById('alert-list');
const alertSummary = document.getElementById('alert-summary');
const markAllBtn = document.getElementById('mark-all-read');
const tabAlertCount = document.getElementById('tab-alert-count');

/* Sévérités backend : 'Critique' | 'Avertissement' | 'Info' (jamais « Résolue »).
   Une alerte active ne doit JAMAIS être affichée comme résolue. */
const SEV_LABEL = { crit: 'Critique', warn: 'Avertissement', info: 'Information' };
const SEV_CLASS = { crit: 'sev-crit', warn: 'sev-warn', info: 'sev-info' };
const BAR_COLOR = { crit: 'var(--err)', warn: 'var(--warn)', info: 'var(--info)' };
const ALERT_FILTERS = [['toutes', 'Toutes'], ['non-lues', 'Non lues'], ['crit', 'Critique'], ['warn', 'Avertissement'], ['info', 'Information']];

const ICO_CRIT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
const ICO_WARN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
const ICO_BELL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';

/* Libellés HUMAINS des types (le back expose type_display ; carte locale en repli). */
const TYPE_LABELS = {
  DEPASSEMENT_SEUIL: 'Dépassement de seuil',
  CONSOMMATION_NOCTURNE: 'Consommation nocturne',
  CREDIT_BAS: 'Crédit prépayé bas',
};
function mapApiAlert(a) {
  const sevRaw = a['sévérité'] || a.severity || '';
  const sev = sevRaw === 'Critique' ? 'crit' : (sevRaw === 'Avertissement' ? 'warn' : 'info');
  const d = a.createdAt ? new Date(a.createdAt) : new Date();
  const time = `${d.toLocaleDateString(_LOCALE, { weekday: 'short', day: 'numeric', month: 'short' })} · ${d.toLocaleTimeString(_LOCALE, { hour: '2-digit', minute: '2-digit' }).replace(':', 'h')}`;
  const raw = a.type || 'ALERTE';
  const type = a.type_display || TYPE_LABELS[raw] || raw.replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase());
  return { id: a.id, type, msg: a.message, time, sev, read: !!a.lue, capteur: a.capteur_nom || null };
}

/* Message d'action transitoire (échec « marquer lu », etc.), honnête, jamais silencieux. */
const alertFeedback = document.getElementById('alert-feedback');
let feedbackTimer = null;
function showAlertFeedback(msg, isError) {
  if (!alertFeedback) return;
  alertFeedback.textContent = msg;
  alertFeedback.classList.toggle('err', !!isError);
  clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => { alertFeedback.textContent = ''; }, 5000);
}

/* Resynchronise le badge de la sidebar + le point de la cloche (rendus par
   client-shell au chargement) après une action « lu », plus de désync. */
function syncShellBadges() {
  const unread = alertState.alerts.filter(x => !x.read).length;
  const navBadge = document.getElementById('nav-alert-badge');
  if (navBadge) {
    navBadge.textContent = String(unread);
    navBadge.style.display = unread > 0 ? '' : 'none';
  }
  const dot = document.getElementById('notif-dot');
  if (dot) dot.style.display = unread > 0 ? '' : 'none';
}

function renderAlertSummary() {
  const a = alertState.alerts;
  const unread = a.filter(x => !x.read).length;
  // Tuiles = alertes ACTIVES (non lues), cohérent avec « Non lues ». Après « Tout
  // marquer lu », Critiques/Avertissements tombent à 0 comme il se doit.
  const crit = a.filter(x => x.sev === 'crit' && !x.read).length;
  const warn = a.filter(x => x.sev === 'warn' && !x.read).length;
  if (alertSummary) alertSummary.innerHTML = `
    <div class="asum"><div class="asum-ico unread">${ICO_BELL}</div><div><div class="asum-val">${unread}</div><div class="asum-lbl">${_LOCALE === 'en-GB' ? 'Unread' : `Non lue${unread > 1 ? 's' : ''}`}</div></div></div>
    <div class="asum"><div class="asum-ico crit">${ICO_CRIT}</div><div><div class="asum-val">${crit}</div><div class="asum-lbl">${_LOCALE === 'en-GB' ? 'Critical' : `Critique${crit > 1 ? 's' : ''}`}</div></div></div>
    <div class="asum"><div class="asum-ico warn">${ICO_WARN}</div><div><div class="asum-val">${warn}</div><div class="asum-lbl">${_LOCALE === 'en-GB' ? 'Warning' : `Avertissement${warn > 1 ? 's' : ''}`}</div></div></div>`;
  if (markAllBtn) markAllBtn.disabled = unread === 0;
  if (tabAlertCount) {
    tabAlertCount.textContent = String(unread);
    tabAlertCount.style.display = unread > 0 ? '' : 'none';
  }
  syncShellBadges();
}

function renderAlertes() {
  const { filter, alerts } = alertState;
  renderAlertSummary();

  filterBar.innerHTML = ALERT_FILTERS.map(([k, lFr]) => {
    const FILTER_EN = { 'Toutes': 'All', 'Non lues': 'Unread', 'Critique': 'Critical', 'Avertissement': 'Warning', 'Information': 'Information' };
    const l = _LOCALE === 'en-GB' ? (FILTER_EN[lFr] || lFr) : lFr;
    return `<button class="fpill${filter === k ? ' active' : ''}" type="button" data-filter="${k}">${l}${k === 'toutes' ? ` (${alerts.length})` : ''}</button>`;
  }).join('');

  const filtered = alerts.filter(a => {
    if (filter === 'toutes') return true;
    if (filter === 'non-lues') return !a.read;
    return a.sev === filter;
  });

  // Empty state - locale-aware
  const emptyMsg = _LOCALE === 'en-GB'
    ? (alerts.length === 0
      ? { t: 'No alerts right now', s: 'All is fine: no rule has been triggered. Alerts will appear here automatically.' }
      : { t: 'No alerts for this filter', s: 'Try another filter, "All" shows the complete history.' })
    : (alerts.length === 0
      ? { t: 'Aucune alerte pour le moment', s: "Tout va bien : aucune règle ne s'est déclenchée. Les alertes apparaîtront ici automatiquement." }
      : { t: 'Aucune alerte pour ce filtre', s: "Essayez un autre filtre, « Toutes » affiche l'historique complet." });
  alertList.innerHTML = (filtered.length === 0
    ? `<div class="empty-state">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        <div class="es-title">${emptyMsg.t}</div>
        <div class="es-sub">${emptyMsg.s}</div>
      </div>`
    : '') + filtered.map(a => `<div class="alert-item${a.read ? ' dismissed' : ''}">
    <div class="abar" style="background:${BAR_COLOR[a.sev]}" aria-hidden="true"></div>
    <div class="a-body">
      <div class="a-type">${esc(a.type)}</div>
      <div class="a-msg">${esc(a.msg)}</div>
      <div class="a-foot">
        <span class="a-time">${esc(a.time)}${a.capteur ? ` · <span class="a-capteur">${esc(a.capteur)}</span>` : ''}</span>
        <div class="a-foot-meta">
          <span class="sev-badge ${SEV_CLASS[a.sev]}">${_LOCALE === 'en-GB' ? { crit: 'Critical', warn: 'Warning', info: 'Info' }[a.sev] : SEV_LABEL[a.sev]}</span>
          ${a.read ? '' : `<button class="dismiss-btn" type="button" data-id="${esc(String(a.id))}" aria-label="${_LOCALE === 'en-GB' ? 'Mark as read' : 'Marquer cette alerte comme lue'}">${_LOCALE === 'en-GB' ? '&#10003; Mark as read' : '&#10003; Marquer comme lue'}</button>`}
        </div>
      </div>
    </div>
  </div>`).join('');
}

function dismissAlert(id) {
  // Optimiste MAIS honnête : si le serveur refuse, on ANNULE et on le dit.
  alertState.alerts = alertState.alerts.map(x => String(x.id) === String(id) ? Object.assign({}, x, { read: true }) : x);
  renderAlertes();
  fetchWithAuth(`/api/alertes/${id}/lire/`, { method: 'PATCH' })
    .catch(err => {
      console.error(err);
      alertState.alerts = alertState.alerts.map(x => String(x.id) === String(id) ? Object.assign({}, x, { read: false }) : x);
      renderAlertes();
      showAlertFeedback(t('Échec, l’alerte n’a pas pu être marquée comme lue. Réessayez.'), true);
    });
}

if (filterBar) filterBar.addEventListener('click', e => {
  const btn = e.target.closest('.fpill');
  if (!btn) return;
  alertState.filter = btn.dataset.filter;
  renderAlertes();
});
if (alertList) alertList.addEventListener('click', e => {
  const btn = e.target.closest('.dismiss-btn');
  if (btn) dismissAlert(btn.dataset.id);
});
if (markAllBtn) markAllBtn.addEventListener('click', () => {
  const nonLues = alertState.alerts.filter(a => !a.read);
  if (nonLues.length === 0) return;
  const idsAvant = new Set(nonLues.map(a => String(a.id)));
  alertState.alerts = alertState.alerts.map(a => a.read ? a : Object.assign({}, a, { read: true }));
  renderAlertes();
  // Endpoint bulk (au lieu de N requêtes individuelles), rollback honnête sur échec.
  fetchWithAuth('/api/alertes/tout-lire/', { method: 'POST' })
    .then(() => {
      const fbText = window.AOCEDA_LANG === 'en'
        ? `${idsAvant.size} alert${idsAvant.size > 1 ? 's' : ''} marked as read.`
        : `${idsAvant.size} alerte${idsAvant.size > 1 ? 's' : ''} marquée${idsAvant.size > 1 ? 's' : ''} comme lue${idsAvant.size > 1 ? 's' : ''}.`;
      showAlertFeedback(fbText);
    })
    .catch(err => {
      console.error(err);
      alertState.alerts = alertState.alerts.map(a => idsAvant.has(String(a.id)) ? Object.assign({}, a, { read: false }) : a);
      renderAlertes();
      showAlertFeedback(t('Échec, les alertes n’ont pas pu être marquées comme lues. Réessayez.'), true);
    });
});

// CTA du bandeau « créer une règle » → ouvre l'onglet Configuration (la vraie création)
const gotoConfigBtn = document.getElementById('goto-config-btn');
if (gotoConfigBtn) gotoConfigBtn.addEventListener('click', () => setTab('config'));

function initAlertes() {
  alertState.filter = 'toutes';
  alertState.alerts = [];
  renderAlertes();
  fetchWithAuth('/api/alertes/')
    .then(data => {
      // Données 100 % réelles depuis /api/alertes/ (liste vide = état vide honnête).
      alertState.alerts = window.AOCEDA.asList(data).map(mapApiAlert);
      renderAlertes();
    })
    .catch(err => console.error(err));
}

/* ════════════════ Onglet « Configuration » ════════════════
   Deux niveaux, distincts et honnêtes :
   • Règles PAR CAPTEUR (seuil de puissance + surveillance nocturne) : éditées en
     CRUD via la modale (Créer / Modifier / Supprimer). La liste « Vos règles de
     surveillance » en est le reflet direct.
   • Préférences GLOBALES du compte (canaux e-mail + seuil crédit prépayé) :
     enregistrées par le bouton « Enregistrer les préférences » plus bas.
   ════════════════════════════════════════════════════════════ */
const CFG_DEFAULTS = { creditSeuil: 10000, emailOn: true, pushOn: false };
const cfg = Object.assign({}, CFG_DEFAULTS);
const cfgEls = {
  creditCard: document.getElementById('cfg-credit-card'),
  creditRange: document.getElementById('cfg-credit-range'),
  creditVal: document.getElementById('cfg-credit-val'),
  emailToggle: document.getElementById('cfg-email-toggle'),
  emailField: document.getElementById('cfg-email-field'),
  emailDisplay: document.getElementById('cfg-email-display'),
  pushToggle: document.getElementById('cfg-push-toggle'),
  pushInfo: document.getElementById('cfg-push-info'),
  save: document.getElementById('cfg-save'),
  saved: document.getElementById('cfg-saved'),
  loading: document.getElementById('cfg-loading'),
};

function setToggle(el, on) { if (!el) return; el.classList.toggle('on', on); el.setAttribute('aria-checked', on ? 'true' : 'false'); }
function sliderGradient(pct) { return `linear-gradient(to right,var(--ac) 0%,var(--ac) ${pct}%,var(--bd-d) ${pct}%,var(--bd-d) 100%)`; }

/* Rendu des PRÉFÉRENCES GLOBALES uniquement (crédit + canaux). Les règles par
   capteur ne sont plus dans ce formulaire, elles vivent dans la modale. */
function renderConfig() {
  const pctC = ((cfg.creditSeuil - 500) / (20000 - 500)) * 100;

  // Carte crédit prépayé : visible UNIQUEMENT pour un compteur prépayé confirmé.
  if (cfgEls.creditCard) cfgEls.creditCard.style.display = cfgServer.isPrepaid ? '' : 'none';
  if (cfgEls.creditRange) { cfgEls.creditRange.value = cfg.creditSeuil; cfgEls.creditRange.style.background = sliderGradient(pctC); }
  if (cfgEls.creditVal) cfgEls.creditVal.textContent = `${cfg.creditSeuil.toLocaleString('fr-FR')} FCFA`;

  setToggle(cfgEls.emailToggle, cfg.emailOn);
  if (cfgEls.emailField) cfgEls.emailField.style.display = cfg.emailOn ? '' : 'none';
  // Notifications push : non déployées (pas de Service Worker) → lecture seule honnête.
  if (cfgEls.pushToggle) {
    cfgEls.pushToggle.setAttribute('aria-disabled', 'true');
    cfgEls.pushToggle.style.opacity = '0.45';
    cfgEls.pushToggle.style.cursor = 'not-allowed';
    cfgEls.pushToggle.title = t('Bientôt disponible');
  }
  if (cfgEls.pushInfo) {
    cfgEls.pushInfo.style.display = '';
    cfgEls.pushInfo.textContent = t('Notifications push, bientôt disponibles.');
    cfgEls.pushInfo.style.color = 'var(--tx-m)';
    cfgEls.pushInfo.style.fontSize = '0.82rem';
  }
}

/* Interrupteur role=switch générique : souris + clavier (Entrée / Espace). */
function bindSwitchOn(el, onToggle) {
  if (!el) return;
  el.addEventListener('click', onToggle);
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); onToggle(); }
  });
}
bindSwitchOn(cfgEls.emailToggle, () => { cfg.emailOn = !cfg.emailOn; renderConfig(); });
// pushToggle n'est PAS branché (fonctionnalité absente, pas de Service Worker)
if (cfgEls.creditRange) cfgEls.creditRange.addEventListener('input', e => { cfg.creditSeuil = +e.target.value; renderConfig(); });

/* État serveur : capteurs + règles + préférences compte. isPrepaid gouverne la
   visibilité de la carte crédit (un postpayé n'a pas de crédit rechargeable). */
const cfgServer = { sensors: [], regles: [], notifEmail: true, isPrepaid: false };

/* Enregistre les PRÉFÉRENCES GLOBALES (e-mail + seuil crédit si prépayé). Les
   règles par capteur passent par la modale, plus par ce bouton. */
function saveConfig() {
  if (!cfgEls.save) return;
  cfgEls.save.disabled = true;
  cfgEls.save.dataset.label = cfgEls.save.dataset.label || cfgEls.save.textContent;
  cfgEls.save.textContent = t('Enregistrement…');
  if (cfgEls.saved) cfgEls.saved.style.display = 'none';

  const profilBody = { notifEmail: cfg.emailOn };
  if (cfgServer.isPrepaid) profilBody.seuilCreditBas_FCFA = cfg.creditSeuil;

  fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify(profilBody) })
    .then(() => {
      if (cfgEls.saved) {
        cfgEls.saved.textContent = t('Préférences de notification enregistrées.');
        cfgEls.saved.classList.remove('err');
        cfgEls.saved.style.display = '';
        setTimeout(() => { cfgEls.saved.style.display = 'none'; }, 6000);
      }
      loadConfigFromServer();
    })
    .catch(err => {
      console.error(err);
      if (cfgEls.saved) {
        cfgEls.saved.textContent = t('Échec de l’enregistrement (erreur réseau), vos réglages n’ont pas été modifiés. Réessayez.');
        cfgEls.saved.classList.add('err');
        cfgEls.saved.style.display = '';
      }
    })
    .finally(() => {
      cfgEls.save.disabled = false;
      cfgEls.save.textContent = cfgEls.save.dataset.label || t('Enregistrer les préférences');
    });
}
if (cfgEls.save) cfgEls.save.addEventListener('click', saveConfig);

/* Charge la configuration réelle (capteurs, règles, préférences compte). */
function loadConfigFromServer() {
  Promise.all([
    fetchWithAuth('/api/users/me/').catch(() => null),
    fetchWithAuth('/api/sensors/').catch(() => []),
    fetchWithAuth('/api/regles/').catch(() => []),
  ]).then(([me, sensors, regles]) => {
    cfgServer.sensors = window.AOCEDA.asList(sensors);
    cfgServer.regles = window.AOCEDA.asList(regles);
    cfgServer.isPrepaid = !!(me && me.typeCompteur === 'prepaye');
    if (me) {
      cfg.emailOn = me.notifEmail !== false;
      cfgServer.notifEmail = cfg.emailOn;
      if (cfgEls.emailDisplay) cfgEls.emailDisplay.textContent = me.email || '—';
      const sc = Number(me.seuilCreditBas_FCFA);
      if (me.seuilCreditBas_FCFA != null && sc > 0) cfg.creditSeuil = sc;
    }
    renderRulesOverview();   // la liste reflète TOUJOURS l'état serveur relu
    if (cfgEls.loading) cfgEls.loading.style.display = 'none';
    if (cfgEls.save) cfgEls.save.disabled = false;
    renderConfig();
  });
}

/* Feedback transitoire sous la liste des règles (création/modif/suppression). */
let rulesFeedbackTimer = null;
function showRulesFeedback(msg, isError) {
  const el = document.getElementById('rules-feedback');
  if (!el) return;
  el.textContent = msg;
  el.className = 'rules-feedback show' + (isError ? ' err' : '');
  clearTimeout(rulesFeedbackTimer);
  rulesFeedbackTimer = setTimeout(() => { el.className = 'rules-feedback'; el.textContent = ''; }, 6000);
}

/* ── Liste « Vos configurations d'alerte » : UNE ligne par configuration (règle).
   Un même capteur peut apparaître sur plusieurs lignes (configs distinctes). ── */
function renderRulesOverview() {
  const list = document.getElementById('rules-list');
  const countEl = document.getElementById('rules-count');
  const uncoveredEl = document.getElementById('rules-uncovered');
  const createBtn = document.getElementById('rules-create-btn');
  if (!list) return;

  const nbTot = cfgServer.sensors.length;
  const regles = cfgServer.regles;
  // Pas de capteur → rien à configurer : on masque le bouton Créer (honnête).
  if (createBtn) createBtn.style.display = nbTot === 0 ? 'none' : '';

  if (nbTot === 0) {
    list.innerHTML = `<div class="rules-empty">${t("Aucun capteur associé à votre compte pour le moment. Vos configurations apparaîtront ici dès qu'un capteur sera installé par votre technicien.")}</div>`;
    if (countEl) countEl.textContent = '';
    if (uncoveredEl) uncoveredEl.textContent = '';
    return;
  }

  if (regles.length === 0) {
    list.innerHTML = `<div class="rules-empty">${t("Aucune configuration pour le moment. Cliquez sur « Créer une configuration » pour surveiller un capteur.")}</div>`;
    if (countEl) countEl.textContent = t('0 configuration');
  } else {
    if (countEl) {
      const configWord = regles.length > 1 ? t('configurations') : t('configuration');
      countEl.textContent = `${regles.length} ${configWord}`;
    }
    list.innerHTML = regles.map(r => {
      const capteurNom = r.capteur_nom || (cfgServer.sensors.find(s => String(s.id) === String(r.capteur)) || {}).nom || t('Capteur');
      const p = Math.round(Number(r.puissanceMax_W)) || 0;
      const actif = p > 0 && p < 100000;
      const seuilHtml = actif
        ? `<span class="rchip rc-on">${p.toLocaleString('fr-FR')} W</span>`
        : `<span class="rchip rc-off">${t('Désactivé')}</span>`;
      const nuitHtml = r.surveilleNuit
        ? `<span class="rchip rc-on">${esc(String(r['heureDébutNuit'] || '00:00').slice(0, 5).replace(':', 'h'))} – ${esc(String(r['heureFinNuit'] || '05:00').slice(0, 5).replace(':', 'h'))}</span>`
        : `<span class="rchip rc-off">${t('Désactivée')}</span>`;
      const nuitDeriveHtml = (r.surveilleNuit && actif) ? `${Math.max(50, Math.round(p * 0.1)).toLocaleString('fr-FR')} W` : (r.surveilleNuit ? '50 W' : '—');
      return `<div class="rule-row">
        <span class="rule-capteur">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
          <span class="rule-config-txt"><span class="rule-config-nom">${esc(r.nom || t('Configuration'))}</span><span class="rule-config-capteur">${esc(capteurNom)}</span></span>
        </span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Seuil puissance')}</span>${seuilHtml}</span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Surveillance nuit')}</span>${nuitHtml}</span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Seuil nuit (auto)')}</span><span class="rule-derive">${nuitDeriveHtml}</span></span>
        <button class="rule-edit-btn" type="button" data-rule="${esc(String(r.id))}">${t('Modifier')}</button>
      </div>`;
    }).join('');
  }

  // Capteurs sans AUCUNE configuration : information honnête, non bloquante.
  if (uncoveredEl) {
    const uncovered = cfgServer.sensors.filter(s => !regles.some(r => String(r.capteur) === String(s.id)));
    if (uncovered.length) {
      const listNames = uncovered.map(s => s.nom || t('Capteur')).join(', ');
      uncoveredEl.textContent = window.AOCEDA_LANG === 'en'
        ? `Not configured: ${listNames}, not monitored until a configuration targets them.`
        : `Sans configuration : ${listNames}, non surveillé${uncovered.length > 1 ? 's' : ''} tant qu'aucune configuration ne le vise.`;
    } else {
      uncoveredEl.textContent = '';
    }
  }
}

/* ════════════════ Modale d'édition d'une règle (CRUD par capteur) ════════════════ */
const rm = {
  overlay: document.getElementById('rule-modal'),
  mode: document.getElementById('rm-mode'),
  title: document.getElementById('rm-capteur'),   // titre = nom vivant de la config
  nom: document.getElementById('rm-nom'),
  capteurSelect: document.getElementById('rm-capteur-select'),
  puissanceToggle: document.getElementById('rm-puissance-toggle'),
  puissanceGroup: document.getElementById('rm-puissance-group'),
  puissanceRange: document.getElementById('rm-puissance-range'),
  puissanceVal: document.getElementById('rm-puissance-val'),
  nuitToggle: document.getElementById('rm-nuit-toggle'),
  nuitSub: document.getElementById('rm-nuit-sub'),
  nuitDerive: document.getElementById('rm-nuit-derive'),
  heureDebut: document.getElementById('rm-heure-debut'),
  heureFin: document.getElementById('rm-heure-fin'),
  foot: document.getElementById('rm-foot'),
  delete: document.getElementById('rm-delete'),
  cancel: document.getElementById('rm-cancel'),
  save: document.getElementById('rm-save'),
  close: document.getElementById('rm-close'),
  confirm: document.getElementById('rm-confirm'),
  confirmCancel: document.getElementById('rm-confirm-cancel'),
  confirmDelete: document.getElementById('rm-confirm-delete'),
  msg: document.getElementById('rm-msg'),
};
// État de la configuration en cours d'édition (indépendant des préférences globales).
const mstate = { ruleId: null, nom: '', sensorId: null, puissance: 2000, puissanceOn: true, nuitOn: true, heureDebut: '00:00', heureFin: '05:00' };

function rmTitleText() { return (mstate.nom || '').trim() || (mstate.ruleId ? t('Configuration') : t('Nouvelle configuration')); }

function rmRender() {
  const pct = ((mstate.puissance - 500) / (5000 - 500)) * 100;
  if (rm.nom) rm.nom.value = mstate.nom;
  if (rm.capteurSelect) rm.capteurSelect.value = mstate.sensorId || '';
  if (rm.title) rm.title.textContent = rmTitleText();
  setToggle(rm.puissanceToggle, mstate.puissanceOn);
  rm.puissanceGroup.style.display = mstate.puissanceOn ? '' : 'none';
  rm.puissanceRange.value = mstate.puissance;
  rm.puissanceRange.style.background = sliderGradient(pct);
  rm.puissanceVal.textContent = `${mstate.puissance.toLocaleString(_LOCALE)} W`;
  setToggle(rm.nuitToggle, mstate.nuitOn);
  rm.nuitSub.style.display = mstate.nuitOn ? '' : 'none';
  // Seuil nocturne dérivé (formule moteur : 10 % du seuil, min 50 W).
  const derive = mstate.puissanceOn ? Math.max(50, Math.round(mstate.puissance * 0.1)) : 50;
  rm.nuitDerive.textContent = `${derive.toLocaleString(_LOCALE)} W (${t('automatique')})`;
  rm.heureDebut.value = mstate.heureDebut;
  rm.heureFin.value = mstate.heureFin;
}

/* Peuple le sélecteur de capteur de la modale à partir des capteurs réels. */
function rmPopulateSensors() {
  if (!rm.capteurSelect) return;
  rm.capteurSelect.innerHTML = cfgServer.sensors
    .map(s => `<option value="${esc(String(s.id))}">${esc(s.nom || 'Capteur')}</option>`).join('');
}

function rmHideConfirm() { if (rm.confirm) rm.confirm.hidden = true; if (rm.foot) rm.foot.hidden = false; }
function rmShowConfirm() { if (rm.confirm) rm.confirm.hidden = false; if (rm.foot) rm.foot.hidden = true; }

/* Affiche la modale (isEdit gouverne libellés + bouton Supprimer). */
function rmShow(isEdit, focusEl) {
  if (!rm.overlay) return;
  rmPopulateSensors();
  rm.mode.textContent = isEdit ? t('Modifier la configuration') : t('Nouvelle configuration');
  rm.save.textContent = isEdit ? t('Enregistrer') : t('Créer la configuration');
  rm.save.dataset.label = rm.save.textContent;
  rm.delete.style.display = isEdit ? '' : 'none';
  rmHideConfirm();
  rm.msg.textContent = ''; rm.msg.className = 'rm-msg';
  rmRender();
  rm.overlay.hidden = false;
  requestAnimationFrame(() => rm.overlay.classList.add('open'));
  document.body.classList.add('rm-lock');
  setTimeout(() => { try { (focusEl || rm.save).focus(); } catch (e) {} }, 60);
}

/* Édition d'une configuration existante (repérée par son id de règle). */
function rmOpenEdit(ruleId) {
  const r = cfgServer.regles.find(x => String(x.id) === String(ruleId));
  if (!r || !rm.overlay) return;
  mstate.ruleId = r.id;
  mstate.nom = r.nom || 'Configuration';
  mstate.sensorId = String(r.capteur);
  const p = Math.round(Number(r.puissanceMax_W)) || 0;
  mstate.puissanceOn = p > 0 && p < 100000;
  mstate.puissance = mstate.puissanceOn ? p : 2000;
  mstate.nuitOn = !!r.surveilleNuit;
  mstate.heureDebut = String(r['heureDébutNuit'] || '00:00').slice(0, 5);
  mstate.heureFin = String(r['heureFinNuit'] || '05:00').slice(0, 5);
  rmShow(true);
}

/* Création d'une nouvelle configuration (capteur par défaut = le premier). */
function rmOpenCreate() {
  if (!rm.overlay || cfgServer.sensors.length === 0) return;
  mstate.ruleId = null;
  mstate.nom = '';
  mstate.sensorId = String(cfgServer.sensors[0].id);
  mstate.puissanceOn = true; mstate.puissance = 2000; mstate.nuitOn = true;
  mstate.heureDebut = '00:00'; mstate.heureFin = '05:00';
  rmShow(false, rm.nom);
}

function rmClose() {
  if (!rm.overlay) return;
  rm.overlay.classList.remove('open');
  document.body.classList.remove('rm-lock');
  setTimeout(() => { rm.overlay.hidden = true; }, 200);
}

function rmSave() {
  // Capteur obligatoire (une config sans capteur ne mesurerait rien de réel).
  if (!mstate.sensorId) {
    rm.msg.textContent = t('Choisissez un capteur à surveiller.');
    rm.msg.className = 'rm-msg err';
    return;
  }
  rm.save.disabled = true;
  const lbl = rm.save.dataset.label || rm.save.textContent;
  rm.save.textContent = t('Enregistrement…');
  const nom = (mstate.nom || '').trim() || t('Configuration');
  const hd = mstate.heureDebut.length === 5 ? mstate.heureDebut + ':00' : mstate.heureDebut;
  const hf = mstate.heureFin.length === 5 ? mstate.heureFin + ':00' : mstate.heureFin;
  const body = {
    nom: nom,
    capteur: mstate.sensorId,
    // Sentinelle 100000 W = « désactivé » (aligné sur le back / le moteur).
    puissanceMax_W: mstate.puissanceOn ? mstate.puissance : 100000,
    surveilleNuit: mstate.nuitOn,
    'heureDébutNuit': hd,
    'heureFinNuit': hf,
  };
  const wasCreate = !mstate.ruleId;
  const req = mstate.ruleId
    ? fetchWithAuth(`/api/regles/${mstate.ruleId}/`, { method: 'PUT', body: JSON.stringify(body) })
    : fetchWithAuth('/api/regles/', { method: 'POST', body: JSON.stringify(body) });
  req.then(() => {
    rmClose();
    const feedbackMsg = wasCreate
      ? (window.AOCEDA_LANG === 'en' ? `Configuration "${nom}" created.` : `Configuration « ${nom} » créée.`)
      : (window.AOCEDA_LANG === 'en' ? `Configuration "${nom}" updated.` : `Configuration « ${nom} » mise à jour.`);
    showRulesFeedback(feedbackMsg, false);
    loadConfigFromServer();
  }).catch(err => {
    console.error(err);
    rm.msg.textContent = t('Échec de l’enregistrement') + ' (' + (err && err.message ? err.message : t('réseau')) + '). ' + t('Réessayez.');
    rm.msg.className = 'rm-msg err';
  }).finally(() => {
    rm.save.disabled = false;
    rm.save.textContent = lbl;
  });
}

function rmDelete() {
  if (!mstate.ruleId) { rmHideConfirm(); return; }
  rm.confirmDelete.disabled = true;
  rm.confirmDelete.textContent = t('Suppression…');
  const nom = (mstate.nom || '').trim() || t('Configuration');
  fetchWithAuth(`/api/regles/${mstate.ruleId}/`, { method: 'DELETE' })
    .then(() => {
      rmClose();
      const feedbackMsg = window.AOCEDA_LANG === 'en' ? `Configuration "${nom}" deleted.` : `Configuration « ${nom} » supprimée.`;
      showRulesFeedback(feedbackMsg, false);
      loadConfigFromServer();
    })
    .catch(err => {
      console.error(err);
      rmHideConfirm();
      rm.msg.textContent = t('Échec de la suppression') + ' (' + (err && err.message ? err.message : t('réseau')) + '). ' + t('Réessayez.');
      rm.msg.className = 'rm-msg err';
    })
    .finally(() => {
      rm.confirmDelete.disabled = false;
      rm.confirmDelete.textContent = t('Supprimer');
    });
}

// Branchements modale
if (rm.nom) rm.nom.addEventListener('input', e => { mstate.nom = e.target.value; if (rm.title) rm.title.textContent = rmTitleText(); });
if (rm.capteurSelect) rm.capteurSelect.addEventListener('change', e => { mstate.sensorId = e.target.value; });
bindSwitchOn(rm.puissanceToggle, () => { mstate.puissanceOn = !mstate.puissanceOn; rmRender(); });
bindSwitchOn(rm.nuitToggle, () => { mstate.nuitOn = !mstate.nuitOn; rmRender(); });
if (rm.puissanceRange) rm.puissanceRange.addEventListener('input', e => { mstate.puissance = +e.target.value; rmRender(); });
if (rm.heureDebut) rm.heureDebut.addEventListener('change', e => { mstate.heureDebut = e.target.value; });
if (rm.heureFin) rm.heureFin.addEventListener('change', e => { mstate.heureFin = e.target.value; });
if (rm.save) rm.save.addEventListener('click', rmSave);
if (rm.cancel) rm.cancel.addEventListener('click', rmClose);
if (rm.close) rm.close.addEventListener('click', rmClose);
if (rm.delete) rm.delete.addEventListener('click', rmShowConfirm);
if (rm.confirmCancel) rm.confirmCancel.addEventListener('click', rmHideConfirm);
if (rm.confirmDelete) rm.confirmDelete.addEventListener('click', rmDelete);
if (rm.overlay) rm.overlay.addEventListener('click', e => { if (e.target === rm.overlay) rmClose(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && rm.overlay && !rm.overlay.hidden) rmClose(); });

// « Créer une configuration » → modale en mode création.
const rulesCreateBtn = document.getElementById('rules-create-btn');
if (rulesCreateBtn) rulesCreateBtn.addEventListener('click', () => rmOpenCreate());

// « Modifier » d'une ligne → ouvre la modale sur CETTE configuration (par id de règle).
document.addEventListener('click', e => {
  const btn = e.target.closest('.rule-edit-btn');
  if (!btn) return;
  rmOpenEdit(btn.dataset.rule);
});

function initConfig() {
  // Anti-flicker : on affiche l'état courant + un indicateur, puis on relit le serveur.
  if (cfgEls.saved) cfgEls.saved.style.display = 'none';
  if (cfgEls.loading) cfgEls.loading.style.display = '';
  if (cfgEls.save) cfgEls.save.disabled = true;
  renderConfig();
  loadConfigFromServer();
}

/* ════════════════ Démarrage ════════════════ */
applyTheme();
renderConfig();
setTab(hashToTab(window.location.hash), { fromHash: true });
