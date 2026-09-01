'use strict';
/* ════════════════════════════════════════════════════════════
   AOCEDA, Espace Technicien
   JavaScript vanilla (ES2020), sans React/Babel
   ════════════════════════════════════════════════════════════ */

/* ── Garde d'authentification ── */
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* ── Helper fetch authentifié, délègue au shell (refresh JWT sur 401) ── */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
    return res.json().catch(() => null);
  });
}

/* ── Helper d'échappement HTML (pour innerHTML) ── */
function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

/* ── Téléchargement authentifié d'un fichier (PDF…) : Authorization requis →
   fetch → blob → lien temporaire, nom lu dans Content-Disposition ── */
function downloadFile(url, fallbackName) {
  return window.AOCEDA.authFetch(url)
    .then(res => {
      if (!res.ok) throw new Error('Téléchargement impossible');
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : (fallbackName || 'aoceda_document.pdf');
      return res.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => window.AOCEDA.downloadBlob(blob, filename));
}

/* QR code de configuration ESP32 : généré CÔTÉ SERVEUR (jamais un service tiers,
   la clé API du dispositif ne doit jamais transiter par une URL externe). Le SVG
   est injecté tel quel (pas d'<img>/objectURL nécessaire, plus simple). */
function loadQrConfig(dispositifId, ssid) {
  window.AOCEDA.authFetch(`/api/sensors/dispositifs/${dispositifId}/qr-config/?ssid=${encodeURIComponent(ssid || '')}`)
    .then(res => (res.ok ? res.text() : Promise.reject()))
    .then(svg => { const box = document.getElementById('qr-config-box'); if (box) box.innerHTML = svg; })
    .catch(() => {
      const box = document.getElementById('qr-config-box');
      if (box) box.innerHTML = '<span style="font-size:10px;color:var(--err)">QR indisponible</span>';
    });
}

/* L'espace technicien s'appuie uniquement sur les données réelles de l'API
   (dispositifs, capteurs, interventions, clients). Aucune donnée maquette :
   en l'absence de données, des états vides honnêtes sont affichés. */

const TYPE_LBL = { INSTALLATION: 'Installation nouvelle', CALIBRATION: 'Calibration requise', PANNE: 'Déclaration de panne', MAINTENANCE: 'Maintenance préventive', DIAGNOSTIC: 'Diagnostic & Audits' };
const STATUT_UI = { EN_ATTENTE: 'pending', EN_COURS: 'progress', TERMINEE: 'done' };
const ST_MAP = {
  online: { cl: 'st-online', lbl: 'En ligne' },
  offline: { cl: 'st-offline', lbl: 'Hors ligne' },
  delayed: { cl: 'st-delayed', lbl: 'Données différées' }
};
const S_MAP = {
  pending: { cl: 'is-pending', l: 'En attente' },
  progress: { cl: 'is-progress', l: 'En cours' },
  done: { cl: 'is-done', l: 'Terminée' }
};

/* Seuils de calibration PARTAGÉS (écart du coefficient Kcal par rapport à 1).
   Utilisés à la fois par la page Installations (compteur « Calibrations à faire »
   et badge) ET par la grille Calibration, afin que les deux vues classent un
   capteur de façon identique (fini l'incohérence « à calibrer » vs « OK »). */
const CALIB_WARN = 0.05;  // écart > 5 %  => à surveiller
const CALIB_CRIT = 0.10;  // écart > 10 % => critique

/* ── Icônes thème ── */
const ICON_MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';

/* ── État global ── */
const state = {
  theme: document.documentElement.getAttribute('data-theme') || 'light',
  tab: 'installations',
  section: 'installations',
  user: null,
  devices: null,        // dispositifs API (null = pas encore chargé)
  devicesLoaded: false,
  capteurs: [],
  clients: [],          // liste réelle des clients (pour le wizard d'installation)
  interventions: null,
  interventionsLoaded: false,
  filter: 'tous',
  search: '',
  interSearch: '',
  interFilter: 'tous',
  calibSearch: '',
  calibFilter: 'tous',
  journal: null,
  journalLoaded: false,
  journalSearch: '',
  journalUser: ''
};

/* Lignes affichées (pour retrouver un dispositif/intervention depuis un bouton) */
let instRows = [];
let interList = [];

/* ── Utilitaires dates ── */
function timeAgo(iso) {
  if (!iso) return '-';
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `il y a ${Math.round(diff)} s`;
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)} h`;
  return `il y a ${Math.round(diff / 86400)} j`;
}
function formatDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }) + ' ' +
    d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }).replace(':', 'h');
}

/* ════════════════════════ THÈME ════════════════════════ */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = state.theme === 'light' ? ICON_MOON : ICON_SUN;
}
function toggleTheme() {
  state.theme = window.AOCEDA.toggleTheme();
  applyTheme();
}

/* ════════════════════════ SECTION (sidebar nav) ════════════════════════ */

const SECTION_META = {
  installations: { title: 'Mes installations', sub: 'Supervision des dispositifs ESP32' },
  interventions:  { title: 'Interventions & pannes', sub: 'Déclarations de pannes et suivi des interventions' },
  calibration:    { title: 'Calibration', sub: 'Coefficients Kcal des capteurs' },
  clients:        { title: 'Mes clients', sub: 'Clients dont vous supervisez les installations' },
  journal:        { title: "Journal d'équipe", sub: 'Les actions des techniciens : qui a fait quoi, et quand' },
  parametres:     { title: 'Paramètres', sub: 'Profil, sécurité et apparence' }
};

function setSection(name) {
  state.section = name;
  state.tab = name; // alias legacy utilisé par renderInstallations()

  // Nav items sidebar
  document.querySelectorAll('.sidebar .nav-item[data-section]').forEach(b => {
    b.classList.toggle('active', b.dataset.section === name);
  });

  // Bottom-nav (mobile) + feuille « Plus » (items débordant la barre)
  const sheetSections = ['journal', 'parametres'];
  document.querySelectorAll('.bottom-nav .bn-item[data-section], .bn-sheet .bn-item[data-section]').forEach(b => {
    b.classList.toggle('active', b.dataset.section === name);
  });
  const moreBtn = document.getElementById('bn-more-btn');
  if (moreBtn) moreBtn.classList.toggle('active', sheetSections.includes(name));

  // Sections contenu
  const ids = ['installations', 'interventions', 'calibration', 'clients', 'journal', 'parametres'];
  ids.forEach(id => {
    const el = document.getElementById('section-' + id);
    if (el) el.style.display = id === name ? '' : 'none';
  });

  // Header dynamique
  const meta = SECTION_META[name] || { title: 'Espace Technicien', sub: '' };
  const titleEl = document.getElementById('tech-section-title');
  const subEl   = document.getElementById('tech-section-sub');
  if (titleEl) titleEl.textContent = meta.title;
  if (subEl)   subEl.textContent   = meta.sub;

  // Charger les données de la section si besoin
  if (name === 'interventions' && !state.interventionsLoaded) loadInterventions();
  if (name === 'calibration' && !state.devicesLoaded) loadInstallations();
  if (name === 'clients') renderClients();
  if (name === 'journal') loadJournalEquipe();
  if (name === 'parametres') loadUser();
}

/* Alias de compatibilité (modal wizard utilise state.tab comparaisons) */
function setTab(tab) { setSection(tab); }

/* Statut de connectivité d'un dispositif, PARTAGÉ par toutes les vues
   (Installations, Détails, Mes clients) pour un affichage cohérent partout.
   'delayed' = connecté mais dernière mesure > 10 min. */
function deviceStatus(d) {
  if (!d || !d.estConnecté) return 'offline';
  const caps = (state.capteurs || []).filter(c => c.dispositif === d.id);
  const lastLect = caps.map(c => c.derniereLecture).filter(Boolean).sort().pop();
  return (lastLect && (Date.now() - new Date(lastLect).getTime()) > 10 * 60 * 1000) ? 'delayed' : 'online';
}

/* ════════════════════════ INSTALLATIONS ════════════════════════ */
function computeRows() {
  if (!Array.isArray(state.devices)) return { usingApi: false, rows: [] };
  const rows = state.devices.map(d => {
    const caps = (state.capteurs || []).filter(c => c.dispositif === d.id);
    const lastLect = caps.map(c => c.derniereLecture).filter(Boolean).sort().pop();
    const needsCalib = caps.some(c => !c.derniereCalibration);
    return {
      id: d.id, raw: d, capteurs: caps,
      client: d.client_nom || d.client_email || 'Client',
      addr: d.adresse || (d.adresseIP ? `IP ${d.adresseIP}` : '-'),
      device: d.nom || d.numeroSerie || ('ESP32-' + String(d.id).replace(/-/g, '').slice(0, 7).toUpperCase()),
      fw: d.firmwareVersion || '-',
      status: deviceStatus(d),
      last: timeAgo(lastLect),
      calib: caps.length > 0 && needsCalib
    };
  });
  return { usingApi: true, rows };
}

function renderInstallations() {
  const { usingApi, rows } = computeRows();
  const search = state.search.toLowerCase();
  const filtered = rows.filter(d => {
    const matchSearch = !search || d.client.toLowerCase().includes(search) || d.device.toLowerCase().includes(search) || (d.addr && d.addr !== '-' && d.addr.toLowerCase().includes(search));
    const matchFilter = state.filter === 'tous' ||
      (state.filter === 'online' && d.status === 'online') ||
      (state.filter === 'offline' && d.status === 'offline') ||
      (state.filter === 'delayed' && d.status === 'delayed');
    return matchSearch && matchFilter;
  });
  instRows = filtered;

  /* Statistiques RÉELLES (zéro tant qu'aucune donnée, jamais de chiffre maquette) */
  const nbTotal = rows.length;
  const nbOffline = rows.filter(d => d.status === 'offline').length;
  const nbCalib = rows.filter(d => d.calib).length;
  const ivList = Array.isArray(state.interventions) ? state.interventions : [];
  const nbAttente = ivList.filter(iv => iv.statut === 'EN_ATTENTE').length;
  const nbUrgentes = ivList.filter(iv => iv.statut === 'EN_ATTENTE' && iv.typeIntervention === 'PANNE').length;

  const set = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  // Tant que les données ne sont pas chargées, on affiche « - » (pas de faux
  // état rassurant type « Tout est en ligne » avant d'avoir la moindre donnée).
  const loaded = state.devicesLoaded;
  const ivLoaded = state.interventionsLoaded;
  set('stat-total', loaded ? String(nbTotal) : '-');
  set('stat-total-sub', loaded ? `dont ${filtered.length} affichée${filtered.length > 1 ? 's' : ''} ici` : '-');
  set('stat-offline', loaded ? String(nbOffline) : '-');
  set('stat-offline-sub', !loaded ? '-' : (nbOffline > 0 ? '⚠ Intervention requise' : '✓ Tout est en ligne'));
  set('stat-attente', ivLoaded ? String(nbAttente) : '-');
  set('stat-attente-sub', !ivLoaded ? '-' : `${nbUrgentes} urgente${nbUrgentes > 1 ? 's' : ''}`);
  set('stat-calib', loaded ? String(nbCalib) : '-');
  // Sous-titre calibration piloté par les vraies données (fini le « Écart > 5 % »
  // codé en dur affiché en permanence). Couleur d'alerte seulement s'il y a lieu.
  const calibSub = document.getElementById('stat-calib-sub');
  if (calibSub) {
    calibSub.textContent = !loaded ? '-' : (nbCalib > 0 ? `Écart > ${Math.round(CALIB_WARN * 100)} % détecté` : '✓ Tous calibrés');
    calibSub.classList.toggle('stat-sub-warn', loaded && nbCalib > 0);
  }

  const tbody = document.getElementById('devices-tbody');
  if (!tbody) return;
  if (filtered.length === 0) {
    const msg = !state.devicesLoaded
      ? 'Chargement des installations…'
      : (rows.length === 0
        ? 'Aucun dispositif enregistré pour le moment. Cliquez sur « Nouveau dispositif » pour en installer un.'
        : 'Aucune installation ne correspond à votre recherche.');
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:var(--sp-8);color:var(--tx-s)">${msg}</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(d => {
    const st = ST_MAP[d.status] || ST_MAP.offline;
    return `<tr>
      <td><span style="font-weight:600">${esc(d.client)}</span>${d.calib ? '<span class="calib-tag">Calibration</span>' : ''}</td>
      <td style="color:var(--tx-s)">${esc(d.addr)}</td>
      <td><span class="cell-device">${esc(d.device)}</span><span class="cell-fw">FW ${esc(d.fw)}</span></td>
      <td><span class="status-badge ${st.cl}"><span class="sdot" style="background:currentColor"></span>${st.lbl}</span></td>
      <td class="cell-last" style="color:var(--tx-s)">${esc(d.last)}</td>
      <td>
        <button class="action-btn" type="button" data-action="details" data-id="${esc(d.id)}">Détails</button>
        ${d.raw ? `<button class="action-btn" type="button" data-action="diagnostiquer" data-id="${esc(d.id)}">Diagnostiquer</button>` : ''}
        ${d.raw ? `<button class="action-btn" type="button" data-action="abonnement" data-id="${esc(d.id)}">Abonnement</button>` : ''}
        ${d.raw ? `<button class="action-btn" type="button" data-action="reassigner" data-id="${esc(d.id)}">Transférer</button>` : ''}
        ${d.capteurs.length > 0 ? `<button class="action-btn${d.calib ? ' action-btn-warn' : ''}" type="button" data-action="calibrate" data-id="${esc(d.id)}">Calibrer${d.calib ? ' ⚠' : ''}</button>` : ''}
        ${d.status === 'offline' ? `<button class="action-btn danger" type="button" data-action="panne" data-id="${esc(d.id)}">Déclarer panne</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}

/* ════════════════════════════════════════════════════════════════
   SYSTÈME DE MODALES STYLISÉES (remplace alert/confirm/prompt natifs)
   ════════════════════════════════════════════════════════════════ */

/**
 * Modale d'information (remplace alert).
 * @param {string} title, Titre de la modale
 * @param {string|HTMLElement} body, Contenu HTML ou texte
 * @param {string} [btnLabel='Fermer'], Libellé du bouton
 */
function showInfo(title, body, btnLabel) {
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'info-overlay-' + Date.now();
  const label = btnLabel || 'Fermer';
  // body = chaîne (texte simple, échappé + retours ligne conservés) OU { html: '...' }
  // (contenu HTML déjà construit et échappé par l'appelant, rendu tel quel).
  const isHtml = !!(body && typeof body === 'object' && typeof body.html === 'string');
  const bodyContent = isHtml ? body.html : esc(body == null ? '' : String(body));
  const bodyStyle = (isHtml ? '' : 'white-space:pre-line;') + 'font-size:13px;line-height:1.65;color:var(--tx-p)';
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="info-title">
    <div class="modal-card" style="max-width:460px">
      <div class="modal-header">
        <span class="modal-title" id="info-title">${esc(title)}</span>
        <button class="modal-close" type="button" id="info-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body" style="${bodyStyle}">${bodyContent}</div>
      <div class="modal-footer"><button class="btn-modal-pri" type="button" id="info-ok" style="min-width:90px">${esc(label)}</button></div>
    </div>
  </div>`;
  const close = () => { root.innerHTML = ''; };
  document.getElementById('info-close').addEventListener('click', close);
  document.getElementById('info-ok').addEventListener('click', close);
  document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) close(); });
}

/**
 * Modale de confirmation (remplace confirm). Renvoie une Promise<boolean>.
 */
function showConfirm(title, body, opts) {
  return new Promise(resolve => {
    const root = document.getElementById('modal-root');
    if (!root) { resolve(false); return; }
    const id = 'confirm-overlay-' + Date.now();
    const dangerBtn = opts && opts.danger;
    const okLabel = (opts && opts.okLabel) || 'Confirmer';
    const cancelLabel = (opts && opts.cancelLabel) || 'Annuler';
    root.innerHTML = `
    <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div class="modal-card" style="max-width:420px">
        <div class="modal-header">
          <span class="modal-title" id="confirm-title">${esc(title)}</span>
          <button class="modal-close" type="button" id="confirm-close" aria-label="Annuler"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
        </div>
        <div class="modal-body" style="font-size:13px;line-height:1.65;color:var(--tx-s)">${esc(body)}</div>
        <div class="modal-footer">
          <button class="btn-modal-sec" type="button" id="confirm-no">${esc(cancelLabel)}</button>
          <button class="${dangerBtn ? 'btn-modal-danger' : 'btn-modal-pri'}" type="button" id="confirm-yes">${esc(okLabel)}</button>
        </div>
      </div>
    </div>`;
    const yes = () => { root.innerHTML = ''; resolve(true); };
    const no  = () => { root.innerHTML = ''; resolve(false); };
    document.getElementById('confirm-close').addEventListener('click', no);
    document.getElementById('confirm-no').addEventListener('click', no);
    document.getElementById('confirm-yes').addEventListener('click', yes);
    document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) no(); });
  });
}

/**
 * Modale de saisie de texte (remplace prompt). Renvoie Promise<string|null>.
 */
