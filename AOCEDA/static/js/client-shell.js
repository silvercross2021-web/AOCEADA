'use strict';
/* ════════════════════════════════════════════════════════════════
   AOCEDA, Comportements communs du shell de l'espace client
   Chargé (defer) AVANT le JS spécifique de chaque page.
   Gère : bloc utilisateur, déconnexion, badge d'alertes,
   navigation mobile (bottom-nav + FAB), animations d'entrée.
   Gère aussi la résolution PARTAGÉE du thème clair/sombre/auto
   (window.AOCEDA.resolveTheme/getThemeChoice/applyTheme/setThemeChoice/
   toggleTheme) ; le clic sur #theme-toggle reste câblé par chaque page
   (certaines doivent recréer leurs graphiques au changement) mais DOIT
   appeler window.AOCEDA.toggleTheme() pour rester cohérent partout.
   ════════════════════════════════════════════════════════════════ */
(function () {
  let currentUser = null;

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

  /* Même détection/miroir natif qu'auth.js : on se fie à la présence de l'interface JS
     native window.AndroidTokenStore (attachée par MainActivity.java, disponible sur toute
     origine), plus fiable que le seul marqueur User-Agent. Le stockage SharedPreferences
     survit à un changement d'IP LAN, contrairement à localStorage (scopé par origine).
     ROTATE_REFRESH_TOKENS=True côté serveur (settings.py) : chaque refresh renvoie un
     NOUVEAU refresh token à remiroiter ici, sinon le store natif garde un jeton révoqué. */
  function saveNativeSession(access, refresh) {
    if (window.AndroidTokenStore) {
      try {
        window.AndroidTokenStore.save(
          access || '', refresh || '', localStorage.getItem('aoceda_user_role') || ''
        );
      } catch (e) {}
    }
  }
  function clearNativeSession() {
    if (window.AndroidTokenStore) {
      try { window.AndroidTokenStore.clear(); } catch (e) {}
    }
  }

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
        saveNativeSession(data.access, data.refresh || rt);
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
    // Évite qu'un rôle/avatar en cache ne survive à la déconnexion, au cas où un
    // autre utilisateur se connecterait ensuite sur ce même appareil.
    localStorage.removeItem('aoceda_user_role');
    localStorage.removeItem('aoceda_user_avatar_cache');
    clearNativeSession();
  }

  /* App native : réhydrate localStorage depuis le store natif si l'origine courante n'a
     PAS de session (cas d'un changement d'IP LAN → nouvelle origine → localStorage vide,
     alors que le store SharedPreferences, lui, a survécu). Exécuté au chargement de
     client-shell.js (defer), donc AVANT le JS spécifique de la page et son 1er appel API. */
  (function rehydrateFromNativeStore() {
    if (!window.AndroidTokenStore) return;
    try {
      if (!localStorage.getItem(TOKEN_KEY) && !localStorage.getItem(REFRESH_KEY)) {
        var a = window.AndroidTokenStore.getAccess();
        var r = window.AndroidTokenStore.getRefresh();
        var role = window.AndroidTokenStore.getRole();
        if (a) localStorage.setItem(TOKEN_KEY, a);
        if (r) localStorage.setItem(REFRESH_KEY, r);
        if (role) localStorage.setItem('aoceda_user_role', role);
      }
    } catch (e) {}
  })();

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

  /** Déclenche le téléchargement d'un Blob déjà récupéré (export CSV/PDF/rapport…),
     avec le bon nom de fichier. Sur le web, un Blob + <a download> suffit (le
     navigateur gère le dossier Téléchargements). Dans l'app native (WebView nue,
     sans intégration navigateur), ce clic ne fait RIEN — voir MainActivity.java →
     NativeDownloader, qui écrit réellement le fichier sur le disque via un pont JS
     natif. Remplace 5 copies quasi identiques de ce code par page (historique.js,
     interventions.js, parametres.js, previsions.js, technicien.js). */
  window.AOCEDA.downloadBlob = function(blob, filename) {
    if (window.NativeDownloader) {
      const reader = new FileReader();
      reader.onload = () => {
        // reader.result = "data:<mime>;base64,<data>" → ne garder que la partie base64
        const base64 = String(reader.result).split(',')[1] || '';
        try { window.NativeDownloader.saveBase64(base64, filename, blob.type || 'application/octet-stream'); }
        catch (e) { console.error(e); }
      };
      reader.readAsDataURL(blob);
      return;
    }
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(objUrl);
  };

  /* ════════════════════════════════════════════════════════════════
     THÈME (partagé) : source de vérité UNIQUE pour la résolution
     clair/sombre/auto, utilisée par le script anti-flash de chaque
     page ET par le #theme-toggle de chaque page.
     - 'aoceda-theme-choice' = préférence utilisateur : 'light' | 'dark' | 'auto'
       (par défaut 'auto' → suit le système, y compris en direct si l'OS change).
     - 'aoceda-theme' = thème EFFECTIF déjà résolu (cache anti-flash).
     ════════════════════════════════════════════════════════════════ */
  const THEME_KEY = 'aoceda-theme';
  const THEME_CHOICE_KEY = 'aoceda-theme-choice';

  function resolveTheme(choice) {
    if (choice === 'light' || choice === 'dark') return choice;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }

  function getThemeChoice() { return localStorage.getItem(THEME_CHOICE_KEY) || 'auto'; }

  /** Applique + persiste le thème EFFECTIF (n'écrit pas le choix). */
  function applySharedTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem(THEME_KEY, t);
    return t;
  }

  /** Change le choix utilisateur ('light' | 'dark' | 'auto') et applique le thème résolu. */
  function setThemeChoice(choice) {
    localStorage.setItem(THEME_CHOICE_KEY, choice);
    return applySharedTheme(resolveTheme(choice));
  }

  /** Bascule clair<->dark ET fige ce choix explicite (sort du mode « auto »). */
  function toggleSharedTheme() {
    const next = (document.documentElement.getAttribute('data-theme') === 'light') ? 'dark' : 'light';
    return setThemeChoice(next);
  }

  window.AOCEDA.resolveTheme = resolveTheme;
  window.AOCEDA.getThemeChoice = getThemeChoice;
  window.AOCEDA.applyTheme = applySharedTheme;
  window.AOCEDA.setThemeChoice = setThemeChoice;
  window.AOCEDA.toggleTheme = toggleSharedTheme;

  // Mode « auto » : si l'utilisateur n'a jamais figé de choix explicite,
  // suit le thème du système EN DIRECT (sans recharger la page).
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (getThemeChoice() !== 'auto') return;
      const t = applySharedTheme(e.matches ? 'dark' : 'light');
      window.dispatchEvent(new CustomEvent('aoceda-theme-changed', { detail: { theme: t } }));
    });
  }

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
    // Demander l'accord pour les notifications
    if (window.Notification && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }

    const t = window.AOCEDA_T || (x => x);
    /* ── 1. Lien actif de la sidebar et de la bottom-nav ── */
    const path = window.location.pathname;
    document.querySelectorAll('.sb-nav .nav-item').forEach(a => {
      const hrefPath = (a.getAttribute('href') || '').split('#')[0];
      a.classList.toggle('active', hrefPath === path);
    });
    document.querySelectorAll('.bottom-nav .bn-item[data-href], .bn-sheet .bn-item[data-href]').forEach(b => {
      const href = (b.dataset.href || '').split('#')[0];
      b.classList.toggle('active', href === path);
    });
    // Le bouton « Plus » de la barre s'allume si la page courante est un des
    // items repliés dans la feuille (ex. /interventions/, /ia/, /parametres/).
    const moreBtn = document.getElementById('bn-more-btn');
    if (moreBtn) {
      const sheetHrefs = [...document.querySelectorAll('.bn-sheet [data-href]')].map(b => (b.dataset.href || '').split('#')[0]);
      moreBtn.classList.toggle('active', sheetHrefs.includes(path));
    }

    /* ── 2. Bloc utilisateur (sidebar) ── */
    // Anti-flash avatar : /api/users/me/ est un aller-retour réseau à CHAQUE
    // navigation (ce n'est pas une SPA, chaque page recharge le shell depuis zéro).
    // Sans cache, l'avatar/nom du header revient au placeholder "?" du template à
    // chaque clic de menu, le temps que la réponse arrive — c'est le flash observé.
    // On applique le dernier avatar CONNU immédiatement (synchrone, avant tout
    // fetch), puis on laisse la requête réelle corriger si besoin (photo changée...).
    const AVATAR_CACHE_KEY = 'aoceda_user_avatar_cache';
    function applyAvatarData(el, photo, initiales) {
      if (!el) return;
      if (photo) {
        el.textContent = '';
        el.style.backgroundImage = 'url("' + photo + '")';
        el.style.backgroundSize = 'cover';
        el.style.backgroundPosition = 'center';
      } else {
        el.style.backgroundImage = '';
        escText(el, initiales);
      }
    }
    try {
      const cached = JSON.parse(localStorage.getItem(AVATAR_CACHE_KEY) || 'null');
      if (cached) {
        applyAvatarData(document.getElementById('user-avatar'), cached.photo, cached.initiales);
        applyAvatarData(document.getElementById('hdr-user-chip'), cached.photo, cached.initiales);
        escText(document.getElementById('user-name'), cached.nom);
      }
    } catch (e) {}

    shellFetch('/api/users/me/').then(me => {
      currentUser = me;

      // Route guards according to role
      const isTechPath = window.location.pathname.includes('/technicien');
      if (isTechPath) {
        if (me.role !== 'technicien') {
          window.location.href = '/dashboard/';
          return;
        }
      } else {
        const clientPaths = ['/dashboard', '/historique', '/alertes', '/ia', '/previsions', '/parametres'];
        const isClientPath = clientPaths.some(p => window.location.pathname.startsWith(p));
        if (isClientPath && me.role === 'technicien') {
          window.location.href = '/technicien/';
          return;
        }
      }

      const nom = me.nom || t('Utilisateur');
      const initiales = nom.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || 'U';
      // Photo de profil si présente, sinon initiales — appliqué partout (sidebar + header).
      applyAvatarData(document.getElementById('user-avatar'), me.photo, initiales);
      applyAvatarData(document.getElementById('hdr-user-chip'), me.photo, initiales);
      escText(document.getElementById('user-name'), nom);
      try {
        localStorage.setItem(AVATAR_CACHE_KEY, JSON.stringify({ photo: me.photo || '', initiales, nom }));
      } catch (e) {}
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
    // null = pas encore de relevé de référence (1er appel de la session) : on ne
    // doit JAMAIS déclencher l'alarme sur ce premier relevé, même s'il existe déjà
    // des alertes critiques non lues en base (backlog d'une session précédente) —
    // seule une AUGMENTATION observée pendant la session en cours doit sonner.
    let lastUnreadCount = null;
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
        if (currentUser && currentUser.role === 'technicien') {
          if (window.location.pathname.includes('/technicien/')) {
            if (typeof window.setSection === 'function') {
              window.setSection('interventions');
            }
          } else {
            localStorage.setItem('aoceda_tech_target_section', 'interventions');
            window.location.href = '/technicien/';
          }
        } else {
          if (window.location.pathname !== '/alertes/') {
             window.location.href = '/alertes/';
          }
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
        
        // Vibration physique du téléphone synchrone avec le bip
        if (navigator.vibrate) {
          navigator.vibrate(200);
        }
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
      // Arrête immédiatement la vibration
      if (navigator.vibrate) {
        navigator.vibrate(0);
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

        // Alarme uniquement si le nombre a AUGMENTÉ depuis le dernier relevé connu
        // DE CETTE SESSION (jamais sur le tout premier relevé, où nonLues peut déjà
        // inclure un backlog d'alertes critiques non lues laissées par une session
        // précédente — ce n'est pas un événement « nouveau »).
        if (lastUnreadCount !== null && nonLues > lastUnreadCount) {
          const critAlert = liste.find(a => !a.lue && a.sévérité === 'Critique');
          if (critAlert) {
            startAlarm(critAlert.message);
          }
        }
        lastUnreadCount = nonLues;
      }).catch(() => {});
    }

    checkAlerts();
    setInterval(checkAlerts, 15000); // Poll every 15s

    /* ── 4. Déconnexion ── */
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn && !logoutBtn.dataset.boundShell) {
      logoutBtn.dataset.boundShell = '1';
      logoutBtn.addEventListener('click', function () {
        // Best-effort : journalise la déconnexion avant de purger les jetons.
        // Ne bloque jamais la navigation (fire-and-forget, y compris en échec réseau).
        const tok = localStorage.getItem('aoceda_access_token');
        if (tok) {
          fetch('/api/auth/logout/', { method: 'POST', headers: { Authorization: 'Bearer ' + tok } }).catch(() => {});
        }
        // logout() partagé (purge aussi le rôle en cache ET le stockage natif de l'app,
        // voir plus haut) — dupliquer la purge ici avait fait dériver ce bouton du reste.
        logout();
        window.location.href = '/auth/';
      });
    }

    /* ── 5. Cloche de notifications ── */
    const notifBtn = document.getElementById('notif-btn');
    if (notifBtn && !notifBtn.dataset.boundShell) {
      notifBtn.dataset.boundShell = '1';
      notifBtn.addEventListener('click', function () {
        if (currentUser && currentUser.role === 'technicien') {
          if (window.location.pathname.includes('/technicien/')) {
            if (typeof window.setSection === 'function') {
              window.setSection('interventions');
            }
          } else {
            localStorage.setItem('aoceda_tech_target_section', 'interventions');
            window.location.href = '/technicien/';
          }
        } else {
          window.location.href = '/alertes/';
        }
      });
    }

    /* ── 6. Navigation mobile : bottom-nav et FAB ── */
    document.querySelectorAll('[data-href]').forEach(el => {
      if (el.dataset.boundShell) return;
      el.dataset.boundShell = '1';
      el.addEventListener('click', () => { window.location.href = el.dataset.href; });
    });

    /* ── 6bis. Feuille « Plus » (items débordant la bottom-nav mobile) ──
       Générique : fonctionne aussi bien pour les items data-href (pages client,
       navigation classique) que data-section (technicien, SPA one-page) — dans
       les deux cas on referme juste la feuille après le clic d'un item. */
    const bnSheet = document.getElementById('bn-sheet');
    const bnMoreBtn = document.getElementById('bn-more-btn');
    if (bnSheet && bnMoreBtn) {
      const setSheetOpen = (open) => {
        bnSheet.hidden = false; // reste dans le DOM, la classe pilote l'affichage/transition
        requestAnimationFrame(() => bnSheet.classList.toggle('open', open));
        bnMoreBtn.setAttribute('aria-expanded', String(open));
        if (!open) setTimeout(() => { if (!bnSheet.classList.contains('open')) bnSheet.hidden = true; }, 250);
      };
      bnMoreBtn.addEventListener('click', () => setSheetOpen(!bnSheet.classList.contains('open')));
      bnSheet.querySelectorAll('[data-bn-sheet-close]').forEach(el => el.addEventListener('click', () => setSheetOpen(false)));
      bnSheet.querySelectorAll('.bn-sheet-item').forEach(el => el.addEventListener('click', () => setSheetOpen(false)));
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setSheetOpen(false); });
    }

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

