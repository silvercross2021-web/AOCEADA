'use strict';
const t = window.AOCEDA_T || (x => x);
const _LOCALE = (localStorage.getItem('aoceda-lang') === 'en') ? 'en-GB' : 'fr-FR';
/* AOCEDA, page Facturation & consommation.
   Refaite le 20/10/2026 : une page pour le POSTPAYÉ (facture du bimestre, tranches, prochaine facture) et une autre pour
   le PRÉPAYÉ (crédit en premier, recharge en un clic, annulation d'une erreur) ; le montant dit ce qu'il couvre
   (appareils suivis, mesures depuis quand) ; le tarif est expliqué en clair et son cycle se règle ici ; l'objectif de
   dépense est une barre qui se remplit ; plus de « - » pour un vrai 0 F, plus de « 2065 jours ».
   Le shell commun (client-shell.js) gère l'utilisateur, la déconnexion, la cloche et la nav mobile. */

// --- Authentification ---
const token = localStorage.getItem('aoceda_access_token');
if (!token && window.location.pathname.indexOf('/auth/') === -1) {
  window.location.href = '/auth/';
}

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401. */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options).then(res => {
    if (res.status === 204) return null;
    // Rejette sur tout statut non-OK : sinon un corps JSON d'erreur serait pris pour une donnée réelle.
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json().catch(() => null);
  });
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// --- Export (Authorization requis → fetch → blob → lien temporaire) ---
function downloadCSV(url, fallbackName) {
  return window.AOCEDA.authFetch(url)
    .then(res => {
      if (!res.ok) throw new Error('Export impossible');
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : (fallbackName || 'aoceda_export.csv');
      return res.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => window.AOCEDA.downloadBlob(blob, filename));
}

/* ── État de la page ── */
let theme = document.documentElement.getAttribute('data-theme') || 'light';
let chartPeriod = 'mois';
let summary = null;
let facture = null;        // décomposition officielle CIE (/api/analytics/facture/)
let prevision = null;      // prévision de fin de période (/api/analytics/prevision/)
let tarif = null;          // le tarif de ce client, tout compris (/api/analytics/tarif/)
let tranche = null;        // où en est le bimestre dans sa 1ʳᵉ tranche (/api/alertes/tranche/)
let moisHisto = [];        // [{annee_mois, mois_libelle, kwh, fixe_fcfa, variable_fcfa, total_fcfa, en_cours, mesure_depuis}]
let projChart = null;
let joursMonth = [];       // [{date:'AAAA-MM-JJ', kwh:…}] de la période en cours
let joursLoaded = false;
let joursError = false;
let heatCells = null, heatLoaded = false, heatError = false;
let exporting = false, exportingPdf = false;

let heures = 2;
let watts = 1500;

const $ = id => document.getElementById(id);

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

const ICON_MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  $('theme-toggle').innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
}