function showPrompt(title, body, defaultValue, opts) {
  return new Promise(resolve => {
    const root = document.getElementById('modal-root');
    if (!root) { resolve(null); return; }
    const id = 'prompt-overlay-' + Date.now();
    const multiline = opts && opts.multiline;
    const placeholder = (opts && opts.placeholder) || '';
    const inputHtml = multiline
      ? `<textarea id="prompt-input" class="modal-fi" rows="4" style="resize:vertical;width:100%;box-sizing:border-box" placeholder="${esc(placeholder)}">${esc(defaultValue || '')}</textarea>`
      : `<input id="prompt-input" class="modal-fi" type="text" style="width:100%;box-sizing:border-box" value="${esc(defaultValue || '')}" placeholder="${esc(placeholder)}">`;
    root.innerHTML = `
    <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="prompt-title">
      <div class="modal-card" style="max-width:440px">
        <div class="modal-header">
          <span class="modal-title" id="prompt-title">${esc(title)}</span>
          <button class="modal-close" type="button" id="prompt-close" aria-label="Annuler"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
        </div>
        <div class="modal-body">
          <p style="font-size:13px;line-height:1.6;color:var(--tx-s);margin-bottom:12px">${esc(body)}</p>
          <div class="modal-fg">${inputHtml}</div>
          <div id="prompt-err" style="font-size:12px;color:var(--err);min-height:16px;margin-top:4px"></div>
        </div>
        <div class="modal-footer">
          <button class="btn-modal-sec" type="button" id="prompt-cancel">Annuler</button>
          <button class="btn-modal-pri" type="button" id="prompt-ok">Valider</button>
        </div>
      </div>
    </div>`;
    const input = document.getElementById('prompt-input');
    setTimeout(() => { if (input) { input.focus(); input.select(); } }, 40);
    const cancel = () => { root.innerHTML = ''; resolve(null); };
    const submit = () => {
      const val = input ? input.value : '';
      if (opts && opts.required && !val.trim()) {
        const err = document.getElementById('prompt-err');
        if (err) err.textContent = 'Ce champ est requis.';
        return;
      }
      root.innerHTML = '';
      resolve(val);
    };
    document.getElementById('prompt-close').addEventListener('click', cancel);
    document.getElementById('prompt-cancel').addEventListener('click', cancel);
    document.getElementById('prompt-ok').addEventListener('click', submit);
    if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter' && !multiline) { e.preventDefault(); submit(); } });
    document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) cancel(); });
  });
}

/**
 * Modale de toast (succès / erreur, disparaît automatiquement).
 */
function showToast(msg, type) {
  const color = type === 'error' ? 'var(--err)' : type === 'warn' ? 'var(--warn)' : 'var(--ok)';
  const icon = type === 'error'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  const toast = document.createElement('div');
  toast.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--bg-p);border:1px solid var(--bd-d);border-left:3px solid ${color};border-radius:8px;padding:10px 16px;font-size:13px;color:var(--tx-p);display:flex;gap:8px;align-items:center;box-shadow:0 4px 12px rgba(0,0,0,.15);z-index:9999;max-width:380px;animation:slideUp .2s ease`;
  toast.innerHTML = `<span style="color:${color}">${icon}</span><span>${esc(msg)}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}

/* Détails + régénération de clé API (POST /api/sensors/dispositifs/<id>/regenerer-cle/) */
function showDetails(d) {
  const rows = [
    ['Référence', d.device],
    d.raw && d.raw.nom ? ['Nom', d.raw.nom] : null,
    ['Client', d.client],
    ['Adresse', d.addr || '-'],
    ['Firmware', d.fw || '-'],
    ['État', (ST_MAP[d.status] || ST_MAP.offline).lbl],
    d.capteurs && d.capteurs.length ? ['Capteurs', `${d.capteurs.length} installé${d.capteurs.length > 1 ? 's' : ''}`] : null,
    d.raw && d.raw.apiKeyDevice ? ['Clé API', d.raw.apiKeyDevice.slice(0, 20) + '…'] : null,
  ].filter(Boolean);
  const bodyHtml = `<div style="background:var(--bg-h);border-radius:8px;padding:12px 14px;margin-bottom:16px">
    ${rows.map(([k, v], i) => `<div style="display:flex;justify-content:space-between;gap:12px;font-size:13px;padding:5px 0;${i < rows.length - 1 ? 'border-bottom:1px solid var(--bd-s)' : ''}"><span style="color:var(--tx-s)">${esc(k)}</span><span style="font-weight:600;color:var(--tx-p)">${esc(v)}</span></div>`).join('')}
  </div>`;
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'details-overlay-' + Date.now();
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="det-title">
    <div class="modal-card" style="max-width:460px">
      <div class="modal-header">
        <span class="modal-title" id="det-title">Détails, ${esc(d.device)}</span>
        <button class="modal-close" type="button" id="det-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">${bodyHtml}<p style="font-size:13px;color:var(--tx-s)">Voulez-vous régénérer la clé API de ce dispositif ? L'ancienne clé sera invalidée.</p></div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="det-cancel">Fermer</button>
        <button class="btn-modal-pri" type="button" id="det-regen">Régénérer la clé API</button>
      </div>
    </div>
  </div>`;
  const close = () => { root.innerHTML = ''; };
  document.getElementById('det-close').addEventListener('click', close);
  document.getElementById('det-cancel').addEventListener('click', close);
  document.getElementById('det-regen').addEventListener('click', () => {
    const btn = document.getElementById('det-regen');
    btn.disabled = true; btn.textContent = 'Génération…';
    fetchWithAuth(`/api/sensors/dispositifs/${d.id}/regenerer-cle/`, { method: 'POST' })
      .then(r => {
        close();
        if (r && r.apiKeyDevice) {
          showInfo('Nouvelle clé API générée', `Clé : ${r.apiKeyDevice}\n\nCopiez-la dans le firmware ESP32. L'ancienne clé est désormais invalide.`, 'Compris');
          loadAll();
        } else {
          showToast('Échec de la régénération de la clé.', 'error');
        }
      })
      .catch(() => { close(); showToast('Erreur réseau : impossible de régénérer la clé.', 'error'); });
  });
}

/* Calibration des capteurs : Calibration automatique ou Ajustement manuel */
function calibrate(d) {
  if (!d.raw || !d.capteurs.length) {
    showInfo('Calibration indisponible', 'Le protocole de calibration est disponible uniquement pour les dispositifs enregistrés via l\'API.');
    return;
  }
  
  const root = document.getElementById('modal-root');
  if (!root) return;
  
  const capOptions = d.capteurs.map((c, idx) => `<option value="${esc(c.id)}" ${idx === 0 ? 'selected' : ''}>${esc(c.nom)} (Actuel Kcal: ${parseFloat(c.coeffCalibration || 1).toFixed(4)})</option>`).join('');
  const ovId = 'calib-overlay-' + Date.now();
  
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(ovId)}" role="dialog" aria-modal="true" aria-labelledby="calib-title">
    <div class="modal-card" style="max-width:480px">
      <div class="modal-header">
        <span class="modal-title" id="calib-title">Calibration des capteurs - ${esc(d.device)}</span>
        <button class="modal-close" type="button" id="calib-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <div class="modal-fg">
          <label class="modal-fl">Capteur à calibrer <span class="modal-req">*</span></label>
          <select class="modal-fi" id="calib-cap">${capOptions}</select>
        </div>
        
        <div class="modal-fg" style="margin-top:12px">
          <label class="modal-fl">Méthode de calibration</label>
          <div style="display:flex;gap:12px;margin-top:4px">
            <label style="display:inline-flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
              <input type="radio" name="calib-method" value="auto" checked style="accent-color:var(--ac)"> Calibration automatique
            </label>
            <label style="display:inline-flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
              <input type="radio" name="calib-method" value="manual" style="accent-color:var(--ac)"> Ajustement manuel Kcal
            </label>
          </div>
        </div>
        
        <!-- Section Auto -->
        <div id="calib-sec-auto" style="margin-top:14px;background:var(--bg-h);border-radius:8px;padding:12px 14px">
          <div style="font-size:12.5px;color:var(--tx-s);line-height:1.5;margin-bottom:8px">
            Allumez un appareil de puissance connue sur ce capteur (ex. ampoule 60W, bouilloire 1500W). Saisissez la puissance réelle ci-dessous. Le système calculera automatiquement le coefficient correctif.
          </div>
          <div class="modal-fg">
            <label class="modal-fl">Puissance réelle de référence (Watts) <span class="modal-req">*</span></label>
            <input class="modal-fi" type="number" step="0.1" id="calib-power" placeholder="Ex: 60.0">
          </div>
        </div>
        
        <!-- Section Manuel -->
        <div id="calib-sec-manual" style="display:none;margin-top:14px;background:var(--bg-h);border-radius:8px;padding:12px 14px">
          <div style="font-size:12.5px;color:var(--tx-s);line-height:1.5;margin-bottom:8px">
            Saisissez directement le coefficient de calibration Kcal multiplicateur à appliquer aux mesures brutes de courant et puissance.
          </div>
          <div class="modal-fg">
            <label class="modal-fl">Coefficient Kcal <span class="modal-req">*</span></label>
            <input class="modal-fi" type="number" step="0.0001" id="calib-coeff" placeholder="Ex: 0.9820">
          </div>
        </div>
        
        <div id="calib-err" style="margin-top:8px;font-size:12px;color:var(--err);min-height:16px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="calib-cancel">Annuler</button>
        <button class="btn-modal-pri" type="button" id="calib-ok">Lancer la calibration</button>
      </div>
    </div>
  </div>`;
  
  const close = () => { root.innerHTML = ''; };
  document.getElementById('calib-close').addEventListener('click', close);
  document.getElementById('calib-cancel').addEventListener('click', close);
  document.getElementById(ovId).addEventListener('click', e => { if (e.target.id === ovId) close(); });
  
  const secAuto = document.getElementById('calib-sec-auto');
  const secManual = document.getElementById('calib-sec-manual');
  
  document.querySelectorAll('input[name="calib-method"]').forEach(radio => {
    radio.addEventListener('change', e => {
      if (e.target.value === 'auto') {
        secAuto.style.display = 'block';
        secManual.style.display = 'none';
      } else {
        secAuto.style.display = 'none';
        secManual.style.display = 'block';
      }
    });
  });
  
  const btnOk = document.getElementById('calib-ok');
  btnOk.addEventListener('click', () => {
    const capId = document.getElementById('calib-cap').value;
    const method = document.querySelector('input[name="calib-method"]:checked').value;
    const err = document.getElementById('calib-err');
    err.textContent = '';
    
    if (method === 'auto') {
      const powerVal = parseFloat(document.getElementById('calib-power').value);
      if (isNaN(powerVal) || powerVal <= 0) {
        err.textContent = 'Veuillez saisir une puissance positive valide.';
        return;
      }
      btnOk.disabled = true; btnOk.textContent = 'Calcul…';
      
      fetchWithAuth(`/api/sensors/capteurs/${capId}/calibrer/`, {
        method: 'POST',
        body: JSON.stringify({ puissance_reelle: powerVal })
      })
        .then(r => {
          if (r && r.nouveau_facteur) {
            close();
            showToast(`Calibration auto réussie : Kcal = ${parseFloat(r.nouveau_facteur).toFixed(4)}`);
            loadAll();
          } else {
            btnOk.disabled = false; btnOk.textContent = 'Lancer la calibration';
            err.textContent = (r && r.detail) ? r.detail : 'Échec de la calibration automatique.';
          }
        })
        .catch(() => {
          btnOk.disabled = false; btnOk.textContent = 'Lancer la calibration';
          err.textContent = 'Erreur de connexion avec le serveur.';
        });
        
    } else {
      const coeffVal = parseFloat(document.getElementById('calib-coeff').value);
      if (isNaN(coeffVal) || coeffVal <= 0) {
        err.textContent = 'Veuillez saisir un coefficient multiplicateur positif valide.';
        return;
      }
      btnOk.disabled = true; btnOk.textContent = 'Enregistrement…';
      
      fetchWithAuth(`/api/sensors/capteurs/${capId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ coeffCalibration: coeffVal.toFixed(4) })
      })
        .then(r => {
          if (r && r.id) {
            close();
            showToast(`Coefficient manuel enregistré : Kcal = ${coeffVal.toFixed(4)}`);
            fetchWithAuth('/api/sensors/interventions/', {
              method: 'POST',
              body: JSON.stringify({
                client: d.raw.client, dispositif: d.id, capteur: capId,
                typeIntervention: 'CALIBRATION',
                description: `Calibration manuelle du capteur, Kcal = ${coeffVal.toFixed(4)}`,
                dateIntervention: new Date().toISOString(), statut: 'TERMINEE'
              })
            }).catch(() => {});
            loadAll();
          } else {
            btnOk.disabled = false; btnOk.textContent = 'Lancer la calibration';
            err.textContent = 'Échec de l\'enregistrement manuel.';
          }
        })
        .catch(() => {
          btnOk.disabled = false; btnOk.textContent = 'Lancer la calibration';
          err.textContent = 'Erreur de connexion avec le serveur.';
        });
    }
  });
}

