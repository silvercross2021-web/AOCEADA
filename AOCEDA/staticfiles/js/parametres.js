'use strict';
/* ════════════════════════════════════════════════════════════
   AOCEDA, Paramètres
   JavaScript vanilla (ES2020), sans React/Babel
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

/* ── État initial NEUTRE (jamais de valeurs d'abonnement fabriquées) ──
   Avant que /api/users/me/ ne réponde (et si l'appel échoue), on n'affiche AUCUNE
   valeur inventée : ampérage/tarif/compteur/logement restent « inconnus » → l'UI
   montre « — » / « Non renseigné », jamais un faux « 10 A · Général · Postpayé ».
   Règle absolue du projet : ne jamais présenter de données fictives comme réelles. */
const FALLBACK_USER = {
  nom: '', email: '',
  typeLogement: '', amperage: null,
  typeTarif: '', typeCompteur: '',
  adresse: '', numeroCIE: ''
};

/* ── Grille tarifaire CIE officielle (mensuelle, TTC, récap informatif) ──
   clé : `${typeTarif}-${amperage}` → seuil T1 (kWh/mois), prix T1, prix T2 */
const GRILLE_RECAP = {
  'social-5': { seuil: 40, t1: '31,72', t2: '65,11' },
  'general-5': { seuil: 99, t1: '86,92', t2: '75,34' },
  'general-10': { seuil: 198, t1: '86,92', t2: '75,34' },
  'general-15': { seuil: 297, t1: '95,62', t2: '82,86' },
};
const t = window.AOCEDA_T || (x => x);

const COMPTEUR_LABELS = { postpaye: t('Intelligent postpayé'), prepaye: t('Prépayé') };
const TARIF_LABELS = { general: t('Général'), social: t('Social') };

/* Récap tarifaire : UNIQUEMENT si la grille (tarif+ampérage) est connue.
   Pas de substitution silencieuse par « general-10 » — on ne montre jamais les
   chiffres d'un autre abonnement sous le tarif du client. Renvoie '' si inconnu. */
function tarifRecapText(amperage, typeTarif) {
  const g = GRILLE_RECAP[`${typeTarif}-${amperage}`];
  if (!g) return '';
  if (window.AOCEDA_LANG === 'en') {
    return `Tier 1: ${g.seuil} kWh/month at ${g.t1} F, VAT included · Tier 2: ${g.t2} F/kWh`;
  }
  return `Tranche 1 : ${g.seuil} kWh/mois à ${g.t1} F, TVA incluse · Tranche 2 : ${g.t2} F/kWh`;
}
/* Variante HTML : chiffres (kWh / FCFA) en police mono tabulaire via <b> */
function tarifRecapHTML(amperage, typeTarif) {
  const g = GRILLE_RECAP[`${typeTarif}-${amperage}`];
  if (!g) return '';
  if (window.AOCEDA_LANG === 'en') {
    return `Tier 1: <b>${esc(g.seuil)} kWh/month</b> at <b>${esc(g.t1)} F</b>, VAT included · Tier 2: <b>${esc(g.t2)} F/kWh</b>`;
  }
  return `Tranche 1 : <b>${esc(g.seuil)} kWh/mois</b> à <b>${esc(g.t1)} F</b>, TVA incluse · Tranche 2 : <b>${esc(g.t2)} F/kWh</b>`;
}
/* ── Icônes & fragments HTML réutilisés ── */
const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
const SVG_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
const SVG_CHECK_SM = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
const SVG_CIRCLE_SM = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/></svg>';
const SAVE_OK_HTML = `<span class="save-ok">${SVG_CHECK}${t('Enregistré')}</span>`;

function saveErrorHTML(msg) {
  return `<span style="font-size:12px;color:var(--err);font-weight:600">${esc(t(msg))}</span>`;
}

/* ── Petites icônes pour les libellés de données (14px, trait courant) ── */
const _svg = p => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const I_USER  = _svg('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>');
const I_MAIL  = _svg('<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 5L2 7"/>');
const I_PHONE = _svg('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>');
const I_HOME  = _svg('<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>');
const I_PIN   = _svg('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>');
const I_LOCK  = _svg('<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>');
const I_INFO  = _svg('<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>');
const I_SENSOR= _svg('<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/>');
const I_BOLT  = _svg('<path d="M13 2L3 14h9l-1 8 10-12h-9z"/>');
const I_ARROW = _svg('<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>');
const I_PENCIL= _svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>');

