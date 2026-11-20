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
  alerts: [], surv: null, tarif: null, prixKwh: 0,
  filtre: 'toutes', type: 'all', capteur: 'all', periode: 'tout', q: '', limite: 50,
  nouveaux: new Set(), derniereMaj: null, majEchec: false,
};

/* Helpers FCFA (tarif réel CIE du client, aucune estimation inventée) */
function prixKwhActuel() {
  if (alertState.prixKwh > 0) return alertState.prixKwh;
  if (typeof cfgServer !== 'undefined' && Array.isArray(cfgServer.sensors)) {
    const s = cfgServer.sensors.find(x => x && Number(x.prixKwh_FCFA) > 0);
    if (s) return Number(s.prixKwh_FCFA);
  }
  return 0;
}
function parseNombreFr(str) {
  const n = Number(String(str || '').replace(/[\s\u00a0\u202f]/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : NaN;
}
function fmtFcfaParHeure(watts, prixKwh) {
  const f = (Number(watts) / 1000) * Number(prixKwh);
  if (!Number.isFinite(f) || f <= 0) return '0 FCFA/h';
  if (f < 1) return `${f.toLocaleString(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} FCFA/h`;
  return `${nbFr(Math.round(f))} FCFA/h`;
}
function traduireAlerteFcfa(a) {
  const msg = String(a.msg || '');
  const msgClean = a.capteur ? msg.split(a.capteur).join(' ') : msg;
  const prix = prixKwhActuel();
  // 1. Alerte déjà exprimée en FCFA (règle budget FCFA, crédit prépayé…)
  const mFcfa = msgClean.match(/(\d[\d\s\u00a0\u202f]*(?:[.,]\d+)?)\s*FCFA/i);
  if (mFcfa) {
    const v = parseNombreFr(mFcfa[1]);
    return { badge: Number.isFinite(v) ? `${nbFr(Math.round(v))} FCFA` : '', texteHtml: esc(msg), detailTech: '' };
  }
  // 2. Alerte de puissance (W) → traduite en rythme horaire FCFA/h selon le tarif CIE réel du client
  if ((a.rawType === 'DEPASSEMENT_SEUIL' || a.rawType === 'CONSOMMATION_NOCTURNE') && prix > 0) {
    const ws = [...msgClean.matchAll(/(\d[\d\s\u00a0\u202f]*(?:[.,]\d+)?)\s*W\b/gi)]
      .map(m => parseNombreFr(m[1])).filter(n => Number.isFinite(n) && n >= 0);
    if (ws.length >= 1) {
      const mesureW = ws[0], seuilW = ws.length >= 2 ? ws[1] : null;
      const coutH = fmtFcfaParHeure(mesureW, prix);
      const seuilH = seuilW ? fmtFcfaParHeure(seuilW, prix) : null;
      const texteHtml = a.rawType === 'CONSOMMATION_NOCTURNE'
        ? `${t('Consommation nocturne détectée à environ')} <strong>${esc(coutH)}</strong>${seuilH ? ` (${t('limite de nuit : env.')} ${esc(seuilH)})` : ''}.`
        : `${t('Consommation élevée détectée : environ')} <strong>${esc(coutH)}</strong>${seuilH ? ` (${t('au-dessus de la limite d’environ')} ${esc(seuilH)})` : ''}.`;
      const detailTech = `${t('Détail capteur :')} ${nbFr(Math.round(mesureW))} W${seuilW ? ` · ${t('limite')} ${nbFr(Math.round(seuilW))} W` : ''}`;
      return { badge: `≈ ${coutH}`, texteHtml, detailTech };
    }
  }
  // 3. Alerte de tranche (kWh) → traduite en montant cumulé FCFA
  if (String(a.rawType || '').indexOf('TRANCHE') === 0 && prix > 0) {
    const ks = [...msgClean.matchAll(/(\d[\d\s\u00a0\u202f]*(?:[.,]\d+)?)\s*kWh\b/gi)]
      .map(m => parseNombreFr(m[1])).filter(n => Number.isFinite(n) && n >= 0);
    if (ks.length >= 1) {
      const pT1 = (alertState.tarif && Number(alertState.tarif.prix_t1)) || prix;
      const consoF = Math.round(ks[0] * pT1);
      const seuilF = ks.length >= 2 ? Math.round(ks[1] * pT1) : null;
      const texteHtml = a.rawType === 'TRANCHE_FRANCHIE'
        ? `${t('Plafond de la 1ʳᵉ tranche dépassé : environ')} <strong>${nbFr(consoF)} FCFA</strong> ${t('consommés')}${seuilF ? ` (${t('plafond env.')} ${nbFr(seuilF)} FCFA)` : ''}.`
        : `${t('Vous approchez du changement de tranche : environ')} <strong>${nbFr(consoF)} FCFA</strong> ${t('consommés')}${seuilF ? ` ${t('sur un plafond d’environ')} ${nbFr(seuilF)} FCFA` : ''}.`;
      return { badge: `≈ ${nbFr(consoF)} FCFA`, texteHtml, detailTech: '' };
    }
  }
  return { badge: '', texteHtml: esc(msg), detailTech: '' };
}
const filterBar = $('filter-bar'), alertList = $('alert-list'), alertSummary = $('alert-summary');
const alertKpis = $('alert-kpis'), alRefreshBtn = $('al-refresh'), alClearBtn = $('al-clear');
const markAllBtn = $('mark-all-read'), tabAlertCount = $('tab-alert-count');

/* Sévérités lisibles : Urgent (Critique) | À surveiller (Avertissement) | Information. */
const SEV_LABEL = { crit: 'Urgent', warn: 'À surveiller', info: 'Information' };
const SEV_CLASS = { crit: 'sev-crit', warn: 'sev-warn', info: 'sev-info' };
const BAR_COLOR = { crit: 'var(--err)', warn: 'var(--warn)', info: 'var(--info)' };
const ALERT_FILTERS = [['toutes', 'Toutes'], ['non-lues', 'À traiter'], ['crit', 'Urgentes'], ['warn', 'À surveiller'], ['info', 'Infos']];
const TYPE_LABELS = {
  DEPASSEMENT_SEUIL: 'Un appareil a consommé trop',
  CONSOMMATION_NOCTURNE: 'Consommation inhabituelle la nuit',
  CREDIT_BAS: 'Crédit prépayé bientôt épuisé',
  TRANCHE_APPROCHE: 'Vous approchez de la 2ᵉ tranche',
  TRANCHE_FRANCHIE: 'Vous êtes passé en 2ᵉ tranche',
  INTERVENTION: 'Suivi de votre intervention',
};
const CONSEIL_PAR_TYPE = {
  DEPASSEMENT_SEUIL: 'Vérifiez les appareils allumés en même temps ou coupez cet appareil depuis le tableau de bord.',
  CONSOMMATION_NOCTURNE: 'Vérifiez qu’aucun appareil n’est resté allumé pendant la nuit ou ajustez vos horaires de nuit.',
  CREDIT_BAS: 'Achetez du crédit auprès de la CIE avant la coupure, puis notez votre compteur dans Facturation.',
  TRANCHE_APPROCHE: 'Limitez vos appareils les plus gourmands pour rester le plus longtemps possible en 1ʳᵉ tranche.',
  TRANCHE_FRANCHIE: 'La 2ᵉ tranche est atteinte pour ce bimestre : surveillez vos gros appareils jusqu’à la prochaine période.',
  INTERVENTION: 'Consultez l’avancement de votre demande dans la page Interventions.',
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
    type: TYPE_LABELS[raw] || a.type_display || raw.replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase()),
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

/* Badge du menu + cloche : mis à jour tout de suite, SANS appel réseau. */
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
  const { alerts, filtre, type, capteur, periode, q } = alertState;
  const duree = { '1j': 864e5, '7j': 7 * 864e5, '30j': 30 * 864e5 }[periode];
  const depuis = duree ? Date.now() - duree : 0;
  const mot = q.trim().toLowerCase();
  return alerts.filter(a =>
    (filtre === 'toutes' || (filtre === 'non-lues' ? !a.read : a.sev === filtre))
    && (type === 'all' || a.rawType === type)
    && (capteur === 'all' || (a.capteur || '') === capteur)
    && (!depuis || a.date.getTime() >= depuis)
    && (!mot || `${a.msg} ${a.type} ${a.capteur || ''} ${a.regleNom || ''}`.toLowerCase().includes(mot)));
}
const filtresActifs = () => alertState.filtre !== 'toutes' || alertState.type !== 'all' || alertState.capteur !== 'all' || alertState.periode !== 'tout' || alertState.q.trim() !== '';

function renderAlertSummary() {
  const a = alertState.alerts, ok = alertState.status === 'ok';
  const unread = a.filter(x => !x.read).length;
  const critAll = a.filter(x => x.sev === 'crit').length;
  const critUnread = a.filter(x => x.sev === 'crit' && !x.read).length;
  const recent7 = a.filter(x => (Date.now() - x.date.getTime()) <= 7 * 864e5).length;

  if (alertSummary) {
    if (!ok || a.length === 0) alertSummary.textContent = '';
    else if (unread === 0) alertSummary.textContent = `${t('Aucune alerte non lue')} · ${a.length} ${a.length > 1 ? t('alertes au total') : t('alerte au total')}`;
    else alertSummary.textContent = `${unread} ${unread > 1 ? t('alertes à traiter') : t('alerte à traiter')}`;
  }
  if (alertKpis) {
    if (!ok || a.length === 0) {
      alertKpis.hidden = true;
    } else {
      alertKpis.hidden = false;
      const f = alertState.filtre;
      const cards = [
        {
          k: 'non-lues', cls: 'is-unread', val: unread,
          lbl: unread > 1 ? t('Alertes à traiter') : t('Alerte à traiter'),
          sub: unread ? t('Cliquez pour voir les non lues') : t('Tout est lu, bravo'),
          ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
        },
        {
          k: 'crit', cls: 'is-crit', val: critAll,
          lbl: critAll > 1 ? t('Alertes urgentes') : t('Alerte urgente'),
          sub: critUnread ? `${critUnread} ${t('non lue')}${critUnread > 1 ? 's' : ''}` : (critAll ? t('Toutes déjà lues') : t('Aucune urgence')),
          ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        },
        {
          k: 'toutes', cls: 'is-all', val: a.length,
          lbl: a.length > 1 ? t('Alertes au total') : t('Alerte au total'),
          sub: recent7 ? `${recent7} ${t('ces 7 derniers jours')}` : t('Historique complet'),
          ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        },
      ];
      alertKpis.innerHTML = cards.map(c =>
        `<button type="button" class="al-kpi ${c.cls}${f === c.k ? ' active' : ''}" data-kpi-filter="${c.k}" aria-pressed="${f === c.k}">
          <span class="al-kpi-ico" aria-hidden="true">${c.ico}</span>
          <span class="al-kpi-txt">
            <span class="al-kpi-val">${c.val}</span>
            <span class="al-kpi-lbl">${esc(c.lbl)}</span>
            <span class="al-kpi-sub">${esc(c.sub)}</span>
          </span>
        </button>`
      ).join('');
    }
  }
  if (markAllBtn) markAllBtn.hidden = !ok || unread === 0;
  if (tabAlertCount) { tabAlertCount.textContent = String(unread); tabAlertCount.style.display = ok && unread > 0 ? '' : 'none'; }
  if (ok) majBadgesLocaux();
}

/* Ce que la surveillance fait RÉELLEMENT. */
function diagnosticSurveillance() {
  const s = alertState.surv;
  if (!s) return null;
  const dernier = s.dernier_contact ? new Date(s.dernier_contact) : null;
  if (s.capteurs === 0) return { niveau: 'warn', titre: t('Aucun capteur installé'), texte: t('Rien n’est surveillé tant qu’aucun capteur n’est installé par votre technicien.') };
  if (s.regles === 0 && !s.reglage_simple) return { niveau: 'warn', titre: t('Aucune alerte activée'), texte: t('Vos appareils ne sont pas surveillés : activez une alerte dans les réglages.'), action: 'reglages' };
  if (!s.en_ligne) {
    return {
      niveau: 'warn', titre: t('Boîtier hors ligne'), texte: dernier
        ? `${t('Aucune mesure reçue depuis')} ${tempsRelatif(dernier).replace(t('il y a') + ' ', '')} : ${t('rien n’est surveillé en ce moment.')}`
        : t('Le boîtier n’a encore jamais envoyé de mesure : rien n’est surveillé pour l’instant.'), action: 'panne'
    };
  }
  if (s.capteurs_surveilles < s.capteurs) {
    const n = s.capteurs - s.capteurs_surveilles;
    return { niveau: 'info', titre: `${n} ${n > 1 ? t('capteurs ne sont pas surveillés') : t('capteur n’est pas surveillé')}`, texte: t('Activez une alerte de consommation dans les réglages pour le surveiller aussi.'), action: 'reglages' };
  }
  if (s.absence_active) {
    return { niveau: 'info', titre: t('Mode absence actif'), texte: `${t('La surveillance nocturne est suspendue')}${s.absence_jusquau ? ` ${t('jusqu’au')} ${new Date(s.absence_jusquau + 'T00:00:00').toLocaleDateString(LOCALE, { day: 'numeric', month: 'long' })}` : ''}. ${t('Le seuil de puissance et le crédit restent surveillés.')}`, action: 'reglages' };
  }
  return {
    niveau: 'ok', live: true, titre: t('Surveillance active en direct'),
    texte: `${s.capteurs} ${s.capteurs > 1 ? t('appareils surveillés') : t('appareil surveillé')}${dernier ? ` · ${t('dernière mesure')} ${tempsRelatif(dernier)}` : ''}.`
  };
}
function renderSurvStrip() {
  const el = $('surv-strip');
  if (!el) return;
  const d = diagnosticSurveillance();
  if (!d) { el.hidden = true; return; }
  el.hidden = false;
  el.className = `surv-strip is-${d.niveau}`;
  const ico = d.live
    ? '<span class="surv-pulse" aria-hidden="true"></span>'
    : (d.niveau === 'ok'
      ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>');
  el.innerHTML = `<span class="surv-ico">${ico}</span><span class="surv-txt"><strong>${esc(d.titre)}</strong> · ${esc(d.texte)}</span>`
    + (d.action ? `<button type="button" class="surv-btn" data-act="${d.action}">${d.action === 'panne' ? t('Déclarer une panne') : t('Voir les réglages')}</button>` : '');
}

function etatVide() {
  const d = diagnosticSurveillance();
  const svg = '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';
  if (d && d.niveau === 'ok') {
    return `<div class="empty-state">${svg}<div class="es-title">${t('Aucune alerte, tout va bien')}</div><div class="es-sub">${esc(d.texte)} ${t('Les nouvelles alertes apparaîtront ici automatiquement.')}</div></div>`;
  }
  return `<div class="empty-state">${svg}<div class="es-title">${t('Aucune alerte pour le moment')}</div><div class="es-sub">${t('Les alertes apparaîtront ici dès qu’un de vos réglages se déclenchera.')}</div></div>`;
}

function itemHtml(a) {
  const nouvelle = alertState.nouveaux.has(a.id);
  const exact = a.date.toLocaleString(LOCALE, { dateStyle: 'full', timeStyle: 'short' });
  const fcfa = traduireAlerteFcfa(a);
  const conseil = !a.read && CONSEIL_PAR_TYPE[a.rawType] ? t(CONSEIL_PAR_TYPE[a.rawType]) : '';
  const lienAppareil = a.capteurId ? `<a class="a-link a-link--act" href="/dashboard/">${t('Gérer l’appareil')}</a>` : '';
  const lienJour = a.capteurId
    ? `<a class="a-link" href="/historique/?jour=${cleJour(a.date)}&capteur=${encodeURIComponent(a.capteurId)}">${t('Voir ce jour')}</a>`
    : (a.rawType === 'CREDIT_BAS' || a.rawType.indexOf('TRANCHE') === 0 ? `<a class="a-link a-link--act" href="/previsions/">${t('Voir ma facture')}</a>` : '');
  const lienDemande = a.interventionId ? `<a class="a-link a-link--act" href="/interventions/?ouvrir=${encodeURIComponent(a.interventionId)}">${t('Voir ma demande')}</a>` : '';
  const lienRegle = a.regleId ? `<button class="a-link" type="button" data-regle="${esc(a.regleId)}" title="${esc(a.regleNom || '')}">${t('Modifier la règle')}</button>` : '';
  const optKind = a.regleId ? '' : ({ DEPASSEMENT_SEUIL: 'depassement', CONSOMMATION_NOCTURNE: 'nuit', CREDIT_BAS: 'credit' }[a.rawType] || (String(a.rawType).indexOf('TRANCHE') === 0 ? 'tranche' : ''));
  const lienReglage = optKind ? `<button class="a-link" type="button" data-reglage="${optKind}">${t('Régler cette alerte')}</button>` : '';
  const lu = a.read
    ? `<button class="undo-btn" type="button" data-id="${esc(a.id)}" data-lue="0" title="${t('Marquer comme non lue')}" aria-label="${t('Marquer cette alerte comme non lue')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 9 8 9"/></svg></button>`
    : `<button class="dismiss-btn" type="button" data-id="${esc(a.id)}" data-lue="1" aria-label="${t('Marquer cette alerte comme lue')}">&#10003; ${t('Marquer lue')}</button>`;
  return `<article class="alert-item${a.read ? ' dismissed' : ' is-unread'}${nouvelle ? ' is-new' : ''}" data-id="${esc(a.id)}">
    <div class="abar" style="background:${BAR_COLOR[a.sev]}" aria-hidden="true"></div>
    <div class="a-body">
      <div class="a-head">
        <div class="a-type">${esc(a.type)}${nouvelle ? ` <span class="a-new">${t('Nouvelle')}</span>` : ''}</div>
        <div class="a-head-badges">
          ${fcfa.badge ? `<span class="a-fcfa">${esc(fcfa.badge)}</span>` : ''}
          ${a.capteur ? `<span class="a-capteur">${esc(a.capteur)}</span>` : ''}
          <span class="sev-badge ${SEV_CLASS[a.sev]}">${t(SEV_LABEL[a.sev])}</span>
        </div>
      </div>
      <div class="a-msg">${fcfa.texteHtml}</div>
      ${fcfa.detailTech ? `<div class="a-tech">${esc(fcfa.detailTech)}</div>` : ''}
      ${conseil ? `<div class="a-guide"><strong>${t('Que faire ?')}</strong> ${esc(conseil)}</div>` : ''}
      <div class="a-foot">
        <span class="a-time" title="${esc(exact)}">${esc(tempsRelatif(a.date))}</span>
        <div class="a-foot-meta">${lienAppareil}${lienJour}${lienDemande}${lienRegle}${lienReglage}${lu}</div>
      </div>
    </div>
  </article>`;
}

function renderAlertes() {
  const { status, alerts, filtre } = alertState;
  renderAlertSummary();
  renderSurvStrip();

  // Pastilles de filtre : cachées quand les 3 cartes KPI suffisent (zéro doublon), affichées uniquement si warn/info existent
  const aAutresGravites = alerts.some(a => a.sev === 'warn' || a.sev === 'info') || filtre === 'warn' || filtre === 'info';
  if (filterBar) {
    filterBar.hidden = !(status === 'ok' && aAutresGravites);
    if (!filterBar.hidden) {
      filterBar.innerHTML = ALERT_FILTERS.map(([k, l]) => {
        const n = k === 'toutes' ? alerts.length : k === 'non-lues' ? alerts.filter(a => !a.read).length : alerts.filter(a => a.sev === k).length;
        if (status === 'ok' && k !== 'toutes' && k !== 'non-lues' && n === 0 && filtre !== k) return '';
        return `<button class="fpill${filtre === k ? ' active' : ''}" type="button" data-filter="${k}" aria-pressed="${filtre === k}">${t(l)}${status === 'ok' ? ` <span class="fpill-n">${n}</span>` : ''}</button>`;
      }).join('');
    }
  }

  // Champs de recherche/période masqués quand il n'y a aucune alerte (laisse seulement Actualiser + horodatage)
  const sansAlerte = status === 'ok' && alerts.length === 0;
  const searchInput = $('al-search'), periodeSel = $('al-periode');
  if (searchInput) searchInput.hidden = sansAlerte;
  if (periodeSel) periodeSel.hidden = sansAlerte;

  // Filtre par appareil (visible dès que ≥ 2 appareils distincts apparaissent dans les alertes)
  const selCap = $('al-capteur');
  if (selCap) {
    const caps = [...new Set(alerts.map(a => a.capteur).filter(Boolean))];
    if (caps.length >= 2) {
      const html = `<option value="all">${t('Tous les appareils')}</option>` + caps.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      if (selCap.__html !== html) { selCap.innerHTML = html; selCap.__html = html; }
      selCap.hidden = false;
      selCap.value = caps.includes(alertState.capteur) ? alertState.capteur : 'all';
    } else {
      selCap.hidden = true;
      alertState.capteur = 'all';
    }
  }
  // Types réellement présents
  const sel = $('al-type');
  if (sel) {
    const types = [...new Map(alerts.map(a => [a.rawType, a.type])).entries()];
    if (types.length >= 2) {
      const html = `<option value="all">${t('Tous les types')}</option>` + types.map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join('');
      if (sel.__html !== html) { sel.innerHTML = html; sel.__html = html; }
      sel.hidden = false;
      sel.value = alertState.type;
    } else {
      sel.hidden = true;
      alertState.type = 'all';
    }
  }
  if (alClearBtn) alClearBtn.hidden = !filtresActifs();

  const maj = $('alert-maj');
  if (maj) {
    maj.className = 'alert-maj' + (alertState.majEchec ? ' err' : '');
    const derniere = alerts.length ? ` · ${t('dernière')} ${tempsRelatif(alerts[0].date)}` : '';
    maj.textContent = alertState.majEchec ? t('Actualisation impossible, nouvel essai automatique…')
      : (alertState.derniereMaj ? `${t('À jour')} ${pad2(alertState.derniereMaj.getHours())}:${pad2(alertState.derniereMaj.getMinutes())}${derniere}` : '');
  }

  let html;
  if (status === 'loading') {
    html = Array.from({ length: 3 }, () => '<div class="alert-item is-skel" aria-hidden="true"><div class="a-body"><div class="skel" style="width:35%;height:15px"></div><div class="skel" style="width:85%;height:12px;margin-top:8px"></div><div class="skel" style="width:55%;height:11px;margin-top:10px"></div></div></div>').join('');
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
    .then(() => { showAlertFeedback(lue ? t('Alerte marquée comme lue.') : t('Alerte remise en non lue.')); })
    .catch(err => {
      console.error(err);
      avant.read = ancien;
      renderAlertes();
      showAlertFeedback(t('Échec : l’alerte n’a pas pu être modifiée. Réessayez.'), true);
    })
    .finally(() => { ecrituresEnCours--; syncShellBadges(); });
}

if (alertKpis) alertKpis.addEventListener('click', e => {
  const btn = e.target.closest('[data-kpi-filter]');
  if (!btn) return;
  const cible = btn.dataset.kpiFilter;
  alertState.filtre = (alertState.filtre === cible && cible !== 'toutes') ? 'toutes' : cible;
  alertState.limite = 50;
  renderAlertes();
});
if (filterBar) filterBar.addEventListener('click', e => {
  const btn = e.target.closest('.fpill');
  if (!btn) return;
  alertState.filtre = btn.dataset.filter; alertState.limite = 50;
  renderAlertes();
  const nouveau = filterBar.querySelector(`[data-filter="${alertState.filtre}"]`);   // le clavier garde sa place
  if (nouveau) nouveau.focus();
});
const alSearch = $('al-search'), alType = $('al-type'), alCapteur = $('al-capteur'), alPeriode = $('al-periode');
let rechercheTimer = null;
if (alSearch) alSearch.addEventListener('input', () => {
  clearTimeout(rechercheTimer);
  rechercheTimer = setTimeout(() => { alertState.q = alSearch.value; alertState.limite = 50; renderAlertes(); }, 180);
});
if (alType) alType.addEventListener('change', () => { alertState.type = alType.value; alertState.limite = 50; renderAlertes(); });
if (alCapteur) alCapteur.addEventListener('change', () => { alertState.capteur = alCapteur.value; alertState.limite = 50; renderAlertes(); });
if (alPeriode) alPeriode.addEventListener('change', () => { alertState.periode = alPeriode.value; alertState.limite = 50; renderAlertes(); });
if (alClearBtn) alClearBtn.addEventListener('click', reinitialiserFiltres);
if (alRefreshBtn) alRefreshBtn.addEventListener('click', () => {
  alRefreshBtn.classList.add('is-spinning');
  chargerAlertes({ silencieux: true, manuel: true }).finally(() => {
    setTimeout(() => alRefreshBtn.classList.remove('is-spinning'), 350);
  });
});
function reinitialiserFiltres() {
  Object.assign(alertState, { filtre: 'toutes', type: 'all', capteur: 'all', periode: 'tout', q: '', limite: 50 });
  if (alSearch) alSearch.value = ''; if (alPeriode) alPeriode.value = 'tout';
  if (alCapteur) alCapteur.value = 'all'; if (alType) alType.value = 'all';
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

/* Chargement : liste + état de la surveillance + tarif CIE réel (pour conversion FCFA). */
let majEnCours = false;
function chargerTarifSiBesoin() {
  if (alertState.tarif) return Promise.resolve(alertState.tarif);
  return fetchWithAuth('/api/analytics/tarif/').then(tr => {
    if (tr && Number(tr.prix_kwh) > 0) {
      alertState.tarif = tr;
      alertState.prixKwh = Number(tr.prix_kwh);
    }
    return alertState.tarif;
  }).catch(() => null);
}
function chargerAlertes(opts) {
  const silencieux = !!(opts && opts.silencieux);
  const manuel = !!(opts && opts.manuel);
  if (majEnCours) return Promise.resolve();
  majEnCours = true;
  return Promise.all([
    fetchWithAuth('/api/alertes/'),
    fetchWithAuth('/api/alertes/compteur/').catch(() => null),
    chargerTarifSiBesoin(),
  ]).then(([data, compteur]) => {
    const liste = window.AOCEDA.asList(data).map(mapApiAlert);
    let nbNeuves = 0;
    if (alertState.status === 'ok') {
      const connues = new Set(alertState.alerts.map(a => a.id));
      const neuves = liste.filter(a => !connues.has(a.id));
      nbNeuves = neuves.length;
      neuves.forEach(a => alertState.nouveaux.add(a.id));
      if (nbNeuves) showAlertFeedback(`${nbNeuves} ${nbNeuves > 1 ? t('nouvelles alertes.') : t('nouvelle alerte.')}`);
      else if (manuel) showAlertFeedback(t('Liste à jour, aucune nouvelle alerte.'));
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
// Actualisation dynamique toutes les 15 s (page visible, onglet « Mes alertes ») + instantanée sur événement shell.
setInterval(() => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') chargerAlertes({ silencieux: true }); }, 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') chargerAlertes({ silencieux: true }); });
window.addEventListener('aoceda-alertes', e => {
  const d = e.detail;
  if (!d || currentTab !== 'alertes' || alertState.status !== 'ok') return;
  if (d.surveillance) { alertState.surv = d.surveillance; renderSurvStrip(); }
  if (ecrituresEnCours > 0) return;
  const locales = alertState.alerts.filter(a => !a.read).length;
  if (Number(d.non_lues) !== locales) chargerAlertes({ silencieux: true });
});
// Les « il y a 5 min » vieillissent : rafraîchis chaque minute
setInterval(() => { if (!document.hidden && currentTab === 'alertes' && alertState.status === 'ok') { alertList.__html = ''; renderAlertes(); } }, 60000);

/* ════════════════ Onglet « Réglages » (refait le 19/10/2026) ════════════════
   Comme les réglages d'un téléphone : un interrupteur par alerte, des choix en quelques mots, AUCUN bouton « Enregistrer » :
   chaque changement part tout de suite au serveur (PUT partiel /api/users/me/), s'affiche tout de suite, et revient en arrière
   en le disant si l'enregistrement échoue. Les règles par capteur (en watts) sont rangées dans « Réglages avancés ».
   L'alarme sonore est un réglage de l'appareil (localStorage), pas du compte.
   ════════════════════════════════════════════════════════════ */
const CFG_DEFAUT = {
  depassement: true, niveau: 'normal', nuit: true, nuitDebut: '22:00', nuitFin: '06:00', tranche: true,
  credit: true, seuilCredit: 10000, email: true, absenceOn: false, absenceDate: ''
};
const cfg = Object.assign({}, CFG_DEFAUT);
const cfgServer = { sensors: [], regles: [], isPrepaid: false, trancheOk: false, amperage: 10, email: '', rulesStatus: 'loading', prefsOk: false, charge: false };
const NIVEAUX = { prudent: 0.5, normal: 0.8, limite: 1 };
/* clé du réglage dans l'API ← valeur locale */
const CHAMP_API = {
  depassement: 'alerteDepassement', niveau: 'niveauDepassement', nuit: 'alerteNuit', tranche: 'alerteTranche',
  credit: 'alerteCredit', seuilCredit: 'seuilCreditBas_FCFA', email: 'notifEmail', absenceOn: 'modeAbsenceActif'
};

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
  const prix = prixKwhActuel();
  Object.keys(NIVEAUX).forEach(k => {
    const el = $(`niv-sub-${k}`);
    if (!el) return;
    if (cap > 0 && prix > 0) el.textContent = `≈ ${fmtFcfaParHeure(cap * NIVEAUX[k], prix)}`;
    else if (cap > 0) el.textContent = `${nbFr(Math.round(cap * NIVEAUX[k]))} W`;
    else el.textContent = '';
  });
  const hint = $('niveau-hint');
  if (hint) {
    const seuilW = Math.round(cap * (NIVEAUX[cfg.niveau] || 0.8));
    if (cap > 0 && prix > 0) {
      hint.innerHTML = `${t('Vous serez prévenu dès environ')} <strong>${esc(fmtFcfaParHeure(seuilW, prix))}</strong> ${t('consommés en même temps')} <span class="opt-hint-tech">(${nbFr(seuilW)} W · ${t('max abonnement : env.')} ${esc(fmtFcfaParHeure(cap, prix))})</span>.`;
    } else if (cap > 0) {
      hint.textContent = `${t('Vous serez prévenu à partir d’environ')} ${nbFr(seuilW)} W ${t('consommés en même temps (votre abonnement supporte')} ${nbFr(cap)} W).`;
    } else {
      hint.textContent = '';
    }
  }
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

/* « Changement de tranche » (postpayé) : exprimé en Francs CFA + jauge claire ; masqué pour un prépayé */
function renderTranche(e) {
  cfgServer.trancheData = e || null;
  cfgServer.trancheOk = !!(e && e.applicable);
  if (cfgServer.trancheOk) {
    const pct = e.seuil_kwh > 0 ? Math.min(100, (e.kwh / e.seuil_kwh) * 100) : 0;
    const barre = $('tr-barre');
    if (barre) { barre.style.width = `${pct}%`; barre.className = pct >= 100 ? 'depasse' : (pct >= e.alerte_pourcent ? 'proche' : ''); }
    const pT1 = (alertState.tarif && Number(alertState.tarif.prix_t1)) || Number(e.prix_t1) || 0;
    const pT2 = (alertState.tarif && Number(alertState.tarif.prix_t2)) || Number(e.prix_t2) || 0;
    const consoFcfa = Math.round(Number(e.kwh || 0) * pT1);
    const plafondFcfa = Math.round(Number(e.seuil_kwh || 0) * pT1);
    const resteFcfa = Math.max(0, plafondFcfa - consoFcfa);
    const etat = $('tr-etat');
    if (etat) {
      let txt;
      if (e.kwh >= e.seuil_kwh) {
        txt = `${t('Vous êtes en 2ᵉ tranche pour ces 2 mois : environ')} <strong>${nbFr(consoFcfa)} FCFA</strong> ${t('consommés (plafond 1ʳᵉ tranche : env.')} ${nbFr(plafondFcfa)} FCFA).`;
      } else {
        txt = `${t('1ʳᵉ tranche utilisée à')} <strong>${Math.round(pct)} %</strong> · ${t('environ')} <strong>${nbFr(consoFcfa)} FCFA</strong> / ${nbFr(plafondFcfa)} FCFA (${t('reste env.')} ${nbFr(resteFcfa)} FCFA).`;
        if (e.jours_avant_seuil != null) txt += ` ${t('Changement de tarif estimé dans')} <strong>${Math.max(1, Math.round(e.jours_avant_seuil))} ${t('jour(s)')}</strong>.`;
        else txt += ` ${t('Il faut 3 journées complètes de mesures pour estimer la date.')}`;
      }
      etat.innerHTML = txt;
    }
    const ex = $('tr-explication');
    if (ex) {
      ex.textContent = `${t('Votre facture CIE sur 2 mois change de tarif après environ')} ${nbFr(plafondFcfa)} FCFA ${t('de consommation (1ʳᵉ tranche à')} ${fmtNb(pT1, 0)} FCFA, ${t('puis 2ᵉ tranche à')} ${fmtNb(pT2, 0)} FCFA). ${t('Cette alerte vous prévient avant ce changement.')}`;
    }
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
  return Promise.allSettled([
    fetchWithAuth('/api/users/me/'), fetchWithAuth('/api/sensors/'), fetchWithAuth('/api/regles/'),
    chargerTarifSiBesoin(), fetchWithAuth('/api/alertes/tranche/'),
  ]).then(([me, sensors, regles, _tarif, tranche]) => {
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
    renderTranche(tranche.status === 'fulfilled' ? tranche.value : null);
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

const GLOBAL_VALUE = '__global__';

/* Résumé de la consommation de chaque appareil et du total combiné (en W et en FCFA) */
function resumeAppareils() {
  const sensors = cfgServer.sensors || [];
  let totalW = 0, auMoinsUneMesureW = false, totalFcfa = 0, prixKwh = 0;
  const lignes = sensors.map(s => {
    const w = s.puissanceActuelle;
    const fcfa = s.coutActuel_FCFA != null ? Math.round(Number(s.coutActuel_FCFA)) : 0;
    if (w !== null && w !== undefined) { totalW += Math.round(Number(w)) || 0; auMoinsUneMesureW = true; }
    totalFcfa += fcfa;
    if (!prixKwh && s.prixKwh_FCFA) prixKwh = Number(s.prixKwh_FCFA);
    const wTxt = (w === null || w === undefined) ? `${t('inconnue')} (W)` : (Number(w) === 0 ? `0 W (${t('éteint')})` : `${nbFr(Math.round(Number(w)))} W`);
    const fcfaTxt = `${nbFr(fcfa)} FCFA`;
    return { id: String(s.id), nom: s.nom || t('Capteur'), w, fcfa, wTxt, fcfaTxt };
  });
  const totalWTxt = auMoinsUneMesureW ? `${nbFr(totalW)} W` : `${t('inconnue')} (W)`;
  const totalFcfaTxt = `${nbFr(totalFcfa)} FCFA`;
  return { lignes, totalW, auMoinsUneMesureW, totalFcfa, totalWTxt, totalFcfaTxt, prixKwh };
}

/* ── Liste « Vos configurations d'alerte » : UNE ligne par configuration + résumé global ── */
function renderRulesOverview() {
  const list = $('rules-list'), countEl = $('rules-count'), uncoveredEl = $('rules-uncovered');
  const createBtn = $('rules-create-btn'), createGlobalBtn = $('rules-create-global-btn'), globalBox = $('rules-global-box');
  if (!list) return;
  const nbTot = cfgServer.sensors.length;
  const regles = cfgServer.regles;
  const cacherBtns = (nbTot === 0 || cfgServer.rulesStatus === 'error');
  if (createBtn) createBtn.style.display = cacherBtns ? 'none' : '';
  if (createGlobalBtn) createGlobalBtn.style.display = cacherBtns ? 'none' : '';
  if (globalBox) {
    if (nbTot > 0 && cfgServer.rulesStatus === 'ok') {
      const res = resumeAppareils();
      globalBox.hidden = false;
      globalBox.innerHTML = `<div class="rules-global-head">
        <span class="rules-global-title">${t('Consommation de vos appareils (période en cours)')}</span>
        <span class="rules-global-tot"><strong>${esc(res.totalFcfaTxt)}</strong> <small class="rules-global-w">(${esc(res.totalWTxt)})</small></span>
      </div>
      <div class="rules-global-grid">${res.lignes.map(l => `<div class="rules-global-item">
        <span class="rm-appareil-nom">${esc(l.nom)}</span>
        <span class="rm-appareil-val"><strong>${esc(l.fcfaTxt)}</strong> · ${esc(l.wTxt)}</span>
      </div>`).join('')}</div>`;
    } else {
      globalBox.hidden = true;
      globalBox.innerHTML = '';
    }
  }
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
    list.innerHTML = `<div class="rules-empty">${t('Aucun budget personnalisé pour l’instant : vos appareils suivent les alertes automatiques ci-dessous. Cliquez sur « + Budget global (FCFA) » ou « + Alerte par appareil » pour fixer une limite en Francs CFA.')}</div>`;
    if (countEl) countEl.textContent = t('0 règle');
  } else {
    if (countEl) countEl.textContent = `${regles.length} ${regles.length > 1 ? t('règles') : t('règle')}`;
    list.innerHTML = regles.map(r => {
      const estGlobale = r.est_globale || r.capteur === null || r.capteur === undefined || r.capteur === '';
      const capteurNom = estGlobale
        ? t('Tous les appareils combinés')
        : (r.capteur_nom || (cfgServer.sensors.find(s => String(s.id) === String(r.capteur)) || {}).nom || t('Capteur'));
      const fcfa = r.seuilMontant_FCFA != null ? Math.round(Number(r.seuilMontant_FCFA)) : 0;
      const fcfaActif = fcfa > 0;
      const fcfaHtml = fcfaActif ? `<span class="rchip rc-on">${nbFr(fcfa)} FCFA</span>` : `<span class="rchip rc-off">${t('Désactivé')}</span>`;
      const p = Math.round(Number(r.puissanceMax_W)) || 0;
      const actif = p > 0 && p < 100000;
      const prix = prixKwhActuel();
      const seuilHtml = actif
        ? `<span class="rchip rc-on">${prix > 0 ? `≈ ${esc(fmtFcfaParHeure(p, prix))}` : `${nbFr(p)} W`}</span>`
        : '';
      const nuitHtml = r.surveilleNuit
        ? `<span class="rchip rc-on">${esc(String(r['heureDébutNuit'] || '00:00').slice(0, 5).replace(':', 'h'))} – ${esc(String(r['heureFinNuit'] || '05:00').slice(0, 5).replace(':', 'h'))}</span>`
        : `<span class="rchip rc-off">${t('Désactivée')}</span>`;
      const perso = r.nom && r.nom.trim() && r.nom.trim() !== 'Configuration';
      const titre = perso ? r.nom : capteurNom;
      return `<div class="rule-row" role="button" tabindex="0" data-rule="${esc(String(r.id))}" aria-label="${t('Modifier la règle')} ${esc(titre)} (${esc(capteurNom)})">
        <span class="rule-capteur">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
          <span class="rule-config-txt"><span class="rule-config-nom">${esc(titre)}</span><span class="rule-config-capteur">${esc(capteurNom)}</span></span>
        </span>
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Budget FCFA')}</span>${fcfaHtml}</span>
        ${actif ? `<span class="rule-cell"><span class="rule-cell-lbl">${t('Seuil instantané')}</span>${seuilHtml}</span>` : ''}
        <span class="rule-cell"><span class="rule-cell-lbl">${t('Surveillance nuit')}</span>${nuitHtml}</span>
        <span class="rule-go" aria-hidden="true"></span>
      </div>`;
    }).join('');
  }
  if (uncoveredEl) {
    const aGlobale = regles.some(r => r.est_globale || r.capteur === null || r.capteur === undefined || r.capteur === '');
    const uncovered = aGlobale ? [] : cfgServer.sensors.filter(s => !regles.some(r => String(r.capteur) === String(s.id)));
    uncoveredEl.textContent = uncovered.length
      ? `${t('Suivent les réglages simples')} : ${uncovered.map(s => s.nom || t('Capteur')).join(', ')}.`
      : '';
  }
}

/* ════════════════ Modale d'édition d'une règle ════════════════ */
const rm = {
  overlay: $('rule-modal'), dialog: document.querySelector('.rm-dialog'), mode: $('rm-mode'), title: $('rm-capteur'), nom: $('rm-nom'),
  porteeGlobal: $('rm-portee-global'), porteeCapteur: $('rm-portee-capteur'),
  capteurSelect: $('rm-capteur-select'), capteurActuel: $('rm-capteur-actuel'), appareilsBox: $('rm-appareils-box'),
  fcfaBlock: $('rm-fcfa-block'), fcfaCheck: $('rm-fcfa-check'), fcfaCheckTxt: $('rm-fcfa-check-txt'), fcfaToggle: $('rm-fcfa-toggle'), fcfaGroup: $('rm-fcfa-group'),
  fcfaRange: $('rm-fcfa-range'), fcfaInput: $('rm-fcfa-input'), fcfaPresets: $('rm-fcfa-presets'), fcfaHint: $('rm-fcfa-hint'),
  puissanceBlock: $('rm-puissance-block'), puissanceCheck: $('rm-puissance-check'), puissanceCheckTxt: $('rm-puissance-check-txt'), puissanceToggle: $('rm-puissance-toggle'),
  wConfirmBox: $('rm-w-confirm-box'), wConfirmYes: $('rm-w-confirm-yes'), wConfirmNo: $('rm-w-confirm-no'),
  puissanceGroup: $('rm-puissance-group'), puissanceRange: $('rm-puissance-range'), puissanceInput: $('rm-puissance-input'),
  nuitSeuil: $('rm-nuit-seuil'), nuitAuto: $('rm-nuit-auto'), nuitToggle: $('rm-nuit-toggle'), nuitSub: $('rm-nuit-sub'),
  nuitDerive: $('rm-nuit-derive'), heureDebut: $('rm-heure-debut'), heureFin: $('rm-heure-fin'),
  foot: $('rm-foot'), delete: $('rm-delete'), cancel: $('rm-cancel'), save: $('rm-save'), close: $('rm-close'),
  confirm: $('rm-confirm'), confirmTxt: $('rm-confirm-txt'), confirmCancel: $('rm-confirm-cancel'), confirmDelete: $('rm-confirm-delete'),
  msg: $('rm-msg'), warn: $('rm-warn'),
};
const mstate = {
  ruleId: null, nom: '', sensorId: null,
  fcfaOn: true, fcfa: 10000,
  puissance: 2000, puissanceOn: false, wAttenteConfirm: false,
  nuitOn: false, nuitSeuil: null, heureDebut: '22:00', heureFin: '05:00'
};
let rmInitial = '', rmOpener = null, rmConfirmMode = 'delete', rmNomPersonnalise = false;
const rmSnapshot = () => { const { wAttenteConfirm, ...s } = mstate; return JSON.stringify(s); };

const PALIERS_W = (() => { const v = []; for (let w = 5; w <= 100; w += 5) v.push(w); for (let w = 110; w <= 500; w += 10) v.push(w); for (let w = 600; w <= 5000; w += 100) v.push(w); return v; })();
const SEUIL_MIN_W = 5, SEUIL_MAX_W = 5000;
function indexPalier(w) { let best = 0; PALIERS_W.forEach((p, i) => { if (Math.abs(p - w) < Math.abs(PALIERS_W[best] - w)) best = i; }); return best; }

const PALIERS_FCFA = [500, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 7500, 8000, 9000, 10000, 12000, 15000, 18000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 60000, 75000, 100000, 150000, 200000];
const SEUIL_MIN_FCFA = 100, SEUIL_MAX_FCFA = 10000000;
function indexPalierFcfa(f) { let best = 0; PALIERS_FCFA.forEach((p, i) => { if (Math.abs(p - f) < Math.abs(PALIERS_FCFA[best] - f)) best = i; }); return best; }

/* Seuil de nuit automatique : même formule que le serveur (alerts.utils.seuil_nuit). */
function seuilNuitAuto(puissance) { return puissance >= 100000 ? 50 : Math.max(50, Math.round(puissance * 0.1)); }
function borner(v, min, max) { return Math.min(max, Math.max(min, Math.round(v))); }
function nomCapteurChoisi() {
  if (mstate.sensorId === GLOBAL_VALUE) return t('Tous les appareils combinés');
  return (cfgServer.sensors.find(x => String(x.id) === String(mstate.sensorId)) || {}).nom || t('Capteur');
}

function rmCapteurActuel() {
  const res = resumeAppareils();
  if (rm.capteurActuel) {
    if (mstate.sensorId === GLOBAL_VALUE) {
      rm.capteurActuel.innerHTML = `${t('Total tous appareils :')} <strong>${esc(res.totalFcfaTxt)}</strong> (${esc(res.totalWTxt)}) ${t('sur la période en cours')}`;
    } else {
      const l = res.lignes.find(x => x.id === String(mstate.sensorId));
      if (!l) rm.capteurActuel.textContent = '';
      else rm.capteurActuel.innerHTML = `${t('Cet appareil :')} <strong>${esc(l.fcfaTxt)}</strong> (${esc(l.wTxt)}) ${t('sur la période en cours')}`;
    }
  }
  if (rm.appareilsBox) {
    if (!res.lignes.length) {
      rm.appareilsBox.hidden = true;
      rm.appareilsBox.innerHTML = '';
    } else {
      rm.appareilsBox.hidden = false;
      const estGlobale = mstate.sensorId === GLOBAL_VALUE;
      rm.appareilsBox.innerHTML = `<div class="rm-appareils-head">
        <span class="rm-appareils-title">${estGlobale ? t('Consommation de chaque appareil (inclus dans l’alerte globale)') : t('Consommation de chaque appareil en Francs CFA')}</span>
        <span class="rm-appareils-tot">${t('Total :')} ${esc(res.totalFcfaTxt)} · ${esc(res.totalWTxt)}</span>
      </div>
      <div class="rm-appareils-list">${res.lignes.map(l => {
        const sel = estGlobale || l.id === String(mstate.sensorId);
        return `<div class="rm-appareil-row${sel ? ' is-selected' : ''}">
          <span class="rm-appareil-nom">${esc(l.nom)}</span>
          <span class="rm-appareil-val"><strong>${esc(l.fcfaTxt)}</strong> · ${esc(l.wTxt)}</span>
        </div>`;
      }).join('')}</div>`;
    }
  }
}
function rmTitleText() { return (mstate.nom || '').trim() || (mstate.ruleId ? t('Règle') : t('Nouvelle règle')); }

/* Cohérence de la règle : bloquant = on n'enregistre pas ; sinon simple avertissement affiché dans la modale */
function rmVerifier() {
  const bloquants = [], avertissements = [];
  if (!mstate.sensorId) bloquants.push(t('Choisissez un appareil ou tous les appareils combinés.'));
  if (!mstate.fcfaOn && !mstate.puissanceOn && !mstate.nuitOn) {
    bloquants.push(t('Activez au moins une surveillance : un seuil en FCFA, le seuil de puissance (W) ou la surveillance nocturne.'));
  }
  if (mstate.fcfaOn && (!Number.isFinite(mstate.fcfa) || mstate.fcfa < SEUIL_MIN_FCFA)) {
    bloquants.push(t('Le seuil en FCFA doit être d’au moins 100 FCFA.'));
  }
  if (mstate.nuitOn && mstate.heureDebut && mstate.heureDebut === mstate.heureFin) {
    bloquants.push(t('La plage nocturne doit commencer et finir à deux heures différentes.'));
  }
  if (mstate.puissanceOn && mstate.nuitOn) {
    const nuit = mstate.nuitSeuil == null ? seuilNuitAuto(mstate.puissance) : mstate.nuitSeuil;
    if (nuit >= mstate.puissance) avertissements.push(`${t('Le seuil de nuit')} (${nbFr(nuit)} W) ${t('est supérieur ou égal au seuil de puissance')} (${nbFr(mstate.puissance)} W) : ${t('seule l’alerte de puissance se déclenchera.')}`);
  }
  const cibleActuelle = mstate.sensorId === GLOBAL_VALUE ? null : String(mstate.sensorId);
  const doublon = cfgServer.regles.some(r => {
    const rCible = (r.est_globale || r.capteur == null) ? null : String(r.capteur);
    const rFcfa = r.seuilMontant_FCFA != null ? Math.round(Number(r.seuilMontant_FCFA)) : null;
    const mFcfa = mstate.fcfaOn ? mstate.fcfa : null;
    return String(r.id) !== String(mstate.ruleId) && rCible === cibleActuelle
      && rFcfa === mFcfa
      && (Math.round(Number(r.puissanceMax_W)) === (mstate.puissanceOn ? mstate.puissance : 100000))
      && !!r.surveilleNuit === mstate.nuitOn;
  });
  if (doublon) avertissements.push(t('Une règle identique existe déjà pour cette cible.'));
  return { bloquants, avertissements };
}

function rmRender() {
  const estGlobale = mstate.sensorId === GLOBAL_VALUE;
  if (rm.porteeGlobal) { rm.porteeGlobal.classList.toggle('on', estGlobale); rm.porteeGlobal.setAttribute('aria-checked', estGlobale ? 'true' : 'false'); }
  if (rm.porteeCapteur) { rm.porteeCapteur.classList.toggle('on', !estGlobale); rm.porteeCapteur.setAttribute('aria-checked', !estGlobale ? 'true' : 'false'); }

  if (rm.fcfaBlock) rm.fcfaBlock.style.display = '';
  if (rm.puissanceBlock) rm.puissanceBlock.style.display = '';

  // 1. Bloc FCFA : régulateur affiché uniquement si la case FCFA est validée
  const idxFcfa = indexPalierFcfa(mstate.fcfa);
  const pctFcfa = (idxFcfa / (PALIERS_FCFA.length - 1)) * 100;
  if (rm.fcfaCheck) rm.fcfaCheck.checked = !!mstate.fcfaOn;
  if (rm.fcfaCheckTxt) rm.fcfaCheckTxt.textContent = mstate.fcfaOn ? t('Validé (FCFA)') : t('Valider (FCFA)');
  setToggle(rm.fcfaToggle, mstate.fcfaOn);
  if (rm.fcfaGroup) rm.fcfaGroup.style.display = mstate.fcfaOn ? '' : 'none';
  if (rm.fcfaRange) {
    rm.fcfaRange.max = PALIERS_FCFA.length - 1;
    rm.fcfaRange.value = idxFcfa;
    rm.fcfaRange.style.background = sliderGradient(pctFcfa);
  }
  if (rm.fcfaInput && document.activeElement !== rm.fcfaInput) rm.fcfaInput.value = mstate.fcfa;
  if (rm.fcfaPresets) {
    rm.fcfaPresets.querySelectorAll('[data-fcfa]').forEach(b => {
      b.classList.toggle('on', Number(b.dataset.fcfa) === Number(mstate.fcfa));
    });
  }
  if (rm.fcfaHint) {
    const cibleTxt = estGlobale ? t('la consommation cumulée de tous vos appareils combinés') : `${t('la consommation de')} ${nomCapteurChoisi()}`;
    rm.fcfaHint.textContent = `${t('Dès que')} ${cibleTxt} ${t('atteint')} ${nbFr(mstate.fcfa)} FCFA ${t('sur la période en cours, une alerte est émise.')}`;
  }

  // 2. Bloc Puissance (W) : masqué par défaut, demande confirmation avant d'afficher le régulateur
  const idx = indexPalier(mstate.puissance);
  const pct = (idx / (PALIERS_W.length - 1)) * 100;
  if (rm.nom && document.activeElement !== rm.nom) rm.nom.value = mstate.nom;
  if (rm.capteurSelect) rm.capteurSelect.value = mstate.sensorId || GLOBAL_VALUE;
  if (rm.title) rm.title.textContent = rmTitleText();
  if (rm.puissanceCheck) rm.puissanceCheck.checked = !!(mstate.puissanceOn || mstate.wAttenteConfirm);
  if (rm.puissanceCheckTxt) rm.puissanceCheckTxt.textContent = mstate.puissanceOn ? t('Validé (W)') : (mstate.wAttenteConfirm ? t('Confirmer…') : t('Valider (W)'));
  setToggle(rm.puissanceToggle, mstate.puissanceOn || mstate.wAttenteConfirm);
  if (rm.wConfirmBox) rm.wConfirmBox.hidden = !mstate.wAttenteConfirm;
  if (rm.puissanceGroup) rm.puissanceGroup.style.display = (mstate.puissanceOn && !mstate.wAttenteConfirm) ? '' : 'none';
  rm.puissanceRange.max = PALIERS_W.length - 1;
  rm.puissanceRange.value = idx;
  rm.puissanceRange.style.background = sliderGradient(pct);
  if (document.activeElement !== rm.puissanceInput) rm.puissanceInput.value = mstate.puissance;
  rmCapteurActuel();

  // Bloc Surveillance nocturne
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
  const res = resumeAppareils();
  const optGlobal = `<option value="${GLOBAL_VALUE}">${esc(t('Tous les appareils combinés (alerte globale)'))} — ${esc(res.totalFcfaTxt)}</option>`;
  const optsCapteurs = res.lignes.map(l => `<option value="${esc(l.id)}">${esc(l.nom)} — ${esc(l.fcfaTxt)}</option>`).join('');
  rm.capteurSelect.innerHTML = optGlobal + optsCapteurs;
}

function rmHideConfirm() { if (rm.confirm) rm.confirm.hidden = true; if (rm.foot) rm.foot.hidden = false; }
function rmShowConfirm(mode) {
  rmConfirmMode = mode;
  if (mode === 'discard') {
    rm.confirmTxt.textContent = t('Abandonner vos modifications ? Elles ne seront pas enregistrées.');
    rm.confirmCancel.textContent = t('Continuer l’édition');
    rm.confirmDelete.textContent = t('Abandonner');
  } else {
    rm.confirmTxt.textContent = t('Supprimer cette règle ? Elle cessera de surveiller cet appareil.');
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
  const estGlobale = r.est_globale || r.capteur === null || r.capteur === undefined || r.capteur === '';
  mstate.sensorId = estGlobale ? GLOBAL_VALUE : String(r.capteur);
  rmNomPersonnalise = !!(r.nom && r.nom.trim() && r.nom.trim() !== 'Configuration');
  mstate.nom = rmNomPersonnalise ? r.nom : `${t('Surveillance')} ${nomCapteurChoisi()}`.trim();
  const fcfa = r.seuilMontant_FCFA != null ? Math.round(Number(r.seuilMontant_FCFA)) : 0;
  const p = Math.round(Number(r.puissanceMax_W)) || 0;
  const regleAutoAncienne = !rmNomPersonnalise && fcfa <= 0;
  mstate.fcfaOn = regleAutoAncienne ? true : (fcfa > 0);
  mstate.fcfa = fcfa > 0 ? fcfa : 10000;
  mstate.puissanceOn = regleAutoAncienne ? false : (p > 0 && p < 100000);
  mstate.puissance = (p > 0 && p < 100000) ? p : 2000;
  mstate.wAttenteConfirm = false;
  mstate.nuitOn = !!r.surveilleNuit;
  mstate.nuitSeuil = (r.seuilNuit_W == null) ? null : Math.round(Number(r.seuilNuit_W));
  mstate.heureDebut = String(r['heureDébutNuit'] || '00:00').slice(0, 5);
  mstate.heureFin = String(r['heureFinNuit'] || '05:00').slice(0, 5);
  rmShow(true);
}
function rmOpenCreate(modeGlobal) {
  if (!rm.overlay || cfgServer.sensors.length === 0) return;
  mstate.ruleId = null;
  rmNomPersonnalise = false;
  mstate.sensorId = modeGlobal ? GLOBAL_VALUE : String(cfgServer.sensors[0].id);
  mstate.nom = modeGlobal ? t('Alerte globale tous appareils') : `${t('Surveillance')} ${nomCapteurChoisi()}`;
  mstate.fcfaOn = true; mstate.fcfa = 10000;
  mstate.puissanceOn = false; mstate.puissance = 2000; mstate.wAttenteConfirm = false;
  mstate.nuitOn = false; mstate.nuitSeuil = null;
  mstate.heureDebut = '22:00'; mstate.heureFin = '05:00';
  rmShow(false, rm.fcfaInput || rm.nom);
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
    nom,
    capteur: mstate.sensorId === GLOBAL_VALUE ? null : mstate.sensorId,
    seuilMontant_FCFA: mstate.fcfaOn ? mstate.fcfa : null,
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

function majNomAutoSiBesoin() {
  if (!rmNomPersonnalise && !mstate.ruleId) {
    mstate.nom = mstate.sensorId === GLOBAL_VALUE
      ? t('Alerte globale tous appareils')
      : `${t('Surveillance')} ${nomCapteurChoisi()}`;
  }
}

if (rm.nom) rm.nom.addEventListener('input', e => { rmNomPersonnalise = true; mstate.nom = e.target.value; if (rm.title) rm.title.textContent = rmTitleText(); });
if (rm.capteurSelect) rm.capteurSelect.addEventListener('change', e => { mstate.sensorId = e.target.value; majNomAutoSiBesoin(); rmRender(); });
if (rm.porteeGlobal) rm.porteeGlobal.addEventListener('click', () => { mstate.sensorId = GLOBAL_VALUE; majNomAutoSiBesoin(); rmRender(); });
if (rm.porteeCapteur) rm.porteeCapteur.addEventListener('click', () => {
  if (mstate.sensorId === GLOBAL_VALUE && cfgServer.sensors.length) mstate.sensorId = String(cfgServer.sensors[0].id);
  majNomAutoSiBesoin(); rmRender();
});
function assurerBoiteConfirmW() {
  if (rm.wConfirmBox || !rm.puissanceBlock) return;
  const box = document.createElement('div');
  box.className = 'rm-w-confirm-box';
  box.id = 'rm-w-confirm-box';
  box.hidden = true;
  box.innerHTML = `<p class="rm-w-confirm-txt">${t("Le réglage en")} <strong>Watts (W)</strong> ${t("s'adresse aux personnes qui maîtrisent la puissance électrique de leurs appareils. Voulez-vous afficher le régulateur en Watts ?")}</p>
    <div class="rm-w-confirm-actions">
      <button type="button" class="rm-btn rm-btn-primary rm-btn--sm" id="rm-w-confirm-yes">${t('Oui, afficher le régulateur en Watts (W)')}</button>
      <button type="button" class="rm-btn rm-btn-ghost rm-btn--sm" id="rm-w-confirm-no">${t('Non, ne pas utiliser les Watts')}</button>
    </div>`;
  rm.puissanceBlock.insertBefore(box, rm.puissanceGroup || null);
  rm.wConfirmBox = box;
  rm.wConfirmYes = box.querySelector('#rm-w-confirm-yes');
  rm.wConfirmNo = box.querySelector('#rm-w-confirm-no');
  if (rm.wConfirmYes) rm.wConfirmYes.addEventListener('click', confirmerOuvertureWatts);
  if (rm.wConfirmNo) rm.wConfirmNo.addEventListener('click', annulerOuvertureWatts);
}
function confirmerOuvertureWatts() {
  mstate.wAttenteConfirm = false;
  mstate.puissanceOn = true;
  rmRender();
}
function annulerOuvertureWatts() {
  mstate.wAttenteConfirm = false;
  mstate.puissanceOn = false;
  rmRender();
}
function basculerFcfa() { mstate.fcfaOn = !mstate.fcfaOn; rmRender(); }
function basculerPuissance() {
  assurerBoiteConfirmW();
  if (mstate.puissanceOn || mstate.wAttenteConfirm) {
    mstate.puissanceOn = false;
    mstate.wAttenteConfirm = false;
  } else if (rm.wConfirmBox) {
    mstate.wAttenteConfirm = true;
  } else {
    mstate.puissanceOn = true;
  }
  rmRender();
}
if (rm.fcfaCheck) rm.fcfaCheck.addEventListener('change', basculerFcfa);
bindSwitchOn(rm.fcfaToggle, basculerFcfa);
if (rm.fcfaBlock) {
  const headFcfa = rm.fcfaBlock.querySelector('.rm-block-head');
  if (headFcfa) {
    headFcfa.style.cursor = 'pointer';
    headFcfa.addEventListener('click', e => {
      if (e.target.closest('.itip, .rm-check-pill, .tog-track, input, button')) return;
      basculerFcfa();
    });
  }
}
if (rm.puissanceCheck) rm.puissanceCheck.addEventListener('change', basculerPuissance);
bindSwitchOn(rm.puissanceToggle, basculerPuissance);
if (rm.puissanceBlock) {
  const headW = rm.puissanceBlock.querySelector('.rm-block-head');
  if (headW) {
    headW.style.cursor = 'pointer';
    headW.addEventListener('click', e => {
      if (e.target.closest('.itip, .rm-check-pill, .tog-track, input, button')) return;
      basculerPuissance();
    });
  }
}
if (rm.wConfirmYes) rm.wConfirmYes.addEventListener('click', confirmerOuvertureWatts);
if (rm.wConfirmNo) rm.wConfirmNo.addEventListener('click', annulerOuvertureWatts);
bindSwitchOn(rm.nuitToggle, () => { mstate.nuitOn = !mstate.nuitOn; rmRender(); });
if (rm.fcfaRange) rm.fcfaRange.addEventListener('input', e => { mstate.fcfa = PALIERS_FCFA[+e.target.value] || 10000; rmRender(); });
if (rm.fcfaInput) {
  rm.fcfaInput.addEventListener('input', e => {
    const v = Number(e.target.value);
    if (Number.isFinite(v) && v >= SEUIL_MIN_FCFA && v <= SEUIL_MAX_FCFA) { mstate.fcfa = Math.round(v); rmRender(); }
  });
  rm.fcfaInput.addEventListener('change', e => {
    const v = Number(e.target.value);
    mstate.fcfa = borner(Number.isFinite(v) ? v : mstate.fcfa, SEUIL_MIN_FCFA, SEUIL_MAX_FCFA);
    e.target.value = mstate.fcfa; rmRender();
  });
}
if (rm.fcfaPresets) {
  rm.fcfaPresets.addEventListener('click', e => {
    const b = e.target.closest('[data-fcfa]');
    if (!b) return;
    mstate.fcfa = Number(b.dataset.fcfa) || 10000;
    mstate.fcfaOn = true;
    rmRender();
  });
}
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
if (rulesCreateBtn) rulesCreateBtn.addEventListener('click', () => rmOpenCreate(false));
const rulesCreateGlobalBtn = $('rules-create-global-btn');
if (rulesCreateGlobalBtn) rulesCreateGlobalBtn.addEventListener('click', () => rmOpenCreate(true));
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
