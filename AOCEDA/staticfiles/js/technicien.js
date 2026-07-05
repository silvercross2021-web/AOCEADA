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

/* L'espace technicien s'appuie uniquement sur les données réelles de l'API
   (dispositifs, capteurs, interventions, clients). Aucune donnée maquette :
   en l'absence de données, des états vides honnêtes sont affichés. */

const TYPE_LBL = { INSTALLATION: 'Installation nouvelle', CALIBRATION: 'Calibration requise', PANNE: 'Déclaration de panne', MAINTENANCE: 'Maintenance préventive' };
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
  theme: localStorage.getItem('aoceda-theme') || 'light',
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
  calibFilter: 'tous'
};

/* Lignes affichées (pour retrouver un dispositif/intervention depuis un bouton) */
let instRows = [];
let interList = [];

/* ── Utilitaires dates ── */
function timeAgo(iso) {
  if (!iso) return '—';
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `il y a ${Math.round(diff)} s`;
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)} h`;
  return `il y a ${Math.round(diff / 86400)} j`;
}
function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }) + ' ' +
    d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }).replace(':', 'h');
}

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
}

/* ════════════════════════ SECTION (sidebar nav) ════════════════════════ */

const SECTION_META = {
  installations: { title: 'Mes installations', sub: 'Supervision des dispositifs ESP32' },
  interventions:  { title: 'Interventions & pannes', sub: 'Déclarations de pannes et suivi des interventions' },
  calibration:    { title: 'Calibration', sub: 'Coefficients Kcal des capteurs' },
  clients:        { title: 'Mes clients', sub: 'Clients dont vous supervisez les installations' },
  parametres:     { title: 'Paramètres', sub: 'Profil, sécurité et apparence' }
};

function setSection(name) {
  state.section = name;
  state.tab = name; // alias legacy utilisé par renderInstallations()

  // Nav items sidebar
  document.querySelectorAll('.sidebar .nav-item[data-section]').forEach(b => {
    b.classList.toggle('active', b.dataset.section === name);
  });

  // Bottom-nav (mobile)
  document.querySelectorAll('.bottom-nav .bn-item[data-section]').forEach(b => {
    b.classList.toggle('active', b.dataset.section === name);
  });

  // Sections contenu
  const ids = ['installations', 'interventions', 'calibration', 'clients', 'parametres'];
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
    const needsCalib = caps.some(c => Math.abs((parseFloat(c.coeffCalibration) || 1) - 1) >= CALIB_WARN);
    return {
      id: d.id, raw: d, capteurs: caps,
      client: d.client_nom || d.client_email || 'Client',
      addr: d.adresse || (d.adresseIP ? `IP ${d.adresseIP}` : '—'),
      device: d.nom || d.numeroSerie || ('ESP32-' + String(d.id).replace(/-/g, '').slice(0, 7).toUpperCase()),
      fw: d.firmwareVersion || '—',
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
    const matchSearch = !search || d.client.toLowerCase().includes(search) || d.device.toLowerCase().includes(search) || (d.addr && d.addr !== '—' && d.addr.toLowerCase().includes(search));
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
  // Tant que les données ne sont pas chargées, on affiche « — » (pas de faux
  // état rassurant type « Tout est en ligne » avant d'avoir la moindre donnée).
  const loaded = state.devicesLoaded;
  const ivLoaded = state.interventionsLoaded;
  set('stat-total', loaded ? String(nbTotal) : '—');
  set('stat-total-sub', loaded ? `dont ${filtered.length} affichée${filtered.length > 1 ? 's' : ''} ici` : '—');
  set('stat-offline', loaded ? String(nbOffline) : '—');
  set('stat-offline-sub', !loaded ? '—' : (nbOffline > 0 ? '⚠ Intervention requise' : '✓ Tout est en ligne'));
  set('stat-attente', ivLoaded ? String(nbAttente) : '—');
  set('stat-attente-sub', !ivLoaded ? '—' : `${nbUrgentes} urgente${nbUrgentes > 1 ? 's' : ''}`);
  set('stat-calib', loaded ? String(nbCalib) : '—');
  // Sous-titre calibration piloté par les vraies données (fini le « Écart > 5 % »
  // codé en dur affiché en permanence). Couleur d'alerte seulement s'il y a lieu.
  const calibSub = document.getElementById('stat-calib-sub');
  if (calibSub) {
    calibSub.textContent = !loaded ? '—' : (nbCalib > 0 ? `Écart > ${Math.round(CALIB_WARN * 100)} % détecté` : '✓ Tous calibrés');
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
        ${d.raw ? `<button class="action-btn" type="button" data-action="abonnement" data-id="${esc(d.id)}">Abonnement</button>` : ''}
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
    ['Adresse', d.addr || '—'],
    ['Firmware', d.fw || '—'],
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

/* Calibration : PATCH /api/sensors/capteurs/<id>/ {coeffCalibration} */
function calibrate(d) {
  if (!d.raw || !d.capteurs.length) {
    showInfo('Calibration indisponible', 'Le protocole de calibration est disponible uniquement pour les dispositifs enregistrés via l\'API.');
    return;
  }
  const cap = d.capteurs.find(c => !c.coeffCalibration || parseFloat(c.coeffCalibration) === 1) || d.capteurs[0];
  showPrompt(
    `Calibration, ${cap.nom}`,
    'Protocole : charge de référence → lecture capteur → coefficient Kcal.\nSaisissez le nouveau coefficient de calibration.',
    cap.coeffCalibration || '1.0000',
    { placeholder: 'Ex : 0.9820', required: true }
  ).then(val => {
    if (val === null) return;
    const num = parseFloat(String(val).replace(',', '.'));
    if (isNaN(num) || num <= 0) { showToast('Coefficient invalide.', 'error'); return; }
    fetchWithAuth(`/api/sensors/capteurs/${cap.id}/`, { method: 'PATCH', body: JSON.stringify({ coeffCalibration: num.toFixed(4) }) })
      .then(r => {
        if (r && r.id) {
          showToast(`Capteur "${cap.nom}" calibré (Kcal = ${num.toFixed(4)}).`);
          fetchWithAuth('/api/sensors/interventions/', {
            method: 'POST',
            body: JSON.stringify({
              client: d.raw.client, dispositif: d.id, capteur: cap.id,
              typeIntervention: 'CALIBRATION',
              description: `Calibration du capteur ${cap.nom}, Kcal ${num.toFixed(4)}`,
              dateIntervention: new Date().toISOString(), statut: 'TERMINEE'
            })
          }).catch(() => {});
          loadAll();
        } else showToast('Échec de la calibration.', 'error');
      })
      .catch(() => showToast('Erreur réseau : calibration impossible.', 'error'));
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
  const grid = document.getElementById('inter-grid');
  if (!grid) return;

  const allList = (Array.isArray(state.interventions) ? state.interventions : []).map(iv => {
    const dev = Array.isArray(state.devices) ? state.devices.find(d => d.id === iv.dispositif) : null;
    const deviceLabel = dev
      ? (dev.nom || dev.numeroSerie || ('ESP32-' + String(dev.id).replace(/-/g, '').slice(0, 7).toUpperCase()))
      : (iv.dispositif ? 'ESP32-' + String(iv.dispositif).replace(/-/g, '').slice(0, 7).toUpperCase() : '—');
    return {
      id: iv.id, raw: iv,
      client: iv.client_nom || '—',
      type: TYPE_LBL[iv.typeIntervention] || iv.typeIntervention,
      status: STATUT_UI[iv.statut] || 'pending',
      statut: iv.statut || 'EN_ATTENTE',
      date: formatDate(iv.dateIntervention),
      note: iv.description || '—',
      device: deviceLabel,
    };
  });
  interList = allList;

  // Mettre à jour les badges sidebar + statistiques
  const nAttente = allList.filter(x => x.statut === 'EN_ATTENTE').length;
  const nCours   = allList.filter(x => x.statut === 'EN_COURS').length;
  const badge = document.getElementById('nav-inter-badge');
  if (badge) { badge.textContent = String(nAttente); badge.style.display = nAttente > 0 ? '' : 'none'; }
  const statsEl = document.getElementById('inter-stats');
  if (statsEl) {
    statsEl.innerHTML = [
      { lbl: 'En attente', val: nAttente, cl: 'stat-val-warn' },
      { lbl: 'En cours', val: nCours, cl: '' },
      { lbl: 'Terminées', val: allList.filter(x => x.statut === 'TERMINEE').length, cl: '' }
    ].map(s => `<div class="inter-stat"><span class="inter-stat-lbl">${s.lbl}</span><span class="inter-stat-val ${s.cl}">${s.val}</span></div>`).join('');
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
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="es-title">${msg}</div></div>`;
    return;
  }

  grid.innerHTML = list.map(iv => {
    const s = S_MAP[iv.status] || S_MAP.pending;
    return `<div class="inter-card">
      <div class="inter-head">
        <span class="inter-title">${esc(iv.type)}</span>
        <span class="inter-status ${s.cl}">${s.l}</span>
      </div>
      <div class="inter-row"><span>Client</span><span>${esc(iv.client)}</span></div>
      <div class="inter-row"><span>Dispositif</span><span style="font-family:var(--fm);font-size:11px">${esc(iv.device)}</span></div>
      <div class="inter-row"><span>Date</span><span>${esc(iv.date)}</span></div>
      <div class="inter-row"><span>Note</span><span style="color:var(--tx-s)" title="${esc(iv.note)}">${esc(iv.note.length > 140 ? iv.note.slice(0, 140) + '…' : iv.note)}</span></div>
      <div class="inter-foot">
        <button class="action-btn" type="button" data-action="fiche" data-id="${esc(iv.id)}">Voir la fiche</button>
        ${iv.status !== 'done' ? `<button class="action-btn" type="button" data-action="update" data-id="${esc(iv.id)}">Mettre à jour</button>` : ''}
      </div>
    </div>`;
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
    ['Technicien', r.technicien_nom || '—'],
    ['Capteur', r.capteur_nom || '—'],
    ['Date', iv.date],
    ['Statut', (S_MAP[iv.status] || S_MAP.pending).l],
    ['Description', iv.note || '—'],
    ['Résultat', r['résultat'] || '—'],
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
        .then(() => showPrompt(
          'Rapport d\'intervention',
          'Rédigez le contenu du rapport (laisser vide pour ignorer) :',
          '',
          { multiline: true }
        ))
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
    fb.textContent = 'Enregistrement…'; fb.style.color = 'var(--tx-m)';
    fetchWithAuth(`/api/users/clients/${clientId}/abonnement/`, { method: 'PATCH', body: JSON.stringify(body) })
      .then(r => {
        if (r && r.id) {
          fb.textContent = '✓ Abonnement enregistré'; fb.style.color = 'var(--ok)';
          setTimeout(closeModal, 900);
        } else {
          const msg = r && (r.typeTarif || r.detail || r.amperage);
          fb.textContent = 'Échec : ' + (Array.isArray(msg) ? msg.join(' ') : (msg || 'données invalides'));
          fb.style.color = 'var(--err)';
        }
      })
      .catch(() => { fb.textContent = 'Erreur réseau.'; fb.style.color = 'var(--err)'; });
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
    const key = m.serverKey || '—';
    return `
      <div class="modal-info-banner">Copiez cette clé et programmez-la sur l'ESP32. <strong>Elle ne sera plus affichée après cette étape.</strong></div>
      <div class="api-key-box">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--ac-text);flex-shrink:0" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span style="flex:1;word-break:break-all">${esc(key)}</span>
        <button class="copy-btn" type="button" id="m-copy">${m.copied ? '✓ Copié' : 'Copier'}</button>
      </div>
      <div class="qr-placeholder">
        <svg viewBox="0 0 30 30" width="90" height="90" fill="var(--tx-p)">
          <rect x="1" y="1" width="7" height="7" rx="1"/><rect x="2" y="2" width="5" height="5" rx=".5" fill="var(--bg-s)"/><rect x="3" y="3" width="3" height="3"/>
          <rect x="22" y="1" width="7" height="7" rx="1"/><rect x="23" y="2" width="5" height="5" rx=".5" fill="var(--bg-s)"/><rect x="24" y="3" width="3" height="3"/>
          <rect x="1" y="22" width="7" height="7" rx="1"/><rect x="2" y="23" width="5" height="5" rx=".5" fill="var(--bg-s)"/><rect x="3" y="24" width="3" height="3"/>
          <rect x="10" y="1" width="2" height="2"/><rect x="13" y="1" width="2" height="2"/><rect x="10" y="4" width="3" height="2"/><rect x="14" y="4" width="2" height="2"/>
          <rect x="10" y="10" width="10" height="2"/><rect x="10" y="13" width="2" height="2"/><rect x="14" y="13" width="3" height="3"/><rect x="18" y="13" width="2" height="2"/>
          <rect x="1" y="10" width="2" height="4"/><rect x="4" y="10" width="4" height="2"/><rect x="4" y="13" width="2" height="2"/>
          <rect x="10" y="18" width="2" height="6"/><rect x="13" y="18" width="3" height="2"/><rect x="18" y="18" width="5" height="2"/><rect x="22" y="21" width="3" height="5"/><rect x="18" y="22" width="3" height="4"/>
        </svg>
      </div>
      <p style="text-align:center;font-size:12px;color:var(--tx-m)">QR Code de configuration, scanner avec l'app AOCEDA Tech</p>
      <div class="modal-fg" style="margin-top:16px">
        <p style="font-size:12.5px;color:var(--tx-s);line-height:1.6;margin:0">
          <strong>Configuration ESP32 :</strong> Flashez le firmware, puis entrez la clé API ci-dessus + le SSID <strong>${esc(m.wifiSsid || '—')}</strong> dans le fichier <code>config.h</code> de l'ESP32.
        </p>
      </div>`;
  }

  /* ── Étape 5 : Résumé ── */
  const capteurNoms = m.capteursCreated.length
    ? m.capteursCreated.map(c => c.nom).join(', ')
    : m.capteurs.filter(c => c.nom.trim()).map(c => c.nom).join(', ') || '—';
  const rows = [
    ['Client', m.selectedClient ? m.selectedClient.name : '—'],
    ['Installation', m.deviceName || '—'],
    ['Adresse', m.addr || '—'],
    ['WiFi (SSID)', m.wifiSsid || '—'],
    ['Capteurs créés', capteurNoms],
    ['Clé API', m.serverKey ? m.serverKey.slice(0, 18) + '…' : '—'],
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
}

function modalFinish() {
  const m = modal;
  if (!m) return;
  const capteurNoms = m.capteursCreated.map(c => c.nom).join(', ');
  const desc = [
    `Installation du dispositif "${m.deviceName || m.serial || m.createdId}"`,
    `chez ${m.selectedClient ? m.selectedClient.name : '—'}.`,
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
        const nom = document.getElementById('tp-nom');
        const email = document.getElementById('tp-email');
        const mat = document.getElementById('tp-matricule');
        const spe = document.getElementById('tp-specialite');
        const tel = document.getElementById('tp-telephone');
        const notifEmail = document.getElementById('tp-notif-email');
        if (nom) nom.value = d.nom || '';
        if (email) email.value = d.email || '';
        if (mat) mat.value = d.matricule || '';
        if (spe) spe.value = d.specialite || '';
        if (tel) tel.value = d.telephone || '';
        if (notifEmail) notifEmail.checked = d.notifEmail !== false;
      }
    })
    .catch(err => console.error(err));
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
    const devLabel = dev ? (dev.nom || dev.numeroSerie || ('ESP32-' + String(dev.id).replace(/-/g, '').slice(0, 7).toUpperCase())) : '—';
    const clientLabel = dev ? (dev.client_nom || dev.client_email || '—') : '—';
    const coeff = c.coeffCalibration ? parseFloat(c.coeffCalibration) : 1;
    const delta = Math.abs(coeff - 1);
    let statusCl, statusLbl, statusKey;
    if (delta < CALIB_WARN) { statusCl = 'calib-status-ok'; statusLbl = 'OK'; statusKey = 'ok'; }
    else if (delta < CALIB_CRIT) { statusCl = 'calib-status-warn'; statusLbl = 'Attention'; statusKey = 'attention'; }
    else { statusCl = 'calib-status-err'; statusLbl = 'Critique'; statusKey = 'critique'; }
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
          <span class="calib-row-val">${lastCalib ? formatDate(lastCalib) : '—'}</span>
        </div>
        <div class="calib-row">
          <span class="calib-row-lbl">Dispositif</span>
          <span class="calib-row-val">${esc(devLabel)}</span>
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
        calib: true, status: dev.estConnecté ? 'online' : 'offline', addr: dev.adresseIP || '—', fw: dev.firmwareVersion || '—', last: '—'
      } : { id: null, raw: null, capteurs: [cap], client: '—', device: '—', calib: true, status: 'offline', addr: '—', fw: '—', last: '—' };
      calibrate(devObj);
    });
  });
}