/* ── Grille d'affichage de DONNÉES en lecture (pas des inputs grisés) ── */
function infoItem(o) {
  const has = o.value !== null && o.value !== undefined && String(o.value).trim() !== '';
  const val = has
    ? `<div class="info-value${o.mono ? ' mono' : ''}">${esc(o.value)}${o.badge ? `<span class="info-badge">${esc(o.badge)}</span>` : ''}</div>`
    : `<div class="info-value empty">${esc(o.empty || 'Non renseigné')}</div>`;
  return `<div class="info-item${o.full ? ' full' : ''}"><span class="info-label">${o.icon || ''}${esc(o.label)}</span>${val}</div>`;
}
function infoGrid(items) { return `<div class="info-grid">${items.map(infoItem).join('')}</div>`; }

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
  // Attributs du foyer (réels, facultatifs)
  nbPersonnesFoyer: '',
  superficie: '',
  // Photo de profil (URL renvoyée par l'API, ou null)
  photo: null,
  uploadingPhoto: false,
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
  is2FA: false,
  // Préférences (thème/langue stockés localement ; notifications issues du backend)
  themeChoice: localStorage.getItem('aoceda-theme-choice') || 'auto',
  langChoice: localStorage.getItem('aoceda-lang') || 'fr',
  theme: localStorage.getItem('aoceda-theme-choice') === 'dark' ? 'dark' : 'light',
  emailNotif: true,
  alarmNotif: localStorage.getItem('aoceda-alarm-enabled') !== 'false',
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
  // Met à jour l'URL avec le hash de la section courante sans provoquer de défilement (scroll jump)
  history.replaceState(null, null, '#' + id);
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
  state.typeLogement = u.typeLogement || '';
  state.adresse = u.adresse || '';
  state.numeroCIE = u.numeroCIE || '';
  // Valeurs d'abonnement : la VRAIE valeur si connue, sinon null/'' → affichées « — »
  // (jamais un défaut fabriqué qui se ferait passer pour l'abonnement réel du client).
  const amp = Number(u.amperage);
  state.amperage = [5, 10, 15].indexOf(amp) !== -1 ? amp : null;
  state.typeTarif = (u.typeTarif === 'social' || u.typeTarif === 'general') ? u.typeTarif : '';
  state.typeCompteur = (u.typeCompteur === 'prepaye' || u.typeCompteur === 'postpaye') ? u.typeCompteur : '';
  state.telephone = (u.telephone == null ? '' : u.telephone);
  // Attributs du foyer + photo (réels ; vides/null si non renseignés → jamais fabriqués)
  state.nbPersonnesFoyer = (u.nbPersonnesFoyer == null ? '' : u.nbPersonnesFoyer);
  state.superficie = (u.superficie_m2 == null ? '' : u.superficie_m2);
  state.photo = u.photo || null;
  state.is2FA = u.is_2fa_enabled || false;
  if (u.notifEmail !== undefined) state.emailNotif = u.notifEmail !== false;
  syncProfilInputs();
  syncFoyerInputs();
  renderProfil();
  renderFoyer();
  renderPrefs();
  refreshAvatars(); // header + sidebar suivent aussi la photo
}

function syncProfilInputs() {
  document.getElementById('profil-prenom').value = state.prenom;
  document.getElementById('profil-nomfam').value = state.nomFam;
  document.getElementById('profil-email').value = state.user.email || '';
  document.getElementById('profil-telephone').value = state.telephone;
  const adr = document.getElementById('profil-adresse');
  if (adr) adr.value = state.adresse || '';
}