/* ── Régime du compteur : tout l'écran en dépend ── */
function getCredit() {
  return (facture && facture.credit_prepaye) || (summary && summary.credit_prepaye) || null;
}
function isPrepaid() {
  return (facture && facture.type_compteur === 'prepaye')
    || (summary && summary.type_compteur === 'prepaye')
    || (tarif && tarif.regime === 'prepaye')
    || !!getCredit();
}
/* Période de facturation : le BIMESTRE en postpayé (la CIE facture tous les deux mois), le mois en prépayé. */
function periodeType() {
  const p = (facture && facture.periode) || (prevision && prevision.periode);
  if (p && p.type) return p.type === 'bimestre' ? 'bimestre' : 'mois';
  return isPrepaid() ? 'mois' : 'bimestre';
}
const fmt = v => Number(v || 0).toLocaleString(_LOCALE, { maximumFractionDigits: 0 });
const fmtKwh = v => Number(v).toLocaleString(_LOCALE, { maximumFractionDigits: 1 });
const fmtPrix = v => Number(v).toLocaleString(_LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function dateLongue(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(_LOCALE, { day: 'numeric', month: 'long', timeZone: 'UTC' });
}
const dateCourte = dateLongue;
function dansJours(n) {
  if (n <= 0) return t("aujourd'hui");
  return n === 1 ? t('demain') : `${t('dans')} ${n} ${t('jours')}`;
}
/* Prix d'un kWh « tout compris » : jamais le prix moyen, qui explose en début de période. */
function prixKwh() {
  if (tarif && tarif.prix_kwh) return Number(tarif.prix_kwh);
  if (facture && facture.prix_kwh_tout_compris) return Number(facture.prix_kwh_tout_compris);
  return null;
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
/* Total à ce jour : un vrai 0 F reste « 0 » (avant, il s'affichait « - »). null = vraiment inconnu. */
function getFacture() {
  if (facture && facture.tranche1) return facture.total_fcfa_arrondi != null ? Number(facture.total_fcfa_arrondi) : decompose(facture).total;
  if (summary && summary.facture_estimee_fcfa != null && summary.mode !== 'vide') return Math.round(Number(summary.facture_estimee_fcfa));
  return null;
}

function infoTip(txt, pos) {
  return `<button type="button" class="itip${pos ? ' itip-' + pos : ''}" aria-label="${esc(txt)}" data-tip="${esc(txt)}">` +
    `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="10.5" x2="12" y2="16.5"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg></button>`;
}

const TIP = {
  titre: "Une estimation basée uniquement sur votre consommation réelle, jamais une promesse. Elle devient votre montant exact le dernier jour de la période.",
  confiance: "Fiable = beaucoup de journées mesurées. Indicative = estimation raisonnable mais encore mouvante. Trop tôt = pas assez de données pour avancer un chiffre.",
  fourchette: "Le montant final a de fortes chances de se situer entre ces deux bornes. La fourchette se resserre à mesure que la période avance.",
  fixe: "L'abonnement : la prime fixe et les redevances fixes (électrification rurale, RTI). Elles sont dues à chaque facture, même sans rien consommer.",
  conso: "Vos kWh estimés d'ici la fin de la période, au rythme de vos habitudes, chiffrés avec la grille officielle (tranches et taxes incluses).",
  tropTot: "Une « journée complète » = un jour où votre capteur a mesuré presque tout le temps (≈ 19 h ou plus). Vos journées récentes n'ont que quelques heures de mesures : pas encore assez pour estimer une période entière sans rien inventer. Laissez le capteur branché plus longtemps et le compte montera tout seul.",
  recharge: "Montant d'énergie à acheter auprès de la CIE pour couvrir le coût estimé jusqu'à la fin du mois, d'après votre rythme actuel.",
};

/* ════════════════ Carte principale ════════════════ */
function renderHero() {
  const prepaid = isPrepaid();
  const bim = periodeType() === 'bimestre';
  const total = getFacture();
  const sub = $('page-sub');
  if (sub) sub.textContent = prepaid
    ? t("Combien il vous reste de crédit, quand acheter de l'énergie, et ce que vous dépensez.")
    : t("Combien vous coûte votre électricité, pourquoi, et ce qu'il vous reste à payer.");

  $('est-q').textContent = prepaid ? t('Ce que vous avez dépensé ce mois-ci') : t('Votre facture à ce jour');
  const cover = $('est-cover');

  if (!facture || !facture.tranche1) {
    // Pas encore de mesure exploitable : état honnête, aucun chiffre inventé.
    $('est-mois').textContent = t('En attente de données');
    $('est-amount').textContent = total != null ? fmt(total) : '-';
    $('est-unit').textContent = total != null ? 'FCFA' : '';
    cover.hidden = false;
    cover.textContent = t("Votre facture apparaîtra dès que votre premier capteur aura envoyé des mesures.");
    $('facts').innerHTML = '';
    $('decomp').innerHTML = `<div class="decomp-empty">${t('Le détail apparaîtra dès que vos mesures seront disponibles.')}</div>`;
    return;
  }

  const f = facture;
  $('est-mois').textContent = `${bim ? t('Bimestre') : t('Mois')} · ${t(f.mois)}`;
  $('est-amount').textContent = fmt(total);
  $('est-unit').textContent = prepaid
    ? t('FCFA · déjà déduits de votre crédit, taxes comprises')
    : t('FCFA · taxes et TVA comprises');

  // Ce que le montant couvre RÉELLEMENT (AOCEDA ne voit que les appareils qu'il suit, et seulement depuis son installation)
  const lignes = [];
  if (f.aucune_mesure) {
    lignes.push(prepaid
      ? t("Aucune consommation mesurée ce mois-ci : rien n'a été déduit de votre crédit.")
      : t("Aucune consommation mesurée depuis le début du bimestre : ce montant ne contient que l'abonnement fixe, dû quoi qu'il arrive."));
  } else {
    const n = Number(f.capteurs_suivis) || 0;
    lignes.push(`${t("Calculé d'après la consommation mesurée par AOCEDA sur")} ${n} ${n > 1 ? t('appareils suivis') : t('appareil suivi')}.`);
  }
  if (f.mesure_depuis) {
    lignes.push(`${t("Mesures disponibles depuis le")} ${esc(dateLongue(f.mesure_depuis))} : ${t("avant cette date AOCEDA n'était pas en service, la période est incomplète.")}`);
  }
  if (f.en_ligne === false && f.dernier_contact) {
    lignes.push(`${t('Boîtier hors ligne : dernière mesure reçue le')} ${esc(new Date(f.dernier_contact).toLocaleDateString(_LOCALE, { day: 'numeric', month: 'long' }))}. ${t("Ce qui s'est passé depuis n'est pas compté.")}`);
  }
  cover.hidden = lignes.length === 0;
  cover.innerHTML = lignes.map(l => `<span>${l}</span>`).join('');

  renderFacts(f, prepaid, bim);
  renderDecomp(f, prepaid, total);
}

/* Les repères de la période, en une liste alignée à droite du montant */
function renderFacts(f, prepaid, bim) {
  const rows = [];
  const jour = Number(f.jours_ecoules) || 0, nb = Number(f.jours_du_mois) || 0;
  if (!prepaid && f.fin_periode) {
    const j = Number(f.jours_restants_periode) || 0;
    rows.push([t('Fin du bimestre'), `${esc(dateLongue(f.fin_periode))} <span class="fz-dim">(${dansJours(j)})</span>`]);
  }
  if (nb) rows.push([bim ? t('Jour du bimestre') : t('Jour du mois'), `${jour} <span class="fz-dim">${t('sur')} ${nb}</span>`]);
  const e = f.ecart;
  if (e && e.precedent_fcfa != null) {
    let v = `${fmt(e.precedent_fcfa)} FCFA`;
    if (e.pct != null && Math.round(e.pct) !== 0) {
      v += ` <span class="cmp-badge ${e.pct > 0 ? 'cmp-up' : 'cmp-dn'}">${e.pct > 0 ? '▲' : '▼'} ${Math.abs(Math.round(e.pct))} %</span>`;
    }
    rows.push([bim ? t('À ce stade du bimestre précédent') : t('À ce stade du mois précédent'), v]);
  }
  $('facts').innerHTML = rows.map(([k, v]) => `<div class="fz-fact"><dt>${k}</dt><dd>${v}</dd></div>`).join('');
}

function renderDecomp(f, prepaid, total) {
  const d = decompose(f);
  const abo = (f.abonnement_fixe_fcfa != null) ? Number(f.abonnement_fixe_fcfa)
    : Math.round(Number(f.prime_fixe_fcfa)) + Math.round(Number(f.taxe_fixe_fcfa || 0));
  const conso = (f.consommation_fcfa != null) ? Number(f.consommation_fcfa) : (total - abo);
  const bim = periodeType() === 'bimestre';
  const HOME = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></svg>';
  const BOLT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';
  const bucket = (ico, cls, lbl, sub, val, tip) =>
    `<div class="decomp-bucket ${cls}"><span class="db-ico">${ico}</span>` +
    `<span class="db-txt"><span class="db-lbl">${esc(t(lbl))}${tip ? ' ' + infoTip(tip) : ''}</span><span class="db-sub">${esc(sub)}</span></span>` +
    `<span class="db-val">${esc(val)}</span></div>`;
  const drow = (l, v) => `<div class="dd-row"><span class="dd-lbl">${esc(l)}</span><span class="dd-val">${esc(v)}</span></div>`;
  const detail = [drow(`${prepaid ? t('Énergie, prix unique (abonnement compris) :') : t('1ʳᵉ tranche :')} ${fmtKwh(f.tranche1.kwh)} kWh × ${fmtPrix(f.tranche1.prix)} F`, `${fmt(d.t1)} FCFA`)];
  if (d.hasT2) detail.push(drow(`${t('2ᵉ tranche :')} ${fmtKwh(f.tranche2.kwh)} kWh × ${fmtPrix(f.tranche2.prix)} F`, `${fmt(d.t2)} FCFA`));
  if (!prepaid) detail.push(drow(`${t('Abonnement fixe (prime fixe')} ${esc(String(f.amperage))} A)`, `${fmt(d.prime)} FCFA`));
  detail.push(drow(`${t('Taxes et redevances')} (${fmtPrix(f.taxes_par_kwh)} F/kWh + ${fmt(f.taxe_fixe_fcfa || 0)} F ${t('fixes')})`, `${fmt(d.taxes)} FCFA`));

  $('decomp').innerHTML =
    `<div class="decomp-title">${prepaid ? t('De quoi se compose votre dépense') : t('De quoi se compose votre facture')}</div>` +
    (prepaid ? '' : bucket(HOME, 'db-fixed', 'Abonnement fixe',
      `${bim ? t('Dû à chaque bimestre, même sans consommer') : t('Dû chaque mois, même sans consommer')} · ${f.amperage} A`, `${fmt(abo)} F`, TIP.fixe)) +
    bucket(BOLT, 'db-conso', prepaid ? 'Ce que vous avez consommé' : 'Votre consommation',
      `${fmtKwh(Number(f.kwh_consommes) || 0)} kWh ${prepaid ? t('ce mois-ci') : t('depuis le début du bimestre')}`, `${fmt(conso)} F`,
      prepaid
        ? t("Vos kWh réellement mesurés ce mois-ci × le prix unique du prépayé (abonnement et taxes compris, sans tranche).")
        : t("Le coût de vos kWh réellement mesurés depuis le début de la période, avec la grille officielle (tranches et taxes incluses). C'est la seule part qui augmente quand vous consommez.")) +
    `<div class="decomp-total"><span class="dt-lbl">${t('Total à ce jour')}<em>${t('TVA 18 % incluse')}</em></span><span class="dt-val">${fmt(total)} F</span></div>` +
    ((!prepaid && abo > conso && !f.aucune_mesure) ? `<p class="decomp-note">${t("L'abonnement fixe est la plus grosse part tant que vous consommez peu. Seule « votre consommation » augmente avec vos kWh.")}</p>` : '') +
    `<details class="decomp-details"><summary>${t('Voir le détail officiel CIE')}</summary><div class="dd-rows">${detail.join('')}</div></details>`;
}

/* ── Progression de la période (le bimestre pour un postpayé, le mois pour un prépayé) ── */
function renderProgress() {
  const now = new Date();
  const per = facture && facture.periode;
  const daysIn = facture && facture.jours_du_mois ? Number(facture.jours_du_mois) : new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const jour = facture && facture.jours_ecoules ? Number(facture.jours_ecoules) : now.getDate();
  const pct = Math.min(100, Math.round(jour / daysIn * 100));
  $('prog-pct').textContent = `${pct} % ${t('écoulé')}`;
  requestAnimationFrame(() => requestAnimationFrame(() => { $('prog-fill').style.width = `${pct}%`; }));
  if (per && per.debut && per.fin) {
    $('prog-start').textContent = dateCourte(per.debut);
    $('prog-end').textContent = dateCourte(per.fin);
  } else {
    $('prog-start').textContent = '';
    $('prog-end').textContent = '';
  }
  $('prog-mid').textContent = `${t('Jour')} ${jour} / ${daysIn}`;
  const lbl = document.querySelector('.prog-label');
  if (lbl) lbl.textContent = periodeType() === 'bimestre' ? t('Progression du bimestre') : t('Progression du mois');
}

/* ════════════════ Objectif de dépense ════════════════ */
let budget = null;       // FCFA, propre à l'appareil (navigateur), par type de période
let budgetEdition = false;
const cleBudget = () => `aoceda-budget-${periodeType()}`;
function lireBudget() {
  try { const v = Number(localStorage.getItem(cleBudget())); budget = v > 0 ? v : null; } catch (e) { budget = null; }
}
function ecrireBudget(v) {
  budget = v;
  try { if (v) localStorage.setItem(cleBudget(), String(v)); else localStorage.removeItem(cleBudget()); } catch (e) { /* stockage indisponible */ }
}
function renderBudget() {
  lireBudget();
  const form = $('bud-form'), state = $('bud-state'), edit = $('bud-edit'), del = $('bud-del'), titre = $('bud-title');
  const bim = periodeType() === 'bimestre';
  titre.textContent = bim ? t('Mon objectif de dépense pour ce bimestre') : t('Mon objectif de dépense pour ce mois');
  const montrerForm = budget == null || budgetEdition;
  form.hidden = !montrerForm;
  edit.hidden = montrerForm;
  del.hidden = !(montrerForm && budget != null);
  if (montrerForm) {
    $('bud-save').textContent = budget == null ? t('Fixer mon objectif') : t('Enregistrer');
    if (budgetEdition && budget != null && !$('budget-input').value) $('budget-input').value = fmt(budget);
  }
  if (budget == null) {
    state.hidden = false;
    state.innerHTML = `<p class="bud-hint">${t("Fixez un montant à ne pas dépasser : une barre vous montre où vous en êtes.")}</p>`;
    return;
  }
  const total = getFacture();
  if (total == null) { state.hidden = true; return; }
  const pct = Math.round(total / budget * 100);
  const reste = budget - total;
  const cls = pct >= 100 ? 'depasse' : (pct >= 80 ? 'proche' : '');
  let phrase = reste >= 0
    ? `<strong>${fmt(reste)} F</strong> ${t('disponibles sur votre objectif de')} ${fmt(budget)} F (${pct} % ${t('utilisé')}).`
    : `${t('Objectif dépassé de')} <strong>${fmt(-reste)} F</strong> (${fmt(budget)} F ${t('prévus')}).`;
  if (prevision && prevision.bill_central != null && prevision.mode !== 'trop_tot' && prevision.mode !== 'vide') {
    const c = Number(prevision.bill_central);
    phrase += ` ${t('À ce rythme, vous finirez vers')} <strong>${fmt(c)} F</strong> : ${c <= budget ? t('dans votre objectif') : t('au-dessus de votre objectif')}.`;
  }
  state.hidden = false;
  state.innerHTML = `<div class="bud-bar ${cls}" role="img" aria-label="${pct} %"><span style="width:${Math.min(100, Math.max(2, pct))}%"></span></div><p class="bud-phrase">${phrase}</p>`;
}
function initBudget() {
  const input = $('budget-input');
  const enregistrer = () => {
    const v = parseInt(String(input.value).replace(/[^\d]/g, ''), 10);
    if (!(v >= 1000 && v <= 10000000)) { input.classList.add('is-err'); input.focus(); return; }
    input.classList.remove('is-err');
    ecrireBudget(v); budgetEdition = false; input.value = ''; renderBudget();
  };
  $('bud-save').addEventListener('click', enregistrer);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); enregistrer(); } });
  input.addEventListener('input', () => input.classList.remove('is-err'));
  $('bud-edit').addEventListener('click', () => { budgetEdition = true; input.value = fmt(budget); renderBudget(); input.focus(); });
  $('bud-del').addEventListener('click', () => { ecrireBudget(null); budgetEdition = false; input.value = ''; renderBudget(); });
}

