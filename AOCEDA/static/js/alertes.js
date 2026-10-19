'use strict';
const t = window.AOCEDA_T || (x => x);
const LOCALE = localStorage.getItem('aoceda-lang') === 'en' ? 'en-GB' : 'fr-FR';
/* ════════════════════════════════════════════════════════════
   AOCEDA, Alertes & Configuration (page dédiée). Deux onglets : « Mes alertes » et « Configuration ».
   Réécrit le 19/10/2026 après audit : états honnêtes (chargement, erreur, « tout va bien » seulement si la surveillance
   tourne vraiment), actualisation automatique, recherche et filtres, jours regroupés, lien vers l'historique du jour et
   vers la règle, « non lue », réglages non perdus, validations des règles, e-mail de test, alarme sonore réglable.
   19/10/2026 (2e passe) : un seul chemin vers les réglages, un seul vocabulaire (« règle »), résumé en une ligne, lignes de
   règle cliquables.
   La traduction anglaise est faite par la page entière (i18n.js) : les textes sont écrits en français ici.
   ════════════════════════════════════════════════════════════ */

const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. REJETTE sur tout statut non-OK (sinon
   un 400/500 à corps JSON serait pris pour un succès) ; le corps de l'erreur est gardé (err.data) pour l'afficher. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
    if (!res.ok) {
      return res.json().catch(() => null).then(data => {
        const e = new Error('HTTP ' + res.status);
        e.status = res.status; e.data = data;
        throw e;
      });
    }
    return res.json().catch(() => null);
  });
}
/* Message lisible d'une erreur d'API : « Le seuil de puissance doit être compris entre 5 W et 5 000 W. » */
function messageErreur(err) {
  const d = err && err.data;
  if (d) {
    const morceaux = [];
    const aplatir = v => { if (Array.isArray(v)) v.forEach(aplatir); else if (v && typeof v === 'object') Object.values(v).forEach(aplatir); else if (v) morceaux.push(String(v)); };
    aplatir(d);
    if (morceaux.length) return morceaux.join(' ');
  }
  return err && err.status ? `${t('erreur')} ${err.status}` : t('erreur réseau');
}
function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
const $ = id => document.getElementById(id);
const nbFr = (v, dec) => Number(v).toLocaleString(LOCALE, { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 });
const pad2 = n => String(n).padStart(2, '0');
const cleJour = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/* ════════════════ Thème ════════════════ */
const MOON_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const SUN_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
let theme = document.documentElement.getAttribute('data-theme') || 'light';
const themeToggleBtn = $('theme-toggle');
function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  if (themeToggleBtn) themeToggleBtn.innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
}
if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => { theme = window.AOCEDA.toggleTheme(); applyTheme(); });

/* ════════════════ Onglets ════════════════ */
let currentTab = 'alertes';
const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
const tabPanels = { alertes: $('tab-alertes'), config: $('tab-config') };
const TAB_TO_HASH = { alertes: '', config: '#config' };
function hashToTab(hash) { return hash === '#config' ? 'config' : 'alertes'; }

function setTab(nom, opts) {
  currentTab = nom;
  tabButtons.forEach(b => {
    const on = b.dataset.tab === nom;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
    b.setAttribute('tabindex', on ? '0' : '-1');
  });
  Object.keys(tabPanels).forEach(k => { if (tabPanels[k]) tabPanels[k].style.display = k === nom ? '' : 'none'; });
  if (!opts || !opts.fromHash) history.replaceState(null, '', window.location.pathname + window.location.search + TAB_TO_HASH[nom]);
  if (nom === 'alertes') initAlertes(); else initConfig();
}
tabButtons.forEach((b, i) => {
  b.addEventListener('click', () => setTab(b.dataset.tab));
  // flèches gauche / droite : navigation clavier entre onglets
  b.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const n = tabButtons[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabButtons.length) % tabButtons.length];
    n.focus(); setTab(n.dataset.tab);
  });
});
window.addEventListener('hashchange', () => {
  const nom = hashToTab(window.location.hash);
  if (nom !== currentTab) setTab(nom, { fromHash: true });
});

/* ════════════════ Onglet « Mes alertes » ════════════════ */
const alertState = {
  status: 'loading',      // 'loading' | 'ok' | 'error'
  alerts: [], surv: null,
  filtre: 'toutes', type: 'all', periode: 'tout', q: '', limite: 50,
  nouveaux: new Set(), derniereMaj: null, majEchec: false,
};
const filterBar = $('filter-bar'), alertList = $('alert-list'), alertSummary = $('alert-summary');
const markAllBtn = $('mark-all-read'), tabAlertCount = $('tab-alert-count');

/* Sévérités du serveur : 'Critique' | 'Avertissement' | 'Info'. Une alerte active n'est JAMAIS affichée « résolue ». */
const SEV_LABEL = { crit: 'Critique', warn: 'Avertissement', info: 'Information' };
const SEV_CLASS = { crit: 'sev-crit', warn: 'sev-warn', info: 'sev-info' };
const BAR_COLOR = { crit: 'var(--err)', warn: 'var(--warn)', info: 'var(--info)' };
const ALERT_FILTERS = [['toutes', 'Toutes'], ['non-lues', 'Non lues'], ['crit', 'Critique'], ['warn', 'Avertissement'], ['info', 'Information']];
const ICO_CRIT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
const ICO_WARN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
const ICO_BELL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';
const TYPE_LABELS = {
  DEPASSEMENT_SEUIL: 'Dépassement de seuil', CONSOMMATION_NOCTURNE: 'Consommation nocturne', CREDIT_BAS: 'Crédit prépayé bas',
  TRANCHE_APPROCHE: 'Tranche suivante proche', TRANCHE_FRANCHIE: 'Tranche suivante atteinte', INTERVENTION: 'Suivi de votre intervention',
};

function tempsRelatif(d) {
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return t('à l’instant');
  if (s < 3600) return `${t('il y a')} ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${t('il y a')} ${Math.round(s / 3600)} h`;
  const hier = new Date(); hier.setDate(hier.getDate() - 1);
  const h = `${pad2(d.getHours())}h${pad2(d.getMinutes())}`;
  return cleJour(d) === cleJour(hier) ? `${t('hier à')} ${h}` : `${d.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short' })} · ${h}`;
}
function libelleJour(d) {
  const auj = new Date(), hier = new Date(); hier.setDate(hier.getDate() - 1);
  if (cleJour(d) === cleJour(auj)) return t('Aujourd’hui');
  if (cleJour(d) === cleJour(hier)) return t('Hier');
  return d.toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long', year: d.getFullYear() === auj.getFullYear() ? undefined : 'numeric' });
}

function mapApiAlert(a) {
  const sevRaw = a['sévérité'] || a.severity || '';
  const sev = sevRaw === 'Critique' ? 'crit' : (sevRaw === 'Avertissement' ? 'warn' : 'info');
  const date = a.createdAt ? new Date(a.createdAt) : new Date();
  const raw = a.type || 'ALERTE';
  return {
    id: String(a.id), rawType: raw,
    type: a.type_display || TYPE_LABELS[raw] || raw.replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase()),
    msg: a.message, date, sev, read: !!a.lue,
    capteur: a.capteur_nom || null, capteurId: a.capteur_id || null, regleId: a.regle_id || null, interventionId: a.intervention_id || null, regleNom: a.regle_nom || null,
  };
}

/* Message d'action transitoire, honnête, jamais silencieux. */
const alertFeedback = $('alert-feedback');
let feedbackTimer = null;
function showAlertFeedback(msg, isError) {
  if (!alertFeedback) return;
  alertFeedback.textContent = msg;
  alertFeedback.classList.toggle('err', !!isError);
  clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => { alertFeedback.textContent = ''; }, 6000);
}

/* Badge du menu + cloche : mis à jour tout de suite, SANS appel réseau (le rendu de la liste le fait à chaque
   affichage). Le serveur n'est relu (syncShellBadges) qu'APRÈS une écriture confirmée : sinon le relevé du compteur
   pouvait revenir avant l'enregistrement et annuler le marquage qu'on venait de faire. */
function majBadgesLocaux() {
  const unread = alertState.alerts.filter(x => !x.read).length;
  const navBadge = $('nav-alert-badge');
  if (navBadge) { navBadge.textContent = String(unread); navBadge.style.display = unread > 0 ? '' : 'none'; }
  const dot = $('notif-dot');
  if (dot) dot.style.display = unread > 0 ? '' : 'none';
}
let ecrituresEnCours = 0;
function syncShellBadges() {
  majBadgesLocaux();
  if (window.AOCEDA && window.AOCEDA.rafraichirAlertes) window.AOCEDA.rafraichirAlertes();
}

