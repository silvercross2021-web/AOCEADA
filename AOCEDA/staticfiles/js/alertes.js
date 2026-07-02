'use strict';
/* ════════════════════════════════════════════════════════════
   AOCEDA — Alertes & Configuration (page dédiée)
   Deux onglets : « Mes alertes » et « Configuration ».
   ════════════════════════════════════════════════════════════ */

const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
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

function mapApiAlert(a) {
  const sevRaw = a['sévérité'] || a.severity || '';
  const sev = sevRaw === 'Critique' ? 'crit' : (sevRaw === 'Avertissement' ? 'warn' : 'info');
  const d = a.createdAt ? new Date(a.createdAt) : new Date();
  const time = `${d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })} · ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }).replace(':', 'h')}`;
  return { id: a.id, type: (a.type || 'ALERTE').replace(/ /g, '_'), msg: a.message, time, sev, read: !!a.lue };
}

function renderAlertSummary() {
  const a = alertState.alerts;
  const unread = a.filter(x => !x.read).length;
  // Tuiles = alertes ACTIVES (non lues), cohérent avec « Non lues ». Après « Tout
  // marquer lu », Critiques/Avertissements tombent à 0 comme il se doit.
  const crit = a.filter(x => x.sev === 'crit' && !x.read).length;
  const warn = a.filter(x => x.sev === 'warn' && !x.read).length;
  if (alertSummary) alertSummary.innerHTML = `
    <div class="asum"><div class="asum-ico unread">${ICO_BELL}</div><div><div class="asum-val">${unread}</div><div class="asum-lbl">Non lue${unread > 1 ? 's' : ''}</div></div></div>
    <div class="asum"><div class="asum-ico crit">${ICO_CRIT}</div><div><div class="asum-val">${crit}</div><div class="asum-lbl">Critique${crit > 1 ? 's' : ''}</div></div></div>
    <div class="asum"><div class="asum-ico warn">${ICO_WARN}</div><div><div class="asum-val">${warn}</div><div class="asum-lbl">Avertissement${warn > 1 ? 's' : ''}</div></div></div>`;
  if (markAllBtn) markAllBtn.disabled = unread === 0;
  if (tabAlertCount) {
    tabAlertCount.textContent = String(unread);
    tabAlertCount.style.display = unread > 0 ? '' : 'none';
  }
}

function renderAlertes() {
  const { filter, alerts } = alertState;
  renderAlertSummary();

  filterBar.innerHTML = ALERT_FILTERS.map(([k, l]) =>
    `<button class="fpill${filter === k ? ' active' : ''}" type="button" data-filter="${k}">${l}${k === 'toutes' ? ` (${alerts.length})` : ''}</button>`
  ).join('');

  const filtered = alerts.filter(a => {
    if (filter === 'toutes') return true;
    if (filter === 'non-lues') return !a.read;
    return a.sev === filter;
  });

  alertList.innerHTML = (filtered.length === 0
    ? `<div class="empty-state">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        <div class="es-title">Aucune alerte</div>
        <div class="es-sub">Aucune alerte ne correspond au filtre sélectionné.</div>
      </div>`
    : '') + filtered.map(a => `<div class="alert-item${a.read ? ' dismissed' : ''}">
    <div class="abar" style="background:${BAR_COLOR[a.sev]}" aria-hidden="true"></div>
    <div class="a-body">
      <div class="a-type">${esc(a.type)}</div>
      <div class="a-msg">${esc(a.msg)}</div>
      <div class="a-foot">
        <span class="a-time">${esc(a.time)}</span>
        <div class="a-foot-meta">
          <span class="sev-badge ${SEV_CLASS[a.sev]}">${SEV_LABEL[a.sev]}</span>
          ${a.read ? '' : `<button class="dismiss-btn" type="button" data-id="${esc(String(a.id))}" aria-label="Marquer cette alerte comme lue">✓ Marquer comme lue</button>`}
        </div>
      </div>
    </div>
  </div>`).join('');
}

