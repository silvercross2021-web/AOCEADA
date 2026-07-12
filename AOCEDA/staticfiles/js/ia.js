'use strict';
const t = window.AOCEDA_T || (x => x);
/* ════════════════════════════════════════════════════════════
   AOCEDA, Assistant IA (vanilla JS, sans React)
   L'IA accède elle-même aux données du client côté serveur ;
   l'interface reste un chat épuré et plein écran.
   ════════════════════════════════════════════════════════════ */

(function () {
  const token = localStorage.getItem('aoceda_access_token');
  if (!token && window.location.pathname.indexOf('/auth/') === -1) {
    window.location.href = '/auth/';
  }
})();

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401.
   Renvoie la Response brute (les appelants lisent res.json() / res.ok). */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options);
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function logoSVG(s) {
  return `<svg width="${s}" height="${s}" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="8" fill="#C9760E"/><path d="M5 18H10L13.5 9L17.5 27L21 14L24 22L27 18H31" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

const MOON_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const SUN_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';

const SUGGESTIONS = [
  "Pourquoi ma facture a augmenté ?",
  "Comment réduire ma consommation la nuit ?",
  "Quel est mon appareil le plus consommateur ?",
  "Comment est calculée ma facture CIE ?"
];

// Quota inconnu tant que l'API n'a pas répondu → on n'affiche jamais un chiffre inventé.
const state = { quota: null, limite: null, quotaKnown: false, user: null, typing: false, depleted: false };
const $ = id => document.getElementById(id);

function nowTime() {
  const locale = (localStorage.getItem('aoceda-lang') === 'en') ? 'en-GB' : 'fr-FR';
  return new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

function renderMsgText(raw) {
  const text = String(raw);

  // 1) Blocs de code (``` ... ```), traités AVANT toute ligne
  const CODE_BLOCKS = [];
  const withoutCodeBlocks = text.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
    const idx = CODE_BLOCKS.length;
    CODE_BLOCKS.push(`<pre class="msg-code"><code>${esc(code.trim())}</code></pre>`);
    return `\x00CODE${idx}\x00`;
  });

  // 2) Traitement ligne par ligne
  const lines = withoutCodeBlocks.split('\n');
  const parts = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length) {
      parts.push(`<ul class="msg-list">${listItems.map(i => `<li>${i}</li>`).join('')}</ul>`);
      listItems = [];
    }
  };

  const inlineFormat = line => esc(line)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')        // **gras**
    .replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>'); // `code`

  lines.forEach(line => {
    // Marqueur de bloc de code → réinjecter
    if (/^\x00CODE\d+\x00$/.test(line.trim())) {
      flushList();
      const idx = parseInt(line.trim().replace(/\x00CODE(\d+)\x00/, '$1'), 10);
      parts.push(CODE_BLOCKS[idx] || '');
      return;
    }
    if (!line.trim()) {
      flushList();
      return; // ligne vide : ferme une liste éventuelle, pas de <br> superflu
    }
    // Liste à tirets (- item) ou liste à puces (* item)
    const listMatch = line.match(/^[-*]\s+(.+)/);
    if (listMatch) {
      listItems.push(inlineFormat(listMatch[1]));
      return;
    }
    // Liste numérotée (1. item)
    const numMatch = line.match(/^\d+\.\s+(.+)/);
    if (numMatch) {
      flushList();
      parts.push(`<p style="margin-bottom:4px">${inlineFormat(numMatch[1])}</p>`);
      return;
    }
    // Paragraphe normal
    flushList();
    parts.push(`<p>${inlineFormat(line)}</p>`);
  });

  flushList();
  return parts.join('');
}

/* ── Thème ── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('aoceda-theme', theme);
  $('theme-toggle').innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
}

/* ── Quota (pied de saisie) ── */
function renderQuota() {
  const inline = $('quota-inline');
  if (!inline) return;
  if (!state.quotaKnown) {
    inline.textContent = t('Quota du jour…');
    inline.classList.remove('is-low');
    return;
  }
  const q = state.quota;
  const s = q > 1 ? 's' : '';
  const lang = localStorage.getItem('aoceda-lang');
  if (lang === 'en') {
    inline.textContent = `${q} question${s} remaining today`;
  } else {
    inline.textContent = `${q} question${s} restante${s} aujourd'hui`;
  }
  inline.classList.toggle('is-low', q <= 2);
}