function visibles() {
  const { alerts, filtre, type, periode, q } = alertState;
  const duree = { '1j': 864e5, '7j': 7 * 864e5, '30j': 30 * 864e5 }[periode];
  const depuis = duree ? Date.now() - duree : 0;
  const mot = q.trim().toLowerCase();
  return alerts.filter(a =>
    (filtre === 'toutes' || (filtre === 'non-lues' ? !a.read : a.sev === filtre))
    && (type === 'all' || a.rawType === type)
    && (!depuis || a.date.getTime() >= depuis)
    && (!mot || `${a.msg} ${a.type} ${a.capteur || ''} ${a.regleNom || ''}`.toLowerCase().includes(mot)));
}
const filtresActifs = () => alertState.filtre !== 'toutes' || alertState.type !== 'all' || alertState.periode !== 'tout' || alertState.q.trim() !== '';

function renderAlertSummary() {
  const a = alertState.alerts, ok = alertState.status === 'ok';
  const unread = a.filter(x => !x.read).length;
  const crit = a.filter(x => x.sev === 'crit' && !x.read).length;
  const warn = a.filter(x => x.sev === 'warn' && !x.read).length;
  if (alertSummary) {
    if (!ok) alertSummary.innerHTML = '';
    else if (a.length === 0) alertSummary.innerHTML = '';
    else if (unread === 0) alertSummary.innerHTML = `<strong>${t('Aucune alerte non lue')}</strong> <span class="sum-sep">·</span> ${a.length} ${a.length > 1 ? t('alertes au total') : t('alerte au total')}`;
    else alertSummary.innerHTML = `<strong>${unread}</strong> ${unread > 1 ? t('alertes non lues') : t('alerte non lue')}`
      + (crit ? ` <span class="sum-chip crit">${crit} ${crit > 1 ? t('critiques') : t('critique')}</span>` : '')
      + (warn ? ` <span class="sum-chip warn">${warn} ${warn > 1 ? t('avertissements') : t('avertissement')}</span>` : '');
  }
  // « Tout marquer comme lu » n'existe que s'il y a quelque chose à marquer (avant : bouton grisé en permanence)
  if (markAllBtn) markAllBtn.hidden = !ok || unread === 0;
  if (tabAlertCount) { tabAlertCount.textContent = String(unread); tabAlertCount.style.display = ok && unread > 0 ? '' : 'none'; }
  if (ok) majBadgesLocaux();
}

/* Ce que la surveillance fait RÉELLEMENT : avant le 19/10/2026 la page disait « Tout va bien, aucune règle ne s'est
   déclenchée » même sans capteur, sans règle, ou boîtier muet depuis des jours. */
function diagnosticSurveillance() {
  const s = alertState.surv;
  if (!s) return null;
  const dernier = s.dernier_contact ? new Date(s.dernier_contact) : null;
  if (s.capteurs === 0) return { niveau: 'warn', titre: t('Aucun capteur installé'), texte: t('Rien n’est surveillé tant qu’aucun capteur n’est installé par votre technicien.') };
  if (s.regles === 0 && !s.reglage_simple) return { niveau: 'warn', titre: t('Aucune alerte activée'), texte: t('Vos appareils ne sont pas surveillés : activez une alerte dans les réglages.'), action: 'reglages' };
  if (!s.en_ligne) {
    return { niveau: 'warn', titre: t('Boîtier hors ligne'), texte: dernier
      ? `${t('Aucune mesure reçue depuis')} ${tempsRelatif(dernier).replace(t('il y a') + ' ', '')} : ${t('rien n’est surveillé en ce moment.')}`
      : t('Le boîtier n’a encore jamais envoyé de mesure : rien n’est surveillé pour l’instant.'), action: 'panne' };
  }
  if (s.capteurs_surveilles < s.capteurs) {
    const n = s.capteurs - s.capteurs_surveilles;
    return { niveau: 'info', titre: `${n} ${n > 1 ? t('capteurs ne sont pas surveillés') : t('capteur n’est pas surveillé')}`, texte: t('Activez une alerte de consommation dans les réglages pour le surveiller aussi.'), action: 'reglages' };
  }
  if (s.absence_active) {
    return { niveau: 'info', titre: t('Mode absence actif'), texte: `${t('La surveillance nocturne est suspendue')}${s.absence_jusquau ? ` ${t('jusqu’au')} ${new Date(s.absence_jusquau + 'T00:00:00').toLocaleDateString(LOCALE, { day: 'numeric', month: 'long' })}` : ''}. ${t('Le seuil de puissance et le crédit restent surveillés.')}`, action: 'reglages' };
  }
  return { niveau: 'ok', titre: t('Surveillance active'),
    texte: `${s.capteurs} ${s.capteurs > 1 ? t('capteurs surveillés') : t('capteur surveillé')}${dernier ? ` · ${t('dernière mesure')} ${tempsRelatif(dernier)}` : ''}.` };
}
function renderSurvStrip() {
  const el = $('surv-strip');
  if (!el) return;
  const d = diagnosticSurveillance();
  if (!d) { el.hidden = true; return; }
  el.hidden = false;
  el.className = `surv-strip is-${d.niveau}`;
  const ico = d.niveau === 'ok' ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
  el.innerHTML = `<span class="surv-ico">${ico}</span><span class="surv-txt"><strong>${esc(d.titre)}</strong> · ${esc(d.texte)}</span>`
    + (d.action ? `<button type="button" class="surv-btn" data-act="${d.action}">${d.action === 'panne' ? t('Déclarer une panne') : t('Voir les réglages')}</button>` : '');
}

function etatVide() {
  const d = diagnosticSurveillance();
  const svg = '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';
  if (d && d.niveau === 'ok') {
    return `<div class="empty-state">${svg}<div class="es-title">${t('Aucune alerte, tout va bien')}</div><div class="es-sub">${esc(d.texte)} ${t('Les alertes apparaîtront ici automatiquement.')}</div></div>`;
  }
  // Un problème de surveillance est déjà expliqué (avec son bouton) dans le bandeau juste au-dessus : pas de second message ni de second bouton
  return `<div class="empty-state">${svg}<div class="es-title">${t('Aucune alerte pour le moment')}</div><div class="es-sub">${t('Les alertes apparaîtront ici dès qu’un de vos réglages se déclenchera.')}</div></div>`;
}

function itemHtml(a) {
  const nouvelle = alertState.nouveaux.has(a.id);
  const exact = a.date.toLocaleString(LOCALE, { dateStyle: 'full', timeStyle: 'short' });
  const lienJour = a.capteurId
    ? `<a class="a-link" href="/historique/?jour=${cleJour(a.date)}&capteur=${encodeURIComponent(a.capteurId)}">${t('Voir ce jour')}</a>`
    : (a.rawType === 'CREDIT_BAS' || a.rawType.indexOf('TRANCHE') === 0 ? `<a class="a-link" href="/previsions/">${t('Voir ma facture')}</a>` : '');
  const lienDemande = a.interventionId ? `<a class="a-link" href="/interventions/?ouvrir=${encodeURIComponent(a.interventionId)}">${t('Voir ma demande')}</a>` : '';
  const lienRegle = a.regleId ? `<button class="a-link" type="button" data-regle="${esc(a.regleId)}" title="${esc(a.regleNom || '')}">${t('Modifier la règle')}</button>` : '';
  const optKind = a.regleId ? '' : ({ DEPASSEMENT_SEUIL: 'depassement', CONSOMMATION_NOCTURNE: 'nuit', CREDIT_BAS: 'credit' }[a.rawType] || (String(a.rawType).indexOf('TRANCHE') === 0 ? 'tranche' : ''));
  const lienReglage = optKind ? `<button class="a-link" type="button" data-reglage="${optKind}">${t('Régler cette alerte')}</button>` : '';
  const lu = a.read
    ? `<button class="undo-btn" type="button" data-id="${esc(a.id)}" data-lue="0" title="${t('Marquer comme non lue')}" aria-label="${t('Marquer cette alerte comme non lue')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 9 8 9"/></svg></button>`
    : `<button class="dismiss-btn" type="button" data-id="${esc(a.id)}" data-lue="1" aria-label="${t('Marquer cette alerte comme lue')}">&#10003; ${t('Lue')}</button>`;
  return `<article class="alert-item${a.read ? ' dismissed' : ''}${nouvelle ? ' is-new' : ''}" data-id="${esc(a.id)}">
    <div class="abar" style="background:${BAR_COLOR[a.sev]}" aria-hidden="true"></div>
    <div class="a-body">
      <div class="a-type">${esc(a.type)}${nouvelle ? ` <span class="a-new">${t('Nouvelle')}</span>` : ''}</div>
      <div class="a-msg">${esc(a.msg)}</div>
      <div class="a-foot">
        <span class="a-time" title="${esc(exact)}">${esc(tempsRelatif(a.date))}</span>${a.capteur ? `<span class="a-capteur">${esc(a.capteur)}</span>` : ''}
        <span class="sev-badge ${SEV_CLASS[a.sev]}">${t(SEV_LABEL[a.sev])}</span>
        <div class="a-foot-meta">${lienJour}${lienDemande}${lienRegle}${lienReglage}${lu}</div>
      </div>
    </div>
  </article>`;
}