function dismissAlert(id) {
  alertState.alerts = alertState.alerts.map(x => String(x.id) === String(id) ? Object.assign({}, x, { read: true }) : x);
  renderAlertes();
  fetchWithAuth(`/api/alertes/${id}/lire/`, { method: 'PATCH' }).catch(err => console.error(err));
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
  alertState.alerts = alertState.alerts.map(a => a.read ? a : Object.assign({}, a, { read: true }));
  renderAlertes();
  // Endpoint bulk (au lieu de N requêtes individuelles)
  fetchWithAuth('/api/alertes/tout-lire/', { method: 'POST' }).catch(err => console.error(err));
});

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

/* ════════════════ Onglet « Configuration » ════════════════ */
const CFG_DEFAULTS = {
  puissance: 2000, puissanceOn: true,
  nuitOn: true, nuitSeuil: 800, heureDebut: '00:00', heureFin: '05:00',
  creditSeuil: 2000, emailOn: true, pushOn: false,
};
const cfg = Object.assign({}, CFG_DEFAULTS);
const cfgEls = {
  puissanceToggle: document.getElementById('cfg-puissance-toggle'),
  puissanceGroup: document.getElementById('cfg-puissance-group'),
  puissanceRange: document.getElementById('cfg-puissance-range'),
  puissanceVal: document.getElementById('cfg-puissance-val'),
  nuitToggle: document.getElementById('cfg-nuit-toggle'),
  nuitSub: document.getElementById('cfg-nuit-sub'),
  nuitRange: document.getElementById('cfg-nuit-range'),
  nuitVal: document.getElementById('cfg-nuit-val'),
  heureDebut: document.getElementById('cfg-heure-debut'),
  heureFin: document.getElementById('cfg-heure-fin'),
  creditCard: document.getElementById('cfg-credit-card'),
  creditRange: document.getElementById('cfg-credit-range'),
  creditVal: document.getElementById('cfg-credit-val'),
  emailToggle: document.getElementById('cfg-email-toggle'),
  emailField: document.getElementById('cfg-email-field'),
  emailInput: document.getElementById('cfg-email-input'),
  pushToggle: document.getElementById('cfg-push-toggle'),
  pushInfo: document.getElementById('cfg-push-info'),
  save: document.getElementById('cfg-save'),
  saved: document.getElementById('cfg-saved'),
};

function setToggle(el, on) { if (!el) return; el.classList.toggle('on', on); el.setAttribute('aria-checked', on ? 'true' : 'false'); }
function sliderGradient(pct) { return `linear-gradient(to right,var(--ac) 0%,var(--ac) ${pct}%,var(--bd-d) ${pct}%,var(--bd-d) 100%)`; }

function renderConfig() {
  const pctP = ((cfg.puissance - 500) / (5000 - 500)) * 100;
  const pctN = ((cfg.nuitSeuil - 100) / (3000 - 100)) * 100;
  const pctC = ((cfg.creditSeuil - 500) / (10000 - 500)) * 100;

  setToggle(cfgEls.puissanceToggle, cfg.puissanceOn);
  cfgEls.puissanceGroup.style.display = cfg.puissanceOn ? '' : 'none';
  cfgEls.puissanceRange.value = cfg.puissance;
  cfgEls.puissanceRange.style.background = sliderGradient(pctP);
  cfgEls.puissanceVal.textContent = `${cfg.puissance.toLocaleString('fr-FR')} W`;

  setToggle(cfgEls.nuitToggle, cfg.nuitOn);
  cfgEls.nuitSub.style.display = cfg.nuitOn ? '' : 'none';
  cfgEls.nuitRange.value = cfg.nuitSeuil;
  cfgEls.nuitRange.style.background = sliderGradient(pctN);
  cfgEls.nuitVal.textContent = `${cfg.nuitSeuil} W`;
  cfgEls.heureDebut.value = cfg.heureDebut;
  cfgEls.heureFin.value = cfg.heureFin;

  // Carte crédit prépayé : visible UNIQUEMENT pour un compteur prépayé confirmé.
  // Pour un postpayé, on la masque (elle serait inopérante et trompeuse).
  if (cfgEls.creditCard) cfgEls.creditCard.style.display = cfgServer.isPrepaid ? '' : 'none';
  cfgEls.creditRange.value = cfg.creditSeuil;
  cfgEls.creditRange.style.background = sliderGradient(pctC);
  cfgEls.creditVal.textContent = `${cfg.creditSeuil.toLocaleString('fr-FR')} FCFA`;

  setToggle(cfgEls.emailToggle, cfg.emailOn);
  cfgEls.emailField.style.display = cfg.emailOn ? '' : 'none';
  // Notifications push : fonctionnalité non encore déployée (pas de Service Worker).
  // Le toggle est affiché en lecture seule pour ne pas induire en erreur.
  if (cfgEls.pushToggle) {
    cfgEls.pushToggle.setAttribute('aria-disabled', 'true');
    cfgEls.pushToggle.style.opacity = '0.45';
    cfgEls.pushToggle.style.cursor = 'not-allowed';
    cfgEls.pushToggle.title = 'Bientôt disponible';
  }
  if (cfgEls.pushInfo) {
    cfgEls.pushInfo.style.display = '';
    cfgEls.pushInfo.textContent = 'Notifications push — bientôt disponibles.';
    cfgEls.pushInfo.style.color = 'var(--tx-m)';
    cfgEls.pushInfo.style.fontSize = '0.82rem';
  }
}

