/* ════════════════════════════════════════════════════════════
   AOCEDA — Page d'authentification (JavaScript vanilla, ES2020)
   Architecture : Django Templates + AJAX (fetch)
   Le squelette HTML vit dans templates/aoceda-auth.html ;
   ce fichier ne contient que la logique (état, AJAX, bascules).
   ════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── Helpers ── */
  const $ = (id) => document.getElementById(id);

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
  let theme = localStorage.getItem('aoceda-theme') || 'light';

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('aoceda-theme', theme);
    const btn = $('theme-toggle');
    btn.innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
    btn.setAttribute('aria-label', theme === 'light' ? 'Mode sombre' : 'Mode clair');
  }

  $('theme-toggle').addEventListener('click', () => {
    theme = theme === 'light' ? 'dark' : 'light';
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
    lbl.textContent = STR_LBLS[s];
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

  /* Message d'erreur sous un champ (classe .ferr + .ferr-msg) */
  function setFieldError(inputId, msg) {
    const input = $(inputId);
    const errEl = $(inputId + '-err');
    if (msg) {
      input.classList.add('ferr');
      errEl.querySelector('span').textContent = msg;
      errEl.hidden = false;
    } else {
      input.classList.remove('ferr');
      errEl.hidden = true;
    }
  }

  /* ════════════════════════════════════
     BASCULE ENTRE LES VUES
     ════════════════════════════════════ */
  const views = {
    login: $('view-login'),
    register: $('view-register'),
    reset: $('view-reset')
  };
  let viewReady = false;

  function setView(name) {
    Object.keys(views).forEach((k) => { views[k].hidden = (k !== name); });
    // Équivalent du remontage React : chaque vue repart d'un état neuf.
    if (name === 'login') resetLoginView();
    else if (name === 'register') resetRegisterView();
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
      ? SPINNER + '<span>Connexion en cours…</span>'
      : 'Se connecter';
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
      showLoginError('Veuillez remplir tous les champs.');
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
            ? 'Email ou mot de passe incorrect.'
            : (data.detail || 'Email ou mot de passe incorrect.'));
        }
        return data;
      })
      .then((data) => {
        if (!data.access) throw new Error('Réponse de connexion invalide.');
        localStorage.setItem('aoceda_access_token', data.access);
        // « Se souvenir de moi » : conserve le refresh (session longue via /refresh/).
        // Sinon, pas de refresh persistant → la session expire avec l'access (30 min).
        if ($('remember').checked && data.refresh) {
          localStorage.setItem('aoceda_refresh_token', data.refresh);
        } else {
          localStorage.removeItem('aoceda_refresh_token');
        }
        // Redirection selon le RÔLE réel de l'utilisateur (pas une cible fixe).
        return fetch('/api/users/me/', { headers: { 'Authorization': 'Bearer ' + data.access } })
          .then((r) => (r.ok ? r.json() : null))
          .then((me) => {
            window.location.href = (me && me.role === 'technicien') ? '/technicien/' : '/dashboard/';
          });
      })
      .catch((err) => {
        showLoginError(err.message);
        setLoginLoading(false);
      });
  });

  $('login-goto-register').addEventListener('click', () => setView('register'));
  $('login-goto-reset').addEventListener('click', () => setView('reset'));

  /* ════════════════════════════════════
     VUE INSCRIPTION (2 étapes)
     ════════════════════════════════════ */
  const resetRegEye = wireEye('reg-eye', 'reg-pwd');
  const REG_FIELDS_S1 = ['prenom', 'nom', 'reg-email', 'reg-pwd', 'confirm'];

  function setRegStep(n) {
    $('reg-step1').hidden = (n !== 1);
    $('reg-step2').hidden = (n !== 2);
    $('reg-title').textContent = n === 1 ? 'Créer un compte' : 'Configuration du foyer';
    $('reg-sdot1').className = 'sdot ' + (n === 1 ? 'cur' : 'done');
    $('reg-sdot2').className = 'sdot ' + (n === 2 ? 'cur' : 'todo');
  }

  function clearRegErrors() {
    REG_FIELDS_S1.forEach((id) => setFieldError(id, null));
  }

  function validateStep1() {
    const e = {};
    if (!$('prenom').value.trim()) e.prenom = 'Requis';
    if (!$('nom').value.trim()) e.nom = 'Requis';
    if (!$('reg-email').value.includes('@')) e['reg-email'] = 'Email invalide';
    if ($('reg-pwd').value.length < 8) e['reg-pwd'] = 'Minimum 8 caractères';
    if ($('reg-pwd').value !== $('confirm').value) e.confirm = 'Les mots de passe ne correspondent pas';
    REG_FIELDS_S1.forEach((id) => setFieldError(id, e[id] || null));
    return Object.keys(e).length === 0;
  }

  function checkedValue(name) {
    const el = document.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }

  function setRadio(name, value) {
    document.querySelectorAll('input[name="' + name + '"]').forEach((r) => {
      r.checked = (r.value === value);
    });
  }

  function resetRegisterView() {
    setRegStep(1);
    REG_FIELDS_S1.forEach((id) => { $(id).value = ''; });
    clearRegErrors();
    renderStrength($('reg-pwd-str'), '');
    resetRegEye();
    setRadio('log', 'Appartement');
    setRadio('amp', '15A');
    setRadio('cpt', 'Prépayé');
    $('cie').value = '';
    $('register-main').hidden = false;
    $('reg-success').hidden = true;
  }

  $('reg-pwd').addEventListener('input', () => {
    renderStrength($('reg-pwd-str'), $('reg-pwd').value);
  });

  $('reg-next').addEventListener('click', () => {
    if (validateStep1()) setRegStep(2);
  });

  $('reg-prev').addEventListener('click', () => setRegStep(1));

  function showRegError(msg) {
    const el = $('reg-error');
    if (el) { el.querySelector('span').textContent = msg; el.hidden = false; }
  }
  function clearRegError() {
    const el = $('reg-error');
    if (el) el.hidden = true;
  }

  $('reg-submit').addEventListener('click', () => {
    const prenom = $('prenom').value;
    const nom = $('nom').value;
    // Map les valeurs HTML françaises vers les clés backend
    // (le backend n'accepte que 5/10/15 A — pas de 20 A à la CIE domestique BT)
    const ampMap = { '5A': 5, '10A': 10, '15A': 15 };
    const cptMap = { 'Postpayé': 'postpaye', 'Prépayé': 'prepaye', 'Intelligent': 'postpaye' };
    const ampRaw = checkedValue('amp');
    const cptRaw = checkedValue('cpt');
    const payload = {
      email: $('reg-email').value,
      nom: `${prenom} ${nom}`,
      password: $('reg-pwd').value,
      typeLogement: checkedValue('log'),
      numeroCIE: $('cie').value,
      amperage: ampMap[ampRaw] || 10,
      typeCompteur: cptMap[cptRaw] || 'postpaye',
    };
    clearRegErrors();
    clearRegError();
    fetch('/api/auth/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const firstError = Object.values(data)[0];
          const errorMsg = Array.isArray(firstError)
            ? firstError[0]
            : (typeof firstError === 'string' ? firstError : "Erreur lors de l'inscription");
          throw new Error(errorMsg);
        }
        return data;
      })
      .then(() => {
        $('reg-success-name').innerHTML = `${esc(prenom)} ${esc(nom)}`;
        $('register-main').hidden = true;
        $('reg-success').hidden = false;
      })
      .catch((err) => {
        showRegError(err.message);
      });
  });

  $('reg-goto-login').addEventListener('click', () => setView('login'));
  $('reg-success-login').addEventListener('click', () => setView('login'));

  /* ════════════════════════════════════
     VUE RÉINITIALISATION (A → B → C → C_done)
     ════════════════════════════════════ */
  let resetLoadingA = false;
  let resetLoadingC = false;
  let resetEmail = '';   // e-mail saisi à l'étape A (réutilisé à la confirmation)
  let resetToken = '';   // token de réinitialisation (dev : renvoyé par l'API ; prod : lien e-mail)

  /* Étape A — envoi du lien */
  function updateSendBtn() {
    $('reset-send').disabled = resetLoadingA || !$('r-email').value;
  }

  function setResetLoadingA(v) {
    resetLoadingA = v;
    $('reset-send').innerHTML = v
      ? SPINNER + '<span>Envoi en cours…</span>'
      : 'Envoyer le lien de réinitialisation';
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
          showResetErrorA((d && d.detail) || "Impossible d'envoyer le lien pour le moment. Réessayez.");
          return;
        }
        // 200 générique (ne révèle pas si le compte existe — anti-énumération).
        resetEmail = email;
        if (d && d.dev_token) resetToken = d.dev_token;
        $('reset-email-badge').innerHTML = esc(email);
        $('reset-stepA').hidden = true;
        $('reset-stepB').hidden = false;
      })
      .catch(() => {
        setResetLoadingA(false);
        showResetErrorA('Erreur réseau. Vérifiez votre connexion et réessayez.');
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

  /* Étape C — nouveau mot de passe */
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
      el.innerHTML = (ok ? ICON_CHECK : ICON_CIRCLE) + r.txt;
    });
  }

  function setResetLoadingC(v) {
    resetLoadingC = v;
    $('reset-confirm').innerHTML = v
      ? SPINNER + '<span>Mise à jour…</span>'
      : 'Confirmer le nouveau mot de passe';
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
      showResetError("Lien de réinitialisation manquant ou expiré. Recommencez la procédure « Mot de passe oublié ».");
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
            || (d.token && 'Lien invalide ou expiré.') || 'Échec de la réinitialisation.';
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
    // ?mode=register : la vitrine ouvre directement l'onglet inscription
    setView(params.get('mode') === 'register' ? 'register' : 'login');
  }
})();