function renderAlertes() {
  const { status, alerts, filtre } = alertState;
  renderAlertSummary();
  renderSurvStrip();

  // pastilles de gravité / état, avec leur nombre
  filterBar.innerHTML = ALERT_FILTERS.map(([k, l]) => {
    const n = k === 'toutes' ? alerts.length : k === 'non-lues' ? alerts.filter(a => !a.read).length : alerts.filter(a => a.sev === k).length;
    return `<button class="fpill${filtre === k ? ' active' : ''}" type="button" data-filter="${k}" aria-pressed="${filtre === k}">${t(l)}${status === 'ok' ? ` (${n})` : ''}</button>`;
  }).join('');
  // types réellement présents
  const sel = $('al-type');
  if (sel) {
    const types = [...new Map(alerts.map(a => [a.rawType, a.type])).entries()];
    const html = `<option value="all">${t('Tous les types')}</option>` + types.map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join('');
    if (sel.__html !== html) { sel.innerHTML = html; sel.__html = html; }
    sel.value = alertState.type;
  }
  const maj = $('alert-maj');
  if (maj) {
    maj.className = 'alert-maj' + (alertState.majEchec ? ' err' : '');
    const derniere = alerts.length ? ` · ${t('dernière alerte')} ${tempsRelatif(alerts[0].date)}` : '';
    maj.textContent = alertState.majEchec ? t('Actualisation impossible, nouvel essai automatique…')
      : (alertState.derniereMaj ? `${t('Actualisé à')} ${pad2(alertState.derniereMaj.getHours())}:${pad2(alertState.derniereMaj.getMinutes())}${derniere}` : '');
  }

  let html;
  if (status === 'loading') {
    html = Array.from({ length: 3 }, () => '<div class="alert-item is-skel" aria-hidden="true"><div class="a-body"><div class="skel" style="width:30%;height:14px"></div><div class="skel" style="width:85%;height:12px;margin-top:8px"></div><div class="skel" style="width:40%;height:11px;margin-top:10px"></div></div></div>').join('');
  } else if (status === 'error') {
    html = `<div class="empty-state is-error"><div class="es-title">${t('Impossible de charger vos alertes')}</div><div class="es-sub">${t('Vos alertes existent toujours : seul leur affichage a échoué. Vérifiez votre connexion.')}</div><button type="button" class="es-btn" data-retry>${t('Réessayer')}</button></div>`;
  } else if (alerts.length === 0) {
    html = etatVide();
  } else {
    const liste = visibles();
    if (liste.length === 0) {
      html = `<div class="empty-state"><div class="es-title">${t('Aucune alerte pour ces filtres')}</div><div class="es-sub">${t('Essayez d’autres filtres : « Toutes » affiche l’historique complet.')}</div><button type="button" class="es-btn" data-reset-filtres>${t('Réinitialiser les filtres')}</button></div>`;
    } else {
      const montrees = liste.slice(0, alertState.limite);
      let jour = '';
      html = montrees.map(a => {
        const k = cleJour(a.date);
        const sep = k !== jour ? `<h3 class="day-sep">${esc(libelleJour(a.date))}</h3>` : '';
        jour = k;
        return sep + itemHtml(a);
      }).join('');
      if (liste.length > montrees.length) html += `<button type="button" class="more-btn" data-more>${t('Afficher plus')} (${liste.length - montrees.length} ${t('restantes')})</button>`;
    }
  }
  if (alertList.__html !== html) { alertList.innerHTML = html; alertList.__html = html; }
}

/* Marquer lue / non lue : optimiste MAIS honnête, on annule et on le dit si le serveur refuse */
function marquer(id, lue) {
  const avant = alertState.alerts.find(a => a.id === id);
  if (!avant) return;
  const ancien = avant.read;
  avant.read = lue;
  alertState.nouveaux.delete(id);
  renderAlertes();
  ecrituresEnCours++;
  fetchWithAuth(`/api/alertes/${id}/lire/`, { method: 'PATCH', body: JSON.stringify({ lue }) })
    .then(() => { showAlertFeedback(lue ? t('Alerte marquée comme lue.') : t('Alerte marquée comme non lue.')); })
    .catch(err => {
      console.error(err);
      avant.read = ancien;
      renderAlertes();
      showAlertFeedback(t('Échec : l’alerte n’a pas pu être modifiée. Réessayez.'), true);
    })
    .finally(() => { ecrituresEnCours--; syncShellBadges(); });
}

if (filterBar) filterBar.addEventListener('click', e => {
  const btn = e.target.closest('.fpill');
  if (!btn) return;
  alertState.filtre = btn.dataset.filter; alertState.limite = 50;
  renderAlertes();
  const nouveau = filterBar.querySelector(`[data-filter="${alertState.filtre}"]`);   // le clavier garde sa place
  if (nouveau) nouveau.focus();
});
const alSearch = $('al-search'), alType = $('al-type'), alPeriode = $('al-periode');
let rechercheTimer = null;
if (alSearch) alSearch.addEventListener('input', () => {
  clearTimeout(rechercheTimer);
  rechercheTimer = setTimeout(() => { alertState.q = alSearch.value; alertState.limite = 50; renderAlertes(); }, 180);
});
if (alType) alType.addEventListener('change', () => { alertState.type = alType.value; alertState.limite = 50; renderAlertes(); });
if (alPeriode) alPeriode.addEventListener('change', () => { alertState.periode = alPeriode.value; alertState.limite = 50; renderAlertes(); });
function reinitialiserFiltres() {
  Object.assign(alertState, { filtre: 'toutes', type: 'all', periode: 'tout', q: '', limite: 50 });
  if (alSearch) alSearch.value = ''; if (alPeriode) alPeriode.value = 'tout';
  renderAlertes();
}
if (alertList) alertList.addEventListener('click', e => {
  const lu = e.target.closest('.dismiss-btn, .undo-btn');
  if (lu) { marquer(lu.dataset.id, lu.dataset.lue === '1'); return; }
  const regle = e.target.closest('[data-regle]');
  if (regle) { ouvrirRegle(regle.dataset.regle); return; }
  const reglage = e.target.closest('[data-reglage]');
  if (reglage) { reglerOption(reglage.dataset.reglage); return; }
  if (e.target.closest('[data-retry]')) { alertState.status = 'loading'; renderAlertes(); chargerAlertes(); return; }
  if (e.target.closest('[data-reset-filtres]')) { reinitialiserFiltres(); return; }
  if (e.target.closest('[data-more]')) { alertState.limite += 50; renderAlertes(); return; }
  const act = e.target.closest('[data-act]');
  if (act) actionPage(act.dataset.act);
});
document.addEventListener('click', e => { const act = e.target.closest('#surv-strip [data-act]'); if (act) actionPage(act.dataset.act); });
/* « Voir les réglages » ouvre l'onglet ; 'creer' (règle avancée) ouvre directement la fenêtre de création. */
function actionPage(act) {
  if (act === 'panne') { window.location.href = '/interventions/?declarer=1&type=PANNE'; return; }
  if (act === 'creer') { creationEnAttente = true; if (currentTab !== 'config') setTab('config'); else loadConfigFromServer(); }
  else setTab('config');
}

if (markAllBtn) markAllBtn.addEventListener('click', () => {
  const nonLues = alertState.alerts.filter(a => !a.read);
  if (nonLues.length === 0) return;
  const ids = new Set(nonLues.map(a => a.id));
  nonLues.forEach(a => { a.read = true; alertState.nouveaux.delete(a.id); });
  renderAlertes();
  ecrituresEnCours++;
  fetchWithAuth('/api/alertes/tout-lire/', { method: 'POST' })
    .then(d => {
      const n = d && typeof d.count === 'number' ? d.count : ids.size;
      showAlertFeedback(`${n} ${n > 1 ? t('alertes marquées comme lues.') : t('alerte marquée comme lue.')}`);
    })
    .catch(err => {
      console.error(err);
      alertState.alerts.forEach(a => { if (ids.has(a.id)) a.read = false; });
      renderAlertes();
      showAlertFeedback(t('Échec : les alertes n’ont pas pu être marquées comme lues. Réessayez.'), true);
    })
    .finally(() => { ecrituresEnCours--; syncShellBadges(); });
});

// (les boutons « Configuration » d'en-tête, de note et de rail ont été supprimés : l'onglet Réglages suffit)

/* Chargement : liste + état de la surveillance. `silencieux` = actualisation automatique (rien ne clignote ; en cas
   d'échec on garde la liste affichée et on le dit sous la barre d'outils). */
