'use strict';
/* ════════════════════════════════════════════════════════════════
   AOCEDA, Comportements communs du shell de l'espace client
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

  /* Transforme le chip avatar du header en MENU utilisateur (nom + avatar + chevron)
     avec un panneau déroulant au clic : nom/email, Paramètres (clients), Déconnexion.
     Idempotent (dataset.menuBuilt). Le nom est placé À GAUCHE de l'avatar. */
  function buildHeaderUserMenu(me, nom) {
    const chip = document.getElementById('hdr-user-chip');
    if (!chip || chip.dataset.menuBuilt) return;
    chip.dataset.menuBuilt = '1';

    const wrap = document.createElement('div');
    wrap.className = 'hdr-user-wrap';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'hdr-user';
    btn.setAttribute('aria-haspopup', 'true');
    btn.setAttribute('aria-expanded', 'false');
    const t = window.AOCEDA_T || (x => x);
    btn.setAttribute('aria-label', t('Menu du compte'));

    const nameSpan = document.createElement('span');
    nameSpan.className = 'hdr-user-name';
    nameSpan.textContent = nom;

    const chev = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chev.setAttribute('class', 'hdr-user-chev');
    chev.setAttribute('width', '15'); chev.setAttribute('height', '15');
    chev.setAttribute('viewBox', '0 0 24 24'); chev.setAttribute('fill', 'none');
    chev.setAttribute('stroke', 'currentColor'); chev.setAttribute('stroke-width', '2');
    chev.setAttribute('stroke-linecap', 'round'); chev.setAttribute('stroke-linejoin', 'round');
    chev.innerHTML = '<polyline points="6 9 12 15 18 9"/>';

    // Insère le wrapper là où était le chip, puis déplace le chip DANS le bouton
    // (il garde sa photo/initiales déjà appliquées) : [nom] [avatar] [chevron].
    chip.parentNode.insertBefore(wrap, chip);
    btn.appendChild(nameSpan);
    btn.appendChild(chip);
    btn.appendChild(chev);
    wrap.appendChild(btn);

    const menu = document.createElement('div');
    menu.className = 'hdr-user-menu';
    menu.hidden = true;

    const head = document.createElement('div');
    head.className = 'hum-head';
    const hn = document.createElement('div'); hn.className = 'hum-name'; hn.textContent = nom;
    head.appendChild(hn);
    if (me.email) { const hm = document.createElement('div'); hm.className = 'hum-mail'; hm.textContent = me.email; head.appendChild(hm); }
    menu.appendChild(head);

    // Lien Paramètres (espace client uniquement : technicien/admin ont leur propre espace)
    if (me.role === 'client' || !me.role) {
      const a = document.createElement('a');
      a.className = 'hum-item'; a.href = '/parametres/';
      a.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg><span>' + t('Paramètres') + '</span>';
      menu.appendChild(a);
    }

    const out = document.createElement('button');
    out.type = 'button';
    out.className = 'hum-item hum-logout';
    out.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg><span>' + t('Déconnexion') + '</span>';
    out.addEventListener('click', function () { logout(); window.location.href = '/'; });
    menu.appendChild(out);

    wrap.appendChild(menu);

    function setOpen(open) { menu.hidden = !open; btn.setAttribute('aria-expanded', String(open)); }
    btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(menu.hidden); });
    document.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
    menu.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  document.addEventListener('DOMContentLoaded', function () {

    const t = window.AOCEDA_T || (x => x);
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
      const nom = me.nom || t('Utilisateur');
      const initiales = nom.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || 'U';
      // Photo de profil si présente, sinon initiales — appliqué partout (sidebar + header).
      const applyAvatar = (el) => {
        if (!el) return;
        if (me.photo) {
          el.textContent = '';
          el.style.backgroundImage = 'url("' + me.photo + '")';
          el.style.backgroundSize = 'cover';
          el.style.backgroundPosition = 'center';
        } else {
          el.style.backgroundImage = '';
          escText(el, initiales);
        }
      };
      applyAvatar(document.getElementById('user-avatar'));
      applyAvatar(document.getElementById('hdr-user-chip'));
      escText(document.getElementById('user-name'), nom);
      const role = document.getElementById('user-role');
      if (role) {
        if (me.role === 'technicien') {
          const parts = [t('Technicien')];
          if (me.specialite) parts.push(me.specialite);
          escText(role, parts.join(' · '));
        } else if (me.role === 'admin') {
          escText(role, t('Administrateur'));
        } else {
          const morceaux = [];
          if (me.adresse) morceaux.push(me.adresse);
          if (me.numeroCIE) morceaux.push(me.numeroCIE);
          escText(role, morceaux.join(' · ') || t('Compte client'));
        }
      }

      /* Menu utilisateur du HEADER (nom + avatar + chevron → dropdown), façon finpay.
         Construit AUTOUR du chip existant → présent sur toutes les pages sans toucher
         à chaque template. Le bloc identité de la sidebar (.sb-user) est masqué en CSS. */
      buildHeaderUserMenu(me, nom);
    }).catch(() => { /* silencieux : la page gère déjà la redirection auth */ });

    /* ── 3. Badge d'alertes non lues et Alarme Sonore Continue ── */
    let lastUnreadCount = 0;
    let alarmInterval = null;
    let alarmCtx = null;
    let activeAlarmModal = null;
    
    function createAlarmModal(message) {
      if (activeAlarmModal) return;
      const overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.inset = '0';
      overlay.style.backgroundColor = 'rgba(0,0,0,0.7)';
      overlay.style.zIndex = '9999';
      overlay.style.display = 'flex';
      overlay.style.alignItems = 'center';
      overlay.style.justifyContent = 'center';
      overlay.style.padding = '20px';
      overlay.style.backdropFilter = 'blur(4px)';

      const modal = document.createElement('div');
      modal.style.background = 'var(--bg-s, #fff)';
      modal.style.padding = '24px';
      modal.style.borderRadius = '16px';
      modal.style.boxShadow = '0 10px 40px rgba(0,0,0,0.3)';
      modal.style.maxWidth = '400px';
      modal.style.width = '100%';
      modal.style.textAlign = 'center';
      modal.style.border = '1px solid var(--bd-s, #E5E7EB)';

      const icon = document.createElement('div');
      icon.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--err, #C32D22)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
      icon.style.marginBottom = '16px';
      // Animation pulse sur l'icône
      icon.style.animation = 'cs-pulse 1.5s infinite';

      const title = document.createElement('h3');
      title.textContent = t('Alerte Critique !');
      title.style.margin = '0 0 8px 0';
      title.style.fontFamily = 'var(--fd, sans-serif)';
      title.style.fontSize = '20px';
      title.style.color = 'var(--tx-p, #000)';

      const desc = document.createElement('p');
      desc.textContent = message || t('Une nouvelle alerte nécessite votre attention immédiate.');
      desc.style.margin = '0 0 24px 0';
      desc.style.fontSize = '14px';
      desc.style.color = 'var(--tx-s, #555)';
      desc.style.lineHeight = '1.5';

      const btn = document.createElement('button');
      btn.textContent = t('Couper l\'alarme et voir');
      btn.style.width = '100%';
      btn.style.padding = '14px';
      btn.style.border = 'none';
      btn.style.borderRadius = '8px';
      btn.style.backgroundColor = 'var(--err, #C32D22)';
      btn.style.color = '#fff';
      btn.style.fontSize = '15px';
      btn.style.fontWeight = 'bold';
      btn.style.cursor = 'pointer';

      btn.addEventListener('click', () => {
        stopAlarm();
        document.body.removeChild(overlay);
        activeAlarmModal = null;
        if (window.location.pathname !== '/alertes/') {
           window.location.href = '/alertes/';
        }
      });

      modal.appendChild(icon);
      modal.appendChild(title);
      modal.appendChild(desc);
      modal.appendChild(btn);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      activeAlarmModal = overlay;
    }

    function beep() {
      try {
        if (!alarmCtx) {
           const AudioContext = window.AudioContext || window.webkitAudioContext;
           if (!AudioContext) return;
           alarmCtx = new AudioContext();
        }
        if (alarmCtx.state === 'suspended') alarmCtx.resume();
        const osc = alarmCtx.createOscillator();
        const gain = alarmCtx.createGain();
        osc.connect(gain);
        gain.connect(alarmCtx.destination);
        osc.type = 'square'; // Son plus strident pour alarme
        osc.frequency.setValueAtTime(880, alarmCtx.currentTime); // A5
        osc.frequency.setValueAtTime(1046.50, alarmCtx.currentTime + 0.15); // C6
        gain.gain.setValueAtTime(0.3, alarmCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, alarmCtx.currentTime + 0.4);
        osc.start(alarmCtx.currentTime);
        osc.stop(alarmCtx.currentTime + 0.4);
      } catch(e){}
    }

    function startAlarm(message) {
      const isEnabled = localStorage.getItem('aoceda-alarm-enabled') !== 'false';
      if (isEnabled) {
         if (!alarmInterval) {
            beep();
            alarmInterval = setInterval(beep, 1200); // Bip toutes les 1.2s
         }
      }
      createAlarmModal(message);
    }

    function stopAlarm() {
      if (alarmInterval) {
        clearInterval(alarmInterval);
        alarmInterval = null;
      }
      if (alarmCtx) {
        alarmCtx.close().catch(()=>{});
        alarmCtx = null;
      }
    }

    function checkAlerts() {
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

        // Si le nombre d'alertes non lues augmente et qu'il y a une critique non lue
        if (nonLues > lastUnreadCount && lastUnreadCount !== -1) {
          const critAlert = liste.find(a => !a.lue && a.sévérité === 'Critique');
          if (critAlert) {
            startAlarm(critAlert.message);
          }
        }
        // Init state
        if (lastUnreadCount === 0) lastUnreadCount = -1;
        else lastUnreadCount = nonLues;
      }).catch(() => {});
    }

    checkAlerts();
    setInterval(checkAlerts, 15000); // Poll every 15s

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

    /* ── 9. Traduction Complète (Langue Dynamique) ── */
    // Géré automatiquement par Google Translate dans i18n.js
  });
})();