/* ════════════════ Mes tranches (postpayé) ════════════════ */
function renderTranche() {
  const card = $('tranche-card');
  if (!card) return;
  if (isPrepaid() || !tranche || !tranche.applicable) { card.hidden = true; return; }
  card.hidden = false;
  const kwh = Number(tranche.kwh) || 0, seuil = Number(tranche.seuil_kwh) || 0;
  const pct = seuil > 0 ? Math.min(100, kwh / seuil * 100) : 0;
  const fill = $('tr-fill');
  fill.style.width = `${Math.max(pct, kwh > 0 ? 2 : 0)}%`;
  fill.className = pct >= 100 ? 'depasse' : (pct >= 90 ? 'proche' : '');
  $('tr-gauge').setAttribute('aria-label', `${Math.round(pct)} %`);
  $('tr-seuil').textContent = `${fmt(seuil)} kWh`;
  const social = tranche.type_tarif === 'social';
  const p1 = tarif && tarif.prix_t1 != null ? Number(tarif.prix_t1) : null;
  const p2 = tarif && tarif.prix_t2 != null ? Number(tarif.prix_t2) : null;
  const lignes = [];
  if (kwh >= seuil) {
    $('tr-lead').innerHTML = `${t('Vous avez consommé')} <strong>${fmtKwh(kwh)} kWh</strong> : ${t('vous avez dépassé les')} <strong>${fmt(seuil)} kWh</strong> ${t('de la 1ʳᵉ tranche, vous êtes dans la 2ᵉ tranche.')}`;
    if (p2 != null) lignes.push(`${t('Chaque kWh coûte maintenant')} <strong>${fmtPrix(p2)} F</strong> (${t('taxes comprises')}), ${p1 != null ? `${t('au lieu de')} ${fmtPrix(p1)} F.` : ''}`);
  } else {
    $('tr-lead').innerHTML = `${t('Vous avez consommé')} <strong>${fmtKwh(kwh)} kWh</strong> ${t('sur les')} <strong>${fmt(seuil)} kWh</strong> ${t('de la 1ʳᵉ tranche de ce bimestre')} (<strong>${Math.round(pct)} %</strong>).`;
    if (p1 != null) lignes.push(`${t("Prix d'un kWh en ce moment :")} <strong>${fmtPrix(p1)} F</strong> (${t('taxes comprises')}).`);
    if (p2 != null) lignes.push(`${t('Au-delà de')} ${fmt(seuil)} kWh : <strong>${fmtPrix(p2)} F</strong> ${t('le kWh')}${social ? ` (${t('beaucoup plus cher')}, ${t('presque le double')})` : ` (${t('un peu moins cher')})`}.`);
    const reste = Math.max(0, Math.round((new Date(tranche.fin + 'T00:00:00') - new Date(new Date().toDateString())) / 86400000));
    if (tranche.jours_avant_seuil != null) {
      const j = Math.max(1, Math.round(Number(tranche.jours_avant_seuil)));
      if (j <= reste) {
        const d = new Date(); d.setDate(d.getDate() + j);
        lignes.push(`${t('Au rythme actuel, vous passerez en 2ᵉ tranche vers le')} <strong>${esc(d.toLocaleDateString(_LOCALE, { day: 'numeric', month: 'long' }))}</strong>.`);
      } else lignes.push(t('Au rythme actuel, vous resterez dans la 1ʳᵉ tranche jusqu\'à la fin du bimestre.'));
    } else if (kwh > 0) lignes.push(t('Il faut 3 journées complètes de mesures pour estimer quand vous changerez de tranche.'));
  }
  if (social) lignes.push(t('Au tarif social, la 2ᵉ tranche coûte presque le double : c\'est la tranche à éviter.'));
  $('tr-lines').innerHTML = lignes.map(l => `<li>${l}</li>`).join('');
}