let majEnCours = false;
function chargerAlertes(opts) {
  const silencieux = !!(opts && opts.silencieux);
  if (majEnCours) return Promise.resolve();
  majEnCours = true;
  return Promise.all([
    fetchWithAuth('/api/alertes/'),
    fetchWithAuth('/api/alertes/compteur/').catch(() => null),
  ]).then(([data, compteur]) => {
    const liste = window.AOCEDA.asList(data).map(mapApiAlert);
    if (alertState.status === 'ok') {
      const connues = new Set(alertState.alerts.map(a => a.id));
      const neuves = liste.filter(a => !connues.has(a.id));
      neuves.forEach(a => alertState.nouveaux.add(a.id));
      if (neuves.length) showAlertFeedback(`${neuves.length} ${neuves.length > 1 ? t('nouvelles alertes.') : t('nouvelle alerte.')}`);
    }
    alertState.alerts = liste;
    if (compteur && compteur.surveillance) alertState.surv = compteur.surveillance;
    alertState.status = 'ok';
    alertState.majEchec = false;
    alertState.derniereMaj = new Date();
    renderAlertes();
  }).catch(err => {
    console.error(err);
    if (silencieux && alertState.status === 'ok') { alertState.majEchec = true; renderAlertes(); }
    else { alertState.status = 'error'; renderAlertes(); }
  }).finally(() => { majEnCours = false; });
}

function initAlertes() {
  if (alertState.status !== 'ok') { alertState.status = 'loading'; }
  renderAlertes();
  chargerAlertes();
}
// Actualisation toutes les 30 s (page visible, onglet « Mes alertes ») ; et tout de suite quand le shell (qui relit
// le compteur toutes les 15 s) voit arriver une alerte que la liste n'a pas encore.
setInterval(() => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') chargerAlertes({ silencieux: true }); }, 30000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') chargerAlertes({ silencieux: true }); });
window.addEventListener('aoceda-alertes', e => {
  const d = e.detail;
  if (!d || currentTab !== 'alertes' || alertState.status !== 'ok') return;
  if (d.surveillance) { alertState.surv = d.surveillance; renderSurvStrip(); }
  if (ecrituresEnCours > 0) return;          // un marquage est en vol : le serveur n'a pas encore la dernière réponse
  const locales = alertState.alerts.filter(a => !a.read).length;
  if (Number(d.non_lues) > locales) chargerAlertes({ silencieux: true });
});
// Les « il y a 5 min » vieillissent : rafraîchis chaque minute
setInterval(() => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') { alertList.__html = ''; renderAlertes(); } }, 60000);

/* ════════════════ Onglet « Réglages » (refait le 19/10/2026) ════════════════
   Comme les réglages d'un téléphone : un interrupteur par alerte, des choix en quelques mots, AUCUN bouton « Enregistrer » :
   chaque changement part tout de suite au serveur (PUT partiel /api/users/me/), s'affiche tout de suite, et revient en arrière
   en le disant si l'enregistrement échoue. Les règles par capteur (en watts) sont rangées dans « Réglages avancés ».
   L'alarme sonore est un réglage de l'appareil (localStorage), pas du compte.
   ════════════════════════════════════════════════════════════ */
const CFG_DEFAUT = { depassement: true, niveau: 'normal', nuit: true, nuitDebut: '22:00', nuitFin: '06:00', tranche: true,
  credit: true, seuilCredit: 10000, email: true, absenceOn: false, absenceDate: '' };
const cfg = Object.assign({}, CFG_DEFAUT);
const cfgServer = { sensors: [], regles: [], isPrepaid: false, trancheOk: false, amperage: 10, email: '', rulesStatus: 'loading', prefsOk: false, charge: false };
const NIVEAUX = { prudent: 0.5, normal: 0.8, limite: 1 };
/* clé du réglage dans l'API ← valeur locale */
const CHAMP_API = { depassement: 'alerteDepassement', niveau: 'niveauDepassement', nuit: 'alerteNuit', tranche: 'alerteTranche',
  credit: 'alerteCredit', seuilCredit: 'seuilCreditBas_FCFA', email: 'notifEmail', absenceOn: 'modeAbsenceActif' };

const cfgStatus = $('cfg-status');
function setToggle(el, on) { if (!el) return; el.classList.toggle('on', on); el.setAttribute('aria-checked', on ? 'true' : 'false'); }
function sliderGradient(pct) { return `linear-gradient(to right,var(--ac) 0%,var(--ac) ${pct}%,var(--bd-d) ${pct}%,var(--bd-d) 100%)`; }
function alarmeActive() { try { return localStorage.getItem('aoceda-alarm-enabled') !== 'false'; } catch (e) { return true; } }
function hhmm(v) { return String(v || '').slice(0, 5); }

let statusTimer = null;
function dire(msg, type) {                    // type : '' | 'ok' | 'err' | 'wait'
  if (!cfgStatus) return;
  clearTimeout(statusTimer);
  cfgStatus.textContent = msg; cfgStatus.className = `cfg-status${type ? ' ' + type : ''}`;
  if (type === 'ok') statusTimer = setTimeout(() => { cfgStatus.textContent = ''; cfgStatus.className = 'cfg-status'; }, 3500);
}

function valeursRecommandees() {
  return { depassement: true, niveau: 'normal', nuit: true, nuitDebut: '22:00', nuitFin: '06:00', tranche: true, credit: true, seuilCredit: 10000 };
}

/* Une option : interrupteur + détail déplié seulement quand elle est active */
function majOption(kind, on, extra) {
  const bloc = $(`opt-${kind}`); if (!bloc) return;
  setToggle($(`opt-${kind}-tog`), on);
  const etat = $(`opt-${kind}-state`); if (etat) { etat.textContent = on ? t('Activée') : t('Désactivée'); etat.classList.toggle('on', on); }
  bloc.classList.toggle('is-on', on);
  const more = $(`opt-${kind}-more`); if (more) more.hidden = !(on && (extra !== false));
}
function majSeg(id, val) {
  const g = $(id); if (!g) return;
  g.querySelectorAll('button').forEach(b => { const a = b.dataset.val === String(val); b.classList.toggle('on', a); b.setAttribute('aria-checked', a ? 'true' : 'false'); b.tabIndex = a ? 0 : -1; });
}
function fmtNb(x, dec) { return Number(x).toLocaleString(LOCALE, { minimumFractionDigits: dec, maximumFractionDigits: dec }); }

function renderConfig() {
  const erreur = cfgServer.charge && !cfgServer.prefsOk;
  const err = $('cfg-error'); if (err) err.hidden = !erreur;
  const tab = $('tab-config'); if (tab) tab.classList.toggle('cfg-off', !cfgServer.prefsOk);
  majOption('depassement', cfg.depassement); majSeg('seg-niveau', cfg.niveau);
  const cap = (Number(cfgServer.amperage) || 0) * 220;
  const hint = $('niveau-hint');
  if (hint) hint.textContent = cap > 0
    ? `${t('Vous serez prévenu à partir d’environ')} ${nbFr(Math.round(cap * (NIVEAUX[cfg.niveau] || 0.8)))} W ${t('consommés en même temps (votre abonnement supporte')} ${nbFr(cap)} W).` : '';
  majOption('nuit', cfg.nuit);
  const d = $('sel-nuit-debut'), f = $('sel-nuit-fin');
  if (d && d.value !== cfg.nuitDebut) d.value = cfg.nuitDebut;
  if (f && f.value !== cfg.nuitFin) f.value = cfg.nuitFin;
  const tr = $('opt-tranche'); if (tr) tr.hidden = !cfgServer.trancheOk;
  majOption('tranche', cfg.tranche);
  const cr = $('opt-credit'); if (cr) cr.hidden = !cfgServer.isPrepaid;
  majOption('credit', cfg.credit); majSeg('seg-credit', cfg.seuilCredit);
  majOption('email', cfg.email);
  const ed = $('cfg-email-display'); if (ed) ed.textContent = cfgServer.email || '-';
  majOption('alarme', alarmeActive(), false);
  majOption('absence', cfg.absenceOn);
  const ad = $('cfg-absence-date');
  if (ad) { ad.min = cleJour(new Date()); if (ad.value !== (cfg.absenceDate || '')) ad.value = cfg.absenceDate || ''; }
  const reco = $('cfg-reco'); const r = valeursRecommandees();
  if (reco) reco.hidden = !cfgServer.prefsOk || Object.keys(r).every(k => cfg[k] === r[k]);
}

/* Enregistrement : une file d'attente (jamais deux PUT en même temps), retour en arrière si ça échoue */
let fileEcriture = Promise.resolve();
function changer(patch) {
  if (!cfgServer.prefsOk) return;
  const avant = {};
  Object.keys(patch).forEach(k => { avant[k] = cfg[k]; });
  Object.assign(cfg, patch); renderConfig();
  const body = {};
  Object.keys(patch).forEach(k => {
    if (k === 'nuitDebut') body.nuitDebut = `${patch[k]}:00`;
    else if (k === 'nuitFin') body.nuitFin = `${patch[k]}:00`;
    else if (k === 'absenceDate') body.absenceJusquau = patch[k] || null;
    else body[CHAMP_API[k]] = patch[k];
  });
  if ('absenceOn' in patch && !patch.absenceOn) { body.absenceJusquau = null; cfg.absenceDate = ''; }
  dire(t('Enregistrement…'), 'wait');
  fileEcriture = fileEcriture.then(() => fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify(body) }))
    .then(() => { dire(t('Enregistré ✓'), 'ok'); chargerAlertes({ silencieux: true }); })
    .catch(err => {
      console.error(err);
      Object.assign(cfg, avant); renderConfig();
      dire(`${t('Non enregistré')} (${messageErreur(err)}). ${t('Le réglage est revenu à son état précédent : réessayez.')}`, 'err');
    });
}

