/* Page « Interventions & pannes » du client.
   Refaite le 20/10/2026 : tout texte venu du serveur est ÉCHAPPÉ (avant, description, nom et téléphone du technicien
   étaient injectés tels quels dans le HTML), choix de l'appareil concerné, suivi visuel de la demande, résultat des
   travaux, annulation d'une demande en attente, signalement « le problème persiste » toujours possible, actualisation
   automatique, fenêtre accessible, plus aucun alert(). */
(function () {
  'use strict';

  const token = localStorage.getItem('aoceda_access_token');
  if (!token && window.location.pathname.indexOf('/auth/') === -1) { window.location.href = '/auth/'; return; }

  const $ = id => document.getElementById(id);
  const A = () => window.AOCEDA;

  /* ── Thème ── */
  const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
  const themeToggleBtn = $('theme-toggle');
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    if (themeToggleBtn) themeToggleBtn.innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
  }
  applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
  if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => applyTheme(A().toggleTheme()));

  const container = $('interventions-container');
  const filtersEl = $('iv-filters');

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const nl2br = s => esc(s).replace(/\r?\n/g, '<br>');

  const TYPES = {
    PANNE: { label: 'Panne', ico: '<path d="M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 1 5.4-5.4l-2.5 2.5"/>' },
    CALIBRATION: { label: 'Valeurs à vérifier (calibration)', ico: '<path d="M12 20V10M18 20V4M6 20v-4"/>' },
    MAINTENANCE: { label: 'Contrôle de l’installation', ico: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>' },
    INSTALLATION: { label: 'Installation de capteur', ico: '<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="3"/>' },
    DIAGNOSTIC: { label: 'Diagnostic', ico: '<circle cx="11" cy="11" r="7"/><line x1="20" y1="20" x2="16.7" y2="16.7"/>' },
  };
  const STATUTS = {
    EN_ATTENTE: { label: 'En attente de prise en charge', cls: 'status-pending', groupe: 'ouvertes' },
    EN_COURS: { label: 'En cours d’intervention', cls: 'status-active', groupe: 'ouvertes' },
    TERMINEE: { label: 'Terminée', cls: 'status-done', groupe: 'terminees' },
    ANNULEE: { label: 'Annulée', cls: 'status-cancelled', groupe: 'annulees' },
  };
  const FILTRES = [['toutes', 'Toutes'], ['ouvertes', 'En cours'], ['terminees', 'Terminées'], ['annulees', 'Annulées']];

  const state = { items: [], status: 'loading', filtre: 'toutes', signature: '', derniere: 0, capteurs: null, ouvrir: null };

  const fmtDate = d => new Date(d).toLocaleString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const fmtJour = d => new Date(d).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
  function duree(depuis) {
    const min = Math.max(0, Math.round((Date.now() - new Date(depuis).getTime()) / 60000));
    if (min < 60) return `${Math.max(1, min)} min`;
    if (min < 1440) { const h = Math.round(min / 60); return `${h} heure${h > 1 ? 's' : ''}`; }
    const j = Math.round(min / 1440);
    return `${j} jour${j > 1 ? 's' : ''}`;
  }
  const ouverte = it => it.statut === 'EN_ATTENTE' || it.statut === 'EN_COURS';

  /* ── Message bref (remplace alert()) ── */
  let toastTimer = null;
  function toast(msg, erreur) {
    const el = $('iv-toast'); if (!el) return;
    el.textContent = msg; el.hidden = false; el.className = `iv-toast${erreur ? ' err' : ''}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, erreur ? 7000 : 4000);
  }
  async function messageErreur(res, defaut) {
    try {
      const d = await res.json();
      const m = [];
      Object.keys(d || {}).forEach(k => { const v = d[k]; m.push(Array.isArray(v) ? v.join(' ') : (typeof v === 'string' ? v : '')); });
      const txt = m.filter(Boolean).join(' ');
      if (txt) return txt;
    } catch (e) { /* corps non JSON */ }
    return defaut;
  }

  /* ── Rendu ── */
  function etapes(it) {
    if (it.statut === 'ANNULEE') return '';
    const pas = [['Demande envoyée', 'done'],
      ['Prise en charge', it.statut === 'EN_ATTENTE' ? 'todo' : (it.statut === 'EN_COURS' ? 'current' : 'done')],
      ['Terminée', it.statut === 'TERMINEE' ? 'done' : 'todo']];
    if (it.statut === 'EN_ATTENTE') pas[1][1] = 'current-wait';
    return `<ol class="iv-steps" aria-label="Avancement de la demande">${pas.map(([l, c]) =>
      `<li class="iv-step is-${c}"><span class="iv-dot" aria-hidden="true"></span><span>${l}</span></li>`).join('')}</ol>`;
  }

  /* Ce qui va se passer, en une phrase : le client sait toujours quelle est la suite */
  function prochaine(it) {
    if (it.statut === 'EN_ATTENTE') return '<p class="iv-next"><strong>Et maintenant ?</strong> Un technicien va prendre votre demande en charge. Vous serez prévenu dans « Alertes » (et par e-mail si vous l’avez activé).</p>';
    if (it.statut === 'EN_COURS') return '<p class="iv-next"><strong>Et maintenant ?</strong> Le technicien s’occupe de votre demande. Le résultat apparaîtra ici dès qu’il aura terminé.</p>';
    return '';
  }

  function cardHtml(it) {
    const type = TYPES[it.typeIntervention] || { label: it.typeIntervention || 'Intervention', ico: TYPES.MAINTENANCE.ico };
    const st = STATUTS[it.statut] || { label: it.statut, cls: 'status-cancelled', groupe: 'annulees' };
    const open = ouverte(it);
    const id = esc(it.id);

    let attente = '';
    if (it.statut === 'EN_ATTENTE') attente = `<span class="iv-wait">En attente depuis ${duree(it.dateIntervention)}</span>`;
    else if (it.statut === 'EN_COURS') attente = '<span class="iv-wait">Votre technicien s’en occupe</span>';

    let prevu = '';
    if (it.dateProgrammee && open) {
      const passe = new Date(it.dateProgrammee).getTime() < Date.now();
      prevu = `<div class="ic-planned${passe ? ' is-late' : ''}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        <span>${passe ? 'Rendez-vous prévu le' : 'Intervention prévue le'} ${esc(fmtDate(it.dateProgrammee))}${passe ? ' : la date est passée, contactez votre technicien.' : ''}</span></div>`;
    }

    const desc = String(it.description || '').trim();
    const longue = desc.length > 260 || desc.split('\n').length > 4;
    const descHtml = desc
      ? `<div class="ic-desc${longue ? ' is-clamped' : ''}" id="desc-${id}">${nl2br(desc)}</div>${longue ? `<button type="button" class="iv-more" data-more="${id}" aria-expanded="false" aria-controls="desc-${id}">Voir tout</button>` : ''}`
      : '<div class="ic-desc iv-muted">Aucune description fournie.</div>';

    let lien = '';
    if (it.interventionOrigine && it.origine_date) lien = `<span class="iv-chip">Suite à l’intervention du ${esc(fmtJour(it.origine_date))}</span>`;
    if (it.suivis_ouverts > 0) lien += '<span class="iv-chip warn">Un signalement « le problème persiste » est en cours</span>';

    const resultat = (it.statut === 'TERMINEE' && it['résultat'] && String(it['résultat']).trim())
      ? `<div class="iv-result"><strong>Résultat des travaux</strong><p>${nl2br(String(it['résultat']).trim())}</p></div>` : '';
    const noteAnnul = (it.statut === 'ANNULEE' && it['résultat']) ? `<div class="iv-muted iv-note">${esc(it['résultat'])}</div>` : '';

    const tel = it.technicien_telephone ? String(it.technicien_telephone).replace(/[^\d+]/g, '') : '';
    const tech = it.technicien_nom
      ? `<span class="ic-tech">Technicien : <strong>${esc(it.technicien_nom)}</strong>${tel ? ` · <a href="tel:${esc(tel)}" class="iv-tel">${esc(it.technicien_telephone)}</a>` : ''}</span>`
      : '<span class="ic-tech"></span>';

    const pdf = (it.statut === 'TERMINEE' && it.rapport)
      ? `<button class="btn-pdf" data-pdf="${id}" type="button"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>Télécharger le rapport (PDF)</button>` : '';
    const annuler = it.statut === 'EN_ATTENTE'
      ? `<span class="iv-cancel" data-cancel-zone="${id}"><button class="btn-link danger" data-cancel="${id}" type="button">Annuler la demande</button>
         <span class="iv-confirm" hidden>Annuler cette demande ? <button class="btn-link danger" data-cancel-yes="${id}" type="button">Oui, annuler</button> <button class="btn-link" data-cancel-no="${id}" type="button">Non</button></span></span>` : '';

    return `<article class="inter-card is-${open ? 'open' : (it.statut === 'TERMINEE' ? 'done' : 'cancelled')}" data-id="${id}" id="iv-${id}">
      <div class="ic-header">
        <span class="ic-type"><span class="ic-ico" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${type.ico}</svg></span>${esc(type.label)}</span>
        <span class="status-badge ${st.cls}">${esc(st.label)}</span>
      </div>
      <div class="ic-meta"><span class="ic-date">Demandée le ${esc(fmtDate(it.dateIntervention))}</span>${it.capteur_nom ? `<span class="iv-chip">${esc(it.capteur_nom)}</span>` : ''}${attente}</div>
      ${prevu}
      ${open ? etapes(it) : ''}
      ${prochaine(it)}
      ${descHtml}
      ${lien ? `<div class="iv-chips">${lien}</div>` : ''}
      ${resultat}${noteAnnul}
      <div class="ic-footer">${tech}<span class="iv-actions">${pdf}${annuler}</span></div>
      ${it.statut === 'TERMINEE' ? feedbackHtml(it) : ''}
    </article>`;
  }

  function feedbackHtml(it) {
    const signal = it.suivis_ouverts > 0 ? ''
      : `<button type="button" class="btn-signal" data-origine="${esc(it.id)}">Le problème persiste ? Le signaler</button>`;
    if (it.dateRetourClient) {
      const n = Number(it.satisfactionClient) || 0;
      return `<div class="ic-feedback"><div class="fb-row"><div class="fb-done">Votre avis : <span class="fb-stars-ro" aria-label="${n} sur 5">${n ? '★'.repeat(n) + '☆'.repeat(5 - n) : '-'}</span>${it.commentaireClient ? `<div class="fb-comment-ro">${nl2br(it.commentaireClient)}</div>` : ''}</div>${signal}</div></div>`;
    }
    return `<div class="ic-feedback" data-feedback-id="${esc(it.id)}">
      <span class="fb-label" id="fbl-${esc(it.id)}">Que pensez-vous de cette intervention ?</span>
      <div class="fb-stars" data-selected="0" role="group" aria-labelledby="fbl-${esc(it.id)}">
        ${[1, 2, 3, 4, 5].map(n => `<button type="button" class="fb-star" data-star="${n}" aria-pressed="false" aria-label="${n} étoile${n > 1 ? 's' : ''} sur 5">★</button>`).join('')}
      </div>
      <input type="text" class="fb-comment" placeholder="Un commentaire ? (facultatif)" maxlength="500" aria-label="Commentaire sur l'intervention">
      <div class="fb-row"><button type="button" class="fb-submit" disabled>Envoyer mon avis</button>${signal}</div>
    </div>`;
  }

  function trier(list) {
    const ouv = list.filter(ouverte).sort((a, b) => new Date(a.dateProgrammee || a.dateIntervention) - new Date(b.dateProgrammee || b.dateIntervention));
    const reste = list.filter(x => !ouverte(x)).sort((a, b) => new Date(b.dateIntervention) - new Date(a.dateIntervention));
    return [ouv, reste];
  }
  function compter() {
    const c = { toutes: state.items.length, ouvertes: 0, terminees: 0, annulees: 0 };
    state.items.forEach(i => { const g = (STATUTS[i.statut] || {}).groupe; if (g) c[g]++; });
    return c;
  }
  function renderFiltres() {
    const c = compter();
    filtersEl.hidden = state.status !== 'ok' || state.items.length === 0;
    filtersEl.innerHTML = FILTRES.map(([k, l]) =>
      `<button type="button" class="fpill${state.filtre === k ? ' active' : ''}" data-filter="${k}" aria-pressed="${state.filtre === k}">${l} (${c[k]})</button>`).join('');
  }

  function render() {
    container.setAttribute('aria-busy', state.status === 'loading' ? 'true' : 'false');
    renderFiltres();
    if (state.status === 'loading') {
      container.innerHTML = '<div class="iv-skel" aria-hidden="true"><span class="skel"></span><span class="skel"></span><span class="skel"></span></div>';
      return;
    }
    if (state.status === 'error') {
      container.innerHTML = `<div class="iv-empty is-error"><strong>Impossible de charger vos demandes.</strong><p>Vos interventions existent toujours : seul l’affichage a échoué.</p><button type="button" class="btn-declare" data-retry>Réessayer</button></div>`;
      return;
    }
    if (state.items.length === 0) {
      container.innerHTML = `<div class="iv-empty"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TYPES.PANNE.ico}</svg><strong>Aucune intervention pour le moment</strong><p>Si quelque chose ne fonctionne pas, utilisez « Déclarer une panne » : un technicien AOCEDA prendra votre demande en charge.</p></div>`;
      return;
    }
    const [ouv, reste] = trier(state.items);
    const f = state.filtre;
    const sel = x => f === 'toutes' || (STATUTS[x.statut] || {}).groupe === f;
    const a = ouv.filter(sel), b = reste.filter(sel);
    if (!a.length && !b.length) {
      container.innerHTML = `<div class="iv-empty"><strong>Rien dans cette catégorie</strong><p><button type="button" class="btn-link" data-filter="toutes">Voir toutes mes demandes</button></p></div>`;
      return;
    }
    let html = '';
    if (a.length) html += `<h2 class="iv-section">À suivre <span>${a.length}</span></h2>${a.map(cardHtml).join('')}`;
    if (b.length) html += `<h2 class="iv-section">${a.length ? 'Historique' : 'Mes interventions'} <span>${b.length}</span></h2>${b.map(cardHtml).join('')}`;
    container.innerHTML = html;
    if (state.ouvrir) {
      const el = document.getElementById(`iv-${state.ouvrir}`);
      if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 2400); }
      state.ouvrir = null;
    }
  }

  /* ── Chargement ── */
  function charger(opts) {
    const silencieux = !!(opts && opts.silencieux);
    if (!silencieux && state.status !== 'ok') { state.status = 'loading'; render(); }
    return A().authFetch('/api/sensors/interventions/')
      .then(res => { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
      .then(data => {
        const list = A().asList(data);
        state.derniere = Date.now();
        const sig = JSON.stringify(list);
        const changement = sig !== state.signature || state.status !== 'ok';
        state.signature = sig; state.items = list; state.status = 'ok';
        // on ne remplace pas l'écran pendant qu'on écrit un avis : rien n'est perdu
        const ecrit = container.contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
        if (changement && !(silencieux && ecrit)) render(); else if (!silencieux) render();
      })
      .catch(err => {
        console.error(err);
        if (state.status !== 'ok') { state.status = 'error'; render(); }
        else if (!silencieux) toast('Actualisation impossible pour le moment.', true);
      });
  }
  // Les statuts changent quand le technicien agit : actualisation douce, sans toucher à l'écran s'il n'y a rien de neuf
  setInterval(() => { if (!document.hidden) charger({ silencieux: true }); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - state.derniere > 30000) charger({ silencieux: true }); });

  /* ── Actions sur la liste (délégation) ── */
  container.addEventListener('click', e => {
    const t = e.target.closest('button'); if (!t) return;
    if (t.hasAttribute('data-retry')) { charger(); return; }
    if (t.dataset.filter) { state.filtre = t.dataset.filter; render(); return; }
    if (t.dataset.more) {
      const d = $(`desc-${t.dataset.more}`); const ouvert = d.classList.toggle('is-clamped') === false;
      t.textContent = ouvert ? 'Réduire' : 'Voir tout'; t.setAttribute('aria-expanded', String(ouvert)); return;
    }
    if (t.dataset.pdf) { telechargerPdf(t.dataset.pdf, t); return; }
    if (t.dataset.cancel) { const z = t.closest('[data-cancel-zone]'); t.hidden = true; z.querySelector('.iv-confirm').hidden = false; z.querySelector('[data-cancel-no]').focus(); return; }
    if (t.dataset.cancelNo) { const z = t.closest('[data-cancel-zone]'); z.querySelector('.iv-confirm').hidden = true; const b = z.querySelector('[data-cancel]'); b.hidden = false; b.focus(); return; }
    if (t.dataset.cancelYes) { annuler(t.dataset.cancelYes, t); return; }
    if (t.dataset.origine) { ouvrirFenetre({ origine: state.items.find(i => i.id === t.dataset.origine) }); return; }
    if (t.classList.contains('fb-star')) {
      const bloc = t.closest('.ic-feedback'); const wrap = bloc.querySelector('.fb-stars'); const n = Number(t.dataset.star);
      wrap.dataset.selected = String(n);
      wrap.querySelectorAll('.fb-star').forEach(s => { const on = Number(s.dataset.star) <= n; s.classList.toggle('on', on); s.setAttribute('aria-pressed', String(Number(s.dataset.star) === n)); });
      bloc.querySelector('.fb-submit').disabled = false; return;
    }
    if (t.classList.contains('fb-submit')) {
      const bloc = t.closest('.ic-feedback');
      envoyerAvis(bloc.dataset.feedbackId, Number(bloc.querySelector('.fb-stars').dataset.selected) || 0, bloc.querySelector('.fb-comment').value, t);
    }
  });
  filtersEl.addEventListener('click', e => { const b = e.target.closest('[data-filter]'); if (b) { state.filtre = b.dataset.filter; render(); } });

  function envoyerAvis(id, note, commentaire, btn) {
    if (note < 1) return;
    btn.disabled = true; btn.textContent = 'Envoi…';
    A().authFetch(`/api/sensors/interventions/${encodeURIComponent(id)}/retour/`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ satisfactionClient: note, commentaireClient: commentaire || '' }),
    }).then(async res => {
      if (!res.ok) throw new Error(await messageErreur(res, 'Impossible d’enregistrer votre avis. Réessayez.'));
      toast('Merci pour votre avis !'); return charger({ silencieux: true });
    }).catch(err => { btn.disabled = false; btn.textContent = 'Envoyer mon avis'; toast(err.message || 'Impossible d’enregistrer votre avis.', true); });
  }
  function annuler(id, btn) {
    btn.disabled = true;
    A().authFetch(`/api/sensors/interventions/${encodeURIComponent(id)}/annuler/`, { method: 'POST' })
      .then(async res => {
        if (!res.ok) throw new Error(await messageErreur(res, 'Impossible d’annuler la demande.'));
        toast('Demande annulée.'); return charger({ silencieux: true });
      }).catch(err => { btn.disabled = false; toast(err.message, true); charger({ silencieux: true }); });
  }
  function telechargerPdf(id, btn) {
    btn.disabled = true;
    A().authFetch(`/api/sensors/interventions/${encodeURIComponent(id)}/rapport/pdf/`)
      .then(res => { if (!res.ok) throw new Error('pdf'); return res.blob(); })
      .then(blob => A().downloadBlob(blob, `rapport_intervention_${id}.pdf`))
      .catch(() => toast('Impossible de télécharger le rapport pour le moment.', true))
      .finally(() => { btn.disabled = false; });
  }

  /* ── Fenêtre de demande ── */
  const overlay = $('modal-overlay'), form = $('form-intervention'), titre = $('modal-title-text'), sous = $('modal-sub');
  const descField = $('description-intervention'), capSel = $('capteur-intervention'), compteur = $('iv-count');
  const errBox = $('iv-error'), typesBox = $('iv-types'), origineBox = $('iv-origine');
  let origineId = null, ouvreur = null;

  function chargerCapteurs() {
    if (state.capteurs) return Promise.resolve();
    return A().authFetch('/api/sensors/').then(r => r.ok ? r.json() : []).then(d => {
      state.capteurs = A().asList(d);
      capSel.innerHTML = '<option value="">Toute mon installation / je ne sais pas</option>'
        + state.capteurs.map(c => `<option value="${esc(c.id)}">${esc(c.nom || 'Appareil')}</option>`).join('');
    }).catch(() => { state.capteurs = []; });
  }
  function erreur(msg) { errBox.textContent = msg || ''; errBox.hidden = !msg; }
  function majCompteur() { compteur.textContent = `${descField.value.length} / 2000`; }
  descField.addEventListener('input', () => { majCompteur(); if (!errBox.hidden) erreur(''); });

  function ouvrirFenetre(opts) {
    opts = opts || {};
    ouvreur = document.activeElement;
    origineId = opts.origine ? opts.origine.id : null;
    form.reset(); erreur(''); majCompteur();
    typesBox.hidden = !!origineId; origineBox.hidden = !origineId;
    if (origineId) {
      const o = opts.origine;
      titre.textContent = 'Le problème persiste';
      sous.textContent = 'Expliquez ce qui ne va toujours pas : votre technicien reprendra le dossier.';
      origineBox.textContent = `Suite à l’intervention du ${fmtJour(o.dateIntervention)} (${(TYPES[o.typeIntervention] || {}).label || 'intervention'}).`;
      descField.placeholder = 'Décrivez pourquoi le problème persiste malgré l’intervention précédente.';
    } else {
      titre.textContent = 'Déclarer une panne';
      sous.textContent = 'Votre technicien reçoit la demande et vous répond sur cette page.';
      descField.placeholder = 'Ex. : le capteur n’affiche plus de consommation depuis ce matin, le voyant est éteint…';
      if (opts.type) { const r = typesBox.querySelector(`input[value="${opts.type}"]`); if (r) r.checked = true; }
    }
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add('active'));
    document.documentElement.classList.add('iv-lock');
    chargerCapteurs().then(() => {
      const cap = opts.capteur || (opts.origine && opts.origine.capteur);
      if (cap && capSel.querySelector(`option[value="${CSS.escape(String(cap))}"]`)) capSel.value = String(cap);
    });
    setTimeout(() => descField.focus(), 60);
  }
  function fermerFenetre() {
    overlay.classList.remove('active');
    document.documentElement.classList.remove('iv-lock');
    setTimeout(() => { overlay.hidden = true; }, 180);
    origineId = null;
    if (ouvreur && ouvreur.focus && document.contains(ouvreur)) ouvreur.focus();
  }
  $('btn-open-modal').addEventListener('click', () => ouvrirFenetre());
  $('btn-close-modal').addEventListener('click', fermerFenetre);
  $('btn-cancel-modal').addEventListener('click', fermerFenetre);
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) fermerFenetre(); });
  document.addEventListener('keydown', e => {
    if (overlay.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); fermerFenetre(); return; }
    if (e.key !== 'Tab') return;
    const f = [...overlay.querySelectorAll('button, input, select, textarea, a[href]')].filter(x => !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });

  form.addEventListener('submit', e => {
    e.preventDefault();
    const btn = form.querySelector('.btn-submit');
    if (btn.disabled) return;
    const description = descField.value.trim();
    if (description.length < 10) { erreur('Décrivez le problème en quelques mots (10 caractères au moins).'); descField.focus(); return; }
    const payload = { typeIntervention: origineId ? 'PANNE' : (form.querySelector('input[name="type"]:checked') || {}).value || 'PANNE', description };
    if (capSel.value) payload.capteur = capSel.value;
    if (origineId) payload.interventionOrigine = origineId;
    btn.disabled = true; btn.textContent = 'Envoi…'; erreur('');
    A().authFetch('/api/sensors/interventions/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(async res => {
        if (!res.ok) throw new Error(await messageErreur(res, 'Impossible d’enregistrer votre demande. Réessayez.'));
        return res.json();
      })
      .then(nv => {
        fermerFenetre();
        state.filtre = 'toutes'; state.ouvrir = nv && nv.id;
        toast('Demande envoyée : un technicien va la prendre en charge.');
        return charger({ silencieux: true });
      })
      .catch(err => erreur(err.message))
      .finally(() => { btn.disabled = false; btn.textContent = 'Envoyer la demande'; });
  });

  /* ── Démarrage ; liens profonds : ?declarer=1&type=PANNE&capteur=<id> ou ?ouvrir=<id> ── */
  const q = new URLSearchParams(window.location.search);
  const ouvrirId = q.get('ouvrir');
  if (ouvrirId && /^[0-9a-fA-F-]{32,36}$/.test(ouvrirId)) state.ouvrir = ouvrirId;
  render();
  charger().then(() => {
    if (q.get('declarer') === '1') {
      const type = ['PANNE', 'CALIBRATION', 'MAINTENANCE'].includes(q.get('type')) ? q.get('type') : 'PANNE';
      ouvrirFenetre({ type, capteur: q.get('capteur') });
    }
    if (q.has('declarer') || q.has('ouvrir') || q.has('type') || q.has('capteur')) history.replaceState(null, '', window.location.pathname);
  });
})();