/* ════════════════ Mon tarif ════════════════ */
const CYCLES = {
  GF1: 'janvier-février, mars-avril, mai-juin, juillet-août, septembre-octobre, novembre-décembre',
  GF2: 'février-mars, avril-mai, juin-juillet, août-septembre, octobre-novembre, décembre-janvier',
};
function renderTarif() {
  const el = $('tarif-body');
  if (!el) return;
  if (!tarif) return;
  const prepaid = tarif.regime === 'prepaye';
  const social = tarif.type_tarif === 'social';
  const li = (a, b, c) => `<li><span class="tf-k">${a}</span><strong class="tf-v">${b}</strong>${c ? `<small class="tf-s">${c}</small>` : ''}</li>`;
  let liste = li(t('Abonnement'), `${tarif.amperage} A · ${social ? t('tarif social') : t('tarif général')}`,
    `${t('puissance')} ${String(tarif.puissance_kva).replace('.', ',')} kVA`);
  if (prepaid) {
    liste += li(t("Prix d'un kWh"), `${fmtPrix(tarif.prix_kwh)} F`, t("prix unique, tout compris : pas de tranche, pas d'abonnement à part"));
    liste += li(t('Par exemple'), `5 000 F ≈ ${fmtKwh(5000 / tarif.prix_kwh)} kWh`, t('ce que vous obtenez en achetant 5 000 F d\'énergie à la CIE'));
  } else {
    liste += li(t("Prix d'un kWh"), `${fmtPrix(tarif.prix_t1)} F`,
      `${t("jusqu'à")} ${fmt(tarif.seuil_t1_kwh)} kWh ${t('par bimestre, puis')} ${fmtPrix(tarif.prix_t2)} F (${tarif.sens === 'progressif' ? t('plus cher') : t('moins cher')})`);
    liste += li(t('Abonnement fixe'), `${fmt(tarif.abonnement_periode)} F`, t('par bimestre, même sans consommer'));
  }
  let reglages = '';
  if (!prepaid) {
    const g = (tarif.cycle && tarif.cycle.groupe) || 'GF1';
    reglages += `<div class="tf-set"><label class="tf-lbl" for="tf-cycle">${t('Mon cycle de facturation')}</label>
      <select id="tf-cycle" class="tf-select">
        <option value="GF1"${g === 'GF1' ? ' selected' : ''}>${t('Groupe 1')} : ${CYCLES.GF1.split(', ').slice(0, 2).join(', ')}…</option>
        <option value="GF2"${g === 'GF2' ? ' selected' : ''}>${t('Groupe 2')} : ${CYCLES.GF2.split(', ').slice(0, 2).join(', ')}…</option>
      </select>
      <p class="tf-help">${t('Regardez votre dernière facture CIE : si elle couvre janvier-février (ou mars-avril…), choisissez le groupe 1 ; si elle couvre février-mars (ou avril-mai…), le groupe 2.')}</p></div>`;
  }
  // La commune (Abidjan ou non, donc la taxe sur les ordures) suit la VILLE choisie dans Paramètres : une seule source
  reglages += `<div class="tf-set"><span class="tf-lbl">${t('Taxe sur les ordures ménagères')}</span>
    <p class="tf-help">${tarif.abidjan ? t('2,50 F par kWh, car votre logement est à Abidjan.') : t('1 F par kWh, car votre logement est hors d’Abidjan.')} <a href="/parametres/#foyer">${t('Changer de ville')}</a></p></div>`;
  const titreReglage = prepaid ? t('Taxe sur les ordures') : t('Mon cycle et la taxe sur les ordures');
  el.innerHTML = `<ul class="tf-list">${liste}</ul><details class="tf-more"><summary>${titreReglage}</summary>${reglages}</details><p class="tf-msg" id="tf-msg" role="status" aria-live="polite"></p>
    <p class="tf-foot">${t("Prix tout compris (TVA, redevances et taxes incluses), d'après l'arrêté officiel du 27 décembre 2023. Pour changer d'ampérage ou de type de compteur, voir")} <a href="/parametres/">${t('Paramètres')}</a>.</p>`;
  const cycle = $('tf-cycle');
  if (cycle) cycle.addEventListener('change', () => enregistrerReglage({ groupeFacturation: cycle.value }));
}
function enregistrerReglage(corps) {
  const msg = $('tf-msg');
  if (msg) { msg.className = 'tf-msg'; msg.textContent = t('Enregistrement…'); }
  fetchWithAuth('/api/users/me/', { method: 'PUT', body: JSON.stringify(corps) })
    .then(() => {
      if (msg) { msg.className = 'tf-msg ok'; msg.textContent = t('Enregistré : vos montants sont recalculés.'); }
      chargerTout();
    })
    .catch(() => {
      if (msg) { msg.className = 'tf-msg err'; msg.textContent = t("Impossible d'enregistrer. Réessayez."); }
      renderTarif();
    });
}

/* ════════════════ Historique des périodes ════════════════ */
function getHisto() {
  if (!moisHisto.length) return [];
  return moisHisto.map(mo => ({
    m: mo.en_cours ? `${t(mo.mois_libelle)} (${t('en cours')})` : t(mo.mois_libelle),
    v: Math.round(Number(mo.total_fcfa)) || 0,
    kwh: Number(mo.kwh) || 0,
    cur: !!mo.en_cours,
    depuis: mo.mesure_depuis || null,
  }));
}
function renderHisto() {
  const histo = getHisto();
  const bim = periodeType() === 'bimestre';
  if (histo.length === 0) {
    $('histo-sub').textContent = t('Aucun historique disponible');
    $('histo-list').innerHTML = '';
    return;
  }
  const total = getFacture();
  const curFound = histo.find(x => x.cur);
  // Le mois/bimestre en cours est aligné sur le total « à ce jour » de la carte principale (mêmes chiffres partout)
  if (curFound && total != null) { curFound.v = total; if (facture) curFound.kwh = Number(facture.kwh_consommes) || curFound.kwh; }
  const maxV = Math.max(...histo.map(x => x.v), 1);
  $('histo-sub').textContent = histo.length > 1
    ? `${t('Les')} ${histo.length} ${bim ? t('derniers bimestres') : t('derniers mois')}`
    : (bim ? t('Votre premier bimestre') : t('Votre premier mois'));
  $('histo-list').innerHTML = histo.map((r, i) => {
    const pct = Math.min(100, Math.max(4, r.v / maxV * 100));
    const cur = r.cur ? ' cur' : '';
    let delta = '';
    const avant = i > 0 ? histo[i - 1] : null;
    // Pas de pourcentage face à une période presque vide, ni face à une période incomplète ou en cours
    if (avant && avant.v >= 100 && !avant.depuis && !r.cur && !r.depuis && Math.abs((r.v - avant.v) / avant.v) <= 3) {
      const p = Math.round((r.v - avant.v) / avant.v * 100);
      delta = p === 0 ? `<span class="histo-delta hd-flat">${t('stable')}</span>`
        : `<span class="histo-delta ${p > 0 ? 'hd-up' : 'hd-dn'}">${p > 0 ? '▲' : '▼'} ${Math.abs(p)} %</span>`;
    }
    const note = r.depuis ? `<div class="histo-note">${t('mesuré depuis le')} ${esc(dateCourte(r.depuis))} (${t('période incomplète')})</div>` : '';
    return `<div class="histo-item">
      <div class="histo-head"><span class="histo-month${cur}">${esc(r.m)}</span>
        <span class="histo-right"><span class="histo-val${cur}">${fmt(r.v)} FCFA</span>${delta}</span></div>
      <div class="histo-track"><div class="histo-bar${cur}" style="width:${pct}%"></div></div>${note}
    </div>`;
  }).join('') + (curFound
    ? `<p class="histo-foot">${bim ? t("Le bimestre en cours grandit jusqu'à son dernier jour : sa barre n'est pas encore comparable à un bimestre complet.") : t("Le mois en cours grandit jusqu'au dernier jour : sa barre n'est pas encore comparable à un mois complet.")}</p>` : '');
}

/* ════════════════ Graphique ════════════════ */
function showChartEmpty(msg) {
  if (projChart) { projChart.destroy(); projChart = null; }
  const canvas = $('proj-chart');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  let ph = wrap.querySelector('.chart-empty');
  if (!ph) { ph = document.createElement('div'); ph.className = 'chart-empty'; wrap.appendChild(ph); }
  ph.textContent = msg; ph.style.display = ''; canvas.style.display = 'none';
}
function hideChartEmpty() {
  const canvas = $('proj-chart');
  if (!canvas) return;
  const ph = canvas.parentElement.querySelector('.chart-empty');
  if (ph) ph.style.display = 'none';
  canvas.style.display = '';
}

/* Consommation journalière RÉELLE de la période : jours mesurés = valeur réelle ; jours passés SANS mesure = null (trou
   honnête, capteur hors ligne ≠ conso nulle) ; jours futurs = null (aucune projection). */