/* Réassigner un dispositif (et ses capteurs) à un autre client */
function reassignerDevice(d) {
  const root = document.getElementById('modal-root');
  if (!root) return;
  const currentClientId = d.raw ? d.raw.client : null;
  const clients = (Array.isArray(state.clients) ? state.clients : [])
    .filter(c => c.id !== currentClientId);
  const clientOptions = clients.length
    ? clients.map(c => `<option value="${esc(c.id)}">${esc(c.nom || c.name || 'Client')} (${esc(c.email)})</option>`).join('')
    : '<option value="">Aucun autre client disponible</option>';

  const ovId = 'reassign-overlay-' + Date.now();
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(ovId)}" role="dialog" aria-modal="true" aria-labelledby="reassign-title">
    <div class="modal-card" style="max-width:440px">
      <div class="modal-header">
        <span class="modal-title" id="reassign-title">Transférer le dispositif</span>
        <button class="modal-close" type="button" id="reassign-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <p style="font-size:13px;color:var(--tx-s);line-height:1.55;margin-bottom:16px">
          Sélectionnez le nouveau client propriétaire de l'ESP32 <strong>${esc(d.device)}</strong>. 
          Toutes les nouvelles mesures émises par cet ESP32 seront instantanément enregistrées sous ce nouveau compte. 
          L'historique précédent reste archivé sur le compte actuel.
        </p>
        <div class="modal-fg">
          <label class="modal-fl">Nouveau propriétaire <span class="modal-req">*</span></label>
          <select class="modal-fi" id="reassign-client">${clientOptions}</select>
        </div>
        <div id="reassign-err" style="font-size:12px;color:var(--err);min-height:16px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="reassign-cancel">Annuler</button>
        <button class="btn-modal-pri" type="button" id="reassign-ok"${clients.length === 0 ? ' disabled' : ''}>Confirmer le transfert</button>
      </div>
    </div>
  </div>`;

  const close = () => { root.innerHTML = ''; };
  document.getElementById('reassign-close').addEventListener('click', close);
  document.getElementById('reassign-cancel').addEventListener('click', close);
  document.getElementById(ovId).addEventListener('click', e => { if (e.target.id === ovId) close(); });
  document.getElementById('reassign-ok').addEventListener('click', () => {
    const clientSel = document.getElementById('reassign-client');
    const err = document.getElementById('reassign-err');
    if (!clientSel.value) { err.textContent = 'Sélectionnez un client.'; return; }
    
    const btn = document.getElementById('reassign-ok');
    btn.disabled = true; btn.textContent = 'Transfert en cours…';
    
    fetchWithAuth(`/api/sensors/dispositifs/${d.id}/reassigner/`, {
      method: 'POST',
      body: JSON.stringify({ client_id: clientSel.value })
    })
      .then(r => {
        close();
        if (r && r.id) {
          showToast('Dispositif et capteurs transférés avec succès.', 'ok');
          loadAll();
        } else {
          showToast('Échec du transfert du dispositif.', 'error');
        }
      })
      .catch(() => {
        close();
        showToast('Erreur réseau : transfert impossible.', 'error');
      });
  });
}

/* Déclarer une panne pour un dispositif : POST /api/sensors/interventions/ */
function declarePanneDevice(d) {
  showPrompt(
    `Déclarer une panne, ${d.device}`,
    `Client : ${d.client}\nDécrivez la panne constatée :`,
    'Dispositif hors ligne, aucun signal reçu',
    { multiline: true, required: true }
  ).then(desc => {
    if (desc === null) return;
    fetchWithAuth('/api/sensors/interventions/', {
      method: 'POST',
      body: JSON.stringify({
        client: d.raw.client, dispositif: d.id, typeIntervention: 'PANNE',
        description: desc, dateIntervention: new Date().toISOString(), statut: 'EN_ATTENTE'
      })
    })
      .then(r => {
        showToast(r && r.id ? 'Panne déclarée : intervention créée.' : 'Échec de la déclaration de panne.', r && r.id ? 'ok' : 'error');
        loadAll();
      })
      .catch(() => showToast('Erreur réseau : déclaration impossible.', 'error'));
  });
}

/* Diagnostiquer un dispositif : affiche les métriques de santé matérielle et de connectivité */
function diagnostiquer(d) {
  const statusLabels = { online: 'Opérationnel / En ligne', offline: 'Hors ligne / Éteint', delayed: 'Données différées (10 min+)' };
  const statusColors = { online: 'var(--ok)', offline: 'var(--err)', delayed: 'var(--warn)' };
  
  const ip = d.raw.adresseIP || 'Non attribuée';
  const fw = d.raw.firmwareVersion || 'Inconnu';
  const statusText = statusLabels[d.status] || 'Inconnu';
  const statusColor = statusColors[d.status] || 'var(--tx-s)';
  
  const connectionHtml = `
    <div style="margin-bottom:16px">
      <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-s);margin-bottom:8px">Connectivité & Réseau</div>
      <div style="background:var(--bg-h);border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.6">
        <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--bd-s)"><span style="color:var(--tx-s)">Statut réseau</span><span style="font-weight:600;color:${statusColor}">${esc(statusText)}</span></div>
        <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--bd-s);margin-top:6px"><span style="color:var(--tx-s)">Adresse IP</span><span style="font-weight:600;color:var(--tx-p)">${esc(ip)}</span></div>
        <div style="display:flex;justify-content:space-between;padding:4px 0;margin-top:6px"><span style="color:var(--tx-s)">Version du Firmware</span><span style="font-weight:600;color:var(--tx-p)">${esc(fw)}</span></div>
      </div>
    </div>
  `;
  
  const sensors = d.capteurs || [];
  let sensorsHtml = '';
  if (sensors.length === 0) {
    sensorsHtml = `
      <div style="margin-bottom:16px">
        <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-s);margin-bottom:8px">État des Capteurs (0)</div>
        <div style="background:var(--bg-h);border-radius:8px;padding:12px;font-size:13px;color:var(--tx-s);text-align:center">Aucun capteur physique n'est relié à ce dispositif.</div>
      </div>`;
  } else {
    sensorsHtml = `
      <div style="margin-bottom:16px">
        <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-s);margin-bottom:8px">État des Capteurs (${sensors.length})</div>
        <div style="display:grid;gap:10px">
          ${sensors.map(c => {
            const isCalibrated = Math.abs((parseFloat(c.coeffCalibration) || 1) - 1) < CALIB_WARN;
            const calibColor = isCalibrated ? 'var(--ok)' : 'var(--warn)';
            const calibText = isCalibrated ? `Kcal = ${parseFloat(c.coeffCalibration).toFixed(4)} (✓ Calibré)` : `Kcal = ${parseFloat(c.coeffCalibration).toFixed(4)} (⚠ Écart détecté)`;
            const stateColor = c.etatCourant === 'ON' ? 'var(--ok)' : 'var(--tx-s)';
            const lastLectVal = c.derniereLecture ? new Date(c.derniereLecture).toLocaleString('fr-FR') : 'Jamais';
            
            return `
              <div style="background:var(--bg-h);border-radius:8px;padding:10px 12px;font-size:12.5px;border-left:3px solid ${c.actif ? 'var(--ok)' : 'var(--err)'}">
                <div style="display:flex;justify-content:space-between;font-weight:600;color:var(--tx-p)">
                  <span>${esc(c.nom)} <span style="font-weight:normal;color:var(--tx-s)">(${esc(c.type)})</span></span>
                  <span style="color:${stateColor}">${esc(c.etatCourant === 'ON' ? 'Allumé (ON)' : 'Éteint (OFF)')}</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:var(--tx-s)">Dernière activité</span><span>${esc(lastLectVal)}</span></div>
                <div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:var(--tx-s)">Coefficient Calibration</span><span style="font-weight:600;color:${calibColor}">${esc(calibText)}</span></div>
                <div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:var(--tx-s)">Statut opérationnel</span><span>${c.actif ? '✓ Actif' : '✗ Inactif (Désactivé)'}</span></div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }
  
  const clientNom = d.client;
  const clientEmail = d.raw.client_email || '-';
  const clientHtml = `
    <div style="margin-bottom:16px">
      <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-s);margin-bottom:8px">Client Propriétaire</div>
      <div style="background:var(--bg-h);border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.6">
        <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--bd-s)"><span style="color:var(--tx-s)">Propriétaire</span><span style="font-weight:600;color:var(--tx-p)">${esc(clientNom)}</span></div>
        <div style="display:flex;justify-content:space-between;padding:4px 0;margin-top:6px"><span style="color:var(--tx-s)">Email</span><span style="font-weight:600;color:var(--tx-p)">${esc(clientEmail)}</span></div>
      </div>
    </div>
  `;
  
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'diag-overlay-' + Date.now();
  
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="diag-title">
    <div class="modal-card" style="max-width:520px">
      <div class="modal-header">
        <span class="modal-title" id="diag-title">Diagnostic en direct - ${esc(d.device)}</span>
        <button class="modal-close" type="button" id="diag-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body" style="max-height:480px;overflow-y:auto">
        ${connectionHtml}
        ${sensorsHtml}
        ${clientHtml}
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="diag-btn-close">Fermer</button>
        <button class="btn-modal-pri" type="button" id="diag-btn-log">Déclarer un incident</button>
      </div>
    </div>
  </div>`;
  
  const close = () => { root.innerHTML = ''; };
  document.getElementById('diag-close').addEventListener('click', close);
  document.getElementById('diag-btn-close').addEventListener('click', close);
  document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) close(); });
  document.getElementById('diag-btn-log').addEventListener('click', () => {
    close();
    declarePanneDevice(d);
  });
}

/* Clients réels pour le wizard : liste complète via /api/users/clients/,
   avec repli sur les clients déduits des dispositifs existants. */
function getApiClients() {
  if (Array.isArray(state.clients) && state.clients.length > 0) {
    return state.clients.map(c => ({ id: c.id, name: c.nom || c.email || 'Client', email: c.email || '' }));
  }
  const apiClients = [];
  if (Array.isArray(state.devices) && state.devices.length > 0) {
    const seen = {};
    state.devices.forEach(d => {
      if (d.client && !seen[d.client]) {
        seen[d.client] = 1;
        apiClients.push({ id: d.client, name: d.client_nom || d.client_email || 'Client', email: d.client_email || '' });
      }
    });
  }
  return apiClients;
}

