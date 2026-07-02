'use strict';
/* ════════════════════════════════════════════════════════════
   AOCEDA — Paramètres
   JavaScript vanilla (ES2020) — sans React/Babel
   N.B. : le shell commun (client-shell.js) gère la sidebar
   globale, la déconnexion, la cloche de notifications et le
   bloc utilisateur. Ce fichier gère le #theme-toggle du header
   (synchronisé avec la radio « Thème » des Préférences) et
   toute la logique des sections.
   ════════════════════════════════════════════════════════════ */

/* ── Garde d'authentification ── */
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* ── Helper fetch authentifié ── */
/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. */
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

/* ── Export CSV (Authorization requis → fetch → blob → lien temporaire) ── */
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

/* ── Repli maquette si l'API échoue ── */
const FALLBACK_USER = {
  nom: '', email: '',
  typeLogement: 'Appartement', amperage: 10,
  typeTarif: 'general', typeCompteur: 'postpaye',
  adresse: '', numeroCIE: ''
};

/* ── Grille tarifaire CIE officielle (mensuelle, TTC — récap informatif) ──
   clé : `${typeTarif}-${amperage}` → seuil T1 (kWh/mois), prix T1, prix T2 */
const GRILLE_RECAP = {
  'social-5': { seuil: 40, t1: '31,72', t2: '65,11' },
  'general-5': { seuil: 99, t1: '86,92', t2: '75,34' },
  'general-10': { seuil: 198, t1: '86,92', t2: '75,34' },
  'general-15': { seuil: 297, t1: '95,62', t2: '82,86' },
};
const COMPTEUR_LABELS = { postpaye: 'Intelligent postpayé', prepaye: 'Prépayé' };
const TARIF_LABELS = { general: 'Général', social: 'Social' };

function tarifRecapText(amperage, typeTarif) {
  const g = GRILLE_RECAP[`${typeTarif}-${amperage}`] || GRILLE_RECAP['general-10'];
  return `Tranche 1 : ${g.seuil} kWh/mois à ${g.t1} F — TVA incluse · Tranche 2 : ${g.t2} F/kWh`;
}
/* Variante HTML : chiffres (kWh / FCFA) en police mono tabulaire via <b> */
function tarifRecapHTML(amperage, typeTarif) {
  const g = GRILLE_RECAP[`${typeTarif}-${amperage}`] || GRILLE_RECAP['general-10'];
  return `Tranche 1 : <b>${esc(g.seuil)} kWh/mois</b> à <b>${esc(g.t1)} F</b> — TVA incluse · Tranche 2 : <b>${esc(g.t2)} F/kWh</b>`;
}
/* ── Icônes & fragments HTML réutilisés ── */
const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
const SVG_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
const SVG_CHECK_SM = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
const SVG_CIRCLE_SM = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>';
const SAVE_OK_HTML = `<span class="save-ok">${SVG_CHECK}Enregistré</span>`;

function saveErrorHTML(msg) {
  return `<span style="font-size:12px;color:var(--err);font-weight:600">${esc(msg)}</span>`;
}

/* ── État global ── */
const state = {
  theme: localStorage.getItem('aoceda-theme') || 'light',
  section: 'profil',
  editing: { profil: false, foyer: false },
  // Profil API
  user: FALLBACK_USER,
  prenom: '',
  nomFam: '',
  telephone: '',
  // Foyer API
  typeLogement: FALLBACK_USER.typeLogement,
  adresse: FALLBACK_USER.adresse,
  numeroCIE: FALLBACK_USER.numeroCIE,
  amperage: FALLBACK_USER.amperage,
  typeTarif: FALLBACK_USER.typeTarif,
  typeCompteur: FALLBACK_USER.typeCompteur,
  // Capteurs & règles API
  sensors: [],
  sensorsLoaded: false,
  regles: [],
  // Sécurité (maquette locale)
  pwdModal: false,
  oldPwd: '',
  newPwd: '',
  confirmPwd: '',
  savingPwd: false,
  pwdSaved: false,
  // Préférences (maquette locale)
  emailNotif: true,
  // On lit la clé de CHOIX ('auto'/'light'/'dark'), pas le thème résolu — sinon
  // « Auto » retombait sur Clair/Sombre au rechargement.
  themeChoice: localStorage.getItem('aoceda-theme-choice') || localStorage.getItem('aoceda-theme') || 'light',
  // Données
  exporting: false
};