function bindSwitchOn(el, onToggle) {
  if (!el) return;
  el.addEventListener('click', onToggle);
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); onToggle(); } });
}
function lierInterrupteur(kind, action) {
  const el = $(`opt-${kind}-tog`); if (!el) return;
  el.addEventListener('click', action);
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); action(); } });
}
lierInterrupteur('depassement', () => changer({ depassement: !cfg.depassement }));
lierInterrupteur('nuit', () => changer({ nuit: !cfg.nuit }));
lierInterrupteur('tranche', () => changer({ tranche: !cfg.tranche }));
lierInterrupteur('credit', () => changer({ credit: !cfg.credit }));
lierInterrupteur('email', () => changer({ email: !cfg.email }));
lierInterrupteur('absence', () => changer({ absenceOn: !cfg.absenceOn }));
lierInterrupteur('alarme', () => {
  const on = !alarmeActive();
  try { localStorage.setItem('aoceda-alarm-enabled', String(on)); } catch (e) { /* ignore */ }
  renderConfig();
  dire(on ? t('Alarme sonore activée sur cet appareil.') : t('Alarme sonore coupée sur cet appareil.'), 'ok');
});
/* choix en quelques mots (boutons radio) */
function lierSeg(id, cle, conv) {
  const g = $(id); if (!g) return;
  g.addEventListener('click', e => { const b = e.target.closest('button[data-val]'); if (b && !b.classList.contains('on')) changer({ [cle]: conv(b.dataset.val) }); });
  g.addEventListener('keydown', e => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const bs = [...g.querySelectorAll('button')]; const i = bs.indexOf(document.activeElement); if (i < 0) return;
    e.preventDefault(); const n = bs[(i + (e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? bs.length - 1 : 1)) % bs.length]; n.focus(); n.click();
  });
}
lierSeg('seg-niveau', 'niveau', v => v);
lierSeg('seg-credit', 'seuilCredit', v => Number(v));
const selDebut = $('sel-nuit-debut'), selFin = $('sel-nuit-fin');
function changerNuit(cle, el) {
  const autre = cle === 'nuitDebut' ? cfg.nuitFin : cfg.nuitDebut;
  if (el.value === autre) { renderConfig(); dire(t('Le début et la fin de la nuit doivent être différents.'), 'err'); return; }
  changer({ [cle]: el.value });
}
if (selDebut) selDebut.addEventListener('change', () => changerNuit('nuitDebut', selDebut));
if (selFin) selFin.addEventListener('change', () => changerNuit('nuitFin', selFin));
const absDate = $('cfg-absence-date');
if (absDate) absDate.addEventListener('change', () => changer({ absenceDate: absDate.value }));
const recoBtn = $('cfg-reco');
if (recoBtn) recoBtn.addEventListener('click', () => changer(valeursRecommandees()));
const retryBtn = $('cfg-retry');
if (retryBtn) retryBtn.addEventListener('click', () => loadConfigFromServer());

// E-mail de test : pour vérifier QUE les alertes arriveront, sans créer de fausse alerte
const emailTestBtn = $('cfg-email-test'), emailTestMsg = $('cfg-email-test-msg');
if (emailTestBtn) emailTestBtn.addEventListener('click', () => {
  emailTestBtn.disabled = true;
  emailTestMsg.className = 'config-note-line'; emailTestMsg.textContent = t('Envoi…');
  fetchWithAuth('/api/alertes/test-email/', { method: 'POST' })
    .then(d => { emailTestMsg.textContent = `${t('E-mail de test envoyé à')} ${d && d.email ? d.email : ''}. ${t('Vérifiez aussi vos courriers indésirables.')}`; })
    .catch(err => { emailTestMsg.className = 'config-note-line err'; emailTestMsg.textContent = err.status === 429 ? t('Un e-mail de test vient d’être envoyé : patientez une minute.') : t('L’e-mail de test n’a pas pu être envoyé. Réessayez.'); })
    .finally(() => { setTimeout(() => { emailTestBtn.disabled = false; }, 4000); });
});

/* « Je change de tranche » (postpayé) : phrase simple et jauge, données réelles ; carte absente pour un prépayé */
function renderTranche(e) {
  cfgServer.trancheOk = !!(e && e.applicable);
  if (cfgServer.trancheOk) {
    const pct = e.seuil_kwh > 0 ? Math.min(100, (e.kwh / e.seuil_kwh) * 100) : 0;
    const barre = $('tr-barre');
    if (barre) { barre.style.width = `${pct}%`; barre.className = pct >= 100 ? 'depasse' : (pct >= e.alerte_pourcent ? 'proche' : ''); }
    const etat = $('tr-etat');
    if (etat) {
      let txt;
      if (e.kwh >= e.seuil_kwh) txt = `${t('Vous êtes déjà passé à la 2ᵉ tranche pour ces 2 mois : le kWh coûte')} ${fmtNb(e.prix_t2, 0)} F ${t('au lieu de')} ${fmtNb(e.prix_t1, 0)} F.`;
      else {
        txt = `${t('Vous avez utilisé')} <strong>${Math.round(pct)} %</strong> ${t('de votre 1ʳᵉ tranche (ces 2 mois-ci).')}`;
        if (e.jours_avant_seuil != null) txt += ` ${t('Au rythme actuel, le changement de prix arrive dans environ')} <strong>${Math.max(1, Math.round(e.jours_avant_seuil))} ${t('jour(s)')}</strong>.`;
        else txt += ` ${t('Il faut 3 journées complètes de mesures pour estimer la date.')}`;
      }
      etat.innerHTML = txt;
    }
    const ex = $('tr-explication');
    if (ex) ex.textContent = e.type_tarif === 'social'
      ? `${t('Votre facture a deux prix : le kWh coûte')} ${fmtNb(e.prix_t1, 0)} F ${t('jusqu’à')} ${fmtNb(e.seuil_kwh, 0)} kWh ${t('consommés en 2 mois (la 1ʳᵉ tranche), puis')} ${fmtNb(e.prix_t2, 0)} F ${t('au-delà (la 2ᵉ tranche). Cette alerte vous laisse le temps d’agir avant le changement de prix.')}`
      : `${t('Votre facture a deux prix : le kWh coûte')} ${fmtNb(e.prix_t1, 0)} F ${t('jusqu’à')} ${fmtNb(e.seuil_kwh, 0)} kWh ${t('consommés en 2 mois (la 1ʳᵉ tranche), puis')} ${fmtNb(e.prix_t2, 0)} F ${t('au-delà (la 2ᵉ tranche). Cette alerte vous prévient avant ce changement.')}`;
  }
  renderConfig();
}

/* « Mon crédit est presque fini » (prépayé) : crédit restant réel, si on peut le lire */
function renderCredit(sum) {
  const el = $('cr-etat'); if (!el) return;
  const c = sum && sum.credit_prepaye;
  if (!c || c.restant_fcfa == null) { el.textContent = ''; return; }
  el.innerHTML = `${t('Il vous reste')} <strong>${nbFr(Math.round(Number(c.restant_fcfa)))} FCFA</strong>${c.fin_estimee ? ` ${t('(fin estimée')} ${esc(String(c.fin_estimee).slice(0, 10).split('-').reverse().join('/'))})` : ''}.`;
}

/* Charge la configuration réelle. Chaque source échoue SÉPARÉMENT et le dit. */
let regleEnAttente = null;
let creationEnAttente = false;
let optionEnAttente = null;
function loadConfigFromServer() {
  cfgServer.rulesStatus = cfgServer.regles.length ? 'ok' : 'loading';
  renderRulesOverview();
  fetchWithAuth('/api/alertes/tranche/').then(renderTranche).catch(() => renderTranche(null));
  return Promise.allSettled([
    fetchWithAuth('/api/users/me/'), fetchWithAuth('/api/sensors/'), fetchWithAuth('/api/regles/'),
  ]).then(([me, sensors, regles]) => {
    cfgServer.sensorsOk = sensors.status === 'fulfilled';
    if (cfgServer.sensorsOk) cfgServer.sensors = window.AOCEDA.asList(sensors.value);
    if (regles.status === 'fulfilled') { cfgServer.regles = window.AOCEDA.asList(regles.value); cfgServer.rulesStatus = 'ok'; }
    else cfgServer.rulesStatus = 'error';
    cfgServer.prefsOk = me.status === 'fulfilled' && !!me.value;
    cfgServer.charge = true;
    if (cfgServer.prefsOk) {
      const m = me.value;
      cfgServer.isPrepaid = m.typeCompteur === 'prepaye';
      cfgServer.amperage = Number(m.amperage) || 10;
      cfgServer.email = m.email || '';
      const sc = Number(m.seuilCreditBas_FCFA);
      Object.assign(cfg, {
        depassement: m.alerteDepassement !== false, niveau: NIVEAUX[m.niveauDepassement] ? m.niveauDepassement : 'normal',
        nuit: m.alerteNuit !== false, nuitDebut: hhmm(m.nuitDebut) || '22:00', nuitFin: hhmm(m.nuitFin) || '06:00',
        tranche: m.alerteTranche !== false, credit: m.alerteCredit !== false,
        seuilCredit: (sc > 0) ? sc : CFG_DEFAUT.seuilCredit, email: m.notifEmail !== false,
        absenceOn: !!m.modeAbsenceActif, absenceDate: m.absenceJusquau || '',
      });
      if (cfgServer.isPrepaid) fetchWithAuth('/api/analytics/summary/').then(renderCredit).catch(() => renderCredit(null));
    }
    renderRulesOverview();
    renderConfig();
    if (creationEnAttente) { creationEnAttente = false; ouvrirAvance(); if (cfgServer.sensors.length) rmOpenCreate(); }
    if (regleEnAttente) {
      const id = regleEnAttente; regleEnAttente = null;
      ouvrirAvance();
      if (cfgServer.regles.some(r => String(r.id) === String(id))) rmOpenEdit(id);
      else showRulesFeedback(t('Cette règle n’existe plus.'), true);
    }
    if (optionEnAttente) { const k = optionEnAttente; optionEnAttente = null; surlignerOption(k); }
  });
}