function renderProfil() {
  const loaded = !!state.user.email; // profil réellement chargé depuis l'API ?
  const displayName = state.user.nom || '';
  const avatarEl = document.getElementById('profil-avatar');
  const nameEl = document.getElementById('profil-name');
  const cieEl = document.getElementById('profil-cie');
  if (!loaded) {
    // Avant chargement : squelette, jamais de tiret « — ».
    if (avatarEl) avatarEl.textContent = '·';
    if (nameEl) nameEl.innerHTML = '<span class="skel" style="width:9em"></span>';
    if (cieEl) { cieEl.style.display = ''; cieEl.innerHTML = '<span class="skel" style="width:6em"></span>'; }
  } else {
    const initials = displayName ? displayName.split(/\s+/).map(n => n[0]).join('').substring(0, 2).toUpperCase() : '';
    setAvatarEl(avatarEl, initials);
    if (nameEl) nameEl.textContent = displayName || t('Client');
    // Pas de tiret : on masque le badge N° CIE s'il n'existe pas (au lieu d'afficher « — »).
    if (cieEl) { cieEl.style.display = state.numeroCIE ? '' : 'none'; cieEl.textContent = state.numeroCIE || ''; }
  }
  document.getElementById('profil-role').textContent = state.adresse ? `${t('Client')} · ${state.adresse}` : t('Client');
  // Le formulaire est TOUJOURS affiché ; en lecture ses champs sont désactivés (grisés),
  // « Modifier » les réactive. On n'utilise plus la grille d'infos (#profil-view).
  const editing = state.editing.profil;
  const editBtn = document.getElementById('profil-edit-btn');
  editBtn.textContent = t('Modifier');
  editBtn.style.display = editing ? 'none' : '';
  document.getElementById('profil-form').style.display = '';
  document.getElementById('profil-view').style.display = 'none';
  ['profil-prenom', 'profil-nomfam', 'profil-telephone', 'profil-adresse'].forEach(id => {
    const el = document.getElementById(id); if (el) el.disabled = !editing;
  }); // #profil-email reste toujours désactivé (lecture seule)
  const brow = document.querySelector('#profil-form .btn-row');
  if (brow) brow.style.display = editing ? 'flex' : 'none';
  // Photo : le badge appareil-photo et « Supprimer » ne sont actifs qu'en édition (cohérent
  // avec le reste : on clique « Modifier » pour changer quoi que ce soit).
  const camBtn = document.getElementById('avatar-cam-btn');
  const delBtn = document.getElementById('avatar-del-btn');
  if (camBtn) camBtn.style.display = editing ? '' : 'none';
  if (delBtn) delBtn.style.display = (editing && state.photo && loaded) ? '' : 'none';
}

/* Applique la photo (ou les initiales) à un élément avatar. Styles de fond posés
   en inline → fonctionne pour n'importe quelle pastille (profil, header, sidebar). */
function setAvatarEl(el, initials) {
  if (!el) return;
  if (state.photo) {
    el.textContent = '';
    el.style.backgroundImage = `url("${state.photo}")`;
    el.style.backgroundSize = 'cover';
    el.style.backgroundPosition = 'center';
    el.classList.add('has-photo');
  } else {
    el.style.backgroundImage = '';
    el.classList.remove('has-photo');
    el.textContent = initials || '·';
  }
}

/* Initiales du nom (repli quand pas de photo). */
function currentInitials() {
  const n = state.user.nom || '';
  return n ? n.split(/\s+/).map(p => p[0]).join('').substring(0, 2).toUpperCase() : '';
}

/* Re-applique la photo/initiales sur toutes les pastilles de la page. */
function refreshAvatars() {
  const ini = currentInitials();
  setAvatarEl(document.getElementById('profil-avatar'), ini);
  setAvatarEl(document.getElementById('hdr-user-chip'), ini);
  setAvatarEl(document.getElementById('user-avatar'), ini);
  const delBtn = document.getElementById('avatar-del-btn');
  if (delBtn) delBtn.style.display = (state.editing.profil && state.photo) ? '' : 'none';
}

function avatarMsg(txt, kind) {
  const el = document.getElementById('avatar-feedback');
  if (!el) return;
  el.textContent = txt || '';
  el.style.color = kind === 'err' ? 'var(--err)' : kind === 'ok' ? 'var(--ok)' : 'var(--tx-s)';
}

