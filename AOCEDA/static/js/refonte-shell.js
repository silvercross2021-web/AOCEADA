/* ════════════════════════════════════════════════════════════════
   AOCEDA, REFONTE VISUELLE : habillage de l'en-tête (présentation)
   ────────────────────────────────────────────────────────────────
   Ce fichier ne fait AUCUN appel réseau et ne calcule AUCUNE donnée.
   Il se contente de :
     1. regrouper nom + rôle (déjà chargés par client-shell.js) sous
        l'avatar de l'en-tête, comme la maquette ;
     2. faire de la barre de recherche un raccourci vers les pages
        déjà présentes dans le menu de gauche.
   Le retirer n'enlève que cet habillage : rien d'autre n'en dépend.
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  /* ── 1) Identité : [avatar] [nom / rôle] [chevron] ──
     client-shell.js construit .hdr-user à la volée : on attend qu'il existe. */
  function initUser() {
    var actions = document.querySelector('.hdr-actions');
    if (!actions) return;

    function build() {
      var btn = actions.querySelector('.hdr-user');
      var nameSpan = btn && btn.querySelector('.hdr-user-name');
      if (!btn || !nameSpan) return false;
      if (btn.dataset.rfBuilt) return true;
      btn.dataset.rfBuilt = '1';

      var box = document.createElement('span');
      box.className = 'hdr-user-txt';
      btn.insertBefore(box, nameSpan);
      box.appendChild(nameSpan);

      var role = document.createElement('span');
      role.className = 'hdr-user-role';
      box.appendChild(role);

      var srcRole = document.getElementById('user-role');
      function syncRole() {
        var v = srcRole ? (srcRole.textContent || '').trim() : '';
        role.textContent = v.split(' · ')[0];   // 1er segment : tient sur une ligne
      }
      syncRole();
      if (srcRole) {
        try { new MutationObserver(syncRole).observe(srcRole, { childList: true, characterData: true, subtree: true }); } catch (e) {}
      }
      return true;
    }

    if (build()) return;
    try {
      var mo = new MutationObserver(function () { if (build()) mo.disconnect(); });
      mo.observe(actions, { childList: true, subtree: true });
    } catch (e) {}
  }

  /* ── 2) Recherche : raccourci vers les pages de l'espace client ──
     La liste est celle du menu de gauche : aucune donnée n'est interrogée. */
  function initSearch() {
    var wrap = document.getElementById('rf-search');
    var input = document.getElementById('rf-search-input');
    var list = document.getElementById('rf-search-list');
    if (!wrap || !input || !list) return;

    var PAGES = [];
    Array.prototype.forEach.call(document.querySelectorAll('.sb-nav .nav-item'), function (a) {
      var label = a.querySelector('span');
      if (label) PAGES.push({ t: label.textContent.trim(), h: a.getAttribute('href') });
    });
    PAGES.push({ t: 'Mes capteurs', h: '/parametres/#capteurs' });

    var idx = -1, shown = [];
    function norm(s) { return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }

    function open(o) {
      list.hidden = !o;
      input.setAttribute('aria-expanded', String(!!o));
      wrap.classList.toggle('open', !!o);
    }
    function mark() {
      Array.prototype.forEach.call(list.children, function (li, i) { li.classList.toggle('on', i === idx); });
    }
    function go(i) { if (shown[i]) window.location.href = shown[i].h; }

    function render(q) {
      var nq = norm(q);
      shown = nq ? PAGES.filter(function (p) { return norm(p.t).indexOf(nq) !== -1; }) : PAGES.slice(0);
      list.innerHTML = '';
      if (!shown.length) {
        var li = document.createElement('li');
        li.className = 'rf-search-empty';
        li.textContent = 'Aucune page ne correspond';
        list.appendChild(li);
      } else {
        shown.forEach(function (p, i) {
          var it = document.createElement('li');
          it.setAttribute('role', 'option');
          it.tabIndex = -1;
          it.textContent = p.t;
          it.addEventListener('mousedown', function (e) { e.preventDefault(); go(i); });
          list.appendChild(it);
        });
      }
      idx = -1;
      open(true);
    }

    input.addEventListener('focus', function () { render(input.value); });
    input.addEventListener('input', function () { render(input.value); });
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, shown.length - 1); mark(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, 0); mark(); }
      else if (e.key === 'Enter') { e.preventDefault(); go(idx === -1 ? 0 : idx); }
      else if (e.key === 'Escape') { open(false); input.blur(); }
    });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) open(false); });
  }

  /* ── 3) Rail « Résumé » ──
        a. le texte d'attente s'efface dès que la synthèse (#insight-strip,
           remplie par historique.js) devient visible ;
        b. la pastille de période recopie la plage déjà affichée (#date-range).
        Aucune valeur n'est calculée ici. */
  function initRail() {
    var strip = document.getElementById('insight-strip');
    var empty = document.getElementById('rail-empty');
    if (strip && empty) {
      var sync = function () { empty.hidden = !strip.hidden; };
      sync();
      try { new MutationObserver(sync).observe(strip, { attributes: true, attributeFilter: ['hidden'] }); } catch (e) {}
    }

    var src = document.getElementById('date-range');
    var pill = document.getElementById('rail-period');
    if (src && pill) {
      var syncPill = function () {
        var v = (src.textContent || '').trim();
        var ok = v && v.indexOf('Chargement') !== 0 && v.indexOf('Erreur') !== 0 && v.indexOf('Aucune') !== 0;
        pill.textContent = ok ? v : '';
        pill.hidden = !ok;
      };
      syncPill();
      try { new MutationObserver(syncPill).observe(src, { childList: true, characterData: true, subtree: true }); } catch (e) {}
    }
  }

  /* ── 4) Raccourcis d'en-tête vers un bouton déjà présent dans la page.
        Ils ne font que relayer le clic : aucune logique nouvelle. ── */
  function initProxyButtons() {
    var target = document.getElementById('goto-config-btn');
    if (!target) return;
    ['rf-goto-config', 'rf-goto-config-2'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('click', function () { target.click(); });
    });
  }

  ready(function () { initUser(); initSearch(); initRail(); initProxyButtons(); });
})();
