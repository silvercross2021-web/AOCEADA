/* ════════════════════════════════════════════════════════════
   AOCEDA, Page d'authentification (JavaScript vanilla, ES2020)
   Architecture : Django Templates + AJAX (fetch)
   Le squelette HTML vit dans templates/aoceda-auth.html ;
   ce fichier ne contient que la logique (état, AJAX, bascules).

   NB : pas d'auto-inscription. Conformément aux diagrammes de cas
   d'utilisation, le compte client est créé par le Technicien ;
   le Visiteur ne fait que se connecter ou réinitialiser son mot de passe.
   ════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const t = window.AOCEDA_T || (x => x);

  /* ── Helpers ── */
  const $ = (id) => document.getElementById(id);

  /* Détection de l'app native : on teste EN PRIORITÉ la présence de l'interface JS
     native window.AndroidTokenStore (attachée par MainActivity.java via
     addJavascriptInterface — disponible sur TOUTES les origines, y compris le serveur
     Django distant). C'est plus fiable que le seul marqueur User-Agent : si le suffixe
     UA n'était pas appliqué, isNativeApp restait faux et TOUTE la persistance de session
     était désactivée en silence (le refresh token n'était jamais conservé). On garde le
     test UA en repli. window.AndroidTokenStore n'existe QUE dans l'APK — jamais sur le web. */
  const hasNativeStore = (typeof window.AndroidTokenStore !== 'undefined' && window.AndroidTokenStore);
  const isNativeApp = !!hasNativeStore || /AOCEDA-NativeApp/.test(navigator.userAgent);

  /* Miroir de session dans le stockage NATIF (MainActivity.java, SharedPreferences),
     INDÉPENDANT de l'origine actuellement chargée — contrairement à localStorage, qui
     est scopé par origine (http://<IP LAN>:<port>) et perdrait la session si l'IP du
     PC change entre deux ouvertures de l'app. */
  function saveNativeSession(access, refresh, role) {
    if (window.AndroidTokenStore) {
      try { window.AndroidTokenStore.save(access || '', refresh || '', role || ''); } catch (e) {}
    }
  }

  /** Échappe toute donnée injectée en innerHTML. */
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  /* ── Icônes SVG (chaînes statiques, aucune donnée utilisateur) ── */
  const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
  const ICON_EYE_OPEN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  const ICON_EYE_OFF = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
  const ICON_CHECK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  const ICON_CIRCLE = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>';
  const SPINNER = '<div class="spin"></div>';

  /* ════════════════════════════════════
     THÈME CLAIR / SOMBRE
     ════════════════════════════════════ */
  let theme = document.documentElement.getAttribute('data-theme') || 'light';

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('aoceda-theme', theme);
    const btn = $('theme-toggle');
    btn.innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
    btn.setAttribute('aria-label', theme === 'light' ? t('Mode sombre') : t('Mode clair'));
  }

  $('theme-toggle').addEventListener('click', () => {
    theme = theme === 'light' ? 'dark' : 'light';
    // Fige un choix explicite (sort du mode « auto ») pour rester cohérent
    // avec les autres pages de la plateforme après connexion.
    localStorage.setItem('aoceda-theme-choice', theme);
    applyTheme();
  });

  /* ════════════════════════════════════
     OUTILS PARTAGÉS
     ════════════════════════════════════ */

  /* Jauge de force du mot de passe (couleurs = tokens sémantiques) */
  const STR_LBLS = ['', 'Très faible', 'Faible', 'Moyen', 'Fort', 'Très fort'];
  const STR_COLS = ['', 'var(--err)', 'var(--warn)', 'var(--warn)', 'var(--ok)', 'var(--ok)'];

  function pwdScore(p) {
    if (!p) return 0;
    let s = 0;
    if (p.length >= 8) s++;
    if (p.length >= 12) s++;
    if (/[A-Z]/.test(p)) s++;
    if (/[0-9]/.test(p)) s++;
    if (/[^A-Za-z0-9]/.test(p)) s++;
    return s;
  }

  function renderStrength(wrapEl, pwd) {
    if (!pwd) { wrapEl.hidden = true; return; }
    wrapEl.hidden = false;
    const s = pwdScore(pwd);
    wrapEl.querySelectorAll('.sbar').forEach((bar, i) => {
      bar.style.background = (i + 1) <= s ? STR_COLS[s] : 'var(--bd-s)';
    });
    const lbl = wrapEl.querySelector('.str-lbl');
    lbl.textContent = t(STR_LBLS[s]);
    lbl.style.color = STR_COLS[s];
  }

  /* Bouton "œil" afficher / masquer le mot de passe.
     Renvoie une fonction de remise à zéro. */
  function wireEye(btnId, inputId) {
    const btn = $(btnId);
    const input = $(inputId);
    let shown = false;
    const render = () => {
      input.type = shown ? 'text' : 'password';
      btn.innerHTML = shown ? ICON_EYE_OFF : ICON_EYE_OPEN;
    };
    btn.addEventListener('click', () => { shown = !shown; render(); });
    render();
    return () => { shown = false; render(); };
  }

  /* ════════════════════════════════════
     BASCULE ENTRE LES VUES
     ════════════════════════════════════ */
  const views = {
    login: $('view-login'),
    reset: $('view-reset'),
    '2fa': $('view-2fa')
  };
  let viewReady = false;

  function setView(name) {
    Object.keys(views).forEach((k) => { views[k].hidden = (k !== name); });
    // Équivalent du remontage React : chaque vue repart d'un état neuf.
    if (name === 'login') resetLoginView();
    else if (name === 'reset') resetResetView();
    // A11y : déplace le focus sur le titre de la vue (sauf au tout premier rendu,
    // pour éviter un saut de défilement non sollicité au chargement).
    if (viewReady) {
      const heading = views[name].querySelector('.ftitle');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus({ preventScroll: true });
      }
    }
    viewReady = true;
  }

  /* ════════════════════════════════════
     VUE CONNEXION
     ════════════════════════════════════ */
  const loginForm = $('login-form');
  const loginBtn = $('login-submit');
  const loginErrBan = $('login-error');
  const resetLoginEye = wireEye('login-eye', 'pwd');
  let loginLoading = false;

  function setLoginLoading(v) {
    loginLoading = v;
    loginBtn.disabled = v;
    loginBtn.innerHTML = v
      ? SPINNER + '<span>' + t('Connexion en cours…') + '</span>'
      : t('Se connecter');
  }

  function showLoginError(msg) {
    $('login-error-text').textContent = msg;
    loginErrBan.hidden = false;
  }

  function resetLoginView() {
    $('pwd').value = '';
    $('remember').checked = false;
    loginErrBan.hidden = true;
    setLoginLoading(false);
    resetLoginEye();
  }

  loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (loginLoading) return;
    loginErrBan.hidden = true;
    const email = $('email').value;
    const pwd = $('pwd').value;
    if (!email || !pwd) {
      showLoginError(t('Veuillez remplir tous les champs.'));
      return;
    }
    setLoginLoading(true);
    fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, password: pwd })
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          // Identifiants invalides : message FR clair (pas le détail JWT anglais brut)
          throw new Error(res.status === 401
            ? t('Email ou mot de passe incorrect.')
            : (data.detail || t('Email ou mot de passe incorrect.')));
        }
        return data;
      })
      .then((data) => {
        if (data.require_2fa) {
          window.pending2faEmail = data.email;
          setView('2fa');
          return;
        }
        if (!data.access) throw new Error(t('Réponse de connexion invalide.'));
        localStorage.setItem('aoceda_access_token', data.access);
        // « Se souvenir de moi » : conserve le refresh (session longue via /refresh/).
        // Sinon, pas de refresh persistant → la session expire avec l'access (30 min).
        // Dans l'app native, la session doit TOUJOURS persister jusqu'à déconnexion
        // explicite (comme toute app mobile) : on force la conservation du refresh,
        // indépendamment de la case à cocher.
        if ((isNativeApp || $('remember').checked) && data.refresh) {
          localStorage.setItem('aoceda_refresh_token', data.refresh);
        } else {
          localStorage.removeItem('aoceda_refresh_token');
        }
        // Redirection selon le RÔLE réel de l'utilisateur (pas une cible fixe).
        return fetch('/api/users/me/', { headers: { 'Authorization': 'Bearer ' + data.access } })
          .then((r) => (r.ok ? r.json() : null))
          .then((me) => {
            const role = (me && me.role === 'technicien') ? 'technicien' : 'client';
            // Mis en cache pour le rebond automatique de /auth/ au prochain lancement
            // de l'app (voir le script en tête de aoceda-auth.html) : évite un aller-retour
            // réseau juste pour savoir vers quel espace rediriger un utilisateur déjà connecté.
            localStorage.setItem('aoceda_user_role', role);
            saveNativeSession(data.access, localStorage.getItem('aoceda_refresh_token'), role);
            window.location.href = (role === 'technicien') ? '/technicien/' : '/dashboard/';
          });
      })
      .catch((err) => {
        showLoginError(err.message);
        setLoginLoading(false);
      });
  });

  $('login-goto-reset').addEventListener('click', () => setView('reset'));

  /* ════════════════════════════════════
     VUE 2FA
     ════════════════════════════════════ */
  const tfaForm = $('tfa-form');
  const tfaBtn = $('tfa-submit');
  const tfaErr = $('tfa-error');
  let tfaLoading = false;

  function showTfaError(msg) {
    $('tfa-error-text').textContent = msg;
    tfaErr.hidden = false;
  }

  $('tfa-back-login').addEventListener('click', () => setView('login'));

  if (tfaForm) {
    tfaForm.addEventListener('submit', (e) => {
      e.preventDefault();
      if (tfaLoading) return;
      tfaErr.hidden = true;
      const code = $('tfa-code').value;
      if (!code) return;
      
      tfaLoading = true;
      tfaBtn.innerHTML = SPINNER + '<span>' + t('Vérification…') + '</span>';
      tfaBtn.disabled = true;

      fetch('/api/auth/login/2fa/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: window.pending2faEmail, code })
      })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Code invalide.');
        return data;
      })
      .then((data) => {
        localStorage.setItem('aoceda_access_token', data.access);
        if ((isNativeApp || $('remember').checked) && data.refresh) {
          localStorage.setItem('aoceda_refresh_token', data.refresh);
        } else {
          localStorage.removeItem('aoceda_refresh_token');
        }
        return fetch('/api/users/me/', { headers: { 'Authorization': 'Bearer ' + data.access } })
          .then((r) => (r.ok ? r.json() : null))
          .then((me) => {
            const role = (me && me.role === 'technicien') ? 'technicien' : 'client';
            localStorage.setItem('aoceda_user_role', role);
            saveNativeSession(data.access, localStorage.getItem('aoceda_refresh_token'), role);
            window.location.href = (role === 'technicien') ? '/technicien/' : '/dashboard/';
          });
      })
      .catch((err) => {
        tfaLoading = false;
        tfaBtn.innerHTML = t('Vérifier');
        tfaBtn.disabled = false;
        showTfaError(t(err.message));
      });
    });
  }

  /* ════════════════════════════════════
     VUE RÉINITIALISATION (A → B → C → C_done)
     ════════════════════════════════════ */
  let resetLoadingA = false;
  let resetLoadingC = false;
  let resetEmail = '';   // e-mail saisi à l'étape A (réutilisé à la confirmation)
  let resetToken = '';   // token de réinitialisation (dev : renvoyé par l'API ; prod : lien e-mail)

  /* Étape A, envoi du lien */
  function updateSendBtn() {
    $('reset-send').disabled = resetLoadingA || !$('r-email').value;
  }

  function setResetLoadingA(v) {
    resetLoadingA = v;
    $('reset-send').innerHTML = v
      ? SPINNER + '<span>' + t('Envoi en cours…') + '</span>'
      : t('Envoyer le lien de réinitialisation');
    updateSendBtn();
  }

  $('r-email').addEventListener('input', () => { updateSendBtn(); hideResetErrorA(); });

  $('reset-form-email').addEventListener('submit', (e) => {
    e.preventDefault();
    const email = $('r-email').value;
    if (!email) return;
    hideResetErrorA();
    setResetLoadingA(true);
    // Demande RÉELLE de réinitialisation. La réponse est volontairement générique
    // (ne révèle pas si le compte existe). En dev, l'API renvoie `dev_token`.
    fetch('/api/auth/password/reset/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    })
      .then(async (res) => { const d = await res.json().catch(() => ({})); return { ok: res.ok, d }; })
      .then(({ ok, d }) => {
        setResetLoadingA(false);
        if (!ok) {
          // Aucun email n'a été envoyé → on RESTE à l'étape A et on le dit honnêtement
          // (jamais de faux « Email envoyé »). L'erreur s'affiche SUR l'étape A.
          showResetErrorA((d && d.detail) || t("Impossible d'envoyer le lien pour le moment. Réessayez."));
          return;
        }
        // 200 générique (ne révèle pas si le compte existe, anti-énumération).
        resetEmail = email;
        if (d && d.dev_token) resetToken = d.dev_token;
        $('reset-email-badge').innerHTML = esc(email);
        $('reset-stepA').hidden = true;
        $('reset-stepB').hidden = false;
      })
      .catch(() => {
        setResetLoadingA(false);
        showResetErrorA(t('Erreur réseau. Vérifiez votre connexion et réessayez.'));
      });
  });

  // Erreur de l'étape A (demande d'email) : bandeau dédié DANS #reset-stepA
  // (l'ancien #reset-error vit dans #reset-stepC, masqué à l'étape A → invisible).
  function showResetErrorA(msg) {
    const t = $('reset-error-A-text');
    const box = $('reset-error-A');
    if (t) t.textContent = msg;
    if (box) box.hidden = false;
  }
  function hideResetErrorA() {
    const box = $('reset-error-A');
    if (box) box.hidden = true;
  }

  // Erreur de l'étape C (nouveau mot de passe) : bandeau #reset-error de l'étape C.
  function showResetError(msg) {
    const el = $('reset-error');
    if (el) { el.querySelector('span').textContent = msg; el.hidden = false; }
  }

  /* Étape C, nouveau mot de passe */
  const RESET_RULES = [
    { key: 'len', txt: 'Minimum 8 caractères', ok: (p) => p.length >= 8 },
    { key: 'upper', txt: 'Au moins 1 majuscule', ok: (p) => /[A-Z]/.test(p) },
    { key: 'digit', txt: 'Au moins 1 chiffre', ok: (p) => /[0-9]/.test(p) }
  ];

  function renderRules(pwd) {
    RESET_RULES.forEach((r) => {
      const el = document.querySelector('#np-rules .rule[data-rule="' + r.key + '"]');
      const ok = r.ok(pwd);
      el.className = 'rule' + (ok ? ' v' : '');
      el.innerHTML = (ok ? ICON_CHECK : ICON_CIRCLE) + t(r.txt);
    });
  }

  function setResetLoadingC(v) {
    resetLoadingC = v;
    $('reset-confirm').innerHTML = v
      ? SPINNER + '<span>' + t('Mise à jour…') + '</span>'
      : t('Confirmer le nouveau mot de passe');
    updateResetC();
  }

  function updateResetC() {
    const np = $('np').value;
    const cp = $('cp').value;
    renderStrength($('np-str'), np);
    renderRules(np);
    const mismatch = cp && cp !== np;
    $('cp').classList.toggle('ferr', !!mismatch);
    $('cp-err').hidden = !mismatch;
    $('reset-confirm').disabled = resetLoadingC || !np || np !== cp;
  }

  $('np').addEventListener('input', updateResetC);
  $('cp').addEventListener('input', updateResetC);

  $('reset-form-pwd').addEventListener('submit', (e) => {
    e.preventDefault();
    if ($('np').value !== $('cp').value) return;
    if (!resetToken || !resetEmail) {
      showResetError(t("Lien de réinitialisation manquant ou expiré. Recommencez la procédure « Mot de passe oublié »."));
      return;
    }
    setResetLoadingC(true);
    // Confirmation RÉELLE : applique le nouveau mot de passe via le token.
    fetch('/api/auth/password/reset/confirm/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: resetEmail, token: resetToken, new_password: $('np').value })
    })
      .then(async (res) => {
        const d = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = (d.new_password && d.new_password[0]) || d.detail
            || (d.token && t('Lien invalide ou expiré.')) || t('Échec de la réinitialisation.');
          throw new Error(msg);
        }
        return d;
      })
      .then(() => {
        setResetLoadingC(false);
        $('reset-form-pwd').hidden = true;
        $('reset-done').hidden = false;
      })
      .catch((err) => {
        setResetLoadingC(false);
        showResetError(err.message);
      });
  });

  // (Le bouton dev « Simuler le lien email » a été retiré : en production,
  //  l'utilisateur ouvre l'étape C via le lien ?reset_token=… reçu par email.)

  function resetResetView() {
    $('r-email').value = '';
    setResetLoadingA(false);
    $('np').value = '';
    $('cp').value = '';
    setResetLoadingC(false);
    $('reset-stepA').hidden = false;
    $('reset-stepB').hidden = true;
    $('reset-stepC').hidden = true;
    $('reset-form-pwd').hidden = false;
    $('reset-done').hidden = true;
  }

  $('reset-back-login').addEventListener('click', () => setView('login'));
  $('resetB-back-login').addEventListener('click', () => setView('login'));
  $('reset-done-login').addEventListener('click', () => setView('login'));

  /* ════════════════════════════════════
     INITIALISATION
     ════════════════════════════════════ */
  applyTheme();
  const params = new URLSearchParams(window.location.search);
  // Lien reçu par e-mail (?reset_token=...&email=...) : ouvre directement l'étape
  // « nouveau mot de passe » avec le token pré-rempli.
  const urlToken = params.get('reset_token');
  if (urlToken) {
    setView('reset');
    resetToken = urlToken;
    resetEmail = params.get('email') || '';
    $('reset-stepA').hidden = true;
    $('reset-stepB').hidden = true;
    $('reset-stepC').hidden = false;
  } else {
    // Plus d'auto-inscription : le Visiteur arrive toujours sur la connexion.
    setView('login');
  }

  // Traduction Complète (Langue Dynamique) si active
  const activeLang = localStorage.getItem('aoceda-lang');
  if (activeLang === 'en' && typeof window.AOCEDA_applyTranslations === 'function') {
    window.AOCEDA_applyTranslations();
  }
})();