/* Upload de la photo → POST multipart /api/users/me/photo/ */
function uploadPhoto(file) {
  if (state.uploadingPhoto) return;
  if (!/^image\//.test(file.type || '')) { avatarMsg(t('Le fichier doit être une image.'), 'err'); return; }
  if (file.size > 5 * 1024 * 1024) { avatarMsg(t('Image trop lourde (maximum 5 Mo).'), 'err'); return; }
  state.uploadingPhoto = true;
  avatarMsg(t('Envoi…'), '');
  const fd = new FormData();
  fd.append('photo', file);
  window.AOCEDA.authFetch('/api/users/me/photo/', { method: 'POST', body: fd })
    .then(res => res.ok ? res.json() : Promise.reject(res))
    .then(data => { state.photo = (data && data.photo) || null; refreshAvatars(); avatarMsg(t('Photo mise à jour.'), 'ok'); })
    .catch(() => avatarMsg(t("Échec de l'envoi de la photo."), 'err'))
    .finally(() => { state.uploadingPhoto = false; });
}

/* Suppression de la photo → DELETE /api/users/me/photo/ */
function deletePhoto() {
  if (state.uploadingPhoto) return;
  state.uploadingPhoto = true;
  avatarMsg(t('Suppression…'), '');
  window.AOCEDA.authFetch('/api/users/me/photo/', { method: 'DELETE' })
    .then(res => res.ok ? true : Promise.reject(res))
    .then(() => { state.photo = null; refreshAvatars(); avatarMsg(t('Photo supprimée.'), 'ok'); })
    .catch(() => avatarMsg(t('Échec de la suppression.'), 'err'))
    .finally(() => { state.uploadingPhoto = false; });
}

/* Enregistrement profil → PUT /api/users/me/ */
function saveProfil() {
  const nomComplet = `${state.nomFam} ${state.prenom}`.trim();
  const fb = document.getElementById('profil-feedback');
  if (fb) fb.innerHTML = '';
  fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify({
    nom: nomComplet, telephone: state.telephone, adresse: state.adresse,
  }) })
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
  const pers = document.getElementById('foyer-personnes');
  if (pers) pers.value = state.nbPersonnesFoyer === '' ? '' : state.nbPersonnesFoyer;
  const sup = document.getElementById('foyer-superficie');
  if (sup) sup.value = state.superficie === '' ? '' : state.superficie;
}

/* Panneau « Abonnement CIE » verrouillé (référencé par le technicien / la CIE).
   Réutilisé en mode lecture ET en mode édition (jamais éditable côté client). */
function lockedAboPanelHTML() {
  const amp = state.amperage != null ? `${esc(state.amperage)} A` : '—';
  const recap = tarifRecapHTML(state.amperage, state.typeTarif); // '' si grille inconnue
  return `<div class="locked-panel">
    <div class="locked-head">${I_LOCK}<span class="locked-title">${t('Abonnement CIE')}<span class="locked-by">${t('· référencé par votre technicien')}</span></span></div>
    <div class="locked-rows">
      <div class="abo-line"><span>${t('Ampérage souscrit')}</span><strong>${amp}</strong></div>
      <div class="abo-line"><span>${t('Type de compteur')}</span><strong>${esc(COMPTEUR_LABELS[state.typeCompteur] || '—')}</strong></div>
      <div class="abo-line"><span>${t('Type de tarif')}</span><strong>${esc(TARIF_LABELS[state.typeTarif] || '—')}</strong></div>
      <div class="abo-line"><span>${t("Numéro d'abonné CIE")}</span><strong>${esc(state.numeroCIE || '—')}</strong></div>
    </div>
    <div class="locked-foot">
      ${recap ? `<div class="abo-recap">${recap}</div>` : ''}
      <p class="abo-note">${I_INFO}<span>${t("Pour changer d'ampérage, de tarif, de type de compteur ou de numéro d'abonné CIE, contactez votre technicien AOCEDA.")}</span></p>
    </div>
  </div>`;
}