function buildPeriodArrays() {
  const now = new Date();
  let debut, today, nbJours;
  if (facture && facture.periode && facture.periode.debut) {
    const [y, m, d] = facture.periode.debut.split('-').map(Number);
    debut = Date.UTC(y, m - 1, d);
    today = Number(facture.jours_ecoules) || now.getDate();
    nbJours = Number(facture.jours_du_mois) || new Date(y, m, 0).getDate();
  } else {
    debut = Date.UTC(now.getFullYear(), now.getMonth(), 1); today = now.getDate();
    nbJours = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  }
  const cles = Array.from({ length: nbJours }, (_, i) => new Date(debut + i * 86400000).toISOString().slice(0, 10));
  const dailyMap = new Map();
  joursMonth.forEach(j => dailyMap.set(String(j.date), Number(j.kwh) || 0));
  let mesures = 0;
  const actual = cles.map((cle, i) => {
    if (i + 1 > today) return null;
    const v = dailyMap.get(cle);
    if (v != null) mesures++;
    return v != null ? Math.round(v * 100) / 100 : null;
  });
  const labels = cles.map((cle, i) => {
    const [, mm, dd] = cle.split('-').map(Number);
    return (i > 0 && dd === 1) ? `${dd}/${mm}` : `${dd}`;
  });
  return { actual, labels, hasRealData: mesures > 0, nbJours };
}

function renderChart() {
  if (projChart) projChart.destroy();
  const d = theme === 'dark';
  const gc = d ? 'rgba(255,255,255,.06)' : 'rgba(35,27,16,.06)';
  const lc = cssVar('--tx-s', d ? '#C2B19A' : '#6B5A45');
  const surf = cssVar('--bg-s', d ? '#1E1A13' : '#FFFFFF');
  const dv2 = cssVar('--dv-2', '#1B7A6E');
  const ink = cssVar('--tx-p', '#231B10');
  const chartSub = $('chart-sub');
  const projNote = $('proj-note');
  const bim = periodeType() === 'bimestre';
  const pillA = $('pill-periode'), pillB = $('pill-passees');
  if (pillA) pillA.textContent = bim ? t('Ce bimestre') : t('Ce mois-ci');
  if (pillB) pillB.textContent = bim ? t('Factures passées') : t('Mois passés');

  if (chartPeriod === '3mois') {
    if (chartSub) chartSub.textContent = bim
      ? t('Facture de chaque bimestre : abonnement fixe + votre consommation (FCFA)')
      : t('Dépense de chaque mois : votre consommation (FCFA)');
    if (!moisHisto.length) { showChartEmpty(t('Aucun historique disponible pour le moment.')); if (projNote) projNote.hidden = true; return; }
    hideChartEmpty();
    const labels3 = moisHisto.map(mo => mo.en_cours ? `${t(mo.mois_libelle)} (${t('en cours')})` : t(mo.mois_libelle));
    const fixe = moisHisto.map(mo => mo.fixe_fcfa);
    const conso = moisHisto.map(mo => mo.variable_fcfa);
    const kwhArr = moisHisto.map(mo => mo.kwh);
    const infoCol = cssVar('--info', '#3E6E8E');
    if (projNote) {
      projNote.hidden = false;
      projNote.textContent = bim
        ? t("Chaque barre = la facture d'un bimestre (deux mois). La part bleue est l'abonnement fixe, dû à chaque bimestre même sans consommer ; la part verte est votre consommation réelle.")
        : t('Chaque barre = ce que vous avez dépensé dans le mois.');
    }
    const datasets = [];
    if (bim) datasets.push({ label: t('Abonnement fixe'), data: fixe, backgroundColor: d ? 'rgba(62,110,142,.55)' : 'rgba(62,110,142,.35)', borderColor: infoCol, borderWidth: 1, stack: 'f', borderRadius: 3, maxBarThickness: 90 });
    datasets.push({ label: t('Votre consommation'), data: conso, backgroundColor: d ? 'rgba(27,122,110,.85)' : 'rgba(27,122,110,.7)', borderColor: dv2, borderWidth: 1, stack: 'f', borderRadius: { topLeft: 6, topRight: 6, bottomLeft: 0, bottomRight: 0 }, maxBarThickness: 90 });
    projChart = new Chart($('proj-chart'), {
      type: 'bar', data: { labels: labels3, datasets },
      options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
        plugins: {
          legend: { display: bim, position: 'top', align: 'end', labels: { color: lc, font: { family: 'Hanken Grotesk', size: 12 }, boxWidth: 12, boxHeight: 12, usePointStyle: true, pointStyle: 'rectRounded' } },
          tooltip: { backgroundColor: surf, borderColor: cssVar('--bd-s', '#E4D9C8'), borderWidth: 1, titleColor: ink, bodyColor: lc, padding: 10, cornerRadius: 8,
            callbacks: {
              label: c => `${t(c.dataset.label)} : ${Number(c.raw).toLocaleString(_LOCALE)} FCFA`,
              footer: items => { const i = items[0].dataIndex; return `Total : ${(fixe[i] + conso[i]).toLocaleString(_LOCALE)} FCFA  ·  ${kwhArr[i].toLocaleString(_LOCALE, { maximumFractionDigits: 1 })} kWh`; },
            } } },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: lc, font: { family: 'Hanken Grotesk', size: 12 } } },
          y: { stacked: true, beginAtZero: true, grid: { color: gc }, border: { display: false }, ticks: { color: lc, font: { family: 'Spline Sans Mono', size: 11 }, callback: v => `${v.toLocaleString(_LOCALE)} F` } }
        } }
    });
    return;
  }

  if (chartSub) chartSub.textContent = t('Consommation réelle, jour par jour (kWh)');
  if (projNote) projNote.hidden = true;
  if (!joursLoaded) { showChartEmpty(t('Chargement…')); return; }
  if (joursError) { showChartEmpty(t('Consommation de la période indisponible (erreur serveur). Réessayez.')); return; }
  const built = buildPeriodArrays();
  if (!built.hasRealData) { showChartEmpty(bim ? t('Aucune consommation enregistrée ce bimestre.') : t('Aucune consommation enregistrée ce mois-ci.')); return; }
  hideChartEmpty();
  const prix = prixKwh();
  projChart = new Chart($('proj-chart'), {
    type: 'bar',
    data: { labels: built.labels, datasets: [{ label: t('Consommation'), data: built.actual, backgroundColor: d ? 'rgba(27,122,110,.6)' : 'rgba(27,122,110,.5)', borderColor: dv2, borderWidth: 1, borderRadius: 4, maxBarThickness: 16 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: {
        backgroundColor: surf, borderColor: cssVar('--bd-s', '#E4D9C8'), borderWidth: 1, titleColor: ink, bodyColor: lc, padding: 10, cornerRadius: 8,
        callbacks: {
          title: items => items.length ? `${t('Jour')} ${items[0].label}` : '',
          label: c => (c.raw == null) ? null : `${c.raw} kWh${prix ? ` ≈ ${Math.round(c.raw * prix).toLocaleString(_LOCALE)} FCFA` : ''}`,
        } } },
      scales: { y: { beginAtZero: true, grid: { color: gc }, border: { display: false }, ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lc, callback: v => `${v} kWh`, maxTicksLimit: 6 } },
        x: { grid: { display: false }, border: { display: false }, ticks: { font: { family: 'Spline Sans Mono', size: 11 }, color: lc, maxTicksLimit: 10, autoSkip: true } }
      } }
  });
}