function renderDepleted() {
  const sug = $('suggestions');
  if (sug) sug.style.display = state.depleted ? 'none' : '';
  $('input-bar').style.display = state.depleted ? 'none' : '';
  $('quota-empty').style.display = state.depleted ? '' : 'none';
  // Numéros du bandeau « limite atteinte » = vraie limite serveur (jamais « 10 » en dur)
  if (state.depleted && state.limite != null) {
    ['qe-lim1', 'qe-lim2', 'qe-lim3'].forEach(id => { const el = $(id); if (el) el.textContent = state.limite; });
  }
}

/* ── Messages ── */
function userInitials() {
  return state.user && state.user.nom ? state.user.nom.substring(0, 2).toUpperCase() : '··';
}
function scrollToEnd() {
  const end = $('messages-end');
  if (end && end.scrollIntoView) end.scrollIntoView({ behavior: 'smooth' });
}
function appendMessage(role, text, time) {
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  const avatar = role === 'ai' ? logoSVG(15) : esc(userInitials());
  const who = role === 'ai' ? t('Assistant AOCEDA') : t('Vous');
  row.innerHTML = `<div class="msg-avatar ${role === 'ai' ? 'av-ai' : 'av-user'}">${avatar}</div>
    <div class="msg-col">
      <div class="msg-bubble ${role}">${renderMsgText(text)}</div>
      <div class="msg-time ${role === 'ai' ? 'ai-t' : ''}">${who}${time ? ' · ' + esc(time) : ''}</div>
    </div>`;
  $('messages').insertBefore(row, $('messages-end'));
  scrollToEnd();
}

function setTyping(on) {
  state.typing = on;
  const existing = $('typing-row');
  if (on && !existing) {
    const t = document.createElement('div');
    t.className = 'typing-row';
    t.id = 'typing-row';
    t.innerHTML = `<div class="msg-avatar av-ai">${logoSVG(16)}</div>
      <div class="typing-bubble"><div class="tydot"></div><div class="tydot"></div><div class="tydot"></div></div>`;
    $('messages').insertBefore(t, $('messages-end'));
    scrollToEnd();
  } else if (!on && existing) {
    existing.remove();
  }
  updateSendBtn();
}

function updateSendBtn() {
  const btn = $('send-btn');
  btn.disabled = !$('msg-input').value.trim() || state.typing;
  btn.classList.toggle('is-sending', state.typing);
  btn.setAttribute('aria-label', state.typing ? t('Envoi en cours…') : t('Envoyer le message'));
}

/* ── Bannière d'erreur (gérée hors du fil de messages) ── */
/* isNetwork=true → « Connexion interrompue » (échec réseau) ; sinon on affiche le
   message applicatif tel quel (ex. un 403 « réservé aux clients » n'est pas une coupure). */
function showError(msg, isNetwork) {
  const box = $('chat-error');
  const txt = $('chat-error-text');
  if (txt) txt.innerHTML = isNetwork ? `<strong>${t('Connexion interrompue.')}</strong> ${esc(msg)}` : esc(msg);
  if (box) box.style.display = 'flex';
}

/* Indicateur « mode dégradé » : signale honnêtement quand la réponse vient des
   conseils locaux (pas d'un vrai LLM). Affiché une seule fois, discret. */
function showFallbackNotice() {
  if (document.getElementById('ia-mode-notice')) return;
  const anchor = $('messages-end');
  if (!anchor || !anchor.parentNode) return;
  const el = document.createElement('div');
  el.id = 'ia-mode-notice';
  el.style.cssText = 'margin:8px auto;max-width:640px;font-size:12px;color:var(--tx-m);text-align:center;font-style:italic';
  el.textContent = t('Conseils basés sur vos données réelles et la grille CIE (assistant IA avancé non configuré).');
  anchor.parentNode.insertBefore(el, anchor);
}
function clearError() {
  const box = $('chat-error');
  if (box) box.style.display = 'none';
}
function autoResize() {
  const t = $('msg-input');
  t.style.height = 'auto';
  t.style.height = Math.min(t.scrollHeight, 120) + 'px';
}