/* Timers des feedbacks « Enregistré » / erreurs */
const feedbackTimers = {};

/* ════════════════════════ THÈME ════════════════════════ */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  localStorage.setItem('aoceda-theme', state.theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = state.theme === 'light' ? ICON_MOON : ICON_SUN;
}

function toggleTheme() {
  state.theme = state.theme === 'light' ? 'dark' : 'light';
  // Garde la radio « Thème » des Préférences synchronisée avec le header
  state.themeChoice = state.theme;
  applyTheme();
  renderPrefs();
}

/* ════════════════════════ NAVIGATION LATÉRALE ════════════════════════ */
const SECTION_IDS = ['profil', 'foyer', 'capteurs', 'securite', 'prefs', 'donnees'];

function showSection(id) {
  state.section = id;
  document.querySelectorAll('.snav-item[data-section]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.section === id);
  });
  SECTION_IDS.forEach(s => {
    const el = document.getElementById(`section-${s}`);
    if (el) el.style.display = s === id ? '' : 'none';
  });
}

/* ════════════════════════ FEEDBACK ENREGISTREMENT ════════════════════════ */
function flagSaved(sec) {
  const el = document.getElementById(`${sec}-feedback`);
  if (!el) return;
  el.innerHTML = SAVE_OK_HTML;
  clearTimeout(feedbackTimers[sec]);
  feedbackTimers[sec] = setTimeout(() => { el.innerHTML = ''; }, 3000);
}

function flagError(sec, msg) {
  const el = document.getElementById(`${sec}-feedback`);
  if (!el) return;
  el.innerHTML = saveErrorHTML(msg);
  clearTimeout(feedbackTimers[sec]);
  feedbackTimers[sec] = setTimeout(() => { el.innerHTML = ''; }, 4000);
}

/* ════════════════════════ PROFIL ════════════════════════ */
/* Découpe « Nom Prénom » → deux champs du formulaire */
function applyUser(u) {
  state.user = u;
  const parts = (u.nom || '').trim().split(/\s+/);
  state.nomFam = parts[0] || '';
  state.prenom = parts.slice(1).join(' ');
  state.typeLogement = u.typeLogement || 'Appartement';
  state.adresse = u.adresse || '';
  state.numeroCIE = u.numeroCIE || '';
  state.amperage = [5, 10, 15].indexOf(Number(u.amperage)) !== -1 ? Number(u.amperage) : 10;
  state.typeTarif = u.typeTarif === 'social' ? 'social' : 'general';
  state.typeCompteur = u.typeCompteur === 'prepaye' ? 'prepaye' : 'postpaye';
  state.telephone = (u.telephone == null ? '' : u.telephone);
  if (u.notifEmail !== undefined) state.emailNotif = u.notifEmail !== false;
  syncProfilInputs();
  syncFoyerInputs();
  renderProfil();
  renderFoyer();
  renderPrefs();
}

function syncProfilInputs() {
  document.getElementById('profil-prenom').value = state.prenom;
  document.getElementById('profil-nomfam').value = state.nomFam;
  document.getElementById('profil-email').value = state.user.email || '';
  document.getElementById('profil-telephone').value = state.telephone;
}

function renderProfil() {
  const displayName = state.user.nom || '—';
  const initials = displayName.split(/\s+/).map(n => n[0]).join('').substring(0, 2).toUpperCase();
  document.getElementById('profil-avatar').textContent = initials;
  document.getElementById('profil-name').textContent = displayName;
  document.getElementById('profil-role').textContent = state.adresse ? `Client · ${state.adresse}` : 'Client';
  document.getElementById('profil-cie').textContent = state.numeroCIE || '—';
  document.getElementById('profil-edit-btn').textContent = state.editing.profil ? 'Annuler' : 'Modifier';

  document.getElementById('profil-form').style.display = state.editing.profil ? '' : 'none';
  const view = document.getElementById('profil-view');
  view.style.display = state.editing.profil ? 'none' : '';
  view.innerHTML = [
    ['Prénom', state.prenom || '—'],
    ['Nom', state.nomFam || '—'],
    ['Email', state.user.email || '—'],
    ['Téléphone', state.telephone || '—']
  ].map(([l, v], i) => `<div class="fg${i >= 2 ? ' full' : ''}">
      <label class="fl">${esc(l)}</label>
      <div class="kv-box">${esc(v)}</div>
    </div>`).join('');
}

