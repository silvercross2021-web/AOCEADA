'use strict';
/* ════════════════════════════════════════════════════════════════
   AOCEDA — Comportements communs du shell de l'espace client
   Chargé (defer) AVANT le JS spécifique de chaque page.
   Gère : bloc utilisateur, déconnexion, badge d'alertes,
   navigation mobile (bottom-nav + FAB), animations d'entrée.
   N.B. : le bouton de thème (#theme-toggle) reste géré par chaque
   page (certaines doivent recréer leurs graphiques au changement).
   ════════════════════════════════════════════════════════════════ */
(function () {

  /* ════════════════════════════════════════════════════════════════
     Helper d'API authentifié PARTAGÉ (exposé sur window.AOCEDA).
     Ajoute le jeton Bearer et, sur 401, tente UN rafraîchissement via
     /api/auth/refresh/ avant de rejouer la requête. En cas d'échec du
     refresh, purge les jetons et renvoie vers /auth/.
     Les pages délèguent leur propre fetchWithAuth à window.AOCEDA.authFetch.
     ════════════════════════════════════════════════════════════════ */
  const TOKEN_KEY = 'aoceda_access_token';
  const REFRESH_KEY = 'aoceda_refresh_token';
  let refreshing = null;

  function refreshAccessToken() {
    if (refreshing) return refreshing;
    const rt = localStorage.getItem(REFRESH_KEY);
    if (!rt) return Promise.reject(new Error('no-refresh'));
    refreshing = fetch('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: rt })
    })
      .then(res => { if (!res.ok) throw new Error('refresh-failed'); return res.json(); })
      .then(data => {
        localStorage.setItem(TOKEN_KEY, data.access);
        if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
        return data.access;
      })
      .finally(() => { refreshing = null; });
    return refreshing;
  }

  function buildOptions(options, token) {
    const headers = Object.assign({}, options.headers || {});
    // En-tête JSON par défaut (sauf override explicite ou FormData)
    if (!('Content-Type' in headers) && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return Object.assign({}, options, { headers });
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  function forceAuth() {
    logout();
    window.location.href = '/auth/';
  }

  /** Renvoie une Promise<Response> ; gère le refresh transparent sur 401. */
  function authFetch(url, options = {}) {
    const token = localStorage.getItem(TOKEN_KEY);
    return fetch(url, buildOptions(options, token)).then(res => {
      if (res.status !== 401) return res;
      // Jeton expiré → tentative de rafraîchissement puis rejeu unique
      return refreshAccessToken()
        .then(newToken => fetch(url, buildOptions(options, newToken)))
        .catch(() => { forceAuth(); throw new Error('Non autorisé'); });
    });
  }

  window.AOCEDA = window.AOCEDA || {};
  window.AOCEDA.authFetch = authFetch;
  window.AOCEDA.refreshAccessToken = refreshAccessToken;
  window.AOCEDA.logout = logout;
  /** Normalise une réponse API liste (paginée ou non) en tableau simple. */
  window.AOCEDA.asList = function(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.results)) return data.results;
    return [];
  };

  function shellFetch(url) {
    const tk = localStorage.getItem(TOKEN_KEY);
    if (!tk) return Promise.reject(new Error('no-token'));
    return authFetch(url).then(res => { if (!res.ok) throw new Error('http-' + res.status); return res.json(); });
  }

  function escText(el, txt) { if (el) el.textContent = txt; }

  document.addEventListener('DOMContentLoaded', function () {

    /* ── 1. Lien actif de la sidebar et de la bottom-nav ── */
    const path = window.location.pathname;
    document.querySelectorAll('.sb-nav .nav-item').forEach(a => {
      const hrefPath = (a.getAttribute('href') || '').split('#')[0];
      a.classList.toggle('active', hrefPath === path);
    });
    document.querySelectorAll('.bottom-nav .bn-item').forEach(b => {
      const href = (b.dataset.href || '').split('#')[0];
      b.classList.toggle('active', href === path);
    });

    /* ── 2. Bloc utilisateur (sidebar) ── */
    shellFetch('/api/users/me/').then(me => {
      const nom = me.nom || 'Utilisateur';
      const initiales = nom.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || 'U';
      escText(document.getElementById('user-avatar'), initiales);
      escText(document.getElementById('hdr-user-chip'), initiales);
      escText(document.getElementById('user-name'), nom);
      const role = document.getElementById('user-role');
      if (role) {
        if (me.role === 'technicien') {
          const parts = ['Technicien'];
          if (me.specialite) parts.push(me.specialite);
          escText(role, parts.join(' · '));
        } else if (me.role === 'admin') {
          escText(role, 'Administrateur');
        } else {
          const morceaux = [];
          if (me.adresse) morceaux.push(me.adresse);
          if (me.numeroCIE) morceaux.push(me.numeroCIE);
          escText(role, morceaux.join(' · ') || 'Compte client');
        }
      }
    }).catch(() => { /* silencieux : la page gère déjà la redirection auth */ });

    /* ── 3. Badge d'alertes non lues (sidebar + cloche) ── */
    shellFetch('/api/alertes/').then(alertes => {
      const liste = Array.isArray(alertes) ? alertes : (alertes.results || []);
      const nonLues = liste.filter(a => !a.lue).length;
      const badge = document.getElementById('nav-alert-badge');
      if (badge) {
        badge.textContent = String(nonLues);
        badge.style.display = nonLues > 0 ? '' : 'none';
      }
      const dot = document.getElementById('notif-dot');
      if (dot) dot.style.display = nonLues > 0 ? '' : 'none';
    }).catch(() => {});

    /* ── 4. Déconnexion ── */
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn && !logoutBtn.dataset.boundShell) {
      logoutBtn.dataset.boundShell = '1';
      logoutBtn.addEventListener('click', function () {
        localStorage.removeItem('aoceda_access_token');
        localStorage.removeItem('aoceda_refresh_token');
        window.location.href = '/';
      });
    }

    /* ── 5. Cloche de notifications → page Alertes ── */
    const notifBtn = document.getElementById('notif-btn');
    if (notifBtn && !notifBtn.dataset.boundShell) {
      notifBtn.dataset.boundShell = '1';
      notifBtn.addEventListener('click', function () {
        window.location.href = '/alertes/';
      });
    }

    /* ── 6. Navigation mobile : bottom-nav et FAB ── */
    document.querySelectorAll('[data-href]').forEach(el => {
      if (el.dataset.boundShell) return;
      el.dataset.boundShell = '1';
      el.addEventListener('click', () => { window.location.href = el.dataset.href; });
    });

    /* ── 7. Animation d'entrée en cascade du contenu ── */
    const blocs = document.querySelectorAll('.content > *');
    blocs.forEach((bloc, i) => {
      bloc.classList.add('anim-in');
      bloc.style.animationDelay = Math.min(i * 70, 420) + 'ms';
    });

    /* ── 8. Shadow header au scroll ── */
    const headerEl = document.querySelector('.header');
    const contentEl = document.querySelector('.content');
    if (headerEl && contentEl) {
      contentEl.addEventListener('scroll', function () {
        headerEl.classList.toggle('scrolled', contentEl.scrollTop > 4);
      }, { passive: true });
    }
  });
})();