/* ════════════════ Carte thermique ════════════════ */
const HEAT_RAMP = ['rgba(27,122,110,.22)', 'rgba(27,122,110,.50)', 'rgba(181,103,11,.40)', 'rgba(181,103,11,.70)', 'rgba(160,88,8,.92)'];
function heatBand(v, maxV) {
  if (v === null || v === undefined) return cssVar('--bg-h', '#F2EBDD');
  const r = maxV > 0 ? v / maxV : 0;
  if (r < 0.2) return HEAT_RAMP[0];
  if (r < 0.4) return HEAT_RAMP[1];
  if (r < 0.6) return HEAT_RAMP[2];
  if (r < 0.8) return HEAT_RAMP[3];
  return HEAT_RAMP[4];
}
function renderHeatmap() {
  const container = $('heatmap');
  if (!container) return;
  container.innerHTML = '';
  const emptyMsg = txt => {
    const el = document.createElement('div');
    el.style.cssText = 'padding:1.5rem;text-align:center;color:var(--tx-m);font-size:.88rem';
    el.textContent = txt; container.appendChild(el);
  };
  if (!heatLoaded) { emptyMsg(t('Chargement…')); return; }
  if (heatError) { emptyMsg(t('Carte thermique indisponible (erreur serveur). Réessayez.')); return; }
  const map = {};
  (heatCells || []).forEach(c => { map[c.dow + '-' + c.hour] = Number(c.avg_w) || 0; });
  const avg = (di, hi) => { const k = di + '-' + hi; return (k in map) ? map[k] : null; };
  let maxV = 0;
  for (let di = 0; di < 7; di++) for (let hi = 0; hi < 24; hi++) { const v = avg(di, hi); if (v != null && v > maxV) maxV = v; }
  if (maxV <= 0) { emptyMsg(t('Aucune donnée de consommation sur les 7 derniers jours.')); return; }
  const days = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'].map(t);
  const dayNames = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'].map(t);
  const wrap = document.createElement('div'); wrap.className = 'heat-wrap';
  const dayCol = document.createElement('div'); dayCol.className = 'heat-daycol';
  days.forEach(dLbl => { const el = document.createElement('div'); el.className = 'heat-daylbl'; el.textContent = dLbl; dayCol.appendChild(el); });
  const grid = document.createElement('div'); grid.className = 'heat-grid';
  for (let ri = 0; ri < 7; ri++) {
    const rowEl = document.createElement('div'); rowEl.className = 'heat-row';
    for (let ci = 0; ci < 24; ci++) {
      const v = avg(ri, ci);
      const cell = document.createElement('div'); cell.className = 'heat-cell';
      cell.title = v == null ? `${dayNames[ri]} ${ci}h : ${t('aucune mesure')}` : `${dayNames[ri]} ${ci}h : ${Math.round(v).toLocaleString(_LOCALE)} ${t('W (puissance moyenne)')}`;
      cell.style.background = heatBand(v, maxV);
      rowEl.appendChild(cell);
    }
    grid.appendChild(rowEl);
  }
  wrap.appendChild(dayCol); wrap.appendChild(grid);
  const hours = document.createElement('div'); hours.className = 'heat-hours';
  ['0h', '6h', '12h', '18h', '23h'].forEach(h => { const s = document.createElement('span'); s.textContent = h; hours.appendChild(s); });
  const legend = document.createElement('div'); legend.className = 'heat-legend';
  const lo = document.createElement('span'); lo.textContent = t('Faible'); legend.appendChild(lo);
  HEAT_RAMP.forEach(c => { const sw = document.createElement('div'); sw.className = 'heat-sw'; sw.style.background = c; legend.appendChild(sw); });
  const hi = document.createElement('span'); hi.textContent = t('Élevée'); legend.appendChild(hi);
  container.appendChild(wrap); container.appendChild(hours); container.appendChild(legend);
}

/* ════════════════ Simulateur : instantané, sans attente fabriquée ════════════════ */
function updateSliders() {
  const pctH = ((heures - 0.5) / (6 - 0.5)) * 100;
  const pctW = ((watts - 50) / (3000 - 50)) * 100;
  $('sim-heures-val').textContent = `${heures} h/jour`;
  $('sim-watts-val').textContent = `${watts.toLocaleString(_LOCALE)} W`;
  $('sim-heures').style.background = `linear-gradient(to right,var(--ac) 0%,var(--ac) ${pctH}%,var(--bg-a) ${pctH}%,var(--bg-a) 100%)`;
  $('sim-watts').style.background = `linear-gradient(to right,var(--dv-2) 0%,var(--dv-2) ${pctW}%,var(--bg-a) ${pctW}%,var(--bg-a) 100%)`;
  $('sim-heures').value = heures; $('sim-watts').value = watts;
  document.querySelectorAll('#sim-presets button').forEach(b => b.classList.toggle('on', Number(b.dataset.w) === watts));
  renderSim();
}
function renderSim() {
  const slot = $('sim-result-slot');
  const prix = prixKwh();
  if (!slot) return;
  if (!prix) { slot.innerHTML = `<p class="chart-note">${t('Le prix du kWh apparaîtra dès que votre tarif sera chargé.')}</p>`; return; }
  const kwh = heures * (watts / 1000) * 30;
  const fcfa = Math.round(kwh * prix);
  const bim = periodeType() === 'bimestre';
  slot.innerHTML = `<div class="sim-result">
    <div class="sim-saving">−${fmt(fcfa)} FCFA</div>
    <div class="sim-saving-label">${t("d'économie par mois")}${bim ? ` · −${fmt(fcfa * 2)} FCFA ${t('sur un bimestre')}` : ''}</div>
    <div class="sim-detail"><strong>${fmtKwh(kwh)} kWh</strong> ${t('en moins par mois')} × ${fmtPrix(prix)} F ${t('le kWh (taxes comprises)')}.<br>
    ${t('Hypothèse : un appareil de')} ${watts.toLocaleString(_LOCALE)} W ${t('utilisé')} ${heures} h ${t('de moins par jour, sur 30 jours.')}</div></div>`;
}

/* ════════════════ Crédit prépayé : AOCEDA ne recharge rien (c'est la CIE) ════════════════
   Le crédit part de la dernière LECTURE du compteur (code 170), moins ce que les capteurs mesurent depuis. */
function renderCredit() {
  const card = $('credit-card');
  if (!card) return;
  const prepaid = isPrepaid();
  card.hidden = !prepaid;
  if (!prepaid) return;
  const credit = getCredit();
  const facts = $('credit-facts');
  if (!credit) {
    // Prépayé confirmé mais aucune lecture : on le dit, on ne fabrique aucun solde.
    $('credit-big').textContent = '-';
    $('credit-unit').textContent = t('Pas encore de lecture de votre compteur.');
    $('credit-gauge').style.width = '0%';
    facts.innerHTML = `<div class="fz-fact"><dt>${t('Pour commencer')}</dt><dd>${t('lisez votre compteur et notez-le à droite')}</dd></div>`;
    $('credit-basis').textContent = t('Dès que vous aurez noté le crédit affiché par votre compteur, AOCEDA le suivra pour vous.');
    $('credit-warning').style.display = 'none';
    $('releve-annuler').hidden = true;
    return;
  }
  const kwh = credit.restant_kwh != null ? Number(credit.restant_kwh) : null;
  const restantF = Math.round(Number(credit.restant_fcfa));
  const consomme = Math.round(Number(credit.consomme_fcfa));
  $('credit-big').innerHTML = kwh != null ? `${fmtKwh(kwh)}<small>kWh</small>` : `${fmt(restantF)}<small>FCFA</small>`;
  $('credit-unit').textContent = `≈ ${fmt(restantF)} FCFA ${t('au prix actuel du kWh · estimation')}`;
  const releve = credit.source === 'releve' && credit.releve;
  const base = releve ? Number(credit.releve.kwh) : (kwh != null ? kwh + (prixKwh() ? consomme / prixKwh() : 0) : 0);
  $('credit-gauge').style.width = `${base > 0 && kwh != null ? Math.max(2, Math.min(100, Math.round(kwh / base * 100))) : 0}%`;

  const j = credit.jours_restants;
  // Au-delà de 60 jours le modèle ne prévoit plus : « 60+ » plutôt qu'un « 2065 jours » absurde
  const jours = j == null ? t('pas encore connu') : (!credit.fin_estimee && j > 60 ? '60+' : String(j));
  const rows = [[t('Jours de crédit restants'), j == null ? `<span class="fz-dim">${jours}</span>` : `${jours} <span class="fz-dim">${t('jours')}</span>`]];
  rows.push([t('Fin prévue'), finCreditHtml(credit)]);
  rows.push([t('Dernière lecture du compteur'), releve
    ? `${fmtKwh(credit.releve.kwh)} kWh <span class="fz-dim">${t('le')} ${esc(new Date(credit.releve.le).toLocaleDateString(_LOCALE, { day: 'numeric', month: 'long' }))}</span>`
    : `<span class="fz-dim">${t('aucune : crédit initial enregistré par votre technicien')}</span>`]);
  facts.innerHTML = rows.map(([k, v]) => `<div class="fz-fact"><dt>${k}</dt><dd>${v}</dd></div>`).join('');

  $('credit-basis').textContent =
    (releve
      ? `${t('Lu sur votre compteur le')} ${new Date(credit.releve.le).toLocaleDateString(_LOCALE, { day: 'numeric', month: 'long' })} : ${fmtKwh(credit.releve.kwh)} kWh, ${t('moins ce que vos capteurs ont mesuré depuis')} (${fmt(consomme)} FCFA).`
      : `${t('Crédit initial enregistré')} (${fmt(Math.round(Number(credit.recharge_fcfa)))} FCFA) ${t('moins le coût de ce que vos capteurs ont mesuré depuis')} (${fmt(consomme)} FCFA).`) +
    (credit.cout_jour_fcfa != null ? ` ${t('Vous dépensez environ')} ${fmt(Math.round(Number(credit.cout_jour_fcfa)))} FCFA ${t('par jour')}.` : ` ${t('Votre rythme journalier sera connu après une journée complète de mesures.')}`);
  $('credit-warning').style.display = (j != null && j <= 4) ? '' : 'none';
  $('releve-annuler').hidden = !releve;
}
function jourFin(d) { return d.toLocaleDateString(_LOCALE, { weekday: 'long', day: 'numeric', month: 'long' }); }
function heureFin(d) { const h = d.getMinutes() >= 30 ? d.getHours() + 1 : d.getHours(); return h >= 24 ? t('minuit') : `${h} h`; }
function finCreditHtml(credit) {
  const fin = credit.fin_estimee ? new Date(credit.fin_estimee) : null;
  if (!fin) return `<span class="fz-dim">${t('dans plus de deux mois')}</span>`;
  const tot = credit.fin_tot ? new Date(credit.fin_tot) : null;
  const tard = credit.fin_tard ? new Date(credit.fin_tard) : null;
  const court = d => d.toLocaleDateString(_LOCALE, { weekday: 'short', day: 'numeric', month: 'short' });
  const plage = tot && tard && court(tot) !== court(tard)
    ? ` <span class="fz-dim">(${t('entre')} ${esc(court(tot))} ${t('et')} ${esc(court(tard))})</span>` : '';
  return `${esc(jourFin(fin))}${credit.heure_fiable ? ` ${t('vers')} ${heureFin(fin)}` : ''}${plage}`;
}