/* ════════════════════════ INTERVENTIONS ════════════════════════ */
function renderInterventions() {
  const tbody = document.getElementById('inter-tbody');
  if (!tbody) return;

  const allList = (Array.isArray(state.interventions) ? state.interventions : []).map(iv => {
    const dev = Array.isArray(state.devices) ? state.devices.find(d => d.id === iv.dispositif) : null;
    const deviceLabel = dev
      ? (dev.nom || dev.numeroSerie || ('ESP32-' + String(dev.id).replace(/-/g, '').slice(0, 7).toUpperCase()))
      : (iv.dispositif ? 'ESP32-' + String(iv.dispositif).replace(/-/g, '').slice(0, 7).toUpperCase() : '-');
    return {
      id: iv.id, raw: iv,
      client: iv.client_nom || '-',
      type: TYPE_LBL[iv.typeIntervention] || iv.typeIntervention,
      status: STATUT_UI[iv.statut] || 'pending',
      statut: iv.statut || 'EN_ATTENTE',
      date: formatDate(iv.dateIntervention),
      note: iv.description || '-',
      device: deviceLabel,
    };
  });
  interList = allList;

  // Mettre à jour les badges sidebar + statistiques
  const nAttente = allList.filter(x => x.statut === 'EN_ATTENTE').length;
  const nCours   = allList.filter(x => x.statut === 'EN_COURS').length;
  const badge = document.getElementById('nav-inter-badge');
  if (badge) { badge.textContent = String(nAttente); badge.style.display = nAttente > 0 ? '' : 'none'; }
  const statsEl = document.getElementById('inter-stats-grid');
  if (statsEl) {
    statsEl.innerHTML = [
      { lbl: 'Total interventions', val: allList.length, sub: 'Enregistrées', cl: '' },
      { lbl: 'En attente', val: nAttente, sub: nAttente > 0 ? 'À traiter' : '-', cl: 'stat-val-warn' },
      { lbl: 'En cours', val: nCours, sub: 'Interventions actives', cl: 'stat-val-info' },
      { lbl: 'Terminées', val: allList.filter(x => x.statut === 'TERMINEE').length, sub: 'Historique', cl: 'stat-val-ok' }
    ].map(s => `<div class="stat-card">
      <div class="stat-lbl">${esc(s.lbl)}</div>
      <div class="stat-val ${s.cl}">${s.val}</div>
      <div class="stat-sub">${esc(s.sub)}</div>
    </div>`).join('');
  }

  // Filtrage par statut et recherche
  const q = (state.interSearch || '').toLowerCase().trim();
  const f = state.interFilter || 'tous';
  const list = allList.filter(iv => {
    if (f !== 'tous' && iv.statut !== f) return false;
    if (q && !iv.client.toLowerCase().includes(q) && !iv.type.toLowerCase().includes(q) && !iv.note.toLowerCase().includes(q)) return false;
    return true;
  });

  if (list.length === 0) {
    const msg = state.interventionsLoaded
      ? (q || f !== 'tous' ? 'Aucune intervention ne correspond aux filtres.' : 'Aucune intervention enregistrée.')
      : 'Chargement des interventions…';
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:var(--sp-8);color:var(--tx-s)">${msg}</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(iv => {
    const s = S_MAP[iv.status] || S_MAP.pending;
    const hasDevice = iv.raw && iv.raw.dispositif;
    return `<tr>
      <td><span style="font-weight:600">${esc(iv.type)}</span></td>
      <td>${esc(iv.client)}</td>
      <td><span class="cell-device">${esc(iv.device)}</span></td>
      <td style="color:var(--tx-s)">${esc(iv.date)}</td>
      <td><span class="status-badge ${s.cl}"><span class="sdot" style="background:currentColor"></span>${s.l}</span></td>
      <td>
        <button class="action-btn" type="button" data-action="fiche" data-id="${esc(iv.id)}">Fiche</button>
        ${hasDevice ? `<button class="action-btn" type="button" data-action="diagnostiquer" data-id="${esc(iv.raw.dispositif)}">Diagnostiquer</button>` : ''}
        ${iv.status !== 'done' ? `<button class="action-btn" type="button" data-action="update" data-id="${esc(iv.id)}">Mettre à jour</button>` : ''}
        ${iv.status !== 'done' ? `<button class="action-btn" type="button" data-action="planifier" data-id="${esc(iv.id)}">Planifier</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}

/* Déclarer une panne (bouton global de l'onglet Interventions) */
function declarePanneGlobal() {
  const root = document.getElementById('modal-root');
  if (!root) return;
  const devices = Array.isArray(state.devices) ? state.devices : [];
  const deviceOptions = devices.length
    ? devices.map(d => `<option value="${esc(d.id)}" data-client="${esc(d.client)}">${esc(d.client_nom || 'Client')}, ${esc(d.nom || d.numeroSerie || ('ESP32-' + String(d.id).replace(/-/g,'').slice(0,7).toUpperCase()))}</option>`).join('')
    : '<option value="">Aucun dispositif disponible</option>';

  const ovId = 'panne-overlay-' + Date.now();
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(ovId)}" role="dialog" aria-modal="true" aria-labelledby="panne-title">
    <div class="modal-card" style="max-width:480px">
      <div class="modal-header">
        <span class="modal-title" id="panne-title">Déclarer une panne</span>
        <button class="modal-close" type="button" id="panne-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <div class="modal-fg">
          <label class="modal-fl">Installation concernée <span class="modal-req">*</span></label>
          <select class="modal-fi" id="panne-dev">${deviceOptions}</select>
        </div>
        <div class="modal-fg">
          <label class="modal-fl">Type de problème</label>
          <select class="modal-fi" id="panne-type">
            <option value="PANNE">Panne matérielle</option>
            <option value="MAINTENANCE">Maintenance préventive</option>
            <option value="DIAGNOSTIC">Diagnostic & Audits</option>
          </select>
        </div>
        <div class="modal-fg">
          <label class="modal-fl">Description de la panne <span class="modal-req">*</span></label>
          <textarea class="modal-fi" id="panne-desc" rows="4" style="resize:vertical;width:100%;box-sizing:border-box" placeholder="Décrivez le problème constaté (symptômes, contexte, actions déjà tentées…)"></textarea>
        </div>
        <div id="panne-err" style="font-size:12px;color:var(--err);min-height:16px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="panne-cancel">Annuler</button>
        <button class="btn-modal-pri" type="button" id="panne-ok"${devices.length === 0 ? ' disabled' : ''}>Déclarer la panne</button>
      </div>
    </div>
  </div>`;

  const close = () => { root.innerHTML = ''; };
  document.getElementById('panne-close').addEventListener('click', close);
  document.getElementById('panne-cancel').addEventListener('click', close);
  document.getElementById(ovId).addEventListener('click', e => { if (e.target.id === ovId) close(); });
  document.getElementById('panne-ok').addEventListener('click', () => {
    const devSel = document.getElementById('panne-dev');
    const desc = (document.getElementById('panne-desc').value || '').trim();
    const type = document.getElementById('panne-type').value;
    const err = document.getElementById('panne-err');
    if (!devSel.value) { err.textContent = 'Sélectionnez une installation.'; return; }
    if (!desc) { err.textContent = 'La description est obligatoire.'; return; }
    const selectedOpt = devSel.options[devSel.selectedIndex];
    const clientId = selectedOpt ? selectedOpt.dataset.client : null;
    const body = {
      typeIntervention: type, description: desc,
      dateIntervention: new Date().toISOString(), statut: 'EN_ATTENTE',
      dispositif: devSel.value, client: clientId || undefined,
    };
    const btn = document.getElementById('panne-ok');
    btn.disabled = true; btn.textContent = 'Envoi…';
    fetchWithAuth('/api/sensors/interventions/', { method: 'POST', body: JSON.stringify(body) })
      .then(r => {
        close();
        showToast(r && r.id ? 'Panne déclarée : intervention créée.' : 'Échec, vérifiez les champs.', r && r.id ? 'ok' : 'error');
        loadAll();
      })
      .catch(() => { close(); showToast('Erreur réseau : déclaration impossible.', 'error'); });
  });
}

/* Voir la fiche : détail complet, contenu du rapport et téléchargement PDF */
function showFiche(iv) {
  const r = iv.raw || {};
  const rap = r.rapport || null;
  const rapDate = rap && rap['dateGénération'] ? new Date(rap['dateGénération']).toLocaleDateString('fr-FR') : null;
  const rows = [
    ['Type', iv.type],
    ['Client', iv.client],
    ['Technicien', r.technicien_nom || '-'],
    ['Capteur', r.capteur_nom || '-'],
    ['Date', iv.date],
    ['Statut', (S_MAP[iv.status] || S_MAP.pending).l],
    ['Description', iv.note || '-'],
    ['Résultat', r['résultat'] || '-'],
    ['Rapport', rap ? ('✓ Rédigé' + (rapDate ? ' le ' + rapDate : '')) : 'Non rédigé'],
  ];
  const bodyHtml = `<div style="background:var(--bg-h);border-radius:8px;padding:12px 14px">
    ${rows.map(([k, v], i) => `<div style="display:flex;justify-content:space-between;gap:12px;font-size:13px;padding:5px 0;${i < rows.length - 1 ? 'border-bottom:1px solid var(--bd-s)' : ''}"><span style="color:var(--tx-s);white-space:nowrap">${esc(k)}</span><span style="font-weight:600;color:var(--tx-p);text-align:right">${esc(v)}</span></div>`).join('')}
  </div>`;
  // Le contenu du rapport est enfin VISIBLE dans la fiche (il n'était que « ✓ Généré »),
  // avec téléchargement du document PDF officiel (même socle que les exports client).
  const rapportHtml = rap ? `
  <div style="margin-top:10px;background:var(--bg-h);border-radius:8px;padding:12px 14px">
    <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-s);margin-bottom:6px">Rapport du technicien</div>
    <div style="font-size:13px;color:var(--tx-p);line-height:1.6;white-space:pre-line;max-height:180px;overflow-y:auto">${esc(rap.contenu || '')}</div>
    <button type="button" id="fiche-dl-rapport" style="margin-top:10px;display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;border:1px solid var(--bd-d);background:var(--bg-p);color:var(--tx-p);font-size:12.5px;font-weight:600;cursor:pointer">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      Télécharger le rapport (PDF)
    </button>
  </div>` : '';
  showInfo("Fiche d'intervention", { html: bodyHtml + rapportHtml });
  const dl = document.getElementById('fiche-dl-rapport');
  if (dl) {
    dl.addEventListener('click', () => {
      dl.disabled = true;
      dl.textContent = 'Téléchargement…';
      downloadFile(`/api/sensors/interventions/${iv.id}/rapport/pdf/`, 'aoceda_rapport_intervention.pdf')
        .catch(() => showToast('Téléchargement du rapport impossible.', 'error'))
        .finally(() => { dl.disabled = false; dl.textContent = 'Télécharger le rapport (PDF)'; });
    });
  }
}

/* Mettre à jour : EN_ATTENTE → EN_COURS → TERMINEE (+ résultat + rapport) */
function updateIv(iv) {
  if (!iv.raw) {
    showInfo('Mise à jour indisponible', 'La mise à jour est disponible uniquement pour les interventions enregistrées via l\'API.');
    return;
  }
  if (iv.status === 'pending') {
    showConfirm(
      'Passer en cours ?',
      `Intervention : ${iv.type}\nClient : ${iv.client}\n\nMarquer cette intervention comme "En cours" ?`,
      { okLabel: 'Oui, démarrer', cancelLabel: 'Annuler' }
    ).then(ok => {
      if (!ok) return;
      fetchWithAuth(`/api/sensors/interventions/${iv.id}/`, { method: 'PATCH', body: JSON.stringify({ statut: 'EN_COURS' }) })
        .then(() => { showToast('Intervention passée en cours.'); loadAll(); })
        .catch(() => showToast('Erreur réseau : mise à jour impossible.', 'error'));
    });
  } else if (iv.status === 'progress') {
    showPrompt(
      'Clôturer l\'intervention',
      'Décrivez le résultat des travaux effectués :',
      '',
      { multiline: true, required: true }
    ).then(res => {
      if (res === null) return;
      fetchWithAuth(`/api/sensors/interventions/${iv.id}/`, { method: 'PATCH', body: JSON.stringify({ statut: 'TERMINEE', 'résultat': res }) })
        .then(() => showRapportModal(iv.id))
        .then(contenu => {
          if (contenu && contenu.trim()) {
            return fetchWithAuth(`/api/sensors/interventions/${iv.id}/rapport/`, {
              method: 'POST',
              // conclusion volontairement absente : c'était un doublon exact du contenu,
              // qui polluait le PDF (le document n'affiche la conclusion que si distincte).
              body: JSON.stringify({ contenu: contenu.trim(), estValidé: true })
            }).then(rp => {
              showToast(rp && rp.id ? 'Rapport généré avec succès.' : 'Intervention clôturée, rapport non généré.', rp && rp.id ? 'ok' : 'warn');
            });
          } else {
            showToast('Intervention clôturée.');
          }
        })
        .then(() => loadAll())
        .catch(() => showToast('Erreur réseau : mise à jour impossible.', 'error'));
    });
  }
}

/* Planifier une date de passage à venir (angle mort produit : le client ne voyait
   ses interventions qu'après coup, jamais de rendez-vous à l'avance). Visible côté
   client sous forme « Intervention prévue le X » tant que le statut n'est pas final.
   dateProgrammee n'est PAS un champ verrouillé après création (contrairement à
   dateIntervention) : librement replanifiable. */
function planifierIv(iv) {
  if (!iv.raw) return;
  const current = iv.raw.dateProgrammee ? new Date(iv.raw.dateProgrammee) : null;
  const defVal = (current && !isNaN(current.getTime())) ? current.toISOString().slice(0, 16) : '';
  showPrompt(
    'Planifier une date de passage',
    'Date et heure prévues (AAAA-MM-JJ HH:MM), visibles par le client sur sa page Interventions. Laissez vide pour retirer la planification.',
    defVal,
    { placeholder: 'AAAA-MM-JJ HH:MM' }
  ).then(val => {
    if (val === null) return;
    const trimmed = val.trim();
    let dateProgrammee = null;
    if (trimmed) {
      const d = new Date(trimmed);
      if (isNaN(d.getTime())) {
        showToast('Date invalide, format attendu AAAA-MM-JJ HH:MM.', 'error');
        return;
      }
      dateProgrammee = d.toISOString();
    }
    fetchWithAuth(`/api/sensors/interventions/${iv.id}/`, { method: 'PATCH', body: JSON.stringify({ dateProgrammee }) })
      .then(() => { showToast(dateProgrammee ? 'Date de passage planifiée.' : 'Planification retirée.'); loadAll(); })
      .catch(() => showToast('Erreur réseau : planification impossible.', 'error'));
  });
}

/* Modale personnalisée avec CKEditor pour les rapports */
function showRapportModal(interventionId) {
  return new Promise((resolve) => {
    const root = document.getElementById('modal-root');
    if (!root) { resolve(null); return; }
    
    const id = 'rapport-modal-' + Date.now();
    root.innerHTML = `
    <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true">
      <div class="modal-card" style="max-width:700px; width:90%">
        <div class="modal-header">
          <span class="modal-title">Rapport d'intervention</span>
          <button class="modal-close" type="button" id="rm-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
        </div>
        <div class="modal-body" style="padding-bottom:8px">
          <p style="font-size:13px;color:var(--tx-s);margin-bottom:12px">Rédigez le contenu complet du rapport d'intervention ci-dessous. Vous pouvez utiliser la mise en forme (gras, listes, etc.) pour un rendu PDF professionnel.</p>
          <textarea id="rm-textarea" name="rapport-content" style="width:100%; height:200px;"></textarea>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" id="rm-cancel" type="button">Ignorer le rapport</button>
          <button class="btn-p" id="rm-ok" type="button">Valider le rapport</button>
        </div>
      </div>
    </div>`;

    let editorInst = null;
    if (typeof CKEDITOR !== 'undefined') {
      editorInst = CKEDITOR.replace('rm-textarea', { height: 250, language: 'fr' });
    }

    const close = (val) => {
      if (editorInst) { editorInst.destroy(); }
      const el = document.getElementById(id);
      if (el) el.remove();
      resolve(val);
    };

    document.getElementById('rm-close').addEventListener('click', () => close(null));
    document.getElementById('rm-cancel').addEventListener('click', () => close(null));
    document.getElementById('rm-ok').addEventListener('click', () => {
      const btn = document.getElementById('rm-ok');
      btn.disabled = true;
      btn.textContent = 'Enregistrement...';
      const content = editorInst ? editorInst.getData() : document.getElementById('rm-textarea').value;
      close(content);
    });
  });
}

/* ════════════════════════ MODAL « NOUVEAU DISPOSITIF » ════════════════════════ */
const STEP_TITLES = ['Sélectionner le client', 'Dispositif & WiFi', 'Nommer les capteurs', 'Clé API de configuration', 'Résumé & Finalisation'];
let modal = null; // état du modal (null = fermé)

function openModal() {
  modal = {
    step: 1,
    clientSearch: '',
    selectedClient: null,
    deviceName: '',
    wifiSsid: '',
    serial: '',
    addr: '',
    capteurs: [{ nom: '' }],
    capteursCreated: [],
    creatingCapteurs: false,
    creating: false,
    createdId: null,
    serverKey: null,
    copied: false,
    apiClients: getApiClients(),
    creatingNewClient: false,
    newClientData: { nom: '', email: '', telephone: '', password: '' },
    newClientError: '',
    savingNewClient: false,
  };
  renderModal();
}

function closeModal() {
  modal = null;
  const root = document.getElementById('modal-root');
  if (root) root.innerHTML = '';
}

/* ════════════════ Abonnement / compteur d'un client ════════════════
   Le technicien référence l'ampérage, le type de compteur (prépayé /
   postpayé) et le n° CIE. Le tarif découle de l'ampérage (5A = social). */
function tarifFromAmp(amp) { return Number(amp) === 5 ? 'social' : 'general'; }

function manageAbonnement(d) {
  const clientId = d.raw && d.raw.client;
  if (!clientId) {
    showInfo('Abonnement indisponible', "L'abonnement est disponible uniquement pour les clients enregistrés via l'API.");
    return;
  }
  fetchWithAuth(`/api/users/clients/${clientId}/abonnement/`)
    .then(c => renderAbonnementModal(clientId, c || {}, d))
    .catch(() => showToast("Impossible de charger l'abonnement de ce client.", 'error'));
}

function renderAbonnementModal(clientId, c, d) {
  const root = document.getElementById('modal-root');
  if (!root) return;
  modal = null;
  const amp = Number(c.amperage) || 10;
  const cpt = c.typeCompteur === 'prepaye' ? 'prepaye' : 'postpaye';

  root.innerHTML = `
  <div class="modal-overlay" id="abo-overlay">
    <div class="modal-card">
      <div class="modal-header">
        <span class="modal-title">Abonnement &amp; compteur, ${esc(c.nom || d.client)}</span>
        <button class="modal-close" type="button" id="abo-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <p style="font-size:13px;color:var(--tx-s);line-height:1.55;margin-bottom:16px">Référencez l'abonnement CIE du client relevé sur le compteur. Le 5A relève automatiquement du <strong>tarif social</strong>.</p>
        <div style="margin-bottom:14px"><label class="modal-fl">Ampérage souscrit</label>
          <select class="modal-fi" id="abo-amp">
            <option value="5">5 A (1,1 kW), Social</option>
            <option value="10">10 A (2,2 kW), Général</option>
            <option value="15">15 A (3,3 kW), Général</option>
          </select></div>
        <div style="margin-bottom:14px"><label class="modal-fl">Type de compteur</label>
          <select class="modal-fi" id="abo-cpt">
            <option value="postpaye">Intelligent postpayé (facture mensuelle)</option>
            <option value="prepaye">Prépayé (crédit rechargeable)</option>
          </select>
          <div style="font-size:12px;color:var(--tx-m);margin-top:6px" id="abo-cpt-hint"></div></div>
        <div style="margin-bottom:14px"><label class="modal-fl">Tarif appliqué (automatique)</label>
          <input class="modal-fi" id="abo-tarif" disabled></div>
        <div style="margin-bottom:4px"><label class="modal-fl">N° d'abonné CIE <span style="font-weight:400;color:var(--tx-m)">(facultatif)</span></label>
          <input class="modal-fi" id="abo-cie" placeholder="Ex: CI-ABJ-2024-..."></div>
        <div id="abo-feedback" style="font-size:13px;margin-top:12px;min-height:18px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="abo-cancel">Annuler</button>
        <button class="btn-modal-pri" type="button" id="abo-save">Enregistrer l'abonnement</button>
      </div>
    </div>
  </div>`;

  const ampSel = document.getElementById('abo-amp');
  const cptSel = document.getElementById('abo-cpt');
  const cieIn = document.getElementById('abo-cie');
  const tarifIn = document.getElementById('abo-tarif');
  ampSel.value = String(amp);
  cptSel.value = cpt;
  cieIn.value = c.numeroCIE || '';
  const refreshTarif = () => { tarifIn.value = tarifFromAmp(ampSel.value) === 'social' ? 'Social (5A)' : 'Général'; };
  refreshTarif();
  ampSel.addEventListener('change', refreshTarif);

  // Explication de l'incidence du type de compteur (postpayé vs prépayé)
  const cptHint = document.getElementById('abo-cpt-hint');
  const refreshCptHint = () => {
    if (!cptHint) return;
    cptHint.textContent = cptSel.value === 'prepaye'
      ? 'Prépayé : le client recharge un crédit qui se vide selon sa consommation ; alerte « crédit bas » automatique.'
      : 'Postpayé : le client est facturé mensuellement (grille CIE, tranches, prime fixe et taxes).';
  };
  refreshCptHint();
  cptSel.addEventListener('change', refreshCptHint);

  document.getElementById('abo-overlay').addEventListener('click', e => { if (e.target.id === 'abo-overlay') closeModal(); });
  document.getElementById('abo-close').addEventListener('click', closeModal);
  document.getElementById('abo-cancel').addEventListener('click', closeModal);
  document.getElementById('abo-save').addEventListener('click', () => {
    const body = {
      amperage: parseInt(ampSel.value, 10),
      typeCompteur: cptSel.value === 'prepaye' ? 'prepaye' : 'postpaye',
      typeTarif: tarifFromAmp(ampSel.value),
      numeroCIE: cieIn.value.trim(),
    };
    const fb = document.getElementById('abo-feedback');
    const btn = document.getElementById('abo-save');
    btn.disabled = true;
    fb.textContent = 'Enregistrement…'; fb.style.color = 'var(--tx-m)';
    fetchWithAuth(`/api/users/clients/${clientId}/abonnement/`, { method: 'PATCH', body: JSON.stringify(body) })
      .then(r => {
        if (r && r.id) {
          fb.textContent = '✓ Abonnement enregistré'; fb.style.color = 'var(--ok)';
          setTimeout(closeModal, 900);
        } else {
          btn.disabled = false;
          const msg = r && (r.typeTarif || r.detail || r.amperage);
          fb.textContent = 'Échec : ' + (Array.isArray(msg) ? msg.join(' ') : (msg || 'données invalides'));
          fb.style.color = 'var(--err)';
        }
      })
      .catch(() => { btn.disabled = false; fb.textContent = 'Erreur réseau.'; fb.style.color = 'var(--err)'; });
  });
}

function modalApiKey() {
  return modal.serverKey || '';
}

function filteredClients() {
  const clients = (modal.apiClients && modal.apiClients.length) ? modal.apiClients : [];
  const q = modal.clientSearch.toLowerCase();
  return clients.filter(c => c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q));
}

function clientListHtml() {
  const list = filteredClients();
  if (!list.length) {
    return `<div style="padding:12px 14px;font-size:13px;color:var(--tx-s)">${(modal.apiClients && modal.apiClients.length) ? 'Aucun client ne correspond à la recherche.' : 'Aucun client disponible.'}</div>`;
  }
  return list.map(c => {
    const sel = modal.selectedClient && String(modal.selectedClient.id) === String(c.id);
    return `<div class="client-pick" role="option" aria-selected="${sel ? 'true' : 'false'}" tabindex="0" data-cid="${esc(c.id)}" style="padding:10px 14px;border:1px solid ${sel ? 'var(--ac)' : 'var(--bd-s)'};border-radius:8px;cursor:pointer;background:${sel ? 'var(--ac-wash)' : 'var(--bg-h)'};transition:border-color .2s,background .2s">
      <div style="font-weight:600;font-size:13px;color:var(--tx-p)">${esc(c.name)}</div>
      <div style="font-size:11px;color:var(--tx-m)">${esc(c.email)}</div>
    </div>`;
  }).join('');
}

function modalStepHtml() {
  const m = modal;

  /* ── Étape 1 : Sélectionner / créer le client ── */
  if (m.step === 1) {
    if (m.creatingNewClient) {
      return `
        <div class="modal-info-banner">Nouveau client, les identifiants de connexion lui seront communiqués.</div>
        <div class="modal-fg"><label class="modal-fl">Nom complet <span class="modal-req">*</span></label>
          <input class="modal-fi" id="nc-nom" placeholder="Ex: Kouamé Bamba" value="${esc(m.newClientData.nom)}"></div>
        <div class="modal-fg"><label class="modal-fl">Adresse email <span class="modal-req">*</span></label>
          <input class="modal-fi" id="nc-email" type="email" placeholder="client@gmail.com" value="${esc(m.newClientData.email)}"></div>
        <div class="modal-fg"><label class="modal-fl">Téléphone <span class="modal-opt">Optionnel</span></label>
          <input class="modal-fi" id="nc-tel" type="tel" placeholder="+225 07 00 00 00" value="${esc(m.newClientData.telephone)}"></div>
        <div class="modal-fg"><label class="modal-fl">Mot de passe provisoire <span class="modal-req">*</span></label>
          <input class="modal-fi" id="nc-pwd" type="password" placeholder="8 caractères minimum" value="${esc(m.newClientData.password)}"></div>
        <div class="modal-error" id="nc-error">${esc(m.newClientError || '')}</div>`;
    }
    return `
      <div class="modal-fg">
        <label class="modal-fl">Rechercher un client existant</label>
        <input class="modal-fi" id="m-client-search" placeholder="Nom, email…" value="${esc(m.clientSearch)}">
      </div>
      <div class="modal-client-list" id="m-client-list">${clientListHtml()}</div>
      <button type="button" id="m-new-client-btn" class="modal-add-btn">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Créer un nouveau compte client
      </button>`;
  }

  /* ── Étape 2 : Dispositif & WiFi ── */
  if (m.step === 2) {
    return `
      <div class="modal-client-chip">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        ${esc(m.selectedClient ? m.selectedClient.name : '')} <span class="modal-chip-email">${esc(m.selectedClient ? m.selectedClient.email : '')}</span>
      </div>
      <div class="modal-fg"><label class="modal-fl">Nom de l'installation <span class="modal-req">*</span></label>
        <input class="modal-fi" id="m-devname" placeholder="Ex: Maison Famille Konan, Bureau ABJ" value="${esc(m.deviceName)}"></div>
      <div class="modal-fg"><label class="modal-fl">Réseau WiFi du client (SSID) <span class="modal-opt">Optionnel</span></label>
        <input class="modal-fi" id="m-wifi" placeholder="Ex: KONAN-Freebox-5G" value="${esc(m.wifiSsid)}">
        <div class="modal-hint">Ce réseau sera programmé dans l'ESP32 lors de la configuration.</div></div>
      <div class="modal-fg"><label class="modal-fl">Adresse d'installation <span class="modal-opt">Optionnel</span></label>
        <input class="modal-fi" id="m-addr" placeholder="Ex: Apt 3B, Résidence Les Palmiers, Cocody" value="${esc(m.addr)}"></div>
      <div class="modal-fg"><label class="modal-fl">N° de série ESP32 <span class="modal-opt">Optionnel</span></label>
        <input class="modal-fi" id="m-serial" placeholder="Ex: ESP32-WR-2407" value="${esc(m.serial)}"></div>`;
  }

  /* ── Étape 3 : Nommer les capteurs ── */
  if (m.step === 3) {
    const capteursHtml = m.capteurs.map((c, i) => `
      <div class="capteur-row" data-ci="${i}">
        <div class="capteur-row-num">${i + 1}</div>
        <input class="modal-fi capteur-nom-input" data-ci="${i}" placeholder="Ex: Prise salon, Circuit cuisine, Éclairage chambre…" value="${esc(c.nom)}">
        ${m.capteurs.length > 1 ? `<button class="capteur-rm-btn" type="button" data-ci="${i}" aria-label="Supprimer ce capteur">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>` : ''}
      </div>`).join('');
    return `
      <div class="modal-info-banner">Donnez un nom parlant à chaque capteur selon son circuit électrique. Ces noms seront visibles par le client.</div>
      <div id="m-capteurs-list" class="capteurs-list">${capteursHtml}</div>
      <button type="button" id="m-add-capteur" class="modal-add-btn">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Ajouter un capteur
      </button>
      <div class="modal-error" id="capteurs-error"></div>`;
  }

  /* ── Étape 4 : Clé API ── */
  if (m.step === 4) {
    const key = m.serverKey || '-';
    return `
      <div class="modal-info-banner">Copiez cette clé et programmez-la sur l'ESP32. <strong>Elle ne sera plus affichée après cette étape.</strong></div>
      <div class="api-key-box">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--ac-text);flex-shrink:0" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span style="flex:1;word-break:break-all">${esc(key)}</span>
        <button class="copy-btn" type="button" id="m-copy">${m.copied ? '✓ Copié' : 'Copier'}</button>
      </div>
      <div class="qr-placeholder" style="background:#ffffff;padding:8px;display:flex;align-items:center;justify-content:center;border-radius:8px">
        <div id="qr-config-box" style="width:90px;height:90px;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--tx-m)">Génération…</div>
      </div>
      <p style="text-align:center;font-size:12px;color:var(--tx-m)">QR Code de configuration, scanner avec l'app AOCEDA Tech</p>
      <div class="modal-fg" style="margin-top:16px">
        <p style="font-size:12.5px;color:var(--tx-s);line-height:1.6;margin:0">
          <strong>Configuration ESP32 :</strong> Flashez le firmware, puis entrez la clé API ci-dessus + le SSID <strong>${esc(m.wifiSsid || '-')}</strong> dans le fichier <code>config.h</code> de l'ESP32.
        </p>
      </div>`;
  }

  /* ── Étape 5 : Résumé ── */
  const capteurNoms = m.capteursCreated.length
    ? m.capteursCreated.map(c => c.nom).join(', ')
    : m.capteurs.filter(c => c.nom.trim()).map(c => c.nom).join(', ') || '-';
  const rows = [
    ['Client', m.selectedClient ? m.selectedClient.name : '-'],
    ['Installation', m.deviceName || '-'],
    ['Adresse', m.addr || '-'],
    ['WiFi (SSID)', m.wifiSsid || '-'],
    ['Capteurs créés', capteurNoms],
    ['Clé API', m.serverKey ? m.serverKey.slice(0, 18) + '…' : '-'],
    ['Statut', m.createdId ? '✓ Dispositif enregistré' : 'Non enregistré'],
  ];
  return `
    <div style="background:var(--bg-h);border-radius:10px;padding:16px;margin-bottom:14px">
      ${rows.map(([k, v], i) => `<div style="display:flex;justify-content:space-between;gap:12px;font-size:13px;padding:6px 0;${i < rows.length - 1 ? 'border-bottom:1px solid var(--bd-s)' : ''}">
        <span style="color:var(--tx-s);flex-shrink:0">${esc(k)}</span>
        <span style="font-weight:600;color:var(--tx-p);text-align:right;word-break:break-word">${esc(v)}</span>
      </div>`).join('')}
    </div>
    <div class="modal-info-banner" style="background:var(--ok-surf);border-color:color-mix(in srgb,var(--ok) 30%,transparent);color:var(--ok)">
      Cliquez sur <strong>Finaliser</strong> pour confirmer l'installation. Une intervention de type « Installation » sera créée automatiquement.
    </div>`;
}

function renderModal() {
  const root = document.getElementById('modal-root');
  if (!root || !modal) return;
  const m = modal;

  const nextDisabled =
    (m.step === 1 && !m.selectedClient && !m.creatingNewClient) ||
    (m.step === 2 && !m.deviceName.trim()) ||
    (m.step === 3 && !m.capteurs.some(c => c.nom.trim())) ||
    m.creating || m.savingNewClient || m.creatingCapteurs;
  const nextLabel =
    m.creating ? 'Enregistrement…' :
    m.savingNewClient ? 'Création…' :
    m.creatingCapteurs ? 'Création capteurs…' :
    (m.step === 1 && m.creatingNewClient) ? 'Créer le client' : 'Suivant';

  root.innerHTML = `
  <div class="modal-overlay" id="m-overlay">
    <div class="modal-card">
      <div class="modal-header">
        <span class="modal-title">Nouveau dispositif, Étape ${m.step}/5 : ${esc(STEP_TITLES[m.step - 1])}</span>
        <button class="modal-close" type="button" id="m-close"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <div class="step-bar">${[1, 2, 3, 4, 5].map(i => `<div class="step-pip ${i < m.step ? 'done' : i === m.step ? 'cur' : ''}"></div>`).join('')}</div>
        ${modalStepHtml()}
      </div>
      <div class="modal-footer">
        ${m.step > 1 ? '<button class="btn-modal-sec" type="button" id="m-prev">Précédent</button>' : ''}
        <button class="btn-modal-sec" type="button" id="m-cancel">Annuler</button>
        ${m.step < 5
          ? `<button class="btn-modal-pri" type="button" id="m-next"${nextDisabled ? ' disabled' : ''}>${nextLabel}</button>`
          : '<button class="btn-modal-pri" type="button" id="m-finish">✓ Enregistrer et finaliser</button>'}
      </div>
    </div>
  </div>`;

  /* ── Événements du modal ── */
  const overlay = document.getElementById('m-overlay');
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.getElementById('m-close').addEventListener('click', closeModal);
  document.getElementById('m-cancel').addEventListener('click', closeModal);
  const prev = document.getElementById('m-prev');
  if (prev) prev.addEventListener('click', () => { m.step -= 1; renderModal(); });
  const next = document.getElementById('m-next');
  if (next) next.addEventListener('click', modalGoNext);
  const finish = document.getElementById('m-finish');
  if (finish) finish.addEventListener('click', modalFinish);

  if (m.step === 1) {
    if (m.creatingNewClient) {
      // Formulaire création client
      ['nc-nom', 'nc-email', 'nc-tel', 'nc-pwd'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', e => {
          const key = { 'nc-nom': 'nom', 'nc-email': 'email', 'nc-tel': 'telephone', 'nc-pwd': 'password' }[id];
          m.newClientData[key] = e.target.value;
          m.newClientError = '';
          const errEl = document.getElementById('nc-error');
          if (errEl) errEl.textContent = '';
        });
      });
    } else {
      const searchInput = document.getElementById('m-client-search');
      const list = document.getElementById('m-client-list');
      if (searchInput) searchInput.addEventListener('input', () => {
        m.clientSearch = searchInput.value;
        if (list) list.innerHTML = clientListHtml();
      });
      const pickClient = item => {
        const clients = m.apiClients || [];
        const c = clients.find(x => String(x.id) === item.dataset.cid);
        if (c) { m.selectedClient = c; m.clientSearch = c.name; renderModal(); }
      };
      if (list) {
        list.addEventListener('click', e => {
          const item = e.target.closest('[data-cid]');
          if (item) pickClient(item);
        });
        list.addEventListener('keydown', e => {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          const item = e.target.closest('[data-cid]');
          if (item) { e.preventDefault(); pickClient(item); }
        });
      }
      const newClientBtn = document.getElementById('m-new-client-btn');
      if (newClientBtn) newClientBtn.addEventListener('click', () => {
        m.creatingNewClient = true;
        m.newClientData = { nom: '', email: '', telephone: '', password: '' };
        m.newClientError = '';
        renderModal();
      });
    }
  } else if (m.step === 2) {
    const bindInput = (id, key) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', e => {
        m[key] = e.target.value;
        const nb = document.getElementById('m-next');
        if (nb) nb.disabled = !m.deviceName.trim() || m.creating;
      });
    };
    bindInput('m-devname', 'deviceName');
    bindInput('m-wifi', 'wifiSsid');
    bindInput('m-addr', 'addr');
    bindInput('m-serial', 'serial');
  } else if (m.step === 3) {
    const bindCapteurInputs = () => {
      document.querySelectorAll('.capteur-nom-input').forEach(inp => {
        inp.addEventListener('input', e => {
          const i = parseInt(e.target.dataset.ci, 10);
          if (m.capteurs[i] !== undefined) {
            m.capteurs[i].nom = e.target.value;
            const nb = document.getElementById('m-next');
            if (nb) nb.disabled = !m.capteurs.some(c => c.nom.trim()) || m.creatingCapteurs;
          }
        });
      });
      document.querySelectorAll('.capteur-rm-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const i = parseInt(btn.dataset.ci, 10);
          m.capteurs.splice(i, 1);
          const listEl = document.getElementById('m-capteurs-list');
          if (listEl) {
            listEl.innerHTML = m.capteurs.map((c, idx) => `
              <div class="capteur-row" data-ci="${idx}">
                <div class="capteur-row-num">${idx + 1}</div>
                <input class="modal-fi capteur-nom-input" data-ci="${idx}" placeholder="Ex: Prise salon, Circuit cuisine…" value="${esc(c.nom)}">
                ${m.capteurs.length > 1 ? `<button class="capteur-rm-btn" type="button" data-ci="${idx}" aria-label="Supprimer">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>` : ''}
              </div>`).join('');
            bindCapteurInputs();
          }
        });
      });
    };
    bindCapteurInputs();
    const addBtn = document.getElementById('m-add-capteur');
    if (addBtn) addBtn.addEventListener('click', () => {
      m.capteurs.push({ nom: '' });
      renderModal();
    });
  } else if (m.step === 4) {
    document.getElementById('m-copy').addEventListener('click', modalCopyKey);
  }
}

/* Création réelle du dispositif au passage de l'étape 2 → 3 (clé API générée côté serveur) */
function modalGoNext() {
  const m = modal;
  if (!m) return;

  // Étape 1, mode création client : POST /api/users/clients/creer/
  if (m.step === 1 && m.creatingNewClient) {
    const { nom, email, password } = m.newClientData;
    const setNcErr = (msg) => { m.newClientError = msg; const el = document.getElementById('nc-error'); if (el) el.textContent = msg; };
    if (!nom.trim() || !email.trim() || !password) { setNcErr('Nom, email et mot de passe sont obligatoires.'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setNcErr('Adresse email invalide.'); return; }
    if (password.length < 8) { setNcErr('Le mot de passe doit contenir au moins 8 caractères.'); return; }
    m.savingNewClient = true;
    renderModal();
    fetchWithAuth('/api/users/clients/creer/', {
      method: 'POST',
      body: JSON.stringify({ nom: nom.trim(), email: email.trim(), password, telephone: (m.newClientData.telephone || '').trim() })
    }).then(r => {
      if (!modal) return;
      m.savingNewClient = false;
      if (r && r.id) {
        const newClient = { id: r.id, name: r.nom || nom.trim(), email: r.email || email.trim() };
        m.apiClients = [newClient, ...(m.apiClients || [])];
        if (Array.isArray(state.clients)) state.clients.unshift({ id: r.id, nom: r.nom || nom.trim(), email: r.email });
        m.selectedClient = newClient;
        m.creatingNewClient = false;
        m.newClientData = { nom: '', email: '', telephone: '', password: '' };
        showToast(`Compte créé pour ${r.nom || nom.trim()}.`);
        renderModal();
      } else {
        const errMsg = r && (r.email || r.nom || r.password || r.detail) || 'Erreur lors de la création du compte.';
        m.newClientError = Array.isArray(errMsg) ? errMsg[0] : String(errMsg);
        const errEl = document.getElementById('nc-error');
        if (errEl) errEl.textContent = m.newClientError;
        renderModal();
      }
    }).catch(() => {
      if (!modal) return;
      m.savingNewClient = false;
      m.newClientError = 'Erreur réseau.';
      renderModal();
    });
    return;
  }

  // Étape 2→3 : créer le dispositif (si pas encore fait)
  if (m.step === 2 && !m.createdId) {
    if (!m.selectedClient) return;
    m.creating = true;
    renderModal();
    fetchWithAuth('/api/sensors/dispositifs/', {
      method: 'POST',
      body: JSON.stringify({
        client: m.selectedClient.id,
        nom: (m.deviceName || '').trim() || undefined,
        adresse: (m.addr || '').trim() || undefined,
        numeroSerie: (m.serial || '').trim() || undefined,
      })
    }).then(d => {
      if (!modal) return;
      m.creating = false;
      if (d && d.apiKeyDevice) {
        m.serverKey = d.apiKeyDevice;
        m.createdId = d.id;
        m.step = 3;
        renderModal();
      } else {
        renderModal();
        showToast("Échec de l'enregistrement du dispositif.", 'error');
      }
    }).catch(() => {
      if (!modal) return;
      m.creating = false;
      renderModal();
      showToast("Erreur réseau : impossible d'enregistrer le dispositif.", 'error');
    });
    return;
  }

  // Retour puis re-avance depuis l'étape 2 : le dispositif existe déjà →
  // on resynchronise ses champs (nom / adresse / n° série) avant de continuer,
  // sinon les modifications saisies après création seraient perdues.
  if (m.step === 2 && m.createdId) {
    m.creating = true;
    renderModal();
    fetchWithAuth(`/api/sensors/dispositifs/${m.createdId}/`, {
      method: 'PATCH',
      body: JSON.stringify({
        nom: (m.deviceName || '').trim() || null,
        adresse: (m.addr || '').trim() || null,
        numeroSerie: (m.serial || '').trim() || null,
      })
    }).then(() => { if (!modal) return; m.creating = false; m.step = 3; renderModal(); })
      .catch(() => { if (!modal) return; m.creating = false; m.step = 3; renderModal(); });
    return;
  }

  // Étape 3→4 : créer les capteurs (si pas encore fait)
  if (m.step === 3 && !m.capteursCreated.length) {
    const toCreate = m.capteurs.filter(c => c.nom.trim());
    if (!toCreate.length) {
      const errEl = document.getElementById('capteurs-error');
      if (errEl) errEl.textContent = 'Ajoutez au moins un capteur.';
      return;
    }
    m.creatingCapteurs = true;
    renderModal();
    Promise.all(toCreate.map(c =>
      fetchWithAuth('/api/sensors/capteurs/', {
        method: 'POST',
        body: JSON.stringify({
          client: m.selectedClient.id,
          dispositif: m.createdId,
          nom: c.nom.trim(),
          type: 'Courant',
          valeurMax: 2000
        })
      })
    )).then(results => {
      if (!modal) return;
      m.creatingCapteurs = false;
      const ok = results.filter(r => r && r.id);
      if (!ok.length) {
        showToast('Échec de la création des capteurs.', 'error');
        renderModal();
        return;
      }
      m.capteursCreated = ok;
      loadAll();
      m.step = 4;
      renderModal();
      loadQrConfig(m.createdId, m.wifiSsid);
    }).catch(() => {
      if (!modal) return;
      m.creatingCapteurs = false;
      showToast('Erreur réseau lors de la création des capteurs.', 'error');
      renderModal();
    });
    return;
  }

  m.step += 1;
  renderModal();
  if (m.step === 4) loadQrConfig(m.createdId, m.wifiSsid);
}

function modalFinish() {
  const m = modal;
  if (!m) return;
  const capteurNoms = m.capteursCreated.map(c => c.nom).join(', ');
  const desc = [
    `Installation du dispositif "${m.deviceName || m.serial || m.createdId}"`,
    `chez ${m.selectedClient ? m.selectedClient.name : '-'}.`,
    m.wifiSsid ? `WiFi : ${m.wifiSsid}.` : '',
    capteurNoms ? `Capteurs installés : ${capteurNoms}.` : '',
    m.addr ? `Adresse : ${m.addr}.` : '',
  ].filter(Boolean).join(' ');
  fetchWithAuth('/api/sensors/interventions/', {
    method: 'POST',
    body: JSON.stringify({
      typeIntervention: 'INSTALLATION',
      description: desc,
      dateIntervention: new Date().toISOString(),
      statut: 'TERMINEE',
      client: m.selectedClient ? m.selectedClient.id : undefined,
      dispositif: m.createdId || undefined,
    })
  }).then(() => {
    loadAll();
    showToast('Installation finalisée. Intervention créée automatiquement.', 'ok');
    closeModal();
  }).catch(() => {
    showToast('Installation enregistrée (intervention non créée).', 'warn');
    closeModal();
  });
}

/* (modalRunTest supprimé : test de connexion jamais câblé à un bouton, code mort) */

function modalCopyKey() {
  const m = modal;
  if (!m) return;
  if (navigator.clipboard) navigator.clipboard.writeText(modalApiKey()).catch(() => {});
  m.copied = true;
  renderModal();
  setTimeout(() => { if (modal && modal.copied) { modal.copied = false; if (modal.step === 3) renderModal(); } }, 2000);
}

/* ════════════════════════ UTILISATEUR ════════════════════════ */
function refreshAvatars() {
  if (!state.user) return;
  const nom = state.user.nom || 'Technicien';
  const ini = nom.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || 'T';
  
  const applyAv = (el) => {
    if (!el) return;
    if (state.user.photo) {
      el.textContent = '';
      el.style.backgroundImage = `url("${state.user.photo}")`;
      el.style.backgroundSize = 'cover';
      el.style.backgroundPosition = 'center';
    } else {
      el.style.backgroundImage = '';
      el.textContent = ini;
    }
  };
  
  applyAv(document.getElementById('profil-avatar'));
  applyAv(document.getElementById('hdr-user-chip'));
  applyAv(document.getElementById('user-avatar'));
  
  const delBtn = document.getElementById('avatar-del-btn');
  if (delBtn) delBtn.style.display = state.user.photo ? '' : 'none';
  
  const nameEl = document.getElementById('profil-name');
  if (nameEl) nameEl.textContent = nom;
}

function renderUser() {
  /* client-shell.js peuple #user-name, #user-avatar et #hdr-user-chip.
     Pour le technicien, on surcharge #user-role avec matricule + spécialité
     au lieu de l'adresse / n°CIE que client-shell.js affiche pour les clients. */
  if (!state.user) return;
  const roleEl = document.getElementById('user-role');
  if (roleEl) {
    const parts = [];
    if (state.user.matricule) parts.push(state.user.matricule);
    if (state.user.specialite) parts.push(state.user.specialite);
    roleEl.textContent = parts.length ? parts.join(' · ') : 'Technicien';
  }
  refreshAvatars();
}

function loadUser() {
  fetchWithAuth('/api/users/me/')
    .then(d => {
      // Garde de rôle : un client ne doit pas rester sur l'espace technicien
      // (les API sont déjà protégées côté serveur ; ceci évite une page inutile).
      if (d && d.role === 'client') { window.location.href = '/dashboard/'; return; }
      if (d && d.nom) {
        state.user = d;
        renderUser();
        // Pré-remplir le formulaire paramètres
        renderTpProfilView();
        const notifEmail = document.getElementById('tp-notif-email');
        if (notifEmail) notifEmail.checked = d.notifEmail !== false;
        const notifA2f = document.getElementById('tp-notif-a2f');
        if (notifA2f) notifA2f.checked = !!d.is_2fa_enabled;
        refreshAvatars();
      }
    })
    .catch(err => console.error(err));
}

function renderTpProfilView() {
  const d = state.user;
  if (!d) return;
  const view = document.getElementById('tp-profil-view');
  if (!view) return;
  view.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:16px">
      <div style="display:flex;flex-direction:column"><span style="font-size:12px;color:var(--tx-s)">Nom complet</span><span style="font-size:14px;font-weight:600;color:var(--tx-p)">${esc(d.nom || '-')}</span></div>
      <div style="display:flex;flex-direction:column"><span style="font-size:12px;color:var(--tx-s)">Adresse email</span><span style="font-size:14px;font-weight:600;color:var(--tx-p)">${esc(d.email || '-')}</span></div>
      <div style="display:flex;flex-direction:column"><span style="font-size:12px;color:var(--tx-s)">Matricule</span><span style="font-size:14px;font-weight:600;color:var(--tx-p)">${esc(d.matricule || '-')}</span></div>
      <div style="display:flex;flex-direction:column"><span style="font-size:12px;color:var(--tx-s)">Spécialité</span><span style="font-size:14px;font-weight:600;color:var(--tx-p)">${esc(d.specialite || '-')}</span></div>
      <div style="display:flex;flex-direction:column"><span style="font-size:12px;color:var(--tx-s)">Téléphone</span><span style="font-size:14px;font-weight:600;color:var(--tx-p)">${esc(d.telephone || '-')}</span></div>
    </div>
  `;
}