/* Enregistrement profil → PUT /api/users/me/ */
function saveProfil() {
  const nomComplet = `${state.nomFam} ${state.prenom}`.trim();
  const fb = document.getElementById('profil-feedback');
  if (fb) fb.innerHTML = '';
  fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify({ nom: nomComplet, telephone: state.telephone }) })
    .then(data => {
      if (data && data.email) {
        applyUser(data);
        state.editing.profil = false;
        renderProfil();
        flagSaved('profil');
      } else {
        flagError('profil', 'Échec de l\'enregistrement');
      }
    })
    .catch(() => flagError('profil', 'Échec de l\'enregistrement'));
}

/* ════════════════════════ FOYER ════════════════════════ */
function syncFoyerInputs() {
  document.querySelectorAll('#foyer-logement input[name="log"]').forEach(r => {
    r.checked = r.value === state.typeLogement;
  });
  document.getElementById('foyer-adresse').value = state.adresse;
  syncTarifUI();
}

/* L'abonnement (ampérage / tarif / compteur) est en LECTURE SEULE côté client :
   il est référencé par le technicien. On affiche seulement les valeurs + le récap. */
function syncTarifUI() {
  const setRo = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  setRo('foyer-amperage-ro', `${state.amperage} A`);
  setRo('foyer-compteur-ro', COMPTEUR_LABELS[state.typeCompteur] || '—');
  setRo('foyer-tarif-ro', TARIF_LABELS[state.typeTarif] || '—');
  setRo('foyer-numcie-ro', state.numeroCIE || '—');
  const recap = document.getElementById('foyer-tarif-recap');
  if (recap) recap.innerHTML = tarifRecapHTML(state.amperage, state.typeTarif);
}

function renderFoyer() {
  document.getElementById('foyer-edit-btn').textContent = state.editing.foyer ? 'Annuler' : 'Modifier';
  document.getElementById('foyer-form').style.display = state.editing.foyer ? '' : 'none';
  const view = document.getElementById('foyer-view');
  view.style.display = state.editing.foyer ? 'none' : '';
  // [libellé, valeur, html?] — html=true : la valeur contient déjà du balisage sûr (chiffres mono)
  view.innerHTML = [
    ['Type de logement', esc(state.typeLogement || '—')],
    ['Adresse', esc(state.adresse || '—')],
    ['Ampérage souscrit', `<b class="kv-num">${esc(state.amperage)} A</b>`, true],
    ['Type de compteur', esc(COMPTEUR_LABELS[state.typeCompteur] || '—')],
    ['Type de tarif', `${esc(TARIF_LABELS[state.typeTarif] || '—')} — ${tarifRecapHTML(state.amperage, state.typeTarif)}`, true],
    ['Numéro abonné CIE', `<b class="kv-num">${esc(state.numeroCIE || '—')}</b>`, true]
  ].map(([l, v]) => `<div class="fg full">
      <label class="fl">${esc(l)}</label>
      <div class="kv-box">${v}</div>
    </div>`).join('');
}