/* ════════════════════════════════════════════════════════════════
   Infobulles « i » (.itip) : portail body-appended, clampé aux bords
   d'écran, piloté par tap/clic (PAS de :hover CSS) — identique en
   souris (desktop), tactile (web mobile) et WebView (APK). Échappe
   à tout ancêtre overflow:hidden puisque #itip-bubble est ajouté
   directement à <body> en position:fixed. Voir client-shell.css
   pour le style ; script partagé par toutes les pages qui utilisent
   `<button class="itip" data-tip="…">`, y compris le markup généré
   dynamiquement (historique.js/previsions.js).
   ════════════════════════════════════════════════════════════════ */
(function () {
  let bubble = null;
  let openTrigger = null;

  function ensureBubble() {
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.id = 'itip-bubble';
      document.body.appendChild(bubble);
    }
    return bubble;
  }

  function closeTip() {
    if (bubble) bubble.classList.remove('show');
    if (openTrigger) openTrigger.classList.remove('is-open');
    openTrigger = null;
  }

  function openTip(trigger) {
    const text = trigger.getAttribute('data-tip');
    if (!text) return;
    const b = ensureBubble();
    b.textContent = text;
    b.classList.add('show');
    trigger.classList.add('is-open');
    openTrigger = trigger;

    // Position calculée APRÈS affichage (offsetWidth/Height requièrent un rendu) puis
    // clampée aux bords de l'écran — jamais de bulle coupée sur un téléphone étroit.
    const r = trigger.getBoundingClientRect();
    const margin = 8;
    const bw = b.offsetWidth, bh = b.offsetHeight;
    let left = r.left + r.width / 2 - bw / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - bw - margin));
    let top = r.top - bh - margin;
    if (top < margin) top = r.bottom + margin; // pas assez de place au-dessus → bascule en dessous
    b.style.left = left + 'px';
    b.style.top = top + 'px';
  }

  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('.itip');
    if (trigger) {
      e.preventDefault();
      e.stopPropagation();
      if (openTrigger === trigger) { closeTip(); return; }
      openTip(trigger);
      return;
    }
    if (openTrigger) closeTip();
  });
  document.addEventListener('scroll', closeTip, true);
  window.addEventListener('resize', closeTip);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeTip(); });
})();