/* ════════════════════════ CALIBRATION (grille) ════════════════════════ */
function renderCalibration() {
  const container = document.getElementById('calibration-grid');
  if (!container) return;

  // On n'affiche que les capteurs réellement installés (rattachés à un dispositif) ;
  // les capteurs du pool non assignés (dispositif=null) ne sont pas calibrables ici.
  const capteurs = (Array.isArray(state.capteurs) ? state.capteurs : []).filter(c => c.dispositif);
  const devices  = Array.isArray(state.devices)  ? state.devices  : [];

  if (capteurs.length === 0) {
    container.innerHTML = `
    <div class="calib-empty">
      <svg class="calib-empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
      <h2 class="calib-empty-title">Aucun capteur disponible</h2>
      <p class="calib-empty-text">Installez au moins un capteur via un dispositif ESP32 pour accéder à la calibration.</p>
    </div>`;
    return;
  }

  // Construire les données de chaque capteur avec leur statut
  const capteurData = capteurs.map(c => {
    const dev = devices.find(d => d.id === c.dispositif);
    const devLabel = dev ? (dev.nom || dev.numeroSerie || ('ESP32-' + String(dev.id).replace(/-/g, '').slice(0, 7).toUpperCase())) : '-';
    const clientLabel = dev ? (dev.client_nom || dev.client_email || '-') : '-';
    const coeff = c.coeffCalibration ? parseFloat(c.coeffCalibration) : 1;
    const devStat = dev ? deviceStatus(dev) : 'offline';
    let statusCl, statusLbl, statusKey;
    if (!c.actif) {
      statusCl = 'calib-status-disabled';
      statusLbl = 'Désactivé';
      statusKey = 'critique';
    } else if (devStat === 'offline') {
      statusCl = 'calib-status-err';
      statusLbl = 'Critique (Hors ligne)';
      statusKey = 'critique';
    } else if (!c.derniereCalibration) {
      statusCl = 'calib-status-warn';
      statusLbl = 'À calibrer';
      statusKey = 'attention';
    } else {
      statusCl = 'calib-status-ok';
      statusLbl = 'OK';
      statusKey = 'ok';
    }
    return { c, dev, devLabel, clientLabel, coeff, statusCl, statusLbl, statusKey, lastCalib: c.derniereCalibration || null };
  });

  // Résumé dans le header
  const sumEl = document.getElementById('calib-summary');
  if (sumEl) {
    const nOk = capteurData.filter(x => x.statusKey === 'ok').length;
    const nWarn = capteurData.filter(x => x.statusKey === 'attention').length;
    const nErr = capteurData.filter(x => x.statusKey === 'critique').length;
    sumEl.innerHTML = [
      nOk > 0 ? `<span class="calib-sum-chip calib-sum-ok">${nOk} OK</span>` : '',
      nWarn > 0 ? `<span class="calib-sum-chip calib-sum-warn">${nWarn} Attention</span>` : '',
      nErr > 0 ? `<span class="calib-sum-chip calib-sum-err">${nErr} Critique</span>` : ''
    ].join('');
    // Badge sidebar calibration
    const calibBadge = document.getElementById('nav-calib-badge');
    if (calibBadge) { calibBadge.textContent = String(nWarn + nErr); calibBadge.style.display = (nWarn + nErr) > 0 ? '' : 'none'; }
  }

  // Filtrage
  const q = (state.calibSearch || '').toLowerCase().trim();
  const f = state.calibFilter || 'tous';
  const filtered = capteurData.filter(x => {
    if (f !== 'tous' && x.statusKey !== f) return false;
    if (q && !x.c.nom.toLowerCase().includes(q) && !x.clientLabel.toLowerCase().includes(q) && !x.devLabel.toLowerCase().includes(q)) return false;
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="es-title">Aucun capteur ne correspond aux filtres.</div></div>`;
    return;
  }

  const cards = filtered.map(({ c, devLabel, clientLabel, coeff, statusCl, statusLbl, lastCalib }) => {

    return `<div class="calib-card">
      <div class="calib-card-head">
        <div>
          <div class="calib-card-name">${esc(c.nom || 'Capteur ' + c.id)}</div>
          <div class="calib-card-device">${esc(devLabel)} · ${esc(clientLabel)}</div>
        </div>
        <span class="calib-status-badge ${statusCl}">${statusLbl}</span>
      </div>
      <div class="calib-rows">
        <div class="calib-row">
          <span class="calib-row-lbl">Coefficient Kcal</span>
          <span class="calib-row-val calib-coeff">${coeff.toFixed(4)}</span>
        </div>
        <div class="calib-row">
          <span class="calib-row-lbl">Dernière calibration</span>
          <span class="calib-row-val">${lastCalib ? formatDate(lastCalib) : '-'}</span>
        </div>
        <div class="calib-row">
          <span class="calib-row-lbl">État capteur</span>
          <span class="calib-row-val" style="color:${c.actif ? 'var(--ok)' : 'var(--tx-m)'}">${c.actif ? 'Actif' : 'Inactif'}</span>
        </div>
      </div>
      <div class="calib-foot">
        <button class="btn-calib" type="button" data-calib-id="${esc(c.id)}">Calibrer</button>
      </div>
    </div>`;
  }).join('');

  container.innerHTML = `<div class="calib-grid-wrap">${cards}</div>`;

  // Délégation : boutons "Calibrer"
  container.querySelectorAll('[data-calib-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const cid = btn.dataset.calibId;
      const cap = capteurs.find(c => String(c.id) === String(cid));
      if (!cap) return;
      const dev = devices.find(d => d.id === cap.dispositif);
      const devObj = dev ? {
        id: dev.id, raw: dev, capteurs: [cap],
        client: dev.client_nom || dev.client_email || 'Client',
        device: 'ESP32-' + String(dev.id).replace(/-/g, '').slice(0, 7).toUpperCase(),
        calib: true, status: dev.estConnecté ? 'online' : 'offline', addr: dev.adresseIP || '-', fw: dev.firmwareVersion || '-', last: '-'
      } : { id: null, raw: null, capteurs: [cap], client: '-', device: '-', calib: true, status: 'offline', addr: '-', fw: '-', last: '-' };
      calibrate(devObj);
    });
  });
}

/* ════════════════════════ PARAMÈTRES TECHNICIEN ════════════════════════ */
function initParamsSection() {
  // ── Photo de profil (upload multipart + suppression) ──
  const camBtn = document.getElementById('avatar-cam-btn');
  const fileInput = document.getElementById('avatar-input');
  const delBtn = document.getElementById('avatar-del-btn');

  function avatarMsg(txt, kind) {
    const el = document.getElementById('avatar-feedback');
    if (!el) return;
    el.textContent = txt;
    el.className = 'avatar-feedback ' + (kind || '');
  }

  function uploadPhoto(file) {
    if (state.uploadingPhoto) return;
    if (!/^image\//.test(file.type || '')) { avatarMsg('Le fichier doit être une image.', 'err'); return; }
    if (file.size > 5 * 1024 * 1024) { avatarMsg('Image trop lourde (maximum 5 Mo).', 'err'); return; }
    state.uploadingPhoto = true;
    avatarMsg('Envoi…', '');
    const fd = new FormData();
    fd.append('photo', file);
    window.AOCEDA.authFetch('/api/users/me/photo/', { method: 'POST', body: fd })
      .then(res => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then(data => {
        if (state.user) state.user.photo = (data && data.photo) || null;
        refreshAvatars();
        avatarMsg('Photo mise à jour.', 'ok');
        setTimeout(() => avatarMsg('', ''), 3000);
      })
      .catch(() => avatarMsg("Échec de l'envoi de la photo.", 'err'))
      .finally(() => { state.uploadingPhoto = false; });
  }

  function deletePhoto() {
    if (state.uploadingPhoto) return;
    state.uploadingPhoto = true;
    avatarMsg('Suppression…', '');
    window.AOCEDA.authFetch('/api/users/me/photo/', { method: 'DELETE' })
      .then(res => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then(() => {
        if (state.user) state.user.photo = null;
        refreshAvatars();
        avatarMsg('Photo supprimée.', 'ok');
        setTimeout(() => avatarMsg('', ''), 3000);
      })
      .catch(() => avatarMsg('Échec de la suppression.', 'err'))
      .finally(() => { state.uploadingPhoto = false; });
  }

  if (camBtn && fileInput) {
    camBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) uploadPhoto(f);
    });
  }
  if (delBtn) delBtn.addEventListener('click', deletePhoto);

  /* Profil, enregistrement (nom, spécialité, téléphone) */
  const btnEditProfil = document.getElementById('btn-edit-tp-profil');
  if (btnEditProfil) btnEditProfil.addEventListener('click', editTechnicienProfileModal);

function editTechnicienProfileModal() {
  const d = state.user;
  if (!d) return;
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'edit-tp-profil-' + Date.now();
  
  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="edit-tp-title">
    <div class="modal-card" style="max-width:440px">
      <div class="modal-header">
        <span class="modal-title" id="edit-tp-title">Éditer le profil technicien</span>
        <button class="modal-close" type="button" id="etp-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <div class="modal-fg">
          <label class="modal-fl" for="etp-nom">Nom complet <span class="modal-req">*</span></label>
          <input class="modal-fi" id="etp-nom" type="text" value="${esc(d.nom || '')}" placeholder="Votre nom complet" autocomplete="name">
        </div>
        <div class="modal-fg">
          <label class="modal-fl" for="etp-email">Adresse e-mail <span class="modal-req">*</span></label>
          <input class="modal-fi" id="etp-email" type="email" value="${esc(d.email || '')}" placeholder="nouvel@email.com" autocomplete="email">
        </div>
        <div class="modal-fg">
          <label class="modal-fl" for="etp-spe">Spécialité</label>
          <input class="modal-fi" id="etp-spe" type="text" value="${esc(d.specialite || '')}" placeholder="Ex : Électricité résidentielle">
        </div>
        <div class="modal-fg">
          <label class="modal-fl" for="etp-tel">Téléphone</label>
          <input class="modal-fi" id="etp-tel" type="tel" value="${esc(d.telephone || '')}" placeholder="+225 07 00 00 00">
        </div>
        <div id="etp-err" style="font-size:12px;color:var(--err);min-height:16px;margin-top:4px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-cancel" id="etp-cancel" type="button">Annuler</button>
        <button class="btn-p" id="etp-ok" type="button">Enregistrer</button>
      </div>
    </div>
  </div>`;
  
  const close = () => { const el = document.getElementById(id); if (el) el.remove(); };
  document.getElementById('etp-close').addEventListener('click', close);
  document.getElementById('etp-cancel').addEventListener('click', close);
  
  document.getElementById('etp-ok').addEventListener('click', () => {
    const nom = (document.getElementById('etp-nom').value || '').trim();
    const email = (document.getElementById('etp-email').value || '').trim();
    const spe = (document.getElementById('etp-spe').value || '').trim();
    const tel = (document.getElementById('etp-tel').value || '').trim();
    const err = document.getElementById('etp-err');
    const btn = document.getElementById('etp-ok');
    
    if (!nom || !email) { err.textContent = 'Le nom et l\'email sont obligatoires.'; return; }
    btn.disabled = true;
    err.textContent = 'Enregistrement en cours...';
    err.style.color = 'var(--tx-p)';
    
    fetchWithAuth('/api/users/me/', {
      method: 'PUT',
      body: JSON.stringify({ nom: nom, email: email, specialite: spe, telephone: tel || null })
    }).then(r => {
      if (r && r.id) {
        state.user.nom = r.nom;
        state.user.email = r.email;
        state.user.specialite = r.specialite;
        state.user.telephone = r.telephone;
        renderUser();
        renderTpProfilView();
        const nameEl = document.getElementById('user-name');
        if (nameEl && r.nom) nameEl.textContent = r.nom;
        showToast('Profil enregistré avec succès.', 'ok');
        close();
      } else {
        err.textContent = r.email ? ('Erreur email: ' + r.email[0]) : 'Échec de l\'enregistrement.';
        err.style.color = 'var(--err)';
        btn.disabled = false;
      }
    }).catch(() => {
      err.textContent = 'Erreur réseau.';
      err.style.color = 'var(--err)';
      btn.disabled = false;
    });
  });
}

  /* Notifications, enregistrement */
  const btnNotif = document.getElementById('tp-notif-save');
  if (btnNotif) btnNotif.addEventListener('click', () => {
    const chk = document.getElementById('tp-notif-email');
    const fb = document.getElementById('tp-notif-feedback');
    if (fb) { fb.textContent = 'Enregistrement…'; fb.className = 'tp-feedback'; }
    fetchWithAuth('/api/users/me/', {
      method: 'PUT',
      body: JSON.stringify({ notifEmail: chk ? chk.checked : true })
    }).then(r => {
      if (r && r.id !== undefined) {
        if (state.user) state.user.notifEmail = r.notifEmail;
        if (fb) { fb.textContent = '✓ Préférences enregistrées'; fb.className = 'tp-feedback ok'; }
        setTimeout(() => { if (fb) { fb.textContent = ''; fb.className = 'tp-feedback'; } }, 3000);
      } else {
        if (fb) { fb.textContent = 'Échec.'; fb.className = 'tp-feedback err'; }
      }
    }).catch(() => {
      if (fb) { fb.textContent = 'Erreur réseau.'; fb.className = 'tp-feedback err'; }
    });
  });

  /* A2F Toggle */
  const a2fTog = document.getElementById('tp-notif-a2f');
  if (a2fTog) {
    a2fTog.addEventListener('change', (e) => {
      const newVal = e.target.checked;
      fetchWithAuth('/api/users/me/2fa/', {
        method: 'POST',
        body: JSON.stringify({ enable: newVal })
      }).then(res => {
        if (res && res.is_2fa_enabled !== undefined) {
          if (state.user) state.user.is_2fa_enabled = res.is_2fa_enabled;
          e.target.checked = res.is_2fa_enabled;
          showToast(res.is_2fa_enabled ? 'A2F activée avec succès.' : 'A2F désactivée.', 'ok');
        } else {
          e.target.checked = !newVal; // revert
          showToast('Erreur lors de la modification de l\'A2F.', 'err');
        }
      }).catch(() => {
        e.target.checked = !newVal; // revert
        showToast('Erreur réseau.', 'err');
      });
    });
  }

  /* Sécurité, changement mot de passe */
  const btnMdp = document.getElementById('tp-mdp-save');
  if (btnMdp) btnMdp.addEventListener('click', () => {
    const ancien  = (document.getElementById('tp-mdp-ancien')  || {}).value || '';
    const nouveau = (document.getElementById('tp-mdp-nouveau') || {}).value || '';
    const confirm = (document.getElementById('tp-mdp-confirm') || {}).value || '';
    const fb = document.getElementById('tp-mdp-feedback');
    if (!ancien || !nouveau) {
      if (fb) { fb.textContent = 'Remplissez tous les champs.'; fb.className = 'tp-feedback err'; }
      return;
    }
    if (nouveau !== confirm) {
      if (fb) { fb.textContent = 'Les nouveaux mots de passe ne correspondent pas.'; fb.className = 'tp-feedback err'; }
      return;
    }
    if (nouveau.length < 8) {
      if (fb) { fb.textContent = 'Le mot de passe doit contenir au moins 8 caractères.'; fb.className = 'tp-feedback err'; }
      return;
    }
    if (fb) { fb.textContent = 'Modification…'; fb.className = 'tp-feedback'; }
    fetchWithAuth('/api/users/me/password/', {
      method: 'PUT',
      body: JSON.stringify({ old_password: ancien, new_password: nouveau })
    }).then(r => {
      // 204 = succès (null retourné par fetchWithAuth)
      if (r === null || (r && r.detail !== undefined && !r.old_password && !r.new_password)) {
        if (fb) { fb.textContent = '✓ Mot de passe modifié'; fb.className = 'tp-feedback ok'; }
        ['tp-mdp-ancien', 'tp-mdp-nouveau', 'tp-mdp-confirm'].forEach(id => {
          const el = document.getElementById(id); if (el) el.value = '';
        });
        setTimeout(() => { if (fb) { fb.textContent = ''; fb.className = 'tp-feedback'; } }, 3000);
      } else {
        const msg = r && (r.old_password || r.new_password || r.detail) || 'Échec du changement de mot de passe.';
        if (fb) { fb.textContent = Array.isArray(msg) ? msg[0] : String(msg); fb.className = 'tp-feedback err'; }
      }
    }).catch(() => {
      if (fb) { fb.textContent = 'Erreur réseau.'; fb.className = 'tp-feedback err'; }
    });
  });

  /* Zone de danger : demande réelle de désactivation (transmise aux administrateurs
     par e-mail + journalisée), plus un simple alert() qui ne faisait rien. */
  const btnDesactivation = document.getElementById('btn-demander-desactivation');
  if (btnDesactivation) btnDesactivation.addEventListener('click', () => {
    const fb = document.getElementById('desactivation-feedback');
    if (!confirm('Confirmer la demande de désactivation de votre compte auprès des administrateurs ?')) return;
    btnDesactivation.disabled = true;
    if (fb) { fb.textContent = 'Envoi de la demande…'; fb.className = 'tp-feedback'; }
    fetchWithAuth('/api/users/me/demander-desactivation/', { method: 'POST' })
      .then(r => {
        if (fb) { fb.textContent = (r && r.detail) || 'Votre demande a été transmise aux administrateurs.'; fb.className = 'tp-feedback ok'; }
        showToast('Demande de désactivation envoyée.', 'success');
      })
      .catch(() => {
        if (fb) { fb.textContent = "Échec de l'envoi de la demande."; fb.className = 'tp-feedback err'; }
      })
      .finally(() => { btnDesactivation.disabled = false; });
  });

  // --- Gestion de la navigation interne des Paramètres ---
  function setTpSection(secId) {
    document.querySelectorAll('.settings-nav .snav-item[data-tpsec]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tpsec === secId);
    });
    document.querySelectorAll('.settings-main .tp-sub-section').forEach(sec => {
      sec.style.display = (sec.id === 'tp-sec-' + secId) ? '' : 'none';
    });
  }

  document.querySelectorAll('.settings-nav .snav-item[data-tpsec]').forEach(btn => {
    btn.addEventListener('click', () => setTpSection(btn.dataset.tpsec));
  });


  /* Apparence, radio thème */
  const radioLight = document.querySelector('.tp-theme-card input[value="light"]');
  const radioDark  = document.querySelector('.tp-theme-card input[value="dark"]');
  const setRadios = () => {
    if (radioLight) radioLight.checked = state.theme === 'light';
    if (radioDark)  radioDark.checked  = state.theme === 'dark';
  };
  setRadios();
  document.querySelectorAll('.tp-theme-card input[name="tp-theme"]').forEach(radio => {
    radio.addEventListener('change', () => {
      if (radio.checked) {
        state.theme = radio.value;
        applyTheme();
        setRadios();
      }
    });
  });
}