function renderFoyer() {
  // Même principe que le profil : formulaire toujours affiché, champs grisés hors édition.
  const editing = state.editing.foyer;
  const editBtn = document.getElementById('foyer-edit-btn');
  editBtn.textContent = t('Modifier');
  editBtn.style.display = editing ? 'none' : '';
  document.getElementById('foyer-form').style.display = '';
  document.getElementById('foyer-view').style.display = 'none';
  // Type de logement (radios) + adresse : désactivés en lecture. L'abonnement CIE reste verrouillé.
  document.querySelectorAll('#foyer-logement input[name="log"]').forEach(r => { r.disabled = !editing; });
  ['foyer-adresse', 'foyer-personnes', 'foyer-superficie'].forEach(id => {
    const el = document.getElementById(id); if (el) el.disabled = !editing;
  });
  const aboEdit = document.getElementById('foyer-abo-edit');
  if (aboEdit) aboEdit.innerHTML = lockedAboPanelHTML();
  const brow = document.querySelector('#foyer-form .btn-row');
  if (brow) brow.style.display = editing ? 'flex' : 'none';
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
    // '' → null (champ vidé) ; sinon entier. Jamais de valeur fabriquée.
    nbPersonnesFoyer: state.nbPersonnesFoyer === '' ? null : Number(state.nbPersonnesFoyer),
    superficie_m2: state.superficie === '' ? null : Number(state.superficie),
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

/* ════════════════════════ CAPTEURS & RÈGLES (vue d'ensemble) ════════════════════════
   Les règles se CRÉENT / MODIFIENT / SUPPRIMENT désormais dans Alertes → Configuration
   (CRUD multi-configurations). Ici, on ne DUPLIQUE plus un second éditeur : on affiche
   un récapitulatif en lecture seule + une passerelle vers la vraie page d'édition. */
function capStateInfo(s) {
  const online = s.derniereLecture && (Date.now() - new Date(s.derniereLecture).getTime()) <= 120000;
  if (!online) return { cls: 'off', txt: t('Hors ligne') };
  return s.etatCourant === 'ON' ? { cls: 'on', txt: t('Actif') } : { cls: 'idle', txt: t('En ligne · éteint') };
}

function renderCapteurs() {
  const wrap = document.getElementById('capteurs-list');
  if (!wrap) return;

  if (!state.sensorsLoaded) {
    wrap.innerHTML = `<div class="card"><div class="empty-card">${t('Chargement de vos capteurs…')}</div></div>`;
    return;
  }
  if (state.sensors.length === 0) {
    wrap.innerHTML = `<div class="card"><div class="empty-card">${t('Aucun capteur installé pour le moment. Un technicien doit installer vos capteurs pour configurer des règles d\'alerte.')}</div></div>`;
    return;
  }

  const items = state.sensors.map(s => {
    const st = capStateInfo(s);
    const rules = state.regles.filter(r => String(r.capteur) === String(s.id));
    const chips = rules.length
      ? rules.map(r => {
          const p = Math.round(Number(r.puissanceMax_W)) || 0;
          const actif = p > 0 && p < 100000;
          const locale = window.AOCEDA_LANG === 'en' ? 'en-GB' : 'fr-FR';
          const seuil = actif ? `${p.toLocaleString(locale)} W` : t('désactivé');
          // Chip vert seulement si la config est active ; sinon pastille neutre (pas de « succès » vert pour un seuil désactivé).
          return `<span class="cap-chip${actif ? '' : ' none'}">${esc(r.nom || t('Configuration'))} · ${esc(seuil)}</span>`;
        }).join('')
      : `<span class="cap-chip none">${t('Aucune configuration')}</span>`;
    
    const configWord = rules.length > 1 ? t('configurations') : t('configuration');
    const capSubText = window.AOCEDA_LANG === 'en'
      ? `${rules.length} monitoring ${configWord}`
      : `${rules.length} ${configWord} de surveillance`;

    return `<div class="cap-item">
      <div class="cap-ico">${I_SENSOR}</div>
      <div class="cap-main">
        <div class="cap-name">${esc(s.nom)}<span class="cap-state ${st.cls}">${esc(st.txt)}</span></div>
        <div class="cap-sub">${capSubText}</div>
      </div>
      <div class="cap-rules">${chips}</div>
      <button type="button" class="cap-rename" data-rename-id="${esc(s.id)}" data-rename-nom="${esc(s.nom)}" aria-label="${t('Renommer cet appareil')}" title="${t('Renommer cet appareil')}">${I_PENCIL}</button>
    </div>`;
  }).join('');

  wrap.innerHTML =
    `<div class="cap-summary">${items}</div>` +
    `<div class="cap-gateway">
      <div class="cap-gateway-ico">${I_BOLT}</div>
      <div class="cap-gateway-txt">
        <div class="cap-gateway-title">${t("Configurer les règles d'alerte")}</div>
        <div class="cap-gateway-sub">${t("Créez, modifiez ou supprimez vos configurations de surveillance (seuil de puissance, surveillance nocturne) — une ou plusieurs par capteur.")}</div>
      </div>
      <a class="cap-gateway-btn" href="/alertes/#config">${t("Gérer mes alertes")} ${I_ARROW}</a>
    </div>`;
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
  document.getElementById('pwd-toggle-btn').textContent = state.pwdModal ? t('Annuler') : t('Changer');
  document.getElementById('pwd-panel').style.display = state.pwdModal ? '' : 'none';

  // Toggle 2FA
  const tfaTog = document.getElementById('tfa-toggle');
  if (tfaTog) {
    tfaTog.classList.toggle('on', state.is2FA);
    tfaTog.setAttribute('aria-checked', String(state.is2FA));
  }

  // Jauge de robustesse
  const strengthEl = document.getElementById('pwd-strength');
  if (!state.newPwd) {
    strengthEl.innerHTML = '';
  } else {
    const s = pwdScore(state.newPwd);
    strengthEl.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <div class="pwd-bars">${[1, 2, 3, 4, 5].map(i => `<div class="pbar" style="background:${i <= s ? PWD_COLS[s] : 'var(--bd-s)'}"></div>`).join('')}</div>
      <span class="pwd-strength-lbl" style="color:${PWD_COLS[s]}">${t(PWD_LBLS[s])}</span>
    </div>`;
  }

  // Liste des règles
  const rules = [
    { txt: t('Minimum 8 caractères'), ok: state.newPwd.length >= 8 },
    { txt: t('Au moins 1 majuscule'), ok: /[A-Z]/.test(state.newPwd) },
    { txt: t('Au moins 1 chiffre'), ok: /[0-9]/.test(state.newPwd) }
  ];
  // État satisfait/non satisfait EXPOSÉ au lecteur d'écran (pas seulement couleur+icône).
  document.getElementById('pwd-rules').innerHTML = rules.map(r =>
    `<div class="rule${r.ok ? ' v' : ''}">${r.ok ? SVG_CHECK_SM : SVG_CIRCLE_SM}${esc(r.txt)}<span class="sr-only"> — ${r.ok ? t('satisfait') : t('non satisfait')}</span></div>`
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
  saveBtn.innerHTML = state.savingPwd ? '<span class="spinner"></span>' + t('Mise à jour…') : t('Enregistrer le mot de passe');

  // Feedback succès
  document.getElementById('pwd-feedback').innerHTML = state.pwdSaved
    ? `<span class="save-ok">${SVG_CHECK}${t('Mot de passe mis à jour')}</span>`
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
          || data.detail || t('Échec de la mise à jour du mot de passe.');
        showPwdError(t(msg));
      }
    })
    .catch(() => { state.savingPwd = false; renderPwdUI(); showPwdError(t('Échec de la mise à jour du mot de passe.')); });
}

/* ════════════════════════ PRÉFÉRENCES (maquette locale) ════════════════════════ */
function renderPrefs() {
  document.querySelectorAll('#theme-options input[name="theme"]').forEach(r => {
    r.checked = r.value === state.themeChoice;
  });
  const tog = document.getElementById('email-toggle');
  tog.classList.toggle('on', state.emailNotif);
  tog.setAttribute('aria-checked', String(state.emailNotif));

  const alarmTog = document.getElementById('alarm-toggle');
  if (alarmTog) {
    alarmTog.classList.toggle('on', state.alarmNotif);
    alarmTog.setAttribute('aria-checked', String(state.alarmNotif));
  }

  document.querySelectorAll('#lang-options input[name="lang"]').forEach(r => {
    r.checked = r.value === state.langChoice;
  });
}

/* ════════════════════════ DONNÉES & CONFIDENTIALITÉ ════════════════════════ */
function exportData() {
  if (state.exporting) return;
  state.exporting = true;
  const btn = document.getElementById('export-btn');
  const label = document.getElementById('export-label');
  btn.disabled = true;
  label.textContent = t('Export en cours…');
  downloadCSV('/api/analytics/export/?period=month', 'aoceda_donnees.csv')
    .catch(err => console.error(err))
    .finally(() => {
      state.exporting = false;
      btn.disabled = false;
      label.textContent = t('Exporter mes mesures (CSV)');
    });
}

function setDelModal(open) {
  document.getElementById('del-overlay').style.display = open ? '' : 'none';
  // Le mot de passe est requis pour la suppression réelle du compte (DELETE /api/users/me/).
  // On vide le champ à la fermeture de la modale.
  const pwd = document.getElementById('del-pwd');
  if (!open && pwd) pwd.value = '';
  // Restaure le focus sur le bouton déclencheur à la fermeture (a11y : on ne laisse
  // pas le focus « nulle part » dans le document).
  if (!open) { const t = document.getElementById('delete-btn'); if (t) t.focus(); }
}

/* Piège de focus : Tab / Shift+Tab bouclent dans la modale de suppression (aria-modal)
   au lieu d'atteindre les contrôles floutés en arrière-plan. */
function trapDelFocus(e) {
  if (e.key !== 'Tab') return;
  const f = ['del-pwd', 'del-cancel-btn', 'del-confirm-btn'].map(id => document.getElementById(id)).filter(Boolean);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/* ════════════════════════ RENOMMAGE APPAREIL ════════════════════════ */
/* Capteur en cours de renommage (id + bouton déclencheur pour restaurer le focus). */
let renameCtx = { id: null, trigger: null };

function openRenameModal(id, nom, trigger) {
  renameCtx = { id, trigger: trigger || null };
  const ov = document.getElementById('rename-overlay');
  const input = document.getElementById('rename-input');
  const err = document.getElementById('rename-error');
  if (err) { err.hidden = true; err.textContent = ''; }
  if (input) { input.value = nom || ''; }
  ov.style.display = '';
  // Focus + sélection du texte pour un renommage rapide.
  if (input) { input.focus(); input.select(); }
}

function closeRenameModal() {
  document.getElementById('rename-overlay').style.display = 'none';
  const t = renameCtx.trigger;
  renameCtx = { id: null, trigger: null };
  // a11y : rend le focus au crayon qui a ouvert la modale.
  if (t && document.body.contains(t)) t.focus();
}

/* Piège de focus dans la modale de renommage (mêmes règles que la suppression). */
function trapRenameFocus(e) {
  if (e.key !== 'Tab') return;
  const f = ['rename-input', 'rename-cancel-btn', 'rename-confirm-btn'].map(id => document.getElementById(id)).filter(Boolean);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

function submitRename() {
  const id = renameCtx.id;
  if (!id) return;
  const input = document.getElementById('rename-input');
  const err = document.getElementById('rename-error');
  const btn = document.getElementById('rename-confirm-btn');
  const nom = (input.value || '').trim();
  if (!nom) {
    if (err) { err.textContent = t('Le nom ne peut pas être vide.'); err.hidden = false; }
    input.focus();
    return;
  }
  // Aucun changement → on ferme sans appel réseau.
  const current = state.sensors.find(s => String(s.id) === String(id));
  if (current && current.nom === nom) { closeRenameModal(); return; }

  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = t('Enregistrement…');
  if (err) { err.hidden = true; err.textContent = ''; }

  fetchWithAuth(`/api/sensors/mes-capteurs/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ nom }),
  })
    .then(data => {
      if (data && data.id) {
        // Maj locale + re-rendu, sans recharger toute la page.
        const s = state.sensors.find(x => String(x.id) === String(data.id));
        if (s) s.nom = data.nom;
        renderCapteurs();
        closeRenameModal();
      } else {
        const msg = (data && (data.nom && data.nom[0])) || (data && data.detail) || t('Renommage impossible.');
        if (err) { err.textContent = t(msg); err.hidden = false; }
        btn.disabled = false;
        btn.textContent = label;
      }
    })
    .catch(() => {
      if (err) { err.textContent = t('Erreur réseau. Réessayez.'); err.hidden = false; }
      btn.disabled = false;
      btn.textContent = label;
    });
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

  // Toggle 2FA
  const tfaTog = document.getElementById('tfa-toggle');
  if (tfaTog) {
    tfaTog.addEventListener('click', () => {
      const newVal = !state.is2FA;
      tfaTog.classList.toggle('on', newVal);
      tfaTog.setAttribute('aria-checked', String(newVal));
      fetchWithAuth('/api/users/me/2fa/', {
        method: 'POST',
        body: JSON.stringify({ enable: newVal })
      }).then(res => {
        if (res && res.is_2fa_enabled !== undefined) {
          state.is2FA = res.is_2fa_enabled;
          renderPwdUI();
        }
      });
    });
  }

  // Changer de langue (simulateur local)
  document.querySelectorAll('#lang-options input[name="lang"]').forEach(r => {
    r.addEventListener('change', (e) => {
      state.langChoice = e.target.value;
      localStorage.setItem('aoceda-lang', state.langChoice);
      window.location.reload(); // recharge la page pour appliquer la langue
    });
  });

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
  const profAdr = document.getElementById('profil-adresse');
  if (profAdr) profAdr.addEventListener('input', e => { state.adresse = e.target.value; });

  // ── Photo de profil (upload multipart + suppression) ──
  const camBtn = document.getElementById('avatar-cam-btn');
  const fileInput = document.getElementById('avatar-input');
  const delBtn = document.getElementById('avatar-del-btn');
  if (camBtn && fileInput) {
    camBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const f = fileInput.files && fileInput.files[0];
      if (f) uploadPhoto(f);
      fileInput.value = ''; // permet de re-sélectionner le même fichier
    });
  }
  if (delBtn) delBtn.addEventListener('click', deletePhoto);

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
  const foyerPers = document.getElementById('foyer-personnes');
  if (foyerPers) foyerPers.addEventListener('input', e => { state.nbPersonnesFoyer = e.target.value; });
  const foyerSup = document.getElementById('foyer-superficie');
  if (foyerSup) foyerSup.addEventListener('input', e => { state.superficie = e.target.value; });

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

  const alarmToggleBtn = document.getElementById('alarm-toggle');
  if (alarmToggleBtn) {
    alarmToggleBtn.addEventListener('click', () => {
      state.alarmNotif = !state.alarmNotif;
      localStorage.setItem('aoceda-alarm-enabled', String(state.alarmNotif));
      renderPrefs();
    });
  }

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
      if (errEl) { errEl.textContent = t('Mot de passe requis.'); errEl.hidden = false; }
      if (pwd) pwd.focus();
      return;
    }
    const btn = document.getElementById('del-confirm-btn');
    btn.disabled = true;
    btn.textContent = t('Suppression…');
    fetchWithAuth('/api/users/me/', { method: 'DELETE', body: JSON.stringify({ password }) })
      .then(data => {
        if (data && data.detail && data.detail.toLowerCase().includes('supprim')) {
          // Succès : purge les tokens et redirige vers l'accueil
          localStorage.removeItem('aoceda_access_token');
          localStorage.removeItem('aoceda_refresh_token');
          window.location.href = '/';
        } else {
          const msg = (data && data.detail) || 'Suppression impossible. Vérifiez votre mot de passe.';
          if (errEl) { errEl.textContent = t(msg); errEl.hidden = false; }
          btn.disabled = false;
          btn.textContent = t('Supprimer mon compte');
        }
      })
      .catch(() => {
        if (errEl) { errEl.textContent = t('Erreur réseau. Réessayez.'); errEl.hidden = false; }
        btn.disabled = false;
        btn.textContent = t('Supprimer mon compte');
      });
  });
  document.getElementById('del-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) setDelModal(false);
  });
  document.getElementById('del-overlay').addEventListener('keydown', trapDelFocus);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('del-overlay').style.display !== 'none') {
      setDelModal(false);
    }
  });

  // ── Renommage : le crayon est rendu dynamiquement → délégation sur le conteneur ──
  const capList = document.getElementById('capteurs-list');
  if (capList) {
    capList.addEventListener('click', e => {
      const btn = e.target.closest('.cap-rename');
      if (!btn) return;
      openRenameModal(btn.dataset.renameId, btn.dataset.renameNom, btn);
    });
  }
  document.getElementById('rename-cancel-btn').addEventListener('click', closeRenameModal);
  document.getElementById('rename-confirm-btn').addEventListener('click', submitRename);
  document.getElementById('rename-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); submitRename(); }
  });
  document.getElementById('rename-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeRenameModal();
  });
  document.getElementById('rename-overlay').addEventListener('keydown', trapRenameFocus);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('rename-overlay').style.display !== 'none') {
      closeRenameModal();
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