/* ════════════════════════════════════════════════════════════════
   Bannière « connexion perdue » — UNIQUEMENT dans l'app native (voir
   consigne explicite du client : le web/desktop garde son comportement
   actuel, non touché). Contrairement à un vrai navigateur, cette app
   pointe vers une IP LAN configurée par l'utilisateur (voir
   mobile_app/www/index.html) — si le PC s'éteint ou le Wi-Fi coupe en
   cours d'usage, les pages restaient bloquées en silence (squelette de
   chargement indéfini) sans jamais dire à l'utilisateur ce qui se passe.
   navigator.onLine n'est pas fiable seul (reste souvent "true" tant que
   le Wi-Fi est associé, même si le serveur cible est injoignable) : on
   vérifie donc aussi par un ping léger périodique vers le serveur.
   ════════════════════════════════════════════════════════════════ */
(function () {
  if (!window.AndroidTokenStore) return; // web/desktop : inchangé

  let banner = null;
  function ensureBanner() {
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'conn-lost-banner';
      banner.innerHTML = '<span class="conn-lost-dot"></span><span>Connexion perdue. Nouvelle tentative…</span>';
      document.body.appendChild(banner);
    }
    return banner;
  }
  function showBanner() { ensureBanner().classList.add('show'); }
  function hideBanner() { if (banner) banner.classList.remove('show'); }

  window.addEventListener('offline', showBanner);
  window.addEventListener('online', hideBanner);
  if (navigator.onLine === false) showBanner();

  function pingServer() {
    fetch(window.location.origin + '/favicon.ico?t=' + Date.now(), { method: 'HEAD', cache: 'no-store' })
      .then(() => hideBanner())
      .catch(() => showBanner());
  }
  setInterval(pingServer, 8000);
})();