/* ════════════════════════ MES CLIENTS ════════════════════════ */
function renderClients() {
  const container = document.getElementById('clients-grid');
  if (!container) return;

  const devices = Array.isArray(state.devices) ? state.devices : [];
  const searchEl = document.getElementById('clients-search');
  const q = (searchEl ? searchEl.value : '').toLowerCase();

  // Dédupliquer les clients à partir des dispositifs
  const seen = new Set();
  const clients = [];
  devices.forEach(d => {
    if (!d.client) return;
    const key = String(d.client);
    if (!seen.has(key)) {
      seen.add(key);
      // Fusionner avec state.clients pour avoir le téléphone et le nom complet
      const apiData = Array.isArray(state.clients) ? state.clients.find(c => String(c.id) === key) : null;
      clients.push({
        id: d.client,
        name: (apiData && apiData.nom) || d.client_nom || '-',
        email: d.client_email || '-',
        telephone: (apiData && apiData.telephone) || '',
        devices: devices.filter(x => String(x.client) === key)
      });
    }
  });

  // Compléter avec les clients chargés dans state.clients (sans dispositif)
  if (Array.isArray(state.clients)) {
    state.clients.forEach(c => {
      if (!seen.has(String(c.id))) {
        seen.add(String(c.id));
        clients.push({ id: c.id, name: c.nom || c.name || '-', email: c.email || '-', telephone: c.telephone || '', devices: [] });
      }
    });
  }

  const filtered = q
    ? clients.filter(c => c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q))
    : clients;

  if (!filtered.length) {
    container.innerHTML = `
      <div class="client-empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" style="color:var(--ac-text);opacity:.4;margin:0 auto var(--sp-3)" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <div style="font-family:var(--fd);font-size:.9375rem;font-weight:700;color:var(--tx-p);margin-bottom:var(--sp-2)">${q ? 'Aucun client correspondant' : 'Aucun client'}</div>
        <div style="font-size:.875rem;color:var(--tx-s)">${q ? 'Modifiez la recherche.' : 'Installez un premier dispositif via « Nouveau dispositif ».'}</div>
      </div>`;
    return;
  }

  container.innerHTML = `<div class="clients-cards">${filtered.map(c => {
    const nbDevices = c.devices.length;
    const nbOnline = c.devices.filter(d => deviceStatus(d) === 'online').length;
    const initiales = c.name.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || '?';
    return `
      <div class="client-card">
        <div class="client-card-head">
          <div class="client-av">${esc(initiales)}</div>
          <div class="client-info">
            <div class="client-name">${esc(c.name)}</div>
            <div class="client-email">${esc(c.email)}</div>
          </div>
          <button class="icon-btn client-act-edit" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}" data-cemail="${esc(c.email)}" data-ctel="${esc(c.telephone)}" aria-label="Éditer le client" title="Éditer le client" style="margin-left:auto">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
        </div>
        <div class="client-card-stats">
          <div class="client-stat">
            <div class="client-stat-val">${nbDevices}</div>
            <div class="client-stat-lbl">dispositif${nbDevices > 1 ? 's' : ''}</div>
          </div>
          <div class="client-stat">
            <div class="client-stat-val ${nbOnline === nbDevices && nbDevices > 0 ? 'cs-ok' : nbOnline === 0 && nbDevices > 0 ? 'cs-err' : ''}">${nbOnline}</div>
            <div class="client-stat-lbl">en ligne</div>
          </div>
          <div class="client-stat">
            <div class="client-stat-val">${c.devices.reduce((acc, d) => acc + (Array.isArray(state.capteurs) ? state.capteurs.filter(cp => cp.dispositif === d.id).length : 0), 0)}</div>
            <div class="client-stat-lbl">capteurs</div>
          </div>
        </div>
        ${nbDevices > 0 ? `<div class="client-card-devices">${c.devices.slice(0, 3).map(d => `
          <div class="client-dev-row">
            <span class="client-dev-dot ${deviceStatus(d) === 'online' ? 'cs-ok' : deviceStatus(d) === 'offline' ? 'cs-err' : 'cs-warn'}"></span>
            <span class="client-dev-name">${esc(d.nom || d.numeroSerie || ('ESP32-' + String(d.id).replace(/-/g, '').slice(0, 7).toUpperCase()))}</span>
            <span class="client-dev-status">${(ST_MAP[deviceStatus(d)] || ST_MAP.offline).lbl}</span>
          </div>`).join('')}
          ${c.devices.length > 3 ? `<div style="font-size:11px;color:var(--tx-m);margin-top:4px">+${c.devices.length - 3} autre${c.devices.length - 3 > 1 ? 's' : ''}</div>` : ''}
        </div>` : `<div style="font-size:12px;color:var(--tx-m);font-style:italic">Aucun dispositif installé</div>`}
        <div class="client-card-actions">
          <button class="action-btn client-act-install" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}" data-cemail="${esc(c.email)}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nouvelle installation
          </button>
          ${nbDevices > 0 ? `<button class="action-btn client-act-capteurs" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}">Capteurs</button>` : ''}
          <button class="action-btn client-act-abo" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}">Abonnement</button>
          <button class="action-btn client-act-interventions" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}">Historique</button>
          <button class="action-btn client-act-notes" type="button" data-cid="${esc(c.id)}" data-cname="${esc(c.name)}">Notes</button>
        </div>
      </div>`;
  }).join('')}</div>`;
}