/* Interrupteurs role=switch : opérables souris ET clavier (Entrée / Espace).
   bindSwitch attache click + keydown et tient aria-checked à jour via renderConfig. */
function bindSwitch(el, key) {
  if (!el) return;
  const toggle = () => { cfg[key] = !cfg[key]; renderConfig(); };
  el.addEventListener('click', toggle);
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault(); // évite le défilement de la page sur Espace
      toggle();
    }
  });
}
bindSwitch(cfgEls.puissanceToggle, 'puissanceOn');
bindSwitch(cfgEls.nuitToggle, 'nuitOn');
bindSwitch(cfgEls.emailToggle, 'emailOn');
// pushToggle n'est PAS branché (fonctionnalité absente — pas de Service Worker)
if (cfgEls.puissanceRange) cfgEls.puissanceRange.addEventListener('input', e => { cfg.puissance = +e.target.value; renderConfig(); });
if (cfgEls.nuitRange) cfgEls.nuitRange.addEventListener('input', e => { cfg.nuitSeuil = +e.target.value; renderConfig(); });
if (cfgEls.creditRange) cfgEls.creditRange.addEventListener('input', e => { cfg.creditSeuil = +e.target.value; renderConfig(); });
if (cfgEls.heureDebut) cfgEls.heureDebut.addEventListener('change', e => { cfg.heureDebut = e.target.value; });
if (cfgEls.heureFin) cfgEls.heureFin.addEventListener('change', e => { cfg.heureFin = e.target.value; });
/* État serveur de la configuration : capteurs + règles + préférence e-mail.
   isPrepaid : type de compteur réel (référencé par le technicien). La carte
   « Alerte crédit prépayé » n'a de sens QUE pour un compteur prépayé — un
   postpayé n'a pas de crédit rechargeable (cf. credit_prepaye_info côté back
   qui renvoie None pour un postpayé). Défaut false → carte masquée. */
const cfgServer = { sensors: [], regles: [], notifEmail: true, isPrepaid: false };