function send(txt) {
  if (!txt || !txt.trim() || state.typing || state.depleted) return;
  clearError();
  const emptyState = $('chat-empty');
  if (emptyState) emptyState.remove();
  appendMessage('user', txt.trim(), nowTime());
  const ta = $('msg-input');
  ta.value = '';
  ta.style.height = 'auto';
  updateSendBtn();
  setTyping(true);

  fetchWithAuth('/api/assistant/chat/', {
    method: 'POST',
    body: JSON.stringify({ message: txt.trim() })
  })
    .then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 429) { state.depleted = true; renderDepleted(); }
        const e = new Error(data.detail || t('Une erreur est survenue.'));
        e.apiError = true; // erreur applicative (corps JSON), pas une coupure réseau
        throw e;
      }
      return data;
    })
    .then(data => {
      if (data.limite_quotidienne != null) state.limite = data.limite_quotidienne;
      state.quota = Math.max(0, (state.limite || 0) - (data.nb_requetes_aujourd_hui || 0));
      state.quotaKnown = true;
      state.depleted = state.quota <= 0;
      renderQuota();
      renderDepleted();
      appendMessage('ai', data.response, nowTime());
      if (data.mode === 'fallback') showFallbackNotice();
      setTyping(false);
    })
    .catch(err => {
      setTyping(false);
      // Quota épuisé : la bannière de quota suffit, pas d'erreur en doublon.
      if (state.depleted) return;
      // Erreur applicative (4xx) → message tel quel ; erreur réseau → « Connexion interrompue ».
      showError(err.apiError ? err.message : `${err.message} ${t('Réessayez dans un instant.')}`, !err.apiError);
    });
}

function renderSuggestions() {
  const wrap = $('suggestions');
  if (!wrap) return;
  wrap.innerHTML = '';
  SUGGESTIONS.forEach(s => {
    const translated = t(s);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sug-chip';
    btn.innerHTML = `<span>${esc(translated)}</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
    btn.addEventListener('click', () => { $('msg-input').value = translated; updateSendBtn(); send(translated); });
    wrap.appendChild(btn);
  });
}

/* ── Initialisation ── */
document.addEventListener('DOMContentLoaded', () => {
  let theme = localStorage.getItem('aoceda-theme') || 'light';
  applyTheme(theme);
  $('theme-toggle').addEventListener('click', () => {
    theme = theme === 'light' ? 'dark' : 'light';
    applyTheme(theme);
  });

  renderQuota();
  renderDepleted();
  renderSuggestions();

  const ta = $('msg-input');
  ta.addEventListener('input', () => { autoResize(); updateSendBtn(); });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(ta.value); }
  });
  const form = $('input-bar');
  if (form) form.addEventListener('submit', e => { e.preventDefault(); send(ta.value); });

  // Données utilisateur (initiales d'avatar)
  fetchWithAuth('/api/users/me/')
    .then(res => res.json())
    .then(data => {
      state.user = data;
      document.querySelectorAll('.msg-row.user .msg-avatar').forEach(el => { el.textContent = userInitials(); });
    })
    .catch(err => console.error(err));

  // Historique de conversation + quota du jour (GET : ne consomme PAS de question)
  fetchWithAuth('/api/assistant/chat/')
    .then(async res => ({ ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) }))
    .then(({ ok, status, data }) => {
      if (!ok) {
        // Accès refusé (ex. un non-client comme un technicien) → état HONNÊTE,
        // on ne laisse pas « Quota du jour… » figé et on désactive la saisie.
        const inline = $('quota-inline');
        if (status === 403) {
          if (inline) inline.textContent = (data && data.detail) || t('Assistant réservé aux clients');
          const bar = $('input-bar'); if (bar) bar.style.display = 'none';
          const sug = $('suggestions'); if (sug) sug.style.display = 'none';
        } else if (inline && !state.quotaKnown) {
          inline.textContent = t('Quota indisponible');
        }
        return;
      }
      if (data.nb_requetes_aujourd_hui !== undefined) {
        if (data.limite_quotidienne != null) state.limite = data.limite_quotidienne;
        state.quota = Math.max(0, (state.limite || 0) - data.nb_requetes_aujourd_hui);
        state.quotaKnown = true;
        state.depleted = state.quota <= 0;
        renderQuota();
        renderDepleted();
      }
      const histo = Array.isArray(data.historique_messages) ? data.historique_messages : [];
      if (histo.length) {
        const emptyState = $('chat-empty');
        if (emptyState) emptyState.remove();
        for (let i = 0; i < histo.length; i++) {
          const m = histo[i];
          if (m.content === 'AOCEDA_INIT_CHECK') {
            // Sonde interne : on saute aussi la réponse assistant qui la suit,
            // sinon un message orphelin s'affiche comme un vrai échange.
            if (histo[i + 1] && histo[i + 1].role === 'assistant') i++;
            continue;
          }
          appendMessage(m.role === 'assistant' ? 'ai' : 'user', m.content, '');
        }
        scrollToEnd();
      }
    })
    .catch(err => {
      console.error(err);
      // Quota inconnu (API injoignable) → état honnête, jamais un « 10 » fabriqué.
      const inline = $('quota-inline');
      if (inline && !state.quotaKnown) inline.textContent = t('Quota indisponible');
    });
});