/* Libellés des actions du journal d'équipe (apps.accounts.models.AuditLog.action).
   Journal PARTAGÉ par toute l'équipe (pas un journal personnel) : chacun peut y voir
   les actions de ses collègues techniciens, avec qui/quoi/quand. */
const ACTION_LBL = {
  CALIBRATION_AUTO: 'Calibration automatique',
  CALIBRATION_MANUELLE: 'Modification du coefficient de calibration',
  EDITION_CAPTEUR: 'Modification d’un capteur',
  'REGENERATION_CLÉ': 'Régénération de la clé API',
  ASSIGNATION_CAPTEUR: 'Assignation d’un capteur',
  CREATION_CLIENT: 'Création du compte client',
  EDITION_CLIENT: 'Modification des informations client',
  EDITION_ABONNEMENT: 'Modification de l’abonnement',
  REASSIGNATION_DISPOSITIF: 'Transfert de dispositif',
  'CRÉATION_INTERVENTION': 'Création d’une intervention',
  'RECHARGE_CRÉDIT': 'Recharge de crédit prépayé',
  CONNEXION: 'Connexion',
  'DÉCONNEXION': 'Déconnexion',
  DEMANDE_DESACTIVATION: 'Demande de désactivation de compte',
  NOTE_CLIENT: 'Note interne ajoutée',
};

/* Historique complet d'un client = interventions (cycle formel panne/installation/
   calibration) + journal d'équipe (actions ponctuelles : calibration directe, édition
   client/abonnement, régénération de clé…), fusionnés et triés par date décroissante.
   Traçabilité "qui a fait quoi, quand" exigée sur l'espace technicien. */
function showClientInterventions(clientId, clientName) {
  const ivEntries = (Array.isArray(state.interventions) ? state.interventions : [])
    .filter(iv => String(iv.client) === String(clientId))
    .map(iv => ({
      date: iv.dateIntervention,
      label: TYPE_LBL[iv.typeIntervention] || iv.typeIntervention,
      badge: `<span class="status-badge ${(S_MAP[STATUT_UI[iv.statut]] || S_MAP.pending).cl}">${esc((S_MAP[STATUT_UI[iv.statut]] || S_MAP.pending).l)}</span>`,
      technicien: iv.technicien_nom || 'Technicien',
      detail: iv.description || '-',
      resultat: iv['résultat'] || null,
    }));

  // ?role=technicien : l'historique montre le travail des techniciens sur ce
  // client, pas les actions du client lui-même (connexions, recharges…).
  fetchWithAuth(`/api/sensors/journal/?client=${clientId}&role=technicien`)
    .then(data => {
      const journalEntries = window.AOCEDA.asList(data).map(j => ({
        date: j.timestamp,
        label: ACTION_LBL[j.action] || j.action,
        badge: '',
        technicien: j.utilisateur_nom || 'Technicien',
        detail: j.description || '-',
        resultat: null,
      }));
      renderClientHistorique(clientName, ivEntries.concat(journalEntries));
    })
    .catch(() => renderClientHistorique(clientName, ivEntries));
}

function renderClientHistorique(clientName, entries) {
  entries.sort((a, b) => new Date(b.date) - new Date(a.date));

  if (entries.length === 0) {
    showInfo(`Historique, ${clientName}`, `<div style="text-align:center;padding:12px;color:var(--tx-s)">Aucune action n'a été enregistrée pour ce client.</div>`);
    return;
  }

  const rows = entries.map(e => `
    <div style="padding:10px 0;border-bottom:1px solid var(--bd-s);font-size:13px">
      <div style="display:flex;justify-content:space-between;font-weight:600;color:var(--tx-p)">
        <span>${esc(e.label)}</span>${e.badge}
      </div>
      <div style="font-size:11.5px;color:var(--tx-s);margin-top:2px">${new Date(e.date).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })} · par ${esc(e.technicien)}</div>
      <div style="font-size:12px;color:var(--tx-p);margin-top:4px;line-height:1.4">${esc(e.detail)}</div>
      ${e.resultat ? `<div style="font-size:12px;color:var(--ok);margin-top:2px;font-style:italic">Résultat : ${esc(e.resultat)}</div>` : ''}
    </div>
  `).join('');

  showInfo(`Historique, ${clientName}`, { html: `<div style="max-height:300px;overflow-y:auto;padding-right:4px">${rows}</div>` });
}

function showClientCapteurs(clientId, clientName) {
  fetchWithAuth(`/api/sensors/capteurs/?client=${clientId}`)
    .then(data => {
      const list = Array.isArray(data) ? data : (data && Array.isArray(data.results) ? data.results : []);
      const rows = list.map(c => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--bd-s);font-size:13px">
          <div>
            <div style="font-weight:600;color:var(--tx-p)">${esc(c.nom)}</div>
            <div style="font-size:11px;color:var(--tx-m)">${esc(c.type)} · Coeff: ${c.coeffCalibration}</div>
          </div>
          <span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:${c.actif ? 'var(--ok-surf)' : 'var(--bg-h)'};color:${c.actif ? 'var(--ok)' : 'var(--tx-m)'}">${c.actif ? 'Actif' : 'Inactif'}</span>
        </div>`).join('');
      showInfo(
        `Capteurs, ${clientName}`,
        { html: list.length
          ? `<div style="max-height:300px;overflow-y:auto">${rows}</div>`
          : '<p style="color:var(--tx-s);font-size:13px">Aucun capteur installé pour ce client.</p>' }
      );
    })
    .catch(() => showToast('Impossible de charger les capteurs.', 'error'));
}

/* Notes internes technicien sur un client : jamais visibles du client, plusieurs
   notes cumulées (pas de champ unique écrasé), chacune horodatée et attribuée. */
function showClientNotes(clientId, clientName) {
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'client-notes-' + Date.now();

  const renderList = notes => notes.length
    ? notes.map(n => `
        <div style="padding:8px 0;border-bottom:1px solid var(--bd-s);font-size:12.5px">
          <div style="font-size:11px;color:var(--tx-s);margin-bottom:2px">${new Date(n.dateCreation).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })} · ${esc(n.technicien_nom || 'Technicien')}</div>
          <div style="color:var(--tx-p);white-space:pre-line">${esc(n.contenu)}</div>
        </div>`).join('')
    : '<p style="color:var(--tx-s);font-size:13px">Aucune note pour ce client.</p>';

  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="cn-title">
    <div class="modal-card" style="max-width:460px">
      <div class="modal-header">
        <span class="modal-title" id="cn-title">Notes internes, ${esc(clientName)}</span>
        <button class="modal-close" type="button" id="cn-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <p style="font-size:11.5px;color:var(--tx-m);margin-bottom:10px">Visibles uniquement par l'équipe technique, jamais par le client.</p>
        <div id="cn-list" style="max-height:220px;overflow-y:auto;margin-bottom:14px">Chargement…</div>
        <div class="modal-fg">
          <label class="modal-fl" for="cn-input">Nouvelle note</label>
          <textarea class="modal-fi" id="cn-input" rows="3" maxlength="2000" placeholder="Ex. accès difficile, prévenir 10 min avant…"></textarea>
        </div>
        <div id="cn-err" style="font-size:12px;color:var(--err);min-height:16px;margin-top:2px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="cn-cancel">Fermer</button>
        <button class="btn-modal-pri" type="button" id="cn-add">Ajouter la note</button>
      </div>
    </div>
  </div>`;

  const close = () => { root.innerHTML = ''; };
  document.getElementById('cn-close').addEventListener('click', close);
  document.getElementById('cn-cancel').addEventListener('click', close);
  document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) close(); });

  function loadNotes() {
    fetchWithAuth(`/api/users/clients/notes/?client=${clientId}`)
      .then(data => {
        const list = document.getElementById('cn-list');
        if (list) list.innerHTML = renderList(window.AOCEDA.asList(data));
      })
      .catch(() => {
        const list = document.getElementById('cn-list');
        if (list) list.innerHTML = '<p style="color:var(--err);font-size:13px">Impossible de charger les notes.</p>';
      });
  }
  loadNotes();

  document.getElementById('cn-add').addEventListener('click', () => {
    const input = document.getElementById('cn-input');
    const err = document.getElementById('cn-err');
    const btn = document.getElementById('cn-add');
    const contenu = (input.value || '').trim();
    if (!contenu) { err.textContent = 'La note ne peut pas être vide.'; return; }
    btn.disabled = true; btn.textContent = 'Ajout…';
    fetchWithAuth('/api/users/clients/notes/', {
      method: 'POST',
      body: JSON.stringify({ client: clientId, contenu })
    }).then(r => {
      btn.disabled = false; btn.textContent = 'Ajouter la note';
      if (r && r.id) {
        input.value = ''; err.textContent = '';
        loadNotes();
      } else {
        const msg = r && (r.contenu || r.detail) || "Échec de l'ajout de la note.";
        err.textContent = Array.isArray(msg) ? msg[0] : String(msg);
      }
    }).catch(() => {
      btn.disabled = false; btn.textContent = 'Ajouter la note';
      err.textContent = 'Erreur réseau.';
    });
  });
}