function ouvrirAvance() { const a = $('adv'); if (a) a.open = true; }
/* Depuis une alerte : amène sur LE réglage concerné et le fait clignoter un instant */
function surlignerOption(kind) {
  const o = $(`opt-${kind}`); if (!o || o.hidden) return;
  o.scrollIntoView({ behavior: 'smooth', block: 'center' });
  o.classList.remove('flash'); void o.offsetWidth; o.classList.add('flash');
  setTimeout(() => o.classList.remove('flash'), 2400);
}
function reglerOption(kind) { optionEnAttente = kind; if (currentTab !== 'config') setTab('config'); else loadConfigFromServer(); }

/* Ouvre la modale d'une règle depuis n'importe où (lien « Modifier la règle » d'une alerte) */
function ouvrirRegle(id) {
  regleEnAttente = id;
  if (currentTab !== 'config') setTab('config'); else loadConfigFromServer();
}

let rulesFeedbackTimer = null;
function showRulesFeedback(msg, isError) {
  const el = $('rules-feedback');
  if (!el) return;
  el.textContent = msg;
  el.className = 'rules-feedback show' + (isError ? ' err' : '');
  clearTimeout(rulesFeedbackTimer);
  rulesFeedbackTimer = setTimeout(() => { el.className = 'rules-feedback'; el.textContent = ''; }, 6000);
}

/* ── Liste « Vos configurations d'alerte » : UNE ligne par configuration ── */
function renderRulesOverview() {
  const list = $('rules-list'), countEl = $('rules-count'), uncoveredEl = $('rules-uncovered'), createBtn = $('rules-create-btn');
  if (!list) return;
  const nbTot = cfgServer.sensors.length;
  const regles = cfgServer.regles;
  if (createBtn) createBtn.style.display = (nbTot === 0 || cfgServer.rulesStatus === 'error') ? 'none' : '';
  if (cfgServer.rulesStatus === 'loading' && !regles.length) {
    list.innerHTML = '<div class="rules-loading"><span class="skel" style="width:70%;height:14px"></span></div>';
    if (countEl) countEl.textContent = ''; if (uncoveredEl) uncoveredEl.textContent = '';
    return;
  }
  if (cfgServer.rulesStatus === 'error') {
    list.innerHTML = `<div class="rules-empty is-error">${t('Impossible de charger vos règles. Elles existent toujours : seul leur affichage a échoué.')} <button type="button" class="es-btn" id="rules-retry">${t('Réessayer')}</button></div>`;
    if (countEl) countEl.textContent = ''; if (uncoveredEl) uncoveredEl.textContent = '';
    const r = $('rules-retry'); if (r) r.addEventListener('click', () => loadConfigFromServer());
    return;
  }
  if (nbTot === 0) {
    list.innerHTML = `<div class="rules-empty">${t("Aucun capteur associé à votre compte pour le moment. Vos règles apparaîtront ici dès qu'un capteur sera installé par votre technicien.")}</div>`;
    if (countEl) countEl.textContent = ''; if (uncoveredEl) uncoveredEl.textContent = '';
    return;
  }
  if (regles.length === 0) {
    list.innerHTML = `<div class="rules-empty">${t('Aucune règle personnalisée : vos appareils suivent les réglages simples ci-dessus. Ajoutez une règle seulement pour un appareil précis.')}</div>`;
    if (countEl) countEl.textContent = t('0 règle');
  } else {
    if (countEl) countEl.textContent = `${regles.length} ${regles.length > 1 ? t('règles') : t('règle')}`;
    list.innerHTML = regles.map(r => {
      const capteurNom = r.capteur_nom || (cfgServer.sensors.find(s => String(s.id) === String(r.capteur)) || {}).nom || t('Capteur');
      const p = Math.round(Number(r.puissanceMax_W)) || 0;
      const actif = p > 0 && p < 100000;
      const seuilHtml = actif ? `<span class="rchip rc-on">${nbFr(p)} W</span>` : `<span class="rchip rc-off">${t('Désactivé')}</span>`;
      const nuitHtml = r.surveilleNuit
        ? `<span class="rchip rc-on">${esc(String(r['heureDébutNuit'] || '00:00').slice(0, 5).replace(':', 'h'))} – ${esc(String(r['heureFinNuit'] || '05:00').slice(0, 5).replace(':', 'h'))}</span>`
        : `<span class="rchip rc-off">${t('Désactivée')}</span>`;
      const nuitEff = Math.round(Number(r.seuilNuitEffectif_W)) || seuilNuitAuto(actif ? p : 100000);
      const nuitDeriveHtml = r.surveilleNuit ? `${nbFr(nuitEff)} W${r.seuilNuit_W == null ? ` (${t('auto')})` : ''}` : '-';
      const perso = r.nom && r.nom.trim() && r.nom.trim() !== 'Configuration';
      const titre = perso ? r.nom : capteurNom;       // un nom par défaut « Configuration » ×5 ne disait rien : on montre le capteur
      return `<div class="rule-row" role="button" tabindex="0" data-rule="${esc(String(r.id))}" aria-label="${t('Modifier la règle')} ${esc(titre)} (${esc(capteurNom)})">
        <span class="rule-capteur">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
          <span class="rule-config-txt"><span class="rule-config-nom">${esc(titre)}</span>${perso ? `<span class="rule-config-capteur">${esc(capteurNom)}</span>` : ''}</span>
        </span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Seuil puissance')}</span>${seuilHtml}</span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Surveillance nuit')}</span>${nuitHtml}</span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Seuil nuit')}</span><span class="rule-derive">${nuitDeriveHtml}</span></span>
        <span class="rule-go" aria-hidden="true"></span>
      </div>`;
    }).join('');
  }
  if (uncoveredEl) {
    const uncovered = cfgServer.sensors.filter(s => !regles.some(r => String(r.capteur) === String(s.id)));
    uncoveredEl.textContent = uncovered.length
      ? `${t('Suivent les réglages simples')} : ${uncovered.map(s => s.nom || t('Capteur')).join(', ')}.`
      : '';
  }
}

/* ════════════════ Modale d'édition d'une règle ════════════════ */
const rm = {
  overlay: $('rule-modal'), dialog: document.querySelector('.rm-dialog'), mode: $('rm-mode'), title: $('rm-capteur'), nom: $('rm-nom'),
  capteurSelect: $('rm-capteur-select'), puissanceToggle: $('rm-puissance-toggle'), puissanceGroup: $('rm-puissance-group'),
  puissanceRange: $('rm-puissance-range'), puissanceInput: $('rm-puissance-input'), capteurActuel: $('rm-capteur-actuel'),
  nuitSeuil: $('rm-nuit-seuil'), nuitAuto: $('rm-nuit-auto'), nuitToggle: $('rm-nuit-toggle'), nuitSub: $('rm-nuit-sub'),
  nuitDerive: $('rm-nuit-derive'), heureDebut: $('rm-heure-debut'), heureFin: $('rm-heure-fin'),
  foot: $('rm-foot'), delete: $('rm-delete'), cancel: $('rm-cancel'), save: $('rm-save'), close: $('rm-close'),
  confirm: $('rm-confirm'), confirmTxt: $('rm-confirm-txt'), confirmCancel: $('rm-confirm-cancel'), confirmDelete: $('rm-confirm-delete'),
  msg: $('rm-msg'), warn: $('rm-warn'),
};
const mstate = { ruleId: null, nom: '', sensorId: null, puissance: 2000, puissanceOn: true, nuitOn: true, nuitSeuil: null, heureDebut: '00:00', heureFin: '05:00' };
let rmInitial = '', rmOpener = null, rmConfirmMode = 'delete';
const rmSnapshot = () => JSON.stringify(mstate);