/* Enregistrement foyer → PUT /api/users/me/ {amperage, typeTarif, typeCompteur, …} */
function saveFoyer() {
  const fb = document.getElementById('foyer-feedback');
  if (fb) fb.innerHTML = '';
  // L'abonnement (ampérage/tarif/compteur/n° CIE) n'est PAS envoyé : il est en
  // lecture seule côté client (référencé par le technicien, read_only serializer).
  const body = {
    typeLogement: state.typeLogement,
    adresse: state.adresse,
  };
  fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify(body) })
    .then(data => {
      if (data && data.email) {
        applyUser(data);
        state.editing.foyer = false;
        renderFoyer();
        flagSaved('foyer');
      } else if (data && data.typeTarif) {
        // Erreur de validation du serializer (ex. social hors 5A)
        const msg = Array.isArray(data.typeTarif) ? data.typeTarif.join(' ') : String(data.typeTarif);
        flagError('foyer', msg);
      } else if (data && data.amperage) {
        const msg = Array.isArray(data.amperage) ? data.amperage.join(' ') : String(data.amperage);
        flagError('foyer', msg);
      } else {
        flagError('foyer', 'Échec de l\'enregistrement');
      }
    })
    .catch(() => flagError('foyer', 'Échec de l\'enregistrement'));
}

/* ════════════════════════ CAPTEURS & ALERTES ════════════════════════ */
function onRegleSaved(r) {
  const idx = state.regles.findIndex(x => x.id === r.id);
  if (idx >= 0) state.regles[idx] = r;
  else state.regles.push(r);
}

/* Carte règle de détection par capteur */
function buildRegleCard(sensor, regle) {
  // État local de la carte (équivalent du useState du composant React)
  let seuil = regle ? Math.round(Number(regle.puissanceMax_W)) || 2000 : 2000;
  let nuit = regle ? !!regle.surveilleNuit : false;
  let debut = regle && regle['heureDébutNuit'] ? String(regle['heureDébutNuit']).slice(0, 5) : '23:00';
  let fin = regle && regle['heureFinNuit'] ? String(regle['heureFinNuit']).slice(0, 5) : '06:00';
  let saving = false;
  let savedTimer = null;

  const card = document.createElement('div');
  card.className = 'card';
  card.style.marginBottom = '14px';
  const seuilId = `rc-seuil-${esc(sensor.id)}`;
  const debutId = `rc-debut-${esc(sensor.id)}`;
  const finId = `rc-fin-${esc(sensor.id)}`;
  card.innerHTML = `
    <div class="rc-head">
      <div>
        <div class="rc-name">${esc(sensor.nom)}</div>
        <div class="rc-meta">${sensor.actif ? 'Capteur en ligne' : 'Capteur hors ligne'}${regle && regle.id ? ' · Règle configurée' : ' · Aucune règle — elle sera créée à l\'enregistrement'}</div>
      </div>
      <span class="rc-status ${sensor.actif ? 'on' : 'off'}">${sensor.actif ? 'Actif' : 'Inactif'}</span>
    </div>
    <div class="fg" style="margin-bottom:14px">
      <label class="fl" for="${seuilId}">Seuil de puissance maximum (W)</label>
      <input class="fi rc-seuil" id="${seuilId}" type="number" min="100" max="10000" step="100" inputmode="numeric">
      <div class="rc-hint">Une alerte est émise si la puissance dépasse ce seuil. Référence : climatiseur ≈ <b>1 500 W</b> · chauffe-eau ≈ <b>2 000 W</b></div>
    </div>
    <div class="rc-nuit-row tog-row" style="margin-bottom:0">
      <div>
        <div class="tog-lbl">Surveillance nocturne</div>
        <div class="tog-sub">Détecter les consommations anormales pendant la nuit</div>
      </div>
      <button type="button" class="tog-track rc-toggle" role="switch" aria-checked="false" aria-label="Surveillance nocturne"><span class="tog-thumb"></span></button>
    </div>
    <div class="rc-hours" style="display:none">
      <div class="fg"><label class="fl" for="${debutId}">Heure de début</label><input class="fi rc-debut" id="${debutId}" type="time"></div>
      <div class="fg"><label class="fl" for="${finId}">Heure de fin</label><input class="fi rc-fin" id="${finId}" type="time"></div>
    </div>
    <div class="btn-row" style="margin-top:12px">
      <button class="btn-save rc-save">Enregistrer la règle</button>
      <span class="rc-feedback" aria-live="polite"></span>
    </div>`;

  const seuilInput = card.querySelector('.rc-seuil');
  const toggleEl = card.querySelector('.rc-toggle');
  const nuitRow = card.querySelector('.rc-nuit-row');
  const hoursEl = card.querySelector('.rc-hours');
  const debutInput = card.querySelector('.rc-debut');
  const finInput = card.querySelector('.rc-fin');
  const saveBtn = card.querySelector('.rc-save');
  const feedback = card.querySelector('.rc-feedback');

  seuilInput.value = seuil;
  debutInput.value = debut;
  finInput.value = fin;

  function renderNuit() {
    toggleEl.classList.toggle('on', nuit);
    toggleEl.setAttribute('aria-checked', String(nuit));
    nuitRow.style.marginBottom = nuit ? '12px' : '0';
    hoursEl.style.display = nuit ? 'grid' : 'none';
  }
  renderNuit();

  seuilInput.addEventListener('input', () => { seuil = +seuilInput.value; });
  debutInput.addEventListener('input', () => { debut = debutInput.value; });
  finInput.addEventListener('input', () => { fin = finInput.value; });
  toggleEl.addEventListener('click', () => { nuit = !nuit; renderNuit(); });

  saveBtn.addEventListener('click', () => {
    if (saving) return;
    saving = true;
    clearTimeout(savedTimer);
    feedback.innerHTML = '';
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner"></span>Enregistrement…';

    const body = { capteur: sensor.id, puissanceMax_W: seuil, surveilleNuit: nuit };
    body['heureDébutNuit'] = debut;
    body['heureFinNuit'] = fin;

    const req = regle && regle.id
      ? fetchWithAuth(`/api/regles/${regle.id}/`, { method: 'PUT', body: JSON.stringify(body) })
      : fetchWithAuth('/api/regles/', { method: 'POST', body: JSON.stringify(body) });

    const reset = () => {
      saving = false;
      saveBtn.disabled = false;
      saveBtn.textContent = 'Enregistrer la règle';
    };

    req.then(data => {
      reset();
      if (data && data.id) {
        const isNew = !(regle && regle.id);
        onRegleSaved(data);
        if (isNew) {
          // Équivalent du changement de clé React : la carte est recréée avec la règle
          card.replaceWith(buildRegleCard(sensor, data));
        } else {
          regle = data;
          feedback.innerHTML = SAVE_OK_HTML;
          savedTimer = setTimeout(() => { feedback.innerHTML = ''; }, 3000);
        }
      } else {
        feedback.innerHTML = saveErrorHTML('Échec de l\'enregistrement de la règle');
      }
    }).catch(() => {
      reset();
      feedback.innerHTML = saveErrorHTML('Échec de l\'enregistrement de la règle');
    });
  });

  return card;
}