function saveConfig() {
  if (!cfgEls.save) return;
  cfgEls.save.disabled = true;
  cfgEls.save.dataset.label = cfgEls.save.dataset.label || cfgEls.save.textContent;
  cfgEls.save.textContent = 'Enregistrement…';
  if (cfgEls.saved) cfgEls.saved.style.display = 'none';

  // 1) Préférences profil : e-mail toujours ; seuil d'alerte crédit UNIQUEMENT
  //    pour un compteur prépayé (ignoré par le back pour un postpayé — inutile
  //    d'écrire une valeur trompeuse).
  const profilBody = { notifEmail: cfg.emailOn };
  if (cfgServer.isPrepaid) profilBody.seuilCreditBas_FCFA = cfg.creditSeuil;
  const tasks = [
    fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify(profilBody) })
  ];

  // 2) Applique le seuil de puissance + surveillance nocturne à TOUS les capteurs
  const heureDebut = cfg.heureDebut.length === 5 ? cfg.heureDebut + ':00' : cfg.heureDebut;
  const heureFin = cfg.heureFin.length === 5 ? cfg.heureFin + ':00' : cfg.heureFin;
  cfgServer.sensors.forEach(s => {
    const regle = cfgServer.regles.find(r => r.capteur === s.id);
    const body = {
      capteur: s.id,
      puissanceMax_W: cfg.puissanceOn ? cfg.puissance : 100000,
      surveilleNuit: cfg.nuitOn,
      'heureDébutNuit': heureDebut,
      'heureFinNuit': heureFin,
    };
    tasks.push(regle && regle.id
      ? fetchWithAuth(`/api/regles/${regle.id}/`, { method: 'PUT', body: JSON.stringify(body) })
      : fetchWithAuth('/api/regles/', { method: 'POST', body: JSON.stringify(body) }));
  });

  Promise.all(tasks)
    .then(() => {
      if (cfgEls.saved) {
        cfgEls.saved.textContent = 'Préférences enregistrées';
        cfgEls.saved.style.display = '';
        setTimeout(() => { cfgEls.saved.style.display = 'none'; }, 4000);
      }
      loadConfigFromServer();
    })
    .catch(() => {
      if (cfgEls.saved) {
        cfgEls.saved.textContent = 'Échec de l’enregistrement';
        cfgEls.saved.style.display = '';
      }
    })
    .finally(() => {
      cfgEls.save.disabled = false;
      cfgEls.save.textContent = cfgEls.save.dataset.label || 'Enregistrer les préférences';
    });
}

if (cfgEls.save) cfgEls.save.addEventListener('click', saveConfig);

/* Charge la configuration réelle (capteurs, règles, préférence e-mail). */
function loadConfigFromServer() {
  Promise.all([
    fetchWithAuth('/api/users/me/').catch(() => null),
    fetchWithAuth('/api/sensors/').catch(() => []),
    fetchWithAuth('/api/regles/').catch(() => []),
  ]).then(([me, sensors, regles]) => {
    cfgServer.sensors = window.AOCEDA.asList(sensors);
    cfgServer.regles = window.AOCEDA.asList(regles);
    // Type de compteur réel (ClientSerializer expose typeCompteur, lecture seule).
    // Seul un prépayé CONFIRMÉ révèle la carte d'alerte crédit.
    cfgServer.isPrepaid = !!(me && me.typeCompteur === 'prepaye');
    if (me) {
      cfg.emailOn = me.notifEmail !== false;
      cfgServer.notifEmail = cfg.emailOn;
      if (cfgEls.emailInput) cfgEls.emailInput.value = me.email || '';
      if (me.seuilCreditBas_FCFA != null) cfg.creditSeuil = Number(me.seuilCreditBas_FCFA);
      if (cfgEls.creditRange) { cfgEls.creditRange.value = cfg.creditSeuil; }
    }
    // Pré-remplit depuis la première règle existante (réglage global simplifié)
    const ref = cfgServer.regles[0];
    if (ref) {
      cfg.puissance = Math.round(Number(ref.puissanceMax_W)) || cfg.puissance;
      cfg.puissanceOn = cfg.puissance < 100000;
      cfg.nuitOn = !!ref.surveilleNuit;
      if (ref['heureDébutNuit']) cfg.heureDebut = String(ref['heureDébutNuit']).slice(0, 5);
      if (ref['heureFinNuit']) cfg.heureFin = String(ref['heureFinNuit']).slice(0, 5);
    }
    renderConfig();
  });
}

function initConfig() {
  Object.assign(cfg, CFG_DEFAULTS);
  if (cfgEls.saved) cfgEls.saved.style.display = 'none';
  renderConfig();
  loadConfigFromServer();
}

/* ════════════════ Démarrage ════════════════ */
applyTheme();
renderConfig();
setTab(hashToTab(window.location.hash), { fromHash: true });