/* ════════════════════════ PARAMÈTRES TECHNICIEN ════════════════════════ */
function initParamsSection() {
  /* Profil, enregistrement (nom, spécialité, téléphone) */
  const btnSave = document.getElementById('tp-profil-save');
  if (btnSave) btnSave.addEventListener('click', () => {
    const nom = (document.getElementById('tp-nom') || {}).value || '';
    const spe = (document.getElementById('tp-specialite') || {}).value || '';
    const tel = (document.getElementById('tp-telephone') || {}).value || '';
    const fb  = document.getElementById('tp-profil-feedback');
    if (!nom.trim()) {
      if (fb) { fb.textContent = 'Le nom est obligatoire.'; fb.className = 'tp-feedback err'; }
      return;
    }
    if (fb) { fb.textContent = 'Enregistrement…'; fb.className = 'tp-feedback'; }
    fetchWithAuth('/api/users/me/', {
      method: 'PUT',
      body: JSON.stringify({ nom: nom.trim(), specialite: spe.trim(), telephone: tel.trim() || null })
    }).then(r => {
      if (r && r.id) {
        if (state.user) { state.user.nom = r.nom; state.user.specialite = r.specialite; state.user.telephone = r.telephone; }
        renderUser();
        const nameEl = document.getElementById('user-name');
        if (nameEl && r.nom) nameEl.textContent = r.nom;
        if (fb) { fb.textContent = '✓ Profil enregistré'; fb.className = 'tp-feedback ok'; }
        setTimeout(() => { if (fb) { fb.textContent = ''; fb.className = 'tp-feedback'; } }, 3000);
      } else {
        if (fb) { fb.textContent = 'Échec de l\'enregistrement.'; fb.className = 'tp-feedback err'; }
      }
    }).catch(() => {
      if (fb) { fb.textContent = 'Erreur réseau.'; fb.className = 'tp-feedback err'; }
    });
  });

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
      clients.push({
        id: d.client,
        name: d.client_nom || '—',
        email: d.client_email || '—',
        devices: devices.filter(x => String(x.client) === key)
      });
    }
  });

  // Compléter avec les clients chargés dans state.clients (sans dispositif)
  if (Array.isArray(state.clients)) {
    state.clients.forEach(c => {
      if (!seen.has(String(c.id))) {
        seen.add(String(c.id));
        clients.push({ id: c.id, name: c.nom || c.name || '—', email: c.email || '—', devices: [] });
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
        </div>
      </div>`;
  }).join('')}</div>`;

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

  // Navigation bottom-nav (mobile, data-section)
  document.querySelectorAll('.bottom-nav .bn-item[data-section]').forEach(btn => {
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
    else if (btn.dataset.action === 'abonnement') manageAbonnement(d);
    else if (btn.dataset.action === 'calibrate') calibrate(d);
    else if (btn.dataset.action === 'panne') declarePanneDevice(d);
  });

  // Déclarer une panne (section Interventions)
  const btnPanne = document.getElementById('btn-declare-panne');
  if (btnPanne) btnPanne.addEventListener('click', declarePanneGlobal);

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

  // Actions des cartes d'intervention (délégation)
  const grid = document.getElementById('inter-grid');
  if (grid) grid.addEventListener('click', e => {
    const btn = e.target.closest('.action-btn');
    if (!btn) return;
    const iv = interList.find(x => String(x.id) === btn.dataset.id);
    if (!iv) return;
    if (btn.dataset.action === 'fiche') showFiche(iv);
    else if (btn.dataset.action === 'update') updateIv(iv);
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
    const btn = e.target.closest('.client-act-install,.client-act-capteurs,.client-act-abo');
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
    }
  });

  // Initialisation de la section paramètres
  initParamsSection();

  // Premier rendu (valeurs de repli), puis chargement des données réelles
  setSection('installations');
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