function majCreditApresAction(data) {
  const c = data ? data.credit_prepaye : null;
  if (facture) facture.credit_prepaye = c;
  if (summary) summary.credit_prepaye = c;
  renderCredit();
  chargerPrevision();     // l'énergie à prévoir d'ici la fin du mois dépend aussi du crédit
}
function envoyerReleve(corps) {
  const fb = $('releve-feedback'), btn = $('releve-btn');
  if (btn) btn.disabled = true;
  if (fb) { fb.style.color = ''; fb.textContent = t('Enregistrement…'); }
  window.AOCEDA.authFetch('/api/analytics/credit/releve/', { method: 'POST', body: JSON.stringify(corps) })
    .then(res => res.json().catch(() => null).then(data => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (btn) btn.disabled = false;
      if (ok && data) {
        majCreditApresAction(data);
        const input = $('releve-input'); if (input) input.value = '';
        if (fb) { fb.style.color = 'var(--ok)'; fb.textContent = data.detail; }
      } else if (fb) { fb.style.color = 'var(--err)'; fb.textContent = (data && data.detail) || t("Impossible d'enregistrer la lecture."); }
    })
    .catch(() => { if (btn) btn.disabled = false; if (fb) { fb.style.color = 'var(--err)'; fb.textContent = t("Impossible d'enregistrer la lecture."); } });
}
function releveCompteur() {
  const input = $('releve-input');
  const v = String(input ? input.value : '').trim();
  if (!/^\d+([.,]\d+)?$/.test(v.replace(/\s/g, ''))) {
    const fb = $('releve-feedback');
    if (fb) { fb.style.color = 'var(--err)'; fb.textContent = t('Saisissez le crédit affiché par votre compteur, en kWh (ex. 183,5).'); }
    return;
  }
  envoyerReleve({ kwh: v.replace(/\s/g, '') });
}

/* ════════════════ Exports : la PÉRIODE de facturation (avant : le mois civil, même pour un bimestre) ════════════════ */
function exportCSV() {
  if (exporting) return;
  exporting = true;
  const btn = $('btn-export-csv');
  btn.disabled = true;
  $('export-label').textContent = t('Export en cours…');
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const fmtD = dt => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
  const debut = (facture && facture.periode && facture.periode.debut) || fmtD(new Date(now.getFullYear(), now.getMonth(), 1));
  downloadCSV(`/api/analytics/export/?date_from=${debut}&date_to=${fmtD(now)}`, 'aoceda_mesures_periode.csv')
    .catch(err => console.error(err))
    .finally(() => { exporting = false; btn.disabled = false; $('export-label').textContent = t('Mesures (CSV)'); });
}
function exportPDF() {
  if (exportingPdf) return;
  exportingPdf = true;
  const btn = $('btn-export-pdf'), lbl = $('pdf-label');
  if (btn) btn.disabled = true;
  if (lbl) lbl.textContent = t('Export en cours…');
  downloadCSV('/api/analytics/export/rapport-mensuel/', 'aoceda_rapport_periode.pdf')
    .catch(err => console.error(err))
    .finally(() => { exportingPdf = false; if (btn) btn.disabled = false; if (lbl) lbl.textContent = t('Rapport PDF'); });
}