function renderCapteurs() {
  const wrap = document.getElementById('capteurs-list');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (state.sensors.length === 0) {
    wrap.innerHTML = state.sensorsLoaded
      ? '<div class="card"><div class="empty-card">Aucun capteur installé pour le moment. Un technicien doit installer vos capteurs pour configurer des règles d’alerte.</div></div>'
      : '<div class="card"><div class="empty-card">Chargement des capteurs…</div></div>';
    return;
  }
  state.sensors.forEach(s => {
    const regle = state.regles.find(r => r.capteur === s.id) || null;
    wrap.appendChild(buildRegleCard(s, regle));
  });
}

/* ════════════════════════ SÉCURITÉ (maquette locale) ════════════════════════ */
/* Couleur de robustesse = token sémantique (jamais de hex en dur) :
   1 err · 2-3 warn · 4-5 ok */
const PWD_COLS = ['', 'var(--err)', 'var(--warn)', 'var(--warn)', 'var(--ok)', 'var(--ok)'];
const PWD_LBLS = ['', 'Très faible', 'Faible', 'Moyen', 'Fort', 'Très fort'];

function pwdScore(pwd) {
  let x = 0;
  if (pwd.length >= 8) x++;
  if (pwd.length >= 12) x++;
  if (/[A-Z]/.test(pwd)) x++;
  if (/[0-9]/.test(pwd)) x++;
  if (/[^A-Za-z0-9]/.test(pwd)) x++;
  return x;
}