const PALIERS_W = (() => { const v = []; for (let w = 5; w <= 100; w += 5) v.push(w); for (let w = 110; w <= 500; w += 10) v.push(w); for (let w = 600; w <= 5000; w += 100) v.push(w); return v; })();
const SEUIL_MIN_W = 5, SEUIL_MAX_W = 5000;
function indexPalier(w) { let best = 0; PALIERS_W.forEach((p, i) => { if (Math.abs(p - w) < Math.abs(PALIERS_W[best] - w)) best = i; }); return best; }
/* Seuil de nuit automatique : même formule que le serveur (alerts.utils.seuil_nuit). */
function seuilNuitAuto(puissance) { return puissance >= 100000 ? 50 : Math.max(50, Math.round(puissance * 0.1)); }
function borner(v, min, max) { return Math.min(max, Math.max(min, Math.round(v))); }
const nomCapteurChoisi = () => (cfgServer.sensors.find(x => String(x.id) === String(mstate.sensorId)) || {}).nom || t('Capteur');

function rmCapteurActuel() {
  if (!rm.capteurActuel) return;
  const s = cfgServer.sensors.find(x => String(x.id) === String(mstate.sensorId));
  if (!s) { rm.capteurActuel.textContent = ''; return; }
  const w = s.puissanceActuelle;
  if (w === null || w === undefined) rm.capteurActuel.textContent = t('Consommation actuelle inconnue (aucune mesure récente).');
  else if (Number(w) === 0) rm.capteurActuel.innerHTML = `${t('En ce moment :')} <strong>${t('éteint')}</strong> (0 W)`;
  else rm.capteurActuel.innerHTML = `${t('En ce moment :')} <strong>${nbFr(w)} W</strong>`;
}
function rmTitleText() { return (mstate.nom || '').trim() || (mstate.ruleId ? t('Règle') : t('Nouvelle règle')); }

/* Cohérence de la règle : bloquant = on n'enregistre pas ; sinon simple avertissement affiché dans la modale */
function rmVerifier() {
  const bloquants = [], avertissements = [];
  if (!mstate.sensorId) bloquants.push(t('Choisissez un capteur à surveiller.'));
  if (!mstate.puissanceOn && !mstate.nuitOn) bloquants.push(t('Activez au moins une surveillance : le seuil de puissance ou la surveillance nocturne.'));
  if (mstate.nuitOn && mstate.heureDebut && mstate.heureDebut === mstate.heureFin) bloquants.push(t('La plage nocturne doit commencer et finir à deux heures différentes.'));
  if (mstate.puissanceOn && mstate.nuitOn) {
    const nuit = mstate.nuitSeuil == null ? seuilNuitAuto(mstate.puissance) : mstate.nuitSeuil;
    if (nuit >= mstate.puissance) avertissements.push(`${t('Le seuil de nuit')} (${nbFr(nuit)} W) ${t('est supérieur ou égal au seuil de puissance')} (${nbFr(mstate.puissance)} W) : ${t('seule l’alerte de puissance se déclenchera.')}`);
  }
  const doublon = cfgServer.regles.some(r => String(r.id) !== String(mstate.ruleId) && String(r.capteur) === String(mstate.sensorId)
    && (Math.round(Number(r.puissanceMax_W)) === (mstate.puissanceOn ? mstate.puissance : 100000)) && !!r.surveilleNuit === mstate.nuitOn);
  if (doublon) avertissements.push(t('Une règle identique existe déjà sur ce capteur.'));
  return { bloquants, avertissements };
}
function rmRender() {
  const idx = indexPalier(mstate.puissance);
  const pct = (idx / (PALIERS_W.length - 1)) * 100;
  if (rm.nom && document.activeElement !== rm.nom) rm.nom.value = mstate.nom;
  if (rm.capteurSelect) rm.capteurSelect.value = mstate.sensorId || '';
  if (rm.title) rm.title.textContent = rmTitleText();
  setToggle(rm.puissanceToggle, mstate.puissanceOn);
  rm.puissanceGroup.style.display = mstate.puissanceOn ? '' : 'none';
  rm.puissanceRange.max = PALIERS_W.length - 1;
  rm.puissanceRange.value = idx;
  rm.puissanceRange.style.background = sliderGradient(pct);
  if (document.activeElement !== rm.puissanceInput) rm.puissanceInput.value = mstate.puissance;
  rmCapteurActuel();
  setToggle(rm.nuitToggle, mstate.nuitOn);
  rm.nuitSub.style.display = mstate.nuitOn ? '' : 'none';
  const auto = seuilNuitAuto(mstate.puissanceOn ? mstate.puissance : 100000);
  const effectif = mstate.nuitSeuil == null ? auto : mstate.nuitSeuil;
  if (document.activeElement !== rm.nuitSeuil) rm.nuitSeuil.value = effectif;
  rm.nuitDerive.textContent = mstate.nuitSeuil == null ? t('(automatique)') : t('(choisi par vous)');
  if (rm.nuitAuto) rm.nuitAuto.hidden = mstate.nuitSeuil == null;
  if (document.activeElement !== rm.heureDebut) rm.heureDebut.value = mstate.heureDebut;
  if (document.activeElement !== rm.heureFin) rm.heureFin.value = mstate.heureFin;
  const v = rmVerifier();
  if (rm.warn) {
    const lignes = [...v.bloquants.map(x => `<span class="rm-w-block">${esc(x)}</span>`), ...v.avertissements.map(x => `<span class="rm-w-soft">${esc(x)}</span>`)];
    rm.warn.hidden = lignes.length === 0;
    rm.warn.innerHTML = lignes.join('<br>');
  }
  if (rm.save) rm.save.disabled = v.bloquants.length > 0;
}
function rmPopulateSensors() {
  if (!rm.capteurSelect) return;
  rm.capteurSelect.innerHTML = cfgServer.sensors.map(s => `<option value="${esc(String(s.id))}">${esc(s.nom || 'Capteur')}</option>`).join('');
}
function rmHideConfirm() { if (rm.confirm) rm.confirm.hidden = true; if (rm.foot) rm.foot.hidden = false; }
function rmShowConfirm(mode) {
  rmConfirmMode = mode;
  if (mode === 'discard') {
    rm.confirmTxt.textContent = t('Abandonner vos modifications ? Elles ne seront pas enregistrées.');
    rm.confirmCancel.textContent = t('Continuer l’édition');
    rm.confirmDelete.textContent = t('Abandonner');
  } else {
    rm.confirmTxt.textContent = t('Supprimer cette règle ? Elle cessera de surveiller ce capteur.');
    rm.confirmCancel.textContent = t('Annuler');
    rm.confirmDelete.textContent = t('Supprimer');
  }
  rm.confirm.hidden = false; rm.foot.hidden = true;
  try { rm.confirmCancel.focus(); } catch (e) { /* ignore */ }
}
function rmShow(isEdit, focusEl) {
  if (!rm.overlay) return;
  rmOpener = document.activeElement;
  rmPopulateSensors();
  rm.mode.textContent = isEdit ? t('Modifier la règle') : t('Nouvelle règle');
  rm.save.textContent = isEdit ? t('Enregistrer') : t('Créer la règle');
  rm.save.dataset.label = rm.save.textContent;
  rm.delete.style.display = isEdit ? '' : 'none';
  rmHideConfirm();
  rm.msg.textContent = ''; rm.msg.className = 'rm-msg';
  rmRender();
  rmInitial = rmSnapshot();
  rm.overlay.hidden = false;
  requestAnimationFrame(() => rm.overlay.classList.add('open'));
  document.body.classList.add('rm-lock');
  setTimeout(() => { try { (focusEl || rm.nom || rm.save).focus(); } catch (e) { /* ignore */ } }, 60);
}
function rmOpenEdit(ruleId) {
  const r = cfgServer.regles.find(x => String(x.id) === String(ruleId));
  if (!r || !rm.overlay) return;
  mstate.ruleId = r.id;
  mstate.nom = (r.nom && r.nom.trim() !== 'Configuration') ? r.nom : `${t('Surveillance')} ${(cfgServer.sensors.find(x => String(x.id) === String(r.capteur)) || {}).nom || ''}`.trim();
  mstate.sensorId = String(r.capteur);
  const p = Math.round(Number(r.puissanceMax_W)) || 0;
  mstate.puissanceOn = p > 0 && p < 100000;
  mstate.puissance = mstate.puissanceOn ? p : 2000;
  mstate.nuitOn = !!r.surveilleNuit;
  mstate.nuitSeuil = (r.seuilNuit_W == null) ? null : Math.round(Number(r.seuilNuit_W));
  mstate.heureDebut = String(r['heureDébutNuit'] || '00:00').slice(0, 5);
  mstate.heureFin = String(r['heureFinNuit'] || '05:00').slice(0, 5);
  rmShow(true);
}
function rmOpenCreate() {
  if (!rm.overlay || cfgServer.sensors.length === 0) return;
  mstate.ruleId = null;
  mstate.sensorId = String(cfgServer.sensors[0].id);
  mstate.nom = `${t('Surveillance')} ${nomCapteurChoisi()}`;     // un nom qui distingue la configuration (avant : « Configuration » partout)
  mstate.puissanceOn = true; mstate.puissance = 2000; mstate.nuitOn = true; mstate.nuitSeuil = null;
  mstate.heureDebut = '22:00'; mstate.heureFin = '05:00';
  rmShow(false, rm.nom);
}
function rmClose(force) {
  if (!rm.overlay || rm.overlay.hidden) return;
  if (!force && rmSnapshot() !== rmInitial) { rmShowConfirm('discard'); return; }
  rm.overlay.classList.remove('open');
  document.body.classList.remove('rm-lock');
  setTimeout(() => { rm.overlay.hidden = true; }, 200);
  try { if (rmOpener && rmOpener.focus) rmOpener.focus(); } catch (e) { /* ignore */ }
}
function rmSave() {
  const v = rmVerifier();
  if (v.bloquants.length) { rm.msg.textContent = v.bloquants[0]; rm.msg.className = 'rm-msg err'; return; }
  rm.save.disabled = true;
  const lbl = rm.save.dataset.label || rm.save.textContent;
  rm.save.textContent = t('Enregistrement…');
  const nom = (mstate.nom || '').trim() || `${t('Surveillance')} ${nomCapteurChoisi()}`;
  const hd = mstate.heureDebut.length === 5 ? mstate.heureDebut + ':00' : mstate.heureDebut;
  const hf = mstate.heureFin.length === 5 ? mstate.heureFin + ':00' : mstate.heureFin;
  const body = {
    nom, capteur: mstate.sensorId,
    puissanceMax_W: mstate.puissanceOn ? mstate.puissance : 100000,     // 100000 W = « désactivé » (aligné sur le serveur)
    surveilleNuit: mstate.nuitOn, seuilNuit_W: mstate.nuitSeuil, 'heureDébutNuit': hd, 'heureFinNuit': hf,
  };
  const wasCreate = !mstate.ruleId;
  const req = mstate.ruleId
    ? fetchWithAuth(`/api/regles/${mstate.ruleId}/`, { method: 'PUT', body: JSON.stringify(body) })
    : fetchWithAuth('/api/regles/', { method: 'POST', body: JSON.stringify(body) });
  req.then(() => {
    rmInitial = rmSnapshot();
    rmClose(true);
    showRulesFeedback(wasCreate ? `${t('Règle')} « ${nom} » ${t('créée.')}` : `${t('Règle')} « ${nom} » ${t('mise à jour.')}`, false);
    loadConfigFromServer();
    chargerAlertes({ silencieux: true });
  }).catch(err => {
    console.error(err);
    rm.msg.textContent = `${t('Échec de l’enregistrement')} : ${messageErreur(err)}`;
    rm.msg.className = 'rm-msg err';
  }).finally(() => { rm.save.textContent = lbl; rmRender(); });
}
function rmDelete() {
  if (!mstate.ruleId) { rmHideConfirm(); return; }
  rm.confirmDelete.disabled = true;
  rm.confirmDelete.textContent = t('Suppression…');
  const nom = (mstate.nom || '').trim() || t('Règle');
  fetchWithAuth(`/api/regles/${mstate.ruleId}/`, { method: 'DELETE' })
    .then(() => {
      rmInitial = rmSnapshot();
      rmClose(true);
      showRulesFeedback(`${t('Règle')} « ${nom} » ${t('supprimée.')}`, false);
      loadConfigFromServer();
      chargerAlertes({ silencieux: true });
    })
    .catch(err => {
      console.error(err);
      rmHideConfirm();
      rm.msg.textContent = `${t('Échec de la suppression')} : ${messageErreur(err)}`;
      rm.msg.className = 'rm-msg err';
    })
    .finally(() => { rm.confirmDelete.disabled = false; rm.confirmDelete.textContent = t('Supprimer'); });
}