/* ════════════════ Estimation de fin de période ════════════════ */
function renderPrevision() {
  const el = $('prevision-card');
  if (!el) return;
  const p = prevision;
  if (!p || p.mode === 'vide') { el.style.display = 'none'; return; }
  el.style.display = '';
  const prepaid = p.type_compteur === 'prepaye';
  const bimestre = (p.periode && p.periode.type === 'bimestre');
  const titre = prepaid ? t('Dépense estimée en fin de mois')
    : (bimestre ? t('Facture estimée en fin de bimestre') : t('Facture estimée en fin de mois'));
  const head = (chipTxt, chipCls) =>
    `<header class="fz-hd fz-hd-row prev-head"><div><h2 class="fz-title">${esc(titre)} ${infoTip(t(TIP.titre))}</h2><p class="fz-sub">${t('Une estimation, pas une promesse')}</p></div>` +
    `<span class="prev-chip ${chipCls}">${esc(t(chipTxt))} ${infoTip(t(TIP.confiance), 'right')}</span></header>`;

  if (p.mode === 'trop_tot') {
    const k = Math.max(0, Math.min(Number(p.k) || 0, p.n_min));
    const steps = Array.from({ length: p.n_min }, (_, i) => `<span class="prev-step${i < k ? ' on' : ''}" aria-hidden="true"></span>`).join('');
    el.innerHTML = head(t('Trop tôt'), 'pc-tot') +
      `<div class="prev-steps-row"><div class="prev-steps">${steps}</div>` +
      `<span class="prev-steps-lbl">${k}/${p.n_min} ${t('journées complètes mesurées')} ${infoTip(t(TIP.tropTot))}</span></div>` +
      `<p class="prev-tot-msg">${t("Une <strong>journée complète</strong> = un jour où le capteur a mesuré quasiment toute la journée. L'estimation attend d'avoir <strong>{n_min} journées complètes</strong>. En attendant, voici ce qui est déjà certain :").replace('{n_min}', p.n_min)}</p>` +
      (prepaid ? '' : `<div class="prev-certain"><span>${bimestre ? t('Abonnement fixe du bimestre') : t('Abonnement fixe du mois')} ${infoTip(t(TIP.fixe))}</span><strong>${fmt(p.fixe_certain)} F</strong></div>`);
    return;
  }
  const confMap = { fiable: [t('Fiable'), 'pc-ok'], indicative: [t('Indicative'), 'pc-ind'], indicative_trous: [t('Indicative'), 'pc-ind'] };
  const conf = confMap[p.confiance] || [t('Estimation'), 'pc-ind'];
  const HOME = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></svg>';
  const BOLT = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';
  const lo = Number(p.bill_low) || 0, hi = Number(p.bill_high) || 0, mid = Number(p.bill_central) || 0;
  const pct = hi > lo ? Math.min(94, Math.max(6, (mid - lo) / (hi - lo) * 100)) : 50;
  const rangeBar =
    `<div class="prev-bar" role="img" aria-label="${t("Fourchette d'estimation : basse {low} FCFA, attendue {central} FCFA, haute {high} FCFA").replace('{low}', fmt(lo)).replace('{central}', fmt(mid)).replace('{high}', fmt(hi))}">` +
      `<div class="prev-bar-track"><span class="prev-bar-dot" style="left:${pct}%"></span></div>` +
      `<div class="prev-bar-lbls"><span>${t('Basse')}<br><strong>${fmt(lo)} F</strong></span>` +
      `<span class="pbl-mid" style="left:${pct}%">${t('Attendue')}<br><strong>≈ ${fmt(mid)} F</strong></span>` +
      `<span>${t('Haute')}<br><strong>${fmt(hi)} F</strong></span></div></div>`;
  const trous = p.offline_days > 0
    ? `<p class="prev-warn">${p.offline_days} jour${p.offline_days > 1 ? 's' : ''} ${t("sans données, estimé(s) à votre consommation habituelle, à confirmer. Votre facture réelle « à ce jour » n'est jamais gonflée.")}</p>` : '';
  const large = p.mode === 'band_large' ? `<p class="prev-note">${t('Fourchette encore large : elle se resserrera après 1-2 journées complètes de plus.')}</p>` : '';
  el.innerHTML = head(conf[0], conf[1]) +
    `<div class="prev-range">${t('entre')} <strong>${fmt(lo)}</strong> ${t('et')} <strong>${fmt(hi)}</strong> <span class="prev-unit">FCFA</span> ${infoTip(t(TIP.fourchette))}</div>` +
    rangeBar +
    `<div class="prev-split">` +
      (prepaid ? '' : `<div class="prev-part pp-fixed"><span class="pp-ico">${HOME}</span><span class="pp-txt"><span class="pp-lbl">${t('Abonnement fixe')} ${infoTip(t(TIP.fixe))}</span><span class="pp-sub">${t("certain, dû quoi qu'il arrive")}</span></span><span class="pp-val">${fmt(p.fixe_certain)} F</span></div>`) +
      `<div class="prev-part pp-conso"><span class="pp-ico">${BOLT}</span><span class="pp-txt"><span class="pp-lbl">${t('Consommation')} ${infoTip(t(TIP.conso))}</span><span class="pp-sub">${t("estimée d'après votre rythme")}</span></span><span class="pp-val">~ ${fmt(p.variable_estime)} F</span></div>` +
    `</div>` +
    `<div class="prev-basis">${t('Basé sur')} ${p.k} ${t(p.k > 1 ? 'journées réelles de mesures' : 'journée réelle de mesures')} · ${t('consommation estimée')} ≈ ${fmtKwh(p.projected_kwh)} kWh</div>` +
    meteoPrevision(p) + trous + large +
    (prepaid && p.recharge_conseillee != null
      ? `<div class="prev-recharge">${t('Pour finir le mois sans coupure : énergie à acheter à la CIE ≈')} <strong>${fmt(p.recharge_conseillee)} FCFA</strong> ${infoTip(t(TIP.recharge))}</div>` : '');
}
function meteoPrevision(p) {
  const m = p.meteo;
  if (!m) return '';
  if (!m.disponible) return `<p class="prev-meteo">${t('Météo indisponible : estimation faite avec vos seules habitudes.')}</p>`;
  if (m.t_prevue == null || m.t_habituelle == null) return '';
  const un = v => Number(v).toLocaleString(_LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const e = Number(m.effet_chaleur_kwh || 0);
  const effet = Math.abs(e) < 0.05 ? t('sans effet notable sur votre consommation') : `${e > 0 ? '+' : '−'}${un(Math.abs(e))} kWh ${t('prévus à cause de la chaleur')}`;
  return `<p class="prev-meteo">${t('Météo')} ${esc(m.ville)} : <strong>${un(m.t_prevue)} °C</strong> ${t('en moyenne les prochains jours, pour')} ${un(m.t_habituelle)} °C ${t("d'habitude")} · ${effet}</p>`;
}

/* ════════════════ Chargement ════════════════ */
function majRangee() {
  const row = $('row-info');
  if (!row) return;
  const n = [...row.children].filter(c => !c.hidden && c.style.display !== 'none').length;
  row.style.setProperty('--n', String(Math.max(1, n)));
}
function tout() {
  applyTheme();
  renderProgress(); renderHero(); renderBudget(); renderTranche(); renderTarif(); renderCredit();
  renderHisto(); renderSim(); renderPrevision(); majRangee();
}
function chargerPrevision() {
  return fetchWithAuth('/api/analytics/prevision/')
    .then(data => { prevision = data; renderPrevision(); renderBudget(); majRangee(); })
    .catch(err => console.error(err));
}
function chargerJours() {
  const debut = (facture && facture.periode && facture.periode.debut) || (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-01`; })();
  return fetchWithAuth(`/api/analytics/historique/?date_from=${debut}`)
    .then(data => { joursMonth = (data && Array.isArray(data.jours)) ? data.jours : []; joursError = false; joursLoaded = true; renderChart(); })
    .catch(() => { joursError = true; joursLoaded = true; renderChart(); });
}
function chargerTout() {
  const f = fetchWithAuth('/api/analytics/facture/')
    .then(data => { facture = (data && data.tranche1) ? data : null; if (data && !data.tranche1 && data.credit_prepaye) { facture = { credit_prepaye: data.credit_prepaye, type_compteur: data.type_compteur }; } })
    .catch(err => console.error(err))
    .then(() => { tout(); return chargerJours(); });
  fetchWithAuth('/api/analytics/summary/').then(d => { summary = d; tout(); }).catch(err => console.error(err));
  fetchWithAuth('/api/analytics/tarif/').then(d => { tarif = d; tout(); }).catch(err => console.error(err));
  fetchWithAuth('/api/alertes/tranche/').then(d => { tranche = d; renderTranche(); majRangee(); }).catch(() => { tranche = null; renderTranche(); majRangee(); });
  fetchWithAuth('/api/analytics/historique-mensuel/').then(d => { moisHisto = (d && Array.isArray(d.mois)) ? d.mois : []; renderHisto(); renderChart(); }).catch(err => console.error(err));
  chargerPrevision();
  return f;
}

function init() {
  applyTheme();
  renderProgress(); renderHero(); renderBudget(); renderChart(); renderHeatmap(); updateSliders(); renderCredit(); renderPrevision();
  initBudget();

  $('theme-toggle').addEventListener('click', () => { theme = window.AOCEDA.toggleTheme(); applyTheme(); renderChart(); });
  document.querySelectorAll('.filter-row .pill').forEach(p => {
    p.addEventListener('click', () => {
      chartPeriod = p.dataset.period;
      document.querySelectorAll('.filter-row .pill').forEach(x => {
        const on = x.dataset.period === chartPeriod;
        x.classList.toggle('active', on); x.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      renderChart();
    });
  });

  $('sim-heures').addEventListener('input', e => { heures = +e.target.value; updateSliders(); });
  $('sim-watts').addEventListener('input', e => { watts = +e.target.value; updateSliders(); });
  $('sim-presets').addEventListener('click', e => { const b = e.target.closest('button[data-w]'); if (b) { watts = Number(b.dataset.w); updateSliders(); } });

  $('btn-export-csv').addEventListener('click', exportCSV);
  const pdfBtn = $('btn-export-pdf'); if (pdfBtn) pdfBtn.addEventListener('click', exportPDF);

  const releveBtn = $('releve-btn'); if (releveBtn) releveBtn.addEventListener('click', releveCompteur);
  const releveInput = $('releve-input');
  if (releveInput) releveInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); releveCompteur(); } });
  const releveAnnuler = $('releve-annuler'); if (releveAnnuler) releveAnnuler.addEventListener('click', () => envoyerReleve({ annuler: true }));

  chargerTout();
  fetchWithAuth('/api/analytics/heatmap/')
    .then(data => { heatCells = (data && Array.isArray(data.cells)) ? data.cells : []; heatError = false; heatLoaded = true; renderHeatmap(); })
    .catch(() => { heatError = true; heatLoaded = true; renderHeatmap(); });
}

init();