function renderPwdUI() {
  document.getElementById('pwd-toggle-btn').textContent = state.pwdModal ? 'Annuler' : 'Changer';
  document.getElementById('pwd-panel').style.display = state.pwdModal ? '' : 'none';

  // Jauge de robustesse
  const strengthEl = document.getElementById('pwd-strength');
  if (!state.newPwd) {
    strengthEl.innerHTML = '';
  } else {
    const s = pwdScore(state.newPwd);
    strengthEl.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <div class="pwd-bars">${[1, 2, 3, 4, 5].map(i => `<div class="pbar" style="background:${i <= s ? PWD_COLS[s] : 'var(--bd-s)'}"></div>`).join('')}</div>
      <span class="pwd-strength-lbl" style="color:${PWD_COLS[s]}">${PWD_LBLS[s]}</span>
    </div>`;
  }

  // Liste des règles
  const rules = [
    { txt: 'Minimum 8 caractères', ok: state.newPwd.length >= 8 },
    { txt: 'Au moins 1 majuscule', ok: /[A-Z]/.test(state.newPwd) },
    { txt: 'Au moins 1 chiffre', ok: /[0-9]/.test(state.newPwd) }
  ];
  document.getElementById('pwd-rules').innerHTML = rules.map(r =>
    `<div class="rule${r.ok ? ' v' : ''}">${r.ok ? SVG_CHECK_SM : SVG_CIRCLE_SM}${esc(r.txt)}</div>`
  ).join('');

  // Non-correspondance de confirmation
  const mismatch = !!(state.confirmPwd && state.confirmPwd !== state.newPwd);
  const confirmInput = document.getElementById('pwd-confirm');
  confirmInput.classList.toggle('ferr', mismatch);
  confirmInput.style.borderColor = mismatch ? 'var(--err)' : '';
  document.getElementById('pwd-mismatch').style.display = mismatch ? '' : 'none';

  // Bouton d'enregistrement
  const saveBtn = document.getElementById('pwd-save-btn');
  saveBtn.disabled = state.savingPwd || !state.oldPwd || !state.newPwd || state.newPwd !== state.confirmPwd || state.newPwd.length < 8;
  saveBtn.innerHTML = state.savingPwd ? '<span class="spinner"></span>Mise à jour…' : 'Enregistrer le mot de passe';

  // Feedback succès
  document.getElementById('pwd-feedback').innerHTML = state.pwdSaved
    ? `<span class="save-ok">${SVG_CHECK}Mot de passe mis à jour</span>`
    : '';
}

function showPwdError(msg) {
  const fb = document.getElementById('pwd-feedback');
  if (fb) fb.innerHTML = `<span style="font-size:12px;color:var(--err);font-weight:600">${esc(msg)}</span>`;
}

function submitPwd() {
  if (!state.oldPwd || !state.newPwd || state.newPwd !== state.confirmPwd) return;
  state.savingPwd = true;
  renderPwdUI();
  // Changement de mot de passe RÉEL (vérifie l'ancien mot de passe côté serveur).
  fetchWithAuth('/api/users/me/password/', {
    method: 'PUT',
    body: JSON.stringify({ old_password: state.oldPwd, new_password: state.newPwd })
  })
    .then(data => {
      state.savingPwd = false;
      const isError = data && (data.old_password || data.new_password
        || (data.detail && /incorrect|invalide|échec/i.test(data.detail)));
      if (!isError && data && data.detail) {
        state.pwdSaved = true;
        state.oldPwd = state.newPwd = state.confirmPwd = '';
        document.getElementById('pwd-old').value = '';
        document.getElementById('pwd-new').value = '';
        document.getElementById('pwd-confirm').value = '';
        renderPwdUI();
        setTimeout(() => { state.pwdSaved = false; renderPwdUI(); }, 3000);
      } else {
        renderPwdUI();
        const msg = (data.old_password && data.old_password[0])
          || (data.new_password && data.new_password[0])
          || data.detail || 'Échec de la mise à jour du mot de passe.';
        showPwdError(msg);
      }
    })
    .catch(() => { state.savingPwd = false; renderPwdUI(); showPwdError('Échec de la mise à jour du mot de passe.'); });
}

/* ════════════════════════ PRÉFÉRENCES (maquette locale) ════════════════════════ */
function renderPrefs() {
  document.querySelectorAll('#theme-options input[name="theme"]').forEach(r => {
    r.checked = r.value === state.themeChoice;
  });
  const tog = document.getElementById('email-toggle');
  tog.classList.toggle('on', state.emailNotif);
  tog.setAttribute('aria-checked', String(state.emailNotif));
}

/* ════════════════════════ DONNÉES & CONFIDENTIALITÉ ════════════════════════ */
function exportData() {
  if (state.exporting) return;
  state.exporting = true;
  const btn = document.getElementById('export-btn');
  const label = document.getElementById('export-label');
  btn.disabled = true;
  label.textContent = 'Export en cours…';
  downloadCSV('/api/analytics/export/?period=month', 'aoceda_donnees.csv')
    .catch(err => console.error(err))
    .finally(() => {
      state.exporting = false;
      btn.disabled = false;
      label.textContent = 'Exporter mes mesures (CSV)';
    });
}

function setDelModal(open) {
  document.getElementById('del-overlay').style.display = open ? '' : 'none';
  // Le mot de passe est requis pour la suppression réelle du compte (DELETE /api/users/me/).
  // On vide le champ à la fermeture de la modale.
  const pwd = document.getElementById('del-pwd');
  if (!open && pwd) pwd.value = '';
}

/* ════════════════════════ INITIALISATION ════════════════════════ */
function init() {
  // « Auto » : le thème effectif suit la préférence système au démarrage.
  if (state.themeChoice === 'auto') {
    state.theme = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  applyTheme();

  // Thème clair/sombre (#theme-toggle du header canonique)
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // Navigation latérale entre sections
  document.querySelectorAll('.snav-item[data-section]').forEach(btn => {
    btn.addEventListener('click', () => showSection(btn.dataset.section));
  });

  // Lien profond : /parametres/#capteurs ouvre directement la bonne section
  const hashSection = (window.location.hash || '').replace('#', '');
  if (SECTION_IDS.includes(hashSection)) showSection(hashSection);

  // ── Profil ──
  document.getElementById('profil-edit-btn').addEventListener('click', () => {
    state.editing.profil = !state.editing.profil;
    renderProfil();
  });
  document.getElementById('profil-cancel-btn').addEventListener('click', () => {
    state.editing.profil = false;
    renderProfil();
  });
  document.getElementById('profil-save-btn').addEventListener('click', saveProfil);
  document.getElementById('profil-prenom').addEventListener('input', e => { state.prenom = e.target.value; });
  document.getElementById('profil-nomfam').addEventListener('input', e => { state.nomFam = e.target.value; });
  document.getElementById('profil-telephone').addEventListener('input', e => { state.telephone = e.target.value; });

  // ── Foyer ──
  document.getElementById('foyer-edit-btn').addEventListener('click', () => {
    state.editing.foyer = !state.editing.foyer;
    renderFoyer();
  });
  document.getElementById('foyer-cancel-btn').addEventListener('click', () => {
    state.editing.foyer = false;
    renderFoyer();
  });
  document.getElementById('foyer-save-btn').addEventListener('click', saveFoyer);
  document.querySelectorAll('#foyer-logement input[name="log"]').forEach(r => {
    r.addEventListener('change', () => { if (r.checked) state.typeLogement = r.value; });
  });
  document.getElementById('foyer-adresse').addEventListener('input', e => { state.adresse = e.target.value; });

  // ── Sécurité ──
  document.getElementById('pwd-toggle-btn').addEventListener('click', () => {
    state.pwdModal = !state.pwdModal;
    renderPwdUI();
  });
  document.getElementById('pwd-old').addEventListener('input', e => { state.oldPwd = e.target.value; renderPwdUI(); });
  document.getElementById('pwd-new').addEventListener('input', e => { state.newPwd = e.target.value; renderPwdUI(); });
  document.getElementById('pwd-confirm').addEventListener('input', e => { state.confirmPwd = e.target.value; renderPwdUI(); });
  document.getElementById('pwd-save-btn').addEventListener('click', submitPwd);

  // ── Préférences ──
  document.querySelectorAll('#theme-options input[name="theme"]').forEach(r => {
    r.addEventListener('change', () => {
      if (!r.checked) return;
      state.themeChoice = r.value;
      localStorage.setItem('aoceda-theme-choice', r.value);
      // « Auto » : suit la préférence système (clair/sombre) du navigateur.
      if (r.value === 'auto') {
        state.theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      } else {
        state.theme = r.value;
      }
      applyTheme();
    });
  });
  document.getElementById('email-toggle').addEventListener('click', () => {
    state.emailNotif = !state.emailNotif;
    renderPrefs();
    // Préférence RÉELLEMENT persistée : le moteur d'alertes respecte notifEmail.
    fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify({ notifEmail: state.emailNotif }) })
      .catch(() => { /* en cas d'échec réseau, l'état UI reste cohérent au prochain chargement */ });
  });

  // ── Données & Confidentialité ──
  document.getElementById('export-btn').addEventListener('click', exportData);
  document.getElementById('delete-btn').addEventListener('click', () => {
    const pwd = document.getElementById('del-pwd');
    if (pwd) pwd.value = '';
    const err = document.getElementById('del-error');
    if (err) { err.textContent = ''; err.hidden = true; }
    setDelModal(true);
    setTimeout(() => { if (pwd) pwd.focus(); }, 50);
  });
  document.getElementById('del-cancel-btn').addEventListener('click', () => setDelModal(false));
  document.getElementById('del-confirm-btn').addEventListener('click', () => {
    const pwd = document.getElementById('del-pwd');
    const errEl = document.getElementById('del-error');
    const password = pwd ? pwd.value : '';
    if (!password) {
      if (errEl) { errEl.textContent = 'Mot de passe requis.'; errEl.hidden = false; }
      if (pwd) pwd.focus();
      return;
    }
    const btn = document.getElementById('del-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Suppression…';
    fetchWithAuth('/api/users/me/', { method: 'DELETE', body: JSON.stringify({ password }) })
      .then(data => {
        if (data && data.detail && data.detail.toLowerCase().includes('supprim')) {
          // Succès : purge les tokens et redirige vers l'accueil
          localStorage.removeItem('aoceda_access_token');
          localStorage.removeItem('aoceda_refresh_token');
          window.location.href = '/';
        } else {
          const msg = (data && data.detail) || 'Suppression impossible. Vérifiez votre mot de passe.';
          if (errEl) { errEl.textContent = msg; errEl.hidden = false; }
          btn.disabled = false;
          btn.textContent = 'Supprimer mon compte';
        }
      })
      .catch(() => {
        if (errEl) { errEl.textContent = 'Erreur réseau. Réessayez.'; errEl.hidden = false; }
        btn.disabled = false;
        btn.textContent = 'Supprimer mon compte';
      });
  });
  document.getElementById('del-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) setDelModal(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('del-overlay').style.display !== 'none') {
      setDelModal(false);
    }
  });

  // Premier rendu (valeurs de repli), puis chargement des données
  applyUser(FALLBACK_USER);
  renderCapteurs();
  renderPwdUI();
  renderPrefs();

  // Chargement initial : profil + capteurs + règles
  fetchWithAuth('/api/users/me/')
    .then(data => { if (data && data.email) applyUser(data); })
    .catch(err => console.error(err));
  fetchWithAuth('/api/sensors/')
    .then(data => {
      // /api/sensors/ est paginé ({results:[…]}) → asList décapsule (comme le dashboard)
      state.sensors = window.AOCEDA.asList(data);
      state.sensorsLoaded = true;
      renderCapteurs();
    })
    .catch(() => {
      state.sensors = [];
      state.sensorsLoaded = true;
      renderCapteurs();
    });
  fetchWithAuth('/api/regles/')
    .then(data => {
      // /api/regles/ est paginé ({results:[…]}) → asList, sinon les règles existantes
      // ne se lient jamais à leur capteur et chaque enregistrement recrée un doublon.
      state.regles = window.AOCEDA.asList(data);
      renderCapteurs();
    })
    .catch(err => console.error(err));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