if (rm.nom) rm.nom.addEventListener('input', e => { mstate.nom = e.target.value; if (rm.title) rm.title.textContent = rmTitleText(); });
if (rm.capteurSelect) rm.capteurSelect.addEventListener('change', e => { mstate.sensorId = e.target.value; rmRender(); });
bindSwitchOn(rm.puissanceToggle, () => { mstate.puissanceOn = !mstate.puissanceOn; rmRender(); });
bindSwitchOn(rm.nuitToggle, () => { mstate.nuitOn = !mstate.nuitOn; rmRender(); });
if (rm.puissanceRange) rm.puissanceRange.addEventListener('input', e => { mstate.puissance = PALIERS_W[+e.target.value] || SEUIL_MIN_W; rmRender(); });
if (rm.puissanceInput) {
  rm.puissanceInput.addEventListener('input', e => {
    const v = Number(e.target.value);
    if (Number.isFinite(v) && v >= SEUIL_MIN_W && v <= SEUIL_MAX_W) { mstate.puissance = Math.round(v); rmRender(); }
  });
  rm.puissanceInput.addEventListener('change', e => {
    const v = Number(e.target.value);
    mstate.puissance = borner(Number.isFinite(v) ? v : mstate.puissance, SEUIL_MIN_W, SEUIL_MAX_W);
    e.target.value = mstate.puissance; rmRender();
  });
}
if (rm.nuitSeuil) {
  rm.nuitSeuil.addEventListener('input', e => {
    const v = Number(e.target.value);
    if (Number.isFinite(v) && v >= 1 && v <= SEUIL_MAX_W) { mstate.nuitSeuil = Math.round(v); rmRender(); }
  });
  rm.nuitSeuil.addEventListener('change', e => {
    const v = Number(e.target.value);
    if (Number.isFinite(v) && v >= 1) mstate.nuitSeuil = borner(v, 1, SEUIL_MAX_W);
    e.target.value = mstate.nuitSeuil == null ? '' : mstate.nuitSeuil; rmRender();
  });
}
if (rm.nuitAuto) rm.nuitAuto.addEventListener('click', () => { mstate.nuitSeuil = null; rmRender(); });
if (rm.heureDebut) rm.heureDebut.addEventListener('change', e => { mstate.heureDebut = e.target.value; rmRender(); });
if (rm.heureFin) rm.heureFin.addEventListener('change', e => { mstate.heureFin = e.target.value; rmRender(); });
if (rm.save) rm.save.addEventListener('click', rmSave);
if (rm.close) rm.close.addEventListener('click', () => rmClose());
if (rm.delete) rm.delete.addEventListener('click', () => rmShowConfirm('delete'));
if (rm.confirmCancel) rm.confirmCancel.addEventListener('click', rmHideConfirm);
if (rm.confirmDelete) rm.confirmDelete.addEventListener('click', () => { if (rmConfirmMode === 'discard') { rmHideConfirm(); rmClose(true); } else rmDelete(); });
if (rm.overlay) rm.overlay.addEventListener('click', e => { if (e.target === rm.overlay) rmClose(); });
// Échap ferme (la croix aussi : plus de bouton « Annuler » en double) ; Tab reste DANS la fenêtre (focus piégé) ; le focus revient au bouton qui l'a ouverte
document.addEventListener('keydown', e => {
  if (!rm.overlay || rm.overlay.hidden) return;
  if (e.key === 'Escape') { rmClose(); return; }
  if (e.key !== 'Tab' || !rm.dialog) return;
  const f = [...rm.dialog.querySelectorAll('button, input, select, [tabindex]:not([tabindex="-1"]), a[href]')].filter(x => x.offsetParent !== null && !x.disabled);
  if (!f.length) return;
  const premier = f[0], dernier = f[f.length - 1];
  if (e.shiftKey && document.activeElement === premier) { e.preventDefault(); dernier.focus(); }
  else if (!e.shiftKey && document.activeElement === dernier) { e.preventDefault(); premier.focus(); }
});
const rulesCreateBtn = $('rules-create-btn');
if (rulesCreateBtn) rulesCreateBtn.addEventListener('click', () => rmOpenCreate());
const rulesListe = $('rules-list');
if (rulesListe) {
  rulesListe.addEventListener('click', e => { const l = e.target.closest('[data-rule]'); if (l) rmOpenEdit(l.dataset.rule); });
  rulesListe.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const l = e.target.closest('[data-rule]');
    if (l) { e.preventDefault(); rmOpenEdit(l.dataset.rule); }
  });
}

function initConfig() {
  renderConfig();
  loadConfigFromServer();
}

/* ════════════════ Démarrage ════════════════ */
applyTheme();
renderConfig();
(function lireLien() {
  const id = new URLSearchParams(window.location.search).get('regle');
  if (id && /^[0-9a-fA-F-]{32,36}$/.test(id)) { regleEnAttente = id; history.replaceState(null, '', window.location.pathname + '#config'); }
})();
setTab(regleEnAttente ? 'config' : hashToTab(window.location.hash), { fromHash: true });