/* Éditer les informations d'un client existant */
/* CRU Client — Mise à jour (Update) : modale multi-champs conforme au diagramme */
function editClient(clientId, currentName, currentEmail, currentTel) {
  const root = document.getElementById('modal-root');
  if (!root) return;
  const id = 'edit-client-' + Date.now();
  // currentTel est passé via data-ctel du bouton, pré-rempli depuis state.clients lors du rendu

  root.innerHTML = `
  <div class="modal-overlay" id="${esc(id)}" role="dialog" aria-modal="true" aria-labelledby="edit-client-title">
    <div class="modal-card" style="max-width:440px">
      <div class="modal-header">
        <span class="modal-title" id="edit-client-title">Modifier le client</span>
        <button class="modal-close" type="button" id="ec-close" aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      </div>
      <div class="modal-body">
        <p style="font-size:13px;color:var(--tx-s);margin-bottom:16px">Compte : <strong>${esc(currentEmail)}</strong></p>
        <div class="modal-fg">
          <label class="modal-fl" for="ec-nom">Nom complet <span class="modal-req">*</span></label>
          <input class="modal-fi" id="ec-nom" type="text" value="${esc(currentName)}" placeholder="Prénom Nom" autocomplete="name">
        </div>
        <div class="modal-fg">
          <label class="modal-fl" for="ec-tel">Téléphone</label>
          <input class="modal-fi" id="ec-tel" type="tel" value="${esc(currentTel)}" placeholder="+225 07 00 00 00" autocomplete="tel">
        </div>
        <div id="ec-err" style="font-size:12px;color:var(--err);min-height:16px;margin-top:4px"></div>
      </div>
      <div class="modal-footer">
        <button class="btn-modal-sec" type="button" id="ec-cancel">Annuler</button>
        <button class="btn-modal-pri" type="button" id="ec-ok">Enregistrer</button>
      </div>
    </div>
  </div>`;

  const close = () => { root.innerHTML = ''; };
  document.getElementById('ec-close').addEventListener('click', close);
  document.getElementById('ec-cancel').addEventListener('click', close);
  document.getElementById(id).addEventListener('click', e => { if (e.target.id === id) close(); });

  const nomInput = document.getElementById('ec-nom');
  setTimeout(() => { if (nomInput) { nomInput.focus(); nomInput.select(); } }, 40);

  document.getElementById('ec-ok').addEventListener('click', () => {
    const nom = (document.getElementById('ec-nom').value || '').trim();
    const tel = (document.getElementById('ec-tel').value || '').trim();
    const err = document.getElementById('ec-err');
    const btn = document.getElementById('ec-ok');

    if (!nom) { err.textContent = 'Le nom est obligatoire.'; return; }

    btn.disabled = true; btn.textContent = 'Enregistrement…';
    fetchWithAuth(`/api/users/clients/${clientId}/`, {
      method: 'PATCH',
      body: JSON.stringify({ nom, telephone: tel || undefined })
    }).then(r => {
      if (r && r.id) {
        showToast('Client mis à jour.', 'ok');
        loadAll();
        close();
      } else {
        btn.disabled = false; btn.textContent = 'Enregistrer';
        const msg = r && (r.nom || r.detail) || 'Échec de la modification.';
        err.textContent = Array.isArray(msg) ? msg[0] : String(msg);
      }
    }).catch(() => {
      btn.disabled = false; btn.textContent = 'Enregistrer';
      err.textContent = 'Erreur réseau : modification impossible.';
    });
  });

  // Soumission au clavier
  nomInput.addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('ec-ok').click(); });
}

/* ════════════════════════ CHARGEMENT DES DONNÉES ════════════════════════ */
function loadInstallations() {
  // Réponses DRF paginées ({count,next,previous,results}) : déballer via asList.
  fetchWithAuth('/api/sensors/dispositifs/')
    .then(d => { state.devices = window.AOCEDA.asList(d); state.devicesLoaded = true; renderInstallations(); renderCalibration(); renderClients(); })
    .catch(() => { state.devices = []; state.devicesLoaded = true; renderInstallations(); renderCalibration(); });
  fetchWithAuth('/api/sensors/capteurs/')
    .then(d => { state.capteurs = window.AOCEDA.asList(d); renderInstallations(); renderCalibration(); renderClients(); })
    .catch(err => console.error(err));
}

function loadInterventions() {
  fetchWithAuth('/api/sensors/interventions/')
    .then(d => { state.interventions = window.AOCEDA.asList(d); state.interventionsLoaded = true; renderInstallations(); renderInterventions(); })
    .catch(() => { state.interventions = []; state.interventionsLoaded = true; renderInterventions(); });
}

/* Journal d'ÉQUIPE : partagé par tous les techniciens (pas un journal personnel),
   mais limité aux actions des TECHNICIENS (?role=technicien) — les actions des
   clients et des admins sont journalisées dans AuditLog mais n'ont pas leur place
   ici. Chaque entrée = quel technicien a fait quoi (action/description),
   sur quel client, et quand (timestamp). Adossé à AuditLog (apps.accounts). */
function loadJournalEquipe() {
  fetchWithAuth('/api/sensors/journal/?role=technicien')
    .then(d => { state.journal = window.AOCEDA.asList(d); state.journalLoaded = true; renderJournal(); })
    .catch(() => { state.journal = []; state.journalLoaded = true; renderJournal(); });
}

function renderJournal() {
  const tbody = document.getElementById('journal-tbody');
  if (!tbody) return;

  const entries = Array.isArray(state.journal) ? state.journal : [];

  // Peuple le filtre "utilisateur" dynamiquement à partir des entrées chargées
  // (pas d'endpoint dédié à la liste des techniciens : on dérive de ce qu'on a).
  const userSelect = document.getElementById('journal-filter-user');
  if (userSelect && userSelect.dataset.populated !== String(entries.length)) {
    const users = new Map();
    entries.forEach(e => { if (e.utilisateur) users.set(e.utilisateur, e.utilisateur_nom || 'Utilisateur'); });
    const current = userSelect.value;
    userSelect.innerHTML = '<option value="">Tous les techniciens</option>' +
      Array.from(users.entries()).sort((a, b) => a[1].localeCompare(b[1]))
        .map(([id, nom]) => `<option value="${esc(id)}">${esc(nom)}</option>`).join('');
    userSelect.value = current;
    userSelect.dataset.populated = String(entries.length);
  }

  const search = state.journalSearch.toLowerCase();
  const filtered = entries.filter(e => {
    const matchUser = !state.journalUser || String(e.utilisateur) === state.journalUser;
    const matchSearch = !search ||
      (e.utilisateur_nom || '').toLowerCase().includes(search) ||
      (e.client_nom || '').toLowerCase().includes(search) ||
      (e.description || '').toLowerCase().includes(search) ||
      (ACTION_LBL[e.action] || e.action || '').toLowerCase().includes(search);
    return matchUser && matchSearch;
  });

  if (!state.journalLoaded) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:var(--sp-8);color:var(--tx-s)">Chargement du journal…</td></tr>`;
    return;
  }
  if (filtered.length === 0) {
    const msg = entries.length === 0
      ? 'Aucune action enregistrée pour le moment.'
      : 'Aucune entrée ne correspond à votre recherche.';
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:var(--sp-8);color:var(--tx-s)">${msg}</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(e => `
    <tr>
      <td class="cell-last">${esc(formatDate(e.timestamp))}</td>
      <td>${esc(e.utilisateur_nom || '-')}</td>
      <td>${esc(ACTION_LBL[e.action] || e.action)}</td>
      <td>${esc(e.client_nom || '-')}</td>
      <td style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(e.description)}">${esc(e.description || '-')}</td>
    </tr>
  `).join('');
}

function loadAll() {
  loadInstallations();
  loadInterventions();
  fetchWithAuth('/api/users/clients/')
    .then(d => { state.clients = window.AOCEDA.asList(d); renderClients(); })
    .catch(() => { state.clients = []; });
}

/* ════════════════════════ INITIALISATION ════════════════════════ */
function init() {
  applyTheme();

  // Anti-autofill : les navigateurs remplissent parfois le 1er champ texte
  // (la recherche) avec l'email de connexion, ce qui filtre le tableau à vide.
  // On rend les champs de recherche readonly jusqu'au 1er focus utilisateur.
  document.querySelectorAll('.search-input').forEach(inp => {
    inp.value = '';
    inp.setAttribute('readonly', '');
    const unlock = () => inp.removeAttribute('readonly');
    inp.addEventListener('focus', unlock, { once: true });
    inp.addEventListener('pointerdown', unlock, { once: true });
  });

  // Thème clair/sombre, client-shell.js gère aussi #theme-toggle, mais
  // on garde la liaison ici pour la cohérence (les deux peuvent coexister).
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // Navigation sidebar (data-section)
  document.querySelectorAll('.sidebar .nav-item[data-section]').forEach(btn => {
    btn.addEventListener('click', () => setSection(btn.dataset.section));
  });

  // Navigation bottom-nav (mobile, data-section) + feuille « Plus »
  document.querySelectorAll('.bottom-nav .bn-item[data-section], .bn-sheet .bn-item[data-section]').forEach(btn => {
    btn.addEventListener('click', () => setSection(btn.dataset.section));
  });

  // Recherche installations
  const search = document.getElementById('inst-search');
  if (search) search.addEventListener('input', () => { state.search = search.value; renderInstallations(); });

  // Filtres installations
  document.querySelectorAll('#filter-tabs .ft').forEach(btn => {
    btn.addEventListener('click', () => {
      state.filter = btn.dataset.filter;
      document.querySelectorAll('#filter-tabs .ft').forEach(b => {
        const on = b === btn;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      renderInstallations();
    });
  });

  // Nouveau dispositif
  const btnNew = document.getElementById('btn-new-device');
  if (btnNew) btnNew.addEventListener('click', openModal);

  // Fermeture des modales à la touche Échap (accessibilité clavier)
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const root = document.getElementById('modal-root');
    if (root && root.querySelector('.modal-overlay')) closeModal();
  });

  // Actions du tableau des installations (délégation : lignes re-rendues dynamiquement)
  const tbody = document.getElementById('devices-tbody');
  if (tbody) tbody.addEventListener('click', e => {
    const btn = e.target.closest('.action-btn');
    if (!btn) return;
    const d = instRows.find(r => String(r.id) === btn.dataset.id);
    if (!d) return;
     if (btn.dataset.action === 'details') showDetails(d);
    else if (btn.dataset.action === 'diagnostiquer') diagnostiquer(d);
    else if (btn.dataset.action === 'abonnement') manageAbonnement(d);
    else if (btn.dataset.action === 'reassigner') reassignerDevice(d);
    else if (btn.dataset.action === 'calibrate') calibrate(d);
    else if (btn.dataset.action === 'panne') declarePanneDevice(d);
  });

  // Déclarer une panne (section Interventions)
  const btnPanne = document.getElementById('btn-declare-panne');
  if (btnPanne) btnPanne.addEventListener('click', declarePanneGlobal);

  // Exporter mes interventions en CSV (section Interventions)
  const btnExportCsv = document.getElementById('btn-export-inter-csv');
  if (btnExportCsv) btnExportCsv.addEventListener('click', () => {
    downloadFile('/api/sensors/interventions/export/csv/', 'aoceda_interventions.csv')
      .catch(() => showToast("Impossible d'exporter les interventions.", 'error'));
  });

  // Recherche & filtre utilisateur du journal d'équipe
  const journalSearch = document.getElementById('journal-search');
  if (journalSearch) journalSearch.addEventListener('input', () => { state.journalSearch = journalSearch.value; renderJournal(); });
  const journalUserSelect = document.getElementById('journal-filter-user');
  if (journalUserSelect) journalUserSelect.addEventListener('change', () => { state.journalUser = journalUserSelect.value; renderJournal(); });

  // Recherche & filtres interventions
  const interSearch = document.getElementById('inter-search');
  if (interSearch) interSearch.addEventListener('input', () => { state.interSearch = interSearch.value; renderInterventions(); });
  document.querySelectorAll('#inter-filter-tabs .ft').forEach(btn => {
    btn.addEventListener('click', () => {
      state.interFilter = btn.dataset.filter;
      document.querySelectorAll('#inter-filter-tabs .ft').forEach(b => {
        const on = b === btn;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      renderInterventions();
    });
  });

  // Recherche & filtres calibration
  const calibSearch = document.getElementById('calib-search');
  if (calibSearch) calibSearch.addEventListener('input', () => { state.calibSearch = calibSearch.value; renderCalibration(); });
  document.querySelectorAll('#calib-filter-tabs .ft').forEach(btn => {
    btn.addEventListener('click', () => {
      state.calibFilter = btn.dataset.filter;
      document.querySelectorAll('#calib-filter-tabs .ft').forEach(b => {
        const on = b === btn;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      renderCalibration();
    });
  });

  // Actions des cartes/tableau d'intervention (délégation)
  const interTbody = document.getElementById('inter-tbody');
  if (interTbody) interTbody.addEventListener('click', e => {
    const btn = e.target.closest('.action-btn');
    if (!btn) return;
    
    if (btn.dataset.action === 'diagnostiquer') {
      const { rows } = computeRows();
      const fmtDev = rows.find(r => String(r.id) === btn.dataset.id);
      if (fmtDev) diagnostiquer(fmtDev);
      else showToast('Dispositif introuvable.', 'error');
      return;
    }
    
    const iv = interList.find(x => String(x.id) === btn.dataset.id);
    if (!iv) return;
    if (btn.dataset.action === 'fiche') showFiche(iv);
    else if (btn.dataset.action === 'update') updateIv(iv);
    else if (btn.dataset.action === 'planifier') planifierIv(iv);
  });

  // Recherche clients
  const clientsSearch = document.getElementById('clients-search');
  if (clientsSearch) clientsSearch.addEventListener('input', renderClients);

  // Nouveau client (section Mes clients)
  const btnNewClient = document.getElementById('btn-new-client');
  if (btnNewClient) btnNewClient.addEventListener('click', () => {
    openModal();
    if (modal) { modal.creatingNewClient = true; renderModal(); }
  });

  // Actions sur les cartes clients (délégation persistante)
  const clientsGrid = document.getElementById('clients-grid');
  if (clientsGrid) clientsGrid.addEventListener('click', e => {
    const btn = e.target.closest('.client-act-install,.client-act-capteurs,.client-act-abo,.client-act-interventions,.client-act-edit,.client-act-notes');
    if (!btn) return;
    if (btn.classList.contains('client-act-install')) {
      const c = { id: btn.dataset.cid, name: btn.dataset.cname, email: btn.dataset.cemail };
      openModal();
      if (modal) { modal.selectedClient = c; modal.step = 2; renderModal(); }
    } else if (btn.classList.contains('client-act-capteurs')) {
      showClientCapteurs(btn.dataset.cid, btn.dataset.cname);
    } else if (btn.classList.contains('client-act-abo')) {
      const devForAbo = (Array.isArray(state.devices) ? state.devices : []).find(d => String(d.client) === String(btn.dataset.cid));
      manageAbonnement({ raw: { client: btn.dataset.cid }, client: btn.dataset.cname, id: devForAbo ? devForAbo.id : null });
    } else if (btn.classList.contains('client-act-interventions')) {
      showClientInterventions(btn.dataset.cid, btn.dataset.cname);
    } else if (btn.classList.contains('client-act-edit')) {
      editClient(btn.dataset.cid, btn.dataset.cname, btn.dataset.cemail, btn.dataset.ctel || '');
    } else if (btn.classList.contains('client-act-notes')) {
      showClientNotes(btn.dataset.cid, btn.dataset.cname);
    }
  });

  // Initialisation de la section paramètres
  initParamsSection();

  // Premier rendu (valeurs de repli), puis chargement des données réelles
  const targetSection = localStorage.getItem('aoceda_tech_target_section') || 'installations';
  localStorage.removeItem('aoceda_tech_target_section');
  setSection(targetSection);
  renderInstallations();
  renderInterventions();
  renderCalibration();

  loadUser();
  loadAll();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
